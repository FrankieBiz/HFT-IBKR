"""Offline authentication of immutable study evidence before operator workflows."""

import argparse
from contextlib import closing
from dataclasses import asdict, replace
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys

from quant_data.bundle import read_bundle
from quant_data.alpaca import DATA_URL, FEEDS
from quant_research.__main__ import source_identity
from quant_research.config import parse_config
from quant_research.evaluation import digest, freeze_selection, parse_protocol, verify_selection
from quant_research.serde import InputError, canonical_json, decimal_value, read_json, _pairs


def _result_metrics(result):
    if not isinstance(result, dict):
        raise InputError('evidence result must be an object')
    for key in ('total_return', 'maximum_drawdown'):
        value = result.get(key)
        if not isinstance(value, str) or len(value) > 64:
            raise InputError(f'evidence {key}: bounded decimal string required')
        try:
            number = Decimal(value)
        except InvalidOperation as error:
            raise InputError(f'evidence {key}: invalid decimal') from error
        if not number.is_finite() or (key == 'total_return' and number < -1) or (
                key == 'maximum_drawdown' and not 0 <= number <= 1):
            raise InputError(f'evidence {key}: nonfinite or impossible metric')
    for key in ('trade_count', 'rejection_count', 'evaluated_sessions', 'exposure_sessions'):
        if key == 'trade_count' or key in result:
            if type(result.get(key)) is not int or result[key] < 0:
                raise InputError(f'evidence {key}: nonnegative integer required')
    if ('evaluated_sessions' in result and 'exposure_sessions' in result
            and result['exposure_sessions'] > result['evaluated_sessions']):
        raise InputError('evidence exposure sessions exceed interval')
    for key in ('fees_paid', 'price_friction', 'modeled_execution_cost'):
        if key in result:
            decimal_value(result[key], 'evidence ' + key)
    for mark in [result.get('final', {}), *result.get('equity_curve', [])]:
        if not isinstance(mark, dict):
            raise InputError('evidence NAV mark must be an object')
        for key in ('cash', 'receivables', 'nav', 'open_nav'):
            if key in mark:
                decimal_value(mark[key], 'evidence ' + key)
        if 'shares' in mark and (type(mark['shares']) is not int or mark['shares'] < 0):
            raise InputError('evidence shares: nonnegative integer required')


def _columns(rows):
    if (not isinstance(rows, list) or len(rows) != 3
            or any(not isinstance(row, dict) or type(row.get('cost_multiplier')) is not int for row in rows)
            or sorted(row['cost_multiplier'] for row in rows) != [1, 2, 5]):
        raise InputError('evidence requires exactly the 1x, 2x and 5x cost columns')
    for row in rows:
        _result_metrics(row.get('result'))
    return {row['cost_multiplier']: row['result'] for row in rows}


def _stored_result(connection, run_id, kind, identities, artifact_digest):
    events = connection.execute('SELECT * FROM events WHERE run_id=? ORDER BY sequence', (run_id,)).fetchall()
    if len(events) != 2 or [row['status'] for row in events] != ['reserved', 'completed']:
        raise InputError(f'{kind} requires one reserved and completed registry event')
    for row in events:
        if (row['kind'] != kind or row['artifact_digest'] != artifact_digest
                or json.loads(row['identities'], object_pairs_hook=_pairs) != identities or row['error'] is not None):
            raise InputError(f'{kind} registry event identities mismatch')
    payloads = connection.execute('SELECT payload FROM result_payloads WHERE run_id=?', (run_id,)).fetchall()
    if len(payloads) != 1:
        raise InputError(f'{kind} original stored payload required')
    payload = payloads[0]['payload']
    report = json.loads(payload, object_pairs_hook=_pairs)
    if (canonical_json(report) != payload
            or hashlib.sha256(payload.encode()).hexdigest() != events[-1]['result_digest']):
        raise InputError(f'{kind} stored report integrity mismatch')
    if not isinstance(report, dict) or report.get('run_id') != run_id:
        raise InputError(f'{kind} report run identity mismatch')
    return report


def _price_feed(dataset):
    source = dataset.manifest.get('source')
    prefix = 'Offline intake v1: '
    if not isinstance(source, str) or not source.startswith(prefix):
        raise InputError('operational price feed requires declared Alpaca intake provenance')
    audit = json.loads(source[len(prefix):], object_pairs_hook=_pairs)
    reference = audit['metadata']['sources']['prices']['reference']
    if not isinstance(reference, str) or reference.split(' ', 1)[0] != DATA_URL + '/v2/stocks/bars':
        raise InputError('operational price feed requires Alpaca stock bars provenance')
    feeds = re.findall(r'(?<!\S)feed=([^\s;]+)', reference)
    if len(feeds) != 1 or feeds[0] not in FEEDS:
        raise InputError('operational price feed must be exactly one declared iex or sip feed')
    return feeds[0]


