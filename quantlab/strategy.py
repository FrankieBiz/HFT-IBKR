"""Illustrative baseline strategy, not a validated trading recommendation."""
from typing import Protocol, Sequence
from .data import Bar


class Strategy(Protocol):
    def target(self, history: Sequence[Bar], position: int) -> int: ...


class MovingAverage:
    def __init__(self, fast: int, slow: int, quantity: int):
        if not 0 < fast < slow or quantity <= 0:
            raise ValueError('require 0 < fast < slow and positive quantity')
        self.fast, self.slow, self.quantity = fast, slow, quantity

    def target(self, history: Sequence[Bar], position: int) -> int:
        if len(history) < self.slow:
            return 0
        fast = sum(b.close for b in history[-self.fast:]) / self.fast
        slow = sum(b.close for b in history[-self.slow:]) / self.slow
        return self.quantity if fast > slow else 0
