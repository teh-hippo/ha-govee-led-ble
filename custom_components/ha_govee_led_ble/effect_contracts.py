"""Versioned contracts shared by the advanced backend and frontend."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Final

from .const import ModelProfile, default_effect_categories, get_profile, supported_effect_categories
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

EDITOR_API_VERSION: Final = 15
EDITOR_ASSET_VERSION: Final = 21
EFFECT_COMPILER_VERSION: Final = 5
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
    H6179_A1_EFFECT_UPLOAD = "h6179_a1_effect_upload"


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


_WORKFLOW_DEFAULTS: Final = {
    CapabilityWorkflow.NATIVE_SCENES: ("Scenes", "scene_builtin", CompilerDeployerStrategy.NATIVE_EFFECT_SELECTION),
    CapabilityWorkflow.EDITED_PALETTE_SCENES: (
        "Edited palette scenes",
        "scene_palette",
        CompilerDeployerStrategy.MODEL_SCENE_ENGINE,
    ),
    CapabilityWorkflow.LAYERED_SCENES: ("Layered scenes", "scene_layered", CompilerDeployerStrategy.MODEL_SCENE_ENGINE),
    CapabilityWorkflow.PAINTED: ("Painted", "h617a_painted", CompilerDeployerStrategy.H617A_CUSTOM_ENGINE),
    CapabilityWorkflow.SINGLE: ("Single", "h617a_single", CompilerDeployerStrategy.H617A_CUSTOM_ENGINE),
    CapabilityWorkflow.MULTI: ("Multi", "h617a_multi", CompilerDeployerStrategy.H617A_CUSTOM_ENGINE),
    CapabilityWorkflow.NATIVE_MUSIC: ("Music", "music_profile", CompilerDeployerStrategy.COORDINATOR_WRITER),
    CapabilityWorkflow.VIDEO: ("Video", "video_profile", CompilerDeployerStrategy.COORDINATOR_WRITER),
    CapabilityWorkflow.PALETTE_DIY: ("Palette DIY", "palette_diy", CompilerDeployerStrategy.H6199_CUSTOM_ENGINE),
    CapabilityWorkflow.ADVANCED: ("Advanced", "advanced", CompilerDeployerStrategy.MODEL_SCENE_ENGINE),
    CapabilityWorkflow.WORKSHOP: ("Workshop", "workshop", CompilerDeployerStrategy.A3_EFFECT_UPLOAD),
}
_STATE_CONFIRMED: Final = (VerificationConfidence.STATE_CONFIRMED, PhysicalValidationState.APPLICATION_VALIDATED)
_APPLICATION_VALIDATED: Final = (VerificationConfidence.SELECTION_ONLY, PhysicalValidationState.APPLICATION_VALIDATED)
_CAPTURE_VALIDATED: Final = (VerificationConfidence.SELECTION_ONLY, PhysicalValidationState.CAPTURE_VALIDATED)
_NOT_VALIDATED: Final = (VerificationConfidence.SELECTION_ONLY, PhysicalValidationState.NOT_VALIDATED)
_UNVERIFIED: Final = (VerificationConfidence.UNVERIFIED, PhysicalValidationState.NOT_VALIDATED)


def _capability(
    model: str,
    workflow: CapabilityWorkflow,
    validation: tuple[VerificationConfidence, PhysicalValidationState],
    evidence: EvidenceClassification = EvidenceClassification.STRUCTURAL,
) -> ReleaseCapability:
    label, content_kind, strategy = _WORKFLOW_DEFAULTS[workflow]
    return ReleaseCapability(
        model=model,
        workflow=workflow,
        label=label,
        frontend_visibility=FrontendVisibility.VISIBLE,
        persistent_content_kind=content_kind,
        application_route=(
            ApplicationRoute.STUDIO_SCENE_APPLY
            if workflow is CapabilityWorkflow.NATIVE_SCENES
            else ApplicationRoute.HOME_ASSISTANT_CONTROL
        ),
        compiler_deployer_strategy=strategy,
        verification_confidence=validation[0],
        physical_validation_state=validation[1],
        diagnostics_evidence_classification=evidence,
    )


_RELEASE_CAPABILITY_BASE: Final = (
    _capability("H617A", CapabilityWorkflow.NATIVE_SCENES, _STATE_CONFIRMED),
    _capability("H617A", CapabilityWorkflow.EDITED_PALETTE_SCENES, _CAPTURE_VALIDATED),
    _capability("H617A", CapabilityWorkflow.LAYERED_SCENES, _CAPTURE_VALIDATED),
    _capability("H617A", CapabilityWorkflow.PAINTED, _APPLICATION_VALIDATED, EvidenceClassification.DETERMINISTIC),
    _capability("H617A", CapabilityWorkflow.SINGLE, _APPLICATION_VALIDATED),
    _capability("H617A", CapabilityWorkflow.MULTI, _APPLICATION_VALIDATED),
    _capability("H617A", CapabilityWorkflow.NATIVE_MUSIC, _APPLICATION_VALIDATED, EvidenceClassification.LIVE),
    _capability("H617A", CapabilityWorkflow.ADVANCED, _CAPTURE_VALIDATED),
    _capability("H617A", CapabilityWorkflow.WORKSHOP, _CAPTURE_VALIDATED),
    _capability("H6179", CapabilityWorkflow.NATIVE_SCENES, _NOT_VALIDATED),
    *(
        replace(
            _capability("H6179", workflow, _NOT_VALIDATED),
            label=label,
            persistent_content_kind=content_kind,
            compiler_deployer_strategy=CompilerDeployerStrategy.H6179_A1_EFFECT_UPLOAD,
        )
        for workflow, label, content_kind in (
            (CapabilityWorkflow.SINGLE, "Single DIY", "h6179_single_diy"),
            (CapabilityWorkflow.MULTI, "Mixed DIY", "h6179_mixed_diy"),
        )
    ),
    _capability("H6179", CapabilityWorkflow.NATIVE_MUSIC, _NOT_VALIDATED),
    _capability("H6199", CapabilityWorkflow.NATIVE_SCENES, _STATE_CONFIRMED),
    _capability("H6199", CapabilityWorkflow.EDITED_PALETTE_SCENES, _CAPTURE_VALIDATED),
    _capability("H6199", CapabilityWorkflow.LAYERED_SCENES, _CAPTURE_VALIDATED),
    _capability("H6199", CapabilityWorkflow.PALETTE_DIY, _CAPTURE_VALIDATED),
    _capability("H6199", CapabilityWorkflow.NATIVE_MUSIC, _STATE_CONFIRMED, EvidenceClassification.LIVE),
    _capability("H6199", CapabilityWorkflow.VIDEO, _STATE_CONFIRMED, EvidenceClassification.LIVE),
    _capability("H6199", CapabilityWorkflow.ADVANCED, _CAPTURE_VALIDATED),
    _capability("H6199", CapabilityWorkflow.WORKSHOP, _CAPTURE_VALIDATED),
)


RELEASE_CAPABILITY_CONTRACT: Final = (
    _capability("H6102", CapabilityWorkflow.NATIVE_SCENES, _NOT_VALIDATED),
    _capability("H6102", CapabilityWorkflow.SINGLE, _NOT_VALIDATED),
    replace(_capability("H6102", CapabilityWorkflow.MULTI, _NOT_VALIDATED), label="Mixed"),
    _capability("H6102", CapabilityWorkflow.PAINTED, _NOT_VALIDATED),
    _capability("H6102", CapabilityWorkflow.NATIVE_MUSIC, _NOT_VALIDATED),
    _capability("H6102", CapabilityWorkflow.EDITED_PALETTE_SCENES, _NOT_VALIDATED),
    _capability("H6102", CapabilityWorkflow.LAYERED_SCENES, _NOT_VALIDATED),
    _capability("H6102", CapabilityWorkflow.ADVANCED, _NOT_VALIDATED),
    *(
        replace(
            _capability("H6099", workflow, _UNVERIFIED),
            label=label,
            compiler_deployer_strategy=CompilerDeployerStrategy.A3_EFFECT_UPLOAD,
        )
        for workflow, label in (
            (CapabilityWorkflow.PAINTED, "Graffiti"),
            (CapabilityWorkflow.SINGLE, "Basic"),
            (CapabilityWorkflow.MULTI, "Mixed"),
        )
    ),
    _capability("H6099", CapabilityWorkflow.NATIVE_SCENES, _UNVERIFIED),
    _capability("H6099", CapabilityWorkflow.NATIVE_MUSIC, _UNVERIFIED),
    _capability("H6099", CapabilityWorkflow.VIDEO, _UNVERIFIED),
    *(
        replace(
            capability,
            model="H6125",
            verification_confidence=VerificationConfidence.SELECTION_ONLY,
            physical_validation_state=PhysicalValidationState.NOT_VALIDATED,
        )
        for capability in _RELEASE_CAPABILITY_BASE
        if capability.model == "H617A"
        and capability.workflow
        in {
            CapabilityWorkflow.NATIVE_SCENES,
            CapabilityWorkflow.SINGLE,
            CapabilityWorkflow.MULTI,
            CapabilityWorkflow.NATIVE_MUSIC,
        }
    ),
    *(
        replace(
            capability,
            model="H6076",
            verification_confidence=VerificationConfidence.SELECTION_ONLY,
            physical_validation_state=PhysicalValidationState.NOT_VALIDATED,
            diagnostics_evidence_classification=EvidenceClassification.STRUCTURAL,
        )
        for capability in _RELEASE_CAPABILITY_BASE
        if capability.model == "H617A" and capability.workflow is CapabilityWorkflow.NATIVE_MUSIC
    ),
    *(capability for capability in _RELEASE_CAPABILITY_BASE if capability.model == "H617A"),
    *(replace(capability, model="H617C") for capability in _RELEASE_CAPABILITY_BASE if capability.model == "H617A"),
    *(replace(capability, model="H617E") for capability in _RELEASE_CAPABILITY_BASE if capability.model == "H617A"),
    *(capability for capability in _RELEASE_CAPABILITY_BASE if capability.model == "H6179"),
    *(replace(capability, model="H617F") for capability in _RELEASE_CAPABILITY_BASE if capability.model == "H617A"),
    *(capability for capability in _RELEASE_CAPABILITY_BASE if capability.model == "H6199"),
)


def release_capabilities_for_model(model: str) -> tuple[ReleaseCapability, ...]:
    return tuple(capability for capability in RELEASE_CAPABILITY_CONTRACT if capability.model == model)


def release_capability(model: str, workflow: CapabilityWorkflow) -> ReleaseCapability | None:
    return next(
        (
            capability
            for capability in RELEASE_CAPABILITY_CONTRACT
            if capability.model == model and capability.workflow is workflow
        ),
        None,
    )


def require_effect_route(
    model: str, workflow: CapabilityWorkflow, grammars: tuple[str, ...] = ("H617A", "H6199", "H6099", "H6179")
) -> str:
    """Require exact-model workflow authorization and matching effect/command grammar."""
    capability = release_capability(model, workflow)
    label = "Workshop" if workflow is CapabilityWorkflow.WORKSHOP else workflow.value
    if capability is None or capability.application_route not in {
        ApplicationRoute.STUDIO_SCENE_APPLY
        if workflow is CapabilityWorkflow.NATIVE_SCENES
        else ApplicationRoute.STUDIO_CUSTOM_APPLY,
        ApplicationRoute.HOME_ASSISTANT_CONTROL,
    }:
        raise ValueError(f"{model} {label} application is not supported")
    profile = get_profile(model)
    if (
        profile.effect_grammar is None
        or profile.effect_grammar not in grammars
        or profile.command_grammar != profile.effect_grammar
    ):
        raise ValueError(f"{model} has no supported {label} grammar and activation route")
    return profile.effect_grammar


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
    physical_ic_count: int | None = None

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "config_entry_id": self.config_entry_id,
            "light_entity_id": self.light_entity_id,
            "model": self.model,
            "support_quality": get_profile(self.model).support_quality.value,
            "display_name": self.display_name,
            "segment_count": self.segment_count,
            "physical_ic_count": self.physical_ic_count,
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
    physical_ic_count: int | None = None,
    profile: ModelProfile | None = None,
) -> DeviceEffectCapabilities:
    profile = get_profile(model) if profile is None else profile
    capabilities = DeviceEffectCapabilities(
        config_entry_id=config_entry_id,
        light_entity_id=light_entity_id,
        model=model,
        display_name=display_name,
        segment_count=segment_count,
        physical_ic_count=physical_ic_count,
        painted=studio_apply_capability_state(model, CapabilityWorkflow.PAINTED)
        if profile.supports_custom_effects
        else CapabilityState.UNSUPPORTED,
        single=studio_apply_capability_state(model, CapabilityWorkflow.SINGLE)
        if profile.supports_custom_effects
        else CapabilityState.UNSUPPORTED,
        multi=studio_apply_capability_state(model, CapabilityWorkflow.MULTI)
        if profile.supports_custom_effects
        else CapabilityState.UNSUPPORTED,
        palette_diy=studio_apply_capability_state(model, CapabilityWorkflow.PALETTE_DIY)
        if profile.supports_custom_effects
        else CapabilityState.UNSUPPORTED,
        advanced=workflow_capability_state(model, CapabilityWorkflow.ADVANCED)
        if profile.supports_advanced_effects
        else CapabilityState.UNSUPPORTED,
        music=studio_apply_capability_state(model, CapabilityWorkflow.NATIVE_MUSIC)
        if profile.supports_music_mode
        else CapabilityState.UNSUPPORTED,
        video=studio_apply_capability_state(model, CapabilityWorkflow.VIDEO)
        if profile.supports_video_mode
        else CapabilityState.UNSUPPORTED,
        workshop=studio_apply_capability_state(model, CapabilityWorkflow.WORKSHOP)
        if profile.supports_advanced_effects
        else CapabilityState.UNSUPPORTED,
        readback=profile.effect_readback,
        effect_categories=tuple(
            category
            for category in (default_effect_categories(model) if effect_categories is None else effect_categories)
            if category in supported_effect_categories(model, profile=profile)
        ),
    )
    if not supported_effect_categories(model, profile=profile):
        capabilities = replace(
            capabilities,
            painted=CapabilityState.UNSUPPORTED,
            single=CapabilityState.UNSUPPORTED,
            multi=CapabilityState.UNSUPPORTED,
            palette_diy=CapabilityState.UNSUPPORTED,
            advanced=CapabilityState.UNSUPPORTED,
            music=CapabilityState.UNSUPPORTED,
            video=CapabilityState.UNSUPPORTED,
            workshop=CapabilityState.UNSUPPORTED,
        )
    return capabilities
