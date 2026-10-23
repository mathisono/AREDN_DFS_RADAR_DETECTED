# Dev1 validation — 2026-10-23

This is a **native package-format and synthetic handler check**, not a successful
live collector installation or a real radar-detection demonstration.

## Target and scope

- MikroTik hAP ac3, ARMv7 / `ipq40xx/mikrotik`.
- AREDN `20261013-8c028e99`, kernel `6.12.94`, apk-tools `3.0.5`.
- Only a 2.4 GHz IBSS interface was active during the checks. No exposed hostapd
  control socket or `hostapd.*` ubus object was available.
- `hostapd_cli`, `timeout`, and Lua were absent; ucode was available.
- No firmware, driver, radio, network or regulatory configuration was changed.

## Published APK check

The exact `v0.1.0-r1` release APK was copied to a private RAM-backed `/tmp`
staging directory. Its on-node SHA-256 matched the published checksum:

```text
da8ec8a666e8c93110f8ec56b4a7e4bc757dcbea13053cd8c0f8f08c4ec732be
```

Dev1's own `apk verify --allow-untrusted` succeeded. `apk extract` succeeded
into the staging directory, producing the four expected payload files. This
did not install the package into the live root or run its lifecycle scripts.

`apk add --simulate --allow-untrusted` failed to resolve `hostapd-utils` from
the target's current package indexes; it also reported missing cached repository
indexes. This does **not** establish that the dependency is unavailable from
all AREDN feeds. No feed refresh, dependency override, package installation,
hostapd replacement or radio enablement was performed.

The r1 collector also requires a `timeout` command, which this target lacks.
Its manifest declares BusyBox but does not separately guarantee that applet.
BusyBox package presence is therefore insufficient to qualify a target. This
is a known r1 compatibility limitation, not a zero-dependency installation.

## Native synthetic checks: 9/9 passed

The extracted, unchanged action and launcher ran under the target's `/bin/sh`.
A temporary fake `logger` captured test output in `/tmp`, so synthetic radar
messages did **not** enter the node's real syslog or radio event stream.

1. Shell syntax accepted for all three packaged scripts.
2. Explicit radar event retained interface, frequency, width and center fields.
3. All seven supported lifecycle/channel-change tokens used context priority.
4. Radar-token lookalikes and unrelated events were ignored.
5. Invalid interface was rejected.
6. Multiline log injection was rejected.
7. Shell metacharacters remained literal data, without execution.
8. Logger failure propagated as a nonzero exit.
9. Collector preflight failed visibly for the missing `hostapd_cli` dependency.

These checks supplement, rather than replace, the original
[64-test local verification](../VERIFICATION.md#historical-r1-checkpoint).

## Observation and unchanged state

- The existing log buffer contained no `DFS-RADAR-DETECTED` token.
- Both readable ath10k `dfs_stats` files reported zero PHY errors, pulse events
  and detected radars at inspection time.
- Before/after SHA-256 hashes matched for `/etc/config/wireless`,
  `/etc/config.mesh/aredn` and `/etc/config/network`.
- The active interface mode/channel remained unchanged. The detector was not
  installed, enabled or left running; only temporary staging files remain.

Zero counters and absent messages on this configuration do **not** demonstrate
absence of physical radar, working DFS coverage, or successful live subscription.
Real AP event delivery, installation/start/stop behavior on an eligible target,
and genuine reported hits still need field validation.

## Community validation and maintenance

The maintainer's own network is not experiencing interference problems, so
community feedback and real-world hit examples are needed. Useful reports include
firmware/build, hardware/driver, interface mode, configured frequency/width,
event-source availability, timestamped original radar messages with `freq`, and
surrounding CAC/NOP/channel-change context. Separate actual observed reports from
synthetic tests, missing coverage, and unrelated slow links. Redact credentials
and private identifiers; do not publish full configuration backups.

This separate APK will continue to be maintained through and after the next
AREDN stable release, with compatibility checks against stable firmware and
improvements informed by community reports. It remains experimental until
installation and genuine event-source behavior have been qualified.
