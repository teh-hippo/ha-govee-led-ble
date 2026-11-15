"""Subscription-bound completion of a physical effect upload."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass

from bleak import BleakClient


class UploadAckTimeoutError(TimeoutError):
    """A physically sent upload has no verdict and must not be replayed."""


@dataclass(frozen=True, slots=True)
class PendingUploadAck:
    client: BleakClient
    token: object | None
    profile_generation: int
    subtype: int
    mode: int | None
    protocol: int
    future: asyncio.Future[bool]
    profile_guard: Callable[[], None]

    def invalidate(self, error: Exception) -> None:
        if not self.future.done():
            self.future.set_exception(error)

    def close(self) -> None:
        self.future.cancel()
        if not self.future.cancelled():
            self.future.exception()
