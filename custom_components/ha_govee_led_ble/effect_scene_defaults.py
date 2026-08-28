"""Bounded per-device native-scene defaults."""

from __future__ import annotations

import asyncio
import copy
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Final, cast

from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .effect_limits import (
    MAX_DEVICE_CACHE_ENTRIES,
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
    optional_persisted_integer,
    required_persisted_integer,
    required_persisted_string,
)
from .effect_store import HomeAssistantVersionedDocumentStore, VersionedDocumentStore
from .generated_protocol_adapter import MAX_SCENE_PARAM_BYTES

SCENE_DEFAULT_STORE_VERSION: Final = 1
SCENE_DEFAULT_STORE_MINOR_VERSION: Final = 0
SCENE_DEFAULT_STORE_KEY: Final = f"{DOMAIN}.native_scene_defaults"
MAX_SCENE_DEFAULTS_PER_DEVICE: Final = 256


@dataclass(frozen=True, slots=True)
class NativeSceneDefault:
    config_entry_id: str
    scene_id: int
    effect_id: int
    updated_at: str
    canonical_body: bytes
    speed_index: int | None = None

    def __post_init__(self) -> None:
        validate_bounded_string(
            self.config_entry_id,
            "scene-default config entry ID",
            maximum=MAX_IDENTIFIER_LENGTH,
            error_type=EffectStorageError,
        )
        if not 0 <= self.scene_id <= 0xFFFF or not 0 <= self.effect_id <= 0xFFFF:
            raise EffectStorageError("scene-default identity must use unsigned 16-bit values")
        validate_timestamp(self.updated_at, "scene-default timestamp", error_type=EffectStorageError)
        if not isinstance(self.canonical_body, bytes) or len(self.canonical_body) > MAX_SCENE_PARAM_BYTES:
            raise EffectStorageError(f"scene-default body must not exceed {MAX_SCENE_PARAM_BYTES} bytes")
        if self.speed_index is not None and not 0 <= self.speed_index <= 0xFF:
            raise EffectStorageError("scene-default speed index must be from 0 to 255")

    @property
    def content_hash(self) -> str:
        return sha256(self.canonical_body).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "config_entry_id": self.config_entry_id,
            "scene_id": self.scene_id,
            "effect_id": self.effect_id,
            "updated_at": self.updated_at,
            "canonical_body": self.canonical_body.hex(),
            "content_hash": self.content_hash,
            "speed_index": self.speed_index,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> NativeSceneDefault:
        try:
            body = bytes.fromhex(required_persisted_string(raw, "canonical_body"))
        except ValueError as exc:
            raise EffectStorageError("scene-default body must be hexadecimal") from exc
        value = cls(
            config_entry_id=required_persisted_string(raw, "config_entry_id"),
            scene_id=required_persisted_integer(raw, "scene_id"),
            effect_id=required_persisted_integer(raw, "effect_id"),
            updated_at=required_persisted_string(raw, "updated_at"),
            canonical_body=body,
            speed_index=optional_persisted_integer(raw, "speed_index"),
        )
        if required_persisted_string(raw, "content_hash") != value.content_hash:
            raise EffectStorageError("scene-default content hash does not match body")
        return value


class NativeSceneDefaultRepository:
    def __init__(self, hass: HomeAssistant | VersionedDocumentStore) -> None:
        self._store = _scene_default_store(hass) if isinstance(hass, HomeAssistant) else hass
        self._data: dict[str, Any] | None = None
        self._lock = asyncio.Lock()

    async def async_load(self) -> tuple[NativeSceneDefault, ...]:
        async with self._lock:
            stored = await self._store.async_load()
            data = {"devices": {}} if stored is None else stored
            values = _validate_store(data)
            self._data = copy.deepcopy(data)
            return values

    def get(self, config_entry_id: str, scene_id: int, effect_id: int) -> NativeSceneDefault | None:
        records = cast(dict[str, Any], self._require_loaded()["devices"].get(config_entry_id, {}))
        raw = records.get(_scene_key(scene_id, effect_id))
        return None if not isinstance(raw, Mapping) else NativeSceneDefault.from_dict(raw)

    async def async_set(self, value: NativeSceneDefault) -> None:
        async with self._lock:
            candidate = copy.deepcopy(self._require_loaded())
            devices = candidate["devices"]
            if value.config_entry_id not in devices and len(devices) >= MAX_DEVICE_CACHE_ENTRIES:
                raise EffectLimitError(f"scene-default store must not exceed {MAX_DEVICE_CACHE_ENTRIES} devices")
            devices.setdefault(value.config_entry_id, {})[_scene_key(value.scene_id, value.effect_id)] = value.to_dict()
            _validate_store(candidate)
            await self._store.async_save(candidate)
            self._data = candidate

    async def async_delete(self, config_entry_id: str, scene_id: int, effect_id: int) -> None:
        async with self._lock:
            candidate = copy.deepcopy(self._require_loaded())
            records = candidate["devices"].get(config_entry_id)
            if not isinstance(records, dict) or records.pop(_scene_key(scene_id, effect_id), None) is None:
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
            raise EffectStorageError("scene-default store has not been loaded")
        return self._data


def _scene_default_store(hass: HomeAssistant) -> VersionedDocumentStore:
    return HomeAssistantVersionedDocumentStore(
        hass,
        SCENE_DEFAULT_STORE_VERSION,
        SCENE_DEFAULT_STORE_KEY,
        minor_version=SCENE_DEFAULT_STORE_MINOR_VERSION,
        migrate=_async_migrate_scene_defaults,
    )


async def _async_migrate_scene_defaults(
    old_major_version: int,
    old_minor_version: int,
    old_data: dict[str, Any],
) -> dict[str, Any]:
    if old_major_version == SCENE_DEFAULT_STORE_VERSION and old_minor_version <= SCENE_DEFAULT_STORE_MINOR_VERSION:
        return old_data
    raise EffectStorageError(f"cannot migrate scene-default store version {old_major_version}.{old_minor_version}")


def _validate_store(data: object) -> tuple[NativeSceneDefault, ...]:
    root = as_persisted_mapping(data, "scene-default store")
    validate_json_document(
        root,
        "scene-default store",
        maximum_bytes=MAX_DEVICE_CACHE_ENTRIES * MAX_SCENE_PARAM_BYTES * 4,
        maximum_nodes=MAX_STORE_JSON_NODES,
        error_type=EffectStorageError,
    )
    devices = as_persisted_mapping(root.get("devices"), "scene-default devices")
    if len(devices) > MAX_DEVICE_CACHE_ENTRIES:
        raise EffectLimitError(f"scene-default store must not exceed {MAX_DEVICE_CACHE_ENTRIES} devices")
    values: list[NativeSceneDefault] = []
    for config_entry_id, raw_records in devices.items():
        records = as_persisted_mapping(raw_records, f"scene defaults for {config_entry_id}")
        if len(records) > MAX_SCENE_DEFAULTS_PER_DEVICE:
            raise EffectLimitError(
                f"scene-default store must not exceed {MAX_SCENE_DEFAULTS_PER_DEVICE} scenes per device"
            )
        for key, raw in records.items():
            value = NativeSceneDefault.from_dict(as_persisted_mapping(raw, f"scene default {key}"))
            if value.config_entry_id != config_entry_id or key != _scene_key(value.scene_id, value.effect_id):
                raise EffectStorageError(f"scene default {key} has mismatched identity")
            values.append(value)
    return tuple(values)


def _scene_key(scene_id: int, effect_id: int) -> str:
    return f"{scene_id}:{effect_id}"
