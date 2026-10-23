# Dev1 banner and passive-noise check — 2026-10-23

This supplements the [r1 package-format check](DEV1-VALIDATION.md). It validates
the **display helper and a passive noise read**, not installation of the r2
package or a real radar detection.

The existing authorized test node was a MikroTik hAP ac3 running AREDN
`20261013-8c028e99`, kernel `6.12.94`. Only a 2.4 GHz IBSS interface was active;
no active AP radar-event feed was available. No collector was started.

## Checks completed

- Staged the helper and its single local announcement in RAM only.
- Used the explicit `demo` path, labeled **SIMULATED — display check only**.
  No fabricated event entered hostapd, ubus or live syslog.
- Added a real noise-floor snapshot for the active radio, with its own measured
  frequency/interface and UTC read timestamp. The radio's survey contained
  cached off-channel entries; only the matching `[in use]` entry was selected.
- Kept the real 2.4 GHz reading explicitly separate from the simulated 5 GHz
  radar example. Refreshing the measurement preserved the demo report's
  original receipt time and updated the independent noise read time.
- Verified the helper output in AREDN's installed native message reader and
  the live HTTP 200 status-page response, including the simulation disclaimer.
- The installed reader/template hashes matched the pinned source in
  [banner provenance](reference/banner-provenance.json).
- The owner confirmed the banner's appearance. Automated browser inspection
  was policy-blocked, so no automated visual-rendering claim is made.

Configuration/native-source hashes, boot ID, radio structure, service identity
and PIDs, routing rules, firewall structure, wired management route and
unrelated announcements were unchanged. Learned mesh routes changed during
observation; raw differences were retained privately, with no routing writes.
No scan, radio restart, tuning, regulatory change or recovery action occurred.

## Limits and retained evidence

The helper and message are volatile, not a boot-persistent monitor. The noise
value is a driver snapshot, not a hardware-timestamped measurement or radar
pulse strength. Actual AP-side event capture, r2 installation/service operation
on an eligible target, and genuine radar reports remain pending.

Private receipts retain source hashes, before/after state, raw survey output,
the live page response and scoped cleanup checks. Node addresses, identifying
radio details, credentials and private telemetry are intentionally omitted here.
Public synthetic tests contain fixture values, not field logs.
