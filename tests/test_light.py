"""Tests for the Govee BLE light entity."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak import BleakError

from custom_components.govee_ble_lights.coordinator import GoveeBLECoordinator
from custom_components.govee_ble_lights.light import GoveeBLELight
from custom_components.govee_ble_lights.protocol import (
    build_brightness,
    build_color_rgb,
    build_power,
    build_scene,
)
from custom_components.govee_ble_lights.scenes import SCENES


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator."""
    coordinator = MagicMock(spec=GoveeBLECoordinator)
    coordinator.address = "AA:BB:CC:DD:EE:FF"
    coordinator.model = "H617A"
    coordinator.is_on = False
    coordinator.brightness_pct = 100
    coordinator.rgb_color = (255, 255, 255)
    coordinator.color_temp_kelvin = None
    coordinator.effect = None
    coordinator.send_command = AsyncMock()
    return coordinator


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    entry = MagicMock()
    entry.entry_id = "test_entry"
    return entry


@pytest.fixture
def light(mock_coordinator, mock_config_entry):
    """Create a light entity for testing."""
    entity = GoveeBLELight(mock_coordinator, mock_config_entry)
    entity.async_write_ha_state = MagicMock()
    return entity


def test_unique_id(light):
    """Test unique ID is derived from address."""
    assert light.unique_id == "aabbccddeeff"


def test_effect_list(light):
    """Test effect list contains all scenes sorted."""
    effects = light.effect_list
    assert len(effects) == len(SCENES)
    assert effects == sorted(SCENES.keys())


def test_is_off_initially(light):
    """Test light starts off."""
    assert light.is_on is False


@pytest.mark.asyncio
async def test_turn_on(light, mock_coordinator):
    """Test turning the light on."""
    await light.async_turn_on()
    mock_coordinator.send_command.assert_called_with(build_power(True))
    assert mock_coordinator.is_on is True


@pytest.mark.asyncio
async def test_turn_off(light, mock_coordinator):
    """Test turning the light off."""
    await light.async_turn_off()
    mock_coordinator.send_command.assert_called_with(build_power(False))
    assert mock_coordinator.is_on is False


@pytest.mark.asyncio
async def test_turn_on_with_brightness(light, mock_coordinator):
    """Test turning on with brightness."""
    await light.async_turn_on(brightness=128)
    calls = mock_coordinator.send_command.call_args_list
    # Should have power on + brightness
    assert len(calls) == 2
    assert calls[0].args[0] == build_power(True)
    assert calls[1].args[0] == build_brightness(50)  # 128/255 * 100 ≈ 50


@pytest.mark.asyncio
async def test_turn_on_with_rgb(light, mock_coordinator):
    """Test turning on with RGB color."""
    await light.async_turn_on(rgb_color=(255, 0, 128))
    calls = mock_coordinator.send_command.call_args_list
    assert len(calls) == 2
    assert calls[1].args[0] == build_color_rgb(255, 0, 128)
    assert mock_coordinator.rgb_color == (255, 0, 128)


@pytest.mark.asyncio
async def test_turn_on_with_effect(light, mock_coordinator):
    """Test turning on with a simple effect."""
    await light.async_turn_on(effect="rainbow")
    calls = mock_coordinator.send_command.call_args_list
    assert len(calls) == 2
    assert calls[1].args[0] == build_scene(SCENES["rainbow"].code)
    assert mock_coordinator.effect == "rainbow"


@pytest.mark.asyncio
async def test_turn_on_with_complex_effect(light, mock_coordinator):
    """Test turning on with a complex multi-packet effect."""
    mock_coordinator.send_commands = AsyncMock()
    await light.async_turn_on(effect="forest")
    # Power on via send_command, then scene via send_commands
    mock_coordinator.send_command.assert_called_once_with(build_power(True))
    mock_coordinator.send_commands.assert_called_once()
    packets = mock_coordinator.send_commands.call_args.args[0]
    assert len(packets) > 1  # multi-packet
    assert packets[0][0] == 0xA3  # first is a3 packet
    assert packets[-1][0] == 0x33  # last is standard command
    assert mock_coordinator.effect == "forest"


def test_brightness_conversion(light, mock_coordinator):
    """Test brightness converts from pct to 0-255."""
    mock_coordinator.brightness_pct = 50
    assert light.brightness == 128


@pytest.mark.asyncio
async def test_turn_on_rollback_on_failure(light, mock_coordinator):
    """Test that state is rolled back when a command fails."""
    mock_coordinator.is_on = False
    mock_coordinator.brightness_pct = 100
    mock_coordinator.rgb_color = (255, 255, 255)
    mock_coordinator.effect = None

    # Fail on the second call (brightness) after power succeeds
    mock_coordinator.send_command = AsyncMock(side_effect=[None, BleakError("connection lost")])

    with pytest.raises(BleakError):
        await light.async_turn_on(brightness=128)

    # State should be rolled back
    assert mock_coordinator.is_on is False
    assert mock_coordinator.brightness_pct == 100


@pytest.mark.asyncio
async def test_turn_off_rollback_on_failure(light, mock_coordinator):
    """Test that state is rolled back when turn_off fails."""
    mock_coordinator.is_on = True
    mock_coordinator.send_command = AsyncMock(side_effect=BleakError("timeout"))

    with pytest.raises(BleakError):
        await light.async_turn_off()

    assert mock_coordinator.is_on is True
