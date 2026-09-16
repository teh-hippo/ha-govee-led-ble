"""Capture-backed music parameter tests."""

import asyncio
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from bleak import BleakError
from homeassistant.core import CoreState

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, ModelProfile, get_profile
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode
from custom_components.ha_govee_led_ble.effect_catalogue import MODEL_EFFECT_CATALOGUES, NativeModeOption
from custom_components.ha_govee_led_ble.effect_compiler import CompatibilityState, compatibility, compile_music_profile
from custom_components.ha_govee_led_ble.effect_deployments import (
    EffectDeploymentRepository,
    ObservationConfidence,
    PriorControlState,
)
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem, MusicProfile
from custom_components.ha_govee_led_ble.effect_persistence_validation import EffectStorageError
from custom_components.ha_govee_led_ble.effect_runtime import (
    EffectDeploymentEngine,
    async_apply_compiled_profile,
    compiled_observation,
)
from custom_components.ha_govee_led_ble.effect_selector import compatible_saved_effects
from custom_components.ha_govee_led_ble.generated_protocol_adapter import MusicBody, build_brightness, build_power
from custom_components.ha_govee_led_ble.music_commands import (
    build_music_params,
    prepare_music_profile_writes,
    prepare_music_request,
)
from custom_components.ha_govee_led_ble.music_semantics import MusicParamSpec, MusicVariant, music_variant
from custom_components.ha_govee_led_ble.transport import WRITE_UUID, xor_checksum
from tests.storage_test_double import InMemoryVersionedDocumentStore

H = bytes.fromhex

_CAPTURED_BODIES = {
    (0x30, ()): "0102413007ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0a50000000000000",
    (0x30, ((27, 0x14),)): "0102413007ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0a14000000000000",
    (0x31, ((20, 0x14), (21, 0x46))): ("0102413105ff0000ff7f00ffff0000ff000000ff14460a0000000000000000000000"),
    (0x32, ((20, 0x05),)): "0102413205ff7f00ff0000ffff000000ff00ff0005015e0000000000000000000000",
    (0x33, ((29, 0),)): (
        "0103413307ff0000ff7f00ffff0000ff000000ff00ffff8b00ffff000000620103020600000000000000000000000000000000"
    ),
    (0x34, ()): "0102413407ff0000ff7f00ffff0000ff000000ff00ffff8b00ff000f0a0407000000",
    (0x35, ((26, 1), (28, 3))): ("0102413507ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0101035000000000"),
    (0x37, ((26, 7), (27, 0x32))): ("0102413707ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0732000000000000"),
}


def _assemble(frames: list[bytes]) -> bytes:
    for frame in frames:
        assert len(frame) == 20 and xor_checksum(frame[:19]) == frame[19]
    return b"".join(frame[2:19] for frame in frames)


@contextmanager
def _music_transport(coordinator):
    client = SimpleNamespace(is_connected=True, write_gatt_char=AsyncMock())
    sequence = coordinator.async_write_effect_sequence

    async def acknowledged_sequence(packets, *, require_upload_ack=False, upload_ack_index=None, writer=None, **kwargs):
        # This fake radio supplies successful ACKs. Correlation/negative ACK handling
        # belongs to the parent-owned transport tests, not these music state tests.
        if require_upload_ack:
            assert upload_ack_index is not None and packets[upload_ack_index][0] == 0xA3
        if writer is None:
            await sequence(packets, **kwargs)
        else:
            for index, packet in enumerate(packets):
                await writer(
                    packet,
                    state_values=kwargs["packet_state_values"][index],
                    write_guard=lambda index=index: kwargs["packet_write_guard"](index),
                )

    with (
        patch.object(coordinator, "_client", client),
        patch.object(coordinator, "_ensure_connected", new_callable=AsyncMock, return_value=client),
        patch.object(coordinator, "_disconnect_locked", new_callable=AsyncMock),
        patch.object(coordinator, "_renew_foreground_lease"),
        patch.object(coordinator, "refresh_state", new_callable=AsyncMock, return_value=False),
        patch.object(coordinator, "async_write_effect_sequence", side_effect=acknowledged_sequence),
    ):
        yield client.write_gatt_char


def _notify(coordinator, payload: bytes) -> None:
    frame = bytearray(payload.ljust(19, b"\x00"))
    frame.append(xor_checksum(frame))
    coordinator._notify_callback(None, frame)


@pytest.mark.parametrize("mode,parameters", [("rhythm", {}), ("separation", {"point": 4})])
def test_music_profile_preparation_scopes_state_to_packets(mode, parameters):
    writes = prepare_music_profile_writes("H617A", mode, 50, None, False, parameters)
    assert isinstance(writes, tuple)
    assert tuple(packet for packet, _ in writes) == prepare_music_request("H617A", mode, 50, None, False, parameters)
    assert writes[0][1] == {"is_on": True}
    selector = 1 if mode == "rhythm" else len(writes) - 1
    assert writes[selector][1] == {
        "music_mode": mode,
        "music_sensitivity": 50,
        **({"music_color": None, "music_calm": False} if mode == "rhythm" else {}),
        "video_mode": "off",
        "effect": None,
        "diy_code": None,
    }
    if mode == "rhythm":
        assert len(writes) == 2
    else:
        assert len(writes) == 4
        assert writes[1][1] == {"_music_palette": None, "_music_body": None}
        assert writes[2][1]["music_separation_point"] == 4
        assert writes[2][1]["_music_palette"][0] == mode


