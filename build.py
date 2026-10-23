#!/usr/bin/env python3
"""Build an unsigned noarch OpenWrt APK v3 using official apk-tools 3.x."""
import argparse
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apk', default=os.environ.get('APK', 'apk'),
                        help='apk-tools 3.x executable (or set APK)')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts')
    args = parser.parse_args()
    # APK stores user/group names. Never bake the workstation owner's identity
    # into router files. fakeroot supplies root metadata without real privilege.
    if os.geteuid() != 0:
        if not shutil.which('fakeroot'):
            parser.error('install fakeroot to build root-owned files without sudo')
        os.execvp('fakeroot', ['fakeroot', sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]])
    version = (ROOT / 'VERSION').read_text().strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+-r\d+', version):
        parser.error('VERSION must be MAJOR.MINOR.PATCH-rN')
    args.output.mkdir(parents=True, exist_ok=True)
    package = args.output.resolve() / f'aredn-dfs-detector-{version}.apk'
    # Normalize timestamps and modes for reproducible output across checkouts.
    epoch = int(os.environ.get('SOURCE_DATE_EPOCH', '1792713600'))
    with tempfile.TemporaryDirectory(prefix='aredn-dfs-build-') as tmp:
        stage = Path(tmp) / 'root'
        shutil.copytree(ROOT / 'files', stage)
        action = stage / 'usr/libexec/aredn-dfs-action.sh'
        action.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / 'dfs_action.sh', action)
        for entry in [stage, *stage.rglob('*')]:
            executable = entry.is_dir() or entry == action or '/init.d/' in str(entry) or '/sbin/' in str(entry)
            entry.chmod(0o755 if executable else 0o644)
            os.chown(entry, 0, 0)
            os.utime(entry, (epoch, epoch))
        command = [args.apk, 'mkpkg', '--files', str(stage), '--output', str(package),
                   '--info', 'name:aredn-dfs-detector', '--info', f'version:{version}',
                   '--info', 'arch:noarch', '--info', f'build-time:{epoch}',
                   '--info', 'description:Passive DFS radar-report collector for AREDN/OpenWrt',
                   '--info', 'url:https://github.com/mathisono/AREDN_DFS_RADAR_DETECTED',
                   '--info', 'license:LicenseRef-Unspecified',
                   '--info', 'depends:busybox hostapd-utils procd uci',
                   '--script', f'pre-deinstall:{ROOT / "package/pre-deinstall"}',
                   '--script', f'pre-upgrade:{ROOT / "package/pre-upgrade"}']
        subprocess.run(command, check=True)
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    (args.output / 'SHA256SUMS').write_text(f'{digest}  {package.name}\n')
    print(f'{digest}  {package}')


if __name__ == '__main__':
    main()
