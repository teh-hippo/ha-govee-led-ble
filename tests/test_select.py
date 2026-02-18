"""Tests for H6199 select helper entities."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from bleak import BleakError

from custom_components.govee_ble_lights.protocol import build_video_mode
from custom_components.govee_ble_lights.select import H6199VideoCaptureSelect


def test_capture_select_current_option(mock_h6199_coordinator):
    entity = H6199VideoCaptureSelect(mock_h6199_coordinator)
    assert entity.current_option == "full"
    mock_h6199_coordinator.video_full_screen = False
    assert entity.current_option == "part"


async def test_capture_select_reapplies(mock_h6199_coordinator):
    mock_h6199_coordinator.video_saturation = 70
    mock_h6199_coordinator.video_sound_effects = True
    mock_h6199_coordinator.video_sound_effects_softness = 40
    entity = H6199VideoCaptureSelect(mock_h6199_coordinator)
    await entity.async_select_option("part")
    assert mock_h6199_coordinator.video_full_screen is False
    mock_h6199_coordinator.send_command.assert_called_once_with(
        build_video_mode(
            full_screen=False, game_mode=False, saturation=70, sound_effects=True, sound_effects_softness=40
        )
    )


async def test_capture_select_rollback(mock_h6199_coordinator):
    mock_h6199_coordinator.send_command = AsyncMock(side_effect=BleakError("timeout"))
    entity = H6199VideoCaptureSelect(mock_h6199_coordinator)
    with pytest.raises(BleakError):
        await entity.async_select_option("part")
    assert mock_h6199_coordinator.video_full_screen is True
