"""Pilot numerical criteria applied to declared data; never grants promotion."""

from decimal import Decimal, localcontext
from fractions import Fraction
import platform

from quant_research.serde import fixed_decimal
from .inputs import SCALE, SCENARIOS
from .statistics import BLOCK_LENGTHS, RESAMPLES, SEED, bootstrap_bound, summary

LIMITATIONS = [
    'Diagnostic only: no holdout isolation, trial registration, multiplicity correction or G0/G1 verification.',
    'Thirty sessions are a pilot; block percentile bounds may be unstable and statistical coverage is not calibrated.',
    'This is a daily-dollar percentile bootstrap, not a studentized Sharpe test or a risk-adjusted alpha estimate.',
    'Net outcomes, cost completeness, capital constraints and scheduled calendar are caller declarations.',
    'double_friction means 2x slippage/impact; commissions retain actual pricing. Aggregate input costs cannot verify this.',
    'Stress scenarios must be frozen independently, including delay tails and liquidity participation; names do not verify them.',
    'Unknown outcomes are retained; no incomplete scenario is summarized as a complete economic cohort.',
    'Drawdown measures supplied daily closes only; it does not bound intraday or future losses.',
    'Repeat diagnostics cannot award promotion or substitute for the separately controlled sealed evaluation.',
    'No-operation benchmark is zero incremental dollars; this does not establish outperformance versus SPY or cash yield.',
]


def _money(units):
    return Fraction(units, SCALE)


def _scenario(days):
    unknown = [day.session for day in days if not day.outcome_bounded]
    failures = [day.session for day in days if not day.constraints_satisfied]
    result = {
        'session_count': len(days), 'unbounded_sessions': unknown, 'constraint_failure_sessions': failures,
        'quality_notes': [{'session': day.session, 'note': day.quality_notes}
                          for day in days if day.quality_notes],
    }
    keys = ('total_gross_pnl', 'total_variable_cost', 'total_recurring_cost',
            'total_net_pnl', 'mean_daily_net_pnl', 'worst_day', 'best_day',
            'net_excluding_best_day', 'max_close_to_close_drawdown', 'losing_days', 'zero_net_days')
    if unknown:
        result.update({key: None for key in keys})
        return result, None
    values = [day.gross_pnl - day.variable_cost - day.recurring_cost for day in days]
    result.update({key: _money(value) for key, value in summary(values).items()})
    result.update({f'total_{key}': _money(sum(getattr(day, key) for day in days))
                   for key in ('gross_pnl', 'variable_cost', 'recurring_cost')})
    result.update(losing_days=sum(value < 0 for value in values),
                  zero_net_days=sum(value == 0 for value in values))
    return result, values


@fixed_decimal
def assess(data):
    scenarios, values = {}, {}
    for name in SCENARIOS:
        scenarios[name], values[name] = _scenario(data.scenarios[name])
    bounds = []
    primary = values['primary']
    if primary is not None:
        bounds = [{'block_length': length, 'role': 'primary' if length == 5 else 'sensitivity',
                   'lower_bound_daily_net_pnl': _money(bootstrap_bound(primary, length))}
                  for length in BLOCK_LENGTHS]
    failures = [f'constraint_failure:{name}' for name, scenario in scenarios.items()
                if scenario['constraint_failure_sessions']]
    unknown = [f'unbounded_outcome:{name}' for name, scenario in scenarios.items()
               if scenario['unbounded_sessions']]
    economic_failures = []
    if primary is not None and sum(primary) <= 0:
        economic_failures.append('nonpositive_primary_mean')
    economic_failures.extend(f'negative_stress_mean:{name}' for name in SCENARIOS[1:]
                             if values[name] is not None and sum(values[name]) < 0)
    uncertain = ['bootstrap_bound_not_positive'] if any(
        bound['lower_bound_daily_net_pnl'] <= 0 for bound in bounds) else []
    if failures:
        decision = 'reject'
    elif unknown:
        decision = 'inconclusive'
    elif economic_failures:
        decision = 'reject'
    elif uncertain:
        decision = 'inconclusive'
    else:
        decision = 'meets_pilot_numeric_criteria'
    report = {
        'schema_version': 1, 'status': 'diagnostic_only', 'promotion_allowed': False, 'g3_complete': False,
        'evidence_kind': data.evidence_kind, 'experiment_id': data.experiment_id,
        'candidate_id': data.candidate_id, 'numeric_assessment': decision,
        'reasons': failures + unknown + economic_failures + uncertain,
        'scheduled_sessions': list(data.scheduled_sessions), 'scenarios': scenarios,
        'bootstrap': bounds, 'do_not_operate_daily_net': _money(0), 'limitations': LIMITATIONS.copy(),
        'method': {
            'name': 'noncircular_moving_block_percentile_mean', 'resamples': RESAMPLES, 'seed': SEED,
            'block_lengths': list(BLOCK_LENGTHS), 'percentile': '0.05',
            'interpolation': '(B-1)*p; linear between adjacent sorted means',
            'rng': 'random.Random / MT19937 / randrange; fresh seed for each block length',
            'python_implementation': platform.python_implementation(), 'python_version': platform.python_version(),
            'cohort_sessions': 30, 'money_unit_usd': '0.000000000001',
        },
    }
    with localcontext() as context:
        context.prec = 80
        return _render(report)


def _render(value):
    if isinstance(value, Fraction):
        return Decimal(value.numerator) / Decimal(value.denominator)
    if isinstance(value, dict):
        return {key: _render(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_render(item) for item in value]
    return value
