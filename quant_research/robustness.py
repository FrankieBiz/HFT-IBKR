"""Offline chronological and paired path diagnostics; never select a study holdout."""

import hashlib
import random
from dataclasses import asdict, replace
from decimal import Decimal

from .backtest import simulate
from .evaluation import RESET, _validated_protocol, digest, identities
from .serde import InputError, fixed_decimal, whole

ZERO = Decimal(0)
ONE = Decimal(1)
MAX_FOLDS = 128
MAX_SAMPLES = 10000
MAX_PATH_STEPS = 5000000


def _bounded(value, name, minimum, maximum):
    result = whole(value, name, minimum=minimum)
    if result > maximum:
        raise InputError(f'{name}: maximum is {maximum}')
    return result


@fixed_decimal
def net_daily_returns(equity_curve, initial_cash):
    """Close NAV changes including first-day execution costs against initial cash."""
    previous = initial_cash
    if not isinstance(previous, Decimal) or not previous.is_finite() or previous <= 0:
        raise InputError('initial cash must be a finite positive Decimal')
    result = []
    for mark in equity_curve:
        nav = mark['nav']
        if not isinstance(nav, Decimal) or not nav.is_finite() or nav <= 0:
            raise InputError('equity marks must be finite positive Decimals')
        result.append(nav / previous - ONE)
        previous = nav
    if not result:
        raise InputError('nonempty equity curve required')
    return tuple(result)


@fixed_decimal
def path_metrics(returns):
    """Compounded return and closing-mark drawdown, with the initial unit NAV peak."""
    nav = peak = ONE
    maximum = ZERO
    if not returns:
        raise InputError('nonempty return path required')
    for value in returns:
        if not isinstance(value, Decimal) or not value.is_finite() or value < -ONE:
            raise InputError('return path requires finite Decimals >= -1')
        nav *= ONE + value
        peak = max(peak, nav)
        maximum = max(maximum, (peak - nav) / peak)
    return {'total_return': nav - ONE, 'maximum_drawdown': maximum}


def _percentiles(values):
    ordered = sorted(values)
    result = {}
    for name, numerator in (('p05', 5), ('p50', 50), ('p95', 95)):
        position = Decimal(len(ordered) - 1) * numerator / 100
        lower = int(position)
        upper = min(lower + 1, len(ordered) - 1)
        result[name] = ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
    return result


@fixed_decimal
def paired_block_resampling(trend, buy_hold, *, block_size=20, samples=500,
                            seed=0, segment_lengths=None):
    """Noncircular moving blocks with identical sampled indices for both paths."""
    block_size = _bounded(block_size, 'block_size', 1, 100000)
    samples = _bounded(samples, 'samples', 1, MAX_SAMPLES)
    seed = _bounded(seed, 'seed', 0, 2**32 - 1)
    if len(trend) != len(buy_hold) or not trend:
        raise InputError('paired nonempty paths of equal length required')
    if samples * len(trend) > MAX_PATH_STEPS:
        raise InputError('resampling exceeds bounded path work')
    lengths = tuple(segment_lengths) if segment_lengths is not None else (len(trend),)
    if any(type(n) is not int or n < block_size for n in lengths) or sum(lengths) != len(trend):
        raise InputError('block size must fit each nonempty reset segment')
    # Validate observed inputs before generating any paths.
    observed = {'trend': path_metrics(trend), 'buy_hold': path_metrics(buy_hold)}
    starts, offset = [], 0
    for length in lengths:
        starts.extend(range(offset, offset + length - block_size + 1))
        offset += length
    generator = random.Random(seed)
    checksum = hashlib.sha256()
    values = {name: {metric: [] for metric in ('total_return', 'maximum_drawdown')}
              for name in ('trend', 'buy_hold', 'difference')}
    for _ in range(samples):
        indices = []
        while len(indices) < len(trend):
            start = starts[generator.randrange(len(starts))]
            indices.extend(range(start, start + min(block_size, len(trend) - len(indices))))
        for index in indices:
            checksum.update(index.to_bytes(8, 'big'))
        trend_metrics = path_metrics(tuple(trend[index] for index in indices))
        hold_metrics = path_metrics(tuple(buy_hold[index] for index in indices))
        for metric in trend_metrics:
            values['trend'][metric].append(trend_metrics[metric])
            values['buy_hold'][metric].append(hold_metrics[metric])
            values['difference'][metric].append(trend_metrics[metric] - hold_metrics[metric])
    return {
        'method': 'paired_noncircular_moving_blocks', 'cost_multiplier': 2,
        'block_size': block_size, 'samples': samples, 'seed': seed,
        'sampled_sessions': len(trend), 'segment_lengths': list(lengths),
        'eligible_block_count': len(starts), 'indices_digest': checksum.hexdigest(),
        'index_encoding': 'sample-major unsigned 8-byte big-endian indices; SHA-256',
        'percentile_method': 'linear interpolation at (samples - 1) * percentile',
        'difference_direction': 'trend minus matched buy-and-hold; negative drawdown difference is lower drawdown',
        'observed': observed,
        **{name: {metric: _percentiles(observations) for metric, observations in metrics.items()}
           for name, metrics in values.items()},
    }


