import io
import json
import re
import ssl
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import urllib.parse
import urllib.request

from quant_data import alpaca
from quant_data.__main__ import main
from quant_data.bundle import prepare_bundle, read_bundle
from quant_research.serde import InputError

# Invented prices; March 2024 sessions are EDT, so New York midnight is 04:00Z.
SESSIONS = ['2024-03-11', '2024-03-12', '2024-03-13', '2024-03-14', '2024-03-15',
            '2024-03-18', '2024-03-19', '2024-03-20', '2024-03-21', '2024-03-22']
START, END = date(2024, 3, 11), date(2024, 3, 22)
CLOCK = lambda: datetime(2026, 10, 5, 12, 0, 0, tzinfo=timezone.utc)


def daily_bar(day, open_='500.10'):
    return {'t': f'{day}T04:00:00Z', 'o': Decimal(open_), 'h': Decimal('505.5'), 'l': Decimal('499'),
            'c': Decimal('503.25'), 'v': 50000000, 'n': 400000, 'vw': Decimal('502')}


def minute_bars(day, first_open='500.10'):
    return [{'t': f'{day}T12:00:00Z', 'o': Decimal('480'), 'h': Decimal('530'), 'l': Decimal('470'),
             'c': Decimal('481'), 'v': 10},  # 08:00 New York, outside the session
            {'t': f'{day}T13:30:00Z', 'o': Decimal(first_open), 'h': Decimal('505.5'), 'l': Decimal('499'),
             'c': Decimal('501'), 'v': 1000},
            {'t': f'{day}T19:59:00Z', 'o': Decimal('503'), 'h': Decimal('504'), 'l': Decimal('502'),
             'c': Decimal('503.25'), 'v': 1000}]


class FakeAlpaca:
    def __init__(self, *, daily=None, dividends=None, minute_open=None, page_size=None):
        self.daily = daily if daily is not None else [daily_bar(day) for day in SESSIONS]
        self.dividends = dividends if dividends is not None else [
            {'symbol': 'SPY', 'rate': Decimal('1.5949'), 'special': False, 'foreign': False,
             'ex_date': '2024-03-15', 'record_date': '2024-03-18', 'payable_date': '2024-04-30'}]
        self.minute_open = minute_open or {}
        self.page_size = page_size
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        parts = urllib.parse.urlsplit(url)
        query = dict(urllib.parse.parse_qsl(parts.query))
        if parts.path == '/v2/calendar':
            body = [{'date': day, 'open': '09:30', 'close': '16:00', 'session_open': '0400',
                     'session_close': '2000', 'settlement_date': day} for day in SESSIONS]
        elif parts.path == '/v1/corporate-actions':
            body = {'corporate_actions': {'cash_dividends': self.dividends}, 'next_page_token': None}
        elif parts.path == '/v2/stocks/bars' and query['timeframe'] == '1Day':
            start = int(query.get('page_token', '0'))
            size = self.page_size or len(self.daily)
            more = start + size < len(self.daily)
            body = {'bars': {'SPY': self.daily[start:start + size]},
                    'next_page_token': str(start + size) if more else None}
        elif parts.path == '/v2/stocks/bars' and query['timeframe'] == '1Min':
            day = query['start'][:10]
            body = {'bars': {'SPY': minute_bars(day, self.minute_open.get(day, '500.10'))},
                    'next_page_token': None}
        else:
            raise AssertionError(f'unexpected request {url}')
        # Emit Decimals as bare JSON numbers, exactly as written, like the real API.
        text = json.dumps(body, default=lambda value: f'@@{value}@@')
        return re.sub(r'"@@([^"]+)@@"', r'\1', text).encode()


def fetched(fake):
    return alpaca.fetch_inputs(fake, START, END, clock=CLOCK)


