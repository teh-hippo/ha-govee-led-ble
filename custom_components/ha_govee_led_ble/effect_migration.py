"""Transactional backup for destructive Effect Studio storage migrations."""

from __future__ import annotations

import json
import os
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import STORAGE_DIR, Store, get_internal_store_manager
from homeassistant.util.file import write_utf8_file_atomic

from .const import DOMAIN
from .effect_deployments import (
    DEPLOYMENT_STORE_KEY,
    DEPLOYMENT_STORE_MINOR_VERSION,
    DEPLOYMENT_STORE_VERSION,
)
from .effect_identity import (
    DEVICE_CACHE_STORE_KEY,
    DEVICE_CACHE_STORE_MINOR_VERSION,
    DEVICE_CACHE_STORE_VERSION,
)
from .effect_persistence_validation import EffectStorageError
from .effect_scene_defaults import (
    SCENE_DEFAULT_STORE_KEY,
    SCENE_DEFAULT_STORE_MINOR_VERSION,
    SCENE_DEFAULT_STORE_VERSION,
)
from .effect_storage import LIBRARY_STORE_KEY, LIBRARY_STORE_MINOR_VERSION, LIBRARY_STORE_VERSION
from .effect_template_defaults import (
    TEMPLATE_DEFAULT_STORE_KEY,
    TEMPLATE_DEFAULT_STORE_MINOR_VERSION,
    TEMPLATE_DEFAULT_STORE_VERSION,
)
from .effect_user_state import USER_STATE_STORE_KEY, USER_STATE_STORE_MINOR_VERSION, USER_STATE_STORE_VERSION

MIGRATION_BACKUP_STORE_VERSION: Final = 1
MIGRATION_BACKUP_STORE_MINOR_VERSION: Final = 0
MIGRATION_BACKUP_STORE_KEY: Final = f"{DOMAIN}.effect_migration_backup"
LEGACY_DRAFT_STORE_KEY: Final = f"{DOMAIN}.effect_drafts"

_DOCUMENT_KEYS: Final = (
    LIBRARY_STORE_KEY,
    DEPLOYMENT_STORE_KEY,
    DEVICE_CACHE_STORE_KEY,
    USER_STATE_STORE_KEY,
    LEGACY_DRAFT_STORE_KEY,
    SCENE_DEFAULT_STORE_KEY,
    TEMPLATE_DEFAULT_STORE_KEY,
)
_LEGACY_DOCUMENT_KEYS: Final = tuple(key for key in _DOCUMENT_KEYS if key != TEMPLATE_DEFAULT_STORE_KEY)
_CURRENT_VERSIONS: Final = {
    LIBRARY_STORE_KEY: (LIBRARY_STORE_VERSION, LIBRARY_STORE_MINOR_VERSION),
    DEPLOYMENT_STORE_KEY: (DEPLOYMENT_STORE_VERSION, DEPLOYMENT_STORE_MINOR_VERSION),
    DEVICE_CACHE_STORE_KEY: (DEVICE_CACHE_STORE_VERSION, DEVICE_CACHE_STORE_MINOR_VERSION),
    USER_STATE_STORE_KEY: (USER_STATE_STORE_VERSION, USER_STATE_STORE_MINOR_VERSION),
    SCENE_DEFAULT_STORE_KEY: (SCENE_DEFAULT_STORE_VERSION, SCENE_DEFAULT_STORE_MINOR_VERSION),
    TEMPLATE_DEFAULT_STORE_KEY: (
        TEMPLATE_DEFAULT_STORE_VERSION,
        TEMPLATE_DEFAULT_STORE_MINOR_VERSION,
    ),
}


