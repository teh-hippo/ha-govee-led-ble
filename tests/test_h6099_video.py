"""H6099 APK video evidence and requested-only firmware gating, not owner qualification."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from bleak.exc import BleakError
from homeassistant.exceptions import HomeAssistantError

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, ReadDomain, get_profile
from custom_components.ha_govee_led_ble.control_arbiter import BLEControlArbiter
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
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
    _STATUS_ROOTS,
    H6099StatusReply,
    build_black_border,
    build_black_border_query,
    build_blank_screen,
    build_subordinate_query,
    build_video_mode,
    parse_command,
)
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.native_profile_controls import (
    apply_active_video_mode,
    apply_black_border,
    apply_blank_screen,
)
from custom_components.ha_govee_led_ble.video_applicability import validate_video_request, video_control_states
from tests.test_h6099 import frame


def content() -> VideoProfile:
    return VideoProfile("H6099", "movie", True, 50, False, 50, None, None, None)


def coordinator(version: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        _control_arbiter=BLEControlArbiter(),
        model="H6099",
        profile=get_profile("H6099"),
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
        _blank_screen_notification_revision=0,
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
    assert all(value == "supported" for key, value in states.items() if key != "black_border")
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
            write_guard()

        with pytest.raises(ValueError, match="black_border"):
            await apply_black_border(device, True, writer=disconnected)
        assert not hasattr(device, "black_border")


async def test_policy_edit_toggle_retention_and_race() -> None:
    device = coordinator()

    async def refresh(**kwargs):
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
    device.refresh_state.assert_awaited_with(expected_blank_screen=False, expected_blank_screen_policy=(1, 300, 600))
    with pytest.raises(ValueError, match="not been read"):
        await apply_blank_screen(device, True, writer=writer)


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
        assert device.subordinate_21_version is None
        raise BleakError("offline")

    monkeypatch.setattr("custom_components.ha_govee_led_ble.coordinator.async_establish_ble_connection", reconnect)
    with pytest.raises(BleakError):
        await device._ensure_connected()
    assert device.subordinate_21_version is None
    assert video_control_states(device.profile, device)["black_border"] == "evidence_gap"
    validate_video_request(device, content())


@pytest.mark.parametrize("model,minimum", [("H6099", 1), ("H6199", 0)])
async def test_saturation_range_at_every_write_entry(hass, monkeypatch, model, minimum) -> None:
    profile = get_profile(model)
    assert profile.video_saturation_min == minimum
    device = GoveeBLECoordinator(hass, "11:22:33:44:55:66", model, configuration_url="test")
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
        with pytest.raises(HomeAssistantError):
            await light._async_set_video_mode("movie", saturation=0)
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
        await light._async_set_video_mode("movie", saturation=0)
        assert writer.await_count == 2
        assert device.video_saturation == 0
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
