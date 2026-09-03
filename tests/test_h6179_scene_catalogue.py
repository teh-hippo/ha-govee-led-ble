import json
from collections import Counter
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.ha_govee_led_ble.const import EFFECT_CATEGORY_SCENES
from custom_components.ha_govee_led_ble.effect_domain import EffectValidationError
from custom_components.ha_govee_led_ble.effect_scene_defaults import NativeSceneDefault
from custom_components.ha_govee_led_ble.effect_scenes import (
    async_apply_scene,
    async_set_scene_default,
    scene_catalogue_payload,
    scene_detail_payload,
)
from custom_components.ha_govee_led_ble.effect_selector import effect_selector_entries
from custom_components.ha_govee_led_ble.native_scenes import build_native_scene_packets
from custom_components.ha_govee_led_ble.scenes import (
    MODEL_SCENE_LABELS,
    MODEL_SCENES,
    SCENE_ENTRIES,
    _build_scene_keys_by_code,
    scene_key_for_code,
    scene_selector_code,
)
from custom_components.ha_govee_led_ble.transport import xor_checksum

CATALOGUE_PATH = (
    Path(__file__).parents[1] / "custom_components" / "ha_govee_led_ble" / "scene_catalogues" / "H6179.json"
)
TIMESTAMP = "2026-08-17T00:00:00Z"


def _selector_frame(code: int) -> bytes:
    packet = bytearray((0x33, 0x05, 0x04, code))
    packet.extend(bytes(19 - len(packet)))
    packet.append(xor_checksum(packet))
    return bytes(packet)


def test_h6179_generated_catalogue_is_the_complete_exact_sku_snapshot() -> None:
    raw = CATALOGUE_PATH.read_bytes()
    catalogue = json.loads(raw)
    effects = catalogue["effects"]

    assert sha256(raw).hexdigest() == "880e8845aa35c2f331afccdb451f9d4c34ee21ac1b5f943d2116e090602f942e"
    assert set(catalogue) == {"schema_version", "sku", "categories", "effects"}
    assert catalogue["schema_version"] == 1
    assert catalogue["sku"] == "H6179"
    assert catalogue["categories"] == [
        {"id": 1, "name": "Natural"},
        {"id": 2, "name": "Festival"},
        {"id": 3, "name": "Life"},
        {"id": 4, "name": "Emotion"},
    ]
    assert len(effects) == 83
    assert len({effect["scene_id"] for effect in effects}) == 82
    assert len({(effect["scene_id"], effect["effect_id"]) for effect in effects}) == 83
    assert Counter(effect["scene_type"] for effect in effects) == {0: 9, 1: 74}
    assert all("param" not in effect for effect in effects if effect["scene_type"] == 0)
    assert all(effect.get("param") for effect in effects if effect["scene_type"] == 1)

    codes = [effect["code"] for effect in effects]
    selectors = [code & 0xFF for code in codes]
    assert len(codes) == len(set(codes)) == 83
    assert len(set(selectors)) == 83
    assert sum(code > 0xFF for code in codes) == 19


def test_h6179_selector_labels_and_reverse_lookup_cover_every_exact_code() -> None:
    scenes = MODEL_SCENES["H6179"]
    labels = MODEL_SCENE_LABELS["H6179"]
    selector_codes = {scene_selector_code("H6179", scene) for scene in scenes.values()}

    assert len(scenes) == len(labels) == len(selector_codes) == 83
    assert len(set(labels.values())) == 83
    assert "dynamic 1" not in scenes
    assert scenes["sunrise"].scene_id == 49
    assert labels["sunrise"] == "Sunrise"
    assert labels["sweet [life, 82:79]"] == "Sweet [Life, 82:79]"
    assert labels["sweet [life, 245:225]"] == "Sweet [Life, 245:225]"
    assert all(scene_key_for_code("H6179", scene_selector_code("H6179", scene)) == key for key, scene in scenes.items())

    unknown = next(code for code in range(0x100) if code not in selector_codes)
    assert scene_key_for_code("H6179", unknown) is None
    assert scene_key_for_code("H6179", 0x1234) is None
    assert scene_key_for_code("H617A", 0x04) == "movie"


