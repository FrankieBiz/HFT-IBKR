import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RunnerLockTests(unittest.TestCase):
    def test_direct_and_nested_runner_share_lock_until_children_exit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'scripts').mkdir()
            shutil.copyfile(ROOT/'scripts/runner_lock.py', root/'scripts/runner_lock.py')
            guard = '''if [[ ${HFT_RUNNER_LOCK_OWNER:-} != "$PPID" ]] || ! python3 scripts/runner_lock.py --verify-held; then
 exec python3 scripts/runner_lock.py NAME "$@"
fi
'''
            (root/'scripts/run_daily.sh').write_text(guard.replace('NAME', 'run_daily.sh')+'bash scripts/daily_shadow.sh\n')
            (root/'scripts/daily_shadow.sh').write_text(guard.replace('NAME','daily_shadow.sh')+'touch entered\nsleep 60\n')
            env = dict(os.environ)
            env.pop('HFT_RUNNER_LOCK_OWNER', None)
            env.pop('HFT_RUNNER_LOCK_FD', None)
            first = subprocess.Popen([sys.executable,'scripts/runner_lock.py','run_daily.sh'], cwd=root,
                                     env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            try:
                deadline=time.monotonic()+5
                while not (root/'entered').exists() and time.monotonic()<deadline:
                    time.sleep(.02)
                self.assertTrue((root/'entered').exists())
                blocked = subprocess.run([sys.executable,'scripts/runner_lock.py','daily_shadow.sh'], cwd=root,
                                         env=env,capture_output=True,text=True,timeout=5)
                self.assertEqual(blocked.returncode,2)
                self.assertIn('already active',blocked.stderr)
            finally:
                os.killpg(first.pid,15)
                first.communicate(timeout=7)
            # Acquire after shutdown; an inherited guardian cannot leak ownership.
            import fcntl
            with (root/'.research-output/shadow/runner.lock').open('a+b') as handle:
                fcntl.flock(handle,fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_unknown_script_rejected(self):
        result=subprocess.run([sys.executable,str(ROOT/'scripts/runner_lock.py'),'anything'],capture_output=True,text=True)
        self.assertEqual(result.returncode,2)


class TerminalJournalTests(unittest.TestCase):
    def test_both_entrypoints_block_corrupt_accounting_before_script_work(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'scripts').mkdir()
            shutil.copyfile(ROOT/'scripts/runner_lock.py',root/'scripts/runner_lock.py')
            shadow=root/'.research-output/shadow'
            shadow.mkdir(parents=True)
            (shadow/'fills.sqlite').write_bytes(b'invented corrupt journal')
            for name in ('run_daily.sh','daily_shadow.sh'):
                (root/'scripts'/name).write_text('touch credential-read\n')
                result=subprocess.run([sys.executable,'scripts/runner_lock.py',name],cwd=root,
                            env=dict(os.environ,PYTHONPATH=str(ROOT)),capture_output=True,text=True,timeout=5)
                self.assertEqual(result.returncode,2,result.stdout+result.stderr)
                self.assertIn('accounting check failed',result.stderr)
                self.assertFalse((root/'credential-read').exists())


class LinuxGroupTests(unittest.TestCase):
    def test_zombie_only_group_does_not_hold_lock_but_live_or_unknown_does(self):
        import importlib.util
        from unittest.mock import patch
        spec=importlib.util.spec_from_file_location('runner_guard_fixture',ROOT/'scripts/runner_lock.py')
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder:
            proc=Path(folder)
            entry=proc/'123'
            entry.mkdir()
            stat=entry/'stat'
            with patch.object(module,'Path',return_value=proc),patch.object(module.os,'killpg',return_value=None):
                stat.write_text('123 (fixture ) name) Z 1 456 456 0')
                self.assertFalse(module.group_alive(456))
                stat.write_text('123 (fixture) S 1 456 456 0')
                self.assertTrue(module.group_alive(456))
                stat.write_text('unparseable fixture')
                self.assertTrue(module.group_alive(456))
