"""Bounded per-device defaults for custom-effect catalogue templates."""

from __future__ import annotations

import asyncio
import copy
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final, cast

from homeassistant.core import HomeAssistant

from .const import DOMAIN, MODEL_PROFILES
from .effect_catalogue import validate_catalogue_template_identity
from .effect_domain import (
    EffectContent,
    EffectValidationError,
    effect_content_from_dict,
    effect_content_hash,
    effect_content_to_dict,
)
from .effect_limits import (
    MAX_DEVICE_CACHE_ENTRIES,
    MAX_EFFECT_DOCUMENT_BYTES,
    MAX_IDENTIFIER_LENGTH,
    MAX_STORE_JSON_NODES,
    validate_bounded_string,
    validate_json_document,
    validate_timestamp,
)
from .effect_persistence_validation import (
    EffectLimitError,
    EffectStorageError,
    as_persisted_mapping,
    required_persisted_string,
)
from .effect_store import HomeAssistantVersionedDocumentStore, VersionedDocumentStore

TEMPLATE_DEFAULT_STORE_VERSION: Final = 1
TEMPLATE_DEFAULT_STORE_MINOR_VERSION: Final = 0
TEMPLATE_DEFAULT_STORE_KEY: Final = f"{DOMAIN}.catalogue_template_defaults"
MAX_TEMPLATE_DEFAULTS_PER_DEVICE: Final = 64


