"""Exact H6072 revision admission and shared runtime regressions."""

from dataclasses import replace

import pytest

from custom_components.ha_govee_led_ble.const import ReadDomain, device_profile, get_profile
from custom_components.ha_govee_led_ble.generated_protocol_adapter import build_segment_query, require_profile_packet
from custom_components.ha_govee_led_ble.light_commands import build_color_rgb, build_color_temp, build_segment_color
from custom_components.ha_govee_led_ble.music_commands import prepare_music_request
from custom_components.ha_govee_led_ble.scenes import MODEL_SCENES


@pytest.mark.parametrize(
    ("pact", "fw", "hw", "static", "segment_brightness", "companion", "low_blue"),
    [
        (None, None, None, False, False, False, False),
        (1, "invalid", "invalid", False, False, False, False),
        (1, "1.00.10", None, True, False, False, False),
        (1, "1.00.11", None, False, False, False, False),
        (1, "1.00.11", "1.00.00", True, False, False, False),
        (1, "1.00.11", "1.00.01", True, True, False, False),
        (1, "1.02.99", "1.00.01", True, True, False, False),
        (1, "1.03.00", "1.00.01", True, True, True, False),
        (2, "2.01.99", "3.02.00", True, True, False, False),
        (2, "2.02.00", "3.02.00", True, True, True, False),
        (2, "2.04.06", "3.02.00", True, True, True, False),
        (2, "2.04.07", "3.02.00", True, True, True, True),
        (None, "2.04.10", "3.02.00", True, True, False, True),
    ],
)
def test_h6072_independent_revision_gates(pact, fw, hw, static, segment_brightness, companion, low_blue):
    profile = device_profile("H6072", pact, 1 if pact is not None else None, firmware=fw, hardware=hw)
    assert profile.supports_rgb is static
    assert profile.supports_segment_brightness is segment_brightness
    assert ("torch" in profile.music_modes) is companion
    assert profile.supports_low_blue_light is low_blue
    assert profile.can_read(ReadDomain.POWER) and profile.can_read(ReadDomain.BRIGHTNESS)
    assert profile.readback_music_modes == get_profile("H6072").music_modes
    assert (profile.segment_count, profile.segment_group_size, profile.physical_ic_count) == (8, 3, 66)


def test_h6072_legacy_and_new_static_are_not_interchangeable():
    legacy = device_profile("H6072", 1, 1, firmware="1.00.10", hardware="1.00.01")
    current = device_profile("H6072", 2, 1, firmware="2.04.10", hardware="3.02.00")
    assert build_segment_color([8], 17, 34, 51, "H6072", profile=legacy)[2:13] == bytes.fromhex(
        "1411223300000000000080"
    )
    assert build_segment_color([8], 17, 34, 51, "H6072", profile=current)[2:14] == bytes.fromhex(
        "150111223300000000008000"
    )
    assert build_segment_query(3, "H6072", profile=legacy)[1:3] == bytes.fromhex("a203")
    assert build_segment_query(3, "H6072", profile=current)[1:3] == bytes.fromhex("a503")
    for source, target in ((legacy, current), (current, legacy)):
        with pytest.raises(ValueError, match="revision"):
            require_profile_packet(build_color_rgb(17, 34, 51, "H6072", profile=source), target)
    with pytest.raises(ValueError):
        require_profile_packet(
            build_color_rgb(17, 34, 51, "H6072", profile=current), device_profile("H6072", None, None)
        )


def test_h6072_kelvin_normalises_and_uses_white_direct_rgb():
    legacy = device_profile("H6072", 1, 1, firmware="1.00.10", hardware="1.00.01")
    current = device_profile("H6072", 2, 1, firmware="2.04.10", hardware="3.02.00")
    assert build_color_temp(2201, "H6072", profile=legacy)[2:13] == bytes.fromhex("14ffffff0898ff982900ff")
    assert build_color_temp(2201, "H6072", profile=current)[2:14] == bytes.fromhex("1501ffffff0898ff9829ff00")


