from datetime import date, datetime, timezone
from decimal import Decimal
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
from quant_session.live import build_schedule, build_snapshot, latest_quote
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
