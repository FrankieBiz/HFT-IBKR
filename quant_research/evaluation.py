"""Predeclared chronological SMA evaluation with separately released holdout."""

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import date
from decimal import Decimal, InvalidOperation

from .backtest import simulate
from .serde import InputError, canonical_json, fixed_decimal, iso_date, strict_keys, whole

METRIC = 'validation_return_under_2x_cost'
RESET = ('Each interval resets initial cash and starts flat; earlier sessions only warm '
         'causal SMA features. Capital, positions and receivables do not carry between intervals.')
CAVEAT = ('Embargo is a selection guard, not proof of independence. No supervised training, '
          'labels or CPCV are used. Results do not establish profitability or significance.')


@dataclass(frozen=True)
class Protocol:
    schema_version: int
    protocol_id: str
    development_start: date
    development_end: date
    validation_start: date
    validation_end: date
    holdout_start: date
    holdout_end: date
    embargo_sessions: int
    candidate_lookbacks: tuple[int, ...]
    selection_metric: str


def parse_protocol(raw, dataset):
    strict_keys(raw, Protocol.__dataclass_fields__, 'protocol')
    if type(raw['schema_version']) is not int or raw['schema_version'] != 1:
        raise InputError('unsupported protocol schema')
    if not isinstance(raw['protocol_id'], str) or not raw['protocol_id'].strip():
        raise InputError('protocol_id: nonempty text required')
    if raw['selection_metric'] != METRIC:
        raise InputError('unsupported selection metric')
    embargo = whole(raw['embargo_sessions'], 'embargo_sessions', minimum=0)
    candidates = raw['candidate_lookbacks']
    if not isinstance(candidates, list) or not candidates:
        raise InputError('candidate_lookbacks: nonempty list required')
    candidates = tuple(whole(n, 'candidate lookback', minimum=2) for n in candidates)
    if len(set(candidates)) != len(candidates):
        raise InputError('candidate lookbacks must be unique')
    sessions = [bar.session for bar in dataset.bars]
    dates, previous_end = {}, None
    for name in ('development', 'validation', 'holdout'):
        start = iso_date(raw[name + '_start'], name + '_start')
        end = iso_date(raw[name + '_end'], name + '_end')
        if start not in sessions or end not in sessions:
            raise InputError('interval boundaries must be supplied sessions')
        first, last = sessions.index(start), sessions.index(end)
        if last - first < 1:
            raise InputError('each interval requires at least two sessions')
        if first < max(candidates):
            raise InputError('each start requires maximum lookback prior sessions')
        if previous_end is not None and (first <= previous_end or first - previous_end - 1 < embargo):
            raise InputError('intervals must be disjoint chronological ranges with required embargo')
        previous_end = last
        dates[name + '_start'], dates[name + '_end'] = start, end
    return Protocol(1, raw['protocol_id'], **dates, embargo_sessions=embargo,
                    candidate_lookbacks=candidates, selection_metric=METRIC)


def digest(value):
    """SHA-256 of the repository's deterministic canonical JSON representation."""
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()


def _validated_protocol(protocol, dataset):
    if not isinstance(protocol, Protocol):
        raise InputError('parsed Protocol required')
    raw = asdict(protocol)
    raw['candidate_lookbacks'] = list(protocol.candidate_lookbacks)
    for name in ('development', 'validation', 'holdout'):
        for bound in ('start', 'end'):
            key = name + '_' + bound
            raw[key] = raw[key].isoformat()
    return parse_protocol(raw, dataset)


def identities(dataset, config, protocol, code_identity):
    if not isinstance(code_identity, str) or not code_identity.strip():
        raise InputError('code identity: nonempty string required')
    return {'protocol_digest': digest(asdict(protocol)), 'config_digest': digest(asdict(config)),
            'code_identity': code_identity, 'dataset_digest': dataset.data_sha256,
            'manifest_digest': dataset.manifest_sha256,
            # Bind the actual in-memory inputs too, so changed objects cannot reuse file digests.
            'bars_digest': digest([asdict(bar) for bar in dataset.bars]),
            'manifest_content_digest': digest(dataset.manifest)}


