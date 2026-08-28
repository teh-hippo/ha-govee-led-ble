"""Effect Studio application use cases."""

from __future__ import annotations

import asyncio
from hashlib import sha256
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.effect_application import EffectStudioApplication
from custom_components.ha_govee_led_ble.effect_deployments import (
    DeploymentPhase,
    DeploymentRecord,
    EffectDeploymentRepository,
    ObservationConfidence,
)
from custom_components.ha_govee_led_ble.effect_domain import (
    AppliedArea,
    BrightnessOrder,
    BrightnessPattern,
    CatalogueRef,
    Distribution,
    EffectLayer,
    EffectValidationError,
    LayeredEffect,
    LayeredScene,
    LibraryItem,
    Movement,
    Origin,
    Selection,
    SelectionType,
    SourceKind,
    TargetHint,
    effect_content_from_dict,
    effect_content_to_dict,
)
from custom_components.ha_govee_led_ble.effect_identity import (
    ActiveEffectHint,
    EffectDeviceCache,
    ObservedDeviceState,
)
from custom_components.ha_govee_led_ble.effect_runtime import EffectDeploymentEngine
from custom_components.ha_govee_led_ble.effect_storage import (
    EffectLibraryRepository,
    EffectVersionConflictError,
)
from custom_components.ha_govee_led_ble.effect_user_state import EffectUserStateRepository
from tests.storage_test_double import InMemoryVersionedDocumentStore

CONTENT = {
    "kind": "h617a_single",
    "family": 0,
    "variant": 0,
    "speed": 50,
    "palette": [[255, 0, 0]],
}


def _layered_content(layer_count: int = 1) -> dict[str, Any]:
    layer = EffectLayer(
        area=AppliedArea(0, 10),
        selection=Selection(SelectionType.CUSTOM, 1, 2),
        brightness_gradient=True,
        brightness_patterns=(BrightnessPattern(100, 10, BrightnessOrder.BRIGHTEST_DARKEST, 50, 3, 4),),
        distribution=Distribution(2),
        colour_speed=60,
        colour_retention=5,
        palette=((255, 0, 0), (0, 0, 255)),
        selected_movement=Movement(True, False, 1, 3, 50),
        overall_movement=Movement(False, True, 2, 1, 20),
        priority=3,
    )
    return effect_content_to_dict(LayeredEffect((layer,) * layer_count))


def _layered_scene_content() -> dict[str, Any]:
    effect = cast(LayeredEffect, effect_content_from_dict(_layered_content()))
    return effect_content_to_dict(
        LayeredScene(
            CatalogueRef("H617A", 1, 2),
            effect,
        ),
    )


async def _application() -> EffectStudioApplication:
    library = EffectLibraryRepository(InMemoryVersionedDocumentStore())
    deployments = EffectDeploymentRepository(InMemoryVersionedDocumentStore())
    user_state = EffectUserStateRepository(InMemoryVersionedDocumentStore())
    device_cache = EffectDeviceCache(InMemoryVersionedDocumentStore())
    await library.async_load()
    await deployments.async_load()
    await user_state.async_load()
    await device_cache.async_load()
    return EffectStudioApplication(library, deployments, user_state, device_cache)


async def test_library_use_cases_publish_current_versions_and_hard_delete() -> None:
    application = await _application()
    listener = MagicMock()
    application.subscribe_library(listener)

    created = await application.async_create_library_item(name="Effect", content=CONTENT)
    updated = await application.async_update_library_item(
        item_id=str(created.item.id),
        name="Updated",
        content={**CONTENT, "speed": 60},
        expected_version=created.item.version,
        expected_updated_at=created.item.updated_at,
    )
    deployment = _deployment(created.item)
    await application.deployments.async_put(deployment, expected_version=0)
    assert application.device_cache is not None
    application.device_cache.set(
        ObservedDeviceState(
            config_entry_id="entry-a",
            mode="custom",
            observed_at="2026-08-17T00:00:00Z",
            confidence=ObservationConfidence.ACTIVATION_MATCH,
            diy_code=800,
            matched_operation_id=deployment.operation_id,
            active_effect=ActiveEffectHint.from_record(
                deployment,
                observable_signature="custom:800",
                confidence=ObservationConfidence.ACTIVATION_MATCH,
            ),
        )
    )
    deleted = await application.async_delete_library_item(
        item_id=str(created.item.id),
        expected_version=updated.item.version,
        expected_updated_at=updated.item.updated_at,
    )

    assert created.item.version == 1
    assert updated.item.version == 2
    assert updated.item.updated_at > created.item.updated_at
    assert deleted.items == ()
    detached = application.deployments.get(deployment.operation_id)
    assert detached.source_kind == "deleted_effect"
    assert detached.item_id is None
    assert detached.item_version is None
    active_effect = application.device_cache.get("entry-a")
    assert active_effect is not None
    assert active_effect.active_effect is not None
    assert active_effect.active_effect.source_kind == "deleted_effect"
    assert active_effect.active_effect.item_id is None
    assert listener.call_count == 3


