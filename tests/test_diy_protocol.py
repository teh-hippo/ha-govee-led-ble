"""Round-trip tests for H617A DIY body encoders."""

import io
from dataclasses import replace

import pytest
from kaitaistruct import KaitaiStream

from custom_components.ha_govee_led_ble import effect_commands as proto
from custom_components.ha_govee_led_ble import effect_contracts
from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, ModelProfile
from custom_components.ha_govee_led_ble.effect_catalogue import (
    H617A_TYPE04_APPLY_CODE,
    H6199_DIY_EFFECTS,
    H6199_PALETTE_DIY_APPLY_CODE,
    WORKSHOP_PROTOCOL_FIXTURES,
)
from custom_components.ha_govee_led_ble.effect_compiler import (
    CompatibilityState,
    compatibility,
    compile_effect,
    compile_h617a,
    compile_h6199,
)
from custom_components.ha_govee_led_ble.effect_contracts import (
    ApplicationRoute,
    CapabilityWorkflow,
    release_capability,
)
from custom_components.ha_govee_led_ble.effect_domain import (
    EffectPair,
    LibraryItem,
    MultiEffect,
    PaintedEffect,
    PaletteDiyEffect,
    SingleEffect,
)
from custom_components.ha_govee_led_ble.effect_protocol_decoder import (
    UnsupportedA3EffectError,
    decode_a3_effect,
)
from custom_components.ha_govee_led_ble.effect_runtime import resolve_diy_code
from custom_components.ha_govee_led_ble.generated_protocol.diy_type03 import DiyType03
from custom_components.ha_govee_led_ble.generated_protocol.diy_type04 import DiyType04
from custom_components.ha_govee_led_ble.generated_protocol.h6199_effect_upload import H6199EffectUpload
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_h6199_palette_diy_envelope,
    parse_a3_effect_envelope,
    parse_command,
)
from custom_components.ha_govee_led_ble.layered_scene_decoder import decode_workshop_effect, encode_workshop_effect
from custom_components.ha_govee_led_ble.transport import fragment_a3, reassemble_a3

H = bytes.fromhex


PAINTED_CONTENT = PaintedEffect(
    "clockwise",
    45,
    80,
    ((10, 20, 30), None, (10, 20, 30)) + (None,) * 12,
)
SINGLE_CONTENT = SingleEffect(9, 9, 50, ((255, 0, 0), (0, 0, 255)))
MULTI_CONTENT = MultiEffect(
    (EffectPair(0, 1), EffectPair(9, 10)),
    60,
    ((1, 2, 3),),
)
H6199_CONTENT = PaletteDiyEffect(
    "H6199",
    9,
    9,
    50,
    ((255, 0, 0), (0, 0, 255)),
)


def test_activation_encoder_uses_diy_code_800() -> None:
    expected = bytes.fromhex("33050a200300000000000000000000000000001f")

    assert proto.build_h617a_diy_activation(800) == expected
    parsed = parse_command(expected)
    assert parsed is not None
    assert parsed.body.sub_body.code == 800


@pytest.mark.parametrize("diy_code", [-1, 0x10000, 1.5])
def test_activation_encoder_rejects_invalid_code(diy_code: int) -> None:
    with pytest.raises(ValueError, match="DIY code"):
        proto.build_h617a_diy_activation(diy_code)


def test_painted_encoder_round_trips_generated_fields() -> None:
    frames = proto.build_h617a_diy_painted(
        "clockwise",
        45,
        80,
        (1, 2, 3),
        [proto.DiyPaintGroup((10, 20, 30), (0, 2, 4))],
    )
    parsed = DiyType03(KaitaiStream(io.BytesIO(reassemble_a3(frames))))
    parsed._read()

    assert parsed.effect.name == "clockwise"
    assert (parsed.speed, parsed.brightness) == (45, 80)
    assert (parsed.background.red, parsed.background.green, parsed.background.blue) == (1, 2, 3)
    assert parsed.groups[0].segment_indices == [0, 2, 4]


