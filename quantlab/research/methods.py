"""Dependency-free, bounded research methods using observation-index intervals."""
import math
from itertools import combinations
from statistics import NormalDist, mean, stdev


def triple_barrier(closes, horizon=10, upper=.01, lower=.01):
    if type(horizon) is not int or horizon < 1 or not closes:
        raise ValueError('positive integer horizon and closes required')
    if any(not math.isfinite(x) or x <= 0 for x in [*closes, upper, lower]):
        raise ValueError('prices and barriers must be finite and positive')
    labels = []
    # The terminal observation has no forward outcome and is omitted.
    for start in range(len(closes) - 1):
        end, label = min(start + horizon, len(closes) - 1), 0
        for index in range(start + 1, end + 1):
            change = closes[index] / closes[start] - 1
            if not math.isfinite(change):
                raise ValueError('barrier return exceeds finite numeric range')
            if change >= upper or change <= -lower:
                end, label = index, 1 if change >= upper else -1
                break
        labels.append(dict(start=start, end=end, label=label,
                           return_value=(closes[end] - closes[start]) / closes[start]))
        labels[-1]['return'] = labels[-1].pop('return_value')
        if not math.isfinite(labels[-1]['return']):
            raise ValueError('barrier return exceeds finite numeric range')
    return labels


def _intervals(intervals):
    if not intervals or any(type(a) is not int or type(b) is not int or a < 0 or b < a
                            for a, b in intervals):
        raise ValueError('nonnegative inclusive integer intervals required')
    if any(intervals[i][0] >= intervals[i + 1][0] for i in range(len(intervals) - 1)):
        raise ValueError('interval starts must increase strictly')


def _purge(intervals, train, test, embargo):
    return [i for i in train if not any(intervals[i][0] <= intervals[j][1] + embargo and
                                        intervals[i][1] >= intervals[j][0] for j in test)]


