"""Launch actual CLI against a blank temporary checkout, without a browser/network job."""
import http.client
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]


class LaunchTests(unittest.TestCase):
    def test_cli_serves_local_assets_no_jobs_and_refuses_second_instance(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'checkout'
            (root/'scripts').mkdir(parents=True)
            for name in ('run_daily.sh','daily_shadow.sh','run_study.sh'):
                (root/'scripts'/name).write_text('# fixture; never run\n')
            study=root/'studies/spy-trend-v2'
            study.mkdir(parents=True)
            (study/'config.json').write_text('{}')
            with socket.socket() as reserved:
                reserved.bind(('127.0.0.1',0))
                port=reserved.getsockname()[1]
            args=[sys.executable,'-m','quant_app','--root',str(root),'--port',str(port),'--no-browser','--config-home',str(Path(folder)/'config')]
            process=subprocess.Popen(args,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                deadline=time.monotonic()+5
                while time.monotonic()<deadline:
                    try:
                        connection=http.client.HTTPConnection('127.0.0.1',port,timeout=.5)
                        connection.request('GET','/')
                        response=connection.getresponse()
                        content=response.read()
                        connection.close()
                        break
                    except OSError:
                        self.assertIsNone(process.poll())
                        time.sleep(.03)
                else:self.fail('App did not become available')
                self.assertEqual(response.status,200)
                self.assertIn(b'Trading desk',content)
                second=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=5)
                self.assertEqual(second.returncode,2)
                self.assertIn('already has an app',second.stderr)
                self.assertFalse((root/'.research-output/shadow').exists())
                self.assertFalse((Path(folder)/'config').exists())
                process.send_signal(signal.SIGTERM)
                process.communicate(timeout=5)
                self.assertEqual(process.returncode,0)
            finally:
                if process.poll() is None:process.kill()
                process.communicate(timeout=5)
