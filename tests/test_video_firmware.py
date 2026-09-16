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


@pytest.fixture(autouse=True)
def synthetic_firmware_policy(monkeypatch):
    """These tests isolate synthetic conditions; exact H6199 gates have their own suite."""
    monkeypatch.setitem(MODEL_PROFILES, "H6199", replace(MODEL_PROFILES["H6199"], video_revision_policy=None))


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


@pytest.mark.parametrize("change_at", ["begin", "transport_lock", "transform"])
async def test_preview_rechecks_firmware_at_physical_write(hass, monkeypatch, change_at):
    import asyncio

    from tests.test_effect_preview import _manager, _open

    gated(monkeypatch)
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H7000", configuration_url="test")
    coordinator.subordinate_21_version = "9.08.07"
    coordinator.is_on = True
    before = coordinator.capture_effect_control_state()
    write = AsyncMock()
    coordinator._client = MagicMock(is_connected=True, write_gatt_char=write)
    monkeypatch.setattr(coordinator, "async_preview_preflight", AsyncMock())
    manager, _ = await _manager(hass, monkeypatch, coordinator)
    owner = object()
    statuses = []
    session = _open(manager, owner, statuses)
    begin = manager._async_begin_transmission
    reached = asyncio.Event()

    async def delayed_begin(request):
        await begin(request)
        if change_at == "begin":
            await asyncio.sleep(0)
            coordinator.subordinate_21_version = "9.08.06"
        reached.set()

    monkeypatch.setattr(manager, "_async_begin_transmission", delayed_begin)
    if change_at == "transport_lock":
        await coordinator._lock.acquire()
    if change_at == "transform":

        def transform(packet):
            coordinator.subordinate_21_version = "9.08.06"
            return packet

        coordinator.profile = replace(coordinator.profile, outbound_transform=transform)
    content = VideoProfile("H7000", "movie", None, None, None, None, None, None, None, white_balance_value=1)
    try:
        await manager.async_queue_snapshot(
            session_id=session,
            owner=owner,
            config_entry_id="entry-a",
            sequence=1,
            updated_at="2026-09-14T00:00:00Z",
            item=LibraryItem.new("Gated preview", content),
        )
        await asyncio.wait_for(reached.wait(), timeout=1)
        if change_at == "transport_lock":
            coordinator.subordinate_21_version = "9.08.06"
            coordinator._lock.release()
        await manager.async_wait_idle("entry-a")
        write.assert_not_awaited()
        assert not coordinator._expected_state
        assert statuses[-1].phase is PreviewPhase.FAILED
        assert coordinator.capture_effect_control_state() == before
    finally:
        if coordinator._lock.locked():
            coordinator._lock.release()
        await manager.async_shutdown()


@pytest.mark.parametrize("change_at", ["begin", "transport_lock", "transform", "unchanged"])
async def test_preview_forwards_retained_field_guard_to_physical_write(hass, monkeypatch, change_at):
    import asyncio

    from tests.test_effect_preview import _manager, _open

    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url="test")
    coordinator.profile = replace(
        coordinator.profile,
        video_firmware_conditions=(VideoFirmwareCondition("saturation", "subordinate_21_version", "9.08.07"),),
    )
    coordinator.is_on = True
    coordinator.video_saturation = 31
    physical = AsyncMock()
    coordinator._client = MagicMock(is_connected=True, write_gatt_char=physical)
    monkeypatch.setattr(coordinator, "async_preview_preflight", AsyncMock())

    async def fresh(**kwargs):
        coordinator._field_revisions["video_saturation"] = coordinator._field_revisions.get("video_saturation", 0) + 1
        return True

    monkeypatch.setattr(coordinator, "refresh_state", fresh)
    monkeypatch.setattr(coordinator, "async_observe_effect", AsyncMock(return_value=True))
    manager, _ = await _manager(hass, monkeypatch, coordinator)
    owner = object()
    statuses = []
    session = _open(manager, owner, statuses)
    begin = manager._async_begin_transmission
    reached = asyncio.Event()

    async def delayed_begin(request):
        await begin(request)
        if change_at == "begin":
            await asyncio.sleep(0)
            coordinator.video_saturation = 50
        reached.set()

    monkeypatch.setattr(manager, "_async_begin_transmission", delayed_begin)
    if change_at == "transport_lock":
        await coordinator._lock.acquire()
    if change_at == "transform":

        def transform(packet):
            coordinator.video_saturation = 50
            return packet

        coordinator.profile = replace(coordinator.profile, outbound_transform=transform)
    content = VideoProfile("H6199", "movie", True, None, False, 50, None, None, None)
    try:
        await manager.async_queue_snapshot(
            session_id=session,
            owner=owner,
            config_entry_id="entry-a",
            sequence=1,
            updated_at="2026-09-14T00:00:00Z",
            item=LibraryItem.new("Retained preview", content),
        )
        await asyncio.wait_for(reached.wait(), timeout=1)
        if change_at == "transport_lock":
            coordinator.video_saturation = 50
            coordinator._lock.release()
        await manager.async_wait_idle("entry-a")
        if change_at == "unchanged":
            physical.assert_awaited_once()
        else:
            physical.assert_not_awaited()
            assert not coordinator._expected_state
            assert statuses[-1].phase is PreviewPhase.FAILED
    finally:
        if coordinator._lock.locked():
            coordinator._lock.release()
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


