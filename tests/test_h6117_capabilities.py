"""Reconstructed H6117 revision, transform and runtime regressions, not hardware confirmation."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak import BleakError
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError

from custom_components.ha_govee_led_ble.const import DOMAIN, ReadDomain, device_profile
from custom_components.ha_govee_led_ble.control_arbiter import ControlIntent
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode
from custom_components.ha_govee_led_ble.effect_catalogue import H617A_TYPE04_APPLY_CODE, H6117_NATIVE_DIY_TEMPLATES
from custom_components.ha_govee_led_ble.effect_compiler import compile_application
from custom_components.ha_govee_led_ble.effect_deployments import DeploymentPhase, EffectDeploymentRepository
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem, SingleEffect, effect_content_to_dict
from custom_components.ha_govee_led_ble.effect_runtime import EffectDeploymentEngine
from custom_components.ha_govee_led_ble.effect_scenes import resolve_scene
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_boolean_control,
    build_boolean_control_query,
    build_brightness,
    build_brightness_query,
    build_colour_mode_query,
    build_firmware_query,
    build_hardware_query,
    build_music_mode,
    build_power,
    build_power_query,
    require_profile_packet,
)
from custom_components.ha_govee_led_ble.light_commands import (
    build_color_rgb,
    build_color_temp,
    build_segment_brightness,
    build_segment_color,
)
from custom_components.ha_govee_led_ble.native_scenes import build_native_scene_packets
from custom_components.ha_govee_led_ble.protocol_core import H6117WireWrite
from custom_components.ha_govee_led_ble.scenes import MODEL_SCENES
from custom_components.ha_govee_led_ble.transport import reassemble_a1_02, xor_checksum
from tests.storage_test_double import InMemoryVersionedDocumentStore
from tests.test_effect_preview import _manager, _open
from tests.test_effect_websocket import _setup_backend


def _profile(*, firmware="1.08.06", hardware="1.00.02", pact=(1, 1)):
    return device_profile("H6117", *pact, firmware=firmware, hardware=hardware)


@pytest.mark.parametrize(
    ("firmware", "hardware", "segments", "kelvin", "mode", "music_count"),
    [
        ("1.03.17", "1.00.01", False, False, "whole_device_colour", 4),
        ("1.03.18", "1.00.01", True, False, "legacy_colour", 4),
        ("1.05.99", "1.00.02", True, False, "legacy_colour", 4),
        ("1.06.00", "1.00.02", True, True, "static", 4),
        ("1.07.00", "1.00.02", True, True, "static", 11),
        ("1.08.06", "1.00.02", True, True, "static", 11),
    ],
)
def test_legacy_revision_boundaries(firmware, hardware, segments, kelvin, mode, music_count):
    profile = _profile(firmware=firmware, hardware=hardware)
    assert profile.supports_segment_writes is segments
    assert profile.supports_color_temperature is kelvin
    assert profile.supports_segment_brightness is kelvin
    assert len(profile.music_modes) == music_count
    assert profile.physical_ic_count == 50 and not profile.can_read(ReadDomain.SEGMENTS)
    logical = build_color_rgb(12, 34, 56, profile=profile)
    require_profile_packet(logical, profile)
    wire = profile.outbound_transform(logical)
    parsed = H6117WireWrite.from_bytes(wire)
    parsed._read()
    assert parsed.body.sub.name == mode


@pytest.mark.parametrize(
    ("hardware", "firmware", "mode", "segments"),
    [
        ("1.00.01", "1.03.17", "whole_device_colour", 1),
        ("1.00.01", "1.03.18", "legacy_colour", 15),
        ("1.00.02", "1.05.99", "legacy_colour", 15),
        ("1.00.02", "1.06.00", "static", 15),
    ],
)
def test_modern_pact_keeps_rgb_revision_gates_without_rewriting_white(hardware, firmware, mode, segments):
    profile = _profile(pact=(2, 1), hardware=hardware, firmware=firmware)
    assert profile.segment_count == segments
    logical = build_color_rgb(12, 34, 56, profile=profile)
    require_profile_packet(logical, profile)
    parsed = H6117WireWrite.from_bytes(profile.outbound_transform(logical))
    parsed._read()
    assert parsed.body.sub.name == mode
    white = build_color_temp(4000, profile=profile)
    require_profile_packet(white, profile)
    assert profile.outbound_transform(white) == white
    if profile.supports_segment_brightness:
        brightness = build_segment_brightness([1, 15], 50, profile=profile)
        require_profile_packet(brightness, profile)
        assert profile.outbound_transform(brightness) == brightness


@pytest.mark.parametrize("firmware", ["1.06.99", "1.07.00", "1.08.06"])
def test_modern_telink_does_not_inherit_legacy_expanded_music(firmware):
    profile = _profile(pact=(2, 1), firmware=firmware)
    assert len(profile.music_modes) == 4
    assert profile.brightness_wire_range == (6, 254)


@pytest.mark.parametrize(
    ("hardware", "firmware", "uploaded"),
    [
        ("1.00.01", "1.08.06", False),
        ("1.00.02", "1.03.99", False),
        ("1.00.02", "1.04.00", True),
    ],
)
def test_modern_pact_does_not_bypass_uploaded_scene_boundaries(hardware, firmware, uploaded):
    profile = _profile(pact=(2, 1), hardware=hardware, firmware=firmware)
    assert profile.supports_multi_layered_effects is uploaded
    assert (profile.selector_only_scene_bits is None) is uploaded


@pytest.mark.parametrize(
    ("name", "logical_code", "prefix"),
    [
        ("energetic", 5, "330511102a"),
        ("rhythm", 3, "330511112a01010c2238"),
        ("spectrum", 4, "330511132a010c2238"),
        ("rolling", 6, "330511122a010c2238"),
    ],
)
def test_legacy_music_uses_its_own_codebook_and_colour_layout(hass, name, logical_code, prefix):
    profile = _profile()
    colour = None if name == "energetic" else (12, 34, 56)
    logical = build_music_mode(logical_code, 42, colour, name == "rhythm", profile=profile)
    wire = profile.outbound_transform(logical)
    assert wire.startswith(bytes.fromhex(prefix))
    parsed = H6117WireWrite.from_bytes(wire)
    parsed._read()
    assert parsed.body.sub_body.mode_id.name == name
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6117", configuration_url="test")
    coordinator.profile = profile
    reply = bytes((0xAA, 0x05)) + wire[2:19]
    coordinator._notify_callback(None, bytearray(reply + bytes((xor_checksum(reply),))))
    assert (coordinator.music_mode, coordinator.music_sensitivity, coordinator.music_color) == (name, 42, colour)
    if name == "rhythm":
        assert coordinator.music_calm is True


@pytest.mark.parametrize("pact", [(1, 1), (2, 1)])
@pytest.mark.parametrize(("percent", "register"), [(1, 6), (50, 128), (100, 254)])
def test_raw_brightness_does_not_choose_the_music_dialect(pact, percent, register):
    profile = _profile(pact=pact)
    brightness = profile.outbound_transform(build_brightness(percent, profile=profile))
    parsed = H6117WireWrite.from_bytes(brightness)
    parsed._read()
    assert parsed.body.register == register
    music = profile.outbound_transform(build_music_mode(5, 42, None, False, profile=profile))
    parsed = H6117WireWrite.from_bytes(music)
    parsed._read()
    assert parsed.body.sub.name == ("legacy_music" if pact[0] == 1 else "music")


@pytest.mark.parametrize(
    ("hardware", "firmware", "count"),
    [
        ("2.01.01", "2.03.99", 4),
        ("2.01.01", "2.04.00", 11),
        ("2.02.01", "2.04.00", 4),
        ("3.01.01", "3.00.99", 4),
        ("3.01.01", "3.01.00", 11),
        ("3.04.01", "3.01.00", 4),
    ],
)
def test_modern_music_qualification_keeps_percentage_brightness(hardware, firmware, count):
    profile = _profile(pact=(2, 1), hardware=hardware, firmware=firmware)
    assert len(profile.music_modes) == count
    logical = build_brightness(50, profile=profile)
    assert profile.outbound_transform(logical) == logical
    assert profile.brightness_wire_range is None


@pytest.mark.parametrize(
    "identity",
    [
        {"pact": (None, None)},
        {"firmware": None},
        {"hardware": None},
        {"hardware": "1.00.02/1.03.04"},
        {"firmware": "2.04.00"},
        {"hardware": "9.00.00", "firmware": "9.00.00"},
    ],
)
def test_unknown_or_conflicting_identity_never_inherits_ceiling_controls(identity):
    profile = _profile(**identity)
    assert profile.command_operations == frozenset({"power"})
    assert not profile.supports_rgb and not profile.music_modes
    assert profile.confirmation_issue == 537


def test_whole_device_rgb_cannot_be_used_for_partial_segments():
    profile = _profile(firmware="1.03.17", hardware="1.00.01")
    logical = build_color_rgb(12, 34, 56, profile=profile)
    require_profile_packet(logical, profile)
    assert not profile.supports_segment_writes
    partial = build_segment_color(
        [2], 12, 34, 56, profile=replace(profile, segment_count=15, supports_segment_writes=True)
    )
    with pytest.raises(ValueError, match="partial masks"):
        profile.outbound_transform(partial)


def test_legacy_fixed_diy_selector_compiles_without_a_user_slot():
    profile = _profile()
    item = LibraryItem.new("H6117 candidate", SingleEffect(0, 0, 50, ((255, 0, 0),)))
    compiled = compile_application(item, "H6117", profile=profile)
    assert compiled.upload_transport == "a1_02"
    assert reassemble_a1_02(compiled.upload_packets)[0] == 0xFE


@pytest.mark.parametrize("pact", [(1, 1), (2, 1)])
def test_master_register_and_music_readback_use_the_effective_profile(hass, pact):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6117", configuration_url="test")
    coordinator.pact_type, coordinator.pact_code = pact
    coordinator.fw_version, coordinator.hw_version = "1.08.06", "1.00.02"
    coordinator._resolve_device_profile()

    def notify(domain, payload):
        frame = bytes((0xAA, domain, *payload)).ljust(19, b"\x00")
        coordinator._notify_callback(None, bytearray(frame + bytes((xor_checksum(frame),))))

    notify(0x04, [128])
    assert coordinator.brightness_pct == 50
    notify(0x05, [0x11, 0x10, 42] if pact[0] == 1 else [0x13, 5, 42])
    assert coordinator.color_mode is ParsedMode.MUSIC
    assert (coordinator.music_mode, coordinator.music_sensitivity) == ("energetic", 42)


async def test_cached_identity_does_not_authorise_reconnect_writes(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6117", configuration_url="test")
    coordinator.pact_type, coordinator.pact_code = 1, 1
    coordinator.fw_version, coordinator.hw_version = "1.08.06", "1.00.02"
    coordinator._resolve_device_profile()

    async def establish(*args, **kwargs):
        assert coordinator.profile.supports_segment_writes
        assert coordinator.profile.brightness_wire_range == (6, 254)
        assert coordinator._authorization_profile().command_operations == frozenset({"power"})
        raise RuntimeError("stop before connecting")

    monkeypatch.setattr("custom_components.ha_govee_led_ble.coordinator.async_establish_ble_connection", establish)
    with pytest.raises(RuntimeError, match="stop before connecting"):
        await coordinator._ensure_connected()


@pytest.fixture(params=[(1, 1), (2, 1)])
async def reconnect_identity(hass, monkeypatch, request):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6117", configuration_url="test")
    coordinator.pact_type, coordinator.pact_code = request.param
    coordinator.fw_version, coordinator.hw_version = "1.08.06", "1.00.02"
    coordinator._resolve_device_profile()
    coordinator.is_on = True
    replies = {
        build_hardware_query("H6117"): b"\xaa\x07\x03" + b"1.00.02",
    }
    packets = []
    timers = []
    client = MagicMock(is_connected=True, services=[])

    def receive(prefix):
        body = prefix.ljust(19, b"\x00")
        client.start_notify.call_args.args[1](None, body + bytes((xor_checksum(body),)))

    async def transmit(_uuid, packet, **kwargs):
        packets.append(packet)
        reply = replies.get(packet)
        if reply is None and coordinator._upload_ack is not None:
            _, _, _, subtype, _, protocol, _ = coordinator._upload_ack
            reply = bytes((protocol, subtype, 0))
        if reply is not None:
            timers.append(asyncio.get_running_loop().call_later(0.01, receive, reply))

    async def disconnect():
        client.is_connected = False
        coordinator._disconnected_callback(client)

    client.start_notify = AsyncMock()
    client.write_gatt_char = AsyncMock(side_effect=transmit)
    client.disconnect = AsyncMock(side_effect=disconnect)
    monkeypatch.setattr(
        "custom_components.ha_govee_led_ble.coordinator.async_establish_ble_connection",
        AsyncMock(return_value=client),
    )
    monkeypatch.setattr("custom_components.ha_govee_led_ble.coordinator.IDENTITY_QUERY_TIMEOUT", 0.08)
    monkeypatch.setattr(coordinator, "_start_keep_alive", MagicMock())
    try:
        await coordinator._ensure_connected()
        assert coordinator.profile.supports_custom_effects
        assert coordinator._confirmed_identity_fields == {"hw_version"}
        packets.clear()
        yield coordinator, replies, packets
    finally:
        await coordinator.disconnect()
        for timer in timers:
            timer.cancel()


@pytest.mark.parametrize("route", ["scenes", "diy", "advanced", "brightness", "gradual", "recovery"])
async def test_foreground_requalifies_missing_reconnect_identity(reconnect_identity, monkeypatch, route, virtual_clock):
    coordinator, replies, packets = reconnect_identity
    replies[build_firmware_query("H6117")] = b"\xaa\x06" + b"1.08.06"
    expected = []
    if route == "scenes":
        for name in ("action-a", "action-b"):
            expected.extend(
                build_native_scene_packets("H6117", MODEL_SCENES["H6117"][name], profile=coordinator.profile)
            )
            await coordinator.async_apply_native_scene(name, verify=False, intent=ControlIntent.APPLY)
    elif route in {"diy", "advanced"}:
        content = SingleEffect(0, 0, 50, ((255, 0, 0),)) if route == "diy" else H6117_NATIVE_DIY_TEMPLATES[0].content
        compiled = compile_application(
            LibraryItem.new("Reconnect", content),
            "H6117",
            diy_code=H617A_TYPE04_APPLY_CODE
            if route == "diy" and coordinator.profile.a1_diy_selector is None
            else None,
            profile=coordinator.profile,
        )
        expected.extend(compiled.packets)
        await coordinator.async_write_effect_sequence(
            compiled.packets,
            intent=ControlIntent.APPLY,
            require_upload_ack=True,
            upload_ack_index=len(compiled.upload_packets) - 1,
        )
    elif route == "gradual":
        query = build_boolean_control_query("gradual", "H6117", profile=coordinator.profile)
        replies[query] = b"\xaa\xa3\x01"
        expected.extend((build_boolean_control("gradual", True, "H6117", profile=coordinator.profile), query))
        await coordinator.async_set_boolean_control("gradual", True)
        assert coordinator.boolean_control_state["gradual"] is True
        assert coordinator.is_on is True
    elif route == "recovery":
        prior = replace(
            coordinator.capture_effect_control_state(),
            is_on=True,
            mode="scene",
            effect="action-a",
            scene_code=None,
            brightness_pct=50,
        )
        monkeypatch.setattr(coordinator, "refresh_state", AsyncMock(return_value=True))
        expected.extend(
            (
                build_power(True, "H6117"),
                coordinator.profile.outbound_transform(build_brightness(50, profile=coordinator.profile)),
                build_native_scene_packets("H6117", MODEL_SCENES["H6117"]["action-a"], profile=coordinator.profile)[-1],
            )
        )
        assert not await coordinator.async_restore_effect_control_state(prior, overwritten_diy_code=None)
    else:
        packet = build_brightness(50, profile=coordinator.profile)
        expected.append(coordinator.profile.outbound_transform(packet))
        await coordinator.send_command(packet)
    assert coordinator.identity_fields_confirmed()
    assert packets[0] == build_firmware_query("H6117")
    assert packets[1:] == expected


@pytest.mark.parametrize("reply", [None, b"\xaa\x06invalid"])
async def test_missing_reconnect_identity_is_not_reported_as_unsupported(reconnect_identity, reply, virtual_clock):
    coordinator, replies, packets = reconnect_identity
    if reply is not None:
        replies[build_firmware_query("H6117")] = reply
    with pytest.raises(HomeAssistantError) as error:
        await coordinator.send_command(build_brightness(50, profile=coordinator.profile))
    assert error.value.translation_key == "identity_not_ready"
    assert not any(packet[0] != 0xAA for packet in packets)
    assert coordinator.control_write_attempts == 0
    await coordinator.send_command(build_power(False, "H6117"))
    assert packets[-1] == build_power(False, "H6117")


async def test_identity_refresh_cancellation_does_not_authorise_writes(reconnect_identity, virtual_clock):
    coordinator, _, packets = reconnect_identity
    request = asyncio.create_task(coordinator.send_command(build_brightness(50, profile=coordinator.profile)))
    await asyncio.sleep(0)
    request.cancel()
    with pytest.raises(asyncio.CancelledError):
        await request
    assert not coordinator.identity_fields_confirmed()
    assert not any(packet[0] != 0xAA for packet in packets)


async def test_identity_refresh_rejects_replaced_subscription(reconnect_identity, virtual_clock):
    coordinator, replies, packets = reconnect_identity
    replies[build_firmware_query("H6117")] = b"\xaa\x06" + b"1.08.06"
    original_write = coordinator._client.write_gatt_char.side_effect

    async def replace_subscription(*args, **kwargs):
        await original_write(*args, **kwargs)
        coordinator._notification_token = object()

    coordinator._client.write_gatt_char.side_effect = replace_subscription
    with pytest.raises(BleakError, match="confirming controller identity"):
        await coordinator._ensure_connected()
    assert not any(packet[0] != 0xAA for packet in packets)


@pytest.mark.parametrize("cold", [False, True])
@pytest.mark.parametrize("identity_available", [False, True])
async def test_studio_snapshot_qualifies_identity_before_applying(
    reconnect_identity, monkeypatch, cold, identity_available, virtual_clock
):
    coordinator, replies, packets = reconnect_identity
    if cold:
        coordinator.fw_version = coordinator.hw_version = None
        coordinator._confirmed_identity_fields.clear()
        coordinator._resolve_device_profile()
    if identity_available:
        replies[build_firmware_query("H6117")] = b"\xaa\x06" + b"1.08.06"
    mode_query = build_colour_mode_query("H6117", profile=_profile())
    replies.update(
        {
            build_power_query("H6117"): b"\xaa\x01\x01",
            build_brightness_query("H6117"): b"\xaa\x04\x80",
            mode_query: b"\xaa\x05\x04\x04\x00",
        }
    )
    transmit = coordinator._client.write_gatt_char.side_effect

    async def write(_uuid, packet, **kwargs):
        if packet[:2] == b"\x33\x05":
            replies[mode_query] = b"\xaa\x05" + packet[2:19]
        await transmit(_uuid, packet, **kwargs)

    coordinator._client.write_gatt_char.side_effect = write
    restore = AsyncMock()
    monkeypatch.setattr(coordinator, "async_restore_effect_control_state", restore)
    repository = EffectDeploymentRepository(InMemoryVersionedDocumentStore())
    await repository.async_load()
    engine = EffectDeploymentEngine(repository)
    item = LibraryItem.new("Studio readiness", SingleEffect(0, 0, 50, ((255, 0, 0),)))

    async def apply():
        return await engine.async_apply_snapshot(
            coordinator, item, config_entry_id="entry-a", updated_at="2026-11-12T00:00:00Z"
        )

    if identity_available:
        result = await apply()
        assert result.phase is DeploymentPhase.CONFIRMED
        compiled = compile_application(
            item,
            "H6117",
            diy_code=H617A_TYPE04_APPLY_CODE if coordinator.profile.a1_diy_selector is None else None,
            profile=coordinator.profile,
        )
        assert [packet for packet in packets if packet[0] != 0xAA] == list(compiled.packets)
        assert coordinator.identity_fields_confirmed()
    elif cold:
        with pytest.raises(HomeAssistantError) as error:
            await apply()
        assert error.value.translation_key == "identity_not_ready"
    else:
        with pytest.raises(RuntimeError, match="current power, mode and brightness"):
            await apply()
    if not identity_available:
        assert not any(packet[0] != 0xAA for packet in packets)
        assert coordinator.control_write_attempts == 0
    restore.assert_not_awaited()


@pytest.mark.parametrize("route", ["scene", "snapshot"])
async def test_cold_studio_preview_qualifies_before_compilation(
    hass, monkeypatch, reconnect_identity, route, virtual_clock
):
    coordinator, replies, packets = reconnect_identity
    coordinator.fw_version = coordinator.hw_version = None
    coordinator._confirmed_identity_fields.clear()
    coordinator._resolve_device_profile()
    replies[build_firmware_query("H6117")] = b"\xaa\x06" + b"1.08.06"
    manager, _cache = await _manager(hass, monkeypatch, coordinator)
    accept = AsyncMock()
    monkeypatch.setattr(manager, "_async_accept", accept)
    owner = object()
    session = _open(manager, owner, [])
    generation = coordinator._control_arbiter.foreground_generation
    kwargs = {
        "session_id": session,
        "owner": owner,
        "config_entry_id": "entry-a",
        "sequence": 1,
        "updated_at": "2026-11-12T00:00:00Z",
    }
    try:
        if route == "snapshot":
            await manager.async_queue_snapshot(
                **kwargs, item=LibraryItem.new("Preview readiness", SingleEffect(0, 0, 50, ((255, 0, 0),)))
            )
        else:
            scene = MODEL_SCENES["H6117"]["action-a"]
            await manager.async_queue_scene(
                **kwargs, scene_id=scene.scene_id, effect_id=scene.effect_id, speed_index=None
            )
        assert coordinator.identity_fields_confirmed()
        accept.assert_awaited_once()
        assert accept.await_args.kwargs["preparation_generation"] == generation
        assert packets and all(packet[0] == 0xAA for packet in packets)
    finally:
        await manager.async_shutdown()


@pytest.mark.parametrize("route", ["snapshot", "saved", "scene"])
@pytest.mark.parametrize("identity_available", [False, True])
async def test_studio_api_prepares_cold_profile_before_admission(
    hass, hass_ws_client, monkeypatch, reconnect_identity, route, identity_available
):
    coordinator, replies, packets = reconnect_identity
    coordinator.fw_version = coordinator.hw_version = None
    coordinator._confirmed_identity_fields.clear()
    coordinator._resolve_device_profile()
    if identity_available:
        replies[build_firmware_query("H6117")] = b"\xaa\x06" + b"1.08.06"
    backend = await _setup_backend(hass)
    entry = SimpleNamespace(entry_id="entry-a", domain=DOMAIN, state=ConfigEntryState.LOADED, runtime_data=coordinator)
    monkeypatch.setattr(hass.config_entries, "async_get_entry", lambda _id: entry)
    record = SimpleNamespace(to_public_dict=lambda: {"phase": "confirmed"})
    snapshot = AsyncMock(return_value=record)
    saved = AsyncMock(return_value=record)
    monkeypatch.setattr(backend.engine, "async_apply_snapshot", snapshot)
    monkeypatch.setattr(backend.engine, "async_apply_saved", saved)
    scene = MODEL_SCENES["H6117"]["action-a"]
    apply_scene = AsyncMock(return_value=(resolve_scene("H6117", scene.scene_id, scene.effect_id), None))
    monkeypatch.setattr("custom_components.ha_govee_led_ble.effect_websocket.async_apply_scene", apply_scene)
    content = effect_content_to_dict(SingleEffect(0, 0, 50, ((255, 0, 0),)))
    message = {"config_entry_id": "entry-a"}
    if route == "scene":
        message.update(type=f"{DOMAIN}/editor/scene/apply", scene_id=scene.scene_id, effect_id=scene.effect_id)
    elif route == "saved":
        mutation = await backend.application.async_create_library_item(name="Cold API", content=content)
        message.update(
            type=f"{DOMAIN}/editor/apply",
            item_id=str(mutation.item.id),
            expected_version=mutation.item.version,
            updated_at="2026-11-12T00:00:00Z",
        )
    else:
        message.update(
            type=f"{DOMAIN}/editor/apply_snapshot",
            name="Cold API",
            content=content,
            updated_at="2026-11-12T00:00:00Z",
        )
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(message)
    response = await client.receive_json()
    assert response["success"] is identity_available
    if identity_available:
        assert coordinator.identity_fields_confirmed()
        assert (snapshot.await_count, saved.await_count, apply_scene.await_count) == (
            int(route == "snapshot"),
            int(route == "saved"),
            int(route == "scene"),
        )
    else:
        assert response["error"]["code"] == "apply_failed"
        snapshot.assert_not_awaited()
        saved.assert_not_awaited()
        apply_scene.assert_not_awaited()
    assert packets and all(packet[0] == 0xAA for packet in packets)
    assert coordinator.control_write_attempts == 0


async def test_write_only_segment_paint_preserves_siblings_without_querying(hass, monkeypatch, virtual_clock):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6117", configuration_url="test")
    coordinator.pact_type, coordinator.pact_code = 1, 1
    coordinator.fw_version, coordinator.hw_version = "1.08.06", "1.00.02"
    coordinator._resolve_device_profile()
    coordinator._confirmed_identity_fields.update(coordinator.profile.profile_identity_fields)
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(), disconnect=AsyncMock())
    coordinator._client = client
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(coordinator, "_renew_foreground_lease", MagicMock())
    refresh = AsyncMock(return_value=False)
    monkeypatch.setattr(coordinator, "async_refresh_segments", refresh)
    before = list(coordinator.segment_colors)
    try:
        await coordinator.async_paint_segments([([1, 15], (12, 34, 56))])
        assert coordinator.segment_colors[0] == coordinator.segment_colors[14] == (12, 34, 56)
        assert coordinator.segment_colors[1:14] == before[1:14]
        assert coordinator.segment_state_source == "optimistic"
        refresh.assert_not_awaited()
        assert client.write_gatt_char.await_count > 0
    finally:
        await coordinator.disconnect()
