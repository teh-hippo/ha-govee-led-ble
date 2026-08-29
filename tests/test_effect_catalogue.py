"""Model-aware Effect Studio catalogue contracts."""

from typing import Any, cast

import pytest

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, MUSIC_MODE_SLUGS
from custom_components.ha_govee_led_ble.effect_catalogue import (
    EFFECT_STUDIO_CATALOGUE_SCHEMA_VERSION,
    H617A_CATALOGUE_TEMPLATES,
    H617A_NATIVE_MUSIC_MODES,
    H617A_PAINTED_EFFECTS,
    H617A_TYPE04_APPLY_CODE,
    H617A_TYPE04_FAMILIES,
    H6199_CATALOGUE_TEMPLATES,
    H6199_NATIVE_MUSIC_MODES,
    H6199_PALETTE_DIY_FAMILIES,
    H6199_VIDEO_MODES,
    LEGACY_CATALOGUE_SKU,
    MODEL_EFFECT_CATALOGUES,
    WORKSHOP_PROTOCOL_FIXTURES,
    custom_effect_catalogue_payload,
    resolve_catalogue_template,
    validate_catalogue_template_identity,
)
from custom_components.ha_govee_led_ble.effect_contracts import (
    RELEASE_CAPABILITY_CONTRACT,
    ApplicationRoute,
    CapabilityState,
    CapabilityWorkflow,
    CompilerDeployerStrategy,
    EvidenceClassification,
    FrontendVisibility,
    PhysicalValidationState,
    VerificationConfidence,
    frontend_release_capabilities,
    release_capability,
    studio_apply_capability_state,
    workflow_capability_state,
)
from custom_components.ha_govee_led_ble.effect_domain import JsonValue, MusicProfile, SingleEffect
from custom_components.ha_govee_led_ble.generated_protocol.diy_type03 import DiyType03


def test_model_aware_catalogue_includes_supported_models_and_legacy_h617a_view() -> None:
    catalogue = custom_effect_catalogue_payload()

    assert catalogue["schema_version"] == EFFECT_STUDIO_CATALOGUE_SCHEMA_VERSION
    assert catalogue["sku"] == LEGACY_CATALOGUE_SKU
    assert catalogue["models"] == {sku: model.to_dict() for sku, model in MODEL_EFFECT_CATALOGUES.items()}
    assert catalogue["painted_effects"] == list(H617A_PAINTED_EFFECTS)
    assert catalogue["effects"] == [family.to_dict() for family in H617A_TYPE04_FAMILIES]
    assert catalogue["music_modes"] == [mode.to_dict() for mode in H617A_NATIVE_MUSIC_MODES]
    assert catalogue["video_modes"] == []
    assert catalogue["templates"] == [template.to_dict() for template in H617A_CATALOGUE_TEMPLATES]
    assert catalogue["limits"] == {
        "palette_min": 1,
        "palette_max": 8,
        "multi_max": 4,
        "music_sensitivity_min": 0,
        "music_sensitivity_max": 99,
    }
    assert H617A_TYPE04_APPLY_CODE == 24
    assert catalogue["apply"] == {
        "painted": "supported",
        "single": "supported",
        "multi": "supported",
        "palette_diy": "unsupported",
        "workshop": "supported",
    }


def test_h617a_model_catalogue_preserves_type04_and_painted_contracts() -> None:
    models = cast(
        dict[str, dict[str, JsonValue]],
        custom_effect_catalogue_payload()["models"],
    )
    catalogue = models["H617A"]

    assert catalogue["painted_effects"] == list(H617A_PAINTED_EFFECTS)
    assert catalogue["effects"] == [family.to_dict() for family in H617A_TYPE04_FAMILIES]
    assert {
        (family.family, variation.variant) for family in H617A_TYPE04_FAMILIES for variation in family.variations
    } == {
        (0, 0),
        (0, 1),
        (0, 2),
        (1, 0),
        (1, 2),
        (2, 0),
        (2, 1),
        (2, 2),
        (3, 3),
        (3, 4),
        (3, 5),
        (4, 6),
        (4, 7),
        (4, 8),
        (8, 9),
        (8, 10),
        (9, 9),
        (9, 10),
        (10, 0),
    }
    assert [effect["id"] for effect in H617A_PAINTED_EFFECTS] == [effect.name for effect in DiyType03.Effect]


