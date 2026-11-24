"""H7025 native 0x58 DIY catalogue and transport contracts."""

from dataclasses import replace

import pytest

from custom_components.ha_govee_led_ble.const import get_profile
from custom_components.ha_govee_led_ble.effect_catalogue import MODEL_EFFECT_CATALOGUES
from custom_components.ha_govee_led_ble.effect_catalogue_models import CatalogueTemplate
from custom_components.ha_govee_led_ble.effect_compiler import (
    CompatibilityState,
    CompiledEffect,
    compatibility,
    compile_application,
)
from custom_components.ha_govee_led_ble.effect_contracts import CapabilityWorkflow
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem, NativeEffect, SingleEffect
from custom_components.ha_govee_led_ble.effect_protocol_decoder import (
    UnsupportedA3EffectError,
    decode_a3_effect,
    decode_effect_frames,
)
from custom_components.ha_govee_led_ble.effect_runtime import _active_workspace_content, _validate_diy_slot_approval
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_diy_activation,
    parse_command_ack_result,
    upload_ack_success,
)
from custom_components.ha_govee_led_ble.h7025_effects import encode_h7025_diy, validate_h7025_diy
from custom_components.ha_govee_led_ble.native_effect import NativeDiyLayer
from custom_components.ha_govee_led_ble.native_effect_codecs import native_effect_codec_for_profile
from custom_components.ha_govee_led_ble.protocol_admission import require_profile_packet
from custom_components.ha_govee_led_ble.protocol_core import H7025DiyBody
from custom_components.ha_govee_led_ble.protocol_effect_bodies import (
    parse_a3_effect_envelope,
    upload_ack_subtype,
)
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
EXPECTED_TRANSACTIONS = {
    16: (
        (
            "a3000102580c320507ff0000ff7f00ffff0000bb",
            "a3ffff000000ff00ffff8b00ff00000000000028",
        ),
        "33050afe000000000000000000000000000000c2",
    ),
    24: (
        (
            "a3000102581132010107ff0000ff7f00ffff00a3",
            "a3ff00ff000000ff00ffff8b00ff000000000028",
        ),
        "33050afe000000000000000000000000000000c2",
    ),
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


@pytest.mark.parametrize(("preset_id", "expected"), EXPECTED_TRANSACTIONS.items())
def test_h7025_native_diy_complete_transaction_is_stable(
    preset_id: int,
    expected: tuple[tuple[str, ...], str],
) -> None:
    template, content = next(item for item in _templates() if item[1].preset_id == preset_id)
    compiled = compile_application(LibraryItem.new(template.label, content), "H7025")
    assert isinstance(compiled, CompiledEffect)

    upload, activation = expected
    assert tuple(packet.hex() for packet in compiled.upload_packets) == upload
    assert compiled.activation_packet is not None
    assert compiled.activation_packet.hex() == activation
    assert (compiled.upload_transport, compiled.upload_subtype, compiled.diy_code) == ("a3", 0x58, 254)


def test_native_a3_profile_selects_wire_parser_without_granting_canonical_semantics() -> None:
    template, content = next(item for item in _templates() if item[1].preset_id == 16)
    compiled = compile_application(LibraryItem.new(template.label, content), "H7025")
    assert isinstance(compiled, CompiledEffect)
    envelope = reassemble_a3(compiled.upload_packets)
    synthetic_profile = replace(get_profile("H7025"), name="Synthetic profile")

    parsed = parse_a3_effect_envelope(envelope, "H9999", profile=synthetic_profile)
    assert isinstance(parsed, H7025DiyBody)
    with pytest.raises(UnsupportedA3EffectError, match="canonical"):
        decode_a3_effect(parsed, "H9999", profile=synthetic_profile)

    narrowed = replace(synthetic_profile, native_diy_upload_subtype=None)
    with pytest.raises(ValueError, match="body type 0x58"):
        parse_a3_effect_envelope(envelope, "H9999", profile=narrowed)
    with pytest.raises(UnsupportedA3EffectError, match="effective profile"):
        decode_a3_effect(parsed, "H7025", profile=narrowed)


def test_native_codec_requires_an_explicit_profile_selection() -> None:
    h7025 = native_effect_codec_for_profile(get_profile("H7025"))
    assert h7025 is not None
    assert h7025.canonical_model == "H7025"
    assert native_effect_codec_for_profile(get_profile("H617A")) is None
    assert native_effect_codec_for_profile(get_profile("H617C")) is None


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"supports_custom_effects": False}, "does not support"),
        ({"effect_workflows": frozenset({"multi"})}, "does not support"),
        ({"command_operations": frozenset({"effect_upload"})}, "activation route"),
        ({"command_operations": frozenset({"diy"})}, "does not support effect uploads"),
        ({"native_diy_upload_subtype": None}, "grammar and activation route"),
    ],
)
def test_native_effect_application_fails_at_its_authority_boundary(
    change: dict[str, object],
    message: str,
) -> None:
    template, content = next(item for item in _templates() if item[1].preset_id == 16)
    item = LibraryItem.new(template.label, content)
    restricted = replace(get_profile("H7025"), **change)

    assert compatibility(item, "H7025", profile=restricted).state is CompatibilityState.INCOMPATIBLE
    with pytest.raises(ValueError, match=message):
        compile_application(item, "H7025", profile=restricted)


