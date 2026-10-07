"""Offline status projection and explicit simulated-book accounting.

Status reads never initialize storage, recover a fill, read API key values or
contact a provider. All mutations share the runner ownership lock. A committed
fill intent precedes book replacement, allowing explicit actions to recover a
crash without guessing about manually changed balances.
"""
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from decimal import Decimal, Inexact, localcontext
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import tempfile

from quant_research.serde import (InputError, _pairs, canonical_json, decimal_value,
                                  durable_sync, fixed_decimal, iso_date, strict_keys, whole)
from quant_session.health import check_health, _expectations
from quant_session.inputs import parse_snapshot, read_document
from quant_session.ledger import DecisionLedger
from quant_session.live import PORTFOLIO_KEYS
from quant_session.readiness import verify_readiness
from .locking import operator_lock
from .evidence import StudyEvidence


TOKEN = re.compile(r'[A-Za-z0-9_-]{1,256}\Z')
DECISION_ID = re.compile(r'[0-9a-f]{64}\Z')


def _now():
    return datetime.now(timezone.utc).isoformat()


def _hash(book):
    return hashlib.sha256(canonical_json(book).encode()).hexdigest()


def _book(raw):
    strict_keys(raw, PORTFOLIO_KEYS, 'shadow portfolio')
    if type(raw['schema_version']) is not int or raw['schema_version'] != 1:
        raise InputError('unsupported shadow portfolio schema')
    cash = decimal_value(raw['cash'], 'cash')
    settled = decimal_value(raw['settled_cash'], 'settled_cash')
    decimal_value(raw['peak_nav'], 'peak_nav', positive=True)
    whole(raw['shares'], 'shares', minimum=0)
    if settled > cash:
        raise InputError('settled_cash must not exceed cash')
    if type(raw['halted']) is not bool:
        raise InputError('halted: strict boolean required')
    return dict(raw)


@fixed_decimal
def _fill_book(before, side, quantity, price, fees):
    """Reject arithmetic that would silently round an operator-declared charge."""
    after = dict(before)
    try:
        with localcontext() as context:
            context.traps[Inexact] = True
            notional = quantity * price
            if notional > Decimal('1e18') or fees > notional:
                raise InputError('Fill notional or fees exceed supported accounting bounds.')
            cash, settled = Decimal(before['cash']), Decimal(before['settled_cash'])
            if side == 'BUY':
                cost = notional + fees
                if cost > settled or cost > cash:
                    raise InputError('The full simulated buy exceeds settled cash.')
                after.update(cash=format(cash-cost,'f'), settled_cash=format(settled-cost,'f'),
                             shares=before['shares']+quantity)
            else:
                if quantity > before['shares'] or notional <= fees:
                    raise InputError('The simulated sell exceeds inventory or has nonpositive proceeds.')
                after.update(cash=format(cash+notional-fees,'f'), shares=before['shares']-quantity)
    except ArithmeticError as error:
        raise InputError('Fill accounting exceeds supported exact decimal precision.') from error
    return _book(after)


