import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from quant_data.bundle import prepare_bundle
from quant_research.__main__ import main

ROOT = Path(__file__).resolve().parents[1]


class RobustnessCliTests(unittest.TestCase):
    def invoke(self, args):
        try:
            return main(args)
        except SystemExit as error:
            return error.code

    def args(self, output):
        return ['robustness', '--data', str(ROOT / 'examples/synthetic_spy_daily.csv'),
                '--manifest', str(ROOT / 'examples/synthetic_spy_manifest.json'),
                '--config', str(ROOT / 'examples/research_config.json'),
                '--protocol', str(ROOT / 'examples/synthetic_protocol.json'),
                '--train-sessions', '30', '--test-sessions', '20', '--block-size', '5',
                '--samples', '10', '--seed', '7', '--output', str(output)]

    def test_diagnostics_are_offline_deterministic_and_cannot_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'robustness.json'
            with patch('socket.socket', side_effect=AssertionError('network forbidden')):
                self.assertEqual(self.invoke(self.args(output)), 0)
            report = json.loads(output.read_text())
            self.assertEqual(report['mode'], 'offline_robustness_diagnostics')
            self.assertNotIn('selected_lookback', report)
            self.assertEqual(report['settings']['seed'], 7)
            second = Path(folder) / 'second.json'
            self.assertEqual(main(self.args(second)), 0)
            self.assertEqual(output.read_bytes(), second.read_bytes())
            original = output.read_bytes()
            self.assertEqual(main(self.args(output)), 2)
            self.assertEqual(output.read_bytes(), original)

    def test_bad_bounds_do_not_publish(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'report.json'
            self.assertEqual(main(self.args(output) + ['--samples', '10001']), 2)
            self.assertFalse(output.exists())

    def test_bundle_input_and_explicit_fold_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            bundle, output = [Path(folder) / name for name in ('spy.qdata', 'report.json')]
            intake = ROOT / 'examples/intake'
            prepare_bundle(*(intake / name for name in (
                'prices.csv', 'distributions.csv', 'calendar.csv', 'metadata.json')), bundle)
            args = self.args(output)
            # Replace the legacy CSV and manifest flags with the immutable bundle.
            args = [args[0], '--bundle', str(bundle), *args[5:], '--folds', '2']
            self.assertEqual(main(args), 0)
            report = json.loads(output.read_text())
            self.assertEqual(report['walk_forward']['fold_count'], 2)
            self.assertEqual(report['settings']['folds'], 2)
            self.assertIn('integrity_digest', report)
