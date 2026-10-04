import unittest
from dataclasses import replace
from decimal import Decimal as D

from quant_control.domain import parse_event, validate_config
from quant_control.engine import EngineState, apply_event
from test_control_domain import control_config, event_raw, intent_raw


class Harness:
    def __init__(self, config=None):
        self.config=validate_config(config or control_config())
        self.state=EngineState.initial(self.config)
        self.sequence=0
        self.outputs=[]

    def send(self,kind,payload=None,time=0):
        self.sequence+=1
        result=apply_event(self.state,parse_event(event_raw(kind,payload,self.sequence,time)),self.config)
        self.state=result.state
        self.outputs.extend(result.outputs)
        return result.outputs

    def snapshots(self,cash='1000',quantity=0,orders=None,executions=None,as_of=0,time=0,generation=None):
        generation=generation or self.state.generation
        parts={'positions':{'account':'SIM','instrument':'SPY','quantity':quantity},
               'orders':{'orders':orders or []},'executions':{'executions':executions or []},
               'account':{'account':'SIM','currency':'USD','cash':cash,'equity':'1000','received_ms':time}}
        for component,data in parts.items():
            self.send('snapshot',{'generation':generation,'component':component,'as_of':as_of,
                                  'complete':True,'data':data},time)

    def ready(self):
        self.send('begin_reconciliation')
        self.send('quote',{'bid':'99','ask':'100','received_ms':0,'data_type':'realtime'})
        self.snapshots()
        self.send('reset',{'generation':self.state.generation})
        return self

    def fill(self,id='buy-1',execid='fill-1',quantity=2,price='99',side='BUY',broker_sequence=1,time=0):
        return self.send('fill',execution(id,execid,quantity,price,side,broker_sequence),time)


def execution(id='buy-1',execid='fill-1',quantity=2,price='99',side='BUY',broker_sequence=1):
    return {'execution_id':execid,'intent_id':id,'side':side,'quantity':quantity,
            'price':price,'broker_sequence':broker_sequence}


def snapshot_order(id='buy-1',quantity=6,filled=2,remaining=4,status='OPEN',side='BUY',price='100'):
    return {'intent_id':id,'side':side,'quantity':quantity,'limit_price':price,
            'filled_quantity':filled,'remaining_quantity':remaining,'status':status}