def test_h6125_catalogue_exposes_scenes_without_h617a_custom_workflows() -> None:
    catalogue = cast(
        dict[str, dict[str, JsonValue]],
        custom_effect_catalogue_payload()["models"],
    )["H6125"]

    assert catalogue["painted_effects"] == []
    assert catalogue["effects"] == []
    assert catalogue["music_modes"] == []
    assert catalogue["video_modes"] == []
    assert catalogue["templates"] == []
    assert catalogue["workshop_templates"] == []
    assert catalogue["supports"] == {
        "multi": "unsupported",
        "advanced": "unsupported",
        "workshop": "unsupported",
    }
    assert catalogue["apply"] == {
        "painted": "unsupported",
        "single": "unsupported",
        "multi": "unsupported",
        "palette_diy": "unsupported",
        "workshop": "unsupported",
    }
    workflows = cast(list[dict[str, JsonValue]], catalogue["workflows"])
    assert [workflow["id"] for workflow in workflows] == [
        "native_scenes",
    ]


def test_h617e_model_catalogue_reuses_h617a_effects_with_h617e_profiles() -> None:
    models = cast(
        dict[str, dict[str, JsonValue]],
        custom_effect_catalogue_payload()["models"],
    )
    catalogue = models["H617E"]
    templates = cast(list[dict[str, Any]], catalogue["templates"])

    assert catalogue["sku"] == "H617E"
    assert catalogue["painted_effects"] == list(H617A_PAINTED_EFFECTS)
    assert catalogue["effects"] == [family.to_dict() for family in H617A_TYPE04_FAMILIES]
    assert {
        template["content"]["model"] for template in templates if template["content"]["kind"] == "music_profile"
    } == {"H617E"}


def test_native_music_modes_are_derived_from_profiles_and_slug_catalogue() -> None:
    def expected_modes(model: str) -> list[dict[str, str]]:
        supported = frozenset(MODEL_PROFILES[model].music_modes)
        return [
            {
                "id": slug,
                "label": slug.replace("_", " ").title(),
            }
            for slug in MUSIC_MODE_SLUGS
            if slug in supported
        ]

    assert [mode.to_dict() for mode in H617A_NATIVE_MUSIC_MODES] == expected_modes("H617A")
    assert [mode.to_dict() for mode in H6199_NATIVE_MUSIC_MODES] == expected_modes("H6199")
    assert all(mode.id != "custom" for mode in (*H617A_NATIVE_MUSIC_MODES, *H6199_NATIVE_MUSIC_MODES))
    models = cast(
        dict[str, dict[str, JsonValue]],
        custom_effect_catalogue_payload()["models"],
    )
    assert models["H617A"]["music_modes"] == expected_modes("H617A")


def test_palette_music_families_remain_single_layer_effects_for_both_models() -> None:
    for families in (H617A_TYPE04_FAMILIES, H6199_PALETTE_DIY_FAMILIES):
        music = next(family for family in families if family.id == "music")

        assert music.label == "Music"
        assert music.rate == "sensitivity"
        assert music.category == "single_layer"
        assert all(family.to_dict()["category"] == "single_layer" for family in families)


def test_h6199_model_catalogue_exposes_confirmed_palette_music_and_video_entries() -> None:
    models = cast(
        dict[str, dict[str, JsonValue]],
        custom_effect_catalogue_payload()["models"],
    )
    catalogue = models["H6199"]

    assert catalogue["painted_effects"] == []
    assert catalogue["effects"] == [family.to_dict() for family in H6199_PALETTE_DIY_FAMILIES]
    assert [mode.to_dict() for mode in H6199_VIDEO_MODES] == [
        {"id": "movie", "label": "Movie"},
        {"id": "game", "label": "Game"},
    ]
    assert catalogue["music_modes"] == [mode.to_dict() for mode in H6199_NATIVE_MUSIC_MODES]
    assert catalogue["video_modes"] == [mode.to_dict() for mode in H6199_VIDEO_MODES]
    assert catalogue["templates"] == [template.to_dict() for template in H6199_CATALOGUE_TEMPLATES]
    assert catalogue["supports"] == {
        "multi": "unsupported",
        "advanced": "supported",
        "workshop": "supported",
    }
    assert catalogue["apply"] == {
        "painted": "unsupported",
        "single": "unsupported",
        "multi": "unsupported",
        "palette_diy": "supported",
        "workshop": "supported",
    }


