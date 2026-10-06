"""Actual local HTTP requests test the app's browser security boundary."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from quant_app.server import make_server


class FakeService:
    def __init__(self, root):
        self.root=Path(root)
        self.calls=[]
    def snapshot(self):
        return {'mode':'shadow','history':{'rows':[]},'study':{'ready':False},'portfolio':{'ready':False},'credentials':{'present':False}}
    def save_keys(self,payload):
        self.calls.append(payload)
        return {'ok':True}


class FakeJobs:
    def __init__(self):
        self.running=False
    def snapshot(self):
        return {'running':self.running,'external_runner':False,'logs':[]}
    def start(self,action):
        self.running=True
        return self.snapshot()
    def stop(self):
        self.running=False
        return self.snapshot()
    def close(self):
        pass


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.service=FakeService(self.tmp.name)
        self.jobs=FakeJobs()
        self.server=make_server(self.service,self.jobs,port=0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.thread.join)
        self.addCleanup(self.server.shutdown)
        self.port=self.server.server_address[1]
        self.origin=f'http://127.0.0.1:{self.port}'
        self.token=self.request('GET','/api/session')[1]['token']

    def request(self,method,path,body=None,headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=3)
        headers={'Origin':self.origin,**(headers or {})}
        if body is not None:
            body=json.dumps(body) if not isinstance(body,str) else body
            headers.setdefault('Content-Type','application/json')
        conn.request(method,path,body,headers)
        response=conn.getresponse()
        data=response.read()
        status=response.status
        self.headers=dict(response.getheaders())
        conn.close()
        return status,json.loads(data) if self.headers.get('Content-Type','').startswith('application/json') else data

    def test_local_bind_and_read_requires_capability(self):
        self.assertEqual(self.server.server_address[0],'127.0.0.1')
        self.assertEqual(self.request('GET','/api/status')[0],403)
        status,value=self.request('GET','/api/status',headers={'X-App-Token':self.token})
        self.assertEqual(status,200)
        self.assertEqual(value['mode'],'shadow')
        self.assertEqual(self.headers['Cache-Control'],'no-store')
        self.assertNotIn('Access-Control-Allow-Origin',self.headers)

    def test_host_origin_fetch_metadata_bootstrap_rejected(self):
        for headers in ({'Host':'evil.test'}, {'Origin':'https://evil.test'}, {'Sec-Fetch-Site':'cross-site'},
                        {'Host':f'localhost:{self.port}','Origin':self.origin}):
            self.assertEqual(self.request('GET','/api/session',headers=headers)[0],403)
        self.assertEqual(self.request('POST','/api/action',{'action':'save_keys'},
                    {'X-App-Token':self.token,'Origin':''})[0],403)
        self.assertEqual(self.service.calls,[])

    def test_mutations_require_capability_and_known_payload(self):
        self.assertEqual(self.request('POST','/api/action',{'action':'save_keys'})[0],403)
        self.assertEqual(self.request('POST','/api/action',{'action':'shell','command':'touch nope'},
                         {'X-App-Token':self.token})[0],400)
        self.assertEqual(self.request('POST','/api/action',{'action':'save_keys','key_id':'FAKE','secret_key':'FAKE'},
                         {'X-App-Token':self.token})[0],200)
        self.assertEqual(self.service.calls,[{'key_id':'FAKE','secret_key':'FAKE'}])

    def test_size_json_and_static_routes(self):
        headers={'X-App-Token':self.token}
        self.assertEqual(self.request('POST','/api/action','x'*9000,headers)[0],413)
        self.assertEqual(self.request('POST','/api/action','{"action":"stop","action":"shell"}',headers)[0],400)
        self.assertEqual(self.request('POST','/api/action',{'action':'stop'},
                                     dict(headers,**{'Content-Type':'text/plain'}))[0],415)
        self.assertEqual(self.request('GET','/../../etc/passwd')[0],404)
        self.assertEqual(self.request('GET','/api/status?path=/etc/passwd',headers=headers)[0],404)

    def test_oversized_local_status_response_is_bounded(self):
        from unittest.mock import patch
        with patch.object(self.service,'snapshot',return_value={'history':{'detail':'x'*(4*1024*1024+1)}}):
            status,value=self.request('GET','/api/status',headers={'X-App-Token':self.token})
        self.assertEqual(status,503)
        self.assertLess(len(str(value)),200)

    def test_active_job_blocks_book_and_key_changes(self):
        self.jobs.running=True
        self.assertEqual(self.request('POST','/api/action',{'action':'save_keys','key_id':'FAKE','secret_key':'FAKE'},
                                     {'X-App-Token':self.token})[0],409)
        self.assertEqual(self.service.calls,[])
