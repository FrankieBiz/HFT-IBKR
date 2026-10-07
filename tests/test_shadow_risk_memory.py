import copy
import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
import sqlite3
import tempfile
import unittest

from quant_research.serde import InputError
from quant_session.inputs import parse_schedule, parse_snapshot
from quant_session.ledger import DecisionLedger
from test_shadow_session import fixtures, decide


def next_session(data, schedule, snapshot, *, nav='10000', peak='10000', shares=0):
    schedule = copy.deepcopy(schedule)
    snapshot = copy.deepcopy(snapshot)
    day = (date.fromisoformat(snapshot['execution_session']) + timedelta(days=1)).isoformat()
    from dataclasses import replace
    price = data.bars[-1].close + 1
    bar = replace(data.bars[-1], session=date.fromisoformat(snapshot['execution_session']),
                  open=price, high=price, low=price, close=price)
    data = replace(data, bars=data.bars + (bar,))
    schedule['sessions'].append({'session': day, 'open_at': day+'T13:30:00Z',
                                 'close_at': day+'T20:00:00Z'})
    snapshot['execution_session'] = day
    snapshot['now'] = snapshot['quote']['as_of'] = snapshot['portfolio']['as_of'] = day+'T13:30:00Z'
    snapshot['portfolio'].update(cash=nav, settled_cash=nav, nav=nav, peak_nav=peak, shares=shares)
    return data, schedule, snapshot


def recorded(ledger, data, config, schedule, snapshot):
    return json.loads(ledger.plan(data, config, parse_schedule(schedule), parse_snapshot(snapshot)))