@dataclass(frozen=True, slots=True)
class CatalogueTemplateDefault:
    config_entry_id: str
    model: str
    template_id: str
    updated_at: str
    content: EffectContent
    content_hash: str = ""

    def __post_init__(self) -> None:
        validate_bounded_string(
            self.config_entry_id,
            "template-default config entry ID",
            maximum=MAX_IDENTIFIER_LENGTH,
            error_type=EffectStorageError,
        )
        validate_bounded_string(
            self.template_id,
            "template-default template ID",
            maximum=MAX_IDENTIFIER_LENGTH,
            error_type=EffectStorageError,
        )
        if self.model not in MODEL_PROFILES:
            raise EffectStorageError(f"template-default model {self.model!r} is unsupported")
        validate_timestamp(self.updated_at, "template-default timestamp", error_type=EffectStorageError)
        try:
            validate_catalogue_template_identity(self.model, self.template_id, self.content)
        except (EffectValidationError, ValueError) as exc:
            raise EffectStorageError(str(exc)) from exc
        expected_hash = effect_content_hash(self.content)
        if self.content_hash and self.content_hash != expected_hash:
            raise EffectStorageError("template-default content hash does not match content")
        object.__setattr__(self, "content_hash", expected_hash)

    def to_dict(self) -> dict[str, Any]:
        return {
            "config_entry_id": self.config_entry_id,
            "model": self.model,
            "template_id": self.template_id,
            "updated_at": self.updated_at,
            "content": effect_content_to_dict(self.content),
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> CatalogueTemplateDefault:
        try:
            content = effect_content_from_dict(as_persisted_mapping(raw.get("content"), "template-default content"))
        except EffectValidationError as exc:
            raise EffectStorageError(f"template-default content is invalid: {exc}") from exc
        return cls(
            config_entry_id=required_persisted_string(raw, "config_entry_id"),
            model=required_persisted_string(raw, "model"),
            template_id=required_persisted_string(raw, "template_id"),
            updated_at=required_persisted_string(raw, "updated_at"),
            content=content,
            content_hash=required_persisted_string(raw, "content_hash"),
        )


class CatalogueTemplateDefaultRepository:
    def __init__(self, hass: HomeAssistant | VersionedDocumentStore) -> None:
        self._store = _template_default_store(hass) if isinstance(hass, HomeAssistant) else hass
        self._data: dict[str, Any] | None = None
        self._lock = asyncio.Lock()

    async def async_load(self) -> tuple[CatalogueTemplateDefault, ...]:
        async with self._lock:
            stored = await self._store.async_load()
            data = {"devices": {}} if stored is None else stored
            values = _validate_store(data)
            self._data = copy.deepcopy(data)
            return values

    def get(self, config_entry_id: str, template_id: str) -> CatalogueTemplateDefault | None:
        records = cast(dict[str, Any], self._require_loaded()["devices"].get(config_entry_id, {}))
        raw = records.get(template_id)
        return None if not isinstance(raw, Mapping) else CatalogueTemplateDefault.from_dict(raw)

    async def async_set(self, value: CatalogueTemplateDefault) -> None:
        async with self._lock:
            candidate = copy.deepcopy(self._require_loaded())
            devices = candidate["devices"]
            if value.config_entry_id not in devices and len(devices) >= MAX_DEVICE_CACHE_ENTRIES:
                raise EffectLimitError(f"template-default store must not exceed {MAX_DEVICE_CACHE_ENTRIES} devices")
            records = devices.setdefault(value.config_entry_id, {})
            if value.template_id not in records and len(records) >= MAX_TEMPLATE_DEFAULTS_PER_DEVICE:
                raise EffectLimitError(
                    f"template-default store must not exceed {MAX_TEMPLATE_DEFAULTS_PER_DEVICE} templates per device"
                )
            records[value.template_id] = value.to_dict()
            _validate_store(candidate)
            await self._store.async_save(candidate)
            self._data = candidate

    async def async_delete(self, config_entry_id: str, template_id: str) -> None:
        async with self._lock:
            candidate = copy.deepcopy(self._require_loaded())
            records = candidate["devices"].get(config_entry_id)
            if not isinstance(records, dict) or records.pop(template_id, None) is None:
                return
            if not records:
                candidate["devices"].pop(config_entry_id)
            await self._store.async_save(candidate)
            self._data = candidate

    async def async_delete_device(self, config_entry_id: str) -> None:
        async with self._lock:
            candidate = copy.deepcopy(self._require_loaded())
            if candidate["devices"].pop(config_entry_id, None) is None:
                return
            await self._store.async_save(candidate)
            self._data = candidate

    def _require_loaded(self) -> dict[str, Any]:
        if self._data is None:
            raise EffectStorageError("template-default store has not been loaded")
        return self._data


def _template_default_store(hass: HomeAssistant) -> VersionedDocumentStore:
    return HomeAssistantVersionedDocumentStore(
        hass,
        TEMPLATE_DEFAULT_STORE_VERSION,
        TEMPLATE_DEFAULT_STORE_KEY,
        minor_version=TEMPLATE_DEFAULT_STORE_MINOR_VERSION,
        migrate=_async_migrate_template_defaults,
    )


async def _async_migrate_template_defaults(
    old_major_version: int,
    old_minor_version: int,
    old_data: dict[str, Any],
) -> dict[str, Any]:
    if (
        old_major_version == TEMPLATE_DEFAULT_STORE_VERSION
        and old_minor_version <= TEMPLATE_DEFAULT_STORE_MINOR_VERSION
    ):
        return old_data
    raise EffectStorageError(f"cannot migrate template-default store version {old_major_version}.{old_minor_version}")


def _validate_store(data: object) -> tuple[CatalogueTemplateDefault, ...]:
    root = as_persisted_mapping(data, "template-default store")
    validate_json_document(
        root,
        "template-default store",
        maximum_bytes=MAX_DEVICE_CACHE_ENTRIES * MAX_TEMPLATE_DEFAULTS_PER_DEVICE * MAX_EFFECT_DOCUMENT_BYTES,
        maximum_nodes=MAX_STORE_JSON_NODES,
        error_type=EffectStorageError,
    )
    devices = as_persisted_mapping(root.get("devices"), "template-default devices")
    if len(devices) > MAX_DEVICE_CACHE_ENTRIES:
        raise EffectLimitError(f"template-default store must not exceed {MAX_DEVICE_CACHE_ENTRIES} devices")
    values: list[CatalogueTemplateDefault] = []
    for config_entry_id, raw_records in devices.items():
        records = as_persisted_mapping(raw_records, f"template defaults for {config_entry_id}")
        if len(records) > MAX_TEMPLATE_DEFAULTS_PER_DEVICE:
            raise EffectLimitError(
                f"template-default store must not exceed {MAX_TEMPLATE_DEFAULTS_PER_DEVICE} templates per device"
            )
        models: set[str] = set()
        for template_id, raw in records.items():
            value = CatalogueTemplateDefault.from_dict(as_persisted_mapping(raw, f"template default {template_id}"))
            if value.config_entry_id != config_entry_id or value.template_id != template_id:
                raise EffectStorageError(f"template default {template_id} has mismatched identity")
            models.add(value.model)
            values.append(value)
        if len(models) > 1:
            raise EffectStorageError(f"template defaults for {config_entry_id} target multiple models")
    return tuple(values)
