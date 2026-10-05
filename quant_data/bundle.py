"""Normalize declared local sources into one bounded, reproducible research bundle."""

import csv
from datetime import datetime, timedelta
import hashlib
import io
import os
from pathlib import Path
import re
import tempfile
from zipfile import BadZipFile, ZipFile, ZipInfo, ZIP_DEFLATED, ZIP_STORED
import zlib

from quant_research.data import COLUMNS, load_dataset
from quant_research.serde import (InputError, canonical_json, decimal_value, durable_sync, iso_date,
                                  read_json_document, strict_keys)

MAX_MEMBER = 32 * 1024 * 1024
MEMBERS = ('dataset.csv', 'manifest.json', 'intake.json')
INPUTS = ('prices', 'distributions', 'calendar', 'metadata')
METADATA_KEYS = ('schema_version', 'symbol', 'currency', 'kind', 'price_policy',
                 'corporate_actions', 'splits_in_interval', 'review_note', 'sources')
LIMITATIONS = [
    'Source, license and corporate-action completeness are declarations, not independently verified facts.',
    'No historical profitability, calibrated execution costs or broker readiness established.',
    'Hashes detect accidental changes, not deliberate rewriting of all provenance declarations.',
]


def _read(path, limit=None):
    if limit is None:
        limit = MAX_MEMBER
    try:
        with Path(path).open('rb') as handle:
            content = handle.read(limit + 1)
    except OSError as error:
        raise InputError(f'cannot read input: {error}') from error
    if len(content) > limit:
        raise InputError('input exceeds size limit')
    return content


def _json(content):
    # Reuse the strict duplicate-key decoder on exactly the bytes consumed.
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'document.json'
        path.write_bytes(content)
        return read_json_document(path)[0]


def _text(value, name):
    if not isinstance(value, str) or not value.strip() or len(value) > 4096:
        raise InputError(f'{name}: nonempty bounded text required')


def _metadata(raw):
    strict_keys(raw, METADATA_KEYS, 'intake metadata')
    if type(raw['schema_version']) is not int or raw['schema_version'] != 1:
        raise InputError('unsupported intake metadata version')
    if raw['symbol'] != 'SPY' or raw['currency'] != 'USD' or raw['kind'] not in ('synthetic', 'historical'):
        raise InputError('unsupported instrument/currency/kind')
    if (raw['price_policy'] != 'raw_unadjusted'
            or raw['corporate_actions'] != 'complete_dividends_no_splits'
            or raw['splits_in_interval'] is not False):
        raise InputError('raw prices, complete dividends and no splits required')
    _text(raw['review_note'], 'review_note')
    strict_keys(raw['sources'], INPUTS[:3], 'sources')
    instants = []
    for name, source in raw['sources'].items():
        strict_keys(source, ('name', 'reference', 'license_reference', 'retrieved_at'), name)
        for field in ('name', 'reference', 'license_reference'):
            _text(source[field], f'{name}.{field}')
        value = source['retrieved_at']
        try:
            instant = datetime.fromisoformat(value)
        except (TypeError, ValueError) as error:
            raise InputError('source retrieval date must be UTC') from error
        if not isinstance(value, str) or 'T' not in value or instant.utcoffset() != timedelta(0):
            raise InputError('source retrieval date must be UTC')
        instants.append(instant)
    return max(instants).isoformat()


def _rows(content, header, name):
    try:
        reader = csv.reader(io.StringIO(content.decode('utf-8')), strict=True)
        if tuple(next(reader, ())) != header:
            raise InputError(f'{name}: incorrect CSV header')
        rows = list(reader)
        if any(len(row) != len(header) for row in rows):
            raise InputError(f'{name}: incorrect CSV field count')
        return rows
    except (csv.Error, UnicodeError) as error:
        raise InputError(f'{name}: invalid UTF-8 CSV') from error


def _dataset(members):
    audit = _json(members['intake.json'])
    strict_keys(audit, ('schema_version', 'metadata', 'input_sha256', 'limitations'), 'intake audit')
    if type(audit['schema_version']) is not int or audit['schema_version'] != 1:
        raise InputError('unsupported audit version')
    _metadata(audit['metadata'])
    strict_keys(audit['input_sha256'], INPUTS, 'input hashes')
    for value in audit['input_sha256'].values():
        if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
            raise InputError('invalid input hash')
    if audit['limitations'] != LIMITATIONS:
        raise InputError('missing intake limitations')
    with tempfile.TemporaryDirectory() as folder:
        csv_path, manifest_path = [Path(folder) / name for name in MEMBERS[:2]]
        csv_path.write_bytes(members['dataset.csv'])
        manifest_path.write_bytes(members['manifest.json'])
        dataset = load_dataset(csv_path, manifest_path)
    metadata = audit['metadata']
    if (dataset.manifest['source'] != 'Offline intake v1: ' + canonical_json(audit)
            or dataset.manifest['kind'] != metadata['kind']
            or dataset.manifest['retrieved_at'] != _metadata(metadata)
            or dataset.manifest['calendar_source'] != metadata['sources']['calendar']['reference']):
        raise InputError('intake audit does not match bound manifest')
    return dataset


