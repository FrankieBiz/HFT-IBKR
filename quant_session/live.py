"""Live inputs for the daily shadow plan: Alpaca calendar schedule and IEX quote.

Renders the schedule and snapshot documents that `quant_session plan` already
validates. The portfolio stays a user-maintained declaration for the SIM shadow book;
no broker is queried and no order exists anywhere in this path. The free plan's
real-time quote is IEX's own best bid/offer: one venue, not the national best quote.
"""
from datetime import datetime, time, timedelta, timezone

from quant_data.alpaca import DATA_URL, NEW_YORK, _calendar_sessions, _decimal, _get_json
from quant_research.serde import InputError, decimal_value, strict_keys, whole

QUOTE_TYPE = 'alpaca_iex_realtime'
PORTFOLIO_KEYS = ('schema_version', 'cash', 'settled_cash', 'shares', 'peak_nav', 'halted')
POLICY = {'max_quote_age_seconds': 60, 'max_account_age_seconds': 300}


def _utc(instant):
    return instant.astimezone(timezone.utc).isoformat()


def _session_instant(day, clock):
    return datetime.fromisoformat(f'{day.isoformat()}T{clock}:00').replace(tzinfo=NEW_YORK)


def build_schedule(calendar, first, today, retrieved_at):
    """Every calendar session from the bundle's first session through today."""
    sessions = _calendar_sessions(calendar, first, today)
    if sessions[-1][0] != today:
        raise InputError(f'{today} is not a trading session on the Alpaca calendar')
    return {'schema_version': 1,
            'source': f'Alpaca Trading API v2 calendar, retrieved {retrieved_at}',
            'sessions': [{'session': day.isoformat(), 'open_at': _utc(_session_instant(day, opening)),
                          'close_at': _utc(_session_instant(day, closing))}
                         for day, opening, closing in sessions]}


def latest_quote(get):
    document = _get_json(get, DATA_URL, '/v2/stocks/quotes/latest', {'symbols': 'SPY', 'feed': 'iex'})
    quote = document.get('quotes', {}).get('SPY') if isinstance(document, dict) else None
    if not isinstance(quote, dict) or not isinstance(quote.get('t'), str):
        raise InputError('latest IEX quote for SPY missing')
    bid, ask = _decimal(quote.get('bp'), 'IEX bid'), _decimal(quote.get('ap'), 'IEX ask')
    if bid >= ask:
        raise InputError('IEX quote is crossed or locked; rerun in a moment')
    stamp = quote['t'].replace('Z', '+00:00')
    whole_seconds, _, rest = stamp.partition('.')
    if rest:  # keep microseconds; Alpaca sends nanoseconds
        digits = rest[:rest.index('+')] if '+' in rest else rest
        stamp = f'{whole_seconds}.{digits[:6].ljust(6, "0")}+00:00'
    try:
        as_of = datetime.fromisoformat(stamp)
    except ValueError as error:
        raise InputError(f'invalid IEX quote time: {quote["t"]}') from error
    if as_of.utcoffset() is None or as_of.utcoffset().total_seconds() != 0:
        raise InputError('IEX quote time must be UTC')
    return {'bid': format(bid, 'f'), 'ask': format(ask, 'f'), 'as_of': _utc(as_of), 'data_type': QUOTE_TYPE}


def build_snapshot(portfolio, quote, now, today):
    """Mark the declared SIM book at the bid; the planner applies every gate."""
    strict_keys(portfolio, PORTFOLIO_KEYS, 'shadow portfolio')
    if type(portfolio['schema_version']) is not int or portfolio['schema_version'] != 1:
        raise InputError('unsupported shadow portfolio schema')
    cash = decimal_value(portfolio['cash'], 'cash')
    settled = decimal_value(portfolio['settled_cash'], 'settled_cash')
    peak = decimal_value(portfolio['peak_nav'], 'peak_nav', positive=True)
    shares = whole(portfolio['shares'], 'shares', minimum=0)
    if type(portfolio['halted']) is not bool:
        raise InputError('halted: strict boolean required')
    nav = cash + shares * decimal_value(quote['bid'], 'bid', positive=True)
    if nav <= 0:
        raise InputError('shadow portfolio has no value')
    stamp = _utc(now)
    return {'schema_version': 1, 'mode': 'offline_shadow', 'account': 'SIM', 'symbol': 'SPY',
            'currency': 'USD', 'execution_session': today.isoformat(), 'now': stamp, 'quote': quote,
            'portfolio': {'cash': format(cash, 'f'), 'settled_cash': format(settled, 'f'),
                          'nav': format(nav, 'f'), 'peak_nav': format(max(peak, nav), 'f'),
                          'shares': shares, 'as_of': stamp, 'reconciled': True, 'pending_orders': 0,
                          'uncertain_orders': 0, 'halted': portfolio['halted']},
            'policy': dict(POLICY)}


def market_clock(calendar, now, *, after_open=timedelta(minutes=1), wake=time(6, 0)):
    """Return (state, seconds until today's run, seconds until tomorrow's wake-up).

    state is 'open' (a session runs today and has not closed), 'closed' (no session
    today) or 'after' (today's session already closed). Times follow the exchange
    calendar in New York time, so holidays, early closes and DST are handled.
    """
    if now.utcoffset() is None:
        raise InputError('timezone-aware time required')
    today = now.astimezone(NEW_YORK).date()
    wake_at = datetime.combine(today + timedelta(days=1), wake, tzinfo=NEW_YORK)
    until_wake = max(60, int((wake_at - now).total_seconds()))
    sessions = [item for item in calendar if isinstance(item, dict) and item.get('date') == today.isoformat()]
    if not sessions:
        return 'closed', 0, until_wake
    _, opening, closing = _calendar_sessions(sessions, today, today)[0]
    run_at = _session_instant(today, opening) + after_open
    if now >= _session_instant(today, closing):
        return 'after', 0, until_wake
    return 'open', max(0, int((run_at - now).total_seconds())), until_wake
