import unittest
from dataclasses import replace
from decimal import Decimal, localcontext
from unittest.mock import patch

from quant_research.config import parse_config
from quant_research.data import Dataset
from quant_research.evaluation import parse_protocol
from quant_research.serde import InputError, canonical_json
from test_inputs import raw_config
from test_strategy_risk import bars_for


def fixture(prices=None):
    bars = bars_for(prices or list(range(100, 140)))
    dataset = Dataset(bars, {'kind': 'synthetic'}, 'a' * 64, 'b' * 64)
    raw = dict(schema_version=1, protocol_id='robust-test', embargo_sessions=2,
               candidate_lookbacks=[3, 2], selection_metric='validation_return_under_2x_cost')
    for name, start, end in [('development', 3, 18), ('validation', 21, 30), ('holdout', 33, 39)]:
        raw[name + '_start'] = bars[start].session.isoformat()
        raw[name + '_end'] = bars[end].session.isoformat()
    return dataset, parse_config(raw_config()), parse_protocol(raw, dataset)


class RobustnessTests(unittest.TestCase):
    def report(self, dataset=None, **updates):
        from quant_research.robustness import run_robustness
        original, config, protocol = fixture()
        options = dict(train_sessions=5, test_sessions=4, block_size=2, samples=30, seed=7)
        options.update(updates)
        return run_robustness(dataset or original, config, protocol, 'test-code', **options)

    def test_drawdown_includes_initial_cash_and_returns_are_compounded(self):
        from quant_research.robustness import path_metrics, net_daily_returns
        curve = [{'nav': Decimal('900')}, {'nav': Decimal('990')}]
        returns = net_daily_returns(curve, Decimal('1000'))
        self.assertEqual(returns, (Decimal('-0.1'), Decimal('0.1')))
        self.assertEqual(path_metrics(returns), {'total_return': Decimal('-0.01'),
                                               'maximum_drawdown': Decimal('0.1')})

    def test_expanding_prior_selection_and_frozen_next_test(self):
        dataset, _, protocol = fixture()
        from quant_research.backtest import simulate
        calls = []
        def capture(bars, config, start, strategy='trend', multiplier=1):
            calls.append((start, bars[-1].session))
            self.assertLessEqual(bars[-1].session, protocol.validation_end)
            return simulate(bars, config, start, strategy, multiplier)
        with patch('quant_research.robustness.simulate', side_effect=capture):
            report = self.report()
        previous, cursor = 0, 0
        for fold in report['walk_forward']['folds']:
            train = fold['training']
            self.assertGreater(train['sessions'], previous)
            previous = train['sessions']
            scores = [(candidate['total_return_2x'], -candidate['lookback'])
                      for candidate in fold['candidates']]
            self.assertEqual(fold['selected_lookback'], -max(scores)[1])
            first_test = next(i for i, bar in enumerate(dataset.bars) if bar.session == fold['test']['start'])
            last_train = next(i for i, bar in enumerate(dataset.bars) if bar.session == train['end'])
            self.assertGreaterEqual(first_test - last_train - 1, protocol.embargo_sessions)
            self.assertEqual([s['cost_multiplier'] for s in fold['scenarios']], [1, 2, 5])
            for _ in fold['candidates']:
                for segment in train['segments']:
                    self.assertEqual(calls[cursor], (segment['start'], segment['end']))
                    cursor += 1
            for _ in range(6):
                self.assertEqual(calls[cursor], (fold['test']['start'], fold['test']['end']))
                cursor += 1
        self.assertEqual(cursor, len(calls))
        self.assertNotIn('selected_lookback', report)

    def test_holdout_and_later_fold_data_cannot_change_earlier_metrics(self):
        dataset, _, _ = fixture()
        original = self.report()
        changed = replace(dataset, bars=tuple(replace(bar, open=Decimal('9999'),
                         high=Decimal('9999'), low=Decimal('9999'), close=Decimal('9999'))
                         if i >= 33 else bar for i, bar in enumerate(dataset.bars)))
        altered = self.report(changed)
        self.assertEqual(original['walk_forward'], altered['walk_forward'])
        self.assertEqual(original['resampling'], altered['resampling'])
        self.assertNotEqual(original['identities'], altered['identities'])
        changed = replace(dataset, bars=tuple(replace(bar, open=Decimal('5'), high=Decimal('5'),
                         low=Decimal('5'), close=Decimal('5')) if i >= 15 else bar
                         for i, bar in enumerate(dataset.bars)))
        self.assertEqual(original['walk_forward']['folds'][0],
                         self.report(changed)['walk_forward']['folds'][0])

    def test_paired_blocks_known_identity_and_no_reset_boundary_crossing(self):
        from quant_research.robustness import paired_block_resampling
        returns = (Decimal('-0.1'), Decimal('0.1'), Decimal('0.2'), Decimal('-0.2'))
        result = paired_block_resampling(returns, returns, block_size=2, samples=25,
                                         seed=5, segment_lengths=(2, 2))
        self.assertEqual(result, paired_block_resampling(returns, returns, block_size=2,
                         samples=25, seed=5, segment_lengths=(2, 2)))
        for metric in result['difference'].values():
            self.assertTrue(all(value == 0 for value in metric.values()))
        self.assertEqual(result['eligible_block_count'], 2)
        self.assertEqual(result['sampled_sessions'], 4)
        self.assertNotEqual(result['indices_digest'], paired_block_resampling(returns, returns,
                         block_size=2, samples=25, seed=6, segment_lengths=(2, 2))['indices_digest'])

    def test_deterministic_even_with_hostile_decimal_context(self):
        expected = canonical_json(self.report())
        with localcontext() as context:
            context.prec = 3
            self.assertEqual(expected, canonical_json(self.report()))

    def test_partial_test_tails_are_excluded_and_disclosed(self):
        report = self.report(block_size=4)
        self.assertTrue(all(fold['test']['sessions'] == 4
                            for fold in report['walk_forward']['folds']))
        self.assertEqual(report['walk_forward']['untested_sessions'], 10)

    def test_one_eligible_block_has_exact_loss_and_drawdown_percentiles(self):
        from quant_research.robustness import paired_block_resampling
        trend = (Decimal('-0.1'), Decimal('0.1'))
        hold = (Decimal('0'), Decimal('0'))
        result = paired_block_resampling(trend, hold, block_size=2, samples=3)
        self.assertEqual(set(result['trend']['total_return'].values()), {Decimal('-0.01')})
        self.assertEqual(set(result['trend']['maximum_drawdown'].values()), {Decimal('0.1')})
        self.assertEqual(set(result['difference']['total_return'].values()), {Decimal('-0.01')})

    def test_bad_bounds_and_insufficient_history_fail_before_simulation(self):
        for options in ({'samples': 0}, {'samples': 10001}, {'samples': True},
                        {'train_sessions': 1}, {'train_sessions': 1000},
                        {'test_sessions': 1}, {'folds': 0}, {'folds': 129},
                        {'block_size': 0}, {'block_size': 5}, {'seed': True},
                        {'embargo_sessions': 1}):
            with self.subTest(options=options), patch('quant_research.robustness.simulate',
                    side_effect=AssertionError('must validate first')), self.assertRaises(InputError):
                self.report(**options)
