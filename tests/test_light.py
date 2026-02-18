"""Tests for the Govee BLE light entity."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak import BleakError
from homeassistant.components.light import ColorMode
from homeassistant.exceptions import ServiceValidationError

from custom_components.govee_ble_lights.const import MODEL_PROFILES
from custom_components.govee_ble_lights.light import GoveeBLELight, _build_effect_list
from custom_components.govee_ble_lights.protocol import (
    build_brightness,
    build_color_rgb,
    build_color_temp,
    build_music_mode_with_color,
    build_power,
    build_scene,
    build_video_mode,
)
from custom_components.govee_ble_lights.scenes import SCENES


@pytest.fixture
def light(mock_coordinator, mock_config_entry):
    entity = GoveeBLELight(mock_coordinator, mock_config_entry)
    entity.async_write_ha_state = MagicMock()
    return entity


@pytest.fixture
def h6199_light(mock_h6199_coordinator, mock_config_entry):
    mock_h6199_coordinator.is_on = False
    mock_h6199_coordinator.effect = None
    entity = GoveeBLELight(mock_h6199_coordinator, mock_config_entry)
    entity.async_write_ha_state = MagicMock()
    return entity


# --- Basic properties ---


def test_unique_id(light):
    assert light.unique_id == "aabbccddeeff"


def test_is_off_initially(light):
    assert light.is_on is False


def test_brightness_conversion(light, mock_coordinator):
    mock_coordinator.brightness_pct = 50
    assert light.brightness == 128


def test_effect_list(light):
    effects = light.effect_list
    assert len(effects) == len(SCENES)
    assert effects == sorted(SCENES.keys())


def test_effect_property(light, mock_coordinator):
    mock_coordinator.effect = "rainbow"
    assert light.effect == "rainbow"
    mock_coordinator.effect = None
    assert light.effect is None


@pytest.mark.parametrize(
    "mode,rgb,temp",
    [
        (ColorMode.RGB, (128, 64, 32), None),
        (ColorMode.COLOR_TEMP, None, 4000),
    ],
)
def test_color_properties(light, mock_coordinator, mode, rgb, temp):
    mock_coordinator.rgb_color = (128, 64, 32)
    mock_coordinator.color_temp_kelvin = 4000
    light._attr_color_mode = mode
    assert light.rgb_color == rgb
    assert light.color_temp_kelvin == temp


# --- Turn on/off ---


async def test_turn_on(light, mock_coordinator):
    await light.async_turn_on()
    mock_coordinator.send_command.assert_called_with(build_power(True))
    assert mock_coordinator.is_on is True


async def test_turn_off(light, mock_coordinator):
    await light.async_turn_off()
    mock_coordinator.send_command.assert_called_with(build_power(False))
    assert mock_coordinator.is_on is False


async def test_turn_on_with_brightness(light, mock_coordinator):
    await light.async_turn_on(brightness=128)
    calls = mock_coordinator.send_command.call_args_list
    assert len(calls) == 2
    assert calls[1].args[0] == build_brightness(50)


async def test_turn_on_with_rgb(light, mock_coordinator):
    await light.async_turn_on(rgb_color=(255, 0, 128))
    calls = mock_coordinator.send_command.call_args_list
    assert calls[1].args[0] == build_color_rgb(255, 0, 128)
    assert mock_coordinator.rgb_color == (255, 0, 128)


async def test_turn_on_with_color_temp(light, mock_coordinator):
    await light.async_turn_on(color_temp_kelvin=4000)
    calls = mock_coordinator.send_command.call_args_list
    assert calls[1].args[0] == build_color_temp(4000)
    assert mock_coordinator.color_temp_kelvin == 4000
    assert light._attr_color_mode == ColorMode.COLOR_TEMP
    # Also clears active effect
    mock_coordinator.effect = "rainbow"
    await light.async_turn_on(color_temp_kelvin=5000)
    assert mock_coordinator.effect is None


async def test_turn_on_with_simple_effect(light, mock_coordinator):
    await light.async_turn_on(effect="rainbow")
    calls = mock_coordinator.send_command.call_args_list
    assert calls[1].args[0] == build_scene(SCENES["rainbow"].code)
    assert mock_coordinator.effect == "rainbow"


async def test_turn_on_with_complex_effect(light, mock_coordinator):
    mock_coordinator.send_commands = AsyncMock()
    await light.async_turn_on(effect="forest")
    mock_coordinator.send_command.assert_called_once_with(build_power(True))
    packets = mock_coordinator.send_commands.call_args.args[0]
    assert len(packets) > 1
    assert packets[0][0] == 0xA3
    assert packets[-1][0] == 0x33


# --- Rollback ---


async def test_turn_on_rollback_on_failure(light, mock_coordinator):
    mock_coordinator.send_command = AsyncMock(side_effect=[None, BleakError("fail")])
    with pytest.raises(BleakError):
        await light.async_turn_on(brightness=128)
    assert mock_coordinator.is_on is False
    assert mock_coordinator.brightness_pct == 100


async def test_turn_off_rollback_on_failure(light, mock_coordinator):
    mock_coordinator.is_on = True
    mock_coordinator.send_command = AsyncMock(side_effect=BleakError("timeout"))
    with pytest.raises(BleakError):
        await light.async_turn_off()
    assert mock_coordinator.is_on is True


# --- H6199 effects ---


def test_build_effect_list_api_model():
    assert len(_build_effect_list(MODEL_PROFILES["H617A"])) == len(SCENES)


def test_build_effect_list_none_model():
    assert len(_build_effect_list(MODEL_PROFILES["H6199"])) == len(MODEL_PROFILES["H6199"].effects)


def test_h6199_effect_list(h6199_light):
    effects = h6199_light.effect_list
    assert "video: movie" in effects and "music: energic" in effects
    assert "rainbow" not in effects


def test_h617a_no_video_effects(light):
    assert "video: movie" not in light.effect_list


async def test_h6199_video_movie(h6199_light, mock_h6199_coordinator):
    await h6199_light.async_turn_on(effect="video: movie")
    calls = mock_h6199_coordinator.send_command.call_args_list
    assert calls[1].args[0] == build_video_mode(full_screen=True, game_mode=False)
    assert calls[2].args[0] == build_brightness(100)
    assert mock_h6199_coordinator.effect == "video: movie"


async def test_h6199_video_game(h6199_light, mock_h6199_coordinator):
    await h6199_light.async_turn_on(effect="video: game")
    calls = mock_h6199_coordinator.send_command.call_args_list
    assert calls[1].args[0] == build_video_mode(full_screen=True, game_mode=True)
    assert mock_h6199_coordinator.effect == "video: game"


@pytest.mark.parametrize(
    "mode,mode_id",
    [
        ("music: energic", 0x05),
        ("music: rhythm", 0x03),
        ("music: spectrum", 0x04),
        ("music: rolling", 0x06),
    ],
)
async def test_h6199_music_effects(h6199_light, mock_h6199_coordinator, mode, mode_id):
    await h6199_light.async_turn_on(effect=mode)
    calls = mock_h6199_coordinator.send_command.call_args_list
    assert calls[1].args[0] == build_music_mode_with_color(mode_id)
    assert mock_h6199_coordinator.effect == mode


async def test_h6199_video_uses_stored_params(h6199_light, mock_h6199_coordinator):
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


async def test_h6199_music_uses_stored_params(h6199_light, mock_h6199_coordinator):
    mock_h6199_coordinator.music_sensitivity = 33
    mock_h6199_coordinator.music_color = (10, 20, 30)
    await h6199_light.async_turn_on(effect="music: spectrum")
    calls = mock_h6199_coordinator.send_command.call_args_list
    assert calls[1].args[0] == build_music_mode_with_color(0x04, sensitivity=33, color=(10, 20, 30))


async def test_h6199_unknown_effect_ignored(h6199_light, mock_h6199_coordinator):
    await h6199_light.async_turn_on(effect="nonexistent_effect")
    assert mock_h6199_coordinator.send_command.call_count == 1
    assert mock_h6199_coordinator.effect is None


async def test_h6199_confirms_power_state(h6199_light, mock_h6199_coordinator):
    await h6199_light.async_turn_on()
    mock_h6199_coordinator.refresh_state.assert_awaited_once_with(expected_effect=None, expected_on=True)
    mock_h6199_coordinator.refresh_state.reset_mock()
    await h6199_light.async_turn_off()
    mock_h6199_coordinator.refresh_state.assert_awaited_once_with(expected_effect=None, expected_on=False)


# --- H6199 services ---


async def test_set_video_mode_movie(h6199_light, mock_h6199_coordinator):
    await h6199_light.async_set_video_mode(mode="movie", saturation=80, brightness=65)
    calls = mock_h6199_coordinator.send_command.call_args_list
    assert calls[0].args[0] == build_power(True)
    assert calls[1].args[0] == build_video_mode(full_screen=True, game_mode=False, saturation=80)
    assert calls[2].args[0] == build_brightness(65)
    assert mock_h6199_coordinator.effect == "video: movie"
    assert mock_h6199_coordinator.video_saturation == 80


async def test_set_video_mode_game_with_sound(h6199_light, mock_h6199_coordinator):
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
    assert mock_h6199_coordinator.video_sound_effects is True


async def test_set_video_mode_capture_region_overrides(h6199_light, mock_h6199_coordinator):
    await h6199_light.async_set_video_mode(
        mode="movie",
        saturation=50,
        brightness=60,
        full_screen=True,
        capture_region="part",
    )
    calls = mock_h6199_coordinator.send_command.call_args_list
    assert calls[1].args[0] == build_video_mode(full_screen=False, game_mode=False, saturation=50)
    assert mock_h6199_coordinator.video_full_screen is False


async def test_set_music_mode_energic(h6199_light, mock_h6199_coordinator):
    await h6199_light.async_set_music_mode(mode="energic", sensitivity=75)
    calls = mock_h6199_coordinator.send_command.call_args_list
    assert calls[1].args[0] == build_music_mode_with_color(0x05, sensitivity=75)
    assert mock_h6199_coordinator.effect == "music: energic"


async def test_set_music_mode_with_color(h6199_light, mock_h6199_coordinator):
    await h6199_light.async_set_music_mode(mode="spectrum", sensitivity=90, color=(255, 0, 128))
    calls = mock_h6199_coordinator.send_command.call_args_list
    assert calls[1].args[0] == build_music_mode_with_color(0x04, sensitivity=90, color=(255, 0, 128))
    assert mock_h6199_coordinator.music_color == (255, 0, 128)


# --- Model guards ---


@pytest.mark.parametrize(
    "service,kwargs",
    [
        ("async_set_video_mode", {"mode": "movie"}),
        ("async_set_music_mode", {"mode": "energic"}),
    ],
)
async def test_service_rejected_on_h617a(light, service, kwargs):
    with pytest.raises(ServiceValidationError, match="H617A"):
        await getattr(light, service)(**kwargs)


# --- Service rollback ---


async def test_set_video_mode_rollback(h6199_light, mock_h6199_coordinator):
    mock_h6199_coordinator.send_command = AsyncMock(side_effect=[None, BleakError("fail")])
    with pytest.raises(BleakError):
        await h6199_light.async_set_video_mode(mode="movie", saturation=42)
    assert mock_h6199_coordinator.is_on is False
    assert mock_h6199_coordinator.video_saturation == 100


async def test_set_music_mode_rollback(h6199_light, mock_h6199_coordinator):
    mock_h6199_coordinator.send_command = AsyncMock(side_effect=[None, BleakError("timeout")])
    with pytest.raises(BleakError):
        await h6199_light.async_set_music_mode(mode="spectrum", sensitivity=50, color=(255, 0, 0))
    assert mock_h6199_coordinator.is_on is False
    assert mock_h6199_coordinator.music_sensitivity == 100
