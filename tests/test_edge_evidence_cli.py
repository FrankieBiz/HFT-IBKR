import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_edge_evidence import fixture

ROOT = Path(__file__).resolve().parents[1]


class EvidenceCLITests(unittest.TestCase):
    def test_report_identity_no_overwrite_and_archive_equivalence(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            source, archive = folder / 'input.json', folder / 'app.pyz'
            source.write_text(json.dumps(fixture()))
            build = subprocess.run([sys.executable, str(ROOT / 'scripts/build.py'),
                                    '--output', str(archive)], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            outputs = [folder / 'source.json', folder / 'archive.json']
            for command, cwd, output in [
                ([sys.executable, '-m', 'quant_evidence'], ROOT, outputs[0]),
                ([sys.executable, str(archive), 'evidence'], folder, outputs[1]),
            ]:
                result = subprocess.run(command + ['assess', '--input', str(source),
                                                   '--output', str(output)], cwd=cwd,
                                        env={}, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(outputs[0].read_bytes(), outputs[1].read_bytes())
            report = json.loads(outputs[0].read_text())
            self.assertEqual(report['input_sha256'], hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual(report['input'], fixture())
            self.assertEqual(report['status'], 'diagnostic_only')
            self.assertFalse(report['promotion_allowed'])
            self.assertIn('evidence', report['code'])
            original = outputs[0].read_bytes()
            retry = subprocess.run([sys.executable, str(archive), 'evidence', 'assess',
                                    '--input', str(source), '--output', str(outputs[0])],
                                   cwd=folder, capture_output=True, text=True)
            self.assertEqual(retry.returncode, 2)
            self.assertEqual(outputs[0].read_bytes(), original)

    def test_duplicate_keys_and_invalid_input_emit_no_report(self):
        for content in ('{"schema_version":1,"schema_version":1}', '{}'):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as folder:
                source, output = Path(folder) / 'input.json', Path(folder) / 'out.json'
                source.write_text(content)
                result = subprocess.run([sys.executable, '-m', 'quant_evidence', 'assess',
                                         '--input', str(source), '--output', str(output)],
                                        cwd=ROOT, capture_output=True, text=True)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertFalse(output.exists())

    def test_unbounded_report_is_written_with_exit_zero_as_diagnostic(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder) / 'input.json', Path(folder) / 'out.json'
            raw = fixture()
            raw['scenarios']['primary'][0].update(outcome_bounded=False, gross_pnl=None,
                                                 quality_notes='Unknown exit price.')
            source.write_text(json.dumps(raw))
            result = subprocess.run([sys.executable, '-m', 'quant_evidence', 'assess',
                                     '--input', str(source), '--output', str(output)],
                                    cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(output.read_text())['numeric_assessment'], 'inconclusive')
