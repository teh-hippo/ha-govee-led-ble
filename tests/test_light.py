import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak import BleakError
from homeassistant.components.light import ColorMode
from homeassistant.exceptions import ServiceValidationError

from custom_components.ha_govee_led_ble import protocol as proto
from custom_components.ha_govee_led_ble.const import MODEL_PROFILES
from custom_components.ha_govee_led_ble.light import (
    GoveeBLELight,
    _coerce_segment_colors,
    async_setup_entry,
)
from custom_components.ha_govee_led_ble.scenes import MODEL_SCENE_LABELS, MODEL_SCENES, SCENES


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
    labels = sorted(MODEL_SCENE_LABELS["H617A"].values(), key=str.casefold)
    assert light.effect_list[: len(labels)] == labels
    mock_coordinator.effect = "rainbow"
    assert light.effect == "Rainbow"
    mock_coordinator.effect = None
    assert light.effect == "off"
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
    assert co.refresh_state.await_args.kwargs["expected_brightness"] == 50
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
    el = light.effect_list
    labels = sorted(MODEL_SCENE_LABELS["H617A"].values(), key=str.casefold)
    assert el[: len(labels)] == labels
    assert "Music: Energetic" in el and "Music: Piano Keys" in el
    assert "Video: Movie" not in el and "music: energetic" not in el
    h = h6199_light.effect_list
    assert h == ["Video: Movie", "Video: Game"]

    mock_h6199_coordinator.effect_families = frozenset({"scenes", "music", "video"})
    h = h6199_light.effect_list
    assert "Sunrise" in h and "Music: Rhythm" in h and h[-2:] == ["Video: Movie", "Video: Game"]
    assert "Music: Bloom" not in h and "Music: Shiny" not in h
    assert "Forest" in h and "Aurora-A" in h


async def test_turn_on_scene_applies_and_clears_sticky(light, mock_coordinator):
    co = mock_coordinator
    co.is_on = True
    co.music_mode, co.video_mode = "rhythm", "off"
    co.diy_slot = 0xF0
    await light.async_turn_on(effect="rainbow")
    sent = [call.args[0] for call in co.send_command.call_args_list]
    scene = SCENES["rainbow"]
    assert sent == proto.build_scene_multi(scene.param, scene.code, scene.scene_type)
    assert co.effect == "rainbow"
    assert co.diy_slot is None
    assert co.music_mode == "off" and co.video_mode == "off"


async def test_turn_on_scene_reuses_only_that_scenes_speed(light, mock_coordinator):
    co = mock_coordinator
    scene = SCENES["glacier"]
    assert scene.speed is not None
    co.is_on = True
    co.scene_speed_scene_code, co.scene_speed_index = scene.code, 0

    await light.async_turn_on(effect="glacier")

    assert [call.args[0] for call in co.send_command.await_args_list] == proto.build_scene_multi(
        scene.param, scene.code, scene.scene_type, scene.speed, speed_index=0
    )
    co._sync_scene_speed.assert_called_once_with("glacier", speed_index=0)


async def test_h6199_scene_disables_linked_music(h6199_light, mock_h6199_coordinator):
    co = mock_h6199_coordinator
    co.is_on = True
    co.effect_families = frozenset({"scenes"})
    await h6199_light.async_turn_on(effect="sunrise")
    sent = [call.args[0] for call in co.send_command.call_args_list]
    scene = MODEL_SCENES["H6199"]["sunrise"]
    assert sent == proto.build_h6199_scene_multi(scene.param, scene.code, scene.scene_type, scene.music_code)
    assert sent[0][5:7] == b"\x00\x00"
    assert co.effect == "sunrise"


async def test_h6199_uploads_an_opted_in_scene(h6199_light, mock_h6199_coordinator):
    co = mock_h6199_coordinator
    co.is_on = True
    co.effect_families = frozenset({"scenes"})
    await h6199_light.async_turn_on(effect="forest")
    scene = MODEL_SCENES["H6199"]["forest"]
    assert [call.args[0] for call in co.send_command.await_args_list] == proto.build_h6199_scene_multi(
        scene.param,
        scene.code,
        scene.scene_type,
        scene.music_code,
    )


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
    co.video_full_screen = False
    co.video_saturation = 63
    co.video_sound_effects = True
    co.video_sound_effects_softness = 27
    co.refresh_state = AsyncMock(side_effect=[False, True])
    await h6199_light.async_turn_on(effect=effect)
    packet = proto.build_video_mode(
        full_screen=False,
        game_mode=mode == "game",
        saturation=63,
        sound_effects=True,
        sound_effects_softness=27,
    )
    assert [call.args[0] for call in co.send_command.call_args_list] == [
        proto.build_power(True),
        packet,
        proto.build_power(True),
        packet,
    ]
    for call in co.refresh_state.await_args_list:
        assert call.kwargs["expected_video_mode"] == mode
        assert call.kwargs["expected_video_full_screen"] is False
        assert call.kwargs["expected_video_saturation"] == 63
        assert call.kwargs["expected_video_sound_effects"] is True
        assert call.kwargs["expected_video_sound_effects_softness"] == 27
    assert co.video_mode == mode and co.effect is None


