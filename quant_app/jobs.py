"""Allowlisted operator jobs: owned process groups, bounded redacted local logs."""
from collections import deque
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading

from quant_research.serde import InputError
from .locking import operator_lock, runner_busy

COMMANDS = {
    'checks': ('-m', 'compileall', '-q', 'quant_app', 'quant_session', 'quant_data', 'quant_research'),
    'study': (sys.executable, 'scripts/runner_lock.py', 'run_study.sh'),
    'setup_check': ('bash', 'scripts/run_daily.sh', '--check'),
    'runner': ('bash', 'scripts/run_daily.sh'),
}
SCRUB = {'CONFIG', 'PORTFOLIO', 'STUDY_OUTPUT', 'STUDY_DIR', 'STUDY_REGISTRY', 'PYTHON',
         'ALPACA_ENV', 'NOTIFY_ENV', 'NTFY_TOPIC', 'NTFY_SERVER', 'APCA_API_KEY_ID',
         'APCA_API_SECRET_KEY', 'ALPACA_DATA_FEED', 'HFT_RUNNER_LOCK_OWNER', 'HFT_RUNNER_LOCK_FD',
         'BASH_ENV', 'ENV', 'SHELLOPTS', 'PYTHONPATH', 'PYTHONHOME', 'PYTHONSTARTUP'}
TOKEN = re.compile(r'^(?:export\s+)?(?:APCA_API_KEY_ID|APCA_API_SECRET_KEY)\s*=\s*[\'\"]?([A-Za-z0-9_-]{1,256})[\'\"]?\s*$')


class JobManager:
    def __init__(self, root, config_home=None):
        self.root = Path(root).resolve()
        self.config_home = Path(config_home or Path.home()/'.config').resolve()
        self.lock = threading.RLock()
        self.process = None
        self.reader = None
        self.action = None
        self.exit_code = None
        self.logs = deque(maxlen=150)
        self.recent = deque(maxlen=12)
        self.secrets = ()
        self.stop_requested = False
        self.closed = False
        self.lease = None

    def _log(self, line):
        for secret in self.secrets:
            line = line.replace(secret, '[redacted]')
        # Defense for unknown tokens included in provider/tool diagnostic output.
        line = re.sub(r'(?i)((?:secret|token|api[_ -]?key)(?:[_ -]?(?:id|key))?\s*[=:]\s*)\S+',
                      r'\1[redacted]', line)
        self.logs.append(line[:2048])

    def _read(self, process):
        try:
            while True:
                raw = process.stdout.readline(4097)
                if not raw:
                    break
                if len(raw) > 4096 or not raw.endswith(b'\n') and len(raw) == 4097:
                    # Never show partial tokens from oversized lines or chunk boundaries.
                    while raw and not raw.endswith(b'\n'):
                        raw = process.stdout.readline(4097)
                    line = '[oversized output line omitted]'
                else:
                    line = raw.decode('utf-8', errors='replace').rstrip('\r\n')
                with self.lock:
                    self._log(line)
            code = process.wait()
            with self.lock:
                self.exit_code = code
                if self.recent:
                    self.recent[-1]['exit_code'] = code
                self._log(f'Job finished with exit code {code}.')
        finally:
            process.stdout.close()
            with self.lock:
                if self.lease is not None:
                    self.lease.__exit__(None, None, None)
                    self.lease = None

    def _environment(self):
        env = {key: value for key, value in os.environ.items() if key not in SCRUB}
        env.update(PYTHON=sys.executable, ALPACA_ENV=str(self.config_home/'alpaca/paper.env'),
                   NOTIFY_ENV=str(self.config_home/'hft-ibkr/notify.env'), PYTHONUNBUFFERED='1')
        return env

    def start(self, action):
        if action not in COMMANDS:
            raise InputError('Unknown job action.')
        with self.lock:
            if self.closed:
                raise InputError('App is shutting down.')
            if self.process is not None and self.process.poll() is None:
                raise InputError('A job is already running. Stop or wait for it first.')
            if self.reader is not None:
                # Reader cannot acquire this mutex while joining; finished reader will
                # be joined outside it by stop/close. Retain outputs across job starts.
                if self.reader.is_alive():
                    raise InputError('Previous job is finishing. Try again shortly.')
            lease = operator_lock(self.root)
            handle = lease.__enter__()
            try:
                secrets = []
                keyfile = self.config_home/'alpaca/paper.env'
                if keyfile.exists():
                    if keyfile.stat().st_size > 8192:
                        raise InputError('Credential file is too large; review it locally.')
                    for line in keyfile.read_text().splitlines():
                        match = TOKEN.fullmatch(line.strip())
                        if match:
                            secrets.append(match[1])
                        elif line.strip() and not line.lstrip().startswith('#'):
                            raise InputError('Credential file must contain only the two simple API-key assignments. Save keys in Setup to replace it explicitly.')
                self.secrets = tuple(secrets)
                command = COMMANDS[action]
                args = [sys.executable, *command] if action == 'checks' else list(command)
                try:
                    env = self._environment()
                    env["HFT_RUNNER_LOCK_FD"] = str(handle.fileno())
                    process = subprocess.Popen(args, cwd=self.root, env=env, pass_fds=(handle.fileno(),),
                                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                               start_new_session=True)
                except OSError:
                    raise InputError('Could not start the job; check Python/Bash installation.') from None
            except BaseException:
                lease.__exit__(None, None, None)
                raise
            self.lease = lease
            self.process = process
            self.action = action
            self.exit_code = None
            self.stop_requested = False
            self.recent.append({'action': action, 'started_at': datetime.now(timezone.utc).isoformat(), 'exit_code': None})
            self._log(f'Started {action}.')
            self.reader = threading.Thread(target=self._read, args=(process,), daemon=True)
            self.reader.start()
        return self.snapshot()

    def stop(self):
        with self.lock:
            process = self.process
            reader = self.reader
            if process is not None and process.poll() is None:
                self.stop_requested = True
                if self.recent:self.recent[-1]['stopped'] = True
                # The handle and new session belong to this backend, never a PID file.
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        if process is not None:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)
        if reader is not None:
            reader.join(timeout=6)
        return self.snapshot()

    def snapshot(self):
        with self.lock:
            running = self.process is not None and (self.process.poll() is None or self.lease is not None)
            return {'action': self.action, 'running': running, 'exit_code': self.exit_code,
                    'logs': list(self.logs), 'recent': list(self.recent), 'stopped': self.stop_requested,
                    'external_runner': runner_busy(self.root) and not running}

    def close(self):
        with self.lock:
            self.closed = True
        self.stop()