@dataclass(slots=True)
class EffectMigrationBackup:
    hass: HomeAssistant
    _store: Store[dict[str, Any]]
    _documents: dict[str, str | None] | None = None

    @classmethod
    async def async_prepare(cls, hass: HomeAssistant) -> EffectMigrationBackup:
        store = Store[dict[str, Any]](
            hass,
            MIGRATION_BACKUP_STORE_VERSION,
            MIGRATION_BACKUP_STORE_KEY,
            private=True,
            atomic_writes=True,
            minor_version=MIGRATION_BACKUP_STORE_MINOR_VERSION,
        )
        instance = cls(hass, store)
        existing = await store.async_load()
        if existing is not None:
            instance._documents = _validate_backup(existing)
            await instance.async_rollback()
            return instance

        documents = await instance._async_read_documents()
        if not _requires_migration(documents):
            return instance
        instance._documents = documents
        await store.async_save({"documents": documents})
        return instance

    @property
    def active(self) -> bool:
        return self._documents is not None

    async def async_commit(self) -> None:
        if self._documents is None:
            return
        await self._async_remove_document(LEGACY_DRAFT_STORE_KEY)
        await self._store.async_remove()
        self._documents = None

    async def async_rollback(self) -> None:
        if self._documents is None:
            return
        for key, content in self._documents.items():
            path = self._path(key)
            if content is None:
                await self.hass.async_add_executor_job(_remove_file, path)
            else:
                await self.hass.async_add_executor_job(write_utf8_file_atomic, path, content, True)
            get_internal_store_manager(self.hass).async_invalidate(key)

    async def _async_read_documents(self) -> dict[str, str | None]:
        return {key: await self.hass.async_add_executor_job(_read_file, self._path(key)) for key in _DOCUMENT_KEYS}

    async def _async_remove_document(self, key: str) -> None:
        await self.hass.async_add_executor_job(_remove_file, self._path(key))
        get_internal_store_manager(self.hass).async_invalidate(key)

    def _path(self, key: str) -> str:
        return self.hass.config.path(STORAGE_DIR, key)


def _requires_migration(documents: dict[str, str | None]) -> bool:
    if documents[LEGACY_DRAFT_STORE_KEY] is not None:
        return True
    for key, current_version in _CURRENT_VERSIONS.items():
        content = documents[key]
        if content is None:
            continue
        envelope = _parse_envelope(content, key)
        if (envelope["version"], envelope.get("minor_version", 1)) != current_version:
            return True
    return False


def _validate_backup(raw: object) -> dict[str, str | None]:
    if not isinstance(raw, dict) or set(raw) != {"documents"}:
        raise EffectStorageError("Effect Studio migration backup is malformed")
    documents = raw["documents"]
    if not isinstance(documents, dict):
        raise EffectStorageError("Effect Studio migration backup documents are malformed")
    if set(documents) == set(_LEGACY_DOCUMENT_KEYS):
        documents = {**documents, TEMPLATE_DEFAULT_STORE_KEY: None}
    elif set(documents) != set(_DOCUMENT_KEYS):
        raise EffectStorageError("Effect Studio migration backup documents are malformed")
    if any(value is not None and not isinstance(value, str) for value in documents.values()):
        raise EffectStorageError("Effect Studio migration backup document is malformed")
    return cast(dict[str, str | None], documents)


def _parse_envelope(content: str, key: str) -> dict[str, Any]:
    try:
        envelope = json.loads(content)
    except json.JSONDecodeError as exc:
        raise EffectStorageError(f"Effect Studio storage document {key} is not valid JSON") from exc
    if not isinstance(envelope, dict):
        raise EffectStorageError(f"Effect Studio storage document {key} is malformed")
    if not isinstance(envelope.get("version"), int) or isinstance(envelope.get("version"), bool):
        raise EffectStorageError(f"Effect Studio storage document {key} has no valid version")
    minor_version = envelope.get("minor_version", 1)
    if not isinstance(minor_version, int) or isinstance(minor_version, bool):
        raise EffectStorageError(f"Effect Studio storage document {key} has no valid minor version")
    if envelope.get("key") != key or "data" not in envelope:
        raise EffectStorageError(f"Effect Studio storage document {key} has an invalid envelope")
    return cast(dict[str, Any], envelope)


def _read_file(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def _remove_file(path: str) -> None:
    with suppress(FileNotFoundError):
        os.unlink(path)
