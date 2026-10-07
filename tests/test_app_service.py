from contextlib import closing
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from quant_research.serde import InputError, canonical_json, read_json
from quant_session.inputs import parse_schedule, parse_snapshot
from quant_session.ledger import DecisionLedger
from quant_session.planner import plan_session
from test_shadow_session import fixtures


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('quant_app.service'), 'operator service is missing')
        from quant_app.service import Service
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'checkout'
        self.root.mkdir()
        self.home = Path(self.tmp.name) / 'config'
        self.service = Service(self.root, self.home)
        self.shadow = self.root / '.research-output/shadow'
        self.book = self.shadow / 'portfolio.json'

    def initialize(self):
        return self.service.initialize_book({'cash': '10000'})

    def proposal(self, *, sells=False):
        self.initialize()
        if sells:
            book = read_json(self.book)
            book['shares'] = 5
            self.book.write_text(canonical_json(book))
        data, config, schedule, snapshot = fixtures((102,100) if sells else (100,102), 5 if sells else 0)
        day = self.shadow / snapshot['execution_session']
        day.mkdir()
        content = canonical_json(snapshot).encode()
        (day / 'snapshot.json').write_bytes(content)
        report = plan_session(data, config, parse_schedule(schedule), parse_snapshot(snapshot),
                              {'snapshot': hashlib.sha256(content).hexdigest()})
        DecisionLedger(self.shadow / 'ledger.sqlite').record(report, 'fixture')
        return report

    def test_missing_inputs_are_truthful_and_snapshot_does_not_initialize(self):
        with patch('socket.socket', side_effect=AssertionError('status must stay offline')):
            status = self.service.snapshot()
        self.assertEqual(status['mode'], 'offline_shadow')
        self.assertFalse(status['credentials']['present'])
        self.assertFalse(status['portfolio']['ready'])
        self.assertFalse(status['study']['ready'])
        self.assertEqual(status['history']['rows'], [])
        self.assertEqual(status['history']['total'], 0)
        self.assertFalse(self.shadow.exists())
        self.assertFalse(self.home.exists())

    def test_fill_eligibility_tracks_original_book_and_snapshot(self):
        report = self.proposal()
        self.assertTrue(self.service.snapshot()['history']['rows'][0]['fill_eligible'])
        self.service.set_halt({})
        status = self.service.snapshot()
        self.assertFalse(status['history']['rows'][0]['fill_eligible'])
        self.assertIn('snapshot', status['history']['rows'][0]['fill_error'])
        with self.assertRaises(InputError):
            self.service.record_fill({'decision_id': report['decision_id'], 'price': '102', 'fees': '0'})

    def test_malformed_heartbeat_is_not_projected_as_a_status(self):
        self.shadow.mkdir(parents=True)
        heartbeat = {'schema_version': 1, 'status': 123, 'updated_at': '2026-10-07T14:00:00+00:00',
                     'expected_session': None, 'expected_deadline': None}
        self.service.heartbeat_path.write_text(canonical_json(heartbeat))
        status = self.service.snapshot()['health']
        self.assertFalse(status['healthy'])
        self.assertEqual(status['status'], 'invalid')

    def test_fill_eligibility_rejects_missing_and_changed_snapshot(self):
        report = self.proposal()
        path = self.shadow/str(report['execution_session'])/'snapshot.json'
        original = path.read_bytes()
        for content in (None, b'{}'):
            if content is None:
                path.unlink()
            else:
                path.write_bytes(content)
            row = self.service.snapshot()['history']['rows'][0]
            self.assertFalse(row['fill_eligible'])
            self.assertTrue(row['fill_error'])
        path.write_bytes(original)
        self.assertTrue(self.service.snapshot()['history']['rows'][0]['fill_eligible'])

    def test_cash_settlement_after_proposal_disables_fill(self):
        report = self.proposal(sells=True)
        path = self.shadow/str(report['execution_session'])/'snapshot.json'
        raw = read_json(path)
        raw['portfolio']['settled_cash'] = '9000'
        content = canonical_json(raw).encode()
        path.write_bytes(content)
        book = read_json(self.book)
        book['settled_cash'] = '9000'
        self.book.write_text(canonical_json(book))
        report['source_hashes']['snapshot'] = hashlib.sha256(content).hexdigest()
        from quant_session.planner import decision_digest
        report['decision_id'] = decision_digest(report)
        # Replace this invented rehearsal ledger; real histories are never reset.
        self.service.ledger_path.unlink()
        DecisionLedger(self.service.ledger_path).record(report, 'fixture')
        self.assertTrue(self.service.snapshot()['history']['rows'][0]['fill_eligible'])
        self.service.settle_cash({})
        self.assertFalse(self.service.snapshot()['history']['rows'][0]['fill_eligible'])

    def test_save_keys_simple_alphabet_permissions_and_no_values_in_result_or_status(self):
        fake = {'key_id': 'FAKE_key-123', 'secret_key': 'FAKE_secret-456'}
        result = self.service.save_keys(fake)
        path = self.home / 'alpaca/paper.env'
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(path.read_text(), 'APCA_API_KEY_ID=FAKE_key-123\nAPCA_API_SECRET_KEY=FAKE_secret-456\n')
        with patch.object(Path, 'read_bytes', autospec=True, side_effect=AssertionError('must not read keys')):
            # Isolated missing fixture inputs are allowed to fail before path.read_bytes.
            with patch('quant_app.service.verify_readiness', side_effect=InputError('missing evidence')), \
                    patch('quant_app.service.check_health', return_value={'healthy':False,'issues':[]}):
                status = self.service.snapshot()
        for value in fake.values():
            self.assertNotIn(value, json.dumps([result, status]))
        for value in ('x\nEXEC=1', '$(echo bad)', "bad'", 'x'*257, ''):
            with self.assertRaises(InputError):
                self.service.save_keys({'key_id':value, 'secret_key':'FAKE'})
        self.assertEqual(path.read_text().count('FAKE_key-123'), 1)

    def test_initialize_only_fresh_positive_book_and_preserve_existing_book(self):
        for value in ('0', '-1', 'NaN', '1e99', 12):
            with self.assertRaises(InputError):
                self.service.initialize_book({'cash':value})
        self.initialize()
        before = self.book.read_bytes()
        with self.assertRaises(InputError):
            self.service.initialize_book({'cash':'20000'})
        self.assertEqual(before, self.book.read_bytes())
        self.book.unlink()
        report = fixtures()
        DecisionLedger(self.shadow / 'ledger.sqlite').record(
            plan_session(report[0], report[1], parse_schedule(report[2]), parse_snapshot(report[3])), 'fixture')
        with self.assertRaisesRegex(InputError, 'history'):
            self.initialize()
        self.assertFalse(self.book.exists())

    def test_invalid_existing_book_fails_closed(self):
        self.initialize()
        base = read_json(self.book)
        for update in ({'settled_cash':'10001'}, {'shares':True}, {'cash':'-1'}, {'peak_nav':'0'},
                       {'halted':1}, {'unknown':1}):
            book = dict(base, **update)
            self.book.write_text(canonical_json(book))
            self.assertFalse(self.service.snapshot()['portfolio']['ready'])
            with self.assertRaises(InputError):
                self.service.set_halt({})
        self.book.write_text(canonical_json(base))
        self.service.set_halt({})
        self.assertTrue(read_json(self.book)['halted'])
        with self.assertRaises(InputError):
            self.service.set_halt({'halted':False})

    def test_verified_buy_fill_full_quantity_exactly_once_and_history_is_proposal(self):
        report = self.proposal()
        status = self.service.snapshot()
        row = status['history']['rows'][0]
        self.assertEqual(row['action'], 'BUY')
        self.assertFalse(row['filled'])
        result = self.service.record_fill({'decision_id':report['decision_id'], 'price':'103', 'fees':'1'})
        quantity = report['proposal']['quantity']
        self.assertEqual(result['book']['shares'], quantity)
        self.assertEqual(result['book']['cash'], str(10000-quantity*103-1))
        self.assertEqual(result['book']['settled_cash'], result['book']['cash'])
        self.assertGreaterEqual(float(result['book']['peak_nav']), 10000)
        self.assertTrue(self.service.snapshot()['history']['rows'][0]['filled'])
        before = self.book.read_bytes()
        with self.assertRaisesRegex(InputError, 'already'):
            self.service.record_fill({'decision_id':report['decision_id'], 'price':'103', 'fees':'1'})
        self.assertEqual(before, self.book.read_bytes())

    def test_sell_proceeds_unsettled_until_explicit_settlement(self):
        report = self.proposal(sells=True)
        self.service.record_fill({'decision_id':report['decision_id'], 'price':'100', 'fees':'1'})
        book = read_json(self.book)
        self.assertEqual((book['cash'],book['settled_cash'],book['shares']), ('10499','10000',0))
        self.service.settle_cash({})
        self.assertEqual(read_json(self.book)['settled_cash'], '10499')
        with self.assertRaises(InputError):
            self.service.settle_cash({'cash':'20000'})

    def test_fill_requires_matching_verified_snapshot_and_book(self):
        report = self.proposal()
        payload = {'decision_id':report['decision_id'], 'price':'103', 'fees':'1'}
        path = self.shadow / '2025-03-11/snapshot.json'
        original = path.read_bytes()
        path.write_bytes(original + b' ')
        with self.assertRaisesRegex(InputError, 'snapshot'):
            self.service.record_fill(payload)
        path.write_bytes(original)
        book = read_json(self.book)
        book['cash'] = '10001'
        self.book.write_text(canonical_json(book))
        with self.assertRaisesRegex(InputError, 'book'):
            self.service.record_fill(payload)

    def test_crash_before_and_after_atomic_write_recover_without_duplicate_fill(self):
        for after in (False, True):
            with self.subTest(after=after):
                # A fresh independent service/root for each crash location.
                self.shadow.mkdir(parents=True, exist_ok=True)
                for file in self.shadow.rglob('*'):
                    if file.is_file(): file.unlink()
                for folder in sorted(self.shadow.glob('*'), reverse=True):
                    if folder.is_dir(): folder.rmdir()
                report = self.proposal()
                payload = {'decision_id':report['decision_id'], 'price':'103', 'fees':'1'}
                original = self.service._write_book
                def crashing(book):
                    if after: original(book)
                    raise OSError('invented crash')
                with patch.object(self.service, '_write_book', side_effect=crashing):
                    with self.assertRaises((InputError,OSError)):
                        self.service.record_fill(payload)
                before = self.book.read_bytes()
                status = self.service.snapshot()
                self.assertTrue(status['portfolio']['accounting_pending'])
                self.assertEqual(before, self.book.read_bytes(), 'status must not recover')
                with self.assertRaisesRegex(InputError, 'already'):
                    self.service.record_fill(payload)
                self.assertEqual(read_json(self.book)['shares'], report['proposal']['quantity'])
                self.assertFalse(self.service.snapshot()['portfolio']['accounting_pending'])

    def test_pending_manual_divergence_is_rejected_without_replacing_book(self):
        report = self.proposal()
        with patch.object(self.service, '_write_book', side_effect=OSError('crash')):
            with self.assertRaises((InputError,OSError)):
                self.service.record_fill({'decision_id':report['decision_id'], 'price':'103', 'fees':'1'})
        book = read_json(self.book)
        book['cash'] = book['settled_cash'] = '9999'
        self.book.write_text(canonical_json(book))
        before = self.book.read_bytes()
        with self.assertRaisesRegex(InputError, 'diverg'):
            self.service.set_halt({})
        self.assertEqual(before, self.book.read_bytes())
        self.assertIn('diverg', self.service.snapshot()['portfolio']['error'])

    def test_corrupt_history_prevents_mutation(self):
        self.proposal()
        with closing(sqlite3.connect(self.shadow / 'ledger.sqlite')) as connection, connection:
            connection.execute('UPDATE decisions SET report=?', (b'{}',))
        status = self.service.snapshot()
        self.assertEqual(status['history']['rows'], [])
        self.assertIn('corrupt', status['history']['error'])
        with self.assertRaises(InputError):
            self.service.set_halt({})

    def test_locked_runner_rejects_all_mutations(self):
        from quant_app.locking import operator_lock
        self.initialize()
        with operator_lock(self.root):
            for method, payload in ((self.service.set_halt,{}), (self.service.settle_cash,{}),
                (self.service.save_keys,{'key_id':'FAKE','secret_key':'FAKE'}),
                (self.service.initialize_book,{'cash':'10000'}),
                (self.service.record_fill,{'decision_id':'a'*64,'price':'1','fees':'0'})):
                with self.assertRaises(InputError): method(payload)

    def test_current_project_tools_are_detected(self):
        scripts = self.root / 'scripts'
        scripts.mkdir()
        for name in ('run_daily.sh','daily_shadow.sh','run_study.sh'):
            (scripts / name).write_text('# invented tool\n')
        self.assertTrue(self.service.snapshot()['environment']['ready'])

    def test_valid_hash_with_malformed_proposal_is_reported_as_corruption(self):
        from quant_session.planner import decision_digest
        report = self.proposal()
        report['proposal'] = {'side': 'BUY', 'quantity': 'many'}
        report['decision_id'] = decision_digest(report)
        content = canonical_json(report).encode()
        with closing(sqlite3.connect(self.shadow / 'ledger.sqlite')) as connection, connection:
            connection.execute('UPDATE decisions SET report=?,decision_id=?,report_sha256=?',
                (content, report['decision_id'], hashlib.sha256(content).hexdigest()))
        status = self.service.snapshot()
        self.assertIn('corrupt', status['history']['error'])
        self.assertEqual(status['history']['rows'], [])
        with self.assertRaises(InputError):
            self.service.settle_cash({})

    def test_peak_and_drawdown_halt_are_retained_on_manual_accounting(self):
        from quant_session.planner import decision_digest
        report = self.proposal(sells=True)
        report['risk_memory'].update(peak_nav='20000', maximum_drawdown='0.5', entry_halted=True)
        report['decision_id'] = decision_digest(report)
        content = canonical_json(report).encode()
        with closing(sqlite3.connect(self.shadow / 'ledger.sqlite')) as connection, connection:
            connection.execute('UPDATE decisions SET report=?,decision_id=?,report_sha256=?',
                (content, report['decision_id'], hashlib.sha256(content).hexdigest()))
        result = self.service.settle_cash({})
        self.assertEqual(result['book']['peak_nav'], '20000')
        self.assertFalse(result['book']['halted'], 'entry halt must keep reducing exits available')
        self.assertTrue(self.service.snapshot()['portfolio']['entry_halted'])
        filled = self.service.record_fill({'decision_id':report['decision_id'], 'price':'100','fees':'1'})
        self.assertEqual(filled['book']['shares'], 0)
        self.assertEqual(filled['book']['peak_nav'], '20000')
        self.assertFalse(filled['book']['halted'])
        self.assertTrue(self.service.snapshot()['portfolio']['entry_halted'])

    def test_only_latest_decision_fill_allowed_and_fill_bounds(self):
        from quant_session.planner import decision_digest
        report = self.proposal()
        for price, fees in (('0','0'), ('103','104000'), ('1000000000000000000','0'), ('103', '-1')):
            with self.assertRaises(InputError):
                self.service.record_fill({'decision_id':report['decision_id'], 'price':price,'fees':fees})
        self.assertEqual(read_json(self.book)['shares'], 0)
        second = copy.deepcopy(report)
        second['execution_session'] = '2025-03-12'
        second['risk_memory']['previous_session'] = '2025-03-11'
        second['status'] = 'HOLD'
        second['proposal'] = None
        second['decision_id'] = decision_digest(second)
        DecisionLedger(self.shadow / 'ledger.sqlite').record(second, 'next fixture')
        with self.assertRaisesRegex(InputError, 'latest'):
            self.service.record_fill({'decision_id':report['decision_id'], 'price':'103','fees':'0'})
        with self.assertRaisesRegex(InputError, 'proposal'):
            self.service.record_fill({'decision_id':second['decision_id'], 'price':'103','fees':'0'})

    def test_fill_uses_fixed_decimal_context(self):
        from decimal import localcontext
        report = self.proposal()
        with localcontext() as context:
            context.prec = 3
            result = self.service.record_fill({'decision_id':report['decision_id'], 'price':'103.01','fees':'0.25'})
        from decimal import Decimal
        expected = Decimal('10000') - report['proposal']['quantity'] * Decimal('103.01') - Decimal('0.25')
        self.assertEqual(Decimal(result['book']['cash']), expected)

    def test_authenticated_study_feed_is_retained_and_readonly(self):
        from test_shadow_readiness import evidence
        source = self.root / 'fixture-study'
        source.mkdir()
        _, paths = evidence(source, real_bundle=True, feed='sip')
        for key, original in (('bundle',source/'spy.qdata'), ('config',paths['config.json']),
            ('protocol',paths['protocol.json']), ('selection',paths['selection.json']),
            ('holdout',paths['holdout.json']), ('registry',paths['registry.sqlite'])):
            target = self.service.study_paths[key]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(original.read_bytes())
        before = self.service.study_paths['registry'].read_bytes()
        with patch('socket.socket', side_effect=AssertionError('no transport on status')):
            study = self.service.snapshot()['study']
        self.assertTrue(study['ready'], study['error'])
        self.assertEqual(study['feed'], 'sip')
        self.assertEqual(before, self.service.study_paths['registry'].read_bytes())

    def test_accounting_rejects_rounding_away_a_supported_tiny_charge(self):
        from quant_session.planner import decision_digest
        report = self.proposal()
        book = read_json(self.book)
        for field in ('cash','settled_cash','peak_nav'):
            book[field] = '1000000000000000000'
        self.book.write_text(canonical_json(book))
        path = self.shadow / '2025-03-11/snapshot.json'
        snapshot = read_json(path)
        for field in ('cash','settled_cash','peak_nav','nav'):
            snapshot['portfolio'][field] = '1000000000000000000'
        content = canonical_json(snapshot).encode()
        path.write_bytes(content)
        report['source_hashes']['snapshot'] = hashlib.sha256(content).hexdigest()
        report['effective_nav'] = report['declared_nav'] = '1000000000000000000'
        report['risk_memory']['peak_nav'] = '1000000000000000000'
        report['decision_id'] = decision_digest(report)
        content = canonical_json(report).encode()
        with closing(sqlite3.connect(self.shadow / 'ledger.sqlite')) as connection, connection:
            connection.execute('UPDATE decisions SET report=?,decision_id=?,report_sha256=?',
                (content, report['decision_id'], hashlib.sha256(content).hexdigest()))
        before = self.book.read_bytes()
        with self.assertRaisesRegex(InputError, 'precision'):
            self.service.record_fill({'decision_id':report['decision_id'], 'price':'0.000000000001', 'fees':'0'})
        self.assertEqual(before, self.book.read_bytes())


