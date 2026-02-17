"""Tests for the Govee BLE light entity."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak import BleakError
from homeassistant.components.light import ColorMode
from homeassistant.exceptions import ServiceValidationError

from custom_components.govee_ble_lights.const import MODEL_PROFILES
from custom_components.govee_ble_lights.coordinator import GoveeBLECoordinator
from custom_components.govee_ble_lights.light import GoveeBLELight, _build_effect_list
from custom_components.govee_ble_lights.protocol import (
    build_brightness,
    build_color_rgb,
    build_music_mode_with_color,
    build_power,
    build_scene,
    build_video_mode,
)
from custom_components.govee_ble_lights.scenes import SCENES


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator for H617A."""
    coordinator = MagicMock(spec=GoveeBLECoordinator)
    coordinator.address = "AA:BB:CC:DD:EE:FF"
    coordinator.model = "H617A"
    coordinator.profile = MODEL_PROFILES["H617A"]
    coordinator.is_on = False
    coordinator.brightness_pct = 100
    coordinator.rgb_color = (255, 255, 255)
    coordinator.color_temp_kelvin = None
    coordinator.effect = None
    coordinator.send_command = AsyncMock()
    return coordinator


@pytest.fixture
def mock_h6199_coordinator():
    """Create a mock coordinator for H6199."""
    coordinator = MagicMock(spec=GoveeBLECoordinator)
    coordinator.address = "11:22:33:44:55:66"
    coordinator.model = "H6199"
    coordinator.profile = MODEL_PROFILES["H6199"]
    coordinator.is_on = False
    coordinator.brightness_pct = 100
    coordinator.rgb_color = (255, 255, 255)
    coordinator.color_temp_kelvin = None
    coordinator.effect = None
    coordinator.video_saturation = 100
    coordinator.video_brightness = 100
    coordinator.video_full_screen = True
    coordinator.video_sound_effects = False
    coordinator.video_sound_effects_softness = 0
    coordinator.music_sensitivity = 100
    coordinator.music_color = None
    coordinator.send_command = AsyncMock()
    coordinator.send_commands = AsyncMock()
    coordinator.refresh_state = AsyncMock(return_value=True)
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


def test_rgb_color_returns_tuple_in_rgb_mode(light, mock_coordinator):
    """Test rgb_color property returns color when in RGB mode."""
    mock_coordinator.rgb_color = (128, 64, 32)
    light._attr_color_mode = ColorMode.RGB
    assert light.rgb_color == (128, 64, 32)


def test_rgb_color_returns_none_in_color_temp_mode(light, mock_coordinator):
    """Test rgb_color returns None when not in RGB mode."""
    light._attr_color_mode = ColorMode.COLOR_TEMP
    assert light.rgb_color is None


def test_color_temp_kelvin_returns_value_in_temp_mode(light, mock_coordinator):
    """Test color_temp_kelvin returns value when in COLOR_TEMP mode."""
    mock_coordinator.color_temp_kelvin = 4000
    light._attr_color_mode = ColorMode.COLOR_TEMP
    assert light.color_temp_kelvin == 4000


def test_color_temp_kelvin_returns_none_in_rgb_mode(light, mock_coordinator):
    """Test color_temp_kelvin returns None when not in COLOR_TEMP mode."""
    mock_coordinator.color_temp_kelvin = 4000
    light._attr_color_mode = ColorMode.RGB
    assert light.color_temp_kelvin is None


def test_effect_property(light, mock_coordinator):
    """Test effect property reflects coordinator state."""
    mock_coordinator.effect = "rainbow"
    assert light.effect == "rainbow"


def test_effect_property_none(light, mock_coordinator):
    """Test effect property returns None when no effect active."""
    mock_coordinator.effect = None
    assert light.effect is None


@pytest.mark.asyncio
async def test_turn_on_with_color_temp(light, mock_coordinator):
    """Test turning on with color temperature."""
    from custom_components.govee_ble_lights.protocol import build_color_temp

    await light.async_turn_on(color_temp_kelvin=4000)
    calls = mock_coordinator.send_command.call_args_list
    assert len(calls) == 2
    assert calls[1].args[0] == build_color_temp(4000)
    assert mock_coordinator.color_temp_kelvin == 4000
    assert light._attr_color_mode == ColorMode.COLOR_TEMP


