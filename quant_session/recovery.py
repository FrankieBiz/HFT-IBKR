"""Offline publication of a committed shadow decision from its original inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from quant_data.bundle import read_bundle
from quant_research.__main__ import publish_report, source_identity
from quant_research.serde import InputError, iso_date
from .inputs import parse_schedule, parse_snapshot, read_document
from .ledger import DecisionLedger
from .readiness import verify_readiness


def recover_decision(*, ledger, session, bundle, config, schedule, snapshot, output,
                     readiness_inputs):
    """Export exact verified bytes, without planning, intake or ledger writes.

    A missing ledger or absent session permits ordinary fresh planning. Existing
    corrupt storage, missing originals or changed identities require review.
    """
    session = iso_date(str(session), 'recovery session').isoformat()
    ledger, output = Path(ledger), Path(output)
    if not ledger.exists():
        return False
    try:
        content = DecisionLedger(ledger).get(session)
    except InputError as error:
        if str(error) == 'no recorded decision for session':
            return False
        raise
    inputs = {'config': Path(config), 'schedule': Path(schedule), 'snapshot': Path(snapshot)}
    protected = {ledger.resolve(), Path(bundle).resolve(), *(path.resolve() for path in inputs.values())}
    protected.update(Path(path).resolve() for path in readiness_inputs.values() if path is not None)
    if output.resolve() in protected or output.exists():
        raise InputError('recovery output must be missing and differ from original inputs; review required')
    report = json.loads(content)
    declarations, hashes = {}, {}
    for name, path in inputs.items():
        declarations[name], raw = read_document(path)
        hashes[name] = hashlib.sha256(raw).hexdigest()
    dataset = read_bundle(bundle)
    hashes.update(data=dataset.data_sha256, manifest=dataset.manifest_sha256)
    for package in ('quant_session', 'quant_research', 'quant_data'):
        hashes[package+'_source'] = source_identity(package=package)['source_sha256']
    if any(report['source_hashes'].get(name) != value for name, value in hashes.items()):
        raise InputError('committed decision input/source identity mismatch; preserve originals for review')
    parse_schedule(declarations['schedule'])
    if parse_snapshot(declarations['snapshot'])['execution_session'].isoformat() != session:
        raise InputError('committed snapshot session mismatch; review required')
    verify_readiness(**readiness_inputs, planning_config=config, daily_bundle=bundle,
                     require_alpaca_feed=True)
    publish_report(output, content.decode('utf-8'))
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('ledger', 'bundle', 'config', 'schedule', 'snapshot', 'output',
                 'study-bundle', 'study-config', 'protocol', 'selection', 'holdout', 'registry'):
        parser.add_argument('--'+name, required=True, type=Path)
    parser.add_argument('--session', required=True)
    args = parser.parse_args(argv)
    try:
        readiness = {name: getattr(args, name) for name in ('protocol', 'selection', 'holdout', 'registry')}
        readiness.update(bundle=args.study_bundle, config=args.study_config)
        recovered = recover_decision(**{name: getattr(args, name) for name in
            ('ledger', 'session', 'bundle', 'config', 'schedule', 'snapshot', 'output')},
            readiness_inputs=readiness)
        print('recovered' if recovered else 'no_decision')
        return 0
    except (InputError, OSError, ValueError, KeyError, TypeError) as error:
        print(f'shadow recovery error: {error}; review required, preserve saved inputs', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
