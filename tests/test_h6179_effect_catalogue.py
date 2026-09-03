"""H6179 Effect Studio catalogue contracts."""

from __future__ import annotations

import hashlib
import json
from typing import Any, cast

import pytest

from custom_components.ha_govee_led_ble.const import (
    EFFECT_CATEGORY_EFFECTS,
    EFFECT_CATEGORY_MULTI_LAYERED,
    effect_category_for_content_kind,
)
from custom_components.ha_govee_led_ble.effect_catalogue import (
    DEFAULT_PALETTE,
    EFFECT_STUDIO_CATALOGUE_SCHEMA_VERSION,
    H6179_CATALOGUE_TEMPLATES,
    H6179_DIY_FAMILIES,
    H6179_NATIVE_MUSIC_MODES,
    custom_effect_catalogue_payload,
    resolve_catalogue_template,
    validate_catalogue_template_identity,
)
from custom_components.ha_govee_led_ble.effect_domain import (
    H6179SingleDiyEffect,
    JsonValue,
    SingleEffect,
)
from custom_components.ha_govee_led_ble.effect_scenes import scene_catalogue_payload

_UNCHANGED_MODEL_PAYLOAD_SHA256 = {
    "H617A": "9a8a43f50d67289fff496cb90bcd7d7e5314bcb99f412172b6d9b92066013dfe",
    "H617E": "ed3c5a0cbbc91f662151c7cedf5ab4dea893a8f8a21acc282bf7917fe8a91508",
    "H6199": "e9acbd87d286eb57e1643e4c3d6ca11593f78f4ed6b0fa672cd588047391d45b",
}
H6179_MODEL_PAYLOAD_SHA256 = "50ec4d259cbc11c05d3e0e1e07873a694011bd28b9433b0100a50cac87c47cb3"


def _payload_hash(value: JsonValue) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def test_catalogue_enumerates_h6179_but_not_h6076_and_preserves_existing_models() -> None:
    payload = custom_effect_catalogue_payload()
    models = cast(dict[str, JsonValue], payload["models"])

    assert EFFECT_STUDIO_CATALOGUE_SCHEMA_VERSION == 9
    assert list(models) == ["H617A", "H617E", "H6179", "H6199"]
    assert "H6076" not in models
    assert _payload_hash(models["H6179"]) == H6179_MODEL_PAYLOAD_SHA256
    assert {model: _payload_hash(models[model]) for model in _UNCHANGED_MODEL_PAYLOAD_SHA256} == (
        _UNCHANGED_MODEL_PAYLOAD_SHA256
    )


def test_h6179_catalogue_exposes_only_three_single_families_mixed_diy_scenes_and_music() -> None:
    model = cast(
        dict[str, Any],
        cast(dict[str, JsonValue], custom_effect_catalogue_payload()["models"])["H6179"],
    )

    assert model["sku"] == "H6179"
    assert model["painted_effects"] == []
    assert model["effects"] == [family.to_dict() for family in H6179_DIY_FAMILIES]
    assert [(family.family, family.variations[0].variant) for family in H6179_DIY_FAMILIES] == [
        (0, 0),
        (1, 0),
        (2, 0),
    ]
    assert all(family.supports_multi for family in H6179_DIY_FAMILIES)
    assert (
        model["music_modes"]
        == [mode.to_dict() for mode in H6179_NATIVE_MUSIC_MODES]
        == [
            {"id": "mode_0", "label": "Mode 1"},
            {"id": "mode_1", "label": "Mode 2"},
        ]
    )
    assert model["video_modes"] == []
    assert model["workshop_templates"] == []
    assert model["supports"] == {
        "multi": "supported",
        "advanced": "unsupported",
        "workshop": "unsupported",
    }
    assert model["apply"] == {
        "painted": "unsupported",
        "single": "supported",
        "multi": "supported",
        "palette_diy": "unsupported",
        "workshop": "unsupported",
    }
    assert model["limits"] == {
        "palette_min": 1,
        "palette_max": 8,
        "multi_max": 4,
        "music_sensitivity_min": 0,
        "music_sensitivity_max": 99,
    }
    assert model["workflows"] == [
        {
            "id": "native_scenes",
            "label": "Scenes",
            "content_kind": "scene_builtin",
            "application": "studio",
        },
        {
            "id": "single",
            "label": "Single DIY",
            "content_kind": "h6179_single_diy",
            "application": "home_assistant",
        },
        {
            "id": "multi",
            "label": "Mixed DIY",
            "content_kind": "h6179_mixed_diy",
            "application": "home_assistant",
        },
        {
            "id": "native_music",
            "label": "Music",
            "content_kind": "music_profile",
            "application": "home_assistant",
        },
    ]


def test_h6179_templates_are_model_scoped_and_contain_no_unsupported_content() -> None:
    templates = [template.to_dict() for template in H6179_CATALOGUE_TEMPLATES]
    contents = [cast(dict[str, Any], template["content"]) for template in templates]

    assert [template["id"] for template in templates] == [
        "template:single:0:0",
        "template:single:1:0",
        "template:single:2:0",
        "template:music:mode_0",
        "template:music:mode_1",
    ]
    assert [content["kind"] for content in contents] == [
        "h6179_single_diy",
        "h6179_single_diy",
        "h6179_single_diy",
        "music_profile",
        "music_profile",
    ]
    assert all(content["model"] == "H6179" for content in contents)
    assert all(content["palette"] == [list(colour) for colour in DEFAULT_PALETTE] for content in contents[:3])
    assert not {
        "h617a_painted",
        "h617a_single",
        "h617a_multi",
        "palette_diy",
        "video_profile",
        "advanced",
        "workshop",
        "scene_palette",
        "scene_layered",
    } & {content["kind"] for content in contents}


def test_h6179_single_template_identity_is_exact_and_model_specific() -> None:
    template = resolve_catalogue_template("H6179", "template:single:1:0")

    assert validate_catalogue_template_identity("H6179", template.id, template.content) is template
    with pytest.raises(ValueError, match="structural identity"):
        validate_catalogue_template_identity(
            "H6179",
            template.id,
            H6179SingleDiyEffect("H6179", 2, 0, 50, ((255, 0, 0),)),
        )
    with pytest.raises(ValueError, match="structural identity"):
        validate_catalogue_template_identity(
            "H6179",
            template.id,
            SingleEffect(1, 0, 50, ((255, 0, 0),)),
        )


def test_h6179_native_scene_catalogue_keeps_selector_only_parameters() -> None:
    catalogue = cast(dict[str, Any], scene_catalogue_payload("H6179"))

    assert catalogue["sku"] == "H6179"
    assert len(catalogue["scenes"]) == 83
    assert {scene["parameter_kind"] for scene in catalogue["scenes"]} == {"none"}


def test_h6179_content_kinds_project_to_existing_effect_categories() -> None:
    assert effect_category_for_content_kind("h6179_single_diy") == EFFECT_CATEGORY_EFFECTS
    assert effect_category_for_content_kind("h6179_mixed_diy") == EFFECT_CATEGORY_MULTI_LAYERED
