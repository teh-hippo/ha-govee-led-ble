"""Exact H6125 candidate: wire encodings that differ from the shared logical frames, and the effect route."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.config_entries import ConfigEntryState

from custom_components.ha_govee_led_ble import generated_protocol_adapter as protocol
from custom_components.ha_govee_led_ble.const import DOMAIN, MODEL_PROFILES, ModelProfile, ReadDomain, device_profile
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode
from custom_components.ha_govee_led_ble.effect_catalogue import (
    H617A_TYPE04_APPLY_CODE,
    MODEL_EFFECT_CATALOGUES,
    resolve_catalogue_template,
)
from custom_components.ha_govee_led_ble.effect_compiler import (
    CompatibilityState,
    compatibility,
    compile_application,
    validate_compiled_geometry,
)
from custom_components.ha_govee_led_ble.effect_deployments import (
    DeploymentPhase,
    EffectDeploymentRepository,
    PriorControlState,
)
from custom_components.ha_govee_led_ble.effect_domain import (
    BuiltinScene,
    EffectPair,
    LayeredEffect,
    LibraryItem,
    MultiEffect,
    PaintedEffect,
    SingleEffect,
    effect_content_from_dict,
)
from custom_components.ha_govee_led_ble.effect_preview import PreviewPhase
from custom_components.ha_govee_led_ble.effect_runtime import EffectDeploymentEngine
from custom_components.ha_govee_led_ble.effect_scenes import scene_catalogue_payload, scene_detail_payload
from custom_components.ha_govee_led_ble.effect_websocket import WS_DEVICE, WS_TEMPLATE_DEFAULT_GET
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_brightness,
    build_brightness_query,
    build_colour_mode_query,
    build_firmware_query,
    build_h617a_diy_activation,
    build_hardware_query,
    build_music_mode,
    build_power,
    build_power_query,
    build_scene_activation,
    build_segment_query,
    decode_wire_brightness,
    encode_wire_brightness,
)
from custom_components.ha_govee_led_ble.layered_scene import CatalogueRef
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.light_commands import build_color_rgb, build_color_temp, build_segment_color
from custom_components.ha_govee_led_ble.music_commands import build_music_params
from custom_components.ha_govee_led_ble.music_semantics import (
    compile_music_parameters,
    music_params_for_mode,
)
from custom_components.ha_govee_led_ble.scenes import SCENE_ENTRIES, scene_supported
from custom_components.ha_govee_led_ble.transport import reassemble_a1_02, reassemble_a3, xor_checksum
from tests.storage_test_double import InMemoryVersionedDocumentStore
from tests.test_effect_preview import _manager, _open
from tests.test_effect_websocket import _setup_backend

H = bytes.fromhex


def frame(domain, body):
    packet = bytes((0xAA, domain, *body)).ljust(19, b"\0")
    return packet + bytes((xor_checksum(packet),))


LEGACY = device_profile("H6125", 1, 2, firmware="1.07.00", hardware="1.00.03")
CURRENT = device_profile("H6125", 1, 2, firmware="1.07.01", hardware="1.00.04")
ORIGINAL = device_profile("H6125", 1, 1, firmware="1.00.11", hardware="1.00.01")
INTERMEDIATE = device_profile("H6125", 1, 1, firmware="1.03.01", hardware="1.00.04")
MODERN = device_profile("H6125", 10, 2, firmware="3.04.37", hardware="3.01.10")


def _wire(profile, packet):
    return profile.outbound_transform(packet)


def test_changed_wire_revision_invalidates_old_control_state(h6125):
    h6125.is_on = True
    h6125.brightness_pct = 37
    h6125.color_mode = ParsedMode.COLOUR
    h6125.rgb_color = (12, 34, 56)
    h6125.hw_version = "1.00.03"
    h6125._resolve_device_profile()

    assert h6125.is_on
    assert h6125.brightness_pct == 100
    assert h6125.color_mode is None
    assert h6125.rgb_color == (12, 34, 56)
    assert h6125.rgb_color_source == "initial"


@pytest.mark.parametrize(
    ("percent", "legacy", "current"),
    [(1, 6, 20), (10, 28, 41), (50, 128, 136), (99, 251, 252), (100, 254, 254)],
)
def test_brightness_register_follows_the_hardware_range(percent, legacy, current):
    for profile, register in ((LEGACY, legacy), (CURRENT, current)):
        wire = _wire(profile, build_brightness(percent, "H6125"))
        assert wire == bytes((0x33, 0x04, register)) + bytes(16) + bytes((xor_checksum(bytes((0x33, 0x04, register))),))
        assert decode_wire_brightness(register, profile.brightness_wire_range) == percent


def test_register_mapping_is_the_apps_linear_rule_and_round_trips() -> None:
    for wire_range in ((6, 254), (20, 254)):
        registers = [encode_wire_brightness(percent, wire_range) for percent in range(1, 101)]
        assert registers == sorted(registers) and len(set(registers)) == 100
        assert [decode_wire_brightness(register, wire_range) for register in registers] == list(range(1, 101))
    assert decode_wire_brightness(1, (20, 254)) == 1
    assert decode_wire_brightness(19, (20, 254)) == 1
    assert decode_wire_brightness(255, (20, 254)) == 100
    assert decode_wire_brightness(5, (6, 254)) == 1
    assert decode_wire_brightness(255, (6, 254)) == 100
    for invalid in (0, 256, -1, True):
        with pytest.raises(ValueError, match="from 6 to 254"):
            decode_wire_brightness(invalid, (6, 254))
    with pytest.raises(ValueError, match="not declared"):
        decode_wire_brightness(100, None)
    with pytest.raises(ValueError, match="from 1 to 100"):
        encode_wire_brightness(0, (6, 254))


def test_reported_frk_identity_uses_percentage_brightness_and_modern_music(h6125):
    h6125.pact_type, h6125.pact_code = 10, 2
    h6125.fw_version, h6125.hw_version = "3.04.37", "3.01.10"
    h6125._resolve_device_profile()
    profile = h6125.profile

    assert profile.supports_rgb and profile.supports_color_temperature and profile.supports_segments
    assert profile.outbound_transform is None
    assert len(profile.music_modes) == 11
    assert build_brightness(50, "H6125", profile=profile)[:3] == H("330432")
    assert build_music_mode(5, 42, None, False, "H6125", profile=profile)[:5] == H("330513052a")
    h6125._notify_callback(None, bytearray(frame(0x04, [50])))
    h6125._notify_callback(None, bytearray(frame(0x05, [0x13, 5, 42, 0, 0])))
    assert h6125.brightness_pct == 50
    assert (h6125.music_mode, h6125.music_sensitivity) == ("energetic", 42)


def test_original_controller_preserves_rgb_only_pages_and_recovery(h6125):
    h6125.fw_version, h6125.hw_version = "1.00.11", "1.00.01"
    h6125._resolve_device_profile()
    profile = h6125.profile
    wire = profile.outbound_transform
    assert wire is not None
    assert wire(build_color_rgb(12, 34, 56, profile=profile))[:8] == H("33050b0c2238ff7f")
    assert wire(build_music_mode(5, 42, None, False, profile=profile))[:5] == H("33050c002a")
    assert wire(build_segment_query(4, profile=profile))[:3] == H("aaa204")

    h6125._notify_callback(None, bytearray(frame(0x05, [0x0B, 0])))
    colours = [(index, index * 2, index * 3) for index in range(15)]
    for group in range(1, 5):
        slots = colours[(group - 1) * 4 : group * 4]
        if len(slots) == 3:
            slots = [*slots, (222, 111, 37)]
        body = [group, *(channel for rgb in slots for channel in rgb), 91, 92, 93, 94]
        h6125._notify_callback(None, bytearray(frame(0xA2, body)))

    assert h6125.segment_colors == colours
    assert h6125._field_revisions.get("segment_colors") == 1
    assert "segment_brightness" not in h6125._field_revisions
    state = h6125.capture_effect_control_state()
    assert state.segment_colors == tuple(colours)
    assert state.segment_brightness is None
    assert PriorControlState.from_dict(state.to_dict()) == state


@pytest.mark.parametrize(
    ("mode_id", "colour", "calm", "wire"),
    [
        (0x05, None, False, "3305111032"),
        (0x03, None, False, "3305111132" + "0000"),
        (0x03, (1, 2, 3), True, "3305111132" + "0101010203"),
        (0x04, (255, 0, 0), False, "3305111232" + "01ff0000"),
        (0x06, None, False, "3305111332" + "00"),
        (0x30, None, False, "3305113032"),
        (0x31, None, False, "3305113132"),
        (0x37, None, False, "3305113732"),
    ],
)
def test_pact1_music_selector_is_reencoded_from_the_shared_logical_frame(mode_id, colour, calm, wire):
    logical = build_music_mode(mode_id, 50, colour, calm, "H6125")
    prefix = bytes.fromhex(wire)
    expected = prefix + bytes(19 - len(prefix))
    assert _wire(CURRENT, logical) == expected + bytes((xor_checksum(expected),))


def test_every_other_frame_reaches_the_device_unchanged() -> None:
    packets = (
        build_power(True, "H6125"),
        build_power_query("H6125"),
        build_brightness_query("H6125"),
        build_firmware_query("H6125"),
        build_hardware_query("H6125"),
        build_segment_query(3, "H6125"),
        build_color_rgb(1, 2, 3, "H6125"),
        build_color_temp(4000, "H6125"),
        build_segment_color([1, 5], 10, 20, 30, "H6125"),
        build_scene_activation("H6125", 1234, 0, scene_type=2),
        build_h617a_diy_activation(0xFE),
        b"\xa1\x02\x00\x01" + bytes(15) + b"\xa2",
        b"short",
    )
    assert all(_wire(CURRENT, packet) == packet for packet in packets)
    assert build_colour_mode_query("H6125", profile=CURRENT) == build_colour_mode_query("H617A", selector=1)


def test_expanded_music_companions_come_from_the_declared_ic_count() -> None:
    expected = {
        0x30: "3007ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0a50",
        0x31: "3107ff0000ff7f00ffff0000ff000000ff00ffff8b00ff05640a",
        0x32: "3207ff0000ff7f00ffff0000ff000000ff00ffff8b00ff030063",
        0x33: "3307ff0000ff7f00ffff0000ff000000ff00ffff8b00ff010101196201030614",
        0x34: "3407ff0000ff7f00ffff0000ff000000ff00ffff8b00ff000f230107",
        0x35: "3507ff0000ff7f00ffff0000ff000000ff00ffff8b00ff01020555",
        0x37: "3707ff0000ff7f00ffff0000ff000000ff00ffff8b00ff071400",
    }
    assert CURRENT.physical_ic_count == 50
    assert CURRENT.music_upload_before_selector and CURRENT.music_requires_upload_ack
    for mode_code, body in expected.items():
        defaults = {spec.profile_key: spec.default for spec in music_params_for_mode(mode_code, CURRENT)}
        compiled = compile_music_parameters(defaults, mode_code, CURRENT)
        companion = reassemble_a3(build_music_params(mode_code, compiled, profile=CURRENT))
        assert companion[2] == 0x41 and companion[3:].startswith(bytes.fromhex(body))
        assert not any(companion[3 + len(body) // 2 :])
    assert music_params_for_mode(0x34, CURRENT)[0].max_value == 30


@pytest.fixture
def h6125(hass):
    coordinator = GoveeBLECoordinator(hass, "66:77:88:99:AA:BB", "H6125", configuration_url=None)
    coordinator.pact_type, coordinator.pact_code = 1, 2
    coordinator.fw_version, coordinator.hw_version = "1.07.01", "1.00.04"
    coordinator._resolve_device_profile()
    coordinator._confirmed_identity_fields.update(coordinator.profile.profile_identity_fields)
    return coordinator


async def test_entity_brightness_is_one_register_write(h6125, monkeypatch):
    h6125.is_on = True
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    h6125._client = client
    monkeypatch.setattr(h6125, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(h6125, "_renew_foreground_lease", lambda: None)
    monkeypatch.setattr(h6125, "refresh_state", AsyncMock(return_value=True))
    light = GoveeBLELight(h6125)
    light.async_write_ha_state = MagicMock()
    await light.async_turn_on(brightness=255)
    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == [
        _wire(CURRENT, build_brightness(100, "H6125"))
    ]
    assert h6125.brightness_pct == 100 and h6125.control_write_attempts == 1


def test_exact_catalogue_scenes_compile_through_the_shared_native_route():
    assert sum(not scene.local_only for scene in SCENE_ENTRIES["H6125"]) == 240
    for scene in SCENE_ENTRIES["H6125"]:
        if not scene_supported(scene, CURRENT):
            continue
        item = LibraryItem.new(scene.name, BuiltinScene(CatalogueRef("H6125", scene.scene_id, scene.effect_id)))
        assert compile_application(item, "H6125", profile=CURRENT).packets


def test_type04_effects_upload_over_a1_to_the_latest_slot():
    single = LibraryItem.new("Fade", SingleEffect(family=0, variant=1, speed=40, palette=((255, 0, 0), (0, 0, 255))))
    multi = LibraryItem.new(
        "Combo", MultiEffect(effects=(EffectPair(0, 0), EffectPair(1, 2)), speed=40, palette=((255, 0, 0),))
    )
    for item in (single, multi):
        compiled = compile_application(item, "H6125", profile=CURRENT)
        body = reassemble_a1_02(compiled.upload_packets)
        assert compiled.upload_transport == "a1_02" and compiled.diy_code == 0xFE
        assert body[0] == 0xFE and compiled.upload_packets[0][:2] == b"\xa1\x02"
        assert compiled.activation_packet == build_h617a_diy_activation(0xFE)
        assert compiled.packets == (*compiled.upload_packets, compiled.activation_packet)
    assert reassemble_a1_02(compile_application(single, "H6125", profile=CURRENT).upload_packets)[1:6] == bytes(
        (0, 1, 40, 6, 255)
    )
    a3 = compile_application(single, "H617A", diy_code=H617A_TYPE04_APPLY_CODE)
    assert a3.upload_transport == "a3" and reassemble_a3(a3.upload_packets)[2] == 0x04


def test_two_controller_profiles_do_not_share_diy_transport_or_slots():
    item = LibraryItem.new("Fade", SingleEffect(family=0, variant=0, speed=40, palette=((255, 0, 0),)))
    modern = replace(CURRENT, a1_diy_selector=None)

    a1 = compile_application(item, "H6125", profile=CURRENT)
    a3 = compile_application(item, "H6125", profile=modern, diy_code=H617A_TYPE04_APPLY_CODE)

    assert (a1.upload_transport, a1.diy_code) == ("a1_02", 0xFE)
    assert (a3.upload_transport, a3.diy_code) == ("a3", H617A_TYPE04_APPLY_CODE)
    assert reassemble_a1_02(a1.upload_packets)[0] == 0xFE
    assert reassemble_a3(a3.upload_packets)[2] == 0x04
    assert MODEL_PROFILES["H6125"].a1_diy_selector == 0xFE
    with pytest.raises(ValueError, match="transport or selector changed"):
        validate_compiled_geometry(a3, CURRENT)
    with pytest.raises(ValueError, match="transport or selector changed"):
        validate_compiled_geometry(a1, modern)


@pytest.mark.parametrize("path", ["saved", "preview"])
@pytest.mark.parametrize(
    ("before", "after", "name", "stage"),
    [
        pytest.param(INTERMEDIATE, CURRENT, "Forest", "preflight", id="selector-to-upload"),
        pytest.param(CURRENT, INTERMEDIATE, "Forest", "preflight", id="upload-to-selector"),
        pytest.param(INTERMEDIATE, CURRENT, "Forest", "write", id="route-at-write"),
        pytest.param(MODERN, ORIGINAL, "Dracarys", "write", id="ineligible-at-write"),
    ],
)
async def test_prepared_scenes_recheck_revision_before_any_write(
    hass, h6125, monkeypatch, path, before, after, name, stage
):
    c = h6125
    c.profile = before
    c.is_on = False
    scene = next(entry for entry in SCENE_ENTRIES["H6125"] if entry.name == name)
    item = LibraryItem.new(name, BuiltinScene(CatalogueRef("H6125", scene.scene_id, scene.effect_id)))
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    c._client = client

    async def preflight(*args, **kwargs):
        if stage == "preflight":
            c.profile = after
        return False

    write_packet = c._async_write_packet

    async def write_attempt(*args, **kwargs):
        if stage == "write":
            c.profile = after
        await write_packet(*args, **kwargs)

    monkeypatch.setattr(c, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(c, "_async_write_packet", write_attempt)
    monkeypatch.setattr(c, "_renew_foreground_lease", MagicMock())
    monkeypatch.setattr(c, "async_restore_effect_control_state", AsyncMock(return_value=False))
    monkeypatch.setattr(c, "refresh_state", AsyncMock(return_value=False))
    if path == "saved":
        repository = EffectDeploymentRepository(InMemoryVersionedDocumentStore())
        await repository.async_load()
        engine = EffectDeploymentEngine(repository)
        monkeypatch.setattr(engine, "_async_prepare_prior_state", AsyncMock(side_effect=preflight))
        with pytest.raises(ValueError, match="scene route changed|Scene is not supported"):
            await engine.async_apply_saved(c, item, config_entry_id="entry-a", updated_at="2026-09-16T00:00:00Z")
        assert repository.snapshot().records[-1].phase is DeploymentPhase.FAILED
    else:
        monkeypatch.setattr(c, "async_preview_preflight", AsyncMock(side_effect=preflight))
        manager, _ = await _manager(hass, monkeypatch, c)
        events = []
        owner = object()
        session = _open(manager, owner, events)
        try:
            await manager.async_queue_snapshot(
                session_id=session,
                owner=owner,
                config_entry_id="entry-a",
                sequence=1,
                updated_at="2026-09-16T00:00:00Z",
                item=item,
            )
            await manager.async_wait_idle("entry-a")
            assert events[-1].phase is PreviewPhase.FAILED
        finally:
            await manager.async_shutdown()
    client.write_gatt_char.assert_not_awaited()
    assert c.is_on is False


async def test_public_device_catalogues_and_music_defaults_are_revision_scoped(hass, hass_ws_client, monkeypatch):
    await _setup_backend(hass)
    entries = {}
    for name, profile in (("original", ORIGINAL), ("modern", MODERN)):
        coordinator = GoveeBLECoordinator(hass, "66:77:88:99:AA:BB", "H6125", configuration_url=None)
        coordinator.profile = profile
        entries[name] = SimpleNamespace(
            entry_id=name,
            domain=DOMAIN,
            title=name,
            state=ConfigEntryState.LOADED,
            runtime_data=coordinator,
        )
    monkeypatch.setattr(hass.config_entries, "async_get_entry", entries.get)
    client = await hass_ws_client(hass)
    ceiling = MODEL_EFFECT_CATALOGUES["H6125"].to_dict()
    for name, entry in entries.items():
        await client.send_json_auto_id({"type": WS_DEVICE, "config_entry_id": name})
        response = await client.receive_json()
        assert response["success"], response
        device = response["result"]["device"]
        profile = entry.runtime_data.profile
        assert device["catalogue"] == MODEL_EFFECT_CATALOGUES["H6125"].to_dict(profile=profile)
        assert device["custom_effects"]["painted"] == ("unsupported" if name == "original" else "supported")
        assert any(template["id"] == "template:paint" for template in device["catalogue"]["templates"]) == (
            name == "modern"
        )
        await client.send_json_auto_id(
            {"type": WS_TEMPLATE_DEFAULT_GET, "config_entry_id": name, "template_id": "template:music:rhythm"}
        )
        response = await client.receive_json()
        assert response["success"], response
        content = response["result"]["content"]
        assert content["calm"] is (None if name == "original" else False)
        template = next(
            template for template in device["catalogue"]["templates"] if template["id"] == "template:music:rhythm"
        )
        assert content == template["content"]
        compiled = compile_application(
            LibraryItem.new("Rhythm", effect_content_from_dict(content)), "H6125", profile=profile
        )
        assert compiled.packets
    assert MODEL_EFFECT_CATALOGUES["H6125"].to_dict() == ceiling


@pytest.mark.parametrize(
    ("firmware", "hardware", "expected_count"),
    [("1.00.11", "1.00.01", 10), ("1.03.01", "1.00.04", 64), ("1.07.01", "1.00.04", 240)],
)
def test_scene_catalogue_and_application_agree_for_each_generation(firmware, hardware, expected_count):
    profile = device_profile("H6125", 1, 1, firmware=firmware, hardware=hardware)
    catalogue = scene_catalogue_payload("H6125", profile=profile)
    summaries = catalogue["scenes"]
    assert isinstance(summaries, list) and len(summaries) == expected_count
    for summary in summaries:
        assert isinstance(summary, dict)
        scene_id, effect_id = summary["scene_id"], summary["effect_id"]
        assert isinstance(scene_id, int) and isinstance(effect_id, int)
        detail = scene_detail_payload("H6125", scene_id, effect_id, profile=profile)
        if profile.selector_only_scene_bits is not None:
            assert summary["selector_only"] and summary["parameter_kind"] == "none"
            content = detail["content"]
            assert isinstance(content, dict) and content["kind"] == "scene_builtin"
    if profile.scene_codes is not None:
        scene = next(scene for scene in SCENE_ENTRIES["H6125"] if scene_supported(scene, profile))
        item = LibraryItem.new(scene.name, BuiltinScene(CatalogueRef("H6125", scene.scene_id, scene.effect_id)))
        assert len(compile_application(item, "H6125", profile=profile).packets) == 1
        foreign = next(scene for scene in SCENE_ENTRIES["H6125"] if not scene_supported(scene, profile))
        item = LibraryItem.new(foreign.name, BuiltinScene(CatalogueRef("H6125", foreign.scene_id, foreign.effect_id)))
        assert compatibility(item, "H6125", profile=profile).state is CompatibilityState.INCOMPATIBLE


def test_native_templates_keep_h6125_preset_quantities_and_a3_activation():
    modern = device_profile("H6125", 10, 2, firmware="3.04.37", hardware="3.01.10")
    for selector in range(501, 508):
        template = resolve_catalogue_template("H6125", f"template:native-diy:{selector}", profile=modern)
        assert isinstance(template.content, LayeredEffect)
        compiled = compile_application(LibraryItem.new(template.label, template.content), "H6125", profile=modern)
        assert reassemble_a3(compiled.upload_packets)[2] == 2
        assert compiled.activation_packet == build_scene_activation("H6125", selector, profile=modern)
        if selector == 504:
            assert all(layer.selection.quantity == 10 for layer in template.content.layers)
        elif selector == 506:
            assert all(layer.selection.quantity == 25 for layer in template.content.layers[2:])


def test_legacy_effect_catalogue_hides_and_rejects_newer_templates():
    profile = device_profile("H6125", 1, 1, firmware="1.00.11", hardware="1.00.01")
    catalogue = MODEL_EFFECT_CATALOGUES["H6125"]
    payload = catalogue.to_dict(profile=profile)
    assert not payload["painted_effects"]
    apply = payload["apply"]
    assert isinstance(apply, dict) and apply["painted"] == apply["workshop"] == "unsupported"
    for template_id in ("template:paint", "template:native-diy:501"):
        with pytest.raises(ValueError, match="does not support"):
            resolve_catalogue_template("H6125", template_id, profile=profile)


async def test_independent_sku_and_status_root_use_shared_control_paths(hass, monkeypatch):
    profile = ModelProfile(
        "Synthetic declared device",
        command_grammar="H617A",
        status_grammar="independent-status",
        read_domains=frozenset(
            {ReadDomain.POWER, ReadDomain.BRIGHTNESS, ReadDomain.COLOUR_MODE, ReadDomain.FIRMWARE, ReadDomain.HARDWARE}
        ),
        supports_rgb=True,
        whole_device_mask=0x7FFF,
        music_modes=("energetic",),
    )
    monkeypatch.setitem(MODEL_PROFILES, "H9908", profile)
    monkeypatch.setitem(
        protocol._STATUS_ROOTS,
        "independent-status",
        ("h6125_modern_status_reply", protocol.H6125ModernStatusReply),
    )
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H9908", configuration_url=None)
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    coordinator._client = client
    packet = build_color_rgb(1, 2, 3, "H9908", profile=profile)
    coordinator._notify_callback(None, bytearray(frame(0x06, list(b"3.04.37\0"))))
    coordinator._notify_callback(None, bytearray(frame(0x07, [3, *b"3.01.10\0"])))
    await coordinator._async_write_packet(client, packet)
    coordinator._notify_callback(None, bytearray(frame(0x04, [50])))
    coordinator._notify_callback(None, bytearray(frame(0x05, [0x13, 5, 42, 0, 0])))
    assert coordinator.brightness_pct == 50
    assert coordinator.music_mode == "energetic"
    assert client.write_gatt_char.call_args.args[1] == packet


@pytest.mark.parametrize(
    ("pact", "firmware", "hardware", "initial_power"),
    [(1, "1.00.11", "1.00.01", False), (1, "1.07.01", "1.00.04", True), (10, "3.04.37", "3.01.10", True)],
)
async def test_saved_apply_and_restoration_use_fresh_revision_specific_readback(
    h6125, monkeypatch, pact, firmware, hardware, initial_power
):
    c = h6125
    c.pact_type, c.pact_code = pact, 2
    c.fw_version, c.hw_version = firmware, hardware
    c._resolve_device_profile()
    profile = c.profile
    power, brightness, gradual = initial_power, 37, True
    initial_colours = [(index, index + 10, index + 20) for index in range(15)]
    colours, levels = list(initial_colours), [100] * 15
    static_mode = 0x15 if profile.supports_segment_brightness else 0x0B
    mode, selector = static_mode, 0
    item = LibraryItem.new("Fade", SingleEffect(family=0, variant=0, speed=40, palette=((255, 0, 0),)))
    compiled = compile_application(item, "H6125", diy_code=0xFE if pact == 1 else 24, profile=profile)
    assert compiled.upload_transport == ("a1_02" if pact == 1 else "a3")
    client = MagicMock(is_connected=True, start_notify=AsyncMock(), write_gatt_char=AsyncMock())
    c._client = client
    await c._start_notify()
    notify = client.start_notify.call_args.args[1]
    monkeypatch.setattr(c, "_ensure_connected", AsyncMock(return_value=client))
    notify(None, bytearray(frame(0x06, list(firmware.encode() + b"\0"))))
    notify(None, bytearray(frame(0x07, [3, *(hardware.encode() + b"\0")])))

    async def radio(_uuid, packet, **kwargs):
        nonlocal power, brightness, gradual, mode, selector, colours, levels
        if packet == compiled.upload_packets[-1]:
            prefix = bytes((0xA1 if pact == 1 else 0xA3, 2 if pact == 1 else 4, 0)).ljust(19, b"\0")
            notify(None, bytearray(prefix + bytes((xor_checksum(prefix),))))
        if packet[0] == 0x33:
            if packet[1] == 1:
                power = bool(packet[2])
            elif packet[1] == 4:
                brightness = (
                    decode_wire_brightness(packet[2], profile.brightness_wire_range)
                    if profile.brightness_wire_range is not None
                    else packet[2]
                )
            elif packet[1] == 0xA3:
                gradual = bool(packet[2])
            elif packet[1] == 5:
                mode = packet[2]
                if mode == 0x0A:
                    selector = int.from_bytes(packet[3:5], "little")
                    brightness, gradual, colours, levels = 100, False, [(0, 0, 255)] * 15, [0] * 15
                elif mode == 0x0B or mode == 0x15 and packet[3] == 1:
                    offset = 3 if mode == 0x0B else 4
                    rgb = tuple(packet[offset : offset + 3])
                    mask_offset = 6 if mode == 0x0B else 12
                    mask = int.from_bytes(packet[mask_offset : mask_offset + 2], "little")
                    colours = [rgb if mask & (1 << index) else colour for index, colour in enumerate(colours)]
                elif mode == 0x15 and packet[3] == 2:
                    mask = int.from_bytes(packet[5:7], "little")
                    levels = [packet[4] if mask & (1 << index) else level for index, level in enumerate(levels)]
            return
        if packet[0] != 0xAA:
            return
        if packet[1] == 1:
            body = [int(power)]
        elif packet[1] == 4:
            body = [
                encode_wire_brightness(brightness, profile.brightness_wire_range)
                if profile.brightness_wire_range is not None
                else brightness
            ]
        elif packet[1] == 5:
            body = [mode, selector & 255, selector >> 8] if mode == 0x0A else [mode, int(gradual), 0, 0]
        elif packet[1] == 0xA3:
            body = [int(gradual)]
        elif packet[1] in (0xA2, 0xA5):
            group = packet[2]
            offset = (group - 1) * profile.segment_group_size
            body = [group]
            for index in range(offset, min(offset + profile.segment_group_size, 15)):
                body.extend(([levels[index]] if packet[1] == 0xA5 else []) + list(colours[index]))
        else:
            return
        notify(None, bytearray(frame(packet[1], body)))

    client.write_gatt_char.side_effect = radio
    repository = EffectDeploymentRepository(InMemoryVersionedDocumentStore())
    await repository.async_load()
    engine = EffectDeploymentEngine(repository)
    try:
        result = await engine.async_apply_saved(
            c, item, config_entry_id="h6125", updated_at="2026-10-20T00:00:00Z", diy_code=compiled.diy_code
        )
        assert result.phase is DeploymentPhase.CONFIRMED
        assert c.diy_code == compiled.diy_code
        assert result.prior_state is not None
        assert await c.async_restore_effect_control_state(result.prior_state, overwritten_diy_code=compiled.diy_code)
        assert colours == initial_colours and power is initial_power and brightness == 37 and gradual
        if profile.supports_segment_brightness:
            assert levels == [100] * 15
    finally:
        if c._cancel_disconnect:
            c._cancel_disconnect()


def test_custom_effects_use_their_transport_slot_and_physical_geometry():
    single = LibraryItem.new("Fade", SingleEffect(family=0, variant=0, speed=40, palette=((255, 0, 0),)))
    assert compile_application(single, "H6125", diy_code=0xFE, profile=CURRENT).diy_code == 0xFE
    with pytest.raises(ValueError, match="A1 selector 0xfe"):
        compile_application(single, "H6125", diy_code=800, profile=CURRENT)
    painted = LibraryItem.new("Paint", PaintedEffect("clockwise", 50, 100, (None,) * 15))
    assert compatibility(painted, "H6125", profile=CURRENT).state is CompatibilityState.INCOMPATIBLE
    catalogue = MODEL_EFFECT_CATALOGUES["H6125"]
    assert catalogue.painted_effects and catalogue.supports.advanced.value == "supported"
    assert catalogue.apply.single.value == catalogue.apply.multi.value == "supported"
    assert catalogue.apply.painted.value == catalogue.apply.workshop.value == "supported"
    physical_paint = LibraryItem.new(
        "Paint", PaintedEffect("clockwise", 50, 100, (None,) * 50, addressing="physical_ic")
    )
    compiled = compile_application(physical_paint, "H6125", profile=CURRENT)
    assert compiled.upload_transport == "a3" and compiled.diy_code == 800
