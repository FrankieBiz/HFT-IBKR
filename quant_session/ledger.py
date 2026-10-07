"""Serialized shadow planning, durable entry-risk memory and frozen decisions.

This is a local audit guard, never an order reservation or a broker balance sheet.
"""
from contextlib import closing, contextmanager
from dataclasses import asdict
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sqlite3

from quant_research.serde import InputError, canonical_json, iso_date, _pairs
from .planner import decision_digest, plan_session


class DecisionLedger:
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def _transaction(self):
        try:
            with closing(sqlite3.connect(self.path, timeout=10)) as connection, connection:
                connection.execute('PRAGMA synchronous=FULL')
                connection.execute('PRAGMA fullfsync=ON')
                connection.execute('BEGIN IMMEDIATE')
                connection.execute('CREATE TABLE IF NOT EXISTS decisions ('
                    'account TEXT NOT NULL CHECK(account="SIM"), '
                    'symbol TEXT NOT NULL CHECK(symbol="SPY"), '
                    'execution_session TEXT NOT NULL, input_id TEXT NOT NULL, '
                    'decision_id TEXT NOT NULL, report BLOB NOT NULL, report_sha256 TEXT NOT NULL, '
                    'PRIMARY KEY(account,symbol,execution_session))')
                yield connection
        except sqlite3.Error as error:
            raise InputError(f'ledger storage error: {error}') from error

    @staticmethod
    def _rows(connection):
        """Verify exact captured bytes, including every preceding decision."""
        reports = []
        for account, symbol, key, input_id, stored_id, content, checksum in connection.execute(
                'SELECT * FROM decisions ORDER BY execution_session'):
            try:
                iso_date(key, 'ledger session')
                if not isinstance(content, bytes) or len(content) > 1024 * 1024:
                    raise ValueError('invalid stored payload')
                report = json.loads(content.decode('utf-8'), object_pairs_hook=_pairs)
                valid = (hashlib.sha256(content).hexdigest() == checksum
                    and canonical_json(report).encode() == content
                    and report.get('decision_id') == stored_id == decision_digest(report)
                    and (account, symbol, report.get('account'), report.get('symbol'),
                         report.get('mode'), report.get('execution_session'))
                        == ('SIM', 'SPY', 'SIM', 'SPY', 'offline_shadow', key)
                    and isinstance(input_id, str) and bool(input_id))
            except (ValueError, UnicodeError, AttributeError, TypeError, RecursionError):
                valid = False
            if not valid:
                raise InputError('corrupt ledger report')
            reports.append((key, input_id, report, content))
        return reports

    @staticmethod
    def _memory(rows):
        peak, maximum, halted, previous = Decimal(0), Decimal(0), False, None
        for key, _, report, _ in rows:
            memory = report.get('risk_memory')
            if memory is None:
                raise InputError('legacy ledger lacks risk memory; reviewed migration required; retain history')
            try:
                if set(memory) != {'peak_nav', 'maximum_drawdown', 'entry_halted', 'mark_valid', 'previous_session'}:
                    raise ValueError()
                if not isinstance(memory['peak_nav'], str) or not isinstance(memory['maximum_drawdown'], str):
                    raise ValueError()
                next_peak = Decimal(memory['peak_nav'])
                next_maximum = Decimal(memory['maximum_drawdown'])
                if (not next_peak.is_finite() or not next_maximum.is_finite()
                        or not peak <= next_peak <= Decimal('1e18')
                        or not maximum <= next_maximum <= 1
                        or type(memory['entry_halted']) is not bool
                        or type(memory['mark_valid']) is not bool
                        or (halted and not memory['entry_halted'])
                        or memory['previous_session'] != previous):
                    raise ValueError()
                if not memory['mark_valid'] and (next_peak, next_maximum, memory['entry_halted']) != (peak, maximum, halted):
                    raise ValueError()
            except (KeyError, ValueError, TypeError, InvalidOperation):
                raise InputError('corrupt ledger risk memory') from None
            peak, maximum, halted, previous = next_peak, next_maximum, memory['entry_halted'], key
        return {'peak_nav': peak, 'maximum_drawdown': maximum,
                'entry_halted': halted, 'previous_session': previous}

    @staticmethod
    def _insert(connection, report, input_id):
        if (report.get('account'), report.get('symbol'), report.get('mode')) != ('SIM', 'SPY', 'offline_shadow'):
            raise InputError('ledger supports only offline_shadow SIM/SPY')
        if report.get('decision_id') != decision_digest(report):
            raise InputError('invalid report decision ID')
        if not isinstance(input_id, str) or not input_id:
            raise InputError('nonempty input identity required')
        content = canonical_json(report).encode('utf-8')
        key = str(report['execution_session'])
        iso_date(key, 'ledger session')
        connection.execute('INSERT INTO decisions VALUES (?,?,?,?,?,?,?)',
            ('SIM', 'SPY', key, input_id, report['decision_id'], content, hashlib.sha256(content).hexdigest()))
        return content

    def plan(self, dataset, config, schedule, snapshot, source_hashes=None):
        """Freeze proposal and observed peak/halt under one write transaction."""
        key = snapshot['execution_session'].isoformat()
        input_id = hashlib.sha256(canonical_json({
            'config': asdict(config), 'schedule': schedule, 'snapshot': snapshot,
            'data': dataset.data_sha256, 'manifest': dataset.manifest_sha256,
            'bars': [asdict(bar) for bar in dataset.bars], 'provenance': dataset.manifest,
            'sources': source_hashes or {},
        }).encode()).hexdigest()
        with self._transaction() as connection:
            rows = self._rows(connection)
            memory = self._memory(rows)
            for session, frozen_input, _, content in rows:
                if session == key:
                    if frozen_input != input_id:
                        raise InputError('session decision conflict: inputs are already frozen')
                    return content
            if rows and key <= rows[-1][0]:
                raise InputError('new decisions must be chronological')
            report = plan_session(dataset, config, schedule, snapshot, source_hashes, memory)
            return self._insert(connection, report, input_id)

    def record(self, report, input_id):
        """Standalone rehearsals; operational CLI uses atomic plan()."""
        with self._transaction() as connection:
            rows = self._rows(connection)
            key = str(report['execution_session'])
            content = canonical_json(report).encode()
            for session, stored_input, _, stored_bytes in rows:
                if session == key:
                    if stored_input != input_id or stored_bytes != content:
                        raise InputError('session decision conflict: inputs are already frozen')
                    return stored_bytes
            if rows and key <= rows[-1][0]:
                raise InputError('new decisions must be chronological')
            return self._insert(connection, report, input_id)

    def get(self, session):
        """Read verified bytes without creating or changing any database."""
        key = iso_date(str(session), 'ledger session').isoformat()
        try:
            uri = self.path.resolve().as_uri() + '?mode=ro'
            with closing(sqlite3.connect(uri, uri=True, timeout=10)) as connection:
                connection.execute('BEGIN')
                rows = self._rows(connection)
                self._memory(rows)
                for stored_session, _, _, content in rows:
                    if stored_session == key:
                        return content
        except sqlite3.Error as error:
            raise InputError(f'cannot read decision ledger: {error}') from error
        raise InputError('no recorded decision for session')

    def history(self, limit=500):
        """Return (newest reports, total), verifying the entire chain read-only.

        Missing storage is an error, never an invitation to initialize history.
        The bounded projection does not weaken verification of earlier records.
        """
        if type(limit) is not int or not 1 <= limit <= 500:
            raise InputError('history limit must be a whole number from 1 to 500')
        try:
            uri = self.path.resolve().as_uri() + '?mode=ro'
            with closing(sqlite3.connect(uri, uri=True, timeout=10)) as connection:
                connection.execute('PRAGMA query_only=ON')
                connection.execute('BEGIN')
                rows = self._rows(connection)
                self._memory(rows)
                return [row[2] for row in reversed(rows[-limit:])], len(rows)
        except sqlite3.Error as error:
            raise InputError(f'cannot read decision ledger: {error}') from error
