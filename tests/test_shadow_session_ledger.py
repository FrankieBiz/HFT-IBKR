import copy
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from quant_research.serde import InputError
from quant_session.inputs import read_document
from quant_session.ledger import DecisionLedger
from test_shadow_session import fixtures, decide


class LedgerTests(unittest.TestCase):
    def test_retry_conflict_corruption_and_frozen_block(self):
        report=decide(*fixtures())
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'ledger.db'
            ledger=DecisionLedger(path)
            first=ledger.record(report,'input-a')
            self.assertEqual(first,ledger.record(report,'input-a'))
            with self.assertRaisesRegex(InputError,'conflict'):
                ledger.record(report,'input-b')
            with closing(sqlite3.connect(path)) as connection, connection:
                self.assertEqual(connection.execute('SELECT count(*) FROM decisions').fetchone()[0],1)
                connection.execute("UPDATE decisions SET report = ?",(b'{}',))
            with self.assertRaisesRegex(InputError,'corrupt'):
                ledger.record(report,'input-a')
            bad=copy.deepcopy(report);bad.update(status='BLOCKED',proposal=None)
            with self.assertRaises(InputError): ledger.record(bad,'input-a')

    def test_strict_bounded_read(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'input.json'
            for content in [b'{"a":1,"a":2}',b'{"a":NaN}',b' '* (1024*1024+1)]:
                path.write_bytes(content)
                with self.assertRaises(InputError):read_document(path)
            path.write_bytes(b'{"a":1}')
            self.assertEqual(read_document(path),({'a':1},b'{"a":1}'))