@pytest.mark.parametrize("fresh_notification", [False, True])
async def test_music_recovery_connection_failure_never_installs_state(hass, fresh_notification):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617A", configuration_url="test")
    state = replace(
        coordinator.capture_effect_control_state(),
        mode="music",
        is_on=True,
        music_mode="rhythm",
        music_sensitivity=50,
        music_parameters={},
    )
    before = coordinator.capture_effect_control_state()
    fields = dict(coordinator._field_revisions)
    domains = dict(coordinator._domain_revisions)
    snapshot = coordinator._pre_mode_snapshot

    async def connect():
        nonlocal before, fields, domains
        assert coordinator.capture_effect_control_state() == before
        if fresh_notification:
            _notify(coordinator, H("aa0513035801"))
            assert (coordinator.music_mode, coordinator.music_sensitivity, coordinator.music_calm) == (
                "rhythm",
                88,
                True,
            )
            before = coordinator.capture_effect_control_state()
            fields = dict(coordinator._field_revisions)
            domains = dict(coordinator._domain_revisions)
        raise BleakError("connection unavailable")

    with _music_transport(coordinator) as physical:
        coordinator._ensure_connected.side_effect = connect
        with pytest.raises(BleakError, match="connection unavailable"):
            await coordinator.async_restore_effect_control_state(state, overwritten_diy_code=None)
        assert coordinator._ensure_connected.await_count == 3
        physical.assert_not_awaited()
        coordinator.refresh_state.assert_not_awaited()
    assert coordinator.capture_effect_control_state() == before
    assert coordinator._field_revisions == fields
    assert coordinator._domain_revisions == domains
    assert coordinator._pre_mode_snapshot is snapshot
    assert coordinator.control_write_attempts == 0
    assert coordinator._expected_state == {}


@pytest.mark.parametrize("failed_index", range(5), ids=["power", "a3-first", "a3-middle", "a3-final", "selector"])
async def test_music_apply_partial_failure_installs_only_attempted_packet_state(hass, failed_index):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617A", configuration_url="test")
    coordinator.rgb_color = (10, 20, 30)
    coordinator.music_mode = "rhythm"
    coordinator.music_sensitivity = 20
    coordinator.music_calm = True
    coordinator.music_color = (1, 2, 3)
    coordinator.video_mode = "movie"
    coordinator.effect = "retained"
    coordinator.diy_code = 7
    coordinator.music_hopping_brightness = 99
    before = coordinator.capture_effect_control_state()
    snapshot = coordinator._pre_mode_snapshot
    compiled = compile_music_profile(
        LibraryItem.new("Hopping", MusicProfile("H617A", "hopping", 50, parameters={"relative_brightness": 0})),
        "H617A",
    )
    packets = prepare_music_request("H617A", "hopping", 50, None, False, compiled.parameters)
    assert len(packets) == 5
    attempted_state = {"is_on": True}
    if failed_index == 4:
        attempted_state.update(
            music_mode="hopping",
            music_sensitivity=50,
            video_mode="off",
            effect=None,
            diy_code=None,
        )
    if failed_index >= 3:
        attempted_state["music_hopping_brightness"] = 0

    async def transmit(uuid, packet, *, response):
        assert uuid == WRITE_UUID and response is False
        if packet == packets[failed_index]:
            # The physical write may reach the device even when its await fails.
            assert all(getattr(coordinator, key) == value for key, value in attempted_state.items())
            raise BleakError("write failed")

    with _music_transport(coordinator) as physical:
        physical.side_effect = transmit
        with pytest.raises(BleakError, match="write failed"):
            await async_apply_compiled_profile(coordinator, compiled)
        assert [call.args[1] for call in physical.await_args_list] == list(packets[: failed_index + 1]) * 3
    for key in (
        "is_on",
        "music_mode",
        "music_sensitivity",
        "music_calm",
        "music_color",
        "video_mode",
        "effect",
        "diy_code",
        "music_hopping_brightness",
        "music_separation_point",
        "brightness_pct",
        "rgb_color",
    ):
        assert getattr(coordinator, key) == attempted_state.get(key, getattr(before, key)), key
    assert coordinator.control_write_attempts == (failed_index + 1) * 3
    assert coordinator._field_revisions == coordinator._domain_revisions == {}
    assert coordinator._pre_mode_snapshot is snapshot
    assert "music_hopping_brightness" not in coordinator._expected_state


