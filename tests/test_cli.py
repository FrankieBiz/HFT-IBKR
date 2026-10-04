import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CliTests(unittest.TestCase):
    def test_demo_offline_roundtrip_and_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            result = subprocess.run([sys.executable, '-m', 'quantlab', 'demo', '--output', folder],
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((root/'result.json').read_text())
            self.assertEqual(report['mode'], 'simulation')
            self.assertIn('dataset_id', report['provenance'])
            self.assertIn('code_revision', report['provenance'])
            self.assertGreater(report['summary']['fills'], 0)
            self.assertTrue((root/'report.html').exists())
            self.assertTrue((root/'research-packet.md').exists())

    def test_invalid_live_mode_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'bad.toml'
            path.write_text('mode="live"\n')
            result = subprocess.run([sys.executable, '-m', 'quantlab', 'validate-config', str(path)],
                                    text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('offline', result.stderr)

    def test_report_escapes_untrusted_metadata(self):
        from quantlab.reporting import render_report
        report = dict(mode='simulation', summary={'state': '<script>alert(1)</script>'}, equity=[],
                      fills=[], provenance={}, assumptions=[])
        self.assertNotIn('<script>alert(1)</script>', render_report(report))

    def test_demo_refuses_overwrite_and_seed_is_reproducible(self):
        with tempfile.TemporaryDirectory() as folder:
            first, second = Path(folder)/'first', Path(folder)/'second'
            command = [sys.executable, '-m', 'quantlab', 'demo', '--output']
            self.assertEqual(subprocess.run(command+[str(first)], capture_output=True).returncode, 0)
            before = (first/'result.json').read_bytes()
            self.assertNotEqual(subprocess.run(command+[str(first)], capture_output=True).returncode, 0)
            self.assertEqual((first/'result.json').read_bytes(), before)
            self.assertEqual(subprocess.run(command+[str(second)], capture_output=True).returncode, 0)
            self.assertEqual((first/'synthetic.csv').read_bytes(), (second/'synthetic.csv').read_bytes())
            a, b = [json.loads((p/'result.json').read_text()) for p in (first, second)]
            self.assertEqual(a['fills'], b['fills'])
            self.assertEqual(a['equity'], b['equity'])

    def test_report_rejects_nonfinite_and_input_overwrite(self):
        from quantlab.reporting import render_report
        report = dict(mode='simulation', summary={}, equity=[{'equity':float('nan')}], fills=[], provenance={}, assumptions=[])
        with self.assertRaises(ValueError):
            render_report(report)
        with tempfile.TemporaryDirectory() as folder:
            report['equity'] = []
            path = Path(folder)/'result.json'
            original = json.dumps(report)
            path.write_text(original)
            result = subprocess.run([sys.executable, '-m', 'quantlab', 'report', str(path), '--output', str(path)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(path.read_text(), original)

    def test_artifacts_refuse_symlink_targets(self):
        from quantlab.reporting import write_artifacts
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root/'precious.txt'
            target.write_text('keep')
            output = root/'run'
            output.mkdir()
            (output/'result.json').symlink_to(target)
            report = dict(mode='simulation', summary={}, equity=[], fills=[], provenance={}, assumptions=[])
            with self.assertRaises(FileExistsError):
                write_artifacts(report, output)
            self.assertEqual(target.read_text(), 'keep')

    def test_research_command_and_persistent_registry(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            demo = root/'demo'
            subprocess.run([sys.executable, '-m', 'quantlab', 'demo', '--output', str(demo)],
                           check=True, capture_output=True)
            command = [sys.executable, '-m', 'quantlab', 'research', '--database', str(demo/'history.sqlite'),
                       '--config', 'examples/simulation.toml', '--output', str(root/'research'),
                       '--registry', str(root/'research.sqlite')]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            research = json.loads((root/'research'/'research.json').read_text())
            self.assertEqual(research['mode'], 'offline_research')
            self.assertEqual(research['campaign_trial_count'], 3)
            rendered = (root/'research'/'report.html').read_text()
            self.assertIn('Holdout PSR', rendered)
            self.assertIn('Full-history selected-candidate DSR', rendered)
            if research['dsr']['status'] == 'defined':
                self.assertIn('selected_candidate_index', rendered)
            listed = subprocess.run([sys.executable, '-m', 'quantlab', 'trials', '--registry', str(root/'research.sqlite')],
                                    capture_output=True, text=True, check=True)
            self.assertEqual(len(json.loads(listed.stdout)), 3)
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            listed = subprocess.run([sys.executable, '-m', 'quantlab', 'trials', '--registry', str(root/'research.sqlite')],
                                    capture_output=True, text=True, check=True)
            self.assertEqual(len(json.loads(listed.stdout)), 3)
