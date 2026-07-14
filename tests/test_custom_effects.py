"""Unit tests for the pure custom-effect content model, validators and JSON codec."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import custom_components.ha_govee_led_ble.custom_effects as ce
from custom_components.ha_govee_led_ble.custom_effects import (
    _COMBO_FAMILY_VARIANTS,
    _CONTENT_TYPES,
    _FLAT_FAMILY_VARIANTS,
    ComboContent,
    CustomEffect,
    EffectValidationError,
    FlatContent,
    SegmentContent,
    SketchContent,
    UnknownContent,
    VibrantContent,
    _is_rgb,
    content_from_dict,
    content_to_dict,
    new_effect_id,
    normalise_name,
    validate_content,
)
from custom_components.ha_govee_led_ble.scenes import SCENES

SEG = 15


# --------------------------------------------------------------------------- #
# _is_rgb
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "value,expected",
    [
        ((0, 0, 0), True),
        ((255, 255, 255), True),
        ((0, 0, 256), False),
        ((-1, 0, 0), False),
        ((0, 0), False),
        ((0, 0, 0, 0), False),
        ([0, 0, 0], False),
        ((0, 0, "x"), False),
        ("abc", False),
    ],
)
def test_is_rgb(value, expected):
    assert _is_rgb(value) is expected


# --------------------------------------------------------------------------- #
# validate_content - accepts valid content
# --------------------------------------------------------------------------- #
_VALID = [
    SegmentContent(),
    SegmentContent(colors=((255, 0, 0), None, (0, 255, 0)), brightness=(100, None, 50)),
    VibrantContent(stops=((0, 0, 0), (255, 255, 255))),
    VibrantContent(stops=((1, 1, 1), (2, 2, 2), (3, 3, 3), (4, 4, 4), (5, 5, 5))),
    SketchContent(motion=0x02, speed=0, brightness=0, background=(0, 0, 255), colors=((0, 255, 0), None)),
    SketchContent(motion=0x14, speed=100, brightness=100),
    FlatContent(family=0x00, variant=0x00, palette=((255, 0, 0),) * 8),
    FlatContent(family=0x0A, variant=0x00, palette=((1, 2, 3),) * 3),
    ComboContent(effects=((0x00, 0x00), (0x03, 0x03), (0x08, 0x09), (0x09, 0x0A)), palette=((9, 9, 9),) * 8),
]


@pytest.mark.parametrize("content", _VALID)
def test_validate_accepts_valid(content):
    validate_content(content, segment_count=SEG)


# --------------------------------------------------------------------------- #
# validate_content - rejects with the right key
# --------------------------------------------------------------------------- #
_INVALID = [
    (SegmentContent(colors=((1, 1, 1),) * (SEG + 1)), "too_many_segments"),
    (SegmentContent(colors=((300, 0, 0),)), "bad_rgb"),
    (SegmentContent(brightness=(50,) * (SEG + 1)), "too_many_segment_brightness"),
    (SegmentContent(brightness=(101,)), "segment_brightness_range"),
    (VibrantContent(stops=((0, 0, 0),)), "vibrant_stops_range"),
    (VibrantContent(stops=((0, 0, 0),) * 6), "vibrant_stops_range"),
    (VibrantContent(stops=((0, 0, 0), (256, 0, 0))), "vibrant_bad_rgb"),
    (SketchContent(colors=((1, 1, 1),) * (SEG + 1)), "too_many_segments"),
    (SketchContent(colors=((300, 0, 0),)), "bad_rgb"),
    (SketchContent(background=(300, 0, 0)), "sketch_bad_background"),
    (SketchContent(motion=0x00), "sketch_motion_invalid"),
    (SketchContent(speed=101), "sketch_speed_range"),
    (SketchContent(brightness=101), "sketch_brightness_range"),
    (FlatContent(family=0x00, variant=0x05), "flat_family_variant_invalid"),
    (FlatContent(family=0x00, variant=0x00, speed=101), "flat_speed_range"),
    (FlatContent(family=0x00, variant=0x00, palette=((1, 1, 1),) * 9), "palette_too_large"),
    (FlatContent(family=0x0A, variant=0x00, palette=((1, 1, 1),) * 4), "palette_too_large"),
    (FlatContent(family=0x00, variant=0x00, palette=((300, 0, 0),)), "flat_bad_rgb"),
    (ComboContent(palette=((1, 1, 1),)), "combo_empty"),
    (ComboContent(effects=((0x00, 0x00),)), "combo_palette_empty"),
    (ComboContent(effects=((0x00, 0x00),) * 5), "combo_too_many"),
    (ComboContent(variant=1, effects=((0x00, 0x00),), palette=((1, 1, 1),)), "combo_variant_invalid"),
    (ComboContent(speed=101, effects=((0x00, 0x00),), palette=((1, 1, 1),)), "combo_speed_range"),
    (
        ComboContent(effects=((0x00, 0x00), (0x04, 0x06)), palette=((1, 1, 1),)),
        "combo_family_variant_invalid",
    ),
    (ComboContent(effects=((0x00, 0x00),), palette=((1, 1, 1),) * 9), "palette_too_large"),
    (ComboContent(effects=((0x00, 0x00),), palette=((300, 0, 0),)), "combo_bad_rgb"),
]


@pytest.mark.parametrize("content,key", _INVALID)
def test_validate_rejects_with_key(content, key):
    with pytest.raises(EffectValidationError) as exc:
        validate_content(content, segment_count=SEG)
    assert exc.value.key == key
    assert str(exc.value) == key
    assert isinstance(exc.value, ValueError)


def test_validate_ignores_non_authorable_content():
    # UnknownContent has no validator case: validation is a defensive no-op (never applied).
    assert validate_content(UnknownContent(kind="future", raw={}), segment_count=SEG) is None


def test_flat_family_variants_cover_catalogue():
    assert len(_FLAT_FAMILY_VARIANTS) == 19
    assert (0x0A, 0x00) in _FLAT_FAMILY_VARIANTS
    assert (0x01, 0x01) not in _FLAT_FAMILY_VARIANTS  # Jumping variant gap


def test_combo_family_variants_match_current_ios_picker():
    assert len(_COMBO_FAMILY_VARIANTS) == 15
    assert (0x09, 0x0A) in _COMBO_FAMILY_VARIANTS
    assert (0x04, 0x06) not in _COMBO_FAMILY_VARIANTS
    assert (0x0A, 0x00) not in _COMBO_FAMILY_VARIANTS


def test_frontend_flat_catalogue_matches_backend():
    path = Path(__file__).parents[1] / "frontend" / "src" / "flat-catalogue.json"
    catalogue = json.loads(path.read_text())
    frontend_pairs = {(family["family"], variant["variant"]) for family in catalogue for variant in family["variants"]}
    assert frontend_pairs == _FLAT_FAMILY_VARIANTS
    assert {family["family"]: family["palette_max"] for family in catalogue}[0x0A] == 3


# --------------------------------------------------------------------------- #
# JSON codec - round-trips every kind
# --------------------------------------------------------------------------- #
_ROUNDTRIP = [
    SegmentContent(),
    SegmentContent(colors=((255, 0, 0), None, (0, 255, 0)), brightness=(100, None, 50)),
    SketchContent(motion=0x09, speed=0x33, brightness=0x64, background=(0, 0, 255), colors=((0, 255, 0), None)),
    VibrantContent(stops=((10, 20, 30), (40, 50, 60), (70, 80, 90))),
    FlatContent(family=0x03, variant=0x04, speed=0x2A, palette=((1, 2, 3), (4, 5, 6))),
    ComboContent(variant=0x00, speed=0x20, palette=((7, 8, 9),), effects=((0x00, 0x00), (0x03, 0x03))),
]


@pytest.mark.parametrize("content", _ROUNDTRIP)
def test_codec_roundtrip(content):
    assert content_from_dict(content_to_dict(content)) == content


@pytest.mark.parametrize("content", _ROUNDTRIP)
def test_to_dict_is_json_native(content):
    data = content_to_dict(content)
    assert isinstance(data["kind"], str)
    assert not any(isinstance(v, tuple) for v in data.values())


def test_unknown_content_roundtrips_verbatim():
    raw = {"kind": "future_kind", "foo": 1, "bar": [1, 2, 3], "nested": {"a": 1}}
    parsed = content_from_dict(raw)
    assert isinstance(parsed, UnknownContent)
    assert parsed.kind == "future_kind"
    assert parsed.raw == {"foo": 1, "bar": [1, 2, 3], "nested": {"a": 1}}
    assert content_to_dict(parsed) == raw


def test_unknown_kind_missing_defaults_to_unknown():
    parsed = content_from_dict({"foo": 1})
    assert isinstance(parsed, UnknownContent)
    assert parsed.kind == "unknown"
    assert parsed.raw == {"foo": 1}


def test_unknown_kind_non_string_defaults_to_unknown():
    parsed = content_from_dict({"kind": 123, "x": 9})
    assert isinstance(parsed, UnknownContent)
    assert parsed.kind == "unknown"
    assert parsed.raw == {"x": 9}


def test_content_types_registry():
    assert set(_CONTENT_TYPES) == {"segments", "sketch", "vibrant", "flat", "combo"}
    assert _CONTENT_TYPES["combo"] is ComboContent


# --------------------------------------------------------------------------- #
# normalise_name
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "name,expected",
    [
        ("Sunset", "sunset"),
        ("  Sunset  ", "sunset"),
        ('  "Sunset"  ', "sunset"),
        ("“Sunset”", "sunset"),
        ("MY   Cool\tEffect", "my cool effect"),
        ("a\nb   c", "a b c"),
        ("ẞ", "ss"),
    ],
)
def test_normalise_name(name, expected):
    assert normalise_name(name) == expected


def test_normalise_name_scene_collision_is_name_key_match():
    scene_key = "sunset"
    assert scene_key in SCENES  # SCENES keys are already normalised scene name_keys
    assert normalise_name('  "Sunset" ') == scene_key
    assert normalise_name("SUNSET") == normalise_name("  sunset  ")


def test_custom_effect_name_key_matches_normalised_display():
    display = '  "My  Effect" '
    effect = CustomEffect(
        id="abc12345",
        display_name=display,
        name_key=normalise_name(display),
        content=VibrantContent(stops=((0, 0, 0), (1, 1, 1))),
    )
    assert effect.name_key == "my effect"
    assert effect.name_key == normalise_name("MY   effect")


# --------------------------------------------------------------------------- #
# new_effect_id
# --------------------------------------------------------------------------- #
def test_new_effect_id_shape_and_uniqueness():
    existing: set[str] = set()
    for _ in range(100):
        generated = new_effect_id(existing)
        assert len(generated) == 8
        assert all(char in "0123456789abcdef" for char in generated)
        assert generated not in existing
        existing.add(generated)
    assert len(existing) == 100


def test_new_effect_id_retries_on_collision(monkeypatch):
    values = iter([SimpleNamespace(hex="deadbeef" + "0" * 24), SimpleNamespace(hex="cafebabe" + "0" * 24)])
    monkeypatch.setattr(ce, "uuid4", lambda: next(values))
    assert new_effect_id({"deadbeef"}) == "cafebabe"
