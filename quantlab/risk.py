"""Synchronous fail-closed risk gate for the offline reference simulator."""
from dataclasses import dataclass
from datetime import datetime
import math
from .config import Config


@dataclass(frozen=True)
class Snapshot:
    cash: float
    positions: dict[str, int]
    marks: dict[str, tuple[float, datetime]]

    def equity(self) -> float:
        return self.cash + sum(q * self.marks[s][0] for s, q in self.positions.items() if q)


class RiskGate:
    def __init__(self, config: Config):
        self.config = config
        self.state = 'RECOVERING'
        self.reason = 'initial reconciliation required'
        self.ids: set[str] = set()
        self.peak = config.initial_cash
        self.day = None
        self.day_start = config.initial_cash
        self.last_equity = config.initial_cash

    def halt(self, reason: str):
        self.state, self.reason = 'HALTED', reason

    def begin_recovery(self):
        self.state, self.reason = 'RECOVERING', 'explicit recovery requested'

    def reconcile(self, local_positions: dict, remote_positions: dict, local_orders: list, remote_orders: list) -> bool:
        if self.state != 'RECOVERING':
            return False
        # Snapshot equality is necessary, never automatic authorization to clear loss limits.
        if local_positions != remote_positions or sorted(local_orders) != sorted(remote_orders):
            self.reason = 'snapshot mismatch'
            return False
        if any(type(q) is not int or q < 0 for q in local_positions.values()):
            self.reason = 'invalid snapshot'
            return False
        self.state, self.reason = 'READY', ''
        return True

    def observe(self, snapshot: Snapshot, now: datetime):
        try:
            equity = snapshot.equity()
        except KeyError:
            self.halt('missing portfolio mark')
            return
        if not math.isfinite(equity) or equity <= 0:
            self.halt('invalid equity')
            return
        if self.day != now.date():
            self.day, self.day_start = now.date(), self.last_equity
        self.last_equity = equity
        self.peak = max(self.peak, equity)
        if equity <= self.day_start * (1 - self.config.limits.max_daily_loss_fraction):
            self.halt('daily loss limit')
        elif equity <= self.peak * (1 - self.config.limits.max_drawdown_fraction):
            self.halt('drawdown limit')

    def check(self, order_id: str, symbol: str, quantity: int, price: float, fee: float,
              snapshot: Snapshot, now: datetime) -> str | None:
        if self.state != 'READY':
            return 'not ready'
        if not order_id or order_id in self.ids:
            return 'duplicate order id'
        # All intents, including rejected ones, are consumed. Retrying requires a new ID.
        self.ids.add(order_id)
        limits = self.config.limits
        if type(quantity) is not int or quantity == 0 or abs(quantity) > limits.max_order_quantity:
            return 'order size limit'
        if not all(math.isfinite(v) for v in (price, fee, snapshot.cash)) or price <= 0 or fee < 0:
            return 'invalid monetary value'
        for item in set(snapshot.positions) | {symbol}:
            if item not in self.config.sectors:
                return 'missing sector classification'
            mark = snapshot.marks.get(item)
            if mark is None:
                return 'missing or stale mark'
            age = (now - mark[1]).total_seconds()
            if not math.isfinite(mark[0]) or mark[0] <= 0 or age < 0 or age > limits.max_mark_age_seconds:
                return 'missing or stale mark'
        positions = dict(snapshot.positions)
        positions[symbol] = positions.get(symbol, 0) + quantity
        if any(type(q) is not int or q < 0 for q in positions.values()):
            return 'short positions disabled'
        cash = snapshot.cash - quantity * price - fee
        if cash < 0:
            return 'insufficient cash'
        # Use the more conservative mark for a proposed purchase.
        exposure = {s: q * (max(snapshot.marks[s][0], price) if s == symbol else snapshot.marks[s][0])
                    for s, q in positions.items()}
        if exposure[symbol] > limits.max_symbol_notional:
            return 'symbol exposure limit'
        if sum(exposure.values()) > min(limits.max_gross_notional, limits.max_net_notional):
            return 'portfolio exposure limit'
        sectors: dict[str, float] = {}
        for s, value in exposure.items():
            sector = self.config.sectors[s]
            sectors[sector] = sectors.get(sector, 0) + value
        if max(sectors.values(), default=0) > limits.max_sector_notional:
            return 'sector exposure limit'
        return None