class TerminalAccountingGuardTests(unittest.TestCase):
    def test_pending_fill_blocks_guard_without_recovering_book(self):
        case=ServiceTests()
        case.setUp()
        try:
            from quant_app.accounting import check_accounting
            report=case.proposal()
            before=case.book.read_bytes()
            with patch.object(case.service,'_write_book',side_effect=InputError('invented crash')):
                with case.assertRaises(InputError):
                    case.service.record_fill({'decision_id':report['decision_id'],'price':'103','fees':'1'})
            with case.assertRaisesRegex(InputError,'Pending simulated fill'):
                check_accounting(case.root)
            case.assertEqual(case.book.read_bytes(),before)
            case.service.recover_accounting({})
            check_accounting(case.root)
        finally:
            case.doCleanups()


class RecoveryActionTests(unittest.TestCase):
    def test_recovery_does_not_force_sell_settlement_or_global_halt(self):
        case=ServiceTests()
        case.setUp()
        try:
            report=case.proposal(sells=True)
            with patch.object(case.service,'_write_book',side_effect=InputError('invented crash')):
                with case.assertRaises(InputError):
                    case.service.record_fill({'decision_id':report['decision_id'],'price':'102','fees':'1'})
            result=case.service.recover_accounting({})
            case.assertEqual(result['book']['settled_cash'],'10000')
            case.assertGreater(float(result['book']['cash']),10000)
            case.assertFalse(result['book']['halted'])
            case.assertFalse(case.service.snapshot()['portfolio']['accounting_pending'])
        finally:
            case.doCleanups()
