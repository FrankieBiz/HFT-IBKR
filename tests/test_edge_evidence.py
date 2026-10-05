import copy
from datetime import date, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction
import unittest

from quant_evidence.inputs import parse_input
from quant_evidence.assessment import assess
from quant_evidence.statistics import _draw_total, fifth_percentile, bootstrap_bound
from quant_research.serde import InputError, canonical_json


def fixture(gross='5'):
    days = []
    day = date(2026, 8, 3)
    while len(days) < 30:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day += timedelta(days=1)
    rows = [dict(session=day, gross_pnl=gross, variable_cost='1', recurring_cost='1',
                 outcome_bounded=True, constraints_satisfied=True, quality_notes='') for day in days]
    return dict(schema_version=1, evidence_kind='synthetic', experiment_id='invented-experiment',
                candidate_id='invented-candidate', source_notes='Invented outcomes and weekday calendar.',
                cost_notes='Invented costs already allocated per scheduled day.', scheduled_sessions=days,
                scenarios={name: copy.deepcopy(rows) for name in
                           ('primary', 'double_friction', 'tail_delay', 'conservative_liquidity')})


def run(raw):
    return assess(parse_input(raw))


class BootstrapTests(unittest.TestCase):
    def test_percentile_exact_interpolation(self):
        self.assertEqual(fifth_percentile([0, 10, 20]), 1)
        self.assertEqual(fifth_percentile([-10, 10]), -9)
        self.assertEqual(fifth_percentile([7]), 7)

    def test_blocks_overlap_without_wrapping_and_last_is_truncated(self):
        class Draws:
            def __init__(self):
                self.values = iter([1, 0])
                self.bounds = []

            def randrange(self, stop):
                self.bounds.append(stop)
                return next(self.values)

        rng = Draws()
        # values 1,2,4: block at 1 -> 2+4; truncated block at 0 -> 1.
        self.assertEqual(_draw_total([0, 1, 3, 7], 2, rng), 7)
        self.assertEqual(rng.bounds, [2, 2])

    def test_full_length_blocks_and_constant_series_have_exact_bounds(self):
        self.assertEqual(bootstrap_bound([1, 2, 3], 3), 2)
        self.assertEqual(bootstrap_bound([7] * 30, 5), 7)

    def test_resampling_is_reproducible(self):
        values = list(range(-15, 15))
        self.assertEqual(bootstrap_bound(values, 5), bootstrap_bound(values, 5))


