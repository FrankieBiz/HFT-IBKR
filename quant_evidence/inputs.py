"""Strict aligned daily outcomes, represented as exact trillionths of a dollar."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction

from quant_research.serde import InputError, iso_date, strict_keys

SCALE = 10 ** 12
SCENARIOS = ('primary', 'double_friction', 'tail_delay', 'conservative_liquidity')


@dataclass(frozen=True)
class Day:
    session: str
    gross_pnl: int | None
    variable_cost: int | None
    recurring_cost: int | None
    outcome_bounded: bool
    constraints_satisfied: bool
    quality_notes: str


@dataclass(frozen=True)
class EvidenceInput:
    evidence_kind: str
    experiment_id: str
    candidate_id: str
    scheduled_sessions: tuple[str, ...]
    scenarios: dict[str, tuple[Day, ...]]


def _text(value, name, *, empty=False):
    if not isinstance(value, str) or len(value) > 4000 or (not empty and not value.strip()):
        raise InputError(f'{name}: expected text, nonempty unless explicitly allowed, <=4000 characters')
    return value


def _amount(value, name, *, signed=False, nullable=False):
    if value is None and nullable:
        return None
    if not isinstance(value, str) or len(value) > 64 or value.strip() != value:
        raise InputError(f'{name}: expected a bounded decimal string')
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise InputError(f'{name}: invalid decimal') from error
    if (not number.is_finite() or number.copy_abs() > Decimal('1e18')
            or (not signed and number < 0)):
        raise InputError(f'{name}: nonfinite, negative cost or out of range')
    # 1e18 with 12 trailing fractional digits has 31 significant digits.
    # Convert directly to a rational; unary Decimal arithmetic could round.
    if number.as_tuple().exponent < -12 or len(number.as_tuple().digits) > 31:
        raise InputError(f'{name}: unsupported decimal precision')
    amount = Fraction(number) * SCALE
    return amount.numerator // amount.denominator


def parse_input(raw):
    strict_keys(raw, ('schema_version', 'evidence_kind', 'experiment_id', 'candidate_id',
                      'source_notes', 'cost_notes', 'scheduled_sessions', 'scenarios'), 'evidence input')
    if type(raw['schema_version']) is not int or raw['schema_version'] != 1:
        raise InputError('schema_version: expected integer 1')
    if raw['evidence_kind'] not in ('synthetic', 'declared'):
        raise InputError('evidence_kind: expected synthetic or declared')
    for name in ('experiment_id', 'candidate_id', 'source_notes', 'cost_notes'):
        _text(raw[name], name)
    dates = raw['scheduled_sessions']
    if not isinstance(dates, list) or len(dates) != 30:
        raise InputError('scheduled_sessions: exactly 30 scheduled dates required')
    parsed = tuple(iso_date(day, 'scheduled_sessions') for day in dates)
    if tuple(sorted(set(parsed))) != parsed:
        raise InputError('scheduled_sessions: must be unique and strictly increasing')
    strict_keys(raw['scenarios'], SCENARIOS, 'scenarios')
    scenarios = {}
    for name in SCENARIOS:
        rows = raw['scenarios'][name]
        if not isinstance(rows, list) or len(rows) != len(dates):
            raise InputError(f'{name}: every scheduled session must have a row')
        days = []
        for session, row in zip(dates, rows):
            strict_keys(row, ('session', 'gross_pnl', 'variable_cost', 'recurring_cost',
                              'outcome_bounded', 'constraints_satisfied', 'quality_notes'), name + ' row')
            if row['session'] != session:
                raise InputError(f'{name}: rows must exactly match scheduled session order')
            for flag in ('outcome_bounded', 'constraints_satisfied'):
                if type(row[flag]) is not bool:
                    raise InputError(f'{name}.{flag}: expected a boolean')
            bounded = row['outcome_bounded']
            notes = _text(row['quality_notes'], 'quality_notes',
                          empty=bounded and row['constraints_satisfied'])
            days.append(Day(
                session=session, outcome_bounded=bounded,
                constraints_satisfied=row['constraints_satisfied'], quality_notes=notes,
                **{key: _amount(row[key], key, signed=key == 'gross_pnl', nullable=not bounded)
                   for key in ('gross_pnl', 'variable_cost', 'recurring_cost')},
            ))
        scenarios[name] = tuple(days)
    return EvidenceInput(raw['evidence_kind'], raw['experiment_id'], raw['candidate_id'],
                         tuple(dates), scenarios)
