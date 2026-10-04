"""Local append-only experiment attempts and irreversible holdout reservations.

A reserved release remains consumed after a crash. Terminal states are separate
records, never updates. This is a local audit guard, not access control over data.
"""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .serde import InputError, canonical_json


class ExperimentRegistry:
    def __init__(self, path):
        try:
            self.connection = sqlite3.connect(str(Path(path)), timeout=30, isolation_level=None)
            self.connection.row_factory = sqlite3.Row
            self.connection.execute('PRAGMA foreign_keys=ON')
            self.connection.execute('PRAGMA synchronous=FULL')
            self.connection.executescript('''
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK(kind IN ('validation','holdout')),
                    status TEXT NOT NULL CHECK(status IN ('reserved','completed','failed')),
                    artifact_digest TEXT,
                    identities TEXT NOT NULL,
                    result_digest TEXT,
                    error TEXT,
                    recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                );
                CREATE UNIQUE INDEX IF NOT EXISTS unique_attempt
                    ON events(run_id) WHERE status='reserved';
                CREATE UNIQUE INDEX IF NOT EXISTS unique_terminal
                    ON events(run_id) WHERE status IN ('completed','failed');
                CREATE UNIQUE INDEX IF NOT EXISTS unique_release
                    ON events(artifact_digest) WHERE kind='holdout' AND status='reserved';
                CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
                    BEGIN SELECT RAISE(ABORT,'events are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
                    BEGIN SELECT RAISE(ABORT,'events are append-only'); END;
                CREATE TABLE IF NOT EXISTS result_payloads (
                    run_id TEXT PRIMARY KEY, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS frozen_selections (
                    artifact_digest TEXT PRIMARY KEY,
                    validation_run_id TEXT NOT NULL UNIQUE,
                    stable_identity TEXT NOT NULL,
                    artifact TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS holdout_claims (
                    stable_identity TEXT PRIMARY KEY,
                    artifact_digest TEXT NOT NULL UNIQUE,
                    run_id TEXT NOT NULL UNIQUE
                );
                CREATE TRIGGER IF NOT EXISTS payloads_no_update BEFORE UPDATE ON result_payloads
                    BEGIN SELECT RAISE(ABORT,'result payloads are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS payloads_no_delete BEFORE DELETE ON result_payloads
                    BEGIN SELECT RAISE(ABORT,'result payloads are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS freezes_no_update BEFORE UPDATE ON frozen_selections
                    BEGIN SELECT RAISE(ABORT,'freezes are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS freezes_no_delete BEFORE DELETE ON frozen_selections
                    BEGIN SELECT RAISE(ABORT,'freezes are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS claims_no_update BEFORE UPDATE ON holdout_claims
                    BEGIN SELECT RAISE(ABORT,'holdout claims are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS claims_no_delete BEFORE DELETE ON holdout_claims
                    BEGIN SELECT RAISE(ABORT,'holdout claims are append-only'); END;
            ''')
        except (OSError, sqlite3.Error) as error:
            if hasattr(self, 'connection'):
                self.connection.close()
            raise InputError(f'cannot open experiment registry: {error}') from error

    @contextmanager
    def _transaction(self):
        try:
            self.connection.execute('BEGIN IMMEDIATE')
            yield
            self.connection.execute('COMMIT')
        except BaseException as error:
            if self.connection.in_transaction:
                self.connection.execute('ROLLBACK')
            if isinstance(error, sqlite3.Error):
                raise InputError(f'experiment registry rejected operation: {error}') from error
            raise

    def _reserve(self, run_id, kind, artifact_digest, identities):
        if not isinstance(run_id, str) or not run_id.strip():
            raise InputError('run_id: nonempty string required')
        if not isinstance(identities, dict):
            raise InputError('identities: object required')
        with self._transaction():
            if kind == 'holdout':
                frozen = self.connection.execute(
                    'SELECT * FROM frozen_selections WHERE artifact_digest=?',
                    (artifact_digest,)).fetchone()
                if frozen is None:
                    raise InputError('holdout requires a registered frozen selection')
                original = json.loads(frozen['artifact'])
                if original['identities'] != identities:
                    raise InputError('frozen selection registry identities mismatch')
                self.connection.execute(
                    'INSERT INTO holdout_claims(stable_identity,artifact_digest,run_id) VALUES(?,?,?)',
                    (frozen['stable_identity'], artifact_digest, run_id))
            self.connection.execute(
                'INSERT INTO events(run_id,kind,status,artifact_digest,identities) VALUES(?,?,?,?,?)',
                (run_id, kind, 'reserved', artifact_digest, canonical_json(identities)))

    def reserve_validation(self, run_id, identities):
        self._reserve(run_id, 'validation', None, identities)

    def reserve_holdout(self, run_id, artifact_digest, identities):
        if not isinstance(artifact_digest, str) or len(artifact_digest) != 64 or any(
                c not in '0123456789abcdef' for c in artifact_digest):
            raise InputError('artifact digest: SHA-256 required')
        self._reserve(run_id, 'holdout', artifact_digest, identities)

    def _finish(self, run_id, status, result_digest=None, error=None, result=None):
        with self._transaction():
            row = self.connection.execute(
                "SELECT * FROM events WHERE run_id=? AND status='reserved'", (run_id,)).fetchone()
            if row is None:
                raise InputError('cannot finalize an unreserved experiment')
            if result is not None:
                payload = canonical_json(result)
                if hashlib.sha256(payload.encode('utf-8')).hexdigest() != result_digest:
                    raise InputError('completed result digest does not match payload')
                self.connection.execute('INSERT INTO result_payloads(run_id,payload) VALUES(?,?)',
                                        (run_id, payload))
            self.connection.execute('''INSERT INTO events
                (run_id,kind,status,artifact_digest,identities,result_digest,error)
                VALUES(?,?,?,?,?,?,?)''',
                (run_id, row['kind'], status, row['artifact_digest'], row['identities'], result_digest, error))

    def complete(self, run_id, result_digest, *, result=None):
        if not isinstance(result_digest, str) or len(result_digest) != 64 or any(
                c not in '0123456789abcdef' for c in result_digest):
            raise InputError('result digest: SHA-256 required')
        self._finish(run_id, 'completed', result_digest=result_digest, result=result)

    def register_freeze(self, validation_run_id, artifact):
        """Bind one original artifact to the actual completed validation payload.

        A new self-computed checksum cannot replace an already registered freeze.
        Different run/report metadata cannot reopen the same input identity.
        """
        if not isinstance(artifact, dict):
            raise InputError('frozen selection: object required')
        try:
            content = {k: v for k, v in artifact.items() if k != 'integrity_digest'}
            artifact_digest = hashlib.sha256(canonical_json(content).encode('utf-8')).hexdigest()
            if artifact_digest != artifact['integrity_digest']:
                raise InputError('frozen selection integrity mismatch')
            with self._transaction():
                row = self.connection.execute('''SELECT events.result_digest, events.identities,
                    result_payloads.payload FROM events JOIN result_payloads USING(run_id)
                    WHERE events.run_id=? AND events.kind='validation' AND events.status='completed' ''',
                    (validation_run_id,)).fetchone()
                if row is None:
                    raise InputError('freeze requires a completed validation with recorded payload')
                report = json.loads(row['payload'])
                if (row['result_digest'] != artifact['validation_report_digest']
                        or report['selected_lookback'] != artifact['selected_lookback']
                        or report['trial_count'] != artifact['trial_count']
                        or report['data_kind'] != artifact['data_kind']
                        or report['identities'] != artifact['identities']
                        or json.loads(row['identities']) != artifact['identities']):
                    raise InputError('freeze does not match completed validation')
                stable_identity = hashlib.sha256(
                    canonical_json(artifact['identities']).encode('utf-8')).hexdigest()
                self.connection.execute('''INSERT INTO frozen_selections
                    (artifact_digest,validation_run_id,stable_identity,artifact) VALUES(?,?,?,?)''',
                    (artifact_digest, validation_run_id, stable_identity, canonical_json(artifact)))
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, InputError):
                raise
            raise InputError('malformed frozen selection for registry') from error

    def fail(self, run_id, error):
        if not isinstance(error, str) or not error:
            raise InputError('failure description required')
        self._finish(run_id, 'failed', error=error)

    def records(self):
        try:
            return [dict(row) for row in self.connection.execute('SELECT * FROM events ORDER BY sequence')]
        except sqlite3.Error as error:
            raise InputError(f'cannot read experiment registry: {error}') from error

    def result(self,run_id):
        """Recover a persisted completed result without reopening its experiment."""
        try:
            row=self.connection.execute('''SELECT payload,result_digest FROM result_payloads
                JOIN events USING(run_id) WHERE events.run_id=? AND status='completed' ''',(run_id,)).fetchone()
            if row is None:
                raise InputError('no stored completed result for this run')
            payload=row['payload']
            if hashlib.sha256(payload.encode('utf-8')).hexdigest()!=row['result_digest']:
                raise InputError('stored result digest mismatch')
            return json.loads(payload)
        except (sqlite3.Error,ValueError) as error:
            if isinstance(error,InputError):
                raise
            raise InputError('cannot recover stored experiment result') from error

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
