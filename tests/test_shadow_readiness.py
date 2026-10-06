import importlib
import json
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from quant_research.__main__ import source_identity
from quant_research.evaluation import (digest, evaluate_registered, freeze_selection, parse_protocol)
from quant_research.experiments import ExperimentRegistry
from quant_research.serde import InputError, canonical_json
from test_evaluation import inputs
from test_inputs import raw_config


def evidence(folder, *, kind='historical', trend_return='0.1', drawdown='0.05', real_bundle=False,
             feed='iex', price_reference=None):
    dataset, config, raw = inputs(list(range(100, 118)))
    dataset = replace(dataset, manifest={'kind': kind})
    if real_bundle:
        from quant_data.bundle import prepare_bundle, read_bundle
        from test_data_intake import inputs as intake_inputs
        prices, distributions, calendar, metadata = intake_inputs(folder)
        prices.write_text('session,open,high,low,close,volume\n' + ''.join(
            f'{b.session},{b.open},{b.high},{b.low},{b.close},{b.volume}\n' for b in dataset.bars))
        distributions.write_text('ex_date,amount,pay_date\n')
        calendar.write_text('session\n' + ''.join(f'{b.session}\n' for b in dataset.bars))
        declared = json.loads(metadata.read_text())
        declared['kind'] = kind  # Invented fixture exercising declared historical provenance only.
        declared['sources']['prices']['reference'] = price_reference or (
            'https://data.alpaca.markets/v2/stocks/bars symbols=SPY timeframe=1Day '
            f'adjustment=raw feed={feed}; invented fixture, no market data')
        metadata.write_text(canonical_json(declared))
        prepare_bundle(prices, distributions, calendar, metadata, folder/'spy.qdata')
        dataset = read_bundle(folder/'spy.qdata')
    protocol = parse_protocol(raw, dataset)
    paths = {name: folder / name for name in ('config.json', 'protocol.json', 'selection.json', 'holdout.json', 'registry.sqlite')}
    paths['config.json'].write_text(canonical_json(raw_config()))
    paths['protocol.json'].write_text(canonical_json(raw))
    code = source_identity()['source_sha256']
    with ExperimentRegistry(paths['registry.sqlite']) as registry:
        validation = evaluate_registered(dataset, config, protocol, code, registry=registry, run_id='validation')
        artifact = freeze_selection(dataset, config, protocol, code, validation)
        registry.register_freeze('validation', artifact)
        def rows(ret, dd):
            return [{'cost_multiplier': m, 'result': {'total_return': ret, 'maximum_drawdown': dd, 'trade_count': 3}}
                    for m in (1, 2, 5)]
        holdout = {'schema_version': 1, 'mode': 'offline_holdout_release', 'data_kind': kind,
                   'strategy_validation': 'unproven', 'run_id': 'holdout',
                   'artifact_digest': artifact['integrity_digest'], 'selected_lookback': artifact['selected_lookback'],
                   'scenarios': rows(trend_return, drawdown),
                   'benchmarks': {'cash': {'total_return': '0'}, 'buy_hold': rows('0.2', '0.15')}}
        registry.reserve_holdout('holdout', artifact['integrity_digest'], artifact['identities'],
                                 scope=f'{kind}:SPY', sessions=[b.session.isoformat() for b in dataset.bars[13:17]])
        registry.complete('holdout', digest(holdout), result=holdout)
    paths['selection.json'].write_text(canonical_json(artifact))
    paths['holdout.json'].write_text(canonical_json(holdout))
    return dataset, paths


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('quant_session.readiness'), 'readiness gate is missing')
        self.readiness = importlib.import_module('quant_session.readiness')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)

    def check(self, dataset, paths, **extra):
        with patch.object(self.readiness, 'read_bundle', return_value=dataset), \
                patch('socket.socket', side_effect=AssertionError('offline gate')):
            return self.readiness.verify_readiness(bundle=self.folder/'immutable.qdata',
                config=paths['config.json'], protocol=paths['protocol.json'], selection=paths['selection.json'],
                holdout=paths['holdout.json'], registry=paths['registry.sqlite'], **extra)

    def test_authenticated_historical_passes_and_registry_bytes_unchanged(self):
        dataset, paths = evidence(self.folder)
        before = paths['registry.sqlite'].read_bytes()
        result = self.check(dataset, paths)
        self.assertTrue(result['proceed_to_shadow'])
        self.assertEqual(result['planning_config']['lookback'], 2)
        self.assertEqual(before, paths['registry.sqlite'].read_bytes())

    def test_missing_registry_is_not_created(self):
        dataset, paths = evidence(self.folder)
        paths['registry.sqlite'].unlink()
        with self.assertRaises(InputError):
            self.check(dataset, paths)
        self.assertFalse(paths['registry.sqlite'].exists())

    def test_operational_feed_is_bound_to_authenticated_study_and_daily_bundle(self):
        for feed in ('iex', 'sip'):
            folder = self.folder / feed
            folder.mkdir()
            dataset, paths = evidence(folder, real_bundle=True, feed=feed)
            result = self.check(dataset, paths, require_alpaca_feed=True,
                                daily_bundle=folder/'spy.qdata')
            self.assertEqual(result['price_feed'], feed)

    def test_mismatched_daily_feed_rejected_before_operations(self):
        from quant_data.bundle import prepare_bundle, read_bundle
        dataset, paths = evidence(self.folder, real_bundle=True, feed='sip')
        metadata = self.folder/'metadata.json'
        declared = json.loads(metadata.read_text())
        declared['sources']['prices']['reference'] = declared['sources']['prices']['reference'].replace('feed=sip', 'feed=iex')
        metadata.write_text(canonical_json(declared))
        daily = self.folder/'daily.qdata'
        prepare_bundle(self.folder/'prices.csv', self.folder/'distributions.csv',
                       self.folder/'calendar.csv', metadata, daily)
        with patch.object(self.readiness, 'read_bundle', side_effect=[dataset, read_bundle(daily)]), \
                self.assertRaisesRegex(InputError, 'feed.*mismatch'):
            self.readiness.verify_readiness(bundle=self.folder/'spy.qdata',
                config=paths['config.json'], protocol=paths['protocol.json'], selection=paths['selection.json'],
                holdout=paths['holdout.json'], registry=paths['registry.sqlite'], daily_bundle=daily)

    def test_operational_feed_requires_unambiguous_alpaca_provenance(self):
        for i, reference in enumerate(('synthetic fixture',
                'https://data.alpaca.markets/v2/stocks/bars feed=auto',
                'https://data.alpaca.markets/v2/stocks/bars feed=sip feed=iex',
                'https://other.example/v2/stocks/bars feed=iex')):
            folder = self.folder / str(i)
            folder.mkdir()
            dataset, paths = evidence(folder, real_bundle=True, price_reference=reference)
            with self.subTest(reference=reference), self.assertRaisesRegex(InputError, 'feed'):
                self.check(dataset, paths, require_alpaca_feed=True)

    def test_synthetic_daily_bundle_cannot_use_historical_study_evidence(self):
        from quant_data.bundle import prepare_bundle, read_bundle
        dataset, paths = evidence(self.folder, real_bundle=True, feed='sip')
        metadata = self.folder/'metadata.json'
        declared = json.loads(metadata.read_text())
        declared['kind'] = 'synthetic'
        metadata.write_text(canonical_json(declared))
        daily = self.folder/'synthetic.qdata'
        prepare_bundle(self.folder/'prices.csv', self.folder/'distributions.csv',
                       self.folder/'calendar.csv', metadata, daily)
        with patch.object(self.readiness, 'read_bundle', side_effect=[dataset, read_bundle(daily)]), \
                self.assertRaisesRegex(InputError, 'historical daily'):
            self.readiness.verify_readiness(bundle=self.folder/'spy.qdata',
                config=paths['config.json'], protocol=paths['protocol.json'], selection=paths['selection.json'],
                holdout=paths['holdout.json'], registry=paths['registry.sqlite'], daily_bundle=daily)

    def test_synthetic_negative_dominated_and_nonfinite_evidence_fail(self):
        for i, kwargs in enumerate(({'kind': 'synthetic'}, {'trend_return': '-0.01'},
                                   {'drawdown': '0.2'}, {'trend_return': 'NaN'},
                                   {'drawdown': '-0.1'}, {'drawdown': '1.1'})):
            folder = self.folder / str(i)
            folder.mkdir()
            dataset, paths = evidence(folder, **kwargs)
            with self.subTest(kwargs=kwargs), self.assertRaises(InputError):
                self.check(dataset, paths)

    def test_source_config_protocol_and_dataset_changes_fail(self):
        dataset, paths = evidence(self.folder)
        with patch.object(self.readiness, 'source_identity', return_value={'source_sha256': 'changed'}), self.assertRaises(InputError):
            self.check(dataset, paths)
        with self.assertRaises(InputError):
            self.check(replace(dataset, data_sha256='c'*64), paths)
        original = json.loads(paths['config.json'].read_text())
        paths['config.json'].write_text(canonical_json(dict(original, target_fraction='0.1')))
        with self.assertRaises(InputError):
            self.check(dataset, paths)
        paths['config.json'].write_text(canonical_json(original))
        protocol = json.loads(paths['protocol.json'].read_text())
        paths['protocol.json'].write_text(canonical_json(dict(protocol, protocol_id='renamed')))
        with self.assertRaises(InputError):
            self.check(dataset, paths)

    def test_custom_config_allows_only_selected_lookback(self):
        dataset, paths = evidence(self.folder)
        config = json.loads(paths['config.json'].read_text())
        config['lookback'] = 2
        selected = self.folder/'selected.json'
        selected.write_text(canonical_json(config))
        self.check(dataset, paths, planning_config=selected)
        for key, value in (('lookback', 3), ('target_fraction', '0.1')):
            changed = dict(config, **{key: value})
            selected.write_text(canonical_json(changed))
            with self.subTest(key=key), self.assertRaises(InputError):
                self.check(dataset, paths, planning_config=selected)

    def test_recomputed_freeze_and_forged_report_are_not_registry_evidence(self):
        dataset, paths = evidence(self.folder)
        original = json.loads(paths['selection.json'].read_text())
        forged = dict(original, selected_lookback=3)
        forged['integrity_digest'] = digest({k:v for k,v in forged.items() if k != 'integrity_digest'})
        paths['selection.json'].write_text(canonical_json(forged))
        with self.assertRaises(InputError):
            self.check(dataset, paths)
        paths['selection.json'].write_text(canonical_json(original))
        holdout = json.loads(paths['holdout.json'].read_text())
        holdout['scenarios'][1]['result']['total_return'] = '0.3'
        paths['holdout.json'].write_text(canonical_json(holdout))
        with self.assertRaises(InputError):
            self.check(dataset, paths)

    def test_corrupt_original_validation_payload_fails(self):
        dataset, paths = evidence(self.folder)
        from contextlib import closing
        with closing(sqlite3.connect(paths['registry.sqlite'])) as db, db:
            db.execute('DROP TRIGGER payloads_no_update')
            db.execute("UPDATE result_payloads SET payload='{}' WHERE run_id='validation'")
        with self.assertRaises(InputError):
            self.check(dataset, paths)

    def test_cli_real_bundle_emits_selected_config_and_refuses_altered_output(self):
        import subprocess
        import sys
        dataset, paths = evidence(self.folder, real_bundle=True)
        selected = self.folder/'planning.json'
        args = [sys.executable, '-m', 'quant_session.readiness', '--bundle', str(self.folder/'spy.qdata'),
                '--config', str(paths['config.json']), '--protocol', str(paths['protocol.json']),
                '--selection', str(paths['selection.json']), '--holdout', str(paths['holdout.json']),
                '--registry', str(paths['registry.sqlite']), '--config-out', str(selected)]
        result = subprocess.run(args, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(selected.read_text())['lookback'], 2)
        raw = json.loads(selected.read_text())
        selected.write_text(canonical_json(dict(raw, target_fraction='0.1')))
        result = subprocess.run(args, text=True, capture_output=True)
        self.assertEqual(result.returncode, 2, result.stdout+result.stderr)
        self.assertIn('selected config differs', result.stderr)

    def test_authenticated_impossible_counts_and_nonfinite_cost_metrics_fail(self):
        from contextlib import closing
        for index, (key, value) in enumerate((('fees_paid', 'NaN'), ('trade_count', True),
                                             ('exposure_sessions', -1), ('total_return', '-1.1'))):
            folder = self.folder/str(index)
            folder.mkdir()
            dataset, paths = evidence(folder)
            report = json.loads(paths['holdout.json'].read_text())
            report['scenarios'][1]['result'][key] = value
            payload = canonical_json(report)
            with closing(sqlite3.connect(paths['registry.sqlite'])) as db, db:
                db.execute('DROP TRIGGER payloads_no_update')
                db.execute('DROP TRIGGER events_no_update')
                db.execute('UPDATE result_payloads SET payload=? WHERE run_id=?', (payload, 'holdout'))
                db.execute("UPDATE events SET result_digest=? WHERE run_id=? AND status='completed'", (digest(report), 'holdout'))
            paths['holdout.json'].write_text(payload)
            with self.subTest(key=key), self.assertRaises(InputError):
                self.check(dataset, paths)
