import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/check_paper_gateway.py'


class Wrapper:
    pass


class Client:
    instances = []
    behavior = 'ready'

    def __init__(self, wrapper):
        self.wrapper = wrapper
        self.calls = []
        Client.instances.append(self)

    def connect(self, host, port, clientId):
        self.calls.append(('connect', host, port, clientId))
        if Client.behavior == 'exception':
            raise RuntimeError('SECRET_ACCOUNT_ID')

    def run(self):
        self.calls.append(('run',))
        self.wrapper.managedAccounts('SECRET_ACCOUNT_ID')
        if Client.behavior == 'ready':
            self.wrapper.nextValidId(98765)
        elif Client.behavior == 'error':
            self.wrapper.error(-1, 123, 326, 'SECRET_ACCOUNT_ID')

    def serverVersion(self):
        return 200

    def disconnect(self):
        self.calls.append(('disconnect',))
        if Client.behavior == 'bad_disconnect':
            raise RuntimeError('SECRET_ACCOUNT_ID')


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.exists(), 'paper Gateway diagnostic has not been implemented')
        spec = importlib.util.spec_from_file_location('gateway_check', SCRIPT)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        Client.instances = []
        Client.behavior = 'ready'
        self.config = self.module.validate('172.30.0.1', 4002, 91, 1, True, True)

    def test_acknowledgements_and_endpoint_fail_before_sdk(self):
        cases = [('8.8.8.8', 4002, 91, 15, True, True),
                 ('gateway.local', 4002, 91, 15, True, True),
                 ('172.30.0.1', 4001, 91, 15, True, True),
                 ('172.30.0.1', 4002, 0, 15, True, True),
                 ('172.30.0.1', 4002, 91, float('nan'), True, True),
                 ('172.30.0.1', 4002, 91, 31, True, True),
                 ('172.30.0.1', 4002, 91, 15, False, True),
                 ('172.30.0.1', 4002, 91, 15, True, False)]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.module.validate(*case)

    def test_only_callback_confirms_api_and_no_requests_are_made(self):
        result = self.module.run_session(self.config, sdk=(Wrapper, Client))
        self.assertEqual(result, {'status': 'api_connected', 'server_version': 200})
        self.assertEqual([x[0] for x in Client.instances[0].calls],
                         ['connect', 'run', 'disconnect'])
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertNotIn('98765', json.dumps(result))

    def test_tcp_only_is_not_success(self):
        Client.behavior = 'no_callback'
        result = self.module.run_session(self.config, sdk=(Wrapper, Client))
        self.assertEqual(result['status'], 'callback_timeout')
        self.assertEqual(Client.instances[0].calls[-1], ('disconnect',))

    def test_callback_with_invalid_server_version_is_rejected(self):
        for version in [None, True, 0, 10001]:
            with self.subTest(version=version), patch.object(Client, 'serverVersion', return_value=version):
                self.assertEqual(self.module.run_session(self.config, sdk=(Wrapper, Client))['status'],
                                 'connection_failed')

    def test_errors_and_exceptions_are_private_and_disconnect(self):
        for behavior in ['exception', 'error', 'bad_disconnect']:
            with self.subTest(behavior=behavior):
                Client.behavior = behavior
                result = self.module.run_session(self.config, sdk=(Wrapper, Client))
                self.assertNotEqual(result['status'], 'api_connected')
                self.assertNotIn('SECRET', json.dumps(result))
                self.assertEqual(Client.instances[-1].calls[-1], ('disconnect',))

    def test_child_result_is_strict_and_bounded(self):
        valid = '{"status":"api_connected","server_version":200}'
        for payload, code in [(valid, 2), (valid[:-1], 0),
                              ('{"status":"api_connected","server_version":true}', 0),
                              ('{"status":"api_connected","server_version":0}', 0),
                              ('{"status":"api_connected","server_version":200,"account":"secret"}', 0),
                              ('x' * 2049, 0),
                              ('{"status":"api_connected","status":"callback_timeout","server_version":null}', 0)]:
            with self.subTest(payload=payload[:80], code=code):
                self.assertEqual(self.module.parse_result(payload, code)['status'], 'invalid_worker_result')
        self.assertEqual(self.module.parse_result(valid, 0)['status'], 'api_connected')

    def test_total_deadline_covers_blocked_child(self):
        with patch.object(self.module.subprocess, 'run', side_effect=subprocess.TimeoutExpired('child', 1)):
            self.assertEqual(self.module.check(self.config)['status'], 'process_timeout')
        # The actual subprocess API kills and reaps a blocked process on timeout.
        with self.assertRaises(subprocess.TimeoutExpired):
            subprocess.run([sys.executable, '-I', '-c', 'import time; time.sleep(5)'],
                           timeout=0.02, capture_output=True)

    def test_worker_direct_invocation_requires_both_confirmations(self):
        result = subprocess.run([sys.executable, str(SCRIPT), '--worker',
                                 '--host', '172.30.0.1'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('--confirm-paper', result.stderr)

    def test_direct_worker_deadline_covers_a_hung_session(self):
        code = ("import runpy,time; g=runpy.run_path(" + repr(str(SCRIPT)) + "); "
                "g['main'].__globals__['run_session']=lambda config: time.sleep(10); "
                "raise SystemExit(g['main'](['--worker','--host','127.0.0.1',"
                "'--timeout','1','--confirm-paper','--confirm-read-only']))")
        process = subprocess.run([sys.executable, '-I', '-c', code],
                                 capture_output=True, text=True, timeout=3)
        self.assertEqual(process.returncode, 2)
        self.assertEqual(json.loads(process.stdout)['status'], 'process_timeout')


if __name__ == '__main__':
    unittest.main()
