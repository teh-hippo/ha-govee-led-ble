from unittest.mock import AsyncMock, patch

import pytest

from custom_components.ha_govee_led_ble import protocol as proto
from custom_components.ha_govee_led_ble.const import MUSIC_MODE_SLUGS
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_modes import PreModeSnapshot
from custom_components.ha_govee_led_ble.light_services import apply_active_video_mode

_CONFIGURATION_URL = "homeassistant://ha-govee-led-ble/editor/test-entry"


@pytest.fixture
def coord(hass):
    return GoveeBLECoordinator(
        hass,
        "AA:BB:CC:DD:EE:FF",
        "H617A",
        configuration_url=_CONFIGURATION_URL,
    )


@pytest.fixture
def h6199(hass):
    return GoveeBLECoordinator(
        hass,
        "11:22:33:44:55:66",
        "H6199",
        configuration_url=_CONFIGURATION_URL,
    )


def _sent(sc):
    return [call.args[0] for call in sc.await_args_list]


async def test_select_music_slug_sends_power_then_music_and_sets_state(coord):
    coord.is_on, coord.effect = True, "prior effect"
    coord.diy_code = 0xF0
    with patch.object(coord, "send_command", new_callable=AsyncMock) as sc:
        await coord.async_select_music_slug("rhythm")
    assert _sent(sc) == [
        proto.build_power(True),
        proto.build_music_mode_with_color(MUSIC_MODE_SLUGS["rhythm"], sensitivity=99, color=None, calm=False),
    ]
    assert coord.is_on is True
    assert (coord.music_mode, coord.video_mode) == ("rhythm", "off")
    assert coord.effect is None
    assert coord.diy_code is None


async def test_h6199_music_reapply_preserves_fixed_colour(h6199):
    h6199.music_color = (1, 2, 3)
    with patch.object(h6199, "send_command", new_callable=AsyncMock) as sc:
        await h6199.async_select_music_slug("rhythm")
    assert _sent(sc) == [
        proto.build_power(True),
        proto.build_music_mode_with_color(
            MUSIC_MODE_SLUGS["rhythm"],
            sensitivity=h6199.music_sensitivity,
            color=(1, 2, 3),
            calm=False,
        ),
    ]


async def test_entering_music_from_color_temp_captures_color_temp_snapshot(coord):
    coord.is_on, coord.color_temp_kelvin = True, 4000
    with patch.object(coord, "send_command", new_callable=AsyncMock):
        await coord.async_select_music_slug("spectrum")
    assert coord._pre_mode_snapshot == PreModeSnapshot(kind="color_temp", kelvin=4000)


async def test_entering_music_from_rgb_captures_rgb_snapshot(coord):
    coord.is_on, coord.color_temp_kelvin, coord.rgb_color = True, None, (7, 8, 9)
    with patch.object(coord, "send_command", new_callable=AsyncMock):
        await coord.async_select_music_slug("bloom")
    assert coord._pre_mode_snapshot == PreModeSnapshot(kind="rgb", rgb=(7, 8, 9))


async def test_entering_music_from_active_mode_preserves_snapshot(coord):
    coord.is_on, coord.music_mode = True, "rhythm"
    original = PreModeSnapshot(kind="color_temp", kelvin=6000)
    coord._pre_mode_snapshot, coord.color_temp_kelvin = original, 4000
    with patch.object(coord, "send_command", new_callable=AsyncMock):
        await coord.async_select_music_slug("spectrum")
    assert coord._pre_mode_snapshot is original


