from unittest.mock import AsyncMock, patch

import pytest

from custom_components.ha_govee_led_ble import protocol as proto
from custom_components.ha_govee_led_ble.const import MUSIC_MODE_SLUGS
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_modes import PreModeSnapshot
from custom_components.ha_govee_led_ble.light_services import apply_active_music_mode, apply_active_video_mode


@pytest.fixture
def coord(hass):
    return GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617A")


def _sent(sc):
    return [call.args[0] for call in sc.await_args_list]


async def test_select_music_slug_sends_power_then_music_and_sets_state(coord):
    coord.is_on, coord.effect, coord.active_custom_id = True, "prior effect", "diy-42"
    with patch.object(coord, "send_command", new_callable=AsyncMock) as sc:
        await coord.async_select_music_slug("rhythm")
    assert _sent(sc) == [
        proto.build_power(True),
        proto.build_music_mode_with_color(MUSIC_MODE_SLUGS["rhythm"], sensitivity=99, color=None, calm=False),
    ]
    assert coord.is_on is True
    assert (coord.music_mode, coord.video_mode) == ("rhythm", "off")
    assert coord.effect is None and coord.active_custom_id is None


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


async def test_music_calm_style_only_applies_to_rhythm(coord):
    coord.is_on, coord.music_calm, coord.music_sensitivity = True, True, 80
    with patch.object(coord, "send_command", new_callable=AsyncMock) as sc:
        await coord.async_select_music_slug("rhythm")
    assert _sent(sc)[-1] == proto.build_music_mode_with_color(
        MUSIC_MODE_SLUGS["rhythm"], sensitivity=80, color=None, calm=True
    )
    with patch.object(coord, "send_command", new_callable=AsyncMock) as sc:
        await coord.async_select_music_slug("hopping")
    assert _sent(sc)[-1] == proto.build_music_mode_with_color(
        MUSIC_MODE_SLUGS["hopping"], sensitivity=80, color=None, calm=False
    )


def test_music_style_reconciles_calm_bool(coord):
    """The ``music_style`` select surface is a Dynamic/Calm view over the ``music_calm`` bool (§2.1)."""
    coord.music_calm = False
    assert coord.music_style == "dynamic"
    coord.music_calm = True
    assert coord.music_style == "calm"
    coord.music_style = "dynamic"
    assert coord.music_calm is False
    coord.music_style = "calm"
    assert coord.music_calm is True


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
    coord.effect, coord.active_custom_id = "leftover", "diy-1"
    with patch.object(coord, "send_command", new_callable=AsyncMock) as sc:
        await coord.async_restore_pre_mode()
    assert _sent(sc) == [expected]
    assert (coord.music_mode, coord.video_mode) == ("off", "off")
    assert coord.effect is None and coord.active_custom_id is None


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


async def test_apply_active_music_mode_reapplies_from_music_mode(coord):
    """A param tweak while music is live re-sends the music frame via the single music-apply path."""
    coord.is_on, coord.music_mode, coord.music_sensitivity = True, "spectrum", 66
    with patch.object(coord, "send_command", new_callable=AsyncMock) as sc:
        assert await apply_active_music_mode(coord) is True
    assert _sent(sc) == [
        proto.build_power(True),
        proto.build_music_mode_with_color(MUSIC_MODE_SLUGS["spectrum"], sensitivity=66, color=None, calm=False),
    ]


async def test_apply_active_music_mode_noop_when_music_off(coord):
    coord.is_on, coord.music_mode = True, "off"
    with patch.object(coord, "send_command", new_callable=AsyncMock) as sc:
        assert await apply_active_music_mode(coord) is False
    assert _sent(sc) == []


async def test_apply_active_video_mode_noop_when_video_off(coord):
    coord.is_on, coord.video_mode = True, "off"
    with patch.object(coord, "send_command", new_callable=AsyncMock) as sc:
        assert await apply_active_video_mode(coord) is False
    assert _sent(sc) == []


async def test_apply_music_params_merges_all_params_for_mode(coord):
    """A per-mode apply merges every stored param so a sibling param is never clobbered (§2.3)."""
    coord.music_separation_point, coord.music_separation_gradient = 5, False
    with patch.object(coord, "send_command", new_callable=AsyncMock) as sc:
        await coord.async_apply_music_params(0x32)
    assert _sent(sc) == proto.build_music_params_a3(0x32, {20: 5, 21: 0})


async def test_apply_music_params_encodes_fountain_direction(coord):
    coord.music_fountain_direction = "counterclockwise"
    with patch.object(coord, "send_command", new_callable=AsyncMock) as sc:
        await coord.async_apply_music_params(0x35)
    assert _sent(sc) == proto.build_music_params_a3(0x35, {28: 0x03})
