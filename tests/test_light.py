from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak import BleakError
from homeassistant.components.light import ColorMode
from homeassistant.exceptions import ServiceValidationError

from custom_components.ha_govee_led_ble import protocol as proto
from custom_components.ha_govee_led_ble.const import MODEL_PROFILES
from custom_components.ha_govee_led_ble.light import MUSIC_MODE_IDS, GoveeBLELight
from custom_components.ha_govee_led_ble.scenes import SCENES


@pytest.fixture
def light(mock_coordinator):
    e = GoveeBLELight(mock_coordinator)
    e.async_write_ha_state = MagicMock()
    return e


@pytest.fixture
def h6199_light(mock_h6199_coordinator):
    mock_h6199_coordinator.is_on = False
    mock_h6199_coordinator.effect = None
    e = GoveeBLELight(mock_h6199_coordinator)
    e.async_write_ha_state = MagicMock()
    return e


def test_basic_and_color_props(light, mock_coordinator):
    assert light.unique_id == "aabbccddeeff" and light.is_on is False
    mock_coordinator.brightness_pct = 50
    assert light.brightness == 128
    exp = sorted(SCENES.keys()) + MODEL_PROFILES["H617A"].effects
    assert light.effect_list == exp
    mock_coordinator.effect = "rainbow"
    assert light.effect == "rainbow"
    mock_coordinator.effect = None
    assert light.effect is None
    mock_coordinator.rgb_color = (128, 64, 32)
    mock_coordinator.color_temp_kelvin = 4000
    light._attr_color_mode = ColorMode.RGB
    assert light.rgb_color == (128, 64, 32) and light.color_temp_kelvin is None
    light._attr_color_mode = ColorMode.COLOR_TEMP
    assert light.rgb_color is None and light.color_temp_kelvin == 4000


@pytest.mark.parametrize("on", [True, False])
async def test_power(light, mock_coordinator, on):
    await (light.async_turn_on() if on else light.async_turn_off())
    mock_coordinator.send_command.assert_called_with(proto.build_power(on))
    assert mock_coordinator.is_on is on


async def test_turn_on_variants(light, mock_coordinator):
    co = mock_coordinator

    async def _on(**kw):
        co.send_command.reset_mock()
        co.is_on = False
        await light.async_turn_on(**kw)
        return co.send_command.call_args_list

    await light.async_turn_on(brightness=128)
    c = co.send_command.call_args_list
    assert len(c) == 2 and c[1].args[0] == proto.build_brightness(50)
    c = await _on(rgb_color=(255, 0, 128))
    assert len(c) == 2 and c[1].args[0] == proto.build_color_rgb(255, 0, 128) and co.rgb_color == (255, 0, 128)
    c = await _on(color_temp_kelvin=4000)
    assert c[1].args[0] == proto.build_color_temp(4000) and co.color_temp_kelvin == 4000
    assert light._attr_color_mode == ColorMode.COLOR_TEMP
    co.effect = "rainbow"
    await _on(color_temp_kelvin=5000)
    assert co.effect is None
    c = await _on(effect="rainbow")
    assert c[1].args[0] == proto.build_scene(SCENES["rainbow"].code) and co.effect == "rainbow"
    co.send_command.reset_mock()
    co.is_on = False
    await light.async_turn_on(effect="forest")
    packets = [call.args[0] for call in co.send_command.call_args_list]
    assert packets[0] == proto.build_power(True)
    assert len(packets) > 2 and packets[1][0] == 0xA3 and packets[-1][0] == 0x33


async def test_power_rollback(light, mock_coordinator):
    mock_coordinator.send_command = AsyncMock(side_effect=[None, BleakError("fail")])
    with pytest.raises(BleakError):
        await light.async_turn_on(brightness=128)
    assert mock_coordinator.is_on is False and mock_coordinator.brightness_pct == 100
    mock_coordinator.is_on = True
    mock_coordinator.send_command = AsyncMock(side_effect=BleakError("timeout"))
    with pytest.raises(BleakError):
        await light.async_turn_off()
    assert mock_coordinator.is_on is True