@pytest.mark.parametrize("change_at", ["unknown", "power", "connect", "retry", "verify", "transform"])
async def test_mode_applicability_rechecked_before_each_write(hass, monkeypatch, change_at):
    from bleak import BleakError

    from custom_components.ha_govee_led_ble.native_profile_controls import apply_active_video_mode

    profile = replace(
        MODEL_PROFILES["H6199"],
        video_firmware_conditions=(VideoFirmwareCondition("saturation", "subordinate_21_version", "9.08.07"),),
    )
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url="test")
    coordinator.profile = profile
    coordinator.subordinate_21_version = None if change_at == "unknown" else "9.08.07"
    coordinator.is_on = change_at != "power"
    coordinator.video_mode = "movie"
    if change_at == "transform":

        def transform(packet):
            coordinator.subordinate_21_version = "9.08.06"
            return packet

        coordinator.profile = replace(coordinator.profile, outbound_transform=transform)
    writes = []

    async def power(packet):
        writes.append(packet)
        coordinator.subordinate_21_version = "9.08.06"

    async def transmit(_uuid, packet, **kwargs):
        writes.append(packet)
        if change_at == "retry":
            coordinator.subordinate_21_version = "9.08.06"
            raise BleakError("retry")
        if change_at == "power" and packet[1] == 1:
            coordinator.subordinate_21_version = "9.08.06"

    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=transmit))

    async def connect():
        if change_at == "connect":
            coordinator.subordinate_21_version = "9.08.06"
        return client

    async def verify(**kwargs):
        coordinator.subordinate_21_version = "9.08.06"
        return False

    monkeypatch.setattr(coordinator, "send_command", power)
    monkeypatch.setattr(coordinator, "_ensure_connected", connect)
    monkeypatch.setattr(coordinator, "_disconnect_locked", AsyncMock())
    monkeypatch.setattr(coordinator, "refresh_state", verify)
    with pytest.raises(ValueError, match="saturation is (unsupported|evidence_gap)"):
        if change_at == "power":
            content = VideoProfile("H6199", "movie", True, 50, False, 50, None, None, None)
            compiled = compile_video_profile(LibraryItem.new("Complete mode", content), "H6199")
            await async_apply_compiled_profile(coordinator, compiled)
        else:
            await apply_active_video_mode(coordinator, mode="movie", requested_values={"saturation": 50})
    assert len(writes) == int(change_at in {"power", "retry", "verify"})


