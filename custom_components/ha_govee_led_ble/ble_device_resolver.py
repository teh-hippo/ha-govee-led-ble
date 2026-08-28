"""Resolve BLE devices through Home Assistant."""

from dataclasses import dataclass

import bleak
from bleak import BleakClient
from bleak.backends.device import BLEDevice
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant


@dataclass(frozen=True, slots=True)
class BLEDeviceResolution:
    """A device paired with the client class suitable for its source."""

    device: BLEDevice
    client_class: type[BleakClient]


@dataclass(frozen=True, slots=True)
class BLEDeviceResolver:
    """Resolve from Home Assistant's connectable BLE cache."""

    async def async_resolve(self, hass: HomeAssistant, address: str) -> BLEDeviceResolution | None:
        device = bluetooth.async_ble_device_from_address(hass, address, connectable=True)
        return None if device is None else BLEDeviceResolution(device, bleak.BleakClient)
