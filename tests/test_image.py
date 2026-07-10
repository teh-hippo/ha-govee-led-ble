"""Tests for the effect-preview image entity: look resolution, caching, triggers and privacy."""

from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from custom_components.ha_govee_led_ble import image, preview
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.custom_effects import CustomEffect, SegmentContent, SketchContent
from custom_components.ha_govee_led_ble.image import GoveeEffectPreviewImage, _resolve_look, async_setup_entry
from custom_components.ha_govee_led_ble.scenes import SCENES, get_scene_names

_TWINKLE = SketchContent(motion=0x0F, colors=tuple([(255, 0, 0)] * 15))


@pytest.fixture
def h617a(hass):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617A")
    coordinator.effect = coordinator.active_custom_id = None
    return coordinator


@pytest.fixture
def entity(hass, h617a):
    built = GoveeEffectPreviewImage(h617a, hass)
    built.hass = hass
    built.async_write_ha_state = MagicMock()
    return built


def _make_custom(coordinator: GoveeBLECoordinator, content: object, *, name_key: str = "flame") -> None:
    coordinator.active_custom_id = "e1"
    coordinator.custom_effects = {
        "e1": CustomEffect(id="e1", display_name=name_key.title(), name_key=name_key, content=content)
    }


async def test_setup_adds_single_image_entity(hass, h617a):
    add = MagicMock()
    await async_setup_entry(hass, MagicMock(runtime_data=h617a), add)
    entities = add.call_args.args[0]
    assert len(entities) == 1 and isinstance(entities[0], GoveeEffectPreviewImage)


def test_resolve_look_colour_from_segment_colours(h617a):
    h617a.segment_colors = [(1, 2, 3)] * h617a.profile.segment_count
    look_id, look = _resolve_look(h617a)
    assert look_id == "colour"
    assert isinstance(look, SegmentContent)
    assert look.colors == tuple(h617a.segment_colors)


def test_resolve_look_scene(h617a):
    name = get_scene_names()[0]
    h617a.effect = name
    look_id, look = _resolve_look(h617a)
    assert look is SCENES[name]
    assert look_id == f"scene:{SCENES[name].code}"


def test_resolve_look_custom_content(h617a):
    content = SketchContent(motion=0x09, colors=((255, 0, 0),))
    _make_custom(h617a, content, name_key="flame")
    look_id, look = _resolve_look(h617a)
    assert look is content
    assert look_id == "custom:e1:flame"


def test_resolve_look_custom_missing_falls_back_to_colour(h617a):
    h617a.active_custom_id, h617a.custom_effects = "ghost", {}
    look_id, look = _resolve_look(h617a)
    assert look_id == "colour" and isinstance(look, SegmentContent)


async def test_async_image_returns_bytes_and_caches_by_key(entity, h617a, monkeypatch):
    calls: list[tuple[int, bool]] = []
    real = preview.render_preview_image

    def counted(look: object, segment_count: int, reduce_motion: bool) -> preview.PreviewImage:
        calls.append((segment_count, reduce_motion))
        return real(look, segment_count, reduce_motion)

    monkeypatch.setattr(preview, "render_preview_image", counted)
    first = await entity.async_image()
    second = await entity.async_image()
    assert first is not None and first == second
    assert len(calls) == 1  # second fetch served from the hass.data cache
    assert entity.content_type == "image/png"  # a static colour look is a single still


async def test_async_image_animated_look_is_gif(entity, h617a):
    _make_custom(h617a, _TWINKLE, name_key="tw")
    h617a.preview_reduce_motion = False
    data = await entity.async_image()
    assert data is not None and data[:4] == b"GIF8"
    assert entity.content_type == "image/gif"


async def test_async_image_reduce_motion_is_single_png(entity, h617a):
    _make_custom(h617a, _TWINKLE, name_key="tw")
    h617a.preview_reduce_motion = True
    data = await entity.async_image()
    assert data is not None and data[:4] == b"\x89PNG"
    assert entity.content_type == "image/png"


def test_image_last_updated_bumps_on_look_change(entity, h617a, monkeypatch):
    before = entity.image_last_updated
    future = before + timedelta(seconds=5)
    monkeypatch.setattr(image.dt_util, "utcnow", lambda: future)
    h617a.effect = get_scene_names()[0]  # colour -> scene
    entity._handle_coordinator_update()
    assert entity.image_last_updated == future
    entity.async_write_ha_state.assert_called_once()


def test_image_last_updated_bumps_on_reduce_motion_toggle(entity, h617a, monkeypatch):
    before = entity.image_last_updated
    future = before + timedelta(seconds=5)
    monkeypatch.setattr(image.dt_util, "utcnow", lambda: future)
    h617a.preview_reduce_motion = True
    entity._handle_coordinator_update()
    assert entity.image_last_updated == future


def test_image_last_updated_stable_on_unrelated_update(entity, h617a, monkeypatch):
    before = entity.image_last_updated
    monkeypatch.setattr(image.dt_util, "utcnow", lambda: before + timedelta(seconds=5))
    h617a.brightness_pct = 42  # not part of the look key
    entity._handle_coordinator_update()
    assert entity.image_last_updated == before  # no bump
    entity.async_write_ha_state.assert_called_once()  # still refreshes availability


def test_device_info_hides_mac_and_ble_name(entity, h617a):
    info = entity.device_info
    assert info is not None
    assert not info.get("connections")  # the BLE MAC must not surface in the device UI
    assert info.get("name") == "Govee H617A"  # a friendly model name, not a MAC or BLE local name


def test_entity_metadata(entity, h617a):
    assert entity.unique_id == "aabbccddeeff_effect_preview"
    assert entity.translation_key == "effect_preview"
    assert entity.entity_category is not None
