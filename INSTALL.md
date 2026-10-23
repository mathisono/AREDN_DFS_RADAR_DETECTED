# Install, configure and remove the OpenWrt APK

## Compatibility and dependency check

This unsigned, architecture-independent shell package targets **apk-tools 3.x
AREDN/OpenWrt** with procd/UCI/BusyBox. It does not include a kernel module,
driver, hostapd replacement, Python runtime or web UI. The matching firmware
feed must provide `hostapd-utils` (`hostapd_cli`); do not use Alpine repositories
or an unrelated firmware feed to satisfy this dependency. If the firmware uses
opkg, stop: this APK is not an IPK. No target-specific live installation has
yet been qualified.

Download the APK and `SHA256SUMS` from the same GitHub release, then on the
monitoring computer:

```sh
sha256sum -c SHA256SUMS
scp aredn-dfs-detector-0.1.0-r1.apk field-ap:/tmp/
```

`field-ap` is an example of your already-authorized SSH alias. On that node:

```sh
apk --version
apk add --simulate --allow-untrusted /tmp/aredn-dfs-detector-0.1.0-r1.apk
```

Review the simulation. Expected new software is this package and, if missing,
firmware-compatible `hostapd-utils` dependencies. Do not proceed if it proposes
radio/driver/firmware replacements. Do not run `apk upgrade` or disable dependency
checks to install it. `--allow-untrusted` applies to this locally supplied,
unsigned APK; the checksum detects mismatched bytes, not publisher identity.

```sh
apk add --allow-untrusted /tmp/aredn-dfs-detector-0.1.0-r1.apk
```

Installation does **not** start or enable the collector. Installed files:

| Path | Purpose |
|---|---|
| `/usr/libexec/aredn-dfs-action.sh` | Exact-token DFS/context relay to syslog |
| `/usr/sbin/aredn-dfs-collector` | Validated hostapd_cli launcher |
| `/etc/config/aredn-dfs-detector` | Disabled UCI defaults |
| `/etc/init.d/aredn-dfs-detector` | Opt-in procd service |

## Choose the actual source

Read-only discovery examples (paths vary by firmware):

```sh
command -v hostapd_cli
ls -l /var/run/hostapd* /run/hostapd* 2>/dev/null
iw dev
iw reg get
```

Choose the AP's actual interface and **existing** per-interface socket. Do not
enable/change hostapd control interfaces, DFS or wireless settings just for this
package. For the examples below only, assume socket `/var/run/hostapd/wlan0`:

```sh
aredn-dfs-collector --check wlan0 /var/run/hostapd
```

A responsive socket is not proof that the radio emits radar reports. Confirm
source capability on the actual firmware. A foreground collection session is:

```sh
aredn-dfs-collector wlan0 /var/run/hostapd
```

Stop it with Ctrl-C before starting the service; running both would duplicate
reports. Keep its diagnostics. Check the configured logger/remote-syslog policy.

## Explicitly enable collection

Substitute the discovered interface/directory; do not copy placeholder values
blindly. These UCI writes affect **only this detector**, not wireless settings:

```sh
uci set aredn-dfs-detector.main.interface='wlan0'
uci set aredn-dfs-detector.main.control_dir='/var/run/hostapd'
uci set aredn-dfs-detector.main.enabled='1'
uci commit aredn-dfs-detector
/etc/init.d/aredn-dfs-detector enable
/etc/init.d/aredn-dfs-detector start
/etc/init.d/aredn-dfs-detector status
logread -e hostapd-dfs
```

The service does not automatically restart after source loss. Investigate its
diagnostics, then explicitly restart it and retain the gap in your evidence.
`status`/PING means process/transport state, not verified radar coverage.

For JSON output, run from the repository on the monitoring computer (Bash):

```sh
set -o pipefail
ssh -T field-ap 'logread -f' | \
  python3 dfs_detector.py --node field-ap --relay-only > radar-events.jsonl
```

Preserve original timestamps; optionally supply `--boot-id` from
`cat /proc/sys/kernel/random/boot_id` on the source node. Logread may replay a
buffer; consumers should deduplicate `event_id`. Only use `--summary` for finite
saved input. Store field logs privately, outside this public repository.

## Upgrade, stop and remove

Back up the detector config before upgrade. APK normally protects locally
modified `/etc` files; review any `.apk-new` file rather than assuming defaults
were merged. The pre-upgrade hook stops collection and does not restart it.
After reviewing/rechecking configuration, explicitly start the service again.
The node log gap is not a zero-hit interval.

```sh
/etc/init.d/aredn-dfs-detector stop
/etc/init.d/aredn-dfs-detector disable
uci set aredn-dfs-detector.main.enabled='0'
uci commit aredn-dfs-detector
apk del aredn-dfs-detector
```

The removal hook also stops/disables the service. Modified configuration may
be retained by APK. Removal does not clear syslog, uninstall the radio driver,
restart wireless, or erase your exported observations. Firmware sysupgrades may
require reinstalling the package; this project adds no sysupgrade policy.