@pytest.mark.asyncio
async def test_turn_on_color_temp_clears_effect(light, mock_coordinator):
    """Test color temp clears any active effect."""
    mock_coordinator.effect = "rainbow"
    await light.async_turn_on(color_temp_kelvin=5000)
    assert mock_coordinator.effect is None


# --- H6199-specific tests ---


@pytest.fixture
def h6199_light(mock_h6199_coordinator, mock_config_entry):
    """Create an H6199 light entity for testing."""
    entity = GoveeBLELight(mock_h6199_coordinator, mock_config_entry)
    entity.async_write_ha_state = MagicMock()
    return entity


def test_h6199_effect_list(h6199_light):
    """Test H6199 effect list contains video + music modes (no scenes)."""
    effects = h6199_light.effect_list
    assert "video: movie" in effects
    assert "video: game" in effects
    assert "music: energic" in effects
    assert "music: rhythm" in effects
    assert "music: spectrum" in effects
    assert "music: rolling" in effects
    # No scenes — H6199 has scene_source="none"
    assert "rainbow" not in effects


def test_h617a_effect_list_has_scenes(light):
    """Test H617A effect list contains scenes (no video/music modes)."""
    effects = light.effect_list
    assert "rainbow" in effects
    assert "video: movie" not in effects


def test_build_effect_list_api_model():
    """Test _build_effect_list includes scenes for api source models."""
    effects = _build_effect_list(MODEL_PROFILES["H617A"])
    assert len(effects) == len(SCENES)


def test_build_effect_list_none_model():
    """Test _build_effect_list uses profile effects for non-api models."""
    effects = _build_effect_list(MODEL_PROFILES["H6199"])
    assert len(effects) == len(MODEL_PROFILES["H6199"].effects)


@pytest.mark.asyncio
async def test_h6199_video_movie(h6199_light, mock_h6199_coordinator):
    """Test H6199 video: movie effect sends video mode command."""
    await h6199_light.async_turn_on(effect="video: movie")
    calls = mock_h6199_coordinator.send_command.call_args_list
    assert len(calls) == 3  # power + video mode + brightness
    assert calls[1].args[0] == build_video_mode(full_screen=True, game_mode=False)
    assert calls[2].args[0] == build_brightness(100)
    assert mock_h6199_coordinator.effect == "video: movie"


@pytest.mark.asyncio
async def test_h6199_turn_on_confirms_power_state(h6199_light, mock_h6199_coordinator):
    """Test H6199 turn_on confirms power state via refresh."""
    await h6199_light.async_turn_on()
    mock_h6199_coordinator.refresh_state.assert_awaited_once_with(expected_effect=None, expected_on=True)


@pytest.mark.asyncio
async def test_h6199_turn_off_confirms_power_state(h6199_light, mock_h6199_coordinator):
    """Test H6199 turn_off confirms power state via refresh."""
    await h6199_light.async_turn_off()
    mock_h6199_coordinator.refresh_state.assert_awaited_once_with(expected_effect=None, expected_on=False)


@pytest.mark.asyncio
async def test_h6199_video_game(h6199_light, mock_h6199_coordinator):
    """Test H6199 video: game effect sends game mode command."""
    await h6199_light.async_turn_on(effect="video: game")
    calls = mock_h6199_coordinator.send_command.call_args_list
    assert calls[1].args[0] == build_video_mode(full_screen=True, game_mode=True)
    assert calls[2].args[0] == build_brightness(100)
    assert mock_h6199_coordinator.effect == "video: game"


@pytest.mark.asyncio
async def test_h6199_music_energic(h6199_light, mock_h6199_coordinator):
    """Test H6199 music: energic effect sends music mode command."""
    await h6199_light.async_turn_on(effect="music: energic")
    calls = mock_h6199_coordinator.send_command.call_args_list
    assert calls[1].args[0] == build_music_mode_with_color(0x05)
    assert mock_h6199_coordinator.effect == "music: energic"