def test_single_encoder_round_trips_generated_fields() -> None:
    frames = proto.build_h617a_diy_single(1, 2, 50, [(255, 0, 0), (0, 0, 255)])
    parsed = DiyType04(KaitaiStream(io.BytesIO(reassemble_a3(frames))))
    parsed._read()

    assert (parsed.family, parsed.body.variant, parsed.body.speed) == (1, 2, 50)
    assert [(colour.red, colour.green, colour.blue) for colour in parsed.body.palette.colours] == [
        (255, 0, 0),
        (0, 0, 255),
    ]


def test_multi_encoder_round_trips_generated_fields() -> None:
    frames = proto.build_h617a_diy_multi([(0, 1), (2, 3)], 60, [(1, 2, 3)])
    parsed = DiyType04(KaitaiStream(io.BytesIO(reassemble_a3(frames))))
    parsed._read()

    assert parsed.family == 0xFF and parsed.body.speed == 60
    assert [(pair.family, pair.variant) for pair in parsed.body.pairs] == [(0, 1), (2, 3)]


@pytest.mark.parametrize("effect", H6199_DIY_EFFECTS, ids=lambda effect: effect.id)
def test_h6199_compiler_matches_every_visible_family_and_variation(effect) -> None:
    palette = ((255, 0, 0), (0, 0, 255))
    item = LibraryItem.new(
        effect.label,
        PaletteDiyEffect(
            "H6199",
            effect.family,
            effect.variant,
            50,
            palette,
        ),
    )

    compiled = compile_h6199(item)
    parsed = H6199EffectUpload(KaitaiStream(io.BytesIO(reassemble_a3(compiled.upload_packets))))
    parsed._read()

    assert int(parsed.content.family) == effect.family
    assert parsed.content.variant == effect.variant
    assert parsed.content.speed == 50
    assert [(colour.red, colour.green, colour.blue) for colour in parsed.content.palette] == list(palette)
    assert compiled.activation_packet == bytes.fromhex("33050491010200000000000000000000000000a0")
    assert compiled.diy_code == H6199_PALETTE_DIY_APPLY_CODE


def test_h6199_activation_encoder_uses_workshop_slot() -> None:
    expected = bytes.fromhex("33050491010200000000000000000000000000a0")

    assert proto.build_h6199_palette_diy_activation(401, 2) == expected


def test_h6199_fixed_diy_envelope_accepts_the_largest_structurally_fitting_palette() -> None:
    envelope = build_h6199_palette_diy_envelope(
        0,
        0,
        50,
        tuple((index, index + 1, index + 2) for index in range(9)),
    )
    parsed = H6199EffectUpload(KaitaiStream(io.BytesIO(envelope)))
    parsed._read()

    assert len(envelope) == 34
    assert len(parsed.content.palette) == 9
    assert parsed.content.padding == []


def test_h6199_fixed_diy_envelope_rejects_palette_overflow_before_writing() -> None:
    with pytest.raises(ValueError, match="does not fit the fixed two-chunk envelope"):
        build_h6199_palette_diy_envelope(
            0,
            0,
            50,
            tuple((index, index + 1, index + 2) for index in range(10)),
        )


@pytest.mark.parametrize(
    ("model", "content", "diy_code", "expected_packets"),
    [
        pytest.param(
            "H617A",
            PAINTED_CONTENT,
            800,
            (
                H("a300010203092d5000000001020a141e000200d6"),
                H("a3ff00000000000000000000000000000000005c"),
            ),
            id="h617a-painted-type03",
        ),
        pytest.param(
            "H617A",
            SINGLE_CONTENT,
            H617A_TYPE04_APPLY_CODE,
            (
                H("a30001020409093206ff00000000ff0000000090"),
                H("a3ff00000000000000000000000000000000005c"),
            ),
            id="h617a-single-type04",
        ),
        pytest.param(
            "H617A",
            MULTI_CONTENT,
            H617A_TYPE04_APPLY_CODE,
            (
                H("a300010204ff003c03010203040001090a000062"),
                H("a3ff00000000000000000000000000000000005c"),
            ),
            id="h617a-multi-type04",
        ),
        pytest.param(
            "H6199",
            H6199_CONTENT,
            H6199_PALETTE_DIY_APPLY_CODE,
            (
                H("a30001020409093206ff00000000ff0000000090"),
                H("a3ff00000000000000000000000000000000005c"),
            ),
            id="h6199-palette-diy",
        ),
    ],
)
def test_compiled_basic_effect_packets_round_trip_to_canonical_content(
    model: str,
    content,
    diy_code: int,
    expected_packets: tuple[bytes, ...],
) -> None:
    item = LibraryItem.new("Round trip", content)
    compiled = compile_h617a(item, diy_code) if model == "H617A" else compile_h6199(item, diy_code)

    assert compiled.upload_packets == expected_packets
    envelope = reassemble_a3(compiled.upload_packets)
    parsed = parse_a3_effect_envelope(envelope, model)
    assert decode_a3_effect(parsed, model) == content


