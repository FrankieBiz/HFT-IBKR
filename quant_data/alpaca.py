"""Free Alpaca source for raw daily SPY bars, cash dividends and the exchange calendar.

Produces the four declared inputs that `quant_data prepare` accepts. Every request goes
through an injected `get(url) -> bytes`, so tests stay offline. The default transport
reads free paper-account keys from the environment and sends them only as request
headers. It never writes, logs or echoes them. Alpaca's terms allow personal
non-commercial use and forbid redistribution, so outputs belong outside Git.
"""

import csv
import io
import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from quant_research.serde import InputError, _pairs, canonical_json, durable_sync, iso_date

DATA_URL = 'https://data.alpaca.markets'
TRADING_URL = 'https://paper-api.alpaca.markets'
KEY_VARIABLES = ('APCA_API_KEY_ID', 'APCA_API_SECRET_KEY')
TERMS = ('Alpaca Terms and Conditions: personal non-commercial use; no redistribution '
         '(https://files.alpaca.markets/disclosures/library/TermsAndConditions.pdf)')
NEW_YORK = ZoneInfo('America/New_York')
MAX_RESPONSE = 32 * 1024 * 1024
MAX_PAGES = 1000
RETRYABLE = (429, 500, 502, 503, 504)
CHECK_SESSIONS = 10
# Tolerance and count for the daily-versus-regular-session cross-check, fixed in advance.
CHECK_TOLERANCE = Decimal('0.001')
CHECK_MAX_FLAGGED = 2
FILES = ('prices.csv', 'distributions.csv', 'calendar.csv', 'metadata.json', 'alpaca-check.json')
SYSTEM_CA_BUNDLE = '/etc/ssl/cert.pem'


def tls_context(system_bundle=SYSTEM_CA_BUNDLE):
    """Certificate-verifying TLS context; never disables verification.

    python.org macOS builds ship without CA certificates until 'Install Certificates'
    runs, so add the macOS system bundle when OpenSSL loaded no anchors of its own.
    """
    context = ssl.create_default_context()
    if not context.cert_store_stats()['x509_ca'] and Path(system_bundle).is_file():
        context.load_verify_locations(system_bundle)
    return context


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """urllib copies custom headers, including API keys, onto redirects; refuse them."""

    def redirect_request(self, *args, **kwargs):
        return None


def _opener(context):
    return urllib.request.build_opener(_NoRedirect(), urllib.request.HTTPSHandler(context=context))


def environment_transport(*, attempts=5, pause=time.sleep, environ=None):
    """Return `get(url)` authenticated with free Alpaca paper keys from the environment."""
    environ = os.environ if environ is None else environ
    keys = [environ.get(name, '') for name in KEY_VARIABLES]
    if not all(keys):
        raise InputError('set APCA_API_KEY_ID and APCA_API_SECRET_KEY (free Alpaca paper-account keys)')
    headers = {'APCA-API-KEY-ID': keys[0], 'APCA-API-SECRET-KEY': keys[1],
               'Accept': 'application/json', 'User-Agent': 'hft-ibkr-research/1'}
    opener = _opener(tls_context())

    def get(url):
        for attempt in range(attempts):
            last = attempt + 1 == attempts
            try:
                with opener.open(urllib.request.Request(url, headers=headers), timeout=30) as response:
                    body = response.read(MAX_RESPONSE + 1)
                if len(body) > MAX_RESPONSE:
                    raise InputError('Alpaca response exceeds size limit')
                return body
            except urllib.error.HTTPError as error:
                if error.code in RETRYABLE and not last:
                    pause(min(60, 2 ** (attempt + 1)))
                    continue
                detail = error.read(512).decode('utf-8', 'replace').strip()
                # No exception chaining: tracebacks stay free of request objects and headers.
                raise InputError(f'Alpaca HTTP {error.code} for {_redacted(url)}: {detail}') from None
            except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
                if not last:
                    pause(min(60, 2 ** (attempt + 1)))
                    continue
                raise InputError(f'Alpaca request failed for {_redacted(url)}: {error}') from None
        raise InputError('Alpaca request attempts exhausted')
    return get


def _redacted(url):
    parts = urllib.parse.urlsplit(url)
    return f'{parts.scheme}://{parts.netloc}{parts.path}'


