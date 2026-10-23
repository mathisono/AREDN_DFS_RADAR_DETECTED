# Changelog

## 0.1.0-r2 — source candidate, not yet released

- Opt-in native AREDN announcement for the latest explicit radar report.
- Python-free driver noise snapshot with measured channel/frequency, interface
  and UTC read time; strict active-entry selection and unavailable-data handling.
- Prominent simulated-demo labeling, separate from real radio noise readings.
- Local Python `--banner-dir` sink; never samples a workstation radio for remote logs.
- Package includes the shell helper, `main.banner` defaults to disabled, and
  uninstall clears only this package's announcement. Stop/upgrade retain the
  last report until explicit clear.
- 95 isolated tests pass with no skips, including native AREDN rendering and
  reproducible five-file APK payload verification.
- Sanitized live display/noise notes; real AP radar and r2 package installation
  qualification remain pending. The existing `timeout` prerequisite is unchanged.

## 0.1.0-r1 — published experimental release

- Passive hostapd action collection, optional off-node log/socket/ubus analysis,
  disabled-by-default APK service, documentation and 64 isolated checks.
- Native package-format/extraction and nine synthetic handler checks on Dev1;
  no successful live installation or genuine radar-event qualification.
