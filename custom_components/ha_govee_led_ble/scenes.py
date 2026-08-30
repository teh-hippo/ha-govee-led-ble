"""Per-model scene catalogues."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .const import MODEL_PROFILES

CATALOGUE_DIR = Path(__file__).with_name("scene_catalogues")


@dataclass(frozen=True, slots=True)
class SceneBrightnessSpeed:
    block: int
    values: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ScenePage:
    page: int
    move_in: tuple[int, ...] = ()
    move_all: tuple[int, ...] = ()
    colour_speed: tuple[int, ...] = ()
    brightness_speeds: tuple[SceneBrightnessSpeed, ...] = ()

    @property
    def option_lists(self) -> tuple[tuple[int, ...], ...]:
        return (
            self.move_in,
            self.move_all,
            self.colour_speed,
            *(brightness.values for brightness in self.brightness_speeds),
        )


@dataclass(frozen=True, slots=True)
class SceneSpeed:
    default_index: int
    pages: tuple[ScenePage, ...]

    @property
    def option_count(self) -> int:
        counts = {len(values) for page in self.pages for values in page.option_lists if values}
        if len(counts) != 1:
            raise ValueError(f"Scene Speed pages disagree on option count: {sorted(counts)}")
        count = counts.pop()
        if not 0 <= self.default_index < count:
            raise ValueError(f"Scene Speed default index {self.default_index} outside 0..{count - 1}")
        return count


@dataclass(frozen=True, slots=True)
class SceneEntry:
    code: int
    param: str = ""
    scene_type: int = 2
    speed: SceneSpeed | None = None
    category_id: int = 0
    category: str = ""
    scene_id: int = 0
    effect_id: int = 0
    name: str = ""
    variant: str = ""
    music_code: int = 0

    @property
    def display_name(self) -> str:
        return self.name if not self.variant else f"{self.name}-{self.variant}"


def _load_speed(data: dict[str, Any] | None) -> SceneSpeed | None:
    if data is None:
        return None
    pages = tuple(
        ScenePage(
            page=int(page["page"]),
            move_in=tuple(page.get("move_in", [])),
            move_all=tuple(page.get("move_all", [])),
            colour_speed=tuple(page.get("colour_speed", [])),
            brightness_speeds=tuple(
                SceneBrightnessSpeed(
                    block=int(brightness["block"]),
                    values=tuple(brightness["values"]),
                )
                for brightness in page.get("brightness", [])
            ),
        )
        for page in data["pages"]
    )
    speed = SceneSpeed(default_index=int(data["default_index"]), pages=pages)
    _ = speed.option_count
    return speed


def _load_catalogue(sku: str) -> tuple[SceneEntry, ...]:
    path = CATALOGUE_DIR / f"{sku}.json"
    data = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    if data.get("schema_version") != 1 or data.get("sku") != sku:
        raise ValueError(f"Invalid scene catalogue metadata in {path}")

    categories = {int(category["id"]): str(category["name"]) for category in data["categories"]}
    entries = tuple(
        SceneEntry(
            code=int(effect["code"]),
            param=str(effect.get("param", "")),
            scene_type=int(effect["scene_type"]),
            speed=_load_speed(effect.get("speed")),
            category_id=int(effect["category_id"]),
            category=categories[int(effect["category_id"])],
            scene_id=int(effect["scene_id"]),
            effect_id=int(effect["effect_id"]),
            name=str(effect["name"]),
            variant=str(effect.get("variant", "")),
            music_code=int(effect.get("music_code", 0)),
        )
        for effect in data["effects"]
    )
    identities = {(entry.scene_id, entry.effect_id) for entry in entries}
    if len(identities) != len(entries):
        raise ValueError(f"Duplicate scene identity in {path}")
    return entries


SCENE_ENTRIES: dict[str, tuple[SceneEntry, ...]] = {
    model: _load_catalogue(profile.scene_catalogue_sku)
    for model, profile in MODEL_PROFILES.items()
    if profile.scene_catalogue_sku is not None
}


def _legacy_h617a_key(entry: SceneEntry) -> str:
    key = entry.name.lower()
    if entry.variant and entry.variant.lower() not in {"a", "#0"}:
        key = f"{key} {entry.variant.lower()}"
    return key


def _model_scene_catalogue(sku: str) -> tuple[dict[str, SceneEntry], dict[str, str]]:
    entries = SCENE_ENTRIES[sku]
    keys = [" ".join(entry.display_name.split()).casefold() for entry in entries]
    duplicates = {key for key, count in Counter(keys).items() if count > 1}
    scenes: dict[str, SceneEntry] = {}
    labels: dict[str, str] = {}
    for entry, key in zip(entries, keys, strict=True):
        label = entry.display_name
        if key in duplicates:
            key = f"{key} [{entry.category.lower()}]"
            label = f"{label} [{entry.category}]"
        scenes[key] = entry
        labels[key] = label
    return scenes, labels


_MODEL_CATALOGUES = {sku: _model_scene_catalogue(sku) for sku in SCENE_ENTRIES}
OFFICIAL_MODEL_SCENES: dict[str, dict[str, SceneEntry]] = {
    sku: dict(catalogue[0]) for sku, catalogue in _MODEL_CATALOGUES.items()
}
MODEL_SCENES: dict[str, dict[str, SceneEntry]] = {sku: dict(scenes) for sku, scenes in OFFICIAL_MODEL_SCENES.items()}
MODEL_SCENE_LABELS: dict[str, dict[str, str]] = {
    sku: dict(catalogue[1]) for sku, catalogue in _MODEL_CATALOGUES.items()
}
MODEL_SCENE_ALIASES: dict[str, dict[str, str]] = {}

# H617A protocol and service lookups use the legacy unhyphenated variant names.
SCENES: dict[str, SceneEntry] = {_legacy_h617a_key(entry): entry for entry in SCENE_ENTRIES["H617A"]}


def _legacy_scene_target(
    scenes: dict[str, SceneEntry],
    legacy_key: str,
    legacy_entry: SceneEntry,
) -> str | None:
    if legacy_key in scenes:
        return legacy_key
    matches = [
        key
        for key, entry in scenes.items()
        if legacy_entry.param and entry.scene_type == legacy_entry.scene_type and entry.param == legacy_entry.param
    ] or [
        key
        for key, entry in scenes.items()
        if entry.scene_type == legacy_entry.scene_type and entry.code == legacy_entry.code
    ]
    return matches[0] if len(matches) == 1 else None


for _model, _profile in MODEL_PROFILES.items():
    _legacy_model = _profile.legacy_scene_catalogue_sku
    if _legacy_model is None or _model not in MODEL_SCENES or _legacy_model not in MODEL_SCENES:
        continue
    _scenes = MODEL_SCENES[_model]
    _labels = MODEL_SCENE_LABELS[_model]
    _aliases: dict[str, str] = {}
    for _legacy_key, _legacy_entry in MODEL_SCENES[_legacy_model].items():
        _target = _legacy_scene_target(_scenes, _legacy_key, _legacy_entry)
        if _target is None:
            _scenes[_legacy_key] = _legacy_entry
            _labels[_legacy_key] = _legacy_entry.display_name
        elif _target != _legacy_key:
            _aliases[_legacy_key] = _target
    MODEL_SCENE_ALIASES[_model] = _aliases


def scene_aliases(model: str, scene_key: str) -> tuple[str, ...]:
    return tuple(alias for alias, target in MODEL_SCENE_ALIASES.get(model, {}).items() if target == scene_key)


def canonical_scene_key(model: str, scene_key: str) -> str:
    return MODEL_SCENE_ALIASES.get(model, {}).get(scene_key, scene_key)


def resolve_scene_code(
    model: str,
    scene_code: int,
    *,
    preferred_key: str | None = None,
) -> tuple[str, SceneEntry] | None:
    legacy_model = MODEL_PROFILES[model].legacy_scene_catalogue_sku
    if preferred_key is not None:
        preferred = OFFICIAL_MODEL_SCENES.get(model, {}).get(preferred_key)
        if preferred is not None and preferred.code == scene_code:
            return preferred_key, preferred
        legacy = MODEL_SCENES.get(legacy_model or "", {}).get(preferred_key)
        if legacy is not None and legacy.code == scene_code:
            return preferred_key, legacy
        canonical_key = canonical_scene_key(model, preferred_key)
        canonical = OFFICIAL_MODEL_SCENES.get(model, {}).get(canonical_key)
        if canonical is not None and canonical.code == scene_code:
            return canonical_key, canonical

    resolved = next(
        ((key, entry) for key, entry in MODEL_SCENES.get(model, {}).items() if entry.code == scene_code),
        None,
    )
    if resolved is not None:
        return resolved
    return next(
        ((key, entry) for key, entry in MODEL_SCENES.get(legacy_model or "", {}).items() if entry.code == scene_code),
        None,
    )


def scene_code_is_ambiguous(model: str, scene_code: int) -> bool:
    exact_keys = {key for key, entry in OFFICIAL_MODEL_SCENES.get(model, {}).items() if entry.code == scene_code}
    legacy_model = MODEL_PROFILES[model].legacy_scene_catalogue_sku
    legacy_keys = {
        MODEL_SCENE_ALIASES.get(model, {}).get(key, key)
        for key, entry in MODEL_SCENES.get(legacy_model or "", {}).items()
        if entry.code == scene_code
    }
    return bool(exact_keys and legacy_keys and exact_keys != legacy_keys)


def legacy_scene_entries(model: str, scene_key: str) -> tuple[SceneEntry, ...]:
    legacy_model = MODEL_PROFILES[model].legacy_scene_catalogue_sku
    legacy_scenes = MODEL_SCENES.get(legacy_model or "", {})
    aliases = MODEL_SCENE_ALIASES.get(model, {})
    return tuple(
        entry for legacy_key, entry in legacy_scenes.items() if aliases.get(legacy_key, legacy_key) == scene_key
    )


def resolve_scene_identity(model: str, scene_id: int, effect_id: int) -> tuple[str, SceneEntry] | None:
    scenes = MODEL_SCENES.get(model)
    if scenes is None:
        return None
    resolved = next(
        ((key, entry) for key, entry in scenes.items() if entry.scene_id == scene_id and entry.effect_id == effect_id),
        None,
    )
    if resolved is not None:
        return resolved

    legacy_model = MODEL_PROFILES[model].legacy_scene_catalogue_sku
    legacy_scenes = MODEL_SCENES.get(legacy_model or "")
    if legacy_scenes is None:
        return None
    return next(
        (
            (key, entry)
            for key, entry in legacy_scenes.items()
            if entry.scene_id == scene_id and entry.effect_id == effect_id
        ),
        None,
    )
