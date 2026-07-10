"""Dev-only Home Assistant shim that points the Govee BLE transport at the simulator.

Mounted alongside the real integration, this redirects the coordinator's two
transport seams (``establish_connection`` and ``async_ble_device_from_address``)
at ``GoveeDeviceSim`` + ``FakeGoveeClient``, so the integration and its entities
run end-to-end with no BLE adapter. Removing the mount restores real hardware
behaviour unchanged. Not shipped with the integration.
"""

from typing import TYPE_CHECKING, Any
from unittest.mock import patch

from bleak.backends.device import BLEDevice

from .mock_device import FakeGoveeClient, GoveeDeviceSim

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.typing import ConfigType

DOMAIN = "mock_ble"
_COORDINATOR = "custom_components.ha_govee_led_ble.coordinator"
_DEFAULT_ADDRESS = "AA:BB:CC:DD:EE:FF"
_DEFAULT_MODEL = "H617A"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    options: dict[str, Any] = config.get(DOMAIN) or {}
    address = str(options.get("address", _DEFAULT_ADDRESS))
    model = str(options.get("model", _DEFAULT_MODEL))
    client = FakeGoveeClient(GoveeDeviceSim(model))
    device = BLEDevice(address, f"Govee_mock_{address}", {})
    patchers = [
        patch(f"{_COORDINATOR}.establish_connection", return_value=client),
        patch(f"{_COORDINATOR}.bluetooth.async_ble_device_from_address", return_value=device),
    ]
    for patcher in patchers:
        patcher.start()
    hass.data[DOMAIN] = patchers
    return True
