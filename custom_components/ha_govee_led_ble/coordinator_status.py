"""Coordinator status DTOs and semantic parsing."""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, cast

from .const import (
    KELVIN_RANGE_1000_10000,
    PERCENT_BRIGHTNESS_STATUS_GRAMMARS,
    VIDEO_GRAMMARS,
    WHOLE_BULB_GRAMMARS,
    ModelProfile,
    ReadDomain,
    get_profile,
)
from .generated_protocol_adapter import (
    boolean_control_is_authorized,
    boolean_control_name,
    parse_status_result,
    table_rgb_kelvin,
    video_parameters_from_detail,
)
from .light_commands import normalize_kelvin
from .protocol_core import ProtocolParseResult
from .protocol_h6179 import ParsedH6179Status, parse_h6179_status_result
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
    "pact": StatusDomain.PACT,
    "subordinate_20": StatusDomain.SUBORDINATE_20,
    "subordinate_21": StatusDomain.SUBORDINATE_21,
    "display_setting": StatusDomain.DISPLAY_SETTING,
    "relative_brightness": StatusDomain.RELATIVE_BRIGHTNESS,
    "segments": StatusDomain.SEGMENTS,
    "legacy_segments": StatusDomain.SEGMENTS,
    "configured_strings": StatusDomain.CONFIGURED_STRINGS,
    "physical_ic_count": StatusDomain.PHYSICAL_IC_COUNT,
    "installation_direction": StatusDomain.INSTALLATION_DIRECTION,
    "camera_health": StatusDomain.CAMERA_HEALTH,
    "low_blue_light": StatusDomain.LOW_BLUE_LIGHT,
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
    domain = decoded.generated.domain
    domain_name = domain if isinstance(domain, str) else getattr(domain, "name", "")
    if getattr(decoded.generated, "is_device_info", False):
        return profile.setting_grammar == "H607C" and bool(profile.boolean_controls)
    if domain_name == "bar_enable":
        return profile.setting_grammar == "H6046" and bool(profile.boolean_controls)
    if domain_name == "zone_enable":
        return profile.setting_grammar == "H60B2" and bool(profile.light_sources)
    if domain_name == "source_info":
        return profile.setting_grammar == "H60B0" and bool(profile.boolean_controls)
    if domain_name == "power_off_memory" and profile.setting_grammar == "H6046":
        return False
    if domain_name == "power_on_behaviour":
        return profile.supports_power_on_behaviour
    if decoded.domain is ReadDomain.LOW_BLUE_LIGHT:
        return profile.setting_grammar == "H6072" and profile.supports_low_blue_light
    control = boolean_control_name(domain_name)
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
    diy_companion: int | None = None
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
    music_fixed_colour: bool | None = None
    music_left_colour: int | None = None
    music_right_colour: int | None = None
    rgb_color: tuple[int, int, int] | None = None
    color_temp_kelvin: int | None = None
    white_brightness: int | None = None
    multi_effect_flag: int | None = None
    left_bar_kelvin: int | None = None
    right_bar_kelvin: int | None = None
    raw_mode: int | None = None
    source_values: dict[str, int] | None = None
    gradient: int | None = None


def _readback_kelvin(reported: int, profile: ModelProfile) -> int:
    """Zero means no Kelvin; a value no device range contains is not a Kelvin reading, so it rejects the frame."""
    if not KELVIN_RANGE_1000_10000[0] <= reported <= KELVIN_RANGE_1000_10000[1]:
        raise ValueError("Kelvin outside any device range")
    return normalize_kelvin(reported, profile)


