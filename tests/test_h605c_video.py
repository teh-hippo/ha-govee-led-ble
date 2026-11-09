"""Exact video layouts and shared semantic admission for H605C."""

from dataclasses import replace
from itertools import permutations
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ha_govee_led_ble.const import ReadDomain
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_expectations import expectations_from_packet
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode, decode_status_frame, parse_color_mode
from custom_components.ha_govee_led_ble.effect_compiler import compile_video_profile
from custom_components.ha_govee_led_ble.effect_deployments import PriorControlState
from custom_components.ha_govee_led_ble.effect_domain import (
    LibraryItem,
    RelativeBrightness,
    VideoProfile,
    effect_content_from_dict,
    effect_content_to_dict,
)
from custom_components.ha_govee_led_ble.effect_runtime import async_apply_compiled_profile, compiled_observation
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_blank_screen,
    build_relative_brightness_query,
    build_video_mode,
    build_white_balance,
    build_white_balance_query,
    build_whole_relative_brightness,
    parse_video_command,
    require_profile_packet,
)
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.native_profile_controls import (
    apply_active_video_mode,
    apply_relative_brightness,
    apply_whole_relative_brightness,
    prepare_video_mode,
)
from custom_components.ha_govee_led_ble.video_applicability import video_control_states, video_profile_control_states
from tests.test_h6099 import frame

EDGES = {"left_percent": 27, "top_percent": 48, "right_percent": 69, "bottom_percent": 80}
SETTINGS = {"full_screen": True, "saturation": 50, "sound_effects": False, "sound_effects_softness": 50}


