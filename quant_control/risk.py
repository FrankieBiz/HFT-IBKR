"""Pure pre-admission checks; outstanding reservations never offset each other."""

import json
from dataclasses import asdict, dataclass
from decimal import Decimal

from quant_research.serde import InputError, canonical_json, fixed_decimal, whole
from .domain import Intent, money, time_value, validate_config


@dataclass(frozen=True)
class Quote:
    bid: Decimal
    ask: Decimal
    received_ms: int
    data_type: str


@dataclass(frozen=True)
class Account:
    equity: Decimal
    received_ms: int
    valid: bool


@dataclass(frozen=True)
class Order:
    intent: Intent
    filled: int
    status: str
    sent_ms: int
    cancel_sent: bool = False
    pending_terminal_quantity: int | None = None
    cancel_sent_ms: int | None = None

    @property
    def remaining(self):
        return 0 if self.status in ('FILLED','CANCELLED','REJECTED') else self.intent.quantity - self.filled


@dataclass(frozen=True)
class Decision:
    accepted: bool
    reason: str


@dataclass(frozen=True)
class RiskView:
    mode: str
    halted: bool
    cash: Decimal
    inventory: int
    account: Account | None
    quote: Quote | None
    orders: tuple[Order, ...]


@fixed_decimal
def evaluate(intent, state, config, now_ms):
    try:
        config=validate_config(json.loads(canonical_json(asdict(config))))
        intent=Intent.from_raw(json.loads(canonical_json(asdict(intent))))
        time_value(now_ms)
        _validate_view(state)
    except (InputError,TypeError,AttributeError,ValueError):
        return Decision(False,'INVALID_INPUT')
    if config.mode != 'simulation' or state.mode != 'READY' or state.halted:
        return Decision(False,'NOT_READY')
    if intent.created_ms > now_ms:
        return Decision(False,'FUTURE_INTENT')
    if now_ms >= intent.expires_ms:
        return Decision(False,'EXPIRED')
    if state.account is None or not state.account.valid:
        return Decision(False,'ACCOUNT_UNAVAILABLE')
    account_age = now_ms - state.account.received_ms
    if account_age < 0:
        return Decision(False,'FUTURE_ACCOUNT')
    if account_age > config.max_account_age_ms:
        return Decision(False,'STALE_ACCOUNT')
    if state.quote is None or state.quote.data_type != 'realtime':
        return Decision(False,'QUOTE_UNAVAILABLE')
    quote_age = now_ms - state.quote.received_ms
    if quote_age < 0:
        return Decision(False,'FUTURE_QUOTE')
    if quote_age > config.max_quote_age_ms:
        return Decision(False,'STALE_QUOTE')
    if config.session_start_equity - state.account.equity >= config.daily_loss_limit:
        return Decision(False,'LOSS_LIMIT')
    if intent.quantity * intent.limit_price > config.max_order_notional:
        return Decision(False,'ORDER_NOTIONAL_LIMIT')
    active = tuple(order for order in state.orders if order.remaining)
    buys = tuple(order for order in active if order.intent.side == 'BUY')
    sells = tuple(order for order in active if order.intent.side == 'SELL')
    pending_buys = sum(order.remaining for order in buys)
    pending_sells = sum(order.remaining for order in sells)
    candidate_buys = intent.quantity if intent.side == 'BUY' else 0
    if state.inventory + pending_buys + candidate_buys > config.max_units:
        return Decision(False,'POSITION_LIMIT')
    if intent.side == 'BUY':
        reserved = sum((order.remaining * order.intent.limit_price for order in buys),Decimal(0))
        if intent.quantity * intent.limit_price > state.cash - reserved:
            return Decision(False,'CASH_LIMIT')
    elif pending_sells + intent.quantity > state.inventory:
        return Decision(False,'INVENTORY_LIMIT')
    prices = [state.quote.ask, *(order.intent.limit_price for order in buys)]
    if intent.side == 'BUY':
        prices.append(intent.limit_price)
    if (state.inventory + pending_buys + candidate_buys) * max(prices) > config.max_position_notional:
        return Decision(False,'POSITION_NOTIONAL_LIMIT')
    return Decision(True,'ACCEPTED')


def _validate_view(state):
    if not isinstance(state,RiskView) or type(state.halted) is not bool:
        raise InputError('invalid risk view')
    if state.mode not in ('BOOTSTRAP','RECONCILING','READY','HALTED'):
        raise InputError('invalid control mode')
    def amount(value,positive=False):
        if not isinstance(value,Decimal):
            raise InputError('typed monetary input required')
        return money(str(value),'risk amount',positive)
    amount(state.cash)
    whole(state.inventory,'inventory',minimum=0)
    if state.account is not None:
        if not isinstance(state.account,Account) or type(state.account.valid) is not bool:
            raise InputError('invalid account view')
        amount(state.account.equity)
        time_value(state.account.received_ms)
    if state.quote is not None:
        if not isinstance(state.quote,Quote) or state.quote.data_type not in ('realtime','delayed'):
            raise InputError('invalid quote view')
        amount(state.quote.bid,True)
        amount(state.quote.ask,True)
        if state.quote.bid>state.quote.ask:
            raise InputError('crossed quote')
        time_value(state.quote.received_ms)
    if not isinstance(state.orders,tuple):
        raise InputError('immutable order collection required')
    ids=set()
    for order in state.orders:
        if not isinstance(order,Order):
            raise InputError('invalid order record')
        normalized=Intent.from_raw(json.loads(canonical_json(asdict(order.intent))))
        if normalized.intent_id in ids:
            raise InputError('duplicate reserved order')
        ids.add(normalized.intent_id)
        whole(order.filled,'filled',minimum=0)
        time_value(order.sent_ms)
        if (order.filled>order.intent.quantity or type(order.cancel_sent) is not bool or
                order.status not in ('PENDING_ACK','OPEN','UNKNOWN_OUTCOME','FILLED','CANCELLED','REJECTED')):
            raise InputError('invalid order state')
        if ((order.status=='FILLED' and order.filled!=order.intent.quantity) or
                (order.status=='REJECTED' and order.filled!=0) or
                (order.status in ('PENDING_ACK','OPEN') and order.filled==order.intent.quantity)):
            raise InputError('inconsistent filled/order status')
        if state.mode=='READY' and order.status=='UNKNOWN_OUTCOME':
            raise InputError('unresolved outcome in ready view')
        if order.pending_terminal_quantity is not None:
            whole(order.pending_terminal_quantity,'terminal filled',minimum=0)
            if not order.filled<=order.pending_terminal_quantity<=order.intent.quantity:
                raise InputError('invalid pending fill evidence')
            if order.status in ('FILLED','CANCELLED','REJECTED') and order.pending_terminal_quantity!=order.filled:
                raise InputError('terminal state omits reported executions')
            if order.status in ('PENDING_ACK','OPEN'):
                raise InputError('pending terminal outcome contradicts open status')
        if order.cancel_sent_ms is not None:
            time_value(order.cancel_sent_ms)
