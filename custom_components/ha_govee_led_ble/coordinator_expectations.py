"""Optimistic coordinator expectations derived from outgoing packets."""

from typing import Any

from .const import ModelProfile, get_profile
from .coordinator_status import ParsedMode
from .generated_protocol_adapter import (
    parse_command,
    parse_h6179_command,
    parse_video_command,
    video_parameters_from_detail,
)
from .light_commands import parse_static_write
from .music_protocol import music_slug_for
from .scenes import MODEL_SCENES, scene_key_for_code

_SCENE_EFFECT_BY_MODEL_ID = {
    model: {scene.code: name for name, scene in scenes.items()} for model, scenes in MODEL_SCENES.items()
}


def expectations_from_packet(
    packet: bytes,
    model: str = "H617A",
    *,
    static_echoes_color: bool = False,
    profile: ModelProfile | None = None,
) -> dict[str, Any]:
    """Map an outgoing command to the optimistic fields its replies should confirm."""
    profile = profile or get_profile(model)
    if profile.command_grammar == "H6179":
        return _h6179_expectations(packet, model, static_echoes_color=static_echoes_color)
    video = parse_video_command(packet, model, profile=profile)
    if video is not None:
        detail = video.detail
        expectations = {
            "color_mode": (ParsedMode.VIDEO, None),
            "video_mode": detail.source.name,
            "video_parameters": video_parameters_from_detail(detail, profile.video_grammar),
        }
        if profile.supports_video_saturation:
            expectations["video_saturation"] = int(detail.saturation)
        if profile.supports_video_sound_effects:
            expectations["video_sound_effects"] = bool(detail.sound_effects)
            expectations["video_sound_effects_softness"] = int(detail.softness)
        return expectations
    generated = parse_command(packet, model, profile=profile)
    if generated is None:
        return {}
    operation = getattr(generated.opcode, "name", None)
    if operation is None:
        return {}
    if operation == "power":
        return {"is_on": bool(generated.body.is_on)}
    if operation == "brightness":
        return {"brightness_pct": int(generated.body.percent)}
    expectations = {}
    if color_mode := _expected_color_mode(
        generated,
        model,
        static_echoes_color=static_echoes_color,
        profile=profile,
    ):
        expectations["color_mode"] = color_mode
    if profile.command_grammar in {"H6099", "H6199"}:
        if operation != "mode":
            return expectations
        mode = getattr(generated.body.sub_mode, "name", None)
        detail = generated.body.detail
        if mode == "music":
            music_mode = music_slug_for(model, int(detail.mode))
            expectations["music_mode"] = music_mode
            expectations["music_sensitivity"] = int(detail.sensitivity)
            if not getattr(detail, "is_legacy", True):
                return expectations
            if music_mode == "rhythm":
                expectations["music_calm"] = bool(detail.is_calm)
            expectations["music_color"] = (
                (int(detail.fixed_colour.red), int(detail.fixed_colour.green), int(detail.fixed_colour.blue))
                if detail.has_fixed_colour
                else None
            )
            return expectations
        if mode == "video":
            if profile.video_grammar not in {"H6099", "H6199"}:
                return expectations
            expectations["video_mode"] = detail.source.name
            if profile.supports_video_capture_region:
                expectations["video_full_screen"] = detail.region.name == "all"
            if profile.supports_video_saturation:
                expectations["video_saturation"] = int(detail.saturation)
            if profile.supports_video_sound_effects:
                expectations["video_sound_effects"] = bool(detail.sound_effects)
                expectations["video_sound_effects_softness"] = int(detail.softness)
            return expectations
        if mode == "scene":
            scene_code = int(detail.scene_id)
            expectations["scene_code"] = scene_code
            expectations["effect"] = _SCENE_EFFECT_BY_MODEL_ID.get(model, {}).get(scene_code)
            expectations["unknown_scene_code"] = scene_code if expectations["effect"] is None else None
            return expectations
    elif operation == "multi":
        mode = getattr(generated.body.sub, "name", None)
        detail = generated.body.sub_body
        if mode == "music":
            music_mode = music_slug_for(model, int(detail.mode_id))
            expectations["music_mode"] = music_mode
            expectations["music_sensitivity"] = int(detail.sensitivity)
            if not detail.is_legacy:
                return expectations
            if music_mode == "rhythm":
                expectations["music_calm"] = bool(detail.style)
            expectations["music_color"] = (
                (int(detail.rgb.red), int(detail.rgb.green), int(detail.rgb.blue)) if detail.has_fixed_colour else None
            )
            return expectations
        if mode == "scene":
            scene_code = int(detail.code)
            expectations["scene_code"] = scene_code
            expectations["effect"] = _SCENE_EFFECT_BY_MODEL_ID.get(model, {}).get(scene_code)
            expectations["unknown_scene_code"] = scene_code if expectations["effect"] is None else None
            return expectations
    if (static := parse_static_write(packet, model, profile=profile)) and static.whole_strip:
        if static.rgb is not None:
            expectations["rgb_color"] = static.rgb
            if profile.static_readback_kelvin:
                expectations["color_temp_kelvin"] = None
        elif static.kelvin is not None:
            expectations["color_temp_kelvin"] = static.kelvin
        elif static.brightness_pct is not None:
            expectations["white_brightness"] = static.brightness_pct
    return expectations


