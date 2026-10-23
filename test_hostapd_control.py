"""Isolated real UNIX-socket fixtures. No hostapd service or radio is used."""

import contextlib
import io
import json
import os
from pathlib import Path
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from dfs_detector import main
from hostapd_control import ControlError, MAX_DATAGRAM, listen


RADAR = b"<3>DFS-RADAR-DETECTED freq=5660 chan_width=2 cf1=5670 cf2=0"


class FakeHostapd:
    def __init__(self, *, attach_reply=b"OK\n", before_attach=(), after_attach=(),
                 ping_reply=b"PONG\n", before_pong=(), exit_after_attach=False):
        self.attach_reply = attach_reply
        self.before_attach = before_attach
        self.after_attach = after_attach
        self.ping_reply = ping_reply
        self.before_pong = before_pong
        self.exit_after_attach = exit_after_attach
        self.commands = []
        self.errors = []
        self.address = None
        self.client_modes = None
        self.attached = threading.Event()
        self.detached = threading.Event()
        self.stopped = threading.Event()

    def __enter__(self):
        self.runtime = tempfile.TemporaryDirectory(prefix="dfs-test-", dir="/tmp")
        self.path = str(Path(self.runtime.name) / "wlan0")
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.sock.bind(self.path)
        self.sock.settimeout(0.05)
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()
        return self

    def serve(self):
        try:
            while not self.stopped.is_set():
                try:
                    command, address = self.sock.recvfrom(1024)
                except socket.timeout:
                    continue
                self.commands.append(command)
                self.address = address
                if command == b"ATTACH":
                    self.client_modes = (
                        stat.S_IMODE(os.stat(Path(address).parent).st_mode),
                        stat.S_IMODE(os.stat(address).st_mode),
                    )
                    for event in self.before_attach:
                        self.sock.sendto(event, address)
                    if self.attach_reply is not None:
                        self.sock.sendto(self.attach_reply, address)
                    self.attached.set()
                    for event in self.after_attach:
                        self.sock.sendto(event, address)
                    if self.exit_after_attach:
                        self.sock.close()
                        return
                elif command == b"PING":
                    for event in self.before_pong:
                        self.sock.sendto(event, address)
                    if self.ping_reply is not None:
                        self.sock.sendto(self.ping_reply, address)
                elif command == b"DETACH":
                    self.detached.set()
                else:
                    raise AssertionError(f"unexpected command: {command!r}")
        except BaseException as error:
            self.errors.append(error)

    def __exit__(self, exc_type, exc, tb):
        self.stopped.set()
        self.thread.join(timeout=1)
        self.sock.close()
        self.runtime.cleanup()
        if self.thread.is_alive():
            raise AssertionError("fixture thread did not exit")
        if self.errors and exc is None:
            raise AssertionError(self.errors)


