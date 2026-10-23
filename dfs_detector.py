#!/usr/bin/env python3
"""Passive hostapd DFS report parser/listener. Python standard library only.

An explicit radar event means the Wi-Fi stack reported radar, not that an
independent RF instrument verified radar. Missing events never mean clear.
"""

import argparse
from collections import Counter
from contextlib import nullcontext
from datetime import datetime, timezone
import hashlib
import json
import re
import signal
import sys
import uuid


EVENTS = {
    "DFS-RADAR-DETECTED": "radar_reported",
    "DFS-CAC-START": "cac_started",
    "DFS-CAC-COMPLETED": "cac_completed",
    "DFS-NOP-FINISHED": "non_occupancy_finished",
    "DFS-PRE-CAC-EXPIRED": "pre_cac_expired",
    "DFS-NEW-CHANNEL": "channel_change",
    "AP-CSA-FINISHED": "channel_change",
    "CTRL-EVENT-CHANNEL-SWITCH": "channel_change",
}
EVENT_RE = re.compile(
    r"(?<![\w-])(" + "|".join(map(re.escape, EVENTS)) + r")(?=\s|$)"
)
FIELD_RE = re.compile(r"\b([a-zA-Z][a-zA-Z0-9_]*)=(-?\d+)(?=[\s,]|$)")
IFACE_RE = re.compile(r"\b((?:wlan|phy|ath|mesh)[\w.-]*):\s*(?:<\d+>)?$")
IFNAME_RE = re.compile(r"(?:^|\s|>)IFNAME=([^\s]+)\s*(?:<\d+>)?$")
RELAY_PREFIX = re.compile(
    r"(?<![\w-])hostapd-dfs(?:\[\d+\])?:\s+DFS_RELAY "
    r"action_pid=(\d+) IFNAME=([\w.-]+)\s+"
)


def channel_5ghz(freq):
    """Only the 5 GHz mapping; do not mislabel 4.9/6 GHz as 5 GHz."""
    if freq is not None and 5000 < freq < 5925 and freq % 5 == 0:
        return (freq - 5000) // 5
    return None


