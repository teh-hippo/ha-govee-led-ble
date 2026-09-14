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
    MODEL_EFFECT_CATALOGUES,
    WORKSHOP_PROTOCOL_FIXTURES,
)
from custom_components.ha_govee_led_ble.effect_compiler import (
    CompatibilityState,
    compatibility,
    compile_application,
    compile_effect,
    compile_h617a,
    compile_h6199,
    resolve_diy_code,
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
    effect_content_from_dict,
    effect_content_to_dict,
)
from custom_components.ha_govee_led_ble.effect_protocol_decoder import (
    UnsupportedA3EffectError,
    decode_a3_effect,
)
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


def test_target_catalogue_limits_do_not_follow_shared_grammar(effect_catalogue_targets, monkeypatch):
    broad, narrow = effect_catalogue_targets
    palette = ((255, 0, 0), (0, 0, 255))
    accepted = SingleEffect(0, 0, 50, palette)
    item = LibraryItem.new("Accepted", accepted)
    assert compile_effect(item, broad, diy_code=24).packets == compile_effect(item, narrow, diy_code=24).packets
    rejected = (
        replace(accepted, variant=1),
        replace(accepted, palette=palette[:1]),
        replace(accepted, palette=(*palette, (0, 255, 0))),
        replace(accepted, speed=19),
        replace(accepted, speed=61),
        MultiEffect((EffectPair(0, 0), EffectPair(0, 0)), 50, palette),
        MultiEffect((EffectPair(1, 0),), 50, palette),
        PaintedEffect("clockwise", 50, 61, (None,) * 15),
        PaintedEffect("clockwise", 19, 50, (None,) * 15),
    )
    for content in rejected:
        item = LibraryItem.new("Rejected", content)
        assert effect_content_from_dict(effect_content_to_dict(content)) == content
        assert compatibility(item, broad).state is CompatibilityState.COMPATIBLE
        assert compatibility(item, narrow).state is CompatibilityState.INCOMPATIBLE
        for compiler in (compile_effect, compile_application):
            with pytest.raises(ValueError):
                compiler(item, narrow, diy_code=24)
        with pytest.raises(ValueError):
            compile_h617a(item, 24, model=narrow)
    # A structurally valid, unknown pair round-trips without granting permission.
    frames = proto.build_h617a_diy_single(42, 7, 50, palette)
    decoded = decode_a3_effect(parse_a3_effect_envelope(reassemble_a3(frames), broad), broad)
    assert decoded == SingleEffect(42, 7, 50, palette)
    unknown = LibraryItem.new("Unknown", decoded)
    for model in (broad, narrow, "H617A", "H617E"):
        with pytest.raises(ValueError, match="family 42 variation 7"):
            compile_effect(unknown, model, diy_code=24)
    catalogue = MODEL_EFFECT_CATALOGUES[broad]
    family = replace(
        catalogue.effects[0], family=42, variations=(replace(catalogue.effects[0].variations[0], variant=7),)
    )
    monkeypatch.setitem(MODEL_EFFECT_CATALOGUES, broad, replace(catalogue, effects=(*catalogue.effects, family)))
    assert compile_effect(unknown, broad, diy_code=24).upload_packets == tuple(frames)
    for model in (narrow, "H617A", "H617E"):
        assert compatibility(unknown, model).state is CompatibilityState.INCOMPATIBLE


def test_direct_compilers_cannot_bypass_target_route():
    with pytest.raises(ValueError):
        compile_h6199(LibraryItem.new("Single", SINGLE_CONTENT), model="H617A")
    with pytest.raises(ValueError):
        compile_h617a(LibraryItem.new("Palette", H6199_CONTENT), 401, model="H6199")


def test_palette_diy_uses_target_catalogue_not_global_encoding_roster(monkeypatch):
    catalogue = MODEL_EFFECT_CATALOGUES["H6199"]
    content = replace(H6199_CONTENT, family=42, variant=7)
    frames = proto.build_h6199_palette_diy(content.family, content.variant, content.speed, content.palette)
    assert decode_a3_effect(parse_a3_effect_envelope(reassemble_a3(frames), "H6199"), "H6199") == content
    item = LibraryItem.new("Extended", content)
    with pytest.raises(ValueError, match="family 42 variation 7"):
        compile_h6199(item)
    family = replace(
        catalogue.effects[0], family=42, variations=(replace(catalogue.effects[0].variations[0], variant=7),)
    )
    monkeypatch.setitem(MODEL_EFFECT_CATALOGUES, "H6199", replace(catalogue, effects=(*catalogue.effects, family)))
    assert compile_h6199(item).upload_packets == tuple(frames)
    monkeypatch.setitem(MODEL_EFFECT_CATALOGUES, "H6199", replace(catalogue, palette_max=1))
    with pytest.raises(ValueError, match="palette"):
        compile_h6199(LibraryItem.new("Too many colours", H6199_CONTENT))


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