@pytest.mark.parametrize("during", ["supersession", "power", "retained_power", "transform", "retained"])
async def test_native_selector_without_default_guards_physical_write(hass, monkeypatch, during):
    from homeassistant.exceptions import HomeAssistantError

    from custom_components.ha_govee_led_ble.effect_backend import EffectBackend
    from custom_components.ha_govee_led_ble.light import GoveeBLELight

    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url="test")
    coordinator.profile = replace(
        coordinator.profile,
        video_firmware_conditions=(VideoFirmwareCondition("saturation", "subordinate_21_version", "9.08.07"),),
    )
    coordinator.subordinate_21_version = "9.08.06" if during == "retained" else "9.08.07"
    coordinator.is_on = during not in {"power", "retained_power"}
    coordinator.video_saturation = 31
    backend = await EffectBackend.async_create(hass)
    entity = GoveeBLELight(coordinator, config_entry_id="entry-a", effect_backend=backend)
    monkeypatch.setattr(entity, "async_write_ha_state", MagicMock())
    assert backend.template_defaults.get("entry-a", "template:video:movie") is None

    async def supersede(*args, **kwargs):
        if during not in {"retained", "retained_power"}:
            coordinator.video_saturation = 50
        if during == "supersession":
            coordinator.subordinate_21_version = "9.08.06"

    monkeypatch.setattr(backend.preview, "async_supersede_device", supersede)
    writes = []

    async def send(packet):
        writes.append(packet)
        if during in {"power", "retained_power"}:
            coordinator.video_saturation = 50
            coordinator.subordinate_21_version = "9.08.06"

    monkeypatch.setattr(coordinator, "send_command", send)
    monkeypatch.setattr(coordinator, "refresh_state", AsyncMock(return_value=True))

    async def transmit(_uuid, packet, **kwargs):
        await send(packet)

    physical = AsyncMock(side_effect=transmit)
    client = MagicMock(is_connected=True, write_gatt_char=physical)
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    if during == "transform":

        def transform(packet):
            coordinator.subordinate_21_version = "9.08.06"
            return packet

        coordinator.profile = replace(coordinator.profile, outbound_transform=transform)
    if during == "retained":
        await entity.async_turn_on(effect="Video: Movie")
        assert physical.await_count == 1
        assert coordinator.video_saturation == 31
    else:
        with pytest.raises((HomeAssistantError, ValueError)) as error:
            await entity.async_turn_on(effect="Video: Movie")
        assert any(
            message in str(error.value.__cause__ or error.value)
            for message in (
                "saturation is unsupported",
                "Retained video settings changed",
            )
        )
        assert all(packet[1] == 1 for packet in writes)


async def test_recovery_rechecks_firmware_after_transform(hass, monkeypatch):
    gated(monkeypatch)
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H7000", configuration_url="test")
    coordinator.subordinate_21_version = "9.08.07"
    coordinator.white_balance_scalar = 90
    prior = replace(
        coordinator.capture_effect_control_state(), white_balance_scalar=100, video_restore_controls=("white_balance",)
    )

    def transform(packet):
        coordinator.subordinate_21_version = "9.08.06"
        return packet

    coordinator.profile = replace(coordinator.profile, outbound_transform=transform)
    physical = AsyncMock()
    client = MagicMock(is_connected=True, write_gatt_char=physical)
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    with pytest.raises(ValueError, match="white_balance is unsupported"):
        await coordinator.async_restore_effect_control_state(prior, overwritten_diy_code=None)
    physical.assert_not_awaited()


async def test_preserved_mode_fields_do_not_request_unavailable_controls(hass, monkeypatch):
    from custom_components.ha_govee_led_ble.native_profile_controls import apply_active_video_mode

    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url="test")
    coordinator.profile = replace(
        coordinator.profile,
        video_firmware_conditions=(VideoFirmwareCondition("saturation", "subordinate_21_version", "9.08.07"),),
    )
    coordinator.video_mode = "movie"
    coordinator.is_on = True
    coordinator.video_saturation = 31
    writer = AsyncMock()
    refresh = AsyncMock(return_value=True)
    monkeypatch.setattr(coordinator, "refresh_state", refresh)
    assert await apply_active_video_mode(
        coordinator, mode="movie", requested_values={"full_screen": True}, writer=writer
    )
    writer.assert_awaited_once()
    assert coordinator.video_saturation == 31
    assert "expected_video_saturation" not in refresh.await_args.kwargs


