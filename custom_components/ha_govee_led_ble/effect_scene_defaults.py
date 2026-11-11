"""Bounded per-device native-scene defaults."""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
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
from .effect_store import DeviceDefaultsRepository, HomeAssistantVersionedDocumentStore, VersionedDocumentStore
from .protocol_core import MAX_SCENE_PARAM_BYTES

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


class NativeSceneDefaultRepository(DeviceDefaultsRepository[NativeSceneDefault]):
    def __init__(self, hass: HomeAssistant | VersionedDocumentStore) -> None:
        super().__init__(
            _scene_default_store(hass) if isinstance(hass, HomeAssistant) else hass,
            _validate_store,
            "scene-default",
        )
        self._entry_cache: (
            tuple[dict[str, Any], dict[tuple[str, int, int], tuple[Mapping[str, Any], NativeSceneDefault]]] | None
        ) = None

    def get(self, config_entry_id: str, scene_id: int, effect_id: int) -> NativeSceneDefault | None:
        data = self._require_loaded()
        records = cast(dict[str, Any], data["devices"].get(config_entry_id, {}))
        raw = records.get(_scene_key(scene_id, effect_id))
        if not isinstance(raw, Mapping):
            return None
        if self._entry_cache is None or self._entry_cache[0] is not data:
            self._entry_cache = (data, {})
        key = (config_entry_id, scene_id, effect_id)
        cached = self._entry_cache[1].get(key)
        if cached is not None and cached[0] is raw:
            return cached[1]
        parsed = NativeSceneDefault.from_dict(raw)
        self._entry_cache[1][key] = (raw, parsed)
        return parsed

    async def async_set(self, value: NativeSceneDefault) -> None:
        await self.async_replace_identities(
            value.config_entry_id,
            ((value.scene_id, value.effect_id),),
            value,
        )

    async def async_delete(self, config_entry_id: str, scene_id: int, effect_id: int) -> None:
        await self.async_replace_identities(
            config_entry_id,
            ((scene_id, effect_id),),
            None,
        )

    async def async_replace_identities(
        self,
        config_entry_id: str,
        identities: Iterable[tuple[int, int]],
        value: NativeSceneDefault | None,
    ) -> None:
        if value is not None and value.config_entry_id != config_entry_id:
            raise EffectStorageError("scene-default replacement has mismatched config entry")
        async with self._lock:
            candidate = copy.deepcopy(self._require_loaded())
            devices = candidate["devices"]
            if value is not None and config_entry_id not in devices and len(devices) >= MAX_DEVICE_CACHE_ENTRIES:
                raise EffectLimitError(f"scene-default store must not exceed {MAX_DEVICE_CACHE_ENTRIES} devices")
            records = devices.get(config_entry_id)
            if not isinstance(records, dict):
                records = {}
            changed = False
            for scene_id, effect_id in identities:
                changed = records.pop(_scene_key(scene_id, effect_id), None) is not None or changed
            if value is not None:
                raw = value.to_dict()
                key = _scene_key(value.scene_id, value.effect_id)
                changed = records.get(key) != raw or changed
                records[key] = raw
                devices[config_entry_id] = records
            elif records:
                devices[config_entry_id] = records
            else:
                changed = devices.pop(config_entry_id, None) is not None or changed
            if not changed:
                return
            _validate_store(candidate)
            await self._store.async_save(candidate)
            self._data = candidate


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
