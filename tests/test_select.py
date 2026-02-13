"""Tests for H6199 select helper entities."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak import BleakError

from custom_components.govee_ble_lights.coordinator import GoveeBLECoordinator
from custom_components.govee_ble_lights.protocol import build_video_mode
from custom_components.govee_ble_lights.select import H6199VideoCaptureSelect


@pytest.fixture
def mock_h6199_coordinator():
    """Create a mock coordinator for H6199 helpers."""
    coordinator = MagicMock(spec=GoveeBLECoordinator)
    coordinator.address = "11:22:33:44:55:66"
    coordinator.model = "H6199"
    coordinator.is_on = True
    coordinator.effect = "video: movie"
    coordinator.video_saturation = 70
    coordinator.video_full_screen = True
    coordinator.video_sound_effects = True
    coordinator.video_sound_effects_softness = 40
    coordinator.data = {}
    coordinator.send_command = AsyncMock()
    coordinator.async_set_updated_data = MagicMock()
    return coordinator


def test_capture_select_current_option(mock_h6199_coordinator):
    """Test select option maps from coordinator boolean."""
    entity = H6199VideoCaptureSelect(mock_h6199_coordinator)
    assert entity.current_option == "full"
    mock_h6199_coordinator.video_full_screen = False
    assert entity.current_option == "part"


@pytest.mark.asyncio
async def test_capture_select_reapplies_active_video_mode(mock_h6199_coordinator):
    """Test selecting part/full reapplies the active video mode."""
    entity = H6199VideoCaptureSelect(mock_h6199_coordinator)

    await entity.async_select_option("part")

    assert mock_h6199_coordinator.video_full_screen is False
    mock_h6199_coordinator.send_command.assert_called_once_with(
        build_video_mode(
            full_screen=False,
            game_mode=False,
            saturation=70,
            sound_effects=True,
            sound_effects_softness=40,
        )
    )


@pytest.mark.asyncio
async def test_capture_select_rolls_back_on_failure(mock_h6199_coordinator):
    """Test select rolls back state if BLE command fails."""
    mock_h6199_coordinator.send_command = AsyncMock(side_effect=BleakError("timeout"))
    entity = H6199VideoCaptureSelect(mock_h6199_coordinator)

    with pytest.raises(BleakError):
        await entity.async_select_option("part")

    assert mock_h6199_coordinator.video_full_screen is True
