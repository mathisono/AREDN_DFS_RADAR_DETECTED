"""Python-free node input fixtures; no router, ubus daemon or syslog writes."""

import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from dfs_detector import UbusCapture, main, parse_event, summarize


SCRIPT = Path(__file__).with_name("dfs_action.sh")
RADAR_ARGS = ["DFS-RADAR-DETECTED", "freq=5660", "ht_enabled=1",
              "chan_offset=1", "chan_width=2", "cf1=5670", "cf2=0"]
UBUS_RADAR = '{ "radar-detected": {"frequency":5660,"width":2,"center1":5670,"center2":0} }'


class ActionRelayTests(unittest.TestCase):
    def setUp(self):
        self.runtime = tempfile.TemporaryDirectory(prefix="dfs-action-test-", dir="/tmp")
        self.addCleanup(self.runtime.cleanup)
        self.directory = Path(self.runtime.name)
        self.log = self.directory / "logger.jsonl"
        logger = self.directory / "logger"
        logger.write_text(
            f"#!{sys.executable}\n"
            "import json, os, sys\n"
            "with open(os.environ['DFS_TEST_LOG'], 'a') as sink:\n"
            "    sink.write(json.dumps(sys.argv[1:]) + '\\n')\n"
            "sys.exit(int(os.environ.get('DFS_TEST_LOGGER_EXIT', '0')))\n"
        )
        logger.chmod(0o700)
        self.env = dict(os.environ, DFS_TEST_LOG=str(self.log),
                        PATH=str(self.directory) + os.pathsep + os.environ.get("PATH", ""))

    def run_action(self, args, shell=None):
        return subprocess.run([*(shell or ["/bin/sh"]), str(SCRIPT), *args],
                              env=self.env, text=True, capture_output=True, timeout=3)

    def logger_calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def parse_last(self):
        call = self.logger_calls()[-1]
        # Actual script output, wrapped in a representative OpenWrt log prefix.
        return parse_event("Fri Oct 23 08:00:00 2026 daemon.notice hostapd-dfs: "
                           + call[-1], "test-ap", "boot-fixture")

    def test_full_fields_survive_sh_and_busybox_ash_to_python(self):
        shells = [["/bin/sh"]]
        if shutil.which("busybox"):
            shells.append([shutil.which("busybox"), "ash"])
        for shell in shells:
            with self.subTest(shell=shell):
                result = self.run_action(["backhaul0", *RADAR_ARGS], shell=shell)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertEqual(self.logger_calls()[-1][:4],
                                 ["-t", "hostapd-dfs", "-p", "daemon.notice"])
                event = self.parse_last()
                self.assertTrue(event["flag_channel"])
                self.assertEqual(event["interface"], "backhaul0")
                self.assertEqual(event["source"], "hostapd_cli_log")
                self.assertEqual(event["reported_primary_channel"], 132)
                self.assertEqual(event["reported_frequency_mhz"], 5660)
                self.assertEqual(event["fields"]["cf1"], 5670)
                self.assertEqual(event["fields"]["chan_width"], 2)

    def test_lifecycle_and_switch_context_relay_but_never_flag_radar(self):
        for kind in ["DFS-CAC-START", "DFS-CAC-COMPLETED", "DFS-NOP-FINISHED",
                     "DFS-PRE-CAC-EXPIRED", "DFS-NEW-CHANNEL", "AP-CSA-FINISHED",
                     "CTRL-EVENT-CHANNEL-SWITCH"]:
            with self.subTest(kind=kind):
                result = self.run_action(["wlan0", kind, "freq=5180"])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.logger_calls()[-1][3], "daemon.info")
                self.assertFalse(self.parse_last()["flag_channel"])

    def test_exact_tokens_ignore_lookalikes_and_non_dfs_events(self):
        for kind in ["DFS-RADAR-DETECTED-TEST", "NOT-DFS-RADAR-DETECTED",
                     "AP-STA-CONNECTED", "NOTE"]:
            with self.subTest(kind=kind):
                self.assertEqual(self.run_action(["wlan0", kind, "freq=5660"]).returncode, 0)
        self.assertEqual(self.logger_calls(), [])

    def test_bad_arguments_cannot_inject_log_lines(self):
        for args in [[], ["wlan0"], ["bad iface", *RADAR_ARGS],
                     ["wlan0\nIFNAME=wlan1", *RADAR_ARGS],
                     ["wlan0", *RADAR_ARGS, "extra=1\nDFS-RADAR-DETECTED freq=5180"],
                     ["wlan0", *RADAR_ARGS, "extra=1\rbad"]]:
            with self.subTest(args=args):
                self.assertEqual(self.run_action(args).returncode, 2)
        self.assertEqual(self.logger_calls(), [])

    def test_shell_metacharacters_remain_literal_data(self):
        marker = self.directory / "must-not-exist"
        extra = f"note=$(touch {marker});`touch {marker}`"
        result = self.run_action(["wlan0", *RADAR_ARGS, extra])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists())
        self.assertIn(extra, self.logger_calls()[-1][-1])

    def test_logger_failure_is_not_suppressed_by_action(self):
        self.env["DFS_TEST_LOGGER_EXIT"] = "7"
        self.assertEqual(self.run_action(["wlan0", *RADAR_ARGS]).returncode, 7)

    def test_distinct_action_invocations_with_same_timestamp_keep_identity(self):
        events = []
        for _ in range(2):
            self.assertEqual(self.run_action(["wlan0", *RADAR_ARGS]).returncode, 0)
            events.append(self.parse_last())
        self.assertNotEqual(events[0]["relay_action_pid"], events[1]["relay_action_pid"])
        self.assertNotEqual(events[0]["event_id"], events[1]["event_id"])
        self.assertEqual(summarize([*events, events[0]])["unique_event_records"], 2)

    def test_relay_only_cli_avoids_counting_native_and_relay_copy(self):
        self.assertEqual(self.run_action(["wlan0", *RADAR_ARGS]).returncode, 0)
        relay = self.parse_last()["log_line"]
        native = "hostapd: wlan0: " + " ".join(RADAR_ARGS)
        output = io.StringIO()
        with patch("sys.stdin", io.StringIO(native + "\n" + relay + "\n")), \
                contextlib.redirect_stdout(output):
            self.assertEqual(main(["--node", "test-ap", "--relay-only", "--summary"]), 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report["unique_event_records"], 1)
        self.assertEqual(report["flagged_channels"][0]["radar_report_records"], 1)