def test_effect_lists(h6199_light, light):
    assert len(light.effect_list) == len(SCENES) + len(MODEL_PROFILES["H617A"].effects)
    assert len(h6199_light.effect_list) == len(MODEL_PROFILES["H6199"].effects)
    assert "music: energic" in light.effect_list and "video: movie" not in light.effect_list
    fx = h6199_light.effect_list
    assert "video: movie" in fx and "music: energic" in fx and "rainbow" not in fx


@pytest.mark.parametrize("effect,game,has_bri", [("video: movie", False, True), ("video: game", True, False)])
async def test_h6199_video(h6199_light, mock_h6199_coordinator, effect, game, has_bri):
    await h6199_light.async_turn_on(effect=effect)
    c = mock_h6199_coordinator.send_command.call_args_list
    assert c[1].args[0] == proto.build_video_mode(full_screen=True, game_mode=game)
    if has_bri:
        assert c[2].args[0] == proto.build_brightness(100)
    assert mock_h6199_coordinator.effect == effect


@pytest.mark.parametrize("mode,mid", [(f"music: {n}", i) for n, i in MUSIC_MODE_IDS.items()])
async def test_h6199_music(h6199_light, mock_h6199_coordinator, mode, mid):
    await h6199_light.async_turn_on(effect=mode)
    c = mock_h6199_coordinator.send_command.call_args_list
    assert c[1].args[0] == proto.build_music_mode_with_color(mid) and mock_h6199_coordinator.effect == mode


async def test_h6199_stored_params(h6199_light, mock_h6199_coordinator):
    co = mock_h6199_coordinator
    co.video_saturation, co.video_brightness = 42, 37
    co.video_full_screen, co.video_sound_effects, co.video_sound_effects_softness = False, True, 55
    await h6199_light.async_turn_on(effect="video: game")
    c = co.send_command.call_args_list
    exp = proto.build_video_mode(
        full_screen=False, game_mode=True, saturation=42, sound_effects=True, sound_effects_softness=55
    )
    assert c[1].args[0] == exp and c[2].args[0] == proto.build_brightness(37)
    co.send_command.reset_mock()
    co.is_on, co.effect = False, None
    co.music_sensitivity, co.music_color = 33, (10, 20, 30)
    await h6199_light.async_turn_on(effect="music: spectrum")
    c = co.send_command.call_args_list
    assert c[1].args[0] == proto.build_music_mode_with_color(0x04, sensitivity=33, color=(10, 20, 30))
    co.send_command.reset_mock()
    co.is_on, co.effect = False, None
    co.music_sensitivity, co.music_color, co.music_calm = 44, (11, 22, 33), True
    await h6199_light.async_turn_on(effect="music: rhythm")
    c = co.send_command.call_args_list
    assert c[1].args[0] == proto.build_music_mode_with_color(0x03, sensitivity=44, color=(11, 22, 33), calm=True)
    co.send_command.reset_mock()
    co.is_on, co.effect = False, None
    await h6199_light.async_turn_on(effect="nonexistent_effect")
    assert co.send_command.call_count == 1 and co.effect is None


async def test_h6199_confirms_power(h6199_light, mock_h6199_coordinator):
    for on in (True, False):
        await (h6199_light.async_turn_on() if on else h6199_light.async_turn_off())
        mock_h6199_coordinator.refresh_state.assert_awaited_once_with(expected_effect=None, expected_on=on)
        mock_h6199_coordinator.refresh_state.reset_mock()


