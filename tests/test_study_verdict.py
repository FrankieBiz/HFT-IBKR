import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/study_verdict.py'
SPEC = importlib.util.spec_from_file_location('study_verdict', SCRIPT)
study_verdict = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(study_verdict)


def report(trend, hold):
    """trend/hold map cost multiplier -> (total_return, maximum_drawdown)."""
    rows = lambda values: [{'cost_multiplier': m, 'result': {'total_return': r, 'maximum_drawdown': d,
                                                            'trade_count': 3}} for m, (r, d) in values.items()]
    return {'mode': 'offline_holdout_release', 'selected_lookback': 150,
            'scenarios': rows(trend), 'benchmarks': {'cash': {}, 'buy_hold': rows(hold)}}


HOLD = {1: ('0.30', '0.20'), 2: ('0.29', '0.20'), 5: ('0.28', '0.20')}


class StudyVerdictTests(unittest.TestCase):
    def test_rule_reads_only_the_2x_column(self):
        cases = [((('0.31', '0.10')), 'DOMINATES', True),
                 ((('0.29', '0.20')), 'DOMINATED', False),   # equal drawdown is not lower
                 ((('0.10', '0.12')), 'RISK_REDUCING', True),
                 ((('-0.01', '0.05')), 'RISK_REDUCING', False)]  # negative return blocks proceeding
        for column, outcome, proceed in cases:
            # 1x and 5x deliberately contradict the 2x result; they must not matter.
            trend = {1: ('0.99', '0.01'), 2: column, 5: ('-0.50', '0.90')}
            with self.subTest(column=column):
                result = study_verdict.verdict(report(trend, HOLD))
                self.assertEqual((result['outcome'], result['proceed_to_shadow']), (outcome, proceed))
                self.assertEqual(set(result['sensitivities_only']), {'1x', '5x'})

    def test_brief_summary_is_one_readable_line(self):
        result = study_verdict.verdict(report({1: ('0.3', '0.1'), 2: ('0.1', '0.12'), 5: ('0', '0.2')}, HOLD))
        self.assertEqual(study_verdict.brief(result),
                         'RISK_REDUCING (proceed to shadow: yes). Holdout at 2x costs, SMA 150: trend return '
                         '10.0%, max drawdown 12.0%; buy-and-hold 29.0%, 20.0%.')

    def test_only_a_released_holdout_is_judged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'validation.json'
            path.write_text(json.dumps(dict(report(HOLD, HOLD), mode='offline_chronological_validation')))
            with patch('sys.stderr', new=io.StringIO()) as stderr:
                self.assertEqual(study_verdict.main([str(path)]), 2)
            self.assertIn('released holdout', stderr.getvalue())


if __name__ == '__main__':
    unittest.main()
