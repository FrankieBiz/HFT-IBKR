"""Continuous cost estimates and analytic break-even; not an execution simulator."""

from decimal import Decimal, localcontext
from fractions import Fraction
from math import ceil

from quant_research.serde import fixed_decimal

ZERO = Fraction(0)

ASSUMPTIONS = [
    'Conditional sensitivity only: no measured forecast, fill probability, latency or market edge.',
    'All costs, calendar coverage, capital and evidence labels are unverified input declarations.',
    'One fully filled buy and sell order per round trip; no partial fills, retries or order replacement.',
    'Continuous fees: no invoice rounding, rebates, volume-tier changes or undocumented charges.',
    'Each side crosses half its own full spread; slippage and impact are additional adverse dollars/share.',
    'Analysis movement increment is a reporting resolution, not an exchange tick-size declaration.',
    'Exact rational decisions; reported nonterminating amounts round to 80 significant decimal digits.',
    'Full declared monthly bill is allocated over every supplied scheduled session, including zero-trade days.',
    'Funding bound reserves entry outlay and any zero-movement exit-fee deficit; sale proceeds are not reused.',
    'Constant-price funding bound is not a pathwise settlement, liquidity, loss-limit or execution guarantee.',
    'Startup costs are separate; no taxes, cash yield, price-path risk or opportunity-cost model.',
    'G0 remains unresolved: licensed feed semantics, calibrated costs/delays, account eligibility and risk policy required.',
]


def _fee(schedule, quantity, price):
    commission = min(max(quantity * schedule.per_share, schedule.minimum),
                     quantity * price * schedule.cap_fraction)
    return (commission + schedule.external_per_order + quantity * schedule.external_per_share
            + quantity * price * schedule.external_fraction)


def _break_even(config, quantity, entry_outlay, exit_drag, overhead):
    """Solve the cap and flat commission regimes, then round movement upward."""
    fee = config.sell_fee
    base = max(quantity * fee.per_share, fee.minimum)
    constant = entry_outlay + fee.external_per_order + quantity * fee.external_per_share + overhead
    capped_price = constant / (quantity * (1 - fee.external_fraction - fee.cap_fraction))
    if quantity * capped_price * fee.cap_fraction <= base:
        exit_price = capped_price
    else:
        exit_price = (constant + base) / (quantity * (1 - fee.external_fraction))
    movement = max(ZERO, exit_price + exit_drag - config.reference_mid)
    increment = config.movement_increment
    return ceil(movement / increment) * increment


def _row(config, scenario, quantity, trips, daily_cost):
    entry_price = (config.reference_mid + scenario.entry_spread / 2
                   + scenario.entry_slippage + scenario.entry_impact)
    exit_drag = scenario.exit_spread / 2 + scenario.exit_slippage + scenario.exit_impact
    exit_zero = config.reference_mid - exit_drag
    entry_notional = quantity * entry_price
    buy_fee = _fee(config.buy_fee, quantity, entry_price)
    entry_outlay = entry_notional + buy_fee
    sell_zero_fee = _fee(config.sell_fee, quantity, exit_zero)
    deficit = max(ZERO, sell_zero_fee - quantity * exit_zero)
    available = max(ZERO, config.settled_cash - config.cash_buffer - daily_cost)
    funding_per_trip = entry_outlay + deficit
    funding_bound = int(available // funding_per_trip)
    failures = []
    if config.settled_cash < config.cash_buffer + daily_cost:
        failures.append('cash_buffer_and_overhead')
    if trips and entry_notional > config.max_entry_notional:
        failures.append('entry_notional_limit')
    if trips > funding_bound:
        failures.append('settled_cash_turnover')
    variable_move = _break_even(config, quantity, entry_outlay, exit_drag, ZERO)
    required = (_break_even(config, quantity, entry_outlay, exit_drag, daily_cost / trips)
                if trips else None)

    def daily_net(move):
        exit_price = config.reference_mid + move - exit_drag
        return trips * (quantity * exit_price - _fee(config.sell_fee, quantity, exit_price)
                        - entry_outlay) - daily_cost

    return {
        'scenario': scenario.name, 'quantity': quantity, 'round_trips_per_session': trips,
        'constraint_status': 'infeasible' if failures else 'within_declared_bounds',
        'constraint_failures': failures, 'entry_price': entry_price,
        'entry_notional': entry_notional, 'entry_fee': buy_fee, 'entry_outlay': entry_outlay,
        'zero_move_exit_fee': sell_zero_fee, 'zero_move_exit_deficit_reserve': deficit,
        'funding_reserved_per_trip': funding_per_trip,
        'available_for_entries': available, 'constant_price_funding_bound': funding_bound,
        'zero_move_variable_cost_per_trip': entry_outlay + sell_zero_fee - quantity * exit_zero,
        'zero_move_daily_net': daily_net(ZERO),
        'variable_only_mid_move': variable_move,
        'variable_only_exit_fee': _fee(config.sell_fee, quantity,
                                      config.reference_mid + variable_move - exit_drag),
        'variable_only_net_per_trip': (
            quantity * (config.reference_mid + variable_move - exit_drag)
            - _fee(config.sell_fee, quantity, config.reference_mid + variable_move - exit_drag)
            - entry_outlay),
        'required_mid_move': required,
        'required_mid_move_bps': required / config.reference_mid * 10000 if trips else None,
        'exit_fee_at_required_move': _fee(config.sell_fee, quantity,
                                        config.reference_mid + required - exit_drag) if trips else None,
        'daily_net_at_required_move': daily_net(required) if trips else None,
        'daily_net_one_increment_lower': daily_net(required - config.movement_increment)
        if trips and required >= config.movement_increment else None,
    }


@fixed_decimal
def assess(config):
    # All financial branches and grid rounding use exact Fractions. Decimal is
    # only the serialization boundary, so ambient precision cannot change risk.
    daily_cost = config.monthly_recurring_cost / config.session_count
    report = {
        'schema_version': 1, 'status': 'conditional_analysis', 'g0_complete': False,
        'evidence': config.evidence, 'daily_recurring_cost': daily_cost,
        'startup_cost_separate': config.startup_cost,
        'do_not_operate_daily_net': ZERO, 'assumptions': list(ASSUMPTIONS),
        'rows': [_row(config, scenario, quantity, trips, daily_cost)
                 for scenario in config.scenarios for quantity in config.quantities
                 for trips in config.round_trips_per_session],
    }
    with localcontext() as context:
        # Accepted inputs: at most 18 integer/12 fractional digits, Q <= 1e6,
        # fee slope < 1 with a minimum 1e-12 gap. 80 digits preserve terminating
        # amount/grid outputs even at the extremes; recurring rational amounts
        # are rounded for display only, never fed back into calculations.
        context.prec = 80
        return _decimal_report(report)


def _decimal_report(value):
    if isinstance(value, Fraction):
        return Decimal(value.numerator) / Decimal(value.denominator)
    if isinstance(value, dict):
        return {key: _decimal_report(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decimal_report(item) for item in value]
    return value
