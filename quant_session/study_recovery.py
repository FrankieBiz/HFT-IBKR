"""Export interrupted study publication from original stored evidence only.

No research is repeated, no consumed dates reopened, and the registry is read-only.
An unfinished attempt or absent registered freeze requires reviewed recovery.
"""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys

from quant_data.bundle import read_bundle
from quant_research.__main__ import publish_report, source_identity
from quant_research.config import parse_config
from quant_research.evaluation import (digest, freeze_selection, identities, parse_protocol,
                                       verify_selection)
from quant_research.serde import InputError, _pairs, canonical_json, read_json
from .readiness import _columns, _stored_result

VALIDATION_RUN = 'spy-trend-v2-validation-1'
HOLDOUT_RUN = 'spy-trend-v2-holdout-1'


def _completed(connection, run_id):
    rows = connection.execute('SELECT status FROM events WHERE run_id=? ORDER BY sequence', (run_id,)).fetchall()
    if not rows:
        return False
    if [row['status'] for row in rows] != ['reserved','completed']:
        raise InputError(f'{run_id} has an unfinished or failed attempt; retain registry for reviewed recovery, do not rerun/reset it')
    return True


def _inputs(paths):
    return [hashlib.sha256(Path(path).read_bytes()).digest() for path in paths]


def recover_study(*, bundle, config, protocol, registry, output,
                  validation_run=VALIDATION_RUN, holdout_run=HOLDOUT_RUN):
    output, registry = Path(output), Path(registry)
    try:
        with closing(sqlite3.connect(registry.resolve().as_uri()+'?mode=ro', uri=True)) as db:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')
            validation_exists = _completed(db, validation_run)
            holdout_exists = _completed(db, holdout_run)
            if not validation_exists:
                if holdout_exists:
                    raise InputError('Completed holdout lacks its original validation; retain registry for review')
                if any(os.path.lexists(output/name) for name in ('validation.json','selection.json','holdout.json')):
                    raise InputError('Study artifacts lack original registered runs; retain files for review')
                return []
            paths = (bundle,config,protocol)
            before = _inputs(paths)
            dataset = read_bundle(bundle)
            base = parse_config(read_json(config))
            parsed = parse_protocol(read_json(protocol), dataset)
            code = source_identity()['source_sha256']
            expected = identities(dataset, base, parsed, code)
            validation = _stored_result(db, validation_run, 'validation', expected, None)
            if (validation.get('mode') != 'offline_chronological_validation'
                    or validation.get('data_kind') != dataset.manifest['kind']):
                raise InputError('Stored validation mode/provenance differs from current inputs')
            freezes = db.execute('SELECT * FROM frozen_selections WHERE validation_run_id=?', (validation_run,)).fetchall()
            if len(freezes) != 1:
                raise InputError('Completed validation lacks exactly one original registered freeze; reviewed recovery required')
            frozen = freezes[0]
            artifact = json.loads(frozen['artifact'], object_pairs_hook=_pairs)
            verify_selection(artifact, dataset, base, parsed, code)
            if (frozen['artifact'] != canonical_json(artifact)
                    or frozen['artifact_digest'] != artifact['integrity_digest']
                    or frozen['stable_identity'] != digest(expected)
                    or artifact['validation_report_digest'] != digest(validation)
                    or freeze_selection(dataset, base, parsed, code, validation) != artifact):
                raise InputError('Registered freeze differs from original validation/identities')
            for candidate in validation['candidates']:
                for interval in ('development','validation'):
                    _columns(candidate[interval])
            for interval in ('development','validation'):
                _columns(validation['benchmarks']['buy_hold'][interval])
            documents = {'validation.json': validation, 'selection.json': artifact}
            if holdout_exists:
                holdout = _stored_result(db, holdout_run, 'holdout', expected, artifact['integrity_digest'])
                if (type(holdout.get('schema_version')) is not int or holdout['schema_version'] != 1
                        or holdout.get('mode') != 'offline_holdout_release'
                        or holdout.get('data_kind') != dataset.manifest['kind']
                        or holdout.get('selected_lookback') != artifact['selected_lookback']
                        or holdout.get('artifact_digest') != artifact['integrity_digest']):
                    raise InputError('Stored holdout differs from original freeze')
                _columns(holdout['scenarios'])
                _columns(holdout['benchmarks']['buy_hold'])
                claim = db.execute('SELECT * FROM holdout_claims WHERE artifact_digest=?', (artifact['integrity_digest'],)).fetchone()
                if claim is None or claim['run_id'] != holdout_run or claim['stable_identity'] != digest(expected):
                    raise InputError('Original holdout claim identity mismatch')
                released = db.execute('SELECT session FROM released_holdout_sessions WHERE scope=? AND run_id=? ORDER BY session',
                    (dataset.manifest['kind']+':SPY', holdout_run)).fetchall()
                sessions = [bar.session.isoformat() for bar in dataset.bars
                            if parsed.holdout_start <= bar.session <= parsed.holdout_end]
                if [row['session'] for row in released] != sessions:
                    raise InputError('Original released holdout sessions mismatch')
                documents['holdout.json'] = holdout
            elif os.path.lexists(output/'holdout.json'):
                raise InputError('Existing holdout lacks original completed registry payload')
            encoded = {name: canonical_json(document) for name,document in documents.items()}
            # Validate every existing target before publishing any missing target.
            for name, content in encoded.items():
                target = output/name
                if os.path.lexists(target) and (target.is_symlink() or not target.is_file()
                        or target.read_bytes() != content.encode()):
                    raise InputError(f'Existing {name} differs from original stored evidence; retain files for review')
            if _inputs(paths) != before or source_identity()['source_sha256'] != code:
                raise InputError('Study inputs/source changed during recovery')
            recovered = []
            for name, content in encoded.items():
                target = output/name
                if not os.path.lexists(target):
                    publish_report(target, content)
                    recovered.append(name)
            return recovered
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError, AttributeError, ArithmeticError) as error:
        if isinstance(error, InputError):
            raise
        raise InputError(f'Invalid stored study evidence; retain for reviewed recovery: {error}') from error


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('bundle','config','protocol','registry','output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        recovered = recover_study(**vars(args))
    except InputError as error:
        print(f'study recovery error: {error}', file=sys.stderr)
        return 2
    if recovered:
        print('Recovered original stored study artifacts: '+', '.join(recovered))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
