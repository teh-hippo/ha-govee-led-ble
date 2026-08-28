"""Bounded canonical content for the active unsaved effect on each device."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, Final, cast

from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .effect_deployments import ObservationConfidence
from .effect_domain import (
    EffectContent,
    Origin,
    SourceKind,
    effect_content_from_dict,
    effect_content_hash,
    effect_content_to_dict,
)
from .effect_limits import (
    MAX_ACTIVE_WORKSPACE_ENTRIES,
    MAX_ACTIVE_WORKSPACE_STORE_BYTES,
    MAX_IDENTIFIER_LENGTH,
    MAX_STORE_JSON_NODES,
    validate_bounded_string,
    validate_json_document,
    validate_revision,
    validate_timestamp,
)
from .effect_persistence_validation import (
    EffectLimitError,
    EffectStorageError,
    as_persisted_mapping,
    optional_persisted_string,
    required_persisted_integer,
    required_persisted_mapping,
    required_persisted_string,
)
from .effect_store import HomeAssistantVersionedDocumentStore, VersionedDocumentStore

ACTIVE_WORKSPACE_STORE_VERSION: Final = 1
ACTIVE_WORKSPACE_STORE_MINOR_VERSION: Final = 0
ACTIVE_WORKSPACE_STORE_KEY: Final = f"{DOMAIN}.active_effect_workspaces"


@dataclass(frozen=True, slots=True)
class ActiveEffectWorkspace:
    config_entry_id: str
    model: str
    selector_label: str
    content: EffectContent
    origin: Origin
    observable_signature: str
    updated_at: str
    generation: int
    confidence: ObservationConfidence = ObservationConfidence.WRITE_COMPLETED

    def __post_init__(self) -> None:
        for value, name in (
            (self.config_entry_id, "active-workspace config entry ID"),
            (self.model, "active-workspace model"),
            (self.selector_label, "active-workspace selector label"),
            (self.observable_signature, "active-workspace observable signature"),
        ):
            validate_bounded_string(
                value,
                name,
                maximum=MAX_IDENTIFIER_LENGTH,
                error_type=EffectStorageError,
            )
        validate_timestamp(self.updated_at, "active-workspace timestamp", error_type=EffectStorageError)
        validate_revision(
            self.generation,
            "active-workspace generation",
            minimum=1,
            error_type=EffectStorageError,
        )
        validate_json_document(
            self.to_dict(),
            "active workspace",
            maximum_bytes=MAX_ACTIVE_WORKSPACE_STORE_BYTES,
            error_type=EffectStorageError,
        )

    @property
    def content_hash(self) -> str:
        return effect_content_hash(self.content)

    def to_dict(self) -> dict[str, Any]:
        return {
            "config_entry_id": self.config_entry_id,
            "model": self.model,
            "selector_label": self.selector_label,
            "content": effect_content_to_dict(self.content),
            "content_hash": self.content_hash,
            "origin": {
                "kind": self.origin.kind.value,
                "source_id": self.origin.source_id,
            },
            "observable_signature": self.observable_signature,
            "updated_at": self.updated_at,
            "generation": self.generation,
            "confidence": self.confidence.value,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> ActiveEffectWorkspace:
        origin_raw = required_persisted_mapping(raw, "origin")
        try:
            origin = Origin(
                SourceKind(required_persisted_string(origin_raw, "kind")),
                optional_persisted_string(origin_raw, "source_id"),
            )
            confidence = ObservationConfidence(required_persisted_string(raw, "confidence"))
            content = effect_content_from_dict(required_persisted_mapping(raw, "content"))
        except ValueError as exc:
            raise EffectStorageError("active workspace is invalid") from exc
        value = cls(
            config_entry_id=required_persisted_string(raw, "config_entry_id"),
            model=required_persisted_string(raw, "model"),
            selector_label=required_persisted_string(raw, "selector_label"),
            content=content,
            origin=origin,
            observable_signature=required_persisted_string(raw, "observable_signature"),
            updated_at=required_persisted_string(raw, "updated_at"),
            generation=required_persisted_integer(raw, "generation"),
            confidence=confidence,
        )
        if required_persisted_string(raw, "content_hash") != value.content_hash:
            raise EffectStorageError("active-workspace content hash does not match content")
        return value


class ActiveEffectWorkspaceRepository:
    def __init__(self, hass: HomeAssistant | VersionedDocumentStore) -> None:
        self._store = _active_workspace_store(hass) if isinstance(hass, HomeAssistant) else hass
        self._data: dict[str, Any] | None = None

    async def async_load(self) -> tuple[ActiveEffectWorkspace, ...]:
        stored = await self._store.async_load()
        data = {"devices": {}} if stored is None else stored
        values = _validate_store(data)
        self._data = copy.deepcopy(data)
        return values

    def get(self, config_entry_id: str) -> ActiveEffectWorkspace | None:
        raw = cast(dict[str, Any], self._require_loaded()["devices"]).get(config_entry_id)
        return None if not isinstance(raw, Mapping) else ActiveEffectWorkspace.from_dict(raw)

    def next_generation(self) -> int:
        values = (
            ActiveEffectWorkspace.from_dict(raw).generation
            for raw in cast(dict[str, Mapping[str, Any]], self._require_loaded()["devices"]).values()
        )
        return max(values, default=0) + 1

    def set(self, value: ActiveEffectWorkspace) -> bool:
        candidate = copy.deepcopy(self._require_loaded())
        devices = cast(dict[str, Any], candidate["devices"])
        current_raw = devices.get(value.config_entry_id)
        if isinstance(current_raw, Mapping):
            current = ActiveEffectWorkspace.from_dict(current_raw)
            if current.generation > value.generation:
                return False
        elif len(devices) >= MAX_ACTIVE_WORKSPACE_ENTRIES:
            raise EffectLimitError(f"active-workspace store must not exceed {MAX_ACTIVE_WORKSPACE_ENTRIES} devices")
        devices[value.config_entry_id] = value.to_dict()
        _validate_store(candidate)
        self._data = candidate
        self._store.async_delay_save(lambda: copy.deepcopy(self._require_loaded()), delay=1)
        return True

    def update_confidence(
        self,
        config_entry_id: str,
        generation: int,
        confidence: ObservationConfidence,
    ) -> bool:
        current = self.get(config_entry_id)
        if current is None or current.generation != generation:
            return False
        return self.set(replace(current, confidence=confidence))

    def clear(self, config_entry_id: str) -> bool:
        candidate = copy.deepcopy(self._require_loaded())
        if candidate["devices"].pop(config_entry_id, None) is None:
            return False
        _validate_store(candidate)
        self._data = candidate
        self._store.async_delay_save(lambda: copy.deepcopy(self._require_loaded()), delay=1)
        return True

    async def async_delete_device(self, config_entry_id: str) -> None:
        candidate = copy.deepcopy(self._require_loaded())
        if candidate["devices"].pop(config_entry_id, None) is None:
            return
        _validate_store(candidate)
        await self._store.async_save(candidate)
        self._data = candidate

    async def async_flush(self) -> None:
        await self._store.async_save(copy.deepcopy(self._require_loaded()))

    def _require_loaded(self) -> dict[str, Any]:
        if self._data is None:
            raise EffectStorageError("active-workspace store has not been loaded")
        return self._data


def _active_workspace_store(hass: HomeAssistant) -> VersionedDocumentStore:
    return HomeAssistantVersionedDocumentStore(
        hass,
        ACTIVE_WORKSPACE_STORE_VERSION,
        ACTIVE_WORKSPACE_STORE_KEY,
        minor_version=ACTIVE_WORKSPACE_STORE_MINOR_VERSION,
        migrate=_async_migrate_active_workspaces,
    )


async def _async_migrate_active_workspaces(
    old_major_version: int,
    old_minor_version: int,
    old_data: dict[str, Any],
) -> dict[str, Any]:
    if (
        old_major_version == ACTIVE_WORKSPACE_STORE_VERSION
        and old_minor_version <= ACTIVE_WORKSPACE_STORE_MINOR_VERSION
    ):
        return old_data
    raise EffectStorageError(f"cannot migrate active-workspace store version {old_major_version}.{old_minor_version}")


def _validate_store(data: object) -> tuple[ActiveEffectWorkspace, ...]:
    root = as_persisted_mapping(data, "active-workspace store")
    devices = as_persisted_mapping(root.get("devices"), "active-workspace devices")
    if len(devices) > MAX_ACTIVE_WORKSPACE_ENTRIES:
        raise EffectLimitError(f"active-workspace store must not exceed {MAX_ACTIVE_WORKSPACE_ENTRIES} devices")
    values = tuple(
        ActiveEffectWorkspace.from_dict(as_persisted_mapping(raw, f"active workspace {config_entry_id}"))
        for config_entry_id, raw in devices.items()
    )
    if any(value.config_entry_id != config_entry_id for config_entry_id, value in zip(devices, values, strict=True)):
        raise EffectStorageError("active-workspace key does not match config entry ID")
    validate_json_document(
        root,
        "active-workspace store",
        maximum_bytes=MAX_ACTIVE_WORKSPACE_STORE_BYTES,
        maximum_nodes=MAX_STORE_JSON_NODES,
        error_type=EffectStorageError,
    )
    return values
