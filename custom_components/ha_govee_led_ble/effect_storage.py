"""Current-only Home Assistant storage for saved effects."""

from __future__ import annotations

import asyncio
import copy
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final, cast
from uuid import UUID

from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .effect_domain import (
    EFFECT_SCHEMA_VERSION,
    EffectValidationError,
    LibraryItem,
    Origin,
    SourceKind,
    TargetHint,
    effect_content_from_dict,
    effect_content_hash,
)
from .effect_limits import (
    MAX_LIBRARY_ITEMS,
    MAX_LIBRARY_STORE_BYTES,
    MAX_REVISION,
    MAX_STORE_JSON_NODES,
    validate_json_document,
    validate_revision,
)
from .effect_persistence_validation import (
    EffectLimitError,
    EffectNotFoundError,
    EffectStorageError,
    EffectVersionConflictError,
    as_persisted_mapping,
)
from .effect_schema_migration import LegacyEffectMigrationError, migrate_effect_content_v1
from .effect_store import HomeAssistantVersionedDocumentStore, VersionedDocumentStore

LIBRARY_STORE_VERSION: Final = 2
LIBRARY_STORE_MINOR_VERSION: Final = 3
LIBRARY_STORE_KEY: Final = f"{DOMAIN}.effect_library"

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "EffectLibraryRepository",
    "EffectLimitError",
    "EffectNotFoundError",
    "EffectVersionConflictError",
    "EffectStorageError",
    "LibrarySnapshot",
]


@dataclass(frozen=True, slots=True)
class LibrarySnapshot:
    items: tuple[LibraryItem, ...]
    generation: int = 0


class EffectLibraryRepository:
    """Atomic current-only saved-effect library."""

    def __init__(self, hass: HomeAssistant | VersionedDocumentStore) -> None:
        self._store = _library_store(hass) if isinstance(hass, HomeAssistant) else hass
        self._lock = asyncio.Lock()
        self._data: dict[str, Any] | None = None
        self._listeners: set[Callable[[LibrarySnapshot], None]] = set()

    async def async_load(self) -> LibrarySnapshot:
        async with self._lock:
            stored = await self._store.async_load()
            data = _empty_library() if stored is None else stored
            snapshot = _validate_library(data)
            self._data = copy.deepcopy(data)
            return snapshot

    def snapshot(self) -> LibrarySnapshot:
        return _snapshot_from_data(self._require_loaded())

    def subscribe(self, listener: Callable[[LibrarySnapshot], None]) -> Callable[[], None]:
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    def get(self, item_id: UUID) -> LibraryItem:
        raw = cast(Mapping[str, Any] | None, self._require_loaded()["items"].get(str(item_id)))
        if raw is None:
            raise EffectNotFoundError(f"effect {item_id} does not exist")
        return LibraryItem.from_dict(raw)

    def assert_write_token(
        self,
        item_id: UUID,
        *,
        expected_version: int,
        expected_updated_at: str,
    ) -> LibraryItem:
        item = self.get(item_id)
        _expect_write_token(item, expected_version, expected_updated_at)
        return item

    async def async_create(self, item: LibraryItem) -> LibrarySnapshot:
        if item.version != 1:
            raise EffectStorageError("new effects must begin at version 1")
        async with self._lock:
            current = self._require_loaded()
            key = str(item.id)
            if key in current["items"]:
                raise EffectStorageError(f"effect {item.id} already exists")
            if len(current["items"]) >= MAX_LIBRARY_ITEMS:
                raise EffectLimitError(f"effect library must not exceed {MAX_LIBRARY_ITEMS} items")
            candidate = copy.deepcopy(current)
            candidate["items"][key] = item.to_dict()
            return await self._async_commit(candidate)

    async def async_update(
        self,
        item: LibraryItem,
        *,
        expected_version: int,
        expected_updated_at: str,
    ) -> LibrarySnapshot:
        async with self._lock:
            current = self._require_loaded()
            existing = self.get(item.id)
            _expect_write_token(existing, expected_version, expected_updated_at)
            if item.version != existing.version + 1:
                raise EffectStorageError(f"updated effect version must be {existing.version + 1}")
            if item.origin != existing.origin:
                raise EffectStorageError("effect origin is immutable")
            candidate = copy.deepcopy(current)
            candidate["items"][str(item.id)] = item.to_dict()
            return await self._async_commit(candidate)

    async def async_delete(
        self,
        item_id: UUID,
        *,
        expected_version: int,
        expected_updated_at: str,
    ) -> LibrarySnapshot:
        async with self._lock:
            current = self._require_loaded()
            existing = self.get(item_id)
            _expect_write_token(existing, expected_version, expected_updated_at)
            candidate = copy.deepcopy(current)
            del candidate["items"][str(item_id)]
            return await self._async_commit(candidate)

    async def _async_commit(self, candidate: dict[str, Any]) -> LibrarySnapshot:
        current_generation = _library_generation(self._require_loaded())
        if current_generation >= MAX_REVISION:
            raise EffectLimitError(f"effect library generation must not exceed {MAX_REVISION}")
        candidate["generation"] = current_generation + 1
        snapshot = _validate_library(candidate)
        await self._store.async_save(candidate)
        self._data = candidate
        for listener in tuple(self._listeners):
            try:
                listener(snapshot)
            except Exception:
                _LOGGER.exception("Effect library subscriber failed after a committed write")
        return snapshot

    def _require_loaded(self) -> dict[str, Any]:
        if self._data is None:
            raise EffectStorageError("effect library has not been loaded")
        return self._data


