import unittest
from dataclasses import replace
from decimal import Decimal
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch

from quant_research.evaluation import (parse_protocol, evaluate_protocol, freeze_selection,
                                      release_holdout, evaluate_registered)
from quant_research.experiments import ExperimentRegistry
from quant_research.data import Dataset
from quant_research.config import parse_config
from quant_research.serde import InputError, canonical_json
from test_inputs import raw_config
from test_strategy_risk import bars_for


def inputs(prices=None):
    bars = bars_for(prices or [100] * 18)
    dataset = Dataset(bars, {'kind': 'synthetic'}, 'a' * 64, 'b' * 64)
    raw = dict(schema_version=1, protocol_id='example', embargo_sessions=1,
               candidate_lookbacks=[3, 2], selection_metric='validation_return_under_2x_cost')
    for name, start, end in [('development', 3, 6), ('validation', 8, 11), ('holdout', 13, 16)]:
        raw[name + '_start'] = bars[start].session.isoformat()
        raw[name + '_end'] = bars[end].session.isoformat()
    return dataset, parse_config(raw_config()), raw


def register_pure(registry, artifact, dataset, config, protocol):
    report = evaluate_protocol(dataset, config, protocol, 'code-v1')
    registry.reserve_validation('setup', artifact['identities'])
    registry.complete('setup', artifact['validation_report_digest'], result=report)
    registry.register_freeze('setup', artifact)


