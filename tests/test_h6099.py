"""Exact H6099 APK hypotheses, not physical device qualification."""

from unittest.mock import patch

import pytest
from homeassistant.config_entries import current_entry
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_govee_led_ble.const import (
    DOMAIN,
    MUSIC_MODE_SLUGS,
    ReadDomain,
    SupportQuality,
    get_profile,
    resolve_model,
    supported_effect_categories,
)
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_expectations import expectations_from_packet
from custom_components.ha_govee_led_ble.coordinator_status import (
    ParsedMode,
    decode_status_frame,
    parse_color_mode,
)
from custom_components.ha_govee_led_ble.effect_catalogue import MODEL_EFFECT_CATALOGUES
from custom_components.ha_govee_led_ble.effect_compiler import compile_effect
from custom_components.ha_govee_led_ble.effect_contracts import (
    CapabilityWorkflow,
    PhysicalValidationState,
    VerificationConfidence,
    release_capabilities_for_model,
    require_effect_route,
)
from custom_components.ha_govee_led_ble.effect_domain import BuiltinScene, LibraryItem, PaletteDiyEffect
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_blank_screen,
    build_blank_screen_query,
    build_brightness,
    build_brightness_query,
    build_camera_health_query,
    build_colour_mode_query,
    build_firmware_query,
    build_h6099_diy_activation,
    build_hardware_query,
    build_installation_direction_query,
    build_music_mode,
    build_power,
    build_power_query,
    build_relative_brightness,
    build_relative_brightness_query,
    build_scene_activation,
    build_segment_query,
    build_subordinate_query,
    build_video_mode,
    build_white_balance,
    build_white_balance_query,
    parse_a3_effect_envelope,
    parse_command,
    parse_command_ack_result,
)
from custom_components.ha_govee_led_ble.layered_scene import CatalogueRef
from custom_components.ha_govee_led_ble.light_commands import (
    build_color_rgb,
    build_color_temp,
    build_segment_brightness,
    build_segment_color,
    parse_static_write,
)
from custom_components.ha_govee_led_ble.music_commands import prepare_music_request
from custom_components.ha_govee_led_ble.native_scenes import build_native_scene_packets
from custom_components.ha_govee_led_ble.scenes import SCENE_ENTRIES
from custom_components.ha_govee_led_ble.transport import reassemble_a3, xor_checksum


def frame(prefix: str) -> bytes:
    body = bytes.fromhex(prefix).ljust(19, b"\0")
    assert len(body) == 19
    return body + bytes((xor_checksum(body),))


def test_exact_profile_and_truthful_effect_authorization() -> None:
    profile = get_profile("H6099")
    assert profile.support_quality is SupportQuality.EXPERIMENTAL
    assert profile.command_grammar == profile.status_grammar == profile.video_grammar == "H6099"
    assert profile.segment_count == 14 and profile.segment_group_count == 4
    assert profile.whole_device_mask == 0x3FFF
    assert profile.physical_ic_count is None and profile.music_variants
    assert profile.scene_catalogue_sku == "H6099" and profile.legacy_scene_catalogue_sku is None
    assert profile.effect_readback == "diy_code_only"
    assert len(SCENE_ENTRIES["H6099"]) == 240
    assert resolve_model("H6098") is None
    assert supported_effect_categories("H6099") == ("video", "scenes", "effects", "reactive")
    assert profile.supports_custom_effects and not profile.supports_advanced_effects
    assert MODEL_EFFECT_CATALOGUES["H6099"].effects
    capabilities = release_capabilities_for_model("H6099")
    assert {cap.workflow for cap in capabilities} == {
        CapabilityWorkflow.NATIVE_SCENES,
        CapabilityWorkflow.NATIVE_MUSIC,
        CapabilityWorkflow.VIDEO,
        CapabilityWorkflow.PAINTED,
        CapabilityWorkflow.SINGLE,
        CapabilityWorkflow.MULTI,
    }
    assert all(cap.physical_validation_state is PhysicalValidationState.NOT_VALIDATED for cap in capabilities)
    assert all(cap.verification_confidence is VerificationConfidence.UNVERIFIED for cap in capabilities)
    for workflow in (CapabilityWorkflow.ADVANCED, CapabilityWorkflow.PALETTE_DIY, CapabilityWorkflow.WORKSHOP):
        with pytest.raises(ValueError, match="not supported"):
            require_effect_route("H6099", workflow)


