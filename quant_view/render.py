"""Normalize bounded report values; never calculate strategy signals or submit orders."""

from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import tempfile

from quant_research.serde import InputError, iso_date, read_json_document, whole
from .template import PAGE

MAX_REPORT = 32 * 1024 * 1024


def read_report(path):
    try:
        with Path(path).open('rb') as handle:
            content = handle.read(MAX_REPORT + 1)
    except OSError as error:
        raise InputError(f'cannot read report: {error}') from error
    if len(content) > MAX_REPORT:
        raise InputError('report exceeds size limit')
    with tempfile.TemporaryDirectory() as folder:
        copy = Path(folder) / 'report.json'
        copy.write_bytes(content)
        raw = read_json_document(copy)[0]
    return raw, hashlib.sha256(content).hexdigest()


def _text(value, maximum=65536):
    if not isinstance(value, str) or len(value) > maximum:
        raise InputError('invalid report text')
    return value


def _number(value):
    if (not isinstance(value, str) or len(value) > 64
            or not re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?', value)):
        raise InputError('financial value must be a bounded decimal string')
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise InputError('invalid report number') from error
    if not number.is_finite() or number.copy_abs() > Decimal('1e18'):
        raise InputError('nonfinite or unbounded report number')
    return value


def _strategy(raw):
    if not isinstance(raw, dict):
        raise InputError('strategy report missing')
    curve = raw.get('equity_curve')
    if not isinstance(curve, list) or not 1 <= len(curve) <= 100000:
        raise InputError('invalid equity curve')
    points = []
    for item in curve:
        if not isinstance(item, dict):
            raise InputError('invalid equity observation')
        date = iso_date(item.get('session'), 'curve session')
        nav = _number(item.get('nav'))
        if points and date.isoformat() <= points[-1]['session']:
            raise InputError('curve sessions must increase')
        points.append({'session': date.isoformat(), 'nav': nav})
    start = iso_date(raw.get('evaluation_start'), 'start').isoformat()
    end = iso_date(raw.get('evaluation_end'), 'end').isoformat()
    if start != points[0]['session'] or end != points[-1]['session']:
        raise InputError('curve does not match reported interval')
    result = {name: _number(raw.get(name)) for name in
              ('total_return', 'maximum_drawdown', 'modeled_execution_cost')}
    result.update({name: whole(raw.get(name), name, minimum=0) for name in ('trade_count', 'rejection_count')})
    final = raw.get('final')
    if not isinstance(final, dict):
        raise InputError('final holdings missing')
    result['final'] = {name: _number(final.get(name)) for name in ('cash', 'nav', 'receivables')}
    result['final']['shares'] = whole(final.get('shares'), 'final shares', minimum=0)
    if Decimal(result['final']['nav']) != Decimal(points[-1]['nav']):
        raise InputError('final NAV differs from curve')
    result['curve'] = points
    return result


def render_page(research, controls, *, report_sha256=None):
    try:
        if (type(research.get('schema_version')) is not int or research['schema_version'] != 1
                or research.get('mode') != 'offline_research'
                or research.get('data_kind') not in ('synthetic', 'historical')
                or research.get('strategy_validation') != 'unproven'):
            raise InputError('unsupported research report')
        scenarios = research.get('scenarios')
        if not isinstance(scenarios, list) or not 1 <= len(scenarios) <= 16:
            raise InputError('cost scenarios missing or too many')
        normalized, multipliers = [], set()
        for item in scenarios:
            raw_cost = item.get('cost_multiplier')
            cost = str(whole(raw_cost, 'cost multiplier')) if type(raw_cost) is int else _number(raw_cost)
            numeric_cost = Decimal(cost)
            if numeric_cost <= 0 or numeric_cost in multipliers:
                raise InputError('invalid or duplicate cost multiplier')
            multipliers.add(numeric_cost)
            trend, hold = [_strategy(item.get(name)) for name in ('trend', 'buy_hold')]
            if [p['session'] for p in trend['curve']] != [p['session'] for p in hold['curve']]:
                raise InputError('benchmark dates differ')
            normalized.append({'cost': cost, 'trend': trend, 'hold': hold})
        hashes = {}
        for name in ('data_sha256', 'manifest_sha256'):
            value = research.get(name)
            if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
                raise InputError('source hash missing')
            hashes[name] = value
        config = research['config']
        initial = _number(config.get('initial_cash'))
        if Decimal(initial) <= 0:
            raise InputError('initial capital must be positive')
        lookback = whole(config.get('lookback'), 'lookback', minimum=2)
        assumptions = research['assumptions']
        if not isinstance(assumptions, list) or len(assumptions) > 100:
            raise InputError('assumptions missing or too many')
        assumptions = [_text(value) for value in assumptions]
        control_rows = []
        if len(controls) > 64:
            raise InputError('too many control reports')
        for control in controls:
            if (type(control.get('schema_version')) is not int or control['schema_version'] != 1
                    or control.get('mode') != 'offline_control_replay'
                    or control.get('provenance') != 'synthetic'):
                raise InputError('unsupported control report')
            state = control['final_state']
            if state['mode'] not in ('BOOTSTRAP', 'RECONCILING', 'READY', 'HALTED'):
                raise InputError('unknown simulated control state')
            reasons = state['halt_reasons']
            if not isinstance(reasons, list) or not isinstance(state['orders'], list):
                raise InputError('malformed control state')
            control_rows.append({'id': _text(control['scenario_id'], 256), 'state': state['mode'],
                                 'reasons': [_text(value, 256) for value in reasons],
                                 'cash': _number(state['cash']),
                                 'shares': whole(state['inventory'], 'inventory', minimum=0),
                                 'orders': len(state['orders'])})
        payload = {'kind': research['data_kind'], 'initial': initial, 'lookback': lookback,
                   'source': _text(research['provenance']['source']), 'hashes': hashes,
                   'report_sha256': report_sha256, 'assumptions': assumptions,
                   'scenarios': normalized, 'controls': control_rows}
    except (KeyError, AttributeError, TypeError) as error:
        raise InputError('malformed report structure') from error
    encoded = json.dumps(payload, ensure_ascii=True, allow_nan=False)
    for char, escape in [('<', '\\u003c'), ('>', '\\u003e'), ('&', '\\u0026')]:
        encoded = encoded.replace(char, escape)
    return PAGE.replace('__REPORT_DATA__', encoded)
