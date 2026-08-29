"""Compile canonical effects into model-specific device operations."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Any, Final, assert_never

from .const import MODEL_PROFILES, MUSIC_MODE_SLUGS, protocol_model
from .coordinator_modes import (
    MUSIC_STYLE_SLUGS,
    music_mode_has_parameter_write,
    music_params_for_mode,
)
from .effect_catalogue import (
    H617A_WORKSHOP_APPLY_CODE,
    H617A_WORKSHOP_SCENE_TYPE,
    H6199_DIY_EFFECTS,
    H6199_PALETTE_DIY_APPLY_CODE,
    H6199_PALETTE_DIY_APPLY_MUSIC_CODE,
    H6199_WORKSHOP_APPLY_CODE,
    H6199_WORKSHOP_APPLY_MUSIC_CODE,
)
from .effect_commands import (
    DiyPaintGroup,
    build_h617a_diy_activation,
    build_h617a_diy_multi,
    build_h617a_diy_painted,
    build_h617a_diy_single,
    build_h6199_palette_diy,
    build_h6199_palette_diy_activation,
)
from .effect_contracts import EFFECT_COMPILER_VERSION
from .effect_domain import (
    BuiltinScene,
    LayeredEffect,
    LayeredScene,
    LibraryItem,
    MultiEffect,
    MusicProfile,
    OpaqueContent,
    PaintedEffect,
    PaletteDiyEffect,
    PaletteScene,
    SingleEffect,
    VideoProfile,
    WorkshopEffect,
)
from .generated_protocol_adapter import (
    H6199EffectUpload,
    SceneBody,
    build_h617a_scene,
    build_h6199_scene,
)
from .layered_scene import CatalogueRef
from .layered_scene_decoder import encode_layered_scene, encode_workshop_effect
from .native_scenes import apply_scene_speed, build_native_scene_packets
from .palette_scene_decoder import encode_palette_scene
from .scenes import MODEL_SCENES, SceneEntry
from .transport import fragment_a3


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
    diy_code: int | None
    activation_mode: ActivationMode
    expected_effect: str | None
    upload_packets: tuple[bytes, ...]
    activation_packet: bytes | None
    artifact_sha256: str
    evidence_codes: tuple[str, ...] = ()
    compiler_version: int = EFFECT_COMPILER_VERSION

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
    compiler_version: int = EFFECT_COMPILER_VERSION
    content_kind: str = "music_profile"
    diy_code: None = None

    @property
    def progress_total(self) -> int:
        return 1 + int(music_mode_has_parameter_write(MUSIC_MODE_SLUGS[self.mode]))


@dataclass(frozen=True, slots=True)
class CompiledVideoProfile:
    item_id: str
    item_version: int
    model: str
    mode: str
    full_screen: bool
    saturation: int
    sound_effects: bool
    sound_effects_softness: int
    white_balance_position: int
    relative_brightness: tuple[int, int, int, int]
    blank_screen: bool
    artifact_sha256: str
    compiler_version: int = EFFECT_COMPILER_VERSION
    content_kind: str = "video_profile"
    diy_code: None = None
    progress_total: int = 4


CompiledApplication = CompiledEffect | CompiledMusicProfile | CompiledVideoProfile


_ADVANCED_CARRIER_IDENTITIES: Final = {
    "H617A": (1013, 11836),
    "H6199": (29884, 41599),
}


def compatibility(item: LibraryItem, model: str) -> CompatibilityResult:
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
        profile = MODEL_PROFILES.get(model)
        if profile is None or content.mode not in profile.music_modes:
            return CompatibilityResult(
                CompatibilityState.INCOMPATIBLE,
                (f"{model} does not support music mode {content.mode}",),
            )
        return CompatibilityResult(CompatibilityState.COMPATIBLE)
    if isinstance(content, VideoProfile):
        if model != "H6199" or content.model != model:
            return CompatibilityResult(
                CompatibilityState.INCOMPATIBLE,
                (f"{model} video-profile application is not supported",),
            )
        return CompatibilityResult(CompatibilityState.COMPATIBLE)
    if isinstance(content, WorkshopEffect):
        if content.model != model:
            return CompatibilityResult(
                CompatibilityState.INCOMPATIBLE,
                (f"Workshop effect targets {content.model}, not {model}",),
            )
        return CompatibilityResult(CompatibilityState.COMPATIBLE)
    if isinstance(content, BuiltinScene):
        if content.template.sku != model:
            return CompatibilityResult(
                CompatibilityState.INCOMPATIBLE,
                (f"scene targets {content.template.sku}, not {model}",),
            )
        try:
            _scene_key, entry = _resolve_scene(model, content.template)
            build_native_scene_packets(
                model,
                entry,
                speed_index=content.speed_index,
            )
        except ValueError as error:
            return CompatibilityResult(CompatibilityState.INCOMPATIBLE, (str(error),))
        return CompatibilityResult(CompatibilityState.COMPATIBLE)
    if isinstance(content, PaletteDiyEffect):
        if model != "H6199":
            return CompatibilityResult(
                CompatibilityState.INCOMPATIBLE,
                (f"H6199 palette DIY definitions are not supported on {model}",),
            )
        if content.model != model:
            return CompatibilityResult(
                CompatibilityState.INCOMPATIBLE,
                (f"palette DIY targets {content.model}, not {model}",),
            )
        supported = {(effect.family, effect.variant) for effect in H6199_DIY_EFFECTS}
        if (content.family, content.variant) not in supported:
            return CompatibilityResult(
                CompatibilityState.INCOMPATIBLE,
                (f"H6199 palette DIY family {content.family} variation {content.variant} is not supported",),
            )
        return CompatibilityResult(CompatibilityState.COMPATIBLE)
    if isinstance(content, PaintedEffect | SingleEffect | MultiEffect):
        if protocol_model(model) == "H617A":
            return CompatibilityResult(CompatibilityState.COMPATIBLE)
        return CompatibilityResult(
            CompatibilityState.INCOMPATIBLE,
            (f"this H617A custom-effect definition is not supported on {model}",),
        )
    if isinstance(content, PaletteScene | LayeredScene):
        if content.template.sku != model:
            return CompatibilityResult(
                CompatibilityState.INCOMPATIBLE,
                (f"scene targets {content.template.sku}, not {model}",),
            )
        try:
            _resolve_scene(
                model,
                content.template,
                expected_scene_type=1 if isinstance(content, PaletteScene) else 2,
            )
            if isinstance(content, PaletteScene) and content.speed_index is not None:
                raise ValueError("type-1 palette scenes do not expose a documented Speed control")
        except ValueError as error:
            return CompatibilityResult(CompatibilityState.INCOMPATIBLE, (str(error),))
        return CompatibilityResult(CompatibilityState.COMPATIBLE)
    if isinstance(content, LayeredEffect):
        if protocol_model(model) in _ADVANCED_CARRIER_IDENTITIES:
            return CompatibilityResult(CompatibilityState.COMPATIBLE)
        return CompatibilityResult(
            CompatibilityState.INCOMPATIBLE,
            (f"{model} layered-scene framing is not supported",),
        )
    assert_never(content)


def compile_effect(item: LibraryItem, model: str, *, diy_code: int | None = None) -> CompiledEffect:
    result = compatibility(item, model)
    if result.state is not CompatibilityState.COMPATIBLE:
        raise ValueError("; ".join(result.reasons))
    if isinstance(item.content, PaintedEffect | SingleEffect | MultiEffect):
        if diy_code is None:
            raise ValueError("H617A custom-effect compilation requires a DIY code")
        return compile_h617a(item, diy_code, model=model)
    if isinstance(item.content, PaletteDiyEffect):
        return compile_h6199(
            item,
            H6199_PALETTE_DIY_APPLY_CODE if diy_code is None else diy_code,
        )
    if isinstance(item.content, BuiltinScene | PaletteScene | LayeredScene | LayeredEffect):
        return compile_scene_effect(item, model)
    if isinstance(item.content, WorkshopEffect):
        expected_code = H6199_WORKSHOP_APPLY_CODE if model == "H6199" else H617A_WORKSHOP_APPLY_CODE
        if diy_code is not None and diy_code != expected_code:
            raise ValueError("Workshop has no evidenced activation packet for the requested slot")
        return _compile_workshop_effect(item, model)
    raise ValueError("unsupported effect content")


def _compile_workshop_effect(
    item: LibraryItem,
    model: str,
) -> CompiledEffect:
    content = item.content
    if isinstance(content, WorkshopEffect):
        payload = encode_workshop_effect(
            model,
            content.effect,
            trailing_padding=content.trailing_padding,
        )
        body_kind = int(H6199EffectUpload.BodyKind.scene) if model == "H6199" else int(SceneBody.SceneType.scene_v2)
        upload = tuple(fragment_a3(body_kind, payload))
        content_kind = "workshop"
    else:
        raise ValueError("content is not an upload-only effect")

    if model == "H6199":
        diy_code = H6199_WORKSHOP_APPLY_CODE
        activation = build_h6199_scene(diy_code, H6199_WORKSHOP_APPLY_MUSIC_CODE)
    else:
        diy_code = H617A_WORKSHOP_APPLY_CODE
        activation = build_h617a_scene(diy_code, scene_type=H617A_WORKSHOP_SCENE_TYPE)
    packets = (*upload, activation)
    return CompiledEffect(
        item_id=str(item.id),
        item_version=item.version,
        model=model,
        content_kind=content_kind,
        diy_code=diy_code,
        activation_mode=ActivationMode.CUSTOM,
        expected_effect=None,
        upload_packets=upload,
        activation_packet=activation,
        artifact_sha256=sha256(b"".join(packets)).hexdigest(),
        evidence_codes=("effect_content_readback_unavailable",),
    )


def compile_scene_effect(item: LibraryItem, model: str) -> CompiledEffect:
    result = compatibility(item, model)
    if result.state is not CompatibilityState.COMPATIBLE:
        raise ValueError("; ".join(result.reasons))

    content = item.content
    evidence_codes: list[str] = []
    if isinstance(content, BuiltinScene):
        content_kind = "scene_builtin"
        scene_key, entry = _resolve_scene(model, content.template)
        packets = tuple(
            build_native_scene_packets(
                model,
                entry,
                speed_index=content.speed_index,
            )
        )
        upload = packets[:-1]
        activation = packets[-1]
        if upload:
            evidence_codes.append("scene_payload_readback_unavailable")
    elif isinstance(content, PaletteScene):
        content_kind = "scene_palette"
        scene_key, entry = _resolve_scene(model, content.template, expected_scene_type=1)
        if content.speed_index is not None:
            raise ValueError("type-1 palette scenes do not expose a documented Speed control")
        scene_type = 1
        payload = encode_palette_scene(content)
        upload = tuple(fragment_a3(scene_type, payload))
        activation = _scene_activation(model, entry)
        evidence_codes.append("scene_payload_readback_unavailable")
    elif isinstance(content, LayeredScene):
        content_kind = "scene_layered"
        scene_key, entry = _resolve_scene(model, content.template, expected_scene_type=2)
        scene_type = 2
        payload = _apply_speed(encode_layered_scene(content), entry, content.speed_index)
        upload = tuple(fragment_a3(scene_type, payload))
        activation = _scene_activation(model, entry)
        evidence_codes.extend(
            (
                "scene_payload_readback_unavailable",
                "layered_field_semantics_uncalibrated",
            )
        )
    elif isinstance(content, LayeredEffect):
        content_kind = "advanced"
        scene_key, entry = _advanced_carrier(model)
        scene_type = 2
        payload = encode_layered_scene(
            LayeredScene(
                template=CatalogueRef(model, entry.scene_id, entry.effect_id),
                effect=content,
            )
        )
        evidence_codes.extend(
            (
                "scene_payload_readback_unavailable",
                "layered_field_semantics_uncalibrated",
                "layered_activation_carrier_uncalibrated",
            )
        )
        upload = tuple(fragment_a3(scene_type, payload))
        activation = _scene_activation(model, entry)
    else:
        raise ValueError("unsupported scene effect content")

    digest = sha256(b"".join((*upload, activation))).hexdigest()
    return CompiledEffect(
        item_id=str(item.id),
        item_version=item.version,
        model=model,
        content_kind=content_kind,
        diy_code=entry.code,
        activation_mode=ActivationMode.SCENE,
        expected_effect=scene_key,
        upload_packets=upload,
        activation_packet=activation,
        artifact_sha256=digest,
        evidence_codes=tuple(evidence_codes),
    )


def compile_h617a(item: LibraryItem, diy_code: int, *, model: str = "H617A") -> CompiledEffect:
    result = compatibility(item, model)
    if result.state is not CompatibilityState.COMPATIBLE:
        raise ValueError("; ".join(result.reasons))

    content = item.content
    if isinstance(content, PaintedEffect):
        content_kind = "h617a_painted"
        upload = build_h617a_diy_painted(
            content.effect,
            content.speed,
            content.brightness,
            (0, 0, 0),
            _paint_groups(content.segments),
        )
    elif isinstance(content, SingleEffect):
        content_kind = "h617a_single"
        upload = build_h617a_diy_single(
            content.family,
            content.variant,
            content.speed,
            content.palette,
        )
    elif isinstance(content, MultiEffect):
        content_kind = "h617a_multi"
        upload = build_h617a_diy_multi(
            tuple((effect.family, effect.variant) for effect in content.effects),
            content.speed,
            content.palette,
        )
    else:
        raise ValueError("unsupported H617A effect content")

    activation = build_h617a_diy_activation(diy_code)
    digest = sha256(b"".join((*upload, activation))).hexdigest()
    return CompiledEffect(
        item_id=str(item.id),
        item_version=item.version,
        model=model,
        content_kind=content_kind,
        diy_code=diy_code,
        activation_mode=ActivationMode.CUSTOM,
        expected_effect=None,
        upload_packets=tuple(upload),
        activation_packet=activation,
        artifact_sha256=digest,
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
    diy_code: int = H6199_PALETTE_DIY_APPLY_CODE,
) -> CompiledEffect:
    result = compatibility(item, "H6199")
    if result.state is not CompatibilityState.COMPATIBLE:
        raise ValueError("; ".join(result.reasons))
    if diy_code != H6199_PALETTE_DIY_APPLY_CODE:
        raise ValueError(f"H6199 DIY activation is only evidenced for slot {H6199_PALETTE_DIY_APPLY_CODE}")

    content = item.content
    if not isinstance(content, PaletteDiyEffect):
        raise ValueError("unsupported H6199 DIY content")
    upload = build_h6199_palette_diy(
        content.family,
        content.variant,
        content.speed,
        content.palette,
    )
    activation = build_h6199_palette_diy_activation(
        H6199_PALETTE_DIY_APPLY_CODE,
        H6199_PALETTE_DIY_APPLY_MUSIC_CODE,
    )
    digest = sha256(b"".join((*upload, activation))).hexdigest()
    return CompiledEffect(
        item_id=str(item.id),
        item_version=item.version,
        model="H6199",
        content_kind="palette_diy",
        diy_code=H6199_PALETTE_DIY_APPLY_CODE,
        activation_mode=ActivationMode.CUSTOM,
        expected_effect=None,
        upload_packets=tuple(upload),
        activation_packet=activation,
        artifact_sha256=digest,
        evidence_codes=("effect_content_readback_unavailable",),
    )


def _resolve_scene(
    model: str,
    template: CatalogueRef,
    *,
    expected_scene_type: int | None = None,
) -> tuple[str, SceneEntry]:
    if template.catalogue_schema_version != 1:
        raise ValueError(f"catalogue schema version {template.catalogue_schema_version} is not supported")
    scenes = MODEL_SCENES.get(model)
    if scenes is None:
        raise ValueError(f"{model} has no scene catalogue")
    for key, entry in scenes.items():
        if entry.scene_id == template.scene_id and entry.effect_id == template.effect_id:
            if expected_scene_type is not None and entry.scene_type != expected_scene_type:
                raise ValueError(
                    f"{model} scene identity ({template.scene_id}, {template.effect_id}) "
                    f"uses type {entry.scene_type}, not type {expected_scene_type}"
                )
            return key, entry
    raise ValueError(f"{model} scene identity ({template.scene_id}, {template.effect_id}) was not found")


def _advanced_carrier(model: str) -> tuple[str, SceneEntry]:
    try:
        scene_id, effect_id = _ADVANCED_CARRIER_IDENTITIES[protocol_model(model) or model]
    except KeyError as error:
        raise ValueError(f"{model} layered-scene framing is not supported") from error
    return _resolve_scene(
        model,
        CatalogueRef(model, scene_id, effect_id),
        expected_scene_type=2,
    )


def _apply_speed(payload: bytes, entry: SceneEntry, speed_index: int | None) -> bytes:
    if entry.speed is None:
        if speed_index is not None:
            raise ValueError("this scene does not expose a documented Speed control")
        return payload
    resolved = entry.speed.default_index if speed_index is None else speed_index
    if not 0 <= resolved < entry.speed.option_count:
        raise ValueError(f"scene speed index {resolved} outside 0..{entry.speed.option_count - 1}")
    return apply_scene_speed(payload, entry.speed, resolved)


def _scene_activation(model: str, entry: SceneEntry) -> bytes:
    if model == "H6199":
        return build_h6199_scene(entry.code, entry.music_code)
    return build_h617a_scene(entry.code)


def compile_application(item: LibraryItem, model: str, *, diy_code: int | None = None) -> CompiledApplication:
    if isinstance(item.content, MusicProfile):
        return compile_music_profile(item, model)
    if isinstance(item.content, VideoProfile):
        return compile_video_profile(item, model)
    if isinstance(item.content, PaintedEffect | SingleEffect | MultiEffect):
        if protocol_model(model) != "H617A":
            raise ValueError(f"{model} custom-effect upload is not supported")
        if diy_code is None:
            raise ValueError("custom-effect application requires a DIY code")
    return compile_effect(item, model, diy_code=diy_code)


def compile_music_profile(item: LibraryItem, model: str) -> CompiledMusicProfile:
    result = compatibility(item, model)
    if result.state is not CompatibilityState.COMPATIBLE:
        raise ValueError("; ".join(result.reasons))
    content = item.content
    if not isinstance(content, MusicProfile):
        raise ValueError("content is not a music profile")
    profile = MODEL_PROFILES[model]
    if content.colour is not None and not profile.supports_music_color:
        raise ValueError(f"{model} does not support a fixed music colour")
    if content.calm is not None and content.mode not in MUSIC_STYLE_SLUGS:
        raise ValueError(f"music mode {content.mode} does not support a style setting")

    mode_code = MUSIC_MODE_SLUGS[content.mode]
    parameters = _compile_music_parameters(content.parameters, mode_code)
    payload = {
        "kind": "music_profile",
        "model": model,
        "mode": content.mode,
        "sensitivity": content.sensitivity,
        "colour": content.colour,
        "calm": bool(content.calm),
        "parameters": parameters,
    }
    return CompiledMusicProfile(
        item_id=str(item.id),
        item_version=item.version,
        model=model,
        mode=content.mode,
        sensitivity=content.sensitivity,
        colour=content.colour,
        calm=bool(content.calm),
        parameters=parameters,
        artifact_sha256=_semantic_digest(payload),
    )


def compile_video_profile(item: LibraryItem, model: str) -> CompiledVideoProfile:
    result = compatibility(item, model)
    if result.state is not CompatibilityState.COMPATIBLE:
        raise ValueError("; ".join(result.reasons))
    content = item.content
    if not isinstance(content, VideoProfile):
        raise ValueError("content is not a video profile")
    brightness = content.relative_brightness
    relative_brightness = brightness.left, brightness.top, brightness.right, brightness.bottom
    payload = {
        "kind": "video_profile",
        "model": model,
        "mode": content.mode,
        "full_screen": content.full_screen,
        "saturation": content.saturation,
        "sound_effects": content.sound_effects,
        "sound_effects_softness": content.sound_effects_softness,
        "white_balance_position": content.white_balance_position,
        "relative_brightness": relative_brightness,
        "blank_screen": content.blank_screen,
    }
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
        relative_brightness=relative_brightness,
        blank_screen=content.blank_screen,
        artifact_sha256=_semantic_digest(payload),
    )


def _compile_music_parameters(
    raw: Mapping[str, Any],
    mode_code: int,
) -> dict[str, int | bool | str]:
    relevant = music_params_for_mode(mode_code)
    unsupported = sorted(set(raw).difference(spec.profile_key for spec in relevant))
    if unsupported:
        raise ValueError(f"music mode does not support parameter {unsupported[0]}")
    compiled: dict[str, int | bool | str] = {}
    for spec in relevant:
        value = raw.get(spec.profile_key, spec.default)
        if spec.kind == "number":
            if not isinstance(value, int) or isinstance(value, bool) or not spec.min_value <= value <= spec.max_value:
                raise ValueError(f"{spec.profile_key} must be an integer from {spec.min_value} to {spec.max_value}")
        elif spec.kind == "switch":
            if not isinstance(value, bool):
                raise ValueError(f"{spec.profile_key} must be a boolean")
        elif not isinstance(value, str) or value not in spec.options:
            raise ValueError(f"{spec.profile_key} must be one of {', '.join(spec.options)}")
        compiled[spec.profile_key] = value
    return compiled


def _semantic_digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return sha256(encoded).hexdigest()
