"""Small passive UNIX-datagram hostapd subscriber; no radio/config commands.

Only ATTACH, PING and best-effort DETACH are sent. Loss of the source fails
visibly instead of silently producing an apparently clear channel history.
"""

import os
import re
import socket
import tempfile
import time


EVENT_PREFIX = re.compile(r"^(?:IFNAME=[^\s]+\s+)?<\d+>")
MAX_DATAGRAM = 65536


class ControlError(OSError):
    """The control connection cannot provide a trustworthy event stream."""


def listen(server_path, on_event, *, on_attached=lambda: None,
           should_stop=lambda: False, timeout=3.0, ping_interval=10.0):
    """Listen until stopped or source failure, calling on_event with raw text.

    Callback execution should be fast. Heartbeats establish only socket
    responsiveness, NOT that DFS detection is enabled or reports are lossless.
    Any failure requires a new collector run; no backlog can be recovered here.
    """
    if timeout <= 0 or ping_interval <= 0:
        raise ValueError("timeouts must be positive")
    with tempfile.TemporaryDirectory(prefix="aredn-dfs-", dir="/tmp") as runtime:
        client_path = os.path.join(runtime, "client")
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.bind(client_path)
            os.chmod(client_path, 0o600)
            sock.settimeout(timeout)
            # A connected datagram socket receives only from this peer.
            sock.connect(os.fspath(server_path))

            def receive(wait):
                sock.settimeout(wait)
                data, _ancillary, flags, _address = sock.recvmsg(MAX_DATAGRAM)
                if flags & socket.MSG_TRUNC:
                    raise ControlError("truncated control datagram; collection gap")
                return data

            def dispatch(data):
                text = data.decode("utf-8", errors="replace")
                if not EVENT_PREFIX.match(text):
                    return False
                on_event(text)
                return True

            def request(command, expected):
                deadline = time.monotonic() + timeout
                sock.settimeout(timeout)
                sock.send(command)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise ControlError(f"{command.decode()} timed out; collection gap")
                    try:
                        data = receive(remaining)
                    except socket.timeout as error:
                        raise ControlError(
                            f"{command.decode()} timed out; collection gap"
                        ) from error
                    # Async events may arrive before the command reply.
                    if dispatch(data):
                        continue
                    if data != expected:
                        raise ControlError(f"{command.decode()} rejected: {data!r}")
                    return

            try:
                request(b"ATTACH", b"OK\n")
                on_attached()
                next_ping = time.monotonic() + ping_interval
                while not should_stop():
                    remaining = next_ping - time.monotonic()
                    if remaining <= 0:
                        request(b"PING", b"PONG\n")
                        next_ping = time.monotonic() + ping_interval
                        continue
                    try:
                        data = receive(min(remaining, 0.5))
                    except socket.timeout:
                        continue
                    if not dispatch(data):
                        raise ControlError(f"unexpected control response: {data!r}")
            finally:
                # Also detach if ATTACH was accepted but its reply was lost.
                # Never let failed cleanup mask the original failure.
                try:
                    sock.settimeout(0.1)
                    sock.send(b"DETACH")
                except OSError:
                    pass
