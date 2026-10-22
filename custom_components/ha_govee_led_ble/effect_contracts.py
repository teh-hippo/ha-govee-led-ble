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

EDITOR_API_VERSION: Final = 16
EDITOR_ASSET_VERSION: Final = 22
EFFECT_COMPILER_VERSION: Final = 6
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


_RELEASE_CAPABILITY_BASE: Final = (
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
        "H6179",
        CapabilityWorkflow.NATIVE_SCENES,
        "Scenes",
        "scene_builtin",
        ApplicationRoute.STUDIO_SCENE_APPLY,
        CompilerDeployerStrategy.NATIVE_EFFECT_SELECTION,
        VerificationConfidence.SELECTION_ONLY,
        PhysicalValidationState.NOT_VALIDATED,
        EvidenceClassification.STRUCTURAL,
    ),
    _capability(
        "H6179",
        CapabilityWorkflow.SINGLE,
        "Single DIY",
        "h6179_single_diy",
        ApplicationRoute.HOME_ASSISTANT_CONTROL,
        CompilerDeployerStrategy.H6179_A1_EFFECT_UPLOAD,
        VerificationConfidence.SELECTION_ONLY,
        PhysicalValidationState.NOT_VALIDATED,
        EvidenceClassification.STRUCTURAL,
    ),
    _capability(
        "H6179",
        CapabilityWorkflow.MULTI,
        "Mixed DIY",
        "h6179_mixed_diy",
        ApplicationRoute.HOME_ASSISTANT_CONTROL,
        CompilerDeployerStrategy.H6179_A1_EFFECT_UPLOAD,
        VerificationConfidence.SELECTION_ONLY,
        PhysicalValidationState.NOT_VALIDATED,
        EvidenceClassification.STRUCTURAL,
    ),
    _capability(
        "H6179",
        CapabilityWorkflow.NATIVE_MUSIC,
        "Music",
        "music_profile",
        ApplicationRoute.HOME_ASSISTANT_CONTROL,
        CompilerDeployerStrategy.COORDINATOR_WRITER,
        VerificationConfidence.SELECTION_ONLY,
        PhysicalValidationState.NOT_VALIDATED,
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


RELEASE_CAPABILITY_CONTRACT: Final = (
    *(
        _capability(
            "H601C",
            workflow,
            label,
            kind,
            route,
            strategy,
            VerificationConfidence.UNVERIFIED,
            PhysicalValidationState.NOT_VALIDATED,
            EvidenceClassification.STRUCTURAL,
        )
        for workflow, label, kind, route, strategy in (
            (
                CapabilityWorkflow.NATIVE_SCENES,
                "Scenes",
                "scene_builtin",
                ApplicationRoute.STUDIO_SCENE_APPLY,
                CompilerDeployerStrategy.NATIVE_EFFECT_SELECTION,
            ),
            (
                CapabilityWorkflow.EDITED_PALETTE_SCENES,
                "Edited palette scenes",
                "scene_palette",
                ApplicationRoute.HOME_ASSISTANT_CONTROL,
                CompilerDeployerStrategy.MODEL_SCENE_ENGINE,
            ),
            (
                CapabilityWorkflow.SINGLE,
                "Basic DIY",
                "h617a_single",
                ApplicationRoute.HOME_ASSISTANT_CONTROL,
                CompilerDeployerStrategy.H617A_CUSTOM_ENGINE,
            ),
            (
                CapabilityWorkflow.MULTI,
                "Mixed DIY",
                "h617a_multi",
                ApplicationRoute.HOME_ASSISTANT_CONTROL,
                CompilerDeployerStrategy.H617A_CUSTOM_ENGINE,
            ),
        )
    ),
    *(
        _capability(
            "H6102",
            workflow,
            label,
            kind,
            route,
            strategy,
            VerificationConfidence.SELECTION_ONLY,
            PhysicalValidationState.NOT_VALIDATED,
            EvidenceClassification.STRUCTURAL,
        )
        for workflow, label, kind, route, strategy in (
            (
                CapabilityWorkflow.NATIVE_SCENES,
                "Scenes",
                "scene_builtin",
                ApplicationRoute.STUDIO_SCENE_APPLY,
                CompilerDeployerStrategy.NATIVE_EFFECT_SELECTION,
            ),
            (
                CapabilityWorkflow.SINGLE,
                "Single",
                "h617a_single",
                ApplicationRoute.HOME_ASSISTANT_CONTROL,
                CompilerDeployerStrategy.H617A_CUSTOM_ENGINE,
            ),
            (
                CapabilityWorkflow.MULTI,
                "Mixed",
                "h617a_multi",
                ApplicationRoute.HOME_ASSISTANT_CONTROL,
                CompilerDeployerStrategy.H617A_CUSTOM_ENGINE,
            ),
            (
                CapabilityWorkflow.PAINTED,
                "Painted",
                "h617a_painted",
                ApplicationRoute.HOME_ASSISTANT_CONTROL,
                CompilerDeployerStrategy.H617A_CUSTOM_ENGINE,
            ),
            (
                CapabilityWorkflow.NATIVE_MUSIC,
                "Music",
                "music_profile",
                ApplicationRoute.HOME_ASSISTANT_CONTROL,
                CompilerDeployerStrategy.COORDINATOR_WRITER,
            ),
            (
                CapabilityWorkflow.EDITED_PALETTE_SCENES,
                "Edited palette scenes",
                "scene_palette",
                ApplicationRoute.HOME_ASSISTANT_CONTROL,
                CompilerDeployerStrategy.MODEL_SCENE_ENGINE,
            ),
            (
                CapabilityWorkflow.LAYERED_SCENES,
                "Layered scenes",
                "scene_layered",
                ApplicationRoute.HOME_ASSISTANT_CONTROL,
                CompilerDeployerStrategy.MODEL_SCENE_ENGINE,
            ),
            (
                CapabilityWorkflow.ADVANCED,
                "Advanced",
                "advanced",
                ApplicationRoute.HOME_ASSISTANT_CONTROL,
                CompilerDeployerStrategy.MODEL_SCENE_ENGINE,
            ),
        )
    ),
    *(
        _capability(
            "H6099",
            workflow,
            label,
            kind,
            ApplicationRoute.HOME_ASSISTANT_CONTROL,
            CompilerDeployerStrategy.A3_EFFECT_UPLOAD,
            VerificationConfidence.UNVERIFIED,
            PhysicalValidationState.NOT_VALIDATED,
            EvidenceClassification.STRUCTURAL,
        )
        for workflow, label, kind in (
            (CapabilityWorkflow.PAINTED, "Graffiti", "h617a_painted"),
            (CapabilityWorkflow.SINGLE, "Basic", "h617a_single"),
            (CapabilityWorkflow.MULTI, "Mixed", "h617a_multi"),
        )
    ),
    _capability(
        "H6099",
        CapabilityWorkflow.NATIVE_SCENES,
        "Scenes",
        "scene_builtin",
        ApplicationRoute.STUDIO_SCENE_APPLY,
        CompilerDeployerStrategy.NATIVE_EFFECT_SELECTION,
        VerificationConfidence.UNVERIFIED,
        PhysicalValidationState.NOT_VALIDATED,
        EvidenceClassification.STRUCTURAL,
    ),
    _capability(
        "H6099",
        CapabilityWorkflow.NATIVE_MUSIC,
        "Music",
        "music_profile",
        ApplicationRoute.HOME_ASSISTANT_CONTROL,
        CompilerDeployerStrategy.COORDINATOR_WRITER,
        VerificationConfidence.UNVERIFIED,
        PhysicalValidationState.NOT_VALIDATED,
        EvidenceClassification.STRUCTURAL,
    ),
    _capability(
        "H6099",
        CapabilityWorkflow.VIDEO,
        "Video",
        "video_profile",
        ApplicationRoute.HOME_ASSISTANT_CONTROL,
        CompilerDeployerStrategy.COORDINATOR_WRITER,
        VerificationConfidence.UNVERIFIED,
        PhysicalValidationState.NOT_VALIDATED,
        EvidenceClassification.STRUCTURAL,
    ),
    *(
        _capability(
            "H7025",
            workflow,
            label,
            kind,
            route,
            strategy,
            VerificationConfidence.SELECTION_ONLY,
            PhysicalValidationState.NOT_VALIDATED,
            EvidenceClassification.STRUCTURAL,
        )
        for workflow, label, kind, route, strategy in (
            (
                CapabilityWorkflow.NATIVE_SCENES,
                "Scenes",
                "scene_builtin",
                ApplicationRoute.STUDIO_SCENE_APPLY,
                CompilerDeployerStrategy.NATIVE_EFFECT_SELECTION,
            ),
            (
                CapabilityWorkflow.LAYERED_SCENES,
                "Layered scenes",
                "scene_layered",
                ApplicationRoute.HOME_ASSISTANT_CONTROL,
                CompilerDeployerStrategy.MODEL_SCENE_ENGINE,
            ),
            (
                CapabilityWorkflow.SINGLE,
                "Basic DIY",
                "h617a_single",
                ApplicationRoute.HOME_ASSISTANT_CONTROL,
                CompilerDeployerStrategy.H617A_CUSTOM_ENGINE,
            ),
            (
                CapabilityWorkflow.MULTI,
                "Mixed DIY",
                "h617a_multi",
                ApplicationRoute.HOME_ASSISTANT_CONTROL,
                CompilerDeployerStrategy.H617A_CUSTOM_ENGINE,
            ),
            (
                CapabilityWorkflow.NATIVE_MUSIC,
                "Music",
                "music_profile",
                ApplicationRoute.HOME_ASSISTANT_CONTROL,
                CompilerDeployerStrategy.COORDINATOR_WRITER,
            ),
        )
    ),
    *(
        replace(
            capability,
            model="H6125",
            verification_confidence=VerificationConfidence.SELECTION_ONLY,
            physical_validation_state=PhysicalValidationState.NOT_VALIDATED,
            diagnostics_evidence_classification=EvidenceClassification.STRUCTURAL,
        )
        for capability in _RELEASE_CAPABILITY_BASE
        if capability.model == "H617A"
        and capability.workflow
        in {
            CapabilityWorkflow.NATIVE_SCENES,
            CapabilityWorkflow.EDITED_PALETTE_SCENES,
            CapabilityWorkflow.LAYERED_SCENES,
            CapabilityWorkflow.PAINTED,
            CapabilityWorkflow.SINGLE,
            CapabilityWorkflow.MULTI,
            CapabilityWorkflow.NATIVE_MUSIC,
            CapabilityWorkflow.ADVANCED,
            CapabilityWorkflow.WORKSHOP,
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
        if capability.model == "H617A"
        and capability.workflow
        in {
            CapabilityWorkflow.NATIVE_SCENES,
            CapabilityWorkflow.LAYERED_SCENES,
            CapabilityWorkflow.PAINTED,
            CapabilityWorkflow.SINGLE,
            CapabilityWorkflow.MULTI,
            CapabilityWorkflow.NATIVE_MUSIC,
            CapabilityWorkflow.ADVANCED,
            CapabilityWorkflow.WORKSHOP,
        }
    ),
    *(capability for capability in _RELEASE_CAPABILITY_BASE if capability.model == "H617A"),
    *(replace(capability, model="H617C") for capability in _RELEASE_CAPABILITY_BASE if capability.model == "H617A"),
    *(replace(capability, model="H617E") for capability in _RELEASE_CAPABILITY_BASE if capability.model == "H617A"),
    *(capability for capability in _RELEASE_CAPABILITY_BASE if capability.model == "H6179"),
    *(replace(capability, model="H617F") for capability in _RELEASE_CAPABILITY_BASE if capability.model == "H617A"),
    *(capability for capability in _RELEASE_CAPABILITY_BASE if capability.model == "H6199"),
    *(
        _capability(
            "H7020",
            workflow,
            label,
            kind,
            route,
            strategy,
            VerificationConfidence.SELECTION_ONLY,
            PhysicalValidationState.NOT_VALIDATED,
            EvidenceClassification.STRUCTURAL,
        )
        for workflow, label, kind, route, strategy in (
            (
                CapabilityWorkflow.NATIVE_SCENES,
                "Scenes",
                "scene_builtin",
                ApplicationRoute.STUDIO_SCENE_APPLY,
                CompilerDeployerStrategy.NATIVE_EFFECT_SELECTION,
            ),
            (
                CapabilityWorkflow.LAYERED_SCENES,
                "Layered scenes",
                "scene_layered",
                ApplicationRoute.HOME_ASSISTANT_CONTROL,
                CompilerDeployerStrategy.MODEL_SCENE_ENGINE,
            ),
            (
                CapabilityWorkflow.SINGLE,
                "Basic DIY",
                "h617a_single",
                ApplicationRoute.HOME_ASSISTANT_CONTROL,
                CompilerDeployerStrategy.H617A_CUSTOM_ENGINE,
            ),
            (
                CapabilityWorkflow.MULTI,
                "Mixed DIY",
                "h617a_multi",
                ApplicationRoute.HOME_ASSISTANT_CONTROL,
                CompilerDeployerStrategy.H617A_CUSTOM_ENGINE,
            ),
            (
                CapabilityWorkflow.ADVANCED,
                "Template DIY",
                "advanced",
                ApplicationRoute.HOME_ASSISTANT_CONTROL,
                CompilerDeployerStrategy.MODEL_SCENE_ENGINE,
            ),
            (
                CapabilityWorkflow.NATIVE_MUSIC,
                "Music",
                "music_profile",
                ApplicationRoute.HOME_ASSISTANT_CONTROL,
                CompilerDeployerStrategy.COORDINATOR_WRITER,
            ),
        )
    ),
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


def profile_supports_workflow(profile: ModelProfile, workflow: CapabilityWorkflow, *, model: str | None = None) -> bool:
    """Apply device restrictions without promoting its exact-SKU workflow ceiling."""
    if profile.effect_workflows is not None and workflow.value not in profile.effect_workflows:
        return False
    advanced_supported = profile.supports_advanced_effects or (
        profile.supports_custom_effects
        and (
            (
                model is not None
                and not get_profile(model).supports_advanced_effects
                and release_capability(model, CapabilityWorkflow.ADVANCED) is not None
            )
            or (model is None and profile.command_grammar == "H7020")
        )
    )
    return {
        CapabilityWorkflow.NATIVE_SCENES: profile.supports_scenes,
        CapabilityWorkflow.EDITED_PALETTE_SCENES: profile.supports_scenes,
        CapabilityWorkflow.LAYERED_SCENES: profile.supports_scenes,
        CapabilityWorkflow.PAINTED: profile.supports_custom_effects,
        CapabilityWorkflow.SINGLE: profile.supports_custom_effects,
        CapabilityWorkflow.MULTI: profile.supports_custom_effects,
        CapabilityWorkflow.NATIVE_MUSIC: profile.supports_music_mode,
        CapabilityWorkflow.VIDEO: profile.supports_video_mode,
        CapabilityWorkflow.PALETTE_DIY: profile.supports_custom_effects,
        CapabilityWorkflow.ADVANCED: advanced_supported,
        CapabilityWorkflow.WORKSHOP: profile.supports_advanced_effects,
    }[workflow]


def require_effect_route(
    model: str,
    workflow: CapabilityWorkflow,
    grammars: tuple[str, ...] = ("H617A", "H6199", "H6099", "H6179"),
    *,
    profile: ModelProfile | None = None,
) -> str:
    """Require independently declared body, upload, activation and readback routes."""
    capability = release_capability(model, workflow)
    label = "Workshop" if workflow is CapabilityWorkflow.WORKSHOP else workflow.value
    if capability is None or capability.application_route not in {
        ApplicationRoute.STUDIO_SCENE_APPLY
        if workflow is CapabilityWorkflow.NATIVE_SCENES
        else ApplicationRoute.STUDIO_CUSTOM_APPLY,
        ApplicationRoute.HOME_ASSISTANT_CONTROL,
    }:
        raise ValueError(f"{model} {label} application is not supported")
    profile = get_profile(model) if profile is None else profile
    if (profile.effect_workflows is not None and workflow.value not in profile.effect_workflows) or (
        profile != get_profile(model) and not profile_supports_workflow(profile, workflow, model=model)
    ):
        raise ValueError(f"{model} effective profile does not support {label}")
    if profile.effect_grammar is None or profile.effect_grammar not in grammars or profile.command_grammar is None:
        raise ValueError(f"{model} has no supported {label} grammar and activation route")
    from .generated_protocol_adapter import build_diy_activation, build_scene_activation

    # The activation codec is independent of the upload codec, but must exist.
    try:
        if workflow in {CapabilityWorkflow.PAINTED, CapabilityWorkflow.SINGLE, CapabilityWorkflow.MULTI}:
            build_diy_activation(0, model, profile=profile)
        else:
            build_scene_activation(model, 0, profile=profile)
    except ValueError as error:
        raise ValueError(f"{model} has no supported {label} grammar and activation route") from error
    return profile.effect_grammar


def frontend_release_capabilities(model: str, *, profile: ModelProfile | None = None) -> list[JsonValue]:
    return [
        capability.to_frontend_dict()
        for capability in release_capabilities_for_model(model)
        if capability.frontend_visibility is FrontendVisibility.VISIBLE
        and (profile is None or profile_supports_workflow(profile, capability.workflow, model=model))
    ]


def diagnostics_release_capabilities(model: str) -> dict[str, JsonValue]:
    return {
        "schema_version": RELEASE_CAPABILITY_SCHEMA_VERSION,
        "model": model,
        "capabilities": [capability.to_diagnostics_dict() for capability in release_capabilities_for_model(model)],
    }


def workflow_capability_state(
    model: str, workflow: CapabilityWorkflow, *, profile: ModelProfile | None = None
) -> CapabilityState:
    if profile is not None and not profile_supports_workflow(profile, workflow, model=model):
        return CapabilityState.UNSUPPORTED
    capability = release_capability(model, workflow)
    if capability is None or capability.frontend_visibility is not FrontendVisibility.VISIBLE:
        return CapabilityState.UNSUPPORTED
    if (
        capability.application_route is ApplicationRoute.NONE
        and capability.verification_confidence is VerificationConfidence.UNVERIFIED
    ):
        return CapabilityState.EVIDENCE_GAP
    return CapabilityState.SUPPORTED


def studio_apply_capability_state(
    model: str, workflow: CapabilityWorkflow, *, profile: ModelProfile | None = None
) -> CapabilityState:
    if profile is not None and not profile_supports_workflow(profile, workflow, model=model):
        return CapabilityState.UNSUPPORTED
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
        painted=studio_apply_capability_state(model, CapabilityWorkflow.PAINTED, profile=profile)
        if profile.supports_custom_effects
        else CapabilityState.UNSUPPORTED,
        single=studio_apply_capability_state(model, CapabilityWorkflow.SINGLE, profile=profile)
        if profile.supports_custom_effects
        else CapabilityState.UNSUPPORTED,
        multi=studio_apply_capability_state(model, CapabilityWorkflow.MULTI, profile=profile)
        if profile.supports_custom_effects
        else CapabilityState.UNSUPPORTED,
        palette_diy=studio_apply_capability_state(model, CapabilityWorkflow.PALETTE_DIY, profile=profile)
        if profile.supports_custom_effects
        else CapabilityState.UNSUPPORTED,
        advanced=workflow_capability_state(model, CapabilityWorkflow.ADVANCED, profile=profile)
        if profile.supports_advanced_effects
        or profile.supports_custom_effects
        and release_capability(model, CapabilityWorkflow.ADVANCED) is not None
        else CapabilityState.UNSUPPORTED,
        music=studio_apply_capability_state(model, CapabilityWorkflow.NATIVE_MUSIC, profile=profile)
        if profile.supports_music_mode
        else CapabilityState.UNSUPPORTED,
        video=studio_apply_capability_state(model, CapabilityWorkflow.VIDEO, profile=profile)
        if profile.supports_video_mode
        else CapabilityState.UNSUPPORTED,
        workshop=studio_apply_capability_state(model, CapabilityWorkflow.WORKSHOP, profile=profile)
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