class EvidenceTests(unittest.TestCase):
    def test_positive_arithmetic_never_promotes_candidate(self):
        report = run(fixture())
        self.assertEqual(report['numeric_assessment'], 'meets_pilot_numeric_criteria')
        self.assertEqual(report['status'], 'diagnostic_only')
        self.assertFalse(report['promotion_allowed'])
        self.assertFalse(report['g3_complete'])
        primary = report['scenarios']['primary']
        self.assertEqual(primary['total_gross_pnl'], 150)
        self.assertEqual(primary['total_variable_cost'], 30)
        self.assertEqual(primary['total_recurring_cost'], 30)
        self.assertEqual(primary['total_net_pnl'], 90)
        self.assertEqual(primary['mean_daily_net_pnl'], 3)
        self.assertEqual(primary['net_excluding_best_day'], 87)
        self.assertEqual(primary['max_close_to_close_drawdown'], 0)
        self.assertEqual([b['lower_bound_daily_net_pnl'] for b in report['bootstrap']], [3, 3, 3])
        self.assertEqual(report['method']['resamples'], 10000)
        self.assertEqual(report['method']['seed'], 20261005)

    def test_losing_and_zero_mean_candidates_rejected(self):
        for gross in ('1', '2'):
            with self.subTest(gross=gross):
                report = run(fixture(gross))
                self.assertEqual(report['numeric_assessment'], 'reject')
                self.assertIn('nonpositive_primary_mean', report['reasons'])

    def test_positive_mean_with_uncertain_lower_bound_is_inconclusive(self):
        raw = fixture('2')
        raw['scenarios']['primary'][0]['gross_pnl'] = '32'
        report = run(raw)
        self.assertEqual(report['scenarios']['primary']['mean_daily_net_pnl'], 1)
        self.assertEqual(report['numeric_assessment'], 'inconclusive')
        self.assertIn('bootstrap_bound_not_positive', report['reasons'])

    def test_negative_stress_mean_rejects_positive_primary(self):
        raw = fixture()
        for row in raw['scenarios']['tail_delay']:
            row['gross_pnl'] = '0'
        report = run(raw)
        self.assertEqual(report['numeric_assessment'], 'reject')
        self.assertIn('negative_stress_mean:tail_delay', report['reasons'])

    def test_exactly_zero_stress_mean_is_allowed(self):
        raw = fixture()
        for row in raw['scenarios']['tail_delay']:
            row['gross_pnl'] = '2'
        self.assertEqual(run(raw)['numeric_assessment'], 'meets_pilot_numeric_criteria')

    def test_unknown_primary_outcome_not_dropped_or_imputed(self):
        raw = fixture()
        raw['scenarios']['primary'][4].update(
            outcome_bounded=False, gross_pnl=None, quality_notes='Exit exposure unresolved.')
        report = run(raw)
        self.assertEqual(report['numeric_assessment'], 'inconclusive')
        self.assertIsNone(report['scenarios']['primary']['total_net_pnl'])
        self.assertEqual(report['scenarios']['primary']['session_count'], 30)
        self.assertEqual(report['scenarios']['primary']['unbounded_sessions'], [raw['scheduled_sessions'][4]])
        self.assertEqual(report['bootstrap'], [])

    def test_unknown_stress_prevents_positive_numeric_assessment(self):
        raw = fixture()
        raw['scenarios']['double_friction'][0].update(
            outcome_bounded=False, quality_notes='Unbounded slippage.')
        report = run(raw)
        self.assertEqual(report['numeric_assessment'], 'inconclusive')
        self.assertEqual(len(report['bootstrap']), 3)

    def test_known_constraint_failure_takes_precedence_over_unknown_outcome(self):
        raw = fixture()
        raw['scenarios']['primary'][0].update(outcome_bounded=False, constraints_satisfied=False,
                                             gross_pnl=None, quality_notes='Unreconciled position.')
        report = run(raw)
        self.assertEqual(report['numeric_assessment'], 'reject')
        self.assertIn('constraint_failure:primary', report['reasons'])

    def test_costs_still_count_on_zero_trade_days_and_drawdown_starts_at_zero(self):
        raw = fixture('2')
        rows = raw['scenarios']['primary']
        rows[0].update(gross_pnl='0', variable_cost='0')  # -1
        rows[1]['gross_pnl'] = '-2'  # -4
        rows[2]['gross_pnl'] = '5'  # +3
        result = run(raw)['scenarios']['primary']
        self.assertEqual(result['total_net_pnl'], -2)
        self.assertEqual(result['max_close_to_close_drawdown'], 5)
        self.assertEqual(result['worst_day'], -4)
        self.assertEqual(result['losing_days'], 2)
        self.assertEqual(result['zero_net_days'], 27)

    def test_exact_small_difference_of_large_amounts(self):
        raw = fixture()
        for rows in raw['scenarios'].values():
            for row in rows:
                row.update(gross_pnl='1000000000000000000',
                           variable_cost='1000000000000000000', recurring_cost='0.000000000001')
        report = run(raw)
        self.assertEqual(report['scenarios']['primary']['total_net_pnl'], Decimal('-0.000000000030'))

    def test_full_documented_amount_precision_is_accepted(self):
        for value, expected in (
            ('999999999999999999.999999999999', 10 ** 30 - 1),
            ('-999999999999999999.999999999999', -(10 ** 30 - 1)),
            ('1000000000000000000.000000000000', 10 ** 30),
        ):
            with self.subTest(value=value):
                raw = fixture()
                raw['scenarios']['primary'][0]['gross_pnl'] = value
                self.assertEqual(parse_input(raw).scenarios['primary'][0].gross_pnl, expected)

    def test_ambient_decimal_precision_has_no_effect(self):
        expected = canonical_json(run(fixture()))
        with localcontext() as context:
            context.prec = 6
            self.assertEqual(canonical_json(run(fixture())), expected)

    def test_bad_inputs_and_missing_sessions_rejected(self):
        mutations = [
            lambda r: r.update(extra=True), lambda r: r.update(schema_version=True),
            lambda r: r.update(evidence_kind='verified'), lambda r: r.update(source_notes=''),
            lambda r: r['scheduled_sessions'].pop(), lambda r: r['scheduled_sessions'].reverse(),
            lambda r: r['scenarios'].pop('tail_delay'),
            lambda r: r['scenarios']['primary'].pop(),
            lambda r: r['scenarios']['primary'].reverse(),
            lambda r: r['scenarios']['primary'][0].update(variable_cost='-1'),
            lambda r: r['scenarios']['primary'][0].update(gross_pnl='NaN'),
            lambda r: r['scenarios']['primary'][0].update(gross_pnl='--1'),
            lambda r: r['scenarios']['primary'][0].update(gross_pnl=None),
            lambda r: r['scenarios']['primary'][0].update(outcome_bounded=1),
            lambda r: r['scenarios']['primary'][0].update(constraints_satisfied='true'),
            lambda r: r['scenarios']['primary'][0].update(outcome_bounded=False),
            lambda r: r['scenarios']['primary'][0].update(gross_pnl='1e-13'),
            lambda r: r['scenarios']['primary'][0].update(gross_pnl='1000000000000000001'),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                raw = fixture()
                mutate(raw)
                with self.assertRaises(InputError):
                    parse_input(raw)