async def test_library_use_cases_reject_stale_write_token() -> None:
    application = await _application()
    created = await application.async_create_library_item(name="Effect", content=CONTENT)

    with pytest.raises(EffectVersionConflictError):
        await application.async_update_library_item(
            item_id=str(created.item.id),
            name="Stale",
            content=CONTENT,
            expected_version=0,
            expected_updated_at=created.item.updated_at,
        )


async def test_library_names_are_unique_and_do_not_shadow_native_effects() -> None:
    application = await _application()
    created = await application.async_create_library_item(name="My Effect", content=CONTENT)

    with pytest.raises(EffectValidationError, match="already in use"):
        await application.async_create_library_item(name="  my   effect  ", content=CONTENT)
    with pytest.raises(EffectValidationError, match="reserved"):
        await application.async_create_library_item(name="Candy", content=CONTENT)
    with pytest.raises(EffectValidationError, match="reserved"):
        await application.async_create_library_item(name="Custom", content=CONTENT)
    with pytest.raises(EffectValidationError, match="reserved"):
        await application.async_create_library_item(name="Energetic [Reactive]", content=CONTENT)
    with pytest.raises(EffectValidationError, match="reserved"):
        await application.async_create_library_item(name="Scene: Candy", content=CONTENT)
    with pytest.raises(EffectValidationError, match="reserved"):
        await application.async_update_library_item(
            item_id=str(created.item.id),
            name="Video: Movie",
            content=CONTENT,
            expected_version=created.item.version,
            expected_updated_at=created.item.updated_at,
        )


async def test_grandfathered_reserved_name_can_keep_its_name_when_edited() -> None:
    application = await _application()
    legacy = application.new_authored_item(name="Custom", content=CONTENT)
    await application.library.async_create(legacy)

    updated = await application.async_update_library_item(
        item_id=str(legacy.id),
        name="Custom",
        content={**CONTENT, "speed": 60},
        expected_version=legacy.version,
        expected_updated_at=legacy.updated_at,
    )

    assert updated.item.name == "Custom"
    assert effect_content_to_dict(updated.item.content)["speed"] == 60

    with pytest.raises(EffectValidationError, match="reserved"):
        await application.async_update_library_item(
            item_id=str(legacy.id),
            name="Scene: Candy",
            content=CONTENT,
            expected_version=updated.item.version,
            expected_updated_at=updated.item.updated_at,
        )


async def test_name_status_uses_reserved_precedence_and_identifies_saved_items() -> None:
    application = await _application()
    saved = await application.async_create_library_item(name="Saved", content=CONTENT)
    grandfathered = application.new_authored_item(name="Custom", content=CONTENT)
    await application.library.async_create(grandfathered)

    assert application.saved_effect_name_status("Available").kind == "available"
    assert application.saved_effect_name_status("Saved", excluding_item_id=str(saved.item.id)).kind == "same_item"
    conflict = application.saved_effect_name_status("Saved")
    assert conflict.kind == "saved"
    assert conflict.item == saved.item
    assert application.saved_effect_name_status("Custom", excluding_item_id=str(grandfathered.id)).kind == "reserved"


@pytest.mark.parametrize(
    ("labels", "message"),
    [
        ([0], "integers"),
        ([True], "integers"),
        ([256], "integers"),
        ([1, 1], "unique"),
        ([1, 2], "layer count"),
    ],
)
async def test_layer_labels_are_validated(labels: list[int], message: str) -> None:
    application = await _application()

    with pytest.raises(EffectValidationError, match=message):
        await application.async_create_library_item(
            name="Layered",
            content=_layered_content(),
            layer_labels=labels,
        )

    with pytest.raises(EffectValidationError, match="layered editor"):
        await application.async_create_library_item(
            name="Single",
            content=CONTENT,
            layer_labels=[1],
        )


