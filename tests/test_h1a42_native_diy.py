"""Exact H1A42 native RGBIC preset admission and wire contracts."""

from dataclasses import replace
from typing import Any, cast

import pytest

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, device_profile
from custom_components.ha_govee_led_ble.effect_catalogue import resolve_catalogue_template
from custom_components.ha_govee_led_ble.effect_catalogue_registry import MODEL_EFFECT_CATALOGUES
from custom_components.ha_govee_led_ble.effect_compiler import CompiledEffect, compile_application
from custom_components.ha_govee_led_ble.effect_contracts import CapabilityWorkflow, frontend_release_capabilities
from custom_components.ha_govee_led_ble.effect_domain import LayeredEffect, LibraryItem
from custom_components.ha_govee_led_ble.layered_scene_decoder import encode_workshop_effect
from custom_components.ha_govee_led_ble.protocol_admission import require_profile_packet
from custom_components.ha_govee_led_ble.transport import reassemble_a3

PRESET_IDS = (501, 502, 504, 505, 506)
EFFECTIVE_PROFILES = (
    device_profile("H1A42", None, None),
    device_profile("H1A42", 1, 1),
    device_profile("H1A42", 10, 1),
)
EXPECTED_BODIES = {
    501: (
        "031a00000001000132320100000002fa00010000ff000000000000002300020a050001ff3201c8000002fa0a04"
        "ff0000ffff000000ff8b00ff000000000000012000021e0a0001ff3201c8000001fa0a03ff7f0000ff0000"
        "ffff00000000000002"
    ),
    502: (
        "021a00020f010001ff0001c8323202c832010000ff000000000000011a00020f010001ff3201c8141402c83201ff000000000000000000"
    ),
    504: (
        "0320200100020201ff0a0200000000fa6403ff000000ff008b00ff0000fa1001fd001d240100020201ff0a"
        "0200000000fa6402ff7f000000ff0000fa1001fd001d270100020201ff0a0200000000fa6402ffff0000ffff"
        "0000fa1001fd00"
    ),
    505: (
        "02260002140a0201ffc800f0000001f00005ff0000ffffffff000000ff000000ff0000ff1001f0011a0001"
        "000000011414000000000000320100000000000000000000"
    ),
    506: (
        "042300020f050001ff0002ff323202ff0204ff0000ffff000000ff8b00ff0000001201fa002000020f050001"
        "ff0002ff323202ff0203ff7f0000ff0000ffff0000001201fa001d500100060001ff0000ff323202640002"
        "00ffffff7f001400ff000000001d550100060001ff0000ff323202640002ff00000000ff1600ff00000000"
    ),
}


@pytest.mark.parametrize("profile", EFFECTIVE_PROFILES)
def test_h1a42_presets_resolve_compile_and_admit(profile) -> None:
    catalogue = MODEL_EFFECT_CATALOGUES["H1A42"]
    native_templates = {
        template.content.native_diy
        for template in catalogue.templates_for_profile(profile)
        if isinstance(template.content, LayeredEffect) and template.content.native_diy is not None
    }
    assert native_templates == set(PRESET_IDS)
    assert not catalogue.advanced_create
    capabilities = cast(list[dict[str, Any]], frontend_release_capabilities("H1A42", profile=profile))
    assert {capability["id"] for capability in capabilities} >= {
        "native_scenes",
        "advanced",
    }

    admission_profile = replace(profile, command_operations=frozenset({"effect_upload", "scene"}))
    for preset_id in PRESET_IDS:
        template = resolve_catalogue_template("H1A42", f"template:native-diy:{preset_id}", profile=profile)
        assert isinstance(template.content, LayeredEffect)
        assert template.content.native_diy == preset_id
        expected_body = bytes.fromhex(EXPECTED_BODIES[preset_id])
        assert encode_workshop_effect("H617A", template.content, profile=profile) == expected_body
        compiled = compile_application(LibraryItem.new(template.label, template.content), "H1A42", profile=profile)
        assert isinstance(compiled, CompiledEffect)
        assembled = reassemble_a3(compiled.upload_packets)
        assert assembled[:3] == bytes((1, len(compiled.upload_packets), 2))
        assert assembled[3 : 3 + len(expected_body)] == expected_body
        assert compiled.activation_packet == bytes.fromhex(
            {
                501: "330504f5010000000000000000000000000000c6",
                502: "330504f6010000000000000000000000000000c5",
                504: "330504f8010000000000000000000000000000cb",
                505: "330504f9010000000000000000000000000000ca",
                506: "330504fa010000000000000000000000000000c9",
            }[preset_id]
        )
        for packet in compiled.packets:
            require_profile_packet(packet, profile)
            require_profile_packet(packet, admission_profile)


def test_h1a42_preset_geometry_defaults_and_frontend_ceiling() -> None:
    profile = MODEL_PROFILES["H1A42"]
    catalogue = MODEL_EFFECT_CATALOGUES["H1A42"]
    assert profile.physical_ic_count == 12
    meteor = resolve_catalogue_template("H1A42", "template:native-diy:504", profile=profile).content
    bloom = resolve_catalogue_template("H1A42", "template:native-diy:506", profile=profile).content
    assert isinstance(meteor, LayeredEffect) and all(layer.selection.quantity == 2 for layer in meteor.layers)
    assert isinstance(bloom, LayeredEffect)
    assert [layer.selection.quantity for layer in bloom.layers[2:]] == [6, 6]

    payload = cast(dict[str, Any], catalogue.to_dict(profile=profile))
    assert payload["advanced_create"] is False
    assert payload["supports"]["advanced"] == "supported"
    assert payload["supports"]["workshop"] == "unsupported"
    assert payload["apply"]["workshop"] == "unsupported"
    assert CapabilityWorkflow.ADVANCED.value in {workflow["id"] for workflow in payload["workflows"]}

    with pytest.raises(ValueError):
        compile_application(
            LibraryItem.new("Unrestricted", replace(meteor, native_diy=None)),
            "H1A42",
            profile=profile,
        )
