import unittest
from dataclasses import replace
from decimal import Decimal as D

from quant_control.domain import validate_config, Intent
from quant_control.risk import evaluate, RiskView, Quote, Account, Order
from test_control_domain import control_config, intent_raw


class ControlRiskTests(unittest.TestCase):
    def test_public_gate_rejects_directly_constructed_invalid_records(self):
        intents=[replace(self.intent,instrument='MES'),replace(self.intent,side='SHORT'),
                 replace(self.intent,quantity=-1),replace(self.intent,quantity=True),
                 replace(self.intent,limit_price=D('NaN'))]
        for intent in intents:
            with self.subTest(intent=intent):
                self.assertFalse(self.check(intent,replace(self.view,inventory=1)).accepted)
        for view in (replace(self.view,cash=D('NaN')),replace(self.view,inventory=-1),
                     replace(self.view,quote=replace(self.view.quote,bid=D('101'))),
                     replace(self.view,orders=(Order(self.intent,7,'OPEN',0),)),
                     replace(self.view,orders=(Order(self.intent,0,'FILLED',0),)),
                     replace(self.view,orders=(Order(self.intent,0,'UNKNOWN_OUTCOME',0),)),
                     replace(self.view,orders=(Order(self.intent,0,'CANCELLED',0,pending_terminal_quantity=3),))):
            with self.subTest(view=view):
                self.assertFalse(self.check(Intent.from_raw(intent_raw(id='candidate',quantity=1)),view=view).accepted)
        self.assertFalse(self.check(config=replace(self.config,max_units=-1)).accepted)

    def setUp(self):
        self.config = validate_config(control_config())
        self.intent = Intent.from_raw(intent_raw())
        self.view = RiskView('READY', False, D('1000'), 0,
                             Account(D('1000'), 0, True), Quote(D('99'),D('100'),0,'realtime'), ())

    def check(self, intent=None, view=None, now=0, config=None):
        return evaluate(intent or self.intent, view or self.view, config or self.config, now)

    def test_cash_reservation_prevents_double_spending(self):
        order = Order(self.intent, 0, 'PENDING_ACK', 0)
        view = replace(self.view, orders=(order,))
        self.assertTrue(self.check().accepted)
        self.assertEqual(self.check(view=view).reason,'CASH_LIMIT')
        four = Intent.from_raw(intent_raw(id='buy-2',quantity=4))
        self.assertTrue(self.check(four, view).accepted)

    def test_freshness_boundary_and_future_timestamp(self):
        self.assertTrue(self.check(now=100).accepted)
        self.assertEqual(self.check(now=101).reason,'STALE_ACCOUNT')
        view = replace(self.view, account=Account(D('1000'),101,True))
        self.assertEqual(self.check(view=view,now=100).reason,'FUTURE_ACCOUNT')
        view = replace(self.view, quote=replace(self.view.quote,received_ms=101))
        self.assertEqual(self.check(view=view,now=100).reason,'FUTURE_QUOTE')
        view = replace(self.view, account=Account(D('1000'),101,True))
        self.assertEqual(self.check(view=view,now=101).reason,'STALE_QUOTE')

    def test_expiry_and_daily_loss_equality(self):
        self.assertEqual(self.check(Intent.from_raw(intent_raw(expires=100)),now=100).reason,'EXPIRED')
        view = replace(self.view, account=Account(D('900'),0,True))
        self.assertEqual(self.check(view=view).reason,'LOSS_LIMIT')

    def test_sell_inventory_does_not_count_unfilled_buys(self):
        buy = Order(self.intent,0,'OPEN',0)
        sell = Intent.from_raw(intent_raw(id='sell',side='SELL',quantity=1))
        self.assertEqual(self.check(sell,replace(self.view,orders=(buy,))).reason,'INVENTORY_LIMIT')
        held = replace(self.view,inventory=10,orders=(Order(Intent.from_raw(intent_raw(id='s',side='SELL',quantity=7)),0,'OPEN',0),))
        self.assertTrue(self.check(Intent.from_raw(intent_raw(id='s2',side='SELL',quantity=3)),held).accepted)
        self.assertEqual(self.check(Intent.from_raw(intent_raw(id='s2',side='SELL',quantity=4)),held).reason,'INVENTORY_LIMIT')

    def test_conservative_notional_and_unit_boundaries(self):
        high = Order(Intent.from_raw(intent_raw(id='h',quantity=1,price='200')),0,'OPEN',0)
        view = replace(self.view,inventory=9,orders=(high,),cash=D('10000'))
        one = Intent.from_raw(intent_raw(id='one',quantity=1))
        self.assertEqual(self.check(one,view).reason,'POSITION_NOTIONAL_LIMIT')
        self.assertEqual(self.check(config=replace(self.config,max_units=5)).reason,'POSITION_LIMIT')
        self.assertEqual(self.check(config=replace(self.config,max_order_notional=D('599'))).reason,'ORDER_NOTIONAL_LIMIT')

    def test_bootstrap_halt_and_missing_data(self):
        for view in (replace(self.view,mode='BOOTSTRAP'), replace(self.view,halted=True),
                     replace(self.view,account=None),replace(self.view,quote=None),
                     replace(self.view,account=Account(D('1000'),0,False)),
                     replace(self.view,quote=replace(self.view.quote,data_type='delayed'))):
            with self.subTest(view=view):
                self.assertFalse(self.check(view=view).accepted)
