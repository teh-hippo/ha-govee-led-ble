"""Tests for H6199 switch helper entities."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak import BleakError

from custom_components.govee_ble_lights.coordinator import GoveeBLECoordinator
from custom_components.govee_ble_lights.protocol import build_video_mode
from custom_components.govee_ble_lights.switch import H6199ParameterSwitch


@pytest.fixture
def mock_h6199_coordinator():
    """Create a mock coordinator for H6199 helpers."""
    coordinator = MagicMock(spec=GoveeBLECoordinator)
    coordinator.address = "11:22:33:44:55:66"
    coordinator.model = "H6199"
    coordinator.is_on = True
    coordinator.effect = "video: game"
    coordinator.video_saturation = 80
    coordinator.video_full_screen = True
    coordinator.video_sound_effects = False
    coordinator.video_sound_effects_softness = 25
    coordinator.data = {}
    coordinator.send_command = AsyncMock()
    coordinator.async_set_updated_data = MagicMock()
    return coordinator


async def test_video_sound_effects_switch_reapplies_active_video_mode(mock_h6199_coordinator):
    """Test sound-effects switch reapplies active video mode."""
    entity = H6199ParameterSwitch(
        mock_h6199_coordinator,
        key="video_sound_effects",
        name="Video sound effects",
    )

    await entity.async_turn_on()

    assert mock_h6199_coordinator.video_sound_effects is True
    mock_h6199_coordinator.send_command.assert_called_once_with(
        build_video_mode(
            full_screen=True,
            game_mode=True,
            saturation=80,
            sound_effects=True,
            sound_effects_softness=25,
        )
    )


async def test_switch_rolls_back_on_send_failure(mock_h6199_coordinator):
    """Test helper switch rolls back if BLE command fails."""
    mock_h6199_coordinator.send_command = AsyncMock(side_effect=BleakError("timeout"))
    entity = H6199ParameterSwitch(
        mock_h6199_coordinator,
        key="video_sound_effects",
        name="Video sound effects",
    )

    with pytest.raises(BleakError):
        await entity.async_turn_on()

    assert mock_h6199_coordinator.video_sound_effects is False
