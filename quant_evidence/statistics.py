"""Exact moving-block mean diagnostic, not a calibrated or studentized test."""

from fractions import Fraction
import random

from quant_research.serde import InputError

RESAMPLES = 10000
SEED = 20261005
BLOCK_LENGTHS = (5, 1, 10)


def fifth_percentile(sorted_values):
    if not sorted_values:
        raise InputError('percentile requires observations')
    position = Fraction(len(sorted_values) - 1, 20)
    index = position.numerator // position.denominator
    fraction = position - index
    if fraction == 0:
        return Fraction(sorted_values[index])
    return sorted_values[index] * (1 - fraction) + sorted_values[index + 1] * fraction


def _draw_total(prefix, block_length, rng):
    count = len(prefix) - 1
    remaining, total = count, 0
    while remaining:
        start = rng.randrange(count - block_length + 1)
        take = min(block_length, remaining)
        total += prefix[start + take] - prefix[start]
        remaining -= take
    return total


def bootstrap_bound(values, block_length):
    if (not values or type(block_length) is not int or not 1 <= block_length <= len(values)
            or any(type(value) is not int for value in values)):
        raise InputError('bootstrap requires integer outcomes and a valid block length')
    prefix = [0]
    for value in values:
        prefix.append(prefix[-1] + value)
    rng = random.Random(SEED)
    totals = sorted(_draw_total(prefix, block_length, rng) for _ in range(RESAMPLES))
    return fifth_percentile(totals) / len(values)


def summary(values):
    cumulative = peak = drawdown = 0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        drawdown = max(drawdown, peak - cumulative)
    return {
        'total_net_pnl': sum(values), 'mean_daily_net_pnl': Fraction(sum(values), len(values)),
        'worst_day': min(values), 'best_day': max(values),
        'net_excluding_best_day': sum(values) - max(values),
        'max_close_to_close_drawdown': drawdown,
    }
