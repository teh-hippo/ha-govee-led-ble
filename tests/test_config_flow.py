import logging
from unittest.mock import AsyncMock, patch

import pytest
from bleak import BleakError
from homeassistant import config_entries
from homeassistant.components.bluetooth import BluetoothServiceInfo
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_govee_led_ble.config_flow import _extract_model
from custom_components.ha_govee_led_ble.const import (
    CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS,
    CONF_EFFECT_CATEGORIES,
    CONF_MODEL,
    CONF_PREFIX_EFFECT_NAMES,
    DOMAIN,
)

M = "custom_components.ha_govee_led_ble.config_flow"
SVC = BluetoothServiceInfo("ihoment_H617A_ABCD", "AA:BB:CC:DD:EE:FF", -60, {}, {}, [], "local")
SVC_LOWER = BluetoothServiceInfo("ihoment_H617A_ABCD", "aa:bb:cc:dd:ee:ff", -60, {}, {}, [], "local")
SVC_UNSUPPORTED = BluetoothServiceInfo("SomeOtherDevice", "11:22:33:44:55:66", -60, {}, {}, [], "local")


@pytest.fixture(autouse=True)
async def mock_bluetooth(hass, enable_custom_integrations):
    hass.config.components |= {"bluetooth", "bluetooth_adapters"}


@pytest.fixture(autouse=True)
def mock_manual_validation():
    with (
        patch(f"{M}.async_validate_ble_connection", new_callable=AsyncMock) as validation,
        patch(f"{M}.bluetooth.async_last_service_info", return_value=None),
    ):
        yield validation


async def _init(hass, source, data=None):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": source}, data=data)


async def _confirm(hass, result):
    return await hass.config_entries.flow.async_configure(result["flow_id"], {})


async def test_bluetooth_discovery(hass: HomeAssistant, mock_manual_validation):
    r = await _init(hass, config_entries.SOURCE_BLUETOOTH, SVC)
    assert r["type"] == FlowResultType.FORM and r["step_id"] == "bluetooth_confirm"
    assert r["description_placeholders"] == {"model": "H617A"}
    r2 = await _confirm(hass, r)
    assert r2["type"] == FlowResultType.CREATE_ENTRY and r2["title"] == "Govee H617A"
    assert r2["data"][CONF_MODEL] == "H617A"
    mock_manual_validation.assert_not_awaited()


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


async def test_user_step_outranks_matching_discovery_in_progress(hass: HomeAssistant):
    discovery = await _init(hass, config_entries.SOURCE_BLUETOOTH, SVC)
    assert discovery["type"] == FlowResultType.FORM

    with patch(f"{M}.bluetooth.async_last_service_info", return_value=SVC):
        manual = await _init(
            hass,
            config_entries.SOURCE_USER,
            {CONF_ADDRESS: SVC.address, CONF_MODEL: "H617A"},
        )

    assert manual["type"] == FlowResultType.CREATE_ENTRY
    assert manual["data"] == {CONF_MODEL: "H617A"}
    assert not hass.config_entries.flow.async_progress()
    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    assert entries[0].unique_id == SVC.address


