from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak import BleakError
from homeassistant.const import EntityCategory

from custom_components.ha_govee_led_ble.coordinator_modes import MUSIC_PARAM_SPECS as _MPS
from custom_components.ha_govee_led_ble.h6199_controls import GoveeMusicStyleSelect as MusicStyle
from custom_components.ha_govee_led_ble.h6199_controls import H6199VideoCaptureSelect as E
from custom_components.ha_govee_led_ble.h6199_controls import (
    MusicParamSelect,
    apply_active_music_param,
    async_setup_select_entry,
)
from custom_components.ha_govee_led_ble.protocol import build_video_mode as bv


def test_current_option(mock_h6199_coordinator):
    assert E(mock_h6199_coordinator).current_option == "full"
    mock_h6199_coordinator.video_full_screen = False
    assert E(mock_h6199_coordinator).current_option == "part"


async def test_reapplies(mock_h6199_coordinator):
    (c := mock_h6199_coordinator).video_saturation, c.video_sound_effects, c.video_sound_effects_softness = 70, True, 40
    c.video_mode = "movie"
    await E(c).async_select_option("part")
    assert c.video_full_screen is False
    assert c.video_sound_effects is True
    c.send_command.assert_any_call(
        bv(
            full_screen=False,
            game_mode=False,
            saturation=70,
            sound_effects=True,
            sound_effects_softness=40,
        )
    )


async def test_rollback(mock_h6199_coordinator):
    (c := mock_h6199_coordinator).video_mode = "movie"
    c.send_command = AsyncMock(side_effect=BleakError("timeout"))
    with pytest.raises(BleakError):
        await E(c).async_select_option("part")
    assert c.video_full_screen is True


async def test_setup_select_entry_h617a(mock_coordinator):
    add = MagicMock()
    await async_setup_select_entry(MagicMock(), MagicMock(runtime_data=mock_coordinator), add)
    entities = add.call_args.args[0]
    assert [type(e) for e in entities] == [MusicStyle, MusicParamSelect]
    assert entities[0]._key == "music_style"
    assert entities[1]._key == "music_fountain_direction"


async def test_setup_select_entry_h6199(mock_h6199_coordinator):
    add = MagicMock()
    await async_setup_select_entry(MagicMock(), MagicMock(runtime_data=mock_h6199_coordinator), add)
    entities = add.call_args.args[0]
    assert [type(e) for e in entities] == [E]


def test_music_style_options_and_current(mock_coordinator):
    c = mock_coordinator
    c.music_style = "dynamic"
    select = MusicStyle(c)
    assert select.options == ["dynamic", "calm"]
    assert select._attr_unique_id == "aabbccddeeff_music_style"
    assert select._attr_entity_category is EntityCategory.CONFIG
    assert select.current_option == "dynamic"
    c.music_style = "calm"
    assert select.current_option == "calm"


async def test_music_style_select_routes_to_music_path_when_live(mock_coordinator):
    c = mock_coordinator
    c.is_on, c.music_mode, c.music_style = True, "rhythm", "dynamic"
    await MusicStyle(c).async_select_option("calm")
    assert c.music_style == "calm"
    c.async_select_music_slug.assert_awaited_once_with("rhythm")


async def test_music_style_select_stores_only_when_inactive(mock_coordinator):
    c = mock_coordinator
    c.is_on, c.music_mode, c.music_style = True, "off", "dynamic"
    await MusicStyle(c).async_select_option("calm")
    assert c.music_style == "calm"
    c.async_select_music_slug.assert_not_awaited()


def _fountain_spec():
    return next(s for s in _MPS if s.key == "music_fountain_direction")


async def test_music_param_select_fountain_reapplies_when_active(mock_coordinator):
    c = mock_coordinator
    c.is_on, c.music_mode = True, "fountain"
    ent = MusicParamSelect(c, _fountain_spec())
    assert ent._attr_entity_registry_enabled_default is False
    assert ent.options == ["clockwise", "counterclockwise", "two_way"]
    assert ent.current_option == "clockwise"
    await ent.async_select_option("two_way")
    assert c.music_fountain_direction == "two_way"
    c.async_apply_music_params.assert_awaited_once_with(0x35)


async def test_apply_active_music_param_returns_false_when_mode_inactive(mock_coordinator):
    c = mock_coordinator
    c.is_on, c.music_mode = True, "off"
    assert await apply_active_music_param(c, mode_code=0x35) is False
    c.async_apply_music_params.assert_not_awaited()