async def test_music_style_applies_to_rhythm_bloom_and_shiny(coord):
    coord.is_on, coord.music_calm, coord.music_sensitivity = True, True, 80

    # Rhythm carries Dynamic/Calm in the base frame only (no a3 companion).
    with patch.object(coord, "send_command", new_callable=AsyncMock) as sc:
        await coord.async_select_music_slug("rhythm")
    assert _sent(sc) == [
        proto.build_power(True),
        proto.build_music_mode_with_color(MUSIC_MODE_SLUGS["rhythm"], sensitivity=80, color=None, calm=True),
    ]

    # A mode without a style keeps calm out of the base frame and sends no companion.
    with patch.object(coord, "send_command", new_callable=AsyncMock) as sc:
        await coord.async_select_music_slug("hopping")
    assert _sent(sc) == [
        proto.build_power(True),
        proto.build_music_mode_with_color(MUSIC_MODE_SLUGS["hopping"], sensitivity=80, color=None, calm=False),
    ]

    # Shiny sets the base-frame STYLE and its a3 companion [20,21] to the Calm values.
    with patch.object(coord, "send_command", new_callable=AsyncMock) as sc:
        await coord.async_select_music_slug("shiny")
    assert _sent(sc) == [
        proto.build_power(True),
        proto.build_music_mode_with_color(MUSIC_MODE_SLUGS["shiny"], sensitivity=80, color=None, calm=True),
        *proto.build_music_params_a3(0x31, {20: 0x14, 21: 0x46}),
    ]

    # Bloom's Calm companion is [27].
    with patch.object(coord, "send_command", new_callable=AsyncMock) as sc:
        await coord.async_select_music_slug("bloom")
    assert _sent(sc) == [
        proto.build_power(True),
        proto.build_music_mode_with_color(MUSIC_MODE_SLUGS["bloom"], sensitivity=80, color=None, calm=True),
        *proto.build_music_params_a3(0x30, {27: 0x14}),
    ]

    # Dynamic Shiny writes the template's baseline companion values.
    coord.music_calm = False
    with patch.object(coord, "send_command", new_callable=AsyncMock) as sc:
        await coord.async_select_music_slug("shiny")
    assert _sent(sc) == [
        proto.build_power(True),
        proto.build_music_mode_with_color(MUSIC_MODE_SLUGS["shiny"], sensitivity=80, color=None, calm=False),
        *proto.build_music_params_a3(0x31, {20: 0x05, 21: 0x64}),
    ]


@pytest.mark.parametrize(
    ("snapshot", "expected"),
    [
        (PreModeSnapshot(kind="rgb", rgb=(1, 2, 3)), proto.build_color_rgb(1, 2, 3)),
        (PreModeSnapshot(kind="color_temp", kelvin=3500), proto.build_color_temp(3500)),
        (PreModeSnapshot(kind="white", level=42), proto.build_white_brightness(42)),
    ],
)
async def test_restore_pre_mode_re_emits_matching_builder(coord, snapshot, expected):
    coord._pre_mode_snapshot = snapshot
    coord.music_mode, coord.video_mode = "rhythm", "movie"
    coord.effect = "leftover"
    coord.diy_code = 0xF0
    with patch.object(coord, "send_command", new_callable=AsyncMock) as sc:
        await coord.async_restore_pre_mode()
    assert _sent(sc) == [expected]
    assert (coord.music_mode, coord.video_mode) == ("off", "off")
    assert coord.effect is None
    assert coord.diy_code is None


async def test_select_off_routes_to_restore_and_clears_music_mode(coord):
    coord.music_mode = "rhythm"
    coord._pre_mode_snapshot = PreModeSnapshot(kind="color_temp", kelvin=5000)
    with patch.object(coord, "send_command", new_callable=AsyncMock) as sc:
        await coord.async_select_music_slug("off")
    assert _sent(sc) == [proto.build_color_temp(5000)]
    assert coord.music_mode == "off"


async def test_fresh_off_falls_back_to_white_rgb(coord):
    assert coord._pre_mode_snapshot == PreModeSnapshot(kind="rgb", rgb=(255, 255, 255))
    with patch.object(coord, "send_command", new_callable=AsyncMock) as sc:
        await coord.async_select_music_slug("off")
    assert _sent(sc) == [proto.build_color_rgb(255, 255, 255)]
    assert (coord.music_mode, coord.video_mode) == ("off", "off")


async def test_apply_active_video_mode_noop_when_video_off(coord):
    coord.is_on, coord.video_mode = True, "off"
    with patch.object(coord, "send_command", new_callable=AsyncMock) as sc:
        assert await apply_active_video_mode(coord) is False
    assert _sent(sc) == []


async def test_apply_active_video_mode_requires_readback(h6199):
    h6199.is_on, h6199.video_mode = True, "game"
    h6199.video_full_screen = False
    h6199.video_saturation = 63
    h6199.video_sound_effects = True
    h6199.video_sound_effects_softness = 27
    with (
        patch.object(h6199, "send_command", new_callable=AsyncMock) as sc,
        patch.object(h6199, "refresh_state", new_callable=AsyncMock, return_value=True) as refresh,
    ):
        assert await apply_active_video_mode(h6199) is True
    assert _sent(sc) == [proto.build_video_mode(False, True, 63, True, 27)]
    refresh.assert_awaited_once_with(
        expected_on=True,
        expected_video_mode="game",
        expected_video_full_screen=False,
        expected_video_saturation=63,
        expected_video_sound_effects=True,
        expected_video_sound_effects_softness=27,
    )