async def test_layer_metadata_updates_without_replacing_unrelated_extensions() -> None:
    application = await _application()
    created = await application.async_create_library_item(
        name="Created layered",
        content=_layered_content(),
        layer_labels=[4],
    )
    assert created.item.extensions == {
        "ha_govee_led_ble.editor": {"layer_labels": [4]},
    }
    original = application.new_authored_item(
        name="Layered",
        content=_layered_content(),
        layer_labels=[9],
    )
    original = LibraryItem(
        id=original.id,
        version=original.version,
        updated_at=original.updated_at,
        name=original.name,
        content=original.content,
        origin=original.origin,
        target_hint=original.target_hint,
        extensions={
            "vendor.example": {"keep": True},
            "ha_govee_led_ble.editor": {"layer_labels": [9]},
        },
    )
    await application.library.async_create(original)

    updated = await application.async_update_library_item(
        item_id=str(original.id),
        name="Layered",
        content=_layered_content(2),
        layer_labels=[3, 1],
        expected_version=original.version,
        expected_updated_at=original.updated_at,
    )

    assert updated.item.extensions == {
        "vendor.example": {"keep": True},
        "ha_govee_led_ble.editor": {"layer_labels": [3, 1]},
    }


async def test_layered_scene_metadata_uses_the_nested_effect_layers() -> None:
    application = await _application()

    created = await application.async_create_library_item(
        name="Layered scene",
        content=_layered_scene_content(),
        layer_labels=[6],
    )

    assert created.item.extensions == {
        "ha_govee_led_ble.editor": {"layer_labels": [6]},
    }


async def test_overwrite_retains_target_identity_and_leaves_source_untouched(monkeypatch) -> None:
    application = await _application()
    source = await application.async_create_library_item(name="Source", content=CONTENT)
    target_item = LibraryItem.new(
        "Target",
        source.item.content,
        origin=Origin(SourceKind.IMPORTED, "import-a"),
        target_hint=TargetHint("H617A", 15),
        extensions={"vendor.example": {"keep": True}},
    )
    await application.library.async_create(target_item)
    monkeypatch.setattr("custom_components.ha_govee_led_ble.effect_storage.MAX_LIBRARY_ITEMS", 2)

    overwritten = await application.async_overwrite_library_item(
        target_item_id=str(target_item.id),
        name="Target",
        content=_layered_content(),
        layer_labels=[7],
        expected_version=target_item.version,
        expected_updated_at=target_item.updated_at,
    )

    assert application.get_saved_effect(str(source.item.id)) == source.item
    assert overwritten.item.id == target_item.id
    assert overwritten.item.origin == target_item.origin
    assert overwritten.item.target_hint == target_item.target_hint
    assert overwritten.item.version == target_item.version + 1
    assert overwritten.item.updated_at > target_item.updated_at
    assert overwritten.item.extensions == {
        "vendor.example": {"keep": True},
        "ha_govee_led_ble.editor": {"layer_labels": [7]},
    }
    assert len(overwritten.snapshot.items) == 2


async def test_concurrent_overwrites_reject_the_stale_target_token() -> None:
    application = await _application()
    target = await application.async_create_library_item(name="Target", content=CONTENT)

    results = await asyncio.gather(
        application.async_overwrite_library_item(
            target_item_id=str(target.item.id),
            name="Target",
            content={**CONTENT, "speed": 60},
            expected_version=target.item.version,
            expected_updated_at=target.item.updated_at,
        ),
        application.async_overwrite_library_item(
            target_item_id=str(target.item.id),
            name="Target",
            content={**CONTENT, "speed": 70},
            expected_version=target.item.version,
            expected_updated_at=target.item.updated_at,
        ),
        return_exceptions=True,
    )

    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert sum(isinstance(result, EffectVersionConflictError) for result in results) == 1
    assert application.library_snapshot().generation == 2


async def test_overwrite_rechecks_name_conflicts_under_the_mutation_lock() -> None:
    application = await _application()
    target = await application.async_create_library_item(name="Target", content=CONTENT)
    await application.async_create_library_item(name="Occupied", content=CONTENT)

    with pytest.raises(EffectValidationError, match="already in use"):
        await application.async_overwrite_library_item(
            target_item_id=str(target.item.id),
            name="Occupied",
            content={**CONTENT, "speed": 60},
            expected_version=target.item.version,
            expected_updated_at=target.item.updated_at,
        )

    assert application.get_saved_effect(str(target.item.id)) == target.item