def parse_event(line, node, boot_id=None, *, interface_hint=None):
    raw = line.rstrip("\r\n")
    match = EVENT_RE.search(raw)
    if not match:
        return None
    event = match.group(1)
    fields = {k: int(v) for k, v in FIELD_RE.findall(raw[match.end():])}
    freq = fields.get("freq")
    if freq is not None and freq <= 0:
        freq = None
    prefix = raw[:match.start()]
    relay = RELAY_PREFIX.search(prefix)
    if relay and relay.end() != len(prefix):
        relay = None
    interface = IFNAME_RE.search(prefix) or IFACE_RE.search(prefix)
    # No fallback to a current channel or cf1: those can refer to a different
    # time, a wide-channel center, or a channel selected AFTER the radar event.
    event_id = hashlib.sha256(
        json.dumps([node, boot_id, raw], separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "event_id": event_id,
        "node": node,
        "boot_id": boot_id,
        "interface": interface.group(1) if interface else interface_hint,
        "source": "hostapd_cli_log" if relay else "log_text",
        "relay_action_pid": int(relay.group(1)) if relay else None,
        "event": event,
        "classification": EVENTS[event],
        "flag_channel": event == "DFS-RADAR-DETECTED",
        "reported_frequency_mhz": freq,
        "reported_primary_channel": channel_5ghz(freq),
        "fields": fields,
        "log_line": raw,
        "ingested_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def summarize(events):
    """Summarize unique records, not independently verified physical hits."""
    unique = {event["event_id"]: event for event in events}
    kinds = Counter(event["classification"] for event in unique.values())
    channels = {}
    for event in unique.values():
        if not event["flag_channel"]:
            continue
        key = (event["node"], event["interface"], event["reported_frequency_mhz"])
        if key not in channels:
            channels[key] = {
                "node": event["node"],
                "interface": event["interface"],
                "reported_frequency_mhz": event["reported_frequency_mhz"],
                "reported_primary_channel": event["reported_primary_channel"],
                "radar_report_records": 0,
                "event_ids": [],
            }
        channels[key]["radar_report_records"] += 1
        channels[key]["event_ids"].append(event["event_id"])
    return {
        "radar_assessment": "reported" if channels else "unknown",
        "unique_event_records": len(unique),
        "event_counts": dict(kinds),
        "flagged_channels": list(channels.values()),
        "interpretation": (
            "Only explicit DFS-RADAR-DETECTED or native ubus radar-detected "
            "records flag channels. Absence "
            "of reports is not evidence of no radar. Counts are unique source "
            "records, not independent physical hits or current NOP state."
        ),
    }


class UbusCapture:
    """Read native `ubus subscribe ONE_OBJECT` JSON lines, not broadcast events.

    The CLI omits the emitting object from its JSON. Its identity must come
    from a single-object subscription selected by the operator, never guessed
    from a channel or an arbitrary payload field.
    """

    def __init__(self, node, object_name, boot_id=None):
        if not re.fullmatch(r"hostapd\.[A-Za-z0-9_.-]+", object_name):
            raise ValueError("--ubus-object must name one hostapd interface object")
        self.node = node
        self.object_name = object_name
        self.interface = object_name[len("hostapd."):]
        self.boot_id = boot_id
        self.capture_id = uuid.uuid4().hex
        self.sequence = 0

    def parse(self, line):
        if len(line) > 65536:
            raise ValueError("oversized ubus record; collection cannot be trusted")
        raw = line.rstrip("\r\n")
        if not raw.strip():
            return None
        frame = json.loads(raw)
        if not isinstance(frame, dict) or len(frame) != 1:
            raise ValueError("expected one native ubus notification per JSON line")
        name, fields = next(iter(frame.items()))
        if name not in ("radar-detected", "channel-switch"):
            return None
        if not isinstance(fields, dict):
            raise ValueError("ubus notification payload must be an object")
        if "ifname" in fields and fields["ifname"] != self.interface:
            raise ValueError("ubus payload interface differs from subscribed object")
        frequency_key = "frequency" if name == "radar-detected" else "freq"
        freq = fields.get(frequency_key)
        if freq is not None and type(freq) is not int:
            raise ValueError("ubus frequency must be an integer")
        if freq is not None and freq <= 0:
            freq = None
        self.sequence += 1
        event_id = hashlib.sha256(json.dumps(
            [self.node, self.boot_id, self.object_name, self.capture_id,
             self.sequence, raw], separators=(",", ":")
        ).encode()).hexdigest()
        return {
            "event_id": event_id, "node": self.node, "boot_id": self.boot_id,
            "interface": self.interface, "source": "ubus_subscription",
            "ubus_object": self.object_name, "capture_id": self.capture_id,
            "capture_sequence": self.sequence, "event": name,
            "classification": "radar_reported" if name == "radar-detected" else "channel_change",
            "flag_channel": name == "radar-detected",
            "reported_frequency_mhz": freq,
            "reported_primary_channel": channel_5ghz(freq),
            "fields": fields, "log_line": raw,
            "ingested_at_utc": datetime.now(timezone.utc).isoformat(),
        }


class ControlCapture:
    """Give each received event an identity, even without a source timestamp."""

    def __init__(self, node, interface, boot_id=None):
        self.node = node
        self.interface = interface
        self.boot_id = boot_id
        self.capture_id = uuid.uuid4().hex
        self.sequence = 0

    def parse(self, line):
        # Control-socket payloads start with a priority tag, optionally IFNAME.
        # Unlike log parsing, do not search arbitrary non-event message bodies.
        from hostapd_control import EVENT_PREFIX

        prefix = EVENT_PREFIX.match(line)
        if not prefix or not EVENT_RE.match(line, prefix.end()):
            return None
        event = parse_event(line, self.node, self.boot_id,
                            interface_hint=self.interface)
        self.sequence += 1
        event.update(source="hostapd_control", capture_id=self.capture_id,
                     capture_sequence=self.sequence)
        event["event_id"] = hashlib.sha256(json.dumps(
            [self.node, self.boot_id, self.capture_id, self.sequence, line],
            separators=(",", ":")
        ).encode()).hexdigest()
        return event


def monitor_control(args):
    from hostapd_control import listen

    capture = ControlCapture(args.node, args.interface, args.boot_id)

    def status(state, detail=None):
        print(json.dumps({
            "collector_status": state, "source": "hostapd_control",
            "node": args.node, "interface": args.interface,
            "control_socket": args.control_socket,
            "capture_id": capture.capture_id,
            "observed_at_utc": datetime.now(timezone.utc).isoformat(),
            "detail": detail,
        }, sort_keys=True), file=sys.stderr, flush=True)

    def receive(line):
        event = capture.parse(line)
        if event is not None:
            print(json.dumps(event, sort_keys=True), flush=True)

    status("connecting")
    try:
        listen(args.control_socket, receive, on_attached=lambda: status("attached"))
    except OSError as error:
        status("unavailable", str(error))
        raise
    except (KeyboardInterrupt, SystemExit):
        status("stopped", "collector interrupted; no further event coverage")
        raise
    else:
        status("stopped")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logfile", nargs="?", help="log text or native ubus JSON lines; default stdin")
    parser.add_argument("--node", required=True, help="identity of the event-producing node")
    parser.add_argument("--boot-id", help="optional boot ID for replay identity across reboots")
    parser.add_argument("--summary", action="store_true", help="summarize finite input at EOF")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--control-socket", help="local per-interface hostapd UNIX socket")
    mode.add_argument("--ubus-object", help="parse JSON lines from ONE hostapd object subscription")
    mode.add_argument("--relay-only", action="store_true", help="accept only tagged dfs_action.sh log records")
    parser.add_argument("--interface", help="interface identity for the control socket")
    args = parser.parse_args(argv)
    if args.control_socket:
        if args.logfile is not None or args.summary:
            parser.error("--control-socket cannot be combined with a logfile or --summary")
        if not args.interface:
            parser.error("--control-socket requires --interface")
        monitor_control(args)
        return 0
    if args.interface:
        parser.error("--interface is only used with --control-socket")
    ubus = UbusCapture(args.node, args.ubus_object, args.boot_id) if args.ubus_object else None
    source = nullcontext(sys.stdin) if args.logfile in (None, "-") else open(
        args.logfile, encoding="utf-8", errors="replace"
    )
    records = []
    with source as lines:
        for line in lines:
            event = ubus.parse(line) if ubus else parse_event(line, args.node, args.boot_id)
            if event is None:
                continue
            if args.relay_only and event["source"] != "hostapd_cli_log":
                continue
            if args.summary:
                records.append(event)
            else:
                # Stream immediately. Downstream consumers can deduplicate by
                # event_id without an unbounded in-process streaming cache.
                print(json.dumps(event, sort_keys=True), flush=True)
    if args.summary:
        print(json.dumps(summarize(records), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    def terminate(signum, _frame):
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, terminate)
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except (OSError, ValueError) as error:
        print(f"dfs_detector: {error}", file=sys.stderr)
        raise SystemExit(2)
