"""Tests for H6199 number helper entities."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak import BleakError

from custom_components.govee_ble_lights.coordinator import GoveeBLECoordinator
from custom_components.govee_ble_lights.number import H6199ParameterNumber
from custom_components.govee_ble_lights.protocol import (
    build_brightness,
    build_music_mode_with_color,
    build_video_mode,
    build_white_brightness,
)


@pytest.fixture
def mock_h6199_coordinator():
    """Create a mock coordinator for H6199 helpers."""
    coordinator = MagicMock(spec=GoveeBLECoordinator)
    coordinator.address = "11:22:33:44:55:66"
    coordinator.model = "H6199"
    coordinator.is_on = True
    coordinator.effect = "video: movie"
    coordinator.brightness_pct = 100
    coordinator.video_saturation = 100
    coordinator.video_brightness = 100
    coordinator.white_brightness = 100
    coordinator.video_full_screen = True
    coordinator.video_sound_effects = False
    coordinator.video_sound_effects_softness = 0
    coordinator.music_sensitivity = 100
    coordinator.music_color = None
    coordinator.data = {}
    coordinator.send_command = AsyncMock()
    coordinator.async_set_updated_data = MagicMock()
    return coordinator


@pytest.mark.asyncio
async def test_video_saturation_number_applies_to_active_video_mode(mock_h6199_coordinator):
    """Test video saturation helper reapplies active video mode."""
    entity = H6199ParameterNumber(
        mock_h6199_coordinator,
        key="video_saturation",
        name="Video saturation",
        minimum=0,
        maximum=100,
    )

    await entity.async_set_native_value(42)

    assert mock_h6199_coordinator.video_saturation == 42
    mock_h6199_coordinator.send_command.assert_called_once_with(
        build_video_mode(
            full_screen=True,
            game_mode=False,
            saturation=42,
            sound_effects=False,
            sound_effects_softness=0,
        )
    )


@pytest.mark.asyncio
async def test_music_sensitivity_number_applies_to_active_music_mode(mock_h6199_coordinator):
    """Test music sensitivity helper reapplies active music mode."""
    mock_h6199_coordinator.effect = "music: rolling"
    mock_h6199_coordinator.music_color = (10, 20, 30)
    entity = H6199ParameterNumber(
        mock_h6199_coordinator,
        key="music_sensitivity",
        name="Music sensitivity",
        minimum=0,
        maximum=100,
    )

    await entity.async_set_native_value(77)

    assert mock_h6199_coordinator.music_sensitivity == 77
    mock_h6199_coordinator.send_command.assert_called_once_with(
        build_music_mode_with_color(0x06, sensitivity=77, color=(10, 20, 30))
    )


@pytest.mark.asyncio
async def test_video_brightness_number_applies_to_active_video_mode(mock_h6199_coordinator):
    """Test video brightness helper sends brightness while video mode is active."""
    entity = H6199ParameterNumber(
        mock_h6199_coordinator,
        key="video_brightness",
        name="Video brightness",
        minimum=0,
        maximum=100,
    )

    await entity.async_set_native_value(28)

    assert mock_h6199_coordinator.video_brightness == 28
    assert mock_h6199_coordinator.brightness_pct == 28
    mock_h6199_coordinator.send_command.assert_called_once_with(build_brightness(28))


@pytest.mark.asyncio
async def test_white_brightness_number_sends_white_brightness_packet(mock_h6199_coordinator):
    """Test white brightness helper sends the white brightness packet."""
    entity = H6199ParameterNumber(
        mock_h6199_coordinator,
        key="white_brightness",
        name="White brightness",
        minimum=1,
        maximum=100,
    )

    await entity.async_set_native_value(50)

    assert mock_h6199_coordinator.white_brightness == 50
    assert mock_h6199_coordinator.brightness_pct == 100  # does not mirror global brightness
    mock_h6199_coordinator.send_command.assert_called_once_with(build_white_brightness(50))


@pytest.mark.asyncio
async def test_number_rolls_back_on_send_failure(mock_h6199_coordinator):
    """Test helper value rolls back if BLE command fails."""
    mock_h6199_coordinator.send_command = AsyncMock(side_effect=BleakError("timeout"))
    entity = H6199ParameterNumber(
        mock_h6199_coordinator,
        key="video_saturation",
        name="Video saturation",
        minimum=0,
        maximum=100,
    )

    with pytest.raises(BleakError):
        await entity.async_set_native_value(20)

    assert mock_h6199_coordinator.video_saturation == 100