@pytest.mark.parametrize("operation", ["apply", "recovery"])
async def test_music_notification_during_write_survives_return(hass, operation):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617A", configuration_url="test")
    compiled = compile_music_profile(LibraryItem.new("Music", MusicProfile("H617A", "rhythm", 50)), "H617A")
    packets = prepare_music_request("H617A", "rhythm", 50, None, False, compiled.parameters)
    state = replace(
        coordinator.capture_effect_control_state(),
        mode="music",
        is_on=True,
        music_mode="rhythm",
        music_sensitivity=50,
        music_parameters=dict(compiled.parameters),
    )
    fields, domains = {}, {}

    async def transmit(_uuid, packet, *, response):
        nonlocal fields, domains
        if packet == packets[1]:
            assert coordinator.music_mode == "rhythm"
            # A reply after the stale-reply window is fresh, even before the write await returns.
            coordinator._expected_state = {key: (value, 0) for key, (value, _) in coordinator._expected_state.items()}
            await asyncio.sleep(0)
            _notify(coordinator, H("aa0513035801"))
            fields = dict(coordinator._field_revisions)
            domains = dict(coordinator._domain_revisions)

    with _music_transport(coordinator) as physical:
        physical.side_effect = transmit
        if operation == "apply":
            await async_apply_compiled_profile(coordinator, compiled)
        else:
            assert not await coordinator.async_restore_effect_control_state(state, overwritten_diy_code=None)
    assert (coordinator.music_mode, coordinator.music_sensitivity, coordinator.music_calm) == ("rhythm", 88, True)
    assert fields["music_mode"] == fields["music_sensitivity"] == 1
    assert coordinator._field_revisions == fields
    assert coordinator._domain_revisions == domains


@pytest.mark.parametrize("fail_at", [None, "power", "selector"])
async def test_music_static_snapshot_is_captured_at_selector_attempt(hass, fail_at):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617A", configuration_url="test")
    coordinator.is_on = True
    coordinator.color_mode = ParsedMode.COLOUR
    coordinator.rgb_color = (1, 2, 3)
    snapshot = coordinator._pre_mode_snapshot
    compiled = compile_music_profile(LibraryItem.new("Music", MusicProfile("H617A", "separation", 50)), "H617A")
    packets = prepare_music_request("H617A", "separation", 50, None, False, compiled.parameters)

    async def transmit(_uuid, packet, *, response):
        if packet == packets[0]:
            assert coordinator._pre_mode_snapshot is snapshot
            if fail_at == "power":
                raise RuntimeError("power failed")
            for group in range(1, 6):
                _notify(coordinator, bytes([0xAA, 0xA5, group, *([100, 10, 20, 30] * 3)]))
            assert coordinator.rgb_color == (10, 20, 30)
        if packet == packets[-1]:
            assert coordinator._pre_mode_snapshot.rgb == (10, 20, 30)
            assert coordinator.music_mode == "separation"
            if fail_at == "selector":
                raise RuntimeError("selector failed")

    with _music_transport(coordinator) as physical:
        physical.side_effect = transmit
        if fail_at:
            with pytest.raises(RuntimeError, match=f"{fail_at} failed"):
                await async_apply_compiled_profile(coordinator, compiled)
        else:
            await async_apply_compiled_profile(coordinator, compiled)
    if fail_at == "power":
        assert coordinator._pre_mode_snapshot is snapshot
    else:
        assert coordinator._pre_mode_snapshot.kind == "rgb"
        assert coordinator._pre_mode_snapshot.rgb == (10, 20, 30)


async def test_music_preview_guard_failure_does_not_install_selector_state(hass):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617A", configuration_url="test")
    compiled = compile_music_profile(LibraryItem.new("Music", MusicProfile("H617A", "separation", 50)), "H617A")
    packets = prepare_music_request("H617A", "separation", 50, None, False, compiled.parameters)
    before = coordinator.capture_effect_control_state()
    snapshot = coordinator._pre_mode_snapshot

    async def writer(packet, *, state_values=None, write_guard=None, expected_values=None):
        def check():
            if state_values and "music_mode" in state_values:
                raise ValueError("preview guard rejected selector")
            if write_guard is not None:
                write_guard()

        await coordinator.async_preview_write(packet, before_write=check, state_values=state_values)

    with _music_transport(coordinator) as physical:
        with pytest.raises(ValueError, match="preview guard rejected selector"):
            await async_apply_compiled_profile(coordinator, compiled, writer=writer)
        assert [call.args[1] for call in physical.await_args_list] == list(packets[:-1])
        coordinator._ensure_connected.assert_not_awaited()
    assert coordinator.capture_effect_control_state() == replace(before, is_on=True, mode="colour")
    assert coordinator._pre_mode_snapshot is snapshot
    assert coordinator.control_write_attempts == len(packets) - 1
    assert coordinator.music_body is None
    assert set(coordinator._expected_state) == {"is_on"}
    assert coordinator._field_revisions == coordinator._domain_revisions == {}


