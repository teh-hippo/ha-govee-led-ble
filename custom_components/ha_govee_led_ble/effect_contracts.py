"""Versioned contracts shared by the advanced backend and frontend."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from .const import default_effect_categories
from .effect_domain import EFFECT_SCHEMA_VERSION, JsonValue
from .effect_limits import (
    MAX_DEPLOYMENT_RECORDS,
    MAX_EDITOR_DEVICES,
    MAX_EFFECT_DOCUMENT_BYTES,
    MAX_EFFECT_NAME_LENGTH,
    MAX_LIBRARY_ITEMS,
    MAX_PREVIEW_SEQUENCE,
    MAX_SCENE_CATALOGUE_ENTRIES,
)

EDITOR_API_VERSION: Final = 14
EDITOR_ASSET_VERSION: Final = 17
EFFECT_COMPILER_VERSION: Final = 4
RELEASE_CAPABILITY_SCHEMA_VERSION: Final = 1


class CapabilityState(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    EVIDENCE_GAP = "evidence_gap"


class CapabilityWorkflow(StrEnum):
    NATIVE_SCENES = "native_scenes"
    EDITED_PALETTE_SCENES = "edited_palette_scenes"
    LAYERED_SCENES = "layered_scenes"
    PAINTED = "painted"
    SINGLE = "single"
    MULTI = "multi"
    NATIVE_MUSIC = "native_music"
    VIDEO = "video"
    PALETTE_DIY = "palette_diy"
    ADVANCED = "advanced"
    WORKSHOP = "workshop"


class FrontendVisibility(StrEnum):
    VISIBLE = "visible"
    HIDDEN = "hidden"


class ApplicationRoute(StrEnum):
    STUDIO_SCENE_APPLY = "studio_scene_apply"
    STUDIO_CUSTOM_APPLY = "studio_custom_apply"
    HOME_ASSISTANT_CONTROL = "home_assistant_control"
    NONE = "none"


class CompilerDeployerStrategy(StrEnum):
    NATIVE_EFFECT_SELECTION = "native_effect_selection"
    H617A_CUSTOM_ENGINE = "h617a_custom_engine"
    H6199_CUSTOM_ENGINE = "h6199_custom_engine"
    MODEL_SCENE_ENGINE = "model_scene_engine"
    COORDINATOR_WRITER = "coordinator_writer"
    CANONICAL_ENCODER_ONLY = "canonical_encoder_only"
    STRUCTURAL_DEFINITION_ONLY = "structural_definition_only"
    STRUCTURAL_PARSER_ONLY = "structural_parser_only"
    RAW_PRESERVATION = "raw_preservation"
    A3_EFFECT_UPLOAD = "a3_effect_upload"


class VerificationConfidence(StrEnum):
    STATE_CONFIRMED = "state_confirmed"
    SELECTION_ONLY = "selection_only"
    UNVERIFIED = "unverified"


class PhysicalValidationState(StrEnum):
    APPLICATION_VALIDATED = "application_validated"
    CAPTURE_VALIDATED = "capture_validated"
    NOT_VALIDATED = "not_validated"


class EvidenceClassification(StrEnum):
    DETERMINISTIC = "deterministic"
    STRUCTURAL = "structural"
    OPAQUE = "opaque"
    LIVE = "live"


class FrontendApplicationState(StrEnum):
    STUDIO = "studio"
    HOME_ASSISTANT = "home_assistant"
    PLANNED = "planned"


@dataclass(frozen=True, slots=True)
class ReleaseCapability:
    model: str
    workflow: CapabilityWorkflow
    label: str
    frontend_visibility: FrontendVisibility
    persistent_content_kind: str
    application_route: ApplicationRoute
    compiler_deployer_strategy: CompilerDeployerStrategy
    verification_confidence: VerificationConfidence
    physical_validation_state: PhysicalValidationState
    diagnostics_evidence_classification: EvidenceClassification

    @property
    def frontend_application(self) -> FrontendApplicationState:
        if self.application_route in {
            ApplicationRoute.STUDIO_SCENE_APPLY,
            ApplicationRoute.STUDIO_CUSTOM_APPLY,
        }:
            return FrontendApplicationState.STUDIO
        if self.application_route is ApplicationRoute.HOME_ASSISTANT_CONTROL:
            return FrontendApplicationState.HOME_ASSISTANT
        return FrontendApplicationState.PLANNED

    def to_frontend_dict(self) -> dict[str, JsonValue]:
        return {
            "id": self.workflow.value,
            "label": self.label,
            "content_kind": self.persistent_content_kind,
            "application": self.frontend_application.value,
        }

    def to_diagnostics_dict(self) -> dict[str, JsonValue]:
        return {
            "workflow": self.workflow.value,
            "frontend_visibility": self.frontend_visibility.value,
            "persistent_content_kind": self.persistent_content_kind,
            "application_route": self.application_route.value,
            "compiler_deployer_strategy": self.compiler_deployer_strategy.value,
            "verification_confidence": self.verification_confidence.value,
            "physical_validation_state": self.physical_validation_state.value,
            "evidence_classification": self.diagnostics_evidence_classification.value,
        }


def _capability(
    model: str,
    workflow: CapabilityWorkflow,
    label: str,
    persistent_content_kind: str,
    application_route: ApplicationRoute,
    compiler_deployer_strategy: CompilerDeployerStrategy,
    verification_confidence: VerificationConfidence,
    physical_validation_state: PhysicalValidationState,
    diagnostics_evidence_classification: EvidenceClassification,
) -> ReleaseCapability:
    return ReleaseCapability(
        model=model,
        workflow=workflow,
        label=label,
        frontend_visibility=FrontendVisibility.VISIBLE,
        persistent_content_kind=persistent_content_kind,
        application_route=application_route,
        compiler_deployer_strategy=compiler_deployer_strategy,
        verification_confidence=verification_confidence,
        physical_validation_state=physical_validation_state,
        diagnostics_evidence_classification=diagnostics_evidence_classification,
    )


RELEASE_CAPABILITY_CONTRACT: Final = (
    _capability(
        "H617A",
        CapabilityWorkflow.NATIVE_SCENES,
        "Scenes",
        "scene_builtin",
        ApplicationRoute.STUDIO_SCENE_APPLY,
        CompilerDeployerStrategy.NATIVE_EFFECT_SELECTION,
        VerificationConfidence.STATE_CONFIRMED,
        PhysicalValidationState.APPLICATION_VALIDATED,
        EvidenceClassification.STRUCTURAL,
    ),
    _capability(
        "H617A",
        CapabilityWorkflow.EDITED_PALETTE_SCENES,
        "Edited palette scenes",
        "scene_palette",
        ApplicationRoute.HOME_ASSISTANT_CONTROL,
        CompilerDeployerStrategy.MODEL_SCENE_ENGINE,
        VerificationConfidence.SELECTION_ONLY,
        PhysicalValidationState.CAPTURE_VALIDATED,
        EvidenceClassification.STRUCTURAL,
    ),
    _capability(
        "H617A",
        CapabilityWorkflow.LAYERED_SCENES,
        "Layered scenes",
        "scene_layered",
        ApplicationRoute.HOME_ASSISTANT_CONTROL,
        CompilerDeployerStrategy.MODEL_SCENE_ENGINE,
        VerificationConfidence.SELECTION_ONLY,
        PhysicalValidationState.CAPTURE_VALIDATED,
        EvidenceClassification.STRUCTURAL,
    ),
    _capability(
        "H617A",
        CapabilityWorkflow.PAINTED,
        "Painted",
        "h617a_painted",
        ApplicationRoute.HOME_ASSISTANT_CONTROL,
        CompilerDeployerStrategy.H617A_CUSTOM_ENGINE,
        VerificationConfidence.SELECTION_ONLY,
        PhysicalValidationState.APPLICATION_VALIDATED,
        EvidenceClassification.DETERMINISTIC,
    ),
    _capability(
        "H617A",
        CapabilityWorkflow.SINGLE,
        "Single",
        "h617a_single",
        ApplicationRoute.HOME_ASSISTANT_CONTROL,
        CompilerDeployerStrategy.H617A_CUSTOM_ENGINE,
        VerificationConfidence.SELECTION_ONLY,
        PhysicalValidationState.APPLICATION_VALIDATED,
        EvidenceClassification.STRUCTURAL,
    ),
    _capability(
        "H617A",
        CapabilityWorkflow.MULTI,
        "Multi",
        "h617a_multi",
        ApplicationRoute.HOME_ASSISTANT_CONTROL,
        CompilerDeployerStrategy.H617A_CUSTOM_ENGINE,
        VerificationConfidence.SELECTION_ONLY,
        PhysicalValidationState.APPLICATION_VALIDATED,
        EvidenceClassification.STRUCTURAL,
    ),
    _capability(
        "H617A",
        CapabilityWorkflow.NATIVE_MUSIC,
        "Music",
        "music_profile",
        ApplicationRoute.HOME_ASSISTANT_CONTROL,
        CompilerDeployerStrategy.COORDINATOR_WRITER,
        VerificationConfidence.SELECTION_ONLY,
        PhysicalValidationState.APPLICATION_VALIDATED,
        EvidenceClassification.LIVE,
    ),
    _capability(
        "H617A",
        CapabilityWorkflow.ADVANCED,
        "Advanced",
        "advanced",
        ApplicationRoute.HOME_ASSISTANT_CONTROL,
        CompilerDeployerStrategy.MODEL_SCENE_ENGINE,
        VerificationConfidence.SELECTION_ONLY,
        PhysicalValidationState.CAPTURE_VALIDATED,
        EvidenceClassification.STRUCTURAL,
    ),
    _capability(
        "H617A",
        CapabilityWorkflow.WORKSHOP,
        "Workshop",
        "workshop",
        ApplicationRoute.HOME_ASSISTANT_CONTROL,
        CompilerDeployerStrategy.A3_EFFECT_UPLOAD,
        VerificationConfidence.SELECTION_ONLY,
        PhysicalValidationState.CAPTURE_VALIDATED,
        EvidenceClassification.STRUCTURAL,
    ),
    _capability(
        "H6199",
        CapabilityWorkflow.NATIVE_SCENES,
        "Scenes",
        "scene_builtin",
        ApplicationRoute.STUDIO_SCENE_APPLY,
        CompilerDeployerStrategy.NATIVE_EFFECT_SELECTION,
        VerificationConfidence.STATE_CONFIRMED,
        PhysicalValidationState.APPLICATION_VALIDATED,
        EvidenceClassification.STRUCTURAL,
    ),
    _capability(
        "H6199",
        CapabilityWorkflow.EDITED_PALETTE_SCENES,
        "Edited palette scenes",
        "scene_palette",
        ApplicationRoute.HOME_ASSISTANT_CONTROL,
        CompilerDeployerStrategy.MODEL_SCENE_ENGINE,
        VerificationConfidence.SELECTION_ONLY,
        PhysicalValidationState.CAPTURE_VALIDATED,
        EvidenceClassification.STRUCTURAL,
    ),
    _capability(
        "H6199",
        CapabilityWorkflow.LAYERED_SCENES,
        "Layered scenes",
        "scene_layered",
        ApplicationRoute.HOME_ASSISTANT_CONTROL,
        CompilerDeployerStrategy.MODEL_SCENE_ENGINE,
        VerificationConfidence.SELECTION_ONLY,
        PhysicalValidationState.CAPTURE_VALIDATED,
        EvidenceClassification.STRUCTURAL,
    ),
    _capability(
        "H6199",
        CapabilityWorkflow.PALETTE_DIY,
        "Palette DIY",
        "palette_diy",
        ApplicationRoute.HOME_ASSISTANT_CONTROL,
        CompilerDeployerStrategy.H6199_CUSTOM_ENGINE,
        VerificationConfidence.SELECTION_ONLY,
        PhysicalValidationState.CAPTURE_VALIDATED,
        EvidenceClassification.STRUCTURAL,
    ),
    _capability(
        "H6199",
        CapabilityWorkflow.NATIVE_MUSIC,
        "Music",
        "music_profile",
        ApplicationRoute.HOME_ASSISTANT_CONTROL,
        CompilerDeployerStrategy.COORDINATOR_WRITER,
        VerificationConfidence.STATE_CONFIRMED,
        PhysicalValidationState.APPLICATION_VALIDATED,
        EvidenceClassification.LIVE,
    ),
    _capability(
        "H6199",
        CapabilityWorkflow.VIDEO,
        "Video",
        "video_profile",
        ApplicationRoute.HOME_ASSISTANT_CONTROL,
        CompilerDeployerStrategy.COORDINATOR_WRITER,
        VerificationConfidence.STATE_CONFIRMED,
        PhysicalValidationState.APPLICATION_VALIDATED,
        EvidenceClassification.LIVE,
    ),
    _capability(
        "H6199",
        CapabilityWorkflow.ADVANCED,
        "Advanced",
        "advanced",
        ApplicationRoute.HOME_ASSISTANT_CONTROL,
        CompilerDeployerStrategy.MODEL_SCENE_ENGINE,
        VerificationConfidence.SELECTION_ONLY,
        PhysicalValidationState.CAPTURE_VALIDATED,
        EvidenceClassification.STRUCTURAL,
    ),
    _capability(
        "H6199",
        CapabilityWorkflow.WORKSHOP,
        "Workshop",
        "workshop",
        ApplicationRoute.HOME_ASSISTANT_CONTROL,
        CompilerDeployerStrategy.A3_EFFECT_UPLOAD,
        VerificationConfidence.SELECTION_ONLY,
        PhysicalValidationState.CAPTURE_VALIDATED,
        EvidenceClassification.STRUCTURAL,
    ),
)


def release_capabilities_for_model(model: str) -> tuple[ReleaseCapability, ...]:
    capabilities = tuple(capability for capability in RELEASE_CAPABILITY_CONTRACT if capability.model == model)
    if not capabilities:
        raise ValueError(f"{model} has no release capability contract")
    return capabilities


def release_capability(model: str, workflow: CapabilityWorkflow) -> ReleaseCapability | None:
    return next(
        (
            capability
            for capability in RELEASE_CAPABILITY_CONTRACT
            if capability.model == model and capability.workflow is workflow
        ),
        None,
    )


def frontend_release_capabilities(model: str) -> list[JsonValue]:
    return [
        capability.to_frontend_dict()
        for capability in release_capabilities_for_model(model)
        if capability.frontend_visibility is FrontendVisibility.VISIBLE
    ]


def diagnostics_release_capabilities(model: str) -> dict[str, JsonValue]:
    return {
        "schema_version": RELEASE_CAPABILITY_SCHEMA_VERSION,
        "model": model,
        "capabilities": [capability.to_diagnostics_dict() for capability in release_capabilities_for_model(model)],
    }


def workflow_capability_state(model: str, workflow: CapabilityWorkflow) -> CapabilityState:
    capability = release_capability(model, workflow)
    if capability is None or capability.frontend_visibility is not FrontendVisibility.VISIBLE:
        return CapabilityState.UNSUPPORTED
    if (
        capability.application_route is ApplicationRoute.NONE
        and capability.verification_confidence is VerificationConfidence.UNVERIFIED
    ):
        return CapabilityState.EVIDENCE_GAP
    return CapabilityState.SUPPORTED


def studio_apply_capability_state(model: str, workflow: CapabilityWorkflow) -> CapabilityState:
    capability = release_capability(model, workflow)
    if capability is None or capability.application_route not in {
        ApplicationRoute.STUDIO_CUSTOM_APPLY,
        ApplicationRoute.HOME_ASSISTANT_CONTROL,
    }:
        return CapabilityState.UNSUPPORTED
    return CapabilityState.SUPPORTED


@dataclass(frozen=True, slots=True)
class EditorApiInfo:
    api_version: int = EDITOR_API_VERSION
    effect_schema_version: int = EFFECT_SCHEMA_VERSION
    compiler_version: int = EFFECT_COMPILER_VERSION

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "api_version": self.api_version,
            "effect_schema_version": self.effect_schema_version,
            "compiler_version": self.compiler_version,
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


@dataclass(frozen=True, slots=True)
class DeviceEffectCapabilities:
    config_entry_id: str
    light_entity_id: str | None
    model: str
    display_name: str
    segment_count: int
    painted: CapabilityState
    single: CapabilityState
    multi: CapabilityState
    palette_diy: CapabilityState
    advanced: CapabilityState
    music: CapabilityState
    video: CapabilityState
    workshop: CapabilityState
    readback: str
    effect_categories: tuple[str, ...]

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "config_entry_id": self.config_entry_id,
            "light_entity_id": self.light_entity_id,
            "model": self.model,
            "display_name": self.display_name,
            "segment_count": self.segment_count,
            "custom_effects": {
                "painted": self.painted.value,
                "single": self.single.value,
                "multi": self.multi.value,
                "palette_diy": self.palette_diy.value,
                "advanced": self.advanced.value,
                "workshop": self.workshop.value,
            },
            "profiles": {
                "music": self.music.value,
                "video": self.video.value,
            },
            "readback": self.readback,
            "effect_categories": list(self.effect_categories),
        }


def device_effect_capabilities(
    config_entry_id: str,
    model: str,
    display_name: str,
    segment_count: int,
    *,
    light_entity_id: str | None = None,
    effect_categories: tuple[str, ...] | None = None,
) -> DeviceEffectCapabilities:
    return DeviceEffectCapabilities(
        config_entry_id=config_entry_id,
        light_entity_id=light_entity_id,
        model=model,
        display_name=display_name,
        segment_count=segment_count,
        painted=studio_apply_capability_state(model, CapabilityWorkflow.PAINTED),
        single=studio_apply_capability_state(model, CapabilityWorkflow.SINGLE),
        multi=studio_apply_capability_state(model, CapabilityWorkflow.MULTI),
        palette_diy=studio_apply_capability_state(model, CapabilityWorkflow.PALETTE_DIY),
        advanced=workflow_capability_state(model, CapabilityWorkflow.ADVANCED),
        music=studio_apply_capability_state(model, CapabilityWorkflow.NATIVE_MUSIC),
        video=studio_apply_capability_state(model, CapabilityWorkflow.VIDEO),
        workshop=studio_apply_capability_state(model, CapabilityWorkflow.WORKSHOP),
        readback="diy_code_only" if model == "H617A" else "scene_selector_for_user_effects",
        effect_categories=(default_effect_categories(model) if effect_categories is None else effect_categories),
    )
