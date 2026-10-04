"""Generation-scoped coherent snapshots; no connectivity-only readiness."""

from dataclasses import replace
from decimal import Decimal

from quant_research.serde import fixed_decimal
from .domain import Execution
from .engine import apply_execution, halt, replace_order
from .risk import Account


@fixed_decimal
def accept_snapshot(state,event,config):
    raw=event.payload
    if raw['generation']!=state.generation or state.mode!='RECONCILING':
        return state
    if event.time_ms-state.reconcile_started_ms>=config.reconciliation_timeout_ms:
        return halt(state,'RECONCILIATION_TIMEOUT')
    parts=dict(state.snapshot_parts)
    previous=parts.get(raw['component'])
    if previous is not None and previous.payload['complete'] and previous.payload!=raw:
        return halt(state,'SNAPSHOT_CONFLICT')
    parts[raw['component']]=event
    state=replace(state,snapshot_parts=tuple(sorted(parts.items())))
    if set(parts)!= {'positions','orders','executions','account'} or not all(part.payload['complete'] for part in parts.values()):
        return state
    values={name:part.payload for name,part in parts.items()}
    sequences={part['as_of'] for part in values.values()}
    if len(sequences)!=1 or min(sequences)<state.last_broker_sequence:
        return halt(state,'SNAPSHOT_SEQUENCE_CONFLICT')
    as_of=sequences.pop()
    account=values['account']['data']
    if not 0<=event.time_ms-account['received_ms']<=config.max_account_age_ms:
        return halt(state,'STALE_SNAPSHOT_ACCOUNT')
    executions=[Execution.from_raw(item) for item in values['executions']['data']['executions']]
    if any(execution.broker_sequence>as_of for execution in executions):
        return halt(state,'FUTURE_SNAPSHOT_EXECUTION')
    if len({execution.broker_sequence for execution in executions})!=len(executions):
        return halt(state,'EXECUTION_SEQUENCE_CONFLICT')
    execution_map={execution.execution_id:execution for execution in executions}
    for known in state.executions:
        if execution_map.get(known.execution_id)!=known:
            return halt(state,'MISSING_OR_CONFLICTING_EXECUTION')
    trial=state
    for execution in sorted(executions,key=lambda item:item.broker_sequence):
        trial=apply_execution(trial,execution)
        if trial.mode=='HALTED':
            return halt(state,trial.halt_reasons[-1])
    snapshot_orders={order['intent_id']:order for order in values['orders']['data']['orders']}
    local={order.intent.intent_id:order for order in trial.orders}
    if set(snapshot_orders)-set(local):
        return halt(state,'EXTERNAL_ORDER')
    for order in trial.orders:
        evidence=snapshot_orders.get(order.intent.intent_id)
        if evidence is None:
            if order.remaining or order.status=='UNKNOWN_OUTCOME' or (order.pending_terminal_quantity is not None and order.pending_terminal_quantity!=order.filled):
                return halt(state,'MISSING_ORDER_OUTCOME')
            continue
        if (evidence['side']!=order.intent.side or evidence['quantity']!=order.intent.quantity or
            Decimal(evidence['limit_price'])!=order.intent.limit_price or evidence['filled_quantity']!=order.filled):
            return halt(state,'ORDER_EVIDENCE_CONFLICT')
        status=evidence['status']
        remaining=evidence['remaining_quantity']
        if order.pending_terminal_quantity is not None and (order.filled!=order.pending_terminal_quantity or status not in ('CANCELLED','FILLED')):
            return halt(state,'CANCEL_FILL_CONFLICT')
        if status=='OPEN':
            if order.status in ('FILLED','CANCELLED','REJECTED') or remaining!=order.intent.quantity-order.filled or remaining<=0:
                return halt(state,'ORDER_EVIDENCE_CONFLICT')
        elif remaining!=0:
            return halt(state,'TERMINAL_REMAINDER_CONFLICT')
        elif status=='FILLED' and order.filled!=order.intent.quantity:
            return halt(state,'MISSING_FILL_EVIDENCE')
        elif status=='REJECTED' and order.filled!=0:
            return halt(state,'REJECTION_CONFLICT')
        elif order.status=='FILLED' and status!='FILLED':
            return halt(state,'TERMINAL_STATUS_CONFLICT')
        elif order.status in ('CANCELLED','REJECTED') and status!=order.status:
            return halt(state,'TERMINAL_STATUS_CONFLICT')
        trial=replace_order(trial,replace(order,status=status,cancel_sent=False,cancel_sent_ms=None,
                                        pending_terminal_quantity=None))
    expected_cash=state.baseline_cash
    expected_inventory=state.baseline_inventory
    for execution in executions:
        if execution.broker_sequence>state.baseline_sequence:
            signed=1 if execution.side=='BUY' else -1
            expected_cash-=signed*execution.quantity*execution.price
            expected_inventory+=signed*execution.quantity
    cash=Decimal(account['cash'])
    inventory=values['positions']['data']['quantity']
    if expected_cash!=cash or expected_inventory!=inventory or trial.cash!=cash or trial.inventory!=inventory:
        return halt(state,'ACCOUNTING_DISCREPANCY')
    return replace(trial,cash=cash,inventory=inventory,
                   account=Account(Decimal(account['equity']),account['received_ms'],True),
                   baseline_cash=cash,baseline_inventory=inventory,baseline_sequence=as_of,
                   last_broker_sequence=as_of,certified_generation=state.generation,
                   certified_ms=event.time_ms,mode='RECONCILING',halted=True)
