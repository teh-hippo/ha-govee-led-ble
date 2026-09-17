"""H6102 APK hypotheses and profile-directed shared codecs, not app captures."""

from dataclasses import replace

import pytest

from custom_components.ha_govee_led_ble.const import ModelProfile, ReadDomain, get_profile
from custom_components.ha_govee_led_ble.coordinator_expectations import expectations_from_packet
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode, decode_status_frame, parse_color_mode
from custom_components.ha_govee_led_ble.effect_commands import build_h617a_diy_single
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    ProtocolParseRejection,
    build_boolean_control,
    build_boolean_control_query,
    build_brightness,
    build_brightness_query,
    build_colour_mode_query,
    build_firmware_query,
    build_h617a_diy_activation,
    build_hardware_query,
    build_power,
    build_power_query,
    build_scene_activation,
    build_segment_query,
    parse_a3_effect_envelope,
    parse_boolean_control,
    parse_command_ack_result,
    parse_command_result,
    parse_status_result,
    require_profile_packet,
    upload_ack_subtype,
    upload_ack_success,
)
from custom_components.ha_govee_led_ble.light_commands import (
    build_color_rgb,
    build_color_temp,
    build_segment_brightness,
    build_segment_color,
    parse_static_write,
)
from custom_components.ha_govee_led_ble.scenes import MODEL_SCENES
from custom_components.ha_govee_led_ble.transport import fragment_a3, reassemble_a3, xor_checksum


def _frame(prefix: str) -> bytes:
    body = bytes.fromhex(prefix).ljust(19, b"\x00")
    assert len(body) == 19
    return body + bytes([xor_checksum(body)])


def test_modern_commands_use_shared_grammar_and_exact_scene_catalogue() -> None:
    assert get_profile("H6102").command_grammar == "H617A"
    assert len(MODEL_SCENES["H6102"]) == 240
    for packet, opcode in (
        (build_power(True, "H6102"), "power"),
        (build_brightness(50, "H6102"), "brightness"),
        (build_color_rgb(32, 64, 96, "H6102"), "multi"),
        (build_scene_activation("H6102", 0x1234), "multi"),
        (build_h617a_diy_activation(0x5678), "multi"),
    ):
        result = parse_command_result(packet, "H6102")
        assert result.rejection is None and result.parser == "command_write"
        assert result.parsed is not None
        assert result.parsed.opcode.name == opcode
    assert build_color_rgb(32, 64, 96, "H6102") == _frame("330515012040600000000000ff7f")
    assert build_scene_activation("H6102", 0x1234) == _frame("3305043412")
    envelope = reassemble_a3(build_h617a_diy_single(0, 0, 50, [(32, 64, 96)]))
    diy = parse_a3_effect_envelope(envelope, "H6102")
    assert diy.family == 0 and diy.body.speed == 50


def test_complete_status_root_covers_exact_profile_and_preserves_unused_slots() -> None:
    frames = {
        ReadDomain.POWER: _frame("aa0101"),
        ReadDomain.BRIGHTNESS: _frame("aa0432"),
        ReadDomain.COLOUR_MODE: _frame("aa0515010fa0"),
        ReadDomain.FIRMWARE: _frame("aa06332e30322e303200"),
        ReadDomain.HARDWARE: _frame("aa0703332e30312e303100"),
        ReadDomain.SEGMENTS: _frame("aaa505000000006420406032aabbccdeadbeef"),
    }
    assert get_profile("H6102").read_domains <= frames.keys()
    for domain, packet in frames.items():
        result = parse_status_result(packet, "H6102")
        assert result.rejection is None and result.parser == "h6102_status_reply"
        decoded = decode_status_frame(packet, "H6102")
        assert decoded is not None and decoded.domain == domain
    generated = parse_status_result(frames[ReadDomain.SEGMENTS], "H6102").parsed
    assert generated is not None
    page = generated.body
    assert page.group == 5 and len(page.segments) == 3
    assert page.segments[0].brightness == 0  # Off/black is a meaningful record.
    assert page.unused == [0xDE, 0xAD, 0xBE, 0xEF]
    assert parse_status_result(frames[ReadDomain.SEGMENTS], "H617A").rejection is ProtocolParseRejection.SCHEMA_REJECTED
    for group in range(1, 6):
        assert build_segment_query(group, "H6102") == _frame(f"aaa5{group:02x}")
    for group in (0, 6):
        assert parse_status_result(_frame(f"aaa5{group:02x}"), "H6102").rejection is not None


