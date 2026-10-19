"""Exact H6125 candidate: wire encodings that differ from the shared logical frames, and the effect route."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, ReadDomain, device_profile
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode, StatusDomain, decode_status_frame
from custom_components.ha_govee_led_ble.effect_catalogue import H617A_TYPE04_APPLY_CODE, MODEL_EFFECT_CATALOGUES
from custom_components.ha_govee_led_ble.effect_compiler import CompatibilityState, compatibility, compile_application
from custom_components.ha_govee_led_ble.effect_domain import (
    BuiltinScene,
    EffectPair,
    LibraryItem,
    MultiEffect,
    PaintedEffect,
    SingleEffect,
)
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
    parse_status,
)
from custom_components.ha_govee_led_ble.layered_scene import CatalogueRef
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.light_commands import build_color_rgb, build_color_temp, build_segment_color
from custom_components.ha_govee_led_ble.music_commands import build_music_params
from custom_components.ha_govee_led_ble.music_semantics import (
    compile_music_parameters,
    music_params_for_mode,
)
from custom_components.ha_govee_led_ble.scenes import SCENE_ENTRIES
from custom_components.ha_govee_led_ble.transport import reassemble_a1_02, reassemble_a3, xor_checksum

H = bytes.fromhex


def frame(domain, body):
    packet = bytes((0xAA, domain, *body)).ljust(19, b"\0")
    return packet + bytes((xor_checksum(packet),))


LEGACY = device_profile("H6125", 1, 2, firmware="1.07.00", hardware="1.00.03")
CURRENT = device_profile("H6125", 1, 2, firmware="1.07.01", hardware="1.00.04")


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
    with pytest.raises(ValueError, match="from 6 to 254"):
        decode_wire_brightness(5, (6, 254))
    with pytest.raises(ValueError, match="not declared"):
        decode_wire_brightness(100, None)
    with pytest.raises(ValueError, match="from 1 to 100"):
        encode_wire_brightness(0, (6, 254))


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


def test_status_root_covers_every_declared_read_domain() -> None:
    samples = {
        ReadDomain.POWER: frame(0x01, [1]),
        ReadDomain.BRIGHTNESS: frame(0x04, [0x80]),
        ReadDomain.COLOUR_MODE: frame(0x05, [0x15, 0, 0x0F, 0xA0]),
        ReadDomain.FIRMWARE: frame(0x06, list(b"1.07.01\0")),
        ReadDomain.HARDWARE: frame(0x07, [3, *b"1.00.04\0"]),
        ReadDomain.SEGMENTS: frame(0xA5, [1, 100, 255, 0, 0, 100, 0, 255, 0, 100, 0, 0, 255]),
    }
    profile = MODEL_PROFILES["H6125"]
    assert set(samples) == profile.read_domains
    for domain, packet in samples.items():
        decoded = decode_status_frame(packet, "H6125", profile=profile)
        assert decoded is not None and decoded.domain is StatusDomain(domain.value)
    segments = parse_status(samples[ReadDomain.SEGMENTS], "H6125", profile=profile)
    assert segments is not None and segments.body.segments[2].colour.blue == 255


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
    assert len(SCENE_ENTRIES["H6125"]) == 240
    for scene in SCENE_ENTRIES["H6125"]:
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


def test_custom_effects_use_only_the_fixed_slot_and_exclude_unevidenced_families():
    single = LibraryItem.new("Fade", SingleEffect(family=0, variant=0, speed=40, palette=((255, 0, 0),)))
    assert compile_application(single, "H6125", diy_code=0xFE, profile=CURRENT).diy_code == 0xFE
    with pytest.raises(ValueError, match="A1 selector 0xfe"):
        compile_application(single, "H6125", diy_code=800, profile=CURRENT)
    painted = LibraryItem.new("Paint", PaintedEffect("clockwise", 50, 100, (None,) * 15))
    assert compatibility(painted, "H6125", profile=CURRENT).state is CompatibilityState.INCOMPATIBLE
    catalogue = MODEL_EFFECT_CATALOGUES["H6125"]
    assert not catalogue.painted_effects and catalogue.supports.advanced.value == "unsupported"
    assert catalogue.apply.single.value == catalogue.apply.multi.value == "supported"
    assert catalogue.apply.painted.value == catalogue.apply.workshop.value == "unsupported"
