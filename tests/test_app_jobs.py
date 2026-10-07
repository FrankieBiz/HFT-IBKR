"""Offline process ownership, bounded output and fixed command contracts."""
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest

from quant_app.jobs import JobManager
from quant_app.locking import operator_lock, runner_busy
from quant_research.serde import InputError


class JobTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root/'scripts').mkdir()
        self.home = self.root/'config'
        (self.home/'alpaca').mkdir(parents=True)
        (self.home/'alpaca/paper.env').write_text('APCA_API_KEY_ID=FAKESECRET123\nAPCA_API_SECRET_KEY=FAKESECRET456\n')
        self.jobs = JobManager(self.root, self.home)
        self.addCleanup(self.jobs.close)

    def script(self, name, content):
        (self.root/'scripts'/name).write_text('#!/usr/bin/env bash\n'+content)

    def finish(self):
        end = time.monotonic()+5
        while self.jobs.snapshot()['running'] and time.monotonic()<end:
            time.sleep(.02)
        self.assertFalse(self.jobs.snapshot()['running'])

    def test_allowlist_no_shell_or_path_override(self):
        for action in ('echo bad', '../run_daily.sh', '', 'live', 'stop'):
            with self.assertRaises(InputError):
                self.jobs.start(action)
        self.assertFalse(self.jobs.snapshot()['running'])

    def test_offline_checks_ignore_malformed_provider_credentials(self):
        (self.home/'alpaca/paper.env').write_text('malformed saved keys\n')
        self.jobs.start('checks')
        self.finish()
        self.assertEqual(self.jobs.snapshot()['exit_code'], 0)
        self.assertEqual(self.jobs.secrets, ())

    def test_failure_and_secrets_are_redacted_and_logs_bounded(self):
        self.script('run_daily.sh', 'echo FAKESECRET123 FAKESECRET456\nprintf "%09000d\\n" 1\nexit 7\n')
        self.jobs.start('setup_check')
        self.finish()
        status = self.jobs.snapshot()
        self.assertEqual(status['exit_code'], 7)
        rendered = str(status)
        self.assertNotIn('FAKESECRET123', rendered)
        self.assertNotIn('FAKESECRET456', rendered)
        self.assertLess(len(rendered), 60000)
        self.assertIn('[redacted]', rendered)

    def test_duplicate_start_and_only_owned_group_stop(self):
        self.script('run_daily.sh', 'sleep 60 &\nwait\n')
        other = subprocess.Popen(['sleep', '60'], start_new_session=True)
        self.addCleanup(other.wait)
        self.addCleanup(lambda: other.poll() is None and other.kill())
        self.jobs.start('runner')
        with self.assertRaises(InputError):
            self.jobs.start('runner')
        self.jobs.stop()
        self.finish()
        self.assertIsNone(other.poll())

    def test_common_lock_blocks_new_jobs_and_mutations(self):
        self.script('run_daily.sh', 'exit 0\n')
        with operator_lock(self.root):
            self.assertTrue(runner_busy(self.root))
            with self.assertRaises(InputError):
                self.jobs.start('runner')
            with self.assertRaises(InputError):
                with operator_lock(self.root):
                    pass
        self.assertFalse(runner_busy(self.root))

    def test_env_overrides_are_scrubbed(self):
        self.script('run_daily.sh', 'echo "${CONFIG-unset}|${NTFY_TOPIC-unset}|$ALPACA_ENV|${HFT_RUNNER_LOCK_OWNER-unset}"\n')
        from unittest.mock import patch
        with patch.dict(os.environ, CONFIG='/evil', NTFY_TOPIC='evil', HFT_RUNNER_LOCK_OWNER='evil'):
            self.jobs.start('setup_check')
        self.finish()
        output='\n'.join(self.jobs.snapshot()['logs'])
        self.assertIn('unset|unset|'+str((self.home/'alpaca/paper.env').resolve())+'|unset', output)

    def test_shutdown_stops_owned_process(self):
        self.script('run_daily.sh', 'sleep 60\n')
        self.jobs.start('runner')
        self.jobs.close()
        self.assertFalse(self.jobs.snapshot()['running'])


class GuardianShutdownTests(unittest.TestCase):
    def test_stop_and_close_remove_owned_uncooperative_descendants(self):
        import shutil
        import sys
        from unittest.mock import patch
        source=Path(__file__).resolve().parents[1]
        for closing,action in ((False,'runner'),(True,'runner'),(False,'study'),(True,'study')):
            with self.subTest(closing=closing,action=action), tempfile.TemporaryDirectory() as folder:
                root=Path(folder)
                (root/'scripts').mkdir()
                shutil.copyfile(source/'scripts/runner_lock.py',root/'scripts/runner_lock.py')
                child=root/'uncooperative.py'
                child.write_text('import os,signal,time,pathlib\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\npathlib.Path("child.pid").write_text(str(os.getpid()))\ntime.sleep(60)\n')
                # Root runner nests daily; both keep descendants in one owned group.
                guard='if [[ ${HFT_RUNNER_LOCK_OWNER:-} != "$PPID" ]] || ! "$PYTHON" scripts/runner_lock.py --verify-held; then\n exec "$PYTHON" scripts/runner_lock.py NAME "$@"\nfi\n'
                (root/'scripts/run_daily.sh').write_text(guard.replace('NAME','run_daily.sh')+'trap "exit 143" TERM\nbash scripts/daily_shadow.sh &\nwait\n')
                (root/'scripts/daily_shadow.sh').write_text(guard.replace('NAME','daily_shadow.sh')+'trap "exit 143" TERM\n"$PYTHON" uncooperative.py &\nwait\n')
                (root/'scripts/run_study.sh').write_text('trap "exit 143" TERM\n"$PYTHON" uncooperative.py &\nwait\n')
                jobs=JobManager(root,root/'config')
                pid=None
                try:
                    jobs.start(action)
                    deadline=time.monotonic()+5
                    while not (root/'child.pid').exists() and time.monotonic()<deadline:
                        time.sleep(.02)
                    self.assertTrue((root/'child.pid').exists())
                    pid=int((root/'child.pid').read_text())
                    jobs.close() if closing else jobs.stop()
                    self.assertFalse(jobs.snapshot()['running'])
                    self.assertFalse(runner_busy(root))
                    try:
                        os.kill(pid,0)
                    except ProcessLookupError:
                        pass
                    else:
                        # Linux init may retain a zombie, but no owned work survives.
                        self.assertEqual(Path(f'/proc/{pid}/stat').read_text().rpartition(') ')[2].split()[0],'Z')
                finally:
                    if pid is not None:
                        try:os.kill(pid,signal.SIGKILL)
                        except ProcessLookupError:pass
                    jobs.close()