@pytest.mark.parametrize("phase", ["connect", "write"])
async def test_music_recovery_cancellation_respects_physical_boundary(hass, phase):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617A", configuration_url="test")
    state = replace(
        coordinator.capture_effect_control_state(),
        mode="music",
        is_on=True,
        music_mode="rhythm",
        music_sensitivity=50,
        music_parameters={},
    )
    before = coordinator.capture_effect_control_state()
    reached = asyncio.Event()

    async def suspend(*_args, **_kwargs):
        reached.set()
        await asyncio.Event().wait()

    with _music_transport(coordinator) as physical:
        if phase == "connect":
            coordinator._ensure_connected.side_effect = suspend
        else:
            physical.side_effect = suspend
        task = asyncio.create_task(coordinator.async_restore_effect_control_state(state, overwritten_diy_code=None))
        try:
            await asyncio.wait_for(reached.wait(), timeout=5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        assert physical.await_count == (phase == "write")
        coordinator.refresh_state.assert_not_awaited()
    # Recovery restores master brightness before its power/music sequence.
    expected = before
    assert coordinator.capture_effect_control_state() == expected
    assert coordinator.control_write_attempts == (phase == "write")
    assert coordinator._field_revisions == coordinator._domain_revisions == {}
    assert not coordinator._lock.locked() and not coordinator._control_lock.locked()


@pytest.mark.parametrize("operation", ["apply", "recovery"])
async def test_music_shutdown_no_write_does_not_install_state(hass, operation):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617A", configuration_url="test")
    compiled = compile_music_profile(LibraryItem.new("Music", MusicProfile("H617A", "separation", 50)), "H617A")
    before = coordinator.capture_effect_control_state()
    snapshot = coordinator._pre_mode_snapshot
    with _music_transport(coordinator) as physical, patch.object(hass, "state", CoreState.stopping):
        with pytest.raises(RuntimeError, match="Home Assistant is stopping"):
            if operation == "apply":
                await async_apply_compiled_profile(coordinator, compiled)
            else:
                state = replace(before, mode="music", is_on=True, music_mode="rhythm", music_parameters={})
                await coordinator.async_restore_effect_control_state(state, overwritten_diy_code=None)
        physical.assert_not_awaited()
        coordinator._ensure_connected.assert_not_awaited()
    assert coordinator.capture_effect_control_state() == before
    assert coordinator._pre_mode_snapshot is snapshot
    assert coordinator.control_write_attempts == 0
    assert coordinator._expected_state == coordinator._field_revisions == coordinator._domain_revisions == {}


@pytest.mark.parametrize("model", ["H617A", "H617E"])
def test_music_parameter_templates_reproduce_captured_bodies(model) -> None:
    settings = [
        ({}, False),
        ({}, True),
        ({}, True),
        ({"point": 5}, False),
        ({"relative_brightness": 0}, False),
        ({}, False),
        ({"direction": "two_way"}, False),
        ({"segment_count": 7, "speed": 50}, False),
    ]
    for ((mode, _), body), (parameters, calm) in zip(_CAPTURED_BODIES.items(), settings, strict=True):
        # Synthetic physical geometry reproduces these historical presets; logical segments are not IC evidence.
        assert _assemble(
            build_music_params(mode, parameters, profile=replace(get_profile(model), physical_ic_count=15), calm=calm)
        ) == H(body)


def test_music_parameter_overlay_changes_only_named_offsets() -> None:
    base = _assemble(build_music_params(0x31, {}, profile=get_profile("H617A")))
    changed = _assemble(build_music_params(0x31, {}, profile=get_profile("H617A"), calm=True))
    assert [index for index, values in enumerate(zip(base, changed, strict=True)) if values[0] != values[1]] == [20, 21]


def test_music_palette_count_guards_downstream_offsets() -> None:
    with pytest.raises(ValueError, match="palette count"):
        build_music_params(0x32, {}, palette=[(1, 2, 3)] * 9, profile=get_profile("H617A"))
    assembled = _assemble(build_music_params(0x32, {}, palette=[(1, 2, 3)] * 5, profile=get_profile("H617A")))
    assert assembled[5:20] == bytes([1, 2, 3] * 5)
    assert assembled[20] == 1


@pytest.fixture
def alternative(monkeypatch):
    # Synthetic software fixture only. Known KSY, two palette entries instead of five,
    # independent bounds/defaults and companion value; not device qualification.
    variant = MusicVariant(
        0x32,
        "TEST ONLY issue #286; no hardware qualification",
        "music_body",
        bytes.fromhex("320201020304050608007a00000000000000000000000000000000000000"),
        (
            MusicParamSpec("music_separation_point", "point", "point", "number", 8, 6, 12),
            MusicParamSpec("music_separation_gradient", "gradient", "gradient", "switch", False),
        ),
    )
    profile = ModelProfile(
        "Synthetic music",
        command_grammar="H617A",
        music_modes=("separation",),
        music_variants=(variant,),
        segment_count=15,
    )
    monkeypatch.setitem(MODEL_PROFILES, "TEST-MUSIC", profile)
    return profile


async def test_variant_encoding_application_and_restoration(hass, alternative):
    catalogue = replace(
        MODEL_EFFECT_CATALOGUES["H617A"], sku="TEST-MUSIC", music_modes=(NativeModeOption("separation", "Separation"),)
    )
    settings = catalogue.to_dict()["music_settings"]["separation"]
    assert settings["palette_size"] == 2
    assert settings["parameters"]["point"] == {"kind": "number", "default": 8, "min": 6, "max": 12, "options": []}
    original = build_music_params(0x32, {}, profile=get_profile("H617A"))
    item = LibraryItem.new("Synthetic", MusicProfile("TEST-MUSIC", "separation", 50))
    compiled = compile_music_profile(item, "TEST-MUSIC")
    assert compiled.parameters == {"point": 8, "gradient": False}
    packets = prepare_music_request("TEST-MUSIC", "separation", 50, None, False, compiled.parameters)
    body = MusicBody.from_bytes(_assemble(list(packets[2:])))
    body._read()
    assert body.num_palette == 2 and body.tail.point == 8 and body.tail.speed == 0x7A
    assert _assemble(list(packets[2:]))[11:14] == bytes([8, 0, 0x7A])
    with pytest.raises(ValueError, match="6 to 12"):
        build_music_params(0x32, {"point": 1}, profile=alternative)
    with pytest.raises(ValueError, match="1 to 5"):
        build_music_params(0x32, {"point": 8}, profile=get_profile("H617A"))
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "TEST-MUSIC", configuration_url="test")
    assert coordinator.music_separation_point == 8
    with _music_transport(coordinator) as send:
        await async_apply_compiled_profile(coordinator, compiled)
        assert [call.args[1] for call in send.await_args_list] == list(packets)
        state = PriorControlState.from_dict(coordinator.capture_effect_control_state().to_dict())
        omitted = state.to_dict()
        del omitted["music_separation_point"]
        assert PriorControlState.from_dict(omitted).music_separation_point == 8
        del omitted["music_model"]
        del omitted["music_body"]
        assert PriorControlState.from_dict(omitted).music_separation_point == 1
        coordinator.music_separation_point = 12
        send.reset_mock()
        assert not await coordinator.async_restore_effect_control_state(state, overwritten_diy_code=None)
        assert [call.args[1] for call in send.await_args_list] == [
            build_brightness(state.brightness_pct, coordinator.model),
            *packets,
        ]
        assert coordinator.music_separation_point == 8
    assert compiled_observation(compiled) == (None, ObservationConfidence.UNKNOWN)
    assert build_music_params(0x32, {}, profile=get_profile("H617A")) == original