def test_native_effect_catalogue_and_release_are_not_replaced_by_codec_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from custom_components.ha_govee_led_ble import effect_contracts

    template, content = next(item for item in _templates() if item[1].preset_id == 16)
    item = LibraryItem.new(template.label, content)
    catalogue = MODEL_EFFECT_CATALOGUES["H7025"]
    capabilities = effect_contracts.RELEASE_CAPABILITY_CONTRACT
    without_release = tuple(
        capability
        for capability in capabilities
        if not (capability.model == "H7025" and capability.workflow is CapabilityWorkflow.SINGLE)
    )

    monkeypatch.setattr(effect_contracts, "RELEASE_CAPABILITY_CONTRACT", without_release)
    with pytest.raises(ValueError, match="application is not supported"):
        compile_application(item, "H7025")
    monkeypatch.setattr(effect_contracts, "RELEASE_CAPABILITY_CONTRACT", capabilities)

    monkeypatch.delitem(MODEL_EFFECT_CATALOGUES, "H7025")
    with pytest.raises(ValueError, match="no custom-effect catalogue"):
        compile_application(item, "H7025")
    monkeypatch.setitem(MODEL_EFFECT_CATALOGUES, "H7025", catalogue)


@pytest.mark.parametrize(
    ("restricted", "message"),
    [
        pytest.param({"supports_custom_effects": False}, "outside profile capabilities", id="custom-effects"),
        pytest.param(
            {"command_operations": frozenset({"diy"})},
            "outside profile capabilities",
            id="upload-operation",
        ),
        pytest.param({"native_diy_upload_subtype": None}, "outside profile capabilities", id="subtype"),
    ],
)
def test_native_upload_packet_admission_requires_current_wire_authority(
    restricted: dict[str, object],
    message: str,
) -> None:
    template, content = next(item for item in _templates() if item[1].preset_id == 16)
    compiled = compile_application(LibraryItem.new(template.label, content), "H7025")
    assert isinstance(compiled, CompiledEffect)
    profile = replace(get_profile("H7025"), **restricted)

    with pytest.raises(ValueError, match=message):
        require_profile_packet(compiled.upload_packets[0], profile)


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


def test_h7025_codec_validation_does_not_reenter_native_effect_initialisation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _template, content = _templates()[0]

    def reject_reentry(_content: NativeEffect) -> None:
        raise AssertionError("structural validation re-entered through __post_init__")

    monkeypatch.setattr(NativeEffect, "__post_init__", reject_reentry)
    validate_h7025_diy(content)


@pytest.mark.parametrize(("status", "success"), [(0, True), (1, False)])
def test_h7025_native_diy_ack_uses_byte_two_result(status: int, success: bool) -> None:
    body = bytes((0xA3, 0x58, status)) + bytes(16)
    result = parse_command_ack_result(body + bytes((xor_checksum(body),)), "H7025")
    assert result.parsed is not None
    assert upload_ack_success(result.parsed, 0x58, protocol=0xA3) is success


def test_h7025_fixed_native_selector_does_not_replace_generic_approved_slot_policy() -> None:
    authored = SingleEffect(0, 0, 50, ((255, 0, 0),))
    generic = compile_application(LibraryItem.new("Generic", authored), "H7025", diy_code=1234)
    assert isinstance(generic, CompiledEffect)
    assert generic.diy_code == 1234
    assert decode_effect_frames(generic.upload_packets, "H7025", generic.upload_transport) == generic.authored_diy
    assert _active_workspace_content(authored, generic) == authored

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
