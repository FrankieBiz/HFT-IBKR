import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DemoTests(unittest.TestCase):
    def test_full_demo_generates_view_after_expected_config_rejection(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'demo'
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/demo.py'),
                                     '--output-dir', str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads((output / 'summary.json').read_text())
            self.assertEqual(summary['control_scenarios'], 14)
            self.assertEqual(summary['results_view'], 'dashboard.html')
            self.assertTrue((output / 'dashboard.html').is_file())
            self.assertFalse((output / 'A03.json').exists())
            self.assertEqual(summary['shadow_session_actions'], ['BUY', 'HOLD', 'SELL', 'BLOCKED'])
            self.assertEqual(summary['shadow_session_retry'], 'byte_identical')
            self.assertEqual(summary['shadow_session_conflict'], 'rejected')
            self.assertEqual(summary['robustness_diagnostics'], 'development_validation_only')
            robustness = json.loads((output / 'robustness.json').read_text())
            self.assertEqual(robustness['mode'], 'offline_robustness_diagnostics')
            self.assertGreater(robustness['walk_forward']['fold_count'], 0)
            self.assertEqual(robustness['resampling']['samples'], 50)
            buy = json.loads((output / 'shadow-buy.json').read_text())
            self.assertEqual(buy['mode'], 'offline_shadow')
            self.assertEqual(buy['status'], 'PROPOSED')
            self.assertEqual(buy['proposal']['side'], 'BUY')
            self.assertGreater(buy['proposal']['quantity'], 0)
