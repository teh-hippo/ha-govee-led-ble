"""Native-scene payload patching and application packet encoding."""

import base64
from dataclasses import replace
from typing import Any

from kaitaistruct import KaitaiStructError

from .const import ModelProfile, get_profile
from .effect_domain import LayeredScene, NativeEffect, PaletteScene
from .generated_protocol_adapter import build_scene_activation, parse_scene_body
from .layered_scene import CatalogueRef, LayeredEffect
from .layered_scene_decoder import decode_layered_scene, encode_layered_scene
from .native_effect_codecs import (
    native_effect_codec_for_content,
    native_effect_codec_for_profile,
    native_effect_codec_for_scene_family,
    native_effect_codec_for_scene_speed,
    native_effect_codec_for_target,
)
from .palette_scene_decoder import encode_palette_scene
from .scenes import SceneEntry, SceneSpeed, scene_for_profile, scene_selector_code
from .transport import fragment_a3, fragment_a4


def apply_scene_speed(
    payload: bytes,
    speed: SceneSpeed,
    index: int,
    *,
    scene_type: int = 2,
    target: str | None = None,
) -> bytes:
    """Apply one speed option through the generated layered-scene fields."""
    if speed.projector_speeds:
        from .projector_protocol import apply_projector_speed

        return apply_projector_speed(payload, speed, index)
    codec = (
        native_effect_codec_for_target(target)
        if target is not None
        else native_effect_codec_for_scene_speed(scene_type, payload)
    )
    if target is None and codec is not None:
        target = codec.canonical_target
    if codec is not None and codec.apply_layered_speed is not None:
        return codec.apply_layered_speed(payload, speed, index)
    if speed.layer_speeds:
        raise ValueError("Scene speed has no selected native codec")
    scene = decode_layered_scene(CatalogueRef(target or "H617A", 0, 0), payload, scene_type=scene_type)
    layers = list(scene.effect.layers)
    for page in speed.pages:
        if not 0 <= page.page < len(layers):
            continue
        layer = layers[page.page]
        brightness_patterns = list(layer.brightness_patterns)
        for brightness in page.brightness_speeds:
            if 0 <= brightness.block < len(brightness_patterns) and brightness.values:
                brightness_patterns[brightness.block] = replace(
                    brightness_patterns[brightness.block],
                    change_speed=_speed_value(brightness.values, index),
                )
        layers[page.page] = replace(
            layer,
            selected_movement=(
                replace(layer.selected_movement, speed=_speed_value(page.move_in, index))
                if page.move_in
                else layer.selected_movement
            ),
            overall_movement=(
                replace(layer.overall_movement, speed=_speed_value(page.move_all, index))
                if page.move_all
                else layer.overall_movement
            ),
            colour_speed=(_speed_value(page.colour_speed, index) if page.colour_speed else layer.colour_speed),
            brightness_patterns=tuple(brightness_patterns),
        )
    return encode_layered_scene(replace(scene, effect=LayeredEffect(tuple(layers))), scene_type=scene_type)


def _speed_value(options: tuple[int, ...], index: int) -> int:
    return options[max(0, min(len(options) - 1, index))]


def _parse_native_scene_body(payload: bytes, family: int) -> Any:
    codec = native_effect_codec_for_scene_family(family)
    if codec is None:
        raise ValueError("Native scene has no documented body family")
    try:
        return codec.parse_scene(payload, family)
    except (KaitaiStructError, EOFError) as error:
        raise ValueError("Invalid native scene body") from error


def native_scene_upload_route(scene: SceneEntry, profile: ModelProfile) -> tuple[str, int] | None:
    """Resolve exact catalogue families independently of their scene-type number."""
    if scene.selector_only or not scene.param:
        return None
    if profile.selector_only_scene_bits is not None:
        return None
    codec = native_effect_codec_for_profile(profile)
    route = None if codec is None else codec.scene_route_for(scene)
    if route is not None:
        return route.carrier.value, route.subtype
    if scene.scene_type == 5 or (profile.native_effect_codec is not None and scene.scene_type not in {1, 2}):
        kind = "native" if scene.scene_type == 5 else "layered"
        raise ValueError(f"Device profile does not support this {kind} scene body")
    return "a3", scene.scene_type


