"""Ordinary H6099 DIY APK evidence; no physical-device qualification."""

from dataclasses import replace

import pytest

from custom_components.ha_govee_led_ble.const import get_profile
from custom_components.ha_govee_led_ble.effect_catalogue import MODEL_EFFECT_CATALOGUES, resolve_catalogue_template
from custom_components.ha_govee_led_ble.effect_compiler import (
    CompiledEffect,
    compile_application,
    compile_effect,
    resolve_diy_code,
)
from custom_components.ha_govee_led_ble.effect_domain import (
    EffectPair,
    LibraryItem,
    MultiEffect,
    PaintedEffect,
    SingleEffect,
    effect_content_to_dict,
)
from custom_components.ha_govee_led_ble.effect_runtime import _active_workspace_content
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_h6099_diy_activation,
    parse_a3_effect_envelope,
)
from custom_components.ha_govee_led_ble.transport import fragment_a3, reassemble_a3


def test_basic_and_mixed_bytes_and_default_activation() -> None:
    basic = LibraryItem.new("Basic", SingleEffect(8, 10, 50, ((255, 0, 0), (0, 255, 0))))
    mixed = LibraryItem.new("Mixed", MultiEffect((EffectPair(0, 2), EffectPair(9, 10)), 100, ((1, 2, 3),)))
    for item, body in (
        (basic, "04080a3206ff000000ff00"),
        (mixed, "04ff006403010203040002090a"),
    ):
        compiled = compile_application(item, "H6099")
        assert isinstance(compiled, CompiledEffect)
        assert isinstance(item.content, SingleEffect | MultiEffect)
        assert compiled.diy_code == resolve_diy_code(item, model="H6099") == 254
        assert compiled.selector_kind == "diy"
        assert compiled.activation_packet == build_h6099_diy_activation()
        assert compiled.activation_packet[:5] == bytes.fromhex("33050afe00")
        envelope = reassemble_a3(compiled.upload_packets)
        assert envelope[2:].startswith(bytes.fromhex(body))
        assert not any(envelope[2 + len(bytes.fromhex(body)) :])
        parsed = parse_a3_effect_envelope(envelope, "H6099")
        assert int(parsed.kind) == 4
        assert parsed.diy.body.speed == item.content.speed
        assert _active_workspace_content(item.content, compiled) == item.content


def test_exact_catalogue_variations_and_limits() -> None:
    catalogue = MODEL_EFFECT_CATALOGUES["H6099"]
    assert {f.family: tuple(v.variant for v in f.variations) for f in catalogue.effects} == {
        0: (0, 1, 2),
        1: (0, 2),
        2: (0, 1, 2),
        3: (3, 4, 5),
        8: (9, 10),
        9: (9, 10),
        10: (0,),
        4: (8, 6, 7),
    }
    assert {f.family for f in catalogue.effects if f.supports_multi} == {0, 1, 2, 3, 8, 9}
    compile_effect(
        LibraryItem.new(
            "Four mixed effects",
            MultiEffect(
                (EffectPair(0, 0), EffectPair(1, 2), EffectPair(8, 9), EffectPair(9, 10)),
                1,
                ((1, 2, 3),) * 8,
            ),
        ),
        "H6099",
    )
    with pytest.raises(ValueError, match="1 to 4"):
        MultiEffect((EffectPair(0, 0),) * 5, 50, ((1, 2, 3),))
    for family in catalogue.effects:
        for variation in family.variations:
            for speed in (family.rate_min, family.rate_max):
                compile_effect(
                    LibraryItem.new("Basic", SingleEffect(family.family, variation.variant, speed, ((255, 0, 0),))),
                    "H6099",
                )
    for content in (
        SingleEffect(0, 0, 0, ((1, 2, 3),)),
        SingleEffect(1, 1, 50, ((1, 2, 3),)),
        SingleEffect(4, 8, 51, ((1, 2, 3),)),
        SingleEffect(10, 0, 50, ((1, 2, 3),) * 4),
        SingleEffect(0, 0, 50, ((1, 2, 3),) * 9),
        MultiEffect((EffectPair(10, 0),), 50, ((1, 2, 3),)),
        MultiEffect((EffectPair(4, 8),), 50, ((1, 2, 3),)),
    ):
        with pytest.raises(ValueError):
            compile_effect(LibraryItem.new("Invalid", content), "H6099")
    for template in catalogue.templates:
        if isinstance(template.content, SingleEffect):
            compile_effect(LibraryItem.new("Template", template.content), "H6099")


def test_graffiti_uses_effective_physical_indices_and_preserves_background() -> None:
    profile = replace(get_profile("H6099"), physical_ic_count=60)
    template = resolve_catalogue_template("H6099", "template:paint", profile=profile)
    assert isinstance(template.content, PaintedEffect)
    assert template.content.segments == (None,) * 60
    with pytest.raises(ValueError, match="known physical IC count"):
        resolve_catalogue_template("H6099", "template:paint")
    for motion, code in (
        ("clockwise", 9),
        ("counter_clockwise", 10),
        ("cycle", 2),
        ("gradient", 19),
        ("twinkle", 15),
        ("breathe", 20),
    ):
        content = PaintedEffect(
            motion, 0, 100, (None,) * 59 + ((255, 0, 0),), background=(255, 255, 255), addressing="physical_ic"
        )
        item = LibraryItem.new("Graffiti", content)
        assert LibraryItem.from_dict(item.to_dict()) == item
        compiled = compile_application(item, "H6099", profile=profile)
        assert isinstance(compiled, CompiledEffect)
        envelope = reassemble_a3(compiled.upload_packets)
        assert envelope[2:15] == bytes.fromhex(f"03{code:02x}0064ffffff0101ff00003b")
        parsed = parse_a3_effect_envelope(envelope, "H6099")
        assert parsed.diy.groups[0].segment_indices == [59]
        assert compiled.activation_packet == build_h6099_diy_activation(254)
        assert _active_workspace_content(content, compiled) == content
        with pytest.raises(ValueError, match="known physical IC count"):
            compile_application(item, "H6099")
        with pytest.raises(ValueError, match="count does not match"):
            compile_application(item, "H6099", profile=replace(profile, physical_ic_count=14))
        with pytest.raises(ValueError, match="addressing"):
            compile_effect(item, "H617A", diy_code=800)
    with pytest.raises(ValueError, match="addressing"):
        compile_application(
            LibraryItem.new("Logical paint", PaintedEffect("cycle", 50, 100, (None,) * 15)), "H6099", profile=profile
        )


def test_legacy_painted_document_hash_and_explicit_diy_code() -> None:
    item = LibraryItem.new("Legacy", PaintedEffect("cycle", 50, 100, (None,) * 15))
    assert "background" not in effect_content_to_dict(item.content)
    assert "addressing" not in effect_content_to_dict(item.content)
    assert LibraryItem.from_dict(item.to_dict()) == item
    basic = LibraryItem.new("Basic", SingleEffect(0, 0, 50, ((1, 2, 3),)))
    assert compile_effect(basic, "H6099", diy_code=1234).activation_packet == build_h6099_diy_activation(1234)


def test_h6099_root_validates_shared_diy_fields() -> None:
    for kind, body in ((4, "0000320100"), (3, "093264ffffff0102ff00003b")):
        with pytest.raises(ValueError, match="invalid H6099"):
            # Nonzero padding or a malformed palette must be parsed, not left opaque.
            parse_a3_effect_envelope(reassemble_a3(fragment_a3(kind, bytes.fromhex(body) + b"\xff" * 34)), "H6099")
