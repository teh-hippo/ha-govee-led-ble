"""H6099 video evidence and requested-only firmware gating, not owner qualification."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, ReadDomain, device_profile, get_profile
from custom_components.ha_govee_led_ble.control_arbiter import BLEControlArbiter
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_refresh import RefreshRequest
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode, decode_status_frame, parse_color_mode
from custom_components.ha_govee_led_ble.effect_catalogue import MODEL_EFFECT_CATALOGUES
from custom_components.ha_govee_led_ble.effect_compiler import compile_video_profile
from custom_components.ha_govee_led_ble.effect_deployments import PriorControlState
from custom_components.ha_govee_led_ble.effect_domain import (
    EffectValidationError,
    LibraryItem,
    VideoProfile,
    effect_content_from_dict,
    effect_content_to_dict,
)
from custom_components.ha_govee_led_ble.effect_runtime import async_apply_compiled_profile, compiled_observation
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_black_border,
    build_black_border_query,
    build_blank_screen,
    build_hdmi_box_light,
    build_hdmi_box_light_query,
    build_hdmi_input,
    build_hdr_contrast,
    build_hdr_contrast_query,
    build_subordinate_query,
    build_video_color_calibration,
    build_video_mode,
    build_video_sensitivity,
    parse_command,
    require_profile_packet,
)
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.native_profile_controls import (
    apply_active_video_mode,
    apply_black_border,
    apply_blank_screen,
    apply_hdmi_box_light,
    apply_hdmi_input,
    apply_hdr_contrast,
    apply_video_color_calibration,
    apply_video_sensitivity,
)
from custom_components.ha_govee_led_ble.protocol_core import _STATUS_ROOTS, H6099StatusReply
from custom_components.ha_govee_led_ble.video_applicability import (
    identity_version,
    validate_video_request,
    video_control_states,
)
from tests.coordinator_test_support import frame
from tests.test_effect_preview import _EffectCoordinator, _known_static_baseline


def content() -> VideoProfile:
    return VideoProfile("H6099", "movie", True, 50, False, 50, None, None, None)


def coordinator(version: str | None = None) -> SimpleNamespace:
    confirmed = {"subordinate_21_version"} if identity_version(version) is not None else set()
    profile = get_profile("H6099")

    async def ensure_connected():
        return None

    return _EffectCoordinator(
        _control_arbiter=BLEControlArbiter(),
        _lock=asyncio.Lock(),
        _confirmed_identity_fields=confirmed,
        identity_fields_confirmed=lambda fields: fields <= confirmed,
        _ensure_connected=ensure_connected,
        model="H6099",
        profile=profile,
        subordinate_21_version=version,
        is_on=True,
        video_full_screen=True,
        video_saturation=50,
        video_sound_effects=False,
        video_sound_effects_softness=50,
        blank_screen=False,
        blank_screen_detection=2,
        blank_screen_low_brightness_duration_seconds=10,
        blank_screen_same_tone_duration_seconds=120,
        _field_revisions={},
        _field_received_at={},
        _notify_started_monotonic=None,
        _authorization_generation=0,
        _blank_screen_notification_revision=0,
        _blank_screen_policy_revision=0,
        _client=None,
        _notification_token=None,
        refresh_state=AsyncMock(return_value=True),
    )


def test_identity_border_and_policy_wire(monkeypatch) -> None:
    profile = get_profile("H6099")
    assert {ReadDomain.SUBORDINATE_20, ReadDomain.SUBORDINATE_21} <= profile.read_domains
    for domain in (0x20, 0x21):
        assert build_subordinate_query(domain, "H6099") == frame(f"aa{domain:02x}")
        decoded = decode_status_frame(frame(f"aa{domain:02x}" + b"1.00.11".hex()), model="H6099")
        assert decoded is not None and decoded.generated.body.text == "1.00.11"
    assert build_black_border_query("H6099") == frame("aaa90b")
    for enabled in (False, True):
        packet = build_black_border(enabled, "H6099")
        assert packet == frame(f"33a90b01{int(enabled):02x}")
        parsed = parse_command(packet, "H6099")
        assert parsed is not None and parsed.body.payload.is_on == enabled
        decoded = decode_status_frame(frame(f"aaa90b01{int(enabled):02x}"), model="H6099")
        assert decoded is not None and decoded.generated.body.payload.is_enabled == enabled
    assert build_blank_screen(True, "H6099", 1, 300, 600) == frame("33a90a0601012c015802")
    domains = set()
    for prefix in (
        "aa0101",
        "aa042a",
        "aa0515011194",
        "aa06312e30302e3131",
        "aa0703312e30302e3030",
        "aa20312e30302e3030",
        "aa21312e30302e3131",
        "aa3002",
        "aa3201",
        "aa400032",
        "aaa90b0101",
        "aaae0104646464640000",
        "aaa50164010203640102036401020364010203",
    ):
        decoded = decode_status_frame(frame(prefix), "H6099")
        assert decoded is not None
        domains.add(decoded.domain)
    assert domains == profile.read_domains
    monkeypatch.setitem(
        MODEL_PROFILES,
        "H7001",
        replace(
            profile,
            name="Software-only video reuse",
            status_grammar="test-h6099-video-status",
        ),
    )
    monkeypatch.setitem(_STATUS_ROOTS, "test-h6099-video-status", ("test-h6099-video-status", H6099StatusReply))
    assert build_black_border(True, "H7001") == build_black_border(True, "H6099")
    assert build_subordinate_query(0x21, "H7001") == frame("aa21")
    assert decode_status_frame(frame("aaa90b0101"), "H7001") is not None
    with pytest.raises(ValueError):
        build_black_border(True, "H6199")


@pytest.mark.parametrize(
    ("version", "state"),
    [
        (None, "evidence_gap"),
        ("malformed", "evidence_gap"),
        ("1.00.10", "unsupported"),
        ("1.00.11", "supported"),
        ("2.00.00", "supported"),
    ],
)
async def test_border_only_gate_and_physical_recheck(version, state) -> None:
    device = coordinator(version)
    states = video_control_states(device.profile, device)
    assert states["black_border"] == state
    assert all(
        value == "supported"
        for key, value in states.items()
        if key not in {"black_border", "whole_relative_brightness", "hdr_contrast"}
    )
    validate_video_request(device, content())
    compiled = compile_video_profile(LibraryItem.new("Video only", content()), "H6099")
    writer = AsyncMock()
    await async_apply_compiled_profile(device, compiled, writer=writer, verify=False)
    assert writer.await_count == 1
    border = replace(content(), black_border=True)
    if state != "supported":
        with pytest.raises(ValueError, match="black_border"):
            validate_video_request(device, border)
        with pytest.raises(ValueError, match="black_border"):
            await apply_black_border(device, True, writer=writer)
        assert writer.await_count == 1
    else:

        async def disconnected(packet, *, write_guard, **kwargs):
            device.subordinate_21_version = None
            device._confirmed_identity_fields.discard("subordinate_21_version")
            write_guard()

        with pytest.raises(ValueError, match="black_border"):
            await apply_black_border(device, True, writer=disconnected)
        assert not hasattr(device, "black_border")


def test_h66a0_hdr_exact_wire_and_public_contract() -> None:
    profile = get_profile("H66A0")
    assert profile.supports_hdr_contrast
    assert profile.video_hdr_contrast_min == 1
    assert profile.video_hdr_contrast_max == 4
    assert video_control_states(profile, SimpleNamespace())["hdr_contrast"] == "supported"
    assert build_hdr_contrast_query("H66A0") == frame("aaa911")
    video_settings = MODEL_EFFECT_CATALOGUES["H66A0"].to_dict(profile=profile)["video_settings"]
    assert isinstance(video_settings, list)
    assert "hdr_contrast" in video_settings
    for enabled in (False, True):
        for contrast in (1, 4):
            packet = build_hdr_contrast(enabled, contrast, "H66A0")
            assert packet == frame(f"33a91102{int(enabled):02x}{contrast:02x}")
            parsed = parse_command(packet, "H66A0")
            assert parsed is not None
            assert parsed.body.setting == 17
            assert bool(parsed.body.payload.is_enabled) is enabled
            assert parsed.body.payload.contrast == contrast
            require_profile_packet(packet, profile)
            decoded = decode_status_frame(frame(f"aaa91102{int(enabled):02x}{contrast:02x}"), "H66A0")
            assert decoded is not None
            assert bool(decoded.generated.body.payload.is_enabled) is enabled
            assert decoded.generated.body.payload.contrast == contrast
    authored = VideoProfile(
        "H66A0",
        "movie",
        None,
        100,
        False,
        50,
        None,
        None,
        None,
        hdr_enabled=True,
        hdr_contrast=4,
    )
    compiled = compile_video_profile(LibraryItem.new("HDR", authored), "H66A0")
    assert compiled.hdr == (True, 4)
    round_trip = effect_content_from_dict(effect_content_to_dict(authored))
    assert round_trip == authored
    with pytest.raises(EffectValidationError, match="both"):
        replace(authored, hdr_contrast=None)
    with pytest.raises(EffectValidationError, match="hdr_contrast"):
        replace(authored, hdr_contrast=5)
    with pytest.raises(ValueError, match="does not support"):
        build_hdr_contrast(True, 2, "H6099")


def test_hdr_codec_is_selected_by_profile_capability(monkeypatch) -> None:
    monkeypatch.setitem(
        MODEL_PROFILES,
        "H7001",
        replace(get_profile("H6099"), name="HDR shared-route fixture", supports_hdr_contrast=True),
    )
    assert build_hdr_contrast(False, 3, "H7001") == frame("33a911020003")
    assert build_hdr_contrast_query("H7001") == frame("aaa911")
    require_profile_packet(build_hdr_contrast(False, 3, "H7001"), MODEL_PROFILES["H7001"])
    require_profile_packet(build_hdr_contrast_query("H7001"), MODEL_PROFILES["H7001"])


async def test_h66a0_hdr_observation_write_and_recovery(hass, monkeypatch) -> None:
    device = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H66A0", configuration_url="test")
    device._client = MagicMock(is_connected=True)
    device._notify_callback(None, bytearray(frame("aaa911020104")))
    assert device.hdr_enabled is True
    assert device.hdr_contrast == 4
    captured = device.capture_effect_control_state()
    assert captured.hdr_enabled is True
    assert captured.hdr_contrast == 4
    assert PriorControlState.from_dict(captured.to_dict()).hdr_contrast == 4

    writer = AsyncMock()
    await apply_hdr_contrast(device, False, 2, writer=writer, verify=False)
    writer_call = writer.await_args
    assert writer_call is not None
    assert writer_call.args[0] == frame("33a911020002")
    assert writer_call.kwargs["state_values"] == {"hdr_enabled": False, "hdr_contrast": 2}

    device.hdr_enabled, device.hdr_contrast = False, 1
    restore = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "custom_components.ha_govee_led_ble.coordinator_recovery.apply_hdr_contrast",
        restore,
    )
    permitted, complete = await device._restore_video_controls(
        replace(captured, mode="colour", video_restore_controls=("hdr_contrast",))
    )
    assert permitted == {"hdr_contrast"}
    assert complete is True
    restore.assert_awaited_once_with(device, True, 4)


async def test_policy_edit_toggle_retention_and_race() -> None:
    device = coordinator("1.00.11")

    async def refresh(_request):
        for field in (
            "blank_screen_detection",
            "blank_screen_low_brightness_duration_seconds",
            "blank_screen_same_tone_duration_seconds",
        ):
            device._field_revisions[field] = device._field_revisions.get(field, 0) + 1
        return True

    device.refresh_state.side_effect = refresh
    writer = AsyncMock()
    await apply_blank_screen(device, True, writer=writer)
    assert writer.call_args.args[0] == build_blank_screen(True, "H6099", 2, 10, 120)
    assert writer.call_args.kwargs["state_values"] == {"blank_screen": True}
    device.blank_screen_detection = 1
    with pytest.raises(ValueError, match="policy changed"):
        writer.call_args.kwargs["write_guard"]()
    device.blank_screen_detection = None
    await apply_blank_screen(device, False, policy=(1, 300, 600), writer=writer)
    assert writer.call_args.args[0] == frame("33a90a0600012c015802")
    assert writer.call_args.kwargs["expected_values"] == {
        "blank_screen": False,
        "blank_screen_detection": 1,
        "blank_screen_low_brightness_duration_seconds": 300,
        "blank_screen_same_tone_duration_seconds": 600,
    }
    device.refresh_state.assert_awaited_with(RefreshRequest(blank_screen=False, blank_screen_policy=(1, 300, 600)))
    with pytest.raises(ValueError, match="not been read"):
        await apply_blank_screen(device, True, writer=writer)


def test_h8604_video_registers_preserve_exact_wire_and_readback(hass) -> None:
    profile = device_profile("H8604", 2, 1)
    sensitivity = build_video_sensitivity(42, "H8604", profile=profile)
    hdmi_input = build_hdmi_input(4, "H8604", profile=profile)
    box_light = build_hdmi_box_light(True, 10, True, 1, "H8604", profile=profile)
    calibration = build_video_color_calibration((10, 20, 30), "H8604", profile=profile)
    red_calibration = build_video_color_calibration((10, 20, 30, 40), "H8604", profile=profile)
    sensitivity_query = build_video_sensitivity(None, "H8604", profile=profile)
    hdmi_query = build_hdmi_input(None, "H8604", profile=profile)
    box_light_query = build_hdmi_box_light_query("H8604", profile=profile)
    calibration_query = build_video_color_calibration(None, "H8604", profile=profile)

    assert sensitivity == frame("33a901012a")
    assert hdmi_input == frame("33a9030104")
    assert box_light == frame("33b6010a0001")
    assert calibration == frame("33a905030a141e")
    assert red_calibration == frame("33a905040a141e28")
    assert sensitivity_query == frame("aaa901")
    assert hdmi_query == frame("aaa903")
    assert box_light_query == frame("aa0708")
    assert calibration_query == frame("aaa905")
    for packet in (
        sensitivity,
        hdmi_input,
        box_light,
        calibration,
        red_calibration,
        sensitivity_query,
        hdmi_query,
        box_light_query,
        calibration_query,
    ):
        require_profile_packet(packet, profile)
    for packet in (sensitivity, hdmi_input, box_light, calibration, red_calibration):
        assert parse_command(packet, "H8604", profile=profile) is not None
    for invalid in (0, 5):
        with pytest.raises(ValueError, match="outside"):
            build_hdmi_input(invalid, "H8604", profile=profile)
    assert decode_status_frame(frame("aaa9030200f0"), "H8604", profile=profile) is None

    device = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H8604", configuration_url=None)
    device.pact_type, device.pact_code = 2, 1
    device._resolve_device_profile()
    device._notify_callback(None, bytearray(frame("aaa901012a")))
    device._notify_callback(None, bytearray(frame("aaa9030203f0")))
    device._notify_callback(None, bytearray(frame("aaa905040a141e28")))
    device._notify_callback(None, bytearray(frame("aa0708000e010a0001000001020300")))
    assert device.video_sensitivity == 42
    assert device.video_hdmi_input == 3
    assert device.video_hdmi_inputs_connected == (True, True, True, True)
    assert device.boolean_control_state == {
        "left_bar_enabled": True,
        "middle_enabled": True,
        "right_bar_enabled": True,
    }
    assert (
        device.hdmi_box_light,
        device.hdmi_box_brightness,
        device.hdmi_box_automatic,
        device.hdmi_box_effect,
    ) == (True, 10, True, 1)
    assert device.video_color_calibration == (10, 20, 30, 40)
    assert device._field_revisions["video_sensitivity"] == 1
    assert device._field_revisions["video_hdmi_input"] == 1
    assert device._field_revisions["video_color_calibration"] == 1


async def test_h8604_final_observer_reads_each_requested_video_setting(hass) -> None:
    device = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H8604", configuration_url=None)
    device.pact_type, device.pact_code = 2, 1
    device._resolve_device_profile()
    responses = {
        build_video_sensitivity(None, "H8604", profile=device.profile): frame("aaa901012a"),
        build_hdmi_input(None, "H8604", profile=device.profile): frame("aaa9030203f0"),
        build_hdmi_box_light_query("H8604", profile=device.profile): frame("aa0708000e010a0001000001020300"),
        build_video_color_calibration(None, "H8604", profile=device.profile): frame("aaa905040a141e28"),
    }
    packets: list[bytes] = []

    async def write_gatt_char(_uuid, packet, **_kwargs):
        packet = bytes(packet)
        packets.append(packet)
        device._notify_callback(None, bytearray(responses[packet]))

    device._client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=write_gatt_char))
    device._notification_token = object()
    expected = {
        "video_sensitivity": 42,
        "video_hdmi_input": 3,
        "hdmi_box_light": True,
        "hdmi_box_brightness": 10,
        "hdmi_box_automatic": True,
        "hdmi_box_effect": 1,
        "video_color_calibration": (10, 20, 30, 40),
    }

    assert await device.async_observe_effect(expected, timeout=0.1) is True
    assert packets == list(responses)


def test_h8604_video_template_uses_one_based_hdmi_inputs() -> None:
    content = next(
        template.content
        for template in MODEL_EFFECT_CATALOGUES["H8604"].templates
        if isinstance(template.content, VideoProfile)
    )
    assert content.hdmi_input == 1
    assert replace(content, hdmi_input=4).hdmi_input == 4
    with pytest.raises(EffectValidationError):
        replace(content, hdmi_input=0)


def test_h8604_video_softness_preserves_exact_declared_range() -> None:
    profile = device_profile("H8604", 2, 1)
    packet = build_video_mode(
        "movie",
        False,
        50,
        False,
        0,
        "H8604",
        profile=profile,
    )
    assert packet == frame("330500000832000200")
    decoded = decode_status_frame(frame("aa0500000832000200"), "H8604", profile=profile)
    assert decoded is not None
    assert (
        parse_color_mode(
            decoded.generated,
            "H8604",
            profile=profile,
        ).video_sound_effects_softness
        == 0
    )

    for invalid in (-1, 100):
        with pytest.raises(ValueError, match="softness"):
            build_video_mode(
                "movie",
                False,
                50,
                False,
                invalid,
                "H8604",
                profile=profile,
            )
    invalid_status = decode_status_frame(frame("aa0500000832000264"), "H8604", profile=profile)
    assert invalid_status is not None
    with pytest.raises(ValueError, match="softness"):
        parse_color_mode(
            invalid_status.generated,
            "H8604",
            profile=profile,
        )


def test_h8604_static_reply_observes_gradual(hass) -> None:
    device = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H8604", configuration_url=None)
    device.profile = device_profile("H8604", 2, 1)

    device._notify_callback(None, bytearray(frame("aa05150107d0")))

    assert device.color_mode is ParsedMode.COLOUR
    assert device.color_temp_kelvin == 2000
    assert device.static_gradual is True


def test_h8604_hdmi_reply_is_atomic_and_connectivity_expires(hass) -> None:
    device = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H8604", configuration_url=None)
    device.profile = device_profile("H8604", 2, 1)
    device.video_hdmi_input = 2
    device.video_hdmi_inputs_connected = (False, False, False, False)
    device._expected_state["video_hdmi_input"] = (2, float("inf"))
    reply = bytearray(frame("aaa9030203f0"))

    device._notify_callback(None, reply)
    assert device.video_hdmi_input == 2
    assert device.video_hdmi_inputs_connected == (False, False, False, False)
    assert "video_hdmi_inputs_connected" not in device._field_revisions

    device._expected_state.clear()
    device._notify_callback(None, reply)
    assert device.video_hdmi_input == 3
    assert device.video_hdmi_inputs_connected == (True, True, True, True)

    client = MagicMock()
    device._client = client
    device._clear_client_state(client)
    assert device.video_hdmi_inputs_connected is None


async def test_h8604_red_calibration_recovery_fails_closed_without_qualified_identity(hass, monkeypatch) -> None:
    device = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H8604", configuration_url=None)
    device.profile = device_profile("H8604", 2, 1)
    device.subordinate_20_version = "2.02.10"
    device.subordinate_21_version = "2.01.11"
    state = PriorControlState(
        mode="video",
        is_on=True,
        brightness_pct=50,
        rgb_color=(255, 255, 255),
        video_color_calibration=(10, 20, 30, 40),
        video_restore_controls=("color_calibration", "color_calibration_red"),
    )
    writer = AsyncMock()
    monkeypatch.setattr(
        "custom_components.ha_govee_led_ble.coordinator_recovery.apply_video_color_calibration",
        writer,
    )

    permitted, complete = await device._restore_video_controls(state)

    assert not complete
    assert "color_calibration" not in permitted
    assert "color_calibration_red" not in permitted
    writer.assert_not_awaited()


@pytest.mark.parametrize(
    ("subordinate_20", "subordinate_21", "red_state"),
    [
        (None, None, "evidence_gap"),
        ("2.02.10", "2.01.11", "unsupported"),
        ("2.02.11", "2.01.10", "unsupported"),
        ("2.02.11", "2.01.11", "supported"),
    ],
)
def test_h8604_colour_calibration_red_is_revision_qualified(subordinate_20, subordinate_21, red_state) -> None:
    identity = SimpleNamespace(
        subordinate_20_version=subordinate_20,
        subordinate_21_version=subordinate_21,
    )
    states = video_control_states(get_profile("H8604"), identity)
    assert states["color_calibration"] == "supported"
    assert states["color_calibration_red"] == red_state
    assert states["video_sensitivity"] == "supported"
    assert states["hdmi_input"] == "supported"
    assert states["hdmi_box_light"] == "supported"


async def test_h8604_video_registers_use_shared_guarded_writer() -> None:
    confirmed = {"subordinate_20_version", "subordinate_21_version"}
    writer = AsyncMock()
    device = SimpleNamespace(
        _control_arbiter=BLEControlArbiter(),
        _confirmed_identity_fields=confirmed,
        identity_fields_confirmed=lambda fields: fields <= confirmed,
        _ensure_connected=AsyncMock(),
        model="H8604",
        profile=device_profile("H8604", 2, 1),
        subordinate_20_version="2.02.11",
        subordinate_21_version="2.01.11",
        _lock=asyncio.Lock(),
        _client=MagicMock(is_connected=True),
        _notification_token=object(),
        _authorization_generation=0,
    )

    assert await apply_video_sensitivity(device, 42, writer=writer, verify=False)
    assert await apply_hdmi_input(device, 4, writer=writer, verify=False)
    assert await apply_hdmi_box_light(device, (True, 10, True, 1), writer=writer, verify=False)
    assert await apply_video_color_calibration(device, (10, 20, 30, 40), writer=writer, verify=False)
    assert [call.args[0] for call in writer.await_args_list] == [
        frame("33a901012a"),
        frame("33a9030104"),
        frame("33b6010a0001"),
        frame("33a905040a141e28"),
    ]
    assert writer.await_args_list[0].kwargs["state_values"] == {"video_sensitivity": 42}
    assert writer.await_args_list[1].kwargs["state_values"] == {"video_hdmi_input": 4}
    assert writer.await_args_list[2].kwargs["state_values"] == {
        "hdmi_box_light": True,
        "hdmi_box_brightness": 10,
        "hdmi_box_automatic": True,
        "hdmi_box_effect": 1,
    }
    assert writer.await_args_list[3].kwargs["state_values"] == {"video_color_calibration": (10, 20, 30, 40)}


def test_optional_fields_hash_observation_and_recovery() -> None:
    legacy = content()
    assert "black_border" not in effect_content_to_dict(legacy)
    edited = replace(
        legacy,
        black_border=False,
        blank_screen=True,
        blank_screen_detection=1,
        blank_screen_low_brightness_duration_seconds=300,
        blank_screen_same_tone_duration_seconds=600,
    )
    assert effect_content_from_dict(effect_content_to_dict(edited)) == edited
    compiled = compile_video_profile(LibraryItem.new("Edited", edited), "H6099")
    assert compiled.blank_screen_policy == (1, 300, 600) and compiled.progress_total == 3
    expected, confidence = compiled_observation(compiled)
    assert confidence.value == "settings_match"
    assert expected is not None and expected["black_border"] is False
    assert expected["blank_screen_low_brightness_duration_seconds"] == 300
    different = compile_video_profile(LibraryItem.new("Edited", replace(edited, blank_screen_detection=2)), "H6099")
    assert different.artifact_sha256 != compiled.artifact_sha256
    for template in MODEL_EFFECT_CATALOGUES["H6099"].templates:
        if isinstance(template.content, VideoProfile):
            assert template.content.black_border is None
    # Persisted preview snapshots keep policy and border without becoming observations.
    prior = PriorControlState(
        mode="video",
        is_on=True,
        brightness_pct=50,
        rgb_color=(255, 255, 255),
        black_border=False,
        blank_screen=True,
        blank_screen_detection=1,
        blank_screen_low_brightness_duration_seconds=300,
        blank_screen_same_tone_duration_seconds=600,
        video_restore_controls=("black_border", "blank_screen"),
    )
    assert PriorControlState.from_dict(prior.to_dict()) == prior


@pytest.mark.parametrize(
    "changes",
    [
        {"blank_screen_detection": 1},
        {"blank_screen": True, "blank_screen_detection": 1},
        {"black_border": 1},
        {
            "blank_screen": True,
            "blank_screen_detection": 3,
            "blank_screen_low_brightness_duration_seconds": 1,
            "blank_screen_same_tone_duration_seconds": 1,
        },
        {
            "blank_screen": True,
            "blank_screen_detection": 1,
            "blank_screen_low_brightness_duration_seconds": -1,
            "blank_screen_same_tone_duration_seconds": 1,
        },
    ],
)
def test_reject_invalid_profile(changes) -> None:
    with pytest.raises(EffectValidationError):
        replace(content(), **changes)


@pytest.mark.parametrize("policy", [(0, 1, 1), (True, 1, 1), (1, -1, 1), (1, 65536, 1), (1, 1, False)])
def test_reject_invalid_wire_policy(policy) -> None:
    with pytest.raises(ValueError):
        build_blank_screen(True, "H6099", *policy)


async def test_h6099_condition_identity_is_connection_scoped(hass, monkeypatch) -> None:
    device = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6099", configuration_url="test")
    device._notify_callback(None, bytearray(frame("aa20312e30302e3030")))
    device._notify_callback(None, bytearray(frame("aa21312e30302e3131")))
    assert device.subordinate_20_version == "1.00.00"
    assert video_control_states(device.profile, device)["black_border"] == "supported"

    async def reconnect(*args, **kwargs):
        assert device.subordinate_21_version == "1.00.11"
        assert not device.identity_fields_confirmed(frozenset({"subordinate_21_version"}))
        raise BleakError("offline")

    monkeypatch.setattr("custom_components.ha_govee_led_ble.coordinator.async_establish_ble_connection", reconnect)
    with pytest.raises(BleakError):
        await device._ensure_connected()
    assert device.subordinate_21_version == "1.00.11"
    assert not device.identity_fields_confirmed(frozenset({"subordinate_21_version"}))
    assert video_control_states(device.profile, device)["black_border"] == "supported"
    validate_video_request(device, content())


@pytest.mark.parametrize("model,minimum", [("H6099", 1), ("H6199", 0), ("H8604", 1)])
async def test_saturation_range_at_every_write_entry(hass, monkeypatch, model, minimum) -> None:
    profile = get_profile(model)
    assert profile.video_saturation_min == minimum
    device = GoveeBLECoordinator(hass, "11:22:33:44:55:66", model, configuration_url="test")
    device._client = MagicMock(is_connected=True)
    if model == "H6199":
        from tests.test_h6199_capabilities import set_qualified_identity

        set_qualified_identity(device)
    elif model == "H8604":
        device.pact_type, device.pact_code = 2, 1
        device._resolve_device_profile()
    device.is_on = False
    writer = AsyncMock()
    monkeypatch.setattr(device, "async_write_effect_sequence", writer)
    light = GoveeBLELight(device)
    monkeypatch.setattr(light, "_async_supersede_preview", AsyncMock())
    monkeypatch.setattr(light, "_notify_state_changed", lambda: None)
    monkeypatch.setattr(light, "_refresh_with_retry", AsyncMock(return_value=True))
    authored = replace(content(), model=model, saturation=minimum)
    compiled = compile_video_profile(LibraryItem.new("Saturation", authored), model)
    parsed = parse_command(build_video_mode("movie", True, minimum, False, 50, model), model)
    assert parsed is not None and parsed.body.detail.saturation == minimum
    if minimum:
        with pytest.raises(ValueError, match="saturation"):
            build_video_mode("movie", True, 0, False, 50, model)
        with pytest.raises(EffectValidationError, match="saturation"):
            replace(authored, saturation=0)
        with pytest.raises(ValueError, match="saturation"):
            await apply_active_video_mode(device, mode="movie", requested_values={"saturation": 0}, writer=writer)
        with pytest.raises(ValueError, match="saturation"):
            await async_apply_compiled_profile(device, replace(compiled, saturation=0), writer=writer, verify=False)
        device.video_saturation = 0
        with pytest.raises(ValueError, match="saturation"):
            await light.async_turn_on(effect="Video: Movie", brightness=50)
        light._async_supersede_preview.assert_not_awaited()
        writer.assert_not_awaited()
        assert device.is_on is False and not device._expected_state
    else:

        async def write(packets, **kwargs):
            vars(device).update(kwargs.get("state_values") or {})

        writer.side_effect = write
        monkeypatch.setattr(device, "refresh_state", AsyncMock(return_value=True))
        monkeypatch.setattr(
            device, "async_prepare_static_baseline", AsyncMock(return_value=_known_static_baseline(device))
        )
        device.video_saturation = 0
        await light.async_turn_on(effect="Video: Movie")
        written = [parse_command(packet, model) for call in writer.await_args_list for packet in call.args[0]]
        video = [item for item in written if item is not None and type(item.body).__name__ == "ModeBody"]
        assert len(video) == 1
        assert video[0].body.detail.saturation == 0
    catalogue = MODEL_EFFECT_CATALOGUES[model]
    controls = catalogue.to_dict()["video_controls"]
    assert isinstance(controls, dict) and controls["saturation_min"] == minimum
    assert all(
        template.content.saturation == (100 if minimum else 50)
        for template in catalogue.templates
        if isinstance(template.content, VideoProfile)
    )


def test_effective_saturation_minimum_is_not_a_model_allowlist() -> None:
    authored = replace(content(), model="H6199", saturation=0)
    item = LibraryItem.new("Old range", authored)
    profile = replace(get_profile("H6199"), video_saturation_min=1)
    with pytest.raises(ValueError, match="saturation"):
        compile_video_profile(item, "H6199", profile=profile)
    with pytest.raises(ValueError, match="saturation"):
        validate_video_request(SimpleNamespace(profile=profile), authored)


@pytest.mark.parametrize("model,accepted", [("H6099", False), ("H6199", True)])
def test_zero_saturation_readback_keeps_sibling_video_fields(hass, model, accepted) -> None:
    packet = frame("aa0500010800010237" if model == "H6099" else "aa05000001000137")
    decoded = decode_status_frame(packet, model)
    assert decoded is not None
    parsed = parse_color_mode(decoded.generated, model)
    assert parsed.mode is ParsedMode.VIDEO and parsed.video_mode == "game"
    assert parsed.video_saturation == (0 if accepted else None)
    device = GoveeBLECoordinator(hass, "11:22:33:44:55:66", model, configuration_url="test")
    device._notify_callback(None, bytearray(packet))
    assert device.video_mode == "game" and device.video_full_screen is False
    assert device.video_sound_effects is True
    assert device.video_saturation == (0 if accepted else 100)
    assert ("video_saturation" in device._field_revisions) is accepted
    assert device._field_revisions["video_mode"] > 0
