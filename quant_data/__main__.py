"""Prepare/inspect declared local market-data files; fetch-alpaca is the only download."""

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sys

from quant_research.__main__ import publish_report
from quant_research.serde import InputError, canonical_json, iso_date
from .alpaca import environment_transport, fetch_inputs, write_inputs
from .bundle import prepare_bundle, inspect_bundle


def main(argv=None):
    parser = argparse.ArgumentParser(description='Strict local data intake; downloads only via fetch-alpaca.')
    commands = parser.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser('prepare', help='Normalize declared source exports into a research bundle.')
    for name in ('prices', 'distributions', 'calendar', 'metadata', 'output'):
        prepare.add_argument('--' + name, type=Path, required=True)
    inspect = commands.add_parser('inspect', help='Validate bundle and export its coverage/provenance report.')
    inspect.add_argument('--bundle', type=Path, required=True)
    inspect.add_argument('--output', type=Path, required=True)
    fetch = commands.add_parser('fetch-alpaca', help='Download raw daily SPY inputs from Alpaca '
                                '(keys from APCA_API_KEY_ID / APCA_API_SECRET_KEY).')
    fetch.add_argument('--start', required=True, help='YYYY-MM-DD, first calendar date requested')
    fetch.add_argument('--end', required=True, help='YYYY-MM-DD, last completed session; must be before today (UTC)')
    fetch.add_argument('--output-dir', type=Path, required=True)
    fetch.add_argument('--feed', choices=('iex', 'sip'), default='iex',
                       help='Price feed: iex (default, single exchange); sip requires permitted access.')
    args = parser.parse_args(argv)
    try:
        if args.command == 'fetch-alpaca':
            start, end = iso_date(args.start, 'start'), iso_date(args.end, 'end')
            if end >= datetime.now(timezone.utc).date():
                raise InputError('end must be a completed session before today (UTC)')
            files = fetch_inputs(environment_transport(), start, end, feed=args.feed)
            write_inputs(args.output_dir, files)
            print(f'Wrote Alpaca intake inputs: {args.output_dir}; not for redistribution. '
                  'Next: quant_data prepare.')
            return 0
        if os.path.lexists(args.output) or not args.output.parent.is_dir():
            raise InputError('output exists or parent directory missing')
        if args.command == 'prepare':
            prepare_bundle(args.prices, args.distributions, args.calendar, args.metadata, args.output)
        else:
            publish_report(args.output, canonical_json(inspect_bundle(args.bundle)))
    except (InputError, OSError) as error:
        print(f'intake error: {error}', file=sys.stderr)
        return 2
    print(f'Wrote offline {args.command} output: {args.output}; provenance is declared, not independently verified.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
