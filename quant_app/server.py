"""Loopback-only browser controller with a fixed route/action surface."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
import json
import secrets
import threading

from quant_research.serde import InputError, _pairs
from .jobs import COMMANDS

ASSETS={'/':('index.html','text/html; charset=utf-8'),
        '/index.html':('index.html','text/html; charset=utf-8'),
        '/app.css':('app.css','text/css; charset=utf-8'),
        '/app.js':('app.js','text/javascript; charset=utf-8')}
ACTIONS={'save_keys':{'key_id','secret_key'},'initialize_book':{'cash'},
         'record_fill':{'decision_id','price','fees'},'set_halt':set(),'settle_cash':set(),'recover_accounting':set()}
MAX_BODY=8192
MAX_RESPONSE=4*1024*1024


class AppServer(ThreadingHTTPServer):
    daemon_threads=True
    block_on_close=False
    def __init__(self,service,jobs,port):
        self.service=service
        self.jobs=jobs
        self.capability=secrets.token_urlsafe(32)
        self.action_lock=threading.RLock()
        self.closing=False
        super().__init__(('127.0.0.1',port),Handler)


class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.0'
    server_version='LocalOperator'
    sys_version=''
    def setup(self):
        super().setup()
        self.connection.settimeout(5)
    def log_message(self,*args):
        # URLs, form values and capabilities are never logged.
        pass
    def _send(self,status,body,content_type='application/json; charset=utf-8'):
        if not isinstance(body,bytes):
            body=json.dumps(body,ensure_ascii=True,allow_nan=False).encode()
        if len(body)>MAX_RESPONSE:
            status=503
            content_type='application/json; charset=utf-8'
            body=b'{"error":"Local status exceeds the display limit. Retain history for reviewed archival."}'
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; form-action 'self'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(body)
    def _boundary(self,mutation=False):
        port=self.server.server_address[1]
        hosts={f'127.0.0.1:{port}',f'localhost:{port}'}
        host=self.headers.get('Host','')
        origin=self.headers.get('Origin')
        if (len(self.headers.get_all('Host',[])) != 1 or host not in hosts
                or self.headers.get('Sec-Fetch-Site') not in (None,'none','same-origin')
                or (origin is not None and origin != 'http://'+host)
                or (mutation and origin != 'http://'+host)):
            self._send(403,{'error':'Only this local app can access these controls.'})
            return False
        return True
    def _authorized(self):
        values=self.headers.get_all('X-App-Token',[])
        if len(values)!=1 or not secrets.compare_digest(values[0],self.server.capability):
            self._send(403,{'error':'Reload the local app to establish its session.'})
            return False
        return True
    def do_GET(self):
        if not self._boundary():
            return
        if self.path in ASSETS:
            name,kind=ASSETS[self.path]
            self._send(200,files('quant_app').joinpath('assets',name).read_bytes(),kind)
        elif self.path=='/api/session':
            self._send(200,{'token':self.server.capability})
        elif self.path=='/api/status':
            if not self._authorized():
                return
            try:
                with self.server.action_lock:
                    status=self.server.service.snapshot()
                    status['jobs']=self.server.jobs.snapshot()
                    busy=status['jobs']['running'] or status['jobs']['external_runner']
                    status['capabilities']={'mutate':not busy,'start':not busy,'stop':status['jobs']['running']}
                self._send(200,status)
            except (InputError,OSError):
                self._send(503,{'error':'Could not read local state. Review files in the app console.'})
        else:
            self._send(404,{'error':'Unknown route.'})
    def do_POST(self):
        if not self._boundary(mutation=True) or not self._authorized():
            return
        if self.path!='/api/action':
            self._send(404,{'error':'Unknown route.'})
            return
        if self.headers.get('Content-Type','').split(';')[0].strip()!='application/json':
            self._send(415,{'error':'JSON content type required.'})
            return
        lengths=self.headers.get_all('Content-Length',[])
        if self.headers.get('Transfer-Encoding') is not None or len(lengths)!=1:
            self._send(400,{'error':'A single bounded body length is required.'})
            return
        try:
            length=int(lengths[0])
        except ValueError:
            length=-1
        if length<0:
            self._send(400,{'error':'Invalid body length.'})
            return
        if length>MAX_BODY:
            self._send(413,{'error':'Request is too large.'})
            return
        action=None
        try:
            raw=self.rfile.read(length)
            payload=json.loads(raw,object_pairs_hook=_pairs,parse_constant=lambda value: (_ for _ in ()).throw(ValueError()))
            if not isinstance(payload,dict) or not isinstance(payload.get('action'),str):
                raise InputError('An action object is required.')
            action=payload.pop('action')
            if action not in COMMANDS and action not in ACTIONS and action!='stop':
                raise InputError('Unknown action.')
            expected=ACTIONS.get(action,set())
            if set(payload)!=expected:
                raise InputError('Unexpected or missing action fields.')
            with self.server.action_lock:
                if self.server.closing:
                    self._send(503,{'error':'App is shutting down.'})
                    return
                jobs=self.server.jobs.snapshot()
                if action!='stop' and (jobs['running'] or jobs['external_runner']):
                    self._send(409,{'error':'A job or external runner is active. Stop it in its owning window first.'})
                    return
                if action=='stop':
                    result=self.server.jobs.stop()
                elif action in COMMANDS:
                    if action=='runner':
                        current=self.server.service.snapshot()
                        if not (current['study']['ready'] and current['portfolio']['ready'] and current['credentials']['present']):
                            raise InputError('Finish the Setup steps before starting the runner.')
                    if action=='study' and self.server.service.snapshot()['study']['ready']:
                        raise InputError('Your study is already verified. Reuse it; no rerun is needed.')
                    result=self.server.jobs.start(action)
                else:
                    result=getattr(self.server.service,action)(payload)
            self._send(200,result)
        except InputError as error:
            message = 'Key save rejected. Enter both simple API key values (letters, digits, _ or -).' if action=='save_keys' else str(error)[:500]
            self._send(400,{'error':message})
        except (ValueError,UnicodeError,RecursionError,TypeError):
            # Do not echo attacker-controlled values or key fields in diagnostics.
            self._send(400,{'error':'Action rejected. Check the entered values and local setup; existing evidence and history were preserved.'})
        except OSError:
            self._send(503,{'error':'Local storage/process operation failed. Review permissions and retry.'})


def make_server(service,jobs,port=8765):
    return AppServer(service,jobs,port)
