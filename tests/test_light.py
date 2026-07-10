import logging
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak import BleakError
from homeassistant.components.light import ColorMode
from homeassistant.exceptions import ServiceValidationError

from custom_components.ha_govee_led_ble import protocol as proto
from custom_components.ha_govee_led_ble.const import MODEL_PROFILES
from custom_components.ha_govee_led_ble.custom_effects import EffectValidationError, content_from_dict
from custom_components.ha_govee_led_ble.light import (
    MUSIC_MODE_IDS,
    GoveeBLELight,
    _coerce_segment_colors,
    async_setup_entry,
)
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
    assert light.effect_list[: len(SCENES)] == sorted(SCENES.keys())
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
    co.send_command.reset_mock()
    co.refresh_state.reset_mock()
    co.is_on = True
    await light.async_turn_on(brightness=128)
    assert co.send_command.call_count == 1
    assert co.send_command.call_args_list[0].args[0] == proto.build_brightness(50)
    co.refresh_state.assert_not_awaited()
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
    c = await _on(effect="Candy")
    packets = [call.args[0] for call in c]
    assert packets[1][0] == 0xA3 and packets[-1] == proto.build_scene(SCENES["candy"].code) and co.effect == "candy"
    c = await _on(effect="“candy”")
    packets = [call.args[0] for call in c]
    assert packets[1][0] == 0xA3 and packets[-1] == proto.build_scene(SCENES["candy"].code) and co.effect == "candy"
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


def test_effect_lists(h6199_light, light, mock_coordinator, mock_h6199_coordinator):
    mock_coordinator.custom_effect_display_names.return_value = ["My Custom"]
    el = light.effect_list
    # H617A: scenes + customs + first-class music effects (no video).
    assert el[: len(SCENES) + 1] == sorted(SCENES.keys()) + ["My Custom"]
    assert "Music: Energetic" in el and "Music: Piano Keys" in el
    assert "Video: Movie" not in el and "music: energetic" not in el
    # H6199: no scene catalogue (scene_source "none"): customs + music + video effects.
    mock_h6199_coordinator.custom_effect_display_names.return_value = ["Solo"]
    h = h6199_light.effect_list
    assert h[0] == "Solo" and "Music: Rhythm" in h and h[-2:] == ["Video: Movie", "Video: Game"]


async def test_turn_on_custom_effect_applies(light, mock_coordinator):
    co = mock_coordinator
    co.is_on = True
    co.resolve_custom = MagicMock(return_value=MagicMock(id="diy-7", display_name="My Custom"))
    await light.async_turn_on(effect="My Custom")
    co.resolve_custom.assert_called_once_with("my custom")
    co.async_apply_custom_effect.assert_awaited_once_with("diy-7")


async def test_turn_on_scene_applies_and_clears_sticky(light, mock_coordinator):
    co = mock_coordinator
    co.is_on = True
    co.active_custom_id, co.music_mode, co.video_mode = "diy-9", "rhythm", "off"
    await light.async_turn_on(effect="rainbow")
    sent = [call.args[0] for call in co.send_command.call_args_list]
    scene = SCENES["rainbow"]
    assert sent == proto.build_scene_multi(scene.param, scene.code, scene.scene_type)
    assert co.effect == "rainbow" and co.active_custom_id is None
    assert co.music_mode == "off" and co.video_mode == "off"


async def test_turn_on_unknown_effect_raises(light, mock_coordinator):
    mock_coordinator.is_on = True
    with pytest.raises(ServiceValidationError):
        await light.async_turn_on(effect="does not exist")


@pytest.mark.parametrize(
    "effect,slug", [("Music: Rhythm", "rhythm"), ("Music: Piano Keys", "piano_keys"), ("music: rhythm", "rhythm")]
)
async def test_turn_on_music_effect_is_first_class(light, mock_coordinator, effect, slug):
    co = mock_coordinator
    co.is_on = True
    await light.async_turn_on(effect=effect)
    co.async_select_music_slug.assert_awaited_once_with(slug)


@pytest.mark.parametrize("effect,mode", [("Video: Movie", "movie"), ("Video: Game", "game"), ("video: game", "game")])
async def test_turn_on_video_effect_is_first_class(h6199_light, mock_h6199_coordinator, effect, mode):
    co = mock_h6199_coordinator
    co.is_on = True
    await h6199_light.async_turn_on(effect=effect)
    sent = [call.args[0] for call in co.send_command.call_args_list]
    assert proto.build_video_mode(full_screen=True, game_mode=mode == "game") in sent
    assert co.video_mode == mode and co.effect is None


