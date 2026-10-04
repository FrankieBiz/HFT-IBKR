import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from quant_local.preflight import assess, parse_inventory, run_probe, collect


GIB = 1024 ** 3


def evidence():
    return {
        'system': 'Linux', 'python': [3, 12, 8], 'ram_bytes': 32 * GIB,
        'packages': {'torch': '2.14.0', 'laya': '0.3.27'},
        'nvidia': {'ok': True, 'devices': []},
        'gpu_index': 0,
        'cuda': {'ok': True, 'device_index': 0, 'device_name': 'NVIDIA GeForce RTX 3070 Ti',
                 'torch_version': '2.14.0', 'cuda_version': '12.8',
                 'total_bytes': 8 * GIB, 'free_bytes': 6 * GIB,
                 'capability': [8, 6], 'bf16_supported': True, 'smoke_result': 6.0},
    }


class PreflightTests(unittest.TestCase):
    def test_good_environment_only_allows_model_benchmark(self):
        result = assess(evidence())
        self.assertEqual(result['status'], 'ready_for_model_benchmark')
        self.assertEqual(result['blockers'], [])
        self.assertFalse(result['model_benchmark_run'])

    def test_required_measurements_fail_closed(self):
        changes = [
            ('system', 'Windows', 'platform'), ('python', [3, 11, 9], 'python'),
            ('python', [3, 15, 0], 'python'), ('ram_bytes', None, 'ram'),
            ('ram_bytes', 27 * GIB, 'ram'), ('ram_bytes', True, 'ram'),
            ('cuda', {'ok': False, 'error': 'timeout'}, 'cuda'),
            ('cuda', {'skipped': True}, 'cuda'),
            ('packages', {'torch': '2.14.0'}, 'laya'),
            ('packages', {'laya': '0.3.27'}, 'torch'),
        ]
        for key, value, blocker in changes:
            with self.subTest(key=key, value=value):
                sample = evidence()
                sample[key] = value
                result = assess(sample)
                self.assertEqual(result['status'], 'blocked')
                self.assertIn(blocker, [x['id'] for x in result['blockers']])

    def test_cuda_bad_evidence_cannot_pass(self):
        changes = [('free_bytes', 3 * GIB), ('total_bytes', 7 * GIB),
                   ('free_bytes', 9 * GIB), ('free_bytes', True),
                   ('smoke_result', 5.0), ('device_index', 1),
                   ('device_index', True), ('device_name', ''),
                   ('torch_version', 'other'), ('bf16_supported', 'true'),
                   ('capability', None), ('ok', 1)]
        for key, value in changes:
            with self.subTest(key=key):
                sample = evidence()
                sample['cuda'][key] = value
                self.assertEqual(assess(sample)['status'], 'blocked')

    def test_smi_is_advisory_and_indices_are_not_matched(self):
        sample = evidence()
        sample['nvidia'] = {'ok': True, 'devices': [
            {'index': 3, 'name': 'Other GPU', 'total_mib': 24576, 'free_mib': 20000,
             'driver': 'test'}]}
        self.assertEqual(assess(sample)['status'], 'ready_for_model_benchmark')
        sample['nvidia'] = {'ok': False, 'error': 'not installed'}
        self.assertEqual(assess(sample)['status'], 'ready_for_model_benchmark')

    def test_inventory_unknown_or_inconsistent_memory_is_rejected(self):
        parsed = parse_inventory('0, NVIDIA GeForce RTX 3070 Ti, 580.00, 8192, 6000\n')
        self.assertEqual(parsed[0]['total_mib'], 8192)
        for value in ['0, card, driver, N/A, 6000', '0, card, driver, 100, 200',
                      '0, card, driver, -1, 0', '', 'broken',
                      '0, card, driver, 8192, 6000\n0, card, driver, 8192, 6000']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_inventory(value)

    def test_missing_or_timed_out_process_is_recorded(self):
        for error in [FileNotFoundError(), subprocess.TimeoutExpired('probe', 1)]:
            with patch('quant_local.preflight.subprocess.run', side_effect=error):
                result = run_probe(['probe'], timeout=1)
            self.assertFalse(result['ok'])

    def test_real_child_deadline_and_failed_exit(self):
        result = run_probe([sys.executable, '-I', '-c', 'import time; time.sleep(10)'], timeout=0.05)
        self.assertFalse(result['ok'])
        self.assertIn('timed out', result['error'])
        result = run_probe([sys.executable, '-I', '-c', 'raise SystemExit(7)'], timeout=5)
        self.assertEqual(result, {'ok': False, 'error': 'probe exited 7'})

    def test_resource_policy_boundaries(self):
        sample = evidence()
        sample['ram_bytes'] = 28 * GIB
        sample['cuda']['total_bytes'] = 15 * GIB // 2
        sample['cuda']['free_bytes'] = 4 * GIB
        self.assertEqual(assess(sample)['status'], 'ready_for_model_benchmark')
        sample['cuda']['free_bytes'] -= 1
        self.assertEqual(assess(sample)['status'], 'blocked')

    def test_skipped_cuda_never_executes_torch(self):
        with patch('quant_local.preflight.run_probe', return_value={'ok': False, 'error': 'absent'}) as run:
            sample = collect(skip_cuda=True)
        self.assertEqual(run.call_count, 1)  # inventory only; no Python CUDA child
        self.assertEqual(sample['cuda'], {'skipped': True})
        self.assertEqual(assess(sample)['status'], 'blocked')

    def test_successful_cuda_child_output_must_be_strict_json(self):
        with patch('quant_local.preflight.package_versions', return_value={'torch': 'test'}), \
             patch('quant_local.preflight.run_probe', side_effect=[
                 {'ok': False, 'error': 'absent'}, {'ok': True, 'stdout': '{"ok":true,"free_bytes":NaN}'}]):
            sample = collect()
        self.assertFalse(sample['cuda']['ok'])


class PreflightCliTests(unittest.TestCase):
    def test_blocked_report_and_non_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'report.json'
            command = [sys.executable, '-m', 'quant_local', 'preflight', '--skip-cuda', '--output', str(output)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2, result.stderr)
            report = json.loads(output.read_text())
            self.assertEqual(report['status'], 'blocked')
            self.assertIn('cuda', [x['id'] for x in report['blockers']])
            original = output.read_bytes()
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(output.read_bytes(), original)

    def test_invalid_gpu_index_creates_no_report(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'report.json'
            result = subprocess.run([sys.executable, '-m', 'quant_local', 'preflight',
                                     '--gpu-index', '-1', '--output', str(output)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(output.exists())

    def test_dangling_output_symlink_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'report.json'
            output.symlink_to(Path(folder) / 'missing.json')
            result = subprocess.run([sys.executable, '-m', 'quant_local', 'preflight',
                                     '--skip-cuda', '--output', str(output)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertTrue(output.is_symlink())
            self.assertFalse(output.exists())
