"""Effect Studio deployment transactions."""

from __future__ import annotations

import asyncio
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call
from uuid import uuid4

import pytest
from homeassistant.core import HomeAssistant

from custom_components.ha_govee_led_ble.effect_active_workspace import (
    ActiveEffectWorkspace,
    ActiveEffectWorkspaceRepository,
)
from custom_components.ha_govee_led_ble.effect_backend import EffectBackend
from custom_components.ha_govee_led_ble.effect_catalogue import (
    H617A_WORKSHOP_APPLY_CODE,
    H6199_PALETTE_DIY_APPLY_CODE,
    H6199_WORKSHOP_APPLY_CODE,
    WORKSHOP_PROTOCOL_FIXTURES,
)
from custom_components.ha_govee_led_ble.effect_compiler import compile_effect, compile_h617a, compile_h6199
from custom_components.ha_govee_led_ble.effect_deployments import (
    DeploymentPhase,
    DeploymentRecord,
    EffectDeploymentRepository,
    ObservationConfidence,
)
from custom_components.ha_govee_led_ble.effect_domain import (
    LibraryItem,
    MusicProfile,
    Origin,
    PaintedEffect,
    PaletteDiyEffect,
    RelativeBrightness,
    SingleEffect,
    SourceKind,
    VideoProfile,
)
from custom_components.ha_govee_led_ble.effect_identity import EffectDeviceCache
from custom_components.ha_govee_led_ble.effect_runtime import (
    EffectDeploymentEngine,
)
from custom_components.ha_govee_led_ble.generated_protocol_adapter import build_power
from custom_components.ha_govee_led_ble.layered_scene_decoder import decode_catalogue_layered_scene
from custom_components.ha_govee_led_ble.scenes import SCENE_ENTRIES
from tests.storage_test_double import InMemoryVersionedDocumentStore


def _item() -> LibraryItem:
    return LibraryItem.new(
        "Paint",
        PaintedEffect("clockwise", 50, 100, (None,) * 15),
    )


def _type04_item() -> LibraryItem:
    return LibraryItem.new("Test", SingleEffect(0, 0, 50, ((255, 0, 0),)))


def _sena_item() -> LibraryItem:
    return LibraryItem.new(
        "Sena",
        SingleEffect(
            9,
            9,
            50,
            (
                (255, 0, 0),
                (255, 127, 0),
                (255, 255, 0),
                (0, 255, 0),
                (0, 0, 255),
                (75, 0, 130),
                (148, 0, 211),
            ),
        ),
    )


def _flow_workspace(
    *,
    confidence: ObservationConfidence = ObservationConfidence.WRITE_COMPLETED,
) -> ActiveEffectWorkspace:
    return ActiveEffectWorkspace(
        config_entry_id="entry-a",
        model="H617A",
        selector_label="Flow",
        content=SingleEffect(
            9,
            9,
            50,
            (
                (255, 0, 0),
                (255, 128, 0),
                (255, 255, 0),
                (0, 255, 0),
                (0, 0, 255),
            ),
        ),
        origin=Origin(SourceKind.CATALOGUE_TEMPLATE, "h617a:flow:clockwise"),
        observable_signature="custom:24",
        updated_at="2026-08-26T00:01:00Z",
        generation=1,
        confidence=confidence,
    )


def _confirmed_saved_record(item: LibraryItem, *, diy_code: int = 24) -> DeploymentRecord:
    return DeploymentRecord(
        operation_id=uuid4(),
        config_entry_id="entry-a",
        diy_code=diy_code,
        phase=DeploymentPhase.CONFIRMED,
        compiler_version=1,
        artifact_sha256=sha256(item.content_hash.encode()).hexdigest(),
        updated_at="2026-08-26T00:00:00Z",
        target_mode="custom",
        source_kind="saved_effect",
        selector_label=item.name,
        source_origin_kind=item.origin.kind.value,
        source_origin_id=item.origin.source_id,
        source_content_hash=item.content_hash,
        item_id=item.id,
        item_version=item.version,
        verification_confidence=ObservationConfidence.ACTIVATION_MATCH,
    )


def _h6199_item(*, family: int = 8, variant: int = 9) -> LibraryItem:
    return LibraryItem.new(
        "H6199 palette",
        PaletteDiyEffect("H6199", family, variant, 60, ((255, 0, 0), (0, 0, 255))),
    )


def _music_item(model: str = "H617A") -> LibraryItem:
    return LibraryItem.new(
        "Separation",
        MusicProfile(
            model,
            "separation" if model == "H617A" else "rolling",
            50,
            (1, 2, 3),
            None,
            {"point": 5, "gradient": False} if model == "H617A" else {},
        ),
    )


def _video_item() -> LibraryItem:
    return LibraryItem.new(
        "Movie",
        VideoProfile(
            "H6199",
            "movie",
            False,
            63,
            True,
            27,
            10,
            RelativeBrightness(20, 30, 40, 50),
            True,
        ),
    )


def _coordinator(*, readable: bool = True):
    coordinator = SimpleNamespace(
        _control_lock=asyncio.Lock(),
        address="AA:BB:CC:DD:EE:FF",
        model="H617A",
        profile=SimpleNamespace(state_readable=readable, supports_color_mode_readback=True),
        is_on=True,
        brightness_pct=72,
        rgb_color=(1, 2, 3),
        color_temp_kelvin=None,
        effect=None,
        unknown_scene_code=None,
        diy_code=None,
        music_mode="off",
        video_mode="off",
        music_sensitivity=50,
        music_calm=False,
        music_color=None,
        send_command=AsyncMock(),
        refresh_state=AsyncMock(return_value=True),
    )

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
            await coordinator.send_command(packet)
            if progress is not None:
                await progress(index)

    coordinator.async_write_effect_sequence = AsyncMock(side_effect=write_effect_sequence)
    return coordinator


