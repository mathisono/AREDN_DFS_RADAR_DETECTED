# AREDN DFS RADAR DETECTED

An **installable AREDN/OpenWrt APK** that adds a small, passive DFS radar-report
collector. This is **not an Android APK**, firmware replacement, RF radar sensor,
or radio-recovery watchdog.

The radio's existing driver/hostapd performs DFS detection. This project captures
its explicit reports, preserves the reported frequency, and distinguishes them
from channel changes and other DFS lifecycle events. It never changes channels,
regulatory settings, transmit power, or radio configuration.

**Status: experimental.** The published release is **0.1.0-r1**; current source
is the **0.1.0-r2 development candidate**, adding the opt-in announcement banner
and passive channel-noise snapshot. The r1 release assets are unchanged and do
not contain these additions. Build r2 from source using [BUILD.md](BUILD.md).
Genuine AP-side radar confirmation and package installation qualification on
an eligible target remain pending. Installation leaves the service and banner
disabled and the interface unset.

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
  -> optional local AREDN announcement + passive noise snapshot (r2)
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

## Detection-test banner and noise measurements

The opt-in [AREDN banner](BANNER.md) shows the latest explicit radar report and,
on the native action path, the radio's noise floor in **dBm**, measured
channel/frequency, interface and read time. It uses only a verified active
survey entry; missing readings are unavailable, not zero. A post-switch sample
is not attributed to the old radar channel. Noise alone never flags radar.

The `demo` command clearly separates **SIMULATED radar data** from a **real
radio noise snapshot**. Samples are collected on banner updates, not continuously.
The helper and live status response were checked on the existing test node;
see the [sanitized display/noise validation](docs/DEV1-BANNER-VALIDATION.md).

## Repository contents

- `dfs_action.sh`: single source for the packaged native event action.
- `dfs_banner.sh`: packaged opt-in announcement and passive noise helper.
- `aredn_banner.py`: optional local Python banner sink, without workstation noise reads.
- `files/`: UCI defaults, opt-in procd service and passive collector launcher.
- `package/`: package removal/upgrade cleanup scripts; no auto-start hook.
- `build.py`, `VERSION`: reproducible APK v3 build with official apk-tools.
- `dfs_detector.py`, `hostapd_control.py`: original off-node analysis and optional
  local control-socket collector (Python standard library only).
- `test_*.py`: parser, native-action, socket and package/service checks.
- `docs/reference/`: pinned upstream source URLs and hashes, not field logs.
- [BANNER.md](BANNER.md): enablement, simulated display, noise semantics and cleanup.
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
