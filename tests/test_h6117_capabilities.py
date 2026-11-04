"""Reconstructed H6117 revision, transform and runtime regressions, not hardware confirmation."""

from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ha_govee_led_ble.const import ReadDomain, device_profile
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode
from custom_components.ha_govee_led_ble.effect_compiler import compile_application
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem, SingleEffect
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_brightness,
    build_music_mode,
    require_profile_packet,
)
from custom_components.ha_govee_led_ble.light_commands import (
    build_color_rgb,
    build_color_temp,
    build_segment_brightness,
    build_segment_color,
)
from custom_components.ha_govee_led_ble.protocol_core import H6117WireWrite
from custom_components.ha_govee_led_ble.transport import reassemble_a1_02, xor_checksum


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