def native_scene_body_is_opaque(scene: SceneEntry, model: str) -> bool:
    codec = native_effect_codec_for_target(model)
    return bool(
        codec is not None
        and scene.scene_type == 5
        and len(scene.diy_effect_codes) == 1
        and scene.diy_effect_codes[0] in codec.opaque_scene_families
    )


def native_scene_prefers_selector(scene: SceneEntry, payload: bytes, profile: ModelProfile) -> bool:
    codec = native_effect_codec_for_profile(profile)
    return bool(
        codec is not None
        and codec.selector_only_native_scene
        and scene.scene_type == 5
        and scene.param
        and payload == base64.b64decode(scene.param, validate=True)
    )


def build_native_scene_packets(
    model: str,
    scene: SceneEntry,
    *,
    speed_index: int | None = None,
    canonical_body: bytes | None = None,
    profile: ModelProfile | None = None,
) -> list[bytes]:
    """Build a catalogue scene upload and activation with its resolved speed default."""
    if profile is not None:
        scene = scene_for_profile(scene, profile)
    profile = get_profile(model) if profile is None else profile
    if scene.selector_only or profile.selector_only_scene_bits is not None:
        if speed_index is not None:
            raise ValueError(f"{model} selector-only native scenes do not accept speed_index")
        if canonical_body is not None:
            raise ValueError(f"{model} selector-only native scenes do not accept canonical_body")
        return [build_scene_activation(model, scene_selector_code(model, scene, profile=profile), profile=profile)]

    payload, _resolved_speed = resolve_native_scene_body(
        scene,
        speed_index=speed_index,
        canonical_body=canonical_body,
        target=model,
    )
    if payload and scene.scene_type == 2 and native_scene_uses_geometry(scene, profile):
        decoded = decode_layered_scene(CatalogueRef(model, scene.scene_id, scene.effect_id), payload)
        payload = encode_layered_scene(decoded, profile=native_scene_geometry_profile(profile))
    if native_scene_prefers_selector(scene, payload, profile):
        return [
            build_scene_activation(
                model, scene_selector_code(model, scene, profile=profile), scene.music_code, profile=profile
            )
        ]
    route = native_scene_upload_route(scene, profile)
    if payload and scene.scene_type == 5:
        native = _parse_native_scene_body(payload, scene.diy_effect_codes[0])
        codec = native_effect_codec_for_profile(profile)
        if codec is not None and codec.prepare_scene_payload is not None:
            payload = codec.prepare_scene_payload(payload, scene.diy_effect_codes[0], native)
    codec = native_effect_codec_for_profile(profile)
    if payload and codec is not None and codec.layered_scene_type == scene.scene_type:
        if codec is not None and codec.prepare_layered_payload is not None:
            payload = codec.prepare_layered_payload(payload)
        else:
            parsed, _padding = parse_scene_body(payload, scene_type=scene.scene_type)
            payload = payload[len(parsed.marker) :]
    upload = (
        (fragment_a4 if route[0] == "a4" else fragment_a3)(route[1], payload) if payload and route is not None else []
    )
    activation = build_scene_activation(
        model, scene_selector_code(model, scene, profile=profile), scene.music_code, profile=profile
    )
    return [*upload, activation]


def native_scene_uses_geometry(scene: SceneEntry, profile: ModelProfile) -> bool:
    """Return whether a native type-2 scene is prepared for installed geometry."""
    return scene.scene_type == 2 and (profile.rgbic_scene_v0 is not None or profile.configured_string_scene_geometry)


