"""Local-only CLI. No broker, model, data-vendor or network clients."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
import sys

from .config import Config
from .data import DatasetStore
from .reporting import code_provenance, render_report, write_artifacts, write_new_files
from .simulation import simulate
from .synthetic import generate


def run_backtest(database: Path, dataset: str, config: Config, output: Path):
    with DatasetStore(database) as store:
        metadata, bars = store.metadata(dataset), store.bars(dataset)
    if config.interval_seconds != metadata['interval_seconds']:
        raise ValueError('config interval must match dataset provenance')
    result = simulate(bars, config)
    result['provenance'] = dict(code_provenance(), dataset_id=dataset, dataset=metadata,
                                strategy='moving-average-v1', strategy_parameters=asdict(config))
    write_artifacts(result, output)
    return result


def parser():
    root = argparse.ArgumentParser(description='Offline quantitative research. Broker modes are unavailable.')
    commands = root.add_subparsers(dest='command', required=True)
    demo = commands.add_parser('demo', help='generate synthetic data and a complete local report')
    demo.add_argument('--output', type=Path, default=Path('artifacts/demo'))
    demo.add_argument('--seed', type=int, default=17)
    validate = commands.add_parser('validate-config')
    validate.add_argument('config', type=Path)
    ingest = commands.add_parser('import-csv')
    ingest.add_argument('csv', type=Path)
    ingest.add_argument('--metadata', type=Path, required=True)
    ingest.add_argument('--database', type=Path, default=Path('artifacts/history.sqlite'))
    listing = commands.add_parser('datasets')
    listing.add_argument('--database', type=Path, default=Path('artifacts/history.sqlite'))
    backtest = commands.add_parser('backtest')
    backtest.add_argument('--database', type=Path, required=True)
    backtest.add_argument('--dataset', required=True)
    backtest.add_argument('--config', type=Path, required=True)
    backtest.add_argument('--output', type=Path, default=Path('artifacts/backtest'))
    report = commands.add_parser('report')
    report.add_argument('result', type=Path)
    report.add_argument('--output', type=Path, required=True)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == 'validate-config':
            print(json.dumps(asdict(Config.load(args.config)), indent=2))
        elif args.command == 'demo':
            args.output.mkdir(parents=True, exist_ok=True)
            for name in ('synthetic.csv', 'history.sqlite', 'result.json', 'report.html', 'research-packet.md'):
                if (args.output/name).exists() or (args.output/name).is_symlink():
                    raise FileExistsError(f'{args.output/name} exists; choose a new output directory')
            csv = args.output/'synthetic.csv'
            generate(csv, args.seed)
            metadata = dict(source='synthetic software fixture', adjustment='none',
                            survivorship='single synthetic instrument', interval_seconds=60, seed=args.seed)
            database = args.output/'history.sqlite'
            with DatasetStore(database) as store:
                dataset = store.import_csv(csv, metadata)
            result = run_backtest(database, dataset, Config(), args.output)
            print(json.dumps(dict(output=str(args.output.resolve()), dataset=dataset, summary=result['summary']), indent=2))
        elif args.command == 'import-csv':
            args.database.parent.mkdir(parents=True, exist_ok=True)
            with DatasetStore(args.database) as store:
                print(store.import_csv(args.csv, json.loads(args.metadata.read_text())))
        elif args.command == 'datasets':
            with DatasetStore(args.database) as store:
                print(json.dumps(store.datasets(), indent=2))
        elif args.command == 'backtest':
            result = run_backtest(args.database, args.dataset, Config.load(args.config), args.output)
            print(json.dumps(result['summary'], indent=2))
        elif args.command == 'report':
            args.output.parent.mkdir(parents=True, exist_ok=True)
            write_new_files(args.output.parent, {args.output.name: render_report(json.loads(args.result.read_text()))})
    except (ValueError, TypeError, KeyError, OSError, sqlite3.Error) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2
    return 0
