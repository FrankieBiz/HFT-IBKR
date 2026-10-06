from datetime import datetime, timedelta, timezone
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from quant_research.serde import InputError

NOW = datetime(2026, 10, 6, 14, 0, tzinfo=timezone.utc)


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('quant_session.health'), 'local heartbeat/health is missing')
        self.health = importlib.import_module('quant_session.health')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'heartbeat.json'
        self.ledger = Path(self.tmp.name)/'ledger.sqlite'

    def write(self, **kwargs):
        self.health.write_heartbeat(self.path, 'waiting', now=NOW, **kwargs)

    def check(self, **kwargs):
        return self.health.check_health(self.path, self.ledger, now=NOW, **kwargs)

    def test_missing_stale_future_failed_and_corrupt_fail(self):
        self.assertFalse(self.check()['healthy'])
        self.write()
        self.assertTrue(self.check()['healthy'])
        for when, status in ((NOW-timedelta(seconds=121), 'waiting'),
                             (NOW+timedelta(seconds=1), 'waiting'), (NOW, 'failed')):
            self.health.write_heartbeat(self.path, status, now=when)
            self.assertFalse(self.check()['healthy'])
        self.path.write_text('{}')
        self.assertFalse(self.check()['healthy'])

    def test_recorded_expected_deadline_checks_verified_ledger_even_after_restart(self):
        self.write(expected_session='2026-10-06', expected_deadline=NOW.isoformat())
        with patch.object(self.health.DecisionLedger, 'get', side_effect=InputError('missing')):
            self.assertFalse(self.check()['healthy'])
        with patch.object(self.health.DecisionLedger, 'get', return_value=b'{}') as get:
            self.assertTrue(self.check()['healthy'])
            get.assert_called_once_with('2026-10-06')
        self.health.write_heartbeat(self.path, 'waiting', now=NOW)
        self.assertEqual(json.loads(self.path.read_text())['expected_session'], '2026-10-06')
        with patch.object(self.health.DecisionLedger, 'get', side_effect=InputError('corrupt')):
            self.assertFalse(self.check()['healthy'])

    def test_explicit_deadline_works_without_expected_heartbeat(self):
        self.write()
        with patch.object(self.health.DecisionLedger, 'get', side_effect=InputError('missing')):
            self.assertFalse(self.check(session='2026-10-06', deadline=NOW.isoformat())['healthy'])
            self.assertTrue(self.check(session='2026-10-06', deadline=(NOW+timedelta(minutes=1)).isoformat())['healthy'])
        self.assertFalse(self.check(session='2026-10-06')['healthy'])

    def test_checker_never_creates_missing_ledger_or_uses_network(self):
        self.write(expected_session='2026-10-06', expected_deadline=NOW.isoformat())
        with patch('socket.socket', side_effect=AssertionError('offline only')):
            self.assertFalse(self.check()['healthy'])
        self.assertFalse(self.ledger.exists())

    def test_restart_cannot_postpone_same_session_deadline(self):
        self.write(expected_session='2026-10-06', expected_deadline=NOW.isoformat())
        self.health.write_heartbeat(self.path, 'waiting', now=NOW,
            expected_session='2026-10-06', expected_deadline=(NOW+timedelta(minutes=10)).isoformat())
        with patch.object(self.health.DecisionLedger, 'get', side_effect=InputError('missing')):
            self.assertFalse(self.check()['healthy'])

    def test_new_session_cannot_hide_previous_missing_or_failed_decision(self):
        prior = '2026-10-05'
        for failure in ('missing', 'corrupt'):
            self.health.write_heartbeat(self.path, 'failed', now=NOW,
                expected_session=prior, expected_deadline=(NOW-timedelta(days=1)).isoformat())
            self.health.write_heartbeat(self.path, 'waiting', now=NOW,
                expected_session='2026-10-06', expected_deadline=(NOW+timedelta(minutes=10)).isoformat())
            with patch.object(self.health.DecisionLedger, 'get', side_effect=InputError(failure)) as get:
                result = self.check()
                self.assertFalse(result['healthy'], result)
                self.assertTrue(any(prior in issue for issue in result['issues']))
                get.assert_called_once_with(prior)

    def test_schema1_expectation_survives_local_migration_to_new_session(self):
        from quant_research.serde import canonical_json
        self.path.write_text(canonical_json({'schema_version': 1, 'status': 'failed', 'updated_at': NOW.isoformat(),
            'expected_session': '2026-10-05', 'expected_deadline': (NOW-timedelta(days=1)).isoformat()}))
        self.health.write_heartbeat(self.path, 'waiting', now=NOW,
            expected_session='2026-10-06', expected_deadline=(NOW+timedelta(minutes=10)).isoformat())
        with patch.object(self.health.DecisionLedger, 'get', side_effect=InputError('missing')):
            self.assertFalse(self.check()['healthy'])

    def test_verified_previous_decision_allows_health_but_does_not_erase_expectation(self):
        self.write(expected_session='2026-10-05', expected_deadline=(NOW-timedelta(days=1)).isoformat())
        self.health.write_heartbeat(self.path, 'waiting', now=NOW,
            expected_session='2026-10-06', expected_deadline=NOW.isoformat())
        with patch.object(self.health.DecisionLedger, 'get', return_value=b'{}') as get:
            self.assertTrue(self.check()['healthy'])
            self.assertEqual({call.args[0] for call in get.call_args_list}, {'2026-10-05', '2026-10-06'})
        self.assertEqual(len(json.loads(self.path.read_text())['pending_expectations']), 2)

    def test_backlog_limit_and_corruption_fail_without_dropping_prior_date(self):
        self.write(expected_session='2026-10-05', expected_deadline=(NOW-timedelta(days=1)).isoformat())
        before = self.path.read_bytes()
        with patch.object(self.health, 'MAX_EXPECTATIONS', 1), self.assertRaises(InputError):
            self.health.write_heartbeat(self.path, 'waiting', now=NOW,
                expected_session='2026-10-06', expected_deadline=NOW.isoformat())
        self.assertEqual(before, self.path.read_bytes())
        report = json.loads(before)
        report['pending_expectations'] = []
        self.path.write_text(json.dumps(report))
        self.assertFalse(self.check()['healthy'])
