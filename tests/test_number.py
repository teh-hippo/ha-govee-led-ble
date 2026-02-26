from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak import BleakError

from custom_components.ha_govee_led_ble.h6199_controls import H6199ParameterNumber as N
from custom_components.ha_govee_led_ble.h6199_controls import async_setup_number_entry
from custom_components.ha_govee_led_ble.protocol import build_music_mode_with_color as bmc
from custom_components.ha_govee_led_ble.protocol import build_power as bp
from custom_components.ha_govee_led_ble.protocol import build_video_mode as bv
from custom_components.ha_govee_led_ble.protocol import build_video_white_balance as bvw


async def test_video_saturation(mock_h6199_coordinator):
    await N(c := mock_h6199_coordinator, key="video_saturation", name="T").async_set_native_value(42)
    assert c.video_saturation == 42
    c.send_command.assert_any_call(
        bv(full_screen=True, game_mode=False, saturation=42, sound_effects=False, sound_effects_softness=0)
    )


async def test_video_white_balance(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    assert c.video_white_balance is None
    await N(c, key="video_white_balance", name="T").async_set_native_value(100)
    assert c.video_white_balance == 100
    c.send_command.assert_called_once_with(bvw(100))


async def test_video_white_balance_restore(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    entity = N(c, key="video_white_balance", name="T")
    entity.async_get_last_state = AsyncMock(return_value=MagicMock(state="73"))
    await entity._async_restore_value()
    assert c.video_white_balance == 73
    c.async_set_updated_data.assert_called_once_with(c.data)


async def test_video_saturation_powers_on(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    c.is_on, c.effect = False, None
    await N(c, key="video_saturation", name="T").async_set_native_value(58)
    calls = c.send_command.call_args_list
    assert calls[0].args[0] == bp(True)
    assert calls[1].args[0] == bv(
        full_screen=True, game_mode=False, saturation=58, sound_effects=False, sound_effects_softness=0
    )
    assert c.is_on is True and c.effect == "video: movie"


async def test_music_sensitivity(mock_h6199_coordinator):
    (c := mock_h6199_coordinator).effect, c.music_color = "music: rolling", (10, 20, 30)
    await N(c, key="music_sensitivity", name="T").async_set_native_value(77)
    assert c.music_sensitivity == 77
    c.send_command.assert_called_once_with(bmc(0x06, sensitivity=77, color=(10, 20, 30)))


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
        "video_white_balance",
        "video_sound_effects_softness",
        "music_sensitivity",
    ]
