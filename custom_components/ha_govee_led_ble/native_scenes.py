"""Native-scene payload patching and application packet encoding."""

import base64
import io
from dataclasses import replace
from typing import Any

from kaitaistruct import KaitaiStream, KaitaiStructError

from .const import ModelProfile, get_profile
from .effect_domain import LayeredScene, NativeEffect, PaletteScene
from .generated_protocol_adapter import build_scene_activation, parse_scene_body
from .h60a6_effects import encode_native_body
from .layered_scene import CatalogueRef, LayeredEffect
from .layered_scene_decoder import decode_layered_scene, encode_layered_scene
from .palette_scene_decoder import encode_palette_scene
from .protocol_core import (
    H60a6DiyBody,
    H60a6EffectFrame,
    H60a6PaintBody,
    H607cSceneBody,
    H1771DiyBody,
    H1771EffectUpload,
    serialize_native_body,
)
from .scenes import SceneEntry, SceneSpeed, scene_for_profile, scene_selector_code
from .transport import fragment_a3, fragment_a4


def apply_scene_speed(payload: bytes, speed: SceneSpeed, index: int, *, scene_type: int = 2) -> bytes:
    """Apply one speed option through the generated layered-scene fields."""
    if payload[:1] == b"\x51" and scene_type == 6:
        from .h60b0_effects import apply_combined_speed

        return apply_combined_speed(payload, speed, index)
    if speed.layer_speeds:
        if not 0 <= index < speed.option_count:
            raise ValueError("Scene speed index is outside its documented options")
        root = _parse_native_scene_body(payload, 797)
        speed.validate_layer_count(root.payload.layer_count)
        for layer, value in zip(root.payload.layers, speed.layer_speeds[index], strict=True):
            if not hasattr(layer.body, "speed"):
                raise ValueError("Scene speed targets an unknown native layer")
            layer.body.speed = value
        return serialize_native_body(root)
    scene = decode_layered_scene(CatalogueRef("H617A", 0, 0), payload, scene_type=scene_type)
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
    if family == int(H1771DiyBody.CatalogueFamily.native_scene):
        try:
            root = H1771DiyBody.Scene(KaitaiStream(io.BytesIO(payload)), _root=H1771DiyBody())
            root._read()
            if not root._io.is_eof():
                raise ValueError("Native scene body contains trailing data")
            return root
        except (KaitaiStructError, EOFError) as error:
            raise ValueError("Invalid native scene body") from error
    root_type = {797: H60a6DiyBody, 798: H60a6PaintBody}.get(family)
    if root_type is None:
        raise ValueError("Native scene has no documented body family")
    try:
        root = root_type.from_bytes(payload)
        root._read()
        if not root._io.is_eof():
            raise ValueError("Native scene body contains trailing data")
        return root
    except KaitaiStructError as error:
        raise ValueError("Invalid native scene body") from error


def native_scene_upload_route(scene: SceneEntry, profile: ModelProfile) -> tuple[str, int] | None:
    """Resolve exact catalogue families independently of their scene-type number."""
    if scene.selector_only or not scene.param:
        return None
    if profile.command_grammar == "H6179" or profile.selector_only_scene_bits is not None:
        return None
    if profile.effect_grammar == "H1771" and scene.scene_type == 5:
        if scene.diy_effect_codes == (int(H1771DiyBody.CatalogueFamily.native_scene),):
            return "a3", int(H1771EffectUpload.UploadKind.native_diy)
        raise ValueError("Native scene has no documented upload family")
    if profile.effect_grammar == "H60A6" and scene.scene_type == 5:
        if scene.diy_effect_codes == (797,):
            return "a3", int(H60a6EffectFrame.Subtype.native_effect)
        if scene.diy_effect_codes == (798,):
            return "a4", int(H60a6EffectFrame.Subtype.native_effect)
        raise ValueError("Native scene has no documented upload family")
    if scene.scene_type == 5:
        raise ValueError("Device profile does not support this native scene body")
    if profile.effect_grammar == "H60B0":
        from .h60b0_effects import H60b0SceneBody

        if scene.scene_type != 6:
            raise ValueError("Device profile does not support this combined scene body")
        return "a3", int(H60b0SceneBody.UploadSubtype.combined)
    if profile.effect_grammar == "H607C" or scene.scene_type == int(H607cSceneBody.CatalogueType.layered_scene):
        if profile.effect_grammar != "H607C" or scene.scene_type != int(H607cSceneBody.CatalogueType.layered_scene):
            raise ValueError("Device profile does not support this layered scene body")
        return "a3", int(H607cSceneBody.UploadSubtype.layered_scene)
    return "a3", scene.scene_type