def _atomic(path, content, *, mode=0o600):
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.operator-', delete=False) as handle:
            temporary = Path(handle.name)
            os.fchmod(handle.fileno(), mode)
            handle.write(content)
            handle.flush()
            durable_sync(handle.fileno())
        os.replace(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise InputError(f'operator storage error: {error}') from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class Service:
    def __init__(self, root, config_home=None):
        self.root = Path(root).resolve()
        self.config_home = Path(config_home if config_home is not None else Path.home() / '.config').resolve()
        self.credentials_path = self.config_home / 'alpaca/paper.env'
        self.shadow = self.root / '.research-output/shadow'
        self.portfolio_path = self.shadow / 'portfolio.json'
        self.ledger_path = self.shadow / 'ledger.sqlite'
        self.heartbeat_path = self.shadow / 'heartbeat.json'
        self.journal_path = self.shadow / 'fills.sqlite'
        output = self.root / '.research-output/spy-trend-v2'
        study = self.root / 'studies/spy-trend-v2'
        self.study_paths = {'bundle': output / 'spy.qdata', 'config': study / 'config.json',
                            'protocol': study / 'protocol.json', 'selection': output / 'selection.json',
                            'holdout': output / 'holdout.json',
                            'registry': self.root / '.research-output/spy-daily-v1/experiments.sqlite'}
        self.study_evidence = StudyEvidence(self.study_paths)

    def _reports(self):
        if not self.ledger_path.exists():
            return [], 0
        reports, total = DecisionLedger(self.ledger_path).history()
        try:
            for report in reports:
                if report['status'] not in ('PROPOSED', 'HOLD', 'BLOCKED'):
                    raise InputError('unsupported decision status')
                if report['signal'] not in ('LONG', 'CASH', 'WARMUP', None):
                    raise InputError('unsupported decision signal')
                decimal_value(report['effective_nav'], 'decision NAV')
                if (not isinstance(report['blockers'], list) or len(report['blockers']) > 100
                        or any(not isinstance(reason, str) or len(reason) > 256 for reason in report['blockers'])):
                    raise InputError('invalid decision reasons')
                if not isinstance(report['source_hashes'], dict):
                    raise InputError('invalid decision sources')
                proposal = report['proposal']
                if (report['status'] == 'PROPOSED') != (proposal is not None):
                    raise InputError('inconsistent decision proposal')
                if proposal is not None:
                    strict_keys(proposal, ('side', 'quantity', 'reference_price', 'estimated_price',
                        'estimated_notional', 'estimated_fees', 'estimated_friction'), 'proposal')
                    if proposal['side'] not in ('BUY', 'SELL'):
                        raise InputError('unsupported proposal side')
                    whole(proposal['quantity'], 'proposal quantity')
                    for key in ('reference_price', 'estimated_price', 'estimated_notional',
                                'estimated_fees', 'estimated_friction'):
                        decimal_value(proposal[key], key, positive=key in ('reference_price', 'estimated_price'))
        except (KeyError, ValueError, TypeError, AttributeError) as error:
            raise InputError(f'corrupt ledger decision projection: {error}') from error
        return reports, total

    def _read_book(self):
        return _book(read_document(self.portfolio_path)[0])

    def _write_book(self, book):
        _atomic(self.portfolio_path, canonical_json(_book(book)).encode())

    def _verify_fill_book(self, report, book):
        raw, content = read_document(self.shadow / report['execution_session'] / 'snapshot.json')
        if report['source_hashes'].get('snapshot') != hashlib.sha256(content).hexdigest():
            raise InputError('The session snapshot differs from the verified source hash.')
        snapshot = parse_snapshot(raw)
        declared = snapshot['portfolio']
        if snapshot['execution_session'].isoformat() != report['execution_session'] or any(
            declared[field] != (Decimal(book[field]) if field in ('cash','settled_cash') else book[field])
                for field in ('cash','settled_cash','shares','halted')):
            raise InputError('The current book differs from the verified session snapshot; no fill applied.')

    @contextmanager
    def _journal(self, *, readonly=False):
        try:
            if readonly:
                target = self.journal_path.resolve().as_uri() + '?mode=ro'
            else:
                self.shadow.mkdir(parents=True, exist_ok=True)
                target = str(self.journal_path)
            with closing(sqlite3.connect(target, uri=readonly, timeout=10)) as connection:
                connection.row_factory = sqlite3.Row
                if readonly:
                    connection.execute('PRAGMA query_only=ON')
                    connection.execute('BEGIN')
                    yield connection
                else:
                    connection.execute('PRAGMA synchronous=FULL')
                    connection.execute('PRAGMA fullfsync=ON')
                    with connection:
                        connection.execute('BEGIN IMMEDIATE')
                        connection.execute('CREATE TABLE IF NOT EXISTS fill_intents ('
                            'decision_id TEXT PRIMARY KEY, session TEXT NOT NULL, side TEXT NOT NULL, '
                            'quantity INTEGER NOT NULL, price TEXT NOT NULL, fees TEXT NOT NULL, '
                            'before_book TEXT NOT NULL, after_book TEXT NOT NULL, '
                            'before_hash TEXT NOT NULL, after_hash TEXT NOT NULL, '
                            'status TEXT NOT NULL CHECK(status IN ("pending","applied")), created_at TEXT NOT NULL)')
                        yield connection
        except sqlite3.Error as error:
            raise InputError(f'fill journal storage error: {error}') from error

    @staticmethod
    def _intents(connection):
        result = []
        try:
            for stored in connection.execute('SELECT * FROM fill_intents ORDER BY rowid'):
                row = dict(stored)
                if (not DECISION_ID.fullmatch(row['decision_id']) or row['side'] not in ('BUY','SELL')
                        or row['status'] not in ('pending', 'applied')):
                    raise InputError('invalid fill identity or state')
                iso_date(row['session'], 'fill session')
                whole(row['quantity'], 'fill quantity')
                decimal_value(row['price'], 'fill price', positive=True)
                decimal_value(row['fees'], 'fill fees')
                for field in ('before', 'after'):
                    content = row[field + '_book']
                    if not isinstance(content, str) or len(content) > 4096:
                        raise InputError('invalid fill book size')
                    book = _book(json.loads(content, object_pairs_hook=_pairs))
                    if canonical_json(book) != content or _hash(book) != row[field + '_hash']:
                        raise InputError('fill book hash mismatch')
                    row[field] = book
                result.append(row)
        except (KeyError, ValueError, TypeError, AttributeError) as error:
            raise InputError(f'corrupt fill journal: {error}') from error
        pending = [row for row in result if row['status'] == 'pending']
        if len(pending) > 1 or (pending and result[-1]['status'] != 'pending'):
            raise InputError('corrupt fill journal ordering')
        return result

    def _read_intents(self):
        if not self.journal_path.exists():
            return []
        with self._journal(readonly=True) as connection:
            return self._intents(connection)

    def _recover(self):
        """Only called under operator_lock, on an explicit mutation."""
        for row in self._read_intents():
            if row['status'] == 'pending':
                current = _hash(self._read_book())
                if current == row['before_hash']:
                    self._write_book(row['after'])
                elif current != row['after_hash']:
                    raise InputError('pending fill book divergence; retain files for reviewed recovery')
                with self._journal() as connection:
                    connection.execute('UPDATE fill_intents SET status="applied" WHERE decision_id=?',
                                       (row['decision_id'],))

    @staticmethod
    def _preserve_risk(book, reports):
        result = dict(book)
        if reports:
            memory = reports[0]['risk_memory']
            result['peak_nav'] = format(max(Decimal(book['peak_nav']), Decimal(memory['peak_nav'])), 'f')
            # The ledger's entry halt remains latched in verified history.
            # It must not become a global manual halt that also blocks exits.
        return _book(result)

    def snapshot(self):
        """Project local evidence; missing/corrupt inputs are reported separately."""
        tools = {name: (self.root / 'scripts' / name).is_file()
                 for name in ('run_daily.sh', 'daily_shadow.sh', 'run_study.sh')}
        environment = {'ready': sys.version_info >= (3,11) and all(tools.values()) and shutil.which('bash') is not None,
                       'python_version': '.'.join(map(str, sys.version_info[:3])), 'tools': tools,
                       'bash_present': shutil.which('bash') is not None}
        credentials = {'present': self.credentials_path.is_file(), 'path': str(self.credentials_path)}
        study = self.study_evidence.snapshot(verifier=verify_readiness)
        history = {'rows': [], 'total': 0, 'error': None, 'present': self.ledger_path.exists()}
        reports = []
        try:
            reports, history['total'] = self._reports()
        except InputError as error:
            history['error'] = str(error)
        portfolio = {'ready': False, 'book': None, 'error': None, 'accounting_pending': False,
                     'last_mark': None, 'entry_halted': None}
        intents = []
        try:
            if self.portfolio_path.exists():
                portfolio['book'] = self._read_book()
                portfolio['ready'] = True
            else:
                portfolio['error'] = 'Manual simulated portfolio is missing; initialize starting cash explicitly.'
            intents = self._read_intents()
            pending = [row for row in intents if row['status'] == 'pending']
            portfolio['accounting_pending'] = bool(pending)
            if pending:
                portfolio['ready'] = False
                if portfolio['book'] is None or _hash(portfolio['book']) not in (
                        pending[0]['before_hash'], pending[0]['after_hash']):
                    raise InputError('pending fill book divergence; retain files for reviewed recovery')
                portfolio['error'] = 'Pending simulated fill requires recovery on an explicit portfolio action.'
        except InputError as error:
            portfolio.update(ready=False, error=str(error))
        states = {row['decision_id']: row['status'] for row in intents}
        for index, report in enumerate(reports):
            proposal = report['proposal']
            state = states.get(report['decision_id'])
            eligible = index == 0 and proposal is not None and state is None and portfolio['ready']
            fill_error = None
            if eligible:
                try:
                    self._verify_fill_book(report, portfolio['book'])
                except InputError as error:
                    eligible, fill_error = False, str(error)
            history['rows'].append({'session': report['execution_session'],
                'action': proposal['side'] if proposal else report['status'],
                'quantity': proposal['quantity'] if proposal else 0,
                'reference_price': proposal['reference_price'] if proposal else None,
                'nav': report['effective_nav'], 'signal': report['signal'],
                'reason': ', '.join(report['blockers']) if report['blockers'] else (
                    'Verified proposal; no execution inferred.' if proposal else 'No trade proposed.'),
                'decision_id': report['decision_id'], 'mark_valid': report['risk_memory']['mark_valid'],
                'filled': state == 'applied', 'fill_state': state, 'detail': report,
                'latest': index == 0,
                'fill_eligible': eligible, 'fill_error': fill_error})
        if reports:
            portfolio['entry_halted'] = reports[0]['risk_memory']['entry_halted']
            mark = next((report for report in reports if report['risk_memory']['mark_valid']), None)
            if mark:
                portfolio['last_mark'] = {'session': mark['execution_session'], 'nav': mark['effective_nav']}
        if history['error']:
            portfolio.update(ready=False, error='Decision history must verify before portfolio changes: ' + history['error'])
        health = check_health(self.heartbeat_path, self.ledger_path)
        health.update(status='missing', updated_at=None, age_seconds=None, expected_session=None, expected_deadline=None)
        if self.heartbeat_path.exists():
            health['status'] = 'invalid'
            try:
                heartbeat = read_document(self.heartbeat_path)[0]
                _expectations(heartbeat)
                instant = datetime.fromisoformat(heartbeat['updated_at'])
                for key in ('status', 'updated_at', 'expected_session', 'expected_deadline'):
                    health[key] = heartbeat[key]
                health['age_seconds'] = (datetime.now(timezone.utc) - instant).total_seconds()
            except (InputError, KeyError, ValueError, TypeError):
                pass
        return {'mode': 'offline_shadow', 'generated_at': _now(), 'environment': environment,
                'credentials': credentials, 'study': study, 'portfolio': portfolio,
                'history': history, 'health': health}

    def save_keys(self, payload):
        strict_keys(payload, ('key_id','secret_key'), 'keys')
        if any(not isinstance(value, str) or TOKEN.fullmatch(value) is None for value in payload.values()):
            raise InputError('Keys must contain 1–256 letters, digits, underscores or hyphens.')
        with operator_lock(self.root):
            if self.credentials_path.is_relative_to(self.root):
                raise InputError('Credentials must be stored outside the checkout.')
            if self.credentials_path.is_symlink() or self.credentials_path.parent.is_symlink():
                raise InputError('Credential destination must not be a symlink.')
            try:
                self.config_home.mkdir(parents=True, exist_ok=True, mode=0o700)
                self.credentials_path.parent.mkdir(exist_ok=True, mode=0o700)
                os.chmod(self.config_home, 0o700)
                os.chmod(self.credentials_path.parent, 0o700)
            except OSError as error:
                raise InputError(f'Cannot prepare private key directory: {error}') from error
            content = f'APCA_API_KEY_ID={payload["key_id"]}\nAPCA_API_SECRET_KEY={payload["secret_key"]}\n'
            _atomic(self.credentials_path, content.encode())
        return {'ok': True, 'credentials': {'present': True, 'path': str(self.credentials_path)}}

    def initialize_book(self, payload):
        strict_keys(payload, ('cash',), 'initialize book')
        cash = decimal_value(payload['cash'], 'starting cash', positive=True)
        with operator_lock(self.root):
            if self.portfolio_path.exists() or self.portfolio_path.is_symlink():
                raise InputError('An existing portfolio cannot be initialized or replaced.')
            _, total = self._reports()
            if total or self.journal_path.exists():
                raise InputError('Existing decision/fill history prevents a new starting book; retain history for review.')
            book = {'schema_version':1, 'cash':format(cash,'f'), 'settled_cash':format(cash,'f'),
                    'shares':0, 'peak_nav':format(cash,'f'), 'halted':False}
            self._write_book(book)
        return {'ok':True, 'book':book}

    @fixed_decimal
    def record_fill(self, payload):
        strict_keys(payload, ('decision_id','price','fees'), 'simulated fill')
        identity = payload['decision_id']
        if not isinstance(identity, str) or DECISION_ID.fullmatch(identity) is None:
            raise InputError('A verified decision identity is required.')
        price = decimal_value(payload['price'], 'fill price', positive=True)
        fees = decimal_value(payload['fees'], 'fill fees')
        with operator_lock(self.root):
            reports, _ = self._reports()
            # Verify history before recovering accounting, preserving corrupt evidence.
            self._recover()
            if any(row['decision_id'] == identity for row in self._read_intents()):
                raise InputError('This decision already has a recorded simulated fill.')
            if not reports or reports[0]['decision_id'] != identity:
                raise InputError('Only the latest verified decision may receive a simulated fill.')
            report = reports[0]
            proposal = report['proposal']
            if report['status'] != 'PROPOSED' or not proposal or proposal['side'] not in ('BUY','SELL'):
                raise InputError('A verified BUY or SELL proposal is required.')
            before = self._read_book()
            self._verify_fill_book(report, before)
            quantity = whole(proposal['quantity'], 'proposal quantity')
            after = self._preserve_risk(_fill_book(before, proposal['side'], quantity, price, fees), reports)
            with self._journal() as connection:
                connection.execute('INSERT INTO fill_intents VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                    (identity, report['execution_session'], proposal['side'], quantity, format(price,'f'),
                     format(fees,'f'), canonical_json(before), canonical_json(after), _hash(before), _hash(after),
                     'pending', _now()))
            # The intent is committed before replacing the book. Recovery accepts
            # exactly these two canonical states, never a guessed balance.
            self._write_book(after)
            with self._journal() as connection:
                connection.execute('UPDATE fill_intents SET status="applied" WHERE decision_id=?', (identity,))
        return {'ok':True, 'book':after, 'decision_id':identity}

    def recover_accounting(self, payload):
        strict_keys(payload, (), 'recover accounting')
        with operator_lock(self.root):
            self._reports()
            self._recover()
            book=self._read_book()
        return {'ok':True, 'book':book}

    def set_halt(self, payload):
        strict_keys(payload, (), 'halt')
        with operator_lock(self.root):
            reports, _ = self._reports()
            self._recover()
            book = self._preserve_risk(self._read_book(), reports)
            book['halted'] = True
            self._write_book(book)
        return {'ok':True, 'book':book}

    def settle_cash(self, payload):
        strict_keys(payload, (), 'settle cash')
        with operator_lock(self.root):
            reports, _ = self._reports()
            self._recover()
            book = self._preserve_risk(self._read_book(), reports)
            book['settled_cash'] = book['cash']
            self._write_book(book)
        return {'ok':True, 'book':book}
