import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from quant_research.serde import InputError
from quant_session.readiness import verify_readiness
from test_shadow_readiness import evidence


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        _, paths = evidence(self.folder, real_bundle=True, feed='sip')
        self.paths = {key: paths[key+'.json'] for key in ('config','protocol','selection','holdout')}
        self.paths.update(bundle=self.folder/'spy.qdata', registry=paths['registry.sqlite'])

    def cache(self):
        from quant_app.evidence import StudyEvidence
        return StudyEvidence(self.paths)

    def test_verified_settings_cost_columns_and_defensive_copy(self):
        cache = self.cache()
        with patch('socket.socket', side_effect=AssertionError('offline')), \
                patch('quant_app.evidence.verify_readiness', wraps=verify_readiness) as gate:
            first = cache.snapshot()
            self.assertTrue(first['ready'])
            self.assertEqual(first['selected_lookback'], 2)
            self.assertEqual(first['settings']['target_fraction'], '0.8')
            self.assertEqual([row['cost_multiplier'] for row in first['cost_scenarios']], [1,2,5])
            self.assertEqual(first['cost_scenarios'][1]['trend']['total_return'], '0.1')
            self.assertEqual(first['cost_scenarios'][1]['benchmark']['total_return'], '0.2')
            self.assertIsNone(first['cost_scenarios'][0]['trend']['rejection_count'])
            first['settings']['lookback'] = 999
            self.assertEqual(cache.snapshot()['settings']['lookback'], 2)
            self.assertEqual(gate.call_count, 1)

    def test_changed_bytes_invalidate_even_with_same_size_and_mtime(self):
        cache = self.cache()
        self.assertTrue(cache.snapshot()['ready'])
        path = self.paths['holdout']
        original, stat = path.read_bytes(), path.stat()
        path.write_bytes(original.replace(b'0.1', b'0.9'))
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        self.assertFalse(cache.snapshot()['ready'])
        path.write_bytes(original)
        self.assertTrue(cache.snapshot()['ready'])

    def test_missing_file_can_be_repaired_and_wal_invalidates(self):
        cache = self.cache()
        path = self.paths['selection']
        original = path.read_bytes()
        path.unlink()
        self.assertFalse(cache.snapshot()['ready'])
        path.write_bytes(original)
        self.assertTrue(cache.snapshot()['ready'])
        with patch('quant_app.evidence.verify_readiness', side_effect=InputError('recheck')) as gate:
            Path(str(self.paths['registry'])+'-wal').write_bytes(b'invented sidecar')
            self.assertFalse(cache.snapshot()['ready'])
            self.assertEqual(gate.call_count, 1)

    def test_change_during_verification_never_publishes_qualified_state(self):
        cache = self.cache()
        def changing(**kwargs):
            result = verify_readiness(**kwargs)
            self.paths['holdout'].write_bytes(b'{}')
            return result
        with patch('quant_app.evidence.verify_readiness', side_effect=changing):
            status = cache.snapshot()
        self.assertFalse(status['ready'])
        self.assertIn('changed', status['error'])
