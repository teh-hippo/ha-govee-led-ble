"""Shared BLE connection establishment and validation."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import cast

from bleak import BleakClient, BleakError  # type: ignore[attr-defined]
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    clear_cache,
    close_stale_connections_by_address,
    establish_connection,
)
from homeassistant.core import HomeAssistant

from .ble_device_resolver import BLEDeviceResolver
from .const import DOMAIN

RETRY_BACKOFF_SECONDS = 2
DEVICE_DISCOVERY_ATTEMPTS = 4
VALIDATION_DISCONNECT_TIMEOUT = 10
VALIDATION_CONNECT_TIMEOUT = 30
GATT_CACHE_CLEAR_TIMEOUT = 10
STALE_GATT_RECOVERY_TIMEOUT = 60
_STALE_GATT_RECOVERY_PENDING = "stale_gatt_recovery_pending"

type DisconnectedCallback = Callable[[BleakClient], None]
type EstablishConnection = Callable[..., Awaitable[BleakClient]]
type Sleep = Callable[[float], Awaitable[None]]

_ESTABLISH_CONNECTION = cast(EstablishConnection, establish_connection)
_SLEEP = cast(Sleep, asyncio.sleep)

_GATT_CONTEXT_MARKERS = (
    "attribute",
    "characteristic",
    "gatt",
    "handle",
    "service",
)
_STALE_GATT_MARKERS = (
    "attribute not found",
    "does not exist",
    "invalid handle",
    "not available",
    "not found",
    "unknown object",
)
_STALE_GATT_ERROR_CODES = (
    "org.bluez.error.doesnotexist",
    "org.freedesktop.dbus.error.unknownobject",
)


def is_stale_gatt_error(err: BaseException) -> bool:
    """Return whether an error indicates stale service or characteristic data."""
    return _is_stale_gatt_error(err, bluez_only=False)


def _is_stale_gatt_error(err: BaseException, *, bluez_only: bool) -> bool:
    """Optionally require BlueZ evidence on the same stale-GATT exception."""
    errors = [err]
    visited: set[int] = set()
    while errors:
        current = errors.pop()
        if id(current) in visited:
            continue
        visited.add(id(current))
        if isinstance(current, KeyError) and current.args == ("org.bluez.GattService1",):
            return True
        error_name = type(current).__name__.lower()
        message = str(current).lower()
        dbus_error = str(getattr(current, "dbus_error", "")).lower()
        bluez = "org.bluez" in message or "/org/bluez/" in message or "org.bluez" in dbus_error
        if (not bluez_only or bluez) and (
            "characteristicnotfound" in error_name
            or (
                any(context in message for context in _GATT_CONTEXT_MARKERS)
                and (
                    any(code in message or code in dbus_error for code in _STALE_GATT_ERROR_CODES)
                    or any(marker in message for marker in _STALE_GATT_MARKERS)
                )
            )
        ):
            return True
        errors.extend(link for link in (current.__cause__, current.__context__) if link is not None)
    return False


def stale_gatt_recovery_pending(hass: HomeAssistant, address: str) -> bool:
    """Return whether this device still requires native GATT cache recovery."""
    return address.upper() in hass.data.get(DOMAIN, {}).get(_STALE_GATT_RECOVERY_PENDING, ())


def mark_stale_gatt_recovery(hass: HomeAssistant, address: str) -> None:
    """Retain recovery across validation, coordinator replacement and reload."""
    hass.data.setdefault(DOMAIN, {}).setdefault(_STALE_GATT_RECOVERY_PENDING, set()).add(address.upper())


def clear_stale_gatt_recovery(hass: HomeAssistant, address: str) -> None:
    """Clear recovery only after required readiness or actual entry removal."""
    pending = hass.data.get(DOMAIN, {}).get(_STALE_GATT_RECOVERY_PENDING)
    if pending is not None:
        pending.discard(address.upper())


async def async_clear_gatt_cache(client: BleakClient) -> bool:
    """Bound native cache clearing through HA's public client API."""
    try:
        async with asyncio.timeout(GATT_CACHE_CLEAR_TIMEOUT):
            return bool(await cast(BleakClientWithServiceCache, client).clear_cache())
    except Exception:
        return False


async def async_establish_ble_connection(
    hass: HomeAssistant,
    address: str,
    *,
    resolver: BLEDeviceResolver | None = None,
    establish: EstablishConnection = _ESTABLISH_CONNECTION,
    sleep: Sleep = _SLEEP,
    disconnected_callback: DisconnectedCallback | None = None,
    use_services_cache: bool = True,
) -> BleakClient:
    """Resolve and establish a BLE connection using production retry semantics."""
    active_resolver = BLEDeviceResolver() if resolver is None else resolver
    recovery_pending = stale_gatt_recovery_pending(hass, address)

    async def connect(callback: DisconnectedCallback | None, cache: bool) -> BleakClient:
        resolution = None
        for attempt in range(DEVICE_DISCOVERY_ATTEMPTS):
            resolution = await active_resolver.async_resolve(hass, address)
            if resolution is not None:
                break
            if attempt < DEVICE_DISCOVERY_ATTEMPTS - 1:
                await sleep(RETRY_BACKOFF_SECONDS)
        if resolution is None:
            raise BleakError(f"Device {address} not found")
        kwargs: dict[str, object] = {"use_services_cache": cache}
        if callback is not None:
            kwargs["disconnected_callback"] = callback
        return await establish(resolution.client_class, resolution.device, address, **kwargs)

    try:
        if not recovery_pending:
            return await connect(disconnected_callback, use_services_cache)
        async with asyncio.timeout(STALE_GATT_RECOVERY_TIMEOUT):
            # ponytail: ESPHome needs a returned client; no-return recovery needs an upstream eviction API.
            bootstrap = await connect(None, False)
            disconnected = False
            try:
                cleared = await async_clear_gatt_cache(bootstrap)
            finally:
                try:
                    async with asyncio.timeout(VALIDATION_DISCONNECT_TIMEOUT):
                        await bootstrap.disconnect()
                    disconnected = True
                except Exception:
                    disconnected = False
            if not cleared or not disconnected:
                raise BleakError("Failed to recover the GATT cache")
            return await connect(disconnected_callback, False)
    except Exception as err:
        if is_stale_gatt_error(err):
            mark_stale_gatt_recovery(hass, address)
            if _is_stale_gatt_error(err, bluez_only=True):
                # BlueZ may fail before returning a client; unblock the next bootstrap.
                with suppress(Exception):
                    async with asyncio.timeout(GATT_CACHE_CLEAR_TIMEOUT):
                        await clear_cache(address)
        if recovery_pending:
            raise BleakError("Failed to recover the GATT cache") from None
        raise


async def async_validate_ble_connection(hass: HomeAssistant, address: str) -> None:
    """Verify a BLE connection can be opened and cleaned up."""
    try:
        async with asyncio.timeout(VALIDATION_CONNECT_TIMEOUT):
            client = await async_establish_ble_connection(hass, address)
    except TimeoutError as err:
        await _async_close_stale_validation_connection(address)
        raise BleakError("Timed out opening the validation connection") from err
    try:
        async with asyncio.timeout(VALIDATION_DISCONNECT_TIMEOUT):
            await client.disconnect()
    except BleakError, TimeoutError:
        await _async_close_stale_validation_connection(address)


async def _async_close_stale_validation_connection(address: str) -> None:
    try:
        async with asyncio.timeout(VALIDATION_DISCONNECT_TIMEOUT):
            await close_stale_connections_by_address(address)
    except (BleakError, TimeoutError) as err:
        raise BleakError("Failed to close the validation connection") from err
