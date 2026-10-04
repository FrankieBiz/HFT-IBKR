import unittest
from decimal import Decimal

from quant_control.domain import validate_config, parse_event, Intent
from quant_research.serde import InputError


def control_config(**updates):
    raw = {'schema_version': 1, 'mode': 'simulation', 'account': 'SIM',
           'instrument': 'SPY', 'currency': 'USD', 'initial_cash': '1000',
           'initial_equity': '1000', 'session_start_equity': '1000',
           'initial_inventory': 0, 'max_units': 20, 'max_order_notional': '1000',
           'max_position_notional': '2000', 'daily_loss_limit': '100',
           'max_quote_age_ms': 100, 'max_account_age_ms': 100,
           'ack_timeout_ms': 50, 'reconciliation_timeout_ms': 100}
    raw.update(updates)
    return raw


def event_raw(kind, payload=None, seq=1, time=0):
    return {'sequence': seq, 'time_ms': time, 'kind': kind, 'payload': payload or {}}


def intent_raw(id='buy-1', side='BUY', quantity=6, price='100', created=0, expires=1000):
    return {'intent_id': id, 'instrument': 'SPY', 'side': side, 'quantity': quantity,
            'limit_price': price, 'created_ms': created, 'expires_ms': expires}


class ControlDomainTests(unittest.TestCase):
    def test_explicit_simulation_baseline(self):
        config = validate_config(control_config())
        self.assertEqual(config.initial_cash, Decimal('1000'))
        self.assertEqual(config.initial_inventory, 0)

    def test_rejects_bad_modes_limits_and_baselines(self):
        for update in ({'mode':'live'}, {'mode':'paper'}, {'account':'DU123456'},
                       {'initial_inventory':1}, {'initial_cash':'NaN'},
                       {'initial_equity':'999'}, {'max_units':True},
                       {'max_quote_age_ms':-1}, {'extra':0}, {'daily_loss_limit':'0'}):
            with self.subTest(update=update), self.assertRaises(InputError):
                validate_config(control_config(**update))
        raw = control_config()
        del raw['ack_timeout_ms']
        with self.assertRaises(InputError):
            validate_config(raw)

    def test_event_is_immutable_and_serializes_original_input(self):
        raw = event_raw('intent', intent_raw())
        event = parse_event(raw)
        raw['payload']['quantity'] = 999
        self.assertEqual(event.payload['quantity'], 6)
        view = event.payload
        view['quantity'] = 555
        self.assertEqual(event.payload['quantity'], 6)
        self.assertEqual(event.raw['payload']['quantity'], 6)

    def test_rejects_unknown_fields_and_malformed_events(self):
        cases = [event_raw('intent', intent_raw(quantity=True)),
                 event_raw('intent', intent_raw(price='Infinity')),
                 event_raw('intent', intent_raw(expires=0)),
                 event_raw('mystery'), event_raw('timer', seq=True),
                 event_raw('timer', time=-1),
                 event_raw('quote', {'bid':'101','ask':'100','received_ms':0,'data_type':'realtime'}),
                 event_raw('fill', {'execution_id':'e','intent_id':'i','side':'BUY',
                     'quantity':1,'price':'0','broker_sequence':1}),
                 event_raw('snapshot', {'generation':1,'component':'missing','as_of':0,'complete':True,'data':{}})]
        for raw in cases:
            with self.subTest(raw=raw), self.assertRaises(InputError):
                parse_event(raw)

    def test_intent_typed_values_and_expiry(self):
        intent = Intent.from_raw(intent_raw())
        self.assertEqual(intent.limit_price, Decimal('100'))
        self.assertEqual(intent.quantity, 6)