def test_h6179_selector_transport_uses_the_low_byte_without_changing_catalogue_identity() -> None:
    karst_cave = next(scene for scene in SCENE_ENTRIES["H6179"] if scene.name == "Karst Cave")
    downpour = next(scene for scene in SCENE_ENTRIES["H6179"] if scene.name == "Downpour")
    boundary = replace(SCENE_ENTRIES["H6179"][0], code=0x1FF)

    assert karst_cave.code == 1019
    assert scene_selector_code("H6179", karst_cave) == 251
    assert downpour.code == 1215
    assert scene_selector_code("H6179", downpour) == 191
    assert scene_selector_code("H6179", SCENE_ENTRIES["H6179"][0]) == 0
    assert scene_selector_code("H6179", boundary) == 0xFF


def test_h6179_reverse_map_rejects_a_synthetic_low_byte_collision() -> None:
    first = SCENE_ENTRIES["H6179"][0]
    collision = replace(SCENE_ENTRIES["H6179"][1], code=first.code + 0x100)

    with pytest.raises(ValueError, match="share selector 0x00"):
        _build_scene_keys_by_code(
            "H6179",
            {"first": first, "collision": collision},
        )


def test_h6179_standard_effect_selector_exposes_83_unique_labels() -> None:
    entries = effect_selector_entries(
        "H6179",
        frozenset({EFFECT_CATEGORY_SCENES}),
        (),
        prefix_effect_names=False,
    )

    assert len(entries) == 83
    assert len({entry.display_label.casefold() for entry in entries}) == 83
    assert {entry.value for entry in entries} == set(MODEL_SCENES["H6179"])


def test_every_h6179_scene_builds_one_selector_and_never_an_upload() -> None:
    with patch(
        "custom_components.ha_govee_led_ble.native_scenes.build_h6179_scene",
        side_effect=_selector_frame,
    ) as build_selector:
        for scene in SCENE_ENTRIES["H6179"]:
            code = scene_selector_code("H6179", scene)
            packets = build_native_scene_packets("H6179", scene)

            assert packets == [_selector_frame(code)]
            assert not packets[0].startswith((b"\xa1", b"\xa3"))

    assert build_selector.call_count == 83


@pytest.mark.parametrize("scene_type", [0, 1])
def test_h6179_scene_detail_is_read_only_builtin_selection(scene_type: int) -> None:
    entry = next(scene for scene in SCENE_ENTRIES["H6179"] if scene.scene_type == scene_type)
    detail = scene_detail_payload("H6179", entry.scene_id, entry.effect_id)
    content = cast(dict[str, Any], detail["content"])
    summary = cast(dict[str, Any], detail["scene"])

    assert content == detail["catalogue_content"]
    assert content == {
        "kind": "scene_builtin",
        "template": {
            "sku": "H6179",
            "scene_id": entry.scene_id,
            "effect_id": entry.effect_id,
            "catalogue_schema_version": 1,
        },
        "speed_index": None,
    }
    assert detail["has_default"] is False
    assert summary["scene_type"] == 0
    assert summary["parameter_kind"] == "none"
    assert summary["speed"] is None


def test_h6179_scene_browser_lists_all_generated_names_categories_and_identities() -> None:
    payload = scene_catalogue_payload("H6179")
    summaries = cast(list[dict[str, Any]], payload["scenes"])

    assert payload["categories"] == [
        {"id": 1, "name": "Natural"},
        {"id": 2, "name": "Festival"},
        {"id": 3, "name": "Life"},
        {"id": 4, "name": "Emotion"},
    ]
    assert len(summaries) == 83
    assert {
        (summary["scene_id"], summary["effect_id"], summary["name"], summary["category"]) for summary in summaries
    } == {(entry.scene_id, entry.effect_id, entry.name, entry.category) for entry in SCENE_ENTRIES["H6179"]}
    assert all(summary["parameter_kind"] == "none" and summary["speed"] is None for summary in summaries)


