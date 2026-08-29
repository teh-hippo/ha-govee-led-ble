"""Native scene editor contracts."""

import base64
import binascii
from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES
from custom_components.ha_govee_led_ble.effect_scene_defaults import NativeSceneDefault, NativeSceneDefaultRepository
from custom_components.ha_govee_led_ble.effect_scenes import (
    async_apply_scene,
    async_reset_scene_default,
    async_set_scene_default,
    resolve_scene,
    scene_catalogue_payload,
    scene_detail_payload,
)
from custom_components.ha_govee_led_ble.native_scenes import resolve_native_scene_body
from custom_components.ha_govee_led_ble.scenes import (
    MODEL_SCENES,
    SCENE_ENTRIES,
)
from tests.storage_test_double import InMemoryVersionedDocumentStore

TIMESTAMP = "2026-08-17T00:00:00Z"


def test_catalogue_and_identity_errors() -> None:
    with pytest.raises(ValueError, match="no native scene catalogue"):
        scene_catalogue_payload("UNKNOWN")

    with pytest.raises(ValueError, match="no native scene catalogue"):
        resolve_scene("UNKNOWN", 0, 0)

    with pytest.raises(ValueError, match="was not found"):
        resolve_scene("H617A", -1, -1)

    assert scene_catalogue_payload("H6199")["enabled"] is True
    h6125 = scene_catalogue_payload("H6125")
    assert h6125["enabled"] is False
    assert cast(list[Any], h6125["scenes"]) == []


def test_layered_scene_detail_decodes_strict_base64_template(monkeypatch) -> None:
    key, entry = next(
        (key, entry) for key, entry in MODEL_SCENES["H617A"].items() if entry.scene_type == 2 and entry.param
    )

    detail = scene_detail_payload("H617A", entry.scene_id, entry.effect_id)
    content = cast(dict[str, Any], detail["content"])

    assert content["kind"] == "scene_layered"
    assert content["template"] == {
        "sku": "H617A",
        "scene_id": entry.scene_id,
        "effect_id": entry.effect_id,
        "catalogue_schema_version": 1,
    }
    assert content["raw_param"] == base64.b64decode(entry.param, validate=True).hex()
    assert content["speed_index"] == (entry.speed.default_index if entry.speed is not None else None)
    assert content["effect"]["layers"]

    monkeypatch.setitem(
        MODEL_SCENES["H617A"],
        key,
        replace(entry, param=f"{entry.param}\n"),
    )
    with pytest.raises(binascii.Error):
        scene_detail_payload("H617A", entry.scene_id, entry.effect_id)


def test_palette_scene_detail_decodes_template() -> None:
    entry = next(scene for scene in SCENE_ENTRIES["H617A"] if scene.scene_type == 1 and scene.param)

    detail = scene_detail_payload("H617A", entry.scene_id, entry.effect_id)
    content = cast(dict[str, Any], detail["content"])

    assert content["kind"] == "scene_palette"
    assert content["template"] == {
        "sku": "H617A",
        "scene_id": entry.scene_id,
        "effect_id": entry.effect_id,
        "catalogue_schema_version": 1,
    }
    assert content["layout"] == 0
    assert content["brightness_flag"] is True
    assert content["steps"]
    assert content["palette"]
    assert content["speed_index"] is None


def test_type_0_scene_detail_remains_builtin() -> None:
    entry = next(scene for scene in SCENE_ENTRIES["H617A"] if scene.scene_type == 0)

    detail = scene_detail_payload("H617A", entry.scene_id, entry.effect_id)
    content = cast(dict[str, Any], detail["content"])

    assert content["kind"] == "scene_builtin"
    assert detail["has_default"] is False


def test_scene_detail_uses_the_device_default_body() -> None:
    entry = next(scene for scene in SCENE_ENTRIES["H617A"] if scene.scene_type == 2 and scene.speed is not None)
    assert entry.speed is not None
    changed_speed = (entry.speed.default_index + 1) % entry.speed.option_count
    body, speed_index = resolve_native_scene_body(entry, speed_index=changed_speed)
    scene_default = NativeSceneDefault(
        config_entry_id="entry-a",
        scene_id=entry.scene_id,
        effect_id=entry.effect_id,
        updated_at=TIMESTAMP,
        canonical_body=body,
        speed_index=speed_index,
    )

    detail = scene_detail_payload(
        "H617A",
        entry.scene_id,
        entry.effect_id,
        scene_default=scene_default,
    )
    content = cast(dict[str, Any], detail["content"])
    catalogue_content = cast(dict[str, Any], detail["catalogue_content"])

    assert detail["has_default"] is True
    assert content["raw_param"] == body.hex()
    assert content["speed_index"] == changed_speed
    assert catalogue_content["raw_param"] != body.hex()
    assert catalogue_content["speed_index"] == entry.speed.default_index


