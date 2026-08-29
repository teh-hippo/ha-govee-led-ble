"""Ephemeral Effect Studio preview workers."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.ha_govee_led_ble.const import DOMAIN, EFFECT_FAMILY_SCENES
from custom_components.ha_govee_led_ble.control_arbiter import BLEControlArbiter, ControlIntent
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.effect_active_workspace import (
    ActiveEffectWorkspaceRepository,
)
from custom_components.ha_govee_led_ble.effect_catalogue import (
    H617A_WORKSHOP_APPLY_CODE,
    WORKSHOP_PROTOCOL_FIXTURES,
    resolve_catalogue_template,
)
from custom_components.ha_govee_led_ble.effect_compiler import CompiledEffect, compile_application
from custom_components.ha_govee_led_ble.effect_deployments import (
    ObservationConfidence,
)
from custom_components.ha_govee_led_ble.effect_diagnostics import EffectDiagnosticHistory
from custom_components.ha_govee_led_ble.effect_domain import (
    LibraryItem,
    MusicProfile,
    Origin,
    RelativeBrightness,
    SingleEffect,
    SourceKind,
    VideoProfile,
)
from custom_components.ha_govee_led_ble.effect_identity import EffectDeviceCache, ObservedDeviceState
from custom_components.ha_govee_led_ble.effect_preview import (
    EffectPreviewManager,
    PreviewError,
    PreviewHealthPhase,
    PreviewHealthStatus,
    PreviewOwnershipError,
    PreviewPhase,
    PreviewSequenceError,
    PreviewSessionNotFoundError,
    PreviewShutdownError,
    PreviewStatus,
    PreviewWriteDisposition,
)
from custom_components.ha_govee_led_ble.effect_runtime import resolve_diy_code
from custom_components.ha_govee_led_ble.effect_scene_defaults import NativeSceneDefaultRepository
from custom_components.ha_govee_led_ble.effect_template_defaults import CatalogueTemplateDefaultRepository
from custom_components.ha_govee_led_ble.generated_protocol_adapter import build_power
from custom_components.ha_govee_led_ble.layered_scene_decoder import decode_catalogue_layered_scene
from custom_components.ha_govee_led_ble.native_scenes import encode_authored_scene_body
from custom_components.ha_govee_led_ble.scenes import SCENE_ENTRIES, SceneEntry
from tests.storage_test_double import InMemoryVersionedDocumentStore


def _item(name: str, speed: int = 50) -> LibraryItem:
    return LibraryItem.new(name, SingleEffect(0, 0, speed, ((255, 0, 0),)))


def _coordinator(
    *,
    model: str = "H617A",
    readable: bool = False,
) -> SimpleNamespace:
    coordinator = SimpleNamespace(
        model=model,
        profile=SimpleNamespace(
            state_readable=readable,
            supports_color_mode_readback=readable,
            supports_scenes=True,
        ),
        effect_families={EFFECT_FAMILY_SCENES},
        _control_lock=asyncio.Lock(),
        is_on=False,
        effect=None,
        diy_code=None,
        music_mode="off",
        video_mode="off",
        writes=[],
        async_update_listeners=MagicMock(),
    )
    coordinator.async_preview_preflight = AsyncMock()
    coordinator.disconnect = AsyncMock()

    async def write(packet: bytes) -> None:
        coordinator.writes.append(packet)

    coordinator.async_preview_write = AsyncMock(side_effect=write)

    async def write_effect_sequence(
        packets,
        *,
        intent,
        before_write=None,
        attempt_started=None,
        progress=None,
    ) -> None:
        if attempt_started is not None:
            await attempt_started(1)
        if before_write is not None:
            await before_write()
        for index, packet in enumerate(packets, start=1):
            await coordinator.async_preview_write(packet)
            if progress is not None:
                await progress(index)

    coordinator.async_write_effect_sequence = AsyncMock(side_effect=write_effect_sequence)
    coordinator.async_preview_observe = AsyncMock(return_value=True)
    coordinator.send_command = AsyncMock(side_effect=AssertionError("preview verification must not call send_command"))
    return coordinator


def _alternate_speed_index(scene: SceneEntry) -> int:
    speed = scene.speed
    assert speed is not None and speed.option_count > 1
    return (speed.default_index + 1) % speed.option_count


async def _manager(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    coordinator: Any,
    **timing: float,
) -> tuple[EffectPreviewManager, EffectDeviceCache]:
    cache = EffectDeviceCache(InMemoryVersionedDocumentStore())
    await cache.async_load()
    scene_defaults = NativeSceneDefaultRepository(InMemoryVersionedDocumentStore())
    await scene_defaults.async_load()
    template_defaults = CatalogueTemplateDefaultRepository(InMemoryVersionedDocumentStore())
    await template_defaults.async_load()
    active_workspaces = ActiveEffectWorkspaceRepository(InMemoryVersionedDocumentStore())
    await active_workspaces.async_load()
    manager = EffectPreviewManager(
        hass,
        cache,
        scene_defaults,
        template_defaults,
        EffectDiagnosticHistory(),
        active_workspaces=active_workspaces,
        verify_delay=timing.get("verify_delay", 0),
        verify_timeout=timing.get("verify_timeout", 0.1),
        connect_timeout=timing.get("connect_timeout", 0.1),
        channel_idle_timeout=timing.get("channel_idle_timeout", 300),
    )
    entry = SimpleNamespace(
        entry_id="entry-a",
        domain=DOMAIN,
        state=ConfigEntryState.LOADED,
        runtime_data=coordinator,
    )
    monkeypatch.setattr(
        hass.config_entries,
        "async_get_entry",
        lambda entry_id: entry if entry_id == entry.entry_id else None,
    )
    return manager, cache


def _open(manager: EffectPreviewManager, owner: object, events: list[PreviewStatus]) -> str:
    session_id = manager.open_session(owner=owner)
    manager.subscribe(
        session_id=session_id,
        owner=owner,
        subscription_id=object(),
        listener=events.append,
    )
    return session_id


async def test_worker_compiles_active_then_only_newest_pending_request(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _coordinator()
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    writes = 0

    async def write(packet: bytes) -> None:
        nonlocal writes
        writes += 1
        if writes == 1:
            first_started.set()
            await release_first.wait()
        coordinator.writes.append(packet)

    coordinator.async_preview_write.side_effect = write
    manager, _cache = await _manager(hass, monkeypatch, coordinator)
    owner = object()
    events: list[PreviewStatus] = []
    session_id = _open(manager, owner, events)
    compiled_names: list[str] = []
    from custom_components.ha_govee_led_ble import effect_preview

    original_compile = effect_preview.compile_application

    def compile_recording(item, model, *, diy_code=None):
        compiled_names.append(item.name)
        return original_compile(item, model, diy_code=diy_code)

    monkeypatch.setattr(effect_preview, "compile_application", compile_recording)

    await manager.async_queue_snapshot(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=1,
        updated_at="2026-08-17T00:00:00Z",
        item=_item("first", 10),
    )
    await first_started.wait()
    await manager.async_queue_snapshot(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=2,
        updated_at="2026-08-17T00:00:01Z",
        item=_item("second", 20),
    )
    await manager.async_queue_snapshot(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=3,
        updated_at="2026-08-17T00:00:02Z",
        item=_item("third", 30),
    )
    release_first.set()
    await manager.async_wait_idle("entry-a")

    assert compiled_names == ["first", "third"]
    assert any(
        event.sequence == 2 and event.phase is PreviewPhase.CANCELLED and event.error_code == "superseded"
        for event in events
    )
    await manager.async_shutdown()


async def test_newest_request_can_return_to_the_active_state(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _coordinator()
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    writes = 0

    async def write(packet: bytes) -> None:
        nonlocal writes
        writes += 1
        if writes == 1:
            first_started.set()
            await release_first.wait()
        coordinator.writes.append(packet)

    coordinator.async_preview_write.side_effect = write
    manager, _cache = await _manager(hass, monkeypatch, coordinator)
    owner = object()
    events: list[PreviewStatus] = []
    session_id = _open(manager, owner, events)
    compiled_names: list[str] = []
    from custom_components.ha_govee_led_ble import effect_preview

    original_compile = effect_preview.compile_application

    def compile_recording(item, model, *, diy_code=None):
        compiled_names.append(item.name)
        return original_compile(item, model, diy_code=diy_code)

    monkeypatch.setattr(effect_preview, "compile_application", compile_recording)

    await manager.async_queue_snapshot(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=1,
        updated_at="2026-08-17T00:00:00Z",
        item=_item("state-a", 10),
    )
    await first_started.wait()
    await manager.async_queue_snapshot(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=2,
        updated_at="2026-08-17T00:00:01Z",
        item=_item("state-b", 20),
    )
    acceptance = await manager.async_queue_snapshot(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=3,
        updated_at="2026-08-17T00:00:02Z",
        item=_item("state-a", 10),
    )
    release_first.set()
    await manager.async_wait_idle("entry-a")

    assert acceptance.accepted
    assert compiled_names == ["state-a", "state-a"]
    await manager.async_shutdown()


async def test_session_ownership_is_enforced_without_rejecting_rapid_updates(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _coordinator()
    manager, _cache = await _manager(hass, monkeypatch, coordinator)
    owner = object()
    session_id = _open(manager, owner, [])

    with pytest.raises(PreviewOwnershipError):
        manager.require_owner(session_id, object())

    for sequence in range(1, 101):
        acceptance = await manager.async_queue_snapshot(
            session_id=session_id,
            owner=owner,
            config_entry_id="entry-a",
            sequence=sequence,
            updated_at="2026-08-17T00:00:00Z",
            item=_item(f"request-{sequence}", sequence),
        )
        assert acceptance.accepted
    await manager.async_wait_idle("entry-a")
    await manager.async_shutdown()


async def test_channel_reattaches_for_same_user_and_expires_when_idle(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, _cache = await _manager(
        hass,
        monkeypatch,
        _coordinator(),
        channel_idle_timeout=0.01,
    )
    session_id = str(uuid4())
    first_connection = SimpleNamespace(user=SimpleNamespace(id="user-a"))
    replacement_connection = SimpleNamespace(user=SimpleNamespace(id="user-a"))
    other_user = SimpleNamespace(user=SimpleNamespace(id="user-b"))

    first_listener = MagicMock()
    replacement_listener = MagicMock()
    unsubscribe = manager.subscribe(
        session_id=session_id,
        owner=first_connection,
        subscription_id=1,
        listener=first_listener,
    )
    unsubscribe_replacement = manager.subscribe(
        session_id=session_id,
        owner=replacement_connection,
        subscription_id=1,
        listener=replacement_listener,
    )
    with pytest.raises(PreviewOwnershipError):
        manager.ensure_session(session_id, other_user)

    unsubscribe()
    assert manager._sessions[session_id].listeners[1] is replacement_listener
    unsubscribe_replacement()
    await asyncio.sleep(0.02)

    with pytest.raises(PreviewSessionNotFoundError):
        manager.require_owner(session_id, replacement_connection)
    await manager.async_shutdown()


async def test_failed_sequence_can_retry_same_desired_revision(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _coordinator()
    coordinator.async_preview_write.side_effect = OSError("transport failed")
    manager, _cache = await _manager(hass, monkeypatch, coordinator)
    owner = object()
    events: list[PreviewStatus] = []
    session_id = _open(manager, owner, events)
    item = _item("retry")

    await manager.async_queue_snapshot(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=1,
        updated_at="2026-08-17T00:00:00Z",
        item=item,
    )
    await manager.async_wait_idle("entry-a")
    failed_status = events[-1]
    assert failed_status.phase is PreviewPhase.FAILED

    coordinator.async_preview_write.side_effect = lambda packet: coordinator.writes.append(packet)
    await manager.async_queue_snapshot(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=1,
        updated_at="2026-08-17T00:00:01Z",
        item=item,
    )
    await manager.async_wait_idle("entry-a")

    written_status = events[-1]
    assert written_status.phase is PreviewPhase.WRITTEN
    assert coordinator.writes
    await manager.async_shutdown()


async def test_status_subscription_is_filtered_to_its_session(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _coordinator()
    manager, _cache = await _manager(hass, monkeypatch, coordinator)
    first_owner = object()
    second_owner = object()
    first_events: list[PreviewStatus] = []
    second_events: list[PreviewStatus] = []
    first_session = _open(manager, first_owner, first_events)
    _open(manager, second_owner, second_events)

    await manager.async_queue_snapshot(
        session_id=first_session,
        owner=first_owner,
        config_entry_id="entry-a",
        sequence=1,
        updated_at="2026-08-17T00:00:00Z",
        item=_item("first"),
    )
    await manager.async_wait_idle("entry-a")

    assert first_events
    assert second_events == []
    await manager.async_shutdown()


async def test_native_scene_preview_uses_scene_speed_primitive_for_repeated_selection(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _coordinator()
    coordinator.effect_families = set()
    applied = []

    async def apply_scene(
        scene_name,
        *,
        speed_index,
        canonical_body,
        before_write,
        verify,
        intent,
    ):
        async with coordinator._control_lock:
            applied.append((scene_name, speed_index, verify))
            await before_write()
            await coordinator.async_preview_write(b"scene")

    coordinator.async_apply_native_scene = AsyncMock(side_effect=apply_scene)
    manager, _cache = await _manager(hass, monkeypatch, coordinator)
    owner = object()
    session_id = _open(manager, owner, [])
    scene = next(entry for entry in SCENE_ENTRIES["H617A"] if entry.speed is not None)
    assert scene.speed is not None

    for sequence in (1, 2):
        acceptance = await manager.async_queue_scene(
            session_id=session_id,
            owner=owner,
            config_entry_id="entry-a",
            sequence=sequence,
            updated_at=f"2026-08-17T00:00:0{sequence}Z",
            scene_id=scene.scene_id,
            effect_id=scene.effect_id,
            speed_index=scene.speed.default_index,
        )
        assert acceptance.accepted is True
        await manager.async_wait_idle("entry-a")

    assert len(applied) == 2
    assert all(item[1:] == (scene.speed.default_index, False) for item in applied)
    await manager.async_shutdown()


async def test_h6125_a3_scene_preview_is_not_exposed(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _coordinator(model="H6125")
    manager, _cache = await _manager(hass, monkeypatch, coordinator)
    owner = object()
    session_id = _open(manager, owner, [])
    scene = next(entry for entry in SCENE_ENTRIES["H6125"] if entry.scene_type == 2)

    with pytest.raises(ValueError, match="was not found"):
        await manager.async_queue_scene(
            session_id=session_id,
            owner=owner,
            config_entry_id="entry-a",
            sequence=1,
            updated_at="2026-08-17T00:00:01Z",
            scene_id=scene.scene_id,
            effect_id=scene.effect_id,
            speed_index=None,
        )
    await manager.async_shutdown()


async def test_committed_scene_snapshot_persists_the_written_canonical_body(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _coordinator()
    manager, _cache = await _manager(hass, monkeypatch, coordinator)
    owner = object()
    session_id = _open(manager, owner, [])
    scene = next(
        entry
        for entry in SCENE_ENTRIES["H617A"]
        if entry.scene_type == 2 and entry.speed is not None and entry.speed.option_count > 1
    )
    content = decode_catalogue_layered_scene("H617A", scene)
    assert content is not None
    content = replace(
        content,
        speed_index=_alternate_speed_index(scene),
    )

    await manager.async_queue_snapshot(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=1,
        updated_at="2026-08-17T00:00:00Z",
        item=LibraryItem.new("Edited scene", content),
        persist_default=True,
    )
    await manager.async_wait_idle("entry-a")

    persisted = manager._scene_defaults.get("entry-a", scene.scene_id, scene.effect_id)
    expected_body, expected_speed = encode_authored_scene_body(content, scene)
    assert persisted is not None
    assert persisted.canonical_body == expected_body
    assert persisted.speed_index == expected_speed
    await manager.async_shutdown()


async def test_committed_catalogue_default_removes_the_stored_override(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _coordinator()
    manager, _cache = await _manager(hass, monkeypatch, coordinator)
    owner = object()
    events: list[PreviewStatus] = []
    session_id = _open(manager, owner, events)
    scene = next(
        entry
        for entry in SCENE_ENTRIES["H617A"]
        if entry.scene_type == 2 and entry.speed is not None and entry.speed.option_count > 1
    )
    content = decode_catalogue_layered_scene("H617A", scene)
    assert content is not None
    changed = replace(
        content,
        speed_index=_alternate_speed_index(scene),
    )

    await manager.async_queue_snapshot(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=1,
        updated_at="2026-08-17T00:00:00Z",
        item=LibraryItem.new("Edited scene", changed),
        persist_default=True,
    )
    await manager.async_wait_idle("entry-a")
    assert manager._scene_defaults.get("entry-a", scene.scene_id, scene.effect_id) is not None
    assert (
        next(event for event in events if event.sequence == 1 and event.phase is PreviewPhase.QUEUED).default_action
        == "set"
    )

    await manager.async_queue_snapshot(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=2,
        updated_at="2026-08-17T00:00:01Z",
        item=LibraryItem.new("Catalogue scene", content),
        persist_default=True,
    )
    await manager.async_wait_idle("entry-a")

    assert manager._scene_defaults.get("entry-a", scene.scene_id, scene.effect_id) is None
    assert (
        next(event for event in events if event.sequence == 2 and event.phase is PreviewPhase.QUEUED).default_action
        == "reset"
    )
    await manager.async_shutdown()


async def test_committed_catalogue_template_snapshot_sets_and_resets_default(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _coordinator()
    manager, _cache = await _manager(hass, monkeypatch, coordinator)
    owner = object()
    events: list[PreviewStatus] = []
    session_id = _open(manager, owner, events)
    template = resolve_catalogue_template("H617A", "template:single:0:0")
    assert isinstance(template.content, SingleEffect)
    origin = Origin(SourceKind.CATALOGUE_TEMPLATE, template.id)

    await manager.async_queue_snapshot(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=1,
        updated_at="2026-08-17T00:00:00Z",
        item=LibraryItem.new("Fade", replace(template.content, speed=75), origin=origin),
        persist_default=True,
    )
    await manager.async_wait_idle("entry-a")

    stored = manager._template_defaults.get("entry-a", template.id)
    assert stored is not None
    assert isinstance(stored.content, SingleEffect)
    assert stored.content.speed == 75
    assert (
        next(event for event in events if event.sequence == 1 and event.phase is PreviewPhase.QUEUED).default_action
        == "set"
    )

    await manager.async_queue_snapshot(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=2,
        updated_at="2026-08-17T00:00:01Z",
        item=LibraryItem.new("Fade", template.content, origin=origin),
        persist_default=True,
    )
    await manager.async_wait_idle("entry-a")

    assert manager._template_defaults.get("entry-a", template.id) is None
    assert (
        next(event for event in events if event.sequence == 2 and event.phase is PreviewPhase.QUEUED).default_action
        == "reset"
    )
    await manager.async_shutdown()


async def test_failed_committed_scene_snapshot_does_not_persist(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _coordinator()
    coordinator.async_preview_write.side_effect = OSError("write failed")
    manager, _cache = await _manager(hass, monkeypatch, coordinator)
    owner = object()
    session_id = _open(manager, owner, [])
    scene = next(
        entry
        for entry in SCENE_ENTRIES["H617A"]
        if entry.scene_type == 2 and entry.speed is not None and entry.speed.option_count > 1
    )
    content = decode_catalogue_layered_scene("H617A", scene)
    assert content is not None
    content = replace(
        content,
        speed_index=_alternate_speed_index(scene),
    )

    await manager.async_queue_snapshot(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=1,
        updated_at="2026-08-17T00:00:00Z",
        item=LibraryItem.new("Edited scene", content),
        persist_default=True,
    )
    await manager.async_wait_idle("entry-a")

    assert manager._scene_defaults.get("entry-a", scene.scene_id, scene.effect_id) is None
    await manager.async_shutdown()


async def test_scene_default_storage_failure_is_reported_after_transport(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _coordinator()
    manager, _cache = await _manager(hass, monkeypatch, coordinator)
    monkeypatch.setattr(
        manager._scene_defaults,
        "async_set",
        AsyncMock(side_effect=OSError("storage failed")),
    )
    owner = object()
    events: list[PreviewStatus] = []
    session_id = _open(manager, owner, events)
    scene = next(
        entry
        for entry in SCENE_ENTRIES["H617A"]
        if entry.scene_type == 2 and entry.speed is not None and entry.speed.option_count > 1
    )
    content = decode_catalogue_layered_scene("H617A", scene)
    assert content is not None
    content = replace(
        content,
        speed_index=_alternate_speed_index(scene),
    )

    await manager.async_queue_snapshot(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=1,
        updated_at="2026-08-17T00:00:00Z",
        item=LibraryItem.new("Edited scene", content),
        persist_default=True,
    )
    await manager.async_wait_idle("entry-a")

    assert events[-1].phase is PreviewPhase.FAILED
    assert events[-1].error_code == "storage_failed"
    await manager.async_shutdown()


async def test_selector_only_scene_preview_never_creates_a_default(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _coordinator()

    async def apply_scene(
        _scene_name,
        *,
        speed_index,
        canonical_body,
        before_write,
        verify,
        intent,
    ):
        assert speed_index is None
        assert canonical_body is None
        assert verify is False
        await before_write()
        await coordinator.async_preview_write(b"scene")

    coordinator.async_apply_native_scene = AsyncMock(side_effect=apply_scene)
    manager, _cache = await _manager(hass, monkeypatch, coordinator)
    owner = object()
    session_id = _open(manager, owner, [])
    scene = next(entry for entry in SCENE_ENTRIES["H617A"] if entry.scene_type == 0)

    await manager.async_queue_scene(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=1,
        updated_at="2026-08-17T00:00:00Z",
        scene_id=scene.scene_id,
        effect_id=scene.effect_id,
        speed_index=None,
        persist_default=True,
    )
    await manager.async_wait_idle("entry-a")

    assert manager._scene_defaults.get("entry-a", scene.scene_id, scene.effect_id) is None
    await manager.async_shutdown()


async def test_transport_failure_does_not_delay_newest_request(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _coordinator()
    failed_write_started = asyncio.Event()
    release_failure = asyncio.Event()
    write_count = 0

    async def write(packet: bytes) -> None:
        nonlocal write_count
        write_count += 1
        if write_count == 1:
            failed_write_started.set()
            await release_failure.wait()
            raise OSError("transport failed")
        coordinator.writes.append(packet)

    coordinator.async_preview_write.side_effect = write
    manager, _cache = await _manager(hass, monkeypatch, coordinator)
    owner = object()
    events: list[PreviewStatus] = []
    session_id = _open(manager, owner, events)
    await manager.async_queue_snapshot(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=1,
        updated_at="2026-08-17T00:00:00Z",
        item=_item("fails"),
    )
    await failed_write_started.wait()
    await manager.async_queue_snapshot(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=2,
        updated_at="2026-08-17T00:00:01Z",
        item=_item("retained", 60),
    )
    release_failure.set()
    async with asyncio.timeout(0.2):
        await manager.async_wait_idle("entry-a")

    assert any(event.sequence == 1 and event.error_code == "transport_failed" for event in events)
    assert any(event.sequence == 2 and event.phase is PreviewPhase.WRITTEN for event in events)
    assert coordinator.writes[0] == build_power(True, "H617A")
    assert coordinator.is_on is True
    await manager.async_shutdown()


async def test_latest_verification_is_read_only_without_holding_control_lock(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _coordinator(readable=True)

    async def observe(_expectations, *, timeout):
        assert timeout == 0.1
        assert not coordinator._control_lock.locked()
        coordinator.send_command.assert_not_awaited()
        return True

    coordinator.async_preview_observe.side_effect = observe
    manager, _cache = await _manager(hass, monkeypatch, coordinator)
    owner = object()
    events: list[PreviewStatus] = []
    session_id = _open(manager, owner, events)
    await manager.async_queue_snapshot(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=1,
        updated_at="2026-08-17T00:00:00Z",
        item=_item("verified"),
    )
    await manager.async_wait_idle("entry-a")

    coordinator.async_preview_observe.assert_awaited_once()
    coordinator.send_command.assert_not_awaited()
    assert any(
        event.phase is PreviewPhase.CONFIRMED and event.confidence is ObservationConfidence.ACTIVATION_MATCH
        for event in events
    )


async def test_silent_preview_remains_written_until_read_only_check_confirms(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _coordinator(readable=True)
    coordinator.async_preview_observe.side_effect = [None, True]
    manager, _cache = await _manager(hass, monkeypatch, coordinator)
    owner = object()
    events: list[PreviewStatus] = []
    session_id = _open(manager, owner, events)

    await manager.async_queue_snapshot(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=1,
        updated_at="2026-08-17T00:00:00Z",
        item=_item("silent"),
    )
    await manager.async_wait_idle("entry-a")

    health = manager.health("entry-a")
    assert health.phase is PreviewHealthPhase.HEALTHY
    assert health.error_code is None
    coordinator.disconnect.assert_not_awaited()
    assert events[-1].phase is PreviewPhase.WRITTEN

    confirmed = await manager.async_check_health("entry-a")

    assert confirmed.phase is PreviewHealthPhase.HEALTHY
    assert confirmed.error_code is None
    assert coordinator.async_preview_write.await_count > 0
    assert coordinator.async_preview_observe.await_count == 2


async def test_health_mints_a_new_incident_after_recovery(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, _cache = await _manager(
        hass,
        monkeypatch,
        _coordinator(),
    )

    first = manager._set_health(
        "entry-a",
        PreviewHealthPhase.DEGRADED,
        error_code="device_readback_unknown",
    )
    manager._set_health(
        "entry-a",
        PreviewHealthPhase.HEALTHY,
    )
    second = manager._set_health(
        "entry-a",
        PreviewHealthPhase.DEGRADED,
        error_code="device_readback_unknown",
    )

    assert first.incident_id is not None
    assert second.incident_id is not None
    assert second.incident_id != first.incident_id


async def test_health_subscriptions_use_independent_tokens(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, _cache = await _manager(
        hass,
        monkeypatch,
        _coordinator(),
    )
    left: list[PreviewHealthStatus] = []
    right: list[PreviewHealthStatus] = []
    unsubscribe_left = manager.subscribe_health(
        subscription_id=object(),
        listener=left.append,
    )
    manager.subscribe_health(
        subscription_id=object(),
        listener=right.append,
    )

    manager._set_health("entry-a", PreviewHealthPhase.DEGRADED)
    unsubscribe_left()
    manager._set_health("entry-a", PreviewHealthPhase.HEALTHY)

    assert [status.phase for status in left] == [
        PreviewHealthPhase.DEGRADED,
    ]
    assert [status.phase for status in right] == [
        PreviewHealthPhase.DEGRADED,
        PreviewHealthPhase.HEALTHY,
    ]
    await manager.async_shutdown()


async def test_stale_in_progress_verification_finishes_but_cannot_publish(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _coordinator(readable=True)
    first_observation_started = asyncio.Event()
    release_first_observation = asyncio.Event()
    observation_count = 0

    async def observe(_expectations, *, timeout):
        nonlocal observation_count
        observation_count += 1
        if observation_count == 1:
            first_observation_started.set()
            await release_first_observation.wait()
        return True

    coordinator.async_preview_observe.side_effect = observe
    manager, _cache = await _manager(hass, monkeypatch, coordinator)
    owner = object()
    events: list[PreviewStatus] = []
    session_id = _open(manager, owner, events)
    await manager.async_queue_snapshot(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=1,
        updated_at="2026-08-17T00:00:00Z",
        item=_item("first"),
    )
    await first_observation_started.wait()
    writes_before_newer = coordinator.async_preview_write.await_count
    await manager.async_queue_snapshot(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=2,
        updated_at="2026-08-17T00:00:01Z",
        item=_item("second", 60),
    )
    await asyncio.sleep(0)
    assert coordinator.async_preview_write.await_count == writes_before_newer

    release_first_observation.set()
    await manager.async_wait_idle("entry-a")

    current_sequences = [event.sequence for event in events if event.phase is PreviewPhase.CONFIRMED]
    assert current_sequences == [2]
    assert observation_count == 2
    await manager.async_shutdown()


async def test_workshop_preview_verifies_evidenced_selector(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _coordinator(readable=True)
    manager, _cache = await _manager(hass, monkeypatch, coordinator)
    owner = object()
    events: list[PreviewStatus] = []
    session_id = _open(manager, owner, events)
    item = LibraryItem.new("Workshop", WORKSHOP_PROTOCOL_FIXTURES[0].content("H617A"))

    await manager.async_queue_snapshot(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=1,
        updated_at="2026-08-17T00:00:00Z",
        item=item,
    )
    await manager.async_wait_idle("entry-a")

    coordinator.async_preview_observe.assert_awaited_once_with(
        {
            "is_on": True,
            "unknown_scene_code": H617A_WORKSHOP_APPLY_CODE,
        },
        timeout=0.1,
    )
    assert any(event.phase is PreviewPhase.CONFIRMED for event in events)
    await manager.async_shutdown()


@pytest.mark.parametrize(
    ("model", "item"),
    [
        (
            "H617A",
            LibraryItem.new(
                "Music",
                MusicProfile("H617A", "separation", 50, (1, 2, 3), None, {"point": 3, "gradient": True}),
            ),
        ),
        (
            "H6199",
            LibraryItem.new(
                "Video",
                VideoProfile(
                    "H6199",
                    "movie",
                    True,
                    70,
                    True,
                    40,
                    12,
                    RelativeBrightness(80, 60, 55, 45),
                    False,
                ),
            ),
        ),
    ],
)
async def test_snapshot_profile_previews_use_preview_transport(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    model: str,
    item: LibraryItem,
) -> None:
    coordinator = GoveeBLECoordinator(
        hass,
        "AA:BB:CC:DD:EE:FF",
        model,
        configuration_url="homeassistant://ha-govee-led-ble/editor/entry-a",
    )
    coordinator.async_preview_preflight = AsyncMock()  # type: ignore[method-assign]
    coordinator.async_preview_write = AsyncMock()  # type: ignore[method-assign]
    coordinator.async_preview_observe = AsyncMock(return_value=True)  # type: ignore[method-assign]
    coordinator.send_command = AsyncMock(side_effect=AssertionError("preview must use preview transport"))  # type: ignore[method-assign]
    manager, _cache = await _manager(hass, monkeypatch, coordinator)
    owner = object()
    session_id = _open(manager, owner, [])

    await manager.async_queue_snapshot(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=1,
        updated_at="2026-08-17T00:00:00Z",
        item=item,
    )
    await manager.async_wait_idle("entry-a")

    coordinator.async_preview_write.assert_awaited()
    coordinator.send_command.assert_not_awaited()
    await manager.async_shutdown()


async def test_successful_unsaved_preview_invalidates_persistent_observed_match(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _coordinator()
    manager, cache = await _manager(hass, monkeypatch, coordinator)
    operation_id = uuid4()
    cache.set(
        ObservedDeviceState(
            config_entry_id="entry-a",
            mode="custom",
            observed_at="2026-08-16T00:00:00Z",
            confidence=ObservationConfidence.ACTIVATION_MATCH,
            diy_code=207,
            matched_operation_id=operation_id,
        )
    )
    owner = object()
    session_id = _open(manager, owner, [])

    await manager.async_queue_snapshot(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=1,
        updated_at="2026-08-17T00:00:00Z",
        item=_item("invalidate"),
    )
    await manager.async_wait_idle("entry-a")

    observed = cache.get("entry-a")
    assert observed is not None
    assert observed.matched_operation_id is None
    assert observed.confidence is ObservationConfidence.UNKNOWN
    assert manager._active_workspaces is not None  # noqa: SLF001
    workspace = manager._active_workspaces.get("entry-a")  # noqa: SLF001
    assert workspace is not None
    assert workspace.selector_label == "invalidate"
    assert workspace.content == _item("invalidate").content
    assert workspace.observable_signature == f"custom:{coordinator.diy_code}"
    assert workspace.confidence is ObservationConfidence.WRITE_COMPLETED
    coordinator.async_update_listeners.assert_called_once()
    await manager.async_shutdown()


async def test_config_unload_waits_for_atomic_write_and_drops_pending_work(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _coordinator()
    write_started = asyncio.Event()
    release_write = asyncio.Event()
    write_count = 0

    async def write(packet: bytes) -> None:
        nonlocal write_count
        write_count += 1
        if write_count == 1:
            write_started.set()
            await release_write.wait()
        coordinator.writes.append(packet)

    coordinator.async_preview_write.side_effect = write
    manager, _cache = await _manager(hass, monkeypatch, coordinator)
    owner = object()
    session_id = _open(manager, owner, [])
    await manager.async_queue_snapshot(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=1,
        updated_at="2026-08-17T00:00:00Z",
        item=_item("active"),
    )
    await write_started.wait()
    await manager.async_queue_snapshot(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=2,
        updated_at="2026-08-17T00:00:01Z",
        item=_item("pending", 60),
    )

    unload = asyncio.create_task(manager.async_unload_device("entry-a"))
    await asyncio.sleep(0)
    assert not unload.done()
    with pytest.raises(PreviewError, match="not loaded"):
        await manager.async_queue_snapshot(
            session_id=session_id,
            owner=owner,
            config_entry_id="entry-a",
            sequence=3,
            updated_at="2026-08-17T00:00:02Z",
            item=_item("rejected", 70),
        )
    release_write.set()
    await unload

    assert "entry-a" not in manager._devices
    await manager.async_shutdown()


async def test_higher_intent_waits_for_complete_atomic_preview_sequence(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _coordinator()
    arbiter = BLEControlArbiter()
    coordinator._control_arbiter = arbiter
    coordinator._control_lock = arbiter
    coordinator.admit_preview = arbiter.admit_preview
    coordinator.invalidate_previews = arbiter.invalidate_previews
    coordinator.is_on = True
    item = _item("atomic")
    compiled = compile_application(item, coordinator.model, diy_code=resolve_diy_code(item, None))
    assert isinstance(compiled, CompiledEffect)
    foreground: asyncio.Task[None] | None = None

    async def run_foreground() -> None:
        async with arbiter.hold(ControlIntent.USER):
            pass

    async def write(packet: bytes) -> None:
        nonlocal foreground
        coordinator.writes.append(packet)
        if foreground is None:
            foreground = asyncio.create_task(run_foreground())
            await asyncio.sleep(0)

    coordinator.async_preview_write.side_effect = write
    manager, _cache = await _manager(hass, monkeypatch, coordinator)
    owner = object()
    events: list[PreviewStatus] = []
    session_id = _open(manager, owner, events)

    await manager.async_queue_snapshot(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=1,
        updated_at="2026-08-17T00:00:00Z",
        item=item,
    )
    await manager.async_wait_idle("entry-a")
    assert foreground is not None
    await foreground

    assert coordinator.writes == list(compiled.packets)
    assert any(
        event.phase is PreviewPhase.CANCELLED
        and event.error_code == "superseded"
        and event.write_disposition is PreviewWriteDisposition.COMPLETED
        for event in events
    )
    assert "entry-a" not in manager._health_targets
    await manager.async_shutdown()


async def test_preview_admitted_during_foreground_intent_applies_after_release(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _coordinator(readable=True)
    arbiter = BLEControlArbiter()
    coordinator._control_arbiter = arbiter
    coordinator._control_lock = arbiter
    coordinator.admit_preview = arbiter.admit_preview
    coordinator.invalidate_previews = arbiter.invalidate_previews
    original_sequence = coordinator.async_write_effect_sequence.side_effect
    foreground_acquired = asyncio.Event()
    release_foreground = asyncio.Event()

    async def write_sequence(*args, intent, **kwargs) -> None:
        async with arbiter.hold(intent):
            await original_sequence(*args, intent=intent, **kwargs)

    async def hold_foreground() -> None:
        async with arbiter.hold(ControlIntent.USER):
            foreground_acquired.set()
            await release_foreground.wait()

    coordinator.async_write_effect_sequence.side_effect = write_sequence
    manager, _cache = await _manager(hass, monkeypatch, coordinator)
    owner = object()
    events: list[PreviewStatus] = []
    session_id = _open(manager, owner, events)
    foreground = asyncio.create_task(hold_foreground())
    await foreground_acquired.wait()

    await manager.async_queue_snapshot(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=1,
        updated_at="2026-08-17T00:00:00Z",
        item=_item("after foreground"),
    )
    await asyncio.sleep(0)
    coordinator.async_preview_write.assert_not_awaited()

    release_foreground.set()
    await foreground
    await manager.async_wait_idle("entry-a")

    assert coordinator.async_preview_write.await_count > 0
    assert any(event.phase is PreviewPhase.CONFIRMED for event in events)
    await manager.async_shutdown()


async def test_session_cancel_finishes_active_sequence_without_replaying_pending_work(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _coordinator()
    write_started = asyncio.Event()
    release_write = asyncio.Event()
    write_count = 0

    async def write(packet: bytes) -> None:
        nonlocal write_count
        write_count += 1
        if write_count == 1:
            write_started.set()
            await release_write.wait()
        coordinator.writes.append(packet)

    coordinator.async_preview_write.side_effect = write
    manager, _cache = await _manager(hass, monkeypatch, coordinator)
    owner = object()
    events: list[PreviewStatus] = []
    session_id = _open(manager, owner, events)
    await manager.async_queue_snapshot(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=1,
        updated_at="2026-08-17T00:00:00Z",
        item=_item("active"),
    )
    await write_started.wait()
    await manager.async_queue_snapshot(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=2,
        updated_at="2026-08-17T00:00:01Z",
        item=_item("pending", 60),
    )

    await manager.async_cancel(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
    )
    release_write.set()
    await manager.async_wait_idle("entry-a")

    assert any(event.sequence == 1 and event.error_code == "session_cancelled" for event in events)
    assert any(event.sequence == 2 and event.error_code == "session_cancelled" for event in events)
    assert not any(event.phase is PreviewPhase.WRITTEN for event in events)
    await manager.async_shutdown()


async def test_shutdown_marks_active_sequence_incomplete_and_rejects_new_sessions(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _coordinator()
    write_started = asyncio.Event()
    release_write = asyncio.Event()

    async def write(packet: bytes) -> None:
        write_started.set()
        await release_write.wait()
        coordinator.writes.append(packet)

    coordinator.async_preview_write.side_effect = write
    manager, _cache = await _manager(hass, monkeypatch, coordinator)
    owner = object()
    events: list[PreviewStatus] = []
    session_id = _open(manager, owner, events)
    await manager.async_queue_snapshot(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=1,
        updated_at="2026-08-17T00:00:00Z",
        item=_item("shutdown"),
    )
    await write_started.wait()

    shutdown = asyncio.create_task(manager.async_shutdown())
    await asyncio.sleep(0)
    release_write.set()
    await shutdown

    assert any(
        event.phase is PreviewPhase.FAILED
        and event.error_code == "shutdown_incomplete"
        and event.write_disposition is PreviewWriteDisposition.COMPLETED
        for event in events
    )
    with pytest.raises(PreviewShutdownError):
        manager.open_session(owner=object())


async def test_scene_preview_validation_errors(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _coordinator()
    manager, _cache = await _manager(hass, monkeypatch, coordinator)
    owner = object()
    session_id = _open(manager, owner, [])
    speed_scene = next(entry for entry in SCENE_ENTRIES["H617A"] if entry.speed is not None)
    no_speed_scene = next(entry for entry in SCENE_ENTRIES["H617A"] if entry.speed is None)

    with pytest.raises(PreviewError, match="does not expose"):
        await manager.async_queue_scene(
            session_id=session_id,
            owner=owner,
            config_entry_id="entry-a",
            sequence=1,
            updated_at="2026-08-17T00:00:00Z",
            scene_id=no_speed_scene.scene_id,
            effect_id=no_speed_scene.effect_id,
            speed_index=1,
        )
    assert speed_scene.speed is not None
    with pytest.raises(PreviewError, match="outside"):
        await manager.async_queue_scene(
            session_id=session_id,
            owner=owner,
            config_entry_id="entry-a",
            sequence=1,
            updated_at="2026-08-17T00:00:00Z",
            scene_id=speed_scene.scene_id,
            effect_id=speed_scene.effect_id,
            speed_index=speed_scene.speed.option_count,
        )
    await manager.async_shutdown()


async def test_preview_acceptance_rejects_stale_unloading_and_incompatible_requests(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, _cache = await _manager(hass, monkeypatch, _coordinator())
    owner = object()
    session_id = _open(manager, owner, [])

    with pytest.raises(PreviewSequenceError, match="from 1"):
        await manager.async_queue_snapshot(
            session_id=session_id,
            owner=owner,
            config_entry_id="entry-a",
            sequence=0,
            updated_at="2026-08-17T00:00:00Z",
            item=_item("zero"),
        )

    await manager.async_queue_snapshot(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=1,
        updated_at="2026-08-17T00:00:00Z",
        item=_item("first"),
    )
    retry = await manager.async_queue_snapshot(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=1,
        updated_at="2026-08-17T00:00:01Z",
        item=_item("same physical state"),
    )
    assert retry.accepted
    with pytest.raises(PreviewSequenceError, match="different desired states"):
        await manager.async_queue_snapshot(
            session_id=session_id,
            owner=owner,
            config_entry_id="entry-a",
            sequence=1,
            updated_at="2026-08-17T00:00:01Z",
            item=_item("different", 60),
        )
    await manager.async_wait_idle("entry-a")

    incompatible = LibraryItem.new(
        "Video",
        VideoProfile(
            "H6199",
            "movie",
            True,
            70,
            True,
            40,
            12,
            RelativeBrightness(80, 60, 55, 45),
            False,
        ),
    )
    with pytest.raises(PreviewError, match="not supported"):
        await manager.async_queue_snapshot(
            session_id=session_id,
            owner=owner,
            config_entry_id="entry-a",
            sequence=2,
            updated_at="2026-08-17T00:00:02Z",
            item=incompatible,
        )

    await manager.async_unload_device("entry-a")
    with pytest.raises(PreviewError, match="not loaded"):
        await manager.async_queue_snapshot(
            session_id=session_id,
            owner=owner,
            config_entry_id="entry-a",
            sequence=2,
            updated_at="2026-08-17T00:00:02Z",
            item=_item("unloading"),
        )
    await manager.async_load_device("entry-a")
    manager._stopping = True
    with pytest.raises(PreviewShutdownError):
        await manager.async_queue_snapshot(
            session_id=session_id,
            owner=owner,
            config_entry_id="entry-a",
            sequence=2,
            updated_at="2026-08-17T00:00:02Z",
            item=_item("stopping"),
        )
    await manager.async_shutdown()


async def test_pending_verification_is_cancelled_by_new_work_cancel_unload_and_shutdown(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from custom_components.ha_govee_led_ble import effect_preview

    coordinator = _coordinator()
    manager, _cache = await _manager(hass, monkeypatch, coordinator)
    owner = object()
    session_id = _open(manager, owner, [])
    request = effect_preview._PreviewRequest(
        session_id=session_id,
        config_entry_id="entry-a",
        sequence=1,
        updated_at="2026-08-17T00:00:00Z",
        fingerprint="pending",
        generation=1,
        correlation_id="correlation",
        persist_default=False,
        content_kind="h617a_single",
        item=_item("pending"),
    )
    verification = asyncio.create_task(asyncio.sleep(10))
    manager._devices["entry-a"] = effect_preview._DeviceWorker(
        verification_task=verification,
        verification_request=request,
    )
    await manager.async_queue_snapshot(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=1,
        updated_at="2026-08-17T00:00:00Z",
        item=_item("new"),
    )
    await asyncio.gather(verification, return_exceptions=True)
    await manager.async_wait_idle("entry-a")

    verification = asyncio.create_task(asyncio.sleep(10))
    worker = manager._devices["entry-a"]
    worker.verification_task = verification
    worker.verification_request = replace(request, sequence=2)
    await manager.async_cancel(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
    )
    await asyncio.gather(verification, return_exceptions=True)

    verification = asyncio.create_task(asyncio.sleep(10))
    worker.pending = replace(request, sequence=3, generation=3)
    worker.verification_task = verification
    worker.verification_request = replace(request, sequence=3)
    await manager.async_unload_device("entry-a")
    await asyncio.gather(verification, return_exceptions=True)
    await manager.async_load_device("entry-a")

    worker = effect_preview._DeviceWorker(
        pending=replace(request, sequence=4, generation=4),
        verification_task=asyncio.create_task(asyncio.sleep(10)),
        verification_request=replace(request, sequence=4),
    )
    manager._devices["entry-a"] = worker
    await manager.async_shutdown()
    assert not manager._devices


async def test_compilation_failure_is_reported_without_writing(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _coordinator()
    manager, _cache = await _manager(hass, monkeypatch, coordinator)
    owner = object()
    events: list[PreviewStatus] = []
    session_id = _open(manager, owner, events)
    from custom_components.ha_govee_led_ble import effect_preview

    def compile_failure(*_args, **_kwargs):
        raise ValueError("invalid")

    monkeypatch.setattr(effect_preview, "compile_application", compile_failure)
    await manager.async_queue_snapshot(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=1,
        updated_at="2026-08-17T00:00:00Z",
        item=_item("invalid"),
    )
    await manager.async_wait_idle("entry-a")

    coordinator.async_preview_write.assert_not_awaited()
    assert any(event.phase is PreviewPhase.FAILED and event.error_code == "compilation_failed" for event in events)
    await manager.async_shutdown()


async def test_external_supersession_clears_pending_health_and_publishes_reason(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from custom_components.ha_govee_led_ble import effect_preview

    coordinator = _coordinator()
    manager, _cache = await _manager(hass, monkeypatch, coordinator)
    owner = object()
    events: list[PreviewStatus] = []
    session_id = _open(manager, owner, events)
    request = effect_preview._PreviewRequest(
        session_id=session_id,
        config_entry_id="entry-a",
        sequence=1,
        updated_at="2026-08-17T00:00:00Z",
        fingerprint="pending",
        generation=1,
        correlation_id="correlation",
        persist_default=False,
        content_kind="h617a_single",
        item=_item("pending"),
    )
    manager._devices["entry-a"] = effect_preview._DeviceWorker(
        pending=request,
        latest_accepted_generation=1,
    )
    manager._health_targets["entry-a"] = effect_preview._HealthTarget(
        expectations={"effect": None},
        confirmed_confidence=ObservationConfidence.ACTIVATION_MATCH,
    )

    await manager.async_supersede_device("entry-a", reason="user_command")

    assert manager._devices["entry-a"].pending is None
    assert "entry-a" not in manager._health_targets
    assert any(event.phase is PreviewPhase.CANCELLED and event.error_code == "user_command" for event in events)
    await manager.async_shutdown()


@pytest.mark.parametrize(
    ("observation", "phase", "error_code"),
    [
        (False, PreviewPhase.UNCONFIRMED, "device_state_mismatch"),
        (RuntimeError("read failed"), PreviewPhase.WRITTEN, None),
        ("timeout", PreviewPhase.WRITTEN, None),
    ],
)
async def test_preview_verification_reports_non_successful_readback(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    observation: object,
    phase: PreviewPhase,
    error_code: str | None,
) -> None:
    coordinator = _coordinator(readable=True)
    if observation == "timeout":
        coordinator.async_preview_observe.side_effect = TimeoutError
    elif isinstance(observation, Exception):
        coordinator.async_preview_observe.side_effect = observation
    else:
        coordinator.async_preview_observe.return_value = observation
    manager, _cache = await _manager(
        hass,
        monkeypatch,
        coordinator,
        verify_timeout=0.01,
    )
    owner = object()
    events: list[PreviewStatus] = []
    session_id = _open(manager, owner, events)

    await manager.async_queue_snapshot(
        session_id=session_id,
        owner=owner,
        config_entry_id="entry-a",
        sequence=1,
        updated_at="2026-08-17T00:00:00Z",
        item=_item("verify"),
    )
    await manager.async_wait_idle("entry-a")

    assert events[-1].phase is phase
    assert events[-1].error_code == error_code
    await manager.async_shutdown()