def _library_store(hass: HomeAssistant) -> VersionedDocumentStore:
    return HomeAssistantVersionedDocumentStore(
        hass,
        LIBRARY_STORE_VERSION,
        LIBRARY_STORE_KEY,
        minor_version=LIBRARY_STORE_MINOR_VERSION,
        migrate=_async_migrate_library,
    )


async def _async_migrate_library(
    old_major_version: int,
    old_minor_version: int,
    old_data: dict[str, Any],
) -> dict[str, Any]:
    if old_major_version == LIBRARY_STORE_VERSION and old_minor_version == LIBRARY_STORE_MINOR_VERSION:
        return old_data
    if old_major_version == LIBRARY_STORE_VERSION:
        without_retired_items = _remove_retired_library_items(old_data)
        if old_minor_version in {1, 2}:
            return {**without_retired_items, "generation": 0}
        if old_minor_version == 0:
            return {**_migrate_current_library(without_retired_items), "generation": 0}
        raise EffectStorageError(f"cannot migrate effect store version {old_major_version}.{old_minor_version}")
    if old_major_version != 1 or old_minor_version > 1:
        raise EffectStorageError(f"cannot migrate effect store version {old_major_version}.{old_minor_version}")
    root = as_persisted_mapping(old_data, "legacy effect library root")
    resources = as_persisted_mapping(root.get("resources"), "legacy effect resources")
    updated_at = datetime.now(UTC).isoformat()
    items: dict[str, Any] = {}
    for key, raw_resource in resources.items():
        resource = as_persisted_mapping(raw_resource, f"legacy effect resource {key}")
        if resource.get("deleted") is True:
            continue
        head = resource.get("head_revision")
        revisions = as_persisted_mapping(resource.get("revisions"), f"legacy effect revisions {key}")
        if not isinstance(head, int) or isinstance(head, bool):
            raise EffectStorageError(f"legacy effect resource {key} has an invalid head revision")
        raw_item = as_persisted_mapping(revisions.get(str(head)), f"legacy effect head {key}")
        if _is_retired_library_item(raw_item):
            continue
        item = _migrate_legacy_item(raw_item, version=head, updated_at=updated_at)
        if str(item.id) != str(key):
            raise EffectStorageError(f"legacy effect resource {key} has mismatched identity")
        items[str(item.id)] = item.to_dict()
    return {"items": items, "generation": 0}