def _interval(dataset, config, protocol, name, lookback, strategy='trend'):
    end = getattr(protocol, name + '_end')
    bars = tuple(bar for bar in dataset.bars if bar.session <= end)
    candidate = replace(config, lookback=lookback)
    return [{'cost_multiplier': multiplier,
             'result': simulate(bars, candidate, getattr(protocol, name + '_start'), strategy, multiplier)}
            for multiplier in (1, 2, 5)]


@fixed_decimal
def evaluate_protocol(dataset, config, protocol, code_identity):
    protocol = _validated_protocol(protocol, dataset)
    report = {'schema_version': 1, 'mode': 'offline_chronological_validation',
              'strategy_validation': 'unproven', 'data_kind': dataset.manifest['kind'],
              'identities': identities(dataset, config, protocol, code_identity),
              'protocol_id': protocol.protocol_id,
              'intervals': {name: {'start': getattr(protocol, name + '_start'),
                                  'end': getattr(protocol, name + '_end')}
                            for name in ('development', 'validation')},
              'trial_count': len(protocol.candidate_lookbacks), 'selection_metric': METRIC,
              'selection_rationale': 'Maximum validation total_return at 2x costs; ties choose smaller lookback.',
              'interval_reset': RESET, 'evaluation_caveat': CAVEAT,
              'candidates': [],
              'benchmarks': {'cash': {'total_return': Decimal(0), 'cash_interest': 'excluded'},
                             'buy_hold': {name:_interval(dataset,config,protocol,name,max(protocol.candidate_lookbacks),'buy_hold')
                                          for name in ('development','validation')}}}
    for lookback in protocol.candidate_lookbacks:
        report['candidates'].append({'lookback': lookback,
                                    'development': _interval(dataset, config, protocol, 'development', lookback),
                                    'validation': _interval(dataset, config, protocol, 'validation', lookback)})
    report['selected_lookback'] = _selected(report['candidates'])
    return report


def _selected(candidates):
    def score(candidate):
        value = candidate['validation'][1]['result']['total_return']
        if not isinstance(value, (Decimal, str)):
            raise InputError('validation return: Decimal or decimal string required')
        try:
            value = Decimal(value)
        except InvalidOperation as error:
            raise InputError('invalid validation return') from error
        if not value.is_finite():
            raise InputError('validation return must be finite')
        return value, -candidate['lookback']
    return max(candidates, key=score)['lookback']


def freeze_selection(dataset, config, protocol, code_identity, report):
    protocol = _validated_protocol(protocol, dataset)
    current = identities(dataset, config, protocol, code_identity)
    if not isinstance(report, dict):
        raise InputError('validation report: object required')
    if (type(report.get('trial_count')) is not int
            or type(report.get('selected_lookback')) is not int):
        raise InputError('validation report: integer selection and trial count required')
    if report.get('identities') != current or report.get('trial_count') != len(protocol.candidate_lookbacks):
        raise InputError('validation report identities do not match current inputs')
    try:
        candidates = report['candidates']
        consistent = (isinstance(candidates, list)
                      and [c['lookback'] for c in candidates] == list(protocol.candidate_lookbacks)
                      and report['selected_lookback'] == _selected(candidates))
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise InputError('malformed validation candidate results') from error
    if not consistent:
        raise InputError('validation report selection is inconsistent')
    artifact = {'schema_version': 1, 'mode': 'frozen_chronological_selection',
                'protocol': asdict(protocol), 'identities': current,
                'data_kind': dataset.manifest['kind'],
                'selected_lookback': report['selected_lookback'],
                'trial_count': report['trial_count'], 'validation_report_digest': digest(report)}
    # Normalize dates/tuples for JSON round-trip comparisons.
    artifact = json.loads(canonical_json(artifact))
    artifact['integrity_digest'] = digest(artifact)
    return artifact


