"""APK-derived H6099 music semantics, not physical-device qualification."""

from dataclasses import replace
from unittest.mock import AsyncMock, patch

import pytest
from bleak import BleakError

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, MUSIC_MODE_SLUGS, get_profile
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.effect_compiler import compile_music_profile
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem, MusicProfile
from custom_components.ha_govee_led_ble.effect_runtime import async_apply_compiled_profile
from custom_components.ha_govee_led_ble.generated_protocol.h6099_music_parameters import H6099MusicParameters
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_brightness,
    build_music_mode,
    build_physical_ic_count_query,
    music_default_palette,
    parse_physical_ic_count,
    parse_status_result,
)
from custom_components.ha_govee_led_ble.music_commands import (
    build_music_params,
    prepare_music_profile_writes,
    prepare_music_request,
)
from custom_components.ha_govee_led_ble.music_semantics import music_params_for_mode, music_variant
from custom_components.ha_govee_led_ble.transport import reassemble_a3, xor_checksum
from tests.test_music_commands import _music_transport


def frame(prefix):
    body = bytes.fromhex(prefix).ljust(19, b"\0")
    return body + bytes((xor_checksum(body),))


def body(mode, parameters=None, *, ic=None, palette=None, calm=False):
    profile = replace(get_profile("H6099"), physical_ic_count=ic)
    packets = build_music_params(mode, parameters or {}, profile=profile, palette=palette, calm=calm)
    parsed = H6099MusicParameters.from_bytes(reassemble_a3(packets)[3:])
    parsed._read()
    return parsed


@pytest.mark.parametrize("count", [0, 1, 14, 29, 30, 60, 32767, -1])
def test_ic_query_and_signed_big_endian_read(count):
    assert build_physical_ic_count_query("H6099") == frame("aa40")
    result = parse_status_result(frame("aa40" + count.to_bytes(2, "big", signed=True).hex()), "H6099")
    assert result.parsed is not None
    assert parse_physical_ic_count(result.parsed) == (count if count > 0 else None)
    with pytest.raises(ValueError):
        build_physical_ic_count_query("H617A")


def test_unknown_ic_blocks_only_dependent_companions():
    profile = get_profile("H6099")
    assert profile.physical_ic_count is None and profile.segment_count == 14
    for slug in profile.music_modes:
        packets = prepare_music_request("H6099", slug, 42, None, False, {})
        assert packets[-1] == frame(f"330513{MUSIC_MODE_SLUGS[slug]:02x}2a")
        assert len(packets) == (4 if slug in {"bloom", "shiny"} else 2)
    for mode in (0x32, 0x33, 0x34, 0x35, 0x37):
        assert music_params_for_mode(mode, profile) == ()
        with pytest.raises(ValueError):
            build_music_params(mode, {}, palette=[(1, 2, 3)], profile=profile)
    with pytest.raises(ValueError):
        prepare_music_request("H6099", "piano_keys", 42, None, False, {"key_count": 14})


@pytest.mark.parametrize("mode", [3, 4, 5, 6, 0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x37])
def test_fixed_colour_and_style_are_mode_specific(mode):
    if mode in (3, 4, 5, 6):
        assert build_music_mode(mode, 42, (1, 2, 3), False, "H6099") == frame(f"330513{mode:02x}2a0001010203")
    else:
        with pytest.raises(ValueError):
            build_music_mode(mode, 42, (1, 2, 3), False, "H6099")
    if mode in (3, 0x30, 0x31):
        assert build_music_mode(mode, 42, None, True, "H6099") == frame(
            f"330513{mode:02x}2a" + ("01" if mode == 3 else "")
        )
    else:
        with pytest.raises(ValueError):
            build_music_mode(mode, 42, None, True, "H6099")


@pytest.mark.parametrize("mode", [0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x37])
def test_variable_palette_uses_named_tail(mode):
    default = body(mode, ic=60)
    assert default.num_palette == 7
    assert [(c.red, c.green, c.blue) for c in default.palette] == [
        (255, 0, 0),
        (255, 127, 0),
        (255, 255, 0),
        (0, 255, 0),
        (0, 0, 255),
        (0, 255, 255),
        (139, 0, 255),
    ]
    for size in (1, 8):
        changed = body(mode, ic=60, palette=[(1, 2, 3)] * size)
        assert changed.num_palette == size
        assert changed.tail.__class__ is default.tail.__class__
    for palette in ([], [(1, 2, 3)] * 9, [(True, 2, 3)], [(256, 2, 3)]):
        with pytest.raises(ValueError):
            body(mode, ic=60, palette=palette)


