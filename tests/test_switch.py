"""Tests for H6199 switch helper entities."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from bleak import BleakError

from custom_components.govee_ble_lights.protocol import build_video_mode
from custom_components.govee_ble_lights.switch import H6199ParameterSwitch


async def test_sound_effects_switch_reapplies(mock_h6199_coordinator):
    mock_h6199_coordinator.effect = "video: game"
    mock_h6199_coordinator.video_saturation = 80
    mock_h6199_coordinator.video_sound_effects_softness = 25
    entity = H6199ParameterSwitch(mock_h6199_coordinator, key="video_sound_effects", name="Video sound effects")
    await entity.async_turn_on()
    assert mock_h6199_coordinator.video_sound_effects is True
    mock_h6199_coordinator.send_command.assert_called_once_with(
        build_video_mode(full_screen=True, game_mode=True, saturation=80, sound_effects=True, sound_effects_softness=25)
    )


async def test_switch_rollback_on_failure(mock_h6199_coordinator):
    mock_h6199_coordinator.effect = "video: game"
    mock_h6199_coordinator.send_command = AsyncMock(side_effect=BleakError("timeout"))
    entity = H6199ParameterSwitch(mock_h6199_coordinator, key="video_sound_effects", name="Video sound effects")
    with pytest.raises(BleakError):
        await entity.async_turn_on()
    assert mock_h6199_coordinator.video_sound_effects is False
