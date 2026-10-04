import json
import tempfile
import unittest
from pathlib import Path

from quantlab.research import (triple_barrier, cpcv, reconstruct_paths, walk_forward,
                               sharpe, psr, dsr, pbo, Registry, evaluate)


class ResearchTests(unittest.TestCase):
    def test_barrier_intervals(self):
        labels = triple_barrier([100, 102, 98, 99], horizon=2, upper=.01, lower=.01)
        self.assertEqual(labels[0], {'start': 0, 'end': 1, 'label': 1, 'return': .02})
        self.assertEqual(labels[-1]['end'], 3)

    def test_purge_and_embargo(self):
        intervals = [(i, min(i + 2, 23)) for i in range(24)]
        splits = cpcv(intervals, groups=6, test_groups=2, embargo=2)
        self.assertEqual(len(splits), 15)
        for split in splits:
            for i in split['train']:
                for j in split['test']:
                    self.assertFalse(intervals[i][0] <= intervals[j][1] + 2 and
                                     intervals[i][1] >= intervals[j][0])
        predictions = {s['id']: {i: float(i) for i in s['test']} for s in splits}
        paths = reconstruct_paths(splits, predictions, 24)
        self.assertEqual(len(paths), 5)
        self.assertTrue(all(p == list(range(24)) for p in paths))

    def test_walk_forward_never_trains_on_future(self):
        for split in walk_forward([(i, i + 2) for i in range(30)], 12, 6, 1):
            self.assertLess(max(i + 2 for i in split['train']) + 1, min(split['test']))

    def test_statistics_fail_closed(self):
        for fn in (sharpe, psr):
            with self.assertRaises(ValueError):
                fn([.01] * 10)
        with self.assertRaises(ValueError):
            dsr([.01, -.02, .03], 0, 5)
        with self.assertRaises(ValueError):
            pbo([[1, 1]] * 16, blocks=4)
        self.assertAlmostEqual(psr([-.02, -.01, .01, .02]), .5)
        self.assertEqual(pbo([[(-1)**i * .01, (-1)**i * .01] for i in range(16)], 4)['pbo'], 1)

    def test_extreme_finite_inputs(self):
        self.assertAlmostEqual(psr([1e100, -1e100, 2e100]), psr([1, -1, 2]))
        self.assertAlmostEqual(psr([1e308, -1e308, 1e308]), psr([1, -1, 1]))
        with self.assertRaises(ValueError):
            triple_barrier([1e-308, 1e308])

    def test_invalid_equity_valuation_rejected(self):
        from unittest.mock import patch
        from quantlab.research.pipeline import _checked_simulate
        result = {'summary': {'state': 'READY'}, 'events': [],
                  'equity': [{'valuation_valid': False}]}
        with patch('quantlab.research.pipeline.simulate', return_value=result):
            with self.assertRaises(ValueError):
                _checked_simulate([], None)

    def test_dsr_uses_selected_full_history_candidate(self):
        from quantlab.config import Config
        from quantlab.data import load_csv
        from quantlab.synthetic import generate
        from statistics import variance
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generate(root / 'bars.csv', count=180)
            result = evaluate(load_csv(root / 'bars.csv'), Config(), [(3, 12), (5, 20)],
                              root / 'registry.db', {'source': 'synthetic'})
            scores = [trial['sharpe']['value'] for trial in result['trials']]
            winner = max(range(len(scores)), key=lambda i: (scores[i], -i))
            selected = [row[winner] for row in result['candidate_returns']]
            self.assertEqual(result['dsr']['selected_candidate_index'], winner)
            self.assertEqual(result['dsr']['scope'], 'full_history_selected_candidate')
            self.assertEqual(result['dsr']['observations'], len(selected))
            self.assertEqual(result['dsr']['value'], dsr(selected, variance(scores), 2))
            from unittest.mock import patch
            from quantlab.research.pipeline import _checked_simulate
            def reject_holdouts(sample, config):
                if len(sample) == 30:
                    raise ValueError('invalid holdout valuation')
                return _checked_simulate(sample, config)
            with patch('quantlab.research.pipeline._checked_simulate', side_effect=reject_holdouts):
                missing_holdouts = evaluate(load_csv(root / 'bars.csv'), Config(), [(3, 12), (5, 20)],
                                            root / 'other_registry.db', {'source': 'synthetic'})
            self.assertEqual(missing_holdouts['psr']['status'], 'undefined')
            self.assertEqual(missing_holdouts['dsr'], result['dsr'])


    def test_registry_retains_review_history(self):
        with tempfile.TemporaryDirectory() as directory:
            with Registry(Path(directory) / 'runs.db') as registry:
                run = registry.start({'fast': 3}, {'source': 'test'})
                registry.finish(run, 'failed', {'error': 'example'})
                registry.review(run, 'rejected', 'Review only')
                self.assertEqual(registry.runs()[0]['status'], 'failed')
                self.assertEqual(len(registry.events(run)), 3)
                with self.assertRaises(ValueError):
                    registry.review(run, 'live', 'No activation')
                json.dumps(registry.runs(), allow_nan=False)

    def test_pipeline_preserves_failed_trials_and_training_selection(self):
        from dataclasses import replace
        from quantlab.config import Config
        from quantlab.data import load_csv
        from quantlab.synthetic import generate
        from quantlab.simulation import simulate
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generate(root / 'bars.csv', count=180)
            bars = load_csv(root / 'bars.csv')
            pairs = [(3, 12), (5, 20), (20, 5)]
            report = evaluate(bars, Config(), pairs, root / 'registry.db', {'source': 'synthetic'})
            self.assertEqual([r['status'] for r in report['trials']], ['completed', 'completed', 'failed'])
            self.assertEqual(report['candidate_matrix_columns'], [0, 1])
            self.assertEqual(report['dsr']['status'], 'undefined')
            json.dumps(report, allow_nan=False)
            first = report['walk_forward'][0]
            start = first['test'][0]
            changed = bars[:start] + [replace(b, open=b.open*1.01, high=b.high*1.01,
                                                   low=b.low*1.01, close=b.close*1.01) for b in bars[start:]]
            second = evaluate(changed, Config(), pairs, root / 'registry.db', {'source': 'perturbed'})
            self.assertEqual(first['candidate_index'], second['walk_forward'][0]['candidate_index'])
            self.assertEqual(first['training_sharpe'], second['walk_forward'][0]['training_sharpe'])
            winner = pairs[first['candidate_index']]
            isolated = simulate([bars[i] for i in first['test']],
                                replace(Config(), fast_window=winner[0], slow_window=winner[1]))
            self.assertEqual(first['returns'], isolated['returns'])
            self.assertEqual(first['returns'][0], 0)
            with Registry(root / 'registry.db') as registry:
                self.assertEqual(len(registry.runs()), 6)
            self.assertEqual(second['campaign_trial_count'], 6)
            self.assertIn('earlier campaign trials', second['dsr']['reason'])
            last = bars[-1]
            halted = bars[:-1] + [replace(last, open=last.open*2, high=last.high*2,
                                         low=last.low*2, close=last.close*2)]
            third = evaluate(halted, Config(), pairs[:2], root / 'registry.db', {'source': 'future halt'})
            self.assertTrue(all(row['status'] == 'failed' for row in third['trials']))
            self.assertEqual(first['candidate_index'], third['walk_forward'][0]['candidate_index'])
            self.assertEqual(first['training_sharpe'], third['walk_forward'][0]['training_sharpe'])
            self.assertEqual(third['psr']['status'], 'undefined')


if __name__ == '__main__':
    unittest.main()