async def test_effect_reflects_active_video_mode(h6199_light, mock_h6199_coordinator):
    mock_h6199_coordinator.effect = None
    mock_h6199_coordinator.video_mode = "movie"
    assert h6199_light.effect == "Video: Movie"
    mock_h6199_coordinator.video_mode = "game"
    assert h6199_light.effect == "Video: Game"
    mock_h6199_coordinator.video_mode = "off"
    mock_h6199_coordinator.effect = "rainbow"
    assert h6199_light.effect == "rainbow"


@pytest.mark.parametrize("mode,slug", [(m, m.replace(" ", "_")) for m in MUSIC_MODE_IDS])
async def test_set_music_mode_all_modes(h6199_light, mock_h6199_coordinator, mode, slug):
    """Every mode routes through the coordinator's single music-apply path with its slug."""
    await h6199_light.async_set_music_mode(mode=mode, sensitivity=70)
    mock_h6199_coordinator.async_select_music_slug.assert_awaited_once_with(slug)
    assert mock_h6199_coordinator.music_sensitivity == 70


async def test_set_music_mode_stores_calm_only_for_rhythm(h6199_light, mock_h6199_coordinator):
    co = mock_h6199_coordinator
    co.music_calm = False
    await h6199_light.async_set_music_mode(mode="rhythm", sensitivity=60, calm=True)
    co.async_select_music_slug.assert_awaited_once_with("rhythm")
    assert co.music_calm is True
    co.music_calm = False
    await h6199_light.async_set_music_mode(mode="spectrum", sensitivity=60, calm=True)
    co.async_select_music_slug.assert_awaited_with("spectrum")
    assert co.music_calm is False


async def test_set_music_mode_energic_alias(h6199_light, mock_h6199_coordinator, caplog):
    with caplog.at_level(logging.WARNING, logger="custom_components.ha_govee_led_ble.light"):
        await h6199_light.async_set_music_mode(mode="energic", sensitivity=75)
    mock_h6199_coordinator.async_select_music_slug.assert_awaited_once_with("energetic")
    assert mock_h6199_coordinator.music_sensitivity == 75
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    msg = warnings[0].getMessage()
    assert "energic" in msg and "deprecated" in msg


async def test_h6199_confirms_power(h6199_light, mock_h6199_coordinator):
    for on in (True, False):
        await (h6199_light.async_turn_on() if on else h6199_light.async_turn_off())
        mock_h6199_coordinator.refresh_state.assert_awaited_once_with(
            expected_effect=None, expected_on=on, expected_music_mode=None, expected_video_mode=None
        )
        mock_h6199_coordinator.refresh_state.reset_mock()


async def test_refresh_with_retry_required_flag(h6199_light, mock_h6199_coordinator):
    """An unconfirmed required write raises; a non-required one (experimental video) degrades quietly."""
    mock_h6199_coordinator.refresh_state = AsyncMock(return_value=False)
    await h6199_light._refresh_with_retry(expected_video_mode="game", required=False)
    with pytest.raises(RuntimeError):
        await h6199_light._refresh_with_retry(expected_music_mode="spectrum")


async def test_set_video_and_music(h6199_light, mock_h6199_coordinator):
    lt, co = h6199_light, mock_h6199_coordinator
    await lt.async_set_video_mode(mode="movie", saturation=80)
    c = co.send_command.call_args_list
    assert c[0].args[0] == proto.build_power(True)
    assert c[1].args[0] == proto.build_video_mode(full_screen=True, game_mode=False, saturation=80)
    assert co.video_mode == "movie" and co.effect is None and co.video_saturation == 80
    co.send_command.reset_mock()
    co.is_on, co.effect = False, None
    await lt.async_set_video_mode(
        mode="game", saturation=60, full_screen=False, sound_effects=True, sound_effects_softness=50
    )
    c = co.send_command.call_args_list
    exp = proto.build_video_mode(
        full_screen=False, game_mode=True, saturation=60, sound_effects=True, sound_effects_softness=50
    )
    assert c[1].args[0] == exp and co.video_mode == "game" and co.video_sound_effects is True
    co.send_command.reset_mock()
    co.is_on, co.effect = False, None
    await lt.async_set_video_mode(mode="movie", saturation=50, full_screen=True, capture_region="part")
    c = co.send_command.call_args_list
    assert c[1].args[0] == proto.build_video_mode(full_screen=False, game_mode=False, saturation=50)
    assert co.video_full_screen is False
    co.async_select_music_slug.reset_mock()
    await lt.async_set_music_mode(mode="energetic", sensitivity=75)
    co.async_select_music_slug.assert_awaited_once_with("energetic")
    assert co.music_sensitivity == 75
    co.async_select_music_slug.reset_mock()
    await lt.async_set_music_mode(mode="spectrum", sensitivity=90, color=(255, 0, 128))
    co.async_select_music_slug.assert_awaited_once_with("spectrum")
    assert co.music_color == (255, 0, 128)
    co.async_select_music_slug.reset_mock()
    await lt.async_set_music_mode(mode="rhythm", sensitivity=55, color=(1, 2, 3), calm=True)
    co.async_select_music_slug.assert_awaited_once_with("rhythm")
    assert co.music_calm is True
    co.send_command.reset_mock()
    co.is_on, co.effect = False, None
    await lt.async_set_white_brightness(brightness=47)
    c = co.send_command.call_args_list
    assert c[0].args[0] == proto.build_power(True)
    assert c[1].args[0] == proto.build_white_brightness(47)
    assert co.white_brightness == 47 and co.brightness_pct == 100 and co.effect is None


