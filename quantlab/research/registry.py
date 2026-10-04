"""Local append-only run and review history; review never activates a strategy."""
import json
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4


class Registry:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS research_runs (
                id TEXT PRIMARY KEY, created TEXT NOT NULL, config TEXT NOT NULL, provenance TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS research_events (
                sequence INTEGER PRIMARY KEY, run_id TEXT REFERENCES research_runs(id),
                created TEXT NOT NULL, status TEXT NOT NULL, notes TEXT NOT NULL);
        ''')

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.db.close()

    def _event(self, run_id, status, notes):
        self.db.execute('INSERT INTO research_events(run_id,created,status,notes) VALUES (?,?,?,?)',
                        (run_id, datetime.now(timezone.utc).isoformat(), status, json.dumps(notes, allow_nan=False, sort_keys=True)))

    def start(self, config, provenance):
        identity = uuid4().hex
        with self.db:
            self.db.execute('INSERT INTO research_runs VALUES (?,?,?,?)',
                            (identity, datetime.now(timezone.utc).isoformat(), json.dumps(config, allow_nan=False, sort_keys=True),
                             json.dumps(provenance, allow_nan=False, sort_keys=True)))
            self._event(identity, 'attempted', {})
        return identity

    def finish(self, identity, status, notes):
        if status not in ('completed', 'failed'):
            raise ValueError('invalid run status')
        if any(event['status'] in ('completed', 'failed') for event in self.events(identity)):
            raise ValueError('run already finished')
        with self.db:
            self._event(identity, status, notes)

    def review(self, identity, state, note):
        if state not in ('pending_review', 'reviewed', 'rejected') or not isinstance(note, str) or not note.strip():
            raise ValueError('manual review state and nonempty note required; activation is unsupported')
        with self.db:
            self._event(identity, state, {'note': note})

    def events(self, identity):
        return [dict(status=s, notes=json.loads(n), created=t) for s,n,t in self.db.execute(
            'SELECT status,notes,created FROM research_events WHERE run_id=? ORDER BY sequence', (identity,))]

    def runs(self):
        result = []
        for identity, created, config, provenance in self.db.execute('SELECT * FROM research_runs ORDER BY created,id'):
            events = self.events(identity)
            statuses = [e['status'] for e in events if e['status'] in ('attempted', 'completed', 'failed')]
            result.append(dict(id=identity, created=created, config=json.loads(config), provenance=json.loads(provenance),
                               status=statuses[-1], events=events))
        return result
