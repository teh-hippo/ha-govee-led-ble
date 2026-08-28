"""Replaceable observed-device state and active-effect identity."""

from __future__ import annotations

import copy
import logging
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, Final, cast
from uuid import UUID

from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .effect_deployments import DeploymentRecord, ObservationConfidence
from .effect_domain import LibraryItem
from .effect_limits import (
    MAX_DEVICE_CACHE_ENTRIES,
    MAX_DEVICE_CACHE_STORE_BYTES,
    MAX_IDENTIFIER_LENGTH,
    MAX_STORE_JSON_NODES,
    validate_bounded_string,
    validate_json_document,
    validate_revision,
    validate_timestamp,
)
from .effect_persistence_validation import EffectLimitError, EffectStorageError
from .effect_persistence_validation import as_persisted_mapping as _as_mapping
from .effect_persistence_validation import optional_persisted_integer as _optional_int
from .effect_persistence_validation import optional_persisted_string as _optional_str
from .effect_persistence_validation import required_persisted_mapping as _required_mapping
from .effect_persistence_validation import required_persisted_string as _required_str
from .effect_store import HomeAssistantVersionedDocumentStore, VersionedDocumentStore

DEVICE_CACHE_STORE_VERSION: Final = 2
DEVICE_CACHE_STORE_MINOR_VERSION: Final = 1
DEVICE_CACHE_STORE_KEY: Final = f"{DOMAIN}.effect_device_cache"

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ActiveEffectHint:
    source_kind: str
    selector_label: str
    content_hash: str
    origin_kind: str
    origin_id: str | None
    observable_signature: str
    confidence: ObservationConfidence
    item_id: UUID | None = None
    item_version: int | None = None

    def __post_init__(self) -> None:
        if self.source_kind not in {"saved_effect", "snapshot", "deleted_effect"}:
            raise EffectStorageError("active-effect source kind is invalid")
        for value, name in (
            (self.selector_label, "active-effect selector label"),
            (self.origin_kind, "active-effect origin kind"),
            (self.observable_signature, "active-effect observable signature"),
        ):
            validate_bounded_string(
                value,
                name,
                maximum=MAX_IDENTIFIER_LENGTH,
                error_type=EffectStorageError,
            )
        if self.origin_id is not None:
            validate_bounded_string(
                self.origin_id,
                "active-effect origin source ID",
                maximum=MAX_IDENTIFIER_LENGTH,
                error_type=EffectStorageError,
            )
        if len(self.content_hash) != 64 or any(character not in "0123456789abcdef" for character in self.content_hash):
            raise EffectStorageError("active-effect content hash must be SHA-256")
        if self.source_kind == "saved_effect":
            if self.item_id is None or self.item_version is None:
                raise EffectStorageError("active-effect library identity is incomplete")
            validate_revision(
                self.item_version,
                "active-effect item version",
                minimum=1,
                error_type=EffectStorageError,
            )
        elif self.item_id is not None or self.item_version is not None:
            raise EffectStorageError("detached active effect must not reference a library item")

    @classmethod
    def from_record(
        cls,
        record: DeploymentRecord,
        *,
        observable_signature: str,
        confidence: ObservationConfidence,
    ) -> ActiveEffectHint:
        return cls(
            source_kind=record.source_kind,
            selector_label=record.selector_label,
            content_hash=record.source_content_hash,
            origin_kind=record.source_origin_kind,
            origin_id=record.source_origin_id,
            observable_signature=observable_signature,
            confidence=confidence,
            item_id=record.item_id,
            item_version=record.item_version,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_kind": self.source_kind,
            "selector_label": self.selector_label,
            "content_hash": self.content_hash,
            "origin": {
                "kind": self.origin_kind,
                "source_id": self.origin_id,
            },
            "observable_signature": self.observable_signature,
            "confidence": self.confidence.value,
            "item_id": str(self.item_id) if self.item_id is not None else None,
            "item_version": self.item_version,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> ActiveEffectHint:
        item_id_raw = raw.get("item_id")
        try:
            item_id = None if item_id_raw is None else UUID(str(item_id_raw))
            confidence = ObservationConfidence(_required_str(raw, "confidence"))
        except ValueError as exc:
            raise EffectStorageError("active-effect hint is invalid") from exc
        origin = _required_mapping(raw, "origin")
        return cls(
            source_kind=_required_str(raw, "source_kind"),
            selector_label=_required_str(raw, "selector_label"),
            content_hash=_required_str(raw, "content_hash"),
            origin_kind=_required_str(origin, "kind"),
            origin_id=_optional_str(origin, "source_id"),
            observable_signature=_required_str(raw, "observable_signature"),
            confidence=confidence,
            item_id=item_id,
            item_version=_optional_int(raw, "item_version"),
        )


@dataclass(frozen=True, slots=True)
class ObservedDeviceState:
    config_entry_id: str
    mode: str
    observed_at: str
    confidence: ObservationConfidence = ObservationConfidence.UNKNOWN
    diy_code: int | None = None
    effect: str | None = None
    native_mode: str | None = None
    matched_operation_id: UUID | None = None
    active_effect: ActiveEffectHint | None = None

    def __post_init__(self) -> None:
        validate_bounded_string(
            self.config_entry_id,
            "observed config entry ID",
            maximum=MAX_IDENTIFIER_LENGTH,
            error_type=EffectStorageError,
        )
        validate_bounded_string(
            self.mode,
            "observed mode",
            maximum=MAX_IDENTIFIER_LENGTH,
            error_type=EffectStorageError,
        )
        validate_timestamp(
            self.observed_at,
            "observation timestamp",
            error_type=EffectStorageError,
        )
        if self.diy_code is not None and not 0 <= self.diy_code <= 0xFFFF:
            raise EffectStorageError("observed DIY code must be from 0 to 65535")
        if self.effect is not None:
            validate_bounded_string(
                self.effect,
                "observed effect",
                maximum=MAX_IDENTIFIER_LENGTH,
                error_type=EffectStorageError,
            )
        if self.native_mode is not None:
            validate_bounded_string(
                self.native_mode,
                "observed native mode",
                maximum=MAX_IDENTIFIER_LENGTH,
                error_type=EffectStorageError,
            )
        if self.active_effect is not None and self.active_effect.confidence is not self.confidence:
            raise EffectStorageError("active-effect confidence must match observation confidence")

    def to_dict(self) -> dict[str, Any]:
        return {
            "config_entry_id": self.config_entry_id,
            "mode": self.mode,
            "observed_at": self.observed_at,
            "confidence": self.confidence.value,
            "diy_code": self.diy_code,
            "effect": self.effect,
            "native_mode": self.native_mode,
            "matched_operation_id": (str(self.matched_operation_id) if self.matched_operation_id is not None else None),
            "active_effect": self.active_effect.to_dict() if self.active_effect is not None else None,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> ObservedDeviceState:
        operation_raw = raw.get("matched_operation_id")
        try:
            operation_id = None if operation_raw is None else UUID(str(operation_raw))
            confidence = ObservationConfidence(_required_str(raw, "confidence"))
        except ValueError as exc:
            raise EffectStorageError("observed device state is invalid") from exc
        return cls(
            config_entry_id=_required_str(raw, "config_entry_id"),
            mode=_required_str(raw, "mode"),
            observed_at=_required_str(raw, "observed_at"),
            confidence=confidence,
            diy_code=_optional_int(raw, "diy_code"),
            effect=_optional_str(raw, "effect"),
            native_mode=_optional_str(raw, "native_mode"),
            matched_operation_id=operation_id,
            active_effect=(
                None
                if raw.get("active_effect") is None
                else ActiveEffectHint.from_dict(_required_mapping(raw, "active_effect"))
            ),
        )

    def to_public_dict(self) -> dict[str, Any]:
        return self.to_dict()


class EffectDeviceCache:
    def __init__(self, hass: HomeAssistant | VersionedDocumentStore) -> None:
        self._store = _device_cache_store(hass) if isinstance(hass, HomeAssistant) else hass
        self._data: dict[str, Any] | None = None

    async def async_load(self) -> tuple[ObservedDeviceState, ...]:
        stored = await self._store.async_load()
        data = {"devices": {}} if stored is None else stored
        states, data = _load_device_cache(data)
        stale_states = tuple(
            replace(
                state,
                confidence=ObservationConfidence.UNKNOWN,
                native_mode=None,
                matched_operation_id=None,
                active_effect=(
                    None
                    if state.active_effect is None
                    else replace(state.active_effect, confidence=ObservationConfidence.UNKNOWN)
                ),
            )
            for state in states
        )
        if stale_states != states:
            data = {"devices": {state.config_entry_id: state.to_dict() for state in stale_states}}
            self._store.async_delay_save(lambda: copy.deepcopy(data), delay=5)
            states = stale_states
        elif stored is not None and data != stored:
            await self._store.async_save(data)
        self._data = copy.deepcopy(data)
        return states

    def get(self, config_entry_id: str) -> ObservedDeviceState | None:
        devices = cast(dict[str, Any], self._require_loaded()["devices"])
        raw = devices.get(config_entry_id)
        return None if not isinstance(raw, Mapping) else ObservedDeviceState.from_dict(cast(Mapping[str, Any], raw))

    def set(self, state: ObservedDeviceState) -> None:
        candidate = copy.deepcopy(self._require_loaded())
        if state.config_entry_id not in candidate["devices"] and len(candidate["devices"]) >= MAX_DEVICE_CACHE_ENTRIES:
            oldest = min(
                candidate["devices"].values(),
                key=lambda raw: _required_str(_as_mapping(raw, "device state"), "observed_at"),
            )
            oldest_id = _required_str(_as_mapping(oldest, "device state"), "config_entry_id")
            candidate["devices"].pop(oldest_id, None)
        candidate["devices"][state.config_entry_id] = state.to_dict()
        _validate_device_cache(candidate)
        self._data = candidate
        self._store.async_delay_save(lambda: copy.deepcopy(self._require_loaded()), delay=5)

    async def async_delete_device(self, config_entry_id: str) -> None:
        candidate = copy.deepcopy(self._require_loaded())
        if candidate["devices"].pop(config_entry_id, None) is None:
            return
        _validate_device_cache(candidate)
        await self._store.async_save(candidate)
        self._data = candidate

    def detach_item(self, item_id: UUID) -> None:
        current = self._require_loaded()
        candidate = copy.deepcopy(current)
        changed = False
        for key, raw in candidate["devices"].items():
            state = ObservedDeviceState.from_dict(_as_mapping(raw, f"device state {key}"))
            hint = state.active_effect
            if hint is None or hint.item_id != item_id:
                continue
            candidate["devices"][key] = replace(
                state,
                active_effect=replace(
                    hint,
                    source_kind="deleted_effect",
                    item_id=None,
                    item_version=None,
                ),
            ).to_dict()
            changed = True
        if not changed:
            return
        _validate_device_cache(candidate)
        self._data = candidate
        self._store.async_delay_save(lambda: copy.deepcopy(self._require_loaded()), delay=5)

    async def async_flush(self) -> None:
        await self._store.async_save(copy.deepcopy(self._require_loaded()))

    async def async_reconcile_library_hashes(self, items: tuple[LibraryItem, ...]) -> None:
        hashes = {(item.id, item.version): item.content_hash for item in items}
        candidate = copy.deepcopy(self._require_loaded())
        changed = False
        for key, raw in candidate["devices"].items():
            state = ObservedDeviceState.from_dict(_as_mapping(raw, f"device state {key}"))
            hint = state.active_effect
            if hint is None or hint.source_kind != "saved_effect" or hint.item_id is None or hint.item_version is None:
                continue
            content_hash = hashes.get((hint.item_id, hint.item_version))
            if content_hash is None or content_hash == hint.content_hash:
                continue
            candidate["devices"][key] = replace(
                state,
                active_effect=replace(hint, content_hash=content_hash),
            ).to_dict()
            changed = True
        if not changed:
            return
        _validate_device_cache(candidate)
        await self._store.async_save(candidate)
        self._data = candidate

    def _require_loaded(self) -> dict[str, Any]:
        if self._data is None:
            raise EffectStorageError("device cache has not been loaded")
        return self._data


def _device_cache_store(hass: HomeAssistant) -> VersionedDocumentStore:
    return HomeAssistantVersionedDocumentStore(
        hass,
        DEVICE_CACHE_STORE_VERSION,
        DEVICE_CACHE_STORE_KEY,
        minor_version=DEVICE_CACHE_STORE_MINOR_VERSION,
        migrate=_async_migrate_device_cache,
    )


async def _async_migrate_device_cache(
    old_major_version: int,
    old_minor_version: int,
    old_data: dict[str, Any],
) -> dict[str, Any]:
    if old_major_version == DEVICE_CACHE_STORE_VERSION and old_minor_version <= DEVICE_CACHE_STORE_MINOR_VERSION:
        return old_data
    if old_major_version == 1 and old_minor_version <= 2:
        return old_data
    raise EffectStorageError(f"cannot migrate device-cache store version {old_major_version}.{old_minor_version}")


def _validate_device_cache(data: object) -> tuple[ObservedDeviceState, ...]:
    raw = _as_mapping(data, "device cache")
    validate_json_document(
        raw,
        "device cache",
        maximum_bytes=MAX_DEVICE_CACHE_STORE_BYTES,
        error_type=EffectStorageError,
        maximum_nodes=MAX_STORE_JSON_NODES,
    )
    devices = _required_mapping(raw, "devices")
    if len(devices) > MAX_DEVICE_CACHE_ENTRIES:
        raise EffectLimitError(f"device cache must not exceed {MAX_DEVICE_CACHE_ENTRIES} records")
    states = tuple(
        ObservedDeviceState.from_dict(_as_mapping(state, f"device state {key}")) for key, state in devices.items()
    )
    if any(state.config_entry_id != key for key, state in zip(devices, states, strict=True)):
        raise EffectStorageError("device-cache key does not match config entry ID")
    return states


def _load_device_cache(data: object) -> tuple[tuple[ObservedDeviceState, ...], dict[str, Any]]:
    raw = _as_mapping(data, "device cache")
    devices = _required_mapping(raw, "devices")
    states: list[ObservedDeviceState] = []
    invalid = 0
    for key, value in devices.items():
        try:
            validate_json_document(
                value,
                f"device state {key}",
                maximum_bytes=MAX_DEVICE_CACHE_STORE_BYTES,
                error_type=EffectStorageError,
            )
            state = ObservedDeviceState.from_dict(_as_mapping(value, "device state"))
            if state.config_entry_id != key:
                raise EffectStorageError("device-cache key does not match config entry ID")
        except EffectStorageError:
            invalid += 1
            continue
        states.append(state)
    states.sort(key=lambda state: state.observed_at, reverse=True)
    states = states[:MAX_DEVICE_CACHE_ENTRIES]
    candidate = {"devices": {state.config_entry_id: state.to_dict() for state in states}}
    if invalid:
        _LOGGER.warning("Discarded %d invalid Effect Studio device-cache record(s)", invalid)
    return _validate_device_cache(candidate), candidate
