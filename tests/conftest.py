"""Fixtures for Govee BLE Lights tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from custom_components.govee_ble_lights.const import DOMAIN, MODEL_PROFILES
from custom_components.govee_ble_lights.coordinator import GoveeBLECoordinator


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def mock_bleak_client():
    client = MagicMock()
    client.is_connected = True
    client.write_gatt_char = AsyncMock()
    client.disconnect = AsyncMock()
    return client


@pytest.fixture
def mock_ble_device():
    device = MagicMock()
    device.address = "AA:BB:CC:DD:EE:FF"
    device.name = "ihoment_H617A_ABCD"
    return device


@pytest.fixture
def mock_config_entry(hass: HomeAssistant):
    entry = MagicMock()
    entry.entry_id = "test_entry"
    return entry


def _make_h6199_coordinator(**overrides) -> MagicMock:
    defaults = dict(
        address="11:22:33:44:55:66",
        model="H6199",
        profile=MODEL_PROFILES["H6199"],
        is_on=True,
        effect="video: movie",
        brightness_pct=100,
        rgb_color=(255, 255, 255),
        color_temp_kelvin=None,
        video_saturation=100,
        video_brightness=100,
        white_brightness=100,
        video_full_screen=True,
        video_sound_effects=False,
        video_sound_effects_softness=0,
        music_sensitivity=100,
        music_color=None,
        data={},
    )
    defaults.update(overrides)
    coordinator = MagicMock(spec=GoveeBLECoordinator)
    for k, v in defaults.items():
        setattr(coordinator, k, v)
    coordinator.send_command = AsyncMock()
    coordinator.send_commands = AsyncMock()
    coordinator.refresh_state = AsyncMock(return_value=True)
    coordinator.async_set_updated_data = MagicMock()
    type(coordinator).device_info = PropertyMock(
        return_value=DeviceInfo(
            identifiers={(DOMAIN, defaults["address"])},
            name=f"Govee {defaults['model']}",
            manufacturer="Govee",
            model=defaults["model"],
        )
    )
    return coordinator


@pytest.fixture
def mock_h6199_coordinator():
    return _make_h6199_coordinator()


@pytest.fixture
def mock_coordinator():
    return _make_h6199_coordinator(
        address="AA:BB:CC:DD:EE:FF",
        model="H617A",
        profile=MODEL_PROFILES["H617A"],
        is_on=False,
        effect=None,
    )
