"""Local runner heartbeat and independent offline freshness/deadline checks."""

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
import tempfile

from quant_research.serde import InputError, canonical_json, durable_sync, iso_date, read_json
from .ledger import DecisionLedger

STATUSES = ('starting', 'waiting', 'running', 'ok', 'failed', 'stopped')
MAX_EXPECTATIONS = 10000


def _instant(value):
    try:
        instant = datetime.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise InputError('health timestamp must be ISO with timezone') from error
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise InputError('health timestamp must have timezone')
    return instant


def _expectations(report):
    fields = {'schema_version', 'status', 'updated_at', 'expected_session', 'expected_deadline'}
    if (not isinstance(report, dict) or type(report.get('schema_version')) is not int
            or report['schema_version'] not in (1, 2)):
        raise InputError('invalid heartbeat schema')
    if report['schema_version'] == 2:
        fields.add('pending_expectations')
    if set(report) != fields or report['status'] not in STATUSES:
        raise InputError('invalid heartbeat schema')
    _instant(report['updated_at'])
    latest_session, latest_deadline = report['expected_session'], report['expected_deadline']
    if (latest_session is None) != (latest_deadline is None):
        raise InputError('incomplete recorded decision expectation')
    rows = report.get('pending_expectations', [])
    if not isinstance(rows, list) or len(rows) > MAX_EXPECTATIONS:
        raise InputError('invalid or excessive pending decision expectations')
    expected = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'session', 'deadline'}:
            raise InputError('invalid pending decision expectation')
        session = iso_date(row['session'], 'pending expected session').isoformat()
        if session in expected:
            raise InputError('duplicate pending decision session')
        expected[session] = _instant(row['deadline'])
    if latest_session is not None:
        iso_date(latest_session, 'recorded expected session')
        deadline = _instant(latest_deadline)
        if report['schema_version'] == 2 and expected.get(latest_session) != deadline:
            raise InputError('latest expectation differs from pending expectations')
        expected[latest_session] = deadline
    return expected


def write_heartbeat(path, status, *, now=None, expected_session=None, expected_deadline=None):
    """Atomically retain every expected session; no missed date is forgotten.

    Schema 1 migrates locally without discarding its recorded expectation. The
    bounded backlog is never silently pruned: each due date remains verifiable
    against ledger history, including after status recovery or a new session.
    """
    path = Path(path)
    now = now or datetime.now(timezone.utc)
    _instant(now.isoformat())
    if status not in STATUSES:
        raise InputError('unknown runner status')
    if (expected_session is None) != (expected_deadline is None):
        raise InputError('expected session and deadline must be provided together')
    expected = {}
    if path.exists():
        previous = read_json(path)
        expected = _expectations(previous)
        if expected_session is None:
            expected_session = previous['expected_session']
            expected_deadline = previous['expected_deadline']
    if expected_session is not None:
        iso_date(expected_session, 'expected session')
        deadline = _instant(expected_deadline)
        if expected_session in expected:
            # Neither a restart nor a cross-day clock update postpones a deadline.
            deadline = min(expected[expected_session], deadline)
        expected[expected_session] = deadline
        expected_deadline = deadline.isoformat()
    if len(expected) > MAX_EXPECTATIONS:
        raise InputError('pending expectation limit reached; reviewed archival required')
    report = {'schema_version': 2, 'status': status, 'updated_at': now.isoformat(),
              'expected_session': expected_session, 'expected_deadline': expected_deadline,
              'pending_expectations': [{'session': session, 'deadline': deadline.isoformat()}
                                       for session, deadline in sorted(expected.items())]}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.heartbeat-', delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(canonical_json(report))
            handle.flush()
            durable_sync(handle.fileno())
        os.replace(temporary, path)
    except OSError as error:
        raise InputError(f'heartbeat storage error: {error}') from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return report


def check_health(heartbeat, ledger, *, now=None, max_age_seconds=120, session=None, deadline=None):
    """No network or initialization: verify heartbeat and each due decision."""
    now = now or datetime.now(timezone.utc)
    issues = []
    expected = []
    try:
        _instant(now.isoformat())
        if type(max_age_seconds) is not int or max_age_seconds < 1:
            raise InputError('max heartbeat age must be a positive integer')
        report = read_json(heartbeat)
        expected.extend(_expectations(report).items())
        age = (now - _instant(report['updated_at'])).total_seconds()
        if age < 0:
            issues.append('heartbeat is in the future')
        elif age > max_age_seconds:
            issues.append('heartbeat is stale')
        if report['status'] in ('failed', 'stopped'):
            issues.append('runner status is ' + report['status'])
    except (InputError, TypeError, AttributeError) as error:
        issues.append(f'missing or invalid heartbeat: {error}')
    try:
        if (session is None) != (deadline is None):
            raise InputError('explicit session and deadline must be provided together')
        if session is not None:
            iso_date(session, 'expected session')
            expected.append((session, _instant(deadline)))
        for expected_session, expected_deadline in sorted(set(expected)):
            if now >= expected_deadline:
                try:
                    DecisionLedger(ledger).get(expected_session)
                except InputError as error:
                    issues.append(f'expected decision {expected_session} missing or invalid: {error}')
    except InputError as error:
        issues.append(str(error))
    return {'healthy': not issues, 'checked_at': now.isoformat(), 'issues': issues}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--path', required=True, type=Path)
    parser.add_argument('--status', required=True, choices=STATUSES)
    parser.add_argument('--expected-session')
    parser.add_argument('--expected-deadline')
    args = parser.parse_args(argv)
    try:
        write_heartbeat(args.path, args.status, expected_session=args.expected_session,
                        expected_deadline=args.expected_deadline)
        return 0
    except InputError as error:
        print(f'heartbeat error: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
