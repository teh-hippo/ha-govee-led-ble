"""Bounded H6179 browser-derived reactive RGB protocol."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from .transport import xor_checksum

H6179_REACTIVE_LEGACY_STATIC_MIN_FIRMWARE = "1.00.02"
H6179_REACTIVE_LEGACY_STATIC_MAX_FIRMWARE = "1.01.00"
H6179_REACTIVE_MAX_UPDATE_HZ = 20
H6179_REACTIVE_MIN_UPDATE_INTERVAL = 1 / H6179_REACTIVE_MAX_UPDATE_HZ
H6179_REACTIVE_SESSION_TIMEOUT = 2.0

_FIRMWARE_PATTERN = re.compile(r"(0|[1-9]\d*)\.(\d{2})\.(\d{2})")
_LEGACY_STATIC_MIN_FIRMWARE_NUMBER = 10002
_LEGACY_STATIC_MAX_FIRMWARE_NUMBER = 10100


class H6179ReactiveRoute(StrEnum):
    """Observed H6179 derived-RGB write order."""

    MUSIC_STREAM = "music_stream_order"
    LEGACY_STATIC_COLOUR = "legacy_static_colour_order"
    UNRESOLVED = "unresolved"


class ReactiveSessionState(StrEnum):
    IDLE = "idle"
    ACTIVE = "active"


class ReactiveStopReason(StrEnum):
    REQUESTED = "requested"
    SUPERSEDED = "superseded"
    TIMEOUT = "timeout"
    DISCONNECTED = "disconnected"


class ReactiveProtocolError(ValueError):
    """Base error for the H6179 reactive protocol contract."""


class ReactivePayloadError(ReactiveProtocolError):
    """Raised when a payload is not exactly one RGB colour."""


class UnresolvedReactiveFirmwareError(ReactiveProtocolError):
    """Raised when a reactive route cannot be selected without guessing."""


class ReactiveSessionError(RuntimeError):
    """Base error for invalid reactive session operations."""


class ReactiveSessionOwnershipError(ReactiveSessionError):
    """Raised when a stale or foreign session attempts control."""


class ReactiveSessionExpiredError(ReactiveSessionError):
    """Raised when an update arrives after the inactivity timeout."""


@dataclass(frozen=True, slots=True)
class RGB:
    """One browser-derived RGB colour, never audio samples."""

    red: int
    green: int
    blue: int

    def __post_init__(self) -> None:
        for name, value in (("red", self.red), ("green", self.green), ("blue", self.blue)):
            if type(value) is not int or not 0 <= value <= 0xFF:
                raise ReactivePayloadError(f"{name} must be an integer from 0 to 255")

    @classmethod
    def from_payload(cls, payload: object) -> RGB:
        """Validate the exact JSON object accepted from a browser."""
        if not isinstance(payload, Mapping) or set(payload) != {"r", "g", "b"}:
            raise ReactivePayloadError("reactive updates require exactly r, g, and b")
        red, green, blue = payload["r"], payload["g"], payload["b"]
        for name, value in (("r", red), ("g", green), ("b", blue)):
            if type(value) is not int or not 0 <= value <= 0xFF:
                raise ReactivePayloadError(f"{name} must be an integer from 0 to 255")
        return cls(cast(int, red), cast(int, green), cast(int, blue))


@dataclass(frozen=True, slots=True)
class ReactiveSessionResult:
    """One deterministic session transition for the backend scheduler."""

    state: ReactiveSessionState
    session_id: str | None
    frame: bytes | None = None
    coalesced: bool = False
    stop_reason: ReactiveStopReason | None = None
    next_due: float | None = None


def select_h6179_reactive_route(
    firmware_version: str | None,
    *,
    legacy_colour_order: bool = False,
) -> H6179ReactiveRoute:
    """Select the current route, or an explicitly requested legacy compatibility route."""
    version = _firmware_number(firmware_version)
    if version is None:
        return H6179ReactiveRoute.UNRESOLVED
    if legacy_colour_order:
        if _LEGACY_STATIC_MIN_FIRMWARE_NUMBER <= version < _LEGACY_STATIC_MAX_FIRMWARE_NUMBER:
            return H6179ReactiveRoute.LEGACY_STATIC_COLOUR
        return H6179ReactiveRoute.UNRESOLVED
    return H6179ReactiveRoute.MUSIC_STREAM


def build_h6179_reactive_frame(route: H6179ReactiveRoute, rgb: RGB) -> bytes:
    """Build one exact H6179 derived-RGB frame."""
    if not isinstance(rgb, RGB):
        raise ReactivePayloadError("reactive frames accept RGB values only")
    if route is H6179ReactiveRoute.LEGACY_STATIC_COLOUR:
        packet = bytearray(20)
        packet[:6] = bytes((0x33, 0x05, 0x0D, rgb.red, rgb.green, rgb.blue))
        packet[19] = xor_checksum(packet[:19])
        return bytes(packet)
    if route is H6179ReactiveRoute.MUSIC_STREAM:
        stream_packet = bytes((0xA5, 0x02, 0x83, rgb.red, rgb.green, rgb.blue))
        return stream_packet + bytes((sum(stream_packet) & 0xFF,))
    raise UnresolvedReactiveFirmwareError("no H6179 reactive frame is selected for this firmware")


class H6179ReactiveSession:
    """Latest-only, rate-limited lifecycle for one H6179 browser session."""

    def __init__(self, firmware_version: str | None, *, legacy_colour_order: bool = False) -> None:
        self.route = select_h6179_reactive_route(
            firmware_version,
            legacy_colour_order=legacy_colour_order,
        )
        if self.route is H6179ReactiveRoute.UNRESOLVED:
            raise UnresolvedReactiveFirmwareError("H6179 reactive RGB route requires a recognised firmware")
        self._state = ReactiveSessionState.IDLE
        self._session_id: str | None = None
        self._expires_at: float | None = None
        self._next_send_at: float | None = None
        self._pending_rgb: RGB | None = None
        self._last_sent_rgb: RGB | None = None
        self._last_now = -math.inf
        self._last_stop_reason: ReactiveStopReason | None = None

    @property
    def state(self) -> ReactiveSessionState:
        return self._state

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def last_stop_reason(self) -> ReactiveStopReason | None:
        return self._last_stop_reason

    def start(self, session_id: str, now: float) -> ReactiveSessionResult:
        """Open an idle session without inventing a non-browser RGB value."""
        timestamp = self._check_now(now)
        if self._state is ReactiveSessionState.ACTIVE:
            raise ReactiveSessionError("reactive session is already active")
        if type(session_id) is not str or not session_id.strip():
            raise ReactiveSessionError("session_id must be a non-empty string")
        self._last_now = timestamp
        self._state = ReactiveSessionState.ACTIVE
        self._session_id = session_id
        self._expires_at = timestamp + H6179_REACTIVE_SESSION_TIMEOUT
        self._next_send_at = None
        self._pending_rgb = None
        self._last_sent_rgb = None
        self._last_stop_reason = None
        return self._active_result()

    def update(self, session_id: str, rgb: RGB, now: float) -> ReactiveSessionResult:
        """Accept one derived colour, emitting now or retaining only the latest."""
        timestamp = self._check_now(now)
        self._require_owner(session_id)
        if self._expires_at is not None and timestamp >= self._expires_at:
            self._last_now = timestamp
            self._clear(ReactiveStopReason.TIMEOUT)
            raise ReactiveSessionExpiredError("reactive session timed out")
        if not isinstance(rgb, RGB):
            raise ReactivePayloadError("reactive updates accept RGB values only")
        self._last_now = timestamp
        self._expires_at = timestamp + H6179_REACTIVE_SESSION_TIMEOUT

        if rgb == self._last_sent_rgb:
            self._pending_rgb = None
            return self._active_result()
        if self._next_send_at is None or timestamp >= self._next_send_at:
            return self._emit(rgb, timestamp)
        self._pending_rgb = rgb
        return self._active_result(coalesced=True)

    def tick(self, now: float) -> ReactiveSessionResult:
        """Flush a due coalesced colour or expire an inactive session."""
        timestamp = self._check_now(now)
        self._last_now = timestamp
        if self._state is ReactiveSessionState.IDLE:
            return self._idle_result()
        if self._expires_at is not None and timestamp >= self._expires_at:
            return self._clear(ReactiveStopReason.TIMEOUT)
        if self._pending_rgb is None or self._next_send_at is None or timestamp < self._next_send_at:
            return self._active_result(coalesced=self._pending_rgb is not None)
        return self._emit(self._pending_rgb, timestamp)

    def stop(self, session_id: str) -> ReactiveSessionResult:
        """Stop the owner without sending an unproven protocol stop frame."""
        self._require_owner(session_id)
        return self._clear(ReactiveStopReason.REQUESTED)

    def supersede(self) -> ReactiveSessionResult:
        """Release control before a normal Home Assistant command."""
        if self._state is ReactiveSessionState.IDLE:
            return self._idle_result()
        return self._clear(ReactiveStopReason.SUPERSEDED)

    def disconnect(self) -> ReactiveSessionResult:
        """Discard all state when the BLE transport disconnects."""
        if self._state is ReactiveSessionState.IDLE:
            return self._idle_result()
        return self._clear(ReactiveStopReason.DISCONNECTED)

    def _emit(self, rgb: RGB, now: float) -> ReactiveSessionResult:
        self._pending_rgb = None
        self._last_sent_rgb = rgb
        self._next_send_at = now + H6179_REACTIVE_MIN_UPDATE_INTERVAL
        return self._active_result(frame=build_h6179_reactive_frame(self.route, rgb))

    def _active_result(self, *, frame: bytes | None = None, coalesced: bool = False) -> ReactiveSessionResult:
        next_due = self._expires_at
        if self._pending_rgb is not None and self._next_send_at is not None:
            next_due = min(cast(float, next_due), self._next_send_at)
        return ReactiveSessionResult(
            state=ReactiveSessionState.ACTIVE,
            session_id=self._session_id,
            frame=frame,
            coalesced=coalesced,
            next_due=next_due,
        )

    @staticmethod
    def _idle_result(stop_reason: ReactiveStopReason | None = None) -> ReactiveSessionResult:
        return ReactiveSessionResult(
            state=ReactiveSessionState.IDLE,
            session_id=None,
            stop_reason=stop_reason,
        )

    def _clear(self, reason: ReactiveStopReason) -> ReactiveSessionResult:
        self._state = ReactiveSessionState.IDLE
        self._session_id = None
        self._expires_at = None
        self._next_send_at = None
        self._pending_rgb = None
        self._last_sent_rgb = None
        self._last_stop_reason = reason
        return self._idle_result(reason)

    def _require_owner(self, session_id: str) -> None:
        if self._state is ReactiveSessionState.IDLE:
            raise ReactiveSessionError("reactive session is not active")
        if session_id != self._session_id:
            raise ReactiveSessionOwnershipError("reactive session is owned by another session_id")

    def _check_now(self, now: float) -> float:
        if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now):
            raise ReactiveSessionError("now must be a finite monotonic timestamp")
        timestamp = float(now)
        if timestamp < self._last_now:
            raise ReactiveSessionError("now must not move backwards")
        return timestamp


def _firmware_number(firmware_version: str | None) -> int | None:
    if not isinstance(firmware_version, str):
        return None
    match = _FIRMWARE_PATTERN.fullmatch(firmware_version.strip())
    if match is None:
        return None
    major, minor, patch = (int(part) for part in match.groups())
    return major * 10000 + minor * 100 + patch


__all__ = [
    "H6179_REACTIVE_MAX_UPDATE_HZ",
    "H6179_REACTIVE_LEGACY_STATIC_MAX_FIRMWARE",
    "H6179_REACTIVE_LEGACY_STATIC_MIN_FIRMWARE",
    "H6179_REACTIVE_MIN_UPDATE_INTERVAL",
    "H6179_REACTIVE_SESSION_TIMEOUT",
    "H6179ReactiveRoute",
    "H6179ReactiveSession",
    "RGB",
    "ReactivePayloadError",
    "ReactiveProtocolError",
    "ReactiveSessionError",
    "ReactiveSessionExpiredError",
    "ReactiveSessionOwnershipError",
    "ReactiveSessionResult",
    "ReactiveSessionState",
    "ReactiveStopReason",
    "UnresolvedReactiveFirmwareError",
    "build_h6179_reactive_frame",
    "select_h6179_reactive_route",
]
