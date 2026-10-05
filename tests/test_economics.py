import copy
import unittest
from decimal import Decimal, localcontext

from quant_economics.inputs import parse_config
from quant_economics.model import assess
from quant_research.serde import InputError, canonical_json


def config():
    fee = dict(per_share='0.0035', minimum='0.35', cap_fraction='0.01',
               external_per_order='0', external_per_share='0', external_fraction='0')
    return dict(
        schema_version=1, evidence='synthetic', source_notes='Invented test assumptions.',
        instrument='SPY', currency='USD', reference_mid='100', settled_cash='10000',
        cash_buffer='0', max_entry_notional='10000', quantities=[10],
        round_trips_per_session=[0, 1], scheduled_sessions=['2026-10-01', '2026-10-02'],
        calendar_notes='Two invented sessions; not an exchange calendar.',
        monthly_recurring_cost='0', startup_cost='0', movement_increment='0.0001',
        buy_fee=fee.copy(), sell_fee=fee.copy(), scenarios=[dict(
            name='base', entry_spread='0.01', exit_spread='0.01',
            entry_slippage='0', exit_slippage='0', entry_impact='0', exit_impact='0')])


def run(raw):
    return assess(parse_config(raw))


class EconomicsTests(unittest.TestCase):
    def test_hand_calculated_minimum_and_spread(self):
        report = run(config())
        row = report['rows'][1]
        # Ten shares, two $0.35 orders, $0.10 round-trip crossing cost.
        self.assertEqual(row['entry_outlay'], Decimal('1000.40'))
        self.assertEqual(row['zero_move_daily_net'], Decimal('-0.80'))
        self.assertEqual(row['required_mid_move'], Decimal('0.08'))
        self.assertEqual(row['required_mid_move_bps'], Decimal('8'))
        self.assertEqual(row['daily_net_at_required_move'], 0)
        self.assertFalse(report['g0_complete'])
        self.assertEqual(report['status'], 'conditional_analysis')

    def test_cap_below_minimum_and_external_fees_outside_cap(self):
        raw = config()
        raw.update(reference_mid='1', quantities=[1])
        for side in ('buy_fee', 'sell_fee'):
            raw[side]['external_per_order'] = '0.02'
        row = run(raw)['rows'][1]
        self.assertEqual(row['entry_fee'], Decimal('0.03005'))
        # Capped buy fee .01005 + .02; sell fee depends on its higher exit price.
        self.assertEqual(row['required_mid_move'], Decimal('0.0708'))
        self.assertGreaterEqual(row['daily_net_at_required_move'], 0)
        self.assertLess(row['daily_net_one_increment_lower'], 0)

    def test_sell_fee_cap_crosses_into_flat_regime(self):
        raw = config()
        raw.update(reference_mid='1', quantities=[1], monthly_recurring_cost='100')
        row = run(raw)['rows'][1]
        self.assertEqual(row['exit_fee_at_required_move'], Decimal('0.35'))
        self.assertEqual(row['required_mid_move'], Decimal('50.3701'))
        self.assertLess(row['daily_net_one_increment_lower'], 0)

    def test_sell_notional_fee_uses_exit_price(self):
        raw = config()
        raw['sell_fee']['external_fraction'] = '0.01'
        row = run(raw)['rows'][1]
        self.assertEqual(row['required_mid_move'], Decimal('1.0909'))
        self.assertGreater(row['exit_fee_at_required_move'], Decimal('10.35'))
        self.assertLess(row['daily_net_one_increment_lower'], 0)

    def test_fixed_cost_applies_on_zero_trade_days(self):
        raw = config()
        raw.update(monthly_recurring_cost='20', startup_cost='77')
        report = run(raw)
        zero, one = report['rows']
        self.assertEqual(report['daily_recurring_cost'], 10)
        self.assertEqual(zero['zero_move_daily_net'], -10)
        self.assertIsNone(zero['required_mid_move'])
        self.assertEqual(one['required_mid_move'], Decimal('1.08'))
        self.assertEqual(one['variable_only_mid_move'], Decimal('0.08'))
        self.assertEqual(report['do_not_operate_daily_net'], 0)
        self.assertEqual(report['startup_cost_separate'], 77)

    def test_settled_cash_not_recycled_and_exact_boundary_admitted(self):
        raw = config()
        raw.update(settled_cash='2000.80', round_trips_per_session=[2, 3])
        two, three = run(raw)['rows']
        self.assertEqual(two['constant_price_funding_bound'], 2)
        self.assertEqual(two['constraint_status'], 'within_declared_bounds')
        self.assertIn('settled_cash_turnover', three['constraint_failures'])
        raw['settled_cash'] = '2000.7999'
        self.assertEqual(run(raw)['rows'][0]['constant_price_funding_bound'], 1)

    def test_recurring_and_protected_cash_reduce_funding_bound(self):
        raw = config()
        raw.update(settled_cash='2020.80', monthly_recurring_cost='20', cash_buffer='11',
                   round_trips_per_session=[2])
        row = run(raw)['rows'][0]
        self.assertEqual(row['constant_price_funding_bound'], 1)
        self.assertEqual(row['constraint_status'], 'infeasible')

    def test_exposure_limit_includes_entry_friction(self):
        raw = config()
        raw.update(quantities=[100], round_trips_per_session=[1])
        row = run(raw)['rows'][0]
        self.assertIn('entry_notional_limit', row['constraint_failures'])
        self.assertIn('settled_cash_turnover', row['constraint_failures'])

    def test_zero_trades_needs_no_entry_capital_but_overhead_needs_funding(self):
        raw = config()
        raw.update(settled_cash='0', max_entry_notional='0', round_trips_per_session=[0])
        self.assertEqual(run(raw)['rows'][0]['constraint_status'], 'within_declared_bounds')
        raw['monthly_recurring_cost'] = '1'
        self.assertIn('cash_buffer_and_overhead', run(raw)['rows'][0]['constraint_failures'])

    def test_stress_changes_friction_without_multiplying_commissions(self):
        raw = config()
        stress = copy.deepcopy(raw['scenarios'][0])
        stress.update(name='stress', entry_slippage='0.01', exit_impact='0.02')
        raw.update(scenarios=[raw['scenarios'][0], stress], round_trips_per_session=[1])
        base, adverse = run(raw)['rows']
        self.assertEqual(adverse['required_mid_move'] - base['required_mid_move'], Decimal('.03'))
        self.assertEqual(adverse['entry_fee'], base['entry_fee'])

    def test_all_zero_costs_allow_zero_movement(self):
        raw = config()
        for side in ('buy_fee', 'sell_fee'):
            raw[side].update(per_share='0', minimum='0')
        raw['scenarios'][0].update(entry_spread='0', exit_spread='0')
        row = run(raw)['rows'][1]
        self.assertEqual(row['required_mid_move'], 0)
        self.assertIsNone(row['daily_net_one_increment_lower'])

    def test_decimal_context_does_not_change_report(self):
        expected = canonical_json(run(config()))
        with localcontext() as context:
            context.prec = 6
            self.assertEqual(canonical_json(run(config())), expected)

    def test_exit_fee_deficit_reserved_from_settled_cash(self):
        raw = config()
        raw.update(reference_mid='1', quantities=[1], settled_cash='1')
        for side in ('buy_fee', 'sell_fee'):
            raw[side].update(per_share='0', minimum='0')
        raw['sell_fee']['external_per_order'] = '5'
        raw['scenarios'][0].update(entry_spread='0', exit_spread='0')
        row = run(raw)['rows'][1]
        self.assertEqual(row['zero_move_exit_deficit_reserve'], 4)
        self.assertEqual(row['constant_price_funding_bound'], 0)
        self.assertEqual(row['required_mid_move'], 5)

    def test_exact_cap_crossover_and_zero_cap(self):
        raw = config()
        raw.update(reference_mid='34', quantities=[1], monthly_recurring_cost='0.6')
        raw['scenarios'][0].update(entry_spread='0', exit_spread='0')
        raw['buy_fee']['external_per_order'] = '0.01'
        # 34 + .35 entry fee + .30 overhead + .35 exit fee = 35.
        row = run(raw)['rows'][1]
        self.assertEqual(row['required_mid_move'], 1)
        self.assertEqual(row['daily_net_at_required_move'], 0)
        for side in ('buy_fee', 'sell_fee'):
            raw[side].update(cap_fraction='0', external_per_order='0')
        self.assertEqual(run(raw)['rows'][1]['required_mid_move'], Decimal('.3'))

    def test_non_divisible_movement_increment_rounds_up(self):
        raw = config()
        raw['movement_increment'] = '.03'
        row = run(raw)['rows'][1]
        self.assertEqual(row['required_mid_move'], Decimal('.09'))
        self.assertLess(row['daily_net_one_increment_lower'], 0)

    def test_tiny_fees_survive_large_notional_and_block_insufficient_cash(self):
        raw = config()
        raw.update(reference_mid='1e18', settled_cash='1e18', max_entry_notional='1e18',
                   quantities=[1], round_trips_per_session=[1], movement_increment='1e-12')
        raw['scenarios'][0].update(entry_spread='0', exit_spread='0')
        for side in ('buy_fee', 'sell_fee'):
            raw[side].update(per_share='1e-12', minimum='0')
        row = run(raw)['rows'][0]
        self.assertEqual(row['required_mid_move'], Decimal('2e-12'))
        self.assertEqual(row['zero_move_daily_net'], Decimal('-2e-12'))
        self.assertEqual(row['constant_price_funding_bound'], 0)
        self.assertIn('settled_cash_turnover', row['constraint_failures'])

    def test_large_funding_ratio_is_exact(self):
        raw = config()
        raw.update(reference_mid='1e-12', settled_cash='1e18', quantities=[1],
                   round_trips_per_session=[0])
        raw['scenarios'][0].update(entry_spread='0', exit_spread='0')
        for side in ('buy_fee', 'sell_fee'):
            raw[side].update(per_share='0', minimum='0')
        self.assertEqual(run(raw)['rows'][0]['constant_price_funding_bound'], 10 ** 30)

    def test_invalid_and_unresolved_inputs_fail_closed(self):
        mutations = [
            lambda c: c.pop('buy_fee'), lambda c: c.update(extra=1),
            lambda c: c.update(evidence='verified'), lambda c: c.update(schema_version=True),
            lambda c: c.update(settled_cash=None), lambda c: c.update(settled_cash='NaN'),
            lambda c: c.update(settled_cash='-1'), lambda c: c.update(quantities=[True]),
            lambda c: c.update(quantities=[1, 1]), lambda c: c.update(quantities=[]),
            lambda c: c.update(round_trips_per_session=[1, 1]),
            lambda c: c.update(round_trips_per_session=[-1]),
            lambda c: c.update(movement_increment='0'),
            lambda c: c.update(source_notes=' '),
            lambda c: c.update(scheduled_sessions=['2026-10-02', '2026-10-01']),
            lambda c: c.update(scheduled_sessions=['2026-10-01', '2026-11-01']),
            lambda c: c.update(scenarios=c['scenarios'] * 2),
            lambda c: c['buy_fee'].update(cap_fraction='0.9', external_fraction='0.1'),
            lambda c: c['scenarios'][0].update(exit_spread='200'),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                raw = config()
                mutate(raw)
                with self.assertRaises(InputError):
                    run(raw)


if __name__ == '__main__':
    unittest.main()
