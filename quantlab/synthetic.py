"""Reproducible software fixture, never a substitute for market history."""
import csv
from datetime import datetime, timedelta, timezone
import math
from pathlib import Path
import random


def generate(path: Path, seed: int = 17, count: int = 720):
    if count < 2:
        raise ValueError('count must be >= 2')
    rng = random.Random(seed)
    start = datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc)
    previous = 100.0
    with path.open('x', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['timestamp', 'symbol', 'open', 'high', 'low', 'close', 'volume'])
        for index in range(count):
            close = 100 + 2*math.sin(index/24) + .6*math.sin(index/7) + rng.gauss(0, .12)
            writer.writerow([(start+timedelta(minutes=index)).isoformat(), 'DEMO', f'{previous:.6f}',
                             f'{max(close, previous)+.05:.6f}', f'{min(close, previous)-.05:.6f}',
                             f'{close:.6f}', rng.randrange(1000, 5000)])
            previous = close