def test_static_writes_kelvin_readback_and_diy_selector() -> None:
    assert build_power(True, "H6099") == frame("330101")
    assert build_brightness(42, "H6099") == frame("33042a")
    rgb = build_color_rgb(1, 2, 3, "H6099")
    assert rgb == frame("330515010102030000000000ff3f")
    parsed_write = parse_static_write(rgb, "H6099")
    assert parsed_write is not None and parsed_write.whole_strip and parsed_write.rgb == (1, 2, 3)
    kelvin_write = parse_static_write(build_color_temp(4500, "H6099"), "H6099")
    assert kelvin_write is not None and kelvin_write.kelvin == 4500 and kelvin_write.whole_strip
    assert expectations_from_packet(rgb, "H6099")["color_temp_kelvin"] is None
    assert build_segment_color([14], 1, 2, 3, "H6099") == frame("3305150101020300000000000020")
    assert build_segment_brightness([14], 42, "H6099") == frame("330515022a0020")
    with pytest.raises(ValueError):
        build_segment_color([15], 1, 2, 3, "H6099")
    for kelvin in (0, 2000, 4500, 9000):
        decoded = decode_status_frame(frame(f"aa051501{kelvin:04x}"), "H6099")
        assert decoded is not None
        parsed = parse_color_mode(decoded.generated, "H6099")
        assert parsed.mode is ParsedMode.COLOUR and parsed.color_temp_kelvin == (kelvin or None)
        assert parsed.rgb_color is None and parsed.multi_effect_flag == 1
    bad = decode_status_frame(frame("aa0515010001"), "H6099")
    assert bad is not None
    with pytest.raises(ValueError, match="Kelvin"):
        parse_color_mode(bad.generated, "H6099")
    diy = build_h6099_diy_activation(0x1234)
    assert diy == frame("33050a3412")
    assert expectations_from_packet(diy, "H6099")["color_mode"] == (ParsedMode.DIY, 0x1234)
    decoded = decode_status_frame(frame("aa050a3412"), "H6099")
    assert decoded is not None
    parsed = parse_color_mode(decoded.generated, "H6099")
    assert parsed.mode is ParsedMode.DIY and parsed.diy_code == 0x1234
    assert build_scene_activation("H6099", 0x1234) == frame("3305043412")


def test_native_catalogue_uses_exact_upload_root() -> None:
    assert require_effect_route("H6099", CapabilityWorkflow.NATIVE_SCENES) == "H6099"
    for scene in SCENE_ENTRIES["H6099"]:
        packets = build_native_scene_packets("H6099", scene)
        selected = parse_command(packets[-1], "H6099")
        assert selected is not None and selected.body.detail.scene_id == scene.code
        if len(packets) > 1:
            parsed = parse_a3_effect_envelope(reassemble_a3(packets[:-1]), "H6099")
            assert int(parsed.kind) == scene.scene_type
    with pytest.raises(ValueError, match="invalid H6099"):
        parse_a3_effect_envelope(bytes.fromhex("010205") + bytes(31), "H6099")
    scene = SCENE_ENTRIES["H6099"][0]
    compiled = compile_effect(
        LibraryItem.new("H6099 scene", BuiltinScene(CatalogueRef("H6099", scene.scene_id, scene.effect_id))),
        "H6099",
    )
    assert compiled.selector_kind == "scene"
    assert compiled.packets == tuple(build_native_scene_packets("H6099", scene))
    with pytest.raises(ValueError, match="not supported"):
        compile_effect(
            LibraryItem.new("Unqualified DIY", PaletteDiyEffect("H6099", 0, 0, 50, ((1, 2, 3),))),
            "H6099",
        )


def test_video_scalar_calibration_topology_and_ack() -> None:
    packet = build_video_mode("game", False, 42, True, 55, "H6099")
    assert packet == frame("33050001082a010237")
    expected = expectations_from_packet(packet, "H6099")
    assert expected["video_mode"] == "game" and expected["video_sound_effects_softness"] == 55
    decoded = decode_status_frame(frame("aa050001082a010237"), "H6099")
    assert decoded is not None
    parsed = parse_color_mode(decoded.generated, "H6099")
    assert parsed.video_mode == "game" and parsed.video_full_screen is False
    assert parsed.video_saturation == 42 and parsed.video_sound_effects_softness == 55
    assert get_profile("H6099").video_white_balance_calibration[49] == (50,)
    assert build_white_balance(50, None, "H6099") == frame("33a9060132")
    assert build_relative_brightness(10, 20, 30, 40, "H6099") == frame("33ae01040a141e280000")
    assert build_blank_screen(True, "H6099") == frame("33a90a0601020a007800")
    assert parse_command_ack_result(frame("33a900"), "H6099").parsed is not None
    assert parse_command_ack_result(frame("33a901"), "H6099").parsed is None