def test_status_retains_kelvin_gradual_identity_and_unknown_modes() -> None:
    for flag in (0, 1):
        result = parse_status_result(_frame(f"aa0515{flag:02x}0fa0dead"), "H6102")
        assert result.parsed is not None
        mode = parse_color_mode(result.parsed, "H6102")
        assert mode.mode is ParsedMode.COLOUR
        assert mode.color_temp_kelvin == 4000 and mode.multi_effect_flag == flag
        assert result.parsed.body.mode_body.unknown_tail.startswith(b"\xde\xad")
        generated = parse_status_result(_frame(f"aaa3{flag:02x}fe"), "H6102").parsed
        assert generated is not None
        gradual = generated.body
        assert gradual.flag == flag and gradual.unknown_tail.startswith(b"\xfe")
    for prefix, expected in (("aa06332e30322e303200", "3.02.02"), ("aa0703312e30302e303300", "1.00.03")):
        generated = parse_status_result(_frame(prefix), "H6102").parsed
        assert generated is not None and generated.body.text == expected
    for prefix, expected_mode, field, value in (
        ("aa05043412ab", ParsedMode.SCENE, "scene_code", 0x1234),
        ("aa050a7856ab", ParsedMode.DIY, "diy_code", 0x5678),
    ):
        generated = parse_status_result(_frame(prefix), "H6102").parsed
        assert generated is not None
        semantic = parse_color_mode(generated, "H6102")
        assert semantic.mode is expected_mode and getattr(semantic, field) == value
        assert generated.body.mode_body.unknown_tail.startswith(b"\xab")
    unknown = parse_status_result(_frame("aa05ee1234"), "H6102").parsed
    assert unknown is not None
    assert unknown.body.mode_body.startswith(b"\x12\x34")
    assert parse_color_mode(unknown, "H6102").mode is ParsedMode.UNKNOWN


def test_effective_profile_reaches_builders_parsers_and_expectations() -> None:
    # Independent context: an unknown SKU can use declared codecs without a SKU allowlist.
    profile = replace(get_profile("H6102"), whole_device_mask=0x0007, segment_count=3)
    packet = build_color_rgb(32, 64, 96, "H9901", profile=profile)
    assert packet == _frame("3305150120406000000000000700")
    static = parse_static_write(packet, "H9901", profile=profile)
    assert static is not None and static.whole_strip and static.rgb == (32, 64, 96)
    assert expectations_from_packet(packet, "H9901", profile=profile)["rgb_color"] == (32, 64, 96)
    assert parse_command_result(packet, "H9901").rejection is ProtocolParseRejection.UNSUPPORTED_MODEL
    generated = parse_status_result(_frame("aa0101"), "H9901", profile=profile).parsed
    assert generated is not None and generated.body.is_on == 1
    assert build_segment_color([3], 1, 2, 3, "H9901", profile=profile) == _frame("3305150101020300000000000400")
    kelvin = parse_static_write(build_color_temp(4000, "H9901", profile=profile), "H9901", profile=profile)
    assert kelvin is not None and kelvin.kelvin == 4000 and kelvin.kelvin_companion_rgb is not None
    restricted = replace(profile, command_operations=frozenset({"power", "brightness"}), effect_grammar=None)
    require_profile_packet(build_power(True, "H9901", profile=restricted), restricted)
    require_profile_packet(build_brightness(50, "H9901", profile=restricted), restricted)
    with pytest.raises(ValueError, match="does not support"):
        require_profile_packet(packet, restricted)
    envelope = reassemble_a3(build_h617a_diy_single(0, 0, 50, [(32, 64, 96)]))
    with pytest.raises(ValueError, match="no generated A3"):
        parse_a3_effect_envelope(envelope, "H9901", profile=restricted)


def test_shared_queries_keep_default_and_expose_apk_selector() -> None:
    profile = get_profile("H6102")
    for builder, prefix in (
        (build_power_query, "aa01"),
        (build_brightness_query, "aa04"),
        (build_firmware_query, "aa06"),
        (build_hardware_query, "aa0703"),
    ):
        assert builder("H9901", profile=profile) == _frame(prefix)
    assert build_colour_mode_query("H6102") == _frame("aa0500")
    assert build_colour_mode_query("H6102", selector=1) == _frame("aa0501")
    restricted = replace(profile, command_operations=frozenset({"power", "brightness"}))
    for selector in (0, 1):
        require_profile_packet(build_colour_mode_query("H9901", profile=restricted, selector=selector), restricted)
    with pytest.raises(ValueError, match="selector"):
        build_colour_mode_query("H6102", selector=2)


