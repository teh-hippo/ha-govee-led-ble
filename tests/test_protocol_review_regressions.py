"""Software wire/persistence regressions, not additional hardware qualification."""

from dataclasses import replace

import pytest

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, MUSIC_MODE_SLUGS
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_status import parse_color_mode
from custom_components.ha_govee_led_ble.effect_deployments import PriorControlState
from custom_components.ha_govee_led_ble.effect_domain import EffectValidationError, RelativeBrightness
from custom_components.ha_govee_led_ble.effect_persistence_validation import EffectStorageError
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    _check_tree,
    _write,
    build_black_border,
    build_blank_screen,
    build_h6199_control,
    build_music_mode,
    build_relative_brightness,
    build_white_balance,
    parse_command,
    parse_command_ack_result,
    parse_status,
)
from custom_components.ha_govee_led_ble.transport import xor_checksum


def frame(prefix):
    body = bytes.fromhex(prefix).ljust(19, b"\0")
    return body + bytes((xor_checksum(body),))


@pytest.mark.parametrize("opcode,control", [("30", "strip_direction"), ("31", "camera_position"), ("a3", "gradient")])
def test_control_command_preserves_unknown_tail(opcode, control):
    packet = frame(f"33{opcode}01abcd")
    parsed = parse_command(packet, "H6199")
    assert parsed.body.unknown_tail == bytes.fromhex("abcd") + bytes(14)
    assert parsed.body._io.is_eof()
    _check_tree(parsed)
    assert _write(parsed, 20) == packet
    for value in (0, 1):
        assert build_h6199_control(control, value) == frame(f"33{opcode}{value:02x}")


@pytest.mark.parametrize(
    "model,setting,write_payload,reply_payload",
    [
        ("H6199", "00", "011003", "011003001505"),
        ("H6199", "06", "32", "32"),
        ("H6199", "0a", "010234127856", "010234127856"),
        ("H6099", "06", "32", "32"),
        ("H6099", "0a", "010234127856", "010234127856"),
        ("H6099", "0b", "01", "01"),
    ],
)
def test_display_payload_extensions_round_trip(model, setting, write_payload, reply_payload):
    for header, payload, parser in (("33", write_payload, parse_command), ("aa", reply_payload, parse_status)):
        size = len(bytes.fromhex(payload))
        for extension in ("", "abcd"):
            length = size + len(bytes.fromhex(extension))
            # Keep the established H6199 reply-padding constraint, testing opaque bytes inside len.
            outer_tail = "" if header == "aa" and model == "H6199" else "fedc"
            packet = frame(f"{header}a9{setting}{length:02x}{payload}{extension}{outer_tail}")
            parsed = parser(packet, model)
            assert parsed.body.payload.unknown_tail == bytes.fromhex(extension)
            assert parsed.body.payload._io.is_eof() and parsed.body._io.is_eof()
            _check_tree(parsed)
            assert _write(parsed, 20) == packet
        assert parser(frame(f"{header}a9{setting}{size - 1:02x}{payload}"), model) is None
        assert parser(frame(f"{header}a9{setting}ff{payload}"), model) is None


@pytest.mark.parametrize("model,prefix", [("H6199", "aa0500010032003207abcd"), ("H6099", "aa050000093200023207abcd")])
def test_video_reply_tail_is_opaque(model, prefix):
    packet = frame(prefix)
    parsed = parse_status(packet, model)
    assert parsed.body.detail.unknown_tail.startswith(bytes.fromhex("07abcd"))
    assert parsed.body.detail._io.is_eof()
    _check_tree(parsed)
    assert _write(parsed, 20) == packet


@pytest.mark.parametrize("model", ["H6199", "H6099"])
def test_authored_display_tails_keep_existing_wire_bytes(model):
    white = build_white_balance(21, 5, model, flag=0) if model == "H6199" else build_white_balance(50, None, model)
    assert white == frame("33a90003001505" if model == "H6199" else "33a9060132")
    blank = build_blank_screen(True, model, 2, 0x1234, 0x5678)
    assert blank == frame("33a90a06010234127856")
    packets = [white, blank]
    if model == "H6099":
        border = build_black_border(True, model)
        assert border == frame("33a90b0101")
        packets.append(border)
    for packet in packets:
        parsed = parse_command(packet, model)
        assert parsed.body.payload.unknown_tail == b""
        assert parsed.body.unknown_tail == bytes(15 - parsed.body.len)


