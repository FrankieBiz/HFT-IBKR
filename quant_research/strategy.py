"""Signals based only on completed sessions; no order or account authority."""

from collections import deque
from enum import StrEnum
from fractions import Fraction

from .serde import fixed_decimal, whole


class TrendSignal(StrEnum):
    WARMUP = 'WARMUP'
    LONG = 'LONG'
    CASH = 'CASH'


@fixed_decimal
def trend_signals(bars, lookback):
    whole(lookback, 'lookback', minimum=2)
    window = deque()
    total = Fraction(0)
    index = None
    previous_close = None
    signals = []
    for bar in bars:
        # Calculate the ratio first: a flat ex-dividend-free session is exactly 1.
        index = bar.close if index is None else index * ((bar.close + bar.dividend) / previous_close)
        previous_close = bar.close
        exact_index = Fraction(index)
        window.append(exact_index)
        total += exact_index
        if len(window) > lookback:
            total -= window.popleft()
        if len(window) < lookback:
            signals.append(TrendSignal.WARMUP)
        else:
            # Exact arithmetic over the represented indices preserves equality and
            # removes rounding drift when expired observations leave the window.
            signals.append(TrendSignal.LONG if exact_index * lookback > total else TrendSignal.CASH)
    return tuple(signals)
