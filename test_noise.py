"""Passive noise snapshots: no real radios, scans, logger or node writes."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from aredn_banner import BannerSink
from dfs_detector import parse_event
from native_banner_fixture import render_native


HERE = Path(__file__).resolve().parent
HELPER = HERE / "dfs_banner.sh"
UCODE = os.environ.get("UCODE") or shutil.which("ucode")
AREDN_SOURCE = Path(os.environ["AREDN_SOURCE"]) if os.environ.get("AREDN_SOURCE") else None


def info(channel=-2, frequency=2397, index=20):
    return (f"Interface wlan0\n\tifindex {index}\n\twdev 0x2\n\twiphy 0\n"
            f"\tchannel {channel} ({frequency} MHz), width: 20 MHz, center1: {frequency} MHz\n")


def survey(frequency=2397, noise=-103, active=True):
    return (f"Survey data from wlan0\n\tfrequency: {frequency} MHz"
            + (" [in use]" if active else "") + "\n"
            + (f"\tnoise: {noise} dBm\n" if noise is not None else ""))


class NoiseTests(unittest.TestCase):
    def setUp(self):
        self.runtime = tempfile.TemporaryDirectory(prefix="dfs-noise-test-", dir="/tmp")
        self.addCleanup(self.runtime.cleanup)
        self.root = Path(self.runtime.name)
        self.messages = self.root / "tmp/other_messages"
        self.messages.mkdir(parents=True)
        self.target = self.messages / "aredn-dfs-detection-test"
        self.other = self.messages / "unrelated"
        self.other.write_text("<strong>&#8611; Other:</strong>Keep this announcement<p>\n")
        self.bindir = self.root / "bin"
        self.bindir.mkdir()
        self.env = dict(os.environ, DFS_BANNER_DIR=str(self.messages),
                        DFS_BANNER_OBSERVED_AT="2026-10-23T10:00:00Z",
                        DFS_BANNER_NOISE_IFACE="wlan0", DFS_NOISE_FIXTURE=str(self.root),
                        PATH=str(self.bindir) + os.pathsep + os.environ.get("PATH", ""))
        # All device access is a strict mock; an unexpected command fails.
        (self.bindir / "iw").write_text('''#!/bin/sh
set -eu
printf '%s\\n' "$*" >> "$DFS_NOISE_FIXTURE/calls"
case "$*" in
    'dev wlan0 info')
        [ ! -e "$DFS_NOISE_FIXTURE/info-fail" ] || exit 1
        if [ -e "$DFS_NOISE_FIXTURE/info-seen" ]; then
            cat "$DFS_NOISE_FIXTURE/info-after"
        else
            : > "$DFS_NOISE_FIXTURE/info-seen"
            cat "$DFS_NOISE_FIXTURE/info-before"
        fi ;;
    'dev wlan0 survey dump')
        cat "$DFS_NOISE_FIXTURE/survey"
        [ ! -e "$DFS_NOISE_FIXTURE/survey-fail" ] ;;
    *) exit 90 ;;
esac
''')
        (self.bindir / "iw").chmod(0o700)
        self.configure(info(), survey(2387, -70, False) + survey())

    def configure(self, before, readings, after=None):
        (self.root / "info-before").write_text(before)
        (self.root / "info-after").write_text(before if after is None else after)
        (self.root / "survey").write_text(readings)
        for name in ["info-seen", "info-fail", "survey-fail", "calls"]:
            (self.root / name).unlink(missing_ok=True)

    def invoke(self, *args, shell=None):
        result = subprocess.run([*(shell or ["/bin/sh"]), str(HELPER), *args],
                                env=self.env, text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        return self.target.read_text()

    def test_demo_uses_current_not_first_survey_and_keeps_simulation_separate(self):
        text = self.invoke("demo", "fixture-ap")
        self.assertIn("SIMULATED", text)
        self.assertIn("channel 132 (5660 MHz)", text)
        self.assertIn("Channel noise: -103 dBm - channel -2 (2397 MHz), wlan0", text)
        self.assertNotIn("-70 dBm", text)
        self.assertIn("Real radio reading; separate from the simulated radar report", text)
        self.assertRegex(text, r"Read \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z; source iw survey")
        self.assertEqual((self.root / "calls").read_text().splitlines(),
                         ["dev wlan0 info", "dev wlan0 survey dump", "dev wlan0 info"])
        self.assertIn("Keep this announcement", self.other.read_text())
        self.assertEqual(len(text.splitlines()), 1)

    def test_matching_report_noise_is_still_a_post_report_snapshot(self):
        self.configure(info(132, 5660), survey(5180, -70, False) + survey(5660, -97))
        text = self.invoke("report", "fixture-ap", "wlan0", "5660", "hostapd_cli")
        self.assertIn("Channel noise: -97 dBm - channel 132 (5660 MHz)", text)
        self.assertIn("Read after the report, not a radar-pulse measurement", text)

    def test_channel_switch_does_not_reuse_cached_radar_channel_noise(self):
        self.configure(info(36, 5180), survey(5660, -41, False) + survey(5180, -99))
        text = self.invoke("report", "fixture-ap", "wlan0", "5660", "hostapd_cli")
        self.assertIn("channel 132 (5660 MHz)", text)
        self.assertIn("Channel noise: -99 dBm - channel 36 (5180 MHz)", text)
        self.assertNotIn("-41 dBm", text)
        self.assertIn("Not a measurement of the reported radar channel/interface", text)

    def test_mismatched_interface_and_unknown_event_frequency_are_not_correlated(self):
        for iface, frequency in [("wlan1", "2397"), ("wlan0", "unknown")]:
            with self.subTest(iface=iface, frequency=frequency):
                self.configure(info(), survey())
                text = self.invoke("report", "ap", iface, frequency, "hostapd_cli")
                self.assertIn("Not a measurement of the reported radar channel/interface", text)

    def test_absent_ambiguous_invalid_or_off_channel_noise_is_unavailable_not_zero(self):
        cases = ["", survey(noise=None), survey(active=False), survey(2412),
                 survey() + survey(), survey(noise="<b>-103</b>"), survey(noise=0),
                 survey(noise=-151), survey(noise=42), survey(noise="-103\nnoise: -99"),
                 survey() + survey(2412)]
        for readings in cases:
            with self.subTest(readings=readings):
                self.configure(info(), readings)
                text = self.invoke("report", "ap", "wlan0", "5660", "hostapd_cli")
                self.assertIn("Radar reported", text)
                self.assertIn("Channel noise: unavailable", text)
                self.assertNotIn("dBm", text)

    def test_channel_or_interface_change_during_read_invalidates_snapshot(self):
        for after in [info(36, 5180), info(index=21), ""]:
            with self.subTest(after=after):
                self.configure(info(), survey(), after)
                self.assertIn("Channel noise: unavailable", self.invoke("demo", "ap"))

    def test_read_failure_does_not_drop_radar_report_or_trust_partial_output(self):
        for failure in ["info-fail", "survey-fail"]:
            with self.subTest(failure=failure):
                self.configure(info(), survey())
                (self.root / failure).touch()
                text = self.invoke("report", "ap", "wlan0", "5660", "hostapd_cli")
                self.assertIn("Radar reported", text)
                self.assertIn("Channel noise: unavailable", text)

    def test_no_opt_in_or_clear_never_queries_radio(self):
        self.env["DFS_BANNER_NOISE_IFACE"] = ""
        self.assertIn("Channel noise: not sampled", self.invoke("demo", "ap"))
        self.assertFalse((self.root / "calls").exists())
        self.env["DFS_BANNER_NOISE_IFACE"] = "wlan0"
        result = subprocess.run(["sh", str(HELPER), "clear"], env=self.env, capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.assertFalse((self.root / "calls").exists())

    def test_invalid_interface_does_not_execute_or_replace_banner(self):
        original = self.invoke("demo", "ap")
        for iface in ["wlan0;false", "wlan0\nspoof", "<b>wlan0</b>", "x" * 16]:
            with self.subTest(iface=iface):
                self.env["DFS_BANNER_NOISE_IFACE"] = iface
                result = subprocess.run(["sh", str(HELPER), "demo", "ap"],
                                        env=self.env, capture_output=True, timeout=5)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.target.read_text(), original)

    def test_python_remote_log_sink_cannot_sample_the_workstation_radio(self):
        with patch.dict(os.environ, self.env):
            event = parse_event("hostapd: wlan0: DFS-RADAR-DETECTED freq=5660", "remote-ap")
            self.assertTrue(BannerSink(self.messages).emit(event))
        self.assertIn("Channel noise: not sampled", self.target.read_text())
        self.assertFalse((self.root / "calls").exists())

    def test_native_action_samples_its_actual_interface_only_for_radar(self):
        logger = self.bindir / "logger"
        logger.write_text("#!/bin/sh\nexit 0\n")
        logger.chmod(0o700)
        self.env.update(DFS_BANNER_HELPER=str(HELPER), DFS_NODE_NAME="fixture-ap",
                        DFS_BANNER_NOISE_IFACE="wrong-radio")
        for event in ["DFS-CAC-START", "DFS-RADAR-DETECTED"]:
            result = subprocess.run(["sh", str(HERE / "dfs_action.sh"), "wlan0", event, "freq=5660"],
                                    env=self.env, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            if event == "DFS-CAC-START":
                self.assertFalse((self.root / "calls").exists())
        self.assertIn("Channel noise: -103 dBm", self.target.read_text())

    @unittest.skipUnless(shutil.which("busybox"), "BusyBox not installed")
    def test_busybox_ash_and_awk_parse_active_channel_noise(self):
        busybox = shutil.which("busybox")
        for name in ["awk", "date", "sed", "mkdir", "mktemp", "chmod", "mv", "rm", "rmdir", "cat"]:
            (self.bindir / name).symlink_to(busybox)
        self.env["PATH"] = str(self.bindir)
        text = self.invoke("demo", "ap", shell=[busybox, "ash"])
        self.assertIn("Channel noise: -103 dBm - channel -2 (2397 MHz)", text)

    @unittest.skipUnless(UCODE and AREDN_SOURCE and AREDN_SOURCE.exists(), "native reader/template unavailable")
    def test_exact_native_reader_and_template_render_noise_and_other_announcements(self):
        self.invoke("demo", "ap")
        rendered = render_native(UCODE, AREDN_SOURCE, self.root)
        self.assertIn("Channel noise: -103 dBm", rendered["html"])
        self.assertIn("Real radio reading; separate from the simulated radar report", rendered["html"])
        self.assertIn("Keep this announcement", rendered["html"])


if __name__ == "__main__":
    unittest.main()
