"""Coordinator-side custom-effect engine: Store, CRUD, sticky apply and capability gating."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.helpers import issue_registry as ir

from custom_components.ha_govee_led_ble import async_remove_entry
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_effects import build_effect_store, effect_store_key
from custom_components.ha_govee_led_ble.custom_effects import (
    EffectValidationError,
    SegmentContent,
    UnknownContent,
    VibrantContent,
)
from custom_components.ha_govee_led_ble.protocol import build_custom_effect

_ADDR = {"H617A": "AA:BB:CC:DD:EE:FF", "H6199": "11:22:33:44:55:66"}


def _coord(hass, entry_id: str, model: str = "H617A") -> GoveeBLECoordinator:
    coord = GoveeBLECoordinator(hass, _ADDR[model], model)
    coord.attach_effect_store(build_effect_store(hass, entry_id))
    return coord


def _vibrant(offset: int = 0) -> VibrantContent:
    return VibrantContent(stops=((0, 0, 0), (offset, offset, offset)))


# --------------------------------------------------------------------------- #
# CRUD round-trip + persistence through a real Store
# --------------------------------------------------------------------------- #
async def test_crud_roundtrip_persists(hass, hass_storage):
    coord = _coord(hass, "crud")
    await coord.async_load_effects()
    assert coord.custom_effects == {}

    eid = await coord.async_save_effect("Stripey Sunset ", SegmentContent(colors=((255, 120, 0), None)))
    assert coord.custom_effects[eid].display_name == "Stripey Sunset"  # trailing space stripped
    assert coord.custom_effects[eid].name_key == "stripey sunset"

    reopened = _coord(hass, "crud")
    await reopened.async_load_effects()
    assert eid in reopened.custom_effects
    assert reopened.custom_effects[eid].content == SegmentContent(colors=((255, 120, 0), None))

    await reopened.async_rename_effect(eid, "Dawn")
    assert reopened.custom_effects[eid].display_name == "Dawn"
    assert reopened.custom_effects[eid].name_key == "dawn"

    await reopened.async_delete_effect(eid)
    assert eid not in reopened.custom_effects

    final = _coord(hass, "crud")
    await final.async_load_effects()
    assert final.custom_effects == {}


# --------------------------------------------------------------------------- #
# Sticky apply
# --------------------------------------------------------------------------- #
async def test_apply_sets_sticky_and_sends_packets(hass, hass_storage):
    coord = _coord(hass, "apply")
    await coord.async_load_effects()
    content = SegmentContent(colors=((255, 0, 0), (0, 255, 0)))
    eid = await coord.async_save_effect("My Reds", content)
    coord.is_on = True
    coord.music_mode, coord.video_mode = "energetic", "off"

    send = AsyncMock()
    with patch.object(coord, "send_command", send):
        await coord.async_apply_custom_effect(eid)

    sent = [call.args[0] for call in send.await_args_list]
    assert sent == build_custom_effect(content, segment_count=15)
    assert sent  # non-empty: packets were actually written
    assert coord.active_custom_id == eid
    assert coord.effect == "My Reds"
    assert coord.music_mode == "off" and coord.video_mode == "off"
    assert coord.active_mode == "custom"


async def test_apply_unknown_id_raises(hass, hass_storage):
    coord = _coord(hass, "apply_unknown")
    await coord.async_load_effects()
    with pytest.raises(EffectValidationError) as exc:
        await coord.async_apply_custom_effect("deadbeef")
    assert exc.value.key == "unknown_effect"


# --------------------------------------------------------------------------- #
# Store migration v1 -> v2
# --------------------------------------------------------------------------- #
async def test_store_migrates_v1_to_v2(hass, hass_storage):
    key = effect_store_key("mig")
    hass_storage[key] = {
        "version": 1,
        "minor_version": 1,
        "key": key,
        "data": {
            "effects": {
                "aaaa1111": {"name": "Sunset Stripes", "content": {"kind": "segments", "colors": [[255, 120, 0]]}},
            }
        },
    }
    data = await build_effect_store(hass, "mig").async_load()
    effect = data["effects"]["aaaa1111"]
    assert effect["display_name"] == "Sunset Stripes"
    assert effect["name_key"] == "sunset stripes"
    assert "name" not in effect
    assert hass_storage[key]["version"] == 2  # migrated file rewritten at v2


async def test_load_effects_applies_migration(hass, hass_storage):
    key = effect_store_key("mig2")
    hass_storage[key] = {
        "version": 1,
        "minor_version": 1,
        "key": key,
        "data": {
            "effects": {
                "bbbb2222": {"name": "My Vibe", "content": {"kind": "vibrant", "stops": [[0, 0, 0], [255, 255, 255]]}},
            }
        },
    }
    coord = _coord(hass, "mig2")
    await coord.async_load_effects()
    effect = coord.custom_effects["bbbb2222"]
    assert effect.display_name == "My Vibe"
    assert effect.name_key == "my vibe"
    assert isinstance(effect.content, VibrantContent)


# --------------------------------------------------------------------------- #
# Concurrency: the store lock serialises overlapping saves (no lost effect)
# --------------------------------------------------------------------------- #
async def test_store_lock_serialises_saves(hass, hass_storage):
    coord = _coord(hass, "conc")
    await coord.async_load_effects()
    names = [f"Custom {i}" for i in range(1, 7)]
    await asyncio.gather(*(coord.async_save_effect(name, _vibrant(i)) for i, name in enumerate(names, start=1)))
    assert len(coord.custom_effects) == 6
    assert {effect.display_name for effect in coord.custom_effects.values()} == set(names)

    reopened = _coord(hass, "conc")
    await reopened.async_load_effects()
    assert len(reopened.custom_effects) == 6


# --------------------------------------------------------------------------- #
# Validation: name + content + scene collision
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", ["", "   ", '  "" '])
async def test_save_rejects_empty_name(hass, hass_storage, name):
    coord = _coord(hass, "empty")
    await coord.async_load_effects()
    with pytest.raises(EffectValidationError) as exc:
        await coord.async_save_effect(name, _vibrant(1))
    assert exc.value.key == "empty_name"


async def test_save_rejects_duplicate_name(hass, hass_storage):
    coord = _coord(hass, "dup")
    await coord.async_load_effects()
    await coord.async_save_effect("My Vibe", _vibrant(1))
    with pytest.raises(EffectValidationError) as exc:
        await coord.async_save_effect("  MY   vibe  ", _vibrant(2))
    assert exc.value.key == "duplicate_name"


async def test_save_rejects_scene_collision(hass, hass_storage):
    coord = _coord(hass, "scene")
    await coord.async_load_effects()
    with pytest.raises(EffectValidationError) as exc:
        await coord.async_save_effect("Sunset", SegmentContent(colors=((255, 0, 0),)))
    assert exc.value.key == "scene_name_collision"


async def test_h6199_has_no_scene_collisions(hass, hass_storage):
    coord = _coord(hass, "scene6199", "H6199")
    await coord.async_load_effects()
    eid = await coord.async_save_effect("Sunset", SegmentContent(colors=((255, 0, 0),)))
    assert coord.custom_effects[eid].name_key == "sunset"


async def test_load_flags_stored_scene_collision_with_repair_issue(hass, hass_storage):
    """Legacy/hand-edited storage can hold a custom named like a scene; loading raises a repair issue."""
    key = effect_store_key("shadow")
    hass_storage[key] = {
        "version": 2,
        "minor_version": 1,
        "key": key,
        "data": {
            "effects": {
                "cccc3333": {
                    "display_name": "Sunset",
                    "name_key": "sunset",
                    "content": {"kind": "vibrant", "stops": [[0, 0, 0], [255, 255, 255]]},
                },
                "dddd4444": {
                    "display_name": "My Vibe",
                    "name_key": "my vibe",
                    "content": {"kind": "vibrant", "stops": [[0, 0, 0], [1, 1, 1]]},
                },
            }
        },
    }
    coord = _coord(hass, "shadow")
    await coord.async_load_effects()
    issues = ir.async_get(hass).issues
    shadow_issues = [i for i in issues.values() if i.translation_key == "custom_effect_scene_shadow"]
    assert len(shadow_issues) == 1
    issue = shadow_issues[0]
    assert issue.translation_placeholders == {"effect": "Sunset"}
    assert issue.severity is ir.IssueSeverity.WARNING and issue.is_fixable is False


async def test_save_rejects_invalid_content(hass, hass_storage):
    coord = _coord(hass, "invalid")
    await coord.async_load_effects()
    with pytest.raises(EffectValidationError) as exc:
        await coord.async_save_effect("Too Many", SegmentContent(colors=((1, 1, 1),) * 16))
    assert exc.value.key == "too_many_segments"


async def test_save_requires_content_or_capture(hass, hass_storage):
    coord = _coord(hass, "req")
    await coord.async_load_effects()
    with pytest.raises(EffectValidationError) as exc:
        await coord.async_save_effect("No Content")
    assert exc.value.key == "content_required"


async def test_save_capture_current_snapshots_segments(hass, hass_storage):
    coord = _coord(hass, "capture")
    await coord.async_load_effects()
    coord.segment_colors = [(index, 0, 0) for index in range(15)]
    eid = await coord.async_save_effect("Snapshot", capture_current=True)
    content = coord.custom_effects[eid].content
    assert isinstance(content, SegmentContent)
    assert content.colors == tuple((index, 0, 0) for index in range(15))


# --------------------------------------------------------------------------- #
# Capability gating
# --------------------------------------------------------------------------- #
async def test_save_rejects_diy_when_unsupported(hass, hass_storage):
    coord = _coord(hass, "gate_diy")
    await coord.async_load_effects()
    coord.profile = replace(coord.profile, supports_diy=False)
    with pytest.raises(EffectValidationError) as exc:
        await coord.async_save_effect("Vibe", _vibrant(1))
    assert exc.value.key == "diy_unsupported"


async def test_save_rejects_segments_when_unsupported(hass, hass_storage):
    coord = _coord(hass, "gate_seg")
    await coord.async_load_effects()
    coord.profile = replace(coord.profile, segment_count=0)
    with pytest.raises(EffectValidationError) as exc:
        await coord.async_save_effect("Paint", SegmentContent(colors=((1, 1, 1),)))
    assert exc.value.key == "segments_unsupported"


async def test_save_rejects_unknown_kind(hass, hass_storage):
    coord = _coord(hass, "gate_unknown")
    await coord.async_load_effects()
    with pytest.raises(EffectValidationError) as exc:
        await coord.async_save_effect("Mystery", UnknownContent(kind="future_kind", raw={"foo": 1}))
    assert exc.value.key == "unknown_kind_not_saveable"


# --------------------------------------------------------------------------- #
# Active-effect delete/rename semantics
# --------------------------------------------------------------------------- #
async def test_delete_active_effect_clears_sticky(hass, hass_storage):
    coord = _coord(hass, "del_active")
    await coord.async_load_effects()
    eid = await coord.async_save_effect("My Reds", SegmentContent(colors=((255, 0, 0),)))
    with patch.object(coord, "send_command", AsyncMock()):
        await coord.async_apply_custom_effect(eid)
    assert coord.active_custom_id == eid

    await coord.async_delete_effect(eid)
    assert coord.active_custom_id is None
    assert coord.effect is None


async def test_rename_active_effect_keeps_id_and_relabels(hass, hass_storage):
    coord = _coord(hass, "ren_active")
    await coord.async_load_effects()
    eid = await coord.async_save_effect("My Reds", SegmentContent(colors=((255, 0, 0),)))
    with patch.object(coord, "send_command", AsyncMock()):
        await coord.async_apply_custom_effect(eid)

    await coord.async_rename_effect(eid, "Crimson")
    assert eid in coord.custom_effects  # id stable
    assert coord.active_custom_id == eid
    assert coord.effect == "Crimson"  # active state relabelled
    assert coord.custom_effects[eid].name_key == "crimson"


async def test_rename_resolves_by_name_key_and_rejects_collision(hass, hass_storage):
    coord = _coord(hass, "ren_key")
    await coord.async_load_effects()
    alpha = await coord.async_save_effect("Alpha", _vibrant(1))
    await coord.async_save_effect("Beta", _vibrant(2))

    await coord.async_rename_effect("alpha", "Gamma")
    assert coord.custom_effects[alpha].display_name == "Gamma"

    with pytest.raises(EffectValidationError) as exc:
        await coord.async_rename_effect(alpha, "Beta")
    assert exc.value.key == "duplicate_name"


async def test_delete_and_rename_unknown_raise(hass, hass_storage):
    coord = _coord(hass, "unknown_key")
    await coord.async_load_effects()
    with pytest.raises(EffectValidationError) as delete_exc:
        await coord.async_delete_effect("nope")
    assert delete_exc.value.key == "unknown_effect"
    with pytest.raises(EffectValidationError) as rename_exc:
        await coord.async_rename_effect("nope", "X")
    assert rename_exc.value.key == "unknown_effect"


# --------------------------------------------------------------------------- #
# Resolve / display helpers
# --------------------------------------------------------------------------- #
async def test_resolve_custom_by_id_and_name_key(hass, hass_storage):
    coord = _coord(hass, "resolve")
    await coord.async_load_effects()
    eid = await coord.async_save_effect("My Cool Effect", _vibrant(1))
    assert coord.resolve_custom(eid).id == eid
    assert coord.resolve_custom("my cool effect").id == eid
    assert coord.resolve_custom("  MY   Cool   Effect ").id == eid
    assert coord.resolve_custom("nope") is None


async def test_display_names_and_index_stable_order(hass, hass_storage):
    coord = _coord(hass, "order")
    await coord.async_load_effects()
    bravo = await coord.async_save_effect("Bravo", _vibrant(1))
    alpha = await coord.async_save_effect("Alpha", _vibrant(2))
    assert coord.custom_effect_display_names() == ["Alpha", "Bravo"]
    assert coord.custom_effect_index() == {alpha: "Alpha", bravo: "Bravo"}


# --------------------------------------------------------------------------- #
# UnknownContent is manageable (delete/rename) but never applied
# --------------------------------------------------------------------------- #
async def test_unknown_content_manageable_but_not_appliable(hass, hass_storage):
    key = effect_store_key("unknown_content")
    hass_storage[key] = {
        "version": 2,
        "minor_version": 1,
        "key": key,
        "data": {
            "effects": {
                "cccc3333": {
                    "display_name": "Future FX",
                    "name_key": "future fx",
                    "content": {"kind": "future_kind", "foo": 1},
                }
            }
        },
    }
    coord = _coord(hass, "unknown_content")
    await coord.async_load_effects()
    assert isinstance(coord.custom_effects["cccc3333"].content, UnknownContent)

    with pytest.raises(EffectValidationError) as exc:
        await coord.async_apply_custom_effect("cccc3333")
    assert exc.value.key == "unknown_kind_not_applyable"

    await coord.async_rename_effect("cccc3333", "Renamed FX")
    assert coord.custom_effects["cccc3333"].display_name == "Renamed FX"
    assert isinstance(coord.custom_effects["cccc3333"].content, UnknownContent)  # preserved verbatim

    await coord.async_delete_effect("cccc3333")
    assert "cccc3333" not in coord.custom_effects


# --------------------------------------------------------------------------- #
# Store lifecycle: async_remove_entry deletes the per-entry Store
# --------------------------------------------------------------------------- #
async def test_async_remove_entry_removes_store(hass, hass_storage):
    key = effect_store_key("remove")
    coord = _coord(hass, "remove")
    await coord.async_load_effects()
    await coord.async_save_effect("Persisted", _vibrant(1))
    assert key in hass_storage

    await async_remove_entry(hass, SimpleNamespace(entry_id="remove"))
    assert key not in hass_storage