def test_ic_independent_style_companions():
    assert reassemble_a3(build_music_params(0x31, {}, profile=get_profile("H6099"))) == bytes.fromhex(
        "0102413107ff0000ff7f00ffff0000ff000000ff00ffff8b00ff05640a"
    ).ljust(34, b"\0")
    assert (body(0x30).tail.no_rhythm_speed, body(0x30).tail.rhythm_speed) == (10, 80)
    assert body(0x30, calm=True).tail.rhythm_speed == 20
    for calm, expected in ((False, (5, 100, 10)), (True, (20, 70, 10))):
        tail = body(0x31, calm=calm).tail
        assert (tail.minimum_brightness, tail.maximum_brightness, tail.speed) == expected


@pytest.mark.parametrize(
    "mode,parameters",
    [
        (0x32, {"point": 0}),
        (0x32, {"point": 6}),
        (0x32, {"gradient": 1}),
        (0x33, {"relative_brightness": -1}),
        (0x33, {"relative_brightness": 51}),
        (0x33, {"background": -1}),
        (0x33, {"background": 0x1000000}),
        (0x35, {"direction": "alternate"}),
    ],
)
def test_h6099_parameter_validation(mode, parameters):
    with pytest.raises(ValueError):
        body(mode, parameters, ic=60)


