"""Generate canonical backend payloads for frontend contract tests."""

from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES
from custom_components.ha_govee_led_ble.effect_catalogue import (
    WORKSHOP_PROTOCOL_FIXTURES,
    custom_effect_catalogue_payload,
)
from custom_components.ha_govee_led_ble.effect_contracts import (
    EFFECT_COMPILER_VERSION,
    EditorApiInfo,
    device_effect_capabilities,
)
from custom_components.ha_govee_led_ble.effect_deployments import (
    DeploymentPhase,
    DeploymentRecord,
    ObservationConfidence,
)
from custom_components.ha_govee_led_ble.effect_domain import (
    EffectPair,
    LibraryItem,
    MultiEffect,
    MusicProfile,
    OpaqueContent,
    PaintedEffect,
    PaletteDiyEffect,
    RelativeBrightness,
    SingleEffect,
    TargetHint,
    VideoProfile,
    effect_content_from_dict,
    effect_content_to_dict,
)
from custom_components.ha_govee_led_ble.effect_identity import ActiveEffectHint, ObservedDeviceState
from custom_components.ha_govee_led_ble.effect_preview import (
    PreviewHealthPhase,
    PreviewHealthStatus,
    PreviewPhase,
    PreviewStatus,
    PreviewWriteDisposition,
)
from custom_components.ha_govee_led_ble.effect_scenes import scene_catalogue_payload, scene_detail_payload
from custom_components.ha_govee_led_ble.effect_storage import LibrarySnapshot
from custom_components.ha_govee_led_ble.effect_websocket_payloads import library_snapshot_payload
from custom_components.ha_govee_led_ble.scenes import SCENE_ENTRIES

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "frontend" / "tests" / "fixtures" / "backend-contracts.json"
MODELS = ("H6125", "H617A", "H617E", "H6199")
TIMESTAMP = "2026-08-17T00:00:00Z"
ITEM_ID = UUID("00000000-0000-4000-8000-000000000001")
DEPLOYMENT_ID = UUID("00000000-0000-4000-8000-000000000003")
CONTENT_FAMILIES = {
    "h617a_painted",
    "h617a_single",
    "h617a_multi",
    "palette_diy",
    "music_profile",
    "video_profile",
    "advanced",
    "workshop",
    "scene_builtin",
    "scene_palette",
    "scene_layered",
    "future_wave",
}


def _painted_segments() -> tuple[tuple[int, int, int] | None, ...]:
    return ((255, 0, 0),) * 3 + (None,) * 12


def _compact_custom_catalogue(catalogue: dict[str, Any]) -> dict[str, Any]:
    models = cast(dict[str, dict[str, Any]], catalogue["models"])
    compact_models: dict[str, dict[str, Any]] = {}
    for model in MODELS:
        compact = dict(models[model])
        for field in (
            "painted_effects",
            "effects",
            "music_modes",
            "video_modes",
            "workshop_templates",
        ):
            compact[field] = cast(list[Any], compact[field])[:1]
        compact_models[model] = compact
    return {
        "schema_version": catalogue["schema_version"],
        **compact_models["H617A"],
        "models": compact_models,
    }


def _compact_scene_catalogue(model: str) -> dict[str, Any]:
    catalogue = cast(dict[str, Any], scene_catalogue_payload(model))
    scenes = cast(list[dict[str, Any]], catalogue["scenes"])
    selected: list[dict[str, Any]] = []
    parameter_kinds: set[str] = set()
    for scene in scenes:
        parameter_kind = cast(str, scene["parameter_kind"])
        if parameter_kind not in parameter_kinds:
            selected.append(scene)
            parameter_kinds.add(parameter_kind)
    category_ids = {scene["category_id"] for scene in selected}
    return {
        **catalogue,
        "categories": [
            category
            for category in cast(list[dict[str, Any]], catalogue["categories"])
            if category["id"] in category_ids
        ],
        "scenes": selected,
    }


def _representative_scene_details() -> dict[str, dict[str, Any]]:
    details: dict[str, dict[str, Any]] = {}
    for model in MODELS:
        for entry in SCENE_ENTRIES[model]:
            detail = cast(dict[str, Any], scene_detail_payload(model, entry.scene_id, entry.effect_id))
            kind = cast(dict[str, Any], detail["content"])["kind"]
            if isinstance(kind, str):
                details.setdefault(kind, detail)
            if {"scene_builtin", "scene_palette", "scene_layered"} <= details.keys():
                return details
    raise RuntimeError("Native scene catalogues do not cover every frontend scene-content family")


