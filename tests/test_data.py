import tempfile
import unittest
from pathlib import Path
from quantlab.data import Bar, DatasetStore, load_csv

HEADER = 'timestamp,symbol,open,high,low,close,volume\n'
ROW = '2026-01-02T14:30:00Z,DEMO,100,102,99,101,1000\n'
META = dict(source='synthetic', adjustment='none', survivorship='synthetic universe', interval_seconds=60)

class DataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'bars.csv'
        self.path.write_text(HEADER + ROW)

    def test_csv_roundtrip_and_version_identity(self):
        bars = load_csv(self.path)
        with DatasetStore(Path(self.tmp.name) / 'data.sqlite') as store:
            key = store.import_csv(self.path, META)
            self.assertEqual(store.import_csv(self.path, META), key)
            self.assertEqual(store.bars(key), bars)
            self.assertEqual(store.metadata(key)['source'], 'synthetic')
            changed = dict(META, adjustment='split adjusted')
            self.assertNotEqual(store.import_csv(self.path, changed), key)

    def test_rejects_duplicate_bad_price_nonfinite_and_naive_time(self):
        for data in [ROW + ROW, ROW.replace('102', '98'), ROW.replace('100,102','nan,102'), ROW.replace('Z,', ',')]:
            with self.subTest(data=data):
                self.path.write_text(HEADER + data)
                with self.assertRaises(ValueError):
                    load_csv(self.path)

    def test_missing_metadata_and_invalid_import_leave_database_empty(self):
        with DatasetStore(Path(self.tmp.name) / 'data.sqlite') as store:
            with self.assertRaises(ValueError):
                store.import_csv(self.path, {})
            self.path.write_text(HEADER + ROW + ROW)
            with self.assertRaises(ValueError):
                store.import_csv(self.path, META)
            self.assertEqual(store.datasets(), [])

    def test_gap_report(self):
        self.path.write_text(HEADER + ROW + ROW.replace('14:30', '14:33'))
        with DatasetStore(Path(self.tmp.name) / 'data.sqlite') as store:
            key = store.import_csv(self.path, META)
            self.assertEqual(store.metadata(key)['gap_count'], 1)