async def test_set_white_brightness_clears_active_custom(h6199_light, mock_h6199_coordinator):
    """Entering a static mode (white) drops any sticky custom/music/video so one mode stays active."""
    co = mock_h6199_coordinator
    co.active_custom_id, co.effect, co.music_mode = "diy-7", "My Effect", "rhythm"
    await h6199_light.async_set_white_brightness(brightness=50)
    assert co.active_custom_id is None and co.effect is None
    assert co.music_mode == "off" and co.video_mode == "off"
    assert co.white_brightness == 50


async def test_h617a_rejection_and_rollback(light, h6199_light, mock_h6199_coordinator):
    c = light.coordinator
    await light.async_set_music_mode(mode="energetic", sensitivity=75)
    c.async_select_music_slug.assert_awaited_once_with("energetic")
    assert c.music_sensitivity == 75
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


async def test_setup_entry_registers_segment_services(mock_coordinator):
    entry = MagicMock(runtime_data=mock_coordinator)
    added: list = []
    platform = MagicMock()
    with patch(
        "custom_components.ha_govee_led_ble.light.entity_platform.async_get_current_platform",
        return_value=platform,
    ):
        await async_setup_entry(MagicMock(), entry, lambda e: added.extend(e))
    handlers = {call.args[0]: call.args[2] for call in platform.async_register_entity_service.call_args_list}
    assert handlers["paint_segments"] == "async_paint_segments"
    assert handlers["set_segment_color"] == "async_set_segment_color"
    assert handlers["set_segment_brightness"] == "async_set_segment_brightness"
    assert len(added) == 1 and isinstance(added[0], GoveeBLELight)


async def test_paint_segments_calls_coordinator(light, mock_coordinator):
    await light.async_paint_segments(
        [{"segments": [1, 2, 3], "rgb_color": (255, 0, 0)}, {"segments": [4, 5], "rgb_color": (0, 255, 0)}]
    )
    mock_coordinator.async_paint_segments.assert_awaited_once_with([([1, 2, 3], (255, 0, 0)), ([4, 5], (0, 255, 0))])


async def test_set_segment_color_delegates(light, mock_coordinator):
    await light.async_set_segment_color(segments=[7, 8], color=(1, 2, 3))
    mock_coordinator.async_paint_segments.assert_awaited_once_with([([7, 8], (1, 2, 3))])


async def test_set_segment_brightness_sends_packet(light, mock_coordinator):
    light.async_write_ha_state = MagicMock()
    await light.async_set_segment_brightness(segments=[2, 4], brightness=60)
    mock_coordinator.send_command.assert_called_once_with(proto.build_segment_brightness([2, 4], 60))
    mock_coordinator._enter_static_mode.assert_called_once_with()
    mock_coordinator.async_set_updated_data.assert_called_once_with(mock_coordinator.data)
    light.async_write_ha_state.assert_called_once_with()