def test_h6072_scene_gate_is_independent_of_static_hardware_gate():
    from custom_components.ha_govee_led_ble.scenes import scene_supported

    profile = device_profile("H6072", 1, 1, firmware="1.01.00", hardware="1.00.00")
    assert not profile.supports_segment_brightness
    assert all(scene_supported(scene, profile) for scene in MODEL_SCENES["H6072"].values())
    old = device_profile("H6072", 1, 1, firmware="1.00.99", hardware="1.00.01")
    for scene in MODEL_SCENES["H6072"].values():
        assert scene_supported(scene, old) is (scene.scene_type in {0, 1})


def test_h6072_receiving_companion_mode_does_not_authorise_its_writer():
    from custom_components.ha_govee_led_ble.coordinator_status import decode_status_frame, parse_color_mode
    from custom_components.ha_govee_led_ble.transport import xor_checksum

    profile = device_profile("H6072", None, None)
    frame = bytes.fromhex("aa050f5063").ljust(19, b"\0")
    decoded = decode_status_frame(frame + bytes((xor_checksum(frame),)), "H6072", profile=profile)
    assert decoded is not None
    assert parse_color_mode(decoded.generated, "H6072", profile=profile).music_mode == "torch"
    with pytest.raises(ValueError):
        prepare_music_request("H6072", "torch", 99, None, False, {}, profile=profile)
    assert replace(profile, music_modes=()).readback_music_modes


@pytest.mark.parametrize("legacy", [False, True])
def test_h6072_raw_pages_preserve_black_zones_and_commit_only_complete_layouts(hass, legacy):
    from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator

    frames = (
        (
            "aaa201010203040506000000000000000000000e",
            "aaa2020708090000000a0b0c0000000000000001",
            "aaa2030000000d0e0f0000000000000000000007",
        )
        if legacy
        else (
            "aaa501640102033204050600000000000000005f",
            "aaa5022507080900000000640a0b0c0000000047",
            "aaa50300000000630d0e0f000000000000000063",
        )
    )
    profile = device_profile("H6072", 1, 1, firmware="1.00.10" if legacy else "1.03.00", hardware="1.00.01")
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6072", configuration_url=None)
    coordinator.profile = replace(profile, profile_identity_fields=frozenset())
    for raw in (frames[0], frames[0], frames[1]):
        coordinator._notify_callback(None, bytearray.fromhex(raw))
        assert coordinator.segment_state_source == "initial"
    coordinator._notify_callback(None, bytearray.fromhex(frames[2]))
    assert coordinator.segment_colors == [
        (1, 2, 3),
        (4, 5, 6),
        (0, 0, 0),
        (7, 8, 9),
        (0, 0, 0),
        (10, 11, 12),
        (0, 0, 0),
        (13, 14, 15),
    ]
    assert coordinator.segment_brightness == ([100] * 8 if legacy else [100, 50, 0, 37, 0, 100, 0, 99])
    assert coordinator.segment_state_source == "observed"


@pytest.mark.parametrize(("gradient", "speed"), [(False, 99), (True, 98)])
def test_h6072_separation_companion_uses_physical_geometry_not_logical_zones(gradient, speed):
    from custom_components.ha_govee_led_ble.protocol_core import H6072MusicBody
    from custom_components.ha_govee_led_ble.transport import reassemble_a3

    profile = device_profile("H6072", 2, 1, firmware="2.04.10", hardware="3.02.00")
    packets = prepare_music_request("H6072", "separation", 99, None, False, {"gradient": gradient}, profile=profile)
    body = H6072MusicBody.from_bytes(reassemble_a3(packets[1:-1]))
    body._read()
    assert body.tail.point == 2 and body.tail.gradient == int(gradient) and body.tail.speed == speed


