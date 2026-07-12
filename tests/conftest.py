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
        fw_version=None,
        hw_version=None,
        available=True,
        brightness_pct=100,
        rgb_color=(255, 255, 255),
        color_temp_kelvin=None,
        video_saturation=100,
        video_white_balance=None,
        white_brightness=100,
        video_full_screen=True,
        video_sound_effects=False,
        video_sound_effects_softness=0,
        music_sensitivity=100,
        music_calm=False,
        music_color=None,
        music_separation_point=1,
        music_separation_gradient=True,
        music_hopping_brightness=50,
        music_piano_key_count=15,
        music_fountain_direction="clockwise",
        music_daynight_segments=1,
        music_daynight_speed=10,
        segment_colors=[(255, 255, 255)] * 15,
        active_custom_id=None,
        music_mode="off",
        video_mode="off",
        custom_effects={},
        preview_reduce_motion=False,
        data={},
    )
    d |= ov
    c = MagicMock(spec=GoveeBLECoordinator, **d)
    c.send_command = AsyncMock()
    c.refresh_state, c.async_set_updated_data = AsyncMock(return_value=True), MagicMock()
    c.resolve_custom = MagicMock(return_value=None)
    c.is_custom_effect_supported = MagicMock(return_value=True)
    c.custom_effect_display_names = MagicMock(return_value=[])
    c.custom_effect_index = MagicMock(return_value={})
    c.quarantined_custom_effect_index = MagicMock(return_value={})

    def _enter_static_mode() -> None:
        c.effect = c.active_custom_id = None
        c.music_mode = c.video_mode = "off"

    c._enter_static_mode = MagicMock(side_effect=_enter_static_mode)
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
