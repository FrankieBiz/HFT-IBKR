"""Immutable control inputs and fail-closed schema boundaries."""

import re
from dataclasses import dataclass
from decimal import Decimal

from quant_research.serde import InputError, decimal_value, strict_keys, whole


def identifier(value, name):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value):
        raise InputError(f'{name}: invalid identifier')
    return value


def money(raw, name, positive=False):
    return decimal_value(raw, name, positive=positive)


def time_value(value, name='timestamp'):
    return whole(value, name, minimum=0)


def _freeze(value):
    if isinstance(value, dict):
        return ('dict', tuple((key, _freeze(item)) for key, item in sorted(value.items())))
    if isinstance(value, list):
        return ('list', tuple(_freeze(item) for item in value))
    return ('scalar', value)


def _thaw(value):
    tag, content = value
    if tag == 'dict':
        return {key: _thaw(item) for key, item in content}
    if tag == 'list':
        return [_thaw(item) for item in content]
    return content


@dataclass(frozen=True)
class ControlConfig:
    schema_version: int
    mode: str
    account: str
    instrument: str
    currency: str
    initial_cash: Decimal
    initial_equity: Decimal
    session_start_equity: Decimal
    initial_inventory: int
    max_units: int
    max_order_notional: Decimal
    max_position_notional: Decimal
    daily_loss_limit: Decimal
    max_quote_age_ms: int
    max_account_age_ms: int
    ack_timeout_ms: int
    reconciliation_timeout_ms: int


def validate_config(raw):
    strict_keys(raw, ControlConfig.__dataclass_fields__, 'control config')
    if type(raw['schema_version']) is not int or raw['schema_version'] != 1:
        raise InputError('invalid control schema')
    if (raw['mode'], raw['account'], raw['instrument'], raw['currency']) != ('simulation','SIM','SPY','USD'):
        raise InputError('only synthetic SIM/SPY/USD simulation is supported')
    if type(raw['initial_inventory']) is not int or raw['initial_inventory'] != 0:
        raise InputError('bootstrap inventory must be zero')
    amounts = {key: money(raw[key], key, True) for key in (
        'initial_cash','initial_equity','session_start_equity','max_order_notional',
        'max_position_notional','daily_loss_limit')}
    if amounts['initial_cash'] != amounts['initial_equity']:
        raise InputError('flat bootstrap cash and equity must agree')
    times = {key: whole(raw[key], key, minimum=0 if key.startswith('max_') else 1)
             for key in ('max_quote_age_ms','max_account_age_ms','ack_timeout_ms','reconciliation_timeout_ms')}
    return ControlConfig(schema_version=1, mode='simulation', account='SIM', instrument='SPY',
                         currency='USD', initial_inventory=0,
                         max_units=whole(raw['max_units'], 'max units'), **amounts, **times)


@dataclass(frozen=True)
class Intent:
    intent_id: str
    instrument: str
    side: str
    quantity: int
    limit_price: Decimal
    created_ms: int
    expires_ms: int

    @classmethod
    def from_raw(cls, raw):
        strict_keys(raw, cls.__dataclass_fields__, 'intent')
        if raw['side'] not in ('BUY','SELL') or raw['instrument'] != 'SPY':
            raise InputError('unsupported intent instrument/side')
        created, expires = time_value(raw['created_ms']), time_value(raw['expires_ms'])
        if expires <= created:
            raise InputError('intent expiry must follow creation')
        return cls(identifier(raw['intent_id'], 'intent id'), raw['instrument'], raw['side'],
                   whole(raw['quantity'], 'quantity'), money(raw['limit_price'], 'limit', True),
                   created, expires)


@dataclass(frozen=True)
class Execution:
    execution_id: str
    intent_id: str
    side: str
    quantity: int
    price: Decimal
    broker_sequence: int

    @classmethod
    def from_raw(cls, raw):
        strict_keys(raw, cls.__dataclass_fields__, 'execution')
        if raw['side'] not in ('BUY','SELL'):
            raise InputError('unsupported fill side')
        return cls(identifier(raw['execution_id'],'execution id'), identifier(raw['intent_id'],'intent id'),
                   raw['side'], whole(raw['quantity'],'fill quantity'), money(raw['price'],'fill price',True),
                   whole(raw['broker_sequence'],'broker sequence'))


@dataclass(frozen=True)
class Event:
    sequence: int
    time_ms: int
    kind: str
    _data: tuple

    @property
    def payload(self):
        return _thaw(self._data)

    @property
    def raw(self):
        return {'sequence':self.sequence, 'time_ms':self.time_ms, 'kind':self.kind, 'payload':self.payload}