@pytest.mark.parametrize("ic", [1, 14, 29, 30, 60])
def test_separation_threshold_and_hopping_defaults(ic):
    tail = body(0x32, ic=ic).tail
    assert (tail.point, tail.gradient, tail.companion) == (3, 0, 97 if ic < 30 else 99)
    assert body(0x32, {"gradient": True}, ic=ic).tail.companion == (94 if ic < 30 else 98)
    tail = body(0x33, ic=ic).tail
    assert (tail.background.red, tail.background.green, tail.background.blue) == (1, 1, 1)
    assert (tail.rel_brightness, tail.speed, tail.piece_length_min, tail.piece_length_max) == (25, 98, 1, 3)
    assert (tail.piece_count_min, tail.piece_count_max) == (max(1, (ic * 3 + 24) // 25), max(1, (ic * 2 + 4) // 5))
    tail = body(0x33, {"background": 0x123456, "relative_brightness": 0}, ic=ic).tail
    assert (tail.background.red, tail.background.green, tail.background.blue, tail.rel_brightness) == (18, 52, 86, 0)


@pytest.mark.parametrize(
    "ic,default,minimum,maximum,speed,off",
    [(14, 11, 7, 14, 10, 4), (29, 22, 15, 29, 10, 8), (30, 9, 9, 18, 35, 1), (60, 18, 9, 36, 35, 1)],
)
def test_piano_ic_bounds_defaults_and_derived_off_maximum(ic, default, minimum, maximum, speed, off):
    profile = replace(get_profile("H6099"), physical_ic_count=ic)
    spec = music_params_for_mode(0x34, profile)[0]
    assert (spec.default, spec.min_value, spec.max_value) == (default, minimum, maximum)
    for count in (minimum, maximum):
        tail = body(0x34, {"key_count": count, "gradient": True}, ic=ic).tail
        assert (tail.key_count, tail.gradient, tail.speed, tail.off_minimum, tail.off_maximum) == (
            count,
            1,
            speed,
            off,
            max(off, count // 2),
        )
    for count in (minimum - 1, maximum + 1, True):
        with pytest.raises(ValueError):
            body(0x34, {"key_count": count}, ic=ic)


@pytest.mark.parametrize(
    "ic,one,two",
    [
        (14, (1, 4, 80), (1, 3, 80)),
        (29, (1, 9, 80), (1, 7, 80)),
        (30, (3, 5, 85), (2, 3, 85)),
        (60, (3, 10, 85), (2, 6, 85)),
    ],
)
def test_fountain_geometry_and_two_way_default(ic, one, two):
    assert body(0x35, ic=ic).tail.start_point == 1
    for direction, start in (("clockwise", 0), ("counterclockwise", 2), ("two_way", 1)):
        tail = body(0x35, {"direction": direction}, ic=ic).tail
        assert tail.start_point == start
        assert (tail.piece_length, tail.piece_count, tail.speed) == (two if start == 1 else one)


@pytest.mark.parametrize("ic,pieces", [(14, 7), (29, 14), (30, 5), (60, 9)])
def test_daynight_matches_actual_default_indexing_without_exposing_broken_ui(ic, pieces):
    tail = body(0x37, ic=ic).tail
    assert (tail.piece_count, tail.speed, tail.gradient) == (pieces, pieces, 0)
    for key in ("segment_count", "speed", "gradient"):
        with pytest.raises(ValueError):
            body(0x37, {key: 1}, ic=ic)


def test_packet_specific_state_follows_reordered_packet():
    writes = prepare_music_profile_writes("H6099", "bloom", 42, None, True, {})
    assert [packet[0] for packet, _ in writes] == [0x33, 0xA3, 0xA3, 0x33]
    palette = music_default_palette(music_variant(get_profile("H6099"), 0x30))
    assert [{key: value for key, value in state.items() if key != "_music_body"} for _, state in writes[:-1]] == [
        {"is_on": True},
        {"_music_palette": None},
        {"music_calm": True, "_music_palette": ("bloom", palette)},
    ]
    assert writes[-1][1]["music_mode"] == "bloom" and "music_calm" not in writes[-1][1]
    profile = replace(get_profile("H6099"), physical_ic_count=60)
    writes = prepare_music_profile_writes("H6099", "piano_keys", 42, None, False, {}, profile=profile)
    assert {key: value for key, value in writes[-2][1].items() if key != "_music_body"} == {
        "music_piano_key_count": 18,
        "music_piano_gradient": False,
        "_music_palette": ("piano_keys", palette),
    }
    assert "music_color" not in writes[-1][1] and "music_calm" not in writes[-1][1]


@pytest.mark.parametrize("route", ["native", "studio", "recovery"])
@pytest.mark.parametrize("failed_index", [0, 1, 2, 3, None])
async def test_all_callers_order_and_physical_attempt_state(hass, route, failed_index):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6099", configuration_url="test")
    coordinator.is_on = False
    coordinator.music_mode = "rhythm"
    coordinator.music_calm = False
    coordinator.music_sensitivity = 42
    packets = prepare_music_request("H6099", "bloom", 42, None, True, {})
    compiled = compile_music_profile(LibraryItem.new("Bloom", MusicProfile("H6099", "bloom", 42, calm=True)), "H6099")
    restored = replace(
        coordinator.capture_effect_control_state(),
        mode="music",
        is_on=True,
        music_mode="bloom",
        music_calm=True,
        music_palette=music_default_palette(music_variant(coordinator.profile, 0x30)),
        music_body=prepare_music_profile_writes("H6099", "bloom", 42, None, True, {})[-2][1]["_music_body"][1],
    )
    if route == "native":
        coordinator.music_calm = True

    attempted = set()

    async def transmit(uuid, packet, *, response):
        if packet == build_brightness(restored.brightness_pct, "H6099"):
            assert route == "recovery"
            return
        index = packets.index(packet)
        attempted.add(index)
        assert coordinator.music_mode == ("bloom" if 3 in attempted else "rhythm")
        # Verbatim recovery derives retained display controls from that same body.
        assert coordinator.music_calm is (route == "native" or 2 in attempted)
        if index == failed_index:
            raise BleakError("music write failed")

    async def apply():
        if route == "native":
            await coordinator.async_select_music_slug("bloom")
        elif route == "studio":
            await async_apply_compiled_profile(coordinator, compiled)
        else:
            await coordinator.async_restore_effect_control_state(restored, overwritten_diy_code=None)

    with _music_transport(coordinator) as physical, patch.object(coordinator, "_encryption", None):
        physical.side_effect = transmit
        if failed_index is None:
            await apply()
            assert [call.args[1] for call in physical.await_args_list] == (
                [build_brightness(restored.brightness_pct, "H6099")] if route == "recovery" else []
            ) + list(packets)
            assert coordinator.music_body == restored.music_body
        else:
            with pytest.raises(BleakError, match="music write failed"):
                await apply()
            assert [call.args[1] for call in physical.await_args_list] == (
                [build_brightness(restored.brightness_pct, "H6099")] if route == "recovery" else []
            ) + list(packets[: failed_index + 1]) * 3
            assert coordinator.music_body is None
    assert coordinator._field_revisions == {}


async def test_native_connection_failure_keeps_state_and_snapshot(hass):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6099", configuration_url="test")
    before = coordinator.capture_effect_control_state()
    snapshot = coordinator._pre_mode_snapshot
    with patch.object(coordinator, "_ensure_connected", AsyncMock(side_effect=BleakError("unavailable"))):
        with pytest.raises(BleakError):
            await coordinator.async_select_music_slug("bloom")
    assert coordinator.capture_effect_control_state() == before
    assert coordinator._pre_mode_snapshot is snapshot


async def test_recovery_without_complete_body_never_substitutes_preset(hass):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6099", configuration_url="test")
    before = coordinator.capture_effect_control_state()
    prior = replace(
        before,
        mode="music",
        is_on=True,
        music_mode="bloom",
        music_calm=True,
        music_palette=music_default_palette(music_variant(coordinator.profile, 0x30)),
    )
    assert prior.music_body is None
    with _music_transport(coordinator) as physical:
        assert not await coordinator.async_restore_effect_control_state(prior, overwritten_diy_code=None)
        physical.assert_not_awaited()
        coordinator._ensure_connected.assert_not_awaited()
    assert coordinator.capture_effect_control_state() == before
    assert coordinator.control_write_attempts == 0


@pytest.mark.parametrize("route", ["native", "studio", "recovery"])
async def test_transform_rejection_keeps_unattempted_selector_state(hass, route):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6099", configuration_url="test")
    coordinator.is_on = True
    coordinator.music_mode = "rhythm"
    coordinator.music_calm = True
    before = coordinator.capture_effect_control_state()
    compiled = compile_music_profile(LibraryItem.new("Bloom", MusicProfile("H6099", "bloom", 42, calm=True)), "H6099")
    restored = replace(
        before,
        mode="music",
        music_mode="bloom",
        music_sensitivity=42,
        music_palette=music_default_palette(music_variant(coordinator.profile, 0x30)),
        music_body=prepare_music_profile_writes("H6099", "bloom", 42, None, True, {})[-2][1]["_music_body"][1],
    )

    def reject(packet):
        if packet[0] == 0xA3:
            raise ValueError("transform rejected upload")
        return packet

    coordinator.profile = replace(coordinator.profile, outbound_transform=reject)
    with _music_transport(coordinator) as physical, patch.object(coordinator, "_encryption", None):
        with pytest.raises(ValueError, match="transform rejected"):
            if route == "native":
                await coordinator.async_select_music_slug("bloom")
            elif route == "studio":
                await async_apply_compiled_profile(coordinator, compiled)
            else:
                await coordinator.async_restore_effect_control_state(restored, overwritten_diy_code=None)
        assert physical.await_count == (2 if route == "recovery" else 1)
    assert coordinator.capture_effect_control_state() == before
    assert coordinator.control_write_attempts == (2 if route == "recovery" else 1)


async def test_native_does_not_overwrite_state_arriving_during_selector_await(hass):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6099", configuration_url="test")
    selector = prepare_music_request("H6099", "bloom", 99, None, False, {})[-1]

    async def transmit(uuid, packet, *, response):
        if packet == selector:
            coordinator.music_mode = "rolling"
            coordinator.music_sensitivity = 17

    with _music_transport(coordinator) as physical, patch.object(coordinator, "_encryption", None):
        physical.side_effect = transmit
        await coordinator.async_select_music_slug("bloom")
    assert (coordinator.music_mode, coordinator.music_sensitivity) == ("rolling", 17)


def test_order_is_a_profile_declaration_not_a_model_allowlist(monkeypatch):
    monkeypatch.setitem(MODEL_PROFILES, "TEST-ORDER", replace(get_profile("H617A"), music_upload_before_selector=True))
    packets = prepare_music_request("TEST-ORDER", "bloom", 42, None, False, {})
    assert [packet[0] for packet in packets] == [0x33, 0xA3, 0xA3, 0x33]