async def test_set_video_and_music(h6199_light, mock_h6199_coordinator):
    lt, co = h6199_light, mock_h6199_coordinator
    await lt.async_set_video_mode(mode="movie", saturation=80, brightness=65)
    c = co.send_command.call_args_list
    assert c[0].args[0] == proto.build_power(True)
    assert c[1].args[0] == proto.build_video_mode(full_screen=True, game_mode=False, saturation=80)
    assert c[2].args[0] == proto.build_brightness(65) and co.effect == "video: movie" and co.video_saturation == 80
    co.send_command.reset_mock()
    co.is_on, co.effect = False, None
    await lt.async_set_video_mode(
        mode="game", saturation=60, brightness=75, full_screen=False, sound_effects=True, sound_effects_softness=50
    )
    c = co.send_command.call_args_list
    exp = proto.build_video_mode(
        full_screen=False, game_mode=True, saturation=60, sound_effects=True, sound_effects_softness=50
    )
    assert c[1].args[0] == exp and co.video_sound_effects is True
    co.send_command.reset_mock()
    co.is_on, co.effect = False, None
    await lt.async_set_video_mode(mode="movie", saturation=50, brightness=60, full_screen=True, capture_region="part")
    c = co.send_command.call_args_list
    assert c[1].args[0] == proto.build_video_mode(full_screen=False, game_mode=False, saturation=50)
    assert co.video_full_screen is False
    co.send_command.reset_mock()
    co.is_on, co.effect = False, None
    _bm = proto.build_music_mode_with_color
    await lt.async_set_music_mode(mode="energic", sensitivity=75)
    assert co.send_command.call_args_list[1].args[0] == _bm(0x05, sensitivity=75) and co.effect == "music: energic"
    co.send_command.reset_mock()
    co.is_on, co.effect = False, None
    await lt.async_set_music_mode(mode="spectrum", sensitivity=90, color=(255, 0, 128))
    assert co.send_command.call_args_list[1].args[0] == _bm(0x04, sensitivity=90, color=(255, 0, 128))
    assert co.music_color == (255, 0, 128)
    co.send_command.reset_mock()
    co.is_on, co.effect = False, None
    await lt.async_set_music_mode(mode="rhythm", sensitivity=55, color=(1, 2, 3), calm=True)
    assert co.send_command.call_args_list[1].args[0] == _bm(0x03, sensitivity=55, color=(1, 2, 3), calm=True)
    assert co.music_calm is True
    co.send_command.reset_mock()
    co.is_on, co.effect = False, None
    await lt.async_set_white_brightness(brightness=47)
    c = co.send_command.call_args_list
    assert c[0].args[0] == proto.build_power(True)
    assert c[1].args[0] == proto.build_white_brightness(47)
    assert co.white_brightness == 47 and co.brightness_pct == 47 and co.effect is None


async def test_h617a_rejection_and_rollback(light, h6199_light, mock_h6199_coordinator):
    c = light.coordinator
    await light.async_set_music_mode(mode="energic", sensitivity=75)
    assert c.send_command.call_args_list[0].args[0] == proto.build_power(True)
    assert c.send_command.call_args_list[1].args[0] == proto.build_music_mode_with_color(0x05, sensitivity=75)
    assert c.effect == "music: energic"
    c.send_command.reset_mock()
    c.is_on, c.effect = False, None
    for svc, kw in [
        ("async_set_video_mode", {"mode": "movie"}),
        ("async_set_white_brightness", {"brightness": 50}),
    ]:
        with pytest.raises(ServiceValidationError, match="H617A"):
            await getattr(light, svc)(**kw)
    for method, kw, attr, val in [
        ("async_set_video_mode", dict(mode="movie", saturation=42), "video_saturation", 100),
        ("async_set_white_brightness", dict(brightness=60), "white_brightness", 100),
    ]:
        mock_h6199_coordinator.send_command = AsyncMock(side_effect=[None, BleakError("fail")])
        mock_h6199_coordinator.is_on = False
        with pytest.raises(BleakError):
            await getattr(h6199_light, method)(**kw)
        assert mock_h6199_coordinator.is_on is False and getattr(mock_h6199_coordinator, attr) == val
