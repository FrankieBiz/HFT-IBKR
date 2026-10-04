"""Pure serialized order lifecycle. Every output is explicitly simulated."""

from dataclasses import dataclass, replace
from decimal import Decimal

from quant_research.serde import InputError, fixed_decimal
from .domain import Execution, Intent
from .risk import Account, Decision, Order, Quote, RiskView, evaluate


@dataclass(frozen=True)
class RecordedDecision:
    intent: Intent
    decision: Decision
    number: int


@dataclass(frozen=True)
class EngineState:
    mode: str
    halted: bool
    halt_reasons: tuple[str, ...]
    cash: Decimal
    inventory: int
    account: Account | None
    quote: Quote | None
    orders: tuple[Order, ...] = ()
    executions: tuple[Execution, ...] = ()
    decisions: tuple[RecordedDecision, ...] = ()
    generation: int = 0
    reconcile_started_ms: int | None = None
    snapshot_parts: tuple = ()
    certified_generation: int | None = None
    certified_ms: int | None = None
    baseline_cash: Decimal = Decimal(0)
    baseline_inventory: int = 0
    baseline_sequence: int = 0
    last_broker_sequence: int = 0
    last_sequence: int = 0
    last_time_ms: int = 0

    @classmethod
    def initial(cls, config):
        return cls('BOOTSTRAP',True,(),config.initial_cash,config.initial_inventory,None,None,
                   baseline_cash=config.initial_cash,baseline_inventory=config.initial_inventory)

    @property
    def view(self):
        return RiskView(self.mode,self.halted,self.cash,self.inventory,self.account,self.quote,self.orders)


@dataclass(frozen=True)
class Transition:
    state: EngineState
    outputs: tuple[dict, ...]


def halt(state, reason):
    reasons=state.halt_reasons if reason in state.halt_reasons else (*state.halt_reasons,reason)
    return replace(state,mode='HALTED',halted=True,halt_reasons=reasons,
                   certified_generation=None,certified_ms=None)


def begin(state, now):
    return replace(state,mode='RECONCILING',halted=True,generation=state.generation+1,
                   reconcile_started_ms=now,snapshot_parts=(),certified_generation=None,certified_ms=None)


def replace_order(state, order):
    orders={item.intent.intent_id:item for item in state.orders}
    orders[order.intent.intent_id]=order
    return replace(state,orders=tuple(orders[key] for key in sorted(orders)))


@fixed_decimal
def apply_execution(state, execution):
    prior=next((item for item in state.executions if item.execution_id==execution.execution_id),None)
    if prior is not None:
        return state if prior==execution else halt(state,'EXECUTION_CONFLICT')
    if any(item.broker_sequence==execution.broker_sequence for item in state.executions):
        return halt(state,'EXECUTION_SEQUENCE_CONFLICT')
    order=next((item for item in state.orders if item.intent.intent_id==execution.intent_id),None)
    if order is None:
        return halt(state,'UNKNOWN_ORDER')
    invalid=(execution.broker_sequence<=state.baseline_sequence or execution.side!=order.intent.side or
             order.status in ('FILLED','CANCELLED','REJECTED') or
             order.filled+execution.quantity>order.intent.quantity or
             (execution.side=='BUY' and execution.price>order.intent.limit_price) or
             (execution.side=='SELL' and execution.price<order.intent.limit_price))
    if invalid:
        return halt(state,'INVALID_FILL')
    cost=execution.quantity*execution.price
    cash=state.cash-cost if execution.side=='BUY' else state.cash+cost
    inventory=state.inventory+execution.quantity if execution.side=='BUY' else state.inventory-execution.quantity
    if cash<0 or inventory<0:
        return halt(state,'FILL_EXPOSURE_ERROR')
    filled=order.filled+execution.quantity
    status='FILLED' if filled==order.intent.quantity else order.status
    pending=order.pending_terminal_quantity
    if pending is not None:
        if filled>pending:
            return halt(state,'CANCEL_FILL_CONFLICT')
        if filled==pending:
            status='CANCELLED'
    order=replace(order,filled=filled,status=status)
    result=replace_order(state,order)
    return replace(result,cash=cash,inventory=inventory,
                   executions=(*state.executions,execution),
                   last_broker_sequence=max(state.last_broker_sequence,execution.broker_sequence))


