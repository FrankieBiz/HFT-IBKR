"""Assess local daily outcomes; no network, accounts or holdout release."""

import argparse
import hashlib
import os
from pathlib import Path
import sys

from quant_research.__main__ import publish_report, source_identity
from quant_research.serde import InputError, canonical_json, read_json_document
from .assessment import assess
from .inputs import parse_input


def main(argv=None):
    parser = argparse.ArgumentParser(description='Offline daily edge evidence diagnostics.')
    commands = parser.add_subparsers(dest='command', required=True)
    operation = commands.add_parser('assess', help='Inspect net outcomes and block uncertainty.')
    operation.add_argument('--input', required=True, type=Path)
    operation.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if os.path.lexists(args.output) or not args.output.parent.is_dir():
            raise InputError('output exists or parent directory is missing')
        raw, content = read_json_document(args.input)
        report = assess(parse_input(raw))
        report.update(input=raw, input_sha256=hashlib.sha256(content).hexdigest(), code={
            'evidence': source_identity(package='quant_evidence'), 'research': source_identity(),
        })
        publish_report(args.output, canonical_json(report))
    except (InputError, OSError) as error:
        print(f'Evidence error: {error}', file=sys.stderr)
        return 2
    print(f"diagnostic_only: {report['numeric_assessment']}; promotion disallowed; {args.output}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