def test_basic_effect_decoder_rejects_uncatalogued_and_reserved_values() -> None:
    single = parse_a3_effect_envelope(
        reassemble_a3(compile_h617a(LibraryItem.new("Single", SINGLE_CONTENT), H617A_TYPE04_APPLY_CODE).upload_packets),
        "H617A",
    )
    single.family = 7
    with pytest.raises(UnsupportedA3EffectError, match="family 7 variation 9 is not catalogued"):
        decode_a3_effect(single, "H617A")

    multi = parse_a3_effect_envelope(
        reassemble_a3(compile_h617a(LibraryItem.new("Multi", MULTI_CONTENT), H617A_TYPE04_APPLY_CODE).upload_packets),
        "H617A",
    )
    multi.body.variant = 1
    with pytest.raises(UnsupportedA3EffectError, match="reserved variant"):
        decode_a3_effect(multi, "H617A")

    h6199 = parse_a3_effect_envelope(
        reassemble_a3(compile_h6199(LibraryItem.new("Palette DIY", H6199_CONTENT)).upload_packets),
        "H6199",
    )
    h6199.content.variant = 8
    with pytest.raises(UnsupportedA3EffectError, match="family 9 variation 8 is not catalogued"):
        decode_a3_effect(h6199, "H6199")


@pytest.mark.parametrize("model", ["H617A", "H617E", "H6199"])
def test_workshop_upload_tree_reuses_lossless_layered_decoder(model: str) -> None:
    workshop = WORKSHOP_PROTOCOL_FIXTURES[0].content(model)
    compiled = compile_effect(LibraryItem.new("Workshop", workshop), model)

    envelope = reassemble_a3(compiled.upload_packets)
    parsed = parse_a3_effect_envelope(envelope, model)

    assert decode_a3_effect(parsed, model) == workshop.effect


@pytest.mark.parametrize("grammar", ["H617A", "H6199"])
def test_profile_effect_grammar_enables_codecs_without_authorizing_application(monkeypatch, grammar) -> None:
    model = "H9999"
    monkeypatch.setitem(MODEL_PROFILES, model, ModelProfile("Synthetic", effect_grammar=grammar))
    workshop = WORKSHOP_PROTOCOL_FIXTURES[0].content(grammar)
    payload = encode_workshop_effect(model, workshop.effect, trailing_padding=workshop.trailing_padding)
    assert payload == workshop.raw_param
    assert decode_workshop_effect(model, payload) == (workshop.effect, workshop.trailing_padding)
    envelope = reassemble_a3(fragment_a3(2, payload))
    parsed = parse_a3_effect_envelope(envelope, model)
    assert decode_a3_effect(parsed, model) == workshop.effect

    item = LibraryItem.new("Synthetic", replace(workshop, model=model))
    assert compatibility(item, model).state is CompatibilityState.INCOMPATIBLE
    with pytest.raises(ValueError, match="Workshop application is not supported"):
        compile_effect(item, model)
    with pytest.raises(ValueError, match="Workshop application is not supported"):
        resolve_diy_code(item)

    # Existing workflow authorization and the matching command route are separate evidence.
    capability = release_capability(grammar, CapabilityWorkflow.WORKSHOP)
    assert capability is not None
    monkeypatch.setattr(
        effect_contracts,
        "RELEASE_CAPABILITY_CONTRACT",
        (*effect_contracts.RELEASE_CAPABILITY_CONTRACT, replace(capability, model=model)),
    )
    with pytest.raises(ValueError, match="activation route"):
        compile_effect(item, model)
    monkeypatch.setitem(MODEL_PROFILES, model, replace(MODEL_PROFILES[model], command_grammar=grammar))
    compiled = compile_effect(item, model)
    reference = compile_effect(LibraryItem.new("Reference", workshop), grammar)
    assert compiled.model == model
    assert compiled.packets == reference.packets
    assert resolve_diy_code(item) == reference.diy_code


