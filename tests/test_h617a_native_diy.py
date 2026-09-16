"""APK-source candidates only: no radio, HA instance or rendering claims."""

import base64
import json
from dataclasses import replace
from hashlib import sha256

import pytest

from custom_components.ha_govee_led_ble.const import get_profile
from custom_components.ha_govee_led_ble.effect_catalogue import (
    H617A_NATIVE_DIY_SEEDS,
    H617A_NATIVE_DIY_TEMPLATES,
    resolve_catalogue_template,
    validate_catalogue_template_identity,
)
from custom_components.ha_govee_led_ble.effect_compiler import compile_effect
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem, SingleEffect
from custom_components.ha_govee_led_ble.generated_protocol_adapter import build_scene_activation, parse_workshop_body
from custom_components.ha_govee_led_ble.layered_scene import Distribution, LayeredEffect, Selection
from custom_components.ha_govee_led_ble.layered_scene_decoder import decode_workshop_effect, encode_workshop_effect
from custom_components.ha_govee_led_ble.transport import fragment_a3


@pytest.mark.parametrize("index", range(7))
def test_native_seed_identity_upload_and_own_selector(index: int) -> None:
    code, label, seed = H617A_NATIVE_DIY_SEEDS[index]
    template = resolve_catalogue_template("H617A", f"template:native-diy:{code}")
    content = template.content
    assert isinstance(content, LayeredEffect)
    assert content.native_diy == code
    raw = base64.b64decode(seed)
    assert encode_workshop_effect("H617A", content) == raw
    item = LibraryItem.new(label, content)
    restored = LibraryItem.from_dict(item.to_dict())
    assert restored == item
    validate_catalogue_template_identity("H617A", template.id, restored.content)
    compiled = compile_effect(restored, "H617A")
    assert compiled.upload_packets == tuple(fragment_a3(2, raw))
    assert compiled.activation_packet == build_scene_activation("H617A", code)
    assert compiled.selector_kind == "scene"
    assert compiled.diy_code == code
    assert compiled.expected_effect is None
    assert "native_diy_positive_ack_required" in compiled.evidence_codes
    assert "native_diy_rendering_unqualified" in compiled.evidence_codes
    with pytest.raises(ValueError, match="own template selector"):
        compile_effect(restored, "H617A", diy_code=401)
    with pytest.raises(ValueError, match="H617A only"):
        compile_effect(restored, "H617E")


def test_packed_fields_and_extensions_round_trip_without_sibling_loss() -> None:
    effect = H617A_NATIVE_DIY_TEMPLATES[-1].content
    assert isinstance(effect, LayeredEffect)
    layer = replace(
        effect.layers[0],
        selection=Selection(1, 0x12, 0x34),
        unknown_flags=0x21,
        brightness_gradient=True,
        distribution=Distribution(0x72, True),
        excess=b"\xa5",
    )
    edited = replace(effect, layers=(layer, *effect.layers[1:]))
    raw = encode_workshop_effect("H617A", edited)
    parsed, _ = parse_workshop_body(raw)
    body = parsed.layers[0].body
    assert body.selection_quantity == layer.selection.quantity == 0x1234
    assert body.brightness_algorithm == layer.brightness_algorithm == 2
    assert body.brightness_type == layer.brightness_type == 3
    assert body.distribution_method == 2
    assert body.distribution_extensions == 0x70
    decoded, padding = decode_workshop_effect("H617A", raw)
    assert encode_workshop_effect("H617A", decoded, trailing_padding=padding) == raw
    assert decoded.layers[1] == effect.layers[1]
    assert decoded.layers[0].excess == b"\xa5"
    assert Selection(2, 9, 3).random_ic_min == 3
    assert Selection(2, 9, 3).random_ic_max == 9
    assert Selection(3, 4, 2).piece_ic_count == 4
    assert Selection(3, 4, 2).gap_ic_count == 2


@pytest.mark.parametrize("code,index", [(502, 0), (504, 0), (506, 2)])
def test_unknown_physical_count_gates_only_dependent_edits(code: int, index: int) -> None:
    content = resolve_catalogue_template("H617A", f"template:native-diy:{code}").content
    assert isinstance(content, LayeredEffect)
    profile = replace(get_profile("H617A"), physical_ic_count=None)
    layers = list(content.layers)
    layers[index] = replace(layers[index], colour_speed=123)
    compile_effect(
        LibraryItem.new("Palette-independent speed", replace(content, layers=tuple(layers))), "H617A", profile=profile
    )
    layers[index] = replace(layers[index], selection=Selection(1, 1, 4))
    with pytest.raises(ValueError, match="physical IC count"):
        compile_effect(LibraryItem.new("Geometry", replace(content, layers=tuple(layers))), "H617A", profile=profile)


def test_chase_default_bound_and_legacy_import_preservation() -> None:
    template = resolve_catalogue_template("H617A", "template:single:10:0")
    assert isinstance(template.content, SingleEffect)
    assert template.content.palette == ((255, 0, 0), (0, 255, 0), (0, 0, 255))
    legacy = LibraryItem.new("Old Chase", replace(template.content, palette=((1, 2, 3),) * 7))
    restored = LibraryItem.from_dict(legacy.to_dict())
    assert restored == legacy
    with pytest.raises(ValueError, match="palette"):
        compile_effect(restored, "H617A", diy_code=24)


def test_legacy_distribution_hash_is_checked_before_lossless_migration() -> None:
    content = H617A_NATIVE_DIY_TEMPLATES[-1].content
    assert isinstance(content, LayeredEffect)
    document = json.loads(json.dumps(LibraryItem.new("Legacy", content).to_dict()))
    document["content"]["layers"][0]["distribution"]["method"] = 0x72
    document["content_hash"] = sha256(
        json.dumps(
            document["content"],
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()
    restored = LibraryItem.from_dict(document)
    assert isinstance(restored.content, LayeredEffect)
    assert restored.content.layers[0].distribution == Distribution(2, extensions=0x70)
    assert LibraryItem.from_dict(restored.to_dict()) == restored
    document["content_hash"] = "corrupted"
    with pytest.raises(ValueError, match="hash"):
        LibraryItem.from_dict(document)
