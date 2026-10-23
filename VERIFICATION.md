# Verification

## Current r2 source candidate

**95/95 tests passed, none skipped**, on 2026-10-23 with Python 3.12.3,
`/bin/sh`, BusyBox ash/applets, native ucode, fakeroot and official apk-tools
3.0.5. Full receipt: [docs/test-results-0.1.0-r2.txt](docs/test-results-0.1.0-r2.txt).

```sh
APK=/path/to/apk-tools-3 UCODE=/path/to/native/ucode \
  AREDN_SOURCE=/path/to/pinned/aredn-source \
  python3 -m unittest discover -s . -p 'test_*.py' -v
```

- **82 detector/banner/noise checks**: all original protocol tests, event-to-banner
  flows, native envelope and escaping, atomic replacement, unrelated message
  preservation, and explicit simulation separation. Noise checks include
  off-channel-first surveys, matching in-use selection, post-switch labeling,
  absent/invalid/ambiguous/failed readings, channel/interface changes during
  sampling, no noise reads for context/clear, and remote-log isolation.
- Three native rendering tests execute the exact AREDN message reader/template
  with isolated imports/filesystem bindings. Both files match the pinned public
  revision `8c028e999413c0640b89b3e1102aae9e402d0d44`; hashes and reproducible
  setup are in [reference provenance](docs/reference/banner-provenance.json)
  and [BUILD.md](BUILD.md). No native UI source is shipped in the APK.
- **13 package/service checks**: the existing source/transport, lifecycle and
  reproducible artifact checks, plus opt-in banner environment/defaults and
  scoped uninstall cleanup while upgrade retains the last report.
- The actual r2 APK builds twice to identical bytes, verifies with apk-tools,
  and extracts to the five exact expected payload files with executable modes
  and root:root ownership. The new file is the shell banner helper; Python and
  native web templates remain outside the package.

The local helper/noise display was also verified on the authorized test node
through its native reader and live HTTP response. See
[the sanitized live summary](docs/DEV1-BANNER-VALIDATION.md). This does not
qualify the r2 package/service on that node or establish genuine DFS detection.
No node was changed as part of this repository integration. The published r1
release and checksum remain unchanged; r2 is a source/build candidate only.

## Historical r1 checkpoint

Verified locally on 2026-10-23 using Python 3.12.3, `/bin/sh`, BusyBox ash,
fakeroot and the OpenWrt host build of apk-tools 3.0.5.

### Results

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

### Test boundaries

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
