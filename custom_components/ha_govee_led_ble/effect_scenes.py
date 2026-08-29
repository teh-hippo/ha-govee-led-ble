"""Native scene catalogue contracts for the advanced editor."""

from __future__ import annotations

import base64
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .effect_domain import (
    BuiltinScene,
    CatalogueRef,
    EffectContent,
    EffectValidationError,
    JsonValue,
    LayeredScene,
    PaletteScene,
    effect_content_from_dict,
    effect_content_to_dict,
)
from .effect_scene_defaults import NativeSceneDefault, NativeSceneDefaultRepository
from .layered_scene_decoder import decode_layered_scene
from .native_scenes import apply_scene_speed, encode_authored_scene_body, resolve_native_scene_body
from .palette_scene_decoder import decode_palette_scene
from .scenes import (
    MODEL_SCENE_LABELS,
    MODEL_SCENES,
    SceneEntry,
)

CATALOGUE_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class ResolvedScene:
    key: str
    label: str
    entry: SceneEntry


def scene_catalogue_payload(model: str) -> dict[str, JsonValue]:
    scenes = MODEL_SCENES.get(model)
    if scenes is None:
        raise ValueError(f"{model} has no native scene catalogue")
    entries = tuple(scenes.values())
    categories: list[JsonValue] = []
    seen_categories: set[int] = set()
    for entry in entries:
        if entry.category_id not in seen_categories:
            seen_categories.add(entry.category_id)
            categories.append({"id": entry.category_id, "name": entry.category})
    return {
        "schema_version": CATALOGUE_SCHEMA_VERSION,
        "sku": model,
        "enabled": bool(entries),
        "categories": categories,
        "scenes": [_scene_summary(model, entry) for entry in entries],
    }


def scene_detail_payload(
    model: str,
    scene_id: int,
    effect_id: int,
    *,
    scene_default: NativeSceneDefault | None = None,
) -> dict[str, JsonValue]:
    resolved = resolve_scene(model, scene_id, effect_id)
    if scene_default is not None and resolved.entry.scene_type == 0:
        scene_default = None
    speed_index = (
        scene_default.speed_index
        if scene_default is not None
        else resolved.entry.speed.default_index
        if resolved.entry.speed is not None
        else None
    )
    template = CatalogueRef(
        sku=model,
        scene_id=scene_id,
        effect_id=effect_id,
        catalogue_schema_version=CATALOGUE_SCHEMA_VERSION,
    )
    catalogue_speed = resolved.entry.speed.default_index if resolved.entry.speed is not None else None
    catalogue_content = _scene_content(resolved.entry, template, None, catalogue_speed)
    content = _scene_content(
        resolved.entry,
        template,
        scene_default.canonical_body if scene_default is not None else None,
        speed_index,
    )
    return {
        "scene": _scene_summary(model, resolved.entry),
        "content": effect_content_to_dict(content),
        "catalogue_content": effect_content_to_dict(catalogue_content),
        "has_default": scene_default is not None,
    }


def resolve_scene(model: str, scene_id: int, effect_id: int) -> ResolvedScene:
    scenes = MODEL_SCENES.get(model)
    labels = MODEL_SCENE_LABELS.get(model)
    if scenes is None or labels is None:
        raise ValueError(f"{model} has no native scene catalogue")
    for key, entry in scenes.items():
        if entry.scene_id == scene_id and entry.effect_id == effect_id:
            return ResolvedScene(key, labels[key], entry)
    raise ValueError(f"{model} scene identity ({scene_id}, {effect_id}) was not found")


async def async_apply_scene(
    hass: HomeAssistant,
    config_entry: ConfigEntry[Any],
    *,
    scene_id: int,
    effect_id: int,
    speed_index: int | None,
    user_id: str,
    scene_defaults: NativeSceneDefaultRepository | None = None,
) -> tuple[ResolvedScene, int | None]:
    del hass, user_id
    coordinator = config_entry.runtime_data
    resolved = resolve_scene(coordinator.model, scene_id, effect_id)
    scene_default = scene_defaults.get(config_entry.entry_id, scene_id, effect_id) if scene_defaults else None
    canonical_body, resolved_speed = resolve_scene_application_body(
        resolved.entry,
        scene_default=scene_default,
        speed_index=speed_index,
    )

    await coordinator.async_apply_native_scene(
        resolved.key,
        speed_index=resolved_speed,
        canonical_body=canonical_body or None,
    )
    return resolved, resolved_speed


async def async_reset_scene_default(
    config_entry: ConfigEntry[Any],
    *,
    scene_id: int,
    effect_id: int,
    scene_defaults: NativeSceneDefaultRepository,
) -> ResolvedScene:
    coordinator = config_entry.runtime_data
    resolved = resolve_scene(coordinator.model, scene_id, effect_id)
    await scene_defaults.async_delete(config_entry.entry_id, scene_id, effect_id)
    return resolved