def cpcv(intervals, groups=6, test_groups=2, embargo=0):
    _intervals(intervals)
    if any(type(x) is not int for x in (groups, test_groups, embargo)) or not 1 <= test_groups < groups <= len(intervals) or embargo < 0:
        raise ValueError('invalid CPCV dimensions or embargo')
    if math.comb(groups, test_groups) > 1000:
        raise ValueError('CPCV exceeds 1000 split bound')
    chunks = [list(range(i * len(intervals) // groups, (i + 1) * len(intervals) // groups)) for i in range(groups)]
    splits = []
    for number, selected in enumerate(combinations(range(groups), test_groups)):
        test = [i for group in selected for i in chunks[group]]
        train = [i for group in range(groups) if group not in selected for i in chunks[group]]
        splits.append(dict(id=number, train=_purge(intervals, train, test, embargo), test=test,
                           test_chunks={g: chunks[g] for g in selected}))
    return splits


def reconstruct_paths(splits, predictions, size):
    """Stitch each group's successive OOS occurrence into deterministic complete paths."""
    occurrences = {}
    for split in splits:
        for group, indices in split['test_chunks'].items():
            occurrences.setdefault(group, []).append((split['id'], indices))
    counts = {len(items) for items in occurrences.values()}
    if len(counts) != 1:
        raise ValueError('unbalanced group occurrences')
    paths = []
    for occurrence in range(counts.pop()):
        path = [None] * size
        for items in occurrences.values():
            split_id, indices = items[occurrence]
            for i in indices:
                value = predictions[split_id][i]
                if not math.isfinite(value) or path[i] is not None:
                    raise ValueError('invalid or duplicate prediction')
                path[i] = value
        if any(value is None for value in path):
            raise ValueError('incomplete path')
        paths.append(path)
    return paths


def walk_forward(intervals, minimum_train, test_size, embargo=0):
    _intervals(intervals)
    if any(type(x) is not int for x in (minimum_train, test_size, embargo)) or minimum_train < 1 or test_size < 1 or embargo < 0:
        raise ValueError('invalid walk-forward dimensions')
    result = []
    for start in range(minimum_train, len(intervals), test_size):
        test = list(range(start, min(start + test_size, len(intervals))))
        # A pre-test gap is conservative: no training outcome can touch holdout.
        train = [i for i in range(start) if intervals[i][1] + embargo < intervals[start][0]]
        result.append(dict(train=train, test=test))
    return result


def _normalized_returns(returns):
    if len(returns) < 3 or any(not math.isfinite(x) for x in returns):
        raise ValueError('at least three finite period returns required')
    scale = max(abs(x) for x in returns)
    if scale == 0:
        raise ValueError('zero return variance: statistic undefined')
    normalized = [x / scale for x in returns]
    deviation = stdev(normalized)
    if not math.isfinite(deviation) or deviation <= 1e-15:
        raise ValueError('zero or numerically unresolved return variance: statistic undefined')
    return normalized, deviation


def sharpe(returns):
    normalized, deviation = _normalized_returns(returns)
    result = mean(normalized) / deviation
    if not math.isfinite(result):
        raise ValueError('nonfinite Sharpe estimate')
    return result


def psr(returns, benchmark=0):
    normalized, deviation = _normalized_returns(returns)
    if not math.isfinite(benchmark):
        raise ValueError('finite benchmark required')
    average, n = mean(normalized), len(normalized)
    # Normalize before centering or taking powers to avoid overflow of finite inputs.
    centered = [x - average for x in normalized]
    try:
        variance = mean([x*x for x in centered])
        skew = mean([x**3 for x in centered]) / variance**1.5
        kurtosis = mean([x**4 for x in centered]) / variance**2
        sr = average / deviation
        denominator = 1 - skew * sr + (kurtosis - 1) * sr**2 / 4
        if not all(math.isfinite(x) for x in (variance, skew, kurtosis, sr, denominator)) or denominator <= 0:
            raise ValueError('invalid PSR asymptotic variance')
        statistic = (sr - benchmark) * math.sqrt((n - 1) / denominator)
        if not math.isfinite(statistic):
            raise ValueError('nonfinite PSR test statistic')
        return NormalDist().cdf(statistic)
    except (OverflowError, ZeroDivisionError) as error:
        raise ValueError('PSR exceeds supported numeric range') from error


def dsr(returns, trial_sharpe_variance, number_trials):
    if type(number_trials) is not int or number_trials < 1 or not math.isfinite(trial_sharpe_variance) or trial_sharpe_variance < 0:
        raise ValueError('explicit trial count and finite nonnegative Sharpe variance required')
    if number_trials == 1:
        benchmark = 0
    else:
        if trial_sharpe_variance == 0:
            raise ValueError('zero trial Sharpe variance: DSR undefined for multiple trials')
        normal, gamma = NormalDist(), .5772156649015329
        benchmark = math.sqrt(trial_sharpe_variance) * ((1-gamma)*normal.inv_cdf(1-1/number_trials) + gamma*normal.inv_cdf(1-1/(number_trials*math.e)))
    return dict(probability=psr(returns, benchmark), benchmark=benchmark, number_trials=number_trials,
                trial_sharpe_variance=trial_sharpe_variance)


def pbo(matrix, blocks=8):
    if type(blocks) is not int or blocks < 2 or blocks % 2 or len(matrix) < blocks * 3:
        raise ValueError('CSCV requires even blocks and at least three rows per block')
    width = len(matrix[0])
    if width < 2 or any(len(row) != width or any(not math.isfinite(x) for x in row) for row in matrix):
        raise ValueError('finite rectangular candidate matrix with at least two candidates required')
    if math.comb(blocks, blocks//2) > 1000:
        raise ValueError('CSCV exceeds 1000 split bound')
    chunks = [range(i*len(matrix)//blocks, (i+1)*len(matrix)//blocks) for i in range(blocks)]
    logits = []
    for selected in combinations(range(blocks), blocks//2):
        train = [i for b in selected for i in chunks[b]]
        test = [i for b in range(blocks) if b not in selected for i in chunks[b]]
        train_scores = [sharpe([matrix[i][j] for i in train]) for j in range(width)]
        winner = max(range(width), key=lambda j: (train_scores[j], -j))
        scores = [sharpe([matrix[i][j] for i in test]) for j in range(width)]
        # Average ranks avoid turning equal strategies into spurious evidence.
        rank = 1 + sum(s < scores[winner] for s in scores) + (sum(s == scores[winner] for s in scores)-1)/2
        relative = rank/(width+1)
        logits.append(math.log(relative/(1-relative)))
    return dict(pbo=sum(x <= 0 for x in logits)/len(logits), logits=logits,
                splits=len(logits), method='CSCV', ties='lowest candidate index in training; average OOS rank')
