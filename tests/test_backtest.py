import unittest
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal, localcontext
from unittest.mock import patch

from quant_research.backtest import simulate, run_research
from quant_research.config import parse_config
from quant_research.data import Dataset
from quant_research.serde import InputError, canonical_json
from test_inputs import raw_config
from test_strategy_risk import bars_for

D = Decimal


class BacktestTests(unittest.TestCase):
    def config(self, **updates):
        raw = raw_config(target_fraction='1', max_position_fraction='1', max_drawdown='1')
        raw.update(updates)
        return parse_config(raw)

    def run_sim(self, bars, config=None, strategy='trend', start=None, multiplier=1):
        return simulate(tuple(bars), config or self.config(), start or bars[3].session,
                        strategy, multiplier)

    def test_close_signal_fills_only_next_open(self):
        bars = list(bars_for([100, 100, 110, 115, 90, 80]))
        bars[3] = replace(bars[3], open=D('120'), high=D('120'))
        result = self.run_sim(bars)
        buy, sell = result['trades']
        self.assertEqual(buy['session'], bars[3].session)
        self.assertEqual(buy['signal_session'], bars[2].session)
        self.assertEqual(buy['fill_price'], D('120'))
        self.assertEqual(buy['quantity'], 8)
        self.assertEqual(sell['session'], bars[5].session)
        self.assertEqual(sell['quantity'], 8)
        self.assertEqual(result['final']['cash'], D('680'))
        self.assertEqual(result['total_return'], D('-0.32'))
        self.assertEqual(result['maximum_drawdown'], D('0.32'))

    def test_same_close_cannot_make_entry_when_prior_signal_is_cash(self):
        bars = bars_for([100, 100, 100, 150, 160])
        result = self.run_sim(bars)
        self.assertEqual(result['trades'][0]['session'], bars[4].session)
        self.assertEqual(result['trades'][0]['signal_session'], bars[3].session)

    def test_open_positions_are_marked_not_fictitiously_liquidated(self):
        bars = bars_for([100, 100, 110, 120, 130])
        result = self.run_sim(bars)
        self.assertEqual(len(result['trades']), 1)
        self.assertEqual(result['final']['shares'], 8)
        self.assertEqual(result['final']['nav'], D('1080'))
        self.assertEqual(result['unexecuted_last_close_target'], 'LONG')

    def test_benchmark_same_evaluation_dates_and_limits(self):
        bars = bars_for([100, 100, 100, 100, 110])
        result = self.run_sim(bars, strategy='buy_hold')
        self.assertEqual(result['trades'][0]['session'], bars[3].session)
        self.assertEqual(result['evaluation_start'], bars[3].session)
        self.assertEqual(result['final']['shares'], 10)
        self.assertEqual(result['final']['nav'], D('1100'))

    def test_cost_accounting_matches_manual_buy_and_sell(self):
        bars = bars_for([100, 100, 110, 100, 90])
        raw = raw_config(target_fraction='1', max_position_fraction='1', max_drawdown='1')
        raw['costs']['minimum_commission'] = '1'
        result = self.run_sim(bars, parse_config(raw))
        self.assertEqual(result['trades'][0]['quantity'], 9)
        self.assertEqual(result['fees_paid'], D('2'))
        self.assertEqual(result['final']['cash'], D('908'))
        self.assertEqual(result['final']['shares'], 0)
        self.assertEqual(result['total_return'], D('-0.092'))

    def test_dividend_receivable_is_not_spendable_and_is_paid_later(self):
        bars = list(bars_for([100, 100, 100, 100, 90, 90, 90]))
        bars[4] = replace(bars[4], dividend=D('10'), dividend_pay_date=bars[6].session)
        result = self.run_sim(bars, strategy='buy_hold')
        self.assertEqual(result['equity_curve'][1]['receivables'], D('100'))
        self.assertEqual(result['equity_curve'][1]['nav'], D('1000'))
        self.assertEqual(result['equity_curve'][1]['cash'], D('0'))
        self.assertEqual(result['final']['cash'], D('100'))
        self.assertEqual(result['final']['receivables'], D('0'))
        self.assertEqual(result['final']['nav'], D('1000'))
        self.assertEqual(result['maximum_drawdown'], D('0'))

    def test_ex_date_purchase_has_no_dividend_entitlement(self):
        bars = list(bars_for([100, 100, 100, 90, 90]))
        bars[3] = replace(bars[3], dividend=D('10'), dividend_pay_date=bars[4].session)
        result = self.run_sim(bars, strategy='buy_hold')
        self.assertEqual(result['final']['receivables'], D('0'))
        self.assertEqual(result['final']['cash'], D('100'))
        self.assertEqual(result['final']['shares'], 10)

    def test_ex_date_sale_retains_dividend_receivable(self):
        bars = list(bars_for([100, 100, 110, 100, 90]))
        bars[4] = replace(bars[4], dividend=D('1'), dividend_pay_date=date(2025, 2, 1))
        result = self.run_sim(bars)
        self.assertEqual(result['final']['shares'], 0)
        self.assertEqual(result['final']['cash'], D('910'))
        self.assertEqual(result['final']['receivables'], D('9'))
        self.assertEqual(result['final']['nav'], D('919'))

    def test_halt_can_leave_inventory_and_still_allows_signal_exit(self):
        bars = bars_for([100, 100, 110, 120, 60, 60, 150, 160, 170])
        result = self.run_sim(bars, self.config(max_drawdown='0.2'))
        self.assertTrue(result['halted'])
        self.assertEqual([trade['side'] for trade in result['trades']], ['BUY', 'SELL'])
        self.assertEqual(result['final']['shares'], 0)
        self.assertTrue(any(row['reason'] == 'HALTED' for row in result['rejections']))

    def test_reported_drawdown_includes_open_gaps(self):
        bars = list(bars_for([100, 100, 100, 100, 100]))
        bars[4] = replace(bars[4], open=D('50'), low=D('50'))
        result = self.run_sim(bars, self.config(max_drawdown='0.2'), strategy='buy_hold')
        self.assertEqual(result['maximum_drawdown'], D('0.5'))
        self.assertTrue(result['halted'])
        self.assertEqual(result['final']['nav'], D('1000'))

    def test_prior_volume_used_and_oversized_exit_is_reported(self):
        bars = list(bars_for([100, 100, 110, 100, 90]))
        bars[3] = replace(bars[3], volume=1)
        result = self.run_sim(bars)
        self.assertEqual(len(result['trades']), 1)
        self.assertEqual(result['final']['shares'], 9)
        self.assertEqual(result['rejections'][-1]['reason'], 'CAPACITY_LIMIT')

    def test_rejected_entry_is_dropped_if_signal_reverses(self):
        bars = list(bars_for([100, 100, 110, 1, 100]))
        bars[2] = replace(bars[2], volume=1)
        result = self.run_sim(bars)
        self.assertEqual(len(result['trades']), 0)
        self.assertEqual(len(result['rejections']), 1)

    def test_benchmark_retries_affordable_entry_without_lookahead(self):
        bars = bars_for([100, 100, 100, 2000, 100, 100])
        result = self.run_sim(bars, strategy='buy_hold')
        self.assertEqual(result['trades'][0]['session'], bars[5].session)
        self.assertEqual(len(result['rejections']), 2)

    def test_lookback_start_and_strategy_validation(self):
        bars = bars_for([100, 100, 110, 120])
        for start, strategy in [(bars[2].session, 'trend'), (date(2026, 1, 1), 'trend'),
                                 (bars[3].session, 'unrecognized')]:
            with self.subTest(start=start, strategy=strategy), self.assertRaises(InputError):
                self.run_sim(bars, start=start, strategy=strategy)

    def test_stress_scenarios_and_decimal_context_are_reproducible(self):
        bars = bars_for([100, 100, 110, 120, 130])
        dataset = Dataset(bars, {'kind': 'synthetic'}, 'a' * 64, 'b' * 64)
        config = self.config()
        expected = run_research(dataset, config, bars[3].session)
        self.assertEqual([scenario['cost_multiplier'] for scenario in expected['scenarios']], [1, 2, 5])
        for scenario in expected['scenarios']:
            self.assertEqual(scenario['trend']['evaluation_start'], scenario['buy_hold']['evaluation_start'])
        with localcontext() as context:
            context.prec = 4
            self.assertEqual(canonical_json(expected), canonical_json(run_research(dataset, config, bars[3].session)))

    def test_simulation_runs_with_socket_creation_blocked(self):
        bars = bars_for([100, 100, 110, 120])
        with patch('socket.socket', side_effect=AssertionError('network forbidden')):
            self.assertEqual(len(self.run_sim(bars)['trades']), 1)

    def test_future_bars_do_not_change_previous_trades_or_marks(self):
        prefix = bars_for([100, 100, 110, 120, 90])
        suffix = tuple(replace(bar, session=bar.session + timedelta(days=5))
                       for bar in bars_for([1, 999, 10]))
        first = self.run_sim(prefix)
        full = self.run_sim(prefix + suffix)
        self.assertEqual(first['equity_curve'], full['equity_curve'][:len(first['equity_curve'])])
        self.assertEqual(first['trades'], [t for t in full['trades'] if t['session'] <= prefix[-1].session])

    def test_fee_stress_reduces_returns_in_hand_calculated_round_trip(self):
        bars = bars_for([100, 100, 110, 100, 90])
        raw = raw_config(target_fraction='1', max_position_fraction='1', max_drawdown='1')
        raw['costs']['minimum_commission'] = '1'
        config = parse_config(raw)
        results = [self.run_sim(bars, config, multiplier=m) for m in (1, 2, 5)]
        self.assertEqual([r['fees_paid'] for r in results], [D('2'), D('4'), D('10')])
        self.assertEqual([r['final']['cash'] for r in results], [D('908'), D('906'), D('900')])
