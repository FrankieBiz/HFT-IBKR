from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from quant_research.serde import InputError
from quant_session.ledger import DecisionLedger
from test_shadow_session import fixtures, decide


class HistoryTests(unittest.TestCase):
    def test_readonly_verified_and_bounded_history(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'ledger.sqlite'
            ledger = DecisionLedger(path)
            self.assertTrue(callable(getattr(ledger, 'history', None)), 'public verified history missing')
            with self.assertRaises(InputError):
                ledger.history()
            self.assertFalse(path.exists())
            report = decide(*fixtures())
            ledger.record(report, 'fixture')
            before = path.read_bytes()
            rows, total = ledger.history(1)
            self.assertEqual(total, 1)
            self.assertEqual(rows[0]['decision_id'], report['decision_id'])
            self.assertEqual(before, path.read_bytes())
            for limit in (0, 501, True, '2'):
                with self.assertRaises(InputError):
                    ledger.history(limit)
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute('UPDATE decisions SET report=?', (b'{}',))
            with self.assertRaisesRegex(InputError, 'corrupt'):
                ledger.history(1)

    def test_history_verifies_risk_memory_even_outside_returned_window(self):
        import copy
        from quant_session.planner import decision_digest
        from quant_research.serde import canonical_json
        import hashlib
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'ledger.sqlite'
            ledger = DecisionLedger(path)
            report = decide(*fixtures())
            self.assertTrue(callable(getattr(ledger, 'history', None)), 'public verified history missing')
            ledger.record(report, 'first')
            second = copy.deepcopy(report)
            second['execution_session'] = '2025-03-12'
            second['risk_memory']['previous_session'] = '2025-03-11'
            second['decision_id'] = decision_digest(second)
            ledger.record(second, 'second')
            self.assertEqual(ledger.history(1)[0][0]['execution_session'], '2025-03-12')
            bad = copy.deepcopy(report)
            bad['risk_memory']['entry_halted'] = True
            bad['decision_id'] = decision_digest(bad)
            content = canonical_json(bad).encode()
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute('UPDATE decisions SET report=?,decision_id=?,report_sha256=? WHERE execution_session=?',
                                   (content, bad['decision_id'], hashlib.sha256(content).hexdigest(), '2025-03-11'))
            with self.assertRaisesRegex(InputError, 'risk memory'):
                ledger.history(1)
