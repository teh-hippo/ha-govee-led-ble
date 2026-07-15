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
    content_to_dict,
)
from custom_components.ha_govee_led_ble.protocol import DEFAULT_DIY_SLOT, build_custom_effect

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
    assert coord.diy_slot is None
    assert coord.music_mode == "off" and coord.video_mode == "off"
    assert coord.active_mode == "custom"


async def test_apply_diy_sets_default_slot_and_runtime_ownership(hass, hass_storage):
    coord = _coord(hass, "apply_diy")
    await coord.async_load_effects()
    eid = await coord.async_save_effect("Vibrant", _vibrant(8))
    with patch.object(coord, "send_command", new_callable=AsyncMock):
        await coord.async_apply_custom_effect(eid)
    assert coord.diy_slot == DEFAULT_DIY_SLOT
    assert coord._owned_diy_effect_id == eid


async def test_apply_unknown_id_raises(hass, hass_storage):
    coord = _coord(hass, "apply_unknown")
    await coord.async_load_effects()
    with pytest.raises(EffectValidationError) as exc:
        await coord.async_apply_custom_effect("deadbeef")
    assert exc.value.key == "unknown_effect"


async def test_load_quarantines_content_that_no_longer_validates(hass, hass_storage):
    key = effect_store_key("invalid_combo")
    hass_storage[key] = {
        "version": 2,
        "minor_version": 1,
        "key": key,
        "data": {
            "effects": {
                "aaaa1111": {
                    "display_name": "Legacy Combo",
                    "name_key": "legacy combo",
                    "content": {
                        "kind": "combo",
                        "variant": 0,
                        "speed": 50,
                        "palette": [[255, 0, 0]],
                        "effects": [[4, 6]],
                    },
                }
            }
        },
    }
    coord = _coord(hass, "invalid_combo")
    await coord.async_load_effects()

    assert coord.custom_effect_index() == {}
    assert coord.quarantined_custom_effect_index() == {"aaaa1111": "Legacy Combo"}
    with pytest.raises(EffectValidationError) as exc:
        await coord.async_apply_custom_effect("aaaa1111")
    assert exc.value.key == "combo_family_variant_invalid"


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


async def test_h6199_rejects_unvalidated_segment_effect(hass, hass_storage):
    coord = _coord(hass, "scene6199", "H6199")
    await coord.async_load_effects()
    with pytest.raises(EffectValidationError) as exc:
        await coord.async_save_effect("Sunset", SegmentContent(colors=((255, 0, 0),)))
    assert exc.value.key == "segments_unsupported"


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


async def test_apply_rejects_stored_diy_when_unsupported(hass, hass_storage):
    coord = _coord(hass, "gate_apply")
    await coord.async_load_effects()
    eid = await coord.async_save_effect("Vibe", _vibrant(1))
    coord.profile = replace(coord.profile, supports_diy=False)
    send = AsyncMock()
    with patch.object(coord, "send_command", send), pytest.raises(EffectValidationError) as exc:
        await coord.async_apply_custom_effect(eid)
    assert exc.value.key == "diy_unsupported"
    send.assert_not_awaited()


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
# Update: stable id, name/content edits, validation and scene-shadow reconcile
# --------------------------------------------------------------------------- #
async def test_update_preserves_id_and_changes_name_and_content(hass, hass_storage):
    coord = _coord(hass, "upd_both")
    await coord.async_load_effects()
    eid = await coord.async_save_effect("Alpha", _vibrant(1))

    await coord.async_update_effect(eid, display_name="Beta", content=_vibrant(2))
    assert list(coord.custom_effects) == [eid]  # id stable, no new entry created
    effect = coord.custom_effects[eid]
    assert (effect.display_name, effect.name_key, effect.content) == ("Beta", "beta", _vibrant(2))

    reopened = _coord(hass, "upd_both")
    await reopened.async_load_effects()
    assert reopened.custom_effects[eid].display_name == "Beta"
    assert reopened.custom_effects[eid].content == _vibrant(2)


async def test_update_name_only_trims_and_keeps_content(hass, hass_storage):
    coord = _coord(hass, "upd_name")
    await coord.async_load_effects()
    eid = await coord.async_save_effect("Alpha", _vibrant(3))
    await coord.async_update_effect(eid, display_name="  Gamma  ")
    effect = coord.custom_effects[eid]
    assert (effect.display_name, effect.name_key) == ("Gamma", "gamma")
    assert effect.content == _vibrant(3)  # untouched


async def test_update_content_only_keeps_name(hass, hass_storage):
    coord = _coord(hass, "upd_content")
    await coord.async_load_effects()
    eid = await coord.async_save_effect("Alpha", _vibrant(1))
    await coord.async_update_effect(eid, content=SegmentContent(colors=((1, 2, 3),)))
    effect = coord.custom_effects[eid]
    assert effect.display_name == "Alpha"  # untouched
    assert effect.content == SegmentContent(colors=((1, 2, 3),))


