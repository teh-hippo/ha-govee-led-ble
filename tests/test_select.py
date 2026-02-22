from unittest.mock import AsyncMock

import pytest
from bleak import BleakError

from custom_components.ha_govee_led_ble.h6199_controls import H6199VideoCaptureSelect as E
from custom_components.ha_govee_led_ble.protocol import build_brightness as bb
from custom_components.ha_govee_led_ble.protocol import build_video_mode as bv


def test_current_option(mock_h6199_coordinator):
    assert E(mock_h6199_coordinator).current_option == "full"
    mock_h6199_coordinator.video_full_screen = False
    assert E(mock_h6199_coordinator).current_option == "part"


async def test_reapplies(mock_h6199_coordinator):
    (c := mock_h6199_coordinator).video_saturation, c.video_sound_effects, c.video_sound_effects_softness = 70, True, 40
    await E(c).async_select_option("part")
    assert c.video_full_screen is False
    c.send_command.assert_any_call(
        bv(full_screen=False, game_mode=False, saturation=70, sound_effects=True, sound_effects_softness=40)
    )
    c.send_command.assert_any_call(bb(100))


async def test_rollback(mock_h6199_coordinator):
    (c := mock_h6199_coordinator).send_command = AsyncMock(side_effect=BleakError("timeout"))
    with pytest.raises(BleakError):
        await E(c).async_select_option("part")
    assert c.video_full_screen is True
