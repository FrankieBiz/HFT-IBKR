"""Load raw daily prices with explicitly supplied corporate-action provenance."""

import csv
import hashlib
import io
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from .serde import InputError, decimal_value, iso_date, read_json_document, strict_keys, whole

COLUMNS = ('session', 'open', 'high', 'low', 'close', 'volume',
           'dividend', 'dividend_pay_date')
MANIFEST_KEYS = ('schema_version', 'symbol', 'currency', 'kind', 'source',
                 'retrieved_at', 'price_policy', 'corporate_actions',
                 'splits_in_interval', 'sha256', 'calendar_source', 'expected_sessions')


@dataclass(frozen=True)
class Bar:
    session: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    dividend: Decimal
    dividend_pay_date: date | None


@dataclass(frozen=True)
class Dataset:
    bars: tuple[Bar, ...]
    manifest: dict
    data_sha256: str
    manifest_sha256: str


def _validate_manifest(manifest):
    strict_keys(manifest, MANIFEST_KEYS, 'manifest')
    if type(manifest['schema_version']) is not int or manifest['schema_version'] != 1:
        raise InputError('unsupported manifest schema')
    if manifest['symbol'] != 'SPY' or manifest['currency'] != 'USD':
        raise InputError('unsupported symbol or currency')
    if manifest['kind'] not in ('synthetic', 'historical'):
        raise InputError('unknown data provenance kind')
    if manifest['price_policy'] != 'raw_unadjusted':
        raise InputError('raw unadjusted data is required')
    if manifest['corporate_actions'] != 'complete_dividends_no_splits':
        raise InputError('complete dividend coverage declaration is required')
    if manifest['splits_in_interval'] is not False:
        raise InputError('splits are unsupported')
    for key in ('source', 'calendar_source'):
        if not isinstance(manifest[key], str) or not manifest[key].strip():
            raise InputError(f'{key}: required provenance text')
    timestamp = manifest['retrieved_at']
    try:
        instant = datetime.fromisoformat(timestamp)
    except (TypeError, ValueError) as error:
        raise InputError('retrieved_at: invalid UTC timestamp') from error
    if not isinstance(timestamp, str) or 'T' not in timestamp or instant.utcoffset() != timedelta(0):
        raise InputError('retrieved_at: UTC timestamp required')
    if not isinstance(manifest['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', manifest['sha256']):
        raise InputError('invalid data hash')
    sessions = manifest['expected_sessions']
    if not isinstance(sessions, list) or not sessions:
        raise InputError('expected_sessions: nonempty list required')
    dates = tuple(iso_date(item, 'expected session') for item in sessions)
    if any(a >= b for a, b in zip(dates, dates[1:])):
        raise InputError('manifest sessions must be strictly increasing')
    return dates


def load_dataset(csv_path, manifest_path):
    manifest, manifest_bytes = read_json_document(manifest_path)
    expected = _validate_manifest(manifest)
    try:
        content = Path(csv_path).read_bytes()
        raw_text = content.decode('utf-8')
    except (OSError, UnicodeError) as error:
        raise InputError(f'cannot read dataset: {error}') from error
    digest = hashlib.sha256(content).hexdigest()
    if digest != manifest['sha256']:
        raise InputError('CSV hash mismatch')
    reader = csv.reader(io.StringIO(raw_text), strict=True)
    bars = []
    try:
        if tuple(next(reader, ())) != COLUMNS:
            raise InputError('CSV header does not match schema')
        for row in reader:
            if len(row) != len(COLUMNS):
                raise InputError('CSV row has wrong field count')
            session = iso_date(row[0], 'session')
            prices = [decimal_value(item, 'OHLC', positive=True) for item in row[1:5]]
            open_, high, low, close = prices
            if low > min(open_, close) or high < max(open_, close) or low > high:
                raise InputError('invalid OHLC range')
            if len(row[5]) > 13 or not re.fullmatch('[0-9]+', row[5]):
                raise InputError('volume must be a positive whole number')
            volume = whole(int(row[5]), 'volume')
            dividend = decimal_value(row[6], 'dividend')
            pay_date = iso_date(row[7], 'dividend pay date') if row[7] else None
            if (dividend == 0 and pay_date is not None) or (dividend > 0 and
                    (pay_date is None or pay_date <= session or not bars)):
                raise InputError('invalid dividend/pay-date context')
            if bars and session <= bars[-1].session:
                raise InputError('CSV sessions must be strictly increasing')
            bars.append(Bar(session, *prices, volume, dividend, pay_date))
    except csv.Error as error:
        raise InputError(f'invalid CSV: {error}') from error
    if tuple(bar.session for bar in bars) != expected:
        raise InputError('CSV sessions do not match supplied calendar (gap or extra session)')
    return Dataset(tuple(bars), manifest, digest, hashlib.sha256(manifest_bytes).hexdigest())
