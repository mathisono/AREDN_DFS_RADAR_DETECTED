# Build and verify

## Requirements

- Linux with Python 3.10+ standard library.
- `fakeroot` for unprivileged builds (for example `sudo apt-get install fakeroot`
  on Debian/Ubuntu). The builder invokes it automatically and stores root:root
  ownership in the package; no actual root privilege is needed.
- Official **apk-tools 3.x** with the `mkpkg` applet, from a matching OpenWrt
  SDK/build tree or a trusted installation. Alpine apk-tools 2.x cannot build
  this APK v3 artifact.
- BusyBox for additional ash tests (if absent, that optional shell variant is
  not exercised; `/bin/sh` still is).

```sh
python3 -m unittest discover -s . -p 'test_*.py' -v
python3 build.py --apk /path/to/openwrt/staging_dir/host/bin/apk
```

Alternatively set `APK=/path/to/apk` or put apk-tools 3.x on PATH. The builder
normalizes modes/timestamps and uses `SOURCE_DATE_EPOCH` (default 2026-10-23
00:00 UTC). Same source, epoch and tool version should yield identical bytes.
It uses a temporary staging directory and does not run node install scripts.

Outputs:

- `artifacts/aredn-dfs-detector-0.1.0-r1.apk`
- `artifacts/SHA256SUMS`

The artifact is unsigned and `noarch`: its installed payload is shell/config
only. It declares `busybox hostapd-utils procd uci` dependencies. It deliberately
does not bundle host Python or hostapd/driver binaries. The package metadata
uses `LicenseRef-Unspecified`; no project license has been selected.

## Inspect the actual artifact

```sh
cd artifacts
sha256sum -c SHA256SUMS
/path/to/apk --allow-untrusted adbdump aredn-dfs-detector-0.1.0-r1.apk
```

The `test_package.py` tests also verify the disabled service, bounded source
checks, full action arguments, and no-auto-respawn service command. To exercise
real APK extraction with official apk-tools:

```sh
APK=/path/to/apk python3 -m unittest test_package.PackageArtifactTests -v
```

The optional artifact test builds twice, compares bytes, verifies/extracts with
apk-tools, and checks exact installed file content and executable modes. It does
not install onto a live router or satisfy dependencies from public feeds.

## Version and release

Change `VERSION` for new payloads; never silently replace a published APK. Run
tests and inspect the resulting package. Publish it and SHA256SUMS together as
a GitHub release with a matching source tag. Prefer an experimental prerelease
until real-device validation has been documented. See [BACKUP.md](BACKUP.md).
