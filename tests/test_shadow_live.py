from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_EVEN, ROUND_UP, localcontext
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.parse

from quant_data.bundle import prepare_bundle
from quant_research.serde import InputError
from quant_session import __main__ as session_cli
from quant_session.inputs import parse_schedule, parse_snapshot
from quant_session.live import build_schedule, build_snapshot, latest_quote, market_clock
from test_data_intake import inputs
from test_inputs import raw_config

# Invented calendar matching the synthetic intake fixture, plus an execution day.
DAYS = ['2025-01-02', '2025-01-03', '2025-01-06', '2025-01-07', '2025-01-08', '2025-01-09']
CALENDAR = [{'date': day, 'open': '09:30', 'close': '16:00', 'session_open': '0400',
             'session_close': '2000', 'settlement_date': day} for day in DAYS]
NOW = datetime(2025, 1, 9, 14, 35, 1, tzinfo=timezone.utc)
PORTFOLIO = {'schema_version': 1, 'cash': '10000', 'settled_cash': '10000', 'shares': 0,
             'peak_nav': '10000', 'halted': False}


def fake_alpaca(bid='105', ask='105.01', stamp='2025-01-09T14:35:00.123456789Z', calendar=CALENDAR):
    def get(url):
        path = urllib.parse.urlsplit(url).path
        if path == '/v2/calendar':
            return json.dumps(calendar).encode()
        if path == '/v2/stocks/quotes/latest':
            assert 'feed=iex' in url
            return ('{"quotes":{"SPY":{"t":"%s","bp":%s,"bs":300,"ap":%s,"as":200,'
                    '"bx":"V","ax":"V","c":["R"],"z":"B"}}}' % (stamp, bid, ask)).encode()
        raise AssertionError(url)
    return get


