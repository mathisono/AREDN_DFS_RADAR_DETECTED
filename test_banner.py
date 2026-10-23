"""Detection-to-native-message fixtures; no production node or announcement."""

import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from aredn_banner import BannerSink
from dfs_detector import ControlCapture, UbusCapture, main, parse_event
from native_banner_fixture import render_native


HERE = Path(__file__).resolve().parent
HELPER = HERE / "dfs_banner.sh"
UCODE = os.environ.get("UCODE") or shutil.which("ucode")
AREDN_SOURCE = Path(os.environ["AREDN_SOURCE"]) if os.environ.get("AREDN_SOURCE") else None
RADAR = "hostapd: wlan0: DFS-RADAR-DETECTED freq=5660 chan_width=2 cf1=5670 cf2=0"


class BannerTests(unittest.TestCase):
    def setUp(self):
        self.runtime = tempfile.TemporaryDirectory(prefix="dfs-banner-test-", dir="/tmp")
        self.addCleanup(self.runtime.cleanup)
        self.root = Path(self.runtime.name)
        self.messages = self.root / "tmp/other_messages"
        self.messages.mkdir(parents=True)
        self.target = self.messages / "aredn-dfs-detection-test"
        self.other = self.messages / "another-addon"
        self.other.write_text("<strong>&#8611; Another add-on:</strong>Keep this announcement<p>\n")
        self.other_original = self.other.read_bytes()
        self.env = dict(os.environ, DFS_BANNER_DIR=str(self.messages),
                        DFS_BANNER_OBSERVED_AT="2026-10-23T10:00:00Z")

    def invoke(self, *args, shell=None):
        return subprocess.run([*(shell or ["/bin/sh"]), str(HELPER), *args],
                              env=self.env, text=True, capture_output=True, timeout=5)

    def test_report_is_bounded_single_line_native_envelope_and_preserves_others(self):
        result = self.invoke("report", "test-ap", "wlan0", "5660", "hostapd_cli")
        self.assertEqual(result.returncode, 0, result.stderr)
        text = self.target.read_text()
        self.assertEqual(len(text.splitlines()), 1)
        self.assertTrue(text.startswith("<strong>&#8611; DFS detection test:</strong>"))
        self.assertIn("channel 132 (5660 MHz)", text)
        self.assertIn("Last report, not current DFS/NOP state", text)
        self.assertIn("2026-10-23T10:00:00Z", text)
        self.assertEqual(self.other.read_bytes(), self.other_original)
        self.assertEqual(sorted(p.name for p in self.messages.iterdir()),
                         ["another-addon", "aredn-dfs-detection-test"])

    def test_demo_is_explicitly_simulated_and_clear_only_removes_owned_message(self):
        self.assertEqual(self.invoke("demo", "test-ap").returncode, 0)
        self.assertIn("SIMULATED", self.target.read_text())
        self.assertIn("Not a real radar detection", self.target.read_text())
        self.assertEqual(self.invoke("clear").returncode, 0)
        self.assertFalse(self.target.exists())
        self.assertEqual(self.other.read_bytes(), self.other_original)
        self.assertEqual(self.invoke("clear").returncode, 0)

    def test_repeated_flags_replace_one_message_without_appending_or_timers(self):
        self.assertEqual(self.invoke("report", "ap", "wlan0", "5660", "hostapd_cli").returncode, 0)
        self.assertEqual(self.invoke("report", "ap", "wlan1", "5500", "hostapd_cli").returncode, 0)
        self.assertNotIn("5660 MHz", self.target.read_text())
        self.assertIn("channel 100 (5500 MHz)", self.target.read_text())
        self.assertEqual(len(list(self.messages.iterdir())), 2)

    def test_untrusted_display_fields_are_html_escaped(self):
        payload = '<img src=x onerror="alert(1)">&\'node'
        result = self.invoke("report", payload, "wlan<0>", "5660", "source&test")
        self.assertEqual(result.returncode, 0, result.stderr)
        text = self.target.read_text()
        self.assertNotIn("<img", text)
        self.assertIn("&lt;img", text)
        self.assertIn("&amp;&#39;node", text)
        self.assertIn("wlan&lt;0&gt;", text)

    def test_multiline_or_invalid_frequency_does_not_replace_existing_banner(self):
        self.assertEqual(self.invoke("demo", "test-ap").returncode, 0)
        original = self.target.read_bytes()
        for args in [("report", "ap\nspoof", "wlan0", "5660", "hostapd_cli"),
                     ("report", "ap", "wlan0", "5660;false", "hostapd_cli"),
                     ("report", "ap", "wlan0", "005660", "hostapd_cli")]:
            with self.subTest(args=args):
                self.assertNotEqual(self.invoke(*args).returncode, 0)
                self.assertEqual(self.target.read_bytes(), original)

    def test_unknown_and_other_band_frequency_do_not_guess_channel(self):
        for freq in ["unknown", "4910", "5955", "5661"]:
            with self.subTest(freq=freq):
                self.assertEqual(self.invoke("report", "ap", "wlan0", freq, "source").returncode, 0)
                self.assertIn("channel unknown", self.target.read_text())

    def test_write_failure_preserves_unrelated_message_and_cleans_staging(self):
        self.target.mkdir()
        result = self.invoke("report", "ap", "wlan0", "5660", "source")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.target.is_dir())
        self.assertEqual(self.other.read_bytes(), self.other_original)
        self.assertFalse(list(self.messages.glob(".aredn-dfs-stage.*")))

    def test_symlink_message_is_not_followed_or_overwritten(self):
        victim = self.root / "other-data"
        victim.write_text("preserve")
        self.target.symlink_to(victim)
        self.assertNotEqual(self.invoke("report", "ap", "wlan0", "5660", "source").returncode, 0)
        self.assertEqual(victim.read_text(), "preserve")
        self.assertTrue(self.target.is_symlink())

    def test_all_detector_sources_feed_the_same_banner_sink(self):
        events = [parse_event(RADAR, "ap"),
                  ControlCapture("ap", "wlan0").parse("<3>DFS-RADAR-DETECTED freq=5660"),
                  UbusCapture("ap", "hostapd.wlan0").parse('{"radar-detected":{"frequency":5660}}')]
        sink = BannerSink(self.messages)
        for event in events:
            with self.subTest(source=event["source"]):
                self.assertTrue(sink.emit(event))
                self.assertIn("channel 132 (5660 MHz)", self.target.read_text())
                self.assertIn("source " + event["source"], self.target.read_text())

    def test_context_never_creates_or_clears_a_radar_banner(self):
        sink = BannerSink(self.messages)
        for token in ["DFS-CAC-START", "DFS-CAC-COMPLETED", "DFS-NOP-FINISHED",
                      "DFS-PRE-CAC-EXPIRED", "DFS-NEW-CHANNEL", "AP-CSA-FINISHED",
                      "CTRL-EVENT-CHANNEL-SWITCH"]:
            self.assertFalse(sink.emit(parse_event(token + " freq=5180", "ap")))
        self.assertFalse(self.target.exists())
        sink.emit(parse_event(RADAR, "ap"))
        original = self.target.read_bytes()
        self.assertFalse(sink.emit(parse_event("DFS-NEW-CHANNEL freq=5180", "ap")))
        self.assertEqual(self.target.read_bytes(), original)

    def test_banner_cli_is_opt_in_and_uses_local_directory_only(self):
        for enabled in [False, True]:
            output = io.StringIO()
            args = ["--node", "ap", "--summary"]
            if enabled:
                args += ["--banner-dir", str(self.messages)]
            with patch("sys.stdin", io.StringIO(RADAR + "\n")), contextlib.redirect_stdout(output):
                self.assertEqual(main(args), 0)
            self.assertEqual(self.target.exists(), enabled)
            self.assertEqual(json.loads(output.getvalue())["radar_assessment"], "reported")

    @unittest.skipUnless(shutil.which("busybox"), "BusyBox not installed")
    def test_native_busybox_ash_and_applets_can_write_and_clear_banner(self):
        bindir = self.root / "busybox-bin"
        bindir.mkdir()
        busybox = shutil.which("busybox")
        for name in ["date", "sed", "mkdir", "mktemp", "chmod", "mv", "rm", "rmdir"]:
            (bindir / name).symlink_to(busybox)
        self.env["PATH"] = str(bindir)
        result = self.invoke("report", "ap", "wlan0", "5660", "hostapd_cli", shell=[busybox, "ash"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("channel 132", self.target.read_text())
        self.assertEqual(self.invoke("clear", shell=[busybox, "ash"]).returncode, 0)

    @unittest.skipUnless(UCODE and AREDN_SOURCE and AREDN_SOURCE.exists(), "set UCODE and AREDN_SOURCE for native consumer fixture")
    def test_exact_native_reader_and_template_render_report_and_preserve_others(self):
        self.assertEqual(self.invoke("report", "ap<&", "wlan0", "5660", "hostapd_cli").returncode, 0)
        # A staging directory, including an unfinished inner file, must not be displayed.
        staging = self.messages / ".aredn-dfs-stage-fixture"
        staging.mkdir()
        (staging / "message").write_text("<strong>&#8611; Incomplete:</strong>must not render<p>")
        result = render_native(UCODE, AREDN_SOURCE, self.root)
        self.assertIn("DFS detection test", result["messages"])
        self.assertIn("Another add-on", result["messages"])
        self.assertNotIn("Incomplete", result["messages"])
        self.assertIn("channel 132 (5660 MHz)", result["html"])
        self.assertIn("ap&lt;&amp;", result["html"])
        self.assertNotIn("ap<&", result["html"])
        self.assertIn("Keep this announcement", result["html"])

    @unittest.skipUnless(UCODE and AREDN_SOURCE and AREDN_SOURCE.exists(), "set UCODE and AREDN_SOURCE for native consumer fixture")
    def test_native_template_demo_and_clear(self):
        self.assertEqual(self.invoke("demo", "ap").returncode, 0)
        demo = render_native(UCODE, AREDN_SOURCE, self.root)
        self.assertIn("SIMULATED", demo["html"])
        self.assertEqual(self.invoke("clear").returncode, 0)
        cleared = render_native(UCODE, AREDN_SOURCE, self.root)
        self.assertNotIn("DFS detection test", cleared["messages"])
        self.assertIn("Keep this announcement", cleared["html"])


if __name__ == "__main__":
    unittest.main()
