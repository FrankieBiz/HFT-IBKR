"""Deterministic long-only bar simulation; all executions are synthetic."""
from __future__ import annotations

from dataclasses import asdict
from datetime import timedelta
from itertools import groupby
from .config import Config
from .data import Bar
from .risk import RiskGate, Snapshot
from .strategy import MovingAverage, Strategy


def simulate(bars: list[Bar], config: Config, strategy: Strategy | None = None) -> dict:
    if not bars:
        raise ValueError('no bars to simulate')
    keys = [(b.timestamp, b.symbol) for b in bars]
    if keys != sorted(set(keys)):
        raise ValueError('bars must be unique and chronologically ordered')
    last = {}
    for bar in bars:
        if bar.symbol in last and (bar.timestamp - last[bar.symbol]).total_seconds() < config.interval_seconds:
            raise ValueError('overlapping bars')
        last[bar.symbol] = bar.timestamp
    strategy = strategy or MovingAverage(config.fast_window, config.slow_window, config.target_quantity)
    risk = RiskGate(config)
    risk.reconcile({}, {}, [], [])
    cash = config.initial_cash
    positions: dict[str, int] = {}
    marks = {}
    history: dict[str, list[Bar]] = {}
    pending: dict[str, tuple[str, int, object]] = {}
    fills, events, equity = [], [], []
    sequence = 0
    total_cost = 0.0
    for timestamp, group in groupby(bars, lambda b: b.timestamp):
        batch = list(group)
        now = timestamp + timedelta(seconds=config.interval_seconds)
        # Mark the entire batch first so cross-symbol risk never depends on row order.
        for bar in batch:
            previous = marks.get(bar.symbol)
            if previous and abs(bar.close / previous[0] - 1) > config.limits.max_price_jump_fraction:
                risk.halt('price jump limit')
            marks[bar.symbol] = (bar.close, now)
        snapshot = Snapshot(cash, positions, marks)
        risk.observe(snapshot, now)
        for bar in batch:
            intent = pending.pop(bar.symbol, None)
            if intent is not None and risk.state == 'READY':
                order_id, requested, created = intent
                age = (timestamp - created).total_seconds()
                if age > config.limits.max_mark_age_seconds or age < 0:
                    events.append(dict(timestamp=now.isoformat(), order_id=order_id, type='expired', reason='stale intent'))
                else:
                    capacity = int(bar.volume * config.limits.max_participation)
                    quantity = min(abs(requested), capacity) * (1 if requested > 0 else -1)
                    executed = 0
                    if quantity:
                        price, fee = config.costs.execution(bar.close, quantity, bar.volume)
                        reason = risk.check(order_id, bar.symbol, quantity, price, fee, Snapshot(cash, positions, marks), now)
                        if reason:
                            events.append(dict(timestamp=now.isoformat(), type='rejected', order_id=order_id, reason=reason))
                        else:
                            executed = quantity
                            cash -= quantity * price + fee
                            positions[bar.symbol] = positions.get(bar.symbol, 0) + quantity
                            if positions[bar.symbol] == 0:
                                del positions[bar.symbol]
                            cost = abs(quantity) * abs(price - bar.close) + fee
                            total_cost += cost
                            fills.append(dict(timestamp=now.isoformat(), order_id=order_id, symbol=bar.symbol,
                                              quantity=quantity, requested=requested, price=price, reference=bar.close,
                                              fee=fee, cost=cost, participation=abs(quantity)/bar.volume))
                            risk.observe(Snapshot(cash, positions, marks), now)
                    events.append(dict(timestamp=now.isoformat(), order_id=order_id, type='remainder_cancelled',
                                       quantity=abs(requested)-abs(executed)))
            elif intent is not None:
                events.append(dict(timestamp=now.isoformat(), type='cancelled', order_id=intent[0], reason=risk.reason))
            history.setdefault(bar.symbol, []).append(bar)
        if risk.state == 'HALTED':
            for order_id, _, _ in pending.values():
                events.append(dict(timestamp=now.isoformat(), type='cancelled', order_id=order_id, reason=risk.reason))
            pending.clear()
            events.append(dict(timestamp=now.isoformat(), type='halt', reason=risk.reason))
        else:
            for bar in batch:
                target = strategy.target(tuple(history[bar.symbol]), positions.get(bar.symbol, 0))
                if type(target) is not int or target < 0:
                    raise ValueError('strategy target must be a nonnegative integer')
                quantity = target - positions.get(bar.symbol, 0)
                if quantity:
                    sequence += 1
                    order_id = f'sim-{sequence:08d}'
                    if abs(quantity) > config.limits.max_order_quantity:
                        events.append(dict(timestamp=now.isoformat(), type='rejected', order_id=order_id, reason='order size limit'))
                    else:
                        pending[bar.symbol] = (order_id, quantity, now)
                        events.append(dict(timestamp=now.isoformat(), type='intent', order_id=order_id,
                                           symbol=bar.symbol, quantity=quantity))
        value = Snapshot(cash, positions, marks).equity()
        valuation_valid = all(0 <= (now - marks[s][1]).total_seconds() <= config.limits.max_mark_age_seconds for s in positions)
        equity.append(dict(timestamp=now.isoformat(), equity=value, cash=cash, valuation_valid=valuation_valid))
    for order_id, _, _ in pending.values():
        events.append(dict(timestamp=now.isoformat(), type='cancelled', order_id=order_id, reason='end of dataset'))
    values = [config.initial_cash] + [row['equity'] for row in equity]
    peak, drawdown = values[0], 0.0
    for value in values:
        peak = max(peak, value)
        drawdown = max(drawdown, 1 - value / peak)
    return dict(schema_version=1, mode='simulation', config=asdict(config),
                assumptions=['Synthetic full subsequent-bar fills booked at bar end using close plus costs.',
                             'No queue priority, limit orders, intrabar path or calibrated impact.',
                             'Long-only cash equities; no corporate actions, borrow, leverage or exchange calendar.',
                             'Open inventory marked to last close; no forced end-of-run liquidation.',
                             'Simultaneous intents allocate cash in lexicographic symbol order.',
                             'Stale portfolio marks halt execution; flagged equity uses last observed prices.'],
                fills=fills, events=events, equity=equity,
                returns=[values[i]/values[i-1]-1 for i in range(1, len(values))],
                summary=dict(equity=values[-1], cash=cash, positions=positions,
                             total_return=values[-1]/config.initial_cash-1, max_drawdown=drawdown,
                             total_cost=total_cost, fills=len(fills), state=risk.state, halt_reason=risk.reason))
