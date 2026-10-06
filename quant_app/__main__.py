"""Launch the local operator app; no background work begins at startup."""
import argparse
from contextlib import ExitStack
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import webbrowser

from quant_research.serde import InputError
from .jobs import JobManager
from .server import make_server
from .service import Service


def open_browser(url):
    proc_version=Path('/proc/version')
    if proc_version.exists() and 'microsoft' in proc_version.read_text().lower():
        try:
            subprocess.Popen(['cmd.exe','/c','start','',url],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            return
        except OSError:
            pass
    webbrowser.open(url)


def main(argv=None):
    parser=argparse.ArgumentParser(description='Local SPY shadow operator app. Python 3.11+ / WSL or POSIX checkout required.')
    parser.add_argument('--root',type=Path,default=Path.cwd(),help='Checkout containing scripts and studies')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--config-home',type=Path,help='Local configuration directory (defaults to ~/.config)')
    args=parser.parse_args(argv)
    root=args.root.resolve()
    if not (root/'scripts/run_daily.sh').is_file() or not (root/'studies/spy-trend-v2/config.json').is_file():
        parser.error('Launch from the HFT-IBKR checkout, or pass --root PATH. The portable artifact still needs the checkout for app jobs.')
    if not 1<=args.port<=65535:
        parser.error('port must be 1..65535')
    app_dir=root/'.research-output/app'
    app_dir.mkdir(parents=True,exist_ok=True)
    with ExitStack() as stack:
        handle=stack.enter_context((app_dir/'app.lock').open('a+b'))
        try:
            fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            print('This checkout already has an app open. Use its browser or stop its terminal first.',file=sys.stderr)
            return 2
        jobs=JobManager(root,args.config_home)
        stack.callback(jobs.close)
        try:
            server=make_server(Service(root,args.config_home),jobs,args.port)
        except OSError:
            print('Could not bind localhost. Port may be in use; choose --port NUMBER.',file=sys.stderr)
            return 2
        def close_server():
            with server.action_lock:
                server.closing=True
                jobs.close()
            server.server_close()
        stack.callback(close_server)
        # shutdown must be called from another thread than serve_forever.
        def stop(signum,frame):
            threading.Thread(target=server.shutdown,daemon=True).start()
        signal.signal(signal.SIGINT,stop)
        signal.signal(signal.SIGTERM,stop)
        url=f'http://localhost:{args.port}'
        print(f'Open {url} in your Windows browser.\nKeep this terminal open. Ctrl+C stops the app and its owned jobs.\nClosing the browser does not stop the app. No jobs start automatically.',flush=True)
        if not args.no_browser:
            open_browser(url)
        try:
            server.serve_forever(poll_interval=.2)
        except KeyboardInterrupt:
            pass
    return 0


if __name__=='__main__':
    sys.exit(main())
