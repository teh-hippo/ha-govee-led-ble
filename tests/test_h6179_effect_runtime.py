"""H6179 DIY deployment policy, ordering and recovery."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from homeassistant.core import HomeAssistant

from custom_components.ha_govee_led_ble.effect_active_workspace import ActiveEffectWorkspaceRepository
from custom_components.ha_govee_led_ble.effect_application import EffectStudioApplication
from custom_components.ha_govee_led_ble.effect_compiler import (
    CompiledEffect,
    CompiledMusicProfile,
    UploadTransport,
    compile_application,
)
from custom_components.ha_govee_led_ble.effect_deployments import (
    DeploymentPhase,
    DeploymentRecord,
    EffectDeploymentRepository,
    ObservationConfidence,
)
from custom_components.ha_govee_led_ble.effect_domain import (
    EffectPair,
    H6179MixedDiyEffect,
    H6179SingleDiyEffect,
    LibraryItem,
    MusicProfile,
    PaletteDiyEffect,
    SingleEffect,
)
from custom_components.ha_govee_led_ble.effect_identity import EffectDeviceCache
from custom_components.ha_govee_led_ble.effect_runtime import (
    EffectDeploymentEngine,
    H6179ActivationEvidenceError,
)
from custom_components.ha_govee_led_ble.effect_storage import EffectLibraryRepository
from custom_components.ha_govee_led_ble.effect_user_state import EffectUserStateRepository
from tests.storage_test_double import InMemoryVersionedDocumentStore

DIY_CODE = 0x1234
RED = (255, 0, 0)
BLUE = (0, 0, 255)


def _item(*, mixed: bool = False) -> LibraryItem:
    content = (
        H6179MixedDiyEffect(
            "H6179",
            (EffectPair(0, 0), EffectPair(2, 0)),
            50,
            (RED, BLUE),
        )
        if mixed
        else H6179SingleDiyEffect("H6179", 0, 0, 50, (RED,))
    )
    return LibraryItem.new("Disposable DIY", content)


def _coordinator(*, model: str = "H6179", diy_code: int | None = DIY_CODE) -> SimpleNamespace:
    coordinator = SimpleNamespace(
        _control_lock=asyncio.Lock(),
        address="AA:BB:CC:DD:EE:79",
        model=model,
        profile=SimpleNamespace(state_readable=False),
        active_mode="custom" if diy_code is not None else "colour",
        is_on=True,
        brightness_pct=72,
        rgb_color=(1, 2, 3),
        color_temp_kelvin=None,
        effect=None,
        unknown_scene_code=None,
        diy_code=diy_code,
        music_mode="off",
        video_mode="off",
        music_sensitivity=50,
        music_calm=False,
        music_color=None,
        writes=[],
        data={},
        async_set_updated_data=MagicMock(),
        send_command=AsyncMock(),
        async_restore_effect_control_state=AsyncMock(return_value=True),
    )

    async def write_effect_sequence(
        packets,
        *,
        intent,
        before_write=None,
        attempt_started=None,
        progress=None,
        operation_id=None,
    ) -> None:
        del operation_id
        if attempt_started is not None:
            await attempt_started(1)
        if before_write is not None:
            await before_write()
        for index, packet in enumerate(packets, start=1):
            coordinator.writes.append(packet)
            if progress is not None:
                await progress(index)

    async def write_once(packet: bytes) -> None:
        coordinator.writes.append(packet)

    coordinator.async_write_effect_sequence = AsyncMock(side_effect=write_effect_sequence)
    coordinator.async_preview_write = AsyncMock(side_effect=write_once)
    coordinator.async_refresh_status_domains = AsyncMock(return_value=True)
    coordinator.refresh_state = AsyncMock(return_value=False)
    return coordinator


async def _repository(hass: HomeAssistant) -> EffectDeploymentRepository:
    repository = EffectDeploymentRepository(hass)
    await repository.async_load()
    return repository


@pytest.mark.parametrize(
    ("requested", "observed", "message"),
    [
        (None, DIY_CODE, "explicitly approved disposable DIY code"),
        (DIY_CODE, None, "no disposable DIY code is currently observed"),
        (0x5678, DIY_CODE, "is not the currently observed disposable code"),
    ],
)
async def test_h6179_missing_or_unmatched_approval_blocks_before_ble(
    hass: HomeAssistant,
    requested: int | None,
    observed: int | None,
    message: str,
) -> None:
    coordinator = _coordinator(diy_code=observed)
    repository = await _repository(hass)

    with pytest.raises(H6179ActivationEvidenceError, match=message):
        await EffectDeploymentEngine(repository).async_apply_snapshot(
            coordinator,
            _item(),
            config_entry_id="entry-a",
            updated_at="2026-09-03T00:00:00Z",
            diy_code=requested,
        )

    coordinator.async_write_effect_sequence.assert_not_awaited()
    coordinator.async_preview_write.assert_not_awaited()
    coordinator.send_command.assert_not_awaited()


async def test_h6179_approved_apply_uploads_then_selects_once_and_confirms_mode(
    hass: HomeAssistant,
) -> None:
    coordinator = _coordinator()
    repository = await _repository(hass)
    item = _item(mixed=True)
    compiled = compile_application(item, "H6179", diy_code=DIY_CODE)
    assert isinstance(compiled, CompiledEffect)

    result = await EffectDeploymentEngine(repository).async_apply_snapshot(
        coordinator,
        item,
        config_entry_id="entry-a",
        updated_at="2026-09-03T00:00:00Z",
        diy_code=DIY_CODE,
    )

    assert result.phase is DeploymentPhase.CONFIRMED
    assert result.verification_confidence is ObservationConfidence.ACTIVATION_MATCH
    assert result.upload_transport == UploadTransport.H6179_A1_02.value
    assert result.overwrite_risk is True
    assert result.activation_evidence == (
        "h6179_diy_code_observed",
        "h6179_diy_code_approved_disposable",
    )
    assert DeploymentRecord.from_dict(result.to_dict()) == result
    assert coordinator.writes == [*compiled.upload_packets, compiled.activation_packet]
    coordinator.async_write_effect_sequence.assert_awaited_once()
    assert coordinator.async_write_effect_sequence.await_args.args[0] == compiled.upload_packets
    assert coordinator.async_write_effect_sequence.await_args.kwargs["operation_id"] == str(result.operation_id)
    coordinator.async_preview_write.assert_awaited_once_with(compiled.activation_packet)
    assert coordinator.async_refresh_status_domains.await_count == 3
    coordinator.async_refresh_status_domains.assert_awaited_with(
        frozenset({"power", "mode"}),
        required_domains=frozenset({"power", "mode"}),
        timeout=2.0,
    )
    coordinator.send_command.assert_not_awaited()


async def test_h6179_fresh_mode_readback_rejects_changed_code_before_upload(
    hass: HomeAssistant,
) -> None:
    coordinator = _coordinator()
    repository = await _repository(hass)

    async def changed_code(*_args, **_kwargs) -> bool:
        coordinator.diy_code = 0x5678
        return True

    coordinator.async_refresh_status_domains.side_effect = changed_code

    with pytest.raises(H6179ActivationEvidenceError, match="not the currently observed disposable code"):
        await EffectDeploymentEngine(repository).async_apply_snapshot(
            coordinator,
            _item(),
            config_entry_id="entry-a",
            updated_at="2026-09-03T00:00:00Z",
            diy_code=DIY_CODE,
        )

    coordinator.async_write_effect_sequence.assert_not_awaited()
    coordinator.async_preview_write.assert_not_awaited()


@pytest.mark.parametrize("failed_index", range(3))
async def test_h6179_each_upload_chunk_failure_suppresses_selector_and_recovers(
    hass: HomeAssistant,
    failed_index: int,
) -> None:
    coordinator = _coordinator()
    repository = await _repository(hass)
    deployment_operation_id = uuid4()

    async def fail_sequence(
        packets,
        *,
        intent,
        before_write=None,
        attempt_started=None,
        progress=None,
        operation_id=None,
    ) -> None:
        assert operation_id == str(deployment_operation_id)
        if attempt_started is not None:
            await attempt_started(1)
        if before_write is not None:
            await before_write()
        for index, packet in enumerate(packets):
            if index == failed_index:
                raise OSError("chunk failed")
            coordinator.writes.append(packet)
            if progress is not None:
                await progress(index + 1)

    coordinator.async_write_effect_sequence.side_effect = fail_sequence

    with pytest.raises(OSError, match="chunk failed"):
        await EffectDeploymentEngine(repository).async_apply_snapshot(
            coordinator,
            _item(),
            config_entry_id="entry-a",
            updated_at="2026-09-03T00:00:00Z",
            diy_code=DIY_CODE,
            operation_id=deployment_operation_id,
        )

    failed = repository.get(deployment_operation_id)
    assert failed.phase is DeploymentPhase.FAILED
    assert coordinator.active_mode == "custom"
    assert coordinator.diy_code == DIY_CODE
    coordinator.async_preview_write.assert_not_awaited()
    assert all(packet[0] == 0xA1 for packet in coordinator.writes)
    assert coordinator.async_refresh_status_domains.await_count == 3


async def test_h6179_reconnect_restarts_upload_at_frame_zero_before_selector(
    hass: HomeAssistant,
) -> None:
    coordinator = _coordinator()
    repository = await _repository(hass)
    compiled = compile_application(_item(), "H6179", diy_code=DIY_CODE)
    assert isinstance(compiled, CompiledEffect)

    async def reconnecting_sequence(
        packets,
        *,
        intent,
        before_write=None,
        attempt_started=None,
        progress=None,
        operation_id=None,
    ) -> None:
        assert operation_id is not None
        if attempt_started is not None:
            await attempt_started(1)
        if before_write is not None:
            await before_write()
        coordinator.writes.extend(packets[:2])
        if progress is not None:
            await progress(1)
            await progress(2)
        if attempt_started is not None:
            await attempt_started(2)
        if before_write is not None:
            await before_write()
        for index, packet in enumerate(packets, start=1):
            coordinator.writes.append(packet)
            if progress is not None:
                await progress(index)

    coordinator.async_write_effect_sequence.side_effect = reconnecting_sequence

    result = await EffectDeploymentEngine(repository).async_apply_snapshot(
        coordinator,
        _item(),
        config_entry_id="entry-a",
        updated_at="2026-09-03T00:00:00Z",
        diy_code=DIY_CODE,
    )

    assert result.phase is DeploymentPhase.CONFIRMED
    assert coordinator.writes == [
        *compiled.upload_packets[:2],
        *compiled.upload_packets,
        compiled.activation_packet,
    ]
    assert coordinator.writes[-1] == compiled.activation_packet
    assert coordinator.writes.count(compiled.activation_packet) == 1
    assert coordinator.async_refresh_status_domains.await_count == 4


async def test_h6179_reconnect_revalidates_disposable_code_before_retry(
    hass: HomeAssistant,
) -> None:
    coordinator = _coordinator()
    repository = await _repository(hass)

    async def changed_retry(
        packets,
        *,
        intent,
        before_write=None,
        attempt_started=None,
        progress=None,
        operation_id=None,
    ) -> None:
        assert operation_id is not None
        assert before_write is not None
        if attempt_started is not None:
            await attempt_started(1)
        await before_write()
        coordinator.writes.append(packets[0])
        if progress is not None:
            await progress(1)
        if attempt_started is not None:
            await attempt_started(2)
        coordinator.diy_code = 0x5678
        await before_write()

    coordinator.async_write_effect_sequence.side_effect = changed_retry

    with pytest.raises(H6179ActivationEvidenceError, match="not the currently observed disposable code"):
        await EffectDeploymentEngine(repository).async_apply_snapshot(
            coordinator,
            _item(),
            config_entry_id="entry-a",
            updated_at="2026-09-03T00:00:00Z",
            diy_code=DIY_CODE,
        )

    assert coordinator.writes and all(packet[0] == 0xA1 for packet in coordinator.writes)
    coordinator.async_preview_write.assert_not_awaited()
    coordinator.async_restore_effect_control_state.assert_awaited_once()


async def test_h6179_verification_requires_fresh_power_readback(
    hass: HomeAssistant,
) -> None:
    coordinator = _coordinator()
    repository = await _repository(hass)
    refresh_count = 0

    async def refresh(domains, **_kwargs) -> bool:
        nonlocal refresh_count
        assert domains == frozenset({"power", "mode"})
        refresh_count += 1
        if refresh_count >= 3:
            coordinator.is_on = False
        return True

    coordinator.async_refresh_status_domains.side_effect = refresh

    result = await EffectDeploymentEngine(repository).async_apply_snapshot(
        coordinator,
        _item(),
        config_entry_id="entry-a",
        updated_at="2026-09-03T00:00:00Z",
        diy_code=DIY_CODE,
    )

    assert result.phase is DeploymentPhase.FAILED
    assert result.verification_confidence is ObservationConfidence.UNKNOWN
    coordinator.async_restore_effect_control_state.assert_awaited_once()


async def test_h6179_verification_mismatch_never_resends_selector(
    hass: HomeAssistant,
) -> None:
    coordinator = _coordinator()
    repository = await _repository(hass)

    async def write_once(packet: bytes) -> None:
        coordinator.writes.append(packet)
        coordinator.diy_code = None
        coordinator.active_mode = "colour"

    coordinator.async_preview_write.side_effect = write_once

    result = await EffectDeploymentEngine(repository).async_apply_snapshot(
        coordinator,
        _item(),
        config_entry_id="entry-a",
        updated_at="2026-09-03T00:00:00Z",
        diy_code=DIY_CODE,
    )

    assert result.phase is DeploymentPhase.FAILED
    coordinator.async_preview_write.assert_awaited_once()
    coordinator.async_restore_effect_control_state.assert_awaited_once()


async def test_h6179_saved_effect_round_trips_storage_and_reapplies_with_fresh_approval(
    hass: HomeAssistant,
) -> None:
    library_store = InMemoryVersionedDocumentStore()
    library = EffectLibraryRepository(library_store)
    await library.async_load()
    item = _item()
    await library.async_create(item)

    reloaded_library = EffectLibraryRepository(library_store)
    await reloaded_library.async_load()
    deployments = await _repository(hass)
    application = EffectStudioApplication(
        reloaded_library,
        deployments,
        EffectUserStateRepository(InMemoryVersionedDocumentStore()),
    )
    coordinator = _coordinator()

    result = await application.async_apply_saved_effect(
        EffectDeploymentEngine(deployments),
        coordinator,
        item_id=str(item.id),
        config_entry_id="entry-a",
        updated_at="2026-09-03T00:00:00Z",
        diy_code=DIY_CODE,
    )

    assert reloaded_library.get(item.id).content == item.content
    assert result.phase is DeploymentPhase.CONFIRMED
    coordinator.async_preview_write.assert_awaited_once()

    reapplied = await application.async_apply_saved_effect(
        EffectDeploymentEngine(deployments),
        coordinator,
        item_id=str(item.id),
        config_entry_id="entry-a",
        updated_at="2026-09-03T00:01:00Z",
        diy_code=DIY_CODE,
    )

    assert reapplied.phase is DeploymentPhase.CONFIRMED
    assert coordinator.async_preview_write.await_count == 2


@pytest.mark.parametrize("requested", [None, 0x5678])
async def test_h6179_saved_apply_rejects_missing_or_mismatched_approval_before_ble(
    hass: HomeAssistant,
    requested: int | None,
) -> None:
    library = EffectLibraryRepository(InMemoryVersionedDocumentStore())
    await library.async_load()
    item = _item()
    await library.async_create(item)
    deployments = await _repository(hass)
    application = EffectStudioApplication(
        library,
        deployments,
        EffectUserStateRepository(InMemoryVersionedDocumentStore()),
    )
    coordinator = _coordinator()

    with pytest.raises(H6179ActivationEvidenceError):
        await application.async_apply_saved_effect(
            EffectDeploymentEngine(deployments),
            coordinator,
            item_id=str(item.id),
            config_entry_id="entry-a",
            updated_at="2026-09-03T00:00:00Z",
            diy_code=requested,
        )

    coordinator.async_write_effect_sequence.assert_not_awaited()
    coordinator.async_preview_write.assert_not_awaited()
    coordinator.send_command.assert_not_awaited()


async def test_h6179_music_profile_applies_and_verifies_without_companion_write(
    hass: HomeAssistant,
) -> None:
    coordinator = _coordinator(diy_code=None)
    coordinator.profile = SimpleNamespace(
        state_readable=False,
        supports_color_mode_readback=True,
    )

    def install_music_profile_state(*, mode, sensitivity, colour, calm, parameters) -> None:
        coordinator.active_mode = "music"
        coordinator.music_mode = mode
        coordinator.music_sensitivity = sensitivity
        coordinator.music_color = colour
        coordinator.music_calm = calm
        assert parameters == {}

    coordinator.install_music_profile_state = install_music_profile_state
    coordinator.async_select_music_slug = AsyncMock()
    coordinator.async_apply_music_params = AsyncMock()
    coordinator.refresh_state = AsyncMock(return_value=True)
    item = LibraryItem.new("Music", MusicProfile("H6179", "mode_1", 50, (1, 2, 3)))
    repository = await _repository(hass)
    compiled = compile_application(item, "H6179")
    assert isinstance(compiled, CompiledMusicProfile)
    assert compiled.progress_total == 1

    result = await EffectDeploymentEngine(repository).async_apply_snapshot(
        coordinator,
        item,
        config_entry_id="entry-a",
        updated_at="2026-09-03T00:00:00Z",
    )

    assert result.phase is DeploymentPhase.CONFIRMED
    assert result.progress_current == result.progress_total == 1
    coordinator.async_select_music_slug.assert_awaited_once_with(
        "mode_1",
        include_parameters=False,
    )
    coordinator.async_apply_music_params.assert_not_awaited()
    coordinator.refresh_state.assert_awaited_once_with(
        expected_on=True,
        expected_music_mode="mode_1",
        expected_music_sensitivity=50,
        expected_music_calm=None,
        expected_music_color=(1, 2, 3),
        expected_music_auto_color=False,
    )


async def test_h6179_ordinary_command_replaces_active_workspace_observation(
    hass: HomeAssistant,
) -> None:
    repository = await _repository(hass)
    cache = EffectDeviceCache(InMemoryVersionedDocumentStore())
    workspaces = ActiveEffectWorkspaceRepository(InMemoryVersionedDocumentStore())
    await cache.async_load()
    await workspaces.async_load()
    coordinator = _coordinator()
    engine = EffectDeploymentEngine(repository, cache, workspaces)

    result = await engine.async_apply_snapshot(
        coordinator,
        _item(),
        config_entry_id="entry-a",
        updated_at="2026-09-03T00:00:00Z",
        diy_code=DIY_CODE,
    )
    assert result.phase is DeploymentPhase.CONFIRMED
    assert workspaces.get("entry-a") is not None

    coordinator.active_mode = "colour"
    coordinator.diy_code = None
    replaced = engine.reconcile_current(
        coordinator,
        config_entry_id="entry-a",
        observed_at="2026-09-03T00:01:00Z",
        refreshed=True,
    )

    assert replaced.mode == "colour"
    assert replaced.active_effect is None


async def test_h6179_content_and_other_custom_effects_fail_cross_sku_before_io(
    hass: HomeAssistant,
) -> None:
    coordinator = _coordinator(model="H617A")
    repository = await _repository(hass)

    with pytest.raises(ValueError, match="targets H6179, not H617A"):
        await EffectDeploymentEngine(repository).async_apply_snapshot(
            coordinator,
            _item(),
            config_entry_id="entry-a",
            updated_at="2026-09-03T00:00:00Z",
            diy_code=DIY_CODE,
        )

    coordinator.async_write_effect_sequence.assert_not_awaited()
    coordinator.async_preview_write.assert_not_awaited()


@pytest.mark.parametrize(
    "item",
    [
        LibraryItem.new("H617A DIY", SingleEffect(0, 0, 50, (RED,))),
        LibraryItem.new("H6199 DIY", PaletteDiyEffect("H6199", 0, 0, 50, (RED,))),
    ],
)
async def test_non_h6179_custom_effect_classes_are_rejected_on_h6179_before_io(
    hass: HomeAssistant,
    item: LibraryItem,
) -> None:
    coordinator = _coordinator()
    repository = await _repository(hass)

    with pytest.raises(ValueError):
        await EffectDeploymentEngine(repository).async_apply_snapshot(
            coordinator,
            item,
            config_entry_id="entry-a",
            updated_at="2026-09-03T00:00:00Z",
        )

    coordinator.async_write_effect_sequence.assert_not_awaited()
    coordinator.async_preview_write.assert_not_awaited()
