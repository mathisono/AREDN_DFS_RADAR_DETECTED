import contextlib
import io
import json
import unittest
from unittest.mock import patch

from dfs_detector import ControlCapture, main, parse_event, summarize


RADAR = (
    "Fri Oct 23 06:25:00 2026 daemon.notice hostapd: wlan0: "
    "DFS-RADAR-DETECTED freq=5660 ht_enabled=1 chan_offset=1 "
    "chan_width=2 cf1=5670 cf2=0"
)


class DetectorTests(unittest.TestCase):
    def test_explicit_report_flags_event_frequency(self):
        event = parse_event(RADAR, "test-ap")
        self.assertTrue(event["flag_channel"])
        self.assertEqual(event["reported_primary_channel"], 132)
        self.assertEqual(event["reported_frequency_mhz"], 5660)
        self.assertEqual(event["interface"], "wlan0")
        self.assertEqual(event["fields"]["cf1"], 5670)
        self.assertEqual(event["fields"]["chan_width"], 2)
        self.assertEqual(event["log_line"], RADAR)

    def test_missing_frequency_still_reports_but_does_not_guess_channel(self):
        event = parse_event("DFS-RADAR-DETECTED cf1=5670 chan=132", "test-ap")
        self.assertTrue(event["flag_channel"])
        self.assertIsNone(event["reported_frequency_mhz"])
        self.assertIsNone(event["reported_primary_channel"])

    def test_invalid_or_other_band_frequencies_not_mapped(self):
        for freq in [0, -1, 2412, 4910, 5955, 5661]:
            with self.subTest(freq=freq):
                event = parse_event(f"DFS-RADAR-DETECTED freq={freq}", "test-ap")
                self.assertIsNone(event["reported_primary_channel"])

    def test_cac_start_is_not_a_hit(self):
        event = parse_event(
            "wlan0: DFS-CAC-START freq=5660 chan=132 sec_chan=1, width=0, "
            "seg0=0, seg1=0, cac_time=60s", "test-ap"
        )
        self.assertFalse(event["flag_channel"])
        self.assertEqual(event["classification"], "cac_started")
        self.assertEqual(event["fields"]["width"], 0)

    def test_cac_result_not_counted_as_a_new_radar_report(self):
        for fields in ["success=1", "success=0", "success=0 radar_detected=1"]:
            with self.subTest(fields=fields):
                event = parse_event(f"DFS-CAC-COMPLETED freq=5660 {fields}", "test-ap")
                self.assertFalse(event["flag_channel"])

    def test_nop_and_pre_cac_expiry_not_new_hits(self):
        for kind in ["DFS-NOP-FINISHED", "DFS-PRE-CAC-EXPIRED"]:
            self.assertFalse(parse_event(f"{kind} freq=5660", "test-ap")["flag_channel"])

    def test_channel_changes_are_context_only(self):
        for kind in ["DFS-NEW-CHANNEL", "AP-CSA-FINISHED", "CTRL-EVENT-CHANNEL-SWITCH"]:
            event = parse_event(f"{kind} freq=5180", "test-ap")
            self.assertEqual(event["classification"], "channel_change")
            self.assertFalse(event["flag_channel"])

    def test_low_rates_and_generic_radar_text_not_hits(self):
        for line in [
            "tx bitrate: 7.2 MBit/s MCS 0", "radar detected: 0", "DFS disabled",
            "radar detection enabled", "tx_retries=100 tx_fail=500",
            "DFS-RADAR-DETECTED-TEST freq=5660", "NOT-DFS-RADAR-DETECTED freq=5660",
        ]:
            with self.subTest(line=line):
                self.assertIsNone(parse_event(line, "test-ap"))

    def test_repeated_backlog_not_double_counted_in_summary(self):
        event1 = parse_event(RADAR, "test-ap", "boot-1")
        event2 = parse_event(RADAR + "\n", "test-ap", "boot-1")
        report = summarize([event1, event2])
        self.assertEqual(report["unique_event_records"], 1)
        self.assertEqual(report["flagged_channels"][0]["radar_report_records"], 1)

    def test_different_nodes_and_boots_have_distinct_ids(self):
        events = [parse_event(RADAR, node, boot) for node, boot in
                  [("ap-a", "boot-1"), ("ap-b", "boot-1"), ("ap-a", "boot-2")]]
        self.assertEqual(len({event["event_id"] for event in events}), 3)

    def test_different_log_timestamps_not_deduplicated(self):
        events = [parse_event(RADAR, "test-ap"),
                  parse_event(RADAR.replace("06:25:00", "06:26:00"), "test-ap")]
        self.assertEqual(summarize(events)["flagged_channels"][0]["radar_report_records"], 2)

    def test_csa_destination_not_flagged_and_nop_does_not_erase_history(self):
        events = [parse_event(RADAR, "test-ap"),
                  parse_event("DFS-NEW-CHANNEL freq=5180", "test-ap"),
                  parse_event("DFS-NOP-FINISHED freq=5660", "test-ap")]
        report = summarize(events)
        self.assertEqual(len(report["flagged_channels"]), 1)
        self.assertEqual(report["flagged_channels"][0]["reported_primary_channel"], 132)

    def test_empty_and_context_only_logs_leave_radar_unknown(self):
        for events in [[], [parse_event("DFS-CAC-COMPLETED success=1 freq=5660", "test-ap")]]:
            self.assertEqual(summarize(events)["radar_assessment"], "unknown")

    def test_cli_summary_reads_stdin(self):
        output = io.StringIO()
        with patch("sys.stdin", io.StringIO(RADAR + "\n")), contextlib.redirect_stdout(output):
            self.assertEqual(main(["--node", "test-ap", "--summary"]), 0)
        self.assertEqual(json.loads(output.getvalue())["radar_assessment"], "reported")

    def test_cli_stream_keeps_replay_id_and_does_not_require_eof_summary(self):
        output = io.StringIO()
        with patch("sys.stdin", io.StringIO(RADAR + "\n")), contextlib.redirect_stdout(output):
            self.assertEqual(main(["--node", "test-ap"]), 0)
        event = json.loads(output.getvalue())
        self.assertEqual(event["event_id"], parse_event(RADAR, "test-ap")["event_id"])

    def test_control_priority_and_ifname_prefixes(self):
        capture = ControlCapture("test-ap", "backhaul0")
        for line, iface in [
            ("<3>DFS-RADAR-DETECTED freq=5660", "backhaul0"),
            ("IFNAME=wlan1 <3>DFS-RADAR-DETECTED freq=5500", "wlan1"),
        ]:
            with self.subTest(line=line):
                event = capture.parse(line)
                self.assertEqual(event["interface"], iface)
                self.assertEqual(event["source"], "hostapd_control")
                self.assertTrue(event["flag_channel"])
                self.assertEqual(event["log_line"], line)

    def test_repeated_live_messages_are_distinct_but_replay_is_deduplicated(self):
        capture = ControlCapture("test-ap", "wlan0")
        line = "<3>DFS-RADAR-DETECTED freq=5660"
        first, second = capture.parse(line), capture.parse(line)
        self.assertNotEqual(first["event_id"], second["event_id"])
        self.assertEqual([first["capture_sequence"], second["capture_sequence"]], [1, 2])
        replay = json.loads(json.dumps(first))
        report = summarize([first, second, replay])
        self.assertEqual(report["unique_event_records"], 2)
        self.assertEqual(report["flagged_channels"][0]["radar_report_records"], 2)

    def test_new_collector_has_new_identity(self):
        line = "<3>DFS-RADAR-DETECTED freq=5660"
        first = ControlCapture("test-ap", "wlan0").parse(line)
        second = ControlCapture("test-ap", "wlan0").parse(line)
        self.assertNotEqual(first["event_id"], second["event_id"])
        self.assertNotEqual(first["capture_id"], second["capture_id"])

    def test_live_control_requires_event_at_start_of_payload(self):
        capture = ControlCapture("test-ap", "wlan0")
        for line in ["OK\n", "PONG\n", "DFS-RADAR-DETECTED freq=5660",
                     "<3>NOTE DFS-RADAR-DETECTED freq=5660",
                     "<3>DFS-RADAR-DETECTED-TEST freq=5660"]:
            with self.subTest(line=line):
                self.assertIsNone(capture.parse(line))

    def test_control_context_does_not_flag_csa_destination(self):
        capture = ControlCapture("test-ap", "wlan0")
        events = [capture.parse(line) for line in [
            "<3>DFS-CAC-START freq=5660 cac_time=60s",
            "<3>DFS-CAC-COMPLETED success=0 freq=5660",
            "<3>DFS-NEW-CHANNEL freq=5180 chan=36 width=80",
            "<3>AP-CSA-FINISHED freq=5180",
        ]]
        report = summarize(events)
        self.assertEqual(report["radar_assessment"], "unknown")
        self.assertEqual(report["flagged_channels"], [])

    def test_summary_keeps_radio_interfaces_separate(self):
        events = [ControlCapture("test-ap", iface).parse(
            "<3>DFS-RADAR-DETECTED freq=5660") for iface in ["wlan0", "wlan1"]]
        self.assertEqual(len(summarize(events)["flagged_channels"]), 2)

    def test_control_cli_rejects_ambiguous_inputs(self):
        for extras in [["--summary"], ["input.log"], ["-"]]:
            with self.subTest(extras=extras), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    main(["--node", "test-ap", "--control-socket", "/missing",
                          "--interface", "wlan0", *extras])
                self.assertEqual(error.exception.code, 2)

    def test_control_cli_requires_interface_and_log_mode_rejects_it(self):
        for extras in [["--control-socket", "/missing"], ["--interface", "wlan0"]]:
            with self.subTest(extras=extras), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    main(["--node", "test-ap", *extras])
                self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