async def test_retained_native_field_changed_during_transform_is_guarded(hass, monkeypatch):
    from custom_components.ha_govee_led_ble.native_profile_controls import apply_active_video_mode

    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url="test")
    coordinator.video_mode = "movie"
    coordinator.is_on = True
    coordinator.video_saturation = 31

    def transform(packet):
        coordinator.video_saturation = 50
        return packet

    coordinator.profile = replace(
        coordinator.profile,
        outbound_transform=transform,
        video_firmware_conditions=(VideoFirmwareCondition("saturation", "subordinate_21_version", "9.08.07"),),
    )
    physical = AsyncMock()
    monkeypatch.setattr(
        coordinator, "_ensure_connected", AsyncMock(return_value=MagicMock(is_connected=True, write_gatt_char=physical))
    )
    with pytest.raises(ValueError, match="Retained video settings changed"):
        await apply_active_video_mode(coordinator, mode="movie", requested_values={"full_screen": True}, verify=False)
    physical.assert_not_awaited()


@pytest.mark.parametrize("setting", ["white_balance", "blank_screen"])
async def test_prior_refresh_requires_only_requested_register(hass, monkeypatch, setting):
    from custom_components.ha_govee_led_ble.transport import xor_checksum

    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url="test")
    omitted = "blank_screen" if setting == "white_balance" else "white_balance"
    coordinator.profile = replace(
        coordinator.profile,
        video_firmware_conditions=(VideoFirmwareCondition(omitted, "subordinate_21_version", "9.08.07"),),
    )
    client = MagicMock(is_connected=True)
    coordinator._client = client
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    queries = []

    async def respond(**kwargs):
        queries.append(kwargs)
        bodies = ["aa0101", "aa05000100320032"]
        if kwargs.get(f"query_{setting}"):
            bodies.append("aaa90006011003011003" if setting == "white_balance" else "aaa90a0600020a007800")
        for body in bodies:
            frame = bytearray.fromhex(body)
            frame.extend(bytes(19 - len(frame)))
            frame.append(xor_checksum(frame))
            coordinator._notify_callback(None, frame)
        return True

    monkeypatch.setattr(coordinator, "_send_state_queries", respond)
    content = VideoProfile(
        "H6199",
        "movie",
        True,
        50,
        False,
        50,
        17 if setting == "white_balance" else None,
        None,
        False if setting == "blank_screen" else None,
    )
    compiled = compile_video_profile(LibraryItem.new("One register", content), "H6199")
    engine = EffectDeploymentEngine(EffectDeploymentRepository(InMemoryVersionedDocumentStore()))
    assert await engine._async_prepare_prior_state(coordinator, compiled)
    assert queries[-1][f"query_{setting}"] is True
    assert queries[-1][f"query_{omitted}"] is False
    if setting == "blank_screen":
        assert coordinator.blank_screen_low_brightness_duration_seconds == 10
        assert coordinator.blank_screen_same_tone_duration_seconds == 120


@pytest.mark.parametrize("on", [True, False])
async def test_whole_profile_guard_rejects_before_first_physical_write(hass, monkeypatch, on):
    gated(monkeypatch)
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H7000", configuration_url="test")
    coordinator.is_on = on
    coordinator.subordinate_21_version = "9.08.07"
    before = coordinator.capture_effect_control_state()

    def transform(packet):
        coordinator.subordinate_21_version = "9.08.06"
        return packet

    coordinator.profile = replace(coordinator.profile, outbound_transform=transform)
    physical = AsyncMock()
    monkeypatch.setattr(
        coordinator, "_ensure_connected", AsyncMock(return_value=MagicMock(is_connected=True, write_gatt_char=physical))
    )
    content = VideoProfile("H7000", "movie", None, None, None, None, None, None, None, white_balance_value=1)
    with pytest.raises(ValueError, match="white_balance is unsupported"):
        await async_apply_compiled_profile(
            coordinator, compile_video_profile(LibraryItem.new("Whole", content), "H7000")
        )
    physical.assert_not_awaited()
    assert not coordinator._expected_state
    assert coordinator.capture_effect_control_state() == before


