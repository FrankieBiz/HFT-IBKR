"""Invented offline fixtures for committed decision publication recovery."""
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from quant_research.__main__ import source_identity
from quant_research.serde import InputError, canonical_json
from quant_session.inputs import parse_schedule, parse_snapshot
from quant_session.ledger import DecisionLedger
from quant_session.planner import decision_digest
from test_shadow_readiness import evidence
from test_shadow_session import fixtures


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('quant_session.recovery'), 'committed recovery helper missing')
        from quant_session.recovery import recover_decision
        self.recover = recover_decision
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        study = self.root/'study'
        study.mkdir()
        dataset, paths = evidence(study, real_bundle=True)
        _, config, schedule, snapshot = fixtures()
        self.kw = dict(ledger=self.root/'ledger.sqlite', session=snapshot['execution_session'],
                       bundle=study/'spy.qdata', output=self.root/'plan.json')
        for name, raw in (('config', asdict(config)), ('schedule', schedule), ('snapshot', snapshot)):
            path = self.root/(name+'.json')
            path.write_text(canonical_json(raw))
            self.kw[name] = path
        self.kw['readiness_inputs'] = dict(bundle=study/'spy.qdata', config=paths['config.json'],
            protocol=paths['protocol.json'], selection=paths['selection.json'],
            holdout=paths['holdout.json'], registry=paths['registry.sqlite'])
        hashes = {name: hashlib.sha256(self.kw[name].read_bytes()).hexdigest()
                  for name in ('config', 'schedule', 'snapshot')}
        for package in ('quant_session', 'quant_research', 'quant_data'):
            hashes[package+'_source'] = source_identity(package=package)['source_sha256']
        self.content = DecisionLedger(self.kw['ledger']).plan(dataset, config,
            parse_schedule(schedule), parse_snapshot(snapshot), hashes)

    def test_exact_committed_bytes_exported_offline_without_planning_or_mutation(self):
        before = {name: self.kw[name].read_bytes() for name in ('config', 'schedule', 'snapshot', 'bundle', 'ledger')}
        with patch('socket.socket', side_effect=AssertionError('offline recovery')), \
                patch('quant_session.ledger.plan_session', side_effect=AssertionError('never replan')):
            self.assertTrue(self.recover(**self.kw))
        self.assertEqual(self.kw['output'].read_bytes(), self.content)
        for name, content in before.items():
            self.assertEqual(self.kw[name].read_bytes(), content)

    def test_missing_originals_require_review_without_publication(self):
        for name in ('config', 'schedule', 'snapshot', 'bundle'):
            original = self.kw[name].read_bytes()
            self.kw[name].unlink()
            with self.subTest(name=name), self.assertRaises(InputError):
                self.recover(**self.kw)
            self.assertFalse(self.kw['output'].exists())
            self.kw[name].write_bytes(original)

    def test_changed_original_inputs_and_package_identity_fail_closed(self):
        for name in ('config', 'schedule', 'snapshot'):
            original = self.kw[name].read_bytes()
            self.kw[name].write_bytes(original+b'\n')
            with self.subTest(name=name), self.assertRaisesRegex(InputError, 'identity mismatch'):
                self.recover(**self.kw)
            self.assertFalse(self.kw['output'].exists())
            self.kw[name].write_bytes(original)
        for key in ('data', 'manifest', 'quant_session_source', 'quant_research_source', 'quant_data_source'):
            report = json.loads(self.content)
            report['source_hashes'][key] = '0'*64
            report['decision_id'] = decision_digest(report)
            self.kw['ledger'].unlink()
            DecisionLedger(self.kw['ledger']).record(report, 'invented')
            before = self.kw['ledger'].read_bytes()
            with self.subTest(key=key), self.assertRaisesRegex(InputError, 'identity mismatch'):
                self.recover(**self.kw)
            self.assertEqual(self.kw['ledger'].read_bytes(), before)
            self.assertFalse(self.kw['output'].exists())

    def test_daily_readiness_failure_and_corrupt_ledger_preserve_files(self):
        path = self.kw['readiness_inputs']['holdout']
        path.write_text('{}')
        with self.assertRaises(InputError):
            self.recover(**self.kw)
        self.assertFalse(self.kw['output'].exists())
        with sqlite3.connect(self.kw['ledger']) as db:
            db.execute('UPDATE decisions SET report_sha256=?', ('0'*64,))
        before = self.kw['ledger'].read_bytes()
        with self.assertRaisesRegex(InputError, 'corrupt ledger'):
            self.recover(**self.kw)
        self.assertEqual(self.kw['ledger'].read_bytes(), before)
        self.assertFalse(self.kw['output'].exists())

    def test_existing_output_is_never_overwritten_and_missing_ledger_not_initialized(self):
        self.kw['output'].write_text('preserve')
        with self.assertRaises(InputError):
            self.recover(**self.kw)
        self.assertEqual(self.kw['output'].read_text(), 'preserve')
        self.kw['output'].unlink()
        self.kw['ledger'].unlink()
        self.assertFalse(self.recover(**self.kw))
        self.assertFalse(self.kw['ledger'].exists())
