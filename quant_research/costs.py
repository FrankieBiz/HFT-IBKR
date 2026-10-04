"""Transparent, uncalibrated cost scenarios for simulated fills."""

from dataclasses import dataclass
from decimal import Decimal

from .serde import InputError, fixed_decimal, whole


@dataclass(frozen=True)
class FillEstimate:
    price: Decimal
    notional: Decimal
    commission: Decimal
    exchange_fee: Decimal
    sell_fee: Decimal
    friction: Decimal

    @property
    @fixed_decimal
    def fees(self):
        return self.commission + self.exchange_fee + self.sell_fee


@fixed_decimal
def estimate_fill(side, quantity, open_price, costs, multiplier):
    whole(quantity, 'quantity')
    if side not in ('BUY', 'SELL'):
        raise InputError('unsupported side')
    if not isinstance(open_price, Decimal) or not open_price.is_finite() or open_price <= 0:
        raise InputError('open price must be a finite positive Decimal')
    if type(multiplier) is not int or multiplier not in (1, 2, 5):
        raise InputError('unsupported cost scenario multiplier')
    for value in vars(costs).values():
        if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
            raise InputError('cost assumptions must be finite nonnegative Decimals')
    adverse = (costs.half_spread_bps + costs.slippage_bps + costs.impact_bps) * multiplier / 10000
    price = open_price * (1 + adverse if side == 'BUY' else 1 - adverse)
    if price <= 0:
        raise InputError('sell fill price must be positive')
    notional = price * quantity
    return FillEstimate(
        price=price, notional=notional,
        commission=max(costs.minimum_commission, costs.commission_per_share * quantity) * multiplier,
        exchange_fee=notional * costs.exchange_fee_bps * multiplier / 10000,
        sell_fee=notional * costs.sell_fee_bps * multiplier / 10000 if side == 'SELL' else Decimal(0),
        friction=abs(price - open_price) * quantity,
    )