def test_release_capability_contract_covers_every_preview_workflow() -> None:
    expected = {
        "H617A": {
            CapabilityWorkflow.NATIVE_SCENES,
            CapabilityWorkflow.EDITED_PALETTE_SCENES,
            CapabilityWorkflow.LAYERED_SCENES,
            CapabilityWorkflow.PAINTED,
            CapabilityWorkflow.SINGLE,
            CapabilityWorkflow.MULTI,
            CapabilityWorkflow.NATIVE_MUSIC,
            CapabilityWorkflow.ADVANCED,
            CapabilityWorkflow.WORKSHOP,
        },
        "H6199": {
            CapabilityWorkflow.NATIVE_SCENES,
            CapabilityWorkflow.EDITED_PALETTE_SCENES,
            CapabilityWorkflow.LAYERED_SCENES,
            CapabilityWorkflow.PALETTE_DIY,
            CapabilityWorkflow.NATIVE_MUSIC,
            CapabilityWorkflow.VIDEO,
            CapabilityWorkflow.ADVANCED,
            CapabilityWorkflow.WORKSHOP,
        },
    }

    for model, workflows in expected.items():
        model_contract = [capability for capability in RELEASE_CAPABILITY_CONTRACT if capability.model == model]
        declared = {capability.workflow for capability in model_contract}
        assert declared == workflows
        assert len(model_contract) == len(workflows)


def test_model_visible_capabilities_declare_application_and_evidence_strategies() -> None:
    visible = [
        capability
        for capability in RELEASE_CAPABILITY_CONTRACT
        if capability.frontend_visibility is FrontendVisibility.VISIBLE
    ]

    assert visible
    assert all(isinstance(capability.application_route, ApplicationRoute) for capability in visible)
    assert all(isinstance(capability.compiler_deployer_strategy, CompilerDeployerStrategy) for capability in visible)
    assert all(isinstance(capability.verification_confidence, VerificationConfidence) for capability in visible)
    assert all(isinstance(capability.physical_validation_state, PhysicalValidationState) for capability in visible)
    assert all(
        isinstance(capability.diagnostics_evidence_classification, EvidenceClassification) for capability in visible
    )
    assert all(capability.persistent_content_kind for capability in visible)


def test_release_capability_contract_routes_saved_effects_through_home_assistant() -> None:
    h6125_scenes = release_capability("H6125", CapabilityWorkflow.NATIVE_SCENES)
    h617a_painted = release_capability("H617A", CapabilityWorkflow.PAINTED)
    h617a_single = release_capability("H617A", CapabilityWorkflow.SINGLE)
    h617a_multi = release_capability("H617A", CapabilityWorkflow.MULTI)
    h617a_scenes = release_capability("H617A", CapabilityWorkflow.NATIVE_SCENES)
    compiled_scenes = tuple(
        release_capability(model, workflow)
        for model in ("H617A", "H6199")
        for workflow in (
            CapabilityWorkflow.EDITED_PALETTE_SCENES,
            CapabilityWorkflow.LAYERED_SCENES,
            CapabilityWorkflow.ADVANCED,
        )
    )
    h617a_music = release_capability("H617A", CapabilityWorkflow.NATIVE_MUSIC)
    h6199_music = release_capability("H6199", CapabilityWorkflow.NATIVE_MUSIC)
    h6199_video = release_capability("H6199", CapabilityWorkflow.VIDEO)
    h6199_diy = release_capability("H6199", CapabilityWorkflow.PALETTE_DIY)

    assert h6125_scenes is not None
    assert h6125_scenes.application_route is ApplicationRoute.STUDIO_SCENE_APPLY
    assert h6125_scenes.verification_confidence is VerificationConfidence.UNVERIFIED
    assert h6125_scenes.physical_validation_state is PhysicalValidationState.NOT_VALIDATED
    assert all(
        capability is not None
        and capability.application_route is ApplicationRoute.HOME_ASSISTANT_CONTROL
        and capability.compiler_deployer_strategy is CompilerDeployerStrategy.H617A_CUSTOM_ENGINE
        and capability.verification_confidence is VerificationConfidence.SELECTION_ONLY
        for capability in (h617a_painted, h617a_single, h617a_multi)
    )
    assert h617a_scenes is not None
    assert h617a_scenes.application_route is ApplicationRoute.STUDIO_SCENE_APPLY
    assert h617a_scenes.compiler_deployer_strategy is CompilerDeployerStrategy.NATIVE_EFFECT_SELECTION
    assert h617a_music is not None
    assert h617a_music.application_route is ApplicationRoute.HOME_ASSISTANT_CONTROL
    assert h617a_music.compiler_deployer_strategy is CompilerDeployerStrategy.COORDINATOR_WRITER
    assert h617a_music.verification_confidence is VerificationConfidence.SELECTION_ONLY
    assert all(
        capability is not None
        and capability.application_route is ApplicationRoute.HOME_ASSISTANT_CONTROL
        and capability.compiler_deployer_strategy is CompilerDeployerStrategy.MODEL_SCENE_ENGINE
        and capability.verification_confidence is VerificationConfidence.SELECTION_ONLY
        for capability in compiled_scenes
    )
    assert all(
        capability is not None
        and capability.application_route is ApplicationRoute.HOME_ASSISTANT_CONTROL
        and capability.compiler_deployer_strategy is CompilerDeployerStrategy.COORDINATOR_WRITER
        and capability.verification_confidence is VerificationConfidence.STATE_CONFIRMED
        for capability in (h6199_music, h6199_video)
    )
    assert h6199_diy is not None
    assert h6199_diy.application_route is ApplicationRoute.HOME_ASSISTANT_CONTROL
    assert h6199_diy.compiler_deployer_strategy is CompilerDeployerStrategy.H6199_CUSTOM_ENGINE
    assert h6199_diy.verification_confidence is VerificationConfidence.SELECTION_ONLY
    assert h6199_diy.diagnostics_evidence_classification is EvidenceClassification.STRUCTURAL