class EvaluationTests(unittest.TestCase):
    def test_saved_report_selection_uses_numeric_negative_returns(self):
        import json
        dataset, config, raw = inputs([90,110,80,100,90,100,100,120,110,120,120,80,90,120,120,110,120,90])
        protocol = parse_protocol(raw, dataset)
        report = evaluate_protocol(dataset, config, protocol, 'code-v1')
        self.assertEqual(report['selected_lookback'],3)
        persisted = json.loads(canonical_json(report))
        self.assertEqual(freeze_selection(dataset,config,protocol,'code-v1',persisted)['selected_lookback'],3)

    def test_strict_protocol_fields_types_ranges_warmup_and_embargo(self):
        dataset, _, raw = inputs()
        parse_protocol(raw, dataset)
        bads = [dict(raw, extra=1), dict(raw, schema_version=True),
                dict(raw, protocol_id=' '), dict(raw, embargo_sessions=True),
                dict(raw, candidate_lookbacks=[2, 2]), dict(raw, candidate_lookbacks=[True]),
                dict(raw, candidate_lookbacks=[]), dict(raw, candidate_lookbacks=[4]),
                dict(raw, selection_metric='return'), dict(raw, development_start='2025-01-01'),
                dict(raw, validation_start=raw['development_end']),
                dict(raw, embargo_sessions=2), dict(raw, development_end=raw['development_start']),
                dict(raw, development_start=raw['validation_end'])]
        for bad in bads:
            with self.subTest(bad=bad), self.assertRaises(InputError):
                parse_protocol(bad, dataset)

    def test_tie_selection_costs_reset_and_no_holdout_disclosure(self):
        dataset, config, raw = inputs()
        report = evaluate_protocol(dataset, config, parse_protocol(raw, dataset), 'code-v1')
        self.assertEqual(report['selected_lookback'], 2)
        self.assertEqual(report['trial_count'], 2)
        self.assertEqual(report['data_kind'], 'synthetic')
        self.assertNotIn('holdout', report['intervals'])
        self.assertIn('reset', report['interval_reset'])
        self.assertEqual(report['benchmarks']['cash']['total_return'],Decimal(0))
        for name in ('development','validation'):
            scenarios=report['benchmarks']['buy_hold'][name]
            self.assertEqual([s['cost_multiplier'] for s in scenarios],[1,2,5])
            self.assertTrue(all(s['result']['evaluated_sessions']==4 for s in scenarios))
        for candidate in report['candidates']:
            for name in ('development', 'validation'):
                scenarios = candidate[name]
                self.assertEqual([s['cost_multiplier'] for s in scenarios], [1, 2, 5])
                for scenario in scenarios:
                    self.assertEqual(scenario['result']['evaluated_sessions'], 4)
                    self.assertEqual(scenario['result']['equity_curve'][0]['shares'], 0)
                    self.assertEqual(scenario['result']['equity_curve'][0]['cash'], config.initial_cash)

    def test_future_holdout_mutation_does_not_change_validation(self):
        dataset, config, raw = inputs(list(range(100, 118)))
        protocol = parse_protocol(raw, dataset)
        original = evaluate_protocol(dataset, config, protocol, 'code-v1')
        bars = tuple(replace(b, close=Decimal('9999'), high=Decimal('9999')) if i >= 13 else b
                     for i, b in enumerate(dataset.bars))
        altered = evaluate_protocol(replace(dataset, bars=bars), config, protocol, 'code-v1')
        self.assertEqual(original['candidates'], altered['candidates'])
        self.assertEqual(original['selected_lookback'], altered['selected_lookback'])

    def test_only_prefixes_are_passed_to_simulator_and_returns_select(self):
        dataset, config, raw = inputs(list(range(100, 118)))
        protocol = parse_protocol(raw, dataset)
        from quant_research.backtest import simulate
        seen = []
        def capture(bars, *args):
            seen.append(bars[-1].session)
            return simulate(bars, *args)
        with patch('quant_research.evaluation.simulate', side_effect=capture):
            report = evaluate_protocol(dataset, config, protocol, 'code-v1')
        self.assertEqual(set(seen), {dataset.bars[6].session, dataset.bars[11].session})
        scores = [(c['validation'][1]['result']['total_return'], -c['lookback']) for c in report['candidates']]
        self.assertEqual(report['selected_lookback'], -max(scores)[1])

    def test_frozen_identity_and_tampering_rejected_before_simulation(self):
        dataset, config, raw = inputs()
        protocol = parse_protocol(raw, dataset)
        artifact = freeze_selection(dataset, config, protocol, 'code-v1',
                                    evaluate_protocol(dataset, config, protocol, 'code-v1'))
        with TemporaryDirectory() as tmp, ExperimentRegistry(Path(tmp) / 'runs.sqlite') as registry:
            register_pure(registry, artifact, dataset, config, protocol)
            cases = [(dict(artifact, selected_lookback=3), dataset, config, protocol, 'code-v1'),
                     (artifact, replace(dataset, data_sha256='c'*64), config, protocol, 'code-v1'),
                     (artifact, replace(dataset, manifest_sha256='c'*64), config, protocol, 'code-v1'),
                     (artifact, dataset, replace(config, lookback=8), protocol, 'code-v1'),
                     (artifact, dataset, config, replace(protocol, protocol_id='changed'), 'code-v1'),
                     (artifact, dataset, config, protocol, 'code-v2')]
            for i, args in enumerate(cases):
                with self.subTest(i=i), patch('quant_research.evaluation.simulate', side_effect=AssertionError), self.assertRaises(InputError):
                    release_holdout(*args, registry=registry, run_id=str(i))
            result = release_holdout(artifact, dataset, config, protocol, 'code-v1', registry=registry, run_id='release')
            self.assertEqual(result['data_kind'], 'synthetic')
            self.assertEqual(result['scenarios'][0]['result']['evaluated_sessions'], 4)
            with self.assertRaises(InputError):
                release_holdout(artifact, dataset, config, protocol, 'code-v1', registry=registry, run_id='again')

    def test_registered_failure_is_visible_and_holdout_failure_consumes_release(self):
        dataset, config, raw = inputs()
        protocol = parse_protocol(raw, dataset)
        artifact = freeze_selection(dataset, config, protocol, 'code-v1', evaluate_protocol(dataset, config, protocol, 'code-v1'))
        with TemporaryDirectory() as tmp, ExperimentRegistry(Path(tmp)/'runs.sqlite') as registry:
            register_pure(registry, artifact, dataset, config, protocol)
            with patch('quant_research.evaluation.simulate', side_effect=RuntimeError('failed')):
                with self.assertRaises(RuntimeError):
                    evaluate_registered(dataset, config, protocol, 'code-v1', registry=registry, run_id='validation')
                with self.assertRaises(RuntimeError):
                    release_holdout(artifact, dataset, config, protocol, 'code-v1', registry=registry, run_id='holdout')
            self.assertEqual([r['status'] for r in registry.records()][2:], ['reserved','failed','reserved','failed'])
            with self.assertRaises(InputError):
                release_holdout(artifact, dataset, config, protocol, 'code-v1', registry=registry, run_id='retry')

    def test_freeze_rejects_malformed_validation_report(self):
        dataset, config, raw = inputs()
        protocol = parse_protocol(raw, dataset)
        report = evaluate_protocol(dataset, config, protocol, 'code-v1')
        bad_reports = [None, {}, dict(report, candidates=[{}]),
                       dict(report, selected_lookback=True), dict(report, trial_count=True)]
        for bad in bad_reports:
            with self.subTest(bad=bad), self.assertRaises(InputError):
                freeze_selection(dataset, config, protocol, 'code-v1', bad)

    def test_holdout_replay_refused_after_registry_reopen(self):
        dataset, config, raw = inputs()
        protocol = parse_protocol(raw, dataset)
        artifact = freeze_selection(dataset, config, protocol, 'code-v1', evaluate_protocol(dataset, config, protocol, 'code-v1'))
        with TemporaryDirectory() as tmp:
            path = Path(tmp)/'runs.sqlite'
            with ExperimentRegistry(path) as registry:
                register_pure(registry, artifact, dataset, config, protocol)
                release_holdout(artifact, dataset, config, protocol, 'code-v1', registry=registry, run_id='first')
            with ExperimentRegistry(path) as registry, self.assertRaises(InputError):
                release_holdout(artifact, dataset, config, protocol, 'code-v1', registry=registry, run_id='second')

    def test_actual_bar_and_manifest_changes_reject_despite_original_file_hashes(self):
        dataset, config, raw = inputs()
        protocol = parse_protocol(raw, dataset)
        artifact = freeze_selection(dataset, config, protocol, 'code-v1', evaluate_protocol(dataset, config, protocol, 'code-v1'))
        changed = [replace(dataset, bars=(replace(dataset.bars[0], close=Decimal('101')),)+dataset.bars[1:]),
                   replace(dataset, manifest={'kind':'historical'})]
        with TemporaryDirectory() as tmp, ExperimentRegistry(Path(tmp)/'runs.sqlite') as registry:
            for i, altered in enumerate(changed):
                with self.subTest(i=i), self.assertRaises(InputError):
                    release_holdout(artifact, altered, config, protocol, 'code-v1', registry=registry, run_id=str(i))
            self.assertEqual(registry.records(), [])

    def test_registry_storage_failure_prevents_any_simulation(self):
        dataset, config, raw = inputs()
        protocol = parse_protocol(raw, dataset)
        with TemporaryDirectory() as tmp, ExperimentRegistry(Path(tmp)/'runs.sqlite') as registry:
            registry.connection.execute('PRAGMA query_only=ON')
            with patch('quant_research.evaluation.simulate', side_effect=AssertionError('must not compute')):
                with self.assertRaises(InputError):
                    evaluate_registered(dataset, config, protocol, 'code-v1', registry=registry, run_id='first')
            self.assertEqual(registry.records(), [])

    def test_recomputed_artifact_checksum_cannot_authorize_changed_selection(self):
        from quant_research.evaluation import digest
        dataset, config, raw = inputs()
        protocol = parse_protocol(raw, dataset)
        with TemporaryDirectory() as tmp, ExperimentRegistry(Path(tmp)/'runs.sqlite') as registry:
            report = evaluate_registered(dataset, config, protocol, 'code-v1', registry=registry, run_id='validation')
            original = freeze_selection(dataset, config, protocol, 'code-v1', report)
            registry.register_freeze('validation', original)
            forged = dict(original, selected_lookback=3)
            forged['integrity_digest'] = digest({k:v for k,v in forged.items() if k != 'integrity_digest'})
            with self.assertRaises(InputError):
                registry.register_freeze('validation', forged)
            with self.assertRaises(InputError):
                release_holdout(forged, dataset, config, protocol, 'code-v1', registry=registry, run_id='forged')

    def test_repeated_validation_cannot_reopen_same_holdout(self):
        dataset, config, raw = inputs()
        protocol = parse_protocol(raw, dataset)
        with TemporaryDirectory() as tmp, ExperimentRegistry(Path(tmp)/'runs.sqlite') as registry:
            for index in range(2):
                run_id = 'validation-' + str(index)
                report = evaluate_registered(dataset, config, protocol, 'code-v1', registry=registry, run_id=run_id)
                artifact = freeze_selection(dataset, config, protocol, 'code-v1', report)
                registry.register_freeze(run_id, artifact)
                if index == 0:
                    release_holdout(artifact, dataset, config, protocol, 'code-v1', registry=registry, run_id='first')
                else:
                    with self.assertRaises(InputError):
                        release_holdout(artifact, dataset, config, protocol, 'code-v1', registry=registry, run_id='second')
