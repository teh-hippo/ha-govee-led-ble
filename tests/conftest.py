import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest
from homeassistant.helpers.device_registry import DeviceInfo

from custom_components.ha_govee_led_ble.const import (
    DOMAIN,
    MODEL_PROFILES,
    default_effect_categories,
    default_effect_families,
)
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode
from custom_components.ha_govee_led_ble.h6199_calibration import WHITE_BALANCE_RESET
from custom_components.ha_govee_led_ble.scenes import MODEL_SCENES


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
        white_brightness=100,
        video_full_screen=True,
        video_sound_effects=False,
        video_sound_effects_softness=100,
        white_balance_red=None,
        white_balance_blue=None,
        subordinate_20_version=None,
        subordinate_21_version=None,
        white_balance=WHITE_BALANCE_RESET,
        relative_brightness=None,
        relative_brightness_left=None,
        relative_brightness_top=None,
        relative_brightness_right=None,
        relative_brightness_bottom=None,
        blank_screen=None,
        blank_screen_detection=2,
        blank_screen_low_brightness_duration_seconds=10,
        blank_screen_same_tone_duration_seconds=120,
        music_sensitivity=100,
        music_calm=False,
        music_color=None,
        segment_colors=[(255, 255, 255)] * 15,
        segment_brightness=[100] * 15,
        segment_state_source="initial",
        segment_state_observed_at=None,
        diy_code=None,
        color_mode=None,
        music_mode="off",
        video_mode="off",
        data={},
    )
    d |= ov
    model = d["model"]
    assert isinstance(model, str)
    d.setdefault("effect_families", default_effect_families(model))
    d.setdefault("effect_categories", frozenset(default_effect_categories(model)))
    d.setdefault("prefix_effect_names", False)
    d.setdefault("always_include_custom_effects", False)
    effect_families = d["effect_families"]
    assert isinstance(effect_families, frozenset)
    d.setdefault(
        "scene_name_set",
        frozenset(MODEL_SCENES[model]) if "scenes" in effect_families else frozenset(),
    )
    c = MagicMock(spec=GoveeBLECoordinator, **d)
    c.send_command = AsyncMock()
    c.async_paint_segments = AsyncMock()
    c.async_set_segment_brightness = AsyncMock()
    c.async_refresh_segments = AsyncMock(return_value=True)

    def mark_segment_state_optimistic(*, colours=None, brightness=None) -> None:
        if colours is not None:
            c.segment_colors = colours
        if brightness is not None:
            c.segment_brightness = brightness
        c.segment_state_source = "optimistic"
        c.segment_state_observed_at = None

    def mark_segment_state_restored(colours, brightness) -> None:
        c.segment_colors = colours
        c.segment_brightness = brightness
        c.segment_state_source = "restored"
        c.segment_state_observed_at = None

    c.mark_segment_state_optimistic = MagicMock(side_effect=mark_segment_state_optimistic)
    c.mark_segment_state_restored = MagicMock(side_effect=mark_segment_state_restored)
    c._control_lock = asyncio.Lock()
    c.refresh_state, c.async_set_updated_data = AsyncMock(return_value=True), MagicMock()
    c.unknown_scene_code = None

    async def write_effect_sequence(packets, **_kwargs) -> None:
        for packet in packets:
            await c.send_command(packet)

    c.async_write_effect_sequence = AsyncMock(side_effect=write_effect_sequence)

    async def _apply_native_scene_locked(*args, **kwargs) -> None:
        await GoveeBLECoordinator._async_apply_native_scene_locked(c, *args, **kwargs)

    c._async_apply_native_scene_locked = AsyncMock(side_effect=_apply_native_scene_locked)

    def _enter_static_mode() -> None:
        c.color_mode = ParsedMode.COLOUR
        c._scene_code = None
        c.unknown_scene_code = None
        c.effect = None
        c.diy_code = None
        c.music_mode = c.video_mode = "off"

    c._enter_static_mode = MagicMock(side_effect=_enter_static_mode)
    type(c).device_info = PropertyMock(
        return_value=DeviceInfo(
            identifiers={(DOMAIN, d["address"])},
            name=f"Govee {d['model']}",
            manufacturer="Govee",
            model=d["model"],
            configuration_url="homeassistant://ha-govee-led-ble/editor/test-entry",
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