@fixed_decimal
def _ready_reasons(state,config,now):
    if state.certified_generation!=state.generation or state.certified_ms is None:
        return 'RECONCILIATION_REQUIRED'
    if now-state.certified_ms>config.reconciliation_timeout_ms:
        return 'RECONCILIATION_EXPIRED'
    if state.account is None or not state.account.valid or not 0<=now-state.account.received_ms<=config.max_account_age_ms:
        return 'STALE_ACCOUNT'
    if state.quote is None or state.quote.data_type!='realtime' or not 0<=now-state.quote.received_ms<=config.max_quote_age_ms:
        return 'STALE_QUOTE'
    if config.session_start_equity-state.account.equity>=config.daily_loss_limit:
        return 'LOSS_LIMIT'
    if any(order.status=='UNKNOWN_OUTCOME' for order in state.orders):
        return 'UNKNOWN_OUTCOME'
    buys=[order for order in state.orders if order.remaining and order.intent.side=='BUY']
    exposure=state.inventory+sum(order.remaining for order in buys)
    if exposure>config.max_units:
        return 'POSITION_LIMIT'
    if exposure*max([state.quote.ask,*(order.intent.limit_price for order in buys)])>config.max_position_notional:
        return 'POSITION_NOTIONAL_LIMIT'
    if sum((order.remaining*order.intent.limit_price for order in buys),Decimal(0))>state.cash:
        return 'CASH_LIMIT'
    return None