async def async_set_scene_default(
    config_entry: ConfigEntry[Any],
    *,
    scene_id: int,
    effect_id: int,
    content: Mapping[str, Any],
    updated_at: str,
    scene_defaults: NativeSceneDefaultRepository,
) -> ResolvedScene:
    coordinator = config_entry.runtime_data
    resolved = resolve_scene(coordinator.model, scene_id, effect_id)
    parsed = effect_content_from_dict(content)
    _validate_scene_content_identity(coordinator.model, resolved.entry, parsed)
    if isinstance(parsed, PaletteScene | LayeredScene):
        canonical_body, resolved_speed = encode_authored_scene_body(parsed, resolved.entry)
    else:
        assert isinstance(parsed, BuiltinScene)
        canonical_body, resolved_speed = resolve_native_scene_body(
            resolved.entry,
            speed_index=parsed.speed_index,
        )
    catalogue_body, catalogue_speed = resolve_native_scene_body(resolved.entry)
    if canonical_body == catalogue_body and resolved_speed == catalogue_speed:
        await scene_defaults.async_delete(config_entry.entry_id, scene_id, effect_id)
    elif canonical_body:
        await scene_defaults.async_set(
            NativeSceneDefault(
                config_entry_id=config_entry.entry_id,
                scene_id=scene_id,
                effect_id=effect_id,
                updated_at=updated_at,
                canonical_body=canonical_body,
                speed_index=resolved_speed,
            )
        )
    return resolved


def _scene_content(
    entry: SceneEntry,
    template: CatalogueRef,
    canonical_body: bytes | None,
    speed_index: int | None,
) -> EffectContent:
    body = canonical_body
    if body is None and entry.param:
        body = base64.b64decode(entry.param, validate=True)
    if entry.scene_type == 1 and body:
        return decode_palette_scene(template, body, speed_index=speed_index)
    if entry.scene_type == 2 and body:
        return decode_layered_scene(template, body, speed_index=speed_index)
    return BuiltinScene(template, speed_index=speed_index)


def _validate_scene_content_identity(
    model: str,
    entry: SceneEntry,
    content: EffectContent,
) -> None:
    if not isinstance(content, BuiltinScene | PaletteScene | LayeredScene):
        raise EffectValidationError("scene default content must be a native-scene definition")
    template = content.template
    if (
        template.sku != model
        or template.scene_id != entry.scene_id
        or template.effect_id != entry.effect_id
        or template.catalogue_schema_version != CATALOGUE_SCHEMA_VERSION
    ):
        raise EffectValidationError("scene default content has mismatched catalogue identity")
    expected_type = {
        0: BuiltinScene,
        1: PaletteScene,
        2: LayeredScene,
    }.get(entry.scene_type)
    if expected_type is None or not isinstance(content, expected_type):
        raise EffectValidationError("scene default content does not match the catalogue scene structure")


def resolve_scene_application_body(
    scene: SceneEntry,
    *,
    scene_default: NativeSceneDefault | None,
    speed_index: int | None,
) -> tuple[bytes, int | None]:
    if scene_default is None:
        return resolve_native_scene_body(scene, speed_index=speed_index)
    speed = scene.speed
    if speed is None:
        if speed_index is not None:
            raise ValueError("this scene does not expose a documented Speed control")
        return scene_default.canonical_body, None
    resolved_speed = scene_default.speed_index if speed_index is None else speed_index
    if resolved_speed is None:
        resolved_speed = speed.default_index
    if not 0 <= resolved_speed < speed.option_count:
        raise ValueError(f"scene speed index {resolved_speed} outside 0..{speed.option_count - 1}")
    body = scene_default.canonical_body
    if speed_index is not None and speed_index != scene_default.speed_index:
        body = apply_scene_speed(body, speed, speed_index)
    return body, resolved_speed


def _scene_summary(model: str, entry: SceneEntry) -> dict[str, JsonValue]:
    resolved = resolve_scene(model, entry.scene_id, entry.effect_id)
    parameter_kind = (
        "none"
        if not entry.param
        else "palette"
        if entry.scene_type == 1
        else "layers"
        if entry.scene_type == 2
        else "opaque"
    )
    return {
        "scene_id": entry.scene_id,
        "effect_id": entry.effect_id,
        "category_id": entry.category_id,
        "category": entry.category,
        "name": entry.name,
        "variant": entry.variant,
        "display_name": resolved.label,
        "scene_type": entry.scene_type,
        "parameter_kind": parameter_kind,
        "speed": (
            {
                "option_count": entry.speed.option_count,
                "default_index": entry.speed.default_index,
            }
            if entry.speed is not None
            else None
        ),
    }