@pytest.mark.parametrize(
    ("operation", "firmware", "hardware", "confirmed"),
    [
        ("rgb", "1.00.10", "3.02.00", "fw_version"),
        ("scene", "1.01.00", "3.02.00", "fw_version"),
        ("music", "1.03.00", "3.02.00", "fw_version"),
        ("rgb", "2.04.10", "1.00.00", "hw_version"),
    ],
)
def test_h6072_physical_authorisation_uses_each_fresh_field_without_cached_siblings(
    hass, operation, firmware, hardware, confirmed
):
    from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
    from custom_components.ha_govee_led_ble.native_scenes import build_native_scene_packets

    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6072", configuration_url=None)
    coordinator.pact_type, coordinator.pact_code = 1, 1
    coordinator.fw_version, coordinator.hw_version = firmware, hardware
    coordinator._resolve_device_profile()
    coordinator._confirmed_identity_fields = {confirmed}
    profile = coordinator.profile
    if operation == "rgb":
        packets = (build_color_rgb(17, 34, 51, "H6072", profile=profile),)
    elif operation == "scene":
        scene = next(scene for scene in MODEL_SCENES["H6072"].values() if scene.scene_type == 2)
        packets = build_native_scene_packets("H6072", scene, profile=profile)
    else:
        packets = prepare_music_request("H6072", "torch", 99, None, False, {}, profile=profile)
    for packet in packets:
        coordinator._validate_authorized_packet(packet)
    coordinator._confirmed_identity_fields.clear()
    with pytest.raises(ValueError):
        coordinator._validate_authorized_packet(packets[-1])


def test_h6072_baseline_palette_edits_use_the_admitted_type_one_route():
    from custom_components.ha_govee_led_ble.effect_compiler import compile_effect
    from custom_components.ha_govee_led_ble.effect_domain import LibraryItem
    from custom_components.ha_govee_led_ble.native_scenes import build_native_scene_packets
    from custom_components.ha_govee_led_ble.palette_scene_decoder import decode_catalogue_palette_scene

    profile = device_profile("H6072", 1, 1, firmware="1.00.10", hardware="1.00.01")
    scene = next(scene for scene in MODEL_SCENES["H6072"].values() if scene.scene_type == 1)
    content = decode_catalogue_palette_scene("H6072", scene)
    assert content is not None
    compiled = compile_effect(LibraryItem.new("Palette scene", content), "H6072", profile=profile)
    assert compiled.packets == tuple(build_native_scene_packets("H6072", scene, profile=profile))


@pytest.mark.parametrize("failure", ["missing", "bleak", "timeout"])
async def test_h6072_basic_setup_survives_optional_setting_failure_and_quarantines_subscription(
    hass, monkeypatch, failure
):
    from unittest.mock import AsyncMock

    from bleak.exc import BleakError

    from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
    from tests.coordinator_test_support import _c, _packet

    c = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6072", configuration_url=None)
    c.pact_type, c.pact_code = 2, 1
    c.fw_version, c.hw_version = "2.04.10", "3.02.00"
    c._resolve_device_profile()
    c._confirmed_identity_fields = {"fw_version", "hw_version"}
    client = _c()
    c._client = client
    monkeypatch.setattr(c, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(c, "_renew_foreground_lease", lambda: None)
    wait = c._wait_for_revisions

    async def wait_for_fields(fields, domains, deadline):
        return False if "low_blue_light" in fields else await wait(fields, domains, deadline)

    monkeypatch.setattr(c, "_wait_for_revisions", wait_for_fields)
    pages = (
        "aaa501640102033204050600000000000000005f",
        "aaa5022507080900000000640a0b0c0000000047",
        "aaa50300000000630d0e0f000000000000000063",
    )

    async def respond(_uuid, packet, **kwargs):
        if packet[1] == 0xBA and failure != "missing":
            raise (TimeoutError if failure == "timeout" else BleakError)("Optional setting transport failed")
        if packet[1] == 0xA5:
            c._notify_callback(None, bytearray.fromhex(pages[packet[2] - 1]))
        elif packet[1] in {0x01, 0x04, 0x05, 0xA3}:
            body = {0x01: [1], 0x04: [37], 0x05: [0x15, 1, 0, 0], 0xA3: [0]}[packet[1]]
            c._notify_callback(None, bytearray(_packet(0xAA, packet[1], body)))

    client.write_gatt_char = AsyncMock(side_effect=respond)
    snapshot = await c._async_update_data()
    assert snapshot["is_on"] is True and snapshot["brightness_pct"] == 37
    assert c._state_read_available and c.segment_state_source == "observed"
    assert any(call.args[1][:2] == b"\xaa\xba" for call in client.write_gatt_char.await_args_list)
    assert c._client is None and not c._confirmed_identity_fields
    client.disconnect.assert_awaited_once()
