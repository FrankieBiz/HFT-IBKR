"""Bounded strict local JSON declarations for synthetic shadow sessions."""
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from quant_research.serde import InputError, _pairs, decimal_value, iso_date, strict_keys, whole

MAX_DOCUMENT = 1024 * 1024
NY = ZoneInfo('America/New_York')


def read_document(path):
    try:
        with Path(path).open('rb') as handle:
            content = handle.read(MAX_DOCUMENT + 1)
        if len(content) > MAX_DOCUMENT:
            raise InputError('JSON document exceeds 1 MiB')
        def reject(value):
            raise InputError('nonfinite JSON constant: ' + value)
        return json.loads(content.decode('utf-8'), object_pairs_hook=_pairs,
                          parse_constant=reject), content
    except (OSError, UnicodeError, ValueError, RecursionError) as error:
        raise InputError(f'cannot read strict JSON: {error}') from error


def timestamp(value, name):
    try:
        if not isinstance(value, str) or len(value) > 40 or 'T' not in value:
            raise ValueError()
        result = datetime.fromisoformat(value)
        if result.utcoffset() != timedelta(0):
            raise ValueError()
        return result
    except ValueError as error:
        raise InputError(f'{name}: explicit UTC timestamp required') from error


def parse_schedule(raw):
    strict_keys(raw, ('schema_version', 'source', 'sessions'), 'schedule')
    if type(raw['schema_version']) is not int or raw['schema_version'] != 1:
        raise InputError('unsupported schedule schema')
    if not isinstance(raw['source'], str) or not raw['source'].strip() or len(raw['source']) > 1024:
        raise InputError('bounded nonempty schedule source required')
    if not isinstance(raw['sessions'], list) or not raw['sessions']:
        raise InputError('nonempty sessions required')
    sessions = []
    for item in raw['sessions']:
        strict_keys(item, ('session', 'open_at', 'close_at'), 'session')
        day = iso_date(item['session'], 'session')
        opening = timestamp(item['open_at'], 'open_at')
        closing = timestamp(item['close_at'], 'close_at')
        if opening >= closing or any(t.astimezone(NY).date() != day for t in (opening, closing)):
            raise InputError('session window must match New York date and open before close')
        if sessions and (sessions[-1]['session'] >= day or sessions[-1]['close_at'] > opening):
            raise InputError('sessions must increase without overlap')
        sessions.append({'session': day, 'open_at': opening, 'close_at': closing})
    return {'source': raw['source'], 'sessions': tuple(sessions)}


def parse_snapshot(raw):
    strict_keys(raw, ('schema_version','mode','account','symbol','currency','execution_session',
                     'now','quote','portfolio','policy'), 'snapshot')
    if type(raw['schema_version']) is not int or raw['schema_version'] != 1:
        raise InputError('unsupported snapshot schema')
    if (raw['mode'],raw['account'],raw['symbol'],raw['currency']) != ('offline_shadow','SIM','SPY','USD'):
        raise InputError('only offline_shadow SIM/SPY/USD supported')
    result = {key: raw[key] for key in ('mode','account','symbol','currency')}
    result.update(execution_session=iso_date(raw['execution_session'],'execution_session'),
                  now=timestamp(raw['now'],'now'))
    quote = raw['quote']
    strict_keys(quote, ('bid','ask','as_of','data_type'), 'quote')
    if quote['data_type'] != 'synthetic':
        raise InputError('only synthetic quotes supported')
    result['quote'] = {key: decimal_value(quote[key],key,positive=True) for key in ('bid','ask')}
    if result['quote']['bid'] > result['quote']['ask']:
        raise InputError('crossed quote')
    result['quote'].update(as_of=timestamp(quote['as_of'],'quote as_of'),data_type='synthetic')
    portfolio = raw['portfolio']
    strict_keys(portfolio, ('cash','settled_cash','nav','peak_nav','shares','as_of','reconciled',
                            'pending_orders','uncertain_orders','halted'), 'portfolio')
    parsed = {key: decimal_value(portfolio[key],key,positive=key in ('nav','peak_nav'))
              for key in ('cash','settled_cash','nav','peak_nav')}
    if parsed['settled_cash'] > parsed['cash'] or parsed['peak_nav'] < parsed['nav']:
        raise InputError('invalid settled cash or peak NAV')
    for key in ('shares','pending_orders','uncertain_orders'):
        parsed[key] = whole(portfolio[key],key,minimum=0)
    for key in ('reconciled','halted'):
        if type(portfolio[key]) is not bool:
            raise InputError(f'{key}: strict boolean required')
        parsed[key] = portfolio[key]
    parsed['as_of'] = timestamp(portfolio['as_of'],'portfolio as_of')
    result['portfolio'] = parsed
    strict_keys(raw['policy'], ('max_quote_age_seconds','max_account_age_seconds'), 'policy')
    result['policy'] = {key: whole(value,key) for key,value in raw['policy'].items()}
    return result
