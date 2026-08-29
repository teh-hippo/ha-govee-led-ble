"""Effect Studio deployment transactions."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock, call
from uuid import uuid4

import pytest
from homeassistant.core import HomeAssistant

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, ReadDomain, get_profile
from custom_components.ha_govee_led_ble.control_arbiter import ControlIntent, async_control_intent
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.effect_active_workspace import (
    ActiveEffectWorkspace,
    ActiveEffectWorkspaceRepository,
)
from custom_components.ha_govee_led_ble.effect_backend import EffectBackend
from custom_components.ha_govee_led_ble.effect_catalogue import (
    H6199_PALETTE_DIY_APPLY_CODE,
    WORKSHOP_PROTOCOL_FIXTURES,
)
from custom_components.ha_govee_led_ble.effect_compiler import (
    compile_application,
    compile_effect,
    compile_h617a,
    compile_h6199,
)
from custom_components.ha_govee_led_ble.effect_deployments import (
    DeploymentPhase,
    DeploymentRecord,
    EffectDeploymentRepository,
    ObservationConfidence,
    PriorControlState,
)
from custom_components.ha_govee_led_ble.effect_domain import (
    BuiltinScene,
    CatalogueRef,
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
from custom_components.ha_govee_led_ble.effect_identity import EffectDeviceCache, ObservedDeviceState
from custom_components.ha_govee_led_ble.effect_runtime import (
    EffectDeploymentEngine,
    _activation_matches,
    compiled_observation,
    observable_signature_for_compiled,
    resolve_diy_code,
)
from custom_components.ha_govee_led_ble.generated_protocol_adapter import build_h6199_video, build_power
from custom_components.ha_govee_led_ble.layered_scene_decoder import decode_catalogue_layered_scene
from custom_components.ha_govee_led_ble.scenes import SCENE_ENTRIES
from custom_components.ha_govee_led_ble.transport import WRITE_UUID, xor_checksum
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
        content_kind="h617a_single",
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


def test_scene_activation_uses_name_only_when_raw_code_is_unavailable() -> None:
    record = replace(
        _confirmed_saved_record(_item()),
        target_mode="scene",
        target_effect="forest",
        diy_code=2163,
    )
    coordinator = SimpleNamespace(
        is_on=True,
        scene_code=212,
        effect="forest",
        diy_code=None,
        unknown_scene_code=None,
    )

    assert not _activation_matches(coordinator, record)
    coordinator.scene_code = None
    assert _activation_matches(coordinator, record)


def test_scene_activation_rejects_ambiguous_code_with_a_different_label() -> None:
    legacy = next(scene for scene in SCENE_ENTRIES["H617A"] if scene.name == "Aurora")
    record = replace(
        _confirmed_saved_record(_item(), diy_code=legacy.code),
        target_mode="scene",
        target_effect="aurora",
    )
    coordinator = SimpleNamespace(
        is_on=True,
        model="H617E",
        scene_code=legacy.code,
        effect="racing game-a",
        diy_code=None,
        unknown_scene_code=None,
    )

    assert not _activation_matches(coordinator, record)
    coordinator.effect = "aurora-a"
    assert _activation_matches(coordinator, record)


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


def test_compiled_observation_uses_read_domains_and_status_grammar() -> None:
    music = compile_application(_music_item("H6199"), "H6199")
    music = replace(music, colour=None)
    expectations, confidence = compiled_observation(music)
    assert expectations == {"is_on": True, "music_mode": "rolling", "music_sensitivity": 50, "music_color": None}
    assert confidence is ObservationConfidence.SETTINGS_MATCH
    profile = replace(get_profile("H6199"), status_grammar="H617A")
    assert compiled_observation(music, profile=profile) == (
        {"is_on": True, "music_mode": "rolling"},
        ObservationConfidence.MODE_MATCH,
    )
    profile = replace(profile, read_domains=frozenset({ReadDomain.POWER}), setup_required_read_domains=frozenset())
    assert compiled_observation(music, profile=profile) == (None, ObservationConfidence.UNKNOWN)
    video = compile_application(_video_item(), "H6199")
    expectations, confidence = compiled_observation(video)
    assert expectations is not None
    assert expectations["relative_brightness"] is None
    assert expectations["relative_brightness_left"] == 20
    assert expectations["relative_brightness_bottom"] == 50
    assert confidence is ObservationConfidence.SETTINGS_MATCH
    profile = replace(
        get_profile("H6199"),
        read_domains=frozenset({ReadDomain.POWER, ReadDomain.COLOUR_MODE}),
        setup_required_read_domains=frozenset(),
    )
    expectations, _ = compiled_observation(video, profile=profile)
    assert expectations is not None
    assert not any(key.startswith(("white_balance", "relative_brightness", "blank_screen")) for key in expectations)


async def test_profile_reconciliation_never_revives_settings_from_mode_only() -> None:
    repository = EffectDeploymentRepository(InMemoryVersionedDocumentStore())
    await repository.async_load()
    record = replace(
        _confirmed_saved_record(_music_item("H6199")),
        target_mode="music",
        content_kind="music_profile",
        diy_code=None,
        target_model="H6199",
        observable_signature="music:rolling",
        verification_confidence=ObservationConfidence.SETTINGS_MATCH,
    )
    await repository.async_put(record, expected_version=None)
    coordinator = _profile_coordinator("H6199")
    engine = EffectDeploymentEngine(repository)
    for mode, expected in [("rhythm", None), ("rolling", record.operation_id)]:
        coordinator.music_mode = mode
        observed = engine.reconcile_current(
            coordinator, config_entry_id="entry-a", observed_at="2026-08-26T00:02:00Z", refreshed=True
        )
        assert observed.matched_operation_id == expected
        assert observed.confidence is (ObservationConfidence.MODE_MATCH if expected else ObservationConfidence.UNKNOWN)
    legacy = replace(record, target_model=None, observable_signature=None)
    await repository.async_put(legacy, expected_version=None)
    observed = engine.reconcile_current(
        coordinator, config_entry_id="entry-a", observed_at="2026-08-26T00:03:00Z", refreshed=True
    )
    assert observed.matched_operation_id is None


async def test_partial_observation_does_not_confirm_or_repeat_activation(hass: HomeAssistant) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _coordinator()
    coordinator.diy_code = 800
    coordinator.async_observe_effect = AsyncMock(return_value=None)
    item = _item()
    result = await EffectDeploymentEngine(repository, cache).async_apply_saved(
        coordinator,
        item,
        config_entry_id="entry-a",
        updated_at="2026-08-11T00:00:00Z",
    )
    assert result.phase is DeploymentPhase.UNCERTAIN
    assert coordinator.async_observe_effect.await_count == 2
    assert coordinator.send_command.await_args_list == [call(packet) for packet in compile_h617a(item, 800).packets]


def _coordinator(*, readable: bool = True):
    coordinator = SimpleNamespace(
        _control_lock=asyncio.Lock(),
        address="AA:BB:CC:DD:EE:FF",
        model="H617A",
        profile=get_profile("H617A")
        if readable
        else replace(get_profile("H617A"), read_domains=frozenset(), setup_required_read_domains=frozenset()),
        is_on=True,
        brightness_pct=72,
        rgb_color=(1, 2, 3),
        color_temp_kelvin=None,
        effect=None,
        scene_code=None,
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

    async def observe(expectations, *, timeout):
        refreshed = await coordinator.refresh_state()
        return refreshed and all(getattr(coordinator, field, None) == value for field, value in expectations.items())

    coordinator.async_observe_effect = AsyncMock(side_effect=observe)
    return coordinator


def _profile_coordinator(model: str):
    coordinator = _coordinator()
    coordinator.active_mode = None

    async def send_command(_packet, *, write_guard=None, state_values=None):
        if write_guard is not None:
            write_guard()
        for field, value in (state_values or {}).items():
            setattr(coordinator, field, value)

    coordinator.send_command = AsyncMock(side_effect=send_command)
    coordinator.model = model
    coordinator.profile = get_profile(model)
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
            coordinator.scene_code = scene_code
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


@pytest.mark.parametrize("advanced", [False, True])
@pytest.mark.parametrize("source", ["saved", "snapshot"])
async def test_layered_scene_uses_shared_transaction_and_identity_verification(
    hass: HomeAssistant,
    advanced,
    source,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _coordinator()
    entry = next(scene for scene in SCENE_ENTRIES["H617A"] if scene.scene_type == 2 and scene.param)
    content = decode_catalogue_layered_scene("H617A", entry)
    assert content is not None
    item = LibraryItem.new("Layered scene", content.effect if advanced else content)
    compiled = compile_effect(item, "H617A")

    async def refresh() -> bool:
        if coordinator.refresh_state.await_count >= 2:
            coordinator.effect = compiled.expected_effect
            coordinator.scene_code = compiled.diy_code
        return True

    coordinator.refresh_state.side_effect = refresh

    workspaces = ActiveEffectWorkspaceRepository(InMemoryVersionedDocumentStore())
    await workspaces.async_load()
    engine = EffectDeploymentEngine(repository, cache, workspaces)
    apply = engine.async_apply_saved if source == "saved" else engine.async_apply_snapshot
    result = await apply(
        coordinator,
        item,
        config_entry_id="entry-a",
        updated_at="2026-08-11T00:00:00Z",
    )

    assert result.phase is DeploymentPhase.CONFIRMED
    assert result.target_mode == "scene"
    assert result.target_effect == compiled.expected_effect
    assert result.verification_confidence is ObservationConfidence.ACTIVATION_MATCH
    assert result.evidence_codes == compiled.evidence_codes
    assert coordinator.send_command.await_args_list == [call(packet) for packet in compiled.packets]
    assert cache.get("entry-a").effect == compiled.expected_effect
    assert cache.get("entry-a").matched_operation_id == result.operation_id
    observed = engine.reconcile_current(
        coordinator, config_entry_id="entry-a", observed_at="2026-08-11T00:01:00Z", refreshed=True
    )
    assert observed.mode == "scene"
    assert observed.diy_code is None
    assert observed.effect == compiled.expected_effect
    assert (workspaces.get("entry-a") is not None) is (source == "snapshot")


async def test_h6125_saved_native_scene_completes_as_write_only(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _coordinator()
    coordinator.model = "H6125"
    coordinator.profile = SimpleNamespace(state_readable=True, supports_color_mode_readback=False)
    entry = next(scene for scene in SCENE_ENTRIES["H6125"] if scene.scene_type == 0)
    item = LibraryItem.new(
        "H6125 scene",
        BuiltinScene(CatalogueRef("H6125", entry.scene_id, entry.effect_id)),
    )
    compiled = compile_effect(item, "H6125")

    result = await EffectDeploymentEngine(repository, cache).async_apply_saved(
        coordinator,
        item,
        config_entry_id="entry-a",
        updated_at="2026-08-11T00:00:00Z",
    )

    assert result.phase is DeploymentPhase.CONFIRMED
    assert result.verification_confidence is ObservationConfidence.WRITE_COMPLETED
    assert coordinator.effect == compiled.expected_effect
    assert coordinator.refresh_state.await_count == 1
    assert coordinator.send_command.await_args_list == [call(packet) for packet in compiled.packets]
    assert cache.get("entry-a").confidence is ObservationConfidence.WRITE_COMPLETED


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
            coordinator.scene_code = compiled.diy_code
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


@pytest.mark.parametrize("attempted", [False, True], ids=["before-first-control", "after-one-attempt"])
async def test_video_deployment_cancellation_recovers_only_after_physical_attempt(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    attempted: bool,
) -> None:
    from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
        build_relative_brightness,
        build_white_balance,
    )
    from custom_components.ha_govee_led_ble.transport import xor_checksum
    from tests.test_video_semantics import alternate, reply

    alternate(monkeypatch)
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H7000", configuration_url="test")
    repository = EffectDeploymentRepository(InMemoryVersionedDocumentStore())
    await repository.async_load()
    engine = EffectDeploymentEngine(repository)
    operation_id = uuid4()
    reached = asyncio.Event()
    controls: list[bytes] = []
    published: list[PriorControlState] = []
    unsubscribe = coordinator.async_add_listener(lambda: published.append(coordinator.capture_effect_control_state()))
    prior_brightness = (11, 22, 33, 44, 55, 66)

    async def transmit(_uuid, packet, **kwargs):
        if packet[0] == 0x33:
            controls.append(packet)
            reached.set()
            await asyncio.Event().wait()
        elif packet[1] == 0xA9:
            coordinator._notify_callback(None, reply(build_white_balance(90, None, "H7000")))
        elif packet[1] == 0xAE:
            coordinator._notify_callback(None, reply(build_relative_brightness(11, 22, 33, 44, "H7000", 55, 66)))
        else:
            body = bytes.fromhex("aa0101" if packet[1] == 1 else "aa05000100640064")
            frame = bytearray(body + bytes(19 - len(body)))
            frame.append(xor_checksum(frame))
            coordinator._notify_callback(None, frame)

    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=transmit))
    coordinator._client = client

    async def connect():
        record = repository.get_optional(operation_id)
        if record is not None and record.prior_state is not None:
            # Prior reads must finish before cancellation can exercise the control boundary.
            published.clear()
            if not attempted:
                reached.set()
                await asyncio.Event().wait()
        return client

    monkeypatch.setattr(coordinator, "_ensure_connected", connect)
    restore = AsyncMock(return_value=False)
    monkeypatch.setattr(coordinator, "async_restore_effect_control_state", restore)
    content = VideoProfile(
        "H7000",
        "movie",
        None,
        None,
        None,
        None,
        None,
        RelativeBrightness(10, 20, 30, 40, 50, 60),
        None,
        white_balance_value=2,
    )
    task = asyncio.create_task(
        engine.async_apply_snapshot(
            coordinator,
            LibraryItem.new("Cancelled video", content),
            config_entry_id="entry-a",
            updated_at="2026-09-14T00:00:00Z",
            operation_id=operation_id,
        )
    )
    try:
        await asyncio.wait_for(reached.wait(), timeout=5)
        record = repository.get(operation_id)
        assert record.phase is DeploymentPhase.UPLOADING
        assert record.prior_state is not None
        assert record.prior_state.white_balance_scalar == 90
        assert record.prior_state.relative_brightness_strip_right == 66
        assert coordinator._control_lock.locked() and coordinator._lock.locked()
        published.append(coordinator.capture_effect_control_state())
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=5)

        interrupted = repository.get(operation_id)
        assert interrupted.error_code == "operation_cancelled"
        assert interrupted.prior_state == record.prior_state
        assert coordinator.control_write_attempts == len(controls) == int(attempted)
        assert controls == ([build_h6199_video(True, False, 100, False, 100)] if attempted else [])
        assert restore.await_count == int(attempted)
        if attempted:
            restore.assert_awaited_once_with(record.prior_state, overwritten_diy_code=None)
            assert interrupted.phase is DeploymentPhase.UNCERTAIN
        else:
            assert interrupted.phase is DeploymentPhase.FAILED
            before = replace(record.prior_state, video_restore_controls=None)
            assert coordinator.capture_effect_control_state() == before
            assert all(state == before for state in published)
            assert not coordinator._expected_state
        published.append(coordinator.capture_effect_control_state())
        assert all(state.white_balance_scalar == 90 for state in published)
        assert all(
            tuple(getattr(state, f"relative_brightness_{zone}") for zone in coordinator.profile.video_brightness_zones)
            == prior_brightness
            for state in published
        )
        assert not any(
            field.startswith(("white_balance", "relative_brightness")) for field in coordinator._expected_state
        )
        assert not coordinator._control_lock.locked()
        assert not coordinator._lock.locked()
        assert not engine._operation_locks and not engine._operation_lock_users
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        unsubscribe()


@pytest.mark.parametrize("source", ["saved", "snapshot"])
@pytest.mark.parametrize("cancelled", [False, True], ids=["connection-failure", "cancel-before-first-control"])
async def test_music_deployment_before_first_control_preserves_native_selection(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    source: str,
    cancelled: bool,
) -> None:
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url="test")
    for body in ("aa0101", "aa051303140000000000"):
        frame = bytearray(bytes.fromhex(body).ljust(19, b"\x00"))
        frame.append(xor_checksum(frame))
        coordinator._notify_callback(None, frame)
    before = coordinator.capture_effect_control_state()
    assert (before.mode, before.music_mode, before.music_sensitivity, before.music_calm, before.music_color) == (
        "music",
        "rhythm",
        20,
        False,
        None,
    )
    field_revisions = dict(coordinator._field_revisions)
    domain_revisions = dict(coordinator._domain_revisions)
    expected = dict(coordinator._expected_state)
    published: list[PriorControlState] = []
    unsubscribe = coordinator.async_add_listener(lambda: published.append(coordinator.capture_effect_control_state()))
    monkeypatch.setattr(coordinator, "refresh_state", AsyncMock(return_value=True))
    restore = AsyncMock(return_value=False)
    monkeypatch.setattr(coordinator, "async_restore_effect_control_state", restore)
    physical = AsyncMock()
    client = MagicMock(is_connected=True, write_gatt_char=physical)
    reached = asyncio.Event()
    release_user = asyncio.Event()

    async def connect():
        reached.set()
        if cancelled:
            await asyncio.Event().wait()
        raise RuntimeError("connection unavailable")

    monkeypatch.setattr(coordinator, "_ensure_connected", connect)
    repository = EffectDeploymentRepository(InMemoryVersionedDocumentStore())
    await repository.async_load()
    engine = EffectDeploymentEngine(repository)
    operation_id = uuid4()
    apply = engine.async_apply_saved if source == "saved" else engine.async_apply_snapshot
    task = asyncio.create_task(
        apply(
            coordinator,
            LibraryItem.new("Calm red", MusicProfile("H6199", "rhythm", 80, (255, 0, 0), True)),
            config_entry_id="entry-a",
            updated_at="2026-09-14T00:00:00Z",
            operation_id=operation_id,
        )
    )

    async def native_selection():
        async with async_control_intent(coordinator, ControlIntent.USER):
            await release_user.wait()
            await coordinator.async_select_music_slug("rhythm")

    user_task = None
    try:
        await asyncio.wait_for(reached.wait(), timeout=5)
        if cancelled:
            assert coordinator._control_lock.locked() and coordinator._lock.locked()
            user_task = asyncio.create_task(native_selection())
            await asyncio.sleep(0)
            assert not user_task.done()
            task.cancel()
        with pytest.raises(asyncio.CancelledError if cancelled else RuntimeError):
            await asyncio.wait_for(task, timeout=5)

        failed = repository.get(operation_id)
        assert failed.phase is DeploymentPhase.FAILED
        assert failed.verification_confidence is ObservationConfidence.UNKNOWN
        assert failed.error_code == ("operation_cancelled" if cancelled else "RuntimeError")
        assert failed.progress_current == 0
        assert failed.prior_state == before
        assert coordinator.control_write_attempts == 0
        physical.assert_not_awaited()
        restore.assert_not_awaited()
        assert coordinator.capture_effect_control_state() == before
        assert coordinator._field_revisions == field_revisions
        assert coordinator._domain_revisions == domain_revisions
        assert coordinator._expected_state == expected
        assert published and all(state == before for state in published)
        assert not coordinator._lock.locked()
        assert not engine._operation_locks and not engine._operation_lock_users

        monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
        if user_task is None:
            user_task = asyncio.create_task(native_selection())
        release_user.set()
        await asyncio.wait_for(user_task, timeout=5)
        assert physical.await_args_list == [
            call(WRITE_UUID, build_power(True, "H6199"), response=False),
            call(WRITE_UUID, bytes.fromhex("3305130314000000000000000000000000000032"), response=False),
        ]
        assert coordinator.control_write_attempts == 2
        assert not coordinator._control_lock.locked()
        restore.assert_not_awaited()
    finally:
        tasks = [task] if user_task is None else [task, user_task]
        for pending in tasks:
            pending.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        unsubscribe()


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
        content_kind="h617a_painted",
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
        content_kind="h617a_painted",
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


async def test_reconciliation_matches_scene_deployments_by_raw_selector_code(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    item = _item()
    official_codes = {scene.code for scene in SCENE_ENTRIES["H617E"]}
    legacy = next(scene for scene in SCENE_ENTRIES["H617A"] if scene.code not in official_codes)
    confirmed = replace(
        _confirmed_saved_record(item, diy_code=legacy.code),
        target_mode="scene",
        target_effect=legacy.name.casefold(),
    )
    await repository.async_put(confirmed, expected_version=None)
    active_workspaces = ActiveEffectWorkspaceRepository(InMemoryVersionedDocumentStore())
    await active_workspaces.async_load()
    active_workspaces.set(
        replace(
            _flow_workspace(),
            model="H617E",
            selector_label=item.name,
            content=BuiltinScene(CatalogueRef("H617A", legacy.scene_id, legacy.effect_id)),
            origin=item.origin,
            observable_signature=f"scene:{legacy.name.casefold()}",
        )
    )
    coordinator = _coordinator()
    coordinator.model = "H617E"
    coordinator.effect = None
    coordinator.scene_code = legacy.code

    observed = await EffectDeploymentEngine(repository, cache, active_workspaces).async_reconcile(
        coordinator,
        config_entry_id="entry-a",
        observed_at="2026-08-11T00:01:00Z",
    )

    assert observed.matched_operation_id == confirmed.operation_id
    assert observed.active_effect is not None
    assert observed.active_effect.item_id == item.id
    workspace = active_workspaces.get("entry-a")
    assert workspace is not None
    assert workspace.observable_signature == f"scene-code:{legacy.code}"


async def test_reconciliation_does_not_fall_back_to_scene_name_when_codes_differ(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    item = _item()
    legacy = next(scene for scene in SCENE_ENTRIES["H617A"] if scene.name == "Forest")
    exact = next(scene for scene in SCENE_ENTRIES["H617E"] if scene.name == "Forest")
    await repository.async_put(
        replace(
            _confirmed_saved_record(item, diy_code=legacy.code),
            target_mode="scene",
            target_effect="forest",
        ),
        expected_version=None,
    )
    coordinator = _coordinator()
    coordinator.model = "H617E"
    coordinator.effect = "forest"
    coordinator.scene_code = exact.code

    observed = await EffectDeploymentEngine(repository, cache).async_reconcile(
        coordinator,
        config_entry_id="entry-a",
        observed_at="2026-08-11T00:01:00Z",
    )

    assert observed.matched_operation_id is None
    assert observed.active_effect is None


async def test_prior_state_uses_the_confirmed_scene_identity_for_ambiguous_codes(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    item = _item()
    legacy = next(scene for scene in SCENE_ENTRIES["H617A"] if scene.name == "Aurora")
    confirmed = replace(
        _confirmed_saved_record(item, diy_code=legacy.code),
        target_mode="scene",
        target_effect="aurora",
    )
    await repository.async_put(confirmed, expected_version=None)
    cache.set(
        ObservedDeviceState(
            config_entry_id="entry-a",
            mode="scene",
            observed_at="2026-08-11T00:01:00Z",
            matched_operation_id=confirmed.operation_id,
        )
    )
    coordinator = _coordinator()
    coordinator.capture_effect_control_state = lambda: PriorControlState(
        mode="scene",
        is_on=True,
        brightness_pct=72,
        rgb_color=(1, 2, 3),
        effect="racing game-a",
        scene_code=legacy.code,
    )

    captured = EffectDeploymentEngine(repository, cache)._capture_prior_state(
        coordinator,
        config_entry_id="entry-a",
    )

    assert captured.effect == "aurora"


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
    coordinator.diy_code = 24
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
    coordinator.diy_code = 24
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


@pytest.mark.parametrize("snapshot", [False, True])
async def test_target_content_limits_reject_before_deployment(hass, effect_catalogue_targets, snapshot):
    _broad, narrow = effect_catalogue_targets
    repository, cache = await _repositories(hass)
    coordinator = _coordinator()
    coordinator.model = narrow
    coordinator.is_on = False
    engine = EffectDeploymentEngine(repository, cache)
    apply = engine.async_apply_snapshot if snapshot else engine.async_apply_saved
    item = LibraryItem.new("Unsupported", SingleEffect(0, 1, 50, ((255, 0, 0), (0, 0, 255))))
    before = repository.snapshot()
    with pytest.raises(ValueError, match="variation 1"):
        await apply(coordinator, item, config_entry_id="entry-a", updated_at="2026-08-11T00:00:00Z")
    coordinator.send_command.assert_not_awaited()
    coordinator.refresh_state.assert_not_awaited()
    assert coordinator.is_on is False
    assert repository.snapshot() == before
    assert cache.get("entry-a") is None


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


@pytest.mark.parametrize(
    "model,kind",
    [
        ("H617A", "basic"),
        ("H617E", "basic"),
        ("H6199", "palette"),
        ("H617A", "workshop"),
        ("H617E", "workshop"),
        ("H6199", "workshop"),
    ],
)
async def test_workshop_uses_evidenced_model_application(
    hass: HomeAssistant,
    model: str,
    kind: str,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _coordinator()
    coordinator.model = model
    coordinator.profile = get_profile(model)
    item = (
        _type04_item()
        if kind == "basic"
        else _h6199_item()
        if kind == "palette"
        else LibraryItem.new("Workshop", WORKSHOP_PROTOCOL_FIXTURES[0].content(model))
    )
    compiled = compile_effect(item, model, diy_code=resolve_diy_code(item, model=model))
    workshop_code = compiled.diy_code
    if kind == "basic":
        _confirm_on_call(coordinator, 2, workshop_code)
    else:
        _confirm_scene_code_on_call(coordinator, 2, workshop_code)
        coordinator.effect = "named catalogue collision"
        coordinator.unknown_scene_code = None

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
    assert cache.get("entry-a").effect is None
    assert result.target_model == model
    assert result.observable_signature == observable_signature_for_compiled(compiled)
    coordinator.async_observe_effect.assert_awaited_once_with(
        {"is_on": True, "diy_code" if kind == "basic" else "scene_code": workshop_code},
        timeout=4.0,
    )
    await repository.async_load()
    observed = EffectDeploymentEngine(repository, cache).reconcile_current(
        coordinator,
        config_entry_id="entry-a",
        observed_at="2026-08-11T00:01:00Z",
        refreshed=True,
    )
    assert observed.matched_operation_id == result.operation_id
    coordinator.scene_code = workshop_code if kind == "basic" else None
    coordinator.diy_code = None if kind == "basic" else workshop_code
    assert not _activation_matches(coordinator, result)


@pytest.mark.parametrize(
    ("target", "source", "reason"),
    [("H6199", "H617A", "targets H617A"), ("H6076", "H6076", "Workshop application is not supported")],
)
async def test_incompatible_workshop_is_rejected_before_any_write(
    hass: HomeAssistant,
    target: str,
    source: str,
    reason: str,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _coordinator()
    coordinator.model = target
    item = LibraryItem.new("Workshop", replace(WORKSHOP_PROTOCOL_FIXTURES[0].content("H617A"), model=source))

    with pytest.raises(ValueError, match=reason):
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

    result = await EffectDeploymentEngine(repository, cache).async_apply_saved(
        coordinator,
        _music_item(),
        config_entry_id="entry-a",
        updated_at="2026-08-11T00:00:00Z",
    )

    assert coordinator.music_separation_point == 5
    assert coordinator.music_separation_gradient is False
    assert coordinator.send_command.await_count == 4
    assert result.phase is DeploymentPhase.CONFIRMED
    assert result.diy_code is None
    assert result.content_kind == "music_profile"
    assert result.progress_current == result.progress_total == 2
    assert result.verification_confidence is ObservationConfidence.MODE_MATCH
    coordinator.async_observe_effect.assert_awaited_once_with(
        {"is_on": True, "music_mode": "separation"},
        timeout=4.0,
    )


async def test_h617a_music_profile_applies_style_companion_parameters(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _profile_coordinator("H617A")
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

    assert coordinator.music_calm is True
    assert coordinator.send_command.await_count == 4
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

    result = await EffectDeploymentEngine(repository, cache).async_apply_saved(
        coordinator,
        _music_item("H6199"),
        config_entry_id="entry-a",
        updated_at="2026-08-11T00:00:00Z",
    )

    assert result.progress_current == result.progress_total == 1
    assert result.verification_confidence is ObservationConfidence.SETTINGS_MATCH
    assert coordinator.send_command.await_count == 2


async def test_unsaved_music_profile_persists_the_applied_snapshot(
    hass: HomeAssistant,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _profile_coordinator("H6199")
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
    coordinator.refresh_state.side_effect = [True, False, True]

    result = await EffectDeploymentEngine(repository, cache).async_apply_saved(
        coordinator,
        _music_item(),
        config_entry_id="entry-a",
        updated_at="2026-08-11T00:00:00Z",
    )

    assert result.phase is DeploymentPhase.CONFIRMED
    packets = [call.args[0] for call in coordinator.send_command.await_args_list]
    assert len(packets) == 8 and packets[:4] == packets[4:]


async def test_h6199_video_profile_uses_native_writers_in_profile_order(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, cache = await _repositories(hass)
    coordinator = _profile_coordinator("H6199")
    initial = {
        field: value
        for field, value in vars(coordinator).items()
        if field.startswith(("video_", "white_balance_", "relative_brightness", "blank_screen"))
    }
    writers = MagicMock()
    for name in ("active_video_mode", "white_balance", "relative_brightness", "blank_screen"):
        writer = AsyncMock(return_value=True)
        writers.attach_mock(writer, name)
        monkeypatch.setattr(f"custom_components.ha_govee_led_ble.effect_runtime.apply_{name}", writer)
    coordinator.async_observe_effect = AsyncMock(return_value=True)

    result = await EffectDeploymentEngine(repository, cache).async_apply_saved(
        coordinator,
        _video_item(),
        config_entry_id="entry-a",
        updated_at="2026-08-11T00:00:00Z",
    )

    assert writers.mock_calls == [
        call.active_video_mode(
            coordinator,
            mode="movie",
            requested_values={
                "full_screen": False,
                "saturation": 63,
                "sound_effects": True,
                "sound_effects_softness": 27,
            },
            writer=ANY,
            verify=True,
        ),
        call.white_balance(coordinator, (13, 3), writer=ANY, verify=True),
        call.relative_brightness(coordinator, (20, 30, 40, 50), writer=ANY, verify=True),
        call.blank_screen(coordinator, True, writer=ANY, verify=True),
    ]
    assert {field: getattr(coordinator, field) for field in initial} == initial
    coordinator.send_command.assert_not_awaited()
    expectations, _ = compiled_observation(compile_application(_video_item(), "H6199"))
    coordinator.async_observe_effect.assert_awaited_once_with(expectations, timeout=4.0)
    assert result.phase is DeploymentPhase.CONFIRMED
    assert result.content_kind == "video_profile"
    assert result.diy_code is None
    assert result.progress_current == result.progress_total == 4
    assert result.verification_confidence is ObservationConfidence.SETTINGS_MATCH
    assert result.prior_state is not None
    assert result.prior_state.relative_brightness_left == 75


async def test_reduced_video_profile_skips_unsupported_companion_workflows(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = "H7000"
    profile = replace(
        MODEL_PROFILES["H6199"],
        name="Synthetic video device",
        supports_video_capture_region=False,
        supports_video_saturation=False,
        supports_video_sound_effects=False,
        supports_white_balance=False,
        supports_relative_brightness=False,
        supports_blank_screen=False,
    )
    monkeypatch.setitem(MODEL_PROFILES, model, profile)
    repository, cache = await _repositories(hass)
    coordinator = GoveeBLECoordinator(
        hass, "AA:BB:CC:DD:EE:FF", model, configuration_url="homeassistant://ha-govee-led-ble/editor/entry-a"
    )
    coordinator.is_on = True
    coordinator.video_saturation = 88
    coordinator.video_sound_effects_softness = 50
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(coordinator, "refresh_state", AsyncMock(return_value=True))
    monkeypatch.setattr(
        coordinator,
        "async_observe_effect",
        AsyncMock(
            side_effect=lambda values, *, timeout: all(
                getattr(coordinator, key) == value for key, value in values.items()
            )
        ),
    )
    apply_white = AsyncMock()
    apply_brightness = AsyncMock()
    apply_blank = AsyncMock()
    monkeypatch.setattr("custom_components.ha_govee_led_ble.effect_runtime.apply_white_balance", apply_white)
    monkeypatch.setattr("custom_components.ha_govee_led_ble.effect_runtime.apply_relative_brightness", apply_brightness)
    monkeypatch.setattr("custom_components.ha_govee_led_ble.effect_runtime.apply_blank_screen", apply_blank)
    item = LibraryItem.new("Movie", VideoProfile(model, "movie", None, None, None, None, None, None, None))

    result = await EffectDeploymentEngine(repository, cache).async_apply_saved(
        coordinator,
        item,
        config_entry_id="entry-a",
        updated_at="2026-08-11T00:00:00Z",
    )

    client.write_gatt_char.assert_awaited_once_with(
        WRITE_UUID, build_h6199_video(True, False, 88, False, 50), response=False
    )
    assert coordinator.video_mode == "movie"
    assert call(expected_on=True, expected_video_mode="movie") in coordinator.refresh_state.await_args_list
    coordinator.async_observe_effect.assert_awaited_once_with({"is_on": True, "video_mode": "movie"}, timeout=4.0)
    apply_white.assert_not_awaited()
    apply_brightness.assert_not_awaited()
    apply_blank.assert_not_awaited()
    assert result.phase is DeploymentPhase.CONFIRMED
    assert result.progress_current == result.progress_total == 1
    assert result.verification_confidence is ObservationConfidence.MODE_MATCH


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