async def test_segment_services_reject_unsupported(mock_coordinator):
    mock_coordinator.profile = replace(MODEL_PROFILES["H617A"], segment_count=0)
    e = GoveeBLELight(mock_coordinator)
    e.async_write_ha_state = MagicMock()
    with pytest.raises(ServiceValidationError, match="H617A"):
        await e.async_paint_segments([{"segments": [1], "rgb_color": (1, 2, 3)}])
    with pytest.raises(ServiceValidationError, match="H617A"):
        await e.async_set_segment_color(segments=[1], color=(1, 2, 3))
    with pytest.raises(ServiceValidationError, match="H617A"):
        await e.async_set_segment_brightness(segments=[1], brightness=50)
    mock_coordinator.async_paint_segments.assert_not_awaited()
    mock_coordinator.send_command.assert_not_called()


def test_segment_colors_attribute_present(light, mock_coordinator):
    mock_coordinator.segment_colors = [(10, 20, 30)] * 15
    mock_coordinator.custom_effect_index.return_value = {"a1b2c3d4": "Sunset"}
    assert light.extra_state_attributes == {
        "custom_effects": {"a1b2c3d4": "Sunset"},
        "segment_colors": [[10, 20, 30]] * 15,
    }


async def test_whole_strip_write_fills_segment_colors(light, mock_coordinator):
    mock_coordinator.segment_colors = [(1, 2, 3)] * 15
    await light.async_turn_on(rgb_color=(10, 20, 30))
    assert mock_coordinator.segment_colors == [(10, 20, 30)] * 15
    await light.async_turn_on(color_temp_kelvin=4000)
    assert mock_coordinator.segment_colors == [proto.kelvin_to_rgb(4000)] * 15


def test_segment_colors_attribute_absent_for_zero_count(mock_coordinator):
    mock_coordinator.profile = replace(MODEL_PROFILES["H617A"], segment_count=0)
    mock_coordinator.segment_colors = []
    mock_coordinator.custom_effect_index.return_value = {"a1b2c3d4": "Sunset"}
    attrs = GoveeBLELight(mock_coordinator).extra_state_attributes
    assert "segment_colors" not in attrs
    assert attrs == {"custom_effects": {"a1b2c3d4": "Sunset"}}


async def test_segment_restore_rehydrates(light, mock_coordinator):
    mock_coordinator.segment_colors = [(255, 255, 255)] * 15
    light.async_get_last_state = AsyncMock(return_value=MagicMock(attributes={"segment_colors": [[1, 2, 3]] * 15}))
    await light._async_restore_segments()
    assert mock_coordinator.segment_colors == [(1, 2, 3)] * 15
    mock_coordinator.async_set_updated_data.assert_called_once_with(mock_coordinator.data)


async def test_segment_restore_skips_when_customised(light, mock_coordinator):
    mock_coordinator.segment_colors = [(9, 9, 9)] * 15
    light.async_get_last_state = AsyncMock()
    await light._async_restore_segments()
    light.async_get_last_state.assert_not_called()
    mock_coordinator.async_set_updated_data.assert_not_called()


async def test_segment_restore_without_last_state(light, mock_coordinator):
    mock_coordinator.segment_colors = [(255, 255, 255)] * 15
    light.async_get_last_state = AsyncMock(return_value=None)
    await light._async_restore_segments()
    assert mock_coordinator.segment_colors == [(255, 255, 255)] * 15
    mock_coordinator.async_set_updated_data.assert_not_called()


async def test_segment_restore_ignores_malformed(light, mock_coordinator):
    mock_coordinator.segment_colors = [(255, 255, 255)] * 15
    light.async_get_last_state = AsyncMock(return_value=MagicMock(attributes={"segment_colors": [[1, 2]] * 15}))
    await light._async_restore_segments()
    assert mock_coordinator.segment_colors == [(255, 255, 255)] * 15
    mock_coordinator.async_set_updated_data.assert_not_called()


async def test_segment_restore_skips_unsupported(mock_coordinator):
    mock_coordinator.profile = replace(MODEL_PROFILES["H617A"], segment_count=0)
    e = GoveeBLELight(mock_coordinator)
    e.async_get_last_state = AsyncMock()
    await e._async_restore_segments()
    e.async_get_last_state.assert_not_called()


def test_coerce_segment_colors_variants():
    assert _coerce_segment_colors([[1, 2, 3], [4, 5, 6]], 2) == [(1, 2, 3), (4, 5, 6)]
    assert _coerce_segment_colors([[300, -5, 10]], 1) == [(255, 0, 10)]
    assert _coerce_segment_colors([(7, 8, 9)], 1) == [(7, 8, 9)]
    assert _coerce_segment_colors("nope", 1) is None
    assert _coerce_segment_colors([[1, 2, 3]], 2) is None
    assert _coerce_segment_colors([[1, 2]], 1) is None
    assert _coerce_segment_colors([["a", "b", "c"]], 1) is None