async def test_invalid_recovery_fails_before_any_write(hass, alternative):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "TEST-MUSIC", configuration_url="test")
    state = PriorControlState(
        mode="music",
        is_on=True,
        brightness_pct=50,
        rgb_color=(1, 2, 3),
        music_mode="separation",
        music_sensitivity=50,
        music_separation_point=1,
    )
    with _music_transport(coordinator) as send:
        # Missing complete body fails closed before any legacy/default reconstruction.
        assert not await coordinator.async_restore_effect_control_state(state, overwritten_diy_code=None)
        send.assert_not_awaited()


async def test_restored_parameters_are_not_device_observations(hass):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617A", configuration_url="test")
    compiled = compile_music_profile(
        LibraryItem.new("Music", MusicProfile("H617A", "separation", 50, parameters={"point": 4})), "H617A"
    )
    with _music_transport(coordinator):
        await async_apply_compiled_profile(coordinator, compiled)
        state = coordinator.capture_effect_control_state()
        coordinator.music_separation_point = 1
        assert not await coordinator.async_restore_effect_control_state(state, overwritten_diy_code=None)
    assert compiled_observation(compiled) == (
        {"is_on": True, "music_mode": "separation"},
        ObservationConfidence.MODE_MATCH,
    )
    assert coordinator.music_separation_point == 4
    assert coordinator._field_revisions == coordinator._domain_revisions == {}


@pytest.mark.parametrize("unknown", ["hardware", "layout"])
async def test_unknown_semantics_never_write_or_install_state(hass, alternative, monkeypatch, unknown):
    variant = replace(
        alternative.music_variants[0],
        **({"requires_physical_ic_count": True} if unknown == "hardware" else {"layout": "unknown"}),
    )
    profile = replace(alternative, music_variants=(variant,))
    monkeypatch.setitem(MODEL_PROFILES, "TEST-MUSIC", profile)
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "TEST-MUSIC", configuration_url="test")
    with _music_transport(coordinator) as send:
        before = coordinator.capture_effect_control_state()
        with pytest.raises(ValueError):
            prepare_music_profile_writes(
                "TEST-MUSIC", mode="separation", sensitivity=40, colour=None, calm=False, parameters={"point": 8}
            )
        assert coordinator.capture_effect_control_state() == before
        send.assert_not_awaited()
        # Native mode selection needs no unknown parameter layout or physical count.
        await coordinator.async_select_music_slug("separation", include_parameters=False)
        assert send.await_count == 2
    if unknown == "hardware":
        assert profile.segment_count == 15 and profile.physical_ic_count is None
        compiled = compile_music_profile(
            LibraryItem.new("Selector", MusicProfile("TEST-MUSIC", "separation", 50)), "TEST-MUSIC"
        )
        assert compiled.parameters == {} and compiled.progress_total == 1
        known = replace(profile, physical_ic_count=20)
        assert build_music_params(0x32, {}, profile=known)