def _h6179_expectations(
    packet: bytes,
    model: str,
    *,
    static_echoes_color: bool,
) -> dict[str, Any]:
    command = parse_h6179_command(packet)
    if command is None:
        return {}
    if command.operation == "power":
        return {"is_on": command.values["is_on"]}
    if command.operation == "brightness":
        return {"brightness_pct": command.values["brightness_pct"]}
    mode = command.values.get("mode")
    if mode == "music":
        return {
            "color_mode": (ParsedMode.MUSIC, None),
            "music_mode": command.values["music_mode"],
            "music_sensitivity": command.values["sensitivity"],
            "music_color": command.values["colour"],
        }
    if mode == "scene":
        scene_code = int(command.values["scene_code"])
        effect = scene_key_for_code(model, scene_code)
        return {
            "color_mode": (ParsedMode.SCENE, None),
            "effect": effect,
            "unknown_scene_code": scene_code if effect is None else None,
        }
    if mode == "diy":
        return {
            "color_mode": (ParsedMode.DIY, int(command.values["diy_code"])),
            "effect": None,
        }
    if mode != "static":
        return {}
    expectations: dict[str, Any] = {
        "color_mode": (
            ParsedMode.COLOUR,
            int(command.values["raw_mode"]) if static_echoes_color else None,
        ),
    }
    static = parse_static_write(packet, model)
    if static is not None and static.rgb is not None:
        expectations["rgb_color"] = static.rgb
    elif static is not None and static.kelvin is not None:
        expectations["color_temp_kelvin"] = static.kelvin
    return expectations


def _expected_color_mode(
    generated: Any,
    model: str,
    *,
    static_echoes_color: bool,
    profile: ModelProfile | None = None,
) -> tuple[ParsedMode, int | None] | None:
    profile = profile or get_profile(model)
    if profile.command_grammar == "H601C":
        return (ParsedMode.COLOUR, None) if generated.is_static else None
    if profile.command_grammar in {"H6099", "H6199"}:
        if generated.opcode.name != "mode":
            return None
        mode = getattr(generated.body.sub_mode, "name", None)
        detail = generated.body.detail
        if mode == "music":
            return ParsedMode.MUSIC, None
        if mode == "diy":
            return ParsedMode.DIY, int(detail.code)
        if mode == "video":
            return (ParsedMode.VIDEO, None) if profile.video_grammar in {"H6099", "H6199"} else None
        if mode == "scene":
            return ParsedMode.SCENE, None
        if mode == "static_colour":
            return ParsedMode.COLOUR, (int(detail.operation) if static_echoes_color else None)
        return None
    if generated.opcode.name != "multi":
        return None
    mode = getattr(generated.body.sub, "name", None)
    detail = generated.body.sub_body
    if mode == "diy":
        return ParsedMode.DIY, int(detail.code)
    if mode == "music":
        return ParsedMode.MUSIC, None
    if mode == "scene":
        return ParsedMode.SCENE, None
    if mode == "static":
        return ParsedMode.COLOUR, (int(detail.static_sub) if static_echoes_color else None)
    return None
