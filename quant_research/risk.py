"""Independent simulated admission. Halts never imply a position is flat."""

from dataclasses import dataclass
from decimal import Decimal

from .costs import FillEstimate, estimate_fill
from .serde import InputError, fixed_decimal, whole


@dataclass(frozen=True)
class Admission:
    accepted: bool
    reason: str
    estimate: FillEstimate | None = None


@dataclass(frozen=True)
class Sizing:
    quantity: int
    reason: str


@dataclass(frozen=True)
class DrawdownState:
    peak: Decimal
    maximum: Decimal
    halted: bool

    @fixed_decimal
    def mark(self, nav, threshold):
        if not nav.is_finite() or nav < 0 or self.peak <= 0:
            raise InputError('invalid portfolio mark')
        peak = max(self.peak, nav)
        decline = (peak - nav) / peak
        return DrawdownState(peak, max(self.maximum, decline), self.halted or decline >= threshold)


@fixed_decimal
def admit(*, side, quantity, cash, shares, nav, open_price, previous_volume,
          config, multiplier, halted):
    if config.mode != 'simulation' or config.symbol != 'SPY':
        return Admission(False, 'UNSUPPORTED_MODE')
    whole(quantity, 'quantity')
    whole(shares, 'shares', minimum=0)
    whole(previous_volume, 'previous volume')
    for amount in (cash, nav):
        if not isinstance(amount, Decimal) or not amount.is_finite() or amount < 0:
            raise InputError('cash and NAV must be finite nonnegative Decimals')
    if side == 'BUY' and halted:
        return Admission(False, 'HALTED')
    estimate = estimate_fill(side, quantity, open_price, config.costs, multiplier)
    if quantity > int(previous_volume * config.participation_limit):
        return Admission(False, 'CAPACITY_LIMIT')
    if estimate.notional > config.max_order_notional:
        return Admission(False, 'ORDER_NOTIONAL_LIMIT')
    if side == 'SELL':
        if quantity > shares:
            return Admission(False, 'INVENTORY_LIMIT')
        if estimate.notional <= estimate.fees:
            return Admission(False, 'NONPOSITIVE_PROCEEDS')
    else:
        if shares + quantity > config.max_shares:
            return Admission(False, 'SHARE_LIMIT')
        if estimate.notional + estimate.fees > cash:
            return Admission(False, 'CASH_LIMIT')
        if shares * open_price + estimate.notional > nav * config.max_position_fraction:
            return Admission(False, 'EXPOSURE_LIMIT')
    return Admission(True, 'ACCEPTED', estimate)


@fixed_decimal
def size_entry(desired, cash, nav, open_price, previous_volume, config, multiplier, halted):
    whole(desired, 'desired shares', minimum=0)
    if desired == 0:
        return Sizing(0, 'BELOW_ONE_SHARE')
    if halted:
        return Sizing(0, 'HALTED')
    # All buy limits are monotone in size; binary search avoids per-share loops.
    low, high = 0, min(desired, config.max_shares, int(previous_volume * config.participation_limit))
    while low < high:
        candidate = (low + high + 1) // 2
        decision = admit(side='BUY', quantity=candidate, cash=cash, shares=0,
                         nav=nav, open_price=open_price, previous_volume=previous_volume,
                         config=config, multiplier=multiplier, halted=halted)
        if decision.accepted:
            low = candidate
        else:
            high = candidate - 1
    if low:
        return Sizing(low, 'ACCEPTED' if low == desired else 'REDUCED_TO_LIMITS')
    reason = admit(side='BUY', quantity=1, cash=cash, shares=0, nav=nav,
                   open_price=open_price, previous_volume=previous_volume,
                   config=config, multiplier=multiplier, halted=halted).reason
    return Sizing(0, reason)