@pytest.mark.parametrize("setting", ["white_balance", "relative_brightness", "blank_screen"])
async def test_rejected_register_does_not_arm_expectations(hass, monkeypatch, setting):
    from custom_components.ha_govee_led_ble import native_profile_controls as controls
    from custom_components.ha_govee_led_ble.transport import xor_checksum

    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url="test")
    coordinator.subordinate_21_version = "9.08.07"
    coordinator.white_balance_red, coordinator.white_balance_blue = 21, 5
    for zone in coordinator.profile.video_brightness_zones:
        setattr(coordinator, f"relative_brightness_{zone}", 80)
    coordinator.blank_screen = True
    coordinator.blank_screen_detection = 2
    coordinator.blank_screen_low_brightness_duration_seconds = 10
    coordinator.blank_screen_same_tone_duration_seconds = 120

    def transform(packet):
        coordinator.subordinate_21_version = "9.08.06"
        return packet

    coordinator.profile = replace(
        coordinator.profile,
        outbound_transform=transform,
        video_firmware_conditions=(VideoFirmwareCondition(setting, "subordinate_21_version", "9.08.07"),),
    )
    physical = AsyncMock()
    monkeypatch.setattr(
        coordinator, "_ensure_connected", AsyncMock(return_value=MagicMock(is_connected=True, write_gatt_char=physical))
    )
    before = coordinator.capture_effect_control_state()
    requested = {"white_balance": (25, 6), "relative_brightness": (70, 70, 70, 70), "blank_screen": False}[setting]

    async def fresh_policy(**kwargs):
        coordinator._notify_callback(None, reply(build_blank_screen(True, "H6199", 2, 10, 120)))
        return True

    if setting == "blank_screen":
        from custom_components.ha_govee_led_ble.generated_protocol_adapter import build_blank_screen

        monkeypatch.setattr(coordinator, "refresh_state", fresh_policy)
    with pytest.raises(ValueError, match="unsupported"):
        await getattr(controls, f"apply_{setting}")(coordinator, requested)
    physical.assert_not_awaited()
    assert not coordinator._expected_state
    assert coordinator.capture_effect_control_state() == before
    body = {
        "white_balance": "aaa90006011003011003",
        "relative_brightness": "aaae0104141414140000",
        "blank_screen": "aaa90a0600020a007800",
    }[setting]
    frame = bytearray.fromhex(body)
    frame.extend(bytes(19 - len(frame)))
    frame.append(xor_checksum(frame))
    coordinator._notify_callback(None, frame)
    field, value = {
        "white_balance": ("white_balance_red", 16),
        "relative_brightness": ("relative_brightness_left", 20),
        "blank_screen": ("blank_screen", False),
    }[setting]
    assert getattr(coordinator, field) == value


def test_video_artifact_hash_includes_resolved_calibration(monkeypatch):
    content = VideoProfile("H6199", "movie", True, 50, False, 50, 17, None, None)
    item = LibraryItem.new("Calibration", content)
    original = item.to_dict()
    before = compile_video_profile(item, "H6199")
    profile = MODEL_PROFILES["H6199"]
    rows = list(profile.video_white_balance_calibration)
    rows[16] = (21, 22)
    monkeypatch.setitem(MODEL_PROFILES, "H6199", replace(profile, video_white_balance_calibration=tuple(rows)))
    after = compile_video_profile(item, "H6199")
    assert before.white_balance_wire != after.white_balance_wire
    assert before.artifact_sha256 != after.artifact_sha256
    assert item.to_dict() == original


