import pytest
from homeassistant import config_entries
from homeassistant.components.bluetooth import BluetoothServiceInfo
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.ha_govee_led_ble.config_flow import _extract_model
from custom_components.ha_govee_led_ble.const import CONF_MODEL, DOMAIN

SVC = BluetoothServiceInfo("ihoment_H617A_ABCD", "AA:BB:CC:DD:EE:FF", -60, {}, {}, [], "local")


@pytest.fixture(autouse=True)
async def mock_bluetooth(hass, enable_custom_integrations):
    hass.config.components |= {"bluetooth", "bluetooth_adapters"}


async def _init(hass, source, data=None):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": source}, data=data)


async def test_bluetooth_discovery(hass: HomeAssistant):
    r = await _init(hass, config_entries.SOURCE_BLUETOOTH, SVC)
    assert r["type"] == FlowResultType.CREATE_ENTRY and r["title"] == "ihoment_H617A_ABCD"
    assert r["data"][CONF_MODEL] == "H617A"


async def test_bluetooth_discovery_abort_duplicate(hass: HomeAssistant):
    await _init(hass, config_entries.SOURCE_BLUETOOTH, SVC)
    r2 = await _init(hass, config_entries.SOURCE_BLUETOOTH, SVC)
    assert r2["type"] == FlowResultType.ABORT and r2["reason"] == "already_configured"


async def test_user_step_shows_form(hass: HomeAssistant):
    r = await _init(hass, config_entries.SOURCE_USER)
    assert r["type"] == FlowResultType.FORM and r["step_id"] == "user"


async def test_user_step_creates_entry(hass: HomeAssistant):
    r = await _init(hass, config_entries.SOURCE_USER, {CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_MODEL: "H617A"})
    assert r["type"] == FlowResultType.CREATE_ENTRY and r["data"][CONF_MODEL] == "H617A"


_EM = [("SomeOtherDevice", None), ("Govee_H9999_ABCD", None), ("", None), ("ihoment_H617A_ABCD", "H617A")]
_EM += [("Govee_H617A_ABCD", "H617A"), ("GBK_H617A_ABCD", "H617A"), ("GVH_H617A_ABCD", "H617A")]


@pytest.mark.parametrize("name,expected", _EM)
def test_extract_model(name, expected):
    assert _extract_model(name) == expected