class NativeUbusTests(unittest.TestCase):
    def capture(self):
        return UbusCapture("test-ap", "hostapd.wlan0", "boot-fixture")

    def test_native_radar_fields_are_preserved_without_center_substitution(self):
        event = self.capture().parse(UBUS_RADAR)
        self.assertEqual(event["source"], "ubus_subscription")
        self.assertEqual(event["ubus_object"], "hostapd.wlan0")
        self.assertEqual(event["interface"], "wlan0")
        self.assertEqual(event["reported_frequency_mhz"], 5660)
        self.assertEqual(event["reported_primary_channel"], 132)
        self.assertEqual(event["fields"]["center1"], 5670)
        self.assertEqual(event["fields"]["width"], 2)
        self.assertTrue(event["flag_channel"])

    def test_ubus_channel_switch_is_not_radar_even_with_extra_claims(self):
        event = self.capture().parse(json.dumps({"channel-switch": {
            "ifname": "wlan0", "freq": 5180, "dfs": 1, "radar_detected": True}}))
        self.assertEqual(event["reported_primary_channel"], 36)
        self.assertFalse(event["flag_channel"])
        self.assertEqual(summarize([event])["radar_assessment"], "unknown")

    def test_missing_frequency_never_guesses_from_center_or_wrong_key(self):
        event = self.capture().parse('{"radar-detected":{"center1":5670,"freq":5180}}')
        self.assertTrue(event["flag_channel"])
        self.assertIsNone(event["reported_frequency_mhz"])
        self.assertIsNone(event["reported_primary_channel"])

    def test_other_bands_or_invalid_frequencies_never_mapped_as_5ghz(self):
        for freq in [0, -1, 2412, 4910, 5955, 5661]:
            with self.subTest(freq=freq):
                event = self.capture().parse(json.dumps({"radar-detected": {"frequency": freq}}))
                self.assertIsNone(event["reported_primary_channel"])

    def test_unrelated_notifications_and_blank_lines_are_not_hits(self):
        for line in ["", "\n", '{"assoc":{"radar-detected":1}}',
                     '{"radar-detected-test":{"frequency":5660}}']:
            with self.subTest(line=line):
                self.assertIsNone(self.capture().parse(line))

    def test_invalid_frames_and_frequency_types_fail_visibly(self):
        for line in ["not JSON", '{"radar-detected":', "[]", "{}",
                     '{"radar-detected":{},"channel-switch":{}}',
                     '{"radar-detected":"freq=5660"}',
                     '{"radar-detected":{"frequency":true}}',
                     '{"radar-detected":{"frequency":"5660"}}',
                     " " * 65537]:
            with self.subTest(line=line[:100]):
                with self.assertRaises(ValueError):
                    self.capture().parse(line)

    def test_subscription_identity_must_be_single_object_and_match_payload(self):
        for name in ["hostapd.*", "hostapd", "hostapd.wlan0 hostapd.wlan1", "network.wlan0"]:
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    UbusCapture("test-ap", name)
        with self.assertRaisesRegex(ValueError, "differs"):
            self.capture().parse('{"channel-switch":{"ifname":"wlan1","freq":5180}}')

    def test_identical_notifications_are_distinct_and_saved_ids_deduplicate(self):
        capture = self.capture()
        events = [capture.parse(UBUS_RADAR), capture.parse(UBUS_RADAR)]
        self.assertNotEqual(events[0]["event_id"], events[1]["event_id"])
        self.assertEqual([e["capture_sequence"] for e in events], [1, 2])
        replay = json.loads(json.dumps(events[0]))
        self.assertEqual(summarize([*events, replay])["unique_event_records"], 2)

    def test_native_ubus_cli_stream_and_summary(self):
        for summary in [False, True]:
            output = io.StringIO()
            with self.subTest(summary=summary), \
                    patch("sys.stdin", io.StringIO((UBUS_RADAR + "\n") * 2)), \
                    contextlib.redirect_stdout(output):
                args = ["--node", "test-ap", "--ubus-object", "hostapd.wlan0"]
                self.assertEqual(main(args + (["--summary"] if summary else [])), 0)
            if summary:
                self.assertEqual(json.loads(output.getvalue())["flagged_channels"][0]["radar_report_records"], 2)
            else:
                events = [json.loads(line) for line in output.getvalue().splitlines()]
                self.assertEqual(len(events), 2)
                self.assertEqual(events[0]["source"], "ubus_subscription")

    def test_cli_modes_are_exclusive(self):
        for args in [["--ubus-object", "hostapd.wlan0", "--relay-only"],
                     ["--ubus-object", "hostapd.wlan0", "--control-socket", "/absent"],
                     ["--relay-only", "--control-socket", "/absent"]]:
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    main(["--node", "test-ap", *args])
                self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
