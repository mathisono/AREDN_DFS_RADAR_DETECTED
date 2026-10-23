# Detection-test announcement and channel noise

Available in **r2 source builds**; not in the published r1 APK. The optional
Python-free helper uses AREDN's existing local announcement reader. It does not
add or replace a web page, change wireless settings, or start radio recovery.

## What it shows

An explicit radar report displays the reported channel/frequency, node/interface,
receipt time and event source under **DFS detection test Messages**. The native
action also adds a passive noise-floor snapshot in dBm, with the **measured**
channel/frequency, interface, UTC read time and `iw survey` source.

- Only exact radar reports set the flag. CAC, NOP expiry, channel changes, noise
  levels and slow links neither create nor clear a radar announcement.
- One bounded file keeps the **latest report**, not counts, history, collector
  health, or a live DFS/NOP blacklist.
- Noise is the driver's noise-floor estimate, **not radar pulse strength** or
  proof of interference. The read timestamp is not a hardware sample timestamp.
- Noise is read once per banner update, not periodically. A web-page refresh
  displays the saved snapshot; it does not resample the radio.
- A driver report is not independent confirmation of a physical radar emitter.

The noise sampler reads `iw dev INTERFACE info`, `survey dump`, then `info`
again. Interface identity and channel must remain unchanged. It accepts only
one matching **`[in use]`** survey entry, never the first entry or a cached
off-channel reading. Missing, failed, ambiguous or invalid data is shown as
**unavailable**, not zero. No scan or tuning is performed.

If the radio has already changed channel, the current noise is explicitly
labeled as **not a measurement of the reported radar channel/interface**.
Matching-frequency readings are still post-report driver snapshots, not
measurements of the radar pulse. Missing event frequency stays unknown.

## Enable with an r2 package

First follow [INSTALL.md](INSTALL.md) to qualify the event source and configure
the disabled-by-default service. The announcement is separately opt-in:

```sh
uci set aredn-dfs-detector.main.banner='1'
uci commit aredn-dfs-detector
/etc/init.d/aredn-dfs-detector restart
```

This does not enable the collector if `main.enabled` is still `0`. The service
passes the packaged helper to its action, which samples the event's local
interface. `iw`/survey support is optional: without it, the radar banner still
appears with noise **unavailable**. The hostapd/timeout compatibility checks
remain required for collection.

To stop further banner updates, set `main.banner='0'`, commit and restart the
already-configured collector. The last announcement remains until cleared.

## Display-only test on an authorized node

No hostapd event source is needed for the banner's display-only test. Stage the
repository's `dfs_banner.sh` executable at `/tmp/dfs_banner.sh`, then select an
actual local interface discovered with `iw dev`:

```sh
DFS_BANNER_NOISE_IFACE=wlan0 sh /tmp/dfs_banner.sh demo "$(uname -n)"
```

The radar example is prominently **SIMULATED — display check only**, with
channel 132 / 5660 MHz as example data. Noise is a **real radio reading,
separate from the simulated radar report**; a 2.4 GHz noise sample must not be
mistaken for a measurement of the simulated 5 GHz channel. Without
`DFS_BANNER_NOISE_IFACE`, the demo reports noise **not sampled**.

To resample the noise without changing the demo report's receipt time, pass its
original UTC timestamp in `DFS_BANNER_OBSERVED_AT`. The noise read timestamp
is generated separately. Do not inject synthetic radar records into a live
hostapd/ubus source to test display.

For a real temporary foreground action subscription, stage both executable
shell helpers and use the discovered socket/interface:

```sh
DFS_BANNER_HELPER=/tmp/dfs_banner.sh \
  hostapd_cli -p /var/run/hostapd -i wlan0 -a /tmp/dfs_action.sh
```

See [OPENWRT.md](OPENWRT.md). Do not run this alongside the packaged collector.

## Native storage, visibility and cleanup

The helper atomically replaces only
`/tmp/other_messages/aredn-dfs-detection-test`, using the native single-line
message envelope with HTML-escaped text. It preserves unrelated announcements.
Default storage is RAM-backed and disappears on reboot. It does not download
or publish a mesh-wide announcement. Anyone who can view this node's status
page can see the banner; do not put credentials or private log payloads in it.

The reviewed native UI refreshes its message component every 300 seconds while
visible. Refresh/focus the page to display an update immediately. This does not
change the snapshot sampling behavior described above.

Stopping collection or upgrading retains the last report. Clear it explicitly:

```sh
# Packaged helper:
/usr/libexec/aredn-dfs-banner.sh clear
# Or, for the temporary display-only test:
sh /tmp/dfs_banner.sh clear
rm -f /tmp/dfs_banner.sh
```

The r2 uninstall hook clears only this task-owned announcement after stopping
the service. Other announcements and syslog are untouched. No new timer, cron
job, startup service or continuous noise monitor is introduced.

## Off-node Python output

```sh
python3 dfs_detector.py --node field-ap \
  --banner-dir /absolute/local/fixture-messages saved-logread.txt
```

This is an opt-in **local filesystem sink**, not a remote-node update. It needs
`aredn_banner.py` and executable `dfs_banner.sh` beside the detector. The Python
sink deliberately disables local noise reads: a workstation radio must not be
attributed to the node whose logs are being analyzed. Replay/synthetic input
should use an isolated directory. Without this option, output remains JSON-only.

## Verification boundary

See [VERIFICATION.md](VERIFICATION.md) for isolated parser, banner/noise,
native-renderer and package tests, and
[the sanitized live display summary](docs/DEV1-BANNER-VALIDATION.md).
Live display plus passive noise verification is not real DFS event validation.