def _profile_coordinator(model: str):
    coordinator = _coordinator()
    coordinator.model = model
    coordinator.profile = SimpleNamespace(
        state_readable=True,
        supports_color_mode_readback=True,
        supports_video_mode=model == "H6199",
        supports_video_sound_effects=model == "H6199",
        supports_white_balance=model == "H6199",
        supports_relative_brightness=model == "H6199",
        supports_blank_screen=model == "H6199",
    )
    coordinator.video_full_screen = True
    coordinator.video_saturation = 88
    coordinator.video_sound_effects = False
    coordinator.video_sound_effects_softness = 50
    coordinator.white_balance_red = 16
    coordinator.white_balance_blue = 3
    coordinator.relative_brightness = 75
    coordinator.relative_brightness_left = 75
    coordinator.relative_brightness_top = 75
    coordinator.relative_brightness_right = 75
    coordinator.relative_brightness_bottom = 75
    coordinator.blank_screen = False
    coordinator.blank_screen_detection = 2
    coordinator.blank_screen_low_brightness_duration_seconds = 10
    coordinator.blank_screen_same_tone_duration_seconds = 120
    coordinator.music_separation_point = 1
    coordinator.music_separation_gradient = True
    coordinator.music_hopping_brightness = 50
    coordinator.music_piano_key_count = 15
    coordinator.music_fountain_direction = "clockwise"
    coordinator.music_daynight_segments = 1
    coordinator.music_daynight_speed = 10
    coordinator.music_daynight_gradient = False
    return coordinator


class YieldingVersionedDocumentStore(InMemoryVersionedDocumentStore):
    async def async_save(self, data) -> None:
        await asyncio.sleep(0)
        await super().async_save(data)


def _confirm_on_call(coordinator, call_number: int, diy_code: int) -> None:
    async def refresh() -> bool:
        if coordinator.refresh_state.await_count >= call_number:
            coordinator.diy_code = diy_code
        return True

    coordinator.refresh_state.side_effect = refresh


def _confirm_scene_code_on_call(coordinator, call_number: int, scene_code: int) -> None:
    async def refresh() -> bool:
        if coordinator.refresh_state.await_count >= call_number:
            coordinator.unknown_scene_code = scene_code
        return True

    coordinator.refresh_state.side_effect = refresh


async def _repositories(hass: HomeAssistant):
    deployments = EffectDeploymentRepository(hass)
    cache = EffectDeviceCache(hass)
    await deployments.async_load()
    await cache.async_load()
    return deployments, cache


