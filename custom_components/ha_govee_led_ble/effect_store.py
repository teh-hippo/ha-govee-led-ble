"""Versioned document storage port and Home Assistant adapter."""

from __future__ import annotations

import asyncio
import copy
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .effect_persistence_validation import EffectStorageError

type EffectDocument = dict[str, Any]
type EffectDocumentFactory = Callable[[], EffectDocument]
type EffectDocumentMigration = Callable[[int, int, EffectDocument], Awaitable[EffectDocument]]


class VersionedDocumentStore(Protocol):
    """Persistence operations required by Effect Studio repositories."""

    async def async_load(self) -> EffectDocument | None: ...

    async def async_save(self, data: EffectDocument) -> None: ...

    def async_delay_save(self, data_func: EffectDocumentFactory, delay: float) -> None: ...


class DeviceDefaultsRepository[T]:
    """Shared lifecycle for validated, immediately persisted per-device defaults."""

    def __init__(
        self,
        store: VersionedDocumentStore,
        validate: Callable[[object], tuple[T, ...]],
        name: str,
    ) -> None:
        self._store = store
        self._validate = validate
        self._name = name
        self._data: EffectDocument | None = None
        self._generation = 0
        self._lock = asyncio.Lock()

    @property
    def generation(self) -> int:
        return self._generation

    def _replace_data(self, data: EffectDocument) -> None:
        self._data = data
        self._generation += 1

    async def async_load(self) -> tuple[T, ...]:
        async with self._lock:
            stored = await self._store.async_load()
            data = {"devices": {}} if stored is None else stored
            values = self._validate(data)
            self._replace_data(copy.deepcopy(data))
            return values

    async def async_delete_device(self, config_entry_id: str) -> None:
        async with self._lock:
            candidate = copy.deepcopy(self._require_loaded())
            if candidate["devices"].pop(config_entry_id, None) is None:
                return
            await self._store.async_save(candidate)
            self._replace_data(candidate)

    def _require_loaded(self) -> EffectDocument:
        if self._data is None:
            raise EffectStorageError(f"{self._name} store has not been loaded")
        return self._data


class _MigratingStore(Store[EffectDocument]):
    def __init__(
        self,
        hass: HomeAssistant,
        version: int,
        key: str,
        *,
        minor_version: int,
        migrate: EffectDocumentMigration,
    ) -> None:
        super().__init__(
            hass,
            version,
            key,
            private=True,
            atomic_writes=True,
            minor_version=minor_version,
        )
        self._migrate = migrate

    async def _async_migrate_func(
        self,
        old_major_version: int,
        old_minor_version: int,
        old_data: EffectDocument,
    ) -> EffectDocument:
        return await self._migrate(old_major_version, old_minor_version, old_data)


class HomeAssistantVersionedDocumentStore:
    """Versioned document store backed by Home Assistant storage."""

    def __init__(
        self,
        hass: HomeAssistant,
        version: int,
        key: str,
        *,
        minor_version: int,
        migrate: EffectDocumentMigration,
    ) -> None:
        self._store = _MigratingStore(
            hass,
            version,
            key,
            minor_version=minor_version,
            migrate=migrate,
        )

    async def async_load(self) -> EffectDocument | None:
        return await self._store.async_load()

    async def async_save(self, data: EffectDocument) -> None:
        await self._store.async_save(data)

    def async_delay_save(self, data_func: EffectDocumentFactory, delay: float) -> None:
        self._store.async_delay_save(data_func, delay)