async def test_async_added_to_hass_triggers_restore(light):
    light._async_restore_effect = AsyncMock()
    light._async_restore_segments = AsyncMock()
    with patch(
        "custom_components.ha_govee_led_ble.entity.GoveeBLEEntity.async_added_to_hass",
        new_callable=AsyncMock,
    ) as super_added:
        await light.async_added_to_hass()
    super_added.assert_awaited_once()
    light._async_restore_effect.assert_awaited_once()
    light._async_restore_segments.assert_awaited_once()


async def test_restore_custom_sets_active_custom_id(light, mock_coordinator):
    mock_coordinator.resolve_custom = MagicMock(return_value=MagicMock(id="diy-3", display_name="Sunset"))
    light.async_get_last_state = AsyncMock(return_value=SimpleNamespace(attributes={"effect": "Sunset"}))
    await light._async_restore_effect()
    mock_coordinator.resolve_custom.assert_called_once_with("sunset")
    assert mock_coordinator.active_custom_id == "diy-3"
    assert mock_coordinator.effect == "Sunset"


async def test_restore_scene_keeps_effect(light, mock_coordinator):
    light.async_get_last_state = AsyncMock(return_value=SimpleNamespace(attributes={"effect": "rainbow"}))
    await light._async_restore_effect()
    assert mock_coordinator.effect == "rainbow"
    assert mock_coordinator.active_custom_id is None


async def test_restore_unknown_effect_is_dropped(light, mock_coordinator):
    light.async_get_last_state = AsyncMock(return_value=SimpleNamespace(attributes={"effect": "bogus"}))
    await light._async_restore_effect()
    assert mock_coordinator.effect is None
    assert mock_coordinator.active_custom_id is None


async def test_restore_effect_skipped_when_state_present(light, mock_coordinator):
    mock_coordinator.effect = "rainbow"
    light.async_get_last_state = AsyncMock()
    await light._async_restore_effect()
    mock_coordinator.effect, mock_coordinator.active_custom_id = None, "diy-1"
    await light._async_restore_effect()
    light.async_get_last_state.assert_not_called()


async def test_restore_effect_skipped_when_music_or_video_active(light, mock_coordinator):
    """A restart that reads back live music/video must not be overwritten by a stale restore."""
    light.async_get_last_state = AsyncMock()
    mock_coordinator.music_mode = "rhythm"
    await light._async_restore_effect()
    mock_coordinator.music_mode, mock_coordinator.video_mode = "off", "movie"
    await light._async_restore_effect()
    light.async_get_last_state.assert_not_called()


async def test_restore_effect_handles_missing_last_state(light, mock_coordinator):
    light.async_get_last_state = AsyncMock(return_value=None)
    await light._async_restore_effect()
    assert mock_coordinator.effect is None
    light.async_get_last_state = AsyncMock(return_value=SimpleNamespace(attributes={}))
    await light._async_restore_effect()
    assert mock_coordinator.effect is None


# --------------------------------------------------------------------------- #
# Custom-effect services (save / delete / rename) + the id index attribute
# --------------------------------------------------------------------------- #
async def test_setup_entry_registers_effect_services(mock_coordinator):
    entry = MagicMock(runtime_data=mock_coordinator)
    platform = MagicMock()
    with patch(
        "custom_components.ha_govee_led_ble.light.entity_platform.async_get_current_platform",
        return_value=platform,
    ):
        await async_setup_entry(MagicMock(), entry, lambda e: None)
    handlers = {call.args[0]: call.args[2] for call in platform.async_register_entity_service.call_args_list}
    assert handlers["save_effect"] == "async_save_effect"
    assert handlers["delete_effect"] == "async_delete_effect"
    assert handlers["rename_effect"] == "async_rename_effect"


async def test_save_effect_with_content_parses_and_delegates(light, mock_coordinator):
    content = {"kind": "vibrant", "stops": [[255, 120, 0], [0, 0, 255]]}
    await light.async_save_effect(name="Sunset", content=content)
    mock_coordinator.async_save_effect.assert_awaited_once_with("Sunset", content=content_from_dict(content))


async def test_save_effect_forwards_unknown_content(light, mock_coordinator):
    """Unknown-kind content is parsed and forwarded so the coordinator owns the rejection."""
    content = {"kind": "future_kind", "foo": 1}
    await light.async_save_effect(name="Mystery", content=content)
    mock_coordinator.async_save_effect.assert_awaited_once_with("Mystery", content=content_from_dict(content))


