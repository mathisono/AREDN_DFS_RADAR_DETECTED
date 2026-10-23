"""Package/service checks isolated from router, system syslog and real hostapd."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
COLLECTOR = ROOT / 'files/usr/sbin/aredn-dfs-collector'
INIT = ROOT / 'files/etc/init.d/aredn-dfs-detector'


class CollectorTests(unittest.TestCase):
    def setUp(self):
        runtime = tempfile.TemporaryDirectory(prefix='dfs-package-', dir='/tmp')
        self.addCleanup(runtime.cleanup)
        self.tmp = Path(runtime.name)
        self.calls = self.tmp / 'calls.jsonl'
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.addCleanup(self.socket.close)
        self.socket.bind(str(self.tmp / 'test0'))
        cli = self.tmp / 'hostapd_cli'
        cli.write_text(f'#!{sys.executable}\n'
                       'import os,sys,json\n'
                       'with open(os.environ["DFS_CALLS"],"a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\n'
                       'if sys.argv[-1] == "ping":\n'
                       ' print(os.environ.get("DFS_PONG","PONG"))\n'
                       ' sys.exit(int(os.environ.get("DFS_PING_RC","0")))\n'
                       'sys.exit(0)\n')
        cli.chmod(0o755)
        logger = self.tmp / 'logger'
        logger.write_text('#!/bin/sh\nexit 0\n')
        logger.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.tmp) + os.pathsep + os.environ['PATH'],
                        DFS_CALLS=str(self.calls))

    def run_collector(self, *args, script=COLLECTOR):
        return subprocess.run(['/bin/sh', str(script), *map(str, args)],
                              env=self.env, capture_output=True, text=True, timeout=8)

    def test_missing_socket_never_contacts_hostapd(self):
        result = self.run_collector('--check', 'missing', self.tmp)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('socket is missing', result.stderr)
        self.assertFalse(self.calls.exists())

    def test_regular_file_is_not_a_socket(self):
        (self.tmp / 'regular').write_text('not a socket')
        result = self.run_collector('--check', 'regular', self.tmp)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.calls.exists())

    def test_bad_interface_and_relative_directory_rejected(self):
        for interface, directory in [('-i', self.tmp), ('bad iface', self.tmp),
                                     ('bad;echo', self.tmp), ('test0', 'relative')]:
            # Leading '-' is syntactically accepted as interface data after -i;
            # without a real socket it must still fail before invoking anything.
            result = self.run_collector('--check', interface, directory)
            self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.calls.exists())

    def test_check_sends_only_ping_and_does_not_claim_dfs_coverage(self):
        result = self.run_collector('--check', 'test0', self.tmp)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('NOT verified', result.stdout)
        self.assertEqual(json.loads(self.calls.read_text()),
                         ['-p', str(self.tmp), '-i', 'test0', 'ping'])

    def test_bad_pong_and_failed_ping_stop_collection(self):
        for fields in [{'DFS_PONG': 'FAIL'}, {'DFS_PING_RC': '7'}]:
            self.env.update(fields)
            result = self.run_collector('--check', 'test0', self.tmp)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('unavailable', result.stderr)
            for name in fields:
                del self.env[name]

    def test_zero_exit_of_action_cli_is_a_coverage_failure(self):
        # Rebase only the fixed installed helper path into this test's staging
        # directory; run the actual launcher logic and mock only hostapd_cli.
        helper = self.tmp / 'action.sh'
        helper.write_text('#!/bin/sh\nexit 0\n')
        helper.chmod(0o755)
        script = self.tmp / 'collector'
        original = COLLECTOR.read_text()
        self.assertEqual(original.count('/usr/libexec/aredn-dfs-action.sh'), 1)
        script.write_text(original.replace('/usr/libexec/aredn-dfs-action.sh', str(helper)))
        result = self.run_collector('test0', self.tmp, script=script)
        self.assertEqual(result.returncode, 1)
        self.assertIn('exited (0); coverage gap', result.stderr)
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertEqual(calls[-1], ['-p', str(self.tmp), '-i', 'test0', '-a', str(helper)])
        self.assertTrue((self.tmp / 'test0').exists())


class ServiceTests(unittest.TestCase):
    def run_service(self, enabled, interface='test0', directory='/var/run/hostapd', banner=0):
        harness = r'''
config_load() { :; }
config_get_bool() {
    case "$1" in
      enabled) enabled=$TEST_ENABLED ;;
      banner) banner=$TEST_BANNER ;;
    esac
}
config_get() {
    case "$1" in
      interface) interface=$TEST_INTERFACE ;;
      control_dir) control_dir=$TEST_DIRECTORY ;;
    esac
}
procd_open_instance() { echo OPEN; }
procd_close_instance() { echo CLOSE; }
procd_set_param() { printf '<%s>\n' "$@"; }
. "$TEST_INIT"
start_service
'''
        env = dict(os.environ, TEST_INIT=str(INIT), TEST_ENABLED=str(enabled),
                   TEST_INTERFACE=interface, TEST_DIRECTORY=directory, TEST_BANNER=str(banner))
        return subprocess.run(['/bin/sh', '-c', harness], env=env,
                              text=True, capture_output=True, timeout=3)

    def test_disabled_default_starts_nothing(self):
        self.assertIn("option enabled '0'", (ROOT / 'files/etc/config/aredn-dfs-detector').read_text())
        result = self.run_service(0)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')

    def test_incomplete_configuration_starts_nothing(self):
        for interface, directory in [('', '/var/run/hostapd'), ('test0', '')]:
            result = self.run_service(1, interface, directory)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, '')

    def test_enabled_service_preserves_arguments_without_auto_respawn(self):
        result = self.run_service(1, 'test0', '/tmp/control directory')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('</usr/sbin/aredn-dfs-collector>\n<test0>\n</tmp/control directory>', result.stdout)
        self.assertNotIn('<respawn>', result.stdout)

    def test_banner_is_disabled_by_default_and_only_exports_packaged_helper_when_enabled(self):
        self.assertIn("option banner '0'", (ROOT / 'files/etc/config/aredn-dfs-detector').read_text())
        disabled = self.run_service(1)
        self.assertEqual(disabled.returncode, 0, disabled.stderr)
        self.assertIn('<DFS_BANNER_HELPER=>', disabled.stdout)
        enabled = self.run_service(1, banner=1)
        self.assertEqual(enabled.returncode, 0, enabled.stderr)
        self.assertIn('<DFS_BANNER_HELPER=/usr/libexec/aredn-dfs-banner.sh>', enabled.stdout)
        self.assertEqual(self.run_service(0, banner=1).stdout, '')

    def test_remove_clears_only_owned_banner_but_upgrade_retains_last_report(self):
        with tempfile.TemporaryDirectory(prefix='dfs-remove-') as temp:
            tmp = Path(temp)
            messages = tmp / 'messages'
            messages.mkdir()
            owned = messages / 'aredn-dfs-detection-test'
            owned.write_text('last report')
            other = messages / 'another-addon'
            other.write_text('keep')
            init = tmp / 'init'
            init.write_text('#!/bin/sh\nexit 0\n')
            init.chmod(0o755)
            for name in ['pre-upgrade', 'pre-deinstall']:
                hook = tmp / name
                source = (ROOT / 'package' / name).read_text()
                source = source.replace('/etc/init.d/aredn-dfs-detector', str(init))
                source = source.replace('/usr/libexec/aredn-dfs-banner.sh', str(ROOT / 'dfs_banner.sh'))
                hook.write_text(source)
                result = subprocess.run(['/bin/sh', str(hook)],
                                        env=dict(os.environ, IPKG_INSTROOT='', DFS_BANNER_DIR=str(messages)),
                                        capture_output=True, text=True, timeout=3)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(owned.exists(), name == 'pre-upgrade')
                self.assertEqual(other.read_text(), 'keep')

    def test_image_root_lifecycle_hooks_do_not_touch_host_services(self):
        for hook in ['pre-upgrade', 'pre-deinstall']:
            result = subprocess.run(['/bin/sh', str(ROOT / 'package' / hook)],
                                    env=dict(os.environ, IPKG_INSTROOT='/not-the-live-root'),
                                    capture_output=True, timeout=3)
            self.assertEqual(result.returncode, 0)


@unittest.skipUnless(os.environ.get('APK'), 'set APK to run real apk-tools artifact verification')
class PackageArtifactTests(unittest.TestCase):
    def test_reproducible_apk_verified_and_exact_payload_extracted(self):
        apk = os.environ['APK']
        with tempfile.TemporaryDirectory(prefix='dfs-artifact-') as temp:
            tmp = Path(temp)
            outputs = []
            for name in ['first', 'second']:
                out = tmp / name
                subprocess.run([sys.executable, str(ROOT / 'build.py'), '--apk', apk,
                                '--output', str(out)], check=True, capture_output=True)
                outputs.append(next(out.glob('*.apk')))
            self.assertEqual(outputs[0].read_bytes(), outputs[1].read_bytes())
            digest = hashlib.sha256(outputs[0].read_bytes()).hexdigest()
            self.assertIn(digest, (outputs[0].parent / 'SHA256SUMS').read_text())
            subprocess.run([apk, '--allow-untrusted', 'verify', str(outputs[0])],
                           check=True, capture_output=True)
            metadata = subprocess.run([apk, '--allow-untrusted', 'adbdump', str(outputs[0])],
                                      check=True, capture_output=True, text=True).stdout
            self.assertIn('arch: noarch', metadata)
            self.assertIn('- hostapd-utils', metadata)
            self.assertNotIn('post-install:', metadata)
            owners = re.findall(r'^\s+(?:user|group): (.+)$', metadata, re.M)
            self.assertTrue(owners)
            self.assertEqual(set(owners), {'root'})
            self.assertIn('pre-deinstall:', metadata)
            dest = tmp / 'extract'
            dest.mkdir()
            subprocess.run([apk, '--allow-untrusted', 'extract', '--no-chown',
                            '--destination', str(dest), str(outputs[0])], check=True, capture_output=True)
            expected = {p.relative_to(ROOT / 'files'): p for p in (ROOT / 'files').rglob('*') if p.is_file()}
            expected[Path('usr/libexec/aredn-dfs-action.sh')] = ROOT / 'dfs_action.sh'
            expected[Path('usr/libexec/aredn-dfs-banner.sh')] = ROOT / 'dfs_banner.sh'
            actual = {p.relative_to(dest) for p in dest.rglob('*') if p.is_file()}
            self.assertEqual(actual, set(expected))
            for relative, source in expected.items():
                self.assertEqual((dest / relative).read_bytes(), source.read_bytes())
                self.assertEqual((dest / relative).stat().st_mode & 0o777,
                                 0o644 if str(relative).startswith('etc/config/') else 0o755)


if __name__ == '__main__':
    unittest.main()