class ControlSocketTests(unittest.TestCase):
    def test_real_socket_attach_events_detach_and_private_cleanup(self):
        received = []
        with FakeHostapd(after_attach=[RADAR, RADAR]) as server:
            listen(server.path, received.append, should_stop=lambda: len(received) == 2)
            self.assertTrue(server.detached.wait(1))
            self.assertEqual(received, [RADAR.decode(), RADAR.decode()])
            self.assertEqual(server.commands, [b"ATTACH", b"DETACH"])
            self.assertEqual(server.client_modes, (0o700, 0o600))
            self.assertFalse(os.path.exists(Path(server.address).parent))
            self.assertTrue(os.path.exists(server.path))  # never removes server socket

    def test_async_event_before_attach_reply_is_not_lost(self):
        received = []
        with FakeHostapd(before_attach=[RADAR]) as server:
            listen(server.path, received.append, should_stop=lambda: bool(received))
            self.assertEqual(received, [RADAR.decode()])

    def test_attach_requires_exact_ok_reply(self):
        for reply in [b"FAIL\n", b"NOT OK\n", b"OK extra\n"]:
            with self.subTest(reply=reply), FakeHostapd(attach_reply=reply) as server:
                attached = []
                with self.assertRaisesRegex(ControlError, "ATTACH rejected"):
                    listen(server.path, lambda line: None,
                           on_attached=lambda: attached.append(True))
                self.assertFalse(attached)
                self.assertTrue(server.detached.wait(1))
                self.assertFalse(os.path.exists(Path(server.address).parent))

    def test_attach_timeout_is_unavailable_not_clear(self):
        with FakeHostapd(attach_reply=None) as server:
            with self.assertRaisesRegex(ControlError, "ATTACH timed out"):
                listen(server.path, lambda line: None, timeout=0.1)
            self.assertTrue(server.detached.wait(1))

    def test_ping_with_interleaved_event_and_reply(self):
        received = []
        with FakeHostapd(before_pong=[RADAR]) as server:
            listen(server.path, received.append, should_stop=lambda: bool(received),
                   ping_interval=0.02, timeout=0.3)
            self.assertTrue(server.detached.wait(1))
            self.assertEqual(received, [RADAR.decode()])
            self.assertEqual(server.commands, [b"ATTACH", b"PING", b"DETACH"])

    def test_ping_timeout_fails_instead_of_silent_loss_of_coverage(self):
        with FakeHostapd(ping_reply=None) as server:
            with self.assertRaisesRegex(ControlError, "PING timed out"):
                listen(server.path, lambda line: None, timeout=0.1, ping_interval=0.02)
            self.assertTrue(server.detached.wait(1))
            self.assertFalse(os.path.exists(Path(server.address).parent))

    def test_event_without_ping_ack_does_not_keep_dead_source_healthy(self):
        received = []
        with FakeHostapd(ping_reply=None, before_pong=[RADAR]) as server:
            with self.assertRaisesRegex(ControlError, "PING timed out"):
                listen(server.path, received.append, timeout=0.1, ping_interval=0.02)
            self.assertEqual(received, [RADAR.decode()])

    def test_daemon_exit_fails_and_removes_client_socket(self):
        with FakeHostapd(exit_after_attach=True) as server:
            with self.assertRaises(OSError):
                listen(server.path, lambda line: None, timeout=0.1, ping_interval=0.02)
            self.assertFalse(os.path.exists(Path(server.address).parent))

    def test_oversized_datagram_is_rejected_not_partially_parsed(self):
        oversized = RADAR + b" " + b"x" * MAX_DATAGRAM
        with FakeHostapd(after_attach=[oversized]) as server:
            received = []
            with self.assertRaisesRegex(ControlError, "truncated"):
                listen(server.path, received.append)
            self.assertEqual(received, [])

    def test_callback_failure_still_detaches_and_cleans_up(self):
        def fail(_line):
            raise RuntimeError("sink unavailable")

        with FakeHostapd(after_attach=[RADAR]) as server:
            with self.assertRaisesRegex(RuntimeError, "sink unavailable"):
                listen(server.path, fail)
            self.assertTrue(server.detached.wait(1))
            self.assertFalse(os.path.exists(Path(server.address).parent))

    def test_missing_socket_reports_collector_unavailable_on_stderr(self):
        with tempfile.TemporaryDirectory(prefix="dfs-missing-") as runtime:
            output, status = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(status):
                with self.assertRaises(OSError):
                    main(["--node", "test-ap", "--control-socket", runtime + "/absent",
                          "--interface", "wlan0"])
            self.assertEqual(output.getvalue(), "")
            records = [json.loads(line) for line in status.getvalue().splitlines()]
            self.assertEqual([r["collector_status"] for r in records],
                             ["connecting", "unavailable"])

    def test_cli_sigterm_keeps_distinct_events_and_removes_client_socket(self):
        script = str(Path(__file__).with_name("dfs_detector.py"))
        with FakeHostapd(after_attach=[RADAR, RADAR]) as server:
            with tempfile.TemporaryFile(mode="w+") as output, \
                    tempfile.TemporaryFile(mode="w+") as status, \
                    tempfile.TemporaryDirectory(prefix="dfs-cli-banner-") as messages:
                proc = subprocess.Popen(
                    [sys.executable, script, "--node", "test-ap", "--interface", "wlan0",
                     "--control-socket", server.path, "--banner-dir", messages],
                    stdout=output, stderr=status)
                try:
                    self.assertTrue(server.attached.wait(2))
                    # Read without changing the writer's shared file offset.
                    # The readiness check is bounded by the test deadline.
                    deadline = time.monotonic() + 2
                    while time.monotonic() < deadline:
                        banner = Path(messages) / "aredn-dfs-detection-test"
                        lines = os.pread(output.fileno(), 65536, 0).splitlines()
                        if len(lines) == 2 and banner.exists():
                            if json.loads(lines[-1])["ingested_at_utc"] in banner.read_text():
                                break
                        time.sleep(0.01)
                    else:
                        self.fail("CLI did not emit both fixture events")
                    proc.send_signal(signal.SIGTERM)
                    self.assertEqual(proc.wait(timeout=2), 128 + signal.SIGTERM)
                finally:
                    if proc.poll() is None:
                        proc.kill()
                        proc.wait(timeout=2)
                output.seek(0)
                records = [json.loads(line) for line in output]
                status.seek(0)
                states = [json.loads(line)["collector_status"] for line in status]
                self.assertEqual(states, ["connecting", "attached", "stopped"])
                self.assertEqual(len({r["event_id"] for r in records}), 2)
                self.assertEqual({r["reported_primary_channel"] for r in records}, {132})
                self.assertIn("channel 132 (5660 MHz)", banner.read_text())
                self.assertFalse(list(Path(messages).glob(".aredn-dfs-stage.*")))
                self.assertTrue(server.detached.wait(1))
                self.assertFalse(os.path.exists(Path(server.address).parent))


if __name__ == "__main__":
    unittest.main()