async def test_update_active_effect_relabels_display(hass, hass_storage):
    coord = _coord(hass, "upd_active")
    await coord.async_load_effects()
    eid = await coord.async_save_effect("My Reds", SegmentContent(colors=((255, 0, 0),)))
    with patch.object(coord, "send_command", AsyncMock()):
        await coord.async_apply_custom_effect(eid)
    assert coord.active_custom_id == eid

    await coord.async_update_effect(eid, display_name="Crimson", content=SegmentContent(colors=((200, 0, 0),)))
    assert coord.active_custom_id == eid  # id stays active
    assert coord.effect == "Crimson"  # active display relabelled
    assert coord.custom_effects[eid].content == SegmentContent(colors=((200, 0, 0),))


async def test_update_inactive_effect_leaves_active_state(hass, hass_storage):
    coord = _coord(hass, "upd_inactive")
    await coord.async_load_effects()
    active = await coord.async_save_effect("Active", _vibrant(1))
    other = await coord.async_save_effect("Other", _vibrant(2))
    with patch.object(coord, "send_command", AsyncMock()):
        await coord.async_apply_custom_effect(active)

    await coord.async_update_effect(other, display_name="Renamed Other")
    assert coord.active_custom_id == active
    assert coord.effect == "Active"  # untouched


async def test_update_requires_name_or_content(hass, hass_storage):
    coord = _coord(hass, "upd_empty")
    await coord.async_load_effects()
    eid = await coord.async_save_effect("Alpha", _vibrant(1))
    with pytest.raises(EffectValidationError) as exc:
        await coord.async_update_effect(eid)
    assert exc.value.key == "update_needs_name_or_content"


async def test_update_unknown_id_raises(hass, hass_storage):
    coord = _coord(hass, "upd_unknown")
    await coord.async_load_effects()
    with pytest.raises(EffectValidationError) as exc:
        await coord.async_update_effect("deadbeef", display_name="X")
    assert exc.value.key == "unknown_effect"


async def test_update_resolves_by_exact_id_only(hass, hass_storage):
    """Update never resolves by name key; passing a name as the id is unknown."""
    coord = _coord(hass, "upd_exact")
    await coord.async_load_effects()
    await coord.async_save_effect("Alpha", _vibrant(1))
    with pytest.raises(EffectValidationError) as exc:
        await coord.async_update_effect("alpha", display_name="Beta")
    assert exc.value.key == "unknown_effect"


async def test_update_rejects_duplicate_name(hass, hass_storage):
    coord = _coord(hass, "upd_dup")
    await coord.async_load_effects()
    await coord.async_save_effect("Alpha", _vibrant(1))
    beta = await coord.async_save_effect("Beta", _vibrant(2))
    with pytest.raises(EffectValidationError) as exc:
        await coord.async_update_effect(beta, display_name="  ALPHA ")
    assert exc.value.key == "duplicate_name"


async def test_update_allows_reusing_own_name(hass, hass_storage):
    """Re-supplying the effect's own name during a content edit must not trip duplicate detection."""
    coord = _coord(hass, "upd_samename")
    await coord.async_load_effects()
    eid = await coord.async_save_effect("Alpha", _vibrant(1))
    await coord.async_update_effect(eid, display_name="Alpha", content=_vibrant(5))
    assert coord.custom_effects[eid].content == _vibrant(5)


async def test_update_rejects_invalid_content(hass, hass_storage):
    coord = _coord(hass, "upd_invalid")
    await coord.async_load_effects()
    eid = await coord.async_save_effect("Alpha", _vibrant(1))
    with pytest.raises(EffectValidationError) as exc:
        await coord.async_update_effect(eid, content=SegmentContent(colors=((1, 1, 1),) * 16))
    assert exc.value.key == "too_many_segments"


async def test_update_rejects_unsupported_content(hass, hass_storage):
    coord = _coord(hass, "upd_unsupported")
    await coord.async_load_effects()
    eid = await coord.async_save_effect("Alpha", _vibrant(1))
    coord.profile = replace(coord.profile, supports_diy=False)
    with pytest.raises(EffectValidationError) as exc:
        await coord.async_update_effect(eid, content=_vibrant(2))
    assert exc.value.key == "diy_unsupported"


async def test_update_rejects_unknown_kind_content(hass, hass_storage):
    coord = _coord(hass, "upd_unknownkind")
    await coord.async_load_effects()
    eid = await coord.async_save_effect("Alpha", _vibrant(1))
    with pytest.raises(EffectValidationError) as exc:
        await coord.async_update_effect(eid, content=UnknownContent(kind="future_kind", raw={}))
    assert exc.value.key == "unknown_kind_not_saveable"


