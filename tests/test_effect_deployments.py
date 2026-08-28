"""Deployment, observation and user-state persistence remain separate from the library."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from typing import Any
from uuid import uuid4

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from custom_components.ha_govee_led_ble.effect_deployments import (
    DEPLOYMENT_STORE_KEY,
    DEPLOYMENT_STORE_MINOR_VERSION,
    DEPLOYMENT_STORE_VERSION,
    DeploymentPhase,
    DeploymentRecord,
    EffectDeploymentRepository,
    ObservationConfidence,
    PriorControlState,
)
from custom_components.ha_govee_led_ble.effect_domain import (
    LibraryItem,
    PaintedEffect,
    SingleEffect,
    effect_content_hash,
)
from custom_components.ha_govee_led_ble.effect_identity import (
    DEVICE_CACHE_STORE_KEY,
    DEVICE_CACHE_STORE_MINOR_VERSION,
    DEVICE_CACHE_STORE_VERSION,
    ActiveEffectHint,
    EffectDeviceCache,
    ObservedDeviceState,
)
from custom_components.ha_govee_led_ble.effect_limits import (
    MAX_DEPLOYMENT_RECORDS,
    MAX_JSON_STRING_LENGTH,
)
from custom_components.ha_govee_led_ble.effect_storage import (
    EffectNotFoundError,
    EffectStorageError,
    EffectVersionConflictError,
)
from custom_components.ha_govee_led_ble.effect_user_state import (
    MAX_RECENT_COLOURS,
    USER_STATE_STORE_KEY,
    USER_STATE_STORE_MINOR_VERSION,
    USER_STATE_STORE_VERSION,
    EffectUserState,
    EffectUserStateRepository,
)
from tests.storage_test_double import InMemoryVersionedDocumentStore


def _item() -> LibraryItem:
    return LibraryItem.new("Test", SingleEffect(0, 0, 50, ((255, 0, 0),)))


def _deployment(phase: DeploymentPhase = DeploymentPhase.COMPILING) -> DeploymentRecord:
    item = _item()
    return DeploymentRecord(
        operation_id=uuid4(),
        config_entry_id="entry-a",
        diy_code=800,
        phase=phase,
        compiler_version=1,
        artifact_sha256=sha256(b"artifact").hexdigest(),
        updated_at="2026-08-11T00:00:00Z",
        source_kind="saved_effect",
        selector_label=item.name,
        source_origin_kind=item.origin.kind.value,
        source_content_hash=item.content_hash,
        item_id=item.id,
        item_version=1,
    )


async def test_personal_repositories_use_injected_stores_without_home_assistant() -> None:
    user_store = InMemoryVersionedDocumentStore()
    user_state = EffectUserStateRepository(user_store)
    await user_state.async_load()
    state = EffectUserState("user-a", navigation={"section": "scenes"})
    user_state.set(state)

    assert user_store.data is None
    assert user_store.delayed_seconds == 5

    await user_store.async_fire_delayed_save()
    reloaded_user_state = EffectUserStateRepository(user_store)
    await reloaded_user_state.async_load()
    assert reloaded_user_state.get("user-a") == state


async def test_library_hash_reconciliation_updates_deployments_and_active_hints() -> None:
    item = _item()
    stale_hash = "0" * 64
    deployment_store = InMemoryVersionedDocumentStore()
    deployments = EffectDeploymentRepository(deployment_store)
    await deployments.async_load()
    record = replace(
        _deployment(DeploymentPhase.CONFIRMED),
        item_id=item.id,
        item_version=item.version,
        source_content_hash=stale_hash,
    )
    await deployments.async_put(record, expected_version=0)

    cache_store = InMemoryVersionedDocumentStore()
    cache = EffectDeviceCache(cache_store)
    await cache.async_load()
    state = ObservedDeviceState(
        config_entry_id="entry-a",
        mode="custom",
        observed_at="2026-08-11T00:00:00Z",
        confidence=ObservationConfidence.ACTIVATION_MATCH,
        diy_code=800,
        active_effect=replace(
            ActiveEffectHint.from_record(
                record,
                observable_signature="custom:800",
                confidence=ObservationConfidence.ACTIVATION_MATCH,
            ),
            content_hash=stale_hash,
        ),
    )
    cache.set(state)
    await cache.async_flush()

    await deployments.async_reconcile_library_hashes((item,))
    await cache.async_reconcile_library_hashes((item,))

    assert deployments.get(record.operation_id).source_content_hash == item.content_hash
    reconciled = cache.get("entry-a")
    assert reconciled is not None
    assert reconciled.active_effect is not None
    assert reconciled.active_effect.content_hash == item.content_hash


async def test_config_entry_removal_purges_device_scoped_effect_state() -> None:
    deployment_store = InMemoryVersionedDocumentStore()
    deployments = EffectDeploymentRepository(deployment_store)
    await deployments.async_load()
    removed = _deployment()
    retained = replace(
        _deployment(),
        config_entry_id="entry-b",
    )
    await deployments.async_put(removed, expected_version=0)
    await deployments.async_put(retained, expected_version=1)

    await deployments.async_delete_device("entry-a")

    assert deployments.get_optional(removed.operation_id) is None
    assert deployments.get(retained.operation_id) == retained

    cache_store = InMemoryVersionedDocumentStore()
    cache = EffectDeviceCache(cache_store)
    await cache.async_load()
    cache.set(
        ObservedDeviceState(
            config_entry_id="entry-a",
            mode="custom",
            observed_at="2026-08-11T00:00:00Z",
        )
    )
    await cache.async_delete_device("entry-a")
    assert cache.get("entry-a") is None

    user_store = InMemoryVersionedDocumentStore()
    user_state = EffectUserStateRepository(user_store)
    await user_state.async_load()
    user_state.set(
        EffectUserState(
            "user-a",
            selected_config_entry_id="entry-a",
            navigation={"section": "scenes"},
        )
    )
    await user_state.async_clear_config_entry("entry-a")
    assert user_state.get("user-a").selected_config_entry_id is None
    assert user_state.get("user-a").navigation == {"section": "scenes"}


async def test_deployment_repositories_use_injected_stores_without_home_assistant() -> None:
    deployment_store = InMemoryVersionedDocumentStore()
    deployments = EffectDeploymentRepository(deployment_store)
    await deployments.async_load()
    pending = _deployment()
    await deployments.async_put(pending, expected_version=0)

    reloaded_deployments = EffectDeploymentRepository(deployment_store)
    snapshot = await reloaded_deployments.async_load()

    assert snapshot.version == 2
    interrupted = reloaded_deployments.get(pending.operation_id)
    assert interrupted.phase is DeploymentPhase.FAILED
    assert interrupted.error_code == "home_assistant_restarted_before_write"
    assert deployment_store.save_count == 2

    progress = replace(
        interrupted,
        progress_current=1,
        progress_total=2,
    )
    await reloaded_deployments.async_put(
        progress,
        expected_version=snapshot.version,
        durable=False,
    )
    assert deployment_store.save_count == 2
    assert deployment_store.delayed_seconds == 5

    cache_store = InMemoryVersionedDocumentStore()
    cache = EffectDeviceCache(cache_store)
    await cache.async_load()
    observed = ObservedDeviceState(
        config_entry_id="entry-a",
        mode="diy",
        observed_at="2026-08-11T00:00:00Z",
        confidence=ObservationConfidence.EXACT_SESSION,
        matched_operation_id=pending.operation_id,
    )
    cache.set(observed)

    assert cache_store.data is None
    assert cache_store.delayed_seconds == 5

    await cache_store.async_fire_delayed_save()
    reloaded_cache = EffectDeviceCache(cache_store)
    states = await reloaded_cache.async_load()
    assert states[0].confidence is ObservationConfidence.UNKNOWN
    assert states[0].matched_operation_id is None


async def test_deployment_transitions_are_durable(hass: HomeAssistant) -> None:
    repository = EffectDeploymentRepository(hass)
    assert (await repository.async_load()).version == 0
    pending = _deployment()

    saved = await repository.async_put(pending, expected_version=0)
    confirmed = replace(
        pending,
        phase=DeploymentPhase.CONFIRMED,
        updated_at="2026-08-11T00:00:10Z",
    )
    saved = await repository.async_put(confirmed, expected_version=saved.version)

    reloaded = EffectDeploymentRepository(hass)
    assert (await reloaded.async_load()).version == saved.version
    assert reloaded.get(pending.operation_id).phase is DeploymentPhase.CONFIRMED

    with pytest.raises(EffectVersionConflictError):
        await reloaded.async_put(confirmed, expected_version=0)
    with pytest.raises(EffectNotFoundError):
        reloaded.get(uuid4())


@pytest.mark.parametrize(
    ("phase", "progress_current", "progress_total", "terminal_phase", "error_code"),
    [
        (
            DeploymentPhase.COMPILING,
            0,
            5,
            DeploymentPhase.FAILED,
            "home_assistant_restarted_before_write",
        ),
        (DeploymentPhase.UPLOADING, 2, 5, DeploymentPhase.UNCERTAIN, "home_assistant_restarted"),
        (DeploymentPhase.ACTIVATING, 4, 5, DeploymentPhase.UNCERTAIN, "home_assistant_restarted"),
        (DeploymentPhase.VERIFYING, 5, 5, DeploymentPhase.UNCERTAIN, "home_assistant_restarted"),
        (DeploymentPhase.RECOVERING, 5, 5, DeploymentPhase.UNCERTAIN, "home_assistant_restarted"),
    ],
)
async def test_inflight_deployment_gets_truthful_terminal_state_after_restart(
    hass: HomeAssistant,
    phase: DeploymentPhase,
    progress_current: int,
    progress_total: int,
    terminal_phase: DeploymentPhase,
    error_code: str,
) -> None:
    repository = EffectDeploymentRepository(hass)
    await repository.async_load()
    inflight = replace(
        _deployment(phase),
        progress_current=progress_current,
        progress_total=progress_total,
    )
    await repository.async_put(inflight, expected_version=0)

    reloaded = EffectDeploymentRepository(hass)
    snapshot = await reloaded.async_load()
    interrupted = reloaded.get(inflight.operation_id)

    assert snapshot.version == 2
    assert interrupted.phase is terminal_phase
    assert interrupted.error_code == error_code
    assert interrupted.progress_current == progress_current
    assert interrupted.progress_total == progress_total


@pytest.mark.parametrize(
    ("legacy_phase", "canonical_phase"),
    [
        (DeploymentPhase.PENDING, DeploymentPhase.FAILED),
        (DeploymentPhase.UNKNOWN, DeploymentPhase.UNCERTAIN),
        (DeploymentPhase.INTERRUPTED, DeploymentPhase.UNCERTAIN),
    ],
)
async def test_legacy_deployment_phases_remain_loadable(
    hass: HomeAssistant,
    legacy_phase: DeploymentPhase,
    canonical_phase: DeploymentPhase,
) -> None:
    legacy = _deployment(legacy_phase)
    store = Store[dict[str, Any]](
        hass,
        1,
        DEPLOYMENT_STORE_KEY,
        private=True,
        atomic_writes=True,
        minor_version=3,
    )
    legacy_document = legacy.to_dict()
    legacy_document["item_revision"] = legacy_document.pop("item_version")
    for key in (
        "source_kind",
        "selector_label",
        "source_origin_kind",
        "source_origin_id",
        "source_content_hash",
    ):
        legacy_document.pop(key)
    await store.async_save(
        {
            "revision": 1,
            "records": {str(legacy.operation_id): legacy_document},
        }
    )

    repository = EffectDeploymentRepository(hass)
    await repository.async_load()

    assert repository.get(legacy.operation_id).phase is canonical_phase


async def test_legacy_painted_snapshot_uses_shared_schema_migration(hass: HomeAssistant) -> None:
    legacy = _deployment(DeploymentPhase.CONFIRMED)
    document = legacy.to_dict()
    document["item_id"] = None
    document["item_revision"] = document.pop("item_version")
    for key in (
        "source_kind",
        "selector_label",
        "source_origin_kind",
        "source_origin_id",
        "source_content_hash",
    ):
        document.pop(key)
    document["snapshot"] = {
        "name": "Legacy paint",
        "content": {
            "kind": "h617a_painted",
            "effect": "clockwise",
            "speed": 50,
            "brightness": 100,
            "background": [0, 0, 0],
            "groups": [{"fill": [255, 0, 0], "segments": [0]}],
        },
        "provenance": {
            "source_kind": "authored",
            "source_id": None,
        },
    }
    await Store[dict[str, Any]](
        hass,
        1,
        DEPLOYMENT_STORE_KEY,
        private=True,
        atomic_writes=True,
        minor_version=3,
    ).async_save(
        {
            "revision": 1,
            "records": {str(legacy.operation_id): document},
        }
    )

    repository = EffectDeploymentRepository(hass)
    await repository.async_load()

    migrated = repository.get(legacy.operation_id)
    expected = PaintedEffect("clockwise", 50, 100, ((255, 0, 0),) + (None,) * 14)
    assert migrated.source_kind == "snapshot"
    assert migrated.source_content_hash == effect_content_hash(expected)


def test_unsaved_apply_records_content_free_source_metadata() -> None:
    item = _item()

    record = DeploymentRecord(
        operation_id=uuid4(),
        config_entry_id="entry-a",
        diy_code=800,
        phase=DeploymentPhase.PENDING,
        compiler_version=1,
        artifact_sha256=sha256(b"artifact").hexdigest(),
        updated_at="2026-08-11T00:00:00Z",
        source_kind="snapshot",
        selector_label=item.name,
        source_origin_kind=item.origin.kind.value,
        source_content_hash=item.content_hash,
    )

    document = record.to_dict()
    assert DeploymentRecord.from_dict(document) == record
    assert "snapshot" not in document
    assert "content" not in document


def test_deployment_round_trip_preserves_prior_state_and_verification_confidence() -> None:
    prior_state = PriorControlState(
        mode="video",
        is_on=True,
        brightness_pct=72,
        rgb_color=(1, 2, 3),
        color_temp_kelvin=4000,
        effect="forest",
        diy_code=800,
        music_mode="separation",
        video_mode="game",
        music_sensitivity=50,
        music_calm=True,
        music_color=(4, 5, 6),
        music_separation_point=4,
        music_separation_gradient=False,
        music_hopping_brightness=40,
        music_piano_key_count=12,
        music_fountain_direction="two_way",
        music_daynight_segments=6,
        music_daynight_speed=30,
        music_daynight_gradient=True,
        video_full_screen=False,
        video_saturation=63,
        video_sound_effects=True,
        video_sound_effects_softness=27,
        white_balance_red=21,
        white_balance_blue=5,
        relative_brightness_left=20,
        relative_brightness_top=30,
        relative_brightness_right=40,
        relative_brightness_bottom=50,
        blank_screen=True,
        blank_screen_detection=2,
        blank_screen_low_brightness_duration_seconds=10,
        blank_screen_same_tone_duration_seconds=120,
    )
    record = replace(
        _deployment(DeploymentPhase.CONFIRMED),
        prior_state=prior_state,
        verification_confidence=ObservationConfidence.ACTIVATION_MATCH,
        target_mode="scene",
        target_effect="forest",
        evidence_codes=(
            "scene_payload_readback_unavailable",
            "layered_field_semantics_uncalibrated",
        ),
    )

    restored = DeploymentRecord.from_dict(record.to_dict())

    assert restored == record
    assert restored.to_public_dict()["verification_confidence"] == "activation_match"
    assert restored.to_public_dict()["target_mode"] == "scene"
    assert restored.to_public_dict()["target_effect"] == "forest"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"music_separation_point": 0}, "prior separation point must be from 1 to 5"),
        ({"music_separation_gradient": 1}, "prior separation gradient must be a boolean"),
        ({"music_fountain_direction": "sideways"}, "prior fountain direction is invalid"),
        ({"white_balance_red": 256}, "prior white-balance red must be from 0 to 255"),
        ({"blank_screen": 1}, "prior blank-screen state must be a boolean or null"),
    ],
)
def test_invalid_profile_recovery_state_is_rejected(changes, message) -> None:
    state = PriorControlState(
        mode="colour",
        is_on=True,
        brightness_pct=72,
        rgb_color=(1, 2, 3),
    )

    with pytest.raises(EffectStorageError, match=message):
        replace(state, **changes)


def test_upload_only_deployment_round_trip_preserves_nullable_selector_and_completion_confidence() -> None:
    record = replace(
        _deployment(DeploymentPhase.APPLIED),
        diy_code=None,
        verification_confidence=ObservationConfidence.WRITE_COMPLETED,
    )

    restored = DeploymentRecord.from_dict(record.to_dict())

    assert restored == record
    assert restored.to_public_dict()["diy_code"] is None
    assert restored.to_public_dict()["verification_confidence"] == "write_completed"


@pytest.mark.parametrize(
    "changes",
    [
        {"config_entry_id": ""},
        {"diy_code": -1},
        {"target_mode": "invalid"},
        {"target_mode": "scene", "target_effect": None},
        {"compiler_version": 0},
        {"artifact_sha256": "short"},
        {"updated_at": ""},
        {"progress_current": 2, "progress_total": 1},
        {"item_id": None, "item_version": None},
        {"source_kind": "snapshot"},
        {"source_content_hash": "short"},
    ],
)
def test_invalid_deployments_are_rejected(changes) -> None:
    with pytest.raises(EffectStorageError):
        replace(_deployment(), **changes)


def test_observation_does_not_contain_authored_definition() -> None:
    deployment = _deployment(DeploymentPhase.CONFIRMED)
    state = ObservedDeviceState(
        config_entry_id="entry-a",
        mode="custom",
        observed_at="2026-08-11T00:00:00Z",
        confidence=ObservationConfidence.ACTIVATION_MATCH,
        diy_code=800,
        matched_operation_id=deployment.operation_id,
        active_effect=ActiveEffectHint.from_record(
            deployment,
            observable_signature="custom:800",
            confidence=ObservationConfidence.ACTIVATION_MATCH,
        ),
    )

    restored = ObservedDeviceState.from_dict(state.to_dict())
    document = restored.to_dict()

    assert restored == state
    assert "content" not in document
    assert isinstance(document["active_effect"], dict)
    assert "content" not in document["active_effect"]


async def test_device_cache_drops_session_confidence_after_reload(
    hass: HomeAssistant,
) -> None:
    cache = EffectDeviceCache(hass)
    await cache.async_load()
    deployment = _deployment(DeploymentPhase.CONFIRMED)
    state = ObservedDeviceState(
        config_entry_id="entry-a",
        mode="custom",
        observed_at="2026-08-11T00:00:00Z",
        confidence=ObservationConfidence.ACTIVATION_MATCH,
        diy_code=800,
        matched_operation_id=deployment.operation_id,
        active_effect=ActiveEffectHint.from_record(
            deployment,
            observable_signature="custom:800",
            confidence=ObservationConfidence.ACTIVATION_MATCH,
        ),
    )
    cache.set(state)
    assert cache.get("entry-a") == state

    await cache.async_flush()
    reloaded = EffectDeviceCache(hass)
    states = await reloaded.async_load()

    assert states[0].confidence is ObservationConfidence.UNKNOWN
    assert states[0].matched_operation_id is None
    assert states[0].active_effect is not None
    assert states[0].active_effect.confidence is ObservationConfidence.UNKNOWN
    assert states[0].active_effect.item_id == deployment.item_id


async def test_device_cache_drops_native_identity_after_reload(
    hass: HomeAssistant,
) -> None:
    cache = EffectDeviceCache(hass)
    await cache.async_load()
    cache.set(
        ObservedDeviceState(
            config_entry_id="entry-a",
            mode="video",
            observed_at="2026-08-11T00:00:00Z",
            native_mode="movie",
        )
    )
    await cache.async_flush()

    (restored,) = await EffectDeviceCache(hass).async_load()

    assert restored.mode == "video"
    assert restored.native_mode is None


async def test_legacy_device_cache_migrates_without_claiming_active_identity(
    hass: HomeAssistant,
) -> None:
    legacy_state = ObservedDeviceState(
        config_entry_id="entry-a",
        mode="custom",
        observed_at="2026-08-11T00:00:00Z",
        confidence=ObservationConfidence.ACTIVATION_MATCH,
        diy_code=800,
        matched_operation_id=uuid4(),
    ).to_dict()
    legacy_state.pop("active_effect")
    await Store[dict[str, Any]](
        hass,
        1,
        DEVICE_CACHE_STORE_KEY,
        private=True,
        atomic_writes=True,
        minor_version=2,
    ).async_save({"devices": {"entry-a": legacy_state}})

    (migrated,) = await EffectDeviceCache(hass).async_load()

    assert migrated.confidence is ObservationConfidence.UNKNOWN
    assert migrated.matched_operation_id is None
    assert migrated.active_effect is None


async def test_recent_colours_are_owner_scoped_deduplicated_and_bounded(
    hass: HomeAssistant,
) -> None:
    repository = EffectUserStateRepository(hass)
    await repository.async_load()
    repository.set(EffectUserState("user-a", navigation={"section": "scenes"}))

    for value in range(MAX_RECENT_COLOURS + 2):
        repository.record_colour("user-a", (value, 0, 0))
    updated = repository.record_colour("user-a", (5, 0, 0))

    assert len(updated.recent_colours) == MAX_RECENT_COLOURS
    assert updated.recent_colours[0] == (5, 0, 0)
    assert len(set(updated.recent_colours)) == MAX_RECENT_COLOURS
    assert repository.get("user-b").recent_colours == ()

    await repository.async_flush()
    reloaded = EffectUserStateRepository(hass)
    await reloaded.async_load()
    assert reloaded.get("user-a") == updated


async def test_user_state_migration_removes_retired_special_diy_navigation(
    hass: HomeAssistant,
) -> None:
    await Store[dict[str, Any]](
        hass,
        USER_STATE_STORE_VERSION,
        USER_STATE_STORE_KEY,
        private=True,
        atomic_writes=True,
        minor_version=USER_STATE_STORE_MINOR_VERSION - 1,
    ).async_save(
        {
            "users": {
                "user-a": EffectUserState(
                    "user-a",
                    navigation={
                        "section": "custom",
                        "custom_category": "special-diy",
                        "auto_save": True,
                    },
                ).to_dict()
            }
        }
    )

    (migrated,) = await EffectUserStateRepository(hass).async_load()

    assert migrated.navigation == {
        "section": "custom",
        "auto_save": True,
    }


@pytest.mark.parametrize(
    "state",
    [
        lambda: EffectUserState("", ()),
        lambda: EffectUserState(
            "user",
            tuple((value, 0, 0) for value in range(MAX_RECENT_COLOURS + 1)),
        ),
        lambda: EffectUserState("user", ((1, 2, 3), (1, 2, 3))),
    ],
)
def test_invalid_personal_state_is_rejected(state) -> None:
    with pytest.raises(EffectStorageError):
        state()


async def test_recovery_stores_drop_only_malformed_records(
    hass: HomeAssistant,
) -> None:
    valid_deployment = _deployment(DeploymentPhase.CONFIRMED)
    deployment_store = Store[dict[str, Any]](
        hass,
        DEPLOYMENT_STORE_VERSION,
        DEPLOYMENT_STORE_KEY,
        private=True,
        atomic_writes=True,
        minor_version=DEPLOYMENT_STORE_MINOR_VERSION,
    )
    await deployment_store.async_save(
        {
            "version": 2,
            "records": {
                str(valid_deployment.operation_id): valid_deployment.to_dict(),
                str(uuid4()): {"phase": "broken"},
                str(uuid4()): {"ignored": "x" * (MAX_JSON_STRING_LENGTH + 1)},
            },
        }
    )
    deployments = EffectDeploymentRepository(hass)

    deployment_snapshot = await deployments.async_load()
    assert deployment_snapshot.records == (valid_deployment,)
    assert deployment_snapshot.version == 3

    valid_device = ObservedDeviceState(
        config_entry_id="entry-a",
        mode="diy",
        observed_at="2026-08-11T00:00:00Z",
    )
    device_store = Store[dict[str, Any]](
        hass,
        DEVICE_CACHE_STORE_VERSION,
        DEVICE_CACHE_STORE_KEY,
        private=True,
        atomic_writes=True,
        minor_version=DEVICE_CACHE_STORE_MINOR_VERSION,
    )
    await device_store.async_save(
        {
            "devices": {
                valid_device.config_entry_id: valid_device.to_dict(),
                "broken": {"mode": "diy"},
                "oversized": {"ignored": "x" * (MAX_JSON_STRING_LENGTH + 1)},
            }
        }
    )
    cache = EffectDeviceCache(hass)

    assert await cache.async_load() == (valid_device,)

    valid_user = EffectUserState("user-a", navigation={"section": "scenes"})
    user_store = Store[dict[str, Any]](
        hass,
        USER_STATE_STORE_VERSION,
        USER_STATE_STORE_KEY,
        private=True,
        atomic_writes=True,
        minor_version=USER_STATE_STORE_MINOR_VERSION,
    )
    await user_store.async_save(
        {
            "users": {
                valid_user.owner_id: valid_user.to_dict(),
                "broken": {"owner_id": ""},
                "oversized": {"ignored": "x" * (MAX_JSON_STRING_LENGTH + 1)},
            }
        }
    )
    user_state = EffectUserStateRepository(hass)

    assert await user_state.async_load() == (valid_user,)


@pytest.mark.parametrize(
    ("repository_type", "version", "key", "minor_version", "data"),
    [
        (
            EffectDeploymentRepository,
            DEPLOYMENT_STORE_VERSION,
            DEPLOYMENT_STORE_KEY,
            DEPLOYMENT_STORE_MINOR_VERSION,
            {"version": 0, "records": {}},
        ),
        (
            EffectDeviceCache,
            DEVICE_CACHE_STORE_VERSION,
            DEVICE_CACHE_STORE_KEY,
            DEVICE_CACHE_STORE_MINOR_VERSION,
            {"devices": {}},
        ),
        (
            EffectUserStateRepository,
            USER_STATE_STORE_VERSION,
            USER_STATE_STORE_KEY,
            USER_STATE_STORE_MINOR_VERSION,
            {"users": {}},
        ),
    ],
)
async def test_optional_stores_refuse_newer_minor_versions(
    hass: HomeAssistant,
    repository_type: type[Any],
    version: int,
    key: str,
    minor_version: int,
    data: dict[str, Any],
) -> None:
    store = Store[dict[str, Any]](
        hass,
        version,
        key,
        private=True,
        atomic_writes=True,
        minor_version=minor_version + 1,
    )
    await store.async_save(data)

    with pytest.raises(EffectStorageError, match="cannot migrate"):
        await repository_type(hass).async_load()


async def test_deployment_history_discards_oldest_terminal_record(
    hass: HomeAssistant,
) -> None:
    records: dict[str, Any] = {}
    for index in range(MAX_DEPLOYMENT_RECORDS):
        record = replace(
            _deployment(DeploymentPhase.CONFIRMED),
            updated_at=f"2026-08-11T{index // 60:02d}:{index % 60:02d}:00Z",
        )
        records[str(record.operation_id)] = record.to_dict()
    oldest_id = next(iter(records))
    store = Store[dict[str, Any]](
        hass,
        DEPLOYMENT_STORE_VERSION,
        DEPLOYMENT_STORE_KEY,
        private=True,
        atomic_writes=True,
        minor_version=DEPLOYMENT_STORE_MINOR_VERSION,
    )
    await store.async_save({"version": MAX_DEPLOYMENT_RECORDS, "records": records})
    repository = EffectDeploymentRepository(hass)
    snapshot = await repository.async_load()

    next_record = replace(
        _deployment(DeploymentPhase.PENDING),
        updated_at="2026-08-12T00:00:00Z",
    )
    updated = await repository.async_put(
        next_record,
        expected_version=snapshot.version,
    )

    assert len(updated.records) == MAX_DEPLOYMENT_RECORDS
    assert all(str(record.operation_id) != oldest_id for record in updated.records)
    assert repository.get(next_record.operation_id) == next_record
