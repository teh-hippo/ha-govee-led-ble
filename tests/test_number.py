"""Tests for H6199 number helper entities."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from bleak import BleakError

from custom_components.govee_ble_lights.number import H6199ParameterNumber
from custom_components.govee_ble_lights.protocol import build_music_mode_with_color, build_video_mode


def _num(coordinator, key, name="Test"):
    return H6199ParameterNumber(coordinator, key=key, name=name)


async def test_video_saturation_applies(mock_h6199_coordinator):
    entity = _num(mock_h6199_coordinator, "video_saturation")
    await entity.async_set_native_value(42)
    assert mock_h6199_coordinator.video_saturation == 42
    mock_h6199_coordinator.send_command.assert_called_once_with(
        build_video_mode(
            full_screen=True, game_mode=False, saturation=42, sound_effects=False, sound_effects_softness=0
        )
    )


async def test_music_sensitivity_applies(mock_h6199_coordinator):
    mock_h6199_coordinator.effect = "music: rolling"
    mock_h6199_coordinator.music_color = (10, 20, 30)
    entity = _num(mock_h6199_coordinator, "music_sensitivity")
    await entity.async_set_native_value(77)
    assert mock_h6199_coordinator.music_sensitivity == 77
    mock_h6199_coordinator.send_command.assert_called_once_with(
        build_music_mode_with_color(0x06, sensitivity=77, color=(10, 20, 30))
    )


async def test_number_rollback_on_failure(mock_h6199_coordinator):
    mock_h6199_coordinator.send_command = AsyncMock(side_effect=BleakError("timeout"))
    entity = _num(mock_h6199_coordinator, "video_saturation")
    with pytest.raises(BleakError):
        await entity.async_set_native_value(20)
    assert mock_h6199_coordinator.video_saturation == 100
