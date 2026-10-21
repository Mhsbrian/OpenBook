#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Health gates must not turn a completed/crashed VM into a passing rehearsal."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

s = importlib.util.spec_from_file_location("rehearse", Path(__file__).with_name("update-rehearse.py"))
r = importlib.util.module_from_spec(s)
s.loader.exec_module(r)
c = r.load("capture", Path(__file__).with_name("rehearsal-capture.py"))


class Gates(unittest.TestCase):
    def setUp(self):
        self.text = (
            "[ 12.0][ T1] init: Verified that /data/misc has the encryption policy " + "a"*32 +
            " v2 modes 1/10 flags 0xa\nEnforcing\nOPENBOOK_RUBY_BOOT_COMPLETED=1\n"
            "/dev/block/dm-12 /data f2fs rw,seclabel,inlinecrypt,checkpoint_merge 0 0\n")
        self.keys = {str(n): "test-key-hash-"+str(n) for n in range(4)}
        self.profile = dict(qemu_sha256="known", data_policy_sha256=r.policy_identity(self.text))
        self.observation = dict(observation_window_elapsed=True, elapsed_s=760.7,
            qemu_sha256="known", qemu_exit=0, input_unchanged=True, source_tpm_unchanged=True,
            software_tpm_restored=True, decoy_unchanged=True, usb_capture_finished=True,
            logs_readback_exit=0, boot_completed_reported=True, kernel_panic=False, sigill=False,
            runtime_findings=dict(system_server_fatal_signals=[], zygote_exit_events=0,
                                  mmd_setup_abort_seen=False, camera_provider_abort_seen=False))

    def verdict(self, **kwargs):
        return r.verdict(kwargs.get('observation', self.observation), kwargs.get('text', self.text),
                         self.keys, kwargs.get('after', self.keys), self.profile)

    def test_healthy_observation_passes_only_bounded_vm_checks(self):
        result = self.verdict()
        self.assertTrue(result['passed'])
        for field in ('owner_credentials_tested','app_data_contents_verified','rollback_tested','physical_device_written'):
            self.assertIs(result[field], False)

    def test_late_crash_overrides_earlier_boot_completed(self):
        result = self.verdict(text=self.text + 'libc: Fatal signal 11 (SIGSEGV) in tid 99 (system_server)\n')
        self.assertTrue(result['checks']['boot_completed'])
        self.assertFalse(result['passed'])
        self.assertIn('no_fatal_exception', result['blockers'])

    def test_zygote_restart_is_not_hidden_by_boot_completion(self):
        self.observation['runtime_findings']['zygote_exit_events'] = 1
        self.assertIn('no_zygote_restart', self.verdict()['blockers'])

    def test_java_fatal_exception_rejects_observation(self):
        self.assertFalse(self.verdict(text=self.text+'AndroidRuntime: FATAL EXCEPTION: main\n')['passed'])

    def test_init_trigger_is_not_boot_completion(self):
        text=self.text.replace('OPENBOOK_RUBY_BOOT_COMPLETED=1','processing action (sys.boot_completed=1) from init.rc')
        self.assertIn('boot_completed', self.verdict(text=text)['blockers'])

    def test_missing_enforcing_or_plain_data_mount_is_rejected(self):
        for text in (self.text.replace('Enforcing','Permissive'), self.text.replace('inlinecrypt,',''),
                     self.text.replace('/dev/block/dm-12','/dev/block/sda9')):
            with self.subTest(text=text):
                self.assertFalse(self.verdict(text=text)['passed'])

    def test_changed_missing_or_ambiguous_policy_is_rejected(self):
        for text in (self.text.replace('a'*32,'b'*32), self.text.replace('Verified that','Will verify that'),
                     self.text+self.text.replace('a'*32,'b'*32)):
            with self.subTest(text=text):
                self.assertIn('encryption_policy_retained', self.verdict(text=text)['blockers'])

    def test_changed_or_missing_keys_are_rejected(self):
        changed=dict(self.keys);changed['0']='different'
        for keys in ({},dict(list(self.keys.items())[:3]),changed):
            self.assertIn('four_metadata_keys_retained',self.verdict(after=keys)['blockers'])

    def test_incomplete_early_or_short_observation_is_rejected(self):
        for field,value in (('observation_window_elapsed',False),('elapsed_s',759),('qemu_exit',1)):
            observation=copy.deepcopy(self.observation);observation[field]=value
            with self.subTest(field=field):
                self.assertFalse(self.verdict(observation=observation)['passed'])

    def test_unchanged_flags_and_current_capture_are_required(self):
        for field in ('input_unchanged','source_tpm_unchanged','software_tpm_restored',
                      'decoy_unchanged','usb_capture_finished'):
            observation=copy.deepcopy(self.observation);observation[field]=False
            with self.subTest(field=field):
                self.assertFalse(self.verdict(observation=observation)['passed'])

    def test_unknown_qemu_and_failed_log_readback_are_rejected(self):
        self.observation['qemu_sha256']='other'
        self.assertIn('qemu_identity',self.verdict()['blockers'])
        self.observation['logs_readback_exit']=1
        self.assertIn('fresh_capture_complete',self.verdict()['blockers'])

    def test_kernel_and_avb_errors_are_blockers(self):
        for message in ('Kernel panic - not syncing','signal 4 (SIGILL)',
                        'vbmeta size mismatch','Failed to verify vbmeta digest'):
            with self.subTest(message=message):
                self.assertFalse(self.verdict(text=self.text+message)['passed'])

    def test_missing_runtime_fields_are_not_a_clean_result(self):
        self.observation['runtime_findings']={}
        self.assertFalse(self.verdict()['passed'])

    def test_private_tpm_tree_refuses_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'state').write_text('fixture')
            before=r.tree_identity(root);(root/'state').write_text('changed')
            self.assertNotEqual(before,r.tree_identity(root))
            (root/'link').symlink_to(root/'state')
            with self.assertRaises(ValueError):r.tree_identity(root)

    def test_cleanup_preserves_evidence_inputs_and_unrelated_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'job';(out/'boot').mkdir(parents=True)
            for name in ('usb-test.img','internal-decoy.img','serial.log','result.json'):
                (out/'boot'/name).write_text('fixture')
            (root/'source.img').write_text('source')
            report=r.clean_scratch(out)
            self.assertTrue(report['complete'])
            self.assertFalse((out/'boot/usb-test.img').exists())
            self.assertTrue((out/'boot/serial.log').is_file())
            self.assertTrue((root/'source.img').is_file())

    def test_cleanup_refuses_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'job';(out/'boot').mkdir(parents=True)
            source=root/'source.img';source.write_text('source')
            (out/'boot/usb-test.img').symlink_to(source)
            with self.assertRaises(ValueError):r.clean_scratch(out)
            self.assertEqual(source.read_text(),'source')


