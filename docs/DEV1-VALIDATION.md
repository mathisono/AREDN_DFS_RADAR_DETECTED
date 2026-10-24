# Dev1 validation — 2026-10-23

## Follow-up on RC `20261023-b3502ade`

Rechecked on 2026-10-24 UTC (2026-10-23 local). The simulated announcement was
removed at the owner's request. No simulated event was injected into hostapd,
netlink, debugfs, or the real syslog stream.

The remaining limitations are **three separate gates**, not just a missing APK:

1. **Tool availability.** The node's five configured AREDN snapshot feeds were
   refreshed successfully into a private temporary cache. Neither
   `hostapd-utils` nor `coreutils-timeout` was present among the 261 available
   packages. A fresh install simulation could not resolve either. `hostapd_cli`
   and the BusyBox `timeout` applet remain absent. This is evidence about those
   exact feeds, not all OpenWrt/AREDN versions. No unrelated repository,
   dependency override, wpad replacement, or tool installation was used.
2. **Active event source.** The only active interface is 2.4 GHz IBSS. The 5 GHz
   radio is disabled, with no AP interface, per-interface hostapd socket, or
   `hostapd.*` ubus object. The hostapd-capable `wpad-mini` binary is installed;
   absence of a running AP feed is distinct from absence of that binary.
3. **DFS configuration.** `iw reg get` reports `country HX: DFS-UNSET` globally
   and on both PHYs. `iw phy phy1 info` lists no radar-marked channels, including
   5500 and 5660 MHz. The matching
   [AREDN HX patch](https://github.com/aredn/aredn/blob/b3502adec92b863adbd2a7378221548a016f9d13/patches/702-enable-country-hx.patch)
   defines its frequency ranges without DFS flags. Advertised **radar-detect
   widths** are driver capabilities, not proof that detection is enabled.
   Enabling an AP alone under this observed profile would not establish the
   normal DFS/CAC/radar-report path.

Both ath10k `dfs_block_radar_events` values were `N`; pulse/radar counters were
zero. This does not demonstrate a functioning detector or the absence of
physical radar. No regulatory profile, radio role, channel, firmware, or driver
was changed to obtain evidence.

For genuine capture, select an AP whose firmware actually enables DFS on its
operating channel and qualify its existing log/socket/ubus source. Existing
`logread` or `ubus subscribe` paths can avoid the missing client/timeout package
dependencies altogether; they still require a functioning source. See
[OPENWRT.md](../OPENWRT.md). This project records reports from that source; it
does not turn an unqualified radio into an independent radar receiver.

The r2 parser/banner/package suite passed **95/95 isolated tests** against this
RC's announcement renderer. A real radar event remains **not captured**.

The native wrong-channel-noise problem was separately reconfirmed in three
hardware samples: current 2397 MHz was −101 dBm, while the installed helper
returned −90 dBm from cached 2387 MHz. This is not radar evidence. The exact
open PR helper returned the correct live noise value, while the independent
remote-SNR consumer still selected the wrong entry. Evidence was added to the
[existing open issue](https://github.com/aredn/aredn/issues/2952#issuecomment-6378500771),
not filed as a duplicate.

## Earlier RC13 checkpoint

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