@fixed_decimal
def apply_event(state,event,config):
    if event.sequence!=state.last_sequence+1 or event.time_ms<state.last_time_ms:
        raise InputError('control event sequence or clock regression')
    now,kind,data=event.time_ms,event.kind,event.payload
    outputs=[]
    original=state
    if state.mode=='READY':
        reason=_health_reason(state,config,now)
        if reason:
            state=halt(state,reason)
    if kind=='intent':
        intent=Intent.from_raw(data)
        prior=next((item for item in state.decisions if item.intent.intent_id==intent.intent_id),None)
        if prior is not None:
            if prior.intent!=intent:
                state=halt(state,'DUPLICATE_CONFLICT')
            else:
                outputs.append({'type':'decision_duplicate','intent_id':intent.intent_id,
                                'number':prior.number,'accepted':prior.decision.accepted,'reason':prior.decision.reason})
        else:
            decision=evaluate(intent,state.view,config,now)
            record=RecordedDecision(intent,decision,len(state.decisions)+1)
            state=replace(state,decisions=(*state.decisions,record))
            if decision.accepted:
                state=replace_order(state,Order(intent,0,'PENDING_ACK',now))
                outputs.append({'type':'submit_simulated','intent_id':intent.intent_id,
                                'number':record.number,'side':intent.side,'quantity':intent.quantity,
                                'limit_price':intent.limit_price})
            else:
                outputs.append({'type':'decision_rejected','intent_id':intent.intent_id,
                                'number':record.number,'reason':decision.reason})
                if decision.reason=='LOSS_LIMIT':
                    state=halt(state,'LOSS_LIMIT')
    elif kind=='quote':
        if data['received_ms']>now:
            state=halt(state,'FUTURE_QUOTE')
        elif state.quote is not None and data['received_ms']<state.quote.received_ms:
            state=halt(state,'QUOTE_TIME_REGRESSION')
        else:
            state=replace(state,quote=Quote(Decimal(data['bid']),Decimal(data['ask']),data['received_ms'],data['data_type']))
    elif kind=='account':
        if (data['received_ms']>now or data['broker_sequence']<state.last_broker_sequence or
                (state.account is not None and data['received_ms']<state.account.received_ms)):
            state=halt(state,'STALE_ACCOUNT_EVENT')
        else:
            valid=Decimal(data['cash'])==state.cash
            state=replace(state,account=Account(Decimal(data['equity']),data['received_ms'],valid),
                          last_broker_sequence=max(state.last_broker_sequence,data['broker_sequence']))
            if not valid:
                state=halt(state,'ACCOUNT_CASH_DISCREPANCY')
            if config.session_start_equity-state.account.equity>=config.daily_loss_limit:
                state=halt(state,'LOSS_LIMIT')
            if original.mode=='RECONCILING' and state.mode!='HALTED':
                state=begin(state,now)
    elif kind=='fill':
        execution=Execution.from_raw(data)
        state=apply_execution(state,execution)
        if original.mode=='RECONCILING' and state.mode!='HALTED' and state.executions!=original.executions:
            state=begin(state,now)
    elif kind in ('ack','cancel','cancelled','rejected'):
        order=next((item for item in state.orders if item.intent.intent_id==data['intent_id']),None)
        if order is None:
            state=halt(state,'UNKNOWN_ORDER')
        elif kind=='ack':
            if order.status=='PENDING_ACK':
                state=replace_order(state,replace(order,status='OPEN'))
        elif kind=='cancel':
            if order.remaining and not order.cancel_sent:
                state=replace_order(state,replace(order,cancel_sent=True,cancel_sent_ms=now))
                outputs.append({'type':'cancel_simulated','intent_id':order.intent.intent_id})
        else:
            state=replace(state,last_broker_sequence=max(state.last_broker_sequence,data['broker_sequence']))
            if data['broker_sequence']<=state.baseline_sequence:
                # Old status cannot contradict or regress an established snapshot.
                pass
            elif kind=='rejected':
                if order.filled or order.status=='FILLED' or order.pending_terminal_quantity is not None:
                    state=halt(state,'REJECTION_CONFLICT')
                elif order.status not in ('CANCELLED','REJECTED'):
                    state=replace_order(state,replace(order,status='REJECTED'))
            else:
                filled=data['filled_quantity']
                if (order.pending_terminal_quantity is not None and filled!=order.pending_terminal_quantity) or filled<order.filled or filled>order.intent.quantity:
                    state=halt(state,'CANCEL_FILL_CONFLICT')
                elif filled==order.filled:
                    if order.status not in ('FILLED','REJECTED'):
                        state=replace_order(state,replace(order,status='CANCELLED',pending_terminal_quantity=filled))
                else:
                    state=replace_order(state,replace(order,status='UNKNOWN_OUTCOME',pending_terminal_quantity=filled))
                    state=halt(state,'UNKNOWN_OUTCOME')
            if original.mode=='RECONCILING' and state.mode!='HALTED':
                state=begin(state,now)
    elif kind in ('begin_reconciliation','restored','restart'):
        if kind=='restart':
            state=replace(state,orders=tuple(replace(order,status='UNKNOWN_OUTCOME') if order.remaining else order for order in state.orders))
        state=begin(state,now)
        if kind=='restored' and data['code']==1101:
            state=replace(state,quote=None)
            outputs.append({'type':'resubscribe_simulated'})
        outputs.append({'type':'reconcile_simulated','generation':state.generation})
    elif kind=='disconnect':
        state=replace(state,orders=tuple(replace(order,status='UNKNOWN_OUTCOME') if order.remaining else order for order in state.orders))
        state=halt(state,'DISCONNECTED')
    elif kind=='account_unsubscribed':
        state=replace(state,account=replace(state.account,valid=False) if state.account else None)
        state=halt(state,'ACCOUNT_UNSUBSCRIBED')
    elif kind=='kill':
        state=halt(state,'KILL_SWITCH')
        orders=[]
        for order in state.orders:
            if order.remaining and not order.cancel_sent:
                order=replace(order,cancel_sent=True,cancel_sent_ms=now)
                outputs.append({'type':'cancel_simulated','intent_id':order.intent.intent_id})
            orders.append(order)
        state=replace(state,orders=tuple(orders))
    elif kind=='timer':
        timed_out=[order for order in state.orders if order.remaining and
                   ((order.status=='PENDING_ACK' and now-order.sent_ms>=config.ack_timeout_ms) or
                    (order.cancel_sent_ms is not None and now-order.cancel_sent_ms>=config.ack_timeout_ms))]
        if timed_out:
            ids={order.intent.intent_id for order in timed_out}
            state=replace(state,orders=tuple(replace(order,status='UNKNOWN_OUTCOME') if order.intent.intent_id in ids else order for order in state.orders))
            state=halt(state,'UNKNOWN_OUTCOME')
        if state.mode=='RECONCILING' and now-state.reconcile_started_ms>=config.reconciliation_timeout_ms:
            state=halt(state,'RECONCILIATION_TIMEOUT')
    elif kind=='snapshot':
        from .reconciliation import accept_snapshot
        state=accept_snapshot(state,event,config)
    elif kind=='reset':
        reason='STALE_GENERATION' if data['generation']!=state.generation else _ready_reasons(state,config,now)
        if reason:
            outputs.append({'type':'reset_rejected','reason':reason})
        else:
            state=replace(state,mode='READY',halted=False,halt_reasons=())
    else:
        raise InputError('unsupported event')
    if state.mode=='READY':
        reason=_health_reason(state,config,now)
        if reason:
            state=halt(state,reason)
    if state.halt_reasons!=original.halt_reasons and state.halt_reasons:
        outputs.append({'type':'halted','reason':state.halt_reasons[-1]})
    return Transition(replace(state,last_sequence=event.sequence,last_time_ms=now),tuple(outputs))


@fixed_decimal
def _health_reason(state,config,now):
    # Readiness is latched off when existing state loses validity. A refreshed
    # callback alone cannot substitute for reconciliation plus operator reset.
    if state.account is None or not state.account.valid or not 0<=now-state.account.received_ms<=config.max_account_age_ms:
        return 'STALE_ACCOUNT'
    if state.quote is None or state.quote.data_type!='realtime' or not 0<=now-state.quote.received_ms<=config.max_quote_age_ms:
        return 'STALE_QUOTE'
    if config.session_start_equity-state.account.equity>=config.daily_loss_limit:
        return 'LOSS_LIMIT'
    buys=[order for order in state.orders if order.remaining and order.intent.side=='BUY']
    exposure=state.inventory+sum(order.remaining for order in buys)
    if exposure>config.max_units:
        return 'POSITION_LIMIT'
    if exposure*max([state.quote.ask,*(order.intent.limit_price for order in buys)])>config.max_position_notional:
        return 'POSITION_NOTIONAL_LIMIT'
    if sum((order.remaining*order.intent.limit_price for order in buys),Decimal(0))>state.cash:
        return 'CASH_LIMIT'
    return None