def test_h6199_fixed_diy_envelope_accepts_the_largest_structurally_fitting_palette(monkeypatch) -> None:
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
    content = decode_a3_effect(parsed, "H6199")
    assert isinstance(content, PaletteDiyEffect)
    assert len(content.palette) == 9
    assert effect_content_from_dict(effect_content_to_dict(content)) == content
    with pytest.raises(ValueError, match="palette"):
        compile_h6199(LibraryItem.new("Imported nine colours", content))
    for model in ("H617A", "H617E", "H6199"):
        assert MODEL_EFFECT_CATALOGUES[model].palette_max == 8
    model = "H9909"
    monkeypatch.setitem(
        MODEL_PROFILES, model, ModelProfile("Synthetic", command_grammar="H6199", effect_grammar="H6199")
    )
    capability = release_capability("H6199", CapabilityWorkflow.PALETTE_DIY)
    assert capability is not None
    monkeypatch.setattr(
        effect_contracts,
        "RELEASE_CAPABILITY_CONTRACT",
        (*effect_contracts.RELEASE_CAPABILITY_CONTRACT, replace(capability, model=model)),
    )
    monkeypatch.setitem(
        MODEL_EFFECT_CATALOGUES, model, replace(MODEL_EFFECT_CATALOGUES["H6199"], sku=model, palette_max=9)
    )
    item = LibraryItem.new("Qualified nine colours", replace(content, model=model))
    assert reassemble_a3(compile_h6199(item, model=model).upload_packets) == envelope


def test_h6199_fixed_diy_envelope_rejects_palette_overflow_before_writing() -> None:
    with pytest.raises(ValueError, match="does not fit the fixed two-chunk envelope"):
        build_h6199_palette_diy_envelope(
            0,
            0,
            50,
            tuple((index, index + 1, index + 2) for index in range(10)),
        )
    with pytest.raises(ValueError, match="does not fit the fixed two-chunk envelope"):
        proto.build_h6199_palette_diy(0, 0, 50, ((1, 2, 3),) * 10)


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


def test_basic_effect_decoder_preserves_uncatalogued_pairs_but_rejects_reserved_values() -> None:
    single = parse_a3_effect_envelope(
        reassemble_a3(compile_h617a(LibraryItem.new("Single", SINGLE_CONTENT), H617A_TYPE04_APPLY_CODE).upload_packets),
        "H617A",
    )
    single.family = 7
    decoded = decode_a3_effect(single, "H617A")
    assert decoded == replace(SINGLE_CONTENT, family=7)
    assert compatibility(LibraryItem.new("Unknown", decoded), "H617A").state is CompatibilityState.INCOMPATIBLE

    multi = parse_a3_effect_envelope(
        reassemble_a3(compile_h617a(LibraryItem.new("Multi", MULTI_CONTENT), H617A_TYPE04_APPLY_CODE).upload_packets),
        "H617A",
    )
    multi.body.variant = 1
    with pytest.raises(UnsupportedA3EffectError, match="reserved variant"):
        decode_a3_effect(multi, "H617A")
    multi.body.variant = 0
    multi.body.pairs[0].family = 4
    multi.body.pairs[0].variant = 8
    decoded = decode_a3_effect(multi, "H617A")
    assert isinstance(decoded, MultiEffect)
    assert decoded.effects[0] == EffectPair(4, 8)
    with pytest.raises(ValueError, match="does not support Multi"):
        compile_h617a(LibraryItem.new("Imported Multi", decoded), 24)

    h6199 = parse_a3_effect_envelope(
        reassemble_a3(compile_h6199(LibraryItem.new("Palette DIY", H6199_CONTENT)).upload_packets),
        "H6199",
    )
    h6199.content.variant = 8
    decoded = decode_a3_effect(h6199, "H6199")
    assert decoded == replace(H6199_CONTENT, variant=8)
    assert compatibility(LibraryItem.new("Unknown", decoded), "H6199").state is CompatibilityState.INCOMPATIBLE


def test_h6125_effect_grammar_accepts_type04_and_rejects_type03() -> None:
    type04 = reassemble_a3(
        compile_h617a(
            LibraryItem.new("Single", SINGLE_CONTENT),
            H617A_TYPE04_APPLY_CODE,
        ).upload_packets
    )
    assert isinstance(parse_a3_effect_envelope(type04, "H6125"), DiyType04)

    type03 = reassemble_a3(
        proto.build_h617a_diy_painted(
            "clockwise",
            45,
            80,
            (1, 2, 3),
            [proto.DiyPaintGroup((10, 20, 30), (0, 2, 4))],
        )
    )
    with pytest.raises(ValueError, match="H6125 A3 body type 0x03 is not supported"):
        parse_a3_effect_envelope(type03, "H6125")


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