@pytest.mark.parametrize("parameters", [{"point": True}, {"gradient": 1}, {"point": 6}, {"unknown": 1}])
def test_parameter_validation_does_not_coerce(parameters):
    with pytest.raises(ValueError):
        build_music_params(0x32, parameters, profile=get_profile("H617A"))


@pytest.mark.parametrize("sensitivity,calm", [(True, False), (50, 1), (100, False)])
def test_selector_validation_does_not_coerce(sensitivity, calm):
    with pytest.raises(ValueError):
        prepare_music_request("H617A", "rhythm", sensitivity, None, calm, {})


async def test_new_fountain_parameter_survives_application_capture_and_recovery(hass, monkeypatch):
    fountain = music_variant(get_profile("H617A"), 0x35)
    assert fountain is not None
    variant = replace(
        fountain,
        evidence="TEST ONLY issue #286 Fountain speed; no new hardware qualification",
        palette_bounds=None,
        parameters=(
            replace(fountain.parameters[0], requires_physical_ic_count=False),
            MusicParamSpec("music_fountain_speed", "speed", "speed", "number", 80, 16, 80),
        ),
    )
    profile = ModelProfile(
        "Synthetic Fountain", command_grammar="H617A", music_modes=("fountain",), music_variants=(variant,)
    )
    monkeypatch.setitem(MODEL_PROFILES, "TEST-FOUNTAIN", profile)
    catalogue = replace(
        MODEL_EFFECT_CATALOGUES["H617A"], sku="TEST-FOUNTAIN", music_modes=(NativeModeOption("fountain", "Fountain"),)
    )
    assert catalogue.to_dict()["music_settings"]["fountain"]["parameters"]["speed"] == {
        "kind": "number",
        "default": 80,
        "min": 16,
        "max": 80,
        "options": [],
    }
    compiled = compile_music_profile(
        LibraryItem.new(
            "Fountain", MusicProfile("TEST-FOUNTAIN", "fountain", 50, parameters={"speed": 16, "direction": "two_way"})
        ),
        "TEST-FOUNTAIN",
    )
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "TEST-FOUNTAIN", configuration_url="test")
    with _music_transport(coordinator) as send:
        await async_apply_compiled_profile(coordinator, compiled)
        packets = [call.args[1] for call in send.await_args_list]
        body = MusicBody.from_bytes(_assemble(packets[2:]))
        body._read()
        assert body.tail.speed == 16 and body.tail.piece_num == 3
        raw = coordinator.capture_effect_control_state().to_dict()
        assert raw["music_parameters"] == {"speed": 16, "direction": "two_way"}
        # The mapping is authoritative even if the retained legacy field disagrees.
        raw["music_fountain_direction"] = "clockwise"
        state = PriorControlState.from_dict(raw)
        coordinator.music_fountain_speed = 80
        coordinator.music_fountain_direction = "clockwise"
        send.reset_mock()
        assert not await coordinator.async_restore_effect_control_state(state, overwritten_diy_code=None)
        assert [call.args[1] for call in send.await_args_list] == [
            build_brightness(state.brightness_pct, coordinator.model),
            *packets,
        ]
        assert coordinator.music_fountain_speed == 16

        # The original body governs replay even when the scalar mapping is empty.
        empty = PriorControlState.from_dict({**raw, "music_parameters": {}})
        await coordinator.async_restore_effect_control_state(empty, overwritten_diy_code=None)
        assert coordinator.music_fountain_speed == 16
        assert coordinator.music_fountain_direction == "two_way"

        # Missing mapping still cannot change the retained original body.
        del raw["music_parameters"]
        raw["music_fountain_direction"] = "two_way"
        legacy = PriorControlState.from_dict(raw)
        assert "music_parameters" not in legacy.to_dict()
        await coordinator.async_restore_effect_control_state(legacy, overwritten_diy_code=None)
        assert coordinator.music_fountain_direction == "two_way"
        assert coordinator.music_fountain_speed == 16
        for invalid in ({"speed": True}, {"speed": 15}, {"unknown": 16}):
            send.reset_mock()
            assert not await coordinator.async_restore_effect_control_state(
                replace(state, music_parameters=invalid), overwritten_diy_code=None
            )
            assert coordinator.music_fountain_speed == 16
            assert coordinator.music_body == state.music_body

    fallback = SimpleNamespace(
        model="TEST-FOUNTAIN",
        profile=profile,
        music_mode="fountain",
        music_fountain_speed=16,
        music_fountain_direction="two_way",
        diy_code=None,
    )
    engine = EffectDeploymentEngine(EffectDeploymentRepository(InMemoryVersionedDocumentStore()))
    captured = engine._capture_prior_state(fallback, config_entry_id="test")
    assert captured.music_parameters == {"speed": 16, "direction": "two_way"}
    assert (
        "speed"
        not in compile_music_profile(
            LibraryItem.new("Legacy", MusicProfile("H617A", "fountain", 50)),
            "H617A",
        ).parameters
    )