class DurableRiskTests(unittest.TestCase):
    def test_restart_and_lower_declared_peak_cannot_clear_drawdown_halt(self):
        data, config, schedule, snapshot = fixtures()
        snapshot['portfolio']['peak_nav'] = '20000'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'ledger.db'
            first = recorded(DecisionLedger(path), data, config, schedule, snapshot)
            self.assertIn('DRAWDOWN_LIMIT', first['blockers'])
            self.assertTrue(first['risk_memory']['entry_halted'])
            data, schedule, snapshot = next_session(data, schedule, snapshot, nav='25000', peak='25000')
            second = recorded(DecisionLedger(path), data, config, schedule, snapshot)
            self.assertIn('DRAWDOWN_LIMIT', second['blockers'])
            self.assertTrue(second['risk_memory']['entry_halted'])
            self.assertEqual(second['risk_memory']['maximum_drawdown'], '0.5')

    def test_observed_peak_survives_edited_portfolio_and_corrupt_history_blocks(self):
        data, config, schedule, snapshot = fixtures()
        config = replace(config, max_drawdown=Decimal('0.20'))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'ledger.db'
            recorded(DecisionLedger(path), data, config, schedule, snapshot)
            data, schedule, snapshot = next_session(data, schedule, snapshot, nav='8000', peak='8000')
            second = recorded(DecisionLedger(path), data, config, schedule, snapshot)
            self.assertEqual(second['risk_memory']['peak_nav'], '10000')
            self.assertIn('DRAWDOWN_LIMIT', second['blockers'])
            with closing(sqlite3.connect(path)) as conn, conn:
                conn.execute('UPDATE decisions SET report=? WHERE execution_session=?',
                             (b'{}', '2025-03-11'))
            data, schedule, snapshot = next_session(data, schedule, snapshot)
            with self.assertRaisesRegex(InputError, 'corrupt'):
                recorded(DecisionLedger(path), data, config, schedule, snapshot)

    def test_exact_retry_recovers_before_memory_recomputation_and_changed_inputs_conflict(self):
        data, config, schedule, snapshot = fixtures()
        with tempfile.TemporaryDirectory() as tmp:
            ledger = DecisionLedger(Path(tmp)/'ledger.db')
            first = recorded(ledger, data, config, schedule, snapshot)
            later_data, later_schedule, later_snapshot = next_session(data, schedule, snapshot)
            recorded(ledger, later_data, config, later_schedule, later_snapshot)
            self.assertEqual(recorded(ledger, data, config, schedule, snapshot), first)
            snapshot['portfolio']['cash'] = snapshot['portfolio']['settled_cash'] = '9000'
            with self.assertRaisesRegex(InputError, 'conflict'):
                recorded(ledger, data, config, schedule, snapshot)

    def test_new_sessions_cannot_be_recorded_out_of_order(self):
        data, config, schedule, snapshot = fixtures()
        with tempfile.TemporaryDirectory() as tmp:
            ledger = DecisionLedger(Path(tmp)/'ledger.db')
            later_data, later_schedule, later_snapshot = next_session(data, schedule, snapshot)
            recorded(ledger, later_data, config, later_schedule, later_snapshot)
            with self.assertRaisesRegex(InputError, 'chronological'):
                recorded(ledger, data, config, schedule, snapshot)

    def test_concurrent_identical_plans_have_one_frozen_row(self):
        data, config, schedule, snapshot = fixtures()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'ledger.db'
            with ThreadPoolExecutor(max_workers=4) as pool:
                rows = list(pool.map(lambda _: recorded(DecisionLedger(path), data, config, schedule, snapshot), range(8)))
            self.assertTrue(all(row == rows[0] for row in rows))
            with closing(sqlite3.connect(path)) as conn:
                self.assertEqual(conn.execute('SELECT count(*) FROM decisions').fetchone()[0], 1)
            self.assertEqual(json.loads(DecisionLedger(path).get('2025-03-11')), rows[0])

    def test_legacy_history_requires_reviewed_migration(self):
        from quant_session.planner import decision_digest
        data, config, schedule, snapshot = fixtures()
        report = decide(data, config, schedule, snapshot)
        report.pop('risk_memory', None)
        report['decision_id'] = decision_digest(report)
        with tempfile.TemporaryDirectory() as tmp:
            ledger = DecisionLedger(Path(tmp)/'ledger.db')
            ledger.record(report, 'legacy-input')
            data, schedule, snapshot = next_session(data, schedule, snapshot)
            with self.assertRaisesRegex(InputError, 'legacy'):
                recorded(ledger, data, config, schedule, snapshot)

    def test_invalid_marks_do_not_latch_or_raise_observed_peak(self):
        data, config, schedule, snapshot = fixtures()
        with tempfile.TemporaryDirectory() as tmp:
            ledger = DecisionLedger(Path(tmp)/'ledger.db')
            recorded(ledger, data, config, schedule, snapshot)
            data, schedule, snapshot = next_session(data, schedule, snapshot, nav='1000', peak='99999')
            snapshot['now'] = snapshot['execution_session']+'T13:32:00Z'
            invalid = recorded(ledger, data, config, schedule, snapshot)
            self.assertIn('STALE_QUOTE', invalid['blockers'])
            self.assertFalse(invalid['risk_memory']['entry_halted'])
            self.assertEqual(invalid['risk_memory']['peak_nav'], '10000')

    def test_latched_drawdown_keeps_signal_exit_available(self):
        data, config, schedule, snapshot = fixtures((102, 100), shares=5)
        snapshot['portfolio']['peak_nav'] = '20000'
        with tempfile.TemporaryDirectory() as tmp:
            result = recorded(DecisionLedger(Path(tmp)/'ledger.db'), data, config, schedule, snapshot)
            self.assertTrue(result['risk_memory']['entry_halted'])
            self.assertEqual(result['proposal']['side'], 'SELL')

    def test_manual_halt_does_not_hide_valid_drawdown_marks(self):
        data, config, schedule, snapshot = fixtures()
        with tempfile.TemporaryDirectory() as tmp:
            ledger = DecisionLedger(Path(tmp)/'ledger.db')
            recorded(ledger, data, config, schedule, snapshot)
            data, schedule, snapshot = next_session(data, schedule, snapshot, nav='5000', peak='10000')
            snapshot['portfolio']['halted'] = True
            during = recorded(ledger, data, config, schedule, snapshot)
            self.assertIn('HALTED', during['blockers'])
            self.assertTrue(during['risk_memory']['entry_halted'])
            data, schedule, snapshot = next_session(data, schedule, snapshot)
            snapshot['portfolio']['halted'] = False
            self.assertIn('DRAWDOWN_LIMIT', recorded(ledger, data, config, schedule, snapshot)['blockers'])

    def test_semantically_invalid_memory_blocks_reads_and_exact_retries(self):
        import hashlib
        from quant_research.serde import canonical_json
        from quant_session.planner import decision_digest
        data, config, schedule, snapshot = fixtures()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'ledger.db'
            ledger = DecisionLedger(path)
            report = recorded(ledger, data, config, schedule, snapshot)
            report['risk_memory']['peak_nav'] = '-1'
            report['decision_id'] = decision_digest(report)
            content = canonical_json(report).encode()
            with closing(sqlite3.connect(path)) as conn, conn:
                conn.execute('UPDATE decisions SET report=?, report_sha256=?, decision_id=?',
                    (content, hashlib.sha256(content).hexdigest(), report['decision_id']))
            for action in (lambda: ledger.get(snapshot['execution_session']),
                           lambda: recorded(ledger, data, config, schedule, snapshot)):
                with self.assertRaisesRegex(InputError, 'corrupt'):
                    action()
