"""Versioned document storage port and Home Assistant adapter."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

type EffectDocument = dict[str, Any]
type EffectDocumentFactory = Callable[[], EffectDocument]
type EffectDocumentMigration = Callable[[int, int, EffectDocument], Awaitable[EffectDocument]]


class VersionedDocumentStore(Protocol):
    """Persistence operations required by Effect Studio repositories."""

    async def async_load(self) -> EffectDocument | None: ...

    async def async_save(self, data: EffectDocument) -> None: ...

    def async_delay_save(self, data_func: EffectDocumentFactory, delay: float) -> None: ...


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
