"""Effect projection for Home Assistant light selectors."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, replace
from functools import cache
from typing import Literal
from uuid import UUID

from homeassistant.components.light import EFFECT_OFF

from .const import (
    EFFECT_CATEGORIES,
    EFFECT_CATEGORY_ADVANCED,
    EFFECT_CATEGORY_EFFECTS,
    EFFECT_CATEGORY_MULTI_LAYERED,
    EFFECT_CATEGORY_REACTIVE,
    EFFECT_CATEGORY_SCENES,
    EFFECT_CATEGORY_VIDEO,
    MUSIC_MODE_SLUGS,
    effect_category_for_content_kind,
    get_profile,
)
from .effect_compiler import CompatibilityState, compatibility
from .effect_domain import EffectValidationError, LibraryItem, effect_content_to_dict
from .scenes import MODEL_SCENE_LABELS

_EFFECT_QUOTE_CHARS = "\"'“”‘’"

VIDEO_EFFECTS: dict[str, str] = {
    "Video: Movie": "movie",
    "Video: Game": "game",
}
MUSIC_EFFECTS: dict[str, str] = {f"Music: {slug.replace('_', ' ').title()}": slug for slug in MUSIC_MODE_SLUGS}

EffectSelectorSource = Literal["scene", "video", "music", "saved"]
SavedEffectNameKind = Literal["available", "reserved", "same_item", "saved"]

_CATEGORY_LABELS = {
    EFFECT_CATEGORY_SCENES: "Scene",
    EFFECT_CATEGORY_VIDEO: "Video",
    EFFECT_CATEGORY_EFFECTS: "Effect",
    EFFECT_CATEGORY_MULTI_LAYERED: "Multi-Layered",
    EFFECT_CATEGORY_REACTIVE: "Reactive",
    EFFECT_CATEGORY_ADVANCED: "Advanced",
}
_CATEGORY_ORDER = {category: index for index, category in enumerate(EFFECT_CATEGORIES)}


@dataclass(frozen=True, slots=True)
class EffectSelectorEntry:
    source: EffectSelectorSource
    category: str
    base_label: str
    display_label: str
    value: str
    aliases: frozenset[str]
    item: LibraryItem | None = None


@dataclass(frozen=True, slots=True)
class SavedEffectNameStatus:
    kind: SavedEffectNameKind
    item: LibraryItem | None = None


class ReservedEffectNameError(EffectValidationError):
    """A saved effect name is reserved by the selector contract."""


class SavedEffectNameConflictError(EffectValidationError):
    """A saved effect name belongs to another library item."""


@dataclass(frozen=True, slots=True)
class _SelectorCandidate:
    source: EffectSelectorSource
    category: str
    base_label: str
    value: str
    aliases: tuple[str, ...]
    item: LibraryItem | None = None


def normalise_effect_name(effect_name: str) -> str:
    stripped = effect_name.strip().strip(_EFFECT_QUOTE_CHARS).strip()
    return " ".join(stripped.split()).casefold()


def effect_selector_entries(
    model: str,
    categories: frozenset[str],
    items: Iterable[LibraryItem],
    *,
    prefix_effect_names: bool,
    always_include_custom_effects: bool = False,
    active_custom: bool = False,
    native_categories: frozenset[str] | None = None,
) -> tuple[EffectSelectorEntry, ...]:
    candidates = _selector_candidates(
        model,
        categories,
        items,
        always_include_custom_effects=always_include_custom_effects,
        native_categories=native_categories,
    )
    counts = Counter(normalise_effect_name(candidate.base_label) for candidate in candidates)
    category_counts = Counter(
        (normalise_effect_name(candidate.base_label), candidate.category) for candidate in candidates
    )
    counts[normalise_effect_name(EFFECT_OFF)] += 1
    if active_custom:
        counts[normalise_effect_name("Custom")] += 1
    represented_categories = frozenset(candidate.category for candidate in candidates)
    use_prefixes = prefix_effect_names and len(represented_categories) > 1
    projected = _ensure_unique_display_labels(
        tuple(
            _project_candidate(
                candidate,
                use_prefix=use_prefixes,
                collides=counts[normalise_effect_name(candidate.base_label)] > 1,
                same_category_collides=category_counts[
                    (normalise_effect_name(candidate.base_label), candidate.category)
                ]
                > 1,
            )
            for candidate in candidates
        ),
        use_prefix=use_prefixes,
    )
    if use_prefixes:
        return tuple(
            sorted(
                projected,
                key=lambda entry: (
                    _CATEGORY_ORDER[entry.category],
                    entry.base_label.casefold(),
                    entry.display_label.casefold(),
                ),
            )
        )
    return tuple(
        sorted(
            projected,
            key=lambda entry: (
                entry.base_label.casefold(),
                _CATEGORY_ORDER[entry.category],
                entry.display_label.casefold(),
            ),
        )
    )


def resolve_effect_selector(
    entries: Iterable[EffectSelectorEntry],
    effect_name: str,
) -> EffectSelectorEntry | None:
    key = normalise_effect_name(effect_name)
    display_matches = [entry for entry in entries if normalise_effect_name(entry.display_label) == key]
    if len(display_matches) > 1:
        raise EffectValidationError(f"effect name {effect_name!r} is ambiguous")
    if display_matches:
        return display_matches[0]
    matches = [entry for entry in entries if key in entry.aliases]
    if len(matches) > 1:
        raise EffectValidationError(f"effect name {effect_name!r} is ambiguous")
    return matches[0] if matches else None


def validate_saved_effect_name(
    name: str,
    items: Iterable[LibraryItem],
    *,
    excluding_item_id: UUID | None = None,
    allow_reserved: bool = False,
) -> None:
    key = normalise_effect_name(name)
    if not allow_reserved and key in _reserved_effect_names():
        raise ReservedEffectNameError(f"effect name {name!r} is reserved by Home Assistant")
    if any(item.id != excluding_item_id and normalise_effect_name(item.name) == key for item in items):
        raise SavedEffectNameConflictError(f"effect name {name!r} is already in use")


def classify_saved_effect_name(
    name: str,
    items: Iterable[LibraryItem],
    *,
    excluding_item_id: UUID | None = None,
) -> SavedEffectNameStatus:
    key = normalise_effect_name(name)
    if key in _reserved_effect_names():
        return SavedEffectNameStatus("reserved")
    matches = tuple(item for item in items if normalise_effect_name(item.name) == key)
    conflicting = next((item for item in matches if item.id != excluding_item_id), None)
    if conflicting is not None:
        return SavedEffectNameStatus("saved", conflicting)
    if excluding_item_id is not None and any(item.id == excluding_item_id for item in matches):
        return SavedEffectNameStatus("same_item")
    return SavedEffectNameStatus("available")


def compatible_saved_effects(
    items: Iterable[LibraryItem],
    model: str,
) -> tuple[LibraryItem, ...]:
    compatible = [item for item in items if compatibility(item, model).state is CompatibilityState.COMPATIBLE]
    counts = Counter(normalise_effect_name(item.name) for item in compatible)
    return tuple(
        sorted(
            (item for item in compatible if counts[normalise_effect_name(item.name)] == 1),
            key=lambda item: item.name.casefold(),
        )
    )


def saved_effect_by_name(
    items: Iterable[LibraryItem],
    model: str,
    effect_name: str,
) -> LibraryItem | None:
    entries = effect_selector_entries(
        model,
        frozenset(EFFECT_CATEGORIES),
        items,
        prefix_effect_names=False,
    )
    resolved = resolve_effect_selector(entries, effect_name)
    return resolved.item if resolved is not None and resolved.source == "saved" else None


def _selector_candidates(
    model: str,
    categories: frozenset[str],
    items: Iterable[LibraryItem],
    *,
    always_include_custom_effects: bool = False,
    native_categories: frozenset[str] | None = None,
) -> tuple[_SelectorCandidate, ...]:
    candidates: list[_SelectorCandidate] = []
    native = categories if native_categories is None else native_categories
    if EFFECT_CATEGORY_SCENES in native:
        candidates.extend(
            _SelectorCandidate(
                source="scene",
                category=EFFECT_CATEGORY_SCENES,
                base_label=label,
                value=key,
                aliases=(key,),
            )
            for key, label in MODEL_SCENE_LABELS[model].items()
        )
    profile = get_profile(model)
    if EFFECT_CATEGORY_VIDEO in native and profile.supports_video_mode:
        candidates.extend(
            _SelectorCandidate(
                source="video",
                category=EFFECT_CATEGORY_VIDEO,
                base_label=_native_base_label(label),
                value=mode,
                aliases=(label,),
            )
            for label, mode in VIDEO_EFFECTS.items()
        )
    if EFFECT_CATEGORY_REACTIVE in native:
        candidates.extend(
            _SelectorCandidate(
                source="music",
                category=EFFECT_CATEGORY_REACTIVE,
                base_label=_native_base_label(label),
                value=slug,
                aliases=(label,),
            )
            for label, slug in MUSIC_EFFECTS.items()
            if slug in profile.music_modes
        )
    candidates.extend(
        _SelectorCandidate(
            source="saved",
            category=category,
            base_label=item.name,
            value=str(item.id),
            aliases=(),
            item=item,
        )
        for item in compatible_saved_effects(items, model)
        if (category := effect_category_for_content_kind(str(effect_content_to_dict(item.content).get("kind"))))
        is not None
        and (category in categories or always_include_custom_effects)
    )
    return tuple(candidates)


def _project_candidate(
    candidate: _SelectorCandidate,
    *,
    use_prefix: bool,
    collides: bool,
    same_category_collides: bool,
) -> EffectSelectorEntry:
    category_label = _CATEGORY_LABELS[candidate.category]
    prefixed = f"{category_label}: {candidate.base_label}"
    suffixed = f"{candidate.base_label} [{category_label}]"
    source_label = "Saved" if candidate.source == "saved" else "Built-in"
    if same_category_collides:
        display_label = (
            f"{prefixed} [{source_label}]"
            if use_prefix
            else f"{candidate.base_label} [{category_label}, {source_label}]"
        )
    else:
        display_label = prefixed if use_prefix else suffixed if collides else candidate.base_label
    raw_aliases = (
        display_label,
        prefixed,
        suffixed,
        *candidate.aliases,
    )
    aliases = frozenset(
        normalise_effect_name(alias)
        for alias in (
            *(
                ()
                if candidate.source == "saved" and normalise_effect_name(candidate.base_label) == EFFECT_OFF
                else (candidate.base_label,)
            ),
            *raw_aliases,
        )
    )
    return EffectSelectorEntry(
        source=candidate.source,
        category=candidate.category,
        base_label=candidate.base_label,
        display_label=display_label,
        value=candidate.value,
        aliases=aliases,
        item=candidate.item,
    )


def _native_base_label(label: str) -> str:
    return label.split(": ", 1)[1] if ": " in label else label


def _ensure_unique_display_labels(
    entries: tuple[EffectSelectorEntry, ...],
    *,
    use_prefix: bool,
) -> tuple[EffectSelectorEntry, ...]:
    projected = entries
    qualification_round = 0
    while True:
        counts = Counter(normalise_effect_name(entry.display_label) for entry in projected)
        if all(count == 1 for count in counts.values()):
            return projected
        include_identity = qualification_round > 0
        projected = tuple(
            (
                _with_display_label(
                    entry,
                    (
                        _source_qualified_label(
                            entry,
                            use_prefix=use_prefix,
                            include_identity=include_identity,
                        )
                        + (f" [{qualification_round}]" if qualification_round > 1 else "")
                    ),
                )
                if counts[normalise_effect_name(entry.display_label)] > 1
                else entry
            )
            for entry in projected
        )
        qualification_round += 1


def _with_display_label(
    entry: EffectSelectorEntry,
    display_label: str,
) -> EffectSelectorEntry:
    return replace(
        entry,
        display_label=display_label,
        aliases=entry.aliases | {normalise_effect_name(display_label)},
    )


def _source_qualified_label(
    entry: EffectSelectorEntry,
    *,
    use_prefix: bool,
    include_identity: bool,
) -> str:
    category_label = _CATEGORY_LABELS[entry.category]
    source_label = "Saved" if entry.source == "saved" else "Built-in"
    identity = (
        f", {str(entry.item.id)[:8]}"
        if include_identity and entry.item is not None
        else f", {entry.source}:{entry.value}"
        if include_identity
        else ""
    )
    return (
        f"{category_label}: {entry.base_label} [{source_label}{identity}]"
        if use_prefix
        else f"{entry.base_label} [{category_label}, {source_label}{identity}]"
    )


@cache
def _reserved_effect_names() -> frozenset[str]:
    names = {normalise_effect_name(EFFECT_OFF), normalise_effect_name("Custom")}
    for model in MODEL_SCENE_LABELS:
        candidates = _selector_candidates(model, frozenset(EFFECT_CATEGORIES), ())
        for candidate in candidates:
            entry = _project_candidate(
                candidate,
                use_prefix=False,
                collides=True,
                same_category_collides=False,
            )
            names.update(entry.aliases)
    return frozenset(names)
