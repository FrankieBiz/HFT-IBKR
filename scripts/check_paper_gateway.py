"""Opt-in paper API handshake only. Never requests data or submits/cancels orders."""

import argparse
import contextlib
import ipaddress
import json
import logging
import math
import os
from pathlib import Path
import subprocess
import sys
import threading


STATUSES = {'api_connected', 'missing_sdk', 'sdk_import_failed', 'callback_timeout',
            'connection_failed', 'disconnect_failed', 'process_timeout',
            'invalid_worker_result', 'worker_failed'}
LOCAL_NETWORKS = tuple(ipaddress.ip_network(value) for value in
                       ('127.0.0.0/8', '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))


def result(status, server_version=None):
    return {'status': status, 'server_version': server_version}


def validate(host, port, client_id, timeout, paper, read_only):
    if paper is not True or read_only is not True:
        raise ValueError('Confirm paper login and Read-Only API before connecting.')
    try:
        address = ipaddress.IPv4Address(host)
    except ipaddress.AddressValueError:
        raise ValueError('Host must be a loopback or RFC1918 IPv4 literal.') from None
    if not any(address in network for network in LOCAL_NETWORKS):
        raise ValueError('Host must be a loopback or RFC1918 IPv4 literal.')
    if type(port) is not int or port != 4002:
        raise ValueError('Only paper Gateway port 4002 is supported by this diagnostic.')
    if type(client_id) is not int or not 1 <= client_id <= 2147483647:
        raise ValueError('Use a nonzero client ID from 1 through 2147483647.')
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 1 <= timeout <= 30:
        raise ValueError('Timeout must be between 1 and 30 seconds.')
    return {'host': str(address), 'port': port, 'client_id': client_id, 'timeout': timeout}


def run_session(config, sdk=None):
    if sdk is None:
        try:
            from ibapi.client import EClient
            from ibapi.wrapper import EWrapper
            sdk = (EWrapper, EClient)
        except ModuleNotFoundError as error:
            return result('missing_sdk' if error.name == 'ibapi' else 'sdk_import_failed')
        except Exception:
            return result('sdk_import_failed')
    wrapper, client = sdk
    done = threading.Event()
    state = {'ready': False, 'failed': False}

    class Probe(wrapper, client):
        def __init__(self):
            wrapper.__init__(self)
            client.__init__(self, self)

        def nextValidId(self, orderId):
            if type(orderId) is not int or orderId < 0:
                state['failed'] = True
            else:
                state['ready'] = True
            done.set()

        def managedAccounts(self, accountsList):
            pass  # Discard unsolicited account identifiers without logging them.

        def managedAccountsProtoBuf(self, message):
            pass

        def nextValidIdProtoBuf(self, message):
            pass  # SDK 10.50.02 also dispatches the ordinary nextValidId callback.

        def error(self, *args, **kwargs):
            # SDK 10.50.02 includes errorTime; older SDKs do not. Never stringify
            # the raw error or advanced rejection JSON: either may identify accounts.
            code = args[2] if len(args) >= 4 and type(args[2]) is int else (
                args[1] if len(args) >= 3 and type(args[1]) is int else None)
            if code in {326, 501, 502, 503, 504, 1100, 1300}:
                state['failed'] = True
                done.set()

        def connectionClosed(self):
            if not state['ready']:
                state['failed'] = True
                done.set()

    try:
        app = Probe()
    except Exception:
        return result('sdk_import_failed')
    outcome = result('connection_failed')
    try:
        app.connect(config['host'], config['port'], clientId=config['client_id'])

        def receive():
            try:
                app.run()
            except Exception:
                state['failed'] = True
                done.set()

        threading.Thread(target=receive, daemon=True).start()
        if not done.wait(config['timeout']):
            outcome = result('callback_timeout')
        elif state['ready'] and not state['failed']:
            version = app.serverVersion()
            if type(version) is int and 1 <= version <= 10000:
                outcome = result('api_connected', version)
    except Exception:
        outcome = result('connection_failed')
    finally:
        try:
            app.disconnect()
        except Exception:
            outcome = result('disconnect_failed')
    return outcome


def parse_result(payload, returncode):
    if len(payload) > 2048:
        return result('invalid_worker_result')

    def unique(pairs):
        values = {}
        for key, value in pairs:
            if key in values:
                raise ValueError('duplicate key')
            values[key] = value
        return values

    try:
        value = json.loads(payload, object_pairs_hook=unique)
        if type(value) is not dict or set(value) != {'status', 'server_version'}:
            raise ValueError('invalid fields')
        status, version = value['status'], value['server_version']
        if type(status) is not str or status not in STATUSES:
            raise ValueError('invalid status')
        if status == 'api_connected':
            if returncode != 0 or type(version) is not int or not 1 <= version <= 10000:
                raise ValueError('invalid success')
        elif version is not None or returncode != 2:
            raise ValueError('invalid failure')
        return value
    except (ValueError, TypeError):
        return result('invalid_worker_result')


def check(config):
    command = [sys.executable, '-I', str(Path(__file__).resolve()), '--worker',
               '--host', config['host'], '--port', str(config['port']),
               '--client-id', str(config['client_id']), '--timeout', str(config['timeout']),
               '--confirm-paper', '--confirm-read-only']
    try:
        child = subprocess.run(command, capture_output=True, text=True,
                               timeout=config['timeout'])
    except subprocess.TimeoutExpired:
        # subprocess.run kills and reaps the child, including hangs during import,
        # connect or disconnect. No partial stdout/stderr crosses this boundary.
        return result('process_timeout')
    except OSError:
        return result('worker_failed')
    return parse_result(child.stdout, child.returncode)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--port', type=int, default=4002)
    parser.add_argument('--client-id', type=int, default=91)
    parser.add_argument('--timeout', type=float, default=15)
    parser.add_argument('--confirm-paper', action='store_true', required=True)
    parser.add_argument('--confirm-read-only', action='store_true', required=True)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        config = validate(args.host, args.port, args.client_id, args.timeout,
                          args.confirm_paper, args.confirm_read_only)
    except ValueError as error:
        parser.error(str(error))
    if args.worker:
        # Also bound a directly invoked worker. Python stream redirection below
        # must not hide this fixed timeout result, so retain the original pipe FD.
        report_fd = os.dup(sys.stdout.fileno())

        def expire():
            try:
                os.write(report_fd, b'{"status":"process_timeout","server_version":null}\n')
            except OSError:
                pass
            finally:
                os._exit(2)

        watchdog = threading.Timer(config['timeout'], expire)
        watchdog.daemon = True
        watchdog.start()
        logging.disable(logging.CRITICAL)
        try:
            with open(os.devnull, 'w') as sink:
                with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                    outcome = run_session(config)
        finally:
            watchdog.cancel()
            os.close(report_fd)
    else:
        outcome = check(config)
    print(json.dumps(outcome, sort_keys=True))
    return 0 if outcome['status'] == 'api_connected' else 2


if __name__ == '__main__':
    sys.exit(main())