def _get_json(get, base, path, params):
    url = base + path + '?' + urllib.parse.urlencode(sorted(params.items()))
    try:
        return json.loads(get(url).decode('utf-8'), parse_float=Decimal, object_pairs_hook=_pairs)
    except (UnicodeError, ValueError) as error:
        if isinstance(error, InputError):
            raise
        raise InputError(f'invalid JSON from {path}: {error}') from error


def _paged(get, base, path, params, extract):
    items, token = [], None
    for _ in range(MAX_PAGES):
        document = _get_json(get, base, path, params if token is None else {**params, 'page_token': token})
        if not isinstance(document, dict):
            raise InputError(f'{path}: object response required')
        items.extend(extract(document))
        token = document.get('next_page_token')
        if token is None:
            return items
        if not isinstance(token, str) or not token:
            raise InputError(f'{path}: invalid page token')
    raise InputError(f'{path}: page limit exceeded')


def _bars_extractor(symbol):
    def extract(document):
        bars = document.get('bars')
        if isinstance(bars, dict):  # multi-symbol shape keyed by symbol
            bars = bars.get(symbol, [])
        if not isinstance(bars, list):
            raise InputError('bars: list required')
        return bars
    return extract


def fetch_bars(get, symbol, start, end, timeframe='1Day'):
    params = {'symbols': symbol, 'timeframe': timeframe, 'start': start, 'end': end,
              'adjustment': 'raw', 'feed': 'sip', 'limit': 10000, 'sort': 'asc'}
    return _paged(get, DATA_URL, '/v2/stocks/bars', params, _bars_extractor(symbol))


def fetch_dividends(get, symbol, start, end):
    def extract(document):
        actions = document.get('corporate_actions', {})
        if not isinstance(actions, dict):
            raise InputError('corporate_actions: object required')
        dividends = actions.get('cash_dividends', [])
        if not isinstance(dividends, list):
            raise InputError('cash_dividends: list required')
        return dividends
    params = {'symbols': symbol, 'types': 'cash_dividend', 'start': start, 'end': end,
              'limit': 1000, 'sort': 'asc'}
    return _paged(get, DATA_URL, '/v1/corporate-actions', params, extract)


def fetch_calendar(get, start, end):
    document = _get_json(get, TRADING_URL, '/v2/calendar', {'start': start, 'end': end})
    if not isinstance(document, list):
        raise InputError('calendar: list response required')
    return document