async def test_user_step_aborts_when_address_is_already_configured(hass: HomeAssistant, mock_manual_validation):
    MockConfigEntry(domain=DOMAIN, unique_id=SVC.address).add_to_hass(hass)

    result = await _init(
        hass,
        config_entries.SOURCE_USER,
        {CONF_ADDRESS: SVC.address, CONF_MODEL: "H617A"},
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    mock_manual_validation.assert_not_awaited()


async def test_user_step_rechecks_duplicate_after_connection_validation(hass: HomeAssistant, mock_manual_validation):
    async def add_entry_during_validation(_hass: HomeAssistant, _address: str) -> None:
        MockConfigEntry(domain=DOMAIN, unique_id=SVC.address).add_to_hass(hass)

    mock_manual_validation.side_effect = add_entry_during_validation
    result = await _init(
        hass,
        config_entries.SOURCE_USER,
        {CONF_ADDRESS: SVC.address, CONF_MODEL: "H617A"},
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


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


async def test_user_step_creates_entry(hass: HomeAssistant, mock_manual_validation):
    r = await _init(hass, config_entries.SOURCE_USER, {CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_MODEL: "H617A"})
    assert r["type"] == FlowResultType.CREATE_ENTRY and r["data"][CONF_MODEL] == "H617A"
    mock_manual_validation.assert_awaited_once_with(hass, "AA:BB:CC:DD:EE:FF")


async def test_user_step_rejects_positive_model_mismatch(hass: HomeAssistant, mock_manual_validation):
    with patch(f"{M}.bluetooth.async_last_service_info", return_value=SVC):
        r = await _init(
            hass,
            config_entries.SOURCE_USER,
            {CONF_ADDRESS: SVC.address, CONF_MODEL: "H6199"},
        )
    assert r["type"] == FlowResultType.FORM
    assert r["errors"] == {"base": "model_mismatch"}
    assert not hass.config_entries.async_entries(DOMAIN)
    mock_manual_validation.assert_not_awaited()


async def test_user_step_validates_when_advertised_name_is_unknown(hass: HomeAssistant, mock_manual_validation):
    service_info = BluetoothServiceInfo("Unknown_Device", "AA:BB:CC:DD:EE:FF", -60, {}, {}, [], "local")
    with patch(f"{M}.bluetooth.async_last_service_info", return_value=service_info):
        r = await _init(
            hass,
            config_entries.SOURCE_USER,
            {CONF_ADDRESS: service_info.address, CONF_MODEL: "H617A"},
        )
    assert r["type"] == FlowResultType.CREATE_ENTRY
    mock_manual_validation.assert_awaited_once_with(hass, service_info.address)


async def test_user_step_surfaces_connection_failure(hass: HomeAssistant, mock_manual_validation):
    mock_manual_validation.side_effect = BleakError("unreachable")
    r = await _init(
        hass,
        config_entries.SOURCE_USER,
        {CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_MODEL: "H617A"},
    )
    assert r["type"] == FlowResultType.FORM
    assert r["errors"] == {"base": "cannot_connect"}
    assert not hass.config_entries.async_entries(DOMAIN)


async def test_user_step_logs_and_surfaces_unexpected_validation_failure(
    hass: HomeAssistant, mock_manual_validation, caplog
):
    mock_manual_validation.side_effect = RuntimeError("unexpected")
    with caplog.at_level(logging.ERROR):
        r = await _init(
            hass,
            config_entries.SOURCE_USER,
            {CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_MODEL: "H617A"},
        )
    assert r["type"] == FlowResultType.FORM
    assert r["errors"] == {"base": "unknown"}
    assert not hass.config_entries.async_entries(DOMAIN)
    assert "Unexpected error validating a Govee BLE device" in caplog.text


@pytest.mark.parametrize("address", ["aa-bb-cc-dd-ee-ff", "aabbccddeeff"])
async def test_user_step_normalizes_common_manual_address_formats(hass: HomeAssistant, address):
    r = await _init(hass, config_entries.SOURCE_USER, {CONF_ADDRESS: address, CONF_MODEL: "H617A"})
    assert r["type"] == FlowResultType.CREATE_ENTRY
    assert hass.config_entries.async_entries(DOMAIN)[0].unique_id == "AA:BB:CC:DD:EE:FF"


@pytest.mark.parametrize("address", ["", "AA:BB:CC", "GG:BB:CC:DD:EE:FF", "not-an-address"])
async def test_user_step_rejects_invalid_manual_address(hass: HomeAssistant, address):
    r = await _init(hass, config_entries.SOURCE_USER, {CONF_ADDRESS: address, CONF_MODEL: "H617A"})
    assert r["type"] == FlowResultType.FORM
    assert r["step_id"] == "user"
    assert r["errors"] == {CONF_ADDRESS: "invalid_address"}
    assert not hass.config_entries.async_entries(DOMAIN)


async def test_user_step_requires_explicit_model(hass: HomeAssistant):
    r = await _init(hass, config_entries.SOURCE_USER)
    with pytest.raises(InvalidData):
        await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_ADDRESS: "11:22:33:44:55:66"})
    assert not hass.config_entries.async_entries(DOMAIN)


