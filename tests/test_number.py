from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak import BleakError

from custom_components.ha_govee_led_ble.h6199_controls import H6199ParameterNumber as N
from custom_components.ha_govee_led_ble.h6199_controls import async_setup_number_entry
from custom_components.ha_govee_led_ble.protocol import build_music_mode_with_color as bmc
from custom_components.ha_govee_led_ble.protocol import build_video_mode as bv
from custom_components.ha_govee_led_ble.protocol import build_white_brightness as bw


async def test_video_saturation(mock_h6199_coordinator):
    await N(c := mock_h6199_coordinator, key="video_saturation", name="T").async_set_native_value(42)
    assert c.video_saturation == 42
    c.send_command.assert_any_call(
        bv(full_screen=True, game_mode=False, saturation=42, sound_effects=False, sound_effects_softness=0)
    )


async def test_music_sensitivity(mock_h6199_coordinator):
    (c := mock_h6199_coordinator).effect, c.music_color = "music: rolling", (10, 20, 30)
    await N(c, key="music_sensitivity", name="T").async_set_native_value(77)
    assert c.music_sensitivity == 77
    c.send_command.assert_called_once_with(bmc(0x06, sensitivity=77, color=(10, 20, 30)))


async def test_white_brightness(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    c.effect = None
    await N(c, key="white_brightness", name="T").async_set_native_value(36)
    assert c.white_brightness == 36 and c.brightness_pct == 36
    c.send_command.assert_called_once_with(bw(36))


async def test_rollback(mock_h6199_coordinator):
    (c := mock_h6199_coordinator).send_command = AsyncMock(side_effect=BleakError("timeout"))
    with pytest.raises(BleakError):
        await N(c, key="video_saturation", name="T").async_set_native_value(20)
    assert c.video_saturation == 100


async def test_setup_number_entry_h617a(mock_coordinator):
    add = MagicMock()
    await async_setup_number_entry(MagicMock(), MagicMock(runtime_data=mock_coordinator), add)
    entities = add.call_args.args[0]
    assert len(entities) == 1 and entities[0]._key == "music_sensitivity"


async def test_setup_number_entry_h6199(mock_h6199_coordinator):
    add = MagicMock()
    await async_setup_number_entry(MagicMock(), MagicMock(runtime_data=mock_h6199_coordinator), add)
    keys = [entity._key for entity in add.call_args.args[0]]
    assert keys == [
        "video_saturation",
        "video_sound_effects_softness",
        "music_sensitivity",
        "white_brightness",
    ]
