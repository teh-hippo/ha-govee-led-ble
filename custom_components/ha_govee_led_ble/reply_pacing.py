"""Pace single-frame requests behind the previous request's reply.

Devices answer each write or query with a frame carrying the same header and command.  Back-to-back frames
can make devices drop replies, so every outbound frame waits for the previous replied frame, up to a bounded
pacing timeout.  Commands that never reply on the current subscription are learned as silent and stop
delaying later frames; a dropped reply from a command that has replied before keeps it paced.
"""

from __future__ import annotations

import asyncio

REPLIED_HEADERS = frozenset({0x33, 0xAA})


class ReplyGate:
    def __init__(self, timeout: float) -> None:
        self.timeout = timeout
        self._pending: bytes | None = None
        self._deadline = 0.0
        self._replied = asyncio.Event()
        self._answered: set[bytes] = set()
        self._silent: set[bytes] = set()

    def reset(self) -> None:
        """Forget learned replies; call whenever the notification subscription changes."""
        self._pending = None
        self._answered.clear()
        self._silent.clear()
        self._replied.set()

    def sent(self, frame: bytes) -> None:
        key = frame[:2]
        if self.timeout <= 0 or len(key) < 2 or key[0] not in REPLIED_HEADERS or key in self._silent:
            self._pending = None
            return
        self._pending = key
        self._deadline = asyncio.get_running_loop().time() + self.timeout
        self._replied.clear()

    def observe(self, frame: bytes) -> None:
        if self._pending is not None and frame[:2] == self._pending:
            self._answered.add(self._pending)
            self._pending = None
            self._replied.set()

    async def wait(self) -> None:
        if self._pending is None:
            return
        remaining = self._deadline - asyncio.get_running_loop().time()
        if remaining > 0:
            try:
                async with asyncio.timeout(remaining):
                    await self._replied.wait()
            except TimeoutError:
                pass
        if (pending := self._pending) is not None:
            if pending not in self._answered:
                self._silent.add(pending)
            self._pending = None
