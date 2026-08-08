from __future__ import annotations

import os
import signal
import threading
from collections.abc import Callable


class CleanupRegistry:
    """Run registered cleanup actions once, in reverse order."""

    def __init__(self, *, force_exit: Callable[[int], None] = os._exit) -> None:
        self._actions: list[Callable[[], None]] = []
        self._closed = False
        self._lock = threading.Lock()
        self.shutdown_requested = threading.Event()
        self._force_exit = force_exit

    def add(self, action: Callable[[], None]) -> None:
        with self._lock:
            if self._closed:
                raise RuntimeError("cleanup has already run")
            self._actions.append(action)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            actions = list(reversed(self._actions))
            self._actions.clear()
        errors: list[Exception] = []
        for action in actions:
            try:
                action()
            except Exception as error:
                errors.append(error)
        if errors:
            raise ExceptionGroup("cleanup failed", errors)

    def signal_handler(self, signum: int, _frame: object) -> None:
        if self.shutdown_requested.is_set():
            self._force_exit(128 + signum)
            return
        self.shutdown_requested.set()

    def install_signal_handlers(self) -> None:
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def __enter__(self) -> CleanupRegistry:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