@pytest.mark.asyncio
async def test_h6199_music_rhythm(h6199_light, mock_h6199_coordinator):
    """Test H6199 music: rhythm effect."""
    await h6199_light.async_turn_on(effect="music: rhythm")
    calls = mock_h6199_coordinator.send_command.call_args_list
    assert calls[1].args[0] == build_music_mode_with_color(0x03)


@pytest.mark.asyncio
async def test_h6199_music_spectrum(h6199_light, mock_h6199_coordinator):
    """Test H6199 music: spectrum effect."""
    await h6199_light.async_turn_on(effect="music: spectrum")
    calls = mock_h6199_coordinator.send_command.call_args_list
    assert calls[1].args[0] == build_music_mode_with_color(0x04)


@pytest.mark.asyncio
async def test_h6199_music_rolling(h6199_light, mock_h6199_coordinator):
    """Test H6199 music: rolling effect."""
    await h6199_light.async_turn_on(effect="music: rolling")
    calls = mock_h6199_coordinator.send_command.call_args_list
    assert calls[1].args[0] == build_music_mode_with_color(0x06)


@pytest.mark.asyncio
async def test_h6199_video_effect_uses_stored_parameters(h6199_light, mock_h6199_coordinator):
    """Test effect dropdown uses current coordinator video parameter values."""
    mock_h6199_coordinator.video_saturation = 42
    mock_h6199_coordinator.video_brightness = 37
    mock_h6199_coordinator.video_full_screen = False
    mock_h6199_coordinator.video_sound_effects = True
    mock_h6199_coordinator.video_sound_effects_softness = 55

    await h6199_light.async_turn_on(effect="video: game")

    calls = mock_h6199_coordinator.send_command.call_args_list
    assert calls[1].args[0] == build_video_mode(
        full_screen=False,
        game_mode=True,
        saturation=42,
        sound_effects=True,
        sound_effects_softness=55,
    )
    assert calls[2].args[0] == build_brightness(37)


@pytest.mark.asyncio
async def test_h6199_music_effect_uses_stored_parameters(h6199_light, mock_h6199_coordinator):
    """Test effect dropdown uses current coordinator music parameter values."""
    mock_h6199_coordinator.music_sensitivity = 33
    mock_h6199_coordinator.music_color = (10, 20, 30)

    await h6199_light.async_turn_on(effect="music: spectrum")

    calls = mock_h6199_coordinator.send_command.call_args_list
    assert calls[1].args[0] == build_music_mode_with_color(
        0x04,
        sensitivity=33,
        color=(10, 20, 30),
    )


@pytest.mark.asyncio
async def test_h6199_unknown_effect_ignored(h6199_light, mock_h6199_coordinator):
    """Test H6199 unrecognized effect name doesn't set effect."""
    await h6199_light.async_turn_on(effect="nonexistent_effect")
    # Only power command, no effect command
    assert mock_h6199_coordinator.send_command.call_count == 1
    assert mock_h6199_coordinator.effect is None


@pytest.mark.asyncio
async def test_h6199_rgb_still_works(h6199_light, mock_h6199_coordinator):
    """Test H6199 supports RGB color just like H617A."""
    await h6199_light.async_turn_on(rgb_color=(255, 0, 0))
    calls = mock_h6199_coordinator.send_command.call_args_list
    assert len(calls) == 2
    assert calls[1].args[0] == build_color_rgb(255, 0, 0)


@pytest.mark.asyncio
async def test_h6199_brightness_still_works(h6199_light, mock_h6199_coordinator):
    """Test H6199 supports brightness just like H617A."""
    await h6199_light.async_turn_on(brightness=200)
    calls = mock_h6199_coordinator.send_command.call_args_list
    assert len(calls) == 2
    assert calls[1].args[0] == build_brightness(78)  # 200/255 * 100 ≈ 78


def test_h6199_unique_id(h6199_light):
    """Test H6199 unique ID derived from its address."""
    assert h6199_light.unique_id == "112233445566"