def _decimal(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise InputError(f'{name}: number required')
    number = Decimal(value)
    if not number.is_finite() or number <= 0:
        raise InputError(f'{name}: positive finite number required')
    # Same bounds as the intake's decimal_value, checked before any text expansion.
    digits, exponent = len(number.as_tuple().digits), number.as_tuple().exponent
    if digits > 28 or exponent < -12 or digits + exponent > 19 or number > Decimal('1e18'):
        raise InputError(f'{name}: magnitude or precision out of range')
    return number


def _text(number):
    return format(number, 'f')


def _bar_session(bar, *, daily):
    if not isinstance(bar, dict) or not isinstance(bar.get('t'), str):
        raise InputError('bar: object with timestamp required')
    try:
        instant = datetime.fromisoformat(bar['t'].replace('Z', '+00:00'))
    except ValueError as error:
        raise InputError(f'bar timestamp invalid: {bar["t"]}') from error
    if instant.utcoffset() != timedelta(0):
        raise InputError('bar timestamp must be UTC')
    local = instant.astimezone(NEW_YORK)
    # Alpaca labels daily bars 00:00 New York time; anything else means different semantics.
    if daily and (local.hour, local.minute, local.second, local.microsecond) != (0, 0, 0, 0):
        raise InputError(f'daily bar not labeled at New York midnight: {bar["t"]}')
    return local


def _calendar_sessions(calendar, start, end):
    sessions = []
    for item in calendar:
        if not isinstance(item, dict):
            raise InputError('calendar entry: object required')
        day = iso_date(item.get('date'), 'calendar date')
        if start <= day <= end:
            for field in ('open', 'close'):
                value = item.get(field)
                if not isinstance(value, str) or len(value) != 5 or value[2] != ':':
                    raise InputError('calendar open/close must be HH:MM')
            sessions.append((day, item['open'], item['close']))
    if not sessions or any(a[0] >= b[0] for a, b in zip(sessions, sessions[1:])):
        raise InputError('calendar sessions must be nonempty and strictly increasing')
    return sessions


def _third_friday(year, month):
    first = date(year, month, 1)
    return first + timedelta(days=(4 - first.weekday()) % 7 + 14)


def issuer_pay_date(ex):
    """SPY's pay date for a quarterly ex-date: the last weekday of the following month.

    The SPDR S&P 500 ETF Trust prospectus (SEC filing dated 2019-01-17) pays dividends on
    "the last Business Day ... of April, July, October and January". No market holiday
    falls on the last weekday of those months, so the exact Business Day definition is moot.
    """
    if ex.month not in (3, 6, 9, 12):
        raise InputError(f'{ex}: no issuer pay-date rule for an ex-date outside Mar/Jun/Sep/Dec')
    year, month = (ex.year + 1, 1) if ex.month == 12 else (ex.year, ex.month + 1)
    pay = date(year, month + 1, 1) - timedelta(days=1)
    while pay.weekday() > 4:
        pay -= timedelta(days=1)
    return pay


def build_inputs(bars, dividends, calendar, *, start, end, retrieved, check=None):
    """Validate fetched records and render the declared intake files as bytes."""
    sessions = _calendar_sessions(calendar, start, end)
    days = [day for day, _, _ in sessions]
    rows = []
    for bar in bars:
        day = _bar_session(bar, daily=True).date()
        if not start <= day <= end:
            continue
        o, h, l, c = (_decimal(bar.get(field), f'bar {field}') for field in 'ohlc')
        volume = bar.get('v')
        if type(volume) is not int or not 0 < volume < 10**13:
            raise InputError(f'{day}: positive whole volume required')
        rows.append((day, o, h, l, c, volume))
    bar_days = [row[0] for row in rows]
    if bar_days != days:
        missing = sorted(set(days) - set(bar_days))[:5]
        extra = sorted(set(bar_days) - set(days))[:5]
        raise InputError(f'daily bars do not match the calendar; missing {missing}, unexpected {extra}')

    first, last = days[0], days[-1]
    distributions = {}
    derived, provided = [], []
    for item in dividends:
        if not isinstance(item, dict):
            raise InputError('dividend: object required')
        ex = iso_date(item.get('ex_date'), 'dividend ex_date')
        if not first < ex <= last:
            continue
        if item.get('foreign') or item.get('currency', 'USD') != 'USD':
            raise InputError(f'{ex}: only USD domestic cash dividends are supported')
        if item.get('payable_date') is None:  # Alpaca omits it on older records
            if item.get('special'):
                raise InputError(f'{ex}: cannot derive a pay date for a special dividend')
            pay = issuer_pay_date(ex)
            derived.append(ex)
        else:
            pay = iso_date(item.get('payable_date'), 'dividend payable_date')
            provided.append((ex, pay))
        if ex in distributions:
            raise InputError(f'{ex}: multiple cash dividends share an ex-date')
        distributions[ex] = (_decimal(item.get('rate'), 'dividend rate'), pay)
    pay_note = ''
    if derived:
        # Alpaca's own dates are the only independent check on the derived ones.
        checkable = [(ex, pay) for ex, pay in provided if ex.month in (3, 6, 9, 12)]
        disagree = [ex.isoformat() for ex, pay in checkable if pay != issuer_pay_date(ex)]
        if disagree:
            raise InputError(f'Alpaca pay dates disagree with the issuer schedule on {disagree[:3]}; '
                             'refusing to derive the missing ones')
        pay_note = (f' Alpaca omitted payable_date for {len(derived)} dividend(s) with ex-dates '
                    f'{min(derived).isoformat()} to {max(derived).isoformat()}; these were derived as the '
                    'last weekday of the month after the ex-date, per the SPDR S&P 500 ETF Trust prospectus '
                    '(SEC filing dated 2019-01-17); '
                    + (f'they matched all {len(checkable)} Alpaca-provided pay dates that could be checked.'
                       if checkable else 'no Alpaca-provided pay date was available to cross-check them.'))
    # SPY goes ex-dividend on the third Friday of each quarter-end month.
    missing = [f'{year}-{month:02d}' for year in range(first.year, last.year + 1) for month in (3, 6, 9, 12)
               if first < _third_friday(year, month) <= last
               and not any(ex.year == year and ex.month == month for ex in distributions)]
    if missing:
        raise InputError(f'dividend history incomplete; no ex-date in {missing[:6]}')

    prices = io.StringIO(newline='')
    writer = csv.writer(prices, lineterminator='\n')
    writer.writerow(('session', 'open', 'high', 'low', 'close', 'volume'))
    for day, o, h, l, c, volume in rows:
        writer.writerow((day.isoformat(), _text(o), _text(h), _text(l), _text(c), volume))
    payouts = io.StringIO(newline='')
    writer = csv.writer(payouts, lineterminator='\n')
    writer.writerow(('ex_date', 'amount', 'pay_date'))
    for ex in sorted(distributions):
        amount, pay = distributions[ex]
        writer.writerow((ex.isoformat(), _text(amount), pay.isoformat()))
    calendar_csv = 'session\n' + ''.join(day.isoformat() + '\n' for day in days)

    window = f'{first.isoformat()} to {last.isoformat()}'
    metadata = {
        'schema_version': 1, 'symbol': 'SPY', 'currency': 'USD', 'kind': 'historical',
        'price_policy': 'raw_unadjusted', 'corporate_actions': 'complete_dividends_no_splits',
        'splits_in_interval': False,
        'review_note': ('Alpaca free-plan SIP daily bars (adjustment=raw), cash dividends from '
                        'Alpaca corporate actions and the Alpaca trading calendar, ' + window + '. '
                        'Quarterly dividend coverage and bar/calendar equality were checked; a '
                        'daily-versus-regular-session minute-bar cross-check is in alpaca-check.json. '
                        'No split is declared because SPY has not split, per public split histories; '
                        'not independently verified against exchange official records.' + pay_note),
        'sources': {
            'prices': {'name': 'Alpaca Market Data API v2 daily bars',
                       'reference': f'{DATA_URL}/v2/stocks/bars symbols=SPY timeframe=1Day adjustment=raw feed=sip; {window}',
                       'license_reference': TERMS, 'retrieved_at': retrieved['prices']},
            'distributions': {'name': 'Alpaca Market Data API v1 corporate actions (cash_dividend)',
                              'reference': f'{DATA_URL}/v1/corporate-actions symbols=SPY types=cash_dividend; {window}',
                              'license_reference': TERMS, 'retrieved_at': retrieved['distributions']},
            'calendar': {'name': 'Alpaca Trading API v2 calendar',
                         'reference': f'{TRADING_URL}/v2/calendar; {window}',
                         'license_reference': TERMS, 'retrieved_at': retrieved['calendar']}}}
    return {'prices.csv': prices.getvalue().encode(), 'distributions.csv': payouts.getvalue().encode(),
            'calendar.csv': calendar_csv.encode(), 'metadata.json': canonical_json(metadata).encode(),
            'alpaca-check.json': canonical_json(check or {}).encode()}


def check_sessions(days, count=CHECK_SESSIONS):
    """Evenly spaced sessions, fixed by position, for the daily/minute cross-check."""
    if len(days) <= count:
        return list(days)
    return [days[round(i * (len(days) - 1) / (count - 1))] for i in range(count)]


def cross_check(get, bars, calendar, *, start, end):
    """Compare daily bars with regular-session minute bars on fixed sample sessions.

    Daily bars that silently included pre- or post-market trades would usually open or
    range away from the regular session. More than CHECK_MAX_FLAGGED sessions beyond
    CHECK_TOLERANCE fails the fetch.
    """
    sessions = {day: (opening, closing) for day, opening, closing in _calendar_sessions(calendar, start, end)}
    daily = {}
    for bar in bars:
        day = _bar_session(bar, daily=True).date()
        if day in sessions:
            daily[day] = bar
    results = []
    for day in check_sessions(sorted(sessions)):
        opening, closing = sessions[day]
        open_at = datetime.fromisoformat(f'{day.isoformat()}T{opening}:00').replace(tzinfo=NEW_YORK)
        close_at = datetime.fromisoformat(f'{day.isoformat()}T{closing}:00').replace(tzinfo=NEW_YORK)
        minutes = [bar for bar in fetch_bars(get, 'SPY', open_at.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z'),
                                             close_at.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z'), '1Min')
                   if open_at <= _bar_session(bar, daily=False) < close_at]
        if not minutes or day not in daily:
            results.append({'session': day.isoformat(), 'flagged': True, 'reason': 'missing bars'})
            continue
        bar = daily[day]
        o, h, l = (_decimal(bar.get(field), f'bar {field}') for field in 'ohl')
        first_open = _decimal(minutes[0].get('o'), 'minute open')
        high = max(_decimal(m.get('h'), 'minute high') for m in minutes)
        low = min(_decimal(m.get('l'), 'minute low') for m in minutes)
        gaps = {'open_vs_first_minute': abs(o - first_open) / first_open,
                'high_above_session': max(Decimal(0), h - high) / high,
                'low_below_session': max(Decimal(0), low - l) / low}
        results.append({'session': day.isoformat(), 'flagged': max(gaps.values()) > CHECK_TOLERANCE,
                        **{name: format(value, '.6f') for name, value in gaps.items()}})
    flagged = sum(item['flagged'] for item in results)
    report = {'schema_version': 1, 'tolerance': format(CHECK_TOLERANCE, 'f'),
              'max_flagged': CHECK_MAX_FLAGGED, 'flagged': flagged, 'sessions': results}
    if flagged > CHECK_MAX_FLAGGED:
        raise InputError(f'daily bars disagree with regular-session minute bars on {flagged} '
                         f'of {len(results)} sample sessions; see semantics before use')
    return report


def fetch_inputs(get, start, end, *, clock=None):
    """Fetch, cross-check and render intake inputs for [start, end] inclusive."""
    clock = clock or (lambda: datetime.now(timezone.utc))
    if not isinstance(start, date) or not isinstance(end, date) or start >= end:
        raise InputError('start must precede end')
    stamp = lambda: clock().replace(microsecond=0).isoformat().replace('+00:00', 'Z')
    retrieved = {}
    calendar = fetch_calendar(get, start.isoformat(), end.isoformat())
    retrieved['calendar'] = stamp()
    # A bare end date may mean midnight UTC, before the final bar's 04:00Z/05:00Z label;
    # request one extra day and filter by session date instead.
    bars = fetch_bars(get, 'SPY', start.isoformat(), (end + timedelta(days=1)).isoformat())
    retrieved['prices'] = stamp()
    dividends = fetch_dividends(get, 'SPY', (start - timedelta(days=31)).isoformat(),
                                (end + timedelta(days=31)).isoformat())
    retrieved['distributions'] = stamp()
    check = cross_check(get, bars, calendar, start=start, end=end)
    return build_inputs(bars, dividends, calendar, start=start, end=end, retrieved=retrieved, check=check)


def _check_destination(folder):
    """Keep licensed data out of version control: inside a Git work tree, only
    under the ignored `.research-output/` directory."""
    resolved = folder.parent.resolve() / folder.name
    for parent in resolved.parents:
        if (parent / '.git').exists():
            if '.research-output' not in resolved.relative_to(parent).parts:
                raise InputError('inside a Git work tree, write Alpaca data only under .research-output/ '
                                 '(the data may not be redistributed)')
            return


def write_inputs(folder, files):
    """Publish all files into a new directory, never into an existing one."""
    folder = Path(folder)
    if os.path.lexists(folder) or not folder.parent.is_dir():
        raise InputError('output directory exists or its parent is missing')
    _check_destination(folder)
    staging = folder.parent / f'.{folder.name}.partial-{os.getpid()}'
    staging.mkdir(mode=0o700)
    try:
        for name in FILES:
            with (staging / name).open('xb') as handle:
                handle.write(files[name])
                handle.flush()
                durable_sync(handle.fileno())
        os.rename(staging, folder)
    except BaseException:
        for name in FILES:
            (staging / name).unlink(missing_ok=True)
        staging.rmdir()
        raise
