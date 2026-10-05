"""Strict, explicitly declared inputs for a bounded economic sensitivity grid."""

from dataclasses import dataclass, fields
from fractions import Fraction

from quant_research.serde import (
    InputError, decimal_value, iso_date, strict_keys, whole,
)


@dataclass(frozen=True)
class Fee:
    per_share: Fraction
    minimum: Fraction
    cap_fraction: Fraction
    external_per_order: Fraction
    external_per_share: Fraction
    external_fraction: Fraction


@dataclass(frozen=True)
class Scenario:
    name: str
    entry_spread: Fraction
    exit_spread: Fraction
    entry_slippage: Fraction
    exit_slippage: Fraction
    entry_impact: Fraction
    exit_impact: Fraction


@dataclass(frozen=True)
class EconomicsConfig:
    evidence: str
    reference_mid: Fraction
    settled_cash: Fraction
    cash_buffer: Fraction
    max_entry_notional: Fraction
    quantities: tuple[int, ...]
    round_trips_per_session: tuple[int, ...]
    session_count: int
    monthly_recurring_cost: Fraction
    startup_cost: Fraction
    movement_increment: Fraction
    buy_fee: Fee
    sell_fee: Fee
    scenarios: tuple[Scenario, ...]


def _text(value, name):
    if not isinstance(value, str) or not value.strip() or len(value) > 4000:
        raise InputError(f'{name}: expected nonempty text of at most 4000 characters')
    return value


def _list(value, name, *, maximum):
    if not isinstance(value, list) or not 1 <= len(value) <= maximum:
        raise InputError(f'{name}: expected 1 to {maximum} entries')
    return value


def _grid(value, name, *, minimum):
    result = tuple(whole(item, name, minimum=minimum)
                   for item in _list(value, name, maximum=32))
    if len(set(result)) != len(result) or max(result) > 1000000:
        raise InputError(f'{name}: duplicate entries or value above 1000000')
    return result


def _fee(raw, name):
    keys = [field.name for field in fields(Fee)]
    strict_keys(raw, keys, name)
    fee = Fee(**{key: Fraction(decimal_value(raw[key], f'{name}.{key}')) for key in keys})
    if fee.cap_fraction + fee.external_fraction >= 1:
        raise InputError(f'{name}: cap plus external fraction must be below one')
    return fee


def parse_config(raw):
    strict_keys(raw, (
        'schema_version', 'evidence', 'source_notes', 'instrument', 'currency',
        'reference_mid', 'settled_cash', 'cash_buffer', 'max_entry_notional',
        'quantities', 'round_trips_per_session', 'scheduled_sessions', 'calendar_notes',
        'monthly_recurring_cost', 'startup_cost', 'movement_increment',
        'buy_fee', 'sell_fee', 'scenarios',
    ), 'economics config')
    if type(raw['schema_version']) is not int or raw['schema_version'] != 1:
        raise InputError('schema_version: expected integer 1')
    if raw['evidence'] not in ('synthetic', 'declared'):
        raise InputError('evidence: expected synthetic or declared; neither is independently verified')
    if raw['instrument'] != 'SPY' or raw['currency'] != 'USD':
        raise InputError('only SPY / USD is supported by this study')
    for key in ('source_notes', 'calendar_notes'):
        _text(raw[key], key)
    amounts = {key: Fraction(decimal_value(raw[key], key, positive=key in (
        'reference_mid', 'movement_increment'))) for key in (
            'reference_mid', 'settled_cash', 'cash_buffer', 'max_entry_notional',
            'monthly_recurring_cost', 'startup_cost', 'movement_increment')}
    sessions = tuple(iso_date(item, 'scheduled_sessions') for item in
                     _list(raw['scheduled_sessions'], 'scheduled_sessions', maximum=31))
    if tuple(sorted(set(sessions))) != sessions:
        raise InputError('scheduled_sessions: dates must be unique and increasing')
    if any((day.year, day.month) != (sessions[0].year, sessions[0].month) for day in sessions):
        raise InputError('scheduled_sessions: supply the declared full schedule of one month')
    scenarios = []
    scenario_keys = [field.name for field in fields(Scenario)]
    for item in _list(raw['scenarios'], 'scenarios', maximum=8):
        strict_keys(item, scenario_keys, 'scenario')
        scenario = Scenario(name=_text(item['name'], 'scenario.name'), **{
            key: Fraction(decimal_value(item[key], 'scenario.' + key))
            for key in scenario_keys if key != 'name'})
        if amounts['reference_mid'] <= (
            scenario.exit_spread / 2 + scenario.exit_slippage + scenario.exit_impact
        ):
            raise InputError('scenario: zero-movement exit price must be positive')
        scenarios.append(scenario)
    if len({item.name for item in scenarios}) != len(scenarios):
        raise InputError('scenario names must be unique')
    quantities = _grid(raw['quantities'], 'quantities', minimum=1)
    trips = _grid(raw['round_trips_per_session'], 'round_trips_per_session', minimum=0)
    if len(quantities) * len(trips) * len(scenarios) > 2048:
        raise InputError('scenario grid exceeds 2048 rows')
    return EconomicsConfig(
        evidence=raw['evidence'], **amounts, quantities=quantities,
        round_trips_per_session=trips, session_count=len(sessions),
        buy_fee=_fee(raw['buy_fee'], 'buy_fee'), sell_fee=_fee(raw['sell_fee'], 'sell_fee'),
        scenarios=tuple(scenarios),
    )