@pytest.mark.parametrize("model", ["H6076", "H9999"])
def test_basic_grammars_do_not_supply_effect_grammar(monkeypatch, model) -> None:
    if model == "H9999":
        monkeypatch.setitem(
            MODEL_PROFILES, model, ModelProfile("Synthetic", command_grammar="H617A", status_grammar="H617A")
        )
    workshop = WORKSHOP_PROTOCOL_FIXTURES[0].content("H617A")
    envelope = reassemble_a3(fragment_a3(2, workshop.raw_param))
    parsed = parse_a3_effect_envelope(envelope, "H617A")
    with pytest.raises(ValueError, match="no generated A3 effect grammar"):
        parse_a3_effect_envelope(envelope, model)
    with pytest.raises(ValueError, match="no canonical A3 effect decoder"):
        decode_a3_effect(parsed, model)
    with pytest.raises(ValueError, match="no Workshop grammar"):
        decode_workshop_effect(model, workshop.raw_param)
    with pytest.raises(ValueError, match="no Workshop grammar"):
        encode_workshop_effect(model, workshop.effect)
    item = LibraryItem.new("Unsupported", replace(workshop, model=model))
    assert compatibility(item, model).state is CompatibilityState.INCOMPATIBLE
    with pytest.raises(ValueError, match="Workshop application is not supported"):
        compile_effect(item, model)
    with pytest.raises(ValueError, match="Workshop application is not supported"):
        resolve_diy_code(item)


@pytest.mark.parametrize("grammar", [None, "unknown"])
def test_workshop_authorization_without_supported_grammar_is_rejected(monkeypatch, grammar) -> None:
    item = LibraryItem.new("Workshop", WORKSHOP_PROTOCOL_FIXTURES[0].content("H617A"))
    monkeypatch.setitem(MODEL_PROFILES, "H617A", replace(MODEL_PROFILES["H617A"], effect_grammar=grammar))
    assert compatibility(item, "H617A").state is CompatibilityState.INCOMPATIBLE
    with pytest.raises(ValueError, match="activation route"):
        compile_effect(item, "H617A")
    with pytest.raises(ValueError, match="activation route"):
        resolve_diy_code(item)


def test_workshop_grammar_cannot_bypass_disabled_workflow(monkeypatch) -> None:
    item = LibraryItem.new("Workshop", WORKSHOP_PROTOCOL_FIXTURES[0].content("H617A"))
    monkeypatch.setattr(
        effect_contracts,
        "RELEASE_CAPABILITY_CONTRACT",
        tuple(
            replace(capability, application_route=ApplicationRoute.NONE)
            if capability.workflow is CapabilityWorkflow.WORKSHOP
            else capability
            for capability in effect_contracts.RELEASE_CAPABILITY_CONTRACT
        ),
    )
    assert compatibility(item, "H617A").state is CompatibilityState.INCOMPATIBLE
    with pytest.raises(ValueError, match="Workshop application is not supported"):
        compile_effect(item, "H617A")
    with pytest.raises(ValueError, match="Workshop application is not supported"):
        resolve_diy_code(item)


def test_h617e_workshop_preserves_exact_identity_and_h617a_bytes() -> None:
    workshop = WORKSHOP_PROTOCOL_FIXTURES[0].content("H617E")
    item = LibraryItem.new("H617E", workshop)
    compiled = compile_effect(item, "H617E")
    reference = compile_effect(LibraryItem.new("H617A", replace(workshop, model="H617A")), "H617A")
    assert workshop.model == compiled.model == "H617E"
    assert compiled.packets == reference.packets
    assert resolve_diy_code(item) == reference.diy_code
    with pytest.raises(ValueError, match="targets H617E"):
        compile_effect(item, "H617A")


