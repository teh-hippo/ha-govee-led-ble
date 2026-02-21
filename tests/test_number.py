from unittest.mock import AsyncMock

import pytest
from bleak import BleakError

from custom_components.ha_govee_led_ble.number import H6199ParameterNumber as N
from custom_components.ha_govee_led_ble.protocol import build_music_mode_with_color as bmc
from custom_components.ha_govee_led_ble.protocol import build_video_mode as bv


async def test_video_saturation(mock_h6199_coordinator):
    await N(c := mock_h6199_coordinator, key="video_saturation", name="T").async_set_native_value(42)
    assert c.video_saturation == 42
    cmd = bv(full_screen=True, game_mode=False, saturation=42, sound_effects=False, sound_effects_softness=0)
    c.send_command.assert_called_once_with(cmd)


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
