# Verification — 0.1.0-r1

Verified locally on 2026-10-23 using Python 3.12.3, `/bin/sh`, BusyBox ash,
fakeroot and the OpenWrt host build of apk-tools 3.0.5.

## Results

**64/64 tests passed, none skipped** with `APK` set to the official apk-tools
executable. Full receipt: [docs/test-results-0.1.0-r1.txt](docs/test-results-0.1.0-r1.txt).

```sh
APK=/path/to/apk-tools-3 python3 -m unittest discover -s . -p 'test_*.py' -v
```

- Original prototype's **53 tests** preserved: event classification, frequency
  attribution, source/replay identity, summaries, native ubus JSON and shell
  relay argument handling, plus temporary UNIX datagram control peers.
- **11 package/service tests**: missing/non-socket sources, input validation,
  bounded PING failure handling, zero CLI exit treated as a coverage gap,
  disabled and incomplete-config startup, exact service arguments, no respawn,
  image-root lifecycle isolation and real APK artifact verification.
- Artifact test builds twice with normalized timestamps and compares exact
  bytes; `apk verify --allow-untrusted` succeeds. Extraction matches every
  expected payload byte, executable mode and root:root metadata.
- Installed payload is four files: config, procd init script, collector and
  action helper. No radio/driver, firmware, Python or web API files are included.
- Shell syntax checked using `/bin/sh` and BusyBox ash.

Current package SHA-256 is recorded in the release's `SHA256SUMS`. Unsigned
package verification checks format/integrity, not signature trust.

## Test boundaries

Socket tests use actual temporary UNIX sockets with **synthetic** peers, not a
radio. Relay tests run the actual action with a fake logger, avoiding host
syslog writes. Launcher checks use a fake hostapd_cli; service checks use a
procd/UCI harness. Real APK extraction is not a live-node installation or a
dependency-resolution test against a target firmware feed. Tests do not prove
that a particular firmware exposes the required socket or emits radar events.

No node was contacted, installed, reconfigured, scanned or restarted as part
of this packaging task. No genuine radar report was captured. No public AREDN
JSON change or upstream request was made. Real target installation and genuine
AP event-source confirmation remain pending; this is an **experimental** release.

The earlier prototype checkpoints passed 15, then 35, then 53 tests. Original
notes and receipts are retained in the owner's private pre-publication backup.
Protocol source references are preserved in [docs/reference](docs/reference).