@pytest.mark.parametrize("saved", [True, False])
@pytest.mark.parametrize("on", [True, False])
@pytest.mark.parametrize("change_at", ["supersede", "transform"])
async def test_native_profile_caller_power_and_brightness_keep_whole_guard(hass, monkeypatch, saved, on, change_at):
    from homeassistant.exceptions import HomeAssistantError

    from custom_components.ha_govee_led_ble.effect_backend import EffectBackend
    from custom_components.ha_govee_led_ble.effect_template_defaults import CatalogueTemplateDefault
    from custom_components.ha_govee_led_ble.light import GoveeBLELight

    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url="test")
    coordinator.profile = replace(
        coordinator.profile,
        video_firmware_conditions=(VideoFirmwareCondition("white_balance", "subordinate_21_version", "9.08.07"),),
    )
    coordinator.subordinate_21_version = "9.08.07"
    coordinator.is_on = on
    backend = await EffectBackend.async_create(hass)
    content = VideoProfile("H6199", "movie", True, 50, False, 50, 17, None, None)
    if saved:
        await backend.library.async_create(LibraryItem.new("Guarded saved", content))
        selector = "Guarded saved"
    else:
        await backend.template_defaults.async_set(
            CatalogueTemplateDefault(
                config_entry_id="entry-a",
                model="H6199",
                template_id="template:video:movie",
                content=content,
                updated_at="2026-09-14T00:00:00Z",
            )
        )
        selector = "Video: Movie"
    entity = GoveeBLELight(coordinator, config_entry_id="entry-a", effect_backend=backend)

    async def supersede(*args, **kwargs):
        if change_at == "supersede":
            coordinator.subordinate_21_version = "9.08.06"

    monkeypatch.setattr(backend.preview, "async_supersede_device", supersede)

    def transform(packet):
        coordinator.subordinate_21_version = "9.08.06"
        return packet

    if change_at == "transform":
        coordinator.profile = replace(coordinator.profile, outbound_transform=transform)
    physical = AsyncMock()
    monkeypatch.setattr(
        coordinator, "_ensure_connected", AsyncMock(return_value=MagicMock(is_connected=True, write_gatt_char=physical))
    )
    with pytest.raises((ValueError, HomeAssistantError)):
        await entity.async_turn_on(effect=selector, brightness=100)
    physical.assert_not_awaited()
    assert not coordinator._expected_state


@pytest.mark.parametrize("route", ["preview", "compiled", "native"])
async def test_supported_omitted_setting_never_overwrites_new_notification(hass, monkeypatch, route):
    from custom_components.ha_govee_led_ble.transport import xor_checksum
    from tests.test_effect_preview import _manager, _open

    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url="test")
    coordinator.is_on = True
    coordinator.video_full_screen = True

    async def fresh(**kwargs):
        coordinator._field_revisions["video_full_screen"] = coordinator._field_revisions.get("video_full_screen", 0) + 1
        return True

    monkeypatch.setattr(coordinator, "refresh_state", fresh)

    def transform(packet):
        frame = bytearray.fromhex("aa05000000320032")
        frame.extend(bytes(19 - len(frame)))
        frame.append(xor_checksum(frame))
        coordinator._notify_callback(None, frame)
        return packet

    coordinator.profile = replace(coordinator.profile, outbound_transform=transform)
    physical = AsyncMock()
    client = MagicMock(is_connected=True, write_gatt_char=physical)
    coordinator._client = client
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    item = LibraryItem.new("Omitted", VideoProfile("H6199", "movie", None, 50, False, 50, None, None, None))
    if route == "native":
        from homeassistant.exceptions import HomeAssistantError

        from custom_components.ha_govee_led_ble.effect_backend import EffectBackend
        from custom_components.ha_govee_led_ble.light import GoveeBLELight

        backend = await EffectBackend.async_create(hass)
        monkeypatch.setattr(backend.preview, "async_supersede_device", AsyncMock())
        entity = GoveeBLELight(coordinator, config_entry_id="entry-a", effect_backend=backend)
        with pytest.raises(HomeAssistantError):
            await entity.async_turn_on(effect="Video: Movie")
    elif route == "preview":
        monkeypatch.setattr(coordinator, "async_preview_preflight", AsyncMock())
        manager, _ = await _manager(hass, monkeypatch, coordinator)
        owner = object()
        statuses = []
        session = _open(manager, owner, statuses)
        await manager.async_queue_snapshot(
            session_id=session,
            owner=owner,
            config_entry_id="entry-a",
            sequence=1,
            updated_at="2026-09-14T00:00:00Z",
            item=item,
        )
        await manager.async_wait_idle("entry-a")
        assert statuses[-1].phase is PreviewPhase.FAILED
        await manager.async_shutdown()
    else:
        with pytest.raises(ValueError, match="Retained video settings changed"):
            await async_apply_compiled_profile(coordinator, compile_video_profile(item, "H6199"), verify=False)
    physical.assert_not_awaited()
    assert coordinator.video_full_screen is False
    assert not coordinator._expected_state