async def test_effect_reflects_active_video_mode(h6199_light, mock_h6199_coordinator):
    mock_h6199_coordinator.effect = None
    mock_h6199_coordinator.video_mode = "movie"
    assert h6199_light.effect == "Video: Movie"
    mock_h6199_coordinator.video_mode = "game"
    assert h6199_light.effect == "Video: Game"
    mock_h6199_coordinator.video_mode = "off"
    mock_h6199_coordinator.effect = "rainbow"
    assert h6199_light.effect == "off"


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


@pytest.mark.parametrize(
    "method,kwargs",
    [
        ("async_paint_segments", {"groups": []}),
        ("async_paint_segments", {"groups": [{"segments": [], "rgb_color": (1, 2, 3)}]}),
        ("async_set_segment_color", {"segments": [], "color": (1, 2, 3)}),
        ("async_set_segment_brightness", {"segments": [], "brightness": 50}),
    ],
)
async def test_segment_services_reject_empty_selections(light, mock_coordinator, method, kwargs):
    with pytest.raises(ServiceValidationError) as exc:
        await getattr(light, method)(**kwargs)
    assert exc.value.translation_key == "invalid_segments"
    mock_coordinator.send_command.assert_not_awaited()


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
    assert light.extra_state_attributes == {
        "segment_colors": [[10, 20, 30]] * 15,
    }


def test_h6199_segment_surface_is_exposed(h6199_light):
    assert h6199_light.extra_state_attributes == {
        "segment_colors": [[255, 255, 255]] * 15,
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
    attrs = GoveeBLELight(mock_coordinator).extra_state_attributes
    assert "segment_colors" not in attrs
    assert attrs == {}


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
    light._async_restore_static_color = AsyncMock()
    light._async_restore_segments = AsyncMock()
    with patch(
        "custom_components.ha_govee_led_ble.entity.GoveeBLEEntity.async_added_to_hass",
        new_callable=AsyncMock,
    ) as super_added:
        await light.async_added_to_hass()
    super_added.assert_awaited_once()
    light._async_restore_static_color.assert_awaited_once()
    light._async_restore_segments.assert_awaited_once()


async def test_restore_static_rgb_as_last_known_presentation(light, mock_coordinator):
    mock_coordinator.color_mode = proto.ParsedMode.COLOUR
    light.async_get_last_state = AsyncMock(
        return_value=SimpleNamespace(
            attributes={
                "color_mode": ColorMode.RGB,
                "rgb_color": [12, 34, 56],
                "segment_colors": [[12, 34, 56]] * 15,
            }
        )
    )

    await light._async_restore_static_color()
    await light._async_restore_segments()

    assert mock_coordinator.rgb_color == (12, 34, 56)
    assert mock_coordinator.segment_colors == [(12, 34, 56)] * 15
    assert light._attr_color_mode is ColorMode.RGB
    mock_coordinator.send_command.assert_not_awaited()


async def test_restore_static_colour_temperature_as_last_known_presentation(light, mock_coordinator):
    mock_coordinator.color_mode = proto.ParsedMode.COLOUR
    light.async_get_last_state = AsyncMock(
        return_value=SimpleNamespace(
            attributes={
                "color_mode": ColorMode.COLOR_TEMP,
                "color_temp_kelvin": 4200,
            }
        )
    )

    await light._async_restore_static_color()

    assert mock_coordinator.color_temp_kelvin == 4200
    assert light._attr_color_mode is ColorMode.COLOR_TEMP
    mock_coordinator.send_command.assert_not_awaited()


async def test_restore_static_colour_never_overwrites_a_live_effect(light, mock_coordinator):
    mock_coordinator.color_mode = proto.ParsedMode.SCENE
    mock_coordinator.effect = "rainbow"
    light.async_get_last_state = AsyncMock()

    await light._async_restore_static_color()

    light.async_get_last_state.assert_not_called()
    assert mock_coordinator.effect == "rainbow"


async def test_control_lock_keeps_failed_rollback_before_newer_colour(light, mock_coordinator):
    mock_coordinator.is_on = True
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    sent: list[bytes] = []
    red = proto.build_color_rgb(255, 0, 0)
    blue = proto.build_color_rgb(0, 0, 255)

    async def send(packet: bytes) -> None:
        sent.append(packet)
        if packet == red:
            first_started.set()
            await release_first.wait()
            raise BleakError("failed red write")

    mock_coordinator.send_command = AsyncMock(side_effect=send)
    first = asyncio.create_task(light.async_turn_on(rgb_color=(255, 0, 0)))
    await first_started.wait()
    second = asyncio.create_task(light.async_turn_on(rgb_color=(0, 0, 255)))
    await asyncio.sleep(0)
    assert sent == [red]

    release_first.set()
    with pytest.raises(BleakError):
        await first
    await second

    assert sent == [red, blue]
    assert mock_coordinator.rgb_color == (0, 0, 255)
