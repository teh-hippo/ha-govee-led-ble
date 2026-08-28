"""Native-scene payload patching and application packet encoding."""

import base64
from dataclasses import replace

from .effect_domain import LayeredScene, PaletteScene
from .generated_protocol_adapter import build_h617a_scene, build_h6199_scene
from .layered_scene import CatalogueRef, LayeredEffect
from .layered_scene_decoder import decode_layered_scene, encode_layered_scene
from .palette_scene_decoder import encode_palette_scene
from .scenes import SceneEntry, SceneSpeed
from .transport import fragment_a3


def apply_scene_speed(payload: bytes, speed: SceneSpeed, index: int) -> bytes:
    """Apply one speed option through the generated layered-scene fields."""
    scene = decode_layered_scene(CatalogueRef("H617A", 0, 0), payload)
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
    return encode_layered_scene(replace(scene, effect=LayeredEffect(tuple(layers))))


def _speed_value(options: tuple[int, ...], index: int) -> int:
    return options[max(0, min(len(options) - 1, index))]


def build_native_scene_packets(
    model: str,
    scene: SceneEntry,
    *,
    speed_index: int | None = None,
    canonical_body: bytes | None = None,
) -> list[bytes]:
    """Build a catalogue scene upload and activation with its resolved speed default."""
    payload, _resolved_speed = resolve_native_scene_body(
        scene,
        speed_index=speed_index,
        canonical_body=canonical_body,
    )
    upload = fragment_a3(scene.scene_type, payload) if payload else []
    activation = build_h6199_scene(scene.code, scene.music_code) if model == "H6199" else build_h617a_scene(scene.code)
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
        return canonical_body, speed_index

    payload = base64.b64decode(scene.param, validate=True) if scene.param else b""
    if scene.speed is not None:
        resolved_speed = scene.speed.default_index if speed_index is None else speed_index
        if not 0 <= resolved_speed < scene.speed.option_count:
            raise ValueError(f"scene speed index {resolved_speed} outside 0..{scene.speed.option_count - 1}")
        return apply_scene_speed(payload, scene.speed, resolved_speed), resolved_speed
    if speed_index is not None:
        raise ValueError("This scene does not expose a documented Speed control")
    return payload, None


def encode_authored_scene_body(
    content: PaletteScene | LayeredScene,
    scene: SceneEntry,
) -> tuple[bytes, int | None]:
    if isinstance(content, PaletteScene):
        if scene.scene_type != 1:
            raise ValueError("palette content does not match the native scene type")
        if content.speed_index is not None:
            raise ValueError("type-1 palette scenes do not expose a documented Speed control")
        return encode_palette_scene(content), None
    if scene.scene_type != 2:
        raise ValueError("layered content does not match the native scene type")
    body = encode_layered_scene(content)
    if scene.speed is None:
        if content.speed_index is not None:
            raise ValueError("this scene does not expose a documented Speed control")
        return body, None
    resolved_speed = scene.speed.default_index if content.speed_index is None else content.speed_index
    if not 0 <= resolved_speed < scene.speed.option_count:
        raise ValueError(f"scene speed index {resolved_speed} outside 0..{scene.speed.option_count - 1}")
    return apply_scene_speed(body, scene.speed, resolved_speed), resolved_speed
