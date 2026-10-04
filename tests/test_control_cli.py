import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]


class ControlCliTests(unittest.TestCase):
    def test_invalid_tail_does_not_create_or_change_journal(self):
        from quant_control.__main__ import main
        with tempfile.TemporaryDirectory() as folder:
            fixture=Path(folder)/'fixture.json'
            raw=json.loads((ROOT/'examples/control/A12.json').read_text())
            raw['events'][-1]['sequence']+=1
            fixture.write_text(json.dumps(raw))
            journal=Path(folder)/'journal.jsonl'
            self.assertEqual(main(['continue','--fixture',str(fixture),'--journal',str(journal),
                                   '--output',str(Path(folder)/'report.json')]),2)
            self.assertFalse(journal.exists())
            valid=json.loads((ROOT/'examples/control/A12.json').read_text())
            fixture.write_text(json.dumps(valid))
            self.assertEqual(main(['continue','--fixture',str(fixture),'--journal',str(journal),
                                   '--output',str(Path(folder)/'first.json')]),0)
            original=journal.read_bytes()
            valid['events']=[{'sequence':99,'time_ms':0,'kind':'kill','payload':{}}]
            fixture.write_text(json.dumps(valid))
            self.assertEqual(main(['continue','--fixture',str(fixture),'--journal',str(journal),
                                   '--output',str(Path(folder)/'second.json')]),2)
            self.assertEqual(journal.read_bytes(),original)

    def call(self,id,output):
        return subprocess.run([sys.executable,'-m','quant_control','replay','--fixture',
                               str(ROOT/'examples/control'/f'{id}.json'),'--output',str(output)],
                              cwd=ROOT,env={},capture_output=True,text=True)

    def test_all_acceptance_fixtures(self):
        expected={'A01':('BOOTSTRAP','1000',0,0),'A02':('READY','1000',0,1),
                  'A04':('READY','1000',0,0),'A05':('READY','1000',0,1),
                  'A06':('HALTED','1000',0,1),'A07':('HALTED','703',3,1),
                  'A08':('READY','802',2,1),'A09':('RECONCILING','1000',0,0),
                  'A10':('HALTED','1000',0,0),'A11':('HALTED','802',2,1),
                  'A12':('READY','802',2,1),'A13':('HALTED','1000',0,0),
                  'A14':('RECONCILING','802',2,1)}
        with tempfile.TemporaryDirectory() as folder:
            for id,values in expected.items():
                with self.subTest(id=id):
                    output=Path(folder)/f'{id}.json'
                    result=self.call(id,output)
                    self.assertEqual(result.returncode,0,result.stderr)
                    report=json.loads(output.read_text())
                    state=report['final_state']
                    actual=(state['mode'],state['cash'],state['inventory'],sum(o['type']=='submit_simulated' for o in report['outputs']))
                    self.assertEqual(actual,values)
            output=Path(folder)/'A03.json'
            self.assertEqual(self.call('A03',output).returncode,2)
            self.assertFalse(output.exists())

    def test_repeat_determinism_and_existing_output(self):
        with tempfile.TemporaryDirectory() as folder:
            a,b=Path(folder)/'a.json',Path(folder)/'b.json'
            self.assertEqual(self.call('A12',a).returncode,0)
            self.assertEqual(self.call('A12',b).returncode,0)
            self.assertEqual(a.read_bytes(),b.read_bytes())
            before=a.read_bytes()
            self.assertEqual(self.call('A12',a).returncode,2)
            self.assertEqual(before,a.read_bytes())

    def test_no_socket_in_process(self):
        from quant_control.__main__ import main
        with tempfile.TemporaryDirectory() as folder,patch('socket.socket',side_effect=AssertionError('network forbidden')):
            self.assertEqual(main(['replay','--fixture',str(ROOT/'examples/control/A12.json'),
                                   '--output',str(Path(folder)/'report.json')]),0)