async def test_update_content_of_shadow_effect_keeps_issue(hass, hass_storage):
    """A stored effect that shadows a scene keeps its repair issue when only content changes."""
    key = effect_store_key("upd_shadow_keep")
    hass_storage[key] = {
        "version": 2,
        "minor_version": 1,
        "key": key,
        "data": {
            "effects": {
                "aaaa1111": {
                    "display_name": "Sunset",
                    "name_key": "sunset",
                    "content": {"kind": "vibrant", "stops": [[0, 0, 0], [1, 1, 1]]},
                }
            }
        },
    }
    coord = _coord(hass, "upd_shadow_keep")
    await coord.async_load_effects()

    await coord.async_update_effect("aaaa1111", content=_vibrant(4))
    issues = ir.async_get(hass).issues
    shadow = [i for i in issues.values() if i.translation_key == "custom_effect_scene_shadow"]
    assert len(shadow) == 1  # still shadowing a scene
    assert shadow[0].translation_placeholders == {"effect": "Sunset"}


async def test_update_name_off_scene_clears_shadow_issue(hass, hass_storage):
    """Renaming a shadow effect off the scene name via update clears its repair issue."""
    key = effect_store_key("upd_shadow_clear")
    hass_storage[key] = {
        "version": 2,
        "minor_version": 1,
        "key": key,
        "data": {
            "effects": {
                "bbbb2222": {
                    "display_name": "Sunset",
                    "name_key": "sunset",
                    "content": {"kind": "vibrant", "stops": [[0, 0, 0], [1, 1, 1]]},
                }
            }
        },
    }
    coord = _coord(hass, "upd_shadow_clear")
    await coord.async_load_effects()
    assert any(i.translation_key == "custom_effect_scene_shadow" for i in ir.async_get(hass).issues.values())

    await coord.async_update_effect("bbbb2222", display_name="Dawn")
    shadow = [i for i in ir.async_get(hass).issues.values() if i.translation_key == "custom_effect_scene_shadow"]
    assert shadow == []  # cleared


# --------------------------------------------------------------------------- #
# Export: portable payload shape and exact-id resolution
# --------------------------------------------------------------------------- #
async def test_export_returns_full_payload(hass, hass_storage):
    content = SegmentContent(colors=((255, 0, 0), None))
    key = effect_store_key("exp")
    hass_storage[key] = {
        "version": 2,
        "minor_version": 1,
        "key": key,
        "data": {
            "effects": {
                "a1b2c3d4": {
                    "display_name": "My Reds",
                    "name_key": "my reds",
                    "content": content_to_dict(content),
                }
            }
        },
    }
    coord = _coord(hass, "exp", "H6199")
    await coord.async_load_effects()

    assert await coord.async_export_effect("a1b2c3d4") == {
        "id": "a1b2c3d4",
        "name": "My Reds",
        "model": "H6199",
        "segment_count": 15,
        "content": content_to_dict(content),
    }


async def test_export_serialises_unknown_content(hass, hass_storage):
    """Export is not capability-gated; it serialises even unknown-kind content verbatim."""
    key = effect_store_key("exp_unknown_content")
    hass_storage[key] = {
        "version": 2,
        "minor_version": 1,
        "key": key,
        "data": {
            "effects": {
                "eeee5555": {
                    "display_name": "Future FX",
                    "name_key": "future fx",
                    "content": {"kind": "future_kind", "foo": 1},
                }
            }
        },
    }
    coord = _coord(hass, "exp_unknown_content", "H6199")
    await coord.async_load_effects()
    payload = await coord.async_export_effect("eeee5555")
    assert payload["name"] == "Future FX"
    assert payload["content"] == {"kind": "future_kind", "foo": 1}


async def test_export_unknown_id_raises(hass, hass_storage):
    coord = _coord(hass, "exp_unknown")
    await coord.async_load_effects()
    with pytest.raises(EffectValidationError) as exc:
        await coord.async_export_effect("deadbeef")
    assert exc.value.key == "unknown_effect"


async def test_export_resolves_by_exact_id_only(hass, hass_storage):
    coord = _coord(hass, "exp_exact")
    await coord.async_load_effects()
    await coord.async_save_effect("Alpha", _vibrant(1))
    with pytest.raises(EffectValidationError) as exc:
        await coord.async_export_effect("alpha")
    assert exc.value.key == "unknown_effect"


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


async def test_unsupported_effects_are_quarantined_but_exportable(hass, hass_storage):
    coord = _coord(hass, "quarantine")
    await coord.async_load_effects()
    static = await coord.async_save_effect("Static", SegmentContent(colors=((1, 2, 3),)))
    diy = await coord.async_save_effect("Vibe", _vibrant(1))
    coord.profile = replace(coord.profile, supports_diy=False)

    assert coord.custom_effect_index() == {static: "Static"}
    assert coord.custom_effect_display_names() == ["Static"]
    assert coord.quarantined_custom_effect_index() == {diy: "Vibe"}
    assert (await coord.async_export_effect(diy))["name"] == "Vibe"


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
