"""Coordinator status DTOs and semantic parsing."""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, cast

from .const import PERCENT_BRIGHTNESS_STATUS_GRAMMARS, VIDEO_GRAMMARS, ModelProfile, ReadDomain, get_profile
from .generated_protocol_adapter import (
    ParsedH6179Status,
    ProtocolParseResult,
    boolean_control_is_authorized,
    boolean_control_name,
    parse_h6179_status_result,
    parse_status_result,
    video_parameters_from_detail,
)
from .scenes import scene_key_for_code

StatusDomain = ReadDomain


_STATUS_DOMAIN_NAMES = {
    "power": StatusDomain.POWER,
    "brightness": StatusDomain.BRIGHTNESS,
    "colormode": StatusDomain.COLOUR_MODE,
    "colour_mode": StatusDomain.COLOUR_MODE,
    "mode": StatusDomain.MODE,
    "fw_version": StatusDomain.FIRMWARE,
    "firmware": StatusDomain.FIRMWARE,
    "hw_version": StatusDomain.HARDWARE,
    "hardware": StatusDomain.HARDWARE,
    "subordinate_20": StatusDomain.SUBORDINATE_20,
    "subordinate_21": StatusDomain.SUBORDINATE_21,
    "display_setting": StatusDomain.DISPLAY_SETTING,
    "relative_brightness": StatusDomain.RELATIVE_BRIGHTNESS,
    "segments": StatusDomain.SEGMENTS,
    "configured_strings": StatusDomain.CONFIGURED_STRINGS,
    "physical_ic_count": StatusDomain.PHYSICAL_IC_COUNT,
    "installation_direction": StatusDomain.INSTALLATION_DIRECTION,
    "camera_health": StatusDomain.CAMERA_HEALTH,
}


@dataclass(frozen=True, slots=True)
class ParsedStatusEnvelope:
    domain: StatusDomain
    raw_domain: int
    payload: bytes
    generated: Any


def decode_status_frame_result(
    frame: bytes, model: str = "H617A", *, profile: ModelProfile | None = None
) -> ProtocolParseResult:
    effective_profile = profile or get_profile(model)
    result = (
        parse_h6179_status_result(frame)
        if effective_profile.status_grammar == "H6179"
        else parse_status_result(frame, model, profile=effective_profile)
    )
    if result.parsed is None:
        return result
    generated = result.parsed
    domain = generated.domain
    domain_name = domain if isinstance(domain, str) else getattr(domain, "name", "")
    return ProtocolParseResult(
        ParsedStatusEnvelope(
            domain=_STATUS_DOMAIN_NAMES.get(domain_name, StatusDomain.OTHER),
            raw_domain=frame[1],
            payload=bytes(frame[2:-1]),
            generated=generated,
        ),
        result.parser,
        None,
    )


def decode_status_frame(
    frame: bytes, model: str = "H617A", *, profile: ModelProfile | None = None
) -> ParsedStatusEnvelope | None:
    """Parse one fixed-size status notification with its model-specific Kaitai class."""
    return cast(ParsedStatusEnvelope | None, decode_status_frame_result(frame, model, profile=profile).parsed)


def status_is_authorized(decoded: ParsedStatusEnvelope, profile: ModelProfile) -> bool:
    """Boolean registers have independent authorization, not the catch-all OTHER domain."""
    control = boolean_control_name(getattr(decoded.generated.domain, "name", ""))
    if control is not None:
        return boolean_control_is_authorized(control, profile)
    if decoded.domain is ReadDomain.PHYSICAL_IC_COUNT:
        return profile.can_read(ReadDomain.PHYSICAL_IC_COUNT)
    return profile.command_operations is None or profile.can_read(decoded.domain)


class ParsedMode(Enum):
    """Operating mode from a colour-mode reply."""

    UNKNOWN = auto()
    COLOUR = auto()
    SCENE = auto()
    DIY = auto()
    MUSIC = auto()
    VIDEO = auto()


