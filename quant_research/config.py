"""Explicit research assumptions; these are not live account limits."""

from dataclasses import dataclass
from decimal import Decimal

from .serde import InputError, decimal_value, whole, strict_keys, fixed_decimal


@dataclass(frozen=True)
class CostConfig:
    half_spread_bps: Decimal
    slippage_bps: Decimal
    impact_bps: Decimal
    commission_per_share: Decimal
    minimum_commission: Decimal
    exchange_fee_bps: Decimal
    sell_fee_bps: Decimal


@dataclass(frozen=True)
class Config:
    schema_version: int
    mode: str
    symbol: str
    initial_cash: Decimal
    lookback: int
    target_fraction: Decimal
    max_position_fraction: Decimal
    max_shares: int
    max_order_notional: Decimal
    max_drawdown: Decimal
    participation_limit: Decimal
    costs: CostConfig


@fixed_decimal
def parse_config(raw):
    strict_keys(raw, Config.__dataclass_fields__, 'configuration')
    if type(raw['schema_version']) is not int or raw['schema_version'] != 1:
        raise InputError('unsupported configuration schema')
    if raw['mode'] != 'simulation' or raw['symbol'] != 'SPY':
        raise InputError('only offline simulation of SPY is supported')
    strict_keys(raw['costs'], CostConfig.__dataclass_fields__, 'costs')
    costs = CostConfig(**{key: decimal_value(value, key)
                          for key, value in raw['costs'].items()})
    adverse_bps = costs.half_spread_bps + costs.slippage_bps + costs.impact_bps
    if adverse_bps * 5 >= 10000:
        raise InputError('cost stress would make sell fill price nonpositive')
    values = {name: decimal_value(raw[name], name, positive=True) for name in (
        'initial_cash', 'target_fraction', 'max_position_fraction',
        'max_order_notional', 'max_drawdown', 'participation_limit')}
    if not values['target_fraction'] <= values['max_position_fraction'] <= 1:
        raise InputError('target must be <= position fraction <= 1')
    if values['max_drawdown'] > 1 or values['participation_limit'] > 1:
        raise InputError('drawdown and participation fractions must be <= 1')
    return Config(schema_version=1, mode='simulation', symbol='SPY', costs=costs,
                  lookback=whole(raw['lookback'], 'lookback', minimum=2),
                  max_shares=whole(raw['max_shares'], 'max_shares'), **values)
