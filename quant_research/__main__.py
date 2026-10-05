"""Command-line local research replay. Nothing here connects to a broker."""

import argparse
import hashlib
import os
import sys
import tempfile
from importlib.resources import files
from dataclasses import asdict
from pathlib import Path

from . import __version__
from .backtest import run_research
from .config import parse_config
from .data import load_dataset
from .evaluation import parse_protocol, evaluate_registered, freeze_selection, release_holdout
from .experiments import ExperimentRegistry
from .serde import InputError, canonical_json, durable_sync, iso_date, read_json_document

ASSUMPTIONS = [
    'Exploratory offline simulation; no strategy profitability or readiness is established.',
    'Raw unadjusted daily SPY prices; no splits; declared dividend coverage and calendar supplied by input owner.',
    'Completed-close signals trade only at following-session open; last-close target remains unexecuted.',
    'Causal dividend-aware SMA; whole shares; long-only cash funding; no daily rebalance.',
    'Buy-and-hold uses same start, capital, costs, sizing and risk; it retries entry until admissible.',
    'Open marks, post-fill open marks and closing marks update drawdown; buy halt is latched; sells still require admission.',
    'Dividends accrue before ex-date trading; receivables enter NAV; cash is credited before first supplied session on/after pay date.',
    'Entry sizing uses prior-close NAV and price, reduced at open for limits, fees and prior-volume capacity.',
    'Full exits exceeding order/capacity limits are rejected and reported; no forced or assumed partial liquidation.',
    'Flat adverse spread/slippage/impact and configurable fee scenarios are assumptions, not calibrated broker/exchange execution.',
    'One fill per admitted transition; no queue modeling; no cash interest, taxes, settlement delays or fractional shares.',
    'ETF expenses are already reflected in raw market prices; no separate expense-ratio deduction.',
    'Replay is exploratory; chronological evaluation and frozen holdout release use separate commands.',
    'Input hash/coverage checks do not independently verify market data, corporate-action completeness or exchange calendar accuracy.',
    'Positions can drift beyond entry exposure cap; end holdings and unpaid receivables remain marked.',
]


def source_identity(folder=None, *, package='quant_research'):
    root = folder or files(package)
    digest = hashlib.sha256()
    for path in sorted((path for path in root.iterdir() if path.is_file() and path.name.endswith('.py')),key=lambda path:path.name):
        digest.update(path.name.encode('utf-8') + b'\0' + path.read_bytes() + b'\0')
    return {'version': __version__, 'source_sha256': digest.hexdigest()}


def publish_report(destination, content):
    """Publish a fully written same-filesystem file without replacing any target."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n',
                                         dir=destination.parent, prefix='.research-',
                                         delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            durable_sync(handle.fileno())
        # A hard link atomically creates the target and fails if any target exists.
        os.link(temporary, destination)
    except OSError as error:
        raise InputError(f'cannot publish output (existing file or storage error): {error}') from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Offline ETF trend research using local input files.')
    subparsers = parser.add_subparsers(dest='command', required=True)
    replay = subparsers.add_parser('replay', help='Compare daily trend with buy-and-hold under cost stress.')
    replay.add_argument('--data', type=Path)
    replay.add_argument('--manifest', type=Path)
    replay.add_argument('--bundle', type=Path)
    replay.add_argument('--config', required=True, type=Path)
    replay.add_argument('--evaluation-start', help='YYYY-MM-DD; default first session after lookback warmup')
    replay.add_argument('--output', required=True, type=Path)
    for command in ('evaluate', 'holdout'):
        operation = subparsers.add_parser(command, help='Offline chronological '+command)
        for field in ('data','manifest','bundle'):
            operation.add_argument('--'+field,type=Path)
        for field in ('config','protocol','registry','selection','output'):
            operation.add_argument('--'+field,required=True,type=Path)
        operation.add_argument('--run-id',required=True)
    recovery=subparsers.add_parser('recover',help='Export a stored completed result without recomputation.')
    recovery.add_argument('--registry',required=True,type=Path)
    recovery.add_argument('--run-id',required=True)
    recovery.add_argument('--output',required=True,type=Path)
    args = parser.parse_args(argv)
    try:
        targets=[args.output]
        if args.command=='evaluate':
            targets.append(args.selection)
        if len(set(path.resolve() for path in targets))!=len(targets):
            raise InputError('outputs must have distinct paths')
        if args.command in ('evaluate','holdout') and any(target.resolve()==args.registry.resolve() for target in targets):
            raise InputError('report/selection outputs must differ from registry')
        if args.command=='holdout' and not args.registry.is_file():
            raise InputError('holdout requires existing experiment registry')
        for target in targets:
            if os.path.lexists(target) or not target.parent.is_dir():
                raise InputError('output already exists or parent directory is missing')
        if args.command=='recover':
            if not args.registry.is_file():
                raise InputError('existing registry required for recovery')
            with ExperimentRegistry(args.registry) as registry:
                report=registry.result(args.run_id)
            publish_report(args.output,canonical_json(report))
            print(f'Recovered stored report: {args.output}')
            return 0
        if args.bundle is not None:
            if args.data is not None or args.manifest is not None:
                raise InputError('use --bundle or --data plus --manifest, never both')
        elif args.data is None or args.manifest is None:
            raise InputError('supply --bundle or both --data and --manifest')
        raw_config, config_bytes = read_json_document(args.config)
        config = parse_config(raw_config)
        if args.bundle is not None:
            from quant_data.bundle import read_bundle
            dataset = read_bundle(args.bundle)
        else:
            dataset = load_dataset(args.data, args.manifest)
        if len(dataset.bars) <= config.lookback:
            raise InputError('dataset has no evaluation sessions after warmup')
        if args.command=='replay':
            start = iso_date(args.evaluation_start, 'evaluation start') if args.evaluation_start else dataset.bars[config.lookback].session
            report = run_research(dataset, config, start)
            report.update({
            'schema_version': 1, 'code': source_identity(), 'config': asdict(config),
            'config_sha256': hashlib.sha256(config_bytes).hexdigest(),
            'data_sha256': dataset.data_sha256, 'manifest_sha256': dataset.manifest_sha256,
            'provenance': dataset.manifest, 'assumptions': ASSUMPTIONS,
            })
        else:
            protocol=parse_protocol(read_json_document(args.protocol)[0],dataset)
            code=source_identity()['source_sha256']
            with ExperimentRegistry(args.registry) as registry:
                if args.command=='evaluate':
                    report=evaluate_registered(dataset,config,protocol,code,registry=registry,run_id=args.run_id)
                    artifact=freeze_selection(dataset,config,protocol,code,report)
                    registry.register_freeze(args.run_id,artifact)
                    publish_report(args.selection,canonical_json(artifact))
                else:
                    artifact=read_json_document(args.selection)[0]
                    report=release_holdout(artifact,dataset,config,protocol,code,registry=registry,run_id=args.run_id)
        publish_report(args.output, canonical_json(report))
    except InputError as error:
        print(f'input error: {error}', file=sys.stderr)
        return 2
    except Exception as error:
        print(f'runtime error: {error}', file=sys.stderr)
        return 1
    print(f'Wrote offline research report: {args.output} ({dataset.manifest["kind"]} data; strategy unproven)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
