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
    category_id: int = 0
    category: str = ""
    scene_id: int = 0
    effect_id: int = 0
    name: str = ""
    variant: str = ""
    music_code: int = 0

    @property
    def is_simple(self) -> bool:
        return not self.param

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


SCENE_ENTRIES: dict[str, tuple[SceneEntry, ...]] = {sku: _load_catalogue(sku) for sku in ("H617A", "H6199")}


def _legacy_h617a_key(entry: SceneEntry) -> str:
    key = entry.name.lower()
    if entry.variant and entry.variant.lower() not in {"a", "#0"}:
        key = f"{key} {entry.variant.lower()}"
    return key


def _model_scene_map(sku: str) -> dict[str, SceneEntry]:
    entries = SCENE_ENTRIES[sku]
    keys = [" ".join(entry.display_name.split()).casefold() for entry in entries]
    duplicates = {key for key, count in Counter(keys).items() if count > 1}
    scenes: dict[str, SceneEntry] = {}
    for entry, key in zip(entries, keys, strict=True):
        if key in duplicates:
            key = f"{key} [{entry.category.lower()}]"
        scenes[key] = entry
    return scenes


MODEL_SCENES: dict[str, dict[str, SceneEntry]] = {sku: _model_scene_map(sku) for sku in SCENE_ENTRIES}

# Compatibility surface until the effect-options rewrite switches callers to model catalogues.
SCENES: dict[str, SceneEntry] = {_legacy_h617a_key(entry): entry for entry in SCENE_ENTRIES["H617A"]}


def get_scene_names() -> list[str]:
    return sorted(SCENES)


def get_model_scene_names(sku: str) -> list[str]:
    return sorted(MODEL_SCENES[sku])
