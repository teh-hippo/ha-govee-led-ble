from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest
from homeassistant.helpers.device_registry import DeviceInfo

from custom_components.ha_govee_led_ble.const import DOMAIN, MODEL_PROFILES
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def _make_coord(**ov) -> MagicMock:
    d = dict(
        address="11:22:33:44:55:66",
        model="H6199",
        profile=MODEL_PROFILES["H6199"],
        is_on=True,
        effect="video: movie",
        brightness_pct=100,
        rgb_color=(255, 255, 255),
        color_temp_kelvin=None,
        video_saturation=100,
        white_brightness=100,
        video_full_screen=True,
        video_sound_effects=False,
        video_sound_effects_softness=0,
        music_sensitivity=100,
        music_calm=False,
        music_color=None,
        data={},
    )
    d |= ov
    c = MagicMock(spec=GoveeBLECoordinator, **d)
    c.send_command = AsyncMock()
    c.refresh_state, c.async_set_updated_data = AsyncMock(return_value=True), MagicMock()
    type(c).device_info = PropertyMock(
        return_value=DeviceInfo(
            identifiers={(DOMAIN, d["address"])}, name=f"Govee {d['model']}", manufacturer="Govee", model=d["model"]
        )
    )
    return c


@pytest.fixture
def mock_h6199_coordinator():
    return _make_coord()


@pytest.fixture
def mock_coordinator():
    return _make_coord(
        address="AA:BB:CC:DD:EE:FF", model="H617A", profile=MODEL_PROFILES["H617A"], is_on=False, effect=None
    )