@pytest.fixture
def device(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H605C", configuration_url="test")
    coordinator._client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    coordinator._notification_token = object()
    coordinator.is_on = True
    monkeypatch.setattr(coordinator, "identity_fields_confirmed", lambda _: True)
    coordinator.fw_version = "1.01.00"
    coordinator.subordinate_20_version = "1.03.30"
    coordinator.subordinate_21_version = "1.00.18"
    monkeypatch.setattr(coordinator, "refresh_state", AsyncMock(return_value=True))
    return coordinator


def test_public_saved_frame_and_nonzero_suffix(device):
    public = bytes.fromhex("33 05 00 01 00 32 00 32 00 64 64 64 64 00 00 00 00 00 00 37")
    assert build_video_mode("movie", True, 50, False, 50, "H605C", values=dict.fromkeys(EDGES, 100)) == public
    reply = bytes.fromhex("aa 05 00 01 00 32 00 32 00 64 64 64 64 00 00 00 00 00 00 ae")
    parsed = decode_status_frame(reply, "H605C")
    assert parsed is not None
    values = parse_color_mode(parsed.generated, "H605C")
    assert values.mode is ParsedMode.VIDEO and values.video_parameters == dict.fromkeys(EDGES, 100)
    assert values.video_full_screen is True and values.video_mode == "movie"
    altered = frame("aa0500010032003200646464647e1122334455")
    decoded = decode_status_frame(altered, "H605C")
    assert decoded is not None
    assert decoded.generated.body.detail.reserved_end == 0x7E
    assert decoded.generated.body.detail.unknown_tail == bytes.fromhex("1122334455")
    require_profile_packet(public, device.profile)
    assert expectations_from_packet(public, "H605C")["video_full_screen"] is True
    assert parse_video_command(public, "H605C").detail.source.name == "movie"


@pytest.mark.parametrize("softness", [0, 99])
def test_long_layout_on_both_pact_revisions(device, softness):
    for pact_code in (1, 2):
        device.pact_type, device.pact_code = 1, pact_code
        packet = build_video_mode("game", False, 1, True, softness, "H605C", values=EDGES)
        assert packet == frame(f"33050000010101{softness:02x}001b30455000")
        require_profile_packet(packet, device.profile)
    with pytest.raises(ValueError, match="complete edge"):
        build_video_mode("movie", True, 50, False, 50, "H605C")


def test_independent_settings_and_metadata(device):
    assert build_white_balance(13, 6, "H605C") == frame("33a90003010d06")
    assert build_white_balance_query("H605C") == frame("aaa900")
    assert build_relative_brightness_query("H605C") == frame("aaae01")
    assert build_whole_relative_brightness(47, "H605C") == frame("33a902012f")
    assert build_whole_relative_brightness(None, "H605C") == frame("aaa902")
    for packet in (
        build_white_balance(13, 6, "H605C"),
        build_white_balance_query("H605C"),
        build_blank_screen(True, "H605C"),
        build_whole_relative_brightness(47, "H605C"),
        build_whole_relative_brightness(None, "H605C"),
    ):
        require_profile_packet(packet, device.profile)
    device._notify_callback(None, bytearray(frame("aaa902012f998877")))
    assert device.whole_relative_brightness == 47
    assert device.relative_brightness_left is None
    assert device._field_revisions["whole_relative_brightness"] == 1
    for prefix, version in (("aa06", "1.01.00"), ("aa0703", "3.02.01"), ("aa20", "1.03.30"), ("aa21", "1.00.18")):
        device._notify_callback(None, bytearray(frame(prefix + version.encode("ascii").hex() + "00")))
    assert (device.fw_version, device.hw_version, device.subordinate_20_version, device.subordinate_21_version) == (
        "1.01.00",
        "3.02.01",
        "1.03.30",
        "1.00.18",
    )
    device._notify_callback(None, bytearray(frame("aa051501ffff")))
    assert device.color_mode is ParsedMode.COLOUR
    assert device.rgb_color_source != "observed" and device.color_temp_kelvin is None


def test_last_segment_page_retains_opaque_slots_and_physical_count(device):
    decoded = decode_status_frame(frame("aaa5043211223332445566deadbeefcafebabe"), "H605C")
    assert decoded is not None
    assert len(decoded.generated.body.segments) == 2
    assert bytes(decoded.generated.body.unused) == bytes.fromhex("deadbeefcafebabe")
    count = decode_status_frame(frame("aa400064"), "H605C")
    assert count is not None and count.generated.body.count == 100


@pytest.mark.parametrize("value,state", [(0, "absent"), (1, "healthy"), (2, "incompatible"), (9, "unknown")])
def test_camera_health_and_direction_use_independent_domains(device, value, state):
    device.profile = replace(
        device.profile,
        read_domains=device.profile.read_domains | {ReadDomain.CAMERA_HEALTH, ReadDomain.INSTALLATION_DIRECTION},
    )
    device._notify_callback(None, bytearray(frame(f"aa32{value:02x}89ab")))
    assert device.camera_health == state
    device._notify_callback(None, bytearray(frame("aa3004dead")))
    assert device.installation_direction == 4


@pytest.mark.parametrize(
    "payload,mode,calm,colour",
    [
        ("05630101112233", "energetic", None, None),
        ("03320101112233", "rhythm", True, (17, 34, 51)),
        ("04320000112233", "spectrum", None, None),
        ("06320001112233", "rolling", None, (17, 34, 51)),
    ],
)
def test_music_status_limits_observations_to_the_selector_semantics(device, payload, mode, calm, colour):
    decoded = decode_status_frame(frame("aa0513" + payload), "H605C")
    assert decoded is not None
    parsed = parse_color_mode(decoded.generated, "H605C")
    assert (parsed.music_mode, parsed.music_calm, parsed.music_color) == (mode, calm, colour)


@pytest.mark.parametrize(
    "main,wireless,hardware,edges,whole",
    [
        ("1.00.12", "1.00.08", "1.03.30", "supported", "unsupported"),
        ("1.00.11", "1.00.08", "1.03.30", "unsupported", "supported"),
        ("1.00.12", "1.00.07", "1.03.30", "unsupported", "supported"),
        ("1.00.08", None, "1.03.30", "unsupported", "unsupported"),
        (None, "1.00.03", None, "unsupported", "unsupported"),
        ("1.00.12", None, "1.03.30", "evidence_gap", "evidence_gap"),
    ],
)
def test_compound_gates_are_order_independent(device, main, wireless, hardware, edges, whole):
    device.fw_version, device.subordinate_21_version, device.subordinate_20_version = main, wireless, hardware
    conditions = device.profile.video_firmware_conditions
    for pair in permutations(conditions[:2]):
        states = video_control_states(replace(device.profile, video_firmware_conditions=pair + conditions[2:]), device)
        assert states["relative_brightness"] == edges
        assert states["whole_relative_brightness"] == whole


async def test_complete_typed_request_supplies_first_frame_without_warmup(device, monkeypatch):
    content = VideoProfile(
        "H605C",
        "game",
        True,
        42,
        False,
        0,
        None,
        RelativeBrightness(27, 48, 69, 80),
        None,
    )
    compiled = compile_video_profile(LibraryItem.new("Complete video", content), "H605C")
    device.video_parameters = None
    read = AsyncMock(side_effect=AssertionError("complete values must not need a preparatory read"))
    monkeypatch.setattr(device, "async_read_video_setting", read)
    await async_apply_compiled_profile(device, compiled, verify=False)
    expected = build_video_mode("game", True, 42, False, 0, "H605C", values=EDGES)
    writes = device._client.write_gatt_char.await_args_list
    assert writes[0].args[1] == expected
    assert device._field_revisions.get("video_parameters", 0) == 0
    light = GoveeBLELight(device)
    monkeypatch.setattr(light, "_compile_template_default", lambda _: compiled)
    monkeypatch.setattr(light, "_notify_state_changed", lambda: None)
    device._client.write_gatt_char.reset_mock()
    device.video_parameters = None
    await light.async_turn_on(effect="Video: Game")
    assert device._client.write_gatt_char.await_args_list[0].args[1] == expected
    read.assert_not_awaited()


async def test_independent_read_recovers_inline_values_after_clear(device, monkeypatch):
    device.video_parameters = None
    device.video_full_screen, device.video_saturation = True, 50
    device.video_sound_effects, device.video_sound_effects_softness = False, 50

    async def read(control):
        assert control == "video_parameters"
        device._notify_callback(None, bytearray(frame("aaae01041b30455099aa")))
        return True

    reader = AsyncMock(side_effect=read)
    monkeypatch.setattr(device, "async_read_video_setting", reader)
    await apply_active_video_mode(device, mode="movie", requested_values=SETTINGS, verify=False)
    assert device._client.write_gatt_char.await_args.args[1] == build_video_mode(
        "movie",
        True,
        50,
        False,
        50,
        "H605C",
        values=EDGES,
    )
    assert device._field_revisions["video_parameters"] == 1
    device.video_parameters = None
    await apply_active_video_mode(device, mode="game", requested_values=SETTINGS, verify=False)
    assert reader.await_count == 2
    assert device._field_revisions["video_parameters"] == 2


async def test_subscription_read_uses_transport_and_does_not_grant_edge_writes(device, monkeypatch):
    device.fw_version, device.subordinate_21_version = "1.00.09", "1.00.04"
    monkeypatch.setattr(device, "_ensure_connected", AsyncMock())
    physical_writer = device._async_write_packet

    async def write(client, packet, **kwargs):
        assert packet == frame("aaae01")
        kwargs["before_write"]()
        kwargs["on_write"]()
        device._notify_callback(None, bytearray(frame("aaae01041b304550")))

    monkeypatch.setattr(device, "_async_write_packet", AsyncMock(side_effect=write))
    assert await device.async_read_video_setting("video_parameters")
    assert device.video_parameters == EDGES
    assert video_control_states(device.profile, device)["relative_brightness"] == "unsupported"
    assert device._field_revisions["video_parameters"] == 1
    monkeypatch.setattr(device, "_async_write_packet", physical_writer)
    await apply_active_video_mode(device, mode="movie", requested_values=SETTINGS, verify=False)
    assert device.video_parameters == EDGES


async def test_cold_static_omissions_fail_before_writes_but_typed_settings_work(device):
    device._notify_callback(None, bytearray(frame("aa051501")))
    with pytest.raises(ValueError, match="complete typed video profile"):
        await apply_active_video_mode(device, mode="movie", requested_values={}, verify=False)
    device._client.write_gatt_char.assert_not_awaited()
    await apply_active_video_mode(
        device,
        mode="movie",
        requested_values=SETTINGS,
        relative_brightness=(27, 48, 69, 80),
        verify=False,
    )
    assert device._client.write_gatt_char.await_count == 1


def test_retention_rejects_new_observation_even_if_value_equal(device):
    device._notify_callback(None, bytearray(frame("aaae01041b304550")))
    _, _, _, guard = prepare_video_mode(device, mode="movie", requested_values=SETTINGS)
    device._notify_callback(None, bytearray(frame("aaae01041b304550")))
    with pytest.raises(ValueError, match="observations or connection"):
        guard()


async def test_scalar_semantics_persist_compile_write_and_snapshot(device, monkeypatch):
    device.fw_version, device.subordinate_21_version = "1.00.09", "1.00.04"
    content = VideoProfile("H605C", "movie", True, 50, False, 50, None, None, None, whole_relative_brightness=47)
    assert effect_content_from_dict(effect_content_to_dict(content)) == content
    compiled = compile_video_profile(LibraryItem.new("Scalar video", content), "H605C")
    assert compiled.whole_relative_brightness == 47 and compiled.relative_brightness is None
    assert compiled.progress_total == 2
    await apply_whole_relative_brightness(device, 47, verify=False)
    assert device._client.write_gatt_char.await_args.args[1] == frame("33a902012f")
    assert device.whole_relative_brightness == 47
    assert device._field_revisions.get("whole_relative_brightness", 0) == 0
    snapshot = device.capture_effect_control_state()
    assert PriorControlState.from_dict(snapshot.to_dict()).whole_relative_brightness == 47
    device._notify_callback(None, bytearray(frame("aaae01041b304550")))
    device._client.write_gatt_char.reset_mock()
    await async_apply_compiled_profile(device, compiled, verify=False)
    assert [call.args[1] for call in device._client.write_gatt_char.await_args_list] == [
        build_video_mode("movie", True, 50, False, 50, "H605C", values=EDGES),
        frame("33a902012f"),
    ]

    async def read(control):
        assert control == "whole_relative_brightness"
        device._notify_callback(None, bytearray(frame("aaa902012f")))
        return True

    monkeypatch.setattr(device, "async_read_video_setting", AsyncMock(side_effect=read))
    device.whole_relative_brightness = 31
    permitted, complete = await device._restore_video_controls(
        replace(snapshot, video_restore_controls=("whole_relative_brightness",))
    )
    assert complete and permitted == {"whole_relative_brightness"}
    assert device.whole_relative_brightness == 47 and device._field_revisions["whole_relative_brightness"] == 1


async def test_older_complete_profile_embeds_edges_without_requiring_the_newer_register(device, monkeypatch):
    device.fw_version, device.subordinate_21_version = "1.00.09", "1.00.04"
    device.video_parameters = None
    reader = AsyncMock(side_effect=AssertionError("complete inline values do not require a register read"))
    monkeypatch.setattr(device, "async_read_video_setting", reader)
    content = VideoProfile(
        "H605C",
        "movie",
        True,
        50,
        False,
        50,
        None,
        RelativeBrightness(27, 48, 69, 80),
        None,
        whole_relative_brightness=47,
    )
    compiled = compile_video_profile(LibraryItem.new("Older video", content), "H605C")
    assert compiled.relative_brightness_inline and compiled.progress_total == 2
    assert effect_content_from_dict(effect_content_to_dict(content)) == content
    native = video_control_states(device.profile, device)
    editor = video_profile_control_states(device.profile, device)
    assert native["relative_brightness"] == "unsupported" and native["whole_relative_brightness"] == "supported"
    assert editor["relative_brightness"] == "supported" and "inline_relative_brightness" not in editor
    await async_apply_compiled_profile(device, compiled, verify=False)
    assert [call.args[1] for call in device._client.write_gatt_char.await_args_list] == [
        build_video_mode("movie", True, 50, False, 50, "H605C", values=EDGES),
        frame("33a902012f"),
    ]
    reader.assert_not_awaited()
    expected, _confidence = compiled_observation(compiled)
    assert expected is not None and expected["video_parameters"] == EDGES
    assert not any(key.startswith("relative_brightness") for key in expected)
    with pytest.raises(ValueError, match="relative_brightness is unsupported"):
        await apply_relative_brightness(device, (27, 48, 69, 80), verify=False)


async def test_inline_recovery_restores_mode_values_without_the_independent_register(device, monkeypatch):
    device.fw_version, device.subordinate_21_version = "1.00.09", "1.00.04"
    device._notify_callback(None, bytearray(frame("aa05000100320032001b30455000")))
    snapshot = replace(
        device.capture_effect_control_state(),
        video_restore_controls=("capture_region", "saturation", "sound_effects", "inline_relative_brightness"),
    )
    device.video_parameters = dict.fromkeys(EDGES, 100)
    reader = AsyncMock(side_effect=AssertionError("inline recovery must not require the independent register"))
    monkeypatch.setattr(device, "async_read_video_setting", reader)
    monkeypatch.setattr(device, "send_command", AsyncMock())
    permitted, complete = await device._restore_video_controls(snapshot)
    assert complete and "inline_relative_brightness" in permitted and "relative_brightness" not in permitted
    assert await device._restore_video_mode(snapshot, permitted, complete)
    assert device._client.write_gatt_char.await_args.args[1] == build_video_mode(
        "movie", True, 50, False, 50, "H605C", values=EDGES
    )
    reader.assert_not_awaited()