def verify_selection(artifact, dataset, config, protocol, code_identity):
    strict_keys(artifact, ('schema_version', 'mode', 'protocol', 'identities', 'data_kind',
                           'selected_lookback', 'trial_count', 'validation_report_digest', 'integrity_digest'),
                'frozen selection')
    if type(artifact['schema_version']) is not int or artifact['schema_version'] != 1:
        raise InputError('unsupported frozen selection schema')
    if artifact['mode'] != 'frozen_chronological_selection':
        raise InputError('invalid frozen selection mode')
    content = {k: v for k, v in artifact.items() if k != 'integrity_digest'}
    if digest(content) != artifact['integrity_digest']:
        raise InputError('frozen selection integrity mismatch')
    protocol = _validated_protocol(protocol, dataset)
    if (canonical_json(artifact['protocol']) != canonical_json(asdict(protocol))
            or artifact['identities'] != identities(dataset, config, protocol, code_identity)
            or artifact['data_kind'] != dataset.manifest['kind']):
        raise InputError('frozen selection input identities changed')
    selected = artifact['selected_lookback']
    if type(selected) is not int or selected not in protocol.candidate_lookbacks:
        raise InputError('invalid frozen candidate')
    if type(artifact['trial_count']) is not int or artifact['trial_count'] != len(protocol.candidate_lookbacks):
        raise InputError('invalid frozen trial count')
    for name in ('validation_report_digest', 'integrity_digest'):
        value = artifact[name]
        if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise InputError('invalid frozen artifact digest')
    return protocol


def _record_failure(registry, run_id, error):
    # If storage itself failed, the durable reservation still shows consumption.
    try:
        registry.fail(run_id, f'{type(error).__name__}: {error}')
    except InputError as storage_error:
        error.add_note(f'failure record could not be appended: {storage_error}; reservation remains consumed')


def evaluate_registered(dataset, config, protocol, code_identity, *, registry, run_id):
    protocol = _validated_protocol(protocol, dataset)
    registry.reserve_validation(run_id, identities(dataset, config, protocol, code_identity))
    try:
        report = evaluate_protocol(dataset, config, protocol, code_identity)
        report['run_id'] = run_id
        report['historical_validation_attempt_count'] = sum(
            r['kind'] == 'validation' and r['status'] == 'reserved' for r in registry.records())
        registry.complete(run_id, digest(report), result=report)
        return report
    except BaseException as error:
        _record_failure(registry, run_id, error)
        raise


@fixed_decimal
def release_holdout(artifact, dataset, config, protocol, code_identity, *, registry, run_id):
    protocol = verify_selection(artifact, dataset, config, protocol, code_identity)
    revealed = [bar.session.isoformat() for bar in dataset.bars
                if protocol.holdout_start <= bar.session <= protocol.holdout_end]
    registry.reserve_holdout(run_id, artifact['integrity_digest'], artifact['identities'],
                             scope=f"{dataset.manifest['kind']}:{config.symbol}", sessions=revealed)
    try:
        report = {'schema_version': 1, 'mode': 'offline_holdout_release',
                  'strategy_validation': 'unproven', 'data_kind': dataset.manifest['kind'],
                  'run_id': run_id, 'artifact_digest': artifact['integrity_digest'],
                  'selected_lookback': artifact['selected_lookback'], 'interval_reset': RESET,
                  'evaluation_caveat': CAVEAT,
                  'scenarios': _interval(dataset, config, protocol, 'holdout', artifact['selected_lookback']),
                  'benchmarks': {'cash': {'total_return':Decimal(0),'cash_interest':'excluded'},
                                 'buy_hold':_interval(dataset,config,protocol,'holdout',artifact['selected_lookback'],'buy_hold')}}
        registry.complete(run_id, digest(report), result=report)
        return report
    except BaseException as error:
        _record_failure(registry, run_id, error)
        raise