class ControlEngineTests(unittest.TestCase):
    def test_rejection_cannot_erase_reported_missing_fills(self):
        h=Harness().ready();h.send('intent',intent_raw())
        h.send('cancelled',{'intent_id':'buy-1','filled_quantity':3,'broker_sequence':3})
        h.send('rejected',{'intent_id':'buy-1','broker_sequence':4})
        self.assertEqual(h.state.orders[0].remaining,6)
        h.send('begin_reconciliation');h.snapshots(as_of=4)
        h.send('reset',{'generation':h.state.generation})
        self.assertNotEqual(h.state.mode,'READY')

    def test_stale_data_refresh_cannot_bypass_reconciliation(self):
        h=Harness().ready()
        h.send('intent',intent_raw(),time=101)
        self.assertEqual(h.state.mode,'HALTED')
        h.send('quote',{'bid':'99','ask':'100','received_ms':101,'data_type':'realtime'},time=101)
        h.send('account',{'cash':'1000','equity':'1000','received_ms':101,'broker_sequence':0},time=101)
        h.send('intent',intent_raw(id='refreshed'),time=101)
        self.assertFalse(h.state.decisions[-1].decision.accepted)

    def test_quote_exposure_breach_latches(self):
        h=Harness().ready();h.send('intent',intent_raw());h.fill(quantity=6)
        h.send('quote',{'bid':'399','ask':'400','received_ms':0,'data_type':'realtime'})
        self.assertEqual(h.state.mode,'HALTED')
        h.send('quote',{'bid':'99','ask':'100','received_ms':0,'data_type':'realtime'})
        h.send('intent',intent_raw(id='new',quantity=1))
        self.assertFalse(h.state.decisions[-1].decision.accepted)

    def test_conflicting_cancel_total_cannot_erase_missing_execution(self):
        h=Harness().ready();h.send('intent',intent_raw());h.fill()
        h.send('cancelled',{'intent_id':'buy-1','filled_quantity':3,'broker_sequence':3})
        h.send('cancelled',{'intent_id':'buy-1','filled_quantity':2,'broker_sequence':4})
        self.assertEqual(h.state.orders[0].remaining,4)
        self.assertEqual(h.state.orders[0].pending_terminal_quantity,3)
        h.send('begin_reconciliation')
        h.snapshots(cash='802',quantity=2,orders=[snapshot_order(filled=2,remaining=0,status='CANCELLED')],executions=[execution()],as_of=4)
        h.send('reset',{'generation':h.state.generation})
        self.assertNotEqual(h.state.mode,'READY')

    def test_execution_sequences_are_unique_but_may_arrive_out_of_order(self):
        h=Harness().ready();h.send('intent',intent_raw());h.fill(broker_sequence=2)
        h.fill(execid='other',broker_sequence=2)
        self.assertEqual(h.state.cash,D('802'))
        self.assertEqual(h.state.mode,'HALTED')
        h.fill(execid='earlier',quantity=1,broker_sequence=1)
        self.assertEqual(h.state.cash,D('703'))

    def test_cancel_timeout_retains_reservation_and_halts(self):
        h=Harness().ready()
        h.send('intent',intent_raw())
        h.send('ack',{'intent_id':'buy-1'})
        h.send('cancel',{'intent_id':'buy-1'},time=10)
        h.send('timer',time=59)
        self.assertEqual(h.state.mode,'READY')
        h.send('timer',time=60)
        self.assertEqual(h.state.mode,'HALTED')
        self.assertEqual(h.state.orders[0].status,'UNKNOWN_OUTCOME')
        self.assertEqual(h.state.orders[0].remaining,6)

    def test_account_clock_regression_and_loss_update_latch_halt(self):
        h=Harness().ready()
        h.send('account',{'cash':'1000','equity':'1000','received_ms':10,'broker_sequence':0},time=10)
        h.send('account',{'cash':'1000','equity':'1000','received_ms':5,'broker_sequence':0},time=10)
        self.assertEqual(h.state.mode,'HALTED')
        h=Harness().ready()
        h.send('account',{'cash':'1000','equity':'900','received_ms':0,'broker_sequence':0})
        self.assertEqual(h.state.mode,'HALTED')

    def test_A01_A02_complete_reconciliation_and_explicit_reset(self):
        h=Harness()
        h.send('intent',intent_raw())
        self.assertEqual(len(h.state.orders),0)
        h.send('begin_reconciliation')
        h.send('reset',{'generation':h.state.generation})
        self.assertNotEqual(h.state.mode,'READY')
        h.send('quote',{'bid':'99','ask':'100','received_ms':0,'data_type':'realtime'})
        h.snapshots()
        self.assertNotEqual(h.state.mode,'READY')
        h.send('reset',{'generation':h.state.generation})
        self.assertEqual(h.state.mode,'READY')
        self.assertEqual(h.state.cash,D('1000'))
        self.assertEqual(h.state.inventory,0)

    def test_A05_A06_reservations_idempotency_and_payload_conflicts(self):
        h=Harness().ready()
        first=h.send('intent',intent_raw())
        self.assertEqual(first[0]['type'],'submit_simulated')
        h.send('intent',intent_raw(id='buy-2'))
        self.assertEqual(h.state.decisions[-1].decision.reason,'CASH_LIMIT')
        duplicate=h.send('intent',intent_raw())
        self.assertFalse(any(o['type']=='submit_simulated' for o in duplicate))
        self.assertEqual(len(h.state.orders),1)
        h.send('intent',intent_raw(quantity=5))
        self.assertEqual(h.state.mode,'HALTED')
        self.assertIn('DUPLICATE_CONFLICT',h.state.halt_reasons)

    def test_A07_partial_duplicate_and_cancel_fill_race(self):
        h=Harness().ready()
        h.send('intent',intent_raw())
        h.send('ack',{'intent_id':'buy-1'})
        h.fill()
        self.assertEqual(h.state.cash,D('802'))
        self.assertEqual(h.state.inventory,2)
        h.fill()
        self.assertEqual(h.state.cash,D('802'))
        h.send('cancel',{'intent_id':'buy-1'})
        self.assertEqual(h.state.orders[0].remaining,4)
        h.send('cancelled',{'intent_id':'buy-1','filled_quantity':3,'broker_sequence':3})
        self.assertEqual(h.state.orders[0].remaining,4)
        h.fill(execid='fill-2',quantity=1,broker_sequence=2)
        self.assertEqual(h.state.orders[0].status,'CANCELLED')
        self.assertEqual(h.state.orders[0].remaining,0)
        self.assertEqual(h.state.cash,D('703'))

    def test_A08_unknown_submission_blocks_resubmission_after_recovery(self):
        h=Harness().ready()
        h.send('intent',intent_raw())
        h.send('timer',time=50)
        self.assertEqual(h.state.mode,'HALTED')
        self.assertEqual(h.state.orders[0].status,'UNKNOWN_OUTCOME')
        h.send('restored',{'code':1102},time=50)
        h.snapshots(time=50)
        h.send('reset',{'generation':h.state.generation},time=50)
        self.assertNotEqual(h.state.mode,'READY')
        self.assertEqual(h.state.orders[0].remaining,6)
        self.assertFalse(any(o['type']=='submit_simulated' for o in h.send('intent',intent_raw(),time=50)))

    def test_A08_missed_partial_fill_is_recovered_once(self):
        h=Harness().ready()
        h.send('intent',intent_raw())
        h.send('disconnect')
        h.send('restored',{'code':1102})
        h.snapshots(cash='802',quantity=2,orders=[snapshot_order()],executions=[execution()],as_of=1)
        h.send('reset',{'generation':h.state.generation})
        self.assertEqual(h.state.mode,'READY')
        self.assertEqual(h.state.cash,D('802'))
        self.assertEqual(h.state.orders[0].remaining,4)
        h.fill()
        self.assertEqual(h.state.cash,D('802'))

    def test_A09_subscription_recovery_differs_by_code(self):
        for code in (1101,1102):
            with self.subTest(code=code):
                h=Harness().ready()
                h.send('disconnect')
                out=h.send('restored',{'code':code})
                self.assertNotEqual(h.state.mode,'READY')
                self.assertEqual(any(o['type']=='resubscribe_simulated' for o in out),code==1101)
                if code==1101:
                    self.assertIsNone(h.state.quote)

    def test_A10_account_unsubscription_and_stale_data(self):
        h=Harness().ready()
        h.send('account_unsubscribed')
        h.send('intent',intent_raw())
        self.assertFalse(h.state.decisions[-1].decision.accepted)
        h=Harness().ready()
        h.send('intent',intent_raw(),time=101)
        self.assertFalse(h.state.decisions[-1].decision.accepted)

    def test_A11_kill_is_latched_cancel_deduplicated_and_fills_continue(self):
        h=Harness().ready()
        h.send('intent',intent_raw())
        first=h.send('kill')
        second=h.send('kill')
        self.assertEqual(sum(o['type']=='cancel_simulated' for o in first),1)
        self.assertEqual(sum(o['type']=='cancel_simulated' for o in second),0)
        h.fill()
        self.assertEqual(h.state.inventory,2)
        h.send('intent',intent_raw(id='new'))
        self.assertFalse(h.state.decisions[-1].decision.accepted)

    def test_A13_external_order_unexplained_position_and_conflicting_fill_halt(self):
        h=Harness().ready()
        h.send('begin_reconciliation')
        h.snapshots(orders=[snapshot_order(id='external')])
        self.assertEqual(h.state.mode,'HALTED')
        h=Harness()
        h.send('begin_reconciliation'); h.snapshots(quantity=1)
        self.assertEqual(h.state.mode,'HALTED')
        h=Harness().ready(); h.send('intent',intent_raw()); h.fill()
        h.fill(price='98')
        self.assertEqual(h.state.mode,'HALTED')
        self.assertEqual(h.state.cash,D('802'))

    def test_A13_fill_during_collection_invalidates_generation(self):
        h=Harness().ready(); h.send('intent',intent_raw()); h.send('begin_reconciliation')
        generation=h.state.generation
        h.fill()
        self.assertGreater(h.state.generation,generation)
        h.snapshots(generation=generation)
        self.assertNotEqual(h.state.mode,'READY')
        self.assertEqual(h.state.cash,D('802'))

    def test_A14_restart_preserves_cash_reservations_ids_and_loss_baseline(self):
        h=Harness().ready(); h.send('intent',intent_raw()); h.fill()
        h.send('restart')
        self.assertNotEqual(h.state.mode,'READY')
        self.assertEqual(h.state.cash,D('802'))
        self.assertEqual(h.state.orders[0].remaining,4)
        out=h.send('intent',intent_raw())
        self.assertFalse(any(o['type']=='submit_simulated' for o in out))
        self.assertEqual(h.config.session_start_equity,D('1000'))

    def test_no_sequence_or_clock_regression_and_no_input_state_mutation(self):
        h=Harness().ready()
        before=h.state
        event=parse_event(event_raw('intent',intent_raw(),h.sequence+1,0))
        transition=apply_event(before,event,h.config)
        self.assertEqual(len(before.orders),0)
        self.assertEqual(len(transition.state.orders),1)
        with self.assertRaises(ValueError):
            apply_event(transition.state,event,h.config)

    def test_terminal_order_cannot_regress_from_late_ack_or_overfill(self):
        h=Harness().ready(); h.send('intent',intent_raw()); h.fill(quantity=6)
        h.send('ack',{'intent_id':'buy-1'})
        self.assertEqual(h.state.orders[0].status,'FILLED')
        h.fill(execid='over',quantity=1,broker_sequence=2)
        self.assertEqual(h.state.mode,'HALTED')
        self.assertEqual(h.state.inventory,6)