def native_scene_geometry_profile(profile: ModelProfile) -> ModelProfile:
    """Enable V1 geometry clamping without opting native DIY into scene preparation."""
    if profile.configured_string_scene_geometry and profile.rgbic_scene_v0 is None:
        if profile.physical_ic_count is None:
            raise ValueError("Native scene geometry is unknown; refresh and retry")
        return replace(profile, rgbic_scene_v0=False, configured_string_scene_geometry=False)
    return profile


def resolve_native_scene_body(
    scene: SceneEntry,
    *,
    speed_index: int | None = None,
    canonical_body: bytes | None = None,
    target: str | None = None,
) -> tuple[bytes, int | None]:
    if canonical_body is not None:
        if scene.scene_type == 0:
            raise ValueError("selector-only scenes cannot have a stored parameter body")
        if not canonical_body:
            raise ValueError("stored scene parameter body must not be empty")
        if scene.scene_type == 5:
            if len(scene.diy_effect_codes) != 1:
                raise ValueError("Native scene has no documented body family")
            _parse_native_scene_body(canonical_body, scene.diy_effect_codes[0])
        elif (
            target_codec := (
                native_effect_codec_for_target(target)
                if target is not None
                else native_effect_codec_for_scene_speed(scene.scene_type, canonical_body)
            )
        ) is not None and target_codec.layered_scene_type == scene.scene_type:
            if target_codec.validate_layered_payload is not None:
                target_codec.validate_layered_payload(canonical_body)
            else:
                parse_scene_body(canonical_body, scene_type=scene.scene_type)
        return canonical_body, speed_index

    payload = base64.b64decode(scene.param, validate=True) if scene.param else b""
    if scene.speed is not None:
        resolved_speed = scene.speed.default_index if speed_index is None else speed_index
        if not 0 <= resolved_speed < scene.speed.option_count:
            raise ValueError(f"scene speed index {resolved_speed} outside 0..{scene.speed.option_count - 1}")
        return apply_scene_speed(
            payload,
            scene.speed,
            resolved_speed,
            scene_type=scene.scene_type,
            target=target,
        ), resolved_speed
    if speed_index is not None:
        raise ValueError("This scene does not expose a documented Speed control")
    return payload, None


def encode_authored_scene_body(
    content: PaletteScene | LayeredScene | NativeEffect,
    scene: SceneEntry,
) -> tuple[bytes, int | None]:
    if isinstance(content, PaletteScene):
        if scene.scene_type != 1:
            raise ValueError("palette content does not match the native scene type")
        if content.speed_index is not None:
            raise ValueError("type-1 palette scenes do not expose a documented Speed control")
        return encode_palette_scene(content), None
    if isinstance(content, NativeEffect):
        if scene.scene_type != 5 or scene.diy_effect_codes != (content.family,):
            raise ValueError("native content does not match the catalogue body family")
        native_codec = native_effect_codec_for_content(content)
        body = native_codec.encode(content)
    else:
        layered_codec = native_effect_codec_for_target(content.template.sku)
        if scene.scene_type != 2 and (layered_codec is None or layered_codec.layered_scene_type != scene.scene_type):
            raise ValueError("layered content does not match the native scene type")
        body = encode_layered_scene(content, scene_type=scene.scene_type)
    if scene.speed is None:
        if content.speed_index is not None:
            raise ValueError("this scene does not expose a documented Speed control")
        return body, None
    target = content.model if isinstance(content, NativeEffect) else content.template.sku
    target_codec = native_effect_codec_for_target(target)
    if content.speed_index is None and (
        isinstance(content, NativeEffect) or target_codec is not None and target_codec.preserves_unspecified_scene_speed
    ):
        return body, None
    resolved_speed = scene.speed.default_index if content.speed_index is None else content.speed_index
    if not 0 <= resolved_speed < scene.speed.option_count:
        raise ValueError(f"scene speed index {resolved_speed} outside 0..{scene.speed.option_count - 1}")
    return (
        apply_scene_speed(body, scene.speed, resolved_speed, scene_type=scene.scene_type, target=target),
        resolved_speed,
    )