@pytest.mark.parametrize("attempted", [False, True])
@pytest.mark.parametrize("saved", [False, True])
async def test_public_deployment_recovers_only_after_control_attempt(hass, monkeypatch, attempted, saved):
    from bleak import BleakError

    from custom_components.ha_govee_led_ble.transport import xor_checksum

    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url="test")
    coordinator.subordinate_21_version = "9.08.07"
    controls = []
    queries = []
    published = []
    unsubscribe = coordinator.async_add_listener(
        lambda: published.append((coordinator.active_mode, coordinator.video_mode, coordinator.video_saturation))
    )
    original_saturation = coordinator.video_saturation

    def transform(packet):
        if packet[0] == 0x33 and not attempted:
            frame = bytearray(b"\xaa\x219.08.06")
            frame.extend(bytes(19 - len(frame)))
            frame.append(xor_checksum(frame))
            coordinator._notify_callback(None, frame)
        return packet

    coordinator.profile = replace(
        coordinator.profile,
        outbound_transform=transform,
        video_firmware_conditions=(VideoFirmwareCondition("white_balance", "subordinate_21_version", "9.08.07"),),
    )

    async def transmit(_uuid, packet, **kwargs):
        if packet[0] == 0x33:
            controls.append(packet)
            raise BleakError("physical attempt may have transmitted")
        queries.append(packet)
        if packet[1] == 0xA9:
            body = "aaa90006011003011003"
        elif packet[1] == 1:
            body = "aa0101"
        else:
            body = "aa0515"
        frame = bytearray.fromhex(body)
        frame.extend(bytes(19 - len(frame)))
        frame.append(xor_checksum(frame))
        coordinator._notify_callback(None, frame)

    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=transmit))
    coordinator._client = client
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(coordinator, "_disconnect_locked", AsyncMock())
    restore = AsyncMock(wraps=coordinator.async_restore_effect_control_state)
    monkeypatch.setattr(coordinator, "async_restore_effect_control_state", restore)
    repository = EffectDeploymentRepository(InMemoryVersionedDocumentStore())
    await repository.async_load()
    item = LibraryItem.new("Guarded", VideoProfile("H6199", "movie", True, 50, False, 50, 17, None, None))
    with pytest.raises(BleakError if attempted else ValueError):
        engine = EffectDeploymentEngine(repository)
        apply = engine.async_apply_saved if saved else engine.async_apply_snapshot
        await apply(
            coordinator,
            item,
            config_entry_id="entry-a",
            updated_at="2026-09-14T00:00:00Z",
        )
    record = repository.snapshot().records[0]
    unsubscribe()
    assert queries
    assert record.prior_state is not None and record.prior_state.mode == "colour"
    if attempted:
        restore.assert_awaited_once()
        assert controls and coordinator.control_write_attempts == len(controls)
        assert record.phase is DeploymentPhase.UNCERTAIN
    else:
        restore.assert_not_awaited()
        assert not controls and coordinator.control_write_attempts == 0
        assert record.phase is DeploymentPhase.FAILED
        assert published and all(state == ("colour", "off", original_saturation) for state in published)
        assert coordinator.active_mode == "colour"
        assert coordinator.video_mode == "off"
        assert coordinator.video_saturation == original_saturation


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("change_at", ["connect", "transform", "retry", "verify", "preview", "unchanged"])
async def test_blank_screen_never_replays_superseded_policy(hass, monkeypatch, enabled, change_at):
    from bleak import BleakError

    from custom_components.ha_govee_led_ble.generated_protocol_adapter import build_blank_screen
    from custom_components.ha_govee_led_ble.native_profile_controls import apply_blank_screen

    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url="test")
    coordinator._notify_callback(None, reply(build_blank_screen(not enabled, "H6199", 2, 10, 120)))

    def observe_policy():
        coordinator._notify_callback(None, reply(build_blank_screen(not enabled, "H6199", 1, 20, 240)))

    def transform(packet):
        if change_at in {"transform", "preview"}:
            observe_policy()
        return packet

    coordinator.profile = replace(coordinator.profile, outbound_transform=transform)
    writes = []

    async def transmit(_uuid, packet, **kwargs):
        writes.append(packet)
        if change_at == "retry":
            # Conflicting enable is protected, but the policy still updates.
            observe_policy()
            raise BleakError("retry")

    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=transmit))
    coordinator._client = client

    async def connect():
        if change_at == "connect":
            observe_policy()
        return client

    async def verify(**kwargs):
        if kwargs == {"refresh_display_settings": frozenset({"blank_screen"})}:
            coordinator._notify_callback(None, reply(build_blank_screen(not enabled, "H6199", 2, 10, 120)))
            return True
        assert kwargs == {"expected_blank_screen": enabled}
        if change_at == "verify":
            observe_policy()
            return False
        coordinator._notify_callback(None, reply(build_blank_screen(enabled, "H6199", 2, 10, 120)))
        return coordinator.blank_screen == enabled

    async def preview(packet, *, write_guard=None, state_values=None, expected_values=None):
        await coordinator.async_preview_write(
            packet, before_write=write_guard, state_values=state_values, expected_values=expected_values
        )

    monkeypatch.setattr(coordinator, "_ensure_connected", connect)
    monkeypatch.setattr(coordinator, "_disconnect_locked", AsyncMock())
    monkeypatch.setattr(coordinator, "refresh_state", verify)
    if change_at == "unchanged":
        assert await apply_blank_screen(coordinator, enabled)
        assert writes == [build_blank_screen(enabled, "H6199", 2, 10, 120)]
    else:
        with pytest.raises(ValueError, match="Blank-screen policy changed"):
            await apply_blank_screen(
                coordinator, enabled, writer=preview if change_at == "preview" else None, verify=change_at != "preview"
            )
        assert len(writes) == int(change_at in {"retry", "verify"})
        assert (
            coordinator.blank_screen_detection,
            coordinator.blank_screen_low_brightness_duration_seconds,
            coordinator.blank_screen_same_tone_duration_seconds,
        ) == (1, 20, 240)
        if not writes:
            assert coordinator.blank_screen == (not enabled)
            assert not coordinator._expected_state
    assert coordinator.control_write_attempts == len(writes)


