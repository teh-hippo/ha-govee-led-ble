"""Canonical custom-effect domain and compiler contracts."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, cast
from uuid import UUID

import pytest

from custom_components.ha_govee_led_ble import effect_commands
from custom_components.ha_govee_led_ble import layered_scene as layered_scene_module
from custom_components.ha_govee_led_ble.effect_catalogue import (
    H617A_WORKSHOP_APPLY_CODE,
    H617A_WORKSHOP_SCENE_TYPE,
    H6199_WORKSHOP_APPLY_CODE,
    WORKSHOP_PROTOCOL_FIXTURES,
)
from custom_components.ha_govee_led_ble.effect_compiler import (
    ActivationMode,
    CompatibilityState,
    compatibility,
    compile_application,
    compile_effect,
    compile_h617a,
    compile_music_profile,
    compile_video_profile,
)
from custom_components.ha_govee_led_ble.effect_contracts import (
    EDITOR_API_VERSION,
    EFFECT_COMPILER_VERSION,
    CapabilityState,
    EditorApiInfo,
    device_effect_capabilities,
)
from custom_components.ha_govee_led_ble.effect_domain import (
    AppliedArea,
    BrightnessOrder,
    BrightnessPattern,
    BuiltinScene,
    CatalogueRef,
    Distribution,
    EffectLayer,
    EffectPair,
    EffectValidationError,
    LayeredEffect,
    LayeredScene,
    LibraryItem,
    Movement,
    MultiEffect,
    MusicProfile,
    OpaqueContent,
    Origin,
    PaintedEffect,
    PaletteDiyEffect,
    PaletteScene,
    RelativeBrightness,
    SceneStep,
    Selection,
    SelectionType,
    SingleEffect,
    SourceKind,
    TargetHint,
    UnsupportedEffectSchemaError,
    VideoProfile,
    effect_content_from_dict,
    effect_content_to_dict,
)
from custom_components.ha_govee_led_ble.effect_limits import (
    MAX_DEPLOYMENT_RECORDS,
    MAX_EDITOR_DEVICES,
    MAX_EFFECT_DOCUMENT_BYTES,
    MAX_EFFECT_NAME_LENGTH,
    MAX_LIBRARY_ITEMS,
    MAX_PREVIEW_SEQUENCE,
    MAX_SCENE_CATALOGUE_ENTRIES,
)
from custom_components.ha_govee_led_ble.generated_protocol_adapter import build_h617a_scene
from custom_components.ha_govee_led_ble.layered_scene_decoder import decode_workshop_effect


def _layered_effect() -> LayeredEffect:
    movement = Movement(True, False, 1, 3, 50, unknown_flags=0x20)
    layer = EffectLayer(
        area=AppliedArea(0, 10),
        selection=Selection(SelectionType.CUSTOM, 1, 2),
        brightness_gradient=True,
        brightness_patterns=(
            BrightnessPattern(
                100,
                10,
                BrightnessOrder.BRIGHTEST_DARKEST,
                50,
                3,
                4,
            ),
        ),
        distribution=Distribution(2, backwards=True),
        colour_speed=60,
        colour_retention=5,
        palette=((255, 0, 0), (0, 0, 255)),
        selected_movement=movement,
        overall_movement=Movement(False, True, 2, 1, 20),
        priority=3,
        unknown_flags=0x01,
        excess=b"\xaa\xbb",
    )
    return LayeredEffect((layer,))


def _first_layer_document(content: LayeredEffect) -> dict[str, Any]:
    return cast(list[dict[str, Any]], effect_content_to_dict(content)["layers"])[0]


def _palette_diy_effect() -> PaletteDiyEffect:
    return PaletteDiyEffect("H6199", 8, 9, 60, ((255, 0, 0), (0, 0, 255)))


def _music_profile() -> MusicProfile:
    return MusicProfile(
        "H6199",
        "rolling",
        75,
        None,
        True,
        {
            "preset": "warm",
            "bands": [1, 2, 3],
            "mirror": False,
            "slot": 2,
            "override": None,
        },
    )


def _video_profile() -> VideoProfile:
    return VideoProfile(
        "H6199",
        "movie",
        True,
        70,
        True,
        40,
        12,
        RelativeBrightness(80, 60, 55, 45),
        False,
    )


def _painted_segments(
    values: dict[int, tuple[int, int, int]] | None = None,
) -> tuple[tuple[int, int, int] | None, ...]:
    segments: list[tuple[int, int, int] | None] = [None] * 15
    for index, colour in (values or {}).items():
        segments[index] = colour
    return tuple(segments)


def test_layered_validation_error_is_shared_with_websocket_boundary() -> None:
    assert EffectValidationError is layered_scene_module.LayeredSceneValidationError


@pytest.mark.parametrize(
    "content",
    [
        PaintedEffect(
            "clockwise",
            50,
            100,
            _painted_segments({0: (255, 0, 0), 1: (255, 0, 0), 2: (255, 0, 0)}),
        ),
        SingleEffect(3, 3, 50, ((255, 0, 0), (0, 0, 255))),
        MultiEffect(
            (EffectPair(0, 0), EffectPair(3, 3)),
            51,
            ((255, 0, 0), (0, 0, 255)),
        ),
    ],
)
def test_library_item_round_trips(content) -> None:
    item = LibraryItem.new(
        "Night light",
        content,
        target_hint=TargetHint("H617A", 15),
    )

    restored = LibraryItem.from_dict(item.to_dict())

    assert restored == item
    assert isinstance(restored.id, UUID)


def test_unknown_content_round_trips_without_becoming_applicable() -> None:
    document = LibraryItem.new(
        "Future",
        OpaqueContent("future_effect", {"nested": {"value": 3}}),
    ).to_dict()

    restored = LibraryItem.from_dict(document)

    assert isinstance(restored.content, OpaqueContent)
    assert restored.to_dict() == document
    assert compatibility(restored, "H617A").state is CompatibilityState.UNKNOWN


@pytest.mark.parametrize(
    "content",
    [_palette_diy_effect(), _music_profile(), _video_profile()],
)
def test_saved_effect_profile_content_round_trips(content) -> None:
    assert effect_content_from_dict(effect_content_to_dict(content)) == content

    item = LibraryItem.new("Studio profile", content)

    assert LibraryItem.from_dict(item.to_dict()) == item


@pytest.mark.parametrize(
    "content",
    [
        WORKSHOP_PROTOCOL_FIXTURES[0].content("H617A"),
        WORKSHOP_PROTOCOL_FIXTURES[0].content("H6199"),
    ],
)
def test_workshop_content_round_trips(content) -> None:
    assert effect_content_from_dict(effect_content_to_dict(content)) == content
    assert LibraryItem.from_dict(LibraryItem.new("Template", content).to_dict()).content == content


@pytest.mark.parametrize(
    "content",
    [
        _layered_effect(),
        BuiltinScene(CatalogueRef("H617A", 1, 2), speed_index=1),
        PaletteScene(
            CatalogueRef("H617A", 3, 4),
            layout=0,
            brightness_flag=True,
            steps=(SceneStep(10, (255, 0, 0)),),
            palette=((255, 0, 0),),
        ),
        LayeredScene(CatalogueRef("H617A", 5, 6), _layered_effect(), raw_param=b"\x00\xff"),
    ],
)
def test_advanced_and_scene_content_round_trips(content) -> None:
    item = LibraryItem.new("Scene copy", content)

    assert LibraryItem.from_dict(item.to_dict()) == item


def test_advanced_effect_compiles_through_the_model_scene_engine() -> None:
    item = LibraryItem.new("Advanced", _layered_effect())

    result = compatibility(item, "H617A")
    compiled = compile_effect(item, "H617A")

    assert result.state is CompatibilityState.COMPATIBLE
    assert compiled.activation_mode is ActivationMode.SCENE
    assert compiled.upload_packets


def test_layered_area_preserves_raw_zero_distinct_from_full_strip() -> None:
    zero = AppliedArea(0, 0)
    full_strip = AppliedArea(0, 10)

    assert zero != full_strip
    content = LayeredEffect((replace(_layered_effect().layers[0], area=zero),))
    assert _first_layer_document(content)["area"] == {"start_tenths": 0, "width_tenths": 0}


@pytest.mark.parametrize("priority", [0, 255])
def test_layered_raw_scopes_and_priority_round_trip(priority: int) -> None:
    base = _layered_effect().layers[0]
    pattern = replace(base.brightness_patterns[0], scope_high=0, scope_low=255)
    content = LayeredEffect((replace(base, brightness_patterns=(pattern,), priority=priority),))
    document = effect_content_to_dict(content)

    assert effect_content_from_dict(document) == content
    layer = _first_layer_document(content)
    assert layer["brightness_patterns"][0] == {
        "scope_high": 0,
        "scope_low": 255,
        "order": 0,
        "change_speed": 50,
        "brightest_retention": 3,
        "darkest_retention": 4,
    }
    assert layer["priority"] == priority


def test_layered_json_preserves_unknown_selection_and_order_values() -> None:
    base = _layered_effect().layers[0]
    content = LayeredEffect(
        (
            replace(
                base,
                selection=replace(base.selection, type=0xFE),
                brightness_patterns=(replace(base.brightness_patterns[0], order=0xFD),),
            ),
        )
    )
    document = effect_content_to_dict(content)

    assert document["kind"] == "advanced"
    assert effect_content_from_dict(document) == content
    layer = _first_layer_document(content)
    assert layer["selection"]["type"] == 0xFE
    assert layer["brightness_patterns"][0]["order"] == 0xFD
    assert type(layer["selection"]["type"]) is int
    assert type(layer["brightness_patterns"][0]["order"]) is int


def test_layer_palette_preserves_more_than_diy_authoring_limit() -> None:
    palette = tuple((value, value + 1, value + 2) for value in range(11))
    content = LayeredEffect((replace(_layered_effect().layers[0], palette=palette),))

    assert effect_content_from_dict(effect_content_to_dict(content)) == content
    with pytest.raises(EffectValidationError, match="1 to 8"):
        SingleEffect(0, 0, 50, palette)


@pytest.mark.parametrize("count", [0, 255])
def test_palette_scene_preserves_full_u1_count_boundaries(count: int) -> None:
    content = PaletteScene(
        CatalogueRef("H617A", 1, 1),
        layout=0,
        brightness_flag=False,
        steps=tuple(SceneStep(value, (1, 2, 3)) for value in range(count)),
        palette=tuple((1, 2, 3) for _ in range(count)),
    )

    assert effect_content_from_dict(effect_content_to_dict(content)) == content


@pytest.mark.parametrize(
    ("steps", "palette", "message"),
    [
        (tuple(SceneStep(value, (1, 2, 3)) for value in range(256)), (), "steps"),
        ((), tuple((1, 2, 3) for _ in range(256)), "palette"),
    ],
)
def test_palette_scene_rejects_counts_outside_u1_range(steps, palette, message: str) -> None:
    with pytest.raises(EffectValidationError, match=message):
        PaletteScene(
            CatalogueRef("H617A", 1, 1),
            layout=0,
            brightness_flag=False,
            steps=steps,
            palette=palette,
        )


def test_layered_effect_preserves_six_layer_order() -> None:
    base = _layered_effect().layers[0]
    content = LayeredEffect(tuple(replace(base, priority=value) for value in (5, 4, 3, 2, 1, 0)))
    restored = effect_content_from_dict(effect_content_to_dict(content))

    assert isinstance(restored, LayeredEffect)
    assert tuple(layer.priority for layer in restored.layers) == (5, 4, 3, 2, 1, 0)


def test_layered_json_preserves_unknown_flags_and_excess() -> None:
    content = _layered_effect()
    document = effect_content_to_dict(content)

    assert effect_content_to_dict(effect_content_from_dict(document)) == document
    layer = _first_layer_document(content)
    assert layer["unknown_flags"] == 0x01
    assert layer["selected_movement"]["unknown_flags"] == 0x20
    assert layer["excess"] == "aabb"


def test_painted_effect_requires_exact_segment_count() -> None:
    with pytest.raises(EffectValidationError, match="exactly 15"):
        PaintedEffect("clockwise", 50, 100, (None,) * 14)


def test_newer_schema_is_not_silently_loaded() -> None:
    item = LibraryItem.new("Test", SingleEffect(0, 0, 50, ((255, 0, 0),)))
    document = item.to_dict()
    document["schema_version"] = 3

    with pytest.raises(UnsupportedEffectSchemaError):
        LibraryItem.from_dict(document)


def test_h617a_compiler_emits_upload_then_activation() -> None:
    item = LibraryItem.new(
        "Paint",
        PaintedEffect(
            "clockwise",
            50,
            100,
            _painted_segments({0: (255, 0, 0), 1: (255, 0, 0)}),
        ),
    )

    compiled = compile_h617a(item, 800)

    assert compiled.upload_packets == tuple(
        effect_commands.build_h617a_diy_painted(
            "clockwise",
            50,
            100,
            (0, 0, 0),
            (effect_commands.DiyPaintGroup((255, 0, 0), (0, 1)),),
        )
    )
    assert compiled.activation_packet == effect_commands.build_h617a_diy_activation(800)
    assert compiled.packets[-1] == compiled.activation_packet
    assert len(compiled.artifact_sha256) == 64


def test_h617a_painted_compiler_preserves_off_and_explicit_black_deterministically() -> None:
    item = LibraryItem.new(
        "Paint",
        PaintedEffect(
            "clockwise",
            50,
            100,
            _painted_segments(
                {
                    0: (255, 0, 0),
                    1: (0, 0, 0),
                    2: (255, 0, 0),
                }
            ),
        ),
    )

    first = compile_h617a(item, 800)
    second = compile_h617a(item, 800)
    expected = tuple(
        effect_commands.build_h617a_diy_painted(
            "clockwise",
            50,
            100,
            (0, 0, 0),
            (
                effect_commands.DiyPaintGroup((255, 0, 0), (0, 2)),
                effect_commands.DiyPaintGroup((0, 0, 0), (1,)),
            ),
        )
    )

    assert first.upload_packets == expected
    assert second.upload_packets == expected
    assert first.artifact_sha256 == second.artifact_sha256


@pytest.mark.parametrize(
    "content",
    [
        SingleEffect(3, 3, 50, ((255, 0, 0), (0, 0, 255))),
        MultiEffect(
            (EffectPair(0, 0), EffectPair(3, 3)),
            51,
            ((255, 0, 0), (0, 0, 255)),
        ),
    ],
)
def test_h617a_compiler_covers_palette_effects(content) -> None:
    item = LibraryItem.new("Palette", content)

    compiled = compile_h617a(item, 123)

    assert compiled.diy_code == 123
    assert compiled.activation_packet == effect_commands.build_h617a_diy_activation(123)
    assert compiled.upload_packets


def test_h6199_is_explicitly_incompatible() -> None:
    item = LibraryItem.new("Test", SingleEffect(0, 0, 50, ((255, 0, 0),)))

    result = compatibility(item, "H6199")

    assert result.state is CompatibilityState.INCOMPATIBLE
    assert "not supported" in result.reasons[0]


@pytest.mark.parametrize(
    ("item", "model", "reason"),
    [
        (
            LibraryItem.new("Music", MusicProfile("H617A", "separation", 50)),
            "H6199",
            "targets H617A",
        ),
        (
            LibraryItem.new("Music", MusicProfile("H617A", "future_mode", 50)),
            "H617A",
            "does not support music mode",
        ),
        (
            LibraryItem.new(
                "Video",
                VideoProfile(
                    "H6199",
                    "movie",
                    True,
                    70,
                    False,
                    50,
                    10,
                    RelativeBrightness(80, 80, 80, 80),
                    False,
                ),
            ),
            "H617A",
            "video-profile application is not supported",
        ),
    ],
)
def test_profile_compatibility_rejects_model_or_mode_mismatches(item, model, reason) -> None:
    result = compatibility(item, model)

    assert result.state is CompatibilityState.INCOMPATIBLE
    assert reason in result.reasons[0]


def test_compile_application_requires_the_matching_application_route() -> None:
    custom = LibraryItem.new("Custom", SingleEffect(0, 0, 50, ((255, 0, 0),)))

    with pytest.raises(ValueError, match="H6199 custom-effect upload is not supported"):
        compile_application(custom, "H6199", diy_code=24)
    with pytest.raises(ValueError, match="requires a DIY code"):
        compile_application(custom, "H617A")


def test_profile_compilers_reject_the_wrong_content_type() -> None:
    custom = LibraryItem.new("Custom", SingleEffect(0, 0, 50, ((255, 0, 0),)))

    with pytest.raises(ValueError, match="content is not a music profile"):
        compile_music_profile(custom, "H617A")
    with pytest.raises(ValueError, match="content is not a video profile"):
        compile_video_profile(custom, "H617A")


@pytest.mark.parametrize(
    ("mode", "calm", "parameters", "message"),
    [
        ("rolling", False, {}, "does not support a style setting"),
        ("separation", None, {"point": 6}, "point must be an integer from 1 to 5"),
        ("separation", None, {"gradient": 1}, "gradient must be a boolean"),
        ("fountain", None, {"direction": "sideways"}, "direction must be one of"),
    ],
)
def test_music_profile_compiler_rejects_invalid_mode_settings(mode, calm, parameters, message) -> None:
    item = LibraryItem.new(
        "Music",
        MusicProfile("H617A", mode, 50, None, calm, parameters),
    )

    with pytest.raises(ValueError, match=message):
        compile_music_profile(item, "H617A")


def test_music_profile_compiler_applies_parameter_defaults_and_select_values() -> None:
    separation = compile_music_profile(
        LibraryItem.new("Separation", MusicProfile("H617A", "separation", 50)),
        "H617A",
    )
    fountain = compile_music_profile(
        LibraryItem.new(
            "Fountain",
            MusicProfile("H617A", "fountain", 50, parameters={"direction": "two_way"}),
        ),
        "H617A",
    )

    assert separation.parameters == {"point": 1, "gradient": True}
    assert fountain.parameters == {"direction": "two_way"}


@pytest.mark.parametrize("template", WORKSHOP_PROTOCOL_FIXTURES, ids=lambda template: template.id)
@pytest.mark.parametrize("model", ["H617A", "H6199"])
def test_workshop_compiler_reproduces_fixture_body_with_evidenced_model_activation(model: str, template) -> None:
    content = template.content(model)
    item = LibraryItem.new("Workshop", content)

    compiled = compile_effect(item, model)

    if model == "H6199":
        assert compiled.activation_packet == effect_commands.build_h6199_palette_diy_activation(
            H6199_WORKSHOP_APPLY_CODE,
            0,
        )
        assert compiled.diy_code == H6199_WORKSHOP_APPLY_CODE
    else:
        assert compiled.activation_packet == build_h617a_scene(
            H617A_WORKSHOP_APPLY_CODE,
            scene_type=H617A_WORKSHOP_SCENE_TYPE,
        )
        assert compiled.activation_packet == bytes.fromhex("33050491010200000000000000000000000000a0")
        assert compiled.diy_code == H617A_WORKSHOP_APPLY_CODE
    assert (
        b"".join(packet[2:19] for packet in compiled.upload_packets)
        == bytes([1, len(compiled.upload_packets), 2]) + content.raw_param
    )


@pytest.mark.parametrize("model", ["H617A", "H6199"])
def test_workshop_edit_preserves_reserved_layer_data(model: str) -> None:
    content = WORKSHOP_PROTOCOL_FIXTURES[0].content(model)
    first = content.effect.layers[0]
    edited = replace(
        content,
        effect=LayeredEffect(
            (
                replace(
                    first,
                    colour_speed=first.colour_speed + 1,
                ),
                *content.effect.layers[1:],
            )
        ),
    )

    compiled = compile_effect(LibraryItem.new("Edited Workshop", edited), model)
    framed = b"".join(packet[2:19] for packet in compiled.upload_packets)
    decoded, trailing_padding = decode_workshop_effect(model, framed[3:])

    assert decoded == edited.effect
    assert decoded.layers[0].unknown_flags == first.unknown_flags
    assert decoded.layers[0].selected_movement.unknown_flags == first.selected_movement.unknown_flags
    assert decoded.layers[0].overall_movement.unknown_flags == first.overall_movement.unknown_flags
    assert decoded.layers[0].excess == first.excess
    assert trailing_padding == edited.trailing_padding
    assert edited.raw_param == content.raw_param


@pytest.mark.parametrize(
    ("item", "model"),
    [
        (LibraryItem.new("Workshop", WORKSHOP_PROTOCOL_FIXTURES[0].content("H617A")), "H617A"),
    ],
)
def test_upload_only_compilers_reject_invented_activation(item: LibraryItem, model: str) -> None:
    with pytest.raises(ValueError, match="no evidenced activation packet"):
        compile_effect(item, model, diy_code=800)


def test_model_mismatch_fails_before_a_packet_can_be_compiled() -> None:
    workshop = LibraryItem.new("Workshop", WORKSHOP_PROTOCOL_FIXTURES[0].content("H617A"))

    with pytest.raises(ValueError, match="targets H617A"):
        compile_effect(workshop, "H6199")


def test_editor_contract_reports_first_slice_boundaries() -> None:
    api = EditorApiInfo().to_dict()
    h617a = device_effect_capabilities("entry-a", "H617A", "Cupboard", 15)
    h6199 = device_effect_capabilities("entry-b", "H6199", "TV", 15)

    assert api == {
        "api_version": EDITOR_API_VERSION,
        "effect_schema_version": 2,
        "compiler_version": EFFECT_COMPILER_VERSION,
        "limits": {
            "effect_name": MAX_EFFECT_NAME_LENGTH,
            "effect_document_bytes": MAX_EFFECT_DOCUMENT_BYTES,
            "devices": MAX_EDITOR_DEVICES,
            "library_items": MAX_LIBRARY_ITEMS,
            "deployment_records": MAX_DEPLOYMENT_RECORDS,
            "scene_catalogue_entries": MAX_SCENE_CATALOGUE_ENTRIES,
            "preview_sequence": MAX_PREVIEW_SEQUENCE,
        },
    }
    assert h617a.painted is CapabilityState.SUPPORTED
    assert h617a.light_entity_id is None
    assert h617a.single is CapabilityState.SUPPORTED
    assert h617a.multi is CapabilityState.SUPPORTED
    assert h617a.palette_diy is CapabilityState.UNSUPPORTED
    assert h617a.advanced is CapabilityState.SUPPORTED
    assert h6199.single is CapabilityState.UNSUPPORTED
    assert h6199.palette_diy is CapabilityState.SUPPORTED
    assert h6199.advanced is CapabilityState.SUPPORTED
    assert h6199.to_dict()["readback"] == "scene_selector_for_user_effects"


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (
            {
                "kind": "palette_diy",
                "model": "H617A",
                "family": 1,
                "variant": 0,
                "speed": 50,
                "palette": [],
            },
            "palette must contain 1 to 8 colours",
        ),
        (
            {
                "kind": "music_profile",
                "model": "H6199",
                "mode": "rolling",
                "sensitivity": 50,
                "colour": None,
                "calm": None,
                "parameters": [],
            },
            "parameters must be a mapping",
        ),
        (
            {
                "kind": "video_profile",
                "model": "H6199",
                "mode": "movie",
                "full_screen": True,
                "saturation": 50,
                "sound_effects": True,
                "sound_effects_softness": 50,
                "white_balance_position": 10,
                "relative_brightness": {
                    "left": 0,
                    "top": 50,
                    "right": 50,
                    "bottom": 50,
                },
                "blank_screen": False,
            },
            "left must be an integer from 1 to 100",
        ),
    ],
)
def test_saved_effect_profile_content_rejects_malformed_payloads(
    raw: dict[str, Any],
    message: str,
) -> None:
    with pytest.raises(EffectValidationError, match=message):
        effect_content_from_dict(raw)


def test_effect_documents_reject_oversized_and_deep_opaque_content() -> None:
    with pytest.raises(EffectValidationError, match="must not exceed"):
        LibraryItem.new(
            "Oversized",
            OpaqueContent("future", {"body": "x" * MAX_EFFECT_DOCUMENT_BYTES}),
        )

    nested: Any = "leaf"
    for _ in range(18):
        nested = [nested]

    with pytest.raises(EffectValidationError, match="nested levels"):
        LibraryItem.new(
            "Deep",
            OpaqueContent("future", {"body": nested}),
        )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: Origin(SourceKind.AUTHORED, "x" * 256),
        lambda: TargetHint("H617A", 0),
        lambda: PaintedEffect("clockwise", 50, 100, ((0, 0, 256),) + (None,) * 14),
        lambda: SingleEffect(0, 0, 50, ()),
        lambda: MusicProfile("future", "rolling", 50, None, None, {}),
        lambda: RelativeBrightness(0, 1, 1, 1),
        lambda: Movement(True, False, 4, 1, 1),
        lambda: CatalogueRef("H617A", -1, 1),
        lambda: BuiltinScene(CatalogueRef("H617A", 1, 1), speed_index=256),
    ],
)
def test_domain_rejects_representative_invalid_boundaries(factory) -> None:
    with pytest.raises(EffectValidationError):
        factory()


def test_origin_hash_and_extensions_round_trip() -> None:
    item = LibraryItem(
        id=UUID(int=1),
        version=2,
        updated_at="2026-08-17T00:00:00+00:00",
        name="Imported",
        content=SingleEffect(0, 0, 50, ((255, 0, 0),)),
        origin=Origin(SourceKind.IMPORTED, "fixture"),
        extensions={"future": {"enabled": True}},
    )

    assert LibraryItem.from_dict(item.to_dict()) == item
    assert len(item.content_hash) == 64


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("id", "not-a-uuid", "UUID"),
        ("version", "one", "integer"),
        ("updated_at", "now", "ISO 8601 timestamp"),
        ("content_hash", "0" * 64, "does not match"),
        ("extensions", [], "mapping"),
    ],
)
def test_library_document_rejects_invalid_envelope(field, value, message) -> None:
    document = LibraryItem.new(
        "Test",
        SingleEffect(0, 0, 50, ((255, 0, 0),)),
    ).to_dict()
    document[field] = value

    with pytest.raises(EffectValidationError, match=message):
        LibraryItem.from_dict(document)