def _migrate_legacy_item(raw: Mapping[str, Any], *, version: int, updated_at: str) -> LibraryItem:
    try:
        item_id = UUID(str(raw["id"]))
        name = str(raw["name"])
        content = effect_content_from_dict(
            migrate_effect_content_v1(as_persisted_mapping(raw.get("content"), "legacy effect content"))
        )
        provenance = as_persisted_mapping(raw.get("provenance"), "legacy effect provenance")
        kind = SourceKind(str(provenance.get("source_kind", SourceKind.MIGRATED.value)))
        target_raw = raw.get("target_hint")
        target = None
        if target_raw is not None:
            target_mapping = as_persisted_mapping(target_raw, "legacy effect target")
            model = target_mapping.get("model")
            segment_count = target_mapping.get("segment_count")
            if not isinstance(model, str) or (
                segment_count is not None and (not isinstance(segment_count, int) or isinstance(segment_count, bool))
            ):
                raise EffectStorageError("legacy effect target is invalid")
            target = TargetHint(model, segment_count)
        extensions = raw.get("extensions", {})
        if not isinstance(extensions, Mapping):
            raise EffectStorageError("legacy effect extensions must be a mapping")
        return LibraryItem(
            id=item_id,
            version=version,
            updated_at=updated_at,
            name=name,
            content=content,
            origin=Origin(kind, cast(str | None, provenance.get("source_id"))),
            target_hint=target,
            extensions=cast(dict[str, Any], dict(extensions)),
        )
    except (KeyError, TypeError, ValueError, EffectValidationError, LegacyEffectMigrationError) as exc:
        raise EffectStorageError(f"legacy effect head is invalid: {exc}") from exc


def _remove_retired_library_items(old_data: object) -> dict[str, Any]:
    root = as_persisted_mapping(old_data, "effect library root")
    items_raw = as_persisted_mapping(root.get("items"), "effect library items")
    return {"items": {str(key): value for key, value in items_raw.items() if not _is_retired_library_item(value)}}


def _is_retired_library_item(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    content = value.get("content")
    return isinstance(content, Mapping) and content.get("kind") == "special_diy"


def _migrate_current_library(old_data: object) -> dict[str, Any]:
    root = as_persisted_mapping(old_data, "effect library root")
    items_raw = as_persisted_mapping(root.get("items"), "effect library items")
    items: dict[str, Any] = {}
    for key, value in items_raw.items():
        raw = dict(as_persisted_mapping(value, f"effect {key}"))
        if raw.get("schema_version") != 1:
            raise EffectStorageError(f"effect {key} does not use schema version 1")
        try:
            content_document = migrate_effect_content_v1(
                as_persisted_mapping(raw.get("content"), f"effect {key} content")
            )
            content = effect_content_from_dict(content_document)
        except (EffectValidationError, LegacyEffectMigrationError) as exc:
            raise EffectStorageError(f"effect {key} is invalid: {exc}") from exc
        raw["schema_version"] = EFFECT_SCHEMA_VERSION
        raw["content"] = content_document
        raw["content_hash"] = effect_content_hash(content)
        item = LibraryItem.from_dict(raw)
        if str(item.id) != str(key):
            raise EffectStorageError(f"effect {key} has mismatched identity")
        items[str(item.id)] = item.to_dict()
    return {"items": items}


def _empty_library() -> dict[str, Any]:
    return {"items": {}, "generation": 0}


def _validate_library(data: object) -> LibrarySnapshot:
    root = as_persisted_mapping(data, "effect library root")
    validate_json_document(
        root,
        "effect library",
        maximum_bytes=MAX_LIBRARY_STORE_BYTES,
        error_type=EffectStorageError,
        maximum_nodes=MAX_STORE_JSON_NODES,
    )
    items_raw = as_persisted_mapping(root.get("items"), "effect library items")
    generation = _library_generation(root)
    if len(items_raw) > MAX_LIBRARY_ITEMS:
        raise EffectLimitError(f"effect library must not exceed {MAX_LIBRARY_ITEMS} items")
    items: list[LibraryItem] = []
    for key, raw_item in items_raw.items():
        try:
            item = LibraryItem.from_dict(as_persisted_mapping(raw_item, f"effect {key}"))
        except EffectValidationError as exc:
            raise EffectStorageError(f"effect {key} is invalid: {exc}") from exc
        if str(item.id) != str(key):
            raise EffectStorageError(f"effect {key} has mismatched identity")
        items.append(item)
    return LibrarySnapshot(tuple(items), generation)


def _snapshot_from_data(data: Mapping[str, Any]) -> LibrarySnapshot:
    return _validate_library(data)


def _library_generation(data: Mapping[str, Any]) -> int:
    generation = data.get("generation", 0)
    validate_revision(
        generation,
        "effect library generation",
        minimum=0,
        error_type=EffectStorageError,
    )
    return cast(int, generation)


def _expect_write_token(item: LibraryItem, expected_version: int, expected_updated_at: str) -> None:
    if item.version != expected_version or item.updated_at != expected_updated_at:
        raise EffectVersionConflictError(item.version)