def test_music_selectors_do_not_inherit_omitted_fields() -> None:
    profile = get_profile("H6099")
    assert len(profile.music_modes) == 11
    for slug in profile.music_modes:
        code = MUSIC_MODE_SLUGS[slug]
        packets = prepare_music_request("H6099", slug, 42, None, False, {})
        assert len(packets) == (4 if slug in {"bloom", "shiny"} else 2)
        assert packets[-1] == frame(f"330513{code:02x}2a")
        # Deliberately nonzero tail: absent new fields must not become observations.
        decoded = decode_status_frame(frame(f"aa0513{code:02x}2a0101010203"), "H6099")
        assert decoded is not None
        parsed = parse_color_mode(decoded.generated, "H6099")
        assert parsed.music_mode == slug and parsed.music_sensitivity == 42
        if code >= 0x30:
            assert parsed.music_calm is None and parsed.music_color is None and not parsed.music_color_present
            expected = expectations_from_packet(packets[-1], "H6099")
            assert "music_calm" not in expected and "music_color" not in expected
        else:
            assert parsed.music_color_present and parsed.music_color == (1, 2, 3)
    with pytest.raises(ValueError):
        prepare_music_request("H6099", "hopping", 42, None, False, {"hopping_brightness": 50})
    assert build_music_mode(0x03, 42, None, True, "H6099") == frame("330513032a01")


def test_declared_query_and_complete_status_root_coverage() -> None:
    queries = (
        (build_power_query("H6099"), "aa0100"),
        (build_brightness_query("H6099"), "aa0400"),
        (build_colour_mode_query("H6099"), "aa0501"),
        (build_firmware_query("H6099"), "aa0600"),
        (build_hardware_query("H6099"), "aa0703"),
        (build_subordinate_query(0x20, "H6099"), "aa20"),
        (build_subordinate_query(0x21, "H6099"), "aa21"),
        (build_installation_direction_query("H6099"), "aa30"),
        (build_camera_health_query("H6099"), "aa32"),
        (build_white_balance_query("H6099"), "aaa906"),
        (build_blank_screen_query("H6099"), "aaa90a"),
        (build_relative_brightness_query("H6099"), "aaae01"),
    )
    for packet, prefix in queries:
        assert packet == frame(prefix)
    replies = (
        "aa0101",
        "aa042a",
        "aa0515011194",
        "aa06312e30302e3131",
        "aa0703312e30302e3030",
        "aa20312e30332e3030",
        "aa21312e30302e3333",
        "aa3002",
        "aa3201",
        "aaa9060132",
        "aaae0104646464640000",
        "aaa50164010203640102036401020364010203",
    )
    domains = set()
    for prefix in replies:
        decoded = decode_status_frame(frame(prefix), "H6099")
        assert decoded is not None
        domains.add(decoded.domain)
    assert domains == get_profile("H6099").read_domains
    assert ReadDomain.OTHER not in domains
    for group, count in ((1, 4), (2, 4), (3, 4), (4, 2)):
        assert build_segment_query(group, "H6099") == frame(f"aaa5{group:02x}")
        decoded = decode_status_frame(frame(f"aaa5{group:02x}" + "64010203" * 4), "H6099")
        assert decoded is not None and len(decoded.generated.body.segments) == count
        if group == 4:
            assert decoded.generated.body.unused == [100, 1, 2, 3] * 2
    with pytest.raises(ValueError):
        build_segment_query(5, "H6099")


def test_coordinator_consumes_exact_read_domains(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="11:22:33:44:55:66")
    entry.add_to_hass(hass)
    with current_entry.set(entry):
        coordinator = GoveeBLECoordinator(hass, entry.unique_id, "H6099", configuration_url="http://example.test")
    with patch.object(coordinator, "async_set_updated_data"):
        for prefix in (
            "aa0101",
            "aa042a",
            "aa0515011194",
            "aa06312e30302e3131",
            "aa0703312e30302e3030",
            "aa20312e30332e3030",
            "aa21312e30302e3333",
            "aaa9060132",
            "aaae01040a141e280000",
        ):
            coordinator._notify_callback(None, bytearray(frame(prefix)))
        for group in range(1, 5):
            coordinator._notify_callback(None, bytearray(frame(f"aaa5{group:02x}" + "64010203" * 4)))
        assert coordinator.is_on and coordinator.brightness_pct == 42
        assert coordinator.color_temp_kelvin == 4500
        assert coordinator.white_balance_scalar == 50
        assert coordinator.relative_brightness_bottom == 40
        assert coordinator.fw_version == "1.00.11" and coordinator.hw_version == "1.00.00"
        assert coordinator.subordinate_20_version == "1.03.00" and coordinator.subordinate_21_version == "1.00.33"
        assert len(coordinator.segment_colors) == 14
        coordinator.music_color = (9, 8, 7)
        coordinator._notify_callback(None, bytearray(frame("aa0513332a0101010203")))
        assert coordinator.music_color == (9, 8, 7)
        coordinator._notify_callback(None, bytearray(frame("aa0515010000")))
        assert coordinator.color_temp_kelvin == 4500
