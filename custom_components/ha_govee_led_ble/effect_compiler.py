"""Compile canonical effects into model-specific device operations."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from types import MappingProxyType
from typing import Any, Literal, assert_never, cast

from .const import ModelProfile, get_profile, supported_effect_categories
from .effect_catalogue import (
    H617A_TYPE04_APPLY_CODE,
    H617A_WORKSHOP_APPLY_CODE,
    H617A_WORKSHOP_SCENE_TYPE,
    H6099_DIY_APPLY_CODE,
    H6199_PALETTE_DIY_APPLY_CODE,
    H6199_WORKSHOP_APPLY_CODE,
    H6199_WORKSHOP_APPLY_MUSIC_CODE,
    diy_destination_range,
    native_diy_template_contract,
    requires_diy_destination_consent,
    validate_effect_eligibility,
    validate_native_diy,
)
from .effect_commands import (
    DiyPaintGroup,
    build_h617a_diy_multi,
    build_h617a_diy_painted,
    build_h617a_diy_single,
    build_h6179_diy,
    build_h6199_palette_diy,
)
from .effect_content_ids import (
    MULTI_EFFECT_CONTENT_KIND,
    PAINTED_EFFECT_CONTENT_KIND,
    SINGLE_EFFECT_CONTENT_KIND,
)
from .effect_contracts import (
    EFFECT_COMPILER_VERSION,
    CapabilityWorkflow,
    ContentProjection,
    SelectorPolicy,
    release_capability,
    release_content_reference_model,
    release_selector_policy,
    require_effect_route,
    require_upload_carrier,
)
from .effect_domain import (
    BuiltinScene,
    EffectContent,
    H6179MixedDiyEffect,
    H6179SingleDiyEffect,
    LayeredEffect,
    LayeredScene,
    LibraryItem,
    MultiEffect,
    MusicProfile,
    NativeEffect,
    OpaqueContent,
    PaintedEffect,
    PaletteDiyEffect,
    PaletteScene,
    RetainedSceneEffect,
    SingleEffect,
    StaticRgbComposition,
    VideoProfile,
    effect_content_workflow,
)
from .generated_protocol_adapter import build_diy_activation, build_scene_activation
from .layered_scene import CatalogueRef
from .layered_scene_decoder import encode_layered_scene, encode_workshop_effect
from .light_commands import scale_segment_groups
from .music_commands import build_zoned_music_body, resolve_music_profile
from .music_protocol import music_code_for
from .music_semantics import music_parameters_depend_on_ic, music_variant
from .native_effect_codecs import native_effect_codec_for_profile
from .native_scenes import (
    apply_scene_speed,
    build_native_scene_packets,
    encode_authored_scene_body,
    native_scene_prefers_selector,
)
from .protocol_core import (
    H6199EffectUpload,
    SceneBody,
)
from .protocol_effect_bodies import build_dedicated_diy, build_inline_diy
from .scenes import MODEL_SCENES, SceneEntry, scene_for_profile, scene_selector_code
from .transport import fragment_a3

DIY_ACK_EVIDENCE = "native_diy_positive_ack_required"


def encode_native_body(content: NativeEffect, *, profile: ModelProfile | None = None) -> bytes:
    selected = native_effect_codec_for_profile(profile or get_profile(content.model))
    if selected is None:
        raise ValueError("native content has no selected codec")
    return selected.encode(content)


class CompatibilityState(StrEnum):
    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    UNKNOWN = "unknown"


class ActivationMode(StrEnum):
    CUSTOM = "custom"
    SCENE = "scene"


@dataclass(frozen=True, slots=True)
class CompatibilityResult:
    state: CompatibilityState
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CompiledEffect:
    item_id: str
    item_version: int
    model: str
    content_kind: str
    workflow: CapabilityWorkflow
    diy_code: int | None
    activation_mode: ActivationMode
    expected_effect: str | None
    upload_packets: tuple[bytes, ...]
    activation_packet: bytes | None
    artifact_sha256: str
    selector_kind: Literal["diy", "scene"] = "diy"
    evidence_codes: tuple[str, ...] = ()
    compiler_version: int = EFFECT_COMPILER_VERSION
    physical_ic_count: int | None = None
    upload_transport: str = "a3"
    scene_entry: SceneEntry | None = None
    scene_route: tuple[str | None, str | None, int | None] | None = None
    scene_speed_index: int | None = None
    upload_subtype: int | None = None
    body_template_id: int | None = None
    body_effect_code: int | None = None
    rgbic_scene_v0: bool | None = None
    native_effect_revision: int = 0
    authored_diy: SingleEffect | MultiEffect | None = None
    upload_prefix: int | None = None
    retained_scene: tuple[str, str] | None = None

    @property
    def packets(self) -> tuple[bytes, ...]:
        return self.upload_packets if self.activation_packet is None else (*self.upload_packets, self.activation_packet)

    @property
    def progress_total(self) -> int:
        return len(self.packets)


@dataclass(frozen=True, slots=True)
class CompiledMusicProfile:
    item_id: str
    item_version: int
    model: str
    mode: str
    sensitivity: int
    colour: tuple[int, int, int] | None
    calm: bool
    parameters: Mapping[str, int | bool | str]
    artifact_sha256: str
    packets: tuple[bytes, ...]
    physical_ic_count: int | None = None
    compiler_version: int = EFFECT_COMPILER_VERSION
    content_kind: str = "music_profile"
    diy_code: None = None
    palette: tuple[tuple[int, int, int], ...] | None = None
    music_body: bytes | None = None

    @property
    def progress_total(self) -> int:
        return 1 + int(len(self.packets) > 2)


@dataclass(frozen=True, slots=True)
class CompiledVideoProfile:
    item_id: str
    item_version: int
    model: str
    mode: str
    full_screen: bool | None
    saturation: int | None
    sound_effects: bool | None
    sound_effects_softness: int | None
    white_balance_position: int | None
    relative_brightness: tuple[int, ...] | None
    blank_screen: bool | None
    artifact_sha256: str
    white_balance_wire: tuple[int, ...] | None = None
    black_border: bool | None = None
    blank_screen_policy: tuple[int, int, int] | None = None
    whole_relative_brightness: int | None = None
    video_sensitivity: int | None = None
    hdmi_input: int | None = None
    hdmi_box_light: tuple[bool, int, bool, int] | None = None
    color_calibration: tuple[int, ...] | None = None
    relative_brightness_inline: bool = False
    compiler_version: int = EFFECT_COMPILER_VERSION
    content_kind: str = "video_profile"
    diy_code: None = None

    @property
    def progress_total(self) -> int:
        return 1 + sum(
            (
                self.white_balance_wire is not None,
                self.relative_brightness is not None and not self.relative_brightness_inline,
                self.whole_relative_brightness is not None,
                self.video_sensitivity is not None,
                self.hdmi_input is not None,
                self.hdmi_box_light is not None,
                self.color_calibration is not None,
                self.blank_screen is not None,
                self.black_border is not None,
            )
        )


@dataclass(frozen=True, slots=True)
class CompiledStaticRgb:
    item_id: str
    item_version: int
    model: str
    segments: tuple[tuple[int, int, int] | None, ...]
    groups: tuple[tuple[tuple[int, ...], tuple[int, int, int]], ...]
    artifact_sha256: str
    content_kind: str = "static_rgb"
    diy_code: None = None
    compiler_version: int = EFFECT_COMPILER_VERSION
    physical_ic_count: None = None

    @property
    def progress_total(self) -> int:
        return 1


CompiledApplication = CompiledEffect | CompiledMusicProfile | CompiledVideoProfile | CompiledStaticRgb


def validate_compiled_geometry(compiled: CompiledApplication, profile: ModelProfile) -> None:
    """Reject prepared work after incompatible permission, encoding or geometry changes."""
    if isinstance(compiled, CompiledStaticRgb):
        if not profile.supports_segments or not profile.supports_rgb or len(compiled.segments) != profile.segment_count:
            raise ValueError("Device no longer supports this static RGB segment layout")
        return
    profiled_layers = False
    if isinstance(compiled, CompiledEffect):
        if compiled.selector_kind not in profile.effect_activation_operations:
            raise ValueError("Device no longer supports the compiled activation route")
        if compiled.upload_packets and not profile.command_operation_supported("effect_upload"):
            raise ValueError("Device no longer supports compiled effect uploads")
        if compiled.content_kind == "native_effect":
            declared_profile = get_profile(compiled.model)
            codec = native_effect_codec_for_profile(profile)
            if codec is None or codec.codec_id != declared_profile.native_effect_codec:
                raise ValueError("Device native effect codec changed since compilation")
            declared_native_subtype = declared_profile.native_diy_upload_subtype
            if declared_native_subtype is not None and compiled.upload_subtype != declared_native_subtype:
                raise ValueError("Device native effect upload subtype changed since compilation")
        profiled_layers = (compiled.rgbic_scene_v0 is not None or profile.rgbic_scene_v0 is not None) and (
            compiled.content_kind in {"advanced", "workshop", "shared_scene", "scene_layered"}
            or (compiled.scene_entry is not None and compiled.scene_entry.scene_type == 2)
        )
        if (
            profiled_layers or compiled.rgbic_scene_v0 is not None
        ) and compiled.rgbic_scene_v0 != profile.rgbic_scene_v0:
            raise ValueError("RGBIC scene format changed since compilation; refresh and retry")
        if (
            compiled.upload_packets
            and profile.diy_requires_upload_ack
            and DIY_ACK_EVIDENCE not in compiled.evidence_codes
        ):
            raise ValueError("Upload acknowledgement contract changed since compilation; refresh and retry")
        if compiled.body_template_id is not None:
            contract = native_diy_template_contract(compiled.model, compiled.body_template_id)
            supported = (
                profile.supports_custom_effects
                and contract is not None
                and compiled.content_kind == "advanced"
                and compiled.activation_mode is ActivationMode.CUSTOM
                and compiled.selector_kind == ("scene" if contract.activation_selector is not None else "diy")
                and (contract.activation_selector is None or compiled.diy_code == contract.activation_selector)
                and compiled.upload_subtype == contract.upload_subtype
                and compiled.body_effect_code == contract.body_effect
            )
        else:
            supported = (
                profile.supports_scenes
                if compiled.content_kind in {"scene_builtin", "scene_palette", "scene_layered"}
                or compiled.scene_entry is not None
                else profile.supports_advanced_effects
                if compiled.content_kind in {"advanced", "workshop"}
                else profile.supports_custom_effects
            )
        if not supported:
            raise ValueError("Device profile no longer supports the compiled effect")
        if (
            compiled.content_kind == "native_effect"
            and profile.effect_grammar != get_profile(compiled.model).effect_grammar
        ):
            raise ValueError("Device native effect grammar changed since compilation")
        if compiled.native_effect_revision and compiled.native_effect_revision != profile.native_effect_revision:
            raise ValueError("Device native effect revision changed since compilation")
        if compiled.retained_scene is not None and (
            compiled.upload_subtype,
            compiled.diy_code,
        ) != _retained_scene_upload_route(compiled.model, *compiled.retained_scene, profile=profile):
            raise ValueError("Device retained scene carrier changed since compilation")
        if compiled.scene_entry is not None:
            entry = scene_for_profile(compiled.scene_entry, profile)
            selector = scene_selector_code(
                compiled.model, entry, profile=profile, authored=compiled.content_kind == "scene_palette"
            )
            packets_match = compiled.scene_route == (
                profile.command_grammar,
                profile.effect_grammar,
                profile.selector_only_scene_bits,
            )
            if compiled.content_kind == "scene_builtin":
                packets_match = (
                    tuple(
                        build_native_scene_packets(
                            compiled.model,
                            entry,
                            speed_index=compiled.scene_speed_index,
                            profile=profile,
                        )
                    )
                    == compiled.packets
                )
            if not packets_match or compiled.diy_code != selector:
                raise ValueError("Device scene route changed since compilation; refresh and retry")
        if compiled.content_kind in {SINGLE_EFFECT_CONTENT_KIND, MULTI_EFFECT_CONTENT_KIND}:
            if compiled.authored_diy is not None:
                validate_effect_eligibility(compiled.authored_diy, compiled.model, profile=profile)
            transport = profile.diy_upload_transport or ("a1_02" if profile.a1_diy_selector is not None else "a3")
            if (
                compiled.upload_transport != transport
                or (profile.a1_diy_selector is not None and compiled.diy_code != profile.a1_diy_selector)
                or compiled.upload_prefix != profile.a1_diy_prefix
            ):
                raise ValueError("Device upload transport or selector changed since compilation")
        if compiled.content_kind in {"h6179_single_diy", "h6179_mixed_diy"}:
            if compiled.upload_transport != profile.diy_upload_transport:
                raise ValueError("Device DIY transport changed since compilation")
        if profile.effect_workflows is not None and compiled.workflow.value not in profile.effect_workflows:
            raise ValueError("Device profile no longer supports the compiled workflow")
    if isinstance(compiled, CompiledVideoProfile):
        if compiled.mode not in profile.video_modes:
            raise ValueError("Device profile no longer supports the compiled video mode")
        if compiled.relative_brightness is not None and (
            compiled.relative_brightness_inline != profile.video_embeds_relative_brightness
        ):
            raise ValueError("Video brightness transport changed since compilation; refresh and retry")
        return
    dependent = compiled.physical_ic_count is not None or profiled_layers
    if isinstance(compiled, CompiledMusicProfile):
        if compiled.mode not in profile.music_modes:
            raise ValueError("Device profile no longer supports the compiled music mode")
        variant = music_variant(
            profile,
            music_code_for(compiled.model, compiled.mode, profile=profile),
        )
        if compiled.calm and (variant is None or not variant.supports_style):
            raise ValueError("Device profile no longer supports the compiled music style")
        if compiled.colour is not None and (
            not profile.supports_music_color or variant is None or not variant.supports_fixed_colour
        ):
            raise ValueError("Device profile no longer supports the compiled music colour")
        dependent = music_parameters_depend_on_ic(variant, compiled.parameters)
    if dependent and compiled.physical_ic_count != profile.physical_ic_count:
        raise ValueError("Physical IC count changed since compilation; refresh and retry")


def require_native_scenes(model: str, profile: ModelProfile) -> None:
    """Authorize native scenes against both the effective profile and model contract."""
    if not profile.supports_scenes:
        raise ValueError(f"{model} native scenes are not supported")
    require_effect_route(model, CapabilityWorkflow.NATIVE_SCENES, profile=profile)


def compatibility(item: LibraryItem, model: str, *, profile: ModelProfile | None = None) -> CompatibilityResult:
    from .effect_targets import resolve_target_item

    try:
        item = resolve_target_item(item, model, profile)
    except ValueError as error:
        return CompatibilityResult(CompatibilityState.INCOMPATIBLE, (str(error),))
    return _target_compatibility(item, model, profile=profile)


def _target_compatibility(item: LibraryItem, model: str, *, profile: ModelProfile | None = None) -> CompatibilityResult:
    profile = get_profile(model) if profile is None else profile
    if isinstance(item.content, StaticRgbComposition):
        supported = (
            profile.supports_segments and profile.supports_rgb and len(item.content.segments) == profile.segment_count
        )
        return CompatibilityResult(
            CompatibilityState.COMPATIBLE if supported else CompatibilityState.INCOMPATIBLE,
            () if supported else ("Static RGB requires matching logical segment geometry and RGB controls",),
        )
    if profile.command_operations is not None and not supported_effect_categories(model, profile=profile):
        return CompatibilityResult(CompatibilityState.INCOMPATIBLE, ("Device profile supports no effects",))
    content = item.content
    if isinstance(content, OpaqueContent):
        return CompatibilityResult(
            CompatibilityState.UNKNOWN,
            (f"content kind {content.kind!r} is not understood",),
        )
    if isinstance(content, MusicProfile):
        if content.model != model:
            return CompatibilityResult(
                CompatibilityState.INCOMPATIBLE,
                (f"music profile targets {content.model}, not {model}",),
            )
        try:
            from .music_commands import validate_music_profile_request

            validate_music_profile_request(
                model,
                content.mode,
                content.sensitivity,
                content.colour,
                content.calm,
                content.parameters,
                profile=profile,
                palette=content.palette,
            )
            if content.zones is not None:
                build_zoned_music_body(profile, content.mode, content.zones)
        except ValueError as error:
            return CompatibilityResult(CompatibilityState.INCOMPATIBLE, (str(error),))
        return CompatibilityResult(CompatibilityState.COMPATIBLE)
    if isinstance(content, VideoProfile):
        try:
            if content.saturation is not None:
                profile.validate_video_saturation(content.saturation)
        except ValueError as error:
            return CompatibilityResult(CompatibilityState.INCOMPATIBLE, (str(error),))
        if content.model != model or not profile.supports_video_mode or profile.video_grammar is None:
            return CompatibilityResult(
                CompatibilityState.INCOMPATIBLE,
                (f"{model} video-profile application is not supported",),
            )
        if content.mode not in profile.video_modes:
            return CompatibilityResult(
                CompatibilityState.INCOMPATIBLE,
                (f"{model} does not support video mode {content.mode}",),
            )
        return CompatibilityResult(CompatibilityState.COMPATIBLE)
    if isinstance(content, H6179SingleDiyEffect | H6179MixedDiyEffect):
        capability = release_capability(model, _effect_workflow(content)) if content.model == model else None
        if capability is None or capability.content_projection is not ContentProjection.TYPED_DIY:
            return CompatibilityResult(
                CompatibilityState.INCOMPATIBLE,
                (f"{model} cannot apply typed DIY content",),
            )
        workflow = _effect_workflow(content)
        try:
            require_effect_route(model, workflow, profile=profile)
        except ValueError as error:
            return CompatibilityResult(CompatibilityState.INCOMPATIBLE, (str(error),))
        return CompatibilityResult(CompatibilityState.COMPATIBLE)
    if isinstance(content, RetainedSceneEffect):
        if content.model != model:
            return CompatibilityResult(
                CompatibilityState.INCOMPATIBLE,
                (f"Workshop effect targets {content.model}, not {model}",),
            )
        try:
            _retained_scene_upload_route(model, content.application, content.carrier, profile=profile)
        except ValueError as error:
            return CompatibilityResult(CompatibilityState.INCOMPATIBLE, (str(error),))
        return CompatibilityResult(CompatibilityState.COMPATIBLE)
    if isinstance(content, NativeEffect):
        try:
            _validate_native_effect(item, model, profile)
        except ValueError as error:
            return CompatibilityResult(CompatibilityState.INCOMPATIBLE, (str(error),))
        return CompatibilityResult(CompatibilityState.COMPATIBLE)
    if isinstance(content, BuiltinScene):
        if not profile.supports_scenes:
            return CompatibilityResult(
                CompatibilityState.INCOMPATIBLE,
                (f"{model} native scenes are not supported",),
            )
        try:
            require_native_scenes(model, profile)
            _scene_key, entry = _resolve_scene(model, content.template)
            entry = scene_for_profile(entry, profile)
            from .native_scenes import native_scene_upload_route

            native_scene_upload_route(entry, profile)
            scene_selector_code(model, entry, profile=profile)
            if content.speed_index is not None:
                if (
                    entry.selector_only
                    or release_selector_policy(model, CapabilityWorkflow.NATIVE_SCENES)
                    is SelectorPolicy.CATALOGUE_SELECTOR_ONLY
                    or profile.selector_only_scene_bits is not None
                ):
                    raise ValueError(f"{model} selector-only native scenes do not accept speed_index")
                if entry.speed is None:
                    raise ValueError("This scene does not expose a documented Speed control")
                if not 0 <= content.speed_index < entry.speed.option_count:
                    raise ValueError("Scene speed index is outside its documented options")
        except ValueError as error:
            return CompatibilityResult(CompatibilityState.INCOMPATIBLE, (str(error),))
        return CompatibilityResult(CompatibilityState.COMPATIBLE)
    if isinstance(content, PaletteDiyEffect):
        if content.model != model:
            return CompatibilityResult(
                CompatibilityState.INCOMPATIBLE,
                (f"palette DIY targets {content.model}, not {model}",),
            )
    if isinstance(content, PaintedEffect | SingleEffect | MultiEffect | PaletteDiyEffect):
        try:
            if requires_diy_destination_consent(model) and isinstance(
                content, PaintedEffect | SingleEffect | MultiEffect | PaletteDiyEffect
            ):
                require_effect_route(
                    model,
                    CapabilityWorkflow.PAINTED
                    if isinstance(content, PaintedEffect)
                    else CapabilityWorkflow.SINGLE
                    if isinstance(content, SingleEffect)
                    else CapabilityWorkflow.MULTI
                    if isinstance(content, MultiEffect)
                    else CapabilityWorkflow.PALETTE_DIY,
                    profile=profile,
                )
            else:
                resolve_diy_code(item, model=model, profile=profile)
            validate_effect_eligibility(content, model, profile=profile)
        except ValueError as error:
            return CompatibilityResult(CompatibilityState.INCOMPATIBLE, (str(error),))
        return CompatibilityResult(CompatibilityState.COMPATIBLE)
    if isinstance(content, PaletteScene | LayeredScene):
        if not profile.supports_scenes:
            return CompatibilityResult(
                CompatibilityState.INCOMPATIBLE,
                (f"{model} authored scenes are not supported",),
            )
        try:
            require_effect_route(
                model,
                CapabilityWorkflow.EDITED_PALETTE_SCENES
                if isinstance(content, PaletteScene)
                else CapabilityWorkflow.LAYERED_SCENES,
                profile=profile,
            )
            _resolve_scene(
                model,
                content.template,
                expected_scene_type=1
                if isinstance(content, PaletteScene)
                else (
                    codec.layered_scene_type
                    if (codec := native_effect_codec_for_profile(profile)) is not None
                    and codec.layered_scene_type is not None
                    else 2
                ),
            )
            if isinstance(content, PaletteScene) and content.speed_index is not None:
                raise ValueError("type-1 palette scenes do not expose a documented Speed control")
        except ValueError as error:
            return CompatibilityResult(CompatibilityState.INCOMPATIBLE, (str(error),))
        return CompatibilityResult(CompatibilityState.COMPATIBLE)
    if isinstance(content, LayeredEffect):
        try:
            if get_profile(model).supports_advanced_effects and not profile.supports_advanced_effects:
                raise ValueError(f"{model} effective profile does not support Advanced effects")
            require_effect_route(model, CapabilityWorkflow.ADVANCED, profile=profile)
            if content.native_diy is not None:
                validate_native_diy(content, model, profile)
            elif profile.advanced_diy_selector is None:
                _advanced_carrier(model)
        except ValueError as error:
            return CompatibilityResult(CompatibilityState.INCOMPATIBLE, (str(error),))
        return CompatibilityResult(CompatibilityState.COMPATIBLE)
    assert_never(content)


def _effect_workflow(content: EffectContent) -> CapabilityWorkflow:
    workflow = effect_content_workflow(content)
    if workflow is None:
        raise ValueError("Opaque content has no applicable workflow")
    return CapabilityWorkflow(workflow)


def _validate_native_effect(item: LibraryItem, model: str, profile: ModelProfile) -> None:
    content = item.content
    if not isinstance(content, NativeEffect):
        raise ValueError("native compiler requires native content")
    native_codec = native_effect_codec_for_profile(profile)
    if native_codec is None or content.model != model or native_codec.canonical_target != model:
        raise ValueError("Native grammar and activation route do not match the effective profile")
    route = native_codec.route_for_content(content, scene=content.template is not None)
    if not native_codec.qualifies_upload_subtype(profile, route.subtype):
        raise ValueError("Native grammar and activation route do not match the effective profile")
    uploadless_scene = content.template is not None and getattr(native_codec, "selector_only_native_scene", False)
    if not profile.command_operation_supported("effect_upload") and not uploadless_scene:
        raise ValueError(f"{model} effective profile does not support effect uploads")
    require_effect_route(model, _effect_workflow(content), (native_codec.effect_grammar,), profile=profile)
    validate_effect_eligibility(content, model, profile=profile)
    if content.template is not None:
        _key, entry = _resolve_scene(model, content.template, expected_scene_type=5)
        if entry.diy_effect_codes != (content.family,):
            raise ValueError("native scene family does not match its catalogue")
        if content.speed_index is not None and (entry.speed is None or content.speed_index >= entry.speed.option_count):
            raise ValueError("native scene speed index is not present in its catalogue")
    resolve_diy_code(item, model=model, profile=profile)


def _prepare_native_effect(item: LibraryItem, model: str, profile: ModelProfile) -> bytes:
    _validate_native_effect(item, model, profile)
    content = item.content
    assert isinstance(content, NativeEffect)
    codec = native_effect_codec_for_profile(profile)
    if codec is None:
        raise ValueError(f"{model} has no native effect codec")
    return encode_native_body(content)


def compile_effect(
    item: LibraryItem,
    model: str,
    *,
    diy_code: int | None = None,
    profile: ModelProfile | None = None,
) -> CompiledEffect:
    from .effect_targets import resolve_target_item

    item = resolve_target_item(item, model, profile)
    if isinstance(item.content, H6179SingleDiyEffect | H6179MixedDiyEffect):
        if diy_code is None:
            raise ValueError("Typed DIY application requires an explicit DIY destination")
        return compile_h6179(item, diy_code, model, profile=profile)
    if isinstance(item.content, NativeEffect):
        return compile_native_effect(item, model, diy_code=diy_code, profile=profile)
    if isinstance(item.content, PaintedEffect | SingleEffect | MultiEffect):
        if _has_fixed_diy_slot(model, profile=profile):
            diy_code = resolve_diy_code(item, diy_code, model=model, profile=profile)
        if diy_code is None:
            raise ValueError("H617A custom-effect compilation requires a DIY code")
        return compile_h617a(item, diy_code, model=model, profile=profile)
    if isinstance(item.content, PaletteDiyEffect):
        return compile_h6199(
            item,
            diy_code,
            model=model,
            profile=profile,
        )
    if isinstance(item.content, BuiltinScene | PaletteScene | LayeredScene | LayeredEffect):
        resolved_diy_code = diy_code
        if isinstance(item.content, LayeredEffect) and item.content.native_diy is not None:
            resolved_diy_code = resolve_diy_code(item, diy_code, model=model, profile=profile)
        return compile_scene_effect(item, model, diy_code=resolved_diy_code, profile=profile)
    if isinstance(item.content, RetainedSceneEffect):
        resolve_diy_code(item, diy_code, model=model, profile=profile)
        return _compile_retained_scene(item, model, profile=profile)
    raise ValueError("unsupported effect content")


def _has_fixed_diy_slot(model: str, *, profile: ModelProfile | None = None) -> bool:
    from .effect_catalogue import MODEL_EFFECT_CATALOGUES

    profile = get_profile(model) if profile is None else profile
    catalogue = MODEL_EFFECT_CATALOGUES.get(model)
    return (
        profile.effect_grammar_has("fixed_diy_slot")
        or profile.diy_upload_transport == "single"
        or profile.a1_diy_selector is not None
        or catalogue is not None
        and catalogue.temporary_diy_selector is not None
    )


def _retained_scene_upload_route(
    model: str, application: str, carrier: str, *, profile: ModelProfile | None = None
) -> tuple[int, int]:
    """Keep retained body format independent of its authorised application route."""
    profile = get_profile(model) if profile is None else profile
    if application == "shared_scene":
        workflow = CapabilityWorkflow.NATIVE_SCENES if carrier == "rgb" else CapabilityWorkflow.LAYERED_SCENES
        require_effect_route(model, workflow, profile=profile)
        require_upload_carrier(model, workflow, carrier)
        for name, subtype, selector in profile.shared_scene_carriers:
            if name == carrier:
                return subtype, selector
        raise ValueError(f"{model} has no {carrier} shared-scene carrier")
    if application != "workshop":
        raise ValueError("Unknown retained scene application")
    require_effect_route(model, CapabilityWorkflow.WORKSHOP, profile=profile)
    require_upload_carrier(model, CapabilityWorkflow.WORKSHOP, carrier)
    if profile.workshop_carriers:
        for name, subtype, selector in profile.workshop_carriers:
            if name == carrier:
                return subtype, selector
        raise ValueError(f"{model} has no {carrier} Workshop carrier")
    if carrier != "rgbic_v1":
        raise ValueError(f"{model} has no {carrier} Workshop carrier")
    subtype = (
        int(H6199EffectUpload.BodyKind.scene)
        if profile.effect_grammar_has("display_scene_body")
        else int(SceneBody.SceneType.scene_v2)
    )
    if profile.workshop_scene_selector is not None:
        return subtype, profile.workshop_scene_selector
    return subtype, (
        H617A_WORKSHOP_APPLY_CODE
        if profile.effect_grammar_has("h617a_workshop_selector")
        else H6199_WORKSHOP_APPLY_CODE
    )


def resolve_diy_code(
    item: LibraryItem,
    requested: int | None = None,
    *,
    model: str | None = None,
    profile: ModelProfile | None = None,
) -> int | None:
    """Resolve a custom selector; scene and profile applications return None."""
    if model is not None:
        from .effect_targets import resolve_target_item

        item = resolve_target_item(item, model, profile)
    content = item.content
    if isinstance(content, StaticRgbComposition):
        if requested is not None:
            raise ValueError("Static RGB compositions do not use a DIY slot")
        return None
    if isinstance(content, NativeEffect):
        if content.template is not None:
            if requested is not None:
                raise ValueError("native scenes use their catalogue selector, not a DIY slot")
            return None
        model = content.model if model is None else model
        if model != content.model:
            raise ValueError("native content targets another model")
        effective_profile = get_profile(model) if profile is None else profile
        codec = native_effect_codec_for_profile(effective_profile)
        if codec is None:
            raise ValueError("native DIY has no selected format codec")
        route = codec.route_for_content(content)
        if route.fixed_selector is not None:
            if requested is not None and requested != route.fixed_selector:
                raise ValueError("Native combination requires its temporary scene selector")
            return route.fixed_selector
        from .effect_catalogue import MODEL_EFFECT_CATALOGUES

        catalogue = MODEL_EFFECT_CATALOGUES.get(model)
        selector = effective_profile.native_diy_selector
        if selector is None:
            selector = None if catalogue is None else catalogue.temporary_diy_selector
        if selector is None or requested is not None and requested != selector:
            raise ValueError("native DIY requires its exact temporary selector")
        return selector
    if isinstance(content, LayeredEffect) and content.native_diy is not None:
        if model is not None:
            from .effect_catalogue import MODEL_EFFECT_CATALOGUES

            require_effect_route(model, CapabilityWorkflow.ADVANCED, profile=profile)
            catalogue = MODEL_EFFECT_CATALOGUES.get(model)
            if catalogue is None or not any(
                isinstance(template.content, LayeredEffect) and template.content.native_diy == content.native_diy
                for template in catalogue.templates
            ):
                raise ValueError("native DIY template is not in the exact-model catalogue")
        if model is not None and requires_diy_destination_consent(model):
            if requested is None:
                raise ValueError(f"{model} native DIY application requires an explicit DIY destination")
            if not isinstance(requested, int) or isinstance(requested, bool) or not 0 <= requested <= 0xFFFF:
                raise ValueError("DIY code must be an integer from 0 to 65535")
            return requested
        if requested is not None and requested != content.native_diy:
            raise ValueError("native DIY requires its own template selector")
        return content.native_diy
    if isinstance(content, MusicProfile | VideoProfile):
        if requested is not None:
            raise ValueError("profiles do not use a DIY code")
        return None
    if isinstance(content, H6179SingleDiyEffect | H6179MixedDiyEffect):
        model = content.model if model is None else model
        if content.model != model:
            raise ValueError(f"effect targets {content.model}, not {model}")
        workflow = _effect_workflow(content)
        require_effect_route(model, workflow, profile=profile)
        capability = release_capability(model, workflow)
        if capability is None or capability.content_projection is not ContentProjection.TYPED_DIY:
            raise ValueError(f"{model} has no supported typed DIY route")
        if requested is None:
            raise ValueError("Typed DIY application requires an explicit DIY destination")
        if not isinstance(requested, int) or isinstance(requested, bool) or not 0 <= requested <= 0xFFFF:
            raise ValueError("DIY code must be an integer from 0 to 65535")
        return requested
    if isinstance(content, RetainedSceneEffect):
        model = content.model if model is None else model
        if content.model != model:
            raise ValueError(f"effect targets {content.model}, not {model}")
        _, expected = _retained_scene_upload_route(model, content.application, content.carrier, profile=profile)
        if requested is not None and requested != expected:
            raise ValueError(f"{model} has no evidenced activation packet for the requested slot; expected {expected}")
        return expected
    if isinstance(content, PaletteDiyEffect):
        model = content.model if model is None else model
        if content.model != model:
            raise ValueError(f"effect targets {content.model}, not {model}")
        require_effect_route(model, CapabilityWorkflow.PALETTE_DIY, profile=profile)
        if release_selector_policy(model, CapabilityWorkflow.PALETTE_DIY) is SelectorPolicy.APPROVED_DISPOSABLE:
            if requested is None:
                return None
            minimum, maximum = diy_destination_range(model)
            if not isinstance(requested, int) or isinstance(requested, bool) or not minimum <= requested <= maximum:
                raise ValueError(f"{model} approved DIY code must be an integer from {minimum} to {maximum}")
            return requested
        if requested is not None and requested != H6199_PALETTE_DIY_APPLY_CODE:
            raise ValueError(
                f"{model} has no evidenced activation packet for the requested slot; "
                f"expected {H6199_PALETTE_DIY_APPLY_CODE}"
            )
        return H6199_PALETTE_DIY_APPLY_CODE
    if isinstance(content, PaintedEffect | SingleEffect | MultiEffect):
        workflow = _effect_workflow(content)
        content_kind = (
            PAINTED_EFFECT_CONTENT_KIND
            if isinstance(content, PaintedEffect)
            else SINGLE_EFFECT_CONTENT_KIND
            if isinstance(content, SingleEffect)
            else MULTI_EFFECT_CONTENT_KIND
        )
        route_model = model or release_content_reference_model(content_kind)
        if route_model is None:
            raise ValueError("generic DIY content has no declared authoring route")
        profile = get_profile(route_model) if profile is None else profile
        require_effect_route(
            route_model,
            workflow,
            profile=profile,
        )
        native_codec = native_effect_codec_for_profile(profile)
        if native_codec is not None and native_codec.paint_selector is not None:
            if not isinstance(content, PaintedEffect):
                raise ValueError("native DIY requires its independently bounded zone definition")
            selector = native_codec.paint_selector
            if requested is not None and requested != selector:
                raise ValueError("native paint requires its exact activation selector")
            return selector
        a1_selector = None if isinstance(content, PaintedEffect) else profile.a1_diy_selector
        explicit_destination = (
            model is not None and release_selector_policy(model, workflow) is SelectorPolicy.APPROVED_DISPOSABLE
        )
        if model is not None:
            from .effect_catalogue import MODEL_EFFECT_CATALOGUES

            catalogue = MODEL_EFFECT_CATALOGUES.get(model)
            fixed_selector = None if catalogue is None else catalogue.temporary_diy_selector
            if fixed_selector is not None:
                if requested is not None and requested != fixed_selector:
                    raise ValueError(f"{model} custom effects require temporary selector {fixed_selector}")
                return fixed_selector
        if explicit_destination and requested is None:
            raise ValueError(f"{model} custom-effect application requires an explicit DIY destination")
        code = (
            (
                H6099_DIY_APPLY_CODE
                if profile.effect_grammar_has("default_diy_selector_254")
                else a1_selector
                if a1_selector is not None
                else 800
                if isinstance(content, PaintedEffect)
                else H617A_TYPE04_APPLY_CODE
            )
            if requested is None
            else requested
        )
        if not isinstance(code, int) or isinstance(code, bool) or not 0 <= code <= 0xFFFF:
            raise ValueError("DIY code must be an integer from 0 to 65535")
        if a1_selector is not None and code != a1_selector:
            raise ValueError(f"{model} custom effects use the A1 selector 0x{a1_selector:02x}")
        return code
    return None


def _compile_retained_scene(
    item: LibraryItem,
    model: str,
    *,
    profile: ModelProfile | None = None,
) -> CompiledEffect:
    profile = get_profile(model) if profile is None else profile
    content = item.content
    if isinstance(content, RetainedSceneEffect):
        body_kind, diy_code = _retained_scene_upload_route(model, content.application, content.carrier, profile=profile)
        if content.model != model:
            raise ValueError(f"Workshop effect targets {content.model}, not {model}")
        payload = encode_workshop_effect(
            model,
            content.effect,
            trailing_padding=content.trailing_padding,
            profile=profile,
            carrier=content.carrier,
            raw_param=content.raw_param,
        )
        upload = tuple(fragment_a3(body_kind, payload))
        content_kind = content.application
    else:
        raise ValueError("content is not an upload-only effect")

    activation = build_scene_activation(
        model,
        diy_code,
        H6199_WORKSHOP_APPLY_MUSIC_CODE,
        scene_type=H617A_WORKSHOP_SCENE_TYPE
        if content.application == "workshop"
        and profile.workshop_scene_selector is None
        and profile.command_grammar_has("workshop_scene_type")
        else 0,
        profile=profile,
    )
    packets = (*upload, activation)
    return CompiledEffect(
        item_id=str(item.id),
        item_version=item.version,
        model=model,
        content_kind=content_kind,
        workflow=_effect_workflow(content),
        diy_code=diy_code,
        activation_mode=ActivationMode.CUSTOM,
        selector_kind="scene",
        expected_effect=None,
        upload_packets=upload,
        activation_packet=activation,
        artifact_sha256=sha256(b"".join(packets)).hexdigest(),
        evidence_codes=(
            "effect_content_readback_unavailable",
            *((DIY_ACK_EVIDENCE,) if profile.diy_requires_upload_ack else ()),
        ),
        upload_subtype=body_kind,
        retained_scene=(content.application, content.carrier),
        rgbic_scene_v0=profile.rgbic_scene_v0,
        physical_ic_count=profile.physical_ic_count if profile.rgbic_scene_v0 is not None else None,
    )


def compile_scene_effect(
    item: LibraryItem,
    model: str,
    *,
    diy_code: int | None = None,
    profile: ModelProfile | None = None,
) -> CompiledEffect:
    result = compatibility(item, model, profile=profile)
    if result.state is not CompatibilityState.COMPATIBLE:
        raise ValueError("; ".join(result.reasons))

    content = item.content
    profile = get_profile(model) if profile is None else profile
    if isinstance(content, LayeredEffect) and (
        content.native_diy is not None or profile.advanced_diy_selector is not None
    ):
        contract = native_diy_template_contract(model, content.native_diy)
        selector = (
            contract.activation_selector
            if contract is not None and contract.activation_selector is not None
            else diy_code
            if contract is not None and requires_diy_destination_consent(model)
            else content.native_diy
            if content.native_diy is not None
            else profile.advanced_diy_selector
        )
        assert selector is not None
        subtype = contract.upload_subtype if contract is not None else int(SceneBody.SceneType.scene_v2)
        upload = tuple(fragment_a3(subtype, encode_workshop_effect(model, content, profile=profile)))
        activation = (
            build_diy_activation(selector, model, profile=profile)
            if contract is not None and requires_diy_destination_consent(model)
            else build_scene_activation(model, selector, 0, profile=profile)
        )
        return CompiledEffect(
            item_id=str(item.id),
            item_version=item.version,
            model=model,
            content_kind="advanced",
            workflow=_effect_workflow(content),
            diy_code=selector,
            activation_mode=ActivationMode.CUSTOM,
            selector_kind="diy" if contract is not None and requires_diy_destination_consent(model) else "scene",
            expected_effect=None,
            upload_packets=upload,
            activation_packet=activation,
            artifact_sha256=sha256(b"".join((*upload, activation))).hexdigest(),
            evidence_codes=(
                *(
                    (DIY_ACK_EVIDENCE,)
                    if contract is not None or profile.diy_requires_upload_ack or profile.supports_color_mode_readback
                    else ()
                ),
                "effect_content_readback_unavailable",
                "native_diy_rendering_unqualified",
            ),
            physical_ic_count=profile.physical_ic_count
            if profile.rgbic_scene_v0 is not None
            or (content.native_diy is not None and validate_native_diy(content, model, profile))
            else None,
            upload_subtype=subtype,
            body_template_id=content.native_diy if contract is not None else None,
            body_effect_code=contract.body_effect if contract is not None else None,
            rgbic_scene_v0=profile.rgbic_scene_v0,
        )
    evidence_codes: list[str] = []
    if isinstance(content, BuiltinScene):
        content_kind = "scene_builtin"
        scene_key, entry = _resolve_scene(model, content.template)
        packets = tuple(
            build_native_scene_packets(
                model,
                entry,
                speed_index=content.speed_index,
                profile=profile,
            )
        )
        upload = packets[:-1]
        activation = packets[-1]
        if upload:
            evidence_codes.append("scene_payload_readback_unavailable")
    elif isinstance(content, PaletteScene | LayeredScene):
        content_kind = "scene_palette" if isinstance(content, PaletteScene) else "scene_layered"
        scene_key, entry = _resolve_scene(
            model,
            content.template,
            expected_scene_type=1
            if isinstance(content, PaletteScene)
            else (
                codec.layered_scene_type
                if (codec := native_effect_codec_for_profile(profile)) is not None
                and codec.layered_scene_type is not None
                else 2
            ),
        )
        payload, speed = encode_authored_scene_body(content, entry)
        packets = tuple(
            build_native_scene_packets(model, entry, speed_index=speed, canonical_body=payload, profile=profile)
        )
        upload = packets[:-1]
        activation = packets[-1]
        if isinstance(content, PaletteScene):
            activation = build_scene_activation(
                model,
                scene_selector_code(model, entry, profile=profile, authored=True),
                entry.music_code,
                profile=profile,
            )
            if profile.authored_palette_scene_selector is not None:
                scene_key = None
        evidence_codes.append("scene_payload_readback_unavailable")
        if isinstance(content, LayeredScene):
            evidence_codes.append("layered_field_semantics_uncalibrated")
    elif isinstance(content, LayeredEffect):
        content_kind = "advanced"
        scene_key, entry = _advanced_carrier(model)
        scene_type = 2
        payload = encode_layered_scene(
            LayeredScene(
                template=CatalogueRef(model, entry.scene_id, entry.effect_id),
                effect=content,
            ),
            profile=profile,
        )
        evidence_codes.extend(
            (
                "scene_payload_readback_unavailable",
                "layered_field_semantics_uncalibrated",
                "layered_activation_carrier_uncalibrated",
            )
        )
        upload = tuple(fragment_a3(scene_type, payload))
        activation = build_scene_activation(
            model, scene_selector_code(model, entry, profile=profile), entry.music_code, profile=profile
        )
    else:
        raise ValueError("unsupported scene effect content")

    if upload and profile.diy_requires_upload_ack:
        evidence_codes.append(DIY_ACK_EVIDENCE)
    digest = sha256(b"".join((*upload, activation))).hexdigest()
    return CompiledEffect(
        item_id=str(item.id),
        item_version=item.version,
        model=model,
        content_kind=content_kind,
        workflow=_effect_workflow(content),
        diy_code=scene_selector_code(model, entry, profile=profile, authored=isinstance(content, PaletteScene)),
        activation_mode=ActivationMode.SCENE,
        selector_kind="scene",
        expected_effect=scene_key,
        upload_packets=upload,
        activation_packet=activation,
        artifact_sha256=digest,
        evidence_codes=tuple(evidence_codes),
        scene_entry=entry,
        scene_route=(profile.command_grammar, profile.effect_grammar, profile.selector_only_scene_bits),
        scene_speed_index=content.speed_index if isinstance(content, BuiltinScene) else None,
        rgbic_scene_v0=profile.rgbic_scene_v0
        if content_kind in {"advanced", "scene_layered"} or entry.scene_type == 2
        else None,
        physical_ic_count=profile.physical_ic_count
        if profile.rgbic_scene_v0 is not None
        and (content_kind in {"advanced", "scene_layered"} or entry.scene_type == 2)
        else None,
        upload_subtype=_builtin_upload_route(entry, profile)[1] if upload else None,
        upload_transport=_builtin_upload_route(entry, profile)[0] if upload else "a3",
    )


def _builtin_upload_route(entry: SceneEntry, profile: ModelProfile) -> tuple[str, int]:
    from .native_scenes import native_scene_upload_route

    route = native_scene_upload_route(entry, profile)
    if route is None:
        raise ValueError("scene packets have no admitted upload route")
    return route


def compile_native_effect(
    item: LibraryItem,
    model: str,
    *,
    diy_code: int | None = None,
    profile: ModelProfile | None = None,
) -> CompiledEffect:
    from .transport import fragment_a4

    profile = get_profile(model) if profile is None else profile
    content = item.content
    if not isinstance(content, NativeEffect):
        raise ValueError("native compiler requires native content")
    body = _prepare_native_effect(item, model, profile)
    codec = native_effect_codec_for_profile(profile)
    if codec is None:
        raise ValueError(f"{model} has no native effect codec")
    entry = None
    scene_key = None
    if content.template is not None:
        if diy_code is not None:
            raise ValueError("native scenes do not accept a temporary DIY selector")
        scene_key, entry = _resolve_scene(model, content.template, expected_scene_type=5)
        if content.speed_index is not None:
            assert entry.speed is not None
            body = apply_scene_speed(body, entry.speed, content.speed_index, target=model)
        if native_scene_prefers_selector(entry, body, profile):
            body = b""
        selector = scene_selector_code(model, entry, profile=profile)
        activation = build_scene_activation(model, selector, entry.music_code, profile=profile)
    else:
        custom_selector = resolve_diy_code(item, diy_code, model=model, profile=profile)
        assert custom_selector is not None
        selector = custom_selector
        upload_route = codec.route_for_content(content)
        activation = (
            build_scene_activation(model, selector, profile=profile)
            if upload_route.scene_activation
            else build_diy_activation(selector, model, profile=profile)
        )
    upload_route = codec.route_for_content(content, scene=entry is not None)
    if body:
        body = codec.prepare_upload(body, content, scene=entry is not None)
    route = upload_route.carrier.value
    subtype = upload_route.subtype
    if profile.native_diy_upload_subtype is not None and entry is None:
        subtype = profile.native_diy_upload_subtype
    upload = tuple((fragment_a4 if route == "a4" else fragment_a3)(subtype, body)) if body else ()
    if upload and not profile.command_operation_supported("effect_upload"):
        raise ValueError(f"{model} effective profile does not support effect uploads")
    return CompiledEffect(
        item_id=str(item.id),
        item_version=item.version,
        model=model,
        content_kind="native_effect",
        workflow=_effect_workflow(content),
        diy_code=selector,
        activation_mode=ActivationMode.SCENE if entry is not None else ActivationMode.CUSTOM,
        selector_kind="scene" if entry is not None or upload_route.scene_activation else "diy",
        expected_effect=scene_key,
        upload_packets=upload,
        activation_packet=activation,
        artifact_sha256=sha256(b"".join((*upload, activation))).hexdigest(),
        evidence_codes=(
            (DIY_ACK_EVIDENCE, "effect_content_readback_unavailable")
            if upload and profile.diy_requires_upload_ack
            else ("effect_content_readback_unavailable",)
        ),
        upload_transport=route,
        upload_subtype=subtype if upload else None,
        body_effect_code=content.family if codec.reports_body_effect_code else None,
        physical_ic_count=profile.physical_ic_count if content.family == codec.physical_geometry_family else None,
        scene_entry=entry,
        native_effect_revision=profile.native_effect_revision if "revision" in codec.serialised_fields else 0,
        scene_route=(profile.command_grammar, profile.effect_grammar, profile.selector_only_scene_bits)
        if entry is not None
        else None,
    )


def compile_h617a(
    item: LibraryItem,
    diy_code: int,
    *,
    model: str | None = None,
    profile: ModelProfile | None = None,
) -> CompiledEffect:
    from .effect_targets import resolve_target_item

    if model is None:
        content = item.content
        kind = (
            PAINTED_EFFECT_CONTENT_KIND
            if isinstance(content, PaintedEffect)
            else SINGLE_EFFECT_CONTENT_KIND
            if isinstance(content, SingleEffect)
            else MULTI_EFFECT_CONTENT_KIND
        )
        model = release_content_reference_model(kind)
        if model is None:
            raise ValueError("generic DIY content has no declared authoring route")
    item = resolve_target_item(item, model, profile)
    profile = get_profile(model) if profile is None else profile
    result = compatibility(item, model, profile=profile)
    if result.state is not CompatibilityState.COMPATIBLE:
        raise ValueError("; ".join(result.reasons))

    content = item.content
    upload_prefix = profile.a1_diy_prefix if profile.a1_diy_prefix is not None else profile.a1_diy_selector
    if profile.effect_grammar_has("dedicated_a1_diy") and isinstance(content, SingleEffect | MultiEffect):
        content_kind = SINGLE_EFFECT_CONTENT_KIND if isinstance(content, SingleEffect) else MULTI_EFFECT_CONTENT_KIND
        upload = build_dedicated_diy(content, diy_code, profile)
    elif isinstance(content, PaintedEffect):
        content_kind = PAINTED_EFFECT_CONTENT_KIND
        upload = build_h617a_diy_painted(
            content.effect,
            content.speed,
            content.brightness,
            content.background,
            _paint_groups(content.segments),
            segment_count=len(content.segments),
            grammar=profile.effect_grammar or "",
        )
    elif isinstance(content, SingleEffect):
        content_kind = SINGLE_EFFECT_CONTENT_KIND
        upload = (
            []
            if profile.diy_upload_transport == "single"
            else build_h617a_diy_single(
                content.family,
                content.variant,
                content.speed,
                content.palette,
                a1_selector=upload_prefix,
            )
        )
    elif isinstance(content, MultiEffect):
        content_kind = MULTI_EFFECT_CONTENT_KIND
        upload = build_h617a_diy_multi(
            tuple((effect.family, effect.variant) for effect in content.effects),
            content.speed,
            content.palette,
            a1_selector=upload_prefix,
        )
    else:
        raise ValueError("unsupported H617A effect content")

    resolve_diy_code(item, diy_code, model=model, profile=profile)
    activation = (
        build_inline_diy(diy_code, content.family, content.variant, content.speed, content.palette)
        if profile.diy_upload_transport == "single" and isinstance(content, SingleEffect)
        else build_diy_activation(diy_code, model, profile=profile)
    )
    digest = sha256(b"".join((*upload, activation))).hexdigest()
    return CompiledEffect(
        item_id=str(item.id),
        item_version=item.version,
        model=model,
        content_kind=content_kind,
        workflow=_effect_workflow(content),
        diy_code=diy_code,
        activation_mode=ActivationMode.CUSTOM,
        selector_kind="diy",
        expected_effect=None,
        upload_packets=tuple(upload),
        activation_packet=activation,
        artifact_sha256=digest,
        evidence_codes=(DIY_ACK_EVIDENCE,) if profile.diy_requires_upload_ack else (),
        physical_ic_count=profile.physical_ic_count
        if isinstance(content, PaintedEffect) and content.addressing == "physical_ic"
        else None,
        upload_transport=profile.diy_upload_transport
        or (
            "a1_02" if profile.a1_diy_selector is not None and isinstance(content, SingleEffect | MultiEffect) else "a3"
        ),
        upload_subtype=(
            None
            if profile.diy_upload_transport in {"a1_02", "single"}
            else 3
            if isinstance(content, PaintedEffect)
            else 4
            if profile.a1_diy_selector is None
            else None
        ),
        authored_diy=content if isinstance(content, SingleEffect | MultiEffect) else None,
        upload_prefix=profile.a1_diy_prefix,
    )


def compile_h6179(
    item: LibraryItem,
    diy_code: int,
    model: str,
    *,
    profile: ModelProfile | None = None,
) -> CompiledEffect:
    from .effect_targets import resolve_target_item

    item = resolve_target_item(item, model, profile)
    profile = profile or get_profile(model)
    result = compatibility(item, model, profile=profile)
    if result.state is not CompatibilityState.COMPATIBLE:
        raise ValueError("; ".join(result.reasons))
    content = item.content
    if not isinstance(content, H6179SingleDiyEffect | H6179MixedDiyEffect):
        raise ValueError("unsupported typed DIY content")
    upload = tuple(build_h6179_diy(content, profile=profile))
    activation = build_diy_activation(diy_code, model, profile=profile)
    return CompiledEffect(
        item_id=str(item.id),
        item_version=item.version,
        model=model,
        content_kind="h6179_single_diy" if isinstance(content, H6179SingleDiyEffect) else "h6179_mixed_diy",
        workflow=_effect_workflow(content),
        diy_code=diy_code,
        activation_mode=ActivationMode.CUSTOM,
        expected_effect=None,
        upload_packets=upload,
        activation_packet=activation,
        artifact_sha256=sha256(b"".join((*upload, activation))).hexdigest(),
        evidence_codes=("effect_content_readback_unavailable",),
        upload_transport="a3" if profile.diy_upload_transport == "a3" else "a1_02",
        upload_subtype=4 if profile.diy_upload_transport == "a3" else None,
    )


def _paint_groups(segments: tuple[tuple[int, int, int] | None, ...]) -> tuple[DiyPaintGroup, ...]:
    grouped: dict[tuple[int, int, int], list[int]] = {}
    for index, colour in enumerate(segments):
        if colour is not None:
            grouped.setdefault(colour, []).append(index)
    return tuple(
        DiyPaintGroup(colour, tuple(indices))
        for colour, indices in sorted(grouped.items(), key=lambda item: item[1][0])
    )


def compile_h6199(
    item: LibraryItem,
    diy_code: int | None = None,
    *,
    model: str | None = None,
    profile: ModelProfile | None = None,
) -> CompiledEffect:
    from .effect_targets import resolve_target_item

    if model is None:
        content = item.content
        if not isinstance(content, PaletteDiyEffect):
            raise ValueError("unsupported palette DIY content")
        model = content.model
    item = resolve_target_item(item, model, profile)
    result = compatibility(item, model, profile=profile)
    if result.state is not CompatibilityState.COMPATIBLE:
        raise ValueError("; ".join(result.reasons))
    resolved_diy_code = resolve_diy_code(item, diy_code, model=model, profile=profile)
    if resolved_diy_code is None:
        raise ValueError(f"{model} palette DIY application requires an approved observed DIY code")

    content = item.content
    if not isinstance(content, PaletteDiyEffect):
        raise ValueError("unsupported H6199 DIY content")
    upload = build_h6199_palette_diy(
        content.family,
        content.variant,
        content.speed,
        content.palette,
    )
    activation = build_diy_activation(resolved_diy_code, model, profile=profile)
    digest = sha256(b"".join((*upload, activation))).hexdigest()
    return CompiledEffect(
        item_id=str(item.id),
        item_version=item.version,
        model=model,
        content_kind="palette_diy",
        workflow=_effect_workflow(content),
        diy_code=resolved_diy_code,
        activation_mode=ActivationMode.CUSTOM,
        selector_kind="diy",
        expected_effect=None,
        upload_packets=tuple(upload),
        activation_packet=activation,
        artifact_sha256=digest,
        evidence_codes=(DIY_ACK_EVIDENCE, "effect_content_readback_unavailable"),
        upload_subtype=int(H6199EffectUpload.BodyKind.diy),
    )


def _resolve_scene(
    model: str,
    template: CatalogueRef,
    *,
    expected_scene_type: int | None = None,
) -> tuple[str, SceneEntry]:
    if template.catalogue_schema_version != 1:
        raise ValueError(f"catalogue schema version {template.catalogue_schema_version} is not supported")
    if model not in MODEL_SCENES:
        raise ValueError(f"{model} has no scene catalogue")
    from .scenes import resolve_scene_target

    resolved = resolve_scene_target(model, template)
    if resolved is None:
        raise ValueError(f"{model} scene identity ({template.scene_id}, {template.effect_id}) was not found")
    key, entry = resolved
    if expected_scene_type is not None and entry.scene_type != expected_scene_type:
        raise ValueError(
            f"{model} scene identity ({template.scene_id}, {template.effect_id}) "
            f"uses type {entry.scene_type}, not type {expected_scene_type}"
        )
    return key, entry


def _advanced_carrier(model: str) -> tuple[str, SceneEntry]:
    identity = get_profile(model).advanced_scene_carrier
    if identity is None:
        raise ValueError(f"{model} layered-scene framing is not supported")
    scene_id, effect_id = identity
    return _resolve_scene(
        model,
        CatalogueRef(model, scene_id, effect_id),
        expected_scene_type=2,
    )


def compile_application(
    item: LibraryItem,
    model: str,
    *,
    diy_code: int | None = None,
    profile: ModelProfile | None = None,
) -> CompiledApplication:
    from .effect_targets import resolve_target_item

    item = resolve_target_item(item, model, profile)
    if isinstance(item.content, StaticRgbComposition):
        resolve_diy_code(item, diy_code, model=model, profile=profile)
        return compile_static_rgb(item, model, profile=profile)
    if isinstance(item.content, MusicProfile):
        return compile_music_profile(item, model, profile=profile)
    if isinstance(item.content, VideoProfile):
        return compile_video_profile(item, model, profile=profile)
    if isinstance(item.content, H6179SingleDiyEffect | H6179MixedDiyEffect):
        resolve_diy_code(item, diy_code, model=model, profile=profile)
    elif isinstance(item.content, PaintedEffect | SingleEffect | MultiEffect):
        resolved = resolve_diy_code(item, diy_code, model=model, profile=profile)
        if _has_fixed_diy_slot(model, profile=profile):
            diy_code = resolved
        if diy_code is None:
            raise ValueError("custom-effect application requires a DIY code")
    return compile_effect(item, model, diy_code=diy_code, profile=profile)


def compile_static_rgb(item: LibraryItem, model: str, *, profile: ModelProfile | None = None) -> CompiledStaticRgb:
    profile = get_profile(model) if profile is None else profile
    content = item.content
    if not isinstance(content, StaticRgbComposition):
        raise ValueError("Expected a static RGB composition")
    result = compatibility(item, model, profile=profile)
    if result.state is not CompatibilityState.COMPATIBLE:
        raise ValueError("; ".join(result.reasons))
    grouped: dict[tuple[int, int, int], list[int]] = {}
    for index, colour in enumerate(content.segments, start=1):
        if colour is not None:
            grouped.setdefault(colour, []).append(index)
    groups = tuple(
        (tuple(indices), colour)
        for indices, colour in scale_segment_groups(
            ((indices, colour) for colour, indices in grouped.items()), content.rgb_scale
        )
    )
    colours = {index: colour for indices, colour in groups for index in indices}
    segments = tuple(colours.get(index) for index in range(1, len(content.segments) + 1))
    digest = sha256(json.dumps({"model": model, "segments": segments}, separators=(",", ":")).encode()).hexdigest()
    return CompiledStaticRgb(str(item.id), item.version, model, segments, groups, digest)


def compile_music_profile(
    item: LibraryItem, model: str, *, profile: ModelProfile | None = None
) -> CompiledMusicProfile:
    from .effect_targets import resolve_target_item

    item = resolve_target_item(item, model, profile)
    profile = get_profile(model) if profile is None else profile
    content = item.content
    if not isinstance(content, MusicProfile):
        raise ValueError("content is not a music profile")
    if content.model != model:
        raise ValueError(f"music profile targets {content.model}, not {model}")
    body = build_zoned_music_body(profile, content.mode, content.zones) if content.zones is not None else None
    calm, parameters, packets = resolve_music_profile(
        model,
        content.mode,
        content.sensitivity,
        content.colour,
        content.calm,
        content.parameters,
        profile=profile,
        palette=content.palette,
        original_body=body,
    )
    payload = {
        "kind": "music_profile",
        "model": model,
        "mode": content.mode,
        "sensitivity": content.sensitivity,
        "colour": content.colour,
        "calm": calm,
        "parameters": parameters,
        "packets": [packet.hex() for packet in packets],
        **({"palette": content.palette} if content.palette is not None else {}),
    }
    return CompiledMusicProfile(
        item_id=str(item.id),
        item_version=item.version,
        model=model,
        mode=content.mode,
        sensitivity=content.sensitivity,
        colour=content.colour,
        calm=calm,
        parameters=MappingProxyType(parameters),
        palette=content.palette,
        music_body=body,
        artifact_sha256=_semantic_digest(payload),
        packets=packets,
        physical_ic_count=profile.physical_ic_count,
    )


def compile_video_profile(
    item: LibraryItem, model: str, *, profile: ModelProfile | None = None
) -> CompiledVideoProfile:
    from .effect_targets import resolve_target_item

    item = resolve_target_item(item, model, profile)
    profile = get_profile(model) if profile is None else profile
    result = compatibility(item, model, profile=profile)
    if result.state is not CompatibilityState.COMPATIBLE:
        raise ValueError("; ".join(result.reasons))
    content = item.content
    if not isinstance(content, VideoProfile):
        raise ValueError("content is not a video profile")
    brightness = content.relative_brightness
    relative_brightness = (
        None if brightness is None else tuple(getattr(brightness, zone) for zone in profile.video_brightness_zones)
    )
    value = (
        content.white_balance_position if content.white_balance_position is not None else content.white_balance_value
    )
    white_balance_wire = (
        None if value is None else profile.video_white_balance_calibration[value - profile.video_white_balance_min]
    )
    hdmi_box_light = (
        None
        if content.hdmi_box_light is None
        else (
            content.hdmi_box_light,
            cast(int, content.hdmi_box_brightness),
            cast(bool, content.hdmi_box_automatic),
            cast(int, content.hdmi_box_effect),
        )
    )
    payload = {
        "kind": "video_profile",
        "model": model,
        "mode": content.mode,
        "full_screen": content.full_screen,
        "saturation": content.saturation,
        "sound_effects": content.sound_effects,
        "sound_effects_softness": content.sound_effects_softness,
        **({"video_sensitivity": content.video_sensitivity} if content.video_sensitivity is not None else {}),
        **({"hdmi_input": content.hdmi_input} if content.hdmi_input is not None else {}),
        **({"hdmi_box_light": hdmi_box_light} if hdmi_box_light is not None else {}),
        **({"color_calibration": content.color_calibration} if content.color_calibration is not None else {}),
        "white_balance_position": content.white_balance_position,
        "white_balance_wire": white_balance_wire,
        **({"white_balance_value": content.white_balance_value} if content.white_balance_value is not None else {}),
        "relative_brightness": relative_brightness,
        **({"relative_brightness_inline": True} if profile.video_embeds_relative_brightness else {}),
        **(
            {"whole_relative_brightness": content.whole_relative_brightness}
            if content.whole_relative_brightness is not None
            else {}
        ),
        "blank_screen": content.blank_screen,
        **({"black_border": content.black_border} if content.black_border is not None else {}),
    }
    policy = None
    if (
        content.blank_screen_detection is not None
        and content.blank_screen_low_brightness_duration_seconds is not None
        and content.blank_screen_same_tone_duration_seconds is not None
    ):
        policy = (
            content.blank_screen_detection,
            content.blank_screen_low_brightness_duration_seconds,
            content.blank_screen_same_tone_duration_seconds,
        )
        payload["blank_screen_policy"] = policy
    return CompiledVideoProfile(
        item_id=str(item.id),
        item_version=item.version,
        model=model,
        mode=content.mode,
        full_screen=content.full_screen,
        saturation=content.saturation,
        sound_effects=content.sound_effects,
        sound_effects_softness=content.sound_effects_softness,
        white_balance_position=content.white_balance_position,
        white_balance_wire=white_balance_wire,
        relative_brightness=relative_brightness,
        relative_brightness_inline=profile.video_embeds_relative_brightness,
        whole_relative_brightness=content.whole_relative_brightness,
        video_sensitivity=content.video_sensitivity,
        hdmi_input=content.hdmi_input,
        hdmi_box_light=hdmi_box_light,
        color_calibration=content.color_calibration,
        blank_screen=content.blank_screen,
        black_border=content.black_border,
        blank_screen_policy=policy,
        artifact_sha256=_semantic_digest(payload),
    )


def _semantic_digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return sha256(encoded).hexdigest()
