import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from quantlab.data import Bar
from quantlab.config import Config, Costs, Limits
from quantlab.risk import RiskGate, Snapshot
from quantlab.simulation import simulate

START = datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc)
def bar(i, price=100, volume=1000, symbol='DEMO'):
    return Bar(START + timedelta(minutes=i), symbol, price, price, price, price, volume)

class BuyOnce:
    def target(self, history, position):
        return 10

class SimulationTests(unittest.TestCase):
    def config(self, **kwargs):
        return Config(costs=Costs(commission_per_share=0, minimum_commission=0, fee_bps=0,
                                  spread_bps=0, slippage_bps=0, impact_bps=0), **kwargs)

    def test_next_bar_fill_and_cash_conservation(self):
        result = simulate([bar(0), bar(1, 101), bar(2, 102)], self.config(), BuyOnce())
        self.assertEqual(result['fills'][0]['timestamp'], (START + timedelta(minutes=2)).isoformat())
        self.assertEqual(result['fills'][0]['price'], 101)
        self.assertEqual(result['summary']['equity'], 100010)
        self.assertEqual(result['summary']['cash'], 98990)
        self.assertEqual(result['summary']['positions'], {'DEMO': 10})

    def test_volume_cap_and_no_fill_at_zero_volume(self):
        result = simulate([bar(0), bar(1, volume=0), bar(2, volume=20)], self.config(), BuyOnce())
        self.assertEqual(len(result['fills']), 1)
        self.assertEqual(result['fills'][0]['quantity'], 2)

    def test_costs_reduce_equity(self):
        result = simulate([bar(0), bar(1)], Config(), BuyOnce())
        self.assertLess(result['summary']['equity'], 100000)
        self.assertGreater(result['summary']['total_cost'], 0)

    def test_jump_halts_and_cancels_pending(self):
        result = simulate([bar(0), bar(1, 130), bar(2, 100)], self.config(), BuyOnce())
        self.assertEqual(result['summary']['state'], 'HALTED')
        self.assertEqual(result['fills'], [])

    def test_missing_sector_rejected(self):
        result = simulate([bar(0, symbol='OTHER'), bar(1, symbol='OTHER')], self.config(), BuyOnce())
        self.assertEqual(result['fills'], [])
        self.assertTrue(any('sector' in event.get('reason', '') for event in result['events']))

    def test_bad_mode_limits_and_costs_rejected(self):
        for factory in [lambda: Config(mode='live'), lambda: Costs(spread_bps=float('nan')),
                        lambda: Limits(max_participation=1.1), lambda: Config(initial_cash=-1)]:
            with self.assertRaises(ValueError):
                factory()

    def test_prior_results_unchanged_by_future_bar(self):
        first = simulate([bar(0), bar(1), bar(2)], self.config(), BuyOnce())
        other = simulate([bar(0), bar(1), bar(2, 105, 1)], self.config(), BuyOnce())
        self.assertEqual(first['fills'][0], other['fills'][0])
        self.assertEqual(first['equity'][:2], other['equity'][:2])

    def test_daily_loss_latches_halt(self):
        limits = replace(Limits(), max_daily_loss_fraction=.00001)
        result = simulate([bar(0), bar(1), bar(2, 99), bar(3, 100)], self.config(limits=limits), BuyOnce())
        self.assertEqual(result['summary']['state'], 'HALTED')
        self.assertEqual(result['summary']['positions'], {'DEMO': 10})

    def test_risk_starts_closed_reconciliation_and_duplicate_ids(self):
        gate = RiskGate(self.config())
        snap = Snapshot(100000, {}, {})
        gate.observe(snap, START)
        self.assertEqual(gate.check('one', 'DEMO', 10, 100, 0, snap, START), 'not ready')
        self.assertFalse(gate.reconcile({}, {'DEMO': 1}, [], []))
        self.assertTrue(gate.reconcile({}, {}, [], []))
        self.assertEqual(gate.check('stale', 'DEMO', 10, 100, 0, snap, START), 'missing or stale mark')
        snap = Snapshot(100000, {}, {'DEMO': (100, START)})
        self.assertIsNone(gate.check('one', 'DEMO', 10, 100, 0, snap, START))
        self.assertEqual(gate.check('one', 'DEMO', 10, 100, 0, snap, START), 'duplicate order id')
        gate.halt('disconnect')
        self.assertFalse(gate.reconcile({}, {}, [], []))
        gate.begin_recovery()
        self.assertTrue(gate.reconcile({}, {}, [], []))

    def test_stale_held_position_blocks_other_symbol(self):
        config = replace(self.config(), sectors={'DEMO': 'test', 'B': 'other'})
        gate = RiskGate(config)
        gate.reconcile({}, {}, [], [])
        snap = Snapshot(99900, {'DEMO': 1}, {'DEMO': (100, START), 'B': (100, START+timedelta(minutes=9))})
        self.assertEqual(gate.check('one', 'B', 1, 100, 0, snap, START+timedelta(minutes=9)), 'missing or stale mark')

    def test_recovery_cannot_bypass_loss_limits(self):
        gate = RiskGate(self.config())
        gate.reconcile({}, {}, [], [])
        gate.observe(Snapshot(100000, {}, {}), START)
        breached = Snapshot(90000, {}, {'DEMO': (100, START)})
        gate.observe(breached, START)
        self.assertEqual(gate.state, 'HALTED')
        gate.begin_recovery()
        gate.reconcile({}, {}, [], [])
        self.assertIsNotNone(gate.check('recovered', 'DEMO', 1, 100, 0, breached, START))
        self.assertEqual(gate.state, 'HALTED')

    def test_projected_overflow_and_invalid_existing_position(self):
        gate = RiskGate(self.config())
        gate.reconcile({}, {}, [], [])
        snap = Snapshot(100000, {'DEMO': 2}, {'DEMO': (100, START)})
        self.assertIsNotNone(gate.check('overflow', 'DEMO', -2, 1e308, 0, snap, START))
        snap = Snapshot(100000, {'DEMO': True}, {'DEMO': (100, START)})
        self.assertIsNotNone(gate.check('bool', 'DEMO', 1, 100, 0, snap, START))

    def test_rejected_order_cancels_all_requested_shares(self):
        result = simulate([bar(0, symbol='OTHER'), bar(1, symbol='OTHER')], self.config(), BuyOnce())
        cancelled = [e for e in result['events'] if e['type'] == 'remainder_cancelled']
        self.assertEqual(cancelled[0]['quantity'], 10)

    def test_observation_halts_on_stale_held_mark(self):
        gate = RiskGate(self.config())
        gate.reconcile({}, {}, [], [])
        gate.observe(Snapshot(99900, {'DEMO': 1}, {'DEMO': (100, START)}), START+timedelta(minutes=5))
        self.assertEqual(gate.state, 'HALTED')

    def test_public_bars_normalize_utc(self):
        offset = timezone(timedelta(hours=5))
        value = replace(bar(0), timestamp=START.astimezone(offset))
        self.assertEqual(value.timestamp.tzinfo, timezone.utc)

    def test_projection_limits_and_cash_competition(self):
        config = replace(self.config(initial_cash=1500), sectors={'A': 'one', 'B': 'two'})
        rows = [bar(i, symbol=s) for i in range(2) for s in ('A', 'B')]
        result = simulate(rows, config, BuyOnce())
        self.assertEqual(result['summary']['positions'], {'A': 10})
        self.assertEqual(result['summary']['cash'], 500)
        for limits, expected in [(replace(Limits(), max_symbol_notional=500), 'symbol exposure limit'),
                                 (replace(Limits(), max_gross_notional=500), 'portfolio exposure limit'),
                                 (replace(Limits(), max_sector_notional=500), 'sector exposure limit')]:
            gate = RiskGate(replace(self.config(), limits=limits))
            gate.reconcile({}, {}, [], [])
            snap = Snapshot(100000, {}, {'DEMO': (100, START)})
            self.assertEqual(gate.check('one', 'DEMO', 10, 100, 0, snap, START), expected)

    def test_existing_marked_exposure_halts_without_order(self):
        config = replace(self.config(), limits=replace(Limits(), max_symbol_notional=100),
                         sectors={'A': 'one', 'B': 'two'})
        gate = RiskGate(config)
        gate.reconcile({}, {}, [], [])
        snap = Snapshot(100000, {'A': 2}, {'A': (100, START), 'B': (1, START)})
        gate.observe(snap, START)
        self.assertEqual(gate.state, 'HALTED')
        self.assertIsNotNone(gate.check('b', 'B', 1, 1, 0, snap, START))
