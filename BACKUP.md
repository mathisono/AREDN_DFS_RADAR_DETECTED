# Backup and recovery

The GitHub repository is the source backup; release assets contain the installable
APK and its SHA-256 manifest. Each release's tag identifies the exact source.
GitHub also provides source ZIP/tar archives for that tag. Source archives alone
do not contain ignored build artifacts: retain the release APK as well.

Before publication, the original prototype (including its original notes and
test receipts) was archived locally with per-file SHA-256 hashes. Those private
notes are intentionally not published. The original working directory is left
untouched. A post-publication Git bundle and released files are also retained
locally; exact private backup paths are reported to the owner, not embedded here.

## Make another independent backup

```sh
git clone --mirror https://github.com/mathisono/AREDN_DFS_RADAR_DETECTED.git detector.git
git -C detector.git bundle create ../aredn-dfs-radar.bundle --all
git -C detector.git bundle verify ../aredn-dfs-radar.bundle
gh release download v0.1.0-r1 --repo mathisono/AREDN_DFS_RADAR_DETECTED --dir release-v0.1.0-r1
(cd release-v0.1.0-r1 && sha256sum -c SHA256SUMS)
```

## Restore

```sh
git clone aredn-dfs-radar.bundle aredn-dfs-radar
cd aredn-dfs-radar
git checkout v0.1.0-r1
python3 -m unittest discover -s . -p 'test_*.py' -v
python3 build.py --apk /path/to/apk-tools-3
```

This backs up the software, not volatile router syslog. Preserve field evidence
separately and privately, with original timestamps, source/node/boot identity,
firmware identity, collector diagnostics and gap records. Never commit credentials
or private captures into this public repository.
