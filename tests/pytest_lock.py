from __future__ import annotations

import fcntl
import os
from pathlib import Path
from typing import TextIO


def acquire_checkout_lock(path: Path) -> TextIO:
    lock = path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        owner = lock.read().strip()
        lock.close()
        detail = f" (PID {owner})" if owner else ""
        raise RuntimeError(f"Another pytest process owns this checkout{detail}.") from None
    lock.seek(0)
    lock.truncate()
    lock.write(str(os.getpid()))
    lock.flush()
    return lock
