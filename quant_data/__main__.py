"""Offline prepare/inspect operations for declared local market-data files."""

import argparse
import os
from pathlib import Path
import sys

from quant_research.__main__ import publish_report
from quant_research.serde import InputError, canonical_json
from .bundle import prepare_bundle, inspect_bundle


def main(argv=None):
    parser = argparse.ArgumentParser(description='Strict local data intake; no downloads or broker access.')
    commands = parser.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser('prepare', help='Normalize declared source exports into a research bundle.')
    for name in ('prices', 'distributions', 'calendar', 'metadata', 'output'):
        prepare.add_argument('--' + name, type=Path, required=True)
    inspect = commands.add_parser('inspect', help='Validate bundle and export its coverage/provenance report.')
    inspect.add_argument('--bundle', type=Path, required=True)
    inspect.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
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
