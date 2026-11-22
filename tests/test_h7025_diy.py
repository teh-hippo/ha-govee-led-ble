"""H7025 native 0x58 DIY catalogue and transport contracts."""

from dataclasses import replace

import pytest

from custom_components.ha_govee_led_ble.const import get_profile
from custom_components.ha_govee_led_ble.effect_catalogue import MODEL_EFFECT_CATALOGUES
from custom_components.ha_govee_led_ble.effect_catalogue_models import CatalogueTemplate
from custom_components.ha_govee_led_ble.effect_compiler import CompiledEffect, compile_application
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem, NativeEffect, SingleEffect
from custom_components.ha_govee_led_ble.effect_protocol_decoder import decode_effect_frames
from custom_components.ha_govee_led_ble.effect_runtime import _validate_diy_slot_approval
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_diy_activation,
    parse_command_ack_result,
    upload_ack_success,
)
from custom_components.ha_govee_led_ble.h7025_effects import encode_h7025_diy, validate_h7025_diy
from custom_components.ha_govee_led_ble.native_effect import NativeDiyLayer
from custom_components.ha_govee_led_ble.protocol_admission import require_profile_packet
from custom_components.ha_govee_led_ble.protocol_effect_bodies import upload_ack_subtype
from custom_components.ha_govee_led_ble.transport import reassemble_a3, xor_checksum

PALETTE = "ff0000ff7f00ffff0000ff000000ff00ffff8b00ff"
EXPECTED_BODIES = {
    16: f"0c320507{PALETTE}",
    17: f"0d3201030307{PALETTE}",
    18: f"0d3202030307{PALETTE}",
    19: f"0e32010007{PALETTE}",
    20: f"0e32010107{PALETTE}",
    21: f"0f320107{PALETTE}",
    22: f"1032030000ff07{PALETTE}",
    23: f"1132010007{PALETTE}",
    24: f"1132010107{PALETTE}",
}


def _templates() -> tuple[tuple[CatalogueTemplate, NativeEffect], ...]:
    result: list[tuple[CatalogueTemplate, NativeEffect]] = []
    for template in MODEL_EFFECT_CATALOGUES["H7025"].templates:
        if isinstance(template.content, NativeEffect) and template.content.preset_id is not None:
            result.append((template, template.content))
    return tuple(result)


def test_h7025_catalogue_adds_six_native_families_and_nine_templates() -> None:
    catalogue = MODEL_EFFECT_CATALOGUES["H7025"]
    native_families = tuple(family for family in catalogue.effects if family.category == "native")
    assert {family.family for family in native_families} == set(range(12, 18))
    assert sum(len(family.variations) for family in native_families) == 9
    assert {content.preset_id for _template, content in _templates()} == set(EXPECTED_BODIES)


@pytest.mark.parametrize("preset_id, expected", EXPECTED_BODIES.items())
def test_h7025_native_diy_exact_bodies_round_trip(preset_id: int, expected: str) -> None:
    template, content = next(item for item in _templates() if item[1].preset_id == preset_id)
    assert encode_h7025_diy(content).hex() == expected
    compiled = compile_application(LibraryItem.new(template.label, content), "H7025")
    assert isinstance(compiled, CompiledEffect)
    envelope = reassemble_a3(compiled.upload_packets)
    assert envelope[:3] == bytes((1, len(envelope) // 17, 0x58))
    assert envelope[3 : 3 + len(bytes.fromhex(expected))] == bytes.fromhex(expected)
    assert compiled.diy_code == 254
    assert compiled.upload_subtype == 0x58
    assert (
        upload_ack_subtype(
            compiled.upload_packets,
            len(compiled.upload_packets) - 1,
            "H7025",
        )
        == 0x58
    )
    assert compiled.activation_packet == build_diy_activation(254, "H7025")
    for packet in compiled.packets:
        require_profile_packet(packet, get_profile("H7025"))
    assert decode_effect_frames(compiled.upload_packets, "H7025", compiled.upload_transport) == content


def test_h7025_native_diy_preserves_evidenced_edit_bounds() -> None:
    _template, content = _templates()[0]
    layer = content.layers[0]
    assert isinstance(layer, NativeDiyLayer)
    validate_h7025_diy(replace(content, layers=(replace(layer, speed=100, parameter=10),)))
    with pytest.raises(ValueError, match="parameters"):
        validate_h7025_diy(replace(content, layers=(replace(layer, parameter=11),)))

    pile_up = next(content for _template, content in _templates() if content.preset_id == 24)
    pile_layer = pile_up.layers[0]
    assert isinstance(pile_layer, NativeDiyLayer)
    with pytest.raises(ValueError, match="palette"):
        validate_h7025_diy(replace(pile_up, layers=(replace(pile_layer, palette=pile_layer.palette[:1]),)))


@pytest.mark.parametrize(("status", "success"), [(0, True), (1, False)])
def test_h7025_native_diy_ack_uses_byte_two_result(status: int, success: bool) -> None:
    body = bytes((0xA3, 0x58, status)) + bytes(16)
    result = parse_command_ack_result(body + bytes((xor_checksum(body),)), "H7025")
    assert result.parsed is not None
    assert upload_ack_success(result.parsed, 0x58, protocol=0xA3) is success


def test_h7025_fixed_native_selector_does_not_replace_generic_approved_slot_policy() -> None:
    generic = compile_application(
        LibraryItem.new("Generic", SingleEffect(0, 0, 50, ((255, 0, 0),))),
        "H7025",
        diy_code=1234,
    )
    assert isinstance(generic, CompiledEffect)
    assert generic.diy_code == 1234
    assert decode_effect_frames(generic.upload_packets, "H7025", generic.upload_transport) == generic.authored_diy

    template, content = next(item for item in _templates() if item[1].preset_id == 16)
    native = compile_application(LibraryItem.new(template.label, content), "H7025")
    assert isinstance(native, CompiledEffect)
    coordinator = type(
        "Coordinator",
        (),
        {"diy_code": 1234, "profile": get_profile("H7025")},
    )()
    _validate_diy_slot_approval(coordinator, native)
    coordinator.diy_code = 4321
    with pytest.raises(ValueError, match="no longer selected"):
        _validate_diy_slot_approval(coordinator, generic)


def test_h7025_glimmer_uses_zero_based_wire_density() -> None:
    _template, content = next(item for item in _templates() if item[1].preset_id == 21)
    for density in (0, 1, 2):
        layer = content.layers[0]
        assert isinstance(layer, NativeDiyLayer)
        edited = replace(content, layers=(replace(layer, parameter=density),))
        assert encode_h7025_diy(edited)[2] == density
    layer = content.layers[0]
    assert isinstance(layer, NativeDiyLayer)
    with pytest.raises(ValueError, match="parameters"):
        validate_h7025_diy(replace(content, layers=(replace(layer, parameter=3),)))