@pytest.mark.parametrize("parameters", [None, [], {"speed": []}, {"speed": 1.5}, {"": 16}])
def test_music_recovery_mapping_rejects_malformed_persisted_data(parameters):
    raw = PriorControlState(mode="music", is_on=True, brightness_pct=50, rgb_color=(1, 2, 3)).to_dict()
    with pytest.raises(EffectStorageError):
        PriorControlState.from_dict({**raw, "music_parameters": parameters})


@pytest.mark.parametrize("next_mode", ["off", "rhythm"])
async def test_alternate_fountain_direction_survives_capture_and_recovery(hass, monkeypatch, next_mode):
    fountain = music_variant(get_profile("H617A"), 0x35)
    assert fountain is not None
    variant = replace(
        fountain,
        evidence="TEST ONLY alternate Fountain direction; no hardware qualification",
        palette_bounds=None,
        parameters=(
            replace(
                fountain.parameters[0], default="alternate", options=("alternate",), requires_physical_ic_count=False
            ),
        ),
        direction_values=(("alternate", 1, 3),),
    )
    profile = ModelProfile(
        "Synthetic Fountain", command_grammar="H617A", music_modes=("fountain", "rhythm"), music_variants=(variant,)
    )
    monkeypatch.setitem(MODEL_PROFILES, "TEST-FOUNTAIN", profile)
    compiled = compile_music_profile(
        LibraryItem.new("Fountain", MusicProfile("TEST-FOUNTAIN", "fountain", 50)), "TEST-FOUNTAIN"
    )
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "TEST-FOUNTAIN", configuration_url="test")
    with _music_transport(coordinator) as send:
        await async_apply_compiled_profile(coordinator, compiled)
        packets = [call.args[1] for call in send.await_args_list]
        raw = coordinator.capture_effect_control_state().to_dict()
        assert raw["music_fountain_direction"] == "alternate"
        assert raw["music_parameters"] == {"direction": "alternate"}
        state = PriorControlState.from_dict(raw)
        coordinator.music_fountain_direction = "clockwise"
        send.reset_mock()
        assert not await coordinator.async_restore_effect_control_state(state, overwritten_diy_code=None)
        assert coordinator.music_fountain_direction == "alternate"
        assert [call.args[1] for call in send.await_args_list] == [
            build_brightness(state.brightness_pct, coordinator.model),
            *packets,
        ]
        body = MusicBody.from_bytes(_assemble(packets[2:]))
        body._read()
        assert (body.tail.start_point, body.tail.piece_num) == (1, 3)
        await coordinator.async_select_music_slug(next_mode)
        assert coordinator.music_fountain_direction == "alternate"
        inactive_raw = coordinator.capture_effect_control_state().to_dict()
        assert inactive_raw["music_parameters"] == {}
        inactive = PriorControlState.from_dict(inactive_raw)
        assert inactive.mode == ("colour" if next_mode == "off" else "music")
        # Recovery must restore the selected mode, not replay retained Fountain parameters.
        await async_apply_compiled_profile(coordinator, compiled)
        send.reset_mock()
        assert not await coordinator.async_restore_effect_control_state(inactive, overwritten_diy_code=None)
        assert coordinator.music_mode == next_mode
        assert all(call.args[1][0] != 0xA3 for call in send.await_args_list)
        assert PriorControlState.from_dict(coordinator.capture_effect_control_state().to_dict()).music_parameters == {}
        coordinator.is_on = False
        powered_off = PriorControlState.from_dict(coordinator.capture_effect_control_state().to_dict())
        assert powered_off.mode == inactive.mode and not powered_off.is_on and powered_off.music_parameters == {}
        send.reset_mock()
        assert not await coordinator.async_restore_effect_control_state(powered_off, overwritten_diy_code=None)
        assert send.await_args_list[-1].args[1] == build_power(False, coordinator.model)
    del raw["music_parameters"]
    with pytest.raises(EffectStorageError, match="prior fountain direction is invalid"):
        PriorControlState.from_dict(raw)


@pytest.mark.parametrize(
    "key,value",
    [
        ("music_separation_point", "alternate"),
        ("music_hopping_brightness", 256),
        ("music_piano_key_count", True),
        ("music_daynight_segments", -1),
        ("music_daynight_speed", "slow"),
        ("music_separation_gradient", 1),
        ("music_daynight_gradient", "alternate"),
        ("music_fountain_direction", "alternate"),
    ],
)
def test_authoritative_mapping_bypasses_only_redundant_legacy_parameter_validation(key, value):
    state = PriorControlState(mode="music", is_on=True, brightness_pct=50, rgb_color=(1, 2, 3))
    with pytest.raises(EffectStorageError):
        replace(state, **{key: value})
    with pytest.raises(EffectStorageError):
        PriorControlState.from_dict({**state.to_dict(), key: value})
    authoritative = replace(state, music_parameters={}, **{key: value})
    assert PriorControlState.from_dict(authoritative.to_dict()) == authoritative