def native_scene_prefers_selector(scene: SceneEntry, payload: bytes, profile: ModelProfile) -> bool:
    return bool(
        profile.effect_grammar == "H1771"
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
    if scene.selector_only or profile.command_grammar == "H6179" or profile.selector_only_scene_bits is not None:
        if speed_index is not None:
            raise ValueError(f"{model} selector-only native scenes do not accept speed_index")
        if canonical_body is not None:
            raise ValueError(f"{model} selector-only native scenes do not accept canonical_body")
        return [build_scene_activation(model, scene_selector_code(model, scene, profile=profile), profile=profile)]

    payload, _resolved_speed = resolve_native_scene_body(
        scene,
        speed_index=speed_index,
        canonical_body=canonical_body,
    )
    if payload and scene.scene_type == 2 and profile.rgbic_scene_v0 is not None:
        decoded = decode_layered_scene(CatalogueRef(model, scene.scene_id, scene.effect_id), payload)
        payload = encode_layered_scene(decoded, profile=profile)
    if native_scene_prefers_selector(scene, payload, profile):
        return [build_scene_activation(model, scene.code, scene.music_code, profile=profile)]
    route = native_scene_upload_route(scene, profile)
    if payload and scene.scene_type == 5:
        native = _parse_native_scene_body(payload, scene.diy_effect_codes[0])
        if profile.effect_grammar == "H1771":
            payload = serialize_native_body(native.body)
    if payload and scene.scene_type == int(H607cSceneBody.CatalogueType.layered_scene):
        if profile.effect_grammar == "H60B0":
            from .h60b0_effects import combined_upload_body

            payload = combined_upload_body(payload)
        else:
            parsed, _padding = parse_scene_body(payload, scene_type=scene.scene_type)
            payload = payload[len(parsed.marker) :]
    upload = (
        (fragment_a4 if route[0] == "a4" else fragment_a3)(route[1], payload) if payload and route is not None else []
    )
    activation = build_scene_activation(model, scene.code, scene.music_code, profile=profile)
    return [*upload, activation]


def resolve_native_scene_body(
    scene: SceneEntry,
    *,
    speed_index: int | None = None,
    canonical_body: bytes | None = None,
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
        elif scene.scene_type == int(H607cSceneBody.CatalogueType.layered_scene):
            if canonical_body[:1] == b"\x51":
                from .h60b0_effects import parse_combined_scene

                parse_combined_scene(canonical_body)
            else:
                parse_scene_body(canonical_body, scene_type=scene.scene_type)
        return canonical_body, speed_index

    payload = base64.b64decode(scene.param, validate=True) if scene.param else b""
    if scene.speed is not None:
        resolved_speed = scene.speed.default_index if speed_index is None else speed_index
        if not 0 <= resolved_speed < scene.speed.option_count:
            raise ValueError(f"scene speed index {resolved_speed} outside 0..{scene.speed.option_count - 1}")
        return apply_scene_speed(payload, scene.speed, resolved_speed, scene_type=scene.scene_type), resolved_speed
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
        body = encode_native_body(content)
    else:
        if scene.scene_type not in {2, int(H607cSceneBody.CatalogueType.layered_scene)}:
            raise ValueError("layered content does not match the native scene type")
        body = encode_layered_scene(content, scene_type=scene.scene_type)
    if scene.speed is None:
        if content.speed_index is not None:
            raise ValueError("this scene does not expose a documented Speed control")
        return body, None
    if (
        isinstance(content, NativeEffect) or isinstance(content, LayeredScene) and content.template.sku == "H60B0"
    ) and content.speed_index is None:
        return body, None
    resolved_speed = scene.speed.default_index if content.speed_index is None else content.speed_index
    if not 0 <= resolved_speed < scene.speed.option_count:
        raise ValueError(f"scene speed index {resolved_speed} outside 0..{scene.speed.option_count - 1}")
    return apply_scene_speed(body, scene.speed, resolved_speed, scene_type=scene.scene_type), resolved_speed
