"""Shared nonblocking POSIX lock for runner ownership and operator book writes."""
from contextlib import contextmanager
import fcntl
from pathlib import Path

from quant_research.serde import InputError


def lock_path(root):
    return Path(root)/'.research-output/shadow/runner.lock'


@contextmanager
def operator_lock(root):
    path = lock_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise InputError('A runner or book operation is active. Stop it in its owning window first.') from None
        try:
            yield handle
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def runner_busy(root):
    path = lock_path(root)
    if not path.exists():
        return False
    with path.open('a+b') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(handle, fcntl.LOCK_UN)
    return False
