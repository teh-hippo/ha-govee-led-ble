"""Current-only saved-effect storage and migration."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import STORAGE_DIR, Store, get_internal_store_manager

from custom_components.ha_govee_led_ble import effect_migration
from custom_components.ha_govee_led_ble.effect_active_workspace import (
    ActiveEffectWorkspace,
    ActiveEffectWorkspaceRepository,
)
from custom_components.ha_govee_led_ble.effect_backend import EffectBackend
from custom_components.ha_govee_led_ble.effect_catalogue import resolve_catalogue_template
from custom_components.ha_govee_led_ble.effect_deployments import (
    EffectDeploymentRepository,
    ObservationConfidence,
)
from custom_components.ha_govee_led_ble.effect_domain import (
    LibraryItem,
    Origin,
    PaintedEffect,
    SingleEffect,
    SourceKind,
)
from custom_components.ha_govee_led_ble.effect_migration import (
    LEGACY_DRAFT_STORE_KEY,
    MIGRATION_BACKUP_STORE_KEY,
)
from custom_components.ha_govee_led_ble.effect_scene_defaults import (
    NativeSceneDefault,
    NativeSceneDefaultRepository,
)
from custom_components.ha_govee_led_ble.effect_storage import (
    LIBRARY_STORE_KEY,
    LIBRARY_STORE_MINOR_VERSION,
    LIBRARY_STORE_VERSION,
    EffectLibraryRepository,
    EffectNotFoundError,
    EffectStorageError,
    EffectVersionConflictError,
)
from custom_components.ha_govee_led_ble.effect_template_defaults import (
    CatalogueTemplateDefault,
    CatalogueTemplateDefaultRepository,
)
from tests.storage_test_double import InMemoryVersionedDocumentStore

TIMESTAMP = "2026-08-17T00:00:00+00:00"


def _item(name: str = "Test", *, updated_at: str = TIMESTAMP) -> LibraryItem:
    return LibraryItem.new(
        name,
        SingleEffect(0, 0, 50, ((255, 0, 0),)),
        updated_at=updated_at,
    )


def test_legacy_migration_backup_treats_template_defaults_as_absent() -> None:
    documents = {
        key: None
        for key in effect_migration._LEGACY_DOCUMENT_KEYS  # noqa: SLF001
    }

    normalised = effect_migration._validate_backup(  # noqa: SLF001
        {"documents": documents}
    )

    assert set(normalised) == set(effect_migration._DOCUMENT_KEYS)  # noqa: SLF001
    assert normalised[effect_migration.TEMPLATE_DEFAULT_STORE_KEY] is None


async def test_current_only_library_creates_updates_and_hard_deletes() -> None:
    store = InMemoryVersionedDocumentStore()
    repository = EffectLibraryRepository(store)
    initial = await repository.async_load()
    assert initial.items == ()
    assert initial.generation == 0
    item = _item()

    created = await repository.async_create(item)
    updated_item = replace(
        item,
        version=2,
        updated_at="2026-08-17T00:01:00+00:00",
        name="Renamed",
    )
    updated = await repository.async_update(
        updated_item,
        expected_version=1,
        expected_updated_at=TIMESTAMP,
    )
    deleted = await repository.async_delete(
        item.id,
        expected_version=2,
        expected_updated_at=updated_item.updated_at,
    )

    assert created.items == (item,)
    assert created.generation == 1
    assert updated.items == (updated_item,)
    assert updated.generation == 2
    assert deleted.items == ()
    assert deleted.generation == 3
    with pytest.raises(EffectNotFoundError):
        repository.get(item.id)
    assert store.data == {"items": {}, "generation": 3}


async def test_template_defaults_round_trip_and_delete_by_device() -> None:
    store = InMemoryVersionedDocumentStore()
    repository = CatalogueTemplateDefaultRepository(store)
    assert await repository.async_load() == ()
    canonical = resolve_catalogue_template("H617A", "template:single:0:0")
    assert isinstance(canonical.content, SingleEffect)
    value = CatalogueTemplateDefault(
        config_entry_id="entry-a",
        model="H617A",
        template_id=canonical.id,
        updated_at=TIMESTAMP,
        content=replace(canonical.content, speed=75),
    )

    await repository.async_set(value)

    assert repository.get("entry-a", canonical.id) == value
    assert len(value.content_hash) == 64
    await repository.async_delete_device("entry-a")
    assert repository.get("entry-a", canonical.id) is None
    assert store.data == {"devices": {}}


async def test_template_defaults_reject_mismatched_structural_identity() -> None:
    with pytest.raises(EffectStorageError, match="structural identity"):
        CatalogueTemplateDefault(
            config_entry_id="entry-a",
            model="H617A",
            template_id="template:single:0:0",
            updated_at=TIMESTAMP,
            content=SingleEffect(1, 0, 50, ((255, 0, 0),)),
        )


async def test_active_workspace_keeps_only_the_latest_generation() -> None:
    store = InMemoryVersionedDocumentStore()
    repository = ActiveEffectWorkspaceRepository(store)
    assert await repository.async_load() == ()
    newest = ActiveEffectWorkspace(
        config_entry_id="entry-a",
        model="H617A",
        selector_label="Flow",
        content=SingleEffect(0, 0, 50, ((255, 0, 0),)),
        origin=Origin(SourceKind.CATALOGUE_TEMPLATE, "template:single:0:0"),
        observable_signature="custom:24",
        updated_at=TIMESTAMP,
        generation=2,
    )
    older = replace(
        newest,
        content=replace(newest.content, speed=25),
        generation=1,
    )

    assert repository.set(newest) is True
    assert repository.set(older) is False
    assert repository.get("entry-a") == newest
    assert repository.update_confidence(
        "entry-a",
        2,
        ObservationConfidence.ACTIVATION_MATCH,
    )
    assert repository.get("entry-a") == replace(
        newest,
        confidence=ObservationConfidence.ACTIVATION_MATCH,
    )

    await store.async_fire_delayed_save()
    restored = ActiveEffectWorkspaceRepository(store)
    assert await restored.async_load() == (replace(newest, confidence=ObservationConfidence.ACTIVATION_MATCH),)


async def test_active_workspace_rejects_content_hash_tampering() -> None:
    store = InMemoryVersionedDocumentStore()
    repository = ActiveEffectWorkspaceRepository(store)
    await repository.async_load()
    workspace = ActiveEffectWorkspace(
        config_entry_id="entry-a",
        model="H617A",
        selector_label="Flow",
        content=SingleEffect(0, 0, 50, ((255, 0, 0),)),
        origin=Origin(),
        observable_signature="custom:24",
        updated_at=TIMESTAMP,
        generation=1,
    )
    raw = workspace.to_dict()
    raw["content_hash"] = "0" * 64

    with pytest.raises(EffectStorageError, match="content hash"):
        await ActiveEffectWorkspaceRepository(
            InMemoryVersionedDocumentStore({"devices": {"entry-a": raw}})
        ).async_load()


@pytest.mark.parametrize(
    ("version", "updated_at"),
    [(0, TIMESTAMP), (1, "2026-08-17T00:00:01+00:00")],
)
async def test_update_rejects_stale_version_or_timestamp(version: int, updated_at: str) -> None:
    repository = EffectLibraryRepository(InMemoryVersionedDocumentStore())
    await repository.async_load()
    item = _item()
    await repository.async_create(item)

    with pytest.raises(EffectVersionConflictError) as error:
        await repository.async_update(
            replace(item, version=2, updated_at="2026-08-17T00:01:00+00:00"),
            expected_version=version,
            expected_updated_at=updated_at,
        )

    assert error.value.current_version == 1


async def test_update_rejects_origin_mutation() -> None:
    repository = EffectLibraryRepository(InMemoryVersionedDocumentStore())
    await repository.async_load()
    item = _item()
    await repository.async_create(item)

    with pytest.raises(EffectStorageError, match="origin is immutable"):
        await repository.async_update(
            replace(
                item,
                version=2,
                updated_at="2026-08-17T00:01:00+00:00",
                origin=Origin(SourceKind.IMPORTED, "other"),
            ),
            expected_version=1,
            expected_updated_at=TIMESTAMP,
        )


async def test_failed_save_does_not_publish_candidate_state(monkeypatch) -> None:
    repository = EffectLibraryRepository(InMemoryVersionedDocumentStore())
    await repository.async_load()
    listener = AsyncMock()
    repository.subscribe(listener)
    monkeypatch.setattr(repository._store, "async_save", AsyncMock(side_effect=OSError("disk unavailable")))

    with pytest.raises(OSError, match="disk unavailable"):
        await repository.async_create(_item())

    assert repository.snapshot().items == ()
    listener.assert_not_called()


async def test_legacy_migration_keeps_only_live_head(hass: HomeAssistant) -> None:
    live = _item()
    deleted = _item("Deleted")
    await _save_legacy_library(hass, live, deleted)

    snapshot = await EffectLibraryRepository(hass).async_load()
    (migrated,) = snapshot.items

    assert migrated.id == live.id
    assert migrated.version == 2
    assert migrated.name == "Current"
    assert migrated.origin == Origin()
    assert snapshot.generation == 0
    assert "Old" not in str(await Store[dict[str, Any]](hass, LIBRARY_STORE_VERSION, LIBRARY_STORE_KEY).async_load())


@pytest.mark.parametrize(
    ("background", "groups", "expected"),
    [
        (
            [0, 0, 0],
            [
                {"fill": [255, 0, 0], "segments": [0]},
                {"fill": [0, 0, 0], "segments": [1]},
            ],
            ((255, 0, 0), (0, 0, 0)) + (None,) * 13,
        ),
        (
            [1, 2, 3],
            [{"fill": [255, 0, 0], "segments": [0]}],
            ((255, 0, 0),) + ((1, 2, 3),) * 14,
        ),
    ],
)
async def test_current_library_migrates_legacy_painted_content(
    hass: HomeAssistant,
    background: list[int],
    groups: list[dict[str, Any]],
    expected: tuple[tuple[int, int, int] | None, ...],
) -> None:
    item = LibraryItem.new("Paint", PaintedEffect("clockwise", 50, 100, (None,) * 15))
    document = cast(dict[str, Any], item.to_dict())
    document["schema_version"] = 1
    document["content"] = {
        "kind": "h617a_painted",
        "effect": "clockwise",
        "speed": 50,
        "brightness": 100,
        "background": background,
        "groups": groups,
    }
    document["content_hash"] = "0" * 64
    await Store[dict[str, Any]](
        hass,
        2,
        LIBRARY_STORE_KEY,
        private=True,
        atomic_writes=True,
        minor_version=0,
    ).async_save({"items": {str(item.id): document}})

    (migrated,) = (await EffectLibraryRepository(hass).async_load()).items

    assert migrated.schema_version == 2
    assert isinstance(migrated.content, PaintedEffect)
    assert migrated.content.segments == expected
    assert migrated.content_hash != "0" * 64


@pytest.mark.parametrize("minor_version", [0, 1, 2])
async def test_current_library_migrations_delete_retired_special_diy_before_decoding(
    hass: HomeAssistant,
    minor_version: int,
) -> None:
    retained = _item("Retained")
    retained_document = retained.to_dict()
    if minor_version == 0:
        retained_document["schema_version"] = 1
        retained_document["content_hash"] = "0" * 64
    removed_id = UUID("00000000-0000-4000-8000-000000000099")
    await Store[dict[str, Any]](
        hass,
        LIBRARY_STORE_VERSION,
        LIBRARY_STORE_KEY,
        private=True,
        atomic_writes=True,
        minor_version=minor_version,
    ).async_save(
        {
            "items": {
                str(retained.id): retained_document,
                str(removed_id): {"content": {"kind": "special_diy"}},
            }
        }
    )

    snapshot = await EffectLibraryRepository(hass).async_load()

    assert snapshot.items == (retained,)
    assert snapshot.generation == 0
    migrated = await Store[dict[str, Any]](
        hass,
        LIBRARY_STORE_VERSION,
        LIBRARY_STORE_KEY,
        private=True,
        atomic_writes=True,
        minor_version=LIBRARY_STORE_MINOR_VERSION,
    ).async_load()
    assert migrated == {
        "items": {str(retained.id): retained.to_dict()},
        "generation": 0,
    }


async def test_current_library_rejects_overlapping_legacy_paint_groups(hass: HomeAssistant) -> None:
    item = LibraryItem.new("Paint", PaintedEffect("clockwise", 50, 100, (None,) * 15))
    document = cast(dict[str, Any], item.to_dict())
    document["schema_version"] = 1
    document["content"] = {
        "kind": "h617a_painted",
        "effect": "clockwise",
        "speed": 50,
        "brightness": 100,
        "background": [0, 0, 0],
        "groups": [
            {"fill": [255, 0, 0], "segments": [0]},
            {"fill": [0, 0, 255], "segments": [0]},
        ],
    }
    await Store[dict[str, Any]](
        hass,
        2,
        LIBRARY_STORE_KEY,
        private=True,
        atomic_writes=True,
        minor_version=0,
    ).async_save({"items": {str(item.id): document}})

    with pytest.raises(EffectStorageError, match="multiple groups"):
        await EffectLibraryRepository(hass).async_load()


@pytest.mark.parametrize("invalid_value", ["version", "name", "origin", "target"])
async def test_legacy_migration_reports_invalid_domain_values_as_storage_errors(
    hass: HomeAssistant,
    invalid_value: str,
) -> None:
    live = _item()
    data = _legacy_library_data(live)
    resource = data["resources"][str(live.id)]
    raw_item = resource["revisions"]["2"]
    if invalid_value == "version":
        resource["head_revision"] = 0
        resource["revisions"]["0"] = resource["revisions"].pop("2")
    elif invalid_value == "name":
        raw_item["name"] = " "
    elif invalid_value == "origin":
        raw_item["provenance"]["source_id"] = 17
    else:
        raw_item["target_hint"] = {"model": "H617A", "segment_count": 0}
    await Store[dict[str, Any]](
        hass,
        1,
        LIBRARY_STORE_KEY,
        private=True,
        atomic_writes=True,
        minor_version=1,
    ).async_save(data)

    with pytest.raises(EffectStorageError, match="legacy effect head is invalid"):
        await EffectLibraryRepository(hass).async_load()


async def test_multi_store_migration_restores_original_documents_after_failure(
    hass: HomeAssistant,
    monkeypatch,
) -> None:
    live = _item()
    await _save_legacy_library(hass, live)
    await _save_legacy_drafts(hass)
    _write_raw_store(hass, LIBRARY_STORE_KEY, 1, 1, _legacy_library_data(live))
    _write_raw_store(hass, LEGACY_DRAFT_STORE_KEY, 1, 1, {"owners": {}})
    library_path = Path(hass.config.path(STORAGE_DIR, LIBRARY_STORE_KEY))
    draft_path = Path(hass.config.path(STORAGE_DIR, LEGACY_DRAFT_STORE_KEY))
    original_library = library_path.read_text(encoding="utf-8")
    original_drafts = draft_path.read_text(encoding="utf-8")
    monkeypatch.setattr(
        EffectDeploymentRepository,
        "async_load",
        AsyncMock(side_effect=OSError("deployment migration failed")),
    )

    with pytest.raises(OSError, match="deployment migration failed"):
        await EffectBackend.async_create(hass)

    assert library_path.read_text(encoding="utf-8") == original_library
    assert draft_path.read_text(encoding="utf-8") == original_drafts
    backup_store: Store[dict[str, Any]] = Store(
        hass,
        1,
        MIGRATION_BACKUP_STORE_KEY,
        private=True,
        atomic_writes=True,
        minor_version=0,
    )
    assert await backup_store.async_load() is not None
    await backup_store.async_remove()


async def test_successful_multi_store_migration_removes_drafts_and_temporary_backup(
    hass: HomeAssistant,
) -> None:
    live = _item()
    await _save_legacy_library(hass, live)
    await _save_legacy_drafts(hass)
    _write_raw_store(hass, LIBRARY_STORE_KEY, 1, 1, _legacy_library_data(live))
    _write_raw_store(hass, LEGACY_DRAFT_STORE_KEY, 1, 1, {"owners": {}})
    draft_path = Path(hass.config.path(STORAGE_DIR, LEGACY_DRAFT_STORE_KEY))

    backend = await EffectBackend.async_create(hass)

    assert backend.library.get(live.id).name == "Current"
    assert (
        await Store[dict[str, Any]](
            hass,
            1,
            MIGRATION_BACKUP_STORE_KEY,
            private=True,
            atomic_writes=True,
            minor_version=0,
        ).async_load()
        is not None
    )
    assert draft_path.is_file()

    await backend.async_complete_storage_migration()

    assert (
        await Store[dict[str, Any]](
            hass,
            1,
            MIGRATION_BACKUP_STORE_KEY,
            private=True,
            atomic_writes=True,
            minor_version=0,
        ).async_load()
        is None
    )
    assert not draft_path.exists()


async def _save_legacy_library(
    hass: HomeAssistant,
    live: LibraryItem,
    deleted: LibraryItem | None = None,
) -> None:
    legacy = Store[dict[str, Any]](
        hass,
        1,
        LIBRARY_STORE_KEY,
        private=True,
        atomic_writes=True,
        minor_version=1,
    )
    await legacy.async_save(_legacy_library_data(live, deleted))


def _legacy_library_data(
    live: LibraryItem,
    deleted: LibraryItem | None = None,
) -> dict[str, Any]:
    resources: dict[str, Any] = {
        str(live.id): {
            "head_revision": 2,
            "deleted": False,
            "revisions": {
                "1": _legacy_item(live, revision=1, name="Old"),
                "2": _legacy_item(live, revision=2, name="Current"),
            },
        }
    }
    if deleted is not None:
        resources[str(deleted.id)] = {
            "head_revision": 1,
            "deleted": True,
            "revisions": {"1": _legacy_item(deleted, revision=1)},
        }
    return {"library_revision": 7, "resources": resources}


def _write_raw_store(
    hass: HomeAssistant,
    key: str,
    version: int,
    minor_version: int,
    data: dict[str, Any],
) -> None:
    path = Path(hass.config.path(STORAGE_DIR, key))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": version,
                "minor_version": minor_version,
                "key": key,
                "data": data,
            }
        ),
        encoding="utf-8",
    )
    get_internal_store_manager(hass).async_invalidate(key)


async def _save_legacy_drafts(hass: HomeAssistant) -> None:
    await Store[dict[str, Any]](
        hass,
        1,
        LEGACY_DRAFT_STORE_KEY,
        private=True,
        atomic_writes=True,
        minor_version=1,
    ).async_save({"owners": {}})


async def test_corrupt_current_store_fails_closed(hass: HomeAssistant) -> None:
    store = Store[dict[str, Any]](
        hass,
        LIBRARY_STORE_VERSION,
        LIBRARY_STORE_KEY,
        private=True,
        atomic_writes=True,
    )
    await store.async_save({"items": {"not-a-uuid": {"id": "not-a-uuid"}}})

    with pytest.raises(EffectStorageError):
        await EffectLibraryRepository(hass).async_load()


async def test_native_scene_defaults_persist_complete_bodies_and_delete_with_device() -> None:
    store = InMemoryVersionedDocumentStore()
    repository = NativeSceneDefaultRepository(store)
    await repository.async_load()
    value = NativeSceneDefault(
        config_entry_id="entry-a",
        scene_id=1,
        effect_id=2,
        updated_at=TIMESTAMP,
        canonical_body=b"\x01\x02\x03",
        speed_index=4,
    )

    await repository.async_set(value)
    reloaded = NativeSceneDefaultRepository(store)
    await reloaded.async_load()
    persisted = reloaded.get("entry-a", 1, 2)

    assert persisted == value
    assert persisted is not None
    assert persisted.content_hash == value.to_dict()["content_hash"]

    await reloaded.async_delete("entry-a", 1, 2)
    assert reloaded.get("entry-a", 1, 2) is None

    await reloaded.async_set(value)
    await reloaded.async_delete_device("entry-a")
    assert reloaded.get("entry-a", 1, 2) is None


def test_native_scene_default_rejects_body_hash_mismatch() -> None:
    value = NativeSceneDefault(
        config_entry_id="entry-a",
        scene_id=1,
        effect_id=2,
        updated_at=TIMESTAMP,
        canonical_body=b"\x01\x02\x03",
    )
    document = value.to_dict()
    document["content_hash"] = "0" * 64

    with pytest.raises(EffectStorageError, match="content hash"):
        NativeSceneDefault.from_dict(document)


def _legacy_item(item: LibraryItem, *, revision: int, name: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "id": str(item.id),
        "revision": revision,
        "name": name or item.name,
        "content": {
            "kind": "h617a_single",
            "family": 0,
            "variant": 0,
            "speed": 50,
            "palette": [[255, 0, 0]],
        },
        "provenance": {
            "source_kind": "authored",
            "source_id": None,
            "source_revision": None,
            "parent_id": None,
            "parent_revision": None,
        },
        "extensions": {},
    }