@pytest.mark.parametrize("changes", [{"music_sensitivity": True}, {"music_calm": 1}, {"music_color": (256, 0, 0)}])
def test_authoritative_parameters_do_not_bypass_selector_validation(changes):
    with pytest.raises(EffectStorageError):
        PriorControlState(
            mode="music", is_on=True, brightness_pct=50, rgb_color=(1, 2, 3), music_parameters={}, **changes
        )


@pytest.mark.parametrize("style,calm_default", [(False, False), (True, True)])
async def test_native_and_compiled_music_defaults_use_variant_style(hass, monkeypatch, style, calm_default):
    bloom = music_variant(get_profile("H617A"), 0x30)
    assert bloom is not None
    variant = replace(
        bloom,
        evidence="TEST ONLY Bloom defaults",
        supports_style=style,
        calm_default=calm_default,
        style_companions=bloom.style_companions if style else None,
    )
    profile = ModelProfile(
        "Synthetic Bloom", command_grammar="H617A", music_modes=("bloom",), music_variants=(variant,)
    )
    monkeypatch.setitem(MODEL_PROFILES, "TEST-BLOOM", profile)
    compiled = compile_music_profile(LibraryItem.new("Bloom", MusicProfile("TEST-BLOOM", "bloom", 99)), "TEST-BLOOM")
    assert compiled.calm is calm_default
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "TEST-BLOOM", configuration_url="test")
    with _music_transport(coordinator) as send:
        await coordinator.async_select_music_slug("bloom")
        native = [call.args[1] for call in send.await_args_list]
        send.reset_mock()
        await async_apply_compiled_profile(coordinator, compiled)
        authored = [call.args[1] for call in send.await_args_list]
        assert native[:2] == authored[:2]
        if style:
            assert native == authored
            coordinator.music_calm = False
            send.reset_mock()
            await coordinator.async_select_music_slug("bloom")
            assert send.await_args_list[1].args[1] == native[1]
            assert [call.args[1] for call in send.await_args_list][2:] != native[2:]
    if not style:
        invalid = LibraryItem.new("Hidden style", MusicProfile("TEST-BLOOM", "bloom", 99, calm=False))
        assert compatibility(invalid, "TEST-BLOOM").state is CompatibilityState.INCOMPATIBLE


@pytest.mark.parametrize(
    "mode,calm,parameters",
    [
        ("separation", None, {"point": 6}),
        ("separation", None, {"point": True}),
        ("separation", None, {"gradient": 1}),
        ("rhythm", False, {"point": 1}),
        ("fountain", None, {"direction": "alternate"}),
        ("rolling", False, {}),
    ],
)
def test_music_eligibility_and_compilation_reject_the_same_content(mode, calm, parameters):
    item = LibraryItem.new("Retained", MusicProfile("H617A", mode, 50, calm=calm, parameters=parameters))
    result = compatibility(item, "H617A")
    assert result.state is CompatibilityState.INCOMPATIBLE
    assert compatible_saved_effects((item,), "H617A") == ()
    with pytest.raises(ValueError) as error:
        compile_music_profile(item, "H617A")
    assert result.reasons == (str(error.value),)


@pytest.mark.parametrize("problem", ["layout", "palette", "hardware", "colour"])
def test_music_target_eligibility_covers_variant_wire_and_hardware(alternative, monkeypatch, problem):
    variant = alternative.music_variants[0]
    colour = None
    parameters = {}
    if problem == "layout":
        variant = replace(variant, layout="unknown")
    elif problem == "palette":
        variant = replace(variant, template=b"\x32\xff")
    elif problem == "hardware":
        variant = replace(variant, requires_physical_ic_count=True)
        parameters = {"point": 8}
    else:
        colour = (1, 2, 3)
    monkeypatch.setitem(MODEL_PROFILES, "TEST-MUSIC", replace(alternative, music_variants=(variant,)))
    item = LibraryItem.new(
        "Retained", MusicProfile("TEST-MUSIC", "separation", 50, colour=colour, parameters=parameters)
    )
    assert compatibility(item, "TEST-MUSIC").state is CompatibilityState.INCOMPATIBLE
    with pytest.raises(ValueError):
        compile_music_profile(item, "TEST-MUSIC")
    catalogue = replace(
        MODEL_EFFECT_CATALOGUES["H617A"], sku="TEST-MUSIC", music_modes=(NativeModeOption("separation", "Separation"),)
    )
    assert catalogue.to_dict()["music_settings"]["separation"]["available"] is (problem in {"hardware", "colour"})
    if problem == "hardware":
        selector = LibraryItem.new("Selector", MusicProfile("TEST-MUSIC", "separation", 50))
        assert compatibility(selector, "TEST-MUSIC").state is CompatibilityState.COMPATIBLE
        assert compile_music_profile(selector, "TEST-MUSIC").parameters == {}
