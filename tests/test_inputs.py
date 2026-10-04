import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from decimal import Decimal

from quant_research.config import parse_config
from quant_research.data import load_dataset
from quant_research.serde import InputError, read_json


def raw_config(**updates):
    raw = {
        'schema_version': 1, 'mode': 'simulation', 'symbol': 'SPY',
        'initial_cash': '1000', 'lookback': 3, 'target_fraction': '0.8',
        'max_position_fraction': '0.9', 'max_shares': 100,
        'max_order_notional': '10000', 'max_drawdown': '0.5',
        'participation_limit': '0.01',
        'costs': {'half_spread_bps': '0', 'slippage_bps': '0', 'impact_bps': '0',
                  'commission_per_share': '0', 'minimum_commission': '0',
                  'exchange_fee_bps': '0', 'sell_fee_bps': '0'},
    }
    raw.update(updates)
    return raw


def write_dataset(folder, rows=None, **metadata):
    path = Path(folder) / 'bars.csv'
    if rows is None:
        rows = [
            ['2025-01-02', '100', '102', '99', '101', '10000', '0', ''],
            ['2025-01-03', '101', '103', '100', '102', '10000', '0', ''],
        ]
    with path.open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['session', 'open', 'high', 'low', 'close', 'volume',
                         'dividend', 'dividend_pay_date'])
        writer.writerows(rows)
    manifest = {
        'schema_version': 1, 'symbol': 'SPY', 'currency': 'USD',
        'kind': 'synthetic', 'source': 'unit test generated data',
        'retrieved_at': '2026-10-04T00:00:00Z', 'price_policy': 'raw_unadjusted',
        'corporate_actions': 'complete_dividends_no_splits',
        'splits_in_interval': False, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'calendar_source': 'synthetic session fixture',
        'expected_sessions': [r[0] for r in rows],
    }
    manifest.update(metadata)
    mpath = Path(folder) / 'manifest.json'
    mpath.write_text(json.dumps(manifest))
    return path, mpath


class ConfigTests(unittest.TestCase):
    def test_valid_config(self):
        config = parse_config(raw_config())
        self.assertEqual(config.initial_cash, Decimal('1000'))
        self.assertEqual(config.lookback, 3)

    def test_fail_closed_configuration(self):
        cases = [
            {'mode': 'live'}, {'mode': 'paper'}, {'lookback': True},
            {'lookback': 1}, {'symbol': 'MES'}, {'max_shares': False},
            {'initial_cash': 'NaN'}, {'initial_cash': 'Infinity'},
            {'initial_cash': 1000.0}, {'initial_cash': '-1'},
            {'target_fraction': '1.1'}, {'max_position_fraction': '0.5'},
            {'max_drawdown': '0'}, {'participation_limit': '0'},
            {'initial_cash': '1e1000000'}, {'surprise': 1},
        ]
        for update in cases:
            with self.subTest(update=update), self.assertRaises(InputError):
                parse_config(raw_config(**update))
        missing = raw_config()
        del missing['max_shares']
        with self.assertRaises(InputError):
            parse_config(missing)

    def test_costs_must_be_safe_in_all_stress_scenarios(self):
        raw = raw_config()
        raw['costs']['slippage_bps'] = '2000'
        with self.assertRaises(InputError):
            parse_config(raw)
        raw = raw_config()
        raw['costs']['sell_fee_bps'] = '-1'
        with self.assertRaises(InputError):
            parse_config(raw)


class DataTests(unittest.TestCase):
    def test_loads_explicit_synthetic_provenance(self):
        with tempfile.TemporaryDirectory() as folder:
            data = load_dataset(*write_dataset(folder))
            self.assertEqual(data.bars[0].close, Decimal('101'))
            self.assertEqual(data.manifest['kind'], 'synthetic')
            self.assertEqual(len(data.data_sha256), 64)

    def test_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(InputError, 'hash'):
                load_dataset(*write_dataset(folder, sha256='0' * 64))

    def test_missing_session_and_duplicate_dates(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(InputError):
                load_dataset(*write_dataset(folder, expected_sessions=['2025-01-02']))
            rows = [['2025-01-02', '100', '100', '100', '100', '1', '0', '']] * 2
            with self.assertRaises(InputError):
                load_dataset(*write_dataset(folder, rows))

    def test_bad_prices_volumes_and_dividends(self):
        for index, value in [(1, 'NaN'), (1, '1e1000000'), (2, '90'),
                             (3, '105'), (4, '0'), (5, '0'), (5, '1.5'),
                             (6, '-1'), (7, '2025-01-04')]:
            with self.subTest(index=index, value=value), tempfile.TemporaryDirectory() as folder:
                rows = [['2025-01-02', '100', '102', '99', '101', '10', '0', '']]
                rows[0][index] = value
                with self.assertRaises(InputError):
                    load_dataset(*write_dataset(folder, rows))

    def test_distribution_requires_pay_date_and_prior_context(self):
        for rows in [
            [['2025-01-02', '100', '100', '100', '100', '10', '1', '2025-01-10']],
            [['2025-01-02', '100', '100', '100', '100', '10', '0', ''],
             ['2025-01-03', '99', '99', '99', '99', '10', '1', '']],
            [['2025-01-02', '100', '100', '100', '100', '10', '0', ''],
             ['2025-01-03', '99', '99', '99', '99', '10', '1', '2025-01-03']],
        ]:
            with self.subTest(rows=rows), tempfile.TemporaryDirectory() as folder:
                with self.assertRaises(InputError):
                    load_dataset(*write_dataset(folder, rows))

    def test_manifest_rejects_adjusted_data_splits_bad_schema_or_time(self):
        for update in [{'price_policy': 'adjusted'}, {'splits_in_interval': True},
                       {'schema_version': True}, {'symbol': 'QQQ'},
                       {'currency': 'EUR'}, {'kind': 'unknown'},
                       {'source': ''}, {'retrieved_at': '2026-10-04'},
                       {'retrieved_at': '2026-10-04T00:00:00+02:00'},
                       {'extra': 'field'}]:
            with self.subTest(update=update), tempfile.TemporaryDirectory() as folder:
                with self.assertRaises(InputError):
                    load_dataset(*write_dataset(folder, **update))

    def test_duplicate_json_keys_are_not_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'bad.json'
            path.write_text('{"mode":"simulation","mode":"live"}')
            with self.assertRaises(InputError):
                read_json(path)

    def test_oversized_volume_is_an_input_error(self):
        with tempfile.TemporaryDirectory() as folder:
            rows = [['2025-01-02', '100', '100', '100', '100', '9' * 5000, '0', '']]
            with self.assertRaises(InputError):
                load_dataset(*write_dataset(folder, rows))

    def test_manifest_digest_matches_parsed_bytes_even_if_file_changes(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            data_path, manifest_path = write_dataset(folder)
            consumed = manifest_path.read_bytes()
            original_read = Path.read_bytes
            def read_and_change(path):
                if path == data_path:
                    manifest_path.write_text('{}')
                return original_read(path)
            with patch.object(Path, 'read_bytes', read_and_change):
                dataset = load_dataset(data_path, manifest_path)
            self.assertEqual(dataset.manifest_sha256, hashlib.sha256(consumed).hexdigest())

    def test_oversized_json_integer_is_an_input_error(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'oversized.json'
            path.write_text('{"schema_version":' + '9' * 5000 + '}')
            with self.assertRaises(InputError):
                read_json(path)