@pytest.mark.parametrize("field", ["effect_grammar", "command_grammar"])
@pytest.mark.parametrize("grammar", [None, "unknown", "other"])
@pytest.mark.parametrize(
    ("model", "content"),
    [
        ("H617A", WORKSHOP_PROTOCOL_FIXTURES[0].content("H617A")),
        ("H6199", WORKSHOP_PROTOCOL_FIXTURES[0].content("H6199")),
        ("H617A", PAINTED_CONTENT),
        ("H617A", SINGLE_CONTENT),
        ("H617A", MULTI_CONTENT),
        ("H6199", H6199_CONTENT),
    ],
)
def test_custom_authorization_without_supported_grammar_pair_is_rejected(monkeypatch, model, content, field, grammar):
    item = LibraryItem.new("Custom", content)
    if grammar == "other":
        grammar = "H6199" if model == "H617A" else "H617A"
    monkeypatch.setitem(
        MODEL_PROFILES,
        model,
        replace(
            MODEL_PROFILES[model], **{field: grammar}, read_domains=frozenset(), setup_required_read_domains=frozenset()
        ),
    )
    assert compatibility(item, model).state is CompatibilityState.INCOMPATIBLE
    with pytest.raises(ValueError, match="activation route"):
        compile_effect(item, model, diy_code=800)
    with pytest.raises(ValueError, match="activation route"):
        resolve_diy_code(item, model=model)


@pytest.mark.parametrize("route", [ApplicationRoute.NONE, ApplicationRoute.STUDIO_SCENE_APPLY])
def test_workshop_grammar_cannot_bypass_disabled_workflow(monkeypatch, route) -> None:
    item = LibraryItem.new("Workshop", WORKSHOP_PROTOCOL_FIXTURES[0].content("H617A"))
    monkeypatch.setattr(
        effect_contracts,
        "RELEASE_CAPABILITY_CONTRACT",
        tuple(
            replace(capability, application_route=route)
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
    ("grammar", "content", "workflow", "default_code"),
    [
        ("H617A", PAINTED_CONTENT, CapabilityWorkflow.PAINTED, 800),
        ("H617A", SINGLE_CONTENT, CapabilityWorkflow.SINGLE, H617A_TYPE04_APPLY_CODE),
        ("H617A", MULTI_CONTENT, CapabilityWorkflow.MULTI, H617A_TYPE04_APPLY_CODE),
        ("H6199", H6199_CONTENT, CapabilityWorkflow.PALETTE_DIY, H6199_PALETTE_DIY_APPLY_CODE),
    ],
)
@pytest.mark.parametrize("disabled_route", [ApplicationRoute.NONE, ApplicationRoute.STUDIO_SCENE_APPLY])
def test_profile_grammar_selects_basic_canonical_semantics(
    monkeypatch, grammar, content, workflow, default_code, disabled_route
) -> None:
    monkeypatch.setitem(MODEL_PROFILES, "H9999", ModelProfile("Synthetic", effect_grammar=grammar, segment_count=15))
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

    synthetic_content = replace(content, model="H9999") if isinstance(content, PaletteDiyEffect) else content
    synthetic = LibraryItem.new("Synthetic", synthetic_content)
    assert resolve_diy_code(item) == default_code
    with pytest.raises(ValueError, match="application is not supported"):
        resolve_diy_code(synthetic, model="H9999")
    capability = release_capability(grammar, workflow)
    assert capability is not None
    monkeypatch.setattr(
        effect_contracts,
        "RELEASE_CAPABILITY_CONTRACT",
        (*effect_contracts.RELEASE_CAPABILITY_CONTRACT, replace(capability, model="H9999")),
    )
    with pytest.raises(ValueError, match="activation route"):
        compile_effect(synthetic, "H9999", diy_code=default_code)
    monkeypatch.setitem(MODEL_PROFILES, "H9999", replace(MODEL_PROFILES["H9999"], command_grammar=grammar))
    with pytest.raises(ValueError, match="no custom-effect catalogue"):
        compile_effect(synthetic, "H9999", diy_code=default_code)
    monkeypatch.setitem(MODEL_EFFECT_CATALOGUES, "H9999", replace(MODEL_EFFECT_CATALOGUES[grammar], sku="H9999"))
    resolved = resolve_diy_code(synthetic, model="H9999")
    qualified = compile_effect(synthetic, "H9999", diy_code=resolved)
    reference = compile_effect(item, grammar, diy_code=default_code)
    assert resolved == qualified.diy_code == default_code
    assert qualified.model == "H9999"
    assert qualified.packets == reference.packets
    assert qualified.selector_kind == ("diy" if grammar == "H617A" else "scene")
    assert qualified.activation_mode.value == "custom"
    if grammar == "H6199":
        assert qualified.activation_packet == H("33050491010200000000000000000000000000a0")
        assert resolve_diy_code(synthetic) == default_code
        with pytest.raises(ValueError, match="targets H9999"):
            compile_effect(synthetic, "H6199")
        with pytest.raises(ValueError, match="no evidenced activation packet"):
            resolve_diy_code(synthetic, 402, model="H9999")
    monkeypatch.setattr(
        effect_contracts,
        "RELEASE_CAPABILITY_CONTRACT",
        tuple(
            replace(capability, application_route=disabled_route) if capability.model == "H9999" else capability
            for capability in effect_contracts.RELEASE_CAPABILITY_CONTRACT
        ),
    )
    with pytest.raises(ValueError, match="application is not supported"):
        compile_effect(synthetic, "H9999", diy_code=default_code)


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


@pytest.mark.parametrize("palette", [[], [(255, 0, 0)] * 86, [(256, 0, 0)], [[255, 0, 0]]])
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
