import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


class BuildTests(unittest.TestCase):
    def test_shadow_session_command_is_available_outside_checkout(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / 'shadow.pyz'
            built = subprocess.run([sys.executable, str(ROOT / 'scripts/build.py'),
                                    '--output', str(archive)], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            result = subprocess.run([sys.executable, str(archive), 'session', 'plan', '--help'],
                                    cwd=folder, env={}, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            for flag in ('--bundle', '--schedule', '--snapshot', '--ledger', '--output'):
                self.assertIn(flag, result.stdout)

    def test_local_preflight_runs_from_archive_outside_checkout(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / 'local.pyz'
            built = subprocess.run([sys.executable, str(ROOT / 'scripts/build.py'),
                                    '--output', str(archive)], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            output = Path(folder) / 'preflight.json'
            result = subprocess.run([sys.executable, str(archive), 'local', 'preflight',
                                     '--skip-cuda', '--output', str(output)], cwd=folder,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertTrue(output.exists(), result.stderr)
            self.assertEqual(json.loads(output.read_text())['status'], 'blocked')

    def test_deterministic_archive_runs_outside_repository_and_matches_source_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            archives=[Path(folder)/name for name in ('first.pyz','second.pyz')]
            for archive in archives:
                result=subprocess.run([sys.executable,str(ROOT/'scripts/build.py'),'--output',str(archive)],
                                      capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(archives[0].read_bytes(),archives[1].read_bytes())
            output=Path(folder)/'report.json'
            result=subprocess.run([sys.executable,str(archives[0]),'control','replay','--fixture',
                                   str(ROOT/'examples/control/A12.json'),'--output',str(output)],
                                  cwd=folder,env={},capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            from quant_research.__main__ import source_identity
            report=json.loads(output.read_text())
            self.assertEqual(report['code']['research'],source_identity())
            self.assertEqual(report['code']['control'],source_identity(package='quant_control'))
