"""Local optional-ML diagnostics. Does not install packages or load models."""

import argparse
import os
from pathlib import Path
import sys

from quant_research.__main__ import publish_report
from quant_research.serde import InputError, canonical_json
from .preflight import assess, collect


def gpu_index(value):
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError('GPU index must be an integer') from error
    if number < 0:
        raise argparse.ArgumentTypeError('GPU index must be nonnegative')
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(description='Local environment checks; no models or accounts.')
    commands = parser.add_subparsers(dest='command', required=True)
    preflight = commands.add_parser('preflight', help='Write a bounded local hardware/software report.')
    preflight.add_argument('--output', type=Path, required=True)
    preflight.add_argument('--gpu-index', type=gpu_index, default=0,
                           help='Logical PyTorch CUDA index; default 0.')
    preflight.add_argument('--skip-cuda', action='store_true',
                           help='Do not import PyTorch; report remains blocked.')
    args = parser.parse_args(argv)
    try:
        if os.path.lexists(args.output) or not args.output.parent.is_dir():
            raise InputError('output exists or parent directory is missing')
        report = assess(collect(gpu_index=args.gpu_index, skip_cuda=args.skip_cuda))
        publish_report(args.output, canonical_json(report))
    except (InputError, ValueError, OSError) as error:
        print(f'Preflight error: {error}', file=sys.stderr)
        return 2
    print(f"{report['status']}: {args.output}")
    for blocker in report['blockers']:
        print(f"  {blocker['id']}: {blocker['detail']}")
    return 2 if report['blockers'] else 0


if __name__ == '__main__':
    sys.exit(main())
