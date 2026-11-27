"""Versioned contracts shared by the advanced backend and frontend."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Final

from .const import ModelProfile, default_effect_categories, get_profile, supported_effect_categories
from .effect_content_ids import (
    MULTI_EFFECT_CONTENT_KIND,
    PAINTED_EFFECT_CONTENT_KIND,
    SINGLE_EFFECT_CONTENT_KIND,
    TYPED_DIY_COMPILER_STRATEGY,
    TYPED_MIXED_DIY_CONTENT_KIND,
    TYPED_SINGLE_DIY_CONTENT_KIND,
)
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
from .layered_scene_decoder import RETAINED_WORKSHOP_GRAMMARS

EDITOR_API_VERSION: Final = 23
EDITOR_ASSET_VERSION: Final = 51
EFFECT_COMPILER_VERSION: Final = 13
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
    GENERIC_DIY_ENGINE = "h617a_custom_engine"
    PALETTE_DIY_ENGINE = "h6199_custom_engine"
    MODEL_SCENE_ENGINE = "model_scene_engine"
    COORDINATOR_WRITER = "coordinator_writer"
    A3_EFFECT_UPLOAD = "a3_effect_upload"
    TYPED_DIY_UPLOAD = TYPED_DIY_COMPILER_STRATEGY


class VerificationConfidence(StrEnum):
    STATE_CONFIRMED = "state_confirmed"
    SELECTION_ONLY = "selection_only"
    UNVERIFIED = "unverified"


class ContentProjection(StrEnum):
    DIRECT = "direct"
    GENERIC_DIY = "generic_diy"
    PALETTE_DIY = "palette_diy"
    TYPED_DIY = "typed_diy"


class SelectorPolicy(StrEnum):
    FIXED = "fixed"
    APPROVED_DISPOSABLE = "approved_disposable"
    CATALOGUE_SELECTOR_ONLY = "catalogue_selector_only"


class FrontendApplicationState(StrEnum):
    STUDIO = "studio"
    HOME_ASSISTANT = "home_assistant"
    PLANNED = "planned"


_SHARED_SCENE_CONTENT_GRAMMARS: Final = frozenset({"H617A", "H6199"})


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
    activation_operations: frozenset[str]
    content_grammars: frozenset[str]
    content_projection: ContentProjection
    selector_policy: SelectorPolicy
    upload_carriers: frozenset[str]
    typed_diy_pairs: frozenset[tuple[int, int]] = frozenset()
    content_reference: bool = False

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
        }


def _capability(
    model: str,
    workflow: CapabilityWorkflow,
    label: str,
    persistent_content_kind: str,
    application_route: ApplicationRoute,
    compiler_deployer_strategy: CompilerDeployerStrategy,
    verification_confidence: VerificationConfidence,
    *,
    activation_operations: frozenset[str] | None = None,
    selector_policy: SelectorPolicy = SelectorPolicy.FIXED,
    upload_carriers: frozenset[str] = frozenset(),
    typed_diy_pairs: frozenset[tuple[int, int]] = frozenset(),
    content_reference: bool = False,
) -> ReleaseCapability:
    projection = (
        ContentProjection.PALETTE_DIY
        if persistent_content_kind == "palette_diy"
        else ContentProjection.TYPED_DIY
        if persistent_content_kind in {TYPED_SINGLE_DIY_CONTENT_KIND, TYPED_MIXED_DIY_CONTENT_KIND}
        else ContentProjection.GENERIC_DIY
        if persistent_content_kind
        in {PAINTED_EFFECT_CONTENT_KIND, SINGLE_EFFECT_CONTENT_KIND, MULTI_EFFECT_CONTENT_KIND}
        else ContentProjection.DIRECT
    )
    upload_carriers = (
        frozenset({"rgbic_v1"}) if not upload_carriers and persistent_content_kind == "workshop" else upload_carriers
    )
    return ReleaseCapability(
        model=model,
        workflow=workflow,
        label=label,
        frontend_visibility=FrontendVisibility.VISIBLE,
        persistent_content_kind=persistent_content_kind,
        application_route=application_route,
        compiler_deployer_strategy=compiler_deployer_strategy,
        verification_confidence=verification_confidence,
        activation_operations=activation_operations
        if activation_operations is not None
        else frozenset(
            {"diy"}
            if workflow in {CapabilityWorkflow.PAINTED, CapabilityWorkflow.SINGLE, CapabilityWorkflow.MULTI}
            or persistent_content_kind == "native_effect"
            and workflow is CapabilityWorkflow.ADVANCED
            else {"scene"}
        ),
        content_grammars=(
            RETAINED_WORKSHOP_GRAMMARS
            if persistent_content_kind == "workshop"
            else _SHARED_SCENE_CONTENT_GRAMMARS
            if workflow
            in {
                CapabilityWorkflow.NATIVE_SCENES,
                CapabilityWorkflow.EDITED_PALETTE_SCENES,
                CapabilityWorkflow.LAYERED_SCENES,
                CapabilityWorkflow.ADVANCED,
            }
            and get_profile(model).effect_grammar in _SHARED_SCENE_CONTENT_GRAMMARS
            else frozenset(grammar for grammar in (get_profile(model).effect_grammar,) if grammar is not None)
        ),
        content_projection=projection,
        selector_policy=(
            selector_policy
            if workflow in _DIY_SELECTOR_WORKFLOWS or selector_policy is _P.CATALOGUE_SELECTOR_ONLY
            else _P.FIXED
        ),
        upload_carriers=upload_carriers,
        typed_diy_pairs=typed_diy_pairs,
        content_reference=content_reference,
    )


def _accepted_content_kinds(target_kind: str) -> frozenset[str]:
    return {
        SINGLE_EFFECT_CONTENT_KIND: frozenset(
            {SINGLE_EFFECT_CONTENT_KIND, TYPED_SINGLE_DIY_CONTENT_KIND, "palette_diy"}
        ),
        MULTI_EFFECT_CONTENT_KIND: frozenset({MULTI_EFFECT_CONTENT_KIND, TYPED_MIXED_DIY_CONTENT_KIND}),
        TYPED_SINGLE_DIY_CONTENT_KIND: frozenset(
            {SINGLE_EFFECT_CONTENT_KIND, TYPED_SINGLE_DIY_CONTENT_KIND, "palette_diy"}
        ),
        TYPED_MIXED_DIY_CONTENT_KIND: frozenset({MULTI_EFFECT_CONTENT_KIND, TYPED_MIXED_DIY_CONTENT_KIND}),
        "palette_diy": frozenset({SINGLE_EFFECT_CONTENT_KIND, TYPED_SINGLE_DIY_CONTENT_KIND, "palette_diy"}),
    }.get(target_kind, frozenset({target_kind}))


# Short aliases keep the capability table one row per line.
_W, _R, _S, _V, _P = (
    CapabilityWorkflow,
    ApplicationRoute,
    CompilerDeployerStrategy,
    VerificationConfidence,
    SelectorPolicy,
)


@dataclass(frozen=True, slots=True)
class CapabilityDeclaration:
    workflow: CapabilityWorkflow
    label: str
    persistent_content_kind: str
    application_route: ApplicationRoute
    compiler_deployer_strategy: CompilerDeployerStrategy
    verification_confidence: VerificationConfidence
    selector_policy: SelectorPolicy = SelectorPolicy.FIXED
    upload_carriers: frozenset[str] = frozenset()


_DIY_SELECTOR_WORKFLOWS: Final = frozenset(
    {
        CapabilityWorkflow.PAINTED,
        CapabilityWorkflow.SINGLE,
        CapabilityWorkflow.MULTI,
        CapabilityWorkflow.PALETTE_DIY,
        CapabilityWorkflow.ADVANCED,
    }
)


def _declared_capabilities(
    model: str,
    declarations: tuple[CapabilityDeclaration, ...],
    *,
    confidence: VerificationConfidence | None = None,
    selector_policy: SelectorPolicy | None = None,
) -> tuple[ReleaseCapability, ...]:
    return tuple(
        _capability(
            model,
            declaration.workflow,
            declaration.label,
            declaration.persistent_content_kind,
            declaration.application_route,
            declaration.compiler_deployer_strategy,
            confidence or declaration.verification_confidence,
            selector_policy=(
                selector_policy
                if selector_policy is not None and declaration.workflow in _DIY_SELECTOR_WORKFLOWS
                else declaration.selector_policy
            ),
            upload_carriers=declaration.upload_carriers,
        )
        for declaration in declarations
    )


_RGBIC_WORKFLOW_DECLARATIONS: Final = (
    CapabilityDeclaration(
        _W.NATIVE_SCENES,
        "Scenes",
        "scene_builtin",
        _R.STUDIO_SCENE_APPLY,
        _S.NATIVE_EFFECT_SELECTION,
        _V.STATE_CONFIRMED,
        upload_carriers=frozenset({"rgb"}),
    ),
    CapabilityDeclaration(
        _W.EDITED_PALETTE_SCENES,
        "Edited palette scenes",
        "scene_palette",
        _R.HOME_ASSISTANT_CONTROL,
        _S.MODEL_SCENE_ENGINE,
        _V.SELECTION_ONLY,
        upload_carriers=frozenset({"rgbic_v1"}),
    ),
    CapabilityDeclaration(
        _W.LAYERED_SCENES,
        "Layered scenes",
        "scene_layered",
        _R.HOME_ASSISTANT_CONTROL,
        _S.MODEL_SCENE_ENGINE,
        _V.SELECTION_ONLY,
        upload_carriers=frozenset({"rgbic_v1"}),
    ),
    CapabilityDeclaration(
        _W.PAINTED,
        "Painted",
        PAINTED_EFFECT_CONTENT_KIND,
        _R.HOME_ASSISTANT_CONTROL,
        _S.GENERIC_DIY_ENGINE,
        _V.SELECTION_ONLY,
    ),
    CapabilityDeclaration(
        _W.SINGLE,
        "Single",
        SINGLE_EFFECT_CONTENT_KIND,
        _R.HOME_ASSISTANT_CONTROL,
        _S.GENERIC_DIY_ENGINE,
        _V.SELECTION_ONLY,
    ),
    CapabilityDeclaration(
        _W.MULTI,
        "Multi",
        MULTI_EFFECT_CONTENT_KIND,
        _R.HOME_ASSISTANT_CONTROL,
        _S.GENERIC_DIY_ENGINE,
        _V.SELECTION_ONLY,
    ),
    CapabilityDeclaration(
        _W.NATIVE_MUSIC,
        "Music",
        "music_profile",
        _R.HOME_ASSISTANT_CONTROL,
        _S.COORDINATOR_WRITER,
        _V.SELECTION_ONLY,
    ),
    CapabilityDeclaration(
        _W.ADVANCED,
        "Advanced",
        "advanced",
        _R.HOME_ASSISTANT_CONTROL,
        _S.MODEL_SCENE_ENGINE,
        _V.SELECTION_ONLY,
    ),
    CapabilityDeclaration(
        _W.WORKSHOP,
        "Workshop",
        "workshop",
        _R.HOME_ASSISTANT_CONTROL,
        _S.A3_EFFECT_UPLOAD,
        _V.SELECTION_ONLY,
        upload_carriers=frozenset({"rgbic_v1"}),
    ),
)


_RELEASE_CAPABILITY_BASE: Final = (
    *(
        _capability(
            "H6022",
            workflow,
            label,
            kind,
            route,
            strategy,
            _V.SELECTION_ONLY,
        )
        for workflow, label, kind, route, strategy in (
            (_W.NATIVE_SCENES, "Scenes", "scene_builtin", _R.STUDIO_SCENE_APPLY, _S.NATIVE_EFFECT_SELECTION),
            (_W.SINGLE, "Single DIY", SINGLE_EFFECT_CONTENT_KIND, _R.HOME_ASSISTANT_CONTROL, _S.GENERIC_DIY_ENGINE),
            (_W.NATIVE_MUSIC, "Music", "music_profile", _R.HOME_ASSISTANT_CONTROL, _S.COORDINATOR_WRITER),
        )
    ),
    *(
        _capability(
            "H6046",
            workflow,
            label,
            kind,
            route,
            strategy,
            _V.SELECTION_ONLY,
            selector_policy=_P.APPROVED_DISPOSABLE,
            upload_carriers=(
                frozenset({"rgb"})
                if workflow is _W.NATIVE_SCENES
                else frozenset({"rgbic_v1"})
                if workflow in {_W.LAYERED_SCENES, _W.WORKSHOP}
                else frozenset()
            ),
        )
        for workflow, label, kind, route, strategy in (
            (_W.NATIVE_SCENES, "Scenes", "scene_builtin", _R.STUDIO_SCENE_APPLY, _S.NATIVE_EFFECT_SELECTION),
            (
                _W.EDITED_PALETTE_SCENES,
                "Edited palette scenes",
                "scene_palette",
                _R.HOME_ASSISTANT_CONTROL,
                _S.MODEL_SCENE_ENGINE,
            ),
            (_W.LAYERED_SCENES, "Layered scenes", "scene_layered", _R.HOME_ASSISTANT_CONTROL, _S.MODEL_SCENE_ENGINE),
            (_W.SINGLE, "Basic DIY", SINGLE_EFFECT_CONTENT_KIND, _R.HOME_ASSISTANT_CONTROL, _S.GENERIC_DIY_ENGINE),
            (_W.MULTI, "Mixed DIY", MULTI_EFFECT_CONTENT_KIND, _R.HOME_ASSISTANT_CONTROL, _S.GENERIC_DIY_ENGINE),
            (_W.NATIVE_MUSIC, "Music", "music_profile", _R.HOME_ASSISTANT_CONTROL, _S.COORDINATOR_WRITER),
            (_W.ADVANCED, "Advanced", "advanced", _R.HOME_ASSISTANT_CONTROL, _S.MODEL_SCENE_ENGINE),
            (_W.WORKSHOP, "Workshop", "workshop", _R.HOME_ASSISTANT_CONTROL, _S.MODEL_SCENE_ENGINE),
        )
    ),
    *(
        _capability(
            "H6053",
            workflow,
            label,
            kind,
            route,
            strategy,
            _V.SELECTION_ONLY,
            selector_policy=_P.APPROVED_DISPOSABLE,
            upload_carriers=(
                frozenset({"rgb"})
                if workflow is _W.NATIVE_SCENES
                else frozenset({"rgbic_v1"})
                if workflow is _W.LAYERED_SCENES
                else frozenset({"rgb", "rgbic_v1", "rgbic_v2"})
                if workflow is _W.WORKSHOP
                else frozenset()
            ),
        )
        for workflow, label, kind, route, strategy in (
            (_W.NATIVE_SCENES, "Scenes", "scene_builtin", _R.STUDIO_SCENE_APPLY, _S.NATIVE_EFFECT_SELECTION),
            (
                _W.EDITED_PALETTE_SCENES,
                "Edited palette scenes",
                "scene_palette",
                _R.HOME_ASSISTANT_CONTROL,
                _S.MODEL_SCENE_ENGINE,
            ),
            (_W.LAYERED_SCENES, "Layered scenes", "scene_layered", _R.HOME_ASSISTANT_CONTROL, _S.MODEL_SCENE_ENGINE),
            (_W.SINGLE, "Basic DIY", SINGLE_EFFECT_CONTENT_KIND, _R.HOME_ASSISTANT_CONTROL, _S.GENERIC_DIY_ENGINE),
            (_W.MULTI, "Mixed DIY", MULTI_EFFECT_CONTENT_KIND, _R.HOME_ASSISTANT_CONTROL, _S.GENERIC_DIY_ENGINE),
            (_W.NATIVE_MUSIC, "Music", "music_profile", _R.HOME_ASSISTANT_CONTROL, _S.COORDINATOR_WRITER),
            (_W.ADVANCED, "Layered effects", "advanced", _R.HOME_ASSISTANT_CONTROL, _S.MODEL_SCENE_ENGINE),
            (_W.WORKSHOP, "Workshop", "workshop", _R.HOME_ASSISTANT_CONTROL, _S.MODEL_SCENE_ENGINE),
        )
    ),
    _capability(
        "H617A",
        _W.NATIVE_SCENES,
        "Scenes",
        "scene_builtin",
        _R.STUDIO_SCENE_APPLY,
        _S.NATIVE_EFFECT_SELECTION,
        _V.STATE_CONFIRMED,
        upload_carriers=frozenset({"rgb"}),
    ),
    _capability(
        "H617A",
        _W.EDITED_PALETTE_SCENES,
        "Edited palette scenes",
        "scene_palette",
        _R.HOME_ASSISTANT_CONTROL,
        _S.MODEL_SCENE_ENGINE,
        _V.SELECTION_ONLY,
        upload_carriers=frozenset({"rgbic_v1"}),
    ),
    _capability(
        "H617A",
        _W.LAYERED_SCENES,
        "Layered scenes",
        "scene_layered",
        _R.HOME_ASSISTANT_CONTROL,
        _S.MODEL_SCENE_ENGINE,
        _V.SELECTION_ONLY,
        upload_carriers=frozenset({"rgbic_v1"}),
    ),
    _capability(
        "H617A",
        _W.PAINTED,
        "Painted",
        PAINTED_EFFECT_CONTENT_KIND,
        _R.HOME_ASSISTANT_CONTROL,
        _S.GENERIC_DIY_ENGINE,
        _V.SELECTION_ONLY,
        content_reference=True,
    ),
    _capability(
        "H617A",
        _W.SINGLE,
        "Single",
        SINGLE_EFFECT_CONTENT_KIND,
        _R.HOME_ASSISTANT_CONTROL,
        _S.GENERIC_DIY_ENGINE,
        _V.SELECTION_ONLY,
        content_reference=True,
    ),
    _capability(
        "H617A",
        _W.MULTI,
        "Multi",
        MULTI_EFFECT_CONTENT_KIND,
        _R.HOME_ASSISTANT_CONTROL,
        _S.GENERIC_DIY_ENGINE,
        _V.SELECTION_ONLY,
        content_reference=True,
    ),
    _capability(
        "H617A",
        _W.NATIVE_MUSIC,
        "Music",
        "music_profile",
        _R.HOME_ASSISTANT_CONTROL,
        _S.COORDINATOR_WRITER,
        _V.SELECTION_ONLY,
    ),
    _capability(
        "H617A",
        _W.ADVANCED,
        "Advanced",
        "advanced",
        _R.HOME_ASSISTANT_CONTROL,
        _S.MODEL_SCENE_ENGINE,
        _V.SELECTION_ONLY,
    ),
    _capability(
        "H617A",
        _W.WORKSHOP,
        "Workshop",
        "workshop",
        _R.HOME_ASSISTANT_CONTROL,
        _S.A3_EFFECT_UPLOAD,
        _V.SELECTION_ONLY,
        upload_carriers=frozenset({"rgbic_v1"}),
    ),
    _capability(
        "H6179",
        _W.NATIVE_SCENES,
        "Scenes",
        "scene_builtin",
        _R.STUDIO_SCENE_APPLY,
        _S.NATIVE_EFFECT_SELECTION,
        _V.SELECTION_ONLY,
        selector_policy=_P.CATALOGUE_SELECTOR_ONLY,
    ),
    _capability(
        "H6179",
        _W.SINGLE,
        "Single DIY",
        TYPED_SINGLE_DIY_CONTENT_KIND,
        _R.HOME_ASSISTANT_CONTROL,
        _S.TYPED_DIY_UPLOAD,
        _V.SELECTION_ONLY,
        selector_policy=_P.APPROVED_DISPOSABLE,
        typed_diy_pairs=frozenset({(0, 0), (1, 0), (2, 0)}),
    ),
    _capability(
        "H6179",
        _W.MULTI,
        "Mixed DIY",
        TYPED_MIXED_DIY_CONTENT_KIND,
        _R.HOME_ASSISTANT_CONTROL,
        _S.TYPED_DIY_UPLOAD,
        _V.SELECTION_ONLY,
        selector_policy=_P.APPROVED_DISPOSABLE,
        typed_diy_pairs=frozenset({(0, 0), (1, 0), (2, 0)}),
    ),
    _capability(
        "H6179",
        _W.NATIVE_MUSIC,
        "Music",
        "music_profile",
        _R.HOME_ASSISTANT_CONTROL,
        _S.COORDINATOR_WRITER,
        _V.SELECTION_ONLY,
    ),
    _capability(
        "H6199",
        _W.NATIVE_SCENES,
        "Scenes",
        "scene_builtin",
        _R.STUDIO_SCENE_APPLY,
        _S.NATIVE_EFFECT_SELECTION,
        _V.STATE_CONFIRMED,
        upload_carriers=frozenset({"rgb"}),
    ),
    _capability(
        "H6199",
        _W.EDITED_PALETTE_SCENES,
        "Edited palette scenes",
        "scene_palette",
        _R.HOME_ASSISTANT_CONTROL,
        _S.MODEL_SCENE_ENGINE,
        _V.SELECTION_ONLY,
        upload_carriers=frozenset({"rgbic_v1"}),
    ),
    _capability(
        "H6199",
        _W.LAYERED_SCENES,
        "Layered scenes",
        "scene_layered",
        _R.HOME_ASSISTANT_CONTROL,
        _S.MODEL_SCENE_ENGINE,
        _V.SELECTION_ONLY,
        upload_carriers=frozenset({"rgbic_v1"}),
    ),
    _capability(
        "H6199",
        _W.PALETTE_DIY,
        "Palette DIY",
        "palette_diy",
        _R.HOME_ASSISTANT_CONTROL,
        _S.PALETTE_DIY_ENGINE,
        _V.SELECTION_ONLY,
        activation_operations=frozenset({"diy"}),
        selector_policy=_P.APPROVED_DISPOSABLE,
    ),
    _capability(
        "H6199",
        _W.NATIVE_MUSIC,
        "Music",
        "music_profile",
        _R.HOME_ASSISTANT_CONTROL,
        _S.COORDINATOR_WRITER,
        _V.STATE_CONFIRMED,
    ),
    _capability(
        "H6199",
        _W.VIDEO,
        "Video",
        "video_profile",
        _R.HOME_ASSISTANT_CONTROL,
        _S.COORDINATOR_WRITER,
        _V.STATE_CONFIRMED,
    ),
    _capability(
        "H6199",
        _W.ADVANCED,
        "Advanced",
        "advanced",
        _R.HOME_ASSISTANT_CONTROL,
        _S.MODEL_SCENE_ENGINE,
        _V.SELECTION_ONLY,
    ),
    _capability(
        "H6199",
        _W.WORKSHOP,
        "Workshop",
        "workshop",
        _R.HOME_ASSISTANT_CONTROL,
        _S.A3_EFFECT_UPLOAD,
        _V.SELECTION_ONLY,
        upload_carriers=frozenset({"rgbic_v1"}),
    ),
)


RELEASE_CAPABILITY_CONTRACT: Final = (
    *_RELEASE_CAPABILITY_BASE,
    *(
        _capability(
            "H60B0",
            workflow,
            label,
            kind,
            route,
            strategy,
            _V.UNVERIFIED,
            activation_operations=frozenset({"scene", "diy"}) if workflow is _W.MULTI else None,
        )
        for workflow, label, kind, route, strategy in (
            (_W.NATIVE_SCENES, "Scenes", "scene_builtin", _R.STUDIO_SCENE_APPLY, _S.NATIVE_EFFECT_SELECTION),
            (
                _W.LAYERED_SCENES,
                "Side and ripple scenes",
                "scene_layered",
                _R.STUDIO_CUSTOM_APPLY,
                _S.MODEL_SCENE_ENGINE,
            ),
            (_W.SINGLE, "DIY", "native_effect", _R.STUDIO_CUSTOM_APPLY, _S.A3_EFFECT_UPLOAD),
            (_W.MULTI, "Combined DIY", "native_effect", _R.STUDIO_CUSTOM_APPLY, _S.A3_EFFECT_UPLOAD),
            (_W.ADVANCED, "Ripple DIY", "native_effect", _R.STUDIO_CUSTOM_APPLY, _S.A3_EFFECT_UPLOAD),
            (_W.NATIVE_MUSIC, "Music", "music_profile", _R.STUDIO_CUSTOM_APPLY, _S.COORDINATOR_WRITER),
        )
    ),
    *(
        _capability("H1771", workflow, label, kind, route, strategy, _V.UNVERIFIED)
        for workflow, label, kind, route, strategy in (
            (_W.NATIVE_SCENES, "Scenes", "scene_builtin", _R.STUDIO_SCENE_APPLY, _S.NATIVE_EFFECT_SELECTION),
            (_W.LAYERED_SCENES, "Native scenes", "native_effect", _R.STUDIO_CUSTOM_APPLY, _S.MODEL_SCENE_ENGINE),
            (_W.SINGLE, "DIY", "native_effect", _R.STUDIO_CUSTOM_APPLY, _S.A3_EFFECT_UPLOAD),
            (_W.MULTI, "Combined DIY", "native_effect", _R.STUDIO_CUSTOM_APPLY, _S.A3_EFFECT_UPLOAD),
            (_W.ADVANCED, "Advanced DIY", "native_effect", _R.STUDIO_CUSTOM_APPLY, _S.A3_EFFECT_UPLOAD),
            (_W.NATIVE_MUSIC, "Music", "music_profile", _R.STUDIO_CUSTOM_APPLY, _S.COORDINATOR_WRITER),
        )
    ),
    *(
        _capability("H60B2", workflow, label, kind, route, strategy, _V.UNVERIFIED)
        for workflow, label, kind, route, strategy in (
            (_W.NATIVE_SCENES, "Scenes", "scene_builtin", _R.STUDIO_SCENE_APPLY, _S.NATIVE_EFFECT_SELECTION),
            (
                _W.EDITED_PALETTE_SCENES,
                "Palette scenes",
                "scene_palette",
                _R.STUDIO_CUSTOM_APPLY,
                _S.MODEL_SCENE_ENGINE,
            ),
            (_W.LAYERED_SCENES, "Layered scenes", "scene_layered", _R.STUDIO_CUSTOM_APPLY, _S.MODEL_SCENE_ENGINE),
            (_W.SINGLE, "DIY", "native_effect", _R.STUDIO_CUSTOM_APPLY, _S.A3_EFFECT_UPLOAD),
            (_W.ADVANCED, "Layered effects", "advanced", _R.STUDIO_CUSTOM_APPLY, _S.A3_EFFECT_UPLOAD),
            (_W.WORKSHOP, "Workshop", "workshop", _R.STUDIO_CUSTOM_APPLY, _S.A3_EFFECT_UPLOAD),
            (_W.NATIVE_MUSIC, "Music", "music_profile", _R.STUDIO_CUSTOM_APPLY, _S.COORDINATOR_WRITER),
        )
    ),
    _capability(
        "H607C",
        _W.WORKSHOP,
        "Workshop",
        "workshop",
        _R.NONE,
        _S.A3_EFFECT_UPLOAD,
        _V.UNVERIFIED,
    ),
    *(
        _capability("H607C", workflow, label, kind, route, strategy, _V.SELECTION_ONLY)
        for workflow, label, kind, route, strategy in (
            (_W.NATIVE_SCENES, "Scenes", "scene_builtin", _R.STUDIO_SCENE_APPLY, _S.NATIVE_EFFECT_SELECTION),
            (_W.LAYERED_SCENES, "Layered scenes", "scene_layered", _R.STUDIO_CUSTOM_APPLY, _S.MODEL_SCENE_ENGINE),
            (_W.SINGLE, "Native DIY", "native_effect", _R.STUDIO_CUSTOM_APPLY, _S.A3_EFFECT_UPLOAD),
            (_W.MULTI, "Pole and base DIY", "native_effect", _R.STUDIO_CUSTOM_APPLY, _S.A3_EFFECT_UPLOAD),
            (_W.PAINTED, "Paint", PAINTED_EFFECT_CONTENT_KIND, _R.STUDIO_CUSTOM_APPLY, _S.A3_EFFECT_UPLOAD),
            (_W.NATIVE_MUSIC, "Music", "music_profile", _R.STUDIO_CUSTOM_APPLY, _S.COORDINATOR_WRITER),
        )
    ),
    *(
        _capability(
            model,
            workflow,
            label,
            kind,
            _R.STUDIO_SCENE_APPLY if workflow is _W.NATIVE_SCENES else _R.HOME_ASSISTANT_CONTROL,
            _S.NATIVE_EFFECT_SELECTION if workflow is _W.NATIVE_SCENES else _S.A3_EFFECT_UPLOAD,
            _V.SELECTION_ONLY,
        )
        for model, workflow, label, kind in (
            ("H60A1", _W.NATIVE_SCENES, "Scenes", "scene_builtin"),
            ("H60A1", _W.LAYERED_SCENES, "Layered scenes", "scene_layered"),
            ("H60A1", _W.SINGLE, "Single DIY", SINGLE_EFFECT_CONTENT_KIND),
            ("H60A1", _W.MULTI, "Mixed DIY", MULTI_EFFECT_CONTENT_KIND),
            ("H60A6", _W.NATIVE_SCENES, "Scenes", "scene_builtin"),
            ("H60A6", _W.LAYERED_SCENES, "Native scenes", "native_effect"),
            ("H60A6", _W.SINGLE, "Native DIY", "native_effect"),
            ("H60A6", _W.MULTI, "Native layers", "native_effect"),
            ("H60A6", _W.PAINTED, "Paint", "native_effect"),
            ("H60A6", _W.ADVANCED, "Native meteor", "native_effect"),
        )
    ),
    *(
        _capability("H6093", workflow, label, kind, route, strategy, _V.UNVERIFIED)
        for workflow, label, kind, route, strategy in (
            (_W.NATIVE_SCENES, "Scenes", "scene_builtin", _R.STUDIO_SCENE_APPLY, _S.NATIVE_EFFECT_SELECTION),
            (_W.LAYERED_SCENES, "Projector scenes", "native_effect", _R.STUDIO_CUSTOM_APPLY, _S.MODEL_SCENE_ENGINE),
            (_W.SINGLE, "Projector presets", "native_effect", _R.STUDIO_CUSTOM_APPLY, _S.A3_EFFECT_UPLOAD),
            (_W.ADVANCED, "Projector effects", "native_effect", _R.STUDIO_CUSTOM_APPLY, _S.A3_EFFECT_UPLOAD),
        )
    ),
    *(
        _capability(
            "H600A",
            workflow,
            label,
            kind,
            route,
            strategy,
            _V.SELECTION_ONLY,
            selector_policy=(_P.APPROVED_DISPOSABLE if workflow in _DIY_SELECTOR_WORKFLOWS else _P.FIXED),
        )
        for workflow, label, kind, route, strategy in (
            (_W.NATIVE_SCENES, "Scenes", "scene_builtin", _R.STUDIO_SCENE_APPLY, _S.NATIVE_EFFECT_SELECTION),
            (
                _W.EDITED_PALETTE_SCENES,
                "Edited palette scenes",
                "scene_palette",
                _R.HOME_ASSISTANT_CONTROL,
                _S.MODEL_SCENE_ENGINE,
            ),
            (_W.SINGLE, "Basic DIY", SINGLE_EFFECT_CONTENT_KIND, _R.HOME_ASSISTANT_CONTROL, _S.GENERIC_DIY_ENGINE),
            (_W.MULTI, "Mixed DIY", MULTI_EFFECT_CONTENT_KIND, _R.HOME_ASSISTANT_CONTROL, _S.GENERIC_DIY_ENGINE),
        )
    ),
    *(
        _capability("H601C", workflow, label, kind, route, strategy, _V.UNVERIFIED)
        for workflow, label, kind, route, strategy in (
            (_W.NATIVE_SCENES, "Scenes", "scene_builtin", _R.STUDIO_SCENE_APPLY, _S.NATIVE_EFFECT_SELECTION),
            (
                _W.EDITED_PALETTE_SCENES,
                "Edited palette scenes",
                "scene_palette",
                _R.HOME_ASSISTANT_CONTROL,
                _S.MODEL_SCENE_ENGINE,
            ),
            (_W.SINGLE, "Basic DIY", SINGLE_EFFECT_CONTENT_KIND, _R.HOME_ASSISTANT_CONTROL, _S.GENERIC_DIY_ENGINE),
            (_W.MULTI, "Mixed DIY", MULTI_EFFECT_CONTENT_KIND, _R.HOME_ASSISTANT_CONTROL, _S.GENERIC_DIY_ENGINE),
        )
    ),
    *(
        _capability("H6102", workflow, label, kind, route, strategy, _V.SELECTION_ONLY)
        for workflow, label, kind, route, strategy in (
            (_W.NATIVE_SCENES, "Scenes", "scene_builtin", _R.STUDIO_SCENE_APPLY, _S.NATIVE_EFFECT_SELECTION),
            (_W.SINGLE, "Single", SINGLE_EFFECT_CONTENT_KIND, _R.HOME_ASSISTANT_CONTROL, _S.GENERIC_DIY_ENGINE),
            (_W.MULTI, "Mixed", MULTI_EFFECT_CONTENT_KIND, _R.HOME_ASSISTANT_CONTROL, _S.GENERIC_DIY_ENGINE),
            (_W.PAINTED, "Painted", PAINTED_EFFECT_CONTENT_KIND, _R.HOME_ASSISTANT_CONTROL, _S.GENERIC_DIY_ENGINE),
            (_W.NATIVE_MUSIC, "Music", "music_profile", _R.HOME_ASSISTANT_CONTROL, _S.COORDINATOR_WRITER),
            (
                _W.EDITED_PALETTE_SCENES,
                "Edited palette scenes",
                "scene_palette",
                _R.HOME_ASSISTANT_CONTROL,
                _S.MODEL_SCENE_ENGINE,
            ),
            (_W.LAYERED_SCENES, "Layered scenes", "scene_layered", _R.HOME_ASSISTANT_CONTROL, _S.MODEL_SCENE_ENGINE),
            (_W.ADVANCED, "Advanced", "advanced", _R.HOME_ASSISTANT_CONTROL, _S.MODEL_SCENE_ENGINE),
        )
    ),
    *(
        _capability(
            "H6097",
            workflow,
            label,
            kind,
            route,
            strategy,
            _V.UNVERIFIED,
        )
        for workflow, label, kind, route, strategy in (
            (_W.PAINTED, "Graffiti", PAINTED_EFFECT_CONTENT_KIND, _R.HOME_ASSISTANT_CONTROL, _S.A3_EFFECT_UPLOAD),
            (_W.SINGLE, "Basic", SINGLE_EFFECT_CONTENT_KIND, _R.HOME_ASSISTANT_CONTROL, _S.A3_EFFECT_UPLOAD),
            (_W.MULTI, "Mixed", MULTI_EFFECT_CONTENT_KIND, _R.HOME_ASSISTANT_CONTROL, _S.A3_EFFECT_UPLOAD),
            (_W.NATIVE_SCENES, "Scenes", "scene_builtin", _R.STUDIO_SCENE_APPLY, _S.NATIVE_EFFECT_SELECTION),
            (
                _W.EDITED_PALETTE_SCENES,
                "Edited palette scenes",
                "scene_palette",
                _R.HOME_ASSISTANT_CONTROL,
                _S.MODEL_SCENE_ENGINE,
            ),
            (_W.LAYERED_SCENES, "Layered scenes", "scene_layered", _R.HOME_ASSISTANT_CONTROL, _S.MODEL_SCENE_ENGINE),
            (_W.NATIVE_MUSIC, "Music", "music_profile", _R.HOME_ASSISTANT_CONTROL, _S.COORDINATOR_WRITER),
            (_W.VIDEO, "Video", "video_profile", _R.HOME_ASSISTANT_CONTROL, _S.COORDINATOR_WRITER),
        )
    ),
    *(
        _capability(
            "H6099",
            workflow,
            label,
            kind,
            _R.HOME_ASSISTANT_CONTROL,
            _S.A3_EFFECT_UPLOAD,
            _V.UNVERIFIED,
        )
        for workflow, label, kind in (
            (_W.PAINTED, "Graffiti", PAINTED_EFFECT_CONTENT_KIND),
            (_W.SINGLE, "Basic", SINGLE_EFFECT_CONTENT_KIND),
            (_W.MULTI, "Mixed", MULTI_EFFECT_CONTENT_KIND),
        )
    ),
    *(
        _capability(
            "H8604",
            workflow,
            label,
            kind,
            route,
            strategy,
            _V.UNVERIFIED,
            upload_carriers=(
                frozenset({"rgb"})
                if workflow is _W.NATIVE_SCENES
                else (
                    frozenset({"rgbic_v1"})
                    if workflow in {_W.EDITED_PALETTE_SCENES, _W.LAYERED_SCENES}
                    else frozenset()
                )
            ),
        )
        for workflow, label, kind, route, strategy in (
            (_W.NATIVE_SCENES, "Scenes", "scene_builtin", _R.STUDIO_SCENE_APPLY, _S.NATIVE_EFFECT_SELECTION),
            (
                _W.EDITED_PALETTE_SCENES,
                "Edited palette scenes",
                "scene_palette",
                _R.HOME_ASSISTANT_CONTROL,
                _S.MODEL_SCENE_ENGINE,
            ),
            (_W.LAYERED_SCENES, "Layered scenes", "scene_layered", _R.HOME_ASSISTANT_CONTROL, _S.MODEL_SCENE_ENGINE),
            (_W.PAINTED, "Graffiti", PAINTED_EFFECT_CONTENT_KIND, _R.HOME_ASSISTANT_CONTROL, _S.A3_EFFECT_UPLOAD),
            (_W.SINGLE, "Basic", SINGLE_EFFECT_CONTENT_KIND, _R.HOME_ASSISTANT_CONTROL, _S.A3_EFFECT_UPLOAD),
            (_W.MULTI, "Mixed", MULTI_EFFECT_CONTENT_KIND, _R.HOME_ASSISTANT_CONTROL, _S.A3_EFFECT_UPLOAD),
            (_W.NATIVE_MUSIC, "Music", "music_profile", _R.HOME_ASSISTANT_CONTROL, _S.COORDINATOR_WRITER),
            (_W.VIDEO, "Video", "video_profile", _R.HOME_ASSISTANT_CONTROL, _S.COORDINATOR_WRITER),
            (_W.ADVANCED, "Advanced", "advanced", _R.HOME_ASSISTANT_CONTROL, _S.MODEL_SCENE_ENGINE),
            (_W.WORKSHOP, "Workshop", "workshop", _R.HOME_ASSISTANT_CONTROL, _S.MODEL_SCENE_ENGINE),
        )
    ),
    _capability(
        "H6099",
        _W.NATIVE_SCENES,
        "Scenes",
        "scene_builtin",
        _R.STUDIO_SCENE_APPLY,
        _S.NATIVE_EFFECT_SELECTION,
        _V.UNVERIFIED,
    ),
    _capability(
        "H6099",
        _W.NATIVE_MUSIC,
        "Music",
        "music_profile",
        _R.HOME_ASSISTANT_CONTROL,
        _S.COORDINATOR_WRITER,
        _V.UNVERIFIED,
    ),
    _capability(
        "H6099",
        _W.VIDEO,
        "Video",
        "video_profile",
        _R.HOME_ASSISTANT_CONTROL,
        _S.COORDINATOR_WRITER,
        _V.UNVERIFIED,
    ),
    *(
        _capability(
            "H66A0",
            workflow,
            label,
            kind,
            _R.HOME_ASSISTANT_CONTROL,
            _S.A3_EFFECT_UPLOAD,
            _V.UNVERIFIED,
        )
        for workflow, label, kind in (
            (_W.PAINTED, "Graffiti", PAINTED_EFFECT_CONTENT_KIND),
            (_W.SINGLE, "Basic", SINGLE_EFFECT_CONTENT_KIND),
            (_W.MULTI, "Mixed", MULTI_EFFECT_CONTENT_KIND),
        )
    ),
    _capability(
        "H66A0",
        _W.NATIVE_SCENES,
        "Scenes",
        "scene_builtin",
        _R.STUDIO_SCENE_APPLY,
        _S.NATIVE_EFFECT_SELECTION,
        _V.SELECTION_ONLY,
    ),
    _capability(
        "H66A0",
        _W.NATIVE_MUSIC,
        "Music",
        "music_profile",
        _R.HOME_ASSISTANT_CONTROL,
        _S.COORDINATOR_WRITER,
        _V.SELECTION_ONLY,
    ),
    _capability(
        "H66A0",
        _W.VIDEO,
        "Video",
        "video_profile",
        _R.HOME_ASSISTANT_CONTROL,
        _S.COORDINATOR_WRITER,
        _V.UNVERIFIED,
    ),
    *(
        _capability(
            "H1A42",
            workflow,
            label,
            kind,
            _R.HOME_ASSISTANT_CONTROL,
            _S.A3_EFFECT_UPLOAD,
            _V.UNVERIFIED,
        )
        for workflow, label, kind in (
            (_W.PAINTED, "Graffiti", PAINTED_EFFECT_CONTENT_KIND),
            (_W.SINGLE, "Basic", SINGLE_EFFECT_CONTENT_KIND),
            (_W.MULTI, "Mixed", MULTI_EFFECT_CONTENT_KIND),
        )
    ),
    _capability(
        "H1A42",
        _W.NATIVE_SCENES,
        "Scenes",
        "scene_builtin",
        _R.STUDIO_SCENE_APPLY,
        _S.NATIVE_EFFECT_SELECTION,
        _V.SELECTION_ONLY,
    ),
    _capability(
        "H1A42",
        _W.NATIVE_MUSIC,
        "Music",
        "music_profile",
        _R.HOME_ASSISTANT_CONTROL,
        _S.COORDINATOR_WRITER,
        _V.SELECTION_ONLY,
    ),
    _capability(
        "H1A42",
        _W.ADVANCED,
        "Native presets",
        "advanced",
        _R.HOME_ASSISTANT_CONTROL,
        _S.MODEL_SCENE_ENGINE,
        _V.SELECTION_ONLY,
    ),
    *(
        _capability(
            "H61F5",
            workflow,
            label,
            kind,
            _R.HOME_ASSISTANT_CONTROL,
            _S.A3_EFFECT_UPLOAD,
            _V.UNVERIFIED,
        )
        for workflow, label, kind in (
            (_W.PAINTED, "Graffiti", PAINTED_EFFECT_CONTENT_KIND),
            (_W.SINGLE, "Basic", SINGLE_EFFECT_CONTENT_KIND),
            (_W.MULTI, "Mixed", MULTI_EFFECT_CONTENT_KIND),
        )
    ),
    *(
        _capability(
            "H61E5",
            workflow,
            label,
            kind,
            route,
            strategy,
            _V.UNVERIFIED,
        )
        for workflow, label, kind, route, strategy in (
            (_W.NATIVE_SCENES, "Scenes", "scene_builtin", _R.STUDIO_SCENE_APPLY, _S.NATIVE_EFFECT_SELECTION),
            (_W.PAINTED, "Graffiti", PAINTED_EFFECT_CONTENT_KIND, _R.HOME_ASSISTANT_CONTROL, _S.A3_EFFECT_UPLOAD),
            (_W.SINGLE, "Basic", SINGLE_EFFECT_CONTENT_KIND, _R.HOME_ASSISTANT_CONTROL, _S.A3_EFFECT_UPLOAD),
            (_W.MULTI, "Mixed", MULTI_EFFECT_CONTENT_KIND, _R.HOME_ASSISTANT_CONTROL, _S.A3_EFFECT_UPLOAD),
            (_W.NATIVE_MUSIC, "Music", "music_profile", _R.HOME_ASSISTANT_CONTROL, _S.COORDINATOR_WRITER),
            (_W.ADVANCED, "Advanced", "advanced", _R.HOME_ASSISTANT_CONTROL, _S.MODEL_SCENE_ENGINE),
        )
    ),
    _capability(
        "H61F5",
        _W.ADVANCED,
        "Native presets",
        "advanced",
        _R.HOME_ASSISTANT_CONTROL,
        _S.MODEL_SCENE_ENGINE,
        _V.SELECTION_ONLY,
    ),
    _capability(
        "H61F5",
        _W.NATIVE_SCENES,
        "Scenes",
        "scene_builtin",
        _R.STUDIO_SCENE_APPLY,
        _S.NATIVE_EFFECT_SELECTION,
        _V.SELECTION_ONLY,
    ),
    _capability(
        "H61F5",
        _W.NATIVE_MUSIC,
        "Music",
        "music_profile",
        _R.HOME_ASSISTANT_CONTROL,
        _S.COORDINATOR_WRITER,
        _V.SELECTION_ONLY,
    ),
    *(
        _capability("H1AB2", workflow, label, kind, route, strategy, _V.UNVERIFIED)
        for workflow, label, kind, route, strategy in (
            (_W.NATIVE_SCENES, "Scenes", "scene_builtin", _R.STUDIO_SCENE_APPLY, _S.NATIVE_EFFECT_SELECTION),
            (_W.LAYERED_SCENES, "Layered scenes", "scene_layered", _R.HOME_ASSISTANT_CONTROL, _S.MODEL_SCENE_ENGINE),
            (_W.PAINTED, "Paint", PAINTED_EFFECT_CONTENT_KIND, _R.HOME_ASSISTANT_CONTROL, _S.A3_EFFECT_UPLOAD),
            (_W.SINGLE, "Basic", "native_effect", _R.HOME_ASSISTANT_CONTROL, _S.A3_EFFECT_UPLOAD),
            (_W.MULTI, "Mixed", MULTI_EFFECT_CONTENT_KIND, _R.HOME_ASSISTANT_CONTROL, _S.A3_EFFECT_UPLOAD),
            (_W.ADVANCED, "Advanced", "advanced", _R.HOME_ASSISTANT_CONTROL, _S.MODEL_SCENE_ENGINE),
            (_W.WORKSHOP, "Workshop", "workshop", _R.HOME_ASSISTANT_CONTROL, _S.MODEL_SCENE_ENGINE),
            (_W.NATIVE_MUSIC, "Music", "music_profile", _R.HOME_ASSISTANT_CONTROL, _S.COORDINATOR_WRITER),
        )
    ),
    *(
        _capability(
            "H7025",
            workflow,
            label,
            kind,
            route,
            strategy,
            _V.SELECTION_ONLY,
            selector_policy=(_P.APPROVED_DISPOSABLE if workflow in _DIY_SELECTOR_WORKFLOWS else _P.FIXED),
        )
        for workflow, label, kind, route, strategy in (
            (_W.NATIVE_SCENES, "Scenes", "scene_builtin", _R.STUDIO_SCENE_APPLY, _S.NATIVE_EFFECT_SELECTION),
            (_W.LAYERED_SCENES, "Layered scenes", "scene_layered", _R.HOME_ASSISTANT_CONTROL, _S.MODEL_SCENE_ENGINE),
            (_W.SINGLE, "Basic DIY", SINGLE_EFFECT_CONTENT_KIND, _R.HOME_ASSISTANT_CONTROL, _S.GENERIC_DIY_ENGINE),
            (_W.MULTI, "Mixed DIY", MULTI_EFFECT_CONTENT_KIND, _R.HOME_ASSISTANT_CONTROL, _S.GENERIC_DIY_ENGINE),
            (_W.NATIVE_MUSIC, "Music", "music_profile", _R.HOME_ASSISTANT_CONTROL, _S.COORDINATOR_WRITER),
        )
    ),
    *tuple(
        capability
        for model in ("H6117", "H612A", "H6125", "H6127", "H618A", "H619A", "H705A")
        for capability in _declared_capabilities(model, _RGBIC_WORKFLOW_DECLARATIONS, confidence=_V.SELECTION_ONLY)
    ),
    *_declared_capabilities(
        "H6076",
        tuple(
            declaration
            for declaration in _RGBIC_WORKFLOW_DECLARATIONS
            if declaration.workflow is not _W.EDITED_PALETTE_SCENES
        ),
        confidence=_V.SELECTION_ONLY,
    ),
    *_declared_capabilities(
        "H6072",
        tuple(declaration for declaration in _RGBIC_WORKFLOW_DECLARATIONS if declaration.workflow is not _W.WORKSHOP),
        confidence=_V.SELECTION_ONLY,
        selector_policy=_P.APPROVED_DISPOSABLE,
    ),
    *_declared_capabilities("H617C", _RGBIC_WORKFLOW_DECLARATIONS, confidence=_V.SELECTION_ONLY),
    *_declared_capabilities("H617E", _RGBIC_WORKFLOW_DECLARATIONS),
    *(
        _capability(
            model,
            workflow,
            label,
            kind,
            route,
            strategy,
            _V.UNVERIFIED,
            selector_policy=selector_policy if workflow in _DIY_SELECTOR_WORKFLOWS else _P.FIXED,
        )
        for model, selector_policy in (
            ("H6138", _P.FIXED),
            ("H6139", _P.FIXED),
            ("H6159", _P.FIXED),
            ("H6181", _P.APPROVED_DISPOSABLE),
            ("H6182", _P.APPROVED_DISPOSABLE),
        )
        for workflow, label, kind, route, strategy in (
            (_W.NATIVE_SCENES, "Scenes", "scene_builtin", _R.STUDIO_SCENE_APPLY, _S.NATIVE_EFFECT_SELECTION),
            (
                _W.EDITED_PALETTE_SCENES,
                "Edited palette scenes",
                "scene_palette",
                _R.HOME_ASSISTANT_CONTROL,
                _S.MODEL_SCENE_ENGINE,
            ),
            (_W.SINGLE, "Basic DIY", SINGLE_EFFECT_CONTENT_KIND, _R.HOME_ASSISTANT_CONTROL, _S.GENERIC_DIY_ENGINE),
            (_W.MULTI, "Mixed DIY", MULTI_EFFECT_CONTENT_KIND, _R.HOME_ASSISTANT_CONTROL, _S.GENERIC_DIY_ENGINE),
            (_W.NATIVE_MUSIC, "Music", "music_profile", _R.HOME_ASSISTANT_CONTROL, _S.COORDINATOR_WRITER),
        )
    ),
    *_declared_capabilities("H617F", _RGBIC_WORKFLOW_DECLARATIONS),
    *(
        _capability(
            "H605C",
            workflow,
            label,
            kind,
            route,
            strategy,
            _V.UNVERIFIED,
            selector_policy=(_P.APPROVED_DISPOSABLE if workflow in _DIY_SELECTOR_WORKFLOWS else _P.FIXED),
        )
        for workflow, label, kind, route, strategy in (
            (_W.NATIVE_SCENES, "Scenes", "scene_builtin", _R.STUDIO_SCENE_APPLY, _S.NATIVE_EFFECT_SELECTION),
            (
                _W.EDITED_PALETTE_SCENES,
                "Edited palette scenes",
                "scene_palette",
                _R.HOME_ASSISTANT_CONTROL,
                _S.MODEL_SCENE_ENGINE,
            ),
            (_W.LAYERED_SCENES, "Layered scenes", "scene_layered", _R.HOME_ASSISTANT_CONTROL, _S.MODEL_SCENE_ENGINE),
            (_W.PAINTED, "Paint", PAINTED_EFFECT_CONTENT_KIND, _R.HOME_ASSISTANT_CONTROL, _S.GENERIC_DIY_ENGINE),
            (_W.SINGLE, "Basic DIY", SINGLE_EFFECT_CONTENT_KIND, _R.HOME_ASSISTANT_CONTROL, _S.GENERIC_DIY_ENGINE),
            (_W.MULTI, "Mixed DIY", MULTI_EFFECT_CONTENT_KIND, _R.HOME_ASSISTANT_CONTROL, _S.GENERIC_DIY_ENGINE),
            (_W.NATIVE_MUSIC, "Music", "music_profile", _R.HOME_ASSISTANT_CONTROL, _S.COORDINATOR_WRITER),
            (_W.VIDEO, "Video", "video_profile", _R.HOME_ASSISTANT_CONTROL, _S.COORDINATOR_WRITER),
            (_W.ADVANCED, "Advanced", "advanced", _R.HOME_ASSISTANT_CONTROL, _S.MODEL_SCENE_ENGINE),
            (_W.WORKSHOP, "Workshop", "workshop", _R.HOME_ASSISTANT_CONTROL, _S.MODEL_SCENE_ENGINE),
        )
    ),
    *(
        _capability(
            "H7020",
            workflow,
            label,
            kind,
            route,
            strategy,
            _V.SELECTION_ONLY,
            activation_operations=frozenset({"diy"}) if workflow is _W.ADVANCED else None,
            selector_policy=(_P.APPROVED_DISPOSABLE if workflow in _DIY_SELECTOR_WORKFLOWS else _P.FIXED),
        )
        for workflow, label, kind, route, strategy in (
            (_W.NATIVE_SCENES, "Scenes", "scene_builtin", _R.STUDIO_SCENE_APPLY, _S.NATIVE_EFFECT_SELECTION),
            (_W.LAYERED_SCENES, "Layered scenes", "scene_layered", _R.HOME_ASSISTANT_CONTROL, _S.MODEL_SCENE_ENGINE),
            (_W.SINGLE, "Basic DIY", SINGLE_EFFECT_CONTENT_KIND, _R.HOME_ASSISTANT_CONTROL, _S.GENERIC_DIY_ENGINE),
            (_W.MULTI, "Mixed DIY", MULTI_EFFECT_CONTENT_KIND, _R.HOME_ASSISTANT_CONTROL, _S.GENERIC_DIY_ENGINE),
            (_W.ADVANCED, "Template DIY", "advanced", _R.HOME_ASSISTANT_CONTROL, _S.MODEL_SCENE_ENGINE),
            (_W.NATIVE_MUSIC, "Music", "music_profile", _R.HOME_ASSISTANT_CONTROL, _S.COORDINATOR_WRITER),
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


def release_projection_capability(model: str, source_content_kind: str) -> ReleaseCapability | None:
    capabilities = release_capabilities_for_model(model)
    return next(
        (capability for capability in capabilities if capability.persistent_content_kind == source_content_kind),
        next(
            (
                capability
                for capability in capabilities
                if source_content_kind in _accepted_content_kinds(capability.persistent_content_kind)
            ),
            None,
        ),
    )


def release_content_capability(model: str, content_kind: str) -> ReleaseCapability | None:
    return next(
        (
            capability
            for capability in release_capabilities_for_model(model)
            if capability.persistent_content_kind == content_kind
        ),
        None,
    )


def release_content_reference_model(content_kind: str) -> str | None:
    return next(
        (
            capability.model
            for capability in RELEASE_CAPABILITY_CONTRACT
            if capability.content_reference and capability.persistent_content_kind == content_kind
        ),
        None,
    )


def release_selector_policy(model: str, workflow: CapabilityWorkflow | None = None) -> SelectorPolicy:
    if workflow is None:
        capabilities = release_capabilities_for_model(model)
    else:
        capability = release_capability(model, workflow)
        return SelectorPolicy.FIXED if capability is None else capability.selector_policy
    return (
        SelectorPolicy.APPROVED_DISPOSABLE
        if any(
            capability.selector_policy is SelectorPolicy.APPROVED_DISPOSABLE
            and capability.content_projection is not ContentProjection.DIRECT
            for capability in capabilities
        )
        else SelectorPolicy.FIXED
    )


def require_upload_carrier(model: str, workflow: CapabilityWorkflow, carrier: str) -> None:
    capability = release_capability(model, workflow)
    if capability is None or carrier not in capability.upload_carriers:
        raise ValueError(f"{model} has no {carrier} upload carrier for {workflow.value}")


def profile_supports_workflow(profile: ModelProfile, workflow: CapabilityWorkflow, *, model: str | None = None) -> bool:
    """Apply device restrictions without promoting its exact-SKU workflow ceiling."""
    if profile.effect_workflows is not None and workflow.value not in profile.effect_workflows:
        return False
    advanced_supported = profile.supports_advanced_effects or (
        profile.supports_custom_effects
        and model is not None
        and not get_profile(model).supports_advanced_effects
        and release_capability(model, CapabilityWorkflow.ADVANCED) is not None
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
    grammars: tuple[str, ...] | None = None,
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
    if (
        profile.effect_grammar is None
        or grammars is not None
        and profile.effect_grammar not in grammars
        or profile.effect_grammar not in capability.content_grammars
        or profile.command_grammar is None
        or (
            workflow is CapabilityWorkflow.PALETTE_DIY
            and profile.effect_grammar_has("exact_palette_diy_activation")
            and not profile.command_grammar_has("exact_palette_diy_activation")
        )
    ):
        raise ValueError(f"{model} has no supported {label} grammar and activation route")
    if not profile.effect_activation_operations & capability.activation_operations:
        raise ValueError(f"{model} has no supported {label} grammar and activation route")
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
    integration_version: str | None = None

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "api_version": self.api_version,
            "effect_schema_version": self.effect_schema_version,
            "compiler_version": self.compiler_version,
            "integration_version": self.integration_version,
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
    static_composition: bool = False

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "config_entry_id": self.config_entry_id,
            "light_entity_id": self.light_entity_id,
            "model": self.model,
            "support_quality": get_profile(self.model).support_quality.value,
            "confirmation_issue": get_profile(self.model).confirmation_issue,
            "display_name": self.display_name,
            "segment_count": self.segment_count,
            "physical_ic_count": self.physical_ic_count,
            "static_composition": self.static_composition,
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
        static_composition=profile.supports_segments and profile.supports_rgb,
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
