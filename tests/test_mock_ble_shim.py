import pytest

from tools.ble.mock_ble import DOMAIN, async_setup


@pytest.fixture(autouse=True)
def _enable(enable_custom_integrations):
    yield


async def test_shim_patches_transport(hass):
    try:
        assert await async_setup(hass, {DOMAIN: {"address": "AA:BB:CC:DD:EE:FF", "model": "H617A"}})
        from custom_components.ha_govee_led_ble import coordinator

        client = await coordinator.establish_connection(None, None, "AA:BB:CC:DD:EE:FF")
        assert type(client).__name__ == "FakeGoveeClient"
        device = coordinator.bluetooth.async_ble_device_from_address(hass, "AA:BB:CC:DD:EE:FF")
        assert device.address == "AA:BB:CC:DD:EE:FF"
    finally:
        for patcher in hass.data.get(DOMAIN, []):
            patcher.stop()


async def test_shim_defaults(hass):
    try:
        assert await async_setup(hass, {})
        assert len(hass.data[DOMAIN]) == 2
    finally:
        for patcher in hass.data.get(DOMAIN, []):
            patcher.stop()
