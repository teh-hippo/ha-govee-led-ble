"""Tests for the Govee BLE Lights config flow."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant import config_entries
from homeassistant.components.bluetooth import BluetoothServiceInfo
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.govee_ble_lights.const import CONF_MODEL, DOMAIN

GOVEE_SERVICE_INFO = BluetoothServiceInfo(
    name="ihoment_H617A_ABCD",
    address="AA:BB:CC:DD:EE:FF",
    rssi=-60,
    manufacturer_data={},
    service_data={},
    service_uuids=[],
    source="local",
)


@pytest.fixture(autouse=True)
async def mock_bluetooth(hass, enable_custom_integrations):
    hass.config.components.add("bluetooth")
    hass.config.components.add("bluetooth_adapters")


async def test_bluetooth_discovery(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=GOVEE_SERVICE_INFO,
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "ihoment_H617A_ABCD"
    assert result["data"][CONF_MODEL] == "H617A"


async def test_bluetooth_discovery_abort_duplicate(hass: HomeAssistant) -> None:
    entry = MagicMock(spec=config_entries.ConfigEntry)
    entry.unique_id = "AA:BB:CC:DD:EE:FF"
    entry.domain = DOMAIN

    # First discovery
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=GOVEE_SERVICE_INFO,
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY

    result2 = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=GOVEE_SERVICE_INFO,
    )
    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "already_configured"


async def test_user_step_shows_form(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_user_step_creates_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_MODEL: "H617A",
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Govee H617A"
    assert result["data"][CONF_MODEL] == "H617A"


@pytest.mark.parametrize(
    "name,expected",
    [
        ("SomeOtherDevice", None),
        ("Govee_H9999_ABCD", None),
        ("", None),
        ("ihoment_H617A_ABCD", "H617A"),
        ("Govee_H617A_ABCD", "H617A"),
        ("GBK_H617A_ABCD", "H617A"),
        ("GVH_H617A_ABCD", "H617A"),
    ],
)
def test_extract_model(name, expected):
    from custom_components.govee_ble_lights.config_flow import _extract_model

    assert _extract_model(name) == expected
