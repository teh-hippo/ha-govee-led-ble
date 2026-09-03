"""Authenticated WebSocket integration for H6179 reactive RGB."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Final, cast

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.components.websocket_api.connection import ActiveConnection
from homeassistant.components.websocket_api.decorators import (
    async_response,
    require_admin,
    websocket_command,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant

from .const import DOMAIN
from .h6179_reactive_backend import (
    H6179ReactiveBackend,
    H6179ReactiveCoordinator,
    ReactiveBackendShutdownError,
    ReactiveSessionBusyError,
    ReactiveSessionNotFoundError,
    ReactiveSessionSupersededError,
    ReactiveSessionUnauthorizedError,
    ReactiveTargetUnavailableError,
    ReactiveTargetUnsupportedError,
    ReactiveWriteError,
)
from .h6179_reactive_protocol import (
    ReactivePayloadError,
    ReactiveSessionError,
    ReactiveSessionExpiredError,
    ReactiveSessionOwnershipError,
    UnresolvedReactiveFirmwareError,
)

WS_REACTIVE_START = f"{DOMAIN}/reactive/start"
WS_REACTIVE_UPDATE = f"{DOMAIN}/reactive/update"
WS_REACTIVE_STOP = f"{DOMAIN}/reactive/stop"

REACTIVE_BACKEND_DATA_KEY: Final = "h6179_reactive_backend"


class ReactiveErrorCode(StrEnum):
    """Stable external error codes for WebSocket handlers."""

    INVALID_PAYLOAD = "reactive_invalid_payload"
    UNKNOWN_FIRMWARE = "reactive_unknown_firmware"
    TARGET_UNSUPPORTED = "reactive_target_unsupported"
    TARGET_UNAVAILABLE = "reactive_target_unavailable"
    SESSION_ACTIVE = "reactive_session_active"
    SESSION_NOT_FOUND = "reactive_session_not_found"
    SESSION_UNAUTHORIZED = "reactive_session_unauthorized"
    SESSION_EXPIRED = "reactive_session_expired"
    SESSION_SUPERSEDED = "reactive_session_superseded"
    WRITE_FAILED = "reactive_write_failed"
    SHUTTING_DOWN = "reactive_shutting_down"
    INVALID_SESSION = "reactive_invalid_session"
    INTERNAL_ERROR = "reactive_internal_error"


def _strict_byte(value: object) -> int:
    if type(value) is not int or not 0 <= value <= 0xFF:
        raise vol.Invalid("RGB channels must be integers from 0 to 255")
    return value


def _strict_bool(value: object) -> bool:
    if type(value) is not bool:
        raise vol.Invalid("value must be a boolean")
    return value


IDENTIFIER = vol.All(str, vol.Length(min=1, max=255))
SESSION_ID = vol.All(str, vol.Length(min=36, max=36))
RGB_PAYLOAD_SCHEMA = vol.Schema(
    {
        vol.Required("r"): _strict_byte,
        vol.Required("g"): _strict_byte,
        vol.Required("b"): _strict_byte,
    },
    extra=vol.PREVENT_EXTRA,
)

REACTIVE_START_WS_SCHEMA = vol.Schema(
    {
        vol.Required("type"): WS_REACTIVE_START,
        vol.Required("config_entry_id"): IDENTIFIER,
        vol.Optional("legacy_colour_order", default=False): _strict_bool,
    },
    extra=vol.PREVENT_EXTRA,
)
REACTIVE_UPDATE_WS_SCHEMA = vol.Schema(
    {
        vol.Required("type"): WS_REACTIVE_UPDATE,
        vol.Required("config_entry_id"): IDENTIFIER,
        vol.Required("session_id"): SESSION_ID,
        vol.Required("rgb"): RGB_PAYLOAD_SCHEMA,
    },
    extra=vol.PREVENT_EXTRA,
)
REACTIVE_STOP_WS_SCHEMA = vol.Schema(
    {
        vol.Required("type"): WS_REACTIVE_STOP,
        vol.Required("config_entry_id"): IDENTIFIER,
        vol.Required("session_id"): SESSION_ID,
    },
    extra=vol.PREVENT_EXTRA,
)


def reactive_error_code(error: BaseException) -> ReactiveErrorCode:
    if isinstance(error, ReactivePayloadError):
        return ReactiveErrorCode.INVALID_PAYLOAD
    if isinstance(error, UnresolvedReactiveFirmwareError):
        return ReactiveErrorCode.UNKNOWN_FIRMWARE
    if isinstance(error, ReactiveTargetUnsupportedError):
        return ReactiveErrorCode.TARGET_UNSUPPORTED
    if isinstance(error, ReactiveTargetUnavailableError):
        return ReactiveErrorCode.TARGET_UNAVAILABLE
    if isinstance(error, ReactiveSessionBusyError):
        return ReactiveErrorCode.SESSION_ACTIVE
    if isinstance(error, ReactiveSessionNotFoundError):
        return ReactiveErrorCode.SESSION_NOT_FOUND
    if isinstance(error, (ReactiveSessionUnauthorizedError, ReactiveSessionOwnershipError)):
        return ReactiveErrorCode.SESSION_UNAUTHORIZED
    if isinstance(error, ReactiveSessionExpiredError):
        return ReactiveErrorCode.SESSION_EXPIRED
    if isinstance(error, ReactiveSessionSupersededError):
        return ReactiveErrorCode.SESSION_SUPERSEDED
    if isinstance(error, ReactiveWriteError):
        return ReactiveErrorCode.WRITE_FAILED
    if isinstance(error, ReactiveBackendShutdownError):
        return ReactiveErrorCode.SHUTTING_DOWN
    if isinstance(error, ReactiveSessionError):
        return ReactiveErrorCode.INVALID_SESSION
    return ReactiveErrorCode.INTERNAL_ERROR


def _backend(hass: HomeAssistant) -> H6179ReactiveBackend:
    return cast(H6179ReactiveBackend, hass.data[DOMAIN][REACTIVE_BACKEND_DATA_KEY])


def get_h6179_reactive_backend(hass: HomeAssistant) -> H6179ReactiveBackend | None:
    return cast(
        H6179ReactiveBackend | None,
        hass.data.get(DOMAIN, {}).get(REACTIVE_BACKEND_DATA_KEY),
    )


def _coordinator_for_entry(
    hass: HomeAssistant,
    config_entry_id: str,
) -> H6179ReactiveCoordinator | None:
    entry = hass.config_entries.async_get_entry(config_entry_id)
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        return None
    return cast(H6179ReactiveCoordinator, entry.runtime_data)


def _send_error(
    connection: ActiveConnection,
    message_id: int,
    error: Exception,
) -> None:
    connection.send_error(message_id, reactive_error_code(error).value, str(error))


@websocket_command(REACTIVE_START_WS_SCHEMA.schema)
@require_admin
@async_response
async def ws_reactive_start(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    try:
        coordinator = _coordinator_for_entry(hass, msg["config_entry_id"])
        if coordinator is None:
            raise ReactiveTargetUnavailableError("target config entry is not loaded")
        status = await _backend(hass).async_start(
            config_entry_id=msg["config_entry_id"],
            owner=connection,
            coordinator=coordinator,
            legacy_colour_order=msg["legacy_colour_order"],
        )
    except Exception as error:
        _send_error(connection, msg["id"], error)
        return
    connection.send_result(msg["id"], status.to_dict())


@websocket_command(REACTIVE_UPDATE_WS_SCHEMA.schema)
@require_admin
@async_response
async def ws_reactive_update(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    try:
        status = await _backend(hass).async_update(
            config_entry_id=msg["config_entry_id"],
            session_id=msg["session_id"],
            owner=connection,
            rgb_payload=msg["rgb"],
        )
    except Exception as error:
        _send_error(connection, msg["id"], error)
        return
    connection.send_result(msg["id"], status.to_dict())


@websocket_command(REACTIVE_STOP_WS_SCHEMA.schema)
@require_admin
@async_response
async def ws_reactive_stop(
    hass: HomeAssistant,
    connection: ActiveConnection,
    msg: dict[str, Any],
) -> None:
    try:
        status = await _backend(hass).async_stop(
            config_entry_id=msg["config_entry_id"],
            session_id=msg["session_id"],
            owner=connection,
        )
    except Exception as error:
        _send_error(connection, msg["id"], error)
        return
    connection.send_result(msg["id"], status.to_dict())


def async_register_h6179_reactive_websocket(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_reactive_start)
    websocket_api.async_register_command(hass, ws_reactive_update)
    websocket_api.async_register_command(hass, ws_reactive_stop)


async def async_setup_h6179_reactive(
    hass: HomeAssistant,
) -> H6179ReactiveBackend:
    data = hass.data.setdefault(DOMAIN, {})
    existing_backend = get_h6179_reactive_backend(hass)
    if existing_backend is not None:
        return existing_backend

    backend = H6179ReactiveBackend()
    data[REACTIVE_BACKEND_DATA_KEY] = backend
    async_register_h6179_reactive_websocket(hass)

    async def async_shutdown(_event: Event) -> None:
        await backend.async_shutdown()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, async_shutdown)
    return backend


__all__ = [
    "REACTIVE_BACKEND_DATA_KEY",
    "REACTIVE_START_WS_SCHEMA",
    "REACTIVE_STOP_WS_SCHEMA",
    "REACTIVE_UPDATE_WS_SCHEMA",
    "RGB_PAYLOAD_SCHEMA",
    "ReactiveErrorCode",
    "WS_REACTIVE_START",
    "WS_REACTIVE_STOP",
    "WS_REACTIVE_UPDATE",
    "async_register_h6179_reactive_websocket",
    "async_setup_h6179_reactive",
    "get_h6179_reactive_backend",
    "reactive_error_code",
    "ws_reactive_start",
    "ws_reactive_stop",
    "ws_reactive_update",
]
