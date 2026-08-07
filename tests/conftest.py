import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest
from homeassistant.helpers.device_registry import DeviceInfo

from custom_components.ha_govee_led_ble.const import DOMAIN, MODEL_PROFILES, default_effect_families
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.protocol import WHITE_BALANCE_RESET
from custom_components.ha_govee_led_ble.scenes import MODEL_SCENES

_IDENTITY_EXAMPLE = Path(__file__).parents[1] / "tools" / "harness" / "devices.local.env.example"


@pytest.fixture(autouse=True)
def harness_identity(monkeypatch):
    """Point the harness at the committed example, so no test needs a real rig identity.

    devices.env refuses to load without an identity file, so without this every test that
    shells into the harness passes on a machine that happens to have a devices.local.env and
    fails on a fresh clone and in CI. Using the shipped example rather than a fabricated temp
    file also means the example cannot rot: if it stops being loadable, these tests say so.
    """
    monkeypatch.setenv("HARNESS_IDENTITY_FILE", str(_IDENTITY_EXAMPLE))


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
        white_balance=WHITE_BALANCE_RESET,
        relative_brightness=None,
        relative_brightness_left=None,
        relative_brightness_top=None,
        relative_brightness_right=None,
        relative_brightness_bottom=None,
        blank_screen=None,
        music_sensitivity=100,
        music_calm=False,
        music_color=None,
        segment_colors=[(255, 255, 255)] * 15,
        diy_slot=None,
        color_mode=None,
        scene_speed_scene_code=None,
        scene_speed_index=None,
        music_mode="off",
        video_mode="off",
        data={},
    )
    d |= ov
    model = d["model"]
    assert isinstance(model, str)
    d.setdefault("effect_families", default_effect_families(model))
    effect_families = d["effect_families"]
    assert isinstance(effect_families, frozenset)
    d.setdefault(
        "scene_name_set",
        frozenset(MODEL_SCENES[model]) if "scenes" in effect_families else frozenset(),
    )
    c = MagicMock(spec=GoveeBLECoordinator, **d)
    c.send_command = AsyncMock()
    c._control_lock = asyncio.Lock()
    c.refresh_state, c.async_set_updated_data = AsyncMock(return_value=True), MagicMock()
    c.unknown_scene_code = None

    def _enter_static_mode() -> None:
        c.effect = None
        c.diy_slot = None
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
