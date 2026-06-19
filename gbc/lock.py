"""Shared import lock (filelock, the canonical lib) -- run & inbox are mutually exclusive without
blocking either. `inbox` (cron) takes it non-blocking and bows out if busy; `run` waits for it.
"""
from contextlib import contextmanager

from filelock import FileLock, Timeout


@contextmanager
def import_lock(cfg, *, blocking: bool = True):
    """Yields True if the lock was acquired (and releases on exit), False if busy (non-blocking)."""
    cfg.beetsdir.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(cfg.beetsdir / ".import.lock"))
    try:
        lock.acquire(timeout=-1 if blocking else 0)
    except Timeout:
        yield False
        return
    try:
        yield True
    finally:
        lock.release()
