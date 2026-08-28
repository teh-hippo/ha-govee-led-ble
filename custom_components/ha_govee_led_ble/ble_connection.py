"""Shared BLE connection establishment and validation."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import cast

from bleak import BleakClient, BleakError  # type: ignore[attr-defined]
from bleak_retry_connector import close_stale_connections_by_address, establish_connection
from homeassistant.core import HomeAssistant

from .ble_device_resolver import BLEDeviceResolver

RETRY_BACKOFF_SECONDS = 2
DEVICE_DISCOVERY_ATTEMPTS = 4
VALIDATION_DISCONNECT_TIMEOUT = 10
VALIDATION_CONNECT_TIMEOUT = 30

type DisconnectedCallback = Callable[[BleakClient], None]
type EstablishConnection = Callable[..., Awaitable[BleakClient]]
type Sleep = Callable[[float], Awaitable[None]]

_ESTABLISH_CONNECTION = cast(EstablishConnection, establish_connection)
_SLEEP = cast(Sleep, asyncio.sleep)


async def async_establish_ble_connection(
    hass: HomeAssistant,
    address: str,
    *,
    resolver: BLEDeviceResolver | None = None,
    establish: EstablishConnection = _ESTABLISH_CONNECTION,
    sleep: Sleep = _SLEEP,
    disconnected_callback: DisconnectedCallback | None = None,
) -> BleakClient:
    """Resolve and establish a BLE connection using production retry semantics."""
    active_resolver = BLEDeviceResolver() if resolver is None else resolver
    resolution = None
    for attempt in range(DEVICE_DISCOVERY_ATTEMPTS):
        resolution = await active_resolver.async_resolve(hass, address)
        if resolution is not None:
            break
        if attempt < DEVICE_DISCOVERY_ATTEMPTS - 1:
            await sleep(RETRY_BACKOFF_SECONDS)
    if resolution is None:
        raise BleakError(f"Device {address} not found")
    if disconnected_callback is None:
        return await establish(resolution.client_class, resolution.device, address)
    return await establish(
        resolution.client_class,
        resolution.device,
        address,
        disconnected_callback=disconnected_callback,
    )


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