def test_h6179_selector_rejects_authored_speed_and_body_before_encoding() -> None:
    scene = next(entry for entry in SCENE_ENTRIES["H6179"] if entry.scene_type == 1)

    with patch("custom_components.ha_govee_led_ble.native_scenes.build_h6179_scene") as build_selector:
        with pytest.raises(ValueError, match="speed_index"):
            build_native_scene_packets("H6179", scene, speed_index=0)
        with pytest.raises(ValueError, match="canonical_body"):
            build_native_scene_packets("H6179", scene, canonical_body=b"\x01")

    build_selector.assert_not_called()


async def test_h6179_scene_application_rejects_authored_edits_before_ble_io(
    hass: HomeAssistant,
) -> None:
    scene = next(entry for entry in SCENE_ENTRIES["H6179"] if entry.scene_type == 1)
    coordinator = SimpleNamespace(model="H6179", async_apply_native_scene=AsyncMock())
    config_entry = SimpleNamespace(entry_id="entry-79", runtime_data=coordinator)

    with pytest.raises(ValueError, match="speed_index"):
        await async_apply_scene(
            hass,
            config_entry,
            scene_id=scene.scene_id,
            effect_id=scene.effect_id,
            speed_index=0,
            user_id="admin",
        )

    scene_default = NativeSceneDefault(
        config_entry_id="entry-79",
        scene_id=scene.scene_id,
        effect_id=scene.effect_id,
        updated_at=TIMESTAMP,
        canonical_body=b"\x01",
    )
    defaults = SimpleNamespace(get=MagicMock(return_value=scene_default))
    with pytest.raises(ValueError, match="canonical_body"):
        await async_apply_scene(
            hass,
            config_entry,
            scene_id=scene.scene_id,
            effect_id=scene.effect_id,
            speed_index=None,
            user_id="admin",
            scene_defaults=defaults,
        )

    coordinator.async_apply_native_scene.assert_not_awaited()


async def test_h6179_scene_application_forwards_only_the_selector_identity(
    hass: HomeAssistant,
) -> None:
    scene = next(entry for entry in SCENE_ENTRIES["H6179"] if entry.scene_type == 1)
    coordinator = SimpleNamespace(model="H6179", async_apply_native_scene=AsyncMock())
    config_entry = SimpleNamespace(entry_id="entry-79", runtime_data=coordinator)

    resolved, speed_index = await async_apply_scene(
        hass,
        config_entry,
        scene_id=scene.scene_id,
        effect_id=scene.effect_id,
        speed_index=None,
        user_id="admin",
    )

    assert resolved.entry == scene
    assert speed_index is None
    coordinator.async_apply_native_scene.assert_awaited_once_with(
        resolved.key,
        speed_index=None,
        canonical_body=None,
    )


async def test_h6179_scene_default_cannot_be_saved() -> None:
    scene = next(entry for entry in SCENE_ENTRIES["H6179"] if entry.scene_type == 1)
    coordinator = SimpleNamespace(model="H6179", async_apply_native_scene=AsyncMock())
    config_entry = SimpleNamespace(entry_id="entry-79", runtime_data=coordinator)
    defaults = SimpleNamespace(async_set=AsyncMock(), async_delete=AsyncMock())
    content = cast(dict[str, Any], scene_detail_payload("H6179", scene.scene_id, scene.effect_id)["content"])

    with pytest.raises(EffectValidationError, match="selector-only"):
        await async_set_scene_default(
            config_entry,
            scene_id=scene.scene_id,
            effect_id=scene.effect_id,
            content=content,
            updated_at=TIMESTAMP,
            scene_defaults=defaults,
        )

    defaults.async_set.assert_not_awaited()
    defaults.async_delete.assert_not_awaited()
    coordinator.async_apply_native_scene.assert_not_awaited()


def test_h6179_scene_detail_rejects_a_canonical_body_default() -> None:
    scene = next(entry for entry in SCENE_ENTRIES["H6179"] if entry.scene_type == 1)
    scene_default = NativeSceneDefault(
        config_entry_id="entry-79",
        scene_id=scene.scene_id,
        effect_id=scene.effect_id,
        updated_at=TIMESTAMP,
        canonical_body=b"\x01",
    )

    with pytest.raises(ValueError, match="canonical-body"):
        scene_detail_payload(
            "H6179",
            scene.scene_id,
            scene.effect_id,
            scene_default=scene_default,
        )
