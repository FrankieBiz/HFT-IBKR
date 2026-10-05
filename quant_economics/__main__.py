"""Local economic sensitivity report. No accounts, network or orders."""

import argparse
import hashlib
import os
from pathlib import Path
import sys

from quant_research.__main__ import publish_report, source_identity
from quant_research.serde import InputError, canonical_json, read_json_document
from .inputs import parse_config
from .model import assess


def main(argv=None):
    parser = argparse.ArgumentParser(description='Offline conditional economic sensitivity.')
    commands = parser.add_subparsers(dest='command', required=True)
    operation = commands.add_parser('assess', help='Calculate explicit costs and funding bounds.')
    operation.add_argument('--config', required=True, type=Path)
    operation.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if os.path.lexists(args.output) or not args.output.parent.is_dir():
            raise InputError('output exists or parent directory is missing')
        raw, content = read_json_document(args.config)
        report = assess(parse_config(raw))
        report.update(config=raw, input_sha256=hashlib.sha256(content).hexdigest(), code={
            'economics': source_identity(package='quant_economics'),
            'research': source_identity(),
        })
        publish_report(args.output, canonical_json(report))
    except (InputError, OSError) as error:
        print(f'Economics error: {error}', file=sys.stderr)
        return 2
    print(f"conditional_analysis: {args.output}; G0 incomplete; {len(report['rows'])} rows")
    return 0


if __name__ == '__main__':
    sys.exit(main())