class LiveInputTests(unittest.TestCase):
    def test_live_inputs_drive_the_unchanged_planner_and_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            prepare_bundle(*inputs(folder), folder / 'data.qdata')
            config = raw_config()
            config['lookback'] = 2
            (folder / 'config.json').write_text(json.dumps(config))
            (folder / 'portfolio.json').write_text(json.dumps(PORTFOLIO))
            live = ['live-inputs', '--bundle', str(folder / 'data.qdata'), '--portfolio', str(folder / 'portfolio.json'),
                    '--schedule-out', str(folder / 'schedule.json'), '--snapshot-out', str(folder / 'snapshot.json')]
            with patch.object(session_cli, 'environment_transport', return_value=fake_alpaca()), \
                    patch.object(session_cli, '_now', return_value=NOW), patch('sys.stdout', new=io.StringIO()):
                self.assertEqual(session_cli.main(live), 0)
                self.assertEqual(session_cli.main(['plan', '--bundle', str(folder / 'data.qdata'),
                                                   '--config', str(folder / 'config.json'),
                                                   '--schedule', str(folder / 'schedule.json'),
                                                   '--snapshot', str(folder / 'snapshot.json'),
                                                   '--ledger', str(folder / 'ledger.db'),
                                                   '--output', str(folder / 'plan.json')]), 0)
            report = json.loads((folder / 'plan.json').read_text())
            snapshot = json.loads((folder / 'snapshot.json').read_text())
        self.assertEqual((report['status'], report['proposal']['side']), ('PROPOSED', 'BUY'))
        self.assertEqual(report['quote_scope'], 'alpaca_iex_realtime')
        self.assertEqual(report['signal_session'], '2025-01-08')
        self.assertEqual(snapshot['quote']['as_of'], '2025-01-09T14:35:00.123456+00:00')
        self.assertEqual(snapshot['now'], '2025-01-09T14:35:01+00:00')

    def test_quote_must_be_two_sided_and_unlocked(self):
        self.assertEqual(latest_quote(fake_alpaca())['bid'], '105')
        for bid, ask in (('105', '105'), ('105.02', '105.01'), ('0', '105.01')):
            with self.subTest(bid=bid, ask=ask), self.assertRaises(InputError):
                latest_quote(fake_alpaca(bid=bid, ask=ask))

    def test_fractional_quote_time_requires_original_utc_offset(self):
        for offset in ('+05:30', '-04:00', '+00:01', '-00:01', ''):
            stamp = f'2025-01-09T14:35:00.123456789{offset}'
            with self.subTest(stamp=stamp), self.assertRaisesRegex(InputError, 'must be UTC'):
                latest_quote(fake_alpaca(stamp=stamp))

    def test_nanosecond_utc_quote_time_keeps_microsecond_precision(self):
        for offset in ('Z', '+00:00'):
            with self.subTest(offset=offset):
                quote = latest_quote(fake_alpaca(stamp=f'2025-01-09T14:35:00.123456789{offset}'))
                self.assertEqual(quote['as_of'], '2025-01-09T14:35:00.123456+00:00')

    def test_schedule_spans_bundle_to_today_in_utc(self):
        schedule = build_schedule(CALENDAR, date(2025, 1, 2), date(2025, 1, 9), '2025-01-09T14:00:00+00:00')
        self.assertEqual(schedule['sessions'][-1], {'session': '2025-01-09', 'open_at': '2025-01-09T14:30:00+00:00',
                                                    'close_at': '2025-01-09T21:00:00+00:00'})
        parse_schedule(schedule)
        with self.assertRaisesRegex(InputError, 'not a trading session'):
            build_schedule(CALENDAR[:-1], date(2025, 1, 2), date(2025, 1, 9), 'x')

    def test_declared_book_is_marked_at_the_bid(self):
        quote = latest_quote(fake_alpaca())
        held = dict(PORTFOLIO, cash='1000', settled_cash='800', shares=10, peak_nav='3000')
        snapshot = build_snapshot(held, quote, NOW, date(2025, 1, 9))
        self.assertEqual(Decimal(snapshot['portfolio']['nav']), Decimal('2050'))
        self.assertEqual(snapshot['portfolio']['peak_nav'], '3000')
        parse_snapshot(snapshot)
        for bad in (dict(PORTFOLIO, extra=1), dict(PORTFOLIO, halted='no'), dict(PORTFOLIO, shares=-1),
                    dict(PORTFOLIO, cash='0', settled_cash='0')):
            with self.subTest(bad=bad), self.assertRaises(InputError):
                build_snapshot(bad, quote, NOW, date(2025, 1, 9))
        with self.assertRaises(InputError):
            parse_snapshot(build_snapshot(dict(PORTFOLIO, settled_cash='20000'), quote, NOW, date(2025, 1, 9)))

    def test_snapshot_is_independent_of_decimal_precision_and_rounding(self):
        quote = latest_quote(fake_alpaca(bid='123456.123456789012', ask='123456.13'))
        held = dict(PORTFOLIO, cash='1000.123456789012', settled_cash='800', shares=999999999999)
        with localcontext() as context:
            context.prec, context.rounding = 28, ROUND_HALF_EVEN
            expected = build_snapshot(held, quote, NOW, date(2025, 1, 9))
        self.assertEqual(expected['portfolio']['nav'], '123456123456666556.0000000000')
        for precision, rounding in ((6, ROUND_HALF_EVEN), (28, ROUND_UP), (40, ROUND_DOWN)):
            with self.subTest(precision=precision, rounding=rounding), localcontext() as context:
                context.prec, context.rounding = precision, rounding
                actual = build_snapshot(held, quote, NOW, date(2025, 1, 9))
                self.assertEqual(actual, expected)
                self.assertEqual((context.prec, context.rounding), (precision, rounding))

    def test_closed_market_records_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            prepare_bundle(*inputs(folder), folder / 'data.qdata')
            (folder / 'portfolio.json').write_text(json.dumps(PORTFOLIO))
            args = session_cli.argparse.Namespace(bundle=folder / 'data.qdata', portfolio=folder / 'portfolio.json',
                                                  schedule_out=folder / 'schedule.json',
                                                  snapshot_out=folder / 'snapshot.json')
            for moment in (datetime(2025, 1, 9, 14, 29, 59, tzinfo=timezone.utc),
                           datetime(2025, 1, 9, 21, 0, 0, tzinfo=timezone.utc)):
                with self.subTest(moment=moment), patch.object(session_cli, '_now', return_value=moment), \
                        self.assertRaisesRegex(InputError, 'market is closed now; run between 09:30 and 16:00'):
                    session_cli.live_inputs(args, transport=fake_alpaca())
            self.assertFalse((folder / 'snapshot.json').exists())

    def test_market_clock_follows_the_exchange_calendar(self):
        def at(day, clock, offset):  # local New York wall time given with its UTC offset
            return datetime.fromisoformat(f'{day}T{clock}{offset}')
        regular = [{'date': '2026-10-06', 'open': '09:30', 'close': '16:00'}]
        early = [{'date': '2026-11-27', 'open': '09:30', 'close': '13:00'}]
        cases = [
            # 06:30 EDT: run at 09:31, three hours one minute later; wake at 06:00 tomorrow.
            (regular, at('2026-10-06', '06:30:00', '-04:00'), ('open', 3 * 3600 + 60, 23 * 3600 + 30 * 60)),
            (regular, at('2026-10-06', '11:00:00', '-04:00'), ('open', 0, 19 * 3600)),
            (regular, at('2026-10-06', '16:00:00', '-04:00'), ('after', 0, 14 * 3600)),
            ([], at('2026-10-10', '06:30:00', '-04:00'), ('closed', 0, 23 * 3600 + 30 * 60)),
            (early, at('2026-11-27', '13:30:00', '-05:00'), ('after', 0, 16 * 3600 + 30 * 60)),
            # DST ends 2026-11-01: the next 06:00 EST wake-up is 24.5 wall hours (25.5 real) away.
            ([{'date': '2026-10-31', 'open': '09:30', 'close': '16:00'}],
             at('2026-10-31', '05:30:00', '-04:00'), ('open', 4 * 3600 + 60, 25 * 3600 + 30 * 60)),
        ]
        for calendar, now, expected in cases:
            with self.subTest(now=now):
                self.assertEqual(market_clock(calendar, now), expected)
        friday = at('2026-10-09', '17:00:00', '-04:00')
        self.assertEqual(market_clock([{'date': '2026-10-09', 'open': '09:30', 'close': '16:00'}], friday)[0], 'after')
        with self.assertRaises(InputError):
            market_clock(regular, datetime(2026, 10, 6, 6, 30))

    def test_existing_outputs_are_never_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / 'schedule.json').write_text('{}')
            args = session_cli.argparse.Namespace(bundle=folder / 'x', portfolio=folder / 'p',
                                                  schedule_out=folder / 'schedule.json',
                                                  snapshot_out=folder / 'snapshot.json')
            with self.assertRaises(InputError):
                session_cli.live_inputs(args, transport=fake_alpaca())


if __name__ == '__main__':
    unittest.main()
