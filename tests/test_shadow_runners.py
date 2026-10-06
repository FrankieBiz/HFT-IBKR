from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


class RunnerGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        shutil.copytree(ROOT/'scripts', self.root/'scripts')
        self.env_file = self.root/'credentials.env'
        self.marker = self.root/'credential-read'
        self.env_file.write_text('touch "' + str(self.marker) + '"\n')
        self.calls = self.root/'calls'
        self.python = self.root/'python'
        self.python.write_text('''#!/usr/bin/env python3
import pathlib, sys
pathlib.Path(__file__).with_name('calls').open('a').write(' '.join(sys.argv[1:])+'\\n')
if sys.argv[1:3] == ['-m', 'quant_session.readiness']:
    print('readiness error: missing historical evidence', file=sys.stderr)
    sys.exit(2)
if sys.argv[1:2] == ['-'] and sys.argv[-1:] == ['registry-preflight']:
    sys.exit(0)
if sys.argv[1:2] == ['-c']:
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    d = datetime.now(ZoneInfo('America/New_York')).date()
    print(d, d-timedelta(days=1))
else:
    sys.exit(2)
''')
        self.python.chmod(0o755)
        self.env = dict(os.environ, PYTHON=str(self.python), ALPACA_ENV=str(self.env_file),
                        NOTIFY_ENV=str(self.env_file))

    def run_script(self, name, *args):
        return subprocess.run(['bash', str(self.root/'scripts'/name), *args], cwd=self.root,
                              env=self.env, text=True, capture_output=True, timeout=10)

    def test_run_daily_and_check_gate_before_credentials_calendar_or_study(self):
        for args in (('--check',), ('--once',)):
            with self.subTest(args=args):
                self.calls.unlink(missing_ok=True)
                result = self.run_script('run_daily.sh', *args)
                self.assertEqual(result.returncode, 2, result.stdout+result.stderr)
                self.assertFalse(self.marker.exists(), 'readiness must precede credential reads')
                calls = self.calls.read_text()
                self.assertIn('quant_session.readiness', calls)
                self.assertNotIn('market-clock', calls)
                self.assertNotIn('quant_data', calls)
                self.assertNotIn('run_study', calls)

    def test_cached_plan_and_custom_config_cannot_bypass_gate(self):
        today = datetime.now(ZoneInfo('America/New_York')).date().isoformat()
        day = self.root/'.research-output/shadow'/today
        day.mkdir(parents=True)
        (day/'plan.json').write_text(json.dumps({'execution_session': today, 'status': 'TRUSTED_CACHE',
             'signal': 'CASH', 'signal_session': '2026-10-05', 'quote_scope': 'synthetic', 'proposal': None, 'blockers': []}))
        for config in ('', '/custom-config.json'):
            with self.subTest(config=config):
                self.env['CONFIG'] = config
                result = self.run_script('daily_shadow.sh')
                self.assertEqual(result.returncode, 2, result.stdout+result.stderr)
                self.assertNotIn('TRUSTED_CACHE', result.stdout)
                self.assertFalse(self.marker.exists())
                self.assertIn('quant_session.readiness', self.calls.read_text())

    def test_study_uses_existing_shared_registry_without_overwriting_v1(self):
        legacy = self.root/'.research-output/spy-daily-v1'
        legacy.mkdir(parents=True)
        (legacy/'holdout.json').write_text('{}')
        result = self.run_script('run_study.sh')
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.marker.exists(), 'missing shared registry must fail before external setup')
        self.assertIn('legacy study artifacts', result.stderr.lower())

    def test_fresh_study_initializes_shared_registry_offline_before_setup(self):
        result = self.run_script('run_study.sh')
        self.assertEqual(result.returncode, 2)
        self.assertTrue(self.calls.exists(), 'fresh study needs offline registry initialization')
        calls = self.calls.read_text()
        self.assertIn('registry-preflight', calls)
        self.assertIn('quant_data fetch-alpaca', calls)

    def test_daily_cache_must_match_verified_ledger_before_presentation(self):
        import sys
        from quant_session.ledger import DecisionLedger
        from quant_session.planner import decision_digest
        from test_shadow_session import fixtures, decide
        from test_shadow_readiness import evidence
        for package in ('quant_research', 'quant_session', 'quant_data'):
            shutil.copytree(ROOT/package, self.root/package)
        study = self.root/'.research-output/spy-trend-v2'
        study.mkdir(parents=True)
        dataset, paths = evidence(study, real_bundle=True)
        shared = self.root/'.research-output/spy-daily-v1'
        shared.mkdir()
        shutil.move(paths['registry.sqlite'], shared/'experiments.sqlite')
        self.env.update(PYTHON=sys.executable, STUDY_DIR=str(study), NTFY_TOPIC='')
        today = datetime.now(ZoneInfo('America/New_York')).date().isoformat()
        day = self.root/'.research-output/shadow'/today
        day.mkdir(parents=True)
        shutil.copyfile(study/'spy.qdata', day/'spy.qdata')
        report = decide(*fixtures())
        report['execution_session'] = today
        report['decision_id'] = decision_digest(report)
        from quant_research.__main__ import source_identity
        from quant_research.serde import canonical_json
        import hashlib
        config = json.loads(paths['config.json'].read_text())
        config['lookback'] = 2
        (day/'config.json').write_text(canonical_json(config))
        report['source_hashes']['config'] = hashlib.sha256((day/'config.json').read_bytes()).hexdigest()
        for package in ('quant_session', 'quant_research', 'quant_data'):
            report['source_hashes'][package+'_source'] = source_identity(package=package)['source_sha256']
        report['decision_id'] = decision_digest(report)
        content = DecisionLedger(day.parent/'ledger.sqlite').record(report, 'fixture')
        (day/'plan.json').write_bytes(content)
        result = self.run_script('daily_shadow.sh')
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertIn('Already recorded', result.stdout)
        self.assertFalse(self.marker.exists())
        import copy
        original = copy.deepcopy(report)
        ledger_path = day.parent/'ledger.sqlite'
        for hash_key in ('config', 'quant_session_source', 'quant_research_source', 'quant_data_source'):
            changed = copy.deepcopy(original)
            changed['source_hashes'][hash_key] = '0'*64
            changed['decision_id'] = decision_digest(changed)
            ledger_path.unlink()
            altered = DecisionLedger(ledger_path).record(changed, 'fixture')
            (day/'plan.json').write_bytes(altered)
            result = self.run_script('daily_shadow.sh')
            with self.subTest(hash_key=hash_key):
                self.assertEqual(result.returncode, 2, result.stdout+result.stderr)
                self.assertNotIn('Already recorded', result.stdout)
                self.assertIn('config/source identity mismatch', result.stderr)
        ledger_path.unlink()
        content = DecisionLedger(ledger_path).record(original, 'fixture')
        (day/'plan.json').write_bytes(content)
        alternate = dict(config, target_fraction='0.1')
        (day/'config.json').write_text(canonical_json(alternate))
        result = self.run_script('daily_shadow.sh')
        self.assertEqual(result.returncode, 2, result.stdout+result.stderr)
        self.assertNotIn('Already recorded', result.stdout)
        (day/'config.json').write_text(canonical_json(config))
        report['status'] = 'UNVERIFIED'
        from quant_research.serde import canonical_json
        (day/'plan.json').write_text(canonical_json(report))
        result = self.run_script('daily_shadow.sh')
        self.assertEqual(result.returncode, 2, result.stdout+result.stderr)
        self.assertNotIn('UNVERIFIED', result.stdout)
        self.assertIn('differs from verified ledger', result.stderr)
        self.assertFalse(self.marker.exists())

    def test_daily_preserves_sip_study_feed_and_blocks_mismatched_cache(self):
        import sys
        from quant_data.bundle import prepare_bundle
        from test_shadow_readiness import evidence
        for package in ('quant_research', 'quant_session', 'quant_data'):
            shutil.copytree(ROOT/package, self.root/package)
        study = self.root/'.research-output/spy-trend-v2'
        study.mkdir(parents=True)
        _, paths = evidence(study, real_bundle=True, feed='sip')
        shared = self.root/'.research-output/spy-daily-v1'
        shared.mkdir()
        registry = shared/'experiments.sqlite'
        shutil.move(paths['registry.sqlite'], registry)
        before = registry.read_bytes()
        self.python.write_text('''#!/usr/bin/env python3
import os, pathlib, sys
if sys.argv[1:4] == ['-m', 'quant_data', 'fetch-alpaca']:
    pathlib.Path(__file__).with_name('calls').write_text(' '.join(sys.argv[1:]))
    sys.exit(2)  # stop before any credentials/transport/network are used by Python
os.execv(REAL_PYTHON, [REAL_PYTHON, *sys.argv[1:]])
'''.replace('REAL_PYTHON', repr(sys.executable)))
        self.env.update(STUDY_DIR=str(study), NTFY_TOPIC='')
        today = datetime.now(ZoneInfo('America/New_York')).date().isoformat()
        root = self.root/'.research-output/shadow'
        root.mkdir()
        shutil.copyfile(ROOT/'examples/shadow/portfolio.template.json', root/'portfolio.json')
        result = self.run_script('daily_shadow.sh')
        self.assertEqual(result.returncode, 2, result.stdout+result.stderr)
        self.assertIn('--feed sip', self.calls.read_text())
        self.assertTrue(self.marker.exists())
        self.marker.unlink()
        self.calls.unlink()

        day = root/today
        for name in ('prices.csv', 'distributions.csv', 'calendar.csv', 'metadata.json'):
            shutil.copyfile(study/name, day/name)
        metadata = json.loads((day/'metadata.json').read_text())
        metadata['sources']['prices']['reference'] = metadata['sources']['prices']['reference'].replace('feed=sip', 'feed=iex')
        (day/'metadata.json').write_text(json.dumps(metadata))
        prepare_bundle(day/'prices.csv', day/'distributions.csv', day/'calendar.csv',
                       day/'metadata.json', day/'spy.qdata')
        for cached_plan in (False, True):
            if cached_plan:
                (day/'plan.json').write_text('{}')
            result = self.run_script('daily_shadow.sh')
            with self.subTest(cached_plan=cached_plan):
                self.assertEqual(result.returncode, 2, result.stdout+result.stderr)
                self.assertIn('feed mismatch', result.stderr)
                self.assertFalse(self.marker.exists(), 'mismatch must fail before credentials')
                self.assertFalse(self.calls.exists(), 'mismatch must fail before intake')
                self.assertNotIn('Already recorded', result.stdout)
        self.assertEqual(registry.read_bytes(), before)

    def test_legacy_holdout_without_session_claims_stops_before_credentials(self):
        import sqlite3
        import sys
        from contextlib import closing
        shutil.copytree(ROOT/'quant_research', self.root/'quant_research')
        shared = self.root/'.research-output/spy-daily-v1'
        shared.mkdir(parents=True)
        with closing(sqlite3.connect(shared/'experiments.sqlite')) as db, db:
            db.execute('CREATE TABLE events(run_id TEXT,kind TEXT,status TEXT)')
            db.execute("INSERT INTO events VALUES('legacy','holdout','reserved')")
        self.env['PYTHON'] = sys.executable
        result = self.run_script('run_study.sh')
        self.assertEqual(result.returncode, 2, result.stdout+result.stderr)
        self.assertIn('reviewed migration required', result.stderr)
        self.assertFalse(self.marker.exists())


    def test_missing_registry_alongside_current_v2_evidence_blocks_audit_reset(self):
        for name in ('selection.json', 'validation.json', 'holdout.json'):
            study = self.root/'.research-output/spy-trend-v2'
            study.mkdir(parents=True, exist_ok=True)
            path = study/name
            path.write_text('{}')
            result = self.run_script('run_study.sh')
            with self.subTest(name=name):
                self.assertEqual(result.returncode, 2)
                self.assertFalse(self.marker.exists(), 'existing v2 evidence must block before credentials')
                self.assertFalse((self.root/'.research-output/spy-daily-v1/experiments.sqlite').exists())
            path.unlink()

    def fake_operational_runner(self, state):
        self.python.write_text('''#!/usr/bin/env python3
import pathlib, sys
root = pathlib.Path(__file__).parent
with (root/'calls').open('a') as out:
    out.write(' '.join(sys.argv[1:])+'\\n')
if sys.argv[1:3] in (['-m', 'quant_session.readiness'], ['-m', 'quant_session.health']):
    sys.exit(0)
if sys.argv[1:3] == ['-m', 'quant_session']:
    counter = root/'clock-count'
    n = int(counter.read_text()) if counter.exists() else 0
    counter.write_text(str(n+1))
    if n: sys.exit(2)
    print(''' + repr(state + ' 0 30') + ''')
    sys.exit(0)
if sys.argv[1] == '-':
    sys.argv = sys.argv[1:]
    exec(compile(sys.stdin.read(), '<runner fixture>', 'exec'))
''')
        bindir = self.root/'bin'
        bindir.mkdir()
        sleeper = bindir/'sleep'
        sleeper.write_text('''#!/usr/bin/env python3
import pathlib, sys
with pathlib.Path(__file__).parent.parent.joinpath('calls').open('a') as out:
    out.write('sleep '+' '.join(sys.argv[1:])+'\\n')
sys.exit(2)
''')
        sleeper.chmod(0o755)
        self.env.update(PATH=str(bindir)+os.pathsep+self.env['PATH'], NTFY_TOPIC='')

    def test_final_calendar_reread_failure_is_failed_before_bounded_wait(self):
        self.fake_operational_runner('closed')
        result = self.run_script('run_daily.sh')
        self.assertEqual(result.returncode, 2)
        calls = self.calls.read_text().splitlines()
        sleep_index = next(i for i, call in enumerate(calls) if call.startswith('sleep '))
        self.assertIn('--status failed', calls[sleep_index-1])
        self.assertIn('Calendar reread FAILED', result.stdout)
        self.assertEqual(calls[sleep_index], 'sleep 30')

    def test_after_session_expected_deadline_is_due_immediately(self):
        from datetime import timezone
        self.fake_operational_runner('after')
        started = datetime.now(timezone.utc)
        result = self.run_script('run_daily.sh', '--once')
        self.assertEqual(result.returncode, 0, result.stderr)
        expectation = next(call for call in self.calls.read_text().splitlines() if '--expected-deadline' in call)
        deadline = datetime.fromisoformat(expectation.split('--expected-deadline ')[1])
        self.assertLessEqual((deadline-started).total_seconds(), 10)