def _publish(destination, content):
    destination = Path(destination)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix='.intake-', delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            durable_sync(handle.fileno())
        os.link(temporary, destination)
    except OSError as error:
        raise InputError(f'cannot publish bundle: {error}') from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def prepare_bundle(prices, distributions, calendar, metadata, destination):
    destination = Path(destination)
    if os.path.lexists(destination) or not destination.parent.is_dir():
        raise InputError('bundle exists or output parent missing')
    contents = {name: _read(path) for name, path in zip(INPUTS, (prices, distributions, calendar, metadata))}
    raw = _json(contents['metadata'])
    retrieved_at = _metadata(raw)
    price_rows = _rows(contents['prices'], COLUMNS[:6], 'prices')
    calendar_rows = _rows(contents['calendar'], ('session',), 'calendar')
    sessions = [row[0] for row in calendar_rows]
    session_set = set(sessions)
    dividends = {}
    for ex_date, amount, pay_date in _rows(contents['distributions'], ('ex_date', 'amount', 'pay_date'), 'distributions'):
        ex = iso_date(ex_date, 'ex date')
        pay = iso_date(pay_date, 'pay date')
        decimal_value(amount, 'distribution amount', positive=True)
        if ex_date not in session_set or ex_date in dividends or pay <= ex:
            raise InputError('duplicate/out-of-interval distribution or invalid pay date')
        dividends[ex_date] = (amount, pay_date)
    normalized = io.StringIO(newline='')
    writer = csv.writer(normalized, lineterminator='\n')
    writer.writerow(COLUMNS)
    for row in price_rows:
        writer.writerow([*row, *dividends.get(row[0], ('0', ''))])
    csv_bytes = normalized.getvalue().encode('utf-8')
    audit = {'schema_version': 1, 'metadata': raw,
             'input_sha256': {name: hashlib.sha256(value).hexdigest() for name, value in contents.items()},
             'limitations': LIMITATIONS}
    manifest = {'schema_version': 1, 'symbol': raw['symbol'], 'currency': raw['currency'],
                'kind': raw['kind'], 'source': 'Offline intake v1: ' + canonical_json(audit),
                'retrieved_at': retrieved_at, 'price_policy': raw['price_policy'],
                'corporate_actions': raw['corporate_actions'], 'splits_in_interval': False,
                'sha256': hashlib.sha256(csv_bytes).hexdigest(),
                'calendar_source': raw['sources']['calendar']['reference'], 'expected_sessions': sessions}
    members = {'dataset.csv': csv_bytes, 'manifest.json': canonical_json(manifest).encode(),
               'intake.json': canonical_json(audit).encode()}
    if any(len(value) > MAX_MEMBER for value in members.values()):
        raise InputError('normalized member exceeds size limit')
    _dataset(members)
    output = io.BytesIO()
    with ZipFile(output, 'w', compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for name, content in sorted(members.items()):
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content, compresslevel=9)
    _publish(destination, output.getvalue())


def read_bundle(path):
    content = _read(path, 3 * MAX_MEMBER + 1024 * 1024)
    try:
        with ZipFile(io.BytesIO(content)) as archive:
            names = archive.namelist()
            if len(names) != len(MEMBERS) or set(names) != set(MEMBERS):
                raise InputError('bundle requires exactly three unique fixed members')
            members = {}
            for name in MEMBERS:
                info = archive.getinfo(name)
                if info.compress_type not in (ZIP_DEFLATED, ZIP_STORED) or info.flag_bits & 1:
                    raise InputError('unsupported compression or encrypted member')
                if info.file_size > MAX_MEMBER:
                    raise InputError('bundle member exceeds size limit')
                with archive.open(name) as handle:
                    members[name] = handle.read(MAX_MEMBER + 1)
                if len(members[name]) > MAX_MEMBER:
                    raise InputError('decompressed member exceeds size limit')
        return _dataset(members)
    except (BadZipFile, RuntimeError, NotImplementedError, OSError, EOFError,
            zlib.error, UnicodeError, ValueError) as error:
        raise InputError(f'invalid bundle: {error}') from error


def inspect_bundle(path):
    dataset = read_bundle(path)
    return {'schema_version': 1, 'status': 'input_valid', 'independently_verified': False,
            'kind': dataset.manifest['kind'], 'symbol': dataset.manifest['symbol'],
            'sessions': len(dataset.bars), 'start': dataset.bars[0].session,
            'end': dataset.bars[-1].session,
            'distribution_events': sum(bar.dividend > 0 for bar in dataset.bars),
            'data_sha256': dataset.data_sha256, 'manifest_sha256': dataset.manifest_sha256,
            'provenance': dataset.manifest, 'limitations': LIMITATIONS}