class AlpacaSourceTests(unittest.TestCase):
    def test_fetched_inputs_pass_strict_intake_end_to_end(self):
        fake = FakeAlpaca()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'alpaca'
            alpaca.write_inputs(folder, fetched(fake))
            bundle = Path(tmp) / 'spy.qdata'
            prepare_bundle(*(folder / name for name in alpaca.FILES[:4]), bundle)
            dataset = read_bundle(bundle)
            check = json.loads((folder / 'alpaca-check.json').read_text())
        self.assertEqual([bar.session.isoformat() for bar in dataset.bars], SESSIONS)
        dividend = dataset.bars[4]
        self.assertEqual((dividend.dividend, dividend.dividend_pay_date), (Decimal('1.5949'), date(2024, 4, 30)))
        self.assertEqual(dataset.bars[0].open, Decimal('500.10'))
        self.assertEqual(dataset.manifest['kind'], 'historical')
        self.assertEqual(check['flagged'], 0)
        daily = next(url for url in fake.urls if 'timeframe=1Day' in url)
        for part in ('adjustment=raw', 'feed=sip', 'start=2024-03-11', 'end=2024-03-23'):
            self.assertIn(part, daily)

    def test_pages_are_followed_until_the_token_ends(self):
        fake = FakeAlpaca(page_size=3)
        files = fetched(fake)
        self.assertEqual(files['prices.csv'].decode().count('\n'), len(SESSIONS) + 1)
        tokens = [dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(u).query)).get('page_token')
                  for u in fake.urls if 'timeframe=1Day' in u]
        self.assertEqual(tokens, [None, '3', '6', '9'])

    def test_bar_calendar_mismatch_and_bad_labels_fail_closed(self):
        with self.assertRaisesRegex(InputError, 'missing'):
            fetched(FakeAlpaca(daily=[daily_bar(day) for day in SESSIONS if day != '2024-03-13']))
        shifted = [daily_bar(day) for day in SESSIONS]
        shifted[2] = dict(shifted[2], t='2024-03-13T13:30:00Z')
        with self.assertRaisesRegex(InputError, 'midnight'):
            fetched(FakeAlpaca(daily=shifted))
        with self.assertRaisesRegex(InputError, 'positive whole volume'):
            fetched(FakeAlpaca(daily=[dict(daily_bar(day), v=0) for day in SESSIONS]))

    def test_missing_quarterly_dividend_fails_closed(self):
        with self.assertRaisesRegex(InputError, r"dividend history incomplete.*2024-03"):
            fetched(FakeAlpaca(dividends=[]))
        foreign = [{'symbol': 'SPY', 'rate': Decimal('1'), 'foreign': True,
                    'ex_date': '2024-03-15', 'payable_date': '2024-04-30'}]
        with self.assertRaisesRegex(InputError, 'USD domestic'):
            fetched(FakeAlpaca(dividends=foreign))

    def test_daily_bars_disagreeing_with_regular_session_fail_closed(self):
        tolerated = {day: '501.00' for day in SESSIONS[:2]}  # 0.18% away on two sessions
        files = fetched(FakeAlpaca(minute_open=tolerated))
        self.assertEqual(json.loads(files['alpaca-check.json'])['flagged'], 2)
        with self.assertRaisesRegex(InputError, 'disagree with regular-session'):
            fetched(FakeAlpaca(minute_open={day: '501.00' for day in SESSIONS[:3]}))

    def test_existing_output_directory_is_never_reused(self):
        files = fetched(FakeAlpaca())
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'alpaca'
            folder.mkdir()
            with self.assertRaises(InputError):
                alpaca.write_inputs(folder, files)
            self.assertEqual(list(Path(tmp).iterdir()), [folder])

    def test_transport_requires_keys_retries_and_never_echoes_secrets(self):
        with self.assertRaisesRegex(InputError, 'APCA_API_KEY_ID'):
            alpaca.environment_transport(environ={})
        environ = {'APCA_API_KEY_ID': 'key-id-123', 'APCA_API_SECRET_KEY': 'secret-456'}
        pauses = []
        url = 'https://data.alpaca.markets/v2/stocks/bars?symbols=SPY'
        busy = urllib.error.HTTPError(url, 429, 'busy', {}, io.BytesIO(b'{"message":"rate limit"}'))

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False
        seen = []

        test = self

        class Opener:
            def __init__(self, context):
                test.assertTrue(context.check_hostname)
                test.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)

            def open(self, request, timeout):
                seen.append(dict(request.header_items()))
                if len(seen) == 1:
                    raise busy
                return Response(b'{"ok":true}')
        with patch.object(alpaca, '_opener', lambda context: Opener(context)):
            get = alpaca.environment_transport(environ=environ, pause=pauses.append)
            self.assertEqual(get(url), b'{"ok":true}')
        self.assertEqual(pauses, [2])
        self.assertEqual(seen[0]['Apca-api-key-id'], 'key-id-123')
        denied = urllib.error.HTTPError(url, 403, 'forbidden', {},
                                        io.BytesIO(b'{"message":"subscription does not permit querying recent SIP data"}'))
        class Denied:
            def open(self, request, timeout):
                raise denied
        with patch.object(alpaca, '_opener', lambda context: Denied()), \
                self.assertRaises(InputError) as raised:
            alpaca.environment_transport(environ=environ, pause=pauses.append)(url + '&page_token=abc')
        message = str(raised.exception)
        self.assertIn('HTTP 403', message)
        self.assertIn('recent SIP data', message)
        self.assertNotIn('secret-456', message)
        self.assertNotIn('page_token', message)
        self.assertIsNone(raised.exception.__cause__)

    def test_redirects_are_refused_so_keys_never_follow_them(self):
        opener = alpaca._opener(alpaca.tls_context())
        self.assertTrue(any(isinstance(handler, alpaca._NoRedirect) for handler in opener.handlers))
        request = urllib.request.Request('https://data.alpaca.markets/x', headers={'APCA-API-SECRET-KEY': 's'})
        self.assertIsNone(alpaca._NoRedirect().redirect_request(
            request, None, 302, 'Found', {}, 'https://elsewhere.example/collect'))

    def test_oversized_or_overprecise_numbers_are_rejected_before_rendering(self):
        for value in ('1E9000000', '1E19', '0.0000000000001', '1.' + '1' * 30):
            with self.subTest(value=value), self.assertRaisesRegex(InputError, 'out of range'):
                alpaca._decimal(Decimal(value), 'bar o')
        with self.assertRaisesRegex(InputError, 'whole volume'):
            fetched(FakeAlpaca(daily=[dict(daily_bar(day), v=10**13) for day in SESSIONS]))

    def test_data_stays_out_of_version_control(self):
        files = fetched(FakeAlpaca())
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / 'repo'
            (repo / '.git').mkdir(parents=True)
            (repo / '.research-output').mkdir()
            with self.assertRaisesRegex(InputError, 'research-output'):
                alpaca.write_inputs(repo / 'data', files)
            alpaca.write_inputs(repo / '.research-output' / 'alpaca', files)
            self.assertEqual(sorted(p.name for p in (repo / '.research-output' / 'alpaca').iterdir()),
                             sorted(alpaca.FILES))

    def test_cli_refuses_incomplete_end_session(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch('sys.stderr', new_callable=io.StringIO) as stderr:
            today = datetime.now(timezone.utc).date().isoformat()
            code = main(['fetch-alpaca', '--start', '2016-01-01', '--end', today,
                         '--output-dir', str(Path(tmp) / 'out')])
        self.assertEqual(code, 2)
        self.assertIn('before today', stderr.getvalue())


if __name__ == '__main__':
    unittest.main()
