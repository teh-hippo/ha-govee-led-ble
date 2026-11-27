"""Subscription-bound completion of a physical effect upload."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from bleak import BleakClient


class UploadOutcome(StrEnum):
    UNCONFIRMED = "upload_unconfirmed"
    CANCELLED = "operation_cancelled"


class UploadAckTimeoutError(TimeoutError):
    """A physically sent upload has no verdict and must not be replayed."""

    before_activation = False
    outcome = UploadOutcome.UNCONFIRMED


class UploadRejectedError(RuntimeError):
    """A device explicitly rejected a completed upload."""


class UploadCancelledError(asyncio.CancelledError):
    """Cancellation interrupted an upload before its selector."""

    outcome = UploadOutcome.CANCELLED


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
    before_activation: bool = False

    def invalidate(self, error: Exception) -> None:
        if not self.future.done():
            self.future.set_exception(error)

    def close(self) -> None:
        self.future.cancel()
        if not self.future.cancelled():
            self.future.exception()