def test_h6199_device_info(h6199_light):
    """Test H6199 device info reports correct model."""
    info = h6199_light.device_info
    assert info["model"] == "H6199"
    assert "Govee H6199" in info["name"]


# --- H6199 service handler tests ---


@pytest.mark.asyncio
async def test_set_video_mode_movie(h6199_light, mock_h6199_coordinator):
    """Test set_video_mode service with movie mode."""
    await h6199_light.async_set_video_mode(mode="movie", saturation=80, brightness=65)
    calls = mock_h6199_coordinator.send_command.call_args_list
    assert len(calls) == 3  # power + video mode + brightness
    assert calls[0].args[0] == build_power(True)
    assert calls[1].args[0] == build_video_mode(
        full_screen=True,
        game_mode=False,
        saturation=80,
    )
    assert calls[2].args[0] == build_brightness(65)
    assert mock_h6199_coordinator.effect == "video: movie"
    assert mock_h6199_coordinator.video_saturation == 80
    assert mock_h6199_coordinator.video_brightness == 65


@pytest.mark.asyncio
async def test_set_video_mode_game_with_sound(h6199_light, mock_h6199_coordinator):
    """Test set_video_mode with game mode and sound effects."""
    await h6199_light.async_set_video_mode(
        mode="game",
        saturation=60,
        brightness=75,
        full_screen=False,
        sound_effects=True,
        sound_effects_softness=50,
    )
    calls = mock_h6199_coordinator.send_command.call_args_list
    assert calls[1].args[0] == build_video_mode(
        full_screen=False,
        game_mode=True,
        saturation=60,
        sound_effects=True,
        sound_effects_softness=50,
    )
    assert calls[2].args[0] == build_brightness(75)
    assert mock_h6199_coordinator.effect == "video: game"
    assert mock_h6199_coordinator.video_sound_effects is True
    assert mock_h6199_coordinator.video_sound_effects_softness == 50


@pytest.mark.asyncio
async def test_set_video_mode_updates_state(h6199_light, mock_h6199_coordinator):
    """Test set_video_mode updates coordinator state fields."""
    await h6199_light.async_set_video_mode(mode="movie", saturation=42, brightness=33, full_screen=False)
    assert mock_h6199_coordinator.is_on is True
    assert mock_h6199_coordinator.video_full_screen is False
    assert mock_h6199_coordinator.video_saturation == 42
    assert mock_h6199_coordinator.video_brightness == 33
    assert mock_h6199_coordinator.brightness_pct == 33
    h6199_light.async_write_ha_state.assert_called_once()


@pytest.mark.asyncio
async def test_set_video_mode_capture_region_overrides_full_screen(h6199_light, mock_h6199_coordinator):
    """Test capture_region field takes precedence over full_screen boolean."""
    await h6199_light.async_set_video_mode(
        mode="movie",
        saturation=50,
        brightness=60,
        full_screen=True,
        capture_region="part",
    )
    calls = mock_h6199_coordinator.send_command.call_args_list
    assert calls[1].args[0] == build_video_mode(
        full_screen=False,
        game_mode=False,
        saturation=50,
    )
    assert mock_h6199_coordinator.video_full_screen is False


@pytest.mark.asyncio
async def test_set_music_mode_energic(h6199_light, mock_h6199_coordinator):
    """Test set_music_mode service with energic mode."""
    await h6199_light.async_set_music_mode(mode="energic", sensitivity=75)
    calls = mock_h6199_coordinator.send_command.call_args_list
    assert len(calls) == 2
    assert calls[1].args[0] == build_music_mode_with_color(0x05, sensitivity=75)
    assert mock_h6199_coordinator.effect == "music: energic"
    assert mock_h6199_coordinator.music_sensitivity == 75


@pytest.mark.asyncio
async def test_set_music_mode_with_color(h6199_light, mock_h6199_coordinator):
    """Test set_music_mode with accent color."""
    await h6199_light.async_set_music_mode(
        mode="spectrum",
        sensitivity=90,
        color=(255, 0, 128),
    )
    calls = mock_h6199_coordinator.send_command.call_args_list
    assert calls[1].args[0] == build_music_mode_with_color(
        0x04,
        sensitivity=90,
        color=(255, 0, 128),
    )
    assert mock_h6199_coordinator.music_color == (255, 0, 128)


