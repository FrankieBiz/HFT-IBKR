import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from quant_research.__main__ import main, source_identity, publish_report
from quant_research.serde import InputError
from test_inputs import write_dataset, raw_config

ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def inputs(self, folder):
        rows = [[f'2025-01-{i + 1:02}', str(p), str(p), str(p), str(p), '10000', '0', '']
                for i, p in enumerate([100, 100, 110, 120, 90, 80])]
        data, manifest = write_dataset(folder, rows)
        config = Path(folder) / 'config.json'
        config.write_text(json.dumps(raw_config()))
        return ['replay', '--data', str(data), '--manifest', str(manifest),
                '--config', str(config)]

    def call(self, args):
        # Empty environment prevents accidental use of account/client variables.
        return subprocess.run([sys.executable, '-m', 'quant_research', *args],
                              cwd=ROOT, env={}, capture_output=True, text=True)

    def test_cli_produces_identical_reproducible_reports(self):
        with tempfile.TemporaryDirectory() as folder:
            args = self.inputs(folder)
            first, second = Path(folder) / 'first.json', Path(folder) / 'second.json'
            for output in (first, second):
                result = self.call([*args, '--output', str(output)])
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            report = json.loads(first.read_text())
            self.assertEqual(report['data_kind'], 'synthetic')
            self.assertEqual(report['strategy_validation'], 'unproven')
            self.assertEqual(report['config']['mode'], 'simulation')
            self.assertEqual(report['provenance']['source'], 'unit test generated data')
            self.assertEqual(report['code']['version'], '0.1.0')
            self.assertEqual(len(report['code']['source_sha256']), 64)
            self.assertEqual(report['config_sha256'], hashlib.sha256((Path(folder) / 'config.json').read_bytes()).hexdigest())

    def test_rejects_existing_report_without_overwriting_it(self):
        with tempfile.TemporaryDirectory() as folder:
            args = self.inputs(folder)
            output = Path(folder) / 'report.json'
            output.write_text('preserve this')
            result = self.call([*args, '--output', str(output)])
            self.assertEqual(result.returncode, 2)
            self.assertEqual(output.read_text(), 'preserve this')
            self.assertEqual(list(Path(folder).glob('.research-*')), [])

    def test_invalid_config_data_and_start_leave_no_output(self):
        with tempfile.TemporaryDirectory() as folder:
            args = self.inputs(folder)
            output = Path(folder) / 'report.json'
            result = self.call([*args, '--evaluation-start', '2025-01-03', '--output', str(output)])
            self.assertEqual(result.returncode, 2)
            self.assertFalse(output.exists())
            config = Path(folder) / 'config.json'
            config.write_text(json.dumps(raw_config(mode='live')))
            self.assertEqual(self.call([*args, '--output', str(output)]).returncode, 2)
            self.assertFalse(output.exists())
            config.write_text(json.dumps(raw_config()))
            (Path(folder) / 'bars.csv').write_text('corrupt')
            self.assertEqual(self.call([*args, '--output', str(output)]).returncode, 2)
            self.assertFalse(output.exists())

    def test_in_process_cli_cannot_create_a_socket(self):
        with tempfile.TemporaryDirectory() as folder:
            args = self.inputs(folder)
            with patch('socket.socket', side_effect=AssertionError('network forbidden')):
                self.assertEqual(main([*args, '--output', str(Path(folder) / 'report.json')]), 0)

    def test_source_identity_covers_uncommitted_content(self):
        with tempfile.TemporaryDirectory() as folder:
            module = Path(folder) / 'a.py'
            module.write_text('x = 1\n')
            first = source_identity(Path(folder))
            module.write_text('x = 2\n')
            self.assertNotEqual(first, source_identity(Path(folder)))

    def test_failed_publication_cleans_temporary_file(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch('os.link', side_effect=OSError('storage error')):
                with self.assertRaises(InputError):
                    publish_report(Path(folder) / 'report.json', '{}\n')
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_unexpected_runtime_failure_is_distinct(self):
        with tempfile.TemporaryDirectory() as folder:
            args = self.inputs(folder)
            with patch('quant_research.__main__.run_research', side_effect=RuntimeError('unexpected')):
                self.assertEqual(main([*args, '--output', str(Path(folder) / 'report.json')]), 1)
            self.assertFalse((Path(folder) / 'report.json').exists())

    def test_config_digest_matches_consumed_bytes_even_if_file_changes(self):
        from quant_research.backtest import run_research as actual_run
        with tempfile.TemporaryDirectory() as folder:
            args = self.inputs(folder)
            config_path = Path(folder) / 'config.json'
            original = config_path.read_bytes()
            def run_and_change(*values):
                result = actual_run(*values)
                config_path.write_text(json.dumps(raw_config(initial_cash='999999')))
                return result
            output = Path(folder) / 'report.json'
            with patch('quant_research.__main__.run_research', side_effect=run_and_change):
                self.assertEqual(main([*args, '--output', str(output)]), 0)
            report = json.loads(output.read_text())
            self.assertEqual(report['config_sha256'], hashlib.sha256(original).hexdigest())
            self.assertEqual(report['config']['initial_cash'], '1000')