async def test_saved_effect_uploads_activates_then_confirms_selector(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _coordinator()
    coordinator.data = {}
    coordinator.async_set_updated_data = MagicMock()
    _confirm_on_call(coordinator, 2, 800)
    item = _item()
    compiled = compile_h617a(item, 800)

    result = await EffectDeploymentEngine(repository, cache).async_apply_saved(
        coordinator,
        item,
        config_entry_id="entry-a",
        updated_at="2026-08-11T00:00:00Z",
    )

    assert result.phase is DeploymentPhase.CONFIRMED
    assert result.verification_confidence is ObservationConfidence.ACTIVATION_MATCH
    assert result.prior_state is not None
    assert result.prior_state.rgb_color == (1, 2, 3)
    assert coordinator.send_command.await_args_list == [call(packet) for packet in compiled.packets]
    assert repository.get(result.operation_id) == result
    assert cache.get("entry-a") is not None
    assert cache.get("entry-a").confidence is ObservationConfidence.ACTIVATION_MATCH
    assert cache.get("entry-a").matched_operation_id == result.operation_id
    assert cache.get("entry-a").active_effect is not None
    assert cache.get("entry-a").active_effect.item_id == item.id
    assert cache.get("entry-a").active_effect.item_version == item.version
    assert cache.get("entry-a").active_effect.content_hash == item.content_hash
    assert cache.get("entry-a").active_effect.observable_signature == "custom:800"
    coordinator.async_set_updated_data.assert_called_once_with({})


async def test_saved_effect_powers_on_before_committed_upload(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _coordinator()
    coordinator.is_on = False
    coordinator.data = {}
    coordinator.async_set_updated_data = MagicMock()
    _confirm_on_call(coordinator, 2, 800)
    item = _item()
    compiled = compile_h617a(item, 800)

    result = await EffectDeploymentEngine(repository, cache).async_apply_saved(
        coordinator,
        item,
        config_entry_id="entry-a",
        updated_at="2026-08-11T00:00:00Z",
    )

    assert result.phase is DeploymentPhase.CONFIRMED
    assert coordinator.is_on is True
    assert coordinator.send_command.await_args_list == [
        call(build_power(True, coordinator.model)),
        *(call(packet) for packet in compiled.packets),
    ]


async def test_layered_scene_uses_shared_transaction_and_identity_verification(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _coordinator()
    entry = next(scene for scene in SCENE_ENTRIES["H617A"] if scene.scene_type == 2 and scene.param)
    content = decode_catalogue_layered_scene("H617A", entry)
    assert content is not None
    item = LibraryItem.new("Layered scene", content)
    compiled = compile_effect(item, "H617A")

    async def refresh() -> bool:
        if coordinator.refresh_state.await_count >= 2:
            coordinator.effect = compiled.expected_effect
        return True

    coordinator.refresh_state.side_effect = refresh

    result = await EffectDeploymentEngine(repository, cache).async_apply_saved(
        coordinator,
        item,
        config_entry_id="entry-a",
        updated_at="2026-08-11T00:00:00Z",
    )

    assert result.phase is DeploymentPhase.CONFIRMED
    assert result.target_mode == "scene"
    assert result.target_effect == compiled.expected_effect
    assert result.verification_confidence is ObservationConfidence.ACTIVATION_MATCH
    assert result.evidence_codes == (
        "scene_payload_readback_unavailable",
        "layered_field_semantics_uncalibrated",
    )
    assert coordinator.send_command.await_args_list == [call(packet) for packet in compiled.packets]
    assert cache.get("entry-a").effect == compiled.expected_effect
    assert cache.get("entry-a").matched_operation_id == result.operation_id


async def test_h6199_layered_scene_uses_model_framing_and_identity_verification(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _coordinator()
    coordinator.model = "H6199"
    entry = next(scene for scene in SCENE_ENTRIES["H6199"] if scene.scene_type == 2 and scene.param)
    content = decode_catalogue_layered_scene("H6199", entry)
    assert content is not None
    item = LibraryItem.new("Layered scene", content)
    compiled = compile_effect(item, "H6199")

    async def refresh() -> bool:
        if coordinator.refresh_state.await_count >= 2:
            coordinator.effect = compiled.expected_effect
        return True

    coordinator.refresh_state.side_effect = refresh

    result = await EffectDeploymentEngine(repository, cache).async_apply_saved(
        coordinator,
        item,
        config_entry_id="entry-a",
        updated_at="2026-08-11T00:00:00Z",
    )

    assert result.phase is DeploymentPhase.CONFIRMED
    assert result.target_mode == "scene"
    assert coordinator.send_command.await_args_list == [call(packet) for packet in compiled.packets]
    assert cache.get("entry-a").effect == compiled.expected_effect


async def test_failed_layered_scene_recovers_prior_state(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _coordinator()
    coordinator.effect = "sunrise"
    coordinator.async_restore_effect_control_state = AsyncMock(return_value=True)
    entry = next(scene for scene in SCENE_ENTRIES["H617A"] if scene.scene_type == 2 and scene.param)
    content = decode_catalogue_layered_scene("H617A", entry)
    assert content is not None
    item = LibraryItem.new("Layered scene", content)
    active_workspaces = ActiveEffectWorkspaceRepository(InMemoryVersionedDocumentStore())
    await active_workspaces.async_load()
    prior_workspace = ActiveEffectWorkspace(
        config_entry_id="entry-a",
        model="H617A",
        selector_label="Flow",
        content=SingleEffect(9, 9, 50, ((255, 0, 0),)),
        origin=item.origin,
        observable_signature="scene:sunrise",
        updated_at="2026-08-10T00:00:00Z",
        generation=1,
    )
    active_workspaces.set(prior_workspace)

    result = await EffectDeploymentEngine(
        repository,
        cache,
        active_workspaces,
    ).async_apply_saved(
        coordinator,
        item,
        config_entry_id="entry-a",
        updated_at="2026-08-11T00:00:00Z",
    )

    assert result.phase is DeploymentPhase.FAILED
    coordinator.async_restore_effect_control_state.assert_awaited_once_with(
        result.prior_state,
        overwritten_diy_code=-1,
    )
    assert active_workspaces.get("entry-a") == prior_workspace


async def test_failed_snapshot_does_not_publish_the_rolled_back_state(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _coordinator()
    coordinator.effect = "sunrise"
    coordinator.async_restore_effect_control_state = AsyncMock(return_value=True)
    entry = next(scene for scene in SCENE_ENTRIES["H617A"] if scene.scene_type == 2 and scene.param)
    content = decode_catalogue_layered_scene("H617A", entry)
    assert content is not None
    active_workspaces = ActiveEffectWorkspaceRepository(InMemoryVersionedDocumentStore())
    await active_workspaces.async_load()

    result = await EffectDeploymentEngine(
        repository,
        cache,
        active_workspaces,
    ).async_apply_snapshot(
        coordinator,
        LibraryItem.new("Layered scene", content),
        config_entry_id="entry-a",
        updated_at="2026-08-11T00:00:00Z",
    )

    assert result.phase is DeploymentPhase.FAILED
    assert active_workspaces.get("entry-a") is None


async def test_verification_retry_only_repeats_safe_activation(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _coordinator()
    item = _item()
    compiled = compile_h617a(item, 800)

    async def refresh() -> bool:
        if coordinator.refresh_state.await_count == 2:
            coordinator.diy_code = 999
        elif coordinator.refresh_state.await_count >= 3:
            coordinator.diy_code = 800
        return True

    coordinator.refresh_state.side_effect = refresh

    result = await EffectDeploymentEngine(repository, cache).async_apply_saved(
        coordinator,
        item,
        config_entry_id="entry-a",
        updated_at="2026-08-11T00:00:00Z",
    )

    assert result.phase is DeploymentPhase.CONFIRMED
    assert coordinator.send_command.await_args_list == [
        *[call(packet) for packet in compiled.upload_packets],
        call(compiled.activation_packet),
        call(compiled.activation_packet),
    ]
    assert coordinator.refresh_state.await_count == 3


async def test_non_transport_sequence_failure_is_not_retried(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _coordinator()
    item = _item()
    compiled = compile_h617a(item, 800)
    coordinator.send_command.side_effect = [
        *([None] * len(compiled.upload_packets)),
        RuntimeError("ambiguous activation write"),
    ]

    with pytest.raises(RuntimeError, match="ambiguous activation write"):
        await EffectDeploymentEngine(repository, cache).async_apply_saved(
            coordinator,
            item,
            config_entry_id="entry-a",
            updated_at="2026-08-11T00:00:00Z",
        )

    assert coordinator.send_command.await_args_list == [
        *[call(packet) for packet in compiled.upload_packets],
        call(compiled.activation_packet),
    ]


async def test_upload_does_not_start_if_uploading_phase_cannot_be_persisted(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _coordinator()
    operation_id = uuid4()
    original_put = repository.async_put

    async def fail_uploading(record, *, expected_version):
        if record.phase is DeploymentPhase.UPLOADING:
            raise OSError("storage unavailable")
        return await original_put(record, expected_version=expected_version)

    monkeypatch.setattr(repository, "async_put", fail_uploading)

    with pytest.raises(OSError, match="storage unavailable"):
        await EffectDeploymentEngine(repository, cache).async_apply_saved(
            coordinator,
            _item(),
            config_entry_id="entry-a",
            updated_at="2026-08-11T00:00:00Z",
            operation_id=operation_id,
        )

    failed = repository.get(operation_id)
    assert failed.phase is DeploymentPhase.FAILED
    assert failed.error_code == "OSError"
    coordinator.send_command.assert_not_awaited()


async def test_mid_upload_failure_is_uncertain_without_supported_recovery(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _coordinator()
    item = _item()
    compiled = compile_h617a(item, 800)
    coordinator.send_command.side_effect = [None, RuntimeError("write failed")]
    operation_id = uuid4()

    with pytest.raises(RuntimeError, match="write failed"):
        await EffectDeploymentEngine(repository, cache).async_apply_saved(
            coordinator,
            item,
            config_entry_id="entry-a",
            updated_at="2026-08-11T00:00:00Z",
            operation_id=operation_id,
        )

    failed = repository.get(operation_id)
    assert failed.phase is DeploymentPhase.UNCERTAIN
    assert failed.error_code == "RuntimeError"
    assert failed.progress_current == 1
    assert failed.progress_total == len(compiled.packets)
    assert coordinator.send_command.await_args_list == [
        call(compiled.upload_packets[0]),
        call(compiled.upload_packets[1]),
    ]


async def test_mid_upload_failure_recovers_prior_state_and_fails_cleanly(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _coordinator()
    coordinator.async_restore_effect_control_state = AsyncMock(return_value=True)
    coordinator.send_command.side_effect = [None, RuntimeError("write failed")]
    operation_id = uuid4()

    with pytest.raises(RuntimeError, match="write failed"):
        await EffectDeploymentEngine(repository, cache).async_apply_saved(
            coordinator,
            _item(),
            config_entry_id="entry-a",
            updated_at="2026-08-11T00:00:00Z",
            operation_id=operation_id,
        )

    failed = repository.get(operation_id)
    assert failed.phase is DeploymentPhase.FAILED
    coordinator.async_restore_effect_control_state.assert_awaited_once()
    assert coordinator.async_restore_effect_control_state.await_args.kwargs == {"overwritten_diy_code": 800}


async def test_queued_user_command_runs_after_recovery_under_original_lock(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _coordinator()
    failed_write_started = asyncio.Event()
    release_failed_write = asyncio.Event()
    order: list[str] = []
    write_count = 0

    async def send_command(_packet: bytes) -> None:
        nonlocal write_count
        write_count += 1
        if write_count == 2:
            failed_write_started.set()
            await release_failed_write.wait()
            raise RuntimeError("write failed")

    async def restore_prior_state(*_args, **_kwargs) -> bool:
        order.append("recovery")
        coordinator.brightness_pct = 72
        return True

    coordinator.send_command.side_effect = send_command
    coordinator.async_restore_effect_control_state = AsyncMock(side_effect=restore_prior_state)
    deployment_task = asyncio.create_task(
        EffectDeploymentEngine(repository, cache).async_apply_saved(
            coordinator,
            _item(),
            config_entry_id="entry-a",
            updated_at="2026-08-11T00:00:00Z",
        )
    )
    await failed_write_started.wait()

    async def queued_user_command() -> None:
        async with coordinator._control_lock:
            order.append("user")
            coordinator.brightness_pct = 10

    user_task = asyncio.create_task(queued_user_command())
    await asyncio.sleep(0)
    release_failed_write.set()

    with pytest.raises(RuntimeError, match="write failed"):
        await deployment_task
    await user_task

    assert order == ["recovery", "user"]
    assert coordinator.brightness_pct == 10


async def test_verification_failure_retries_reads_then_recovers(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _coordinator()
    coordinator.async_restore_effect_control_state = AsyncMock(return_value=True)

    async def refresh() -> bool:
        if coordinator.refresh_state.await_count == 1:
            return True
        raise RuntimeError("read failed")

    coordinator.refresh_state.side_effect = refresh
    item = _item()
    compiled = compile_h617a(item, 800)
    operation_id = uuid4()

    with pytest.raises(RuntimeError, match="read failed"):
        await EffectDeploymentEngine(repository, cache).async_apply_saved(
            coordinator,
            item,
            config_entry_id="entry-a",
            updated_at="2026-08-11T00:00:00Z",
            operation_id=operation_id,
        )

    failed = repository.get(operation_id)
    assert failed.phase is DeploymentPhase.FAILED
    assert failed.progress_current == len(compiled.packets)
    assert coordinator.refresh_state.await_count == 3
    assert coordinator.send_command.await_args_list == [call(packet) for packet in compiled.packets]
    coordinator.async_restore_effect_control_state.assert_awaited_once()


async def test_cancelled_partial_upload_is_not_resumed(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _coordinator()
    coordinator.async_restore_effect_control_state = AsyncMock(return_value=False)
    coordinator.send_command.side_effect = [None, asyncio.CancelledError()]
    operation_id = uuid4()

    with pytest.raises(asyncio.CancelledError):
        await EffectDeploymentEngine(repository, cache).async_apply_saved(
            coordinator,
            _item(),
            config_entry_id="entry-a",
            updated_at="2026-08-11T00:00:00Z",
            operation_id=operation_id,
        )

    interrupted = repository.get(operation_id)
    assert interrupted.phase is DeploymentPhase.UNCERTAIN
    assert interrupted.error_code == "operation_cancelled"
    assert interrupted.progress_current == 1
    assert coordinator.send_command.await_count == 2


async def test_same_operation_id_does_not_repeat_uncertain_upload(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _coordinator()
    coordinator.send_command.side_effect = RuntimeError("write failed")
    operation_id = uuid4()
    engine = EffectDeploymentEngine(repository, cache)

    with pytest.raises(RuntimeError, match="write failed"):
        await engine.async_apply_saved(
            coordinator,
            _item(),
            config_entry_id="entry-a",
            updated_at="2026-08-11T00:00:00Z",
            operation_id=operation_id,
        )
    writes_after_failure = coordinator.send_command.await_count

    with pytest.raises(RuntimeError, match="already exists"):
        await engine.async_apply_saved(
            coordinator,
            _item(),
            config_entry_id="entry-a",
            updated_at="2026-08-11T00:00:00Z",
            operation_id=operation_id,
        )

    assert coordinator.send_command.await_count == writes_after_failure


async def test_simultaneous_same_operation_id_shares_one_device_transaction() -> None:
    deployment_store = YieldingVersionedDocumentStore()
    repository = EffectDeploymentRepository(deployment_store)
    await repository.async_load()
    coordinator = _coordinator()
    item = _item()
    compiled = compile_h617a(item, 800)
    _confirm_on_call(coordinator, 2, 800)
    operation_id = uuid4()
    engine = EffectDeploymentEngine(repository)

    first, second = await asyncio.gather(
        engine.async_apply_saved(
            coordinator,
            item,
            config_entry_id="entry-a",
            updated_at="2026-08-11T00:00:00Z",
            operation_id=operation_id,
        ),
        engine.async_apply_saved(
            coordinator,
            item,
            config_entry_id="entry-a",
            updated_at="2026-08-11T00:00:00Z",
            operation_id=operation_id,
        ),
    )

    assert first == second
    assert first.phase is DeploymentPhase.CONFIRMED
    assert coordinator.send_command.await_args_list == [call(packet) for packet in compiled.packets]
    assert repository.snapshot().records == (first,)
    assert engine._operation_locks == {}
    assert engine._operation_lock_users == {}


async def test_custom_writes_wait_for_coordinator_control_lock(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _coordinator()
    _confirm_on_call(coordinator, 2, 800)
    engine = EffectDeploymentEngine(repository, cache)
    await coordinator._control_lock.acquire()

    task = asyncio.create_task(
        engine.async_apply_saved(
            coordinator,
            _item(),
            config_entry_id="entry-a",
            updated_at="2026-08-11T00:00:00Z",
        )
    )
    await asyncio.sleep(0)
    coordinator.send_command.assert_not_awaited()

    coordinator._control_lock.release()
    result = await task

    assert result.phase is DeploymentPhase.CONFIRMED


async def test_reconciliation_matches_only_latest_confirmed_selector(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    confirmed_item = _item()
    confirmed = DeploymentRecord(
        operation_id=uuid4(),
        config_entry_id="entry-a",
        diy_code=800,
        phase=DeploymentPhase.CONFIRMED,
        compiler_version=1,
        artifact_sha256=sha256(b"confirmed").hexdigest(),
        updated_at="2026-08-11T00:00:00Z",
        source_kind="saved_effect",
        selector_label=confirmed_item.name,
        source_origin_kind=confirmed_item.origin.kind.value,
        source_content_hash=confirmed_item.content_hash,
        item_id=confirmed_item.id,
        item_version=confirmed_item.version,
        verification_confidence=ObservationConfidence.ACTIVATION_MATCH,
    )
    await repository.async_put(confirmed, expected_version=None)
    coordinator = _coordinator()
    coordinator.diy_code = 800

    matched = await EffectDeploymentEngine(repository, cache).async_reconcile(
        coordinator,
        config_entry_id="entry-a",
        observed_at="2026-08-11T00:01:00Z",
    )

    assert matched.confidence is ObservationConfidence.ACTIVATION_MATCH
    assert matched.matched_operation_id == confirmed.operation_id

    uncertain_item = _item()
    uncertain = DeploymentRecord(
        operation_id=uuid4(),
        config_entry_id="entry-a",
        diy_code=800,
        phase=DeploymentPhase.UNCERTAIN,
        compiler_version=1,
        artifact_sha256=sha256(b"uncertain").hexdigest(),
        updated_at="2026-08-11T00:02:00Z",
        source_kind="saved_effect",
        selector_label=uncertain_item.name,
        source_origin_kind=uncertain_item.origin.kind.value,
        source_content_hash=uncertain_item.content_hash,
        item_id=uncertain_item.id,
        item_version=uncertain_item.version,
    )
    await repository.async_put(uncertain, expected_version=None)

    unmatched = await EffectDeploymentEngine(repository, cache).async_reconcile(
        coordinator,
        config_entry_id="entry-a",
        observed_at="2026-08-11T00:03:00Z",
    )

    assert unmatched.confidence is ObservationConfidence.UNKNOWN
    assert unmatched.matched_operation_id is None
    assert unmatched.active_effect is not None
    assert unmatched.active_effect.item_id == confirmed_item.id
    assert unmatched.active_effect.confidence is ObservationConfidence.UNKNOWN

    coordinator.diy_code = 801
    changed = await EffectDeploymentEngine(repository, cache).async_reconcile(
        coordinator,
        config_entry_id="entry-a",
        observed_at="2026-08-11T00:04:00Z",
    )

    assert changed.active_effect is None


async def test_matching_flow_workspace_suppresses_saved_sena_selector_history(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    sena = _sena_item()
    await repository.async_put(_confirmed_saved_record(sena), expected_version=None)
    active_workspaces = ActiveEffectWorkspaceRepository(InMemoryVersionedDocumentStore())
    await active_workspaces.async_load()
    workspace = _flow_workspace(confidence=ObservationConfidence.ACTIVATION_MATCH)
    active_workspaces.set(workspace)
    coordinator = _coordinator()
    coordinator.unknown_scene_code = 24
    repository.latest_for_diy_code = MagicMock(wraps=repository.latest_for_diy_code)
    repository.latest_for_effect = MagicMock(wraps=repository.latest_for_effect)
    repository.latest_for_profile = MagicMock(wraps=repository.latest_for_profile)

    observed = EffectDeploymentEngine(repository, cache, active_workspaces).reconcile_current(
        coordinator,
        config_entry_id="entry-a",
        observed_at="2026-08-26T00:02:00Z",
        refreshed=True,
    )

    assert observed.mode == "custom"
    assert observed.diy_code == 24
    assert observed.confidence is workspace.confidence
    assert observed.matched_operation_id is None
    assert observed.active_effect is None
    assert cache.get("entry-a") == observed
    assert active_workspaces.get("entry-a") == workspace
    repository.latest_for_diy_code.assert_not_called()
    repository.latest_for_effect.assert_not_called()
    repository.latest_for_profile.assert_not_called()


async def test_matching_flow_workspace_replaces_persisted_sena_hint_after_restart() -> None:
    deployment_store = InMemoryVersionedDocumentStore()
    cache_store = InMemoryVersionedDocumentStore()
    workspace_store = InMemoryVersionedDocumentStore()
    repository = EffectDeploymentRepository(deployment_store)
    cache = EffectDeviceCache(cache_store)
    active_workspaces = ActiveEffectWorkspaceRepository(workspace_store)
    await repository.async_load()
    await cache.async_load()
    await active_workspaces.async_load()
    sena = _sena_item()
    await repository.async_put(_confirmed_saved_record(sena), expected_version=None)
    coordinator = _coordinator()
    coordinator.unknown_scene_code = 24
    stale = EffectDeploymentEngine(repository, cache).reconcile_current(
        coordinator,
        config_entry_id="entry-a",
        observed_at="2026-08-26T00:00:30Z",
        refreshed=True,
    )
    assert stale.active_effect is not None
    assert stale.active_effect.item_id == sena.id
    await cache.async_flush()
    active_workspaces.set(_flow_workspace())
    await active_workspaces.async_flush()

    restored_repository = EffectDeploymentRepository(deployment_store)
    restored_cache = EffectDeviceCache(cache_store)
    restored_workspaces = ActiveEffectWorkspaceRepository(workspace_store)
    await restored_repository.async_load()
    restored_states = await restored_cache.async_load()
    await restored_workspaces.async_load()
    assert restored_states[0].active_effect is not None
    observed = EffectDeploymentEngine(
        restored_repository,
        restored_cache,
        restored_workspaces,
    ).reconcile_current(
        coordinator,
        config_entry_id="entry-a",
        observed_at="2026-08-26T00:02:00Z",
        refreshed=True,
    )

    assert observed.active_effect is None
    assert observed.matched_operation_id is None
    await restored_cache.async_flush()
    reloaded_cache = EffectDeviceCache(cache_store)
    assert (await reloaded_cache.async_load())[0].active_effect is None


async def test_confirmed_saved_sena_reapply_clears_matching_flow_workspace(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    active_workspaces = ActiveEffectWorkspaceRepository(InMemoryVersionedDocumentStore())
    await active_workspaces.async_load()
    active_workspaces.set(_flow_workspace())
    coordinator = _coordinator()
    published_workspaces = []
    coordinator.async_set_updated_data = MagicMock(
        side_effect=lambda _data: published_workspaces.append(active_workspaces.get("entry-a"))
    )
    coordinator.diy_code = 24
    _confirm_on_call(coordinator, 2, 24)
    sena = _sena_item()

    result = await EffectDeploymentEngine(
        repository,
        cache,
        active_workspaces,
    ).async_apply_saved(
        coordinator,
        sena,
        config_entry_id="entry-a",
        updated_at="2026-08-26T00:03:00Z",
        diy_code=24,
    )

    observed = cache.get("entry-a")
    assert result.phase is DeploymentPhase.CONFIRMED
    assert active_workspaces.get("entry-a") is None
    assert observed is not None
    assert observed.active_effect is not None
    assert observed.active_effect.item_id == sena.id
    assert observed.active_effect.item_version == sena.version
    assert observed.active_effect.content_hash == sena.content_hash
    assert len(published_workspaces) == 1
    assert published_workspaces[-1] is None


async def test_workspace_signature_mismatch_suspends_without_clearing() -> None:
    repository = EffectDeploymentRepository(InMemoryVersionedDocumentStore())
    cache = EffectDeviceCache(InMemoryVersionedDocumentStore())
    active_workspaces = ActiveEffectWorkspaceRepository(InMemoryVersionedDocumentStore())
    await repository.async_load()
    await cache.async_load()
    await active_workspaces.async_load()
    workspace = _flow_workspace()
    active_workspaces.set(workspace)
    coordinator = _coordinator()
    coordinator.diy_code = 25

    observed = EffectDeploymentEngine(repository, cache, active_workspaces).reconcile_current(
        coordinator,
        config_entry_id="entry-a",
        observed_at="2026-08-26T00:04:00Z",
        refreshed=True,
    )

    assert observed.diy_code == 25
    assert observed.active_effect is None
    assert active_workspaces.get("entry-a") == workspace


@pytest.mark.parametrize(
    ("mode_attribute", "native_mode"),
    [
        ("effect", "candlelight"),
        ("music_mode", "separation"),
        ("video_mode", "movie"),
    ],
)
async def test_reconciliation_preserves_native_mode_with_unknown_confidence(
    hass: HomeAssistant,
    mode_attribute: str,
    native_mode: str,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _coordinator()
    setattr(coordinator, mode_attribute, native_mode)

    observed = await EffectDeploymentEngine(repository, cache).async_reconcile(
        coordinator,
        config_entry_id="entry-a",
        observed_at="2026-08-11T00:00:00Z",
    )

    assert observed.native_mode == native_mode
    assert observed.confidence is ObservationConfidence.UNKNOWN

    coordinator.refresh_state.return_value = False
    stale = await EffectDeploymentEngine(repository, cache).async_reconcile(
        coordinator,
        config_entry_id="entry-a",
        observed_at="2026-08-11T00:01:00Z",
    )

    assert stale.native_mode == native_mode
    assert stale.confidence is ObservationConfidence.UNKNOWN


async def test_unreadable_device_is_uncertain_not_confirmed(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _coordinator(readable=False)

    result = await EffectDeploymentEngine(repository, cache).async_apply_saved(
        coordinator,
        _item(),
        config_entry_id="entry-a",
        updated_at="2026-08-11T00:00:00Z",
    )

    assert result.phase is DeploymentPhase.UNCERTAIN
    assert result.verification_confidence is ObservationConfidence.UNKNOWN
    coordinator.refresh_state.assert_not_awaited()


async def test_h6199_is_rejected_before_any_write(hass: HomeAssistant) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _coordinator()
    coordinator.model = "H6199"

    with pytest.raises(ValueError, match="not supported"):
        await EffectDeploymentEngine(repository, cache).async_apply_saved(
            coordinator,
            _item(),
            config_entry_id="entry-a",
            updated_at="2026-08-11T00:00:00Z",
        )

    coordinator.send_command.assert_not_awaited()


async def test_h6199_upload_without_selector_readback_stays_uncertain(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _coordinator()
    coordinator.model = "H6199"
    coordinator.unknown_scene_code = None
    item = _h6199_item()
    compiled = compile_h6199(item)

    result = await EffectDeploymentEngine(repository, cache).async_apply_saved(
        coordinator,
        item,
        config_entry_id="entry-a",
        updated_at="2026-08-11T00:00:00Z",
    )

    assert result.phase is DeploymentPhase.UNCERTAIN
    assert result.error_code == "device_state_unconfirmed"
    assert result.verification_confidence is ObservationConfidence.UNKNOWN
    assert coordinator.send_command.await_args_list == [
        *[call(packet) for packet in compiled.upload_packets],
        call(compiled.activation_packet),
        call(compiled.activation_packet),
    ]
    assert coordinator.refresh_state.await_count == 3


async def test_h6199_slot_readback_confirms_selection_without_claiming_content_readback(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _coordinator()
    coordinator.model = "H6199"
    coordinator.unknown_scene_code = None

    _confirm_scene_code_on_call(coordinator, 2, H6199_PALETTE_DIY_APPLY_CODE)

    result = await EffectDeploymentEngine(repository, cache).async_apply_saved(
        coordinator,
        _h6199_item(),
        config_entry_id="entry-a",
        updated_at="2026-08-11T00:00:00Z",
    )

    assert result.phase is DeploymentPhase.CONFIRMED
    assert result.error_code is None
    assert result.verification_confidence is ObservationConfidence.ACTIVATION_MATCH
    assert result.evidence_codes == ("effect_content_readback_unavailable",)
    assert cache.get("entry-a") is not None
    assert cache.get("entry-a").mode == "custom"
    assert cache.get("entry-a").diy_code == H6199_PALETTE_DIY_APPLY_CODE
    assert cache.get("entry-a").confidence is ObservationConfidence.ACTIVATION_MATCH
    assert cache.get("entry-a").matched_operation_id == result.operation_id


async def test_h6199_rejects_unsupported_variation_before_any_write(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _coordinator()
    coordinator.model = "H6199"

    with pytest.raises(ValueError, match="is not supported"):
        await EffectDeploymentEngine(repository, cache).async_apply_saved(
            coordinator,
            _h6199_item(family=8, variant=11),
            config_entry_id="entry-a",
            updated_at="2026-08-11T00:00:00Z",
        )

    coordinator.send_command.assert_not_awaited()
    coordinator.refresh_state.assert_not_awaited()


async def test_h6199_uncertain_result_emits_structured_evidence_gap(
    hass: HomeAssistant,
) -> None:
    backend = await EffectBackend.async_create(hass)
    coordinator = _coordinator()
    coordinator.model = "H6199"
    coordinator.unknown_scene_code = None

    result = await backend.engine.async_apply_saved(
        coordinator,
        _h6199_item(),
        config_entry_id="entry-a",
        updated_at="2026-08-11T00:00:00Z",
    )

    gap = backend.diagnostics.snapshot(config_entry_id="entry-a")["events"][-1]
    assert result.phase is DeploymentPhase.UNCERTAIN
    assert gap["stage"] == "evidence_gap"
    assert gap["code"] == "device_state_uncertain"
    assert gap["presentation"] == "diagnostic_only"
    assert gap["details"] == {
        "confidence": "unknown",
        "error_code": "device_state_unconfirmed",
        "progress_current": 3,
        "progress_total": 3,
    }


@pytest.mark.parametrize("model", ["H617A", "H6199"])
async def test_workshop_uses_evidenced_model_application(
    hass: HomeAssistant,
    model: str,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _coordinator()
    coordinator.model = model
    item = LibraryItem.new("Workshop", WORKSHOP_PROTOCOL_FIXTURES[0].content(model))
    compiled = compile_effect(item, model)
    workshop_code = H6199_WORKSHOP_APPLY_CODE if model == "H6199" else H617A_WORKSHOP_APPLY_CODE
    _confirm_scene_code_on_call(coordinator, 2, workshop_code)

    result = await EffectDeploymentEngine(repository, cache).async_apply_saved(
        coordinator,
        item,
        config_entry_id="entry-a",
        updated_at="2026-08-11T00:00:00Z",
    )

    assert result.phase is DeploymentPhase.CONFIRMED
    assert result.diy_code == workshop_code
    assert result.verification_confidence is ObservationConfidence.ACTIVATION_MATCH
    assert coordinator.send_command.await_args_list == [call(packet) for packet in compiled.packets]
    assert cache.get("entry-a").mode == "custom"
    assert cache.get("entry-a").diy_code == workshop_code


async def test_cross_model_workshop_is_rejected_before_any_write(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _coordinator()
    coordinator.model = "H6199"
    item = LibraryItem.new("Workshop", WORKSHOP_PROTOCOL_FIXTURES[0].content("H617A"))

    with pytest.raises(ValueError, match="targets H617A"):
        await EffectDeploymentEngine(repository, cache).async_apply_saved(
            coordinator,
            item,
            config_entry_id="entry-a",
            updated_at="2026-08-11T00:00:00Z",
        )
    coordinator.send_command.assert_not_awaited()
    coordinator.send_command.assert_not_awaited()


async def test_type04_uses_evidenced_code_and_confirms_readback(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _coordinator()
    _confirm_on_call(coordinator, 2, 24)

    result = await EffectDeploymentEngine(repository, cache).async_apply_saved(
        coordinator,
        _type04_item(),
        config_entry_id="entry-a",
        updated_at="2026-08-11T00:00:00Z",
    )

    assert result.phase is DeploymentPhase.CONFIRMED
    assert result.diy_code == 24


async def test_h617a_music_profile_applies_base_then_parameters_with_mode_confidence(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _profile_coordinator("H617A")
    events: list[str] = []

    def install_music_profile_state(**values) -> None:
        events.append(f"install:{values['mode']}")
        coordinator.music_sensitivity = values["sensitivity"]
        coordinator.music_color = values["colour"]
        coordinator.music_calm = values["calm"]

    async def select_music(mode: str, *, include_parameters: bool) -> None:
        events.append(f"select:{mode}:{include_parameters}")
        coordinator.music_mode = mode

    async def apply_parameters(mode_code: int) -> None:
        events.append(f"parameters:{mode_code}")

    coordinator.install_music_profile_state = install_music_profile_state
    coordinator.async_select_music_slug = select_music
    coordinator.async_apply_music_params = apply_parameters

    result = await EffectDeploymentEngine(repository, cache).async_apply_saved(
        coordinator,
        _music_item(),
        config_entry_id="entry-a",
        updated_at="2026-08-11T00:00:00Z",
    )

    assert events == ["install:separation", "select:separation:False", "parameters:50"]
    assert result.phase is DeploymentPhase.CONFIRMED
    assert result.diy_code is None
    assert result.content_kind == "music_profile"
    assert result.progress_current == result.progress_total == 2
    assert result.verification_confidence is ObservationConfidence.MODE_MATCH
    assert coordinator.refresh_state.await_args_list[-1] == call(
        expected_on=True,
        expected_music_mode="separation",
    )


async def test_h617a_music_profile_applies_style_companion_parameters(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _profile_coordinator("H617A")
    events: list[str] = []
    coordinator.install_music_profile_state = lambda **values: None

    async def select_music(mode: str, *, include_parameters: bool) -> None:
        events.append(f"select:{mode}:{include_parameters}")
        coordinator.music_mode = mode

    async def apply_parameters(mode_code: int) -> None:
        events.append(f"parameters:{mode_code}")

    coordinator.async_select_music_slug = select_music
    coordinator.async_apply_music_params = apply_parameters
    item = LibraryItem.new(
        "Bloom",
        MusicProfile("H617A", "bloom", 50, None, True, {}),
    )

    result = await EffectDeploymentEngine(repository, cache).async_apply_saved(
        coordinator,
        item,
        config_entry_id="entry-a",
        updated_at="2026-08-11T00:00:00Z",
    )

    assert events == ["select:bloom:False", "parameters:48"]
    assert result.progress_current == result.progress_total == 2
    assert result.verification_confidence is ObservationConfidence.MODE_MATCH


async def test_music_profile_rejects_parameters_not_owned_by_the_mode(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _profile_coordinator("H617A")
    item = LibraryItem.new(
        "Rhythm",
        MusicProfile("H617A", "rhythm", 50, None, False, {"point": 3}),
    )

    with pytest.raises(ValueError, match="does not support parameter point"):
        await EffectDeploymentEngine(repository, cache).async_apply_saved(
            coordinator,
            item,
            config_entry_id="entry-a",
            updated_at="2026-08-11T00:00:00Z",
        )

    assert repository.snapshot().records == ()


async def test_music_profile_rejects_a_diy_code_override(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _profile_coordinator("H617A")

    with pytest.raises(ValueError, match="profiles do not use a DIY code"):
        await EffectDeploymentEngine(repository, cache).async_apply_saved(
            coordinator,
            _music_item(),
            config_entry_id="entry-a",
            updated_at="2026-08-11T00:00:00Z",
            diy_code=24,
        )

    assert repository.snapshot().records == ()


async def test_h6199_music_profile_confirms_all_written_settings(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _profile_coordinator("H6199")
    coordinator.install_music_profile_state = lambda **values: None

    async def select_music(mode: str, *, include_parameters: bool) -> None:
        coordinator.music_mode = mode

    coordinator.async_select_music_slug = select_music
    coordinator.async_apply_music_params = AsyncMock()

    result = await EffectDeploymentEngine(repository, cache).async_apply_saved(
        coordinator,
        _music_item("H6199"),
        config_entry_id="entry-a",
        updated_at="2026-08-11T00:00:00Z",
    )

    assert result.progress_current == result.progress_total == 1
    assert result.verification_confidence is ObservationConfidence.SETTINGS_MATCH
    coordinator.async_apply_music_params.assert_not_awaited()


async def test_unsaved_music_profile_persists_the_applied_snapshot(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _profile_coordinator("H6199")
    coordinator.install_music_profile_state = lambda **values: None

    async def select_music(mode: str, *, include_parameters: bool) -> None:
        coordinator.music_mode = mode

    coordinator.async_select_music_slug = select_music
    coordinator.async_apply_music_params = AsyncMock()
    item = _music_item("H6199")
    active_workspaces = ActiveEffectWorkspaceRepository(InMemoryVersionedDocumentStore())
    await active_workspaces.async_load()
    published_workspaces = []
    coordinator.async_set_updated_data = MagicMock(
        side_effect=lambda _data: published_workspaces.append(active_workspaces.get("entry-a"))
    )
    result = await EffectDeploymentEngine(
        repository,
        cache,
        active_workspaces,
    ).async_apply_snapshot(
        coordinator,
        item,
        config_entry_id="entry-a",
        updated_at="2026-08-11T00:00:00Z",
    )

    persisted = repository.get(result.operation_id)
    assert persisted.source_kind == "snapshot"
    assert persisted.selector_label == item.name
    assert persisted.source_content_hash == item.content_hash
    assert persisted.item_id is None
    assert persisted.content_kind == "music_profile"
    workspace = active_workspaces.get("entry-a")
    assert workspace is not None
    assert workspace.selector_label == item.name
    assert workspace.content == item.content
    assert isinstance(workspace.content, MusicProfile)
    assert workspace.observable_signature == f"music:{workspace.content.mode}"
    assert workspace.confidence is ObservationConfidence.SETTINGS_MATCH
    assert published_workspaces == [workspace]


async def test_music_profile_retries_the_complete_writer_before_confirmation(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _profile_coordinator("H617A")
    events: list[str] = []

    def install_music_profile_state(**values) -> None:
        events.append("install")

    async def select_music(mode: str, *, include_parameters: bool) -> None:
        events.append("select")
        coordinator.music_mode = mode

    async def apply_parameters(mode_code: int) -> None:
        events.append("parameters")

    coordinator.install_music_profile_state = install_music_profile_state
    coordinator.async_select_music_slug = select_music
    coordinator.async_apply_music_params = apply_parameters
    coordinator.refresh_state.side_effect = [True, False, True]

    result = await EffectDeploymentEngine(repository, cache).async_apply_saved(
        coordinator,
        _music_item(),
        config_entry_id="entry-a",
        updated_at="2026-08-11T00:00:00Z",
    )

    assert result.phase is DeploymentPhase.CONFIRMED
    assert events == ["install", "select", "parameters", "install", "select", "parameters"]


async def test_h6199_video_profile_uses_native_writers_in_profile_order(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _profile_coordinator("H6199")
    events: list[str] = []
    monkeypatch.setattr(
        "custom_components.ha_govee_led_ble.effect_runtime.apply_active_video_mode",
        AsyncMock(side_effect=lambda _coordinator: events.append("video")),
    )
    monkeypatch.setattr(
        "custom_components.ha_govee_led_ble.effect_runtime.apply_white_balance",
        AsyncMock(side_effect=lambda _coordinator: events.append("white_balance")),
    )
    monkeypatch.setattr(
        "custom_components.ha_govee_led_ble.effect_runtime.apply_relative_brightness",
        AsyncMock(side_effect=lambda _coordinator: events.append("relative_brightness")),
    )
    monkeypatch.setattr(
        "custom_components.ha_govee_led_ble.effect_runtime.apply_blank_screen",
        AsyncMock(side_effect=lambda _coordinator: events.append("blank_screen")),
    )

    result = await EffectDeploymentEngine(repository, cache).async_apply_saved(
        coordinator,
        _video_item(),
        config_entry_id="entry-a",
        updated_at="2026-08-11T00:00:00Z",
    )

    assert events == ["video", "white_balance", "relative_brightness", "blank_screen"]
    assert result.phase is DeploymentPhase.CONFIRMED
    assert result.content_kind == "video_profile"
    assert result.diy_code is None
    assert result.progress_current == result.progress_total == 4
    assert result.verification_confidence is ObservationConfidence.SETTINGS_MATCH
    assert result.prior_state is not None
    assert result.prior_state.relative_brightness_left == 75


async def test_video_profile_requires_complete_prior_display_state(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _profile_coordinator("H6199")
    coordinator.blank_screen = None
    operation_id = uuid4()

    with pytest.raises(RuntimeError, match="current video settings are incomplete"):
        await EffectDeploymentEngine(repository, cache).async_apply_saved(
            coordinator,
            _video_item(),
            config_entry_id="entry-a",
            updated_at="2026-08-11T00:00:00Z",
            operation_id=operation_id,
        )

    failed = repository.get(operation_id)
    assert failed.phase is DeploymentPhase.FAILED
    assert failed.error_code == "RuntimeError"
    assert failed.prior_state is None


async def test_video_profile_failure_restores_complete_prior_state(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _profile_coordinator("H6199")
    coordinator.async_restore_effect_control_state = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "custom_components.ha_govee_led_ble.effect_runtime.apply_active_video_mode",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "custom_components.ha_govee_led_ble.effect_runtime.apply_white_balance",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "custom_components.ha_govee_led_ble.effect_runtime.apply_relative_brightness",
        AsyncMock(side_effect=RuntimeError("write failed")),
    )
    operation_id = uuid4()

    with pytest.raises(RuntimeError, match="write failed"):
        await EffectDeploymentEngine(repository, cache).async_apply_saved(
            coordinator,
            _video_item(),
            config_entry_id="entry-a",
            updated_at="2026-08-11T00:00:00Z",
            operation_id=operation_id,
        )

    failed = repository.get(operation_id)
    assert failed.phase is DeploymentPhase.FAILED
    assert failed.progress_current == 2
    coordinator.async_restore_effect_control_state.assert_awaited_once()
    assert coordinator.async_restore_effect_control_state.await_args.kwargs == {"overwritten_diy_code": None}
