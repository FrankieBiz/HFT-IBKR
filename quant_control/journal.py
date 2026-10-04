"""Single-writer durable synthetic input journal with a corruption-detecting chain.

The hash chain detects damaged records; it is not authority against a malicious
operator rewriting the entire file. A failed write poisons the current writer.
"""

import fcntl
import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path

from quant_research.serde import InputError, canonical_json, strict_keys
from .domain import parse_event, validate_config

SCHEMA = 1
ZERO_DIGEST = '0' * 64
RECORD_KEYS = ('schema_version', 'sequence', 'kind', 'config_digest', 'payload',
               'previous_digest', 'digest')


def _digest(value):
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()


def _normalized(value):
    return json.loads(canonical_json(value))


def _validated_config(config):
    try:
        return validate_config(_normalized(asdict(config)))
    except (TypeError, AttributeError) as error:
        raise InputError('validated control configuration required') from error


def config_digest(config):
    return _digest(asdict(_validated_config(config)))


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError('duplicate journal JSON field')
        result[key] = value
    return result


def _read_records(content, config):
    if not content or not content.endswith(b'\n'):
        raise InputError('empty or truncated journal')
    expected_config = _normalized(asdict(_validated_config(config)))
    expected_digest = _digest(expected_config)
    events = []
    previous = ZERO_DIGEST
    timestamp = 0
    try:
        for number, line in enumerate(content.splitlines()):
            record = json.loads(line.decode('utf-8'), object_pairs_hook=_pairs)
            strict_keys(record, RECORD_KEYS, 'journal record')
            if (type(record['schema_version']) is not int or record['schema_version'] != SCHEMA
                    or type(record['sequence']) is not int or record['sequence'] != number):
                raise InputError('journal schema or sequence mismatch')
            if record['config_digest'] != expected_digest:
                raise InputError('journal configuration mismatch')
            if record['previous_digest'] != previous:
                raise InputError('journal digest chain mismatch')
            content_record = {key: value for key, value in record.items() if key != 'digest'}
            if record['digest'] != _digest(content_record):
                raise InputError('journal payload digest mismatch')
            if number == 0:
                if record['kind'] != 'header' or record['payload'] != expected_config:
                    raise InputError('journal header configuration mismatch')
            else:
                if record['kind'] != 'input':
                    raise InputError('unexpected journal record kind')
                event = parse_event(record['payload'])
                if event.sequence != number or event.time_ms < timestamp:
                    raise InputError('journal input sequence or clock regression')
                events.append(event)
                timestamp = event.time_ms
            previous = record['digest']
    except (UnicodeError, ValueError, TypeError) as error:
        if isinstance(error, InputError):
            raise
        raise InputError('invalid journal encoding or JSON') from error
    return tuple(events), previous


def replay_journal(path, config):
    """Read and validate every record before rebuilding historical state.

    This function never appends restart events and never returns outbound traffic.
    Its outputs are historical simulated decisions only.
    """
    try:
        content = Path(path).read_bytes()
    except OSError as error:
        raise InputError(f'cannot read control journal: {error}') from error
    events, _ = _read_records(content, config)
    from .runtime import replay
    return replay(events, config)


class Journal:
    def __init__(self, path, config):
        self.path = Path(path)
        self.config = _validated_config(config)
        self.config_digest = _digest(asdict(self.config))
        self.poisoned = False
        self._file = None
        try:
            try:
                descriptor = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_APPEND, 0o600)
                created = True
            except FileExistsError:
                descriptor = os.open(self.path, os.O_RDWR | os.O_APPEND)
                created = False
            self._file = os.fdopen(descriptor, 'a+b', buffering=0)
            try:
                fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                raise InputError('control journal already has an exclusive writer') from error
            self._file.seek(0)
            content = self._file.read()
            self.existing = not created
            if self.existing:
                self.events, self._previous = _read_records(content, self.config)
            else:
                self.events = ()
                self._previous = ZERO_DIGEST
                self._write_record(0, 'header', _normalized(asdict(self.config)))
                # Persist a newly created directory entry as well as its header.
                directory = os.open(self.path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            self._file.seek(0, os.SEEK_END)
        except (OSError, InputError) as error:
            self.close()
            if isinstance(error, InputError):
                raise
            raise InputError(f'cannot open control journal: {error}') from error

    def _write_record(self, sequence, kind, payload):
        record = {'schema_version': SCHEMA, 'sequence': sequence, 'kind': kind,
                  'config_digest': self.config_digest, 'payload': payload,
                  'previous_digest': self._previous}
        record['digest'] = _digest(record)
        line = json.dumps(record, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=True, allow_nan=False).encode('utf-8') + b'\n'
        try:
            written = self._file.write(line)
            if written != len(line):
                raise OSError('short control journal write')
            self._file.flush()
            os.fsync(self._file.fileno())
        except (OSError, ValueError) as error:
            self.poisoned = True
            raise InputError(f'control journal storage failure: {error}') from error
        self._previous = record['digest']

    def append(self, event):
        if self.poisoned or self._file is None:
            raise InputError('control journal writer is poisoned or closed')
        event = parse_event(event.raw)
        expected = len(self.events) + 1
        previous_time = self.events[-1].time_ms if self.events else 0
        if event.sequence != expected or event.time_ms < previous_time:
            raise InputError('journal append sequence or clock regression')
        self._write_record(expected, 'input', event.raw)
        self.events = (*self.events, event)

    def close(self):
        if self._file is not None:
            self._file.close()
            self._file = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