def parse_color_mode(generated: Any, model: str, *, profile: ModelProfile | None = None) -> ParsedColorModeResponse:
    profile = profile or get_profile(model)
    if profile.status_grammar == "H6179":
        if not isinstance(generated, ParsedH6179Status) or generated.domain != "mode":
            return ParsedColorModeResponse()
        values = generated.values
        mode_name = values.get("mode")
        if mode_name == "static":
            if kelvin := int(values["kelvin"]):
                return ParsedColorModeResponse(
                    mode=ParsedMode.COLOUR,
                    color_temp_kelvin=_readback_kelvin(kelvin, profile),
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
    detail = getattr(body, "detail", None)
    if detail is None:
        detail = getattr(body, "mode_body", None)
    if profile.status_grammar == "H60B0" and mode_name == "source_control":
        from .h60b0_controls import source_readback

        return ParsedColorModeResponse(mode=ParsedMode.COLOUR, source_values=source_readback(detail, profile))
    if mode_name in {"legacy_static", "legacy_colour", "whole_device_colour"}:
        mode_name = "static"
    elif mode_name == "legacy_music":
        mode_name = "music"
    if profile.bulk_status_grammar == "H60A" and mode_name == "music":
        return ParsedColorModeResponse(mode=ParsedMode.MUSIC)
    if mode_name == "music":
        return _parse_music_mode(detail, model, profile)
    if mode_name in {"static", "static_colour"}:
        return _parse_static_mode(detail, profile)
    if mode_name == "video":
        return _parse_video_mode(detail, profile)
    detail = body if detail is None else detail
    if mode_name == "scene":
        scene_code = int(detail.scene_id)
        return ParsedColorModeResponse(
            mode=ParsedMode.SCENE, effect=scene_key_for_code(model, scene_code, profile=profile), scene_code=scene_code
        )
    if mode_name == "diy":
        return ParsedColorModeResponse(
            mode=ParsedMode.DIY, diy_code=int(detail.code), diy_companion=getattr(detail, "companion", None)
        )
    return ParsedColorModeResponse()


def _rgb_values(rgb: Any) -> tuple[int, int, int]:
    return int(rgb.red), int(rgb.green), int(rgb.blue)


def _parse_music_mode(detail: Any, model: str, profile: ModelProfile) -> ParsedColorModeResponse:
    if detail is None:
        raise ValueError("Music status has no details")
    if profile.status_grammar == "H60B0":
        from .music_protocol import music_slug_for

        mode = music_slug_for(model, int(detail.mode), profile=profile)
        if mode not in profile.music_modes or not 0 <= detail.sensitivity <= 100:
            raise ValueError("Invalid native music status")
        return ParsedColorModeResponse(
            mode=ParsedMode.MUSIC, music_mode=mode, music_sensitivity=int(detail.sensitivity), music_color_present=False
        )
    if profile.music_readback_ambiguous:
        selector = getattr(detail.observed_selector, "name", None)
        sensitivity = int(detail.sensitivity)
        return ParsedColorModeResponse(
            mode=ParsedMode.MUSIC,
            music_mode=selector if selector in profile.music_modes else None,
            music_sensitivity=sensitivity
            if profile.music_sensitivity_min <= sensitivity <= profile.music_sensitivity_max
            else None,
            music_color_present=False,
        )
    mode_id = detail.mode if hasattr(detail, "mode") else getattr(detail, "mode_id", -1)
    music_mode = getattr(mode_id, "name", None)
    if music_mode not in (profile.readback_music_modes or profile.music_modes):
        raise ValueError("music selector is unsupported for model")
    if profile.status_grammar == "H6046":
        music_values: dict[str, Any] = {}
        if detail.is_base:
            music_values["music_fixed_colour"] = bool(detail.has_fixed_colour)
            for bar in ("left", "right"):
                red, green, blue = _rgb_values(getattr(detail, f"{bar}_colour"))
                music_values[f"music_{bar}_colour"] = (red << 16) | (green << 8) | blue
            if detail.has_fixed_colour and music_values["music_left_colour"] == music_values["music_right_colour"]:
                music_values["music_color"] = _rgb_values(detail.left_colour)
        return ParsedColorModeResponse(
            mode=ParsedMode.MUSIC,
            music_mode=music_mode,
            music_sensitivity=int(detail.sensitivity),
            music_calm=bool(detail.is_calm) if music_mode == "rhythm" else None,
            music_color_present=bool(detail.is_base),
            **music_values,
        )
    if not getattr(detail, "is_legacy", True):
        return ParsedColorModeResponse(
            mode=ParsedMode.MUSIC,
            music_mode=music_mode,
            music_sensitivity=int(detail.sensitivity),
            music_color_present=False,
        )
    percent = profile.status_grammar in PERCENT_BRIGHTNESS_STATUS_GRAMMARS | {"H605C"}
    colour = None
    if detail.has_fixed_colour:
        colour = detail.fixed_colour if percent else detail.rgb
    style = getattr(detail, "is_calm" if percent else "style", None)
    return ParsedColorModeResponse(
        mode=ParsedMode.MUSIC,
        music_mode=music_mode,
        music_sensitivity=int(detail.sensitivity),
        music_calm=bool(style) if music_mode == "rhythm" and style is not None else None,
        music_color=_rgb_values(colour) if colour is not None else None,
    )


def _parse_static_mode(detail: Any, profile: ModelProfile) -> ParsedColorModeResponse:
    if profile.status_grammar == "H605C":
        return ParsedColorModeResponse(mode=ParsedMode.COLOUR)
    if detail is None:
        raise ValueError("Static status has no details")
    if profile.status_grammar == "H6046":
        left, right = (
            _readback_kelvin(value, profile) if value else 0
            for value in (int(detail.left_kelvin), int(detail.right_kelvin))
        )
        return ParsedColorModeResponse(
            mode=ParsedMode.COLOUR,
            color_temp_kelvin=left if left == right and left else None,
            left_bar_kelvin=left,
            right_bar_kelvin=right,
        )
    if profile.status_grammar == "H6181":
        if detail.temperature_flag not in (0, 1):
            raise ValueError("Invalid legacy colour-temperature flag")
        if detail.temperature_flag:
            kelvin = table_rgb_kelvin(_rgb_values(detail.companion_rgb))
            if kelvin is None or not profile.min_color_temp_kelvin <= kelvin <= profile.max_color_temp_kelvin:
                raise ValueError("Unrecognised legacy colour-temperature companion")
            return ParsedColorModeResponse(mode=ParsedMode.COLOUR, color_temp_kelvin=kelvin)
        return ParsedColorModeResponse(mode=ParsedMode.COLOUR, rgb_color=_rgb_values(detail.rgb))
    reported = getattr(detail, "kelvin", None)
    kelvin = _readback_kelvin(int(reported), profile) if reported else None
    rgb = getattr(detail, "rgb", None)
    return ParsedColorModeResponse(
        mode=ParsedMode.COLOUR,
        rgb_color=_rgb_values(rgb)
        if rgb is not None
        and not (profile.status_grammar in WHOLE_BULB_GRAMMARS | {"H6181-modern", "H60B0"} and kelvin is not None)
        else None,
        color_temp_kelvin=kelvin,
        multi_effect_flag=getattr(detail, "sub", None),
        gradient=int(detail.gradient) if profile.status_grammar == "H6199" and detail.gradient in (0, 1) else None,
    )


def _parse_video_mode(detail: Any, profile: ModelProfile) -> ParsedColorModeResponse:
    if profile.video_grammar not in VIDEO_GRAMMARS | {"H605C-video", "H66A0-video"}:
        return ParsedColorModeResponse()
    source = getattr(detail.source, "name", None)
    if source not in profile.video_modes:
        return ParsedColorModeResponse()
    full_screen = None
    if profile.video_grammar == "H66A0-video":
        if detail.sound_effects not in (0, 1) or not 0 <= detail.softness <= 100:
            raise ValueError("invalid video sound effects or softness")
    else:
        region = getattr(detail.region, "name", None)
        if region not in {"part", "all"}:
            return ParsedColorModeResponse()
        if profile.supports_video_capture_region:
            full_screen = region == "all"
    return ParsedColorModeResponse(
        mode=ParsedMode.VIDEO,
        video_mode=source,
        video_parameters=video_parameters_from_detail(detail, profile.video_grammar),
        video_full_screen=full_screen,
        video_saturation=int(detail.saturation)
        if profile.supports_video_saturation and profile.video_saturation_min <= detail.saturation <= 100
        else None,
        video_sound_effects=bool(detail.sound_effects) if profile.supports_video_sound_effects else None,
        video_sound_effects_softness=int(detail.softness) if profile.supports_video_sound_effects else None,
    )
