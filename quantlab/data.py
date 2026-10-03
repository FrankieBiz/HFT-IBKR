"""Validated, versioned local bar data. Timestamps identify bar starts in UTC."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


def utc(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('timestamp must include a timezone')
    return result.astimezone(timezone.utc)


def finite(value: float, name: str, minimum: float = 0) -> float:
    if isinstance(value, bool) or not math.isfinite(value) or value < minimum:
        raise ValueError(f'{name} must be finite and >= {minimum}')
    return value


@dataclass(frozen=True)
class Bar:
    timestamp: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: int

    def __post_init__(self):
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError('bar timestamp must be timezone aware')
        if not self.symbol or not self.symbol.isascii() or any(c.isspace() for c in self.symbol):
            raise ValueError('symbol must be nonempty ASCII without whitespace')
        for name in ('open', 'high', 'low', 'close'):
            finite(getattr(self, name), name, 1e-12)
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close) or self.low > self.high:
            raise ValueError('invalid OHLC bounds')
        if type(self.volume) is not int or self.volume < 0:
            raise ValueError('volume must be a nonnegative integer')


def parse_csv(raw: str) -> list[Bar]:
    reader = csv.DictReader(io.StringIO(raw))
    fields = ['timestamp', 'symbol', 'open', 'high', 'low', 'close', 'volume']
    if reader.fieldnames != fields:
        raise ValueError(f'CSV header must be {",".join(fields)}')
    bars = []
    previous = None
    seen = set()
    for number, row in enumerate(reader, 2):
        try:
            if None in row or any(v is None for v in row.values()):
                raise ValueError('wrong number of columns')
            bar = Bar(utc(row['timestamp']), row['symbol'], *(float(row[n]) for n in fields[2:6]), int(row['volume']))
            key = (bar.timestamp, bar.symbol)
            if key in seen or (previous is not None and key <= previous):
                raise ValueError('bars must be unique and ordered by timestamp, then symbol')
            seen.add(key)
            previous = key
            bars.append(bar)
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError(f'CSV line {number}: {exc}') from exc
    if not bars:
        raise ValueError('dataset is empty')
    return bars


def load_csv(path: Path) -> list[Bar]:
    return parse_csv(Path(path).read_text(encoding='utf-8'))


class DatasetStore:
    """Immutable dataset identity includes raw CSV and supplied provenance."""

    def __init__(self, path: Path):
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA foreign_keys = ON')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS datasets (
                id TEXT PRIMARY KEY, metadata TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS bars (
                dataset TEXT NOT NULL REFERENCES datasets(id), timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL, open REAL NOT NULL, high REAL NOT NULL,
                low REAL NOT NULL, close REAL NOT NULL, volume INTEGER NOT NULL,
                PRIMARY KEY(dataset, timestamp, symbol));
        ''')

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.db.close()

    def import_csv(self, path: Path, metadata: dict) -> str:
        for key in ('source', 'adjustment', 'survivorship'):
            if not isinstance(metadata.get(key), str) or not metadata[key].strip():
                raise ValueError(f'metadata requires {key}')
        interval = metadata.get('interval_seconds')
        if type(interval) is not int or interval <= 0:
            raise ValueError('interval_seconds must be a positive integer')
        raw = Path(path).read_bytes()
        bars = parse_csv(raw.decode('utf-8'))
        for bar in bars:
            if bar.volume > 2**63 - 1:
                raise ValueError('volume exceeds SQLite integer range')
        provenance = json.dumps(metadata, sort_keys=True, allow_nan=False)
        identity = hashlib.sha256(raw + b'\x00' + provenance.encode()).hexdigest()
        previous = {}
        gaps = 0
        for bar in bars:
            if bar.symbol in previous:
                elapsed = (bar.timestamp - previous[bar.symbol]).total_seconds()
                if elapsed < interval:
                    raise ValueError('bars overlap the declared interval')
                if elapsed != interval:
                    gaps += 1
            previous[bar.symbol] = bar.timestamp
        enriched = dict(metadata, sha256=hashlib.sha256(raw).hexdigest(), rows=len(bars),
                        gap_count=gaps, timestamp_convention='UTC bar start', schema_version=1,
                        gap_note='Includes overnight/session gaps; no exchange calendar assumed.')
        # Parsing finishes before transaction; either the entire version is stored or none.
        with self.db:
            if self.db.execute('SELECT 1 FROM datasets WHERE id=?', (identity,)).fetchone():
                return identity
            self.db.execute('INSERT INTO datasets VALUES (?,?)', (identity, json.dumps(enriched, sort_keys=True)))
            self.db.executemany('INSERT INTO bars VALUES (?,?,?,?,?,?,?,?)',
                                [(identity, b.timestamp.isoformat(), b.symbol, b.open, b.high,
                                  b.low, b.close, b.volume) for b in bars])
        return identity

    def datasets(self) -> list[dict]:
        return [dict(id=row[0], **json.loads(row[1])) for row in self.db.execute('SELECT * FROM datasets ORDER BY id')]

    def metadata(self, dataset: str) -> dict:
        row = self.db.execute('SELECT metadata FROM datasets WHERE id=?', (dataset,)).fetchone()
        if row is None:
            raise ValueError('unknown dataset')
        return json.loads(row[0])

    def bars(self, dataset: str) -> list[Bar]:
        self.metadata(dataset)
        return [Bar(utc(row[0]), row[1], *row[2:]) for row in self.db.execute(
            'SELECT timestamp,symbol,open,high,low,close,volume FROM bars WHERE dataset=? ORDER BY timestamp,symbol', (dataset,))]


def bar_dict(bar: Bar) -> dict:
    return dict(asdict(bar), timestamp=bar.timestamp.isoformat())
