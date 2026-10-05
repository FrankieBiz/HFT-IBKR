import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_economics import config

ROOT = Path(__file__).resolve().parents[1]


class EconomicsCLITests(unittest.TestCase):
    def test_deterministic_report_provenance_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'config.json'
            source.write_text(json.dumps(config()))
            outputs = [Path(folder) / f'{i}.json' for i in range(2)]
            for output in outputs:
                result = subprocess.run([sys.executable, '-m', 'quant_economics', 'assess',
                                         '--config', str(source), '--output', str(output)],
                                        cwd=ROOT, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(outputs[0].read_bytes(), outputs[1].read_bytes())
            report = json.loads(outputs[0].read_text())
            self.assertEqual(report['input_sha256'], hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual(report['config'], config())
            self.assertIn('economics', report['code'])
            self.assertEqual(report['status'], 'conditional_analysis')
            original = outputs[0].read_bytes()
            result = subprocess.run([sys.executable, '-m', 'quant_economics', 'assess',
                                     '--config', str(source), '--output', str(outputs[0])],
                                    cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(outputs[0].read_bytes(), original)

    def test_duplicate_json_key_rejected_without_output(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder) / 'in.json', Path(folder) / 'out.json'
            source.write_text('{"schema_version":1,"schema_version":1}')
            result = subprocess.run([sys.executable, '-m', 'quant_economics', 'assess',
                                     '--config', str(source), '--output', str(output)],
                                    cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn('duplicate JSON key', result.stderr)
            self.assertFalse(output.exists())

    def test_portable_archive_matches_checkout_report(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / 'quant.pyz'
            source = ROOT / 'examples/economics/synthetic.json'
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/build.py'),
                                     '--output', str(archive)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            outputs = [Path(folder) / 'source.json', Path(folder) / 'archive.json']
            for command, cwd, output in [
                ([sys.executable, '-m', 'quant_economics'], ROOT, outputs[0]),
                ([sys.executable, str(archive), 'economics'], folder, outputs[1]),
            ]:
                result = subprocess.run(command + ['assess', '--config', str(source),
                                                   '--output', str(output)], cwd=cwd,
                                        env={}, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(outputs[0].read_bytes(), outputs[1].read_bytes())