async def test_video_retry_keeps_request_and_does_not_install_rejected_companion(hass, monkeypatch):
    from custom_components.ha_govee_led_ble.generated_protocol_adapter import build_video_mode

    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url="test")
    coordinator.is_on = True
    coordinator.subordinate_21_version = "9.08.07"
    original_white = coordinator.white_balance
    writes = []
    published = []
    monkeypatch.setattr(
        coordinator,
        "async_set_updated_data",
        lambda _: published.append((coordinator.video_mode, coordinator.white_balance)),
    )

    def transform(packet):
        if len(writes) == 2:
            coordinator.subordinate_21_version = "9.08.06"
            coordinator.async_set_updated_data({})
        return packet

    coordinator.profile = replace(
        coordinator.profile,
        outbound_transform=transform,
        video_firmware_conditions=(VideoFirmwareCondition("white_balance", "subordinate_21_version", "9.08.07"),),
    )

    async def transmit(_uuid, packet, **kwargs):
        writes.append(packet)
        assert coordinator.video_mode == "movie"
        assert coordinator.white_balance == original_white
        if len(writes) == 1:
            coordinator._expected_state.clear()
            coordinator._notify_callback(None, reply(build_video_mode("game", True, 25, False, 50, "H6199")))

    async def verify(**kwargs):
        assert kwargs["expected_video_mode"] == "movie"
        assert kwargs["expected_video_saturation"] == 50
        return len(writes) == 2

    monkeypatch.setattr(coordinator, "refresh_state", verify)
    monkeypatch.setattr(
        coordinator, "_ensure_connected", AsyncMock(return_value=MagicMock(is_connected=True, write_gatt_char=transmit))
    )
    content = VideoProfile("H6199", "movie", True, 50, False, 50, 17, None, None)
    with pytest.raises(ValueError, match="white_balance is unsupported"):
        await async_apply_compiled_profile(
            coordinator, compile_video_profile(LibraryItem.new("Retry", content), "H6199")
        )
    assert writes == [build_video_mode("movie", True, 50, False, 50, "H6199")] * 2
    assert published and all(white == original_white for _, white in published)
    assert coordinator.white_balance == original_white
    assert coordinator.control_write_attempts == 2
    assert not any(field.startswith("white_balance") for field in coordinator._expected_state)
