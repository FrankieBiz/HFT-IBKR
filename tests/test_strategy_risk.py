import unittest
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal, localcontext

from quant_research.data import Bar
from quant_research.strategy import TrendSignal, trend_signals
from quant_research.costs import estimate_fill
from quant_research.risk import admit, size_entry, DrawdownState
from quant_research.config import parse_config
from quant_research.serde import InputError
from test_inputs import raw_config

D = Decimal


def bars_for(closes):
    return tuple(Bar(date(2025, 1, 1) + timedelta(days=i), D(str(p)), D(str(p)),
                     D(str(p)), D(str(p)), 10000, D('0'), None)
                 for i, p in enumerate(closes))


class StrategyTests(unittest.TestCase):
    def test_warmup_equality_and_trend(self):
        self.assertEqual(trend_signals(bars_for([100, 100, 100, 110, 90]), 3),
                         (TrendSignal.WARMUP, TrendSignal.WARMUP,
                          TrendSignal.CASH, TrendSignal.LONG, TrendSignal.CASH))

    def test_signal_prefix_is_invariant_to_future_prices(self):
        prefix = bars_for([100, 101, 103, 102, 105])
        long_data = prefix + tuple(replace(bar, session=bar.session + timedelta(days=5))
                                   for bar in bars_for([1, 999, 3]))
        self.assertEqual(trend_signals(prefix, 3), trend_signals(long_data, 3)[:5])

    def test_dividend_drop_does_not_create_false_price_trend(self):
        bars = list(bars_for([100, 100, 99]))
        bars[2] = replace(bars[2], dividend=D('1'), dividend_pay_date=date(2025, 1, 9))
        self.assertEqual(trend_signals(tuple(bars), 2)[-1], TrendSignal.CASH)
        rising = list(bars_for([100, 100, 99.5]))
        rising[2] = replace(rising[2], dividend=D('1'), dividend_pay_date=date(2025, 1, 9))
        self.assertEqual(trend_signals(tuple(rising), 2)[-1], TrendSignal.LONG)

    def test_ambient_decimal_precision_does_not_change_signal(self):
        bars = bars_for([100, 100.01, 100.02, 100.01])
        expected = trend_signals(bars, 3)
        with localcontext() as context:
            context.prec = 3
            self.assertEqual(expected, trend_signals(bars, 3))

    def test_flat_dividend_adjusted_tail_is_exact_sma_equality(self):
        bars = list(bars_for([100, 90, 91, 91, 91, 91]))
        bars[1] = replace(bars[1], dividend=D('1'), dividend_pay_date=date(2025, 2, 1))
        self.assertEqual(trend_signals(tuple(bars), 3)[4:],
                         (TrendSignal.CASH, TrendSignal.CASH))

    def test_invalid_lookback(self):
        for lookback in (True, 0, 1):
            with self.subTest(lookback=lookback), self.assertRaises(InputError):
                trend_signals(bars_for([100, 101]), lookback)


class CostTests(unittest.TestCase):
    def test_cost_components_and_adverse_sides(self):
        raw = raw_config()
        raw['costs'].update(half_spread_bps='1', slippage_bps='2', impact_bps='3',
                            commission_per_share='0.005', minimum_commission='1',
                            exchange_fee_bps='1', sell_fee_bps='2')
        costs = parse_config(raw).costs
        buy = estimate_fill('BUY', 10, D('100'), costs, 1)
        self.assertEqual(buy.price, D('100.06'))
        self.assertEqual(buy.commission, D('1'))
        self.assertEqual(buy.exchange_fee, D('0.10006'))
        self.assertEqual(buy.sell_fee, D('0'))
        self.assertEqual(buy.friction, D('0.6'))
        sell = estimate_fill('SELL', 10, D('100'), costs, 1)
        self.assertEqual(sell.price, D('99.94'))
        self.assertEqual(sell.sell_fee, D('0.19988'))
        self.assertEqual(estimate_fill('BUY', 10, D('100'), costs, 5).price, D('100.30'))
        self.assertEqual(estimate_fill('BUY', 10, D('100'), costs, 5).commission, D('5'))

    def test_invalid_order_inputs(self):
        costs = parse_config(raw_config()).costs
        for side, quantity, price in [('BUY', True, D('1')), ('BUY', 0, D('1')),
                                      ('SELL', 1, D('NaN')), ('SHORT', 1, D('1'))]:
            with self.subTest(side=side, quantity=quantity), self.assertRaises(InputError):
                estimate_fill(side, quantity, price, costs, 1)


