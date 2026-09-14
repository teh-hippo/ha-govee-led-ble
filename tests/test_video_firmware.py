"""Firmware conditions narrow synthetic qualified controls, never authorize a SKU."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, ReadDomain, VideoFirmwareCondition
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.effect_compiler import compile_video_profile
from custom_components.ha_govee_led_ble.effect_contracts import CapabilityState
from custom_components.ha_govee_led_ble.effect_deployments import (
    DeploymentPhase,
    EffectDeploymentRepository,
    PriorControlState,
)
from custom_components.ha_govee_led_ble.effect_diagnostics import EffectDiagnosticHistory
from custom_components.ha_govee_led_ble.effect_domain import (
    LibraryItem,
    VideoProfile,
    effect_content_from_dict,
    effect_content_to_dict,
)
from custom_components.ha_govee_led_ble.effect_identity import EffectDeviceCache
from custom_components.ha_govee_led_ble.effect_preview import EffectPreviewManager, PreviewPhase, PreviewStatus
from custom_components.ha_govee_led_ble.effect_runtime import EffectDeploymentEngine, async_apply_compiled_profile
from custom_components.ha_govee_led_ble.effect_scene_defaults import NativeSceneDefaultRepository
from custom_components.ha_govee_led_ble.effect_template_defaults import CatalogueTemplateDefaultRepository
from custom_components.ha_govee_led_ble.effect_websocket import _device_payload
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_relative_brightness,
    build_white_balance,
    build_white_balance_query,
)
from custom_components.ha_govee_led_ble.video_applicability import validate_video_request, video_control_states
from tests.storage_test_double import InMemoryVersionedDocumentStore
from tests.test_video_semantics import alternate, reply


def gated(monkeypatch: pytest.MonkeyPatch):
    base = alternate(monkeypatch)
    profile = replace(
        base,
        read_domains=base.read_domains | {ReadDomain.SUBORDINATE_20, ReadDomain.SUBORDINATE_21},
        video_firmware_conditions=(VideoFirmwareCondition("white_balance", "subordinate_21_version", "9.08.07"),),
    )
    monkeypatch.setitem(MODEL_PROFILES, "H7000", profile)
    return profile


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("9.08.07", CapabilityState.SUPPORTED),
        ("9.08.08", CapabilityState.SUPPORTED),
        ("10.00.00", CapabilityState.SUPPORTED),
        ("9.08.06", CapabilityState.UNSUPPORTED),
        (None, CapabilityState.EVIDENCE_GAP),
        ("", CapabilityState.EVIDENCE_GAP),
        ("9.8.7", CapabilityState.EVIDENCE_GAP),
        ("v9.08.07", CapabilityState.EVIDENCE_GAP),
        (True, CapabilityState.EVIDENCE_GAP),
    ],
)
def test_correct_identity_and_qualification(monkeypatch: pytest.MonkeyPatch, version, expected):
    profile = gated(monkeypatch)
    identity = SimpleNamespace(
        fw_version="99.99.99", hw_version="99.99.99", subordinate_20_version="99.99.99", subordinate_21_version=version
    )
    assert video_control_states(profile, identity)["white_balance"] is expected
    assert video_control_states(profile, identity)["relative_brightness"] is CapabilityState.SUPPORTED
    assert (
        video_control_states(replace(profile, supports_white_balance=False), identity)["white_balance"]
        is CapabilityState.UNSUPPORTED
    )
    assert (
        video_control_states(MODEL_PROFILES["H6199"], SimpleNamespace())["white_balance"] is CapabilityState.SUPPORTED
    )
    assert "H6099" not in MODEL_PROFILES


async def test_admission_recheck_omission_and_recovery(hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch):
    gated(monkeypatch)
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H7000", configuration_url="test")
    content = VideoProfile("H7000", "movie", None, None, None, None, None, None, None, white_balance_value=1)
    item = LibraryItem.new("Gated", content)
    raw = effect_content_to_dict(content)
    assert effect_content_from_dict(raw) == content
    assert LibraryItem.new("Gated", effect_content_from_dict(raw)).content_hash == item.content_hash
    compiled = compile_video_profile(item, coordinator.model)
    writer = AsyncMock()
    with pytest.raises(ValueError, match="white_balance is evidence_gap"):
        validate_video_request(coordinator, content)
    repository = EffectDeploymentRepository(InMemoryVersionedDocumentStore())
    await repository.async_load()
    engine = EffectDeploymentEngine(repository)
    with pytest.raises(ValueError, match="white_balance is evidence_gap"):
        await engine.async_apply_snapshot(
            coordinator, item, config_entry_id="entry-a", updated_at="2026-09-14T00:00:00Z"
        )
    assert not repository.snapshot().records
    coordinator.subordinate_21_version = "9.08.07"
    validate_video_request(coordinator, content)
    coordinator.subordinate_21_version = "9.08.06"
    before = coordinator.capture_effect_control_state()
    with pytest.raises(ValueError, match="white_balance is unsupported"):
        await async_apply_compiled_profile(coordinator, compiled, writer=writer, verify=False)
    writer.assert_not_awaited()
    assert coordinator.capture_effect_control_state() == before
    # Omitted controls remain absent from writes even while the gate is unavailable.
    omitted = compile_video_profile(
        LibraryItem.new("Mode", replace(content, white_balance_value=None)), coordinator.model
    )
    coordinator.is_on = True
    await async_apply_compiled_profile(coordinator, omitted, writer=writer, verify=False)
    assert writer.await_count == 1
    # Recovery does not rewrite unrequested or newly unavailable registers.
    send = AsyncMock()
    monkeypatch.setattr(coordinator, "send_command", send)
    monkeypatch.setattr(coordinator, "refresh_state", AsyncMock(return_value=True))
    prior = replace(before, white_balance_scalar=100, video_restore_controls=("white_balance",))
    assert PriorControlState.from_dict(prior.to_dict()) == prior
    assert not await coordinator.async_restore_effect_control_state(prior, overwritten_diy_code=None)
    assert send.await_count == 1  # power only
    coordinator.subordinate_21_version = "9.08.07"
    send.reset_mock()
    await coordinator.async_restore_effect_control_state(
        replace(prior, video_restore_controls=()), overwritten_diy_code=None
    )
    assert send.await_count == 1
    # Identity gating is write-only: the existing query remains available.
    coordinator.subordinate_21_version = None
    assert build_white_balance_query("H7000")


async def test_live_payload_changes_with_identity_notifications(hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch):
    gated(monkeypatch)
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H7000", configuration_url="test")
    backend = MagicMock()
    backend.active_workspaces.get.return_value = None
    entry = SimpleNamespace(entry_id="entry-a", runtime_data=coordinator, title="Synthetic")
    assert _device_payload(hass, backend, entry)["video_control_states"]["white_balance"] == "evidence_gap"
    # Attributable opcode mapping, synthetic version and checksum.
    from custom_components.ha_govee_led_ble.transport import xor_checksum

    for opcode, version in ((0x20, b"99.99.99"), (0x21, b"9.08.07")):
        frame = bytearray(bytes((0xAA, opcode)) + version)
        frame.extend(bytes(19 - len(frame)))
        frame.append(xor_checksum(frame))
        coordinator._notify_callback(None, frame)
        expected = "evidence_gap" if opcode == 0x20 else "supported"
        assert _device_payload(hass, backend, entry)["video_control_states"]["white_balance"] == expected


async def test_preview_rejects_before_admission_and_rechecks_execution(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
):
    gated(monkeypatch)
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H7000", configuration_url="test")
    manager = EffectPreviewManager(
        hass,
        EffectDeviceCache(InMemoryVersionedDocumentStore()),
        NativeSceneDefaultRepository(InMemoryVersionedDocumentStore()),
        CatalogueTemplateDefaultRepository(InMemoryVersionedDocumentStore()),
        EffectDiagnosticHistory(),
    )
    monkeypatch.setattr(manager, "_loaded_coordinator", lambda _entry: coordinator)
    owner = object()
    session = manager.open_session(owner=owner)
    statuses: list[PreviewStatus] = []
    manager.subscribe(session_id=session, owner=owner, subscription_id=object(), listener=statuses.append)
    content = VideoProfile("H7000", "movie", None, None, None, None, None, None, None, white_balance_value=1)
    item = LibraryItem.new("Gated", content)
    with pytest.raises(ValueError, match="evidence_gap"):
        await manager.async_queue_snapshot(
            session_id=session,
            owner=owner,
            config_entry_id="entry-a",
            sequence=1,
            updated_at="2026-09-14T00:00:00Z",
            item=item,
        )
    assert not manager._devices
    coordinator.subordinate_21_version = "9.08.07"
    write = AsyncMock()
    monkeypatch.setattr(coordinator, "async_preview_write", write)
    await manager.async_queue_snapshot(
        session_id=session,
        owner=owner,
        config_entry_id="entry-a",
        sequence=1,
        updated_at="2026-09-14T00:00:00Z",
        item=item,
    )
    coordinator.subordinate_21_version = None
    await manager.async_wait_idle("entry-a")
    write.assert_not_awaited()
    assert statuses[-1].phase is PreviewPhase.FAILED
    await manager.async_shutdown()


async def test_stale_omitted_compound_field_rejects_without_writes(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url="test")
    content = VideoProfile("H6199", "movie", None, 50, False, 50, None, None, None)
    compiled = compile_video_profile(LibraryItem.new("Partial", content), "H6199")
    writer = AsyncMock()
    monkeypatch.setattr(coordinator, "refresh_state", AsyncMock(return_value=True))
    with pytest.raises(ValueError, match="fresh readback"):
        await async_apply_compiled_profile(coordinator, compiled, writer=writer, verify=False)
    writer.assert_not_awaited()


@pytest.mark.parametrize("invalid", [None, "white_balance", [1], [{}], ["unknown"]])
def test_recovery_controls_reject_malformed_data(invalid):
    prior = PriorControlState("colour", False, 50, (1, 2, 3))
    raw = prior.to_dict()
    assert "video_restore_controls" not in raw
    assert PriorControlState.from_dict(raw).to_dict() == raw
    raw["video_restore_controls"] = invalid
    from custom_components.ha_govee_led_ble.effect_storage import EffectStorageError

    with pytest.raises(EffectStorageError, match="restoration controls"):
        PriorControlState.from_dict(raw)


async def test_synthetic_deployment_uses_real_ble_parser_and_writer(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
):
    from custom_components.ha_govee_led_ble.effect_domain import RelativeBrightness
    from custom_components.ha_govee_led_ble.transport import xor_checksum

    gated(monkeypatch)
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H7000", configuration_url="test")
    coordinator.subordinate_21_version = "9.08.07"
    state = {"white": 90, "brightness": (11, 22, 33, 44, 55, 66)}
    writes: list[bytes] = []

    async def transmit(_uuid, packet, **kwargs):
        writes.append(packet)
        if packet[0] == 0x33:
            if packet[1] == 0xA9:
                state["white"] = packet[4]
            elif packet[1] == 0xAE:
                state["brightness"] = tuple(packet[4:10])
            return
        if packet[1] == 0xA9:
            frame = reply(build_white_balance(state["white"], None, "H7000"))
        elif packet[1] == 0xAE:
            values = state["brightness"]
            frame = reply(
                build_relative_brightness(values[0], values[1], values[2], values[3], "H7000", values[4], values[5])
            )
        else:
            body = bytes.fromhex("aa0101") if packet[1] == 1 else bytes.fromhex("aa05000100640064")
            frame = bytearray(body + bytes(19 - len(body)))
            frame.append(xor_checksum(frame))
        coordinator._notify_callback(None, frame)

    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=transmit))
    coordinator._client = client
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    repository = EffectDeploymentRepository(InMemoryVersionedDocumentStore())
    await repository.async_load()
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
    result = await EffectDeploymentEngine(repository).async_apply_snapshot(
        coordinator, LibraryItem.new("Synthetic", content), config_entry_id="entry-a", updated_at="2026-09-14T00:00:00Z"
    )
    assert result.phase is DeploymentPhase.CONFIRMED
    assert result.prior_state is not None and result.prior_state.white_balance_scalar == 90
    assert result.prior_state.relative_brightness_strip_right == 66
    assert result.prior_state.video_restore_controls == ("relative_brightness", "white_balance")
    assert build_white_balance(110, None, "H7000") in writes
    assert build_relative_brightness(10, 20, 30, 40, "H7000", 50, 60) in writes


async def test_display_refresh_cannot_reuse_stale_sibling_fields(hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch):
    from custom_components.ha_govee_led_ble.transport import xor_checksum

    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url="test")
    coordinator.white_balance_red, coordinator.white_balance_blue = 16, 3
    coordinator.blank_screen = False
    coordinator.blank_screen_detection = 2
    coordinator.blank_screen_low_brightness_duration_seconds = 10
    coordinator.blank_screen_same_tone_duration_seconds = 120
    client = MagicMock(is_connected=True)
    coordinator._client = client
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))

    async def only_white(**kwargs):
        frame = bytearray.fromhex("aaa90006011003011003000000000000000000")
        frame.append(xor_checksum(frame))
        coordinator._notify_callback(None, frame)
        return True

    monkeypatch.setattr(coordinator, "_send_state_queries", only_white)
    assert not await coordinator.refresh_state(
        refresh_display_settings=True, timeout=0.001, required_domains=frozenset()
    )
