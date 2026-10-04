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
