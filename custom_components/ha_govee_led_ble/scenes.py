"""Per-model scene catalogues."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

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
    selector_only: bool = False
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
            selector_only=sku == "H6179",
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


SCENE_ENTRIES: dict[str, tuple[SceneEntry, ...]] = {sku: _load_catalogue(sku) for sku in ("H617A", "H6179", "H6199")}
SCENE_ENTRIES["H617E"] = SCENE_ENTRIES["H617A"]


def _legacy_h617a_key(entry: SceneEntry) -> str:
    key = entry.name.lower()
    if entry.variant and entry.variant.lower() not in {"a", "#0"}:
        key = f"{key} {entry.variant.lower()}"
    return key


def _model_scene_catalogue(sku: str) -> tuple[dict[str, SceneEntry], dict[str, str]]:
    entries = SCENE_ENTRIES[sku]
    keys = [" ".join(entry.display_name.split()).casefold() for entry in entries]
    duplicates = {key for key, count in Counter(keys).items() if count > 1}
    category_counts = Counter((key, entry.category.casefold()) for key, entry in zip(keys, entries, strict=True))
    scenes: dict[str, SceneEntry] = {}
    labels: dict[str, str] = {}
    for entry, key in zip(entries, keys, strict=True):
        label = entry.display_name
        if key in duplicates:
            qualifier = entry.category
            if category_counts[key, entry.category.casefold()] > 1:
                qualifier = f"{qualifier}, {entry.scene_id}:{entry.effect_id}"
            key = f"{key} [{qualifier.casefold()}]"
            label = f"{label} [{qualifier}]"
        scenes[key] = entry
        labels[key] = label
    if len(scenes) != len(entries):
        raise ValueError(f"Duplicate scene selector key in {sku} catalogue")
    return scenes, labels


_MODEL_CATALOGUES = {sku: _model_scene_catalogue(sku) for sku in SCENE_ENTRIES}
MODEL_SCENES: dict[str, dict[str, SceneEntry]] = {sku: catalogue[0] for sku, catalogue in _MODEL_CATALOGUES.items()}
MODEL_SCENE_LABELS: dict[str, dict[str, str]] = {sku: catalogue[1] for sku, catalogue in _MODEL_CATALOGUES.items()}


def scene_selector_code(model: str, scene: SceneEntry) -> int:
    """Return the selector; H6179 keeps the full identity but its u1 transport uses the low byte."""
    if model != "H6179":
        return scene.code
    if not isinstance(scene.code, int) or isinstance(scene.code, bool) or scene.code < 0:
        raise ValueError("H6179 catalogue scene code must be a non-negative integer")
    return scene.code & 0xFF


def _build_scene_keys_by_code(model: str, scenes: dict[str, SceneEntry]) -> dict[int, str]:
    selectors: dict[int, str] = {}
    for key, scene in scenes.items():
        selector = scene_selector_code(model, scene)
        if selector in selectors:
            existing = selectors[selector]
            raise ValueError(f"{model} scenes {existing!r} and {key!r} share selector 0x{selector:02x}")
        selectors[selector] = key
    return selectors


_MODEL_SCENE_KEYS_BY_CODE: dict[str, dict[int, str]] = {
    model: _build_scene_keys_by_code(model, scenes) for model, scenes in MODEL_SCENES.items()
}


def scene_key_for_code(model: str, code: int) -> str | None:
    """Return a model-specific selector key for a native scene code."""
    return _MODEL_SCENE_KEYS_BY_CODE.get(model, {}).get(code)


# H617A protocol and service lookups use the legacy unhyphenated variant names.
SCENES: dict[str, SceneEntry] = {_legacy_h617a_key(entry): entry for entry in SCENE_ENTRIES["H617A"]}
