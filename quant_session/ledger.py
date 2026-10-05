"""SQLite freeze-once decision ledger; never an order reservation."""
from contextlib import closing
import hashlib
import json
import sqlite3

from quant_research.serde import InputError, canonical_json, _pairs
from .planner import decision_digest


class DecisionLedger:
    def __init__(self, path):
        self.path = path

    def record(self, report, input_id):
        if (report.get('account'),report.get('symbol'),report.get('mode')) != ('SIM','SPY','offline_shadow'):
            raise InputError('ledger supports only offline_shadow SIM/SPY')
        if report.get('decision_id') != decision_digest(report):
            raise InputError('invalid report decision ID')
        content = canonical_json(report).encode('utf-8')
        digest = hashlib.sha256(content).hexdigest()
        key = str(report['execution_session'])
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
                row = connection.execute('SELECT input_id, decision_id, report, report_sha256 FROM decisions '
                    'WHERE account=? AND symbol=? AND execution_session=?',('SIM','SPY',key)).fetchone()
                if row:
                    stored_input, stored_id, stored_bytes, stored_hash = row
                    try:
                        stored = json.loads(stored_bytes.decode('utf-8'),object_pairs_hook=_pairs)
                        valid = (hashlib.sha256(stored_bytes).hexdigest() == stored_hash
                            and canonical_json(stored).encode() == stored_bytes
                            and stored.get('decision_id') == stored_id == decision_digest(stored)
                            and (stored.get('account'),stored.get('symbol'),stored.get('mode'),stored.get('execution_session'))
                                == ('SIM','SPY','offline_shadow',key))
                    except (ValueError, UnicodeError, AttributeError, TypeError):
                        valid = False
                    if not valid:
                        raise InputError('corrupt ledger report')
                    if stored_input != input_id or stored_id != report['decision_id'] or stored_bytes != content:
                        raise InputError('session decision conflict: inputs are already frozen')
                    return stored_bytes
                connection.execute('INSERT INTO decisions VALUES (?,?,?,?,?,?,?)',
                    ('SIM','SPY',key,input_id,report['decision_id'],content,digest))
                return content
        except sqlite3.Error as error:
            raise InputError(f'ledger storage error: {error}') from error