def _content_samples(
    catalogue: dict[str, Any],
    scene_details: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    workshop = WORKSHOP_PROTOCOL_FIXTURES[0].content("H617A")
    workshop_payload = effect_content_to_dict(workshop)

    samples = {
        "h617a_painted": effect_content_to_dict(
            PaintedEffect(
                "clockwise",
                50,
                80,
                _painted_segments(),
            )
        ),
        "h617a_single": effect_content_to_dict(SingleEffect(3, 3, 50, ((255, 0, 0), (0, 0, 255)))),
        "h617a_multi": effect_content_to_dict(
            MultiEffect(
                (EffectPair(0, 0), EffectPair(3, 3)),
                60,
                ((255, 0, 0), (0, 255, 0)),
            )
        ),
        "palette_diy": effect_content_to_dict(PaletteDiyEffect("H6199", 2, 1, 70, ((255, 128, 0),))),
        "music_profile": effect_content_to_dict(
            MusicProfile("H617A", "separation", 50, (1, 2, 3), False, {"point": 3, "gradient": True})
        ),
        "video_profile": effect_content_to_dict(
            VideoProfile(
                "H6199",
                "movie",
                True,
                75,
                False,
                50,
                10,
                RelativeBrightness(100, 90, 80, 70),
                False,
            )
        ),
        "advanced": effect_content_to_dict(workshop.effect),
        "workshop": workshop_payload,
        "scene_builtin": cast(dict[str, Any], scene_details["scene_builtin"]["content"]),
        "scene_palette": cast(dict[str, Any], scene_details["scene_palette"]["content"]),
        "scene_layered": cast(dict[str, Any], scene_details["scene_layered"]["content"]),
        "future_wave": effect_content_to_dict(
            OpaqueContent(
                "future_wave",
                {
                    "schema": 7,
                    "enabled": False,
                    "nested": {"mode": "prism", "values": [1, None, "three"]},
                },
            )
        ),
    }
    if samples.keys() != CONTENT_FAMILIES:
        raise RuntimeError("Frontend content fixture coverage is incomplete")
    return cast(dict[str, dict[str, Any]], samples)


def rendered_data() -> str:
    catalogue = _compact_custom_catalogue(cast(dict[str, Any], custom_effect_catalogue_payload()))
    scene_details = _representative_scene_details()
    item = LibraryItem(
        id=ITEM_ID,
        version=1,
        updated_at=TIMESTAMP,
        name="Canonical painted effect",
        content=PaintedEffect("clockwise", 50, 80, _painted_segments()),
        target_hint=TargetHint("H617A", MODEL_PROFILES["H617A"].segment_count),
    )
    scene_item = LibraryItem(
        id=UUID("00000000-0000-4000-8000-000000000004"),
        version=1,
        updated_at=TIMESTAMP,
        name="Canonical palette scene",
        content=effect_content_from_dict(scene_details["scene_palette"]["content"]),
    )
    deployment = DeploymentRecord(
        operation_id=DEPLOYMENT_ID,
        config_entry_id="h617a-main",
        diy_code=800,
        phase=DeploymentPhase.CONFIRMED,
        compiler_version=EFFECT_COMPILER_VERSION,
        artifact_sha256=sha256(b"frontend-contract-fixture").hexdigest(),
        updated_at=TIMESTAMP,
        content_kind="h617a_painted",
        source_kind="saved_effect",
        selector_label=item.name,
        source_origin_kind=item.origin.kind.value,
        source_origin_id=item.origin.source_id,
        source_content_hash=item.content_hash,
        item_id=ITEM_ID,
        item_version=1,
        progress_current=2,
        progress_total=2,
        verification_confidence=ObservationConfidence.ACTIVATION_MATCH,
    )
    preview = PreviewStatus(
        session_id="fixture-session",
        config_entry_id="h617a-main",
        sequence=4,
        phase=PreviewPhase.CONFIRMED,
        content_kind="h617a_painted",
        confidence=ObservationConfidence.ACTIVATION_MATCH,
        error_code=None,
    )
    active_state = ObservedDeviceState(
        config_entry_id="h617a-main",
        mode="custom",
        observed_at=TIMESTAMP,
        confidence=ObservationConfidence.ACTIVATION_MATCH,
        diy_code=800,
        matched_operation_id=DEPLOYMENT_ID,
        active_effect=ActiveEffectHint.from_record(
            deployment,
            observable_signature="custom:800",
            confidence=ObservationConfidence.ACTIVATION_MATCH,
        ),
    )
    library_snapshot = LibrarySnapshot((item, scene_item))
    devices = []
    for model in MODELS:
        device = device_effect_capabilities(
            f"{model.lower()}-main",
            model,
            MODEL_PROFILES[model].name,
            MODEL_PROFILES[model].segment_count,
            light_entity_id="light.h617a_main" if model == "H617A" else None,
        ).to_dict()
        device["active_state"] = active_state.to_public_dict() if model == "H617A" else None
        device["preview_health"] = PreviewHealthStatus(
            config_entry_id=f"{model.lower()}-main",
            revision=1,
            phase=PreviewHealthPhase.HEALTHY,
            incident_id=None,
            error_code=None,
            error_message=None,
            write_disposition=PreviewWriteDisposition.COMPLETED,
            checked_at=TIMESTAMP,
        ).to_dict()
        devices.append(device)
    document = {
        "schema_version": 1,
        "responses": {
            "editor_info": EditorApiInfo().to_dict(),
            "devices": devices,
            "custom_catalogue": catalogue,
            "library_snapshot": library_snapshot_payload(library_snapshot),
            "library_item": item.to_dict(),
            "preview_status": preview.to_dict(),
            "scene_catalogues": {model: _compact_scene_catalogue(model) for model in MODELS},
            "scene_details": scene_details,
        },
        "content_samples": _content_samples(catalogue, scene_details),
    }
    return f"{json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True)}\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = rendered_data()
    if args.check:
        if not OUTPUT_PATH.exists() or OUTPUT_PATH.read_text(encoding="utf-8") != rendered:
            print(f"{OUTPUT_PATH.relative_to(REPO_ROOT)} is out of date")
            return 1
        return 0
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
