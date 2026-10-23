"""Short, reentrant cross-process transactions for shared app metadata."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import os
import threading
import time

_mutex = threading.RLock()
_held = threading.local()


@contextmanager
def state_transaction(path: Path):
    with _mutex:
        if getattr(_held, "depth", 0):
            _held.depth += 1
            try:
                yield
            finally:
                _held.depth -= 1
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.with_name(path.name + ".lock").open("a+b") as handle:
            handle.seek(0, 2)
            if not handle.tell():
                handle.write(b"\0")
                handle.flush()
            deadline = time.monotonic() + 3
            while True:
                try:
                    handle.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as error:
                    if time.monotonic() >= deadline:
                        raise OSError("App-Daten werden gerade von einem anderen Prozess gespeichert.") from error
                    time.sleep(0.025)
            _held.depth = 1
            try:
                yield
            finally:
                _held.depth = 0
                handle.seek(0)
                if os.name == "nt":
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
