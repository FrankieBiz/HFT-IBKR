from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from quant_research.serde import InputError, canonical_json
from test_shadow_readiness import evidence


class StudyRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        _, self.paths = evidence(self.folder, real_bundle=True, feed='sip')

    def recover(self):
        from quant_session.study_recovery import recover_study
        return recover_study(bundle=self.folder/'spy.qdata', config=self.paths['config.json'],
            protocol=self.paths['protocol.json'], registry=self.paths['registry.sqlite'],
            output=self.folder, validation_run='validation', holdout_run='holdout')

    def test_restore_completed_artifacts_without_touching_registry_or_existing_files(self):
        original = {name: self.paths[name].read_bytes() for name in ('selection.json','holdout.json')}
        registry = self.paths['registry.sqlite'].read_bytes()
        for name in original:
            self.paths[name].unlink()
        with patch('socket.socket', side_effect=AssertionError('offline recovery')):
            self.assertEqual(self.recover(), ['validation.json','selection.json','holdout.json'])
        for name, content in original.items():
            self.assertEqual(self.paths[name].read_bytes(), content)
        self.assertEqual(registry, self.paths['registry.sqlite'].read_bytes())
        self.assertEqual(self.recover(), [])

    def test_divergent_existing_output_blocks_all_exports(self):
        self.paths['holdout.json'].write_bytes(b'{}')
        self.paths['selection.json'].unlink()
        with self.assertRaisesRegex(InputError, 'differs'):
            self.recover()
        self.assertFalse(self.paths['selection.json'].exists())
        self.assertFalse((self.folder/'validation.json').exists())
        self.assertEqual(self.paths['holdout.json'].read_bytes(), b'{}')

    def test_rejected_completed_results_are_restored_without_qualifying_them(self):
        with tempfile.TemporaryDirectory() as directory:
            self.folder = Path(directory)
            _, self.paths = evidence(self.folder, real_bundle=True, drawdown='0.2')
            original = self.paths['holdout.json'].read_bytes()
            self.paths['holdout.json'].unlink()
            self.recover()
            self.assertEqual(self.paths['holdout.json'].read_bytes(), original)
            from quant_session.readiness import verify_readiness
            with self.assertRaisesRegex(InputError, 'verdict'):
                verify_readiness(bundle=self.folder/'spy.qdata', config=self.paths['config.json'],
                    protocol=self.paths['protocol.json'], selection=self.paths['selection.json'],
                    holdout=self.paths['holdout.json'], registry=self.paths['registry.sqlite'])

    def test_fresh_registry_without_data_is_allowed_but_reserved_validation_blocks(self):
        from quant_research.experiments import ExperimentRegistry
        from quant_session.study_recovery import recover_study, VALIDATION_RUN
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            registry = folder/'registry.sqlite'
            with ExperimentRegistry(registry):
                pass
            kwargs = dict(bundle=folder/'absent.qdata',config=folder/'config.json',
                          protocol=folder/'protocol.json',registry=registry,output=folder)
            self.assertEqual(recover_study(**kwargs), [])
            with ExperimentRegistry(registry) as db:
                db.reserve_validation(VALIDATION_RUN, {})
            before = registry.read_bytes()
            with self.assertRaisesRegex(InputError, 'do not rerun/reset'):
                recover_study(**kwargs)
            self.assertEqual(registry.read_bytes(), before)

    def test_changed_inputs_or_payload_never_recompute_or_publish(self):
        self.paths['holdout.json'].unlink()
        config = self.paths['config.json']
        config.write_bytes(config.read_bytes().replace(b'0.8',b'0.7'))
        with self.assertRaisesRegex(InputError, 'identit'):
            self.recover()
        self.assertFalse((self.folder/'validation.json').exists())
        self.assertFalse(self.paths['holdout.json'].exists())

    def test_reserved_failed_or_missing_freeze_requires_review(self):
        for state in ('reserved','failed','no-freeze','corrupt-payload'):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as directory:
                previous = self.folder, self.paths
                self.folder = Path(directory)
                _, self.paths = evidence(self.folder, real_bundle=True)
                with sqlite3.connect(self.paths['registry.sqlite']) as db:
                    # Deliberately damage this invented registry, never real history.
                    for name in ('events_no_delete','events_no_update','freezes_no_delete','payloads_no_update'):
                        db.execute('DROP TRIGGER '+name)
                    if state in ('reserved','failed'):
                        db.execute("DELETE FROM events WHERE run_id='holdout' AND status='completed'")
                        if state == 'failed':
                            db.execute("UPDATE events SET status='failed',error='fixture' WHERE run_id='holdout'")
                    elif state == 'no-freeze':
                        db.execute('DELETE FROM frozen_selections')
                    else:
                        db.execute("UPDATE result_payloads SET payload='{}' WHERE run_id='validation'")
                self.paths['holdout.json'].unlink()
                before = self.paths['registry.sqlite'].read_bytes()
                with self.assertRaises(InputError):
                    self.recover()
                self.assertEqual(before, self.paths['registry.sqlite'].read_bytes())
                self.assertFalse((self.folder/'validation.json').exists())
                self.assertFalse(self.paths['holdout.json'].exists())
                self.folder, self.paths = previous