def test_h6099_direction_ack_is_not_a_state_observation(hass):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6099", configuration_url=None)
    coordinator.installation_direction = 4
    packet = frame("333000abcd")
    parsed = parse_command_ack_result(packet, "H6099").parsed
    assert parsed.opcode.name == "installation_direction" and parsed.status == 0
    assert parsed.unknown_tail.startswith(bytes.fromhex("abcd"))
    _check_tree(parsed)
    assert _write(parsed, 20) == packet
    coordinator._notify_callback(None, bytearray(packet))
    assert coordinator.packet_log[-1]["reason"] == "command_ack_parsed"
    assert coordinator.installation_direction == 4 and not coordinator._field_revisions
    assert parse_command_ack_result(frame("333001"), "H6099").parsed is None


@pytest.mark.parametrize("model", ["H6199", "H6099"])
@pytest.mark.parametrize("value", [0, 100])
def test_observed_relative_brightness_persists_and_reencodes(hass, model, value):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", model, configuration_url=None)
    packet = build_relative_brightness(value, value, value, value, model)
    coordinator._notify_callback(None, bytearray(frame("aa" + packet[1:-1].hex())))
    state = coordinator.capture_effect_control_state()
    restored = PriorControlState.from_dict(state.to_dict())
    assert restored == state and restored.relative_brightness == value
    assert (
        build_relative_brightness(
            restored.relative_brightness_left,
            restored.relative_brightness_top,
            restored.relative_brightness_right,
            restored.relative_brightness_bottom,
            model,
        )
        == packet
    )
    extended = replace(state, relative_brightness_strip_left=value, relative_brightness_strip_right=value)
    assert PriorControlState.from_dict(extended.to_dict()) == extended
    for field in (
        "relative_brightness",
        *(f"relative_brightness_{zone}" for zone in ("left", "top", "right", "bottom", "strip_left", "strip_right")),
    ):
        for invalid in (-1, 101, True):
            with pytest.raises(EffectStorageError):
                replace(state, **{field: invalid})
    with pytest.raises(EffectValidationError):
        RelativeBrightness(0, 100, 100, 100)


@pytest.mark.parametrize("model,code", [("H6199", 0x30), ("H6199", 0xFF), ("H6099", 0xFF), ("H617A", 0xFF)])
@pytest.mark.parametrize("prior", ["aa050afe00", "aa0504e8fd", "aa0513033200012060a0", "video"])
def test_unknown_music_rejected_before_any_state_mutation(hass, model, code, prior):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", model, configuration_url=None)
    coordinator.is_on = True
    if prior == "video":
        if model == "H617A":
            pytest.skip("H617A has no video readback")
        prior = "aa0500000932000232" if model == "H6099" else "aa05000100320032"
    coordinator._notify_callback(None, bytearray(frame(prior)))
    before = (
        coordinator.capture_effect_control_state(),
        coordinator.color_mode,
        dict(coordinator._field_revisions),
        dict(coordinator._domain_revisions),
    )
    packet = frame(f"aa0513{code:02x}3200012060a0")
    parsed = parse_status(packet, model)
    assert parsed is not None
    with pytest.raises(ValueError, match="music selector"):
        parse_color_mode(parsed, model)
    coordinator._notify_callback(None, bytearray(packet))
    assert coordinator.packet_log[-1]["reason"] == "semantic_rejected"
    assert (
        coordinator.capture_effect_control_state(),
        coordinator.color_mode,
        coordinator._field_revisions,
        coordinator._domain_revisions,
    ) == before


@pytest.mark.parametrize("model", ["H6199", "H6099", "H617A"])
def test_supported_music_selector_still_decodes(model):
    for slug in MODEL_PROFILES[model].music_modes:
        packet = build_music_mode(MUSIC_MODE_SLUGS[slug], 50, None, False, model)
        parsed = parse_status(frame("aa" + packet[1:-1].hex()), model)
        assert parse_color_mode(parsed, model).music_mode == slug