@pytest.mark.asyncio
async def test_set_music_mode_rhythm(h6199_light, mock_h6199_coordinator):
    """Test set_music_mode with rhythm mode."""
    await h6199_light.async_set_music_mode(mode="rhythm", sensitivity=50)
    calls = mock_h6199_coordinator.send_command.call_args_list
    assert calls[1].args[0] == build_music_mode_with_color(0x03, sensitivity=50)
    assert mock_h6199_coordinator.effect == "music: rhythm"


@pytest.mark.asyncio
async def test_set_music_mode_rolling_with_color(h6199_light, mock_h6199_coordinator):
    """Test set_music_mode rolling with color."""
    await h6199_light.async_set_music_mode(
        mode="rolling",
        sensitivity=100,
        color=(0, 255, 0),
    )
    calls = mock_h6199_coordinator.send_command.call_args_list
    assert calls[1].args[0] == build_music_mode_with_color(
        0x06,
        sensitivity=100,
        color=(0, 255, 0),
    )


@pytest.mark.asyncio
async def test_set_music_mode_no_color(h6199_light, mock_h6199_coordinator):
    """Test set_music_mode without color."""
    await h6199_light.async_set_music_mode(mode="energic")
    calls = mock_h6199_coordinator.send_command.call_args_list
    assert calls[1].args[0] == build_music_mode_with_color(0x05, sensitivity=100)
    assert mock_h6199_coordinator.music_color is None


# --- Model guard tests ---


@pytest.mark.asyncio
async def test_set_video_mode_rejected_on_h617a(light):
    """Test set_video_mode raises error on H617A entity."""
    with pytest.raises(ServiceValidationError, match="H617A"):
        await light.async_set_video_mode(mode="movie")


@pytest.mark.asyncio
async def test_set_music_mode_rejected_on_h617a(light):
    """Test set_music_mode raises error on H617A entity."""
    with pytest.raises(ServiceValidationError, match="H617A"):
        await light.async_set_music_mode(mode="energic")


# --- Rollback tests for services ---


@pytest.mark.asyncio
async def test_set_video_mode_rollback_on_failure(h6199_light, mock_h6199_coordinator):
    """Test set_video_mode rolls back state when BLE command fails."""
    mock_h6199_coordinator.is_on = False
    mock_h6199_coordinator.effect = None
    mock_h6199_coordinator.video_saturation = 100
    # Fail on the second send_command (the video mode packet)
    mock_h6199_coordinator.send_command = AsyncMock(side_effect=[None, BleakError("connection lost")])

    with pytest.raises(BleakError):
        await h6199_light.async_set_video_mode(mode="movie", saturation=42)

    # is_on was set to True after power-on succeeded, but should be rolled back
    assert mock_h6199_coordinator.is_on is False
    assert mock_h6199_coordinator.effect is None
    assert mock_h6199_coordinator.video_saturation == 100
    assert mock_h6199_coordinator.video_brightness == 100


@pytest.mark.asyncio
async def test_set_music_mode_rollback_on_failure(h6199_light, mock_h6199_coordinator):
    """Test set_music_mode rolls back state when BLE command fails."""
    mock_h6199_coordinator.is_on = False
    mock_h6199_coordinator.effect = None
    mock_h6199_coordinator.music_sensitivity = 100
    mock_h6199_coordinator.music_color = None
    mock_h6199_coordinator.send_command = AsyncMock(side_effect=[None, BleakError("timeout")])

    with pytest.raises(BleakError):
        await h6199_light.async_set_music_mode(mode="spectrum", sensitivity=50, color=(255, 0, 0))

    assert mock_h6199_coordinator.is_on is False
    assert mock_h6199_coordinator.effect is None
    assert mock_h6199_coordinator.music_sensitivity == 100
    assert mock_h6199_coordinator.music_color is None