def _summary(result):
    return {key: value for key, value in result.items()
            if key not in ('trades', 'rejections', 'equity_curve', 'unpaid_distributions')}


def _ranges(dataset, protocol):
    return [(name, next(i for i, bar in enumerate(dataset.bars)
                        if bar.session == getattr(protocol, name + '_start')),
             next(i for i, bar in enumerate(dataset.bars)
                  if bar.session == getattr(protocol, name + '_end')))
            for name in ('development', 'validation')]


def _fold_boundaries(ranges, train_sessions, test_sessions, embargo_sessions):
    allowed = [i for _, first, last in ranges for i in range(first, last + 1)]
    if len(allowed) <= train_sessions:
        raise InputError('insufficient development/validation history for initial training')
    earliest = allowed[train_sessions - 1] + embargo_sessions + 1
    folds = []
    for name, first, last in ranges:
        test_start = max(first, earliest)
        while test_start + test_sessions - 1 <= last:
            test_end = test_start + test_sessions - 1
            train_end = test_start - embargo_sessions - 1
            train_ranges = [(period, start, min(end, train_end))
                            for period, start, end in ranges if start <= train_end]
            count = sum(end - start + 1 for _, start, end in train_ranges)
            if count >= train_sessions:
                folds.append((train_ranges, name, test_start, test_end))
            test_start = test_end + 1
    if not folds:
        raise InputError('insufficient development/validation history for next test interval')
    return folds


