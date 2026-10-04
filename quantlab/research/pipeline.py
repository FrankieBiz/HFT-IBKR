"""Small reproducible MA sweep with isolated holdout portfolios."""
import hashlib
import json
from dataclasses import asdict, replace
from statistics import variance
from ..data import bar_dict
from ..simulation import simulate
from .methods import triple_barrier, walk_forward, cpcv, sharpe, psr, dsr, pbo
from .registry import Registry


def _diagnostic(function, *args):
    try:
        return dict(status='defined', value=function(*args))
    except ValueError as error:
        return dict(status='undefined', reason=str(error))


def _checked_simulate(bars, config):
    result = simulate(bars, config)
    if result['summary']['state'] != 'READY' or any(
            row.get('valuation_valid') is not True for row in result['equity']):
        raise ValueError('simulation halted or contains invalid valuations')
    return result


def evaluate(bars, config, candidates, registry_path, provenance):
    """Evaluate [(fast, slow), ...] offline; all returns are per bar, unannualized."""
    if len(bars) < 120 or len({b.symbol for b in bars}) != 1:
        raise ValueError('research requires >=120 bars for exactly one symbol')
    if not candidates or len(candidates) > 32:
        raise ValueError('provide 1 to 32 candidates')
    provenance = dict(provenance, bars_sha256=hashlib.sha256(json.dumps([bar_dict(b) for b in bars], sort_keys=True).encode()).hexdigest())
    labels = triple_barrier([b.close for b in bars], horizon=5)
    intervals = [(label['start'], label['end']) for label in labels] + [(len(bars)-1, len(bars)-1)]
    folds = walk_forward(intervals, len(bars)//2, max(20, len(bars)//6), embargo=2)
    matrix = [[] for _ in bars]
    candidate_results, training = [], {}
    with Registry(registry_path) as registry:
        historical_trials = len(registry.runs())
        for index, pair in enumerate(candidates):
            identity = registry.start(dict(base=asdict(config), candidate=list(pair)), provenance)
            try:
                fast, slow = pair
                candidate = replace(config, fast_window=fast, slow_window=slow)
                scores = []
                for fold in folds:
                    # Training outcomes never touch the test. No training portfolio is carried forward.
                    sample = [bars[i] for i in fold['train']]
                    try:
                        scores.append(_diagnostic(sharpe, _checked_simulate(sample, candidate)['returns']))
                    except ValueError as error:
                        scores.append(dict(status='undefined', reason=str(error)))
                training[index] = scores
                returns = _checked_simulate(bars, candidate)['returns']
                for row, value in zip(matrix, returns):
                    row.append(value)
                record = dict(id=identity, candidate=[fast, slow], status='completed',
                              sharpe=_diagnostic(sharpe, returns))
                registry.finish(identity, 'completed', record)
                candidate_results.append(record)
            except Exception as error:
                registry.finish(identity, 'failed', {'error': str(error)})
                candidate_results.append(dict(id=identity, candidate=list(pair), status='failed', reason=str(error)))
        valid = [i for i, row in enumerate(candidate_results) if row['status'] == 'completed']
        holdout, selected_folds = [], []
        for number, fold in enumerate(folds):
            eligible = [i for i in training if training[i][number]['status'] == 'defined']
            if not eligible:
                selected_folds.append(dict(fold=number, status='undefined', reason='no candidate has defined training Sharpe'))
                continue
            winner = max(eligible, key=lambda i: (training[i][number]['value'], -i))
            chosen = replace(config, fast_window=candidates[winner][0], slow_window=candidates[winner][1])
            try:
                result = _checked_simulate([bars[i] for i in fold['test']], chosen)
            except ValueError as error:
                selected_folds.append(dict(fold=number, candidate_index=winner, status='undefined', reason=str(error),
                                           training_sharpe=training[winner][number]['value']))
                continue
            holdout.extend(result['returns'])
            selected_folds.append(dict(fold=number, candidate_index=winner, train=fold['train'], test=fold['test'],
                                       training_sharpe=training[winner][number]['value'], returns=result['returns'],
                                       summary=result['summary']))
        trial_scores = [r['sharpe']['value'] for r in candidate_results if r['status']=='completed' and r['sharpe']['status']=='defined']
        dsr_result = dict(status='undefined', reason='all attempted candidates need defined comparable trial Sharpe estimates')
        complete_holdout = all('returns' in fold for fold in selected_folds)
        if historical_trials:
            dsr_result = dict(status='undefined', reason='registry contains earlier campaign trials; comparable historical Sharpe variance is not reconstructed')
        elif len(trial_scores) == len(candidates):
            selected = max(range(len(trial_scores)), key=lambda i: (trial_scores[i], -i))
            selected_returns = [row[selected] for row in matrix]
            dsr_result = _diagnostic(dsr, selected_returns, variance(trial_scores) if len(trial_scores)>1 else 0, len(candidates))
            dsr_result['selected_candidate_index'] = selected
        dsr_result.update(scope='full_history_selected_candidate', observations=len(bars),
                          horizon_start=bars[0].timestamp.isoformat(), horizon_end=bars[-1].timestamp.isoformat(),
                          number_trials=historical_trials + len(candidates))
        output = dict(schema_version=1, mode='offline_research', provenance=provenance, config=asdict(config), candidates=[list(p) for p in candidates],
                      campaign_trial_count=historical_trials + len(candidates),
                      trials=candidate_results, candidate_matrix_columns=valid, candidate_returns=matrix,
                      labels=labels, walk_forward=selected_folds, holdout_returns=holdout,
                      psr=(_diagnostic(psr, holdout) if complete_holdout else dict(status='undefined', reason='one or more holdout folds invalid')), dsr=dsr_result,
                      pbo=_diagnostic(pbo, matrix), cpcv_splits=cpcv(intervals, embargo=2),
                      limitations=[
                          'CSCV PBO uses full candidate returns and is separate from CPCV splitting.',
                          'CPCV splits and reconstruction utility supplied; pipeline does not fit CPCV models or claim CPCV portfolio paths.',
                          'Holdout folds reset to cash with cold strategy history; open positions are marked, not liquidated.',
                          'Disjoint holdout returns describe repeated fixed-capital experiments, not one continuous investable portfolio.',
                          'PSR assumes asymptotic moments and does not correct serial dependence.',
                          'The registry defines a campaign; DSR is undefined when earlier campaign trials exist without reconstructed comparable variance. Unrecorded trials remain unknown.',
                          'CSCV rearranges return observations and does not replay execution at block boundaries.',
                          'Costs are illustrative; liquidity, corporate actions, survivorship and market impact need external validation.',
                          'Diagnostics and manual review states never authorize or activate live trading.'])
    json.dumps(output, allow_nan=False)
    return output
