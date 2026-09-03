"""H6179 frontend and diagnostics payload contracts."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, cast

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES
from custom_components.ha_govee_led_ble.effect_compiler import compile_music_profile
from custom_components.ha_govee_led_ble.effect_contracts import (
    EDITOR_API_VERSION,
    EDITOR_ASSET_VERSION,
    EFFECT_COMPILER_VERSION,
    RELEASE_CAPABILITY_SCHEMA_VERSION,
    device_effect_capabilities,
    diagnostics_release_capabilities,
    frontend_release_capabilities,
)
from custom_components.ha_govee_led_ble.effect_domain import (
    EFFECT_SCHEMA_VERSION,
    EffectPair,
    H6179MixedDiyEffect,
    H6179SingleDiyEffect,
    LibraryItem,
    MusicProfile,
    effect_content_from_dict,
)
from custom_components.ha_govee_led_ble.effect_scenes import scene_detail_payload
from custom_components.ha_govee_led_ble.effect_websocket_payloads import item_summary
from custom_components.ha_govee_led_ble.scenes import SCENE_ENTRIES
from tools.generate_frontend_contract_fixtures import rendered_data


def test_h6179_frontend_release_payload_is_frozen_to_supported_workflows() -> None:
    assert frontend_release_capabilities("H6179") == [
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


def test_h6179_release_diagnostics_freeze_experimental_evidence_gaps() -> None:
    diy_evidence = {
        "activation_policy": "observed_disposable_approval",
        "overwrite_risk": True,
        "evidence_gaps": [
            "activation_code_not_fixed",
            "effect_content_readback_unavailable",
            "physical_application_not_validated",
        ],
    }

    assert diagnostics_release_capabilities("H6179") == {
        "schema_version": 2,
        "model": "H6179",
        "capabilities": [
            {
                "workflow": "native_scenes",
                "frontend_visibility": "visible",
                "persistent_content_kind": "scene_builtin",
                "application_route": "studio_scene_apply",
                "compiler_deployer_strategy": "native_effect_selection",
                "verification_confidence": "selection_only",
                "physical_validation_state": "not_validated",
                "evidence_classification": "structural",
                "support_status": "experimental",
                "evidence_gaps": ["physical_application_not_validated"],
            },
            {
                "workflow": "single",
                "frontend_visibility": "visible",
                "persistent_content_kind": "h6179_single_diy",
                "application_route": "home_assistant_control",
                "compiler_deployer_strategy": "h6179_a1_effect_upload",
                "verification_confidence": "selection_only",
                "physical_validation_state": "not_validated",
                "evidence_classification": "structural",
                "support_status": "experimental",
                **diy_evidence,
            },
            {
                "workflow": "multi",
                "frontend_visibility": "visible",
                "persistent_content_kind": "h6179_mixed_diy",
                "application_route": "home_assistant_control",
                "compiler_deployer_strategy": "h6179_a1_effect_upload",
                "verification_confidence": "selection_only",
                "physical_validation_state": "not_validated",
                "evidence_classification": "structural",
                "support_status": "experimental",
                **diy_evidence,
            },
            {
                "workflow": "native_music",
                "frontend_visibility": "visible",
                "persistent_content_kind": "music_profile",
                "application_route": "home_assistant_control",
                "compiler_deployer_strategy": "coordinator_writer",
                "verification_confidence": "selection_only",
                "physical_validation_state": "not_validated",
                "evidence_classification": "structural",
                "support_status": "experimental",
                "evidence_gaps": ["physical_application_not_validated"],
            },
        ],
    }


def test_h6179_device_summary_uses_diy_code_readback_without_other_workflows() -> None:
    summary = device_effect_capabilities("entry-79", "H6179", "Backlight", 0).to_dict()

    assert summary["custom_effects"] == {
        "painted": "unsupported",
        "single": "supported",
        "multi": "supported",
        "palette_diy": "unsupported",
        "advanced": "unsupported",
        "workshop": "unsupported",
    }
    assert summary["profiles"] == {
        "music": "supported",
        "video": "unsupported",
        "reactive_rgb": "supported",
    }
    assert summary["readback"] == "diy_code_only"


def test_h6179_library_summaries_include_model_for_every_persistent_kind() -> None:
    scene = SCENE_ENTRIES["H6179"][0]
    scene_content = effect_content_from_dict(
        cast(
            dict[str, Any],
            scene_detail_payload("H6179", scene.scene_id, scene.effect_id)["content"],
        )
    )
    items = (
        LibraryItem.new(
            "Single",
            H6179SingleDiyEffect("H6179", 0, 0, 50, ((255, 0, 0),)),
        ),
        LibraryItem.new(
            "Mixed",
            H6179MixedDiyEffect(
                "H6179",
                (EffectPair(0, 0), EffectPair(2, 0)),
                50,
                ((255, 0, 0),),
            ),
        ),
        LibraryItem.new("Music", MusicProfile("H6179", "mode_0", 50)),
        LibraryItem.new("Scene", scene_content),
    )

    assert [(item_summary(item)["kind"], item_summary(item)["model"]) for item in items] == [
        ("h6179_single_diy", "H6179"),
        ("h6179_mixed_diy", "H6179"),
        ("music_profile", "H6179"),
        ("scene_builtin", "H6179"),
    ]


def test_fixture_generator_renders_atomic_h6179_contract_input_without_writing() -> None:
    document = json.loads(rendered_data())
    responses = document["responses"]

    assert document["schema_version"] == 1
    assert responses["editor_info"]["api_version"] == EDITOR_API_VERSION == 16
    assert responses["editor_info"]["effect_schema_version"] == EFFECT_SCHEMA_VERSION == 2
    assert responses["editor_info"]["compiler_version"] == EFFECT_COMPILER_VERSION == 5
    assert EDITOR_ASSET_VERSION == 19
    assert RELEASE_CAPABILITY_SCHEMA_VERSION == 2
    assert [device["model"] for device in responses["devices"]] == [
        "H617A",
        "H617E",
        "H6179",
        "H6199",
    ]
    assert set(responses["custom_catalogue"]["models"]) == {"H617A", "H617E", "H6179", "H6199"}
    assert set(responses["scene_catalogues"]) == {"H617A", "H617E", "H6179", "H6199"}
    assert {"h6179_single_diy", "h6179_mixed_diy"} <= document["content_samples"].keys()
    assert [
        (item["kind"], item.get("model"))
        for item in responses["library_snapshot"]["items"]
        if item.get("model") == "H6179"
    ] == [
        ("h6179_single_diy", "H6179"),
        ("music_profile", "H6179"),
    ]


def test_h6179_music_profile_compiler_uses_model_codebook_and_one_step_progress(monkeypatch) -> None:
    monkeypatch.setitem(
        MODEL_PROFILES,
        "H6179",
        replace(
            MODEL_PROFILES["H6179"],
            music_modes=("mode_0", "mode_1"),
            supports_music_color=True,
        ),
    )
    compiled = compile_music_profile(
        LibraryItem.new(
            "Mode 2",
            MusicProfile("H6179", "mode_1", 50, (1, 2, 3)),
        ),
        "H6179",
    )

    assert compiled.model == "H6179"
    assert compiled.mode == "mode_1"
    assert compiled.parameters == {}
    assert compiled.progress_total == 1