async def test_failed_library_delete_restores_deployment_link(monkeypatch) -> None:
    application = await _application()
    created = await application.async_create_library_item(name="Effect", content=CONTENT)
    deployment = _deployment(created.item)
    await application.deployments.async_put(deployment, expected_version=0)
    monkeypatch.setattr(
        application.library._store,
        "async_save",
        AsyncMock(side_effect=OSError("library unavailable")),
    )

    with pytest.raises(OSError, match="library unavailable"):
        await application.async_delete_library_item(
            item_id=str(created.item.id),
            expected_version=created.item.version,
            expected_updated_at=created.item.updated_at,
        )

    assert application.get_saved_effect(str(created.item.id)) == created.item
    restored = application.deployments.get(deployment.operation_id)
    assert restored.source_kind == "saved_effect"
    assert restored.item_id == created.item.id
    assert restored.item_version == created.item.version


async def test_hard_delete_waits_for_saved_effect_application() -> None:
    application = await _application()
    created = await application.async_create_library_item(name="Effect", content=CONTENT)
    entered = asyncio.Event()
    release = asyncio.Event()
    applied: list[LibraryItem] = []

    async def apply_saved(_coordinator, item, **_kwargs):
        applied.append(item)
        entered.set()
        await release.wait()
        return _deployment(item)

    engine = cast(
        EffectDeploymentEngine,
        SimpleNamespace(async_apply_saved=apply_saved),
    )
    coordinator = cast(GoveeBLECoordinator, SimpleNamespace())
    apply_task = asyncio.create_task(
        application.async_apply_saved_effect(
            engine,
            coordinator,
            item_id=str(created.item.id),
            config_entry_id="entry-a",
            updated_at="2026-08-17T00:00:00Z",
        )
    )
    await entered.wait()
    delete_task = asyncio.create_task(
        application.async_delete_library_item(
            item_id=str(created.item.id),
            expected_version=created.item.version,
            expected_updated_at=created.item.updated_at,
        )
    )
    await asyncio.sleep(0)

    assert not delete_task.done()

    release.set()
    await apply_task
    await delete_task

    assert applied == [created.item]
    assert application.library_snapshot().items == ()


async def test_name_based_apply_rejects_a_concurrently_changed_version() -> None:
    application = await _application()
    created = await application.async_create_library_item(name="Effect", content=CONTENT)
    await application.async_update_library_item(
        item_id=str(created.item.id),
        name="Renamed",
        content=CONTENT,
        expected_version=created.item.version,
        expected_updated_at=created.item.updated_at,
    )

    with pytest.raises(EffectVersionConflictError):
        await application.async_apply_saved_effect(
            AsyncMock(),
            cast(GoveeBLECoordinator, SimpleNamespace()),
            item_id=str(created.item.id),
            config_entry_id="entry-a",
            updated_at="2026-08-17T00:00:00Z",
            expected_version=created.item.version,
        )


async def test_user_state_keeps_only_device_navigation_and_colours() -> None:
    application = await _application()

    updated = application.update_user_state(
        "user-a",
        selected_config_entry_id="entry-a",
        navigation={"section": "scenes", "item_id": "effect-a"},
    )
    coloured = application.record_user_colour("user-a", (1, 2, 3))

    assert updated.selected_config_entry_id == "entry-a"
    assert updated.navigation == {"section": "scenes", "item_id": "effect-a"}
    assert coloured.recent_colours == ((1, 2, 3),)


def _deployment(item: LibraryItem) -> DeploymentRecord:
    return DeploymentRecord(
        operation_id=uuid4(),
        config_entry_id="entry-a",
        diy_code=800,
        phase=DeploymentPhase.CONFIRMED,
        compiler_version=1,
        artifact_sha256=sha256(b"artifact").hexdigest(),
        updated_at="2026-08-17T00:00:00Z",
        source_kind="saved_effect",
        selector_label=item.name,
        source_origin_kind=item.origin.kind.value,
        source_content_hash=item.content_hash,
        item_id=item.id,
        item_version=item.version,
    )
