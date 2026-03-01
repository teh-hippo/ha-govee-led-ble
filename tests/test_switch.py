from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak import BleakError

from custom_components.ha_govee_led_ble.h6199_controls import H6199ParameterSwitch as S
from custom_components.ha_govee_led_ble.h6199_controls import async_setup_switch_entry
from custom_components.ha_govee_led_ble.protocol import build_music_mode_with_color as bmc
from custom_components.ha_govee_led_ble.protocol import build_video_mode as bv


async def test_reapplies(mock_h6199_coordinator):
    (c := mock_h6199_coordinator).effect, c.video_saturation, c.video_sound_effects_softness = "video: game", 80, 25
    await S(c, key="video_sound_effects", name="V").async_turn_on()
    assert c.video_sound_effects is True
    c.send_command.assert_any_call(
        bv(full_screen=True, game_mode=True, saturation=80, sound_effects=True, sound_effects_softness=25)
    )


async def test_rollback(mock_h6199_coordinator):
    (c := mock_h6199_coordinator).effect, c.send_command = "video: game", AsyncMock(side_effect=BleakError("timeout"))
    with pytest.raises(BleakError):
        await S(c, key="video_sound_effects", name="V").async_turn_on()
    assert c.video_sound_effects is False


async def test_music_calm_reapplies(mock_h6199_coordinator):
    (c := mock_h6199_coordinator).effect, c.music_sensitivity, c.music_color = "music: rhythm", 88, (1, 2, 3)
    await S(c, key="music_calm", name="M").async_turn_on()
    assert c.music_calm is True
    c.send_command.assert_called_once_with(bmc(0x03, sensitivity=88, color=(1, 2, 3), calm=True))


def test_is_on_reflects_coordinator_value(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    c.music_calm = True
    assert S(c, key="music_calm", name="M").is_on is True
    c.music_calm = False
    assert S(c, key="music_calm", name="M").is_on is False


async def test_music_calm_turn_off_reapplies(mock_h6199_coordinator):
    (c := mock_h6199_coordinator).effect, c.music_sensitivity, c.music_color, c.music_calm = (
        "music: rhythm",
        88,
        (
            1,
            2,
            3,
        ),
        True,
    )
    await S(c, key="music_calm", name="M").async_turn_off()
    assert c.music_calm is False
    c.send_command.assert_called_once_with(bmc(0x03, sensitivity=88, color=(1, 2, 3), calm=False))


async def test_setup_switch_entry_h617a(mock_coordinator):
    add = MagicMock()
    await async_setup_switch_entry(MagicMock(), MagicMock(runtime_data=mock_coordinator), add)
    entities = add.call_args.args[0]
    assert len(entities) == 1 and entities[0]._key == "music_calm"


async def test_setup_switch_entry_h6199(mock_h6199_coordinator):
    add = MagicMock()
    await async_setup_switch_entry(MagicMock(), MagicMock(runtime_data=mock_h6199_coordinator), add)
    keys = [entity._key for entity in add.call_args.args[0]]
    assert keys == ["video_sound_effects", "music_calm"]


async def test_setup_switch_entry_video_only(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    c.profile = replace(c.profile, supports_music_calm=False)
    add = MagicMock()
    await async_setup_switch_entry(MagicMock(), MagicMock(runtime_data=c), add)
    entities = add.call_args.args[0]
    assert len(entities) == 1 and entities[0]._key == "video_sound_effects"


async def test_setup_switch_entry_without_supported_controls(mock_coordinator):
    c = mock_coordinator
    c.profile = replace(c.profile, supports_music_calm=False)
    add = MagicMock()
    await async_setup_switch_entry(MagicMock(), MagicMock(runtime_data=c), add)
    add.assert_not_called()
