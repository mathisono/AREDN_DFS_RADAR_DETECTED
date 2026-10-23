# AREDN DFS RADAR DETECTED

An **installable AREDN/OpenWrt APK** that adds a small, passive DFS radar-report
collector. This is **not an Android APK**, firmware replacement, RF radar sensor,
or radio-recovery watchdog.

The radio's existing driver/hostapd performs DFS detection. This project captures
its explicit reports, preserves the reported frequency, and distinguishes them
from channel changes and other DFS lifecycle events. It never changes channels,
regulatory settings, transmit power, or radio configuration.

**Status: experimental 0.1.0-r1.** Source, synthetic tests, package build and
installation instructions are available. Genuine AP-side radar confirmation
and installation qualification on the intended AREDN firmware remain pending.
Installation leaves the service disabled and the interface unset.

## Download and install

Get `aredn-dfs-detector-0.1.0-r1.apk` and `SHA256SUMS` from
[Releases](https://github.com/mathisono/AREDN_DFS_RADAR_DETECTED/releases).
Requires an **apk-tools 3.x AREDN/OpenWrt build**, BusyBox, procd, UCI and a
firmware-compatible `hostapd-utils` package. No Python is installed on the node.

The collector also requires a `timeout` command; do not assume the firmware's
BusyBox includes it. [Dev1 validation](docs/DEV1-VALIDATION.md) passed APK
verification/extraction and 9 native synthetic checks, but that target lacked
required commands and an active hostapd event source. It was not live-installed.

Follow [INSTALL.md](INSTALL.md) for checksum verification, dependency simulation,
interface discovery, explicit enablement, observation, upgrade and removal.
Do not install this `.apk` on opkg/IPK-based firmware or Android.

## How detection works

```text
Existing radio/driver DFS implementation
  -> hostapd per-interface control event
  -> hostapd_cli action subscription
  -> installed shell action (preserves all arguments)
  -> syslog: hostapd-dfs / DFS_RELAY / IFNAME / event / frequency
  -> optional off-node Python JSON parser and summary
```

| Evidence | Interpretation |
|---|---|
| Exact `DFS-RADAR-DETECTED` event | Radar **reported by the stack** |
| Native ubus `radar-detected` in explicitly selected ubus input | Radar reported by the stack; alternative off-node input |
| CAC start/completion, NOP expiration | Context, not another radar report |
| CSA/channel-switch notifications | Context, not evidence of a radar cause |
| Low rate, packet loss, outage, missing events | Radar unknown |

A report can be a hardware/driver false positive or relate to a background
channel. It does not prove a physical emitter or a channel vacation. Silence
does not establish that radar is absent. See [DETECTION.md](DETECTION.md) for
frequency handling, counting, source identity, limitations and source references.

## Repository contents

- `dfs_action.sh`: single source for the packaged native event action.
- `files/`: UCI defaults, opt-in procd service and passive collector launcher.
- `package/`: package removal/upgrade cleanup scripts; no auto-start hook.
- `build.py`, `VERSION`: reproducible APK v3 build with official apk-tools.
- `dfs_detector.py`, `hostapd_control.py`: original off-node analysis and optional
  local control-socket collector (Python standard library only).
- `test_*.py`: parser, native-action, socket and package/service checks.
- `docs/reference/`: pinned upstream source URLs and hashes, not field logs.
- [OPENWRT.md](OPENWRT.md): existing-log, action-relay and ubus capture recipes.
- [BUILD.md](BUILD.md), [VERIFICATION.md](VERIFICATION.md),
  [BACKUP.md](BACKUP.md): build, test boundaries and restore instructions.

```sh
python3 -m unittest discover -s . -p 'test_*.py' -v
python3 build.py --apk /path/to/apk-tools-3
```

Only detector code and sanitized project documentation are published. Credentials,
private radio telemetry, node identities, unrelated watchdog code and local
agent/workspace state are not part of this repository. No open-source license
has yet been selected for this project; publication alone does not grant one.

Public AREDN JSON radar-field support is proposed for community review, not
implemented by this release. Integration still needs real-device confirmation
and a capability-aware design; unsupported sources must not appear radar-free.

## Maintenance and community feedback

The separate APK will continue to be maintained through and after the next
AREDN stable release. The maintainer does not currently experience interference
problems on their own network and needs community feedback and genuine radar-hit
examples to validate event capture. See the
[field-report guidance](docs/DEV1-VALIDATION.md#community-validation-and-maintenance).
