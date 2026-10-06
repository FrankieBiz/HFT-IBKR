"""Shared lock guardian; retain ownership until the entire owned group exits."""
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def inherited_fd(path):
    try:
        fd=int(os.environ.get('HFT_RUNNER_LOCK_FD',''))
        opened=os.fstat(fd)
        target=path.stat()
        if fd<3 or (opened.st_dev,opened.st_ino)!=(target.st_dev,target.st_ino):
            return None
        return fd
    except (ValueError,OSError):
        return None


def group_alive(pgid):
    try:
        os.killpg(pgid,0)
        # Linux init/container supervisors can retain orphan zombie records.
        # Zombies have closed their descriptors and cannot run; do not wait for
        # their unrelated reaper. Kernel proc_pid_stat(5), checked 2026-10-06.
        proc=Path('/proc')
        if proc.is_dir():
            found=False
            uncertain=False
            for entry in proc.iterdir():
                if not entry.name.isdigit():continue
                try:
                    fields=(entry/'stat').read_text().rpartition(') ')[2].split()
                    if int(fields[2])==pgid:
                        found=True
                        if fields[0] not in ('Z','X','x'):return True
                except FileNotFoundError:
                    continue
                except (OSError,ValueError,IndexError):
                    uncertain=True
            if found and not uncertain:return False
        return True
    except ProcessLookupError:
        return False


def main():
    root=Path(__file__).resolve().parents[1]
    path=root/'.research-output/shadow/runner.lock'
    if sys.argv[1:]==['--verify-held']:
        return 0 if inherited_fd(path) is not None else 2
    if len(sys.argv)<2 or sys.argv[1] not in ('run_daily.sh','daily_shadow.sh','run_study.sh'):
        print('Usage: runner_lock.py {run_daily.sh|daily_shadow.sh|run_study.sh} [OPTIONS]',file=sys.stderr)
        return 2
    path.parent.mkdir(parents=True,exist_ok=True)
    fd=inherited_fd(path)
    handle=None
    nested=fd is not None and bool(os.environ.get('HFT_RUNNER_LOCK_OWNER'))
    if fd is None:
        handle=path.open('a+b')
        fd=handle.fileno()
    try:
        fcntl.flock(fd,fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print('Shadow runner already active. Stop it in its owning window first.',file=sys.stderr)
        if handle is not None:handle.close()
        return 2
    if (root/'.research-output/shadow/fills.sqlite').exists():
        sys.path.insert(0,str(root))
        try:
            from quant_app.accounting import check_accounting
            check_accounting(root)
        except Exception as error:
            print(f'Simulated accounting check failed: {error}',file=sys.stderr)
            if handle is not None:handle.close()
            return 2
    script=['bash',str(root/'scripts'/sys.argv[1]),*sys.argv[2:]]
    if nested:
        # Keep nested scripts in the outer guardian's owned group; never create a
        # detached grandchild session that can escape group shutdown.
        env=dict(os.environ,HFT_RUNNER_LOCK_OWNER=str(os.getppid()))
        os.execvpe('bash',script,env)
    child=None
    stopping=None
    def terminate(signum,frame):
        nonlocal stopping
        stopping=stopping or time.monotonic()
        if child is not None:
            try:os.killpg(child.pid,signal.SIGTERM)
            except ProcessLookupError:pass
    signal.signal(signal.SIGTERM,terminate)
    signal.signal(signal.SIGINT,terminate)
    try:
        env=dict(os.environ,HFT_RUNNER_LOCK_OWNER=str(os.getpid()),HFT_RUNNER_LOCK_FD=str(fd))
        child=subprocess.Popen(script,cwd=root,env=env,pass_fds=(fd,),start_new_session=True)
        if stopping is not None:terminate(signal.SIGTERM,None)
        code=None
        while True:
            code=child.poll()
            if code is not None:
                if not group_alive(child.pid):
                    return code
                # A shell can exit before a background child. Own the whole group
                # until that child has exited, including on normal shell exit.
                if stopping is None:terminate(signal.SIGTERM,None)
            if stopping is not None and time.monotonic()-stopping>2:
                try:os.killpg(child.pid,signal.SIGKILL)
                except ProcessLookupError:pass
            time.sleep(.03)
    finally:
        if handle is not None:handle.close()


if __name__=='__main__':
    sys.exit(main())