@dataclass(frozen=True)
class ParsedColorModeResponse:
    mode: ParsedMode = ParsedMode.UNKNOWN
    effect: str | None = None
    scene_code: int | None = None
    diy_code: int | None = None
    music_mode: str | None = None
    video_mode: str | None = None
    video_parameters: dict[str, Any] | None = None
    video_full_screen: bool | None = None
    video_saturation: int | None = None
    video_sound_effects: bool | None = None
    video_sound_effects_softness: int | None = None
    music_sensitivity: int | None = None
    music_calm: bool | None = None
    music_color: tuple[int, int, int] | None = None
    music_color_present: bool = True
    rgb_color: tuple[int, int, int] | None = None
    color_temp_kelvin: int | None = None
    white_brightness: int | None = None
    multi_effect_flag: int | None = None
    raw_mode: int | None = None


def parse_color_mode(generated: Any, model: str, *, profile: ModelProfile | None = None) -> ParsedColorModeResponse:
    profile = profile or get_profile(model)
    if profile.status_grammar == "H6179":
        if not isinstance(generated, ParsedH6179Status) or generated.domain != "mode":
            return ParsedColorModeResponse()
        values = generated.values
        mode_name = values.get("mode")
        if mode_name == "static":
            kelvin = int(values["kelvin"])
            if kelvin:
                return ParsedColorModeResponse(
                    mode=ParsedMode.COLOUR,
                    color_temp_kelvin=kelvin,
                    raw_mode=int(values["raw_mode"]),
                )
            red, green, blue = values["rgb"]
            return ParsedColorModeResponse(
                mode=ParsedMode.COLOUR,
                rgb_color=(int(red), int(green), int(blue)),
                raw_mode=int(values["raw_mode"]),
            )
        if mode_name == "scene":
            scene_code = int(values["scene_code"])
            return ParsedColorModeResponse(
                mode=ParsedMode.SCENE,
                effect=scene_key_for_code(model, scene_code, profile=profile),
                scene_code=scene_code,
            )
        if mode_name == "diy":
            return ParsedColorModeResponse(mode=ParsedMode.DIY, diy_code=int(values["diy_code"]))
        if mode_name == "music":
            music_mode = values["music_mode"]
            if music_mode not in profile.music_modes:
                raise ValueError("music selector is unsupported for model")
            colour = values["colour"]
            music_color = None
            if colour is not None:
                red, green, blue = colour
                music_color = (int(red), int(green), int(blue))
            return ParsedColorModeResponse(
                mode=ParsedMode.MUSIC,
                music_mode=music_mode,
                music_sensitivity=int(values["sensitivity"]),
                music_color=music_color,
            )
        return ParsedColorModeResponse()

    body = generated.body
    mode_name = getattr(body.mode, "name", None)
    if profile.bulk_status_grammar == "H60A" and mode_name == "music":
        return ParsedColorModeResponse(mode=ParsedMode.MUSIC)
    if mode_name == "video" and profile.video_grammar == "H66A0-video":
        detail = body.detail
        source = getattr(detail.source, "name", None)
        if source not in profile.video_modes:
            return ParsedColorModeResponse()
        parameters = video_parameters_from_detail(detail, profile.video_grammar)
        if detail.sound_effects not in (0, 1) or not 0 <= detail.softness <= 100:
            raise ValueError("invalid video sound effects or softness")
        return ParsedColorModeResponse(
            mode=ParsedMode.VIDEO,
            video_mode=source,
            video_parameters=parameters,
            video_saturation=int(detail.saturation)
            if profile.supports_video_saturation and profile.video_saturation_min <= detail.saturation <= 100
            else None,
            video_sound_effects=bool(detail.sound_effects) if profile.supports_video_sound_effects else None,
            video_sound_effects_softness=int(detail.softness) if profile.supports_video_sound_effects else None,
        )
    music_mode = None
    if mode_name == "music":
        detail = getattr(body, "detail", getattr(body, "mode_body", None))
        mode_id = getattr(detail, "mode", getattr(detail, "mode_id", -1))
        music_mode = getattr(mode_id, "name", None)
        if music_mode not in (profile.readback_music_modes or profile.music_modes):
            raise ValueError("music selector is unsupported for model")
    if mode_name in {"static", "static_colour"}:
        detail = getattr(body, "mode_body", getattr(body, "detail", None))
        rgb = getattr(detail, "rgb", None)
        raw_kelvin = getattr(detail, "kelvin", None) or None
        min_kelvin = profile.readback_min_color_temp_kelvin or profile.min_color_temp_kelvin
        if raw_kelvin is not None and not min_kelvin <= int(raw_kelvin) <= profile.max_color_temp_kelvin:
            raise ValueError("static Kelvin outside profile range")
        return ParsedColorModeResponse(
            mode=ParsedMode.COLOUR,
            rgb_color=(int(rgb.red), int(rgb.green), int(rgb.blue))
            if rgb is not None and not (profile.status_grammar == "H601C" and raw_kelvin is not None)
            else None,
            color_temp_kelvin=int(raw_kelvin) if raw_kelvin is not None else None,
            multi_effect_flag=getattr(detail, "sub", None),
        )
    if profile.status_grammar in PERCENT_BRIGHTNESS_STATUS_GRAMMARS or (
        mode_name == "video" and profile.video_grammar in VIDEO_GRAMMARS
    ):
        if mode_name == "video":
            if profile.video_grammar not in VIDEO_GRAMMARS:
                return ParsedColorModeResponse()
            detail = body.detail
            source_name = getattr(detail.source, "name", None)
            region_name = getattr(detail.region, "name", None)
            if source_name not in profile.video_modes or region_name not in {"part", "all"}:
                return ParsedColorModeResponse()
            return ParsedColorModeResponse(
                mode=ParsedMode.VIDEO,
                video_mode=source_name,
                video_full_screen=region_name == "all" if profile.supports_video_capture_region else None,
                # Keep sibling video observations when firmware reports an unqualified saturation.
                video_saturation=(
                    int(detail.saturation)
                    if profile.supports_video_saturation and profile.video_saturation_min <= detail.saturation <= 100
                    else None
                ),
                video_sound_effects=bool(detail.sound_effects) if profile.supports_video_sound_effects else None,
                video_sound_effects_softness=int(detail.softness) if profile.supports_video_sound_effects else None,
            )
        if mode_name == "music":
            detail = body.detail
            if not getattr(detail, "is_legacy", True):
                return ParsedColorModeResponse(
                    mode=ParsedMode.MUSIC,
                    music_mode=music_mode,
                    music_sensitivity=int(detail.sensitivity),
                    music_color_present=False,
                )
            fixed_colour = None
            if detail.has_fixed_colour:
                fixed_colour = (
                    int(detail.fixed_colour.red),
                    int(detail.fixed_colour.green),
                    int(detail.fixed_colour.blue),
                )
            return ParsedColorModeResponse(
                mode=ParsedMode.MUSIC,
                music_mode=music_mode,
                music_sensitivity=int(detail.sensitivity),
                music_calm=bool(detail.is_calm) if music_mode == "rhythm" else None,
                music_color=fixed_colour,
            )
        if mode_name == "scene":
            scene_code = int(body.detail.scene_id)
            return ParsedColorModeResponse(
                mode=ParsedMode.SCENE,
                effect=scene_key_for_code(model, scene_code, profile=profile),
                scene_code=scene_code,
            )
        if mode_name == "diy":
            return ParsedColorModeResponse(mode=ParsedMode.DIY, diy_code=int(body.detail.code))
        return ParsedColorModeResponse()

    if mode_name == "scene":
        detail = getattr(body, "mode_body", getattr(body, "detail", body))
        scene_code = int(detail.scene_id)
        return ParsedColorModeResponse(
            mode=ParsedMode.SCENE,
            effect=scene_key_for_code(model, scene_code, profile=profile),
            scene_code=scene_code,
        )
    if mode_name == "diy":
        detail = getattr(body, "mode_body", getattr(body, "detail", body))
        return ParsedColorModeResponse(mode=ParsedMode.DIY, diy_code=int(detail.code))
    if mode_name == "music":
        detail = body.mode_body
        if not getattr(detail, "is_legacy", True):
            return ParsedColorModeResponse(
                mode=ParsedMode.MUSIC,
                music_mode=music_mode,
                music_sensitivity=int(detail.sensitivity),
                music_color_present=False,
            )
        music_color = None
        if detail.has_fixed_colour:
            music_color = (int(detail.rgb.red), int(detail.rgb.green), int(detail.rgb.blue))
        return ParsedColorModeResponse(
            mode=ParsedMode.MUSIC,
            music_mode=music_mode,
            music_sensitivity=int(detail.sensitivity),
            music_calm=bool(detail.style) if music_mode == "rhythm" and hasattr(detail, "style") else None,
            music_color=music_color,
        )
    return ParsedColorModeResponse()
