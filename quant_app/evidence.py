"""Content-keyed verification for the read-only study display, never execution.

Every refresh hashes evidence bytes, research source and SQLite WAL/journal.
The expensive bundle/registry verification is reused only for identical content.
Books, fills, ledger history and runner readiness are outside this cache.
"""
from copy import deepcopy
import hashlib
from importlib.resources import files
from pathlib import Path
import threading

from quant_research.serde import InputError, read_json
from quant_session.readiness import verify_readiness


def _identity(paths):
    digest = hashlib.sha256()
    research = files('quant_research')
    inputs = [Path(value) for value in paths.values()]
    inputs.extend(path for path in research.iterdir() if path.name.endswith('.py'))
    inputs.extend(Path(str(paths['registry'])+suffix) for suffix in ('-wal','-journal'))
    for path in sorted(inputs, key=str):
        digest.update(str(path).encode() + b'\0')
        try:
            with path.open('rb') as handle:
                content_digest = hashlib.sha256()
                while content := handle.read(1024*1024):
                    content_digest.update(content)
                digest.update(b'present\0' + content_digest.digest())
        except FileNotFoundError:
            digest.update(b'missing\0')
        digest.update(b'\0')
    return digest.digest()


def _projection(verified, report):
    fields = ('total_return','maximum_drawdown','trade_count','rejection_count',
              'evaluated_sessions','exposure_sessions','modeled_execution_cost')
    trend = {row['cost_multiplier']: row['result'] for row in report['scenarios']}
    benchmark = {row['cost_multiplier']: row['result'] for row in report['benchmarks']['buy_hold']}
    return {'ready': True, 'error': None, 'outcome': verified['outcome'],
            'feed': verified['price_feed'], 'selected_lookback': verified['selected_lookback'],
            'settings': verified['planning_config'], 'cost_scenarios': [
                {'cost_multiplier': multiplier,
                 'trend': {key: trend[multiplier].get(key) for key in fields},
                 'benchmark': {key: benchmark[multiplier].get(key) for key in fields}}
                for multiplier in (1,2,5)]}


class StudyEvidence:
    def __init__(self, paths):
        self.paths = dict(paths)
        self.identity = None
        self.status = None
        self.lock = threading.Lock()

    def snapshot(self, *, verifier=None):
        with self.lock:
            empty = {'ready': False, 'outcome': None, 'feed': None, 'error': None,
                     'selected_lookback': None, 'settings': None, 'cost_scenarios': []}
            try:
                identity = _identity(self.paths)
                if self.status is not None and self.identity == identity:
                    return deepcopy(self.status)
                try:
                    verified = (verifier or verify_readiness)(**self.paths, require_alpaca_feed=True)
                    if _identity(self.paths) != identity:
                        raise InputError('Study evidence changed during verification; refresh to recheck.')
                    status = _projection(verified, read_json(self.paths['holdout']))
                except InputError as error:
                    status = dict(empty, error=str(error))
                if _identity(self.paths) != identity:
                    raise InputError('Study evidence changed during verification; refresh to recheck.')
                self.identity, self.status = identity, status
                return deepcopy(status)
            except (OSError, InputError, ValueError, KeyError, TypeError) as error:
                self.identity, self.status = None, None
                return dict(empty, error=str(error))
