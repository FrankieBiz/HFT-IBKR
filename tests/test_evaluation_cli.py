import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from quant_research.__main__ import main

ROOT=Path(__file__).resolve().parents[1]


class EvaluationCliTests(unittest.TestCase):
    def args(self,folder):
        return ['--data',str(ROOT/'examples/synthetic_spy_daily.csv'),
                '--manifest',str(ROOT/'examples/synthetic_spy_manifest.json'),
                '--config',str(ROOT/'examples/research_config.json'),
                '--protocol',str(ROOT/'examples/synthetic_protocol.json'),
                '--registry',str(Path(folder)/'experiments.sqlite')]

    def call(self,args):
        return subprocess.run([sys.executable,'-m','quant_research',*args],cwd=ROOT,env={},
                              capture_output=True,text=True)

    def test_validation_freeze_holdout_and_repeated_release(self):
        with tempfile.TemporaryDirectory() as folder:
            args=self.args(folder)
            report,artifact,holdout=[Path(folder)/name for name in ('validation.json','selection.json','holdout.json')]
            result=self.call(['evaluate',*args,'--run-id','validation','--output',str(report),'--selection',str(artifact)])
            self.assertEqual(result.returncode,0,result.stderr)
            validation=json.loads(report.read_text())
            self.assertNotIn('holdout',validation['intervals'])
            result=self.call(['holdout',*args,'--run-id','holdout','--selection',str(artifact),'--output',str(holdout)])
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(holdout.read_text())['data_kind'],'synthetic')
            recovered=Path(folder)/'recovered.json'
            result=self.call(['recover','--registry',str(Path(folder)/'experiments.sqlite'),
                              '--run-id','holdout','--output',str(recovered)])
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(holdout.read_bytes(),recovered.read_bytes())
            result=self.call(['holdout',*args,'--run-id','again','--selection',str(artifact),'--output',str(Path(folder)/'again.json')])
            self.assertEqual(result.returncode,2,result.stderr)

    def test_existing_output_refused_before_registering_experiment(self):
        with tempfile.TemporaryDirectory() as folder:
            report=Path(folder)/'validation.json'
            report.write_text('preserve')
            result=self.call(['evaluate',*self.args(folder),'--run-id','validation','--output',str(report),
                              '--selection',str(Path(folder)/'selection.json')])
            self.assertEqual(result.returncode,2,result.stderr)
            self.assertFalse((Path(folder)/'experiments.sqlite').exists())

    def test_selection_cannot_alias_registry(self):
        with tempfile.TemporaryDirectory() as folder:
            result=self.call(['evaluate',*self.args(folder),'--run-id','validation',
                              '--output',str(Path(folder)/'report.json'),
                              '--selection',str(Path(folder)/'experiments.sqlite')])
            self.assertEqual(result.returncode,2,result.stderr)
            self.assertFalse((Path(folder)/'experiments.sqlite').exists())

    def test_evaluation_cannot_create_socket(self):
        with tempfile.TemporaryDirectory() as folder, patch('socket.socket',side_effect=AssertionError('network forbidden')):
            self.assertEqual(main(['evaluate',*self.args(folder),'--run-id','offline','--output',str(Path(folder)/'report.json'),
                                   '--selection',str(Path(folder)/'selection.json')]),0)
