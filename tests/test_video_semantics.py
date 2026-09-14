"""Synthetic declarations prove reuse, not qualification of physical devices."""

from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, ModelProfile, ReadDomain
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.effect_compiler import compile_video_profile
from custom_components.ha_govee_led_ble.effect_deployments import ObservationConfidence, PriorControlState
from custom_components.ha_govee_led_ble.effect_domain import (
    LibraryItem,
    RelativeBrightness,
    VideoProfile,
    effect_content_from_dict,
    effect_content_to_dict,
)
from custom_components.ha_govee_led_ble.effect_runtime import async_apply_compiled_profile, compiled_observation
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    _STATUS_ROOTS,
    H6199StatusReply,
    build_relative_brightness,
    build_white_balance,
    parse_command,
)
from custom_components.ha_govee_led_ble.h6199_calibration import WHITE_BALANCE_POSITIONS
from custom_components.ha_govee_led_ble.transport import xor_checksum


def alternate(monkeypatch: pytest.MonkeyPatch) -> ModelProfile:
    profile = ModelProfile(
        "Synthetic scalar/six-zone video",
        command_grammar="H6199",
        status_grammar="test-video-status",
        video_grammar="H6199",
        supports_video_mode=True,
        video_modes=("movie", "game"),
        supports_white_balance=True,
        supports_relative_brightness=True,
        video_white_balance_representation="scalar",
        video_white_balance_min=0,
        video_white_balance_max=2,
        video_white_balance_default=1,
        video_white_balance_calibration=((90,), (100,), (110,)),
        video_brightness_zones=("left", "top", "right", "bottom", "strip_left", "strip_right"),
        read_domains=frozenset(
            {ReadDomain.POWER, ReadDomain.COLOUR_MODE, ReadDomain.DISPLAY_SETTING, ReadDomain.RELATIVE_BRIGHTNESS}
        ),
    )
    monkeypatch.setitem(MODEL_PROFILES, "H7000", profile)
    monkeypatch.setitem(_STATUS_ROOTS, "test-video-status", ("test-video-status", H6199StatusReply))
    return profile


def reply(command: bytes) -> bytearray:
    frame = bytearray(command)
    frame[0] = 0xAA
    frame[-1] = xor_checksum(frame[:-1])
    return frame


async def test_alternate_roundtrip_writer_parser_observation_and_recovery(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = alternate(monkeypatch)
    content = VideoProfile(
        "H7000",
        "movie",
        None,
        None,
        None,
        None,
        None,
        RelativeBrightness(10, 20, 30, 40, 50, 60),
        None,
        white_balance_value=2,
    )
    raw = effect_content_to_dict(content)
    assert effect_content_from_dict(raw) == content
    item = LibraryItem.new("Synthetic", content)
    compiled = compile_video_profile(item, "H7000")
    assert compiled.white_balance_wire == (110,)
    assert compiled.relative_brightness == (10, 20, 30, 40, 50, 60)
    assert compiled.progress_total == 3
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H7000", configuration_url="test")
    coordinator.is_on = True
    packets: list[bytes] = []

    async def write(packet: bytes) -> None:
        packets.append(packet)

    await async_apply_compiled_profile(coordinator, compiled, writer=write, verify=False)
    assert packets[1] == build_white_balance(110, None, "H7000")
    assert packets[2] == build_relative_brightness(10, 20, 30, 40, "H7000", 50, 60)
    white = parse_command(packets[1], "H7000")
    brightness = parse_command(packets[2], "H7000")
    assert white is not None and white.body.payload.value == 110
    assert brightness is not None and brightness.body.strip_right_percent == 60
    for packet in packets[1:]:
        coordinator._notify_callback(None, reply(packet))
    expected, confidence = compiled_observation(compiled)
    assert expected is not None
    assert confidence is ObservationConfidence.SETTINGS_MATCH
    for field, value in expected.items():
        if field not in {"is_on", "video_mode"}:
            assert getattr(coordinator, field) == value
            assert coordinator._field_revisions[field] == 1
    coordinator._client = MagicMock(is_connected=True)
    monkeypatch.setattr(coordinator, "_send_state_queries", AsyncMock(return_value=True))
    assert await coordinator.async_observe_effect(expected, timeout=0.001) is None

    # Only a fresh scalar reply does not establish the missing six zones or mode.
    async def scalar_only(**kwargs: object) -> bool:
        coordinator._notify_callback(None, reply(packets[1]))
        return True

    monkeypatch.setattr(coordinator, "_send_state_queries", scalar_only)
    assert await coordinator.async_observe_effect(expected, timeout=0.001) is None
    prior = coordinator.capture_effect_control_state()
    assert PriorControlState.from_dict(prior.to_dict()) == prior
    send = AsyncMock()
    monkeypatch.setattr(coordinator, "send_command", send)
    monkeypatch.setattr(coordinator, "refresh_state", AsyncMock(return_value=True))
    await coordinator.async_restore_effect_control_state(replace(prior, is_on=False), overwritten_diy_code=None)
    writes = [call.args[0] for call in send.await_args_list]
    assert packets[1] in writes and packets[2] in writes
    unavailable = replace(profile, read_domains=frozenset({ReadDomain.POWER, ReadDomain.COLOUR_MODE}))
    assert compiled_observation(compiled, profile=unavailable)[1] is ObservationConfidence.MODE_MATCH
    assert "H6099" not in MODEL_PROFILES


async def test_legacy_calibration_hash_and_omitted_registers(hass: HomeAssistant) -> None:
    content = VideoProfile("H6199", "movie", True, 50, False, 50, 17, RelativeBrightness(100, 100, 100, 100), False)
    raw = effect_content_to_dict(content)
    assert "white_balance_value" not in raw
    item = LibraryItem.new("Legacy", content)
    assert LibraryItem.new("Legacy", effect_content_from_dict(raw)).content_hash == item.content_hash
    compiled = compile_video_profile(item, "H6199")
    assert compiled.white_balance_wire == WHITE_BALANCE_POSITIONS[16]
    assert build_white_balance(*compiled.white_balance_wire, "H6199") == bytes.fromhex(
        "33a900030110030000000000000000000000008b"
    )
    omitted = replace(content, white_balance_position=None, relative_brightness=None, blank_screen=None)
    compiled = compile_video_profile(LibraryItem.new("Omitted", omitted), "H6199")
    expected, _ = compiled_observation(compiled)
    assert expected is not None and not any(
        key.startswith(("white_balance", "relative_brightness", "blank_screen")) for key in expected
    )
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url="test")
    coordinator.is_on = True
    writer = AsyncMock()
    await async_apply_compiled_profile(coordinator, compiled, writer=writer, verify=False)
    assert writer.await_count == 1
    assert coordinator.white_balance_red is None