async def test_scene_speed_request_is_validated_before_write(
    hass: HomeAssistant,
) -> None:
    no_speed = next(scene for scene in SCENE_ENTRIES["H617A"] if scene.speed is None)
    with_speed = next(scene for scene in SCENE_ENTRIES["H617A"] if scene.speed is not None)
    coordinator = SimpleNamespace(
        model="H617A",
    )
    entry = SimpleNamespace(entry_id="entry-a", runtime_data=coordinator)

    with pytest.raises(ValueError, match="does not expose"):
        await async_apply_scene(
            hass,
            entry,
            scene_id=no_speed.scene_id,
            effect_id=no_speed.effect_id,
            speed_index=0,
            user_id="admin",
        )

    assert with_speed.speed is not None
    with pytest.raises(ValueError, match="outside"):
        await async_apply_scene(
            hass,
            entry,
            scene_id=with_speed.scene_id,
            effect_id=with_speed.effect_id,
            speed_index=with_speed.speed.option_count,
            user_id="admin",
        )


async def test_scene_without_speed_uses_coordinator_primitive(
    hass: HomeAssistant,
) -> None:
    scene = next(item for item in SCENE_ENTRIES["H617A"] if item.speed is None)
    coordinator = SimpleNamespace(
        model="H617A",
        profile=MODEL_PROFILES["H617A"],
        async_apply_native_scene=AsyncMock(),
    )
    entry = SimpleNamespace(entry_id="entry-a", runtime_data=coordinator)

    resolved, speed_index = await async_apply_scene(
        hass,
        entry,
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
        canonical_body=base64.b64decode(scene.param, validate=True) if scene.param else None,
    )


async def test_scene_application_uses_the_stored_device_default(
    hass: HomeAssistant,
) -> None:
    scene = next(item for item in SCENE_ENTRIES["H617A"] if item.scene_type == 2 and item.speed is not None)
    body, speed_index = resolve_native_scene_body(scene, speed_index=0)
    repository = NativeSceneDefaultRepository(InMemoryVersionedDocumentStore())
    await repository.async_load()
    await repository.async_set(
        NativeSceneDefault(
            config_entry_id="entry-a",
            scene_id=scene.scene_id,
            effect_id=scene.effect_id,
            updated_at=TIMESTAMP,
            canonical_body=body,
            speed_index=speed_index,
        )
    )
    coordinator = SimpleNamespace(
        model="H617A",
        profile=MODEL_PROFILES["H617A"],
        async_apply_native_scene=AsyncMock(),
    )
    entry = SimpleNamespace(entry_id="entry-a", runtime_data=coordinator)

    resolved, applied_speed = await async_apply_scene(
        hass,
        entry,
        scene_id=scene.scene_id,
        effect_id=scene.effect_id,
        speed_index=None,
        user_id="admin",
        scene_defaults=repository,
    )

    assert resolved.entry == scene
    assert applied_speed == 0
    coordinator.async_apply_native_scene.assert_awaited_once_with(
        resolved.key,
        speed_index=0,
        canonical_body=body,
    )


@pytest.mark.parametrize("scene_type", [0, 1, 2])
def test_h6125_scenes_are_not_exposed(scene_type: int) -> None:
    scene = next(item for item in SCENE_ENTRIES["H6125"] if item.scene_type == scene_type)

    with pytest.raises(ValueError, match="was not found"):
        resolve_scene("H6125", scene.scene_id, scene.effect_id)


async def test_reset_deletes_default_without_applying_to_the_device() -> None:
    scene = next(item for item in SCENE_ENTRIES["H617A"] if item.scene_type == 2)
    coordinator = SimpleNamespace(
        model="H617A",
        async_apply_native_scene=AsyncMock(),
    )
    repository = SimpleNamespace(async_delete=AsyncMock())
    entry = SimpleNamespace(entry_id="entry-a", runtime_data=coordinator)

    await async_reset_scene_default(
        entry,
        scene_id=scene.scene_id,
        effect_id=scene.effect_id,
        scene_defaults=repository,
    )

    repository.async_delete.assert_awaited_once_with("entry-a", scene.scene_id, scene.effect_id)
    coordinator.async_apply_native_scene.assert_not_awaited()


async def test_set_scene_default_encodes_content_without_applying_to_the_device() -> None:
    scene = next(item for item in SCENE_ENTRIES["H617A"] if item.scene_type == 2 and item.speed is not None)
    coordinator = SimpleNamespace(
        model="H617A",
        async_apply_native_scene=AsyncMock(),
    )
    repository = NativeSceneDefaultRepository(InMemoryVersionedDocumentStore())
    await repository.async_load()
    entry = SimpleNamespace(entry_id="entry-a", runtime_data=coordinator)
    speed = scene.speed
    assert speed is not None
    changed_speed = (speed.default_index + 1) % speed.option_count
    content = cast(dict[str, Any], scene_detail_payload("H617A", scene.scene_id, scene.effect_id)["content"])
    content["speed_index"] = changed_speed

    await async_set_scene_default(
        entry,
        scene_id=scene.scene_id,
        effect_id=scene.effect_id,
        content=content,
        updated_at=TIMESTAMP,
        scene_defaults=repository,
    )

    persisted = repository.get("entry-a", scene.scene_id, scene.effect_id)
    assert persisted is not None
    assert persisted.speed_index == changed_speed
    coordinator.async_apply_native_scene.assert_not_awaited()

    content["speed_index"] = speed.default_index
    await async_set_scene_default(
        entry,
        scene_id=scene.scene_id,
        effect_id=scene.effect_id,
        content=content,
        updated_at=TIMESTAMP,
        scene_defaults=repository,
    )

    assert repository.get("entry-a", scene.scene_id, scene.effect_id) is None
