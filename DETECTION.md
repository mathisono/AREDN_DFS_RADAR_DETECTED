# Detection method and interpretation

## What produces the evidence

Radar pulse detection is performed by the radio/firmware/driver's existing DFS
implementation. This package does not implement pulse classification, packet
sniffing, or a software-defined radar sensor. It observes the stack's reports.
The AP's actual firmware must have DFS enabled, expose the selected source and
emit the supported events. Socket presence/PONG alone do not establish this.
A station must not be assumed to have the same coverage as its AP.

The packaged path uses `hostapd_cli -p DIRECTORY -i INTERFACE -a ACTION` against
an existing per-interface control socket. The action receives interface as `$1`,
event token as `$2`, and fields in `$3...`. It shifts off the interface and
preserves **all remaining arguments**, not only `$2`. It accepts exact tokens,
rejects newline/CR injection and treats shell metacharacters as data (no eval).

`DFS-RADAR-DETECTED` is logged at `daemon.notice`. These tokens are logged at
`daemon.info` as context only:

- `DFS-CAC-START`, `DFS-CAC-COMPLETED`
- `DFS-NOP-FINISHED`, `DFS-PRE-CAC-EXPIRED`
- `DFS-NEW-CHANNEL`, `AP-CSA-FINISHED`, `CTRL-EVENT-CHANNEL-SWITCH`

Other action tokens are ignored. A retained report looks like this synthetic
example (prefix/timestamp depends on syslog):

```text
hostapd-dfs: DFS_RELAY action_pid=1234 IFNAME=wlan0 DFS-RADAR-DETECTED freq=5660 chan_width=2 cf1=5670 cf2=0
```

The off-node parser sets `classification=radar_reported` and `flag_channel=true`
for this explicit event. CAC failure (even a field `radar_detected=1`), CSA,
retries and low PHY rate do not create another radar record. The text parser
expects trusted native log input, not arbitrary prose containing event strings;
use `--relay-only` for packaged relay output.

## Frequency and timing

Use the report's `freq` (native ubus `frequency`) as the affected reported
frequency. Never replace it with a current status-page channel, CSA destination,
`cf1`/`center1`, or an inferred prior channel. Missing frequency remains unknown.
The parser maps 5 GHz frequencies only: `(freq - 5000) / 5` when `5000 < freq <
5925` and divisible by 5. This arithmetic mapping is not a regulatory permission
check; 4.9/6 GHz are not mapped. Width values remain source enums, not assumed
MHz. A wide-channel report does not identify which 20 MHz segment had a pulse.

Preserve the original log line/time and provide node boot ID when available.
`ingested_at_utc` is parser receipt time, not hardware occurrence time. The
detector does not infer NOP/CAC durations, start a blacklist, or promise latency.

## Identity, duplicates and summaries

Log IDs hash node, boot ID and exact raw line. Replayed identical lines collapse
in summaries, so indistinguishable same-timestamp native lines can also collapse.
The action adds PID/interface information; PID reuse remains possible. Socket
and ubus inputs add capture UUID/sequence, preserving distinct identical received
notifications. Retain their JSON IDs for replay; do not reparse JSON as log text.

Counts are **source records**, not unique physical radar incidents. Select one
source per radio: do not add native logs and their relay copies. `--relay-only`
excludes untagged originals. Multiple BSS ubus notifications may describe the
same radio report. Summaries group by node, interface and reported frequency.

## Source health and gaps

The node launcher checks the socket and bounded PING before starting. It reports
any CLI exit, including zero, as a collection gap; procd does not auto-respawn.
Stopping/upgrading/removing the service stops collection only, never the radio.
Hostapd CLI's own heartbeat cannot certify event delivery: action logger errors
may not propagate to it, and quiet/running processes do not prove DFS coverage.
The package uses existing syslog retention/forwarding; it creates no separate
flash history. Log buffer rollover and restart can lose evidence.

The Python local-socket collector sends only ATTACH/PING/DETACH, with deadlines,
strict replies, a peer-bound private socket, truncation checks and cleanup.
Its lifecycle diagnostics go to stderr. These checks establish transport health,
not radar-detector enablement or lossless reporting.

## Native ubus alternative

The reviewed OpenWrt code emits `radar-detected` as an **object notification**.
Use `ubus subscribe hostapd.INTERFACE`, not `ubus listen hostapd.*`. The CLI
omits the emitting object's identity, so use one object per stream and specify
`--ubus-object` explicitly. Native `channel-switch` is context only. The APK
service deliberately uses the action-relay path, not concurrent ubus capture.

## Reviewed upstream sources

- Hostap AOSP mirror: revision `ab49c33aef291e4d9cabe9a16f535bca40569a10`.
  Reporting: `src/ap/dfs.c`, `src/common/wpa_ctrl.h`; transport:
  `src/common/wpa_ctrl.c`, `hostapd/ctrl_iface.c`; action argv:
  `hostapd/hostapd_cli.c`, `src/utils/os_unix.c`.
- OpenWrt reference: `f0a60eee2fe051741c643ea6118718aae1ef17fb`, hostapd
  ubus implementation and patch.
- Ubus CLI: `24864e7840b3a02a9ef76284a373f6b2f00b8a9b`.

Exact URLs and SHA-256 hashes are in [docs/reference](docs/reference). These
are protocol references, **not matches to installed field firmware binaries**.

## Field confirmation still required

Capture a genuine timestamped AP-side report with frequency; record firmware,
driver, active DFS/regulatory capability and corroborating passive driver/state
evidence where available. Distinguish driver false positives, background events,
channel changes and collection gaps. Do not manufacture an RF event or change
the production link to test the parser. Public status JSON alone lacks the
needed radar evidence; request an API extension only after this confirmation.
