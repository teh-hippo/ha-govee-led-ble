from unittest.mock import AsyncMock

import pytest
from bleak import BleakError

from custom_components.ha_govee_led_ble.h6199_controls import H6199ParameterSwitch as S
from custom_components.ha_govee_led_ble.protocol import build_video_mode as bv


async def test_reapplies(mock_h6199_coordinator):
    (c := mock_h6199_coordinator).effect, c.video_saturation, c.video_sound_effects_softness = "video: game", 80, 25
    await S(c, key="video_sound_effects", name="V").async_turn_on()
    assert c.video_sound_effects is True
    cmd = bv(full_screen=True, game_mode=True, saturation=80, sound_effects=True, sound_effects_softness=25)
    c.send_command.assert_called_once_with(cmd)


async def test_rollback(mock_h6199_coordinator):
    (c := mock_h6199_coordinator).effect, c.send_command = "video: game", AsyncMock(side_effect=BleakError("timeout"))
    with pytest.raises(BleakError):
        await S(c, key="video_sound_effects", name="V").async_turn_on()
    assert c.video_sound_effects is False