@pytest.mark.parametrize(
    ("grammar", "content"),
    [("H617A", PAINTED_CONTENT), ("H617A", SINGLE_CONTENT), ("H617A", MULTI_CONTENT), ("H6199", H6199_CONTENT)],
)
def test_profile_grammar_selects_basic_canonical_semantics(monkeypatch, grammar, content) -> None:
    monkeypatch.setitem(MODEL_PROFILES, "H9999", ModelProfile("Synthetic", effect_grammar=grammar))
    item = LibraryItem.new("Reference", content)
    compiled = compile_effect(item, grammar, diy_code=800 if grammar == "H617A" else None)
    envelope = reassemble_a3(compiled.upload_packets)
    for model in ("H9999", "H617E") if grammar == "H617A" else ("H9999",):
        expected = replace(content, model=model) if isinstance(content, PaletteDiyEffect) else content
        assert decode_a3_effect(parse_a3_effect_envelope(envelope, model), model) == expected
        if model == "H9999":
            assert compatibility(LibraryItem.new("Decoded", expected), model).state is CompatibilityState.INCOMPATIBLE
    if grammar == "H617A":
        assert compile_effect(item, "H617E", diy_code=800).packets == compiled.packets


@pytest.mark.parametrize("effect", ["", "unknown", "Clockwise"])
def test_painted_encoder_rejects_unknown_effect(effect: str) -> None:
    with pytest.raises(ValueError, match="unknown painted effect"):
        proto.build_h617a_diy_painted(effect, 50, 100, (0, 0, 0))


@pytest.mark.parametrize("value", [-1, 101, 1.5])
def test_painted_encoder_rejects_invalid_percentages(value: int) -> None:
    with pytest.raises(ValueError):
        proto.build_h617a_diy_painted("clockwise", value, 100, (0, 0, 0))
    with pytest.raises(ValueError):
        proto.build_h617a_diy_painted("clockwise", 50, value, (0, 0, 0))


@pytest.mark.parametrize("background", [(-1, 0, 0), (0, 0, 256), (0, 0), [0, 0, 0]])
def test_painted_encoder_rejects_invalid_background(background) -> None:
    with pytest.raises(ValueError, match="background"):
        proto.build_h617a_diy_painted("clockwise", 50, 100, background)


def test_painted_encoder_rejects_invalid_groups() -> None:
    with pytest.raises(ValueError, match="at least one"):
        proto.build_h617a_diy_painted(
            "clockwise",
            50,
            100,
            (0, 0, 0),
            [proto.DiyPaintGroup((255, 0, 0), ())],
        )
    with pytest.raises(ValueError, match="out of range"):
        proto.build_h617a_diy_painted(
            "clockwise",
            50,
            100,
            (0, 0, 0),
            [proto.DiyPaintGroup((255, 0, 0), (15,))],
        )
    with pytest.raises(ValueError, match="more than one group"):
        proto.build_h617a_diy_painted(
            "clockwise",
            50,
            100,
            (0, 0, 0),
            [
                proto.DiyPaintGroup((255, 0, 0), (0, 1)),
                proto.DiyPaintGroup((0, 0, 255), (1,)),
            ],
        )


@pytest.mark.parametrize("family", [-1, 0xFF, 0x100])
def test_single_encoder_rejects_invalid_family(family: int) -> None:
    with pytest.raises(ValueError):
        proto.build_h617a_diy_single(family, 0, 50, [(255, 0, 0)])


@pytest.mark.parametrize("palette", [[], [(255, 0, 0)] * 9, [(256, 0, 0)], [[255, 0, 0]]])
def test_single_encoder_rejects_invalid_palette(palette) -> None:
    with pytest.raises(ValueError):
        proto.build_h617a_diy_single(0, 0, 50, palette)


def test_multi_encoder_rejects_invalid_effects() -> None:
    with pytest.raises(ValueError, match="1 to 4"):
        proto.build_h617a_diy_multi([], 50, [(255, 0, 0)])
    with pytest.raises(ValueError, match="1 to 4"):
        proto.build_h617a_diy_multi([(0, 0)] * 5, 50, [(255, 0, 0)])
    with pytest.raises(ValueError, match="reserved"):
        proto.build_h617a_diy_multi([(0xFF, 0)], 50, [(255, 0, 0)])
    with pytest.raises(ValueError, match="effect variant"):
        proto.build_h617a_diy_multi([(0, 0x100)], 50, [(255, 0, 0)])
