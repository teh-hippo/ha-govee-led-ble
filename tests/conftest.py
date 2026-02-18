"""Fixtures for Govee BLE Lights tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for all tests."""
    yield


@pytest.fixture
def mock_bleak_client():
    """Return a mock BleakClient."""
    client = MagicMock()
    client.is_connected = True
    client.write_gatt_char = AsyncMock()
    client.disconnect = AsyncMock()
    return client


@pytest.fixture
def mock_ble_device():
    """Return a mock BLE device."""
    device = MagicMock()
    device.address = "AA:BB:CC:DD:EE:FF"
    device.name = "ihoment_H617A_ABCD"
    return device


@pytest.fixture
def mock_config_entry(hass: HomeAssistant):
    """Return a mock config entry registered with hass."""
    entry = MagicMock()
    entry.entry_id = "test_entry"
    return entry