_EM = [("SomeOtherDevice", None), ("Govee_H9999_ABCD", None), ("", None), ("ihoment_H617A_ABCD", "H617A")]
_EM += [("Govee_H617A_ABCD", "H617A"), ("GBK_H617A_ABCD", "H617A"), ("GVH_H617A_ABCD", "H617A")]
_EM += [
    ("ihoment_H617E_ABCD", "H617E"),
    ("Govee_H617E_ABCD", "H617E"),
    ("GBK_H617E_ABCD", "H617E"),
    ("GVH_H617E_ABCD", "H617E"),
]


@pytest.mark.parametrize("name,expected", _EM)
def test_extract_model(name, expected):
    assert _extract_model(name) == expected


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("H617A", ["scenes", "effects", "multi_layered", "reactive", "advanced"]),
        ("H6199", ["video", "scenes", "effects", "reactive", "advanced"]),
    ],
)
async def test_options_flow_shows_supported_category_checkboxes(hass: HomeAssistant, model: str, expected: list[str]):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_MODEL: model}, unique_id="AA:BB:CC:DD:EE:FF")
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    schema = result["data_schema"]
    assert schema is not None
    assert [marker.schema for marker in schema.schema] == [
        *expected,
        CONF_PREFIX_EFFECT_NAMES,
        CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS,
    ]
    assert schema({}) == {
        **dict.fromkeys(expected, True),
        CONF_PREFIX_EFFECT_NAMES: False,
        CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS: False,
    }


async def test_options_flow_uses_stored_category_list_for_checkbox_defaults(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_MODEL: "H6199"},
        options={CONF_EFFECT_CATEGORIES: ["scenes", "reactive"]},
        unique_id="AA:BB:CC:DD:EE:FF",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    schema = result["data_schema"]
    assert schema is not None
    assert schema({}) == {
        "scenes": True,
        "video": False,
        "effects": False,
        "reactive": True,
        "advanced": False,
        CONF_PREFIX_EFFECT_NAMES: False,
        CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS: False,
    }


async def test_options_flow_aborts_for_unsupported_model(hass: HomeAssistant):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_MODEL: "H9999"}, unique_id="AA:BB:CC:DD:EE:FF")
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_supported"


async def test_options_flow_saves_ordered_studio_categories(hass: HomeAssistant):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_MODEL: "H6199"}, unique_id="AA:BB:CC:DD:EE:FF")
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    with patch.object(hass.config_entries, "async_reload", new_callable=AsyncMock):
        saved = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                "scenes": True,
                "video": False,
                "effects": False,
                "reactive": True,
                "advanced": False,
                CONF_PREFIX_EFFECT_NAMES: False,
                CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS: True,
            },
        )
    assert saved["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        CONF_EFFECT_CATEGORIES: ["scenes", "reactive"],
        CONF_PREFIX_EFFECT_NAMES: False,
        CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS: True,
    }


async def test_options_flow_persists_prefix_preference(hass: HomeAssistant):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_MODEL: "H6199"}, unique_id="AA:BB:CC:DD:EE:FF")
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)

    with patch.object(hass.config_entries, "async_reload", new_callable=AsyncMock):
        saved = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                "video": True,
                "scenes": True,
                "effects": False,
                "reactive": False,
                "advanced": False,
                CONF_PREFIX_EFFECT_NAMES: True,
                CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS: False,
            },
        )

    assert saved["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        CONF_EFFECT_CATEGORIES: ["video", "scenes"],
        CONF_PREFIX_EFFECT_NAMES: True,
        CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS: False,
    }
