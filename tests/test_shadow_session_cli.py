from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from quant_data.bundle import prepare_bundle
from test_data_intake import inputs
from test_inputs import raw_config

ROOT=Path(__file__).resolve().parents[1]


def cli_inputs(folder):
    folder=Path(folder)
    prepare_bundle(*inputs(folder),folder/'data.qdata')
    config=raw_config();config['lookback']=2
    (folder/'config.json').write_text(json.dumps(config))
    dates=['2025-01-02','2025-01-03','2025-01-06','2025-01-07','2025-01-08','2025-01-09']
    schedule={'schema_version':1,'source':'invented','sessions':[
        {'session':day,'open_at':day+'T14:30:00Z','close_at':day+'T21:00:00Z'} for day in dates]}
    snapshot={'schema_version':1,'mode':'offline_shadow','account':'SIM','symbol':'SPY','currency':'USD',
        'execution_session':dates[-1],'now':dates[-1]+'T14:30:00Z',
        'quote':{'bid':'105','ask':'106','as_of':dates[-1]+'T14:30:00Z','data_type':'synthetic'},
        'portfolio':{'cash':'10000','settled_cash':'10000','nav':'10000','peak_nav':'10000','shares':0,
            'as_of':dates[-1]+'T14:30:00Z','reconciled':True,'pending_orders':0,'uncertain_orders':0,'halted':False},
        'policy':{'max_quote_age_seconds':60,'max_account_age_seconds':60}}
    for name,value in [('schedule',schedule),('snapshot',snapshot)]:
        (folder/(name+'.json')).write_text(json.dumps(value))
    return [sys.executable,'-m','quant_session','plan','--bundle',str(folder/'data.qdata'),
        '--config',str(folder/'config.json'),'--schedule',str(folder/'schedule.json'),
        '--snapshot',str(folder/'snapshot.json'),'--ledger',str(folder/'ledger.db')]


class CliTests(unittest.TestCase):
    def test_retry_conflict_failed_output_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);command=cli_inputs(folder)
            existing=folder/'existing.json';existing.write_text('preserved')
            failed=subprocess.run(command+['--output',str(existing)],cwd=ROOT,capture_output=True,text=True)
            self.assertNotEqual(failed.returncode,0)
            self.assertEqual(existing.read_text(),'preserved')
            with closing(sqlite3.connect(folder/'ledger.db')) as connection, connection:
                self.assertEqual(connection.execute('SELECT count(*) FROM decisions').fetchone()[0],1)
            for name in ('one.json','two.json'):
                result=subprocess.run(command+['--output',str(folder/name)],cwd=ROOT,capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual((folder/'one.json').read_bytes(),(folder/'two.json').read_bytes())
            raw=json.loads((folder/'snapshot.json').read_text());raw['portfolio']['halted']=True
            (folder/'snapshot.json').write_text(json.dumps(raw))
            result=subprocess.run(command+['--output',str(folder/'changed.json')],cwd=ROOT,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('conflict',result.stderr)
            self.assertFalse((folder/'changed.json').exists())
