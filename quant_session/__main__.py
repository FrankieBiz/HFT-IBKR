"""Shadow decision commands. No orders, broker connections or order methods exist here.

`plan` is offline. `live-inputs` is the only network use: it reads the Alpaca calendar
and SPY's free real-time IEX quote to render plan inputs.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sys

from quant_data.alpaca import NEW_YORK, environment_transport, fetch_calendar
from quant_data.bundle import read_bundle
from quant_research.__main__ import publish_report, source_identity
from quant_research.config import parse_config
from quant_research.serde import InputError, canonical_json
from .inputs import parse_schedule, parse_snapshot, read_document
from .ledger import DecisionLedger
from .live import build_schedule, build_snapshot, latest_quote
from .planner import plan_session


def _now():
    return datetime.now(timezone.utc)


def live_inputs(args, transport=None):
    for target in (args.schedule_out, args.snapshot_out):
        if target.exists() or not target.parent.is_dir():
            raise InputError('live input outputs must be new files in existing directories')
    dataset = read_bundle(args.bundle)
    portfolio, _ = read_document(args.portfolio)
    get = transport or environment_transport()
    today = _now().astimezone(NEW_YORK).date()
    calendar = fetch_calendar(get, dataset.bars[0].session.isoformat(), today.isoformat())
    schedule = build_schedule(calendar, dataset.bars[0].session, today,
                              _now().replace(microsecond=0).isoformat())
    session = parse_schedule(schedule)['sessions'][-1]
    if not session['open_at'] <= _now() < session['close_at']:
        # A plan outside the window would freeze today's decision as BLOCKED.
        raise InputError(f"market is closed now; run between {session['open_at'].astimezone(NEW_YORK):%H:%M} "
                         f"and {session['close_at'].astimezone(NEW_YORK):%H:%M} New York time")
    quote = latest_quote(get)
    # Read the clock after the quote so a fresh quote is never stamped in the future.
    snapshot = build_snapshot(portfolio, quote, _now(), today)
    parse_snapshot(snapshot)
    publish_report(args.schedule_out, canonical_json(schedule))
    publish_report(args.snapshot_out, canonical_json(snapshot))
    print(f"Live inputs for {today}: IEX bid {quote['bid']} / ask {quote['ask']} at {quote['as_of']}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description='Non-binding shadow session proposals; never places orders.')
    commands = parser.add_subparsers(dest='command', required=True)
    plan = commands.add_parser('plan')
    for field in ('bundle','config','schedule','snapshot','ledger','output'):
        plan.add_argument('--'+field, required=True, type=Path)
    live = commands.add_parser('live-inputs', help='Render today\'s schedule and snapshot from the free '
                               'Alpaca calendar and IEX quote (keys from APCA_API_KEY_ID / APCA_API_SECRET_KEY).')
    for field in ('bundle','portfolio','schedule-out','snapshot-out'):
        live.add_argument('--'+field, required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'live-inputs':
            return live_inputs(args)
        inputs = (args.bundle,args.config,args.schedule,args.snapshot)
        if args.ledger.resolve() in {path.resolve() for path in inputs}:
            raise InputError('ledger must differ from input paths')
        if args.output.resolve() in {path.resolve() for path in (*inputs,args.ledger)}:
            raise InputError('output must differ from input and ledger paths')
        dataset = read_bundle(args.bundle)
        declarations = {}
        hashes = {}
        for field in ('config','schedule','snapshot'):
            raw,content = read_document(getattr(args,field))
            declarations[field] = raw
            hashes[field] = hashlib.sha256(content).hexdigest()
        for package in ('quant_session','quant_research','quant_data'):
            hashes[package+'_source'] = source_identity(package=package)['source_sha256']
        report = plan_session(dataset,parse_config(declarations['config']),
                              parse_schedule(declarations['schedule']),
                              parse_snapshot(declarations['snapshot']),hashes)
        input_id = hashlib.sha256(canonical_json(report['source_hashes']).encode()).hexdigest()
        content = DecisionLedger(args.ledger).record(report,input_id)
        publish_report(args.output,content.decode('utf-8'))
        print(f"{report['status']}: {report['decision_id']}")
        return 0
    except (InputError, OSError) as error:
        print(f'input error: {error}',file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