@pytest.mark.parametrize(("control", "opcode"), [("gradual", "a3"), ("limit", "0e")])
def test_boolean_register_contract(control: str, opcode: str) -> None:
    profile = ModelProfile(
        "Synthetic boolean controls",
        command_grammar="H617A",
        status_grammar="H6102",
        command_operations=frozenset({"power", "brightness"}),
        boolean_controls=frozenset({"gradual", "limit"}),
    )
    for enabled in (False, True):
        packet = build_boolean_control(control, enabled, "H9901", profile=profile)
        assert packet == _frame(f"33{opcode}{int(enabled):02x}")
        require_profile_packet(packet, profile)
        query = build_boolean_control_query(control, "H9901", profile=profile)
        assert query == _frame(f"aa{opcode}")
        require_profile_packet(query, profile)
        generated = parse_status_result(_frame(f"aa{opcode}{int(enabled):02x}dead"), profile=profile).parsed
        assert generated is not None and generated.body.unknown_tail.startswith(b"\xde\xad")
        assert parse_boolean_control(generated, "H9901", profile=profile) == {control: enabled}
        disabled = replace(profile, boolean_controls=frozenset())
        assert parse_boolean_control(generated, "H9901", profile=disabled) == {}
        with pytest.raises(ValueError, match="does not support"):
            build_boolean_control(control, enabled, "H9901", profile=disabled)
        with pytest.raises(ValueError, match="does not support"):
            build_boolean_control_query(control, "H9901", profile=disabled)
        for denied in (packet, query):
            with pytest.raises(ValueError, match="does not support"):
                require_profile_packet(denied, disabled)
    with pytest.raises(ValueError, match="requires a boolean"):
        build_boolean_control(control, 1, "H6102")
    generated = parse_status_result(_frame(f"aa{opcode}02"), "H6102").parsed
    assert generated is not None
    with pytest.raises(ValueError, match="0 or 1"):
        parse_boolean_control(generated, "H6102")
    # Neither AA05's gradual flag nor an ordinary ACK confirms the register.
    for generated in (
        parse_status_result(_frame("aa0515010fa0"), "H6102").parsed,
        parse_command_ack_result(_frame(f"33{opcode}00"), "H6102").parsed,
    ):
        assert generated is not None and parse_boolean_control(generated, "H6102") == {}


def test_static_operation_gate_does_not_grant_other_multi_commands() -> None:
    profile = replace(
        get_profile("H6102"),
        command_operations=frozenset({"power", "brightness", "static"}),
        effect_grammar=None,
        boolean_controls=frozenset(),
    )
    for packet in (
        build_color_rgb(1, 2, 3, "H6102", profile=profile),
        build_color_temp(4000, "H6102", profile=profile),
        build_segment_brightness([2, 4], 50, "H6102", profile=profile),
        _frame("33051503" + "32" * 15),
    ):
        require_profile_packet(packet, profile)
    for packet in (
        build_scene_activation("H6102", 402),
        build_h617a_diy_activation(800),
        _frame("3305130332"),
        _frame("330515ff"),  # Unknown static operation is not authorized.
        _frame("3305ee"),
        _frame("33a300"),
        _frame("330e01"),
        *build_h617a_diy_single(0, 0, 50, [(1, 2, 3)]),
    ):
        with pytest.raises(ValueError, match="does not support"):
            require_profile_packet(packet, profile)


@pytest.mark.parametrize("subtype", [2, 3, 4, 0x41])
def test_shared_upload_ack_offsets_and_positive_result(subtype: int) -> None:
    profile = get_profile("H6102")
    packets = fragment_a3(subtype, bytes(18))
    assert upload_ack_subtype(packets, len(packets) - 1, "H9901", profile=profile) == subtype
    for success in (False, True):
        # Music's byte 2 is deliberately opposite to status at byte 3.
        payload = f"{int(success):02x}{int(not success):02x}" if subtype == 0x41 else f"{int(not success):02x}a5"
        result = parse_command_ack_result(_frame(f"a3{subtype:02x}{payload}"), "H9901", profile=profile)
        assert result.parsed is not None and result.parser == "h617a_command_ack"
        assert upload_ack_success(result.parsed, subtype) is success
        assert upload_ack_success(result.parsed, subtype + 1) is None
    ordinary = parse_command_ack_result(_frame(f"33{subtype:02x}00"), "H6102").parsed
    assert ordinary is not None and upload_ack_success(ordinary, subtype) is None
    with pytest.raises(ValueError, match="complete A3"):
        upload_ack_subtype(packets, len(packets) - 2, "H6102")


def test_native_and_advanced_diy_share_layered_upload_syntax() -> None:
    from custom_components.ha_govee_led_ble.effect_catalogue import resolve_catalogue_template
    from custom_components.ha_govee_led_ble.effect_compiler import CompiledEffect, compile_application
    from custom_components.ha_govee_led_ble.effect_domain import LayeredEffect, LibraryItem

    for code in range(501, 508):
        content = resolve_catalogue_template("H6102", f"template:native-diy:{code}").content
        assert isinstance(content, LayeredEffect)
        for selector, effect in ((code, content), (402, replace(content, native_diy=None))):
            compiled = compile_application(LibraryItem.new("Synthetic protocol check", effect), "H6102")
            assert isinstance(compiled, CompiledEffect)
            assert compiled.activation_packet == build_scene_activation("H6102", selector)
            assert upload_ack_subtype(compiled.upload_packets, len(compiled.upload_packets) - 1, "H6102") == 2
            parsed = parse_a3_effect_envelope(reassemble_a3(compiled.upload_packets), "H6102")
            assert len(parsed.records) == len(content.layers)