@fixed_decimal
def run_robustness(dataset, config, protocol, code_identity, *, train_sessions=252,
                   test_sessions=63, embargo_sessions=None, folds=None,
                   block_size=20, samples=500, seed=0):
    """Expanding chronological selection and independent next-interval diagnostics."""
    protocol = _validated_protocol(protocol, dataset)
    train_sessions = _bounded(train_sessions, 'train_sessions', 2, 100000)
    test_sessions = _bounded(test_sessions, 'test_sessions', 2, 100000)
    embargo = protocol.embargo_sessions if embargo_sessions is None else _bounded(
        embargo_sessions, 'embargo_sessions', 0, 100000)
    if embargo < protocol.embargo_sessions:
        raise InputError('diagnostic embargo cannot weaken protocol embargo')
    fold_limit = None if folds is None else _bounded(folds, 'folds', 1, MAX_FOLDS)
    block_size = _bounded(block_size, 'block_size', 1, 100000)
    samples = _bounded(samples, 'samples', 1, MAX_SAMPLES)
    seed = _bounded(seed, 'seed', 0, 2**32 - 1)
    ranges = _ranges(dataset, protocol)
    boundaries = _fold_boundaries(ranges, train_sessions, test_sessions, embargo)
    available = len(boundaries)
    if fold_limit is not None:
        if fold_limit > available:
            raise InputError('requested folds exceed available chronological folds')
        boundaries = boundaries[:fold_limit]
    if len(boundaries) > MAX_FOLDS:
        raise InputError('too many folds; request an explicit bounded --folds limit')
    lengths = [end - start + 1 for _, _, start, end in boundaries]
    if block_size > min(lengths):
        raise InputError('block size must fit every test interval')
    if sum(lengths) * samples > MAX_PATH_STEPS:
        raise InputError('resampling exceeds bounded path work')
    simulation_steps = sum(sum(end + 1 for _, _, end in training) * len(protocol.candidate_lookbacks)
                           + (last + 1) * 6 for training, _, _, last in boundaries)
    if simulation_steps > MAX_PATH_STEPS:
        raise InputError('walk-forward exceeds bounded simulation work')
    settings = dict(train_sessions=train_sessions, test_sessions=test_sessions,
                    embargo_sessions=embargo, folds=fold_limit, block_size=block_size,
                    samples=samples, seed=seed, candidate_lookbacks=list(protocol.candidate_lookbacks),
                    selection_cost_multiplier=2, test_cost_multipliers=[1, 2, 5])
    # These bind all inputs; full-input hashes may change when excluded holdout bytes change.
    bound_identities = identities(dataset, config, protocol, code_identity)
    reports, trend_returns, hold_returns = [], [], []
    for ordinal, (training, name, first, last) in enumerate(boundaries, 1):
        candidates = []
        for lookback in protocol.candidate_lookbacks:
            segments, combined = [], ONE
            for period, start, end in training:
                result = simulate(dataset.bars[:end + 1], replace(config, lookback=lookback),
                                  dataset.bars[start].session, 'trend', 2)
                combined *= ONE + result['total_return']
                segments.append({'period': period, 'result': _summary(result)})
            candidates.append({'lookback': lookback, 'total_return_2x': combined - ONE,
                               'segments': segments})
        selected = max(candidates, key=lambda c: (c['total_return_2x'], -c['lookback']))['lookback']
        scenarios = []
        for multiplier in (1, 2, 5):
            candidate = replace(config, lookback=selected)
            prefix = dataset.bars[:last + 1]
            trend = simulate(prefix, candidate, dataset.bars[first].session, 'trend', multiplier)
            hold = simulate(prefix, candidate, dataset.bars[first].session, 'buy_hold', multiplier)
            scenarios.append({'cost_multiplier': multiplier, 'trend': _summary(trend),
                              'buy_hold': _summary(hold)})
            if multiplier == 2:
                trend_returns.extend(net_daily_returns(trend['equity_curve'], config.initial_cash))
                hold_returns.extend(net_daily_returns(hold['equity_curve'], config.initial_cash))
        reports.append({'fold': ordinal,
                        'training': {'start': dataset.bars[training[0][1]].session,
                                     'end': dataset.bars[training[-1][2]].session,
                                     'sessions': sum(end - start + 1 for _, start, end in training),
                                     'segments': [{'period': period, 'start': dataset.bars[start].session,
                                                   'end': dataset.bars[end].session, 'sessions': end - start + 1}
                                                  for period, start, end in training]},
                        'test': {'period': name, 'start': dataset.bars[first].session,
                                 'end': dataset.bars[last].session, 'sessions': last - first + 1},
                        'candidates': candidates, 'selected_lookback': selected,
                        'selection_frozen_before': dataset.bars[first].session,
                        'scenarios': scenarios})
    report = {
        'schema_version': 1, 'mode': 'offline_robustness_diagnostics',
        'strategy_validation': 'unproven', 'data_kind': dataset.manifest['kind'],
        'protocol_id': protocol.protocol_id, 'identities': bound_identities,
        'config': asdict(config), 'protocol': asdict(protocol), 'settings': settings,
        'interval_reset': RESET,
        'selection_rationale': 'Maximum compounded prior training-segment return at 2x costs; ties choose smaller lookback. Freeze before next test.',
        'walk_forward': {'fold_count': len(reports), 'available_fold_count': available,
                         'candidate_trial_count': len(reports) * len(protocol.candidate_lookbacks),
                         'tested_sessions': sum(lengths),
                         'untested_sessions': sum(end - start + 1 for _, start, end in ranges) - sum(lengths),
                         'folds': reports},
        'resampling': paired_block_resampling(tuple(trend_returns), tuple(hold_returns),
                                              block_size=block_size, samples=samples, seed=seed,
                                              segment_lengths=lengths),
        'limitations': [
            'Development and validation only; no final holdout observations enter selection, metrics or resampling. Full provenance hashes cover the complete supplied input.',
            'Diagnostics cannot select or change the final study lookback or authorize holdout reuse.',
            'Known historical dates and repeated candidate trials remain subject to selection bias; these are scenario diagnostics, not success probabilities or significance tests.',
            'Training and test intervals reset cash, positions and receivables. Gap and embargo sessions only warm causal features; incomplete test tails are excluded. Untested counts also include initial training and any explicit fold limit.',
            'Resampling compounds next-test net closing-NAV returns across reset intervals. Blocks never cross fold boundaries; partial last blocks are truncated. Closing-mark drawdowns omit intraday loss paths and do not rerun risk controls.',
            'Matched buy-and-hold uses the same capital, allocation, costs and entry risk rules; it is a bounded sleeve comparator.',
            'Flat execution-cost assumptions are uncalibrated. Cash yield, taxes, settlement delays, market impact dynamics and independently verified data quality remain open.',
        ],
    }
    report['integrity_digest'] = digest(report)
    return report