class RiskTests(unittest.TestCase):
    def setUp(self):
        self.config = parse_config(raw_config(target_fraction='1', max_position_fraction='1'))

    def admission(self, **updates):
        args = dict(side='BUY', quantity=10, cash=D('1000'), shares=0, nav=D('1000'),
                    open_price=D('100'), previous_volume=10000,
                    config=self.config, multiplier=1, halted=False)
        args.update(updates)
        return admit(**args)

    def test_exact_cash_then_fee_and_gap(self):
        self.assertTrue(self.admission().accepted)
        self.assertFalse(self.admission(open_price=D('100.01')).accepted)
        costs = replace(self.config.costs, minimum_commission=D('1'))
        self.assertEqual(self.admission(config=replace(self.config, costs=costs)).reason,
                         'CASH_LIMIT')
        self.assertEqual(size_entry(10, D('1000'), D('1000'), D('101'), 10000,
                                   self.config, 1, False).quantity, 9)

    def test_fraction_and_order_caps(self):
        fraction = replace(self.config, target_fraction=D('0.8'), max_position_fraction=D('0.8'))
        self.assertEqual(self.admission(config=fraction).reason, 'EXPOSURE_LIMIT')
        self.assertEqual(size_entry(10, D('1000'), D('1000'), D('100'), 10000,
                                   fraction, 1, False).quantity, 8)
        self.assertEqual(self.admission(config=replace(self.config, max_order_notional=D('999'))).reason,
                         'ORDER_NOTIONAL_LIMIT')
        self.assertEqual(self.admission(config=replace(self.config, max_shares=9)).reason,
                         'SHARE_LIMIT')

    def test_capacity_does_not_assume_todays_volume(self):
        self.assertEqual(self.admission(previous_volume=500).reason, 'CAPACITY_LIMIT')
        self.assertEqual(size_entry(10, D('1000'), D('1000'), D('100'), 500,
                                   self.config, 1, False).quantity, 5)

    def test_halt_blocks_buys_but_allows_inventory_exit(self):
        self.assertEqual(self.admission(halted=True).reason, 'HALTED')
        self.assertTrue(self.admission(side='SELL', cash=D('0'), shares=10, halted=True).accepted)
        self.assertEqual(self.admission(side='SELL', shares=9).reason, 'INVENTORY_LIMIT')

    def test_sale_cannot_have_negative_net_proceeds(self):
        costly = replace(self.config, costs=replace(self.config.costs, minimum_commission=D('1001')))
        self.assertEqual(self.admission(side='SELL', shares=10, config=costly).reason,
                         'NONPOSITIVE_PROCEEDS')

    def test_drawdown_equality_latches_and_cannot_reset_on_recovery(self):
        state = DrawdownState(D('1000'), D('0'), False)
        state = state.mark(D('1100'), D('0.2'))
        state = state.mark(D('880'), D('0.2'))
        self.assertTrue(state.halted)
        self.assertEqual(state.maximum, D('0.2'))
        state = state.mark(D('1200'), D('0.2'))
        self.assertTrue(state.halted)
        self.assertEqual(state.maximum, D('0.2'))

    def test_risk_rejects_unsupported_mode_even_if_caller_bypasses_parser(self):
        self.assertEqual(self.admission(config=replace(self.config, mode='live')).reason,
                         'UNSUPPORTED_MODE')

class DecimalIsolationTests(unittest.TestCase):
    def test_ambient_traps_and_exponent_limits_cannot_break_replay(self):
        from decimal import Inexact, Rounded
        bars = bars_for([100, 101, 102])
        expected = trend_signals(bars, 3)
        with localcontext() as context:
            context.traps[Inexact] = True
            context.traps[Rounded] = True
            context.Emax = 1
            self.assertEqual(trend_signals(bars, 3), expected)
