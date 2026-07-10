import pytest
from homeassistant import config_entries
from homeassistant.components.bluetooth import BluetoothServiceInfo
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.ha_govee_led_ble.config_flow import GoveeConfigFlow, _extract_model
from custom_components.ha_govee_led_ble.const import CONF_MODEL, DOMAIN

SVC = BluetoothServiceInfo("ihoment_H617A_ABCD", "AA:BB:CC:DD:EE:FF", -60, {}, {}, [], "local")
SVC_LOWER = BluetoothServiceInfo("ihoment_H617A_ABCD", "aa:bb:cc:dd:ee:ff", -60, {}, {}, [], "local")
SVC_UNSUPPORTED = BluetoothServiceInfo("SomeOtherDevice", "11:22:33:44:55:66", -60, {}, {}, [], "local")


@pytest.fixture(autouse=True)
async def mock_bluetooth(hass, enable_custom_integrations):
    hass.config.components |= {"bluetooth", "bluetooth_adapters"}


async def _init(hass, source, data=None):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": source}, data=data)


async def _confirm(hass, result):
    return await hass.config_entries.flow.async_configure(result["flow_id"], {})


async def test_bluetooth_discovery(hass: HomeAssistant):
    r = await _init(hass, config_entries.SOURCE_BLUETOOTH, SVC)
    assert r["type"] == FlowResultType.FORM and r["step_id"] == "bluetooth_confirm"
    assert r["description_placeholders"] == {"model": "H617A"}
    r2 = await _confirm(hass, r)
    assert r2["type"] == FlowResultType.CREATE_ENTRY and r2["title"] == "Govee H617A"
    assert r2["data"][CONF_MODEL] == "H617A"


async def test_bluetooth_discovery_unsupported_aborts(hass: HomeAssistant):
    r = await _init(hass, config_entries.SOURCE_BLUETOOTH, SVC_UNSUPPORTED)
    assert r["type"] == FlowResultType.ABORT and r["reason"] == "not_supported"
    assert not hass.config_entries.async_entries(DOMAIN)


async def test_bluetooth_discovery_normalizes_unique_id(hass: HomeAssistant):
    r = await _init(hass, config_entries.SOURCE_BLUETOOTH, SVC_LOWER)
    await _confirm(hass, r)
    assert hass.config_entries.async_entries(DOMAIN)[0].unique_id == "AA:BB:CC:DD:EE:FF"


async def test_bluetooth_discovery_abort_duplicate(hass: HomeAssistant):
    r = await _init(hass, config_entries.SOURCE_BLUETOOTH, SVC)
    await _confirm(hass, r)
    r2 = await _init(hass, config_entries.SOURCE_BLUETOOTH, SVC)
    assert r2["type"] == FlowResultType.ABORT and r2["reason"] == "already_configured"


async def test_bluetooth_discovery_abort_duplicate_with_user_entry(hass: HomeAssistant):
    await _init(hass, config_entries.SOURCE_USER, {CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_MODEL: "H617A"})
    r = await _init(hass, config_entries.SOURCE_BLUETOOTH, SVC_LOWER)
    assert r["type"] == FlowResultType.ABORT and r["reason"] == "already_configured"


async def test_bluetooth_discovery_exposes_no_pii(hass: HomeAssistant):
    r = await _init(hass, config_entries.SOURCE_BLUETOOTH, SVC)
    context = hass.config_entries.flow.async_progress()[0]["context"]
    assert r["description_placeholders"] == {"model": "H617A"}
    assert context["title_placeholders"] == {"name": "H617A"}
    r2 = await _confirm(hass, r)
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert r2["title"] == entry.title == "Govee H617A" and entry.data == {CONF_MODEL: "H617A"}
    for surface in (r["description_placeholders"], context["title_placeholders"], entry.title, entry.data):
        blob = str(surface)
        assert SVC.address not in blob and "ABCD" not in blob


async def test_user_step_shows_form(hass: HomeAssistant):
    r = await _init(hass, config_entries.SOURCE_USER)
    assert r["type"] == FlowResultType.FORM and r["step_id"] == "user"


async def test_user_step_creates_entry(hass: HomeAssistant):
    r = await _init(hass, config_entries.SOURCE_USER, {CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_MODEL: "H617A"})
    assert r["type"] == FlowResultType.CREATE_ENTRY and r["data"][CONF_MODEL] == "H617A"


async def test_user_step_defaults_model_to_h617a(hass: HomeAssistant):
    r = await _init(hass, config_entries.SOURCE_USER)
    r2 = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_ADDRESS: "11:22:33:44:55:66"})
    assert r2["type"] == FlowResultType.CREATE_ENTRY and r2["data"][CONF_MODEL] == "H617A"


_EM = [("SomeOtherDevice", None), ("Govee_H9999_ABCD", None), ("", None), ("ihoment_H617A_ABCD", "H617A")]
_EM += [("Govee_H617A_ABCD", "H617A"), ("GBK_H617A_ABCD", "H617A"), ("GVH_H617A_ABCD", "H617A")]


@pytest.mark.parametrize("name,expected", _EM)
def test_extract_model(name, expected):
    assert _extract_model(name) == expected


def test_no_options_flow():
    """The experimental OptionsFlow is gone; opt-in is via disabled-by-default entities."""
    assert GoveeConfigFlow.async_get_options_flow is config_entries.ConfigFlow.async_get_options_flow