async def test_save_effect_capture_current_snapshots(light, mock_coordinator):
    await light.async_save_effect(name="Snapshot", capture_current=True)
    mock_coordinator.async_save_effect.assert_awaited_once_with("Snapshot", capture_current=True)


async def test_save_effect_rejects_both_and_neither(light, mock_coordinator):
    with pytest.raises(ServiceValidationError) as both:
        await light.async_save_effect(name="X", content={"kind": "vibrant"}, capture_current=True)
    assert both.value.translation_key == "content_xor_capture"
    with pytest.raises(ServiceValidationError) as neither:
        await light.async_save_effect(name="X")
    assert neither.value.translation_key == "content_xor_capture"
    mock_coordinator.async_save_effect.assert_not_awaited()


@pytest.mark.parametrize(
    "key",
    ["duplicate_name", "scene_name_collision", "empty_name", "unknown_kind_not_saveable", "diy_unsupported"],
)
async def test_save_effect_maps_effect_errors(light, mock_coordinator, key):
    mock_coordinator.async_save_effect = AsyncMock(side_effect=EffectValidationError(key))
    with pytest.raises(ServiceValidationError) as exc:
        await light.async_save_effect(name="X", content={"kind": "vibrant", "stops": [[1, 2, 3], [4, 5, 6]]})
    assert exc.value.translation_key == key


async def test_delete_effect_by_id_and_name(light, mock_coordinator):
    await light.async_delete_effect(id="a1b2c3d4")
    mock_coordinator.async_delete_effect.assert_awaited_once_with("a1b2c3d4")
    mock_coordinator.async_delete_effect.reset_mock()
    await light.async_delete_effect(name="Sunset")
    mock_coordinator.async_delete_effect.assert_awaited_once_with("Sunset")


async def test_delete_effect_rejects_both_and_neither(light, mock_coordinator):
    with pytest.raises(ServiceValidationError) as exc:
        await light.async_delete_effect(id="x", name="y")
    assert exc.value.translation_key == "delete_needs_id_or_name"
    with pytest.raises(ServiceValidationError):
        await light.async_delete_effect()
    mock_coordinator.async_delete_effect.assert_not_awaited()


async def test_delete_effect_unknown_maps_error(light, mock_coordinator):
    mock_coordinator.async_delete_effect = AsyncMock(side_effect=EffectValidationError("unknown_effect"))
    with pytest.raises(ServiceValidationError) as exc:
        await light.async_delete_effect(id="missing")
    assert exc.value.translation_key == "unknown_effect"
    assert exc.value.translation_placeholders == {"effect": "missing"}


async def test_rename_effect_by_id_and_from_name(light, mock_coordinator):
    await light.async_rename_effect(to="Dawn", id="a1b2c3d4")
    mock_coordinator.async_rename_effect.assert_awaited_once_with("a1b2c3d4", "Dawn")
    mock_coordinator.async_rename_effect.reset_mock()
    await light.async_rename_effect(to="Dawn", from_name="Sunset")
    mock_coordinator.async_rename_effect.assert_awaited_once_with("Sunset", "Dawn")


async def test_rename_effect_rejects_both_and_neither(light, mock_coordinator):
    with pytest.raises(ServiceValidationError) as exc:
        await light.async_rename_effect(to="Dawn", id="x", from_name="y")
    assert exc.value.translation_key == "rename_needs_id_or_from"
    with pytest.raises(ServiceValidationError):
        await light.async_rename_effect(to="Dawn")
    mock_coordinator.async_rename_effect.assert_not_awaited()


@pytest.mark.parametrize("key", ["duplicate_name", "scene_name_collision", "empty_name", "unknown_effect"])
async def test_rename_effect_maps_effect_errors(light, mock_coordinator, key):
    mock_coordinator.async_rename_effect = AsyncMock(side_effect=EffectValidationError(key))
    with pytest.raises(ServiceValidationError) as exc:
        await light.async_rename_effect(to="Dawn", id="a1b2c3d4")
    assert exc.value.translation_key == key


def test_custom_effects_attribute_maps_id_to_name(light, mock_coordinator):
    mock_coordinator.custom_effect_index.return_value = {"a1b2c3d4": "Sunset", "e5f6a7b8": "Dawn"}
    assert light.extra_state_attributes["custom_effects"] == {"a1b2c3d4": "Sunset", "e5f6a7b8": "Dawn"}