def test_catalogue_apply_support_and_visible_workflows_derive_from_release_contract() -> None:
    apply_workflows = {
        "painted": CapabilityWorkflow.PAINTED,
        "single": CapabilityWorkflow.SINGLE,
        "multi": CapabilityWorkflow.MULTI,
        "palette_diy": CapabilityWorkflow.PALETTE_DIY,
        "workshop": CapabilityWorkflow.WORKSHOP,
    }
    models = cast(
        dict[str, dict[str, JsonValue]],
        custom_effect_catalogue_payload()["models"],
    )

    for model, catalogue in models.items():
        assert catalogue["workflows"] == frontend_release_capabilities(model)
        for field, workflow in apply_workflows.items():
            assert (
                cast(dict[str, str], catalogue["apply"])[field]
                == studio_apply_capability_state(
                    model,
                    workflow,
                ).value
            )


def test_capability_state_distinguishes_visibility_from_deployability() -> None:
    assert workflow_capability_state("H617A", CapabilityWorkflow.ADVANCED) is CapabilityState.SUPPORTED
    assert workflow_capability_state("H6199", CapabilityWorkflow.ADVANCED) is CapabilityState.SUPPORTED
    assert studio_apply_capability_state("H6199", CapabilityWorkflow.PALETTE_DIY) is CapabilityState.SUPPORTED
    assert studio_apply_capability_state("H617A", CapabilityWorkflow.WORKSHOP) is CapabilityState.SUPPORTED
    assert studio_apply_capability_state("H6199", CapabilityWorkflow.WORKSHOP) is CapabilityState.SUPPORTED


def test_workshop_protocol_fixtures_decode_embedded_payloads() -> None:
    for model in ("H617A", "H6199"):
        for template in WORKSHOP_PROTOCOL_FIXTURES:
            content = template.content(model)

            assert content.model == model
            assert content.raw_param
            assert content.template == template.id


def test_product_catalogues_do_not_expose_protocol_fixtures_as_starters() -> None:
    models = cast(
        dict[str, dict[str, JsonValue]],
        custom_effect_catalogue_payload()["models"],
    )

    assert all(catalogue["workshop_templates"] == [] for catalogue in models.values())


def test_catalogue_templates_expose_canonical_sidebar_defaults() -> None:
    paint = resolve_catalogue_template("H617A", "template:paint").to_dict()
    assert paint == {
        "id": "template:paint",
        "label": "Paint",
        "category": "single-layer",
        "content": {
            "kind": "h617a_painted",
            "effect": "clockwise",
            "speed": 50,
            "brightness": 100,
            "segments": [None] * 15,
        },
    }
    assert resolve_catalogue_template("H617A", "template:music:rhythm").to_dict()["content"] == {
        "kind": "music_profile",
        "model": "H617A",
        "mode": "rhythm",
        "sensitivity": 99,
        "colour": None,
        "calm": False,
        "parameters": {},
    }
    assert resolve_catalogue_template("H6199", "template:video:movie").to_dict()["content"] == {
        "kind": "video_profile",
        "model": "H6199",
        "mode": "movie",
        "full_screen": True,
        "saturation": 50,
        "sound_effects": False,
        "sound_effects_softness": 50,
        "white_balance_position": 17,
        "relative_brightness": {"left": 100, "top": 100, "right": 100, "bottom": 100},
        "blank_screen": False,
    }


def test_catalogue_template_identity_rejects_cross_template_content() -> None:
    canonical = resolve_catalogue_template("H617A", "template:single:0:0")
    assert validate_catalogue_template_identity("H617A", canonical.id, canonical.content) is canonical

    with pytest.raises(ValueError, match="structural identity"):
        validate_catalogue_template_identity(
            "H617A",
            canonical.id,
            SingleEffect(1, 0, 50, ((255, 0, 0),)),
        )
    with pytest.raises(ValueError, match="structural identity"):
        validate_catalogue_template_identity(
            "H617A",
            canonical.id,
            MusicProfile("H617A", "rhythm", 99),
        )