def _validate_snapshot(raw):
    strict_keys(raw, ('generation','component','as_of','complete','data'), 'snapshot')
    whole(raw['generation'],'generation')
    time_value(raw['as_of'],'as of broker sequence')
    if type(raw['complete']) is not bool:
        raise InputError('snapshot completion must be explicit boolean')
    component, data = raw['component'], raw['data']
    if component == 'positions':
        strict_keys(data, ('account','instrument','quantity'), 'positions snapshot')
        if data['account'] != 'SIM' or data['instrument'] != 'SPY':
            raise InputError('snapshot account/instrument mismatch')
        whole(data['quantity'],'position',minimum=0)
    elif component == 'account':
        strict_keys(data, ('account','currency','cash','equity','received_ms'), 'account snapshot')
        if data['account'] != 'SIM' or data['currency'] != 'USD':
            raise InputError('snapshot account/currency mismatch')
        money(data['cash'],'cash'); money(data['equity'],'equity')
        time_value(data['received_ms'])
    elif component == 'executions':
        strict_keys(data, ('executions',), 'executions snapshot')
        if not isinstance(data['executions'],list):
            raise InputError('executions must be a list')
        executions = [Execution.from_raw(item) for item in data['executions']]
        if len({e.execution_id for e in executions}) != len(executions):
            raise InputError('duplicate snapshot execution ids')
    elif component == 'orders':
        strict_keys(data, ('orders',), 'orders snapshot')
        if not isinstance(data['orders'],list):
            raise InputError('orders must be a list')
        ids = []
        for order in data['orders']:
            strict_keys(order, ('intent_id','side','quantity','limit_price','filled_quantity',
                               'remaining_quantity','status'), 'order snapshot')
            ids.append(identifier(order['intent_id'],'intent id'))
            if order['side'] not in ('BUY','SELL') or order['status'] not in ('OPEN','FILLED','CANCELLED','REJECTED'):
                raise InputError('unknown order side/status')
            whole(order['quantity'],'order quantity')
            whole(order['filled_quantity'],'filled quantity',minimum=0)
            whole(order['remaining_quantity'],'remaining quantity',minimum=0)
            money(order['limit_price'],'limit price',True)
        if len(set(ids)) != len(ids):
            raise InputError('duplicate snapshot order ids')
    else:
        raise InputError('unknown snapshot component')


def parse_event(raw):
    strict_keys(raw, ('sequence','time_ms','kind','payload'), 'event')
    sequence, timestamp = whole(raw['sequence'],'event sequence'), time_value(raw['time_ms'])
    kind, data = raw['kind'], raw['payload']
    if not isinstance(kind,str) or not isinstance(data,dict):
        raise InputError('event kind/payload types invalid')
    if kind in ('begin_reconciliation','timer','disconnect','account_unsubscribed','kill','restart'):
        strict_keys(data, (), kind)
    elif kind == 'intent':
        Intent.from_raw(data)
    elif kind == 'fill':
        Execution.from_raw(data)
    elif kind == 'quote':
        strict_keys(data, ('bid','ask','received_ms','data_type'), 'quote')
        bid, ask = money(data['bid'],'bid',True), money(data['ask'],'ask',True)
        if bid > ask or data['data_type'] not in ('realtime','delayed'):
            raise InputError('crossed quote or unsupported data type')
        time_value(data['received_ms'])
    elif kind == 'account':
        strict_keys(data, ('cash','equity','received_ms','broker_sequence'), 'account update')
        money(data['cash'],'cash'); money(data['equity'],'equity')
        time_value(data['received_ms']); time_value(data['broker_sequence'],'broker sequence')
    elif kind in ('ack','cancel'):
        strict_keys(data, ('intent_id',), kind)
        identifier(data['intent_id'],'intent id')
    elif kind in ('cancelled','rejected'):
        keys = ('intent_id','broker_sequence','filled_quantity') if kind == 'cancelled' else ('intent_id','broker_sequence')
        strict_keys(data, keys, kind)
        identifier(data['intent_id'],'intent id'); whole(data['broker_sequence'],'broker sequence')
        if kind == 'cancelled':
            whole(data['filled_quantity'],'filled quantity',minimum=0)
    elif kind == 'reset':
        strict_keys(data, ('generation',), kind); whole(data['generation'],'generation')
    elif kind == 'restored':
        strict_keys(data, ('code',), kind)
        if type(data['code']) is not int or data['code'] not in (1101,1102):
            raise InputError('unsupported recovery code')
    elif kind == 'snapshot':
        _validate_snapshot(data)
    else:
        raise InputError('unknown control event kind')
    return Event(sequence, timestamp, kind, _freeze(data))