def verify_readiness(*, bundle, config, protocol, selection, holdout, registry, planning_config=None,
                     require_alpaca_feed=False, daily_bundle=None):
    """Return verified selected config and verdict; all evidence reads stay local.

    Frozen identities belong to the immutable original study bundle, base config
    and current research source. Optional daily data must retain the study's feed.
    The registry is opened in read-only mode and never initialized or migrated.
    """
    try:
        dataset = read_bundle(bundle)
        base = parse_config(read_json(config))
        parsed_protocol = parse_protocol(read_json(protocol), dataset)
        artifact, report = read_json(selection), read_json(holdout)
        code = source_identity()['source_sha256']
        verify_selection(artifact, dataset, base, parsed_protocol, code)
        if dataset.manifest['kind'] != 'historical' or artifact['data_kind'] != 'historical':
            raise InputError('readiness requires historical study provenance')
        if (type(report.get('schema_version')) is not int or report.get('schema_version') != 1 or report.get('mode') != 'offline_holdout_release'
                or report.get('data_kind') != 'historical'
                or type(report.get('selected_lookback')) is not int
                or report['selected_lookback'] != artifact['selected_lookback']
                or report.get('artifact_digest') != artifact['integrity_digest']):
            raise InputError('holdout does not match frozen historical selection')
        path = Path(registry).resolve()
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute('PRAGMA query_only=ON')
            connection.execute('BEGIN')
            frozen = connection.execute('SELECT * FROM frozen_selections WHERE artifact_digest=?',
                                        (artifact['integrity_digest'],)).fetchone()
            if (frozen is None or frozen['artifact'] != canonical_json(artifact)
                    or frozen['stable_identity'] != digest(artifact['identities'])):
                raise InputError('selection is not the original registered freeze')
            validation = _stored_result(connection, frozen['validation_run_id'], 'validation', artifact['identities'], None)
            if (validation.get('mode') != 'offline_chronological_validation'
                    or validation.get('data_kind') != 'historical'
                    or digest(validation) != artifact['validation_report_digest']):
                raise InputError('original validation report does not match freeze')
            for candidate in validation['candidates']:
                for interval in ('development', 'validation'):
                    _columns(candidate[interval])
            for interval in ('development', 'validation'):
                _columns(validation['benchmarks']['buy_hold'][interval])
            if freeze_selection(dataset, base, parsed_protocol, code, validation) != artifact:
                raise InputError('selection differs from original validation')
            stored_holdout = _stored_result(connection, report['run_id'], 'holdout', artifact['identities'], artifact['integrity_digest'])
            if canonical_json(stored_holdout) != canonical_json(report):
                raise InputError('holdout file differs from original completed registry payload')
            claim = connection.execute('SELECT * FROM holdout_claims WHERE artifact_digest=?',
                                       (artifact['integrity_digest'],)).fetchone()
            if (claim is None or claim['run_id'] != report['run_id']
                    or claim['stable_identity'] != frozen['stable_identity']):
                raise InputError('holdout release claim mismatch')
            released = connection.execute('SELECT session FROM released_holdout_sessions WHERE scope=? AND run_id=? ORDER BY session',
                                          ('historical:SPY', report['run_id'])).fetchall()
            expected = [b.session.isoformat() for b in dataset.bars
                        if parsed_protocol.holdout_start <= b.session <= parsed_protocol.holdout_end]
            if [row['session'] for row in released] != expected:
                raise InputError('holdout released-session identity mismatch')
        trend, benchmark = _columns(report['scenarios'])[2], _columns(report['benchmarks']['buy_hold'])[2]
        tr, td = Decimal(trend['total_return']), Decimal(trend['maximum_drawdown'])
        br, bd = Decimal(benchmark['total_return']), Decimal(benchmark['maximum_drawdown'])
        outcome = 'DOMINATED' if td >= bd else ('DOMINATES' if tr >= br else 'RISK_REDUCING')
        if outcome == 'DOMINATED' or tr < 0:
            raise InputError('holdout verdict does not proceed_to_shadow')
        selected = replace(base, lookback=artifact['selected_lookback'])
        if planning_config is not None and parse_config(read_json(planning_config)) != selected:
            raise InputError('planning config may change only the frozen selected lookback')
        result = {'status': 'ready_for_shadow', 'proceed_to_shadow': True, 'outcome': outcome,
                'selected_lookback': selected.lookback, 'artifact_digest': artifact['integrity_digest'],
                'planning_config': json.loads(canonical_json(asdict(selected)))}
        if require_alpaca_feed or daily_bundle is not None:
            result['price_feed'] = _price_feed(dataset)
            if daily_bundle is not None:
                daily = read_bundle(daily_bundle)
                if daily.manifest['kind'] != 'historical':
                    raise InputError('operator workflows require historical daily provenance')
                if _price_feed(daily) != result['price_feed']:
                    raise InputError('daily price feed mismatch with authenticated study; preserve inputs for review')
        return result
    except (OSError, sqlite3.Error, ValueError, KeyError, IndexError, TypeError, AttributeError, UnicodeError, RecursionError, ArithmeticError) as error:
        if isinstance(error, InputError):
            raise
        raise InputError(f'invalid or missing readiness evidence: {error}') from error


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('bundle', 'config', 'protocol', 'selection', 'holdout', 'registry'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--planning-config', type=Path)
    parser.add_argument('--config-out', type=Path)
    parser.add_argument('--daily-bundle', type=Path)
    parser.add_argument('--feed-only', action='store_true', help='Authenticate evidence and print its Alpaca price feed.')
    args = parser.parse_args(argv)
    try:
        result = verify_readiness(**{name: getattr(args, name) for name in (
            'bundle', 'config', 'protocol', 'selection', 'holdout', 'registry', 'planning_config', 'daily_bundle')},
            require_alpaca_feed=args.feed_only)
        if args.config_out is not None:
            # Never overwrite supplied evidence or a custom config.
            protected = [getattr(args, name).resolve() for name in ('bundle', 'config', 'protocol', 'selection', 'holdout', 'registry')]
            if args.config_out.resolve() in protected:
                raise InputError('config output cannot replace study evidence')
            from quant_research.__main__ import publish_report
            content = canonical_json(result['planning_config'])
            if args.config_out.exists():
                if parse_config(read_json(args.config_out)) != parse_config(result['planning_config']):
                    raise InputError('existing selected config differs from verified freeze')
            else:
                publish_report(args.config_out, content)
        print(result['price_feed'] if args.feed_only else canonical_json(result),
              end='\n' if args.feed_only else '')
        return 0
    except InputError as error:
        print(f'readiness error: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
