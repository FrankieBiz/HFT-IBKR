"""Strict boundaries and deterministic, bounded decimal arithmetic."""

import json
from datetime import date
from decimal import (Context, Decimal, DivisionByZero, InvalidOperation, Overflow,
                     localcontext, ROUND_HALF_EVEN)
from functools import wraps
from pathlib import Path


class InputError(ValueError):
    """A supplied dataset, configuration or output destination is invalid."""


def strict_keys(raw, keys, name):
    if not isinstance(raw, dict) or set(raw) != set(keys):
        raise InputError(f'{name}: missing or unknown fields')


def decimal_value(value, name, *, positive=False):
    if not isinstance(value, str) or len(value) > 64 or value.strip() != value:
        raise InputError(f'{name}: expected a decimal string')
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise InputError(f'{name}: invalid decimal') from error
    if not number.is_finite() or number < 0 or number > Decimal('1e18'):
        raise InputError(f'{name}: nonfinite, negative or out of range')
    if number != 0 and number < Decimal('1e-12'):
        raise InputError(f'{name}: magnitude below supported precision')
    if len(number.as_tuple().digits) > 28 or number.as_tuple().exponent < -12:
        raise InputError(f'{name}: unsupported decimal precision')
    if positive and number == 0:
        raise InputError(f'{name}: must be positive')
    return number


def whole(value, name, *, minimum=1):
    if type(value) is not int or not minimum <= value <= 10**12:
        raise InputError(f'{name}: expected a bounded whole number >= {minimum}')
    return value


def iso_date(value, name):
    if not isinstance(value, str):
        raise InputError(f'{name}: expected ISO date')
    try:
        result = date.fromisoformat(value)
    except ValueError as error:
        raise InputError(f'{name}: invalid ISO date') from error
    if result.isoformat() != value:
        raise InputError(f'{name}: expected YYYY-MM-DD')
    return result


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def read_json_document(path):
    """Return the parsed object and exactly the bytes consumed, read once."""
    try:
        content = Path(path).read_bytes()
        return json.loads(content.decode('utf-8'), object_pairs_hook=_pairs), content
    except (OSError, UnicodeError, ValueError) as error:
        raise InputError(f'cannot read JSON: {path}: {error}') from error


def read_json(path):
    return read_json_document(path)[0]


def canonical_json(value):
    def encode(item):
        if isinstance(item, Decimal):
            return format(item, 'f')
        if isinstance(item, date):
            return item.isoformat()
        raise TypeError(f'unsupported report type: {type(item)}')
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True,
                      allow_nan=False, default=encode) + '\n'


def fixed_decimal(function):
    """Prevent callers' ambient Decimal precision/rounding changing a replay."""
    @wraps(function)
    def wrapped(*args, **kwargs):
        context = Context(prec=28, rounding=ROUND_HALF_EVEN, Emin=-999999,
                          Emax=999999, capitals=1, clamp=0,
                          traps=[InvalidOperation, DivisionByZero, Overflow])
        with localcontext(context):
            return function(*args, **kwargs)
    return wrapped
