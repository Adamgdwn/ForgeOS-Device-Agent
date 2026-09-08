"""Exercise exact property bytes and simulated recovery mount transitions.

Host tests substitute paths/block-file checks and simulate kernel mount/SELinux
operations. SHA-256, file edits, mode/ownership and shell control flow are real.
They do not prove recovery kernel behavior or effective Android ADB policy.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import stat
import subprocess
import tempfile
import unittest
import zipfile

REPO = Path(__file__).resolve().parents[1]
POLICY = REPO / 'appliance/recovery-policy'
BINARY = POLICY / 'META-INF/com/google/android/update-binary'
BUILDER = POLICY / 'build_recovery_policy_zip.py'
FIXTURE = REPO / 'tests/fixtures/gteslte/build.prop'
SOURCE_HASH = 'b9af705d7c15b09577725f74a8e694705e0d44a0b5f0a639c8cccc4d3e05b15a'
TARGET_HASH = '83af1087bdc8943f1236d2bc057ecc73b0d42e0e411d979d54cad0f8f6f1770a'

STUB = r'''#!/usr/bin/python3
import json,os,pathlib,shutil,signal,sys
c=json.loads(pathlib.Path(os.environ['FIXTURE_CONFIG']).read_text())
a=sys.argv[1:];tool=pathlib.Path(sys.argv[0]).name
m=pathlib.Path(c['mountpoint']);table=pathlib.Path(c['mounts'])
with open(c['log'],'a') as f:f.write(tool+' '+repr(a)+'\n')
if tool=='getprop':
 print(c.get('device','gteslte'));sys.exit(0)
if tool=='mount':
 if c.get('mount_fails'):sys.exit(1)
 assert a==['-t','ext4','-o','rw',c['block'],c['mountpoint']]
 (m/'system').mkdir();shutil.copy2(c['backing'],m/'system/build.prop')
 src=c.get('mount_source',c['block']);opts=c.get('mount_options','rw,relatime')
 table.write_text(f'{src} {m} ext4 {opts} 0 0\n');sys.exit(0)
if tool=='umount':
 if c.get('unmount_fails'):sys.exit(1)
 assert a==[c['mountpoint']]
 if (m/'system/build.prop').exists():shutil.copy2(m/'system/build.prop',c['backing'])
 shutil.rmtree(m/'system');table.write_text('');sys.exit(0)
if tool=='ls':
 print(c.get('label','u:object_r:system_file:s0')+' '+a[-1]);sys.exit(0)
if tool=='chcon':
 if c.get('signal_at_label'):os.kill(os.getppid(),signal.SIGTERM)
 if c.get('label_fails'):sys.exit(1)
 assert a[0]=='u:object_r:system_file:s0';sys.exit(0)
if tool=='sync':sys.exit(0)
raise AssertionError(tool)
'''


class RecoveryPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='forgeos-policy-test-')
        self.root = Path(self.temp.name)
        self.bin = self.root/'bin';self.bin.mkdir()
        self.backing=self.root/'backing.prop';shutil.copyfile(FIXTURE,self.backing)
        self.backing.chmod(0o644)
        self.block=self.root/'SYSTEM';self.block.touch()
        self.size=self.root/'size';self.size.write_text('6144000\n')
        self.mounts=self.root/'mounts';self.mounts.write_text('')
        self.fstab=self.root/'fstab';self.fstab.write_text(f'{self.block} /system ext4 ro wait,recoveryonly\n')
        self.mountpoint=self.root/'private-mount'
        self.log=self.root/'calls.log'
        self.config={'mountpoint':str(self.mountpoint),'mounts':str(self.mounts),
                     'block':str(self.block),'backing':str(self.backing),'log':str(self.log)}
        for tool in ('sha256sum','sed','rm','stat','chown','chmod','mv','readlink','cat','mkdir','rmdir'):
            os.symlink(shutil.which(tool),self.bin/tool)
        for tool in ('getprop','mount','umount','ls','chcon','sync'):
            p=self.bin/tool;p.write_text(STUB);p.chmod(0o755)
        script=BINARY.read_text()
        replacements={'SYSTEM_BLOCK':self.block,'EXPECTED_BLOCK':self.block,
                      'BLOCK_SIZE_FILE':self.size,'MOUNT_POINT':self.mountpoint,
                      'MOUNTS':self.mounts,'FSTAB':self.fstab}
        lines=script.splitlines()
        for i,line in enumerate(lines):
            name=line.split('=',1)[0]
            if name in replacements:lines[i]=name+'='+shlex.quote(str(replacements[name]))
        script='\n'.join(lines)+'\n'
        script=script.replace('[ -b "$SYSTEM_BLOCK" ]','[ -f "$SYSTEM_BLOCK" ]')
        self.script=self.root/'update-binary';self.script.write_text(script)

    def tearDown(self):
        self.temp.cleanup()

    def run_policy(self, **options):
        self.config.update(options)
        c=self.root/'config.json';c.write_text(json.dumps(self.config))
        return subprocess.run(['/bin/sh',str(self.script),'3','1','/irrelevant.zip'],
                              capture_output=True,text=True,timeout=10,
                              env={'PATH':str(self.bin),'FIXTURE_CONFIG':str(c)})

    def assert_clean_mount(self):
        self.assertEqual(self.mounts.read_text(),'')
        self.assertFalse(self.mountpoint.exists())

    def test_real_fixture_hash_and_apply_after_gapps_unmounted(self):
        self.assertEqual(hashlib.sha256(self.backing.read_bytes()).hexdigest(),SOURCE_HASH)
        original=self.backing.stat()
        r=self.run_policy()
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(hashlib.sha256(self.backing.read_bytes()).hexdigest(),TARGET_HASH)
        final=self.backing.stat()
        self.assertEqual((original.st_uid,original.st_gid,stat.S_IMODE(original.st_mode)),
                         (final.st_uid,final.st_gid,stat.S_IMODE(final.st_mode)))
        calls=self.log.read_text()
        self.assertIn('mount ',calls);self.assertIn('chcon ',calls);self.assertIn('umount ',calls)
        self.assert_clean_mount()

    def test_second_install_is_idempotent(self):
        self.assertEqual(self.run_policy().returncode,0)
        self.log.write_text('');before=self.backing.read_bytes()
        r=self.run_policy()
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(self.backing.read_bytes(),before)
        self.assertNotIn('chcon ',self.log.read_text());self.assert_clean_mount()

    def test_unrecognized_file_rejected_without_change(self):
        self.backing.write_bytes(self.backing.read_bytes()+b'unknown=1\n');before=self.backing.read_bytes()
        r=self.run_policy()
        self.assertNotEqual(r.returncode,0);self.assertIn('source hash',r.stderr)
        self.assertEqual(self.backing.read_bytes(),before);self.assert_clean_mount()

    def test_wrong_device_rejected_before_mount(self):
        r=self.run_policy(device='another-tablet')
        self.assertNotEqual(r.returncode,0);self.assertNotIn('mount ',self.log.read_text())
        self.assert_clean_mount()

    def test_wrong_partition_size_rejected(self):
        self.size.write_text('100\n');r=self.run_policy()
        self.assertNotEqual(r.returncode,0);self.assertIn('capacity',r.stderr);self.assert_clean_mount()

    def test_wrong_fstab_rejected(self):
        self.fstab.write_text('/dev/wrong /system ext4 ro wait\n');r=self.run_policy()
        self.assertNotEqual(r.returncode,0);self.assertIn('fstab',r.stderr);self.assert_clean_mount()

    def test_conflicting_fstab_row_rejected(self):
        with self.fstab.open('a') as f:f.write('/dev/wrong /system ext4 ro wait\n')
        r=self.run_policy()
        self.assertNotEqual(r.returncode,0);self.assertIn('conflicting',r.stderr)
        self.assertNotIn('mount ',self.log.read_text());self.assert_clean_mount()

    def test_existing_system_mount_rejected_untouched(self):
        entry=f'{self.block} /mnt/system ext4 rw 0 0\n';self.mounts.write_text(entry)
        r=self.run_policy()
        self.assertNotEqual(r.returncode,0);self.assertIn('already mounted',r.stderr)
        self.assertEqual(self.mounts.read_text(),entry);self.assertFalse(self.mountpoint.exists())

    def test_missing_hash_tool_rejected_before_mount(self):
        (self.bin/'sha256sum').unlink();r=self.run_policy()
        self.assertNotEqual(r.returncode,0);self.assertIn('sha256sum',r.stderr);self.assert_clean_mount()

    def test_mount_failure_cleans_private_directory(self):
        r=self.run_policy(mount_fails=True)
        self.assertNotEqual(r.returncode,0);self.assert_clean_mount()

    def test_mount_identity_and_readonly_fail_closed(self):
        for options in ({'mount_source':'/wrong'}, {'mount_options':'ro,relatime'}):
            with self.subTest(options=options):
                self.config.pop('mount_source',None);self.config.pop('mount_options',None)
                r=self.run_policy(**options)
                self.assertNotEqual(r.returncode,0)
                self.assertEqual(hashlib.sha256(self.backing.read_bytes()).hexdigest(),SOURCE_HASH)
                self.assert_clean_mount()

    def test_selinux_failure_preserves_original_and_unmounts(self):
        r=self.run_policy(label_fails=True)
        self.assertNotEqual(r.returncode,0)
        self.assertEqual(hashlib.sha256(self.backing.read_bytes()).hexdigest(),SOURCE_HASH)
        self.assert_clean_mount()

    def test_termination_preserves_original_and_unmounts(self):
        r=self.run_policy(signal_at_label=True)
        self.assertNotEqual(r.returncode,0)
        self.assertEqual(hashlib.sha256(self.backing.read_bytes()).hexdigest(),SOURCE_HASH)
        self.assert_clean_mount()

    def test_failed_unmount_is_failure_not_success(self):
        r=self.run_policy(unmount_fails=True)
        self.assertNotEqual(r.returncode,0);self.assertIn('do not reboot',r.stderr)
        self.assertTrue(self.mountpoint.exists())

    def test_builder_reproducible_and_executable(self):
        first=self.root/'first.zip';second=self.root/'second.zip'
        for output in (first,second):subprocess.run(['python3',str(BUILDER),str(output)],check=True)
        self.assertEqual(first.read_bytes(),second.read_bytes())
        with zipfile.ZipFile(first) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual((archive.getinfo('META-INF/com/google/android/update-binary').external_attr>>16)&0o777,0o755)
            self.assertNotIn(b'FORGEOS_TEST_ROOT',archive.read('META-INF/com/google/android/update-binary'))


if __name__=='__main__':
    unittest.main()
