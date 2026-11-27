"""Resolve BLE devices through Home Assistant."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak_retry_connector import BleakClientWithServiceCache
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant


@dataclass(frozen=True, slots=True)
class BLEDeviceResolution:
    """A device paired with the client class suitable for its source."""

    device: BLEDevice
    client_class: type[BleakClient]


type BLEDeviceResolver = Callable[[HomeAssistant, str], Awaitable[BLEDeviceResolution | None]]


async def async_resolve_ble_device(hass: HomeAssistant, address: str) -> BLEDeviceResolution | None:
    """Resolve from Home Assistant's connectable BLE cache."""
    device = bluetooth.async_ble_device_from_address(hass, address, connectable=True)
    return None if device is None else BLEDeviceResolution(device, BleakClientWithServiceCache)
