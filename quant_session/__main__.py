"""Offline local-file shadow rehearsal command. No orders or network clients."""
import argparse
import hashlib
from pathlib import Path
import sys

from quant_data.bundle import read_bundle
from quant_research.__main__ import publish_report, source_identity
from quant_research.config import parse_config
from quant_research.serde import InputError, canonical_json
from .inputs import parse_schedule, parse_snapshot, read_document
from .ledger import DecisionLedger
from .planner import plan_session


def main(argv=None):
    parser = argparse.ArgumentParser(description='Non-binding offline synthetic session proposals.')
    commands = parser.add_subparsers(dest='command', required=True)
    plan = commands.add_parser('plan')
    for field in ('bundle','config','schedule','snapshot','ledger','output'):
        plan.add_argument('--'+field, required=True, type=Path)
    args = parser.parse_args(argv)
    try:
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