class Captures(unittest.TestCase):
    """Read only current, inventoried capture files; serial alone is insufficient."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        (self.root/'serial.log').write_text('OPENBOOK_RUBY_BOOT_COMPLETED=1\n')
        (self.root/'prior-logs/old').mkdir(parents=True)
        (self.root/'saved-logs/old').mkdir(parents=True)
        (self.root/'saved-logs/old/android.txt').write_text('Fatal signal 11 from an old boot\n')
        (self.root/'saved-logs/current').mkdir(parents=True)
        (self.root/'saved-logs/current/complete.txt').write_text('complete\n')
        self.log=self.root/'saved-logs/current/android.txt';self.log.write_text('current clean log\n')
        self.observation=dict(prior_log_sessions_excluded=1,
            saved_log_files=['saved-logs/current/android.txt','saved-logs/current/complete.txt'])

    def test_saved_capture_fatal_is_seen_when_serial_is_clean(self):
        self.log.write_text('FATAL EXCEPTION: current app\n')
        text,inventory=c.current_capture(self.root,self.observation)
        self.assertIn('FATAL EXCEPTION:',text)
        self.assertEqual(len(inventory),3)

    def test_old_session_is_excluded(self):
        text,_=c.current_capture(self.root,self.observation)
        self.assertNotIn('old boot',text)
        self.observation['saved_log_files'].append('saved-logs/old/android.txt')
        with self.assertRaisesRegex(ValueError,'prior'):
            c.current_capture(self.root,self.observation)

    def test_missing_or_duplicate_inventory_is_refused(self):
        for files in (None,['saved-logs/current/android.txt']*2):
            self.observation['saved_log_files']=files
            with self.subTest(files=files),self.assertRaises(ValueError):
                c.current_capture(self.root,self.observation)

    def test_escape_and_symlink_are_refused(self):
        outside=self.root/'outside.txt';outside.write_text('not a capture')
        for name in ('../outside.txt',str(outside),'saved-logs/current/../../outside.txt'):
            self.observation['saved_log_files']=[name]
            with self.subTest(name=name),self.assertRaises(ValueError):
                c.current_capture(self.root,self.observation)
        self.log.unlink();self.log.symlink_to(outside)
        self.observation['saved_log_files']=['saved-logs/current/android.txt']
        with self.assertRaises(ValueError):c.current_capture(self.root,self.observation)

    def test_missing_file_or_changed_prior_inventory_is_refused(self):
        self.log.unlink()
        with self.assertRaises((ValueError,OSError)):c.current_capture(self.root,self.observation)
        self.log.write_text('restored')
        self.observation['prior_log_sessions_excluded']=0
        with self.assertRaises(ValueError):c.current_capture(self.root,self.observation)

    def test_capture_digest_changes_with_bytes(self):
        _,before=c.current_capture(self.root,self.observation)
        self.log.write_text('changed current log')
        _,after=c.current_capture(self.root,self.observation)
        self.assertNotEqual(before,after)


class Jobs(unittest.TestCase):
    """Synthetic lifecycle integration; never counted as real VM observations."""
    def setUp(self):
        Gates.setUp(self)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.a = SimpleNamespace(**{n:self.root/n for n in
            ('job','fixture','tpm','base_manifest','qemu','out')})
        self.a.job.mkdir()
        (self.a.job/'job.json').write_text('parent-assembly-record')
        self.a.fixture.write_text('unchanged synthetic fixture')
        profile_file=self.root/'profile.json';profile_file.write_text('fixed rehearsal profile')
        self.profile.update(candidate_sha256='candidate',fixture_sha256='fixture')
        self.calls=[]
        self.inject=None
        for item in (
            patch.object(r,'PROFILE',profile_file),
            patch.object(r,'validate',return_value=self.profile),
            patch.object(r,'load',return_value=SimpleNamespace(metadata_key_hashes=lambda *a:self.keys.copy())),
            patch.object(r.w,'run_command',side_effect=self.runner),
            patch.object(r.w.shutil,'disk_usage',return_value=SimpleNamespace(free=200*r.w.GIB)),
        ):
            item.start();self.addCleanup(item.stop)

    def runner(self, command, log, workspace, **kwargs):
        log.write_text('synthetic invocation fixture\n')
        if '--prepare-only' in command:
            self.calls.append('prepare')
            (self.a.out/'prepared').mkdir()
            (self.a.out/'prepared/manifest.json').write_text(json.dumps({'installable':False}))
            (self.a.out/'prepared/ruby-live.img').write_text('prepared')
        elif str(command[0]) == 'cp':
            self.calls.append('copy')
            shutil.copyfile(command[-2],command[-1])
        else:
            out=Path(command[command.index('--out')+1]);out.mkdir()
            self.calls.append(out.name)
            (out/'usb-test.img').write_text('post-boot synthetic state')
            (out/'serial.log').write_text(self.text)
            observation=copy.deepcopy(self.observation)
            (out/'saved-logs/current').mkdir(parents=True)
            (out/'saved-logs/current/complete.txt').write_text('complete\n')
            observation.update(prior_log_sessions_excluded=0,
                               saved_log_files=['saved-logs/current/complete.txt'])
            if self.inject:self.inject(out,observation)
            (out/'result.json').write_text(json.dumps(observation))

    def test_two_boots_link_parent_and_cleanup_after_collection(self):
        self.assertEqual(r.execute(self.a),0)
        job=r.w.read_json(self.a.out/'job.json')
        self.assertEqual(job['state'],'rehearsed_unqualified')
        self.assertEqual(self.calls,['prepare','boot','copy','restart'])
        self.assertEqual((self.a.job/'job.json').read_text(),'parent-assembly-record')
        self.assertEqual(self.a.fixture.read_text(),'unchanged synthetic fixture')
        self.assertTrue((self.a.out/'boot-verdict.json').exists())
        self.assertTrue((self.a.out/'restart-verdict.json').exists())
        self.assertFalse((self.a.out/'boot/usb-test.img').exists())
        self.assertFalse(job['release_approved'])

    def test_late_crash_keeps_evidence_and_finishes_held(self):
        def crash(out,observation):
            if out.name=='restart':
                (out/'serial.log').write_text(self.text+'libc: Fatal signal 11 (SIGSEGV)\n')
        self.inject=crash
        self.assertEqual(r.execute(self.a),2)
        job=r.w.read_json(self.a.out/'job.json')
        self.assertEqual(job['state'],'held')
        self.assertTrue(job['cases']['boot']['passed'])
        self.assertFalse(job['cases']['restart']['passed'])
        self.assertTrue(job['cleanup']['complete'])
        self.assertIn('Fatal signal',(self.a.out/'restart/serial.log').read_text())

    def test_saved_log_only_crash_holds_job(self):
        def crash(out,observation):
            path=out/'saved-logs/current/android.txt'
            path.write_text('AndroidRuntime: FATAL EXCEPTION: current app\n')
            observation['saved_log_files'].append('saved-logs/current/android.txt')
        self.inject=crash
        self.assertEqual(r.execute(self.a),2)
        job=r.w.read_json(self.a.out/'job.json')
        self.assertEqual(job['state'],'held')
        for phase in ('boot','restart'):
            self.assertIn('no_fatal_exception',job['cases'][phase]['blockers'])
            self.assertEqual(job['cases'][phase]['capture_file_count'],3)

    def test_incomplete_first_observation_does_not_restart(self):
        self.inject=lambda out,observation:observation.update(observation_window_elapsed=False)
        self.assertEqual(r.execute(self.a),2)
        self.assertEqual(self.calls,['prepare','boot'])
        self.assertEqual(r.w.read_json(self.a.out/'job.json')['state'],'held')

    def test_parent_record_change_prevents_success(self):
        def mutate(out,observation):
            (self.a.job/'job.json').write_text('changed parent')
        self.inject=mutate
        with self.assertRaisesRegex(ValueError,'Parent job/profile changed'):
            r.execute(self.a)
        self.assertEqual(r.w.read_json(self.a.out/'job.json')['state'],'failed')

    def test_low_space_prevents_native_work(self):
        r.w.shutil.disk_usage.return_value.free=103*r.w.GIB
        with self.assertRaisesRegex(ValueError,'40 GiB'):r.execute(self.a)
        self.assertEqual(self.calls,[])

    def test_existing_rehearsal_is_never_overwritten(self):
        self.a.out.mkdir();(self.a.out/'job.json').write_text('prior')
        with self.assertRaises(FileExistsError):r.execute(self.a)
        self.assertEqual((self.a.out/'job.json').read_text(),'prior')


if __name__ == '__main__':
    unittest.main()
