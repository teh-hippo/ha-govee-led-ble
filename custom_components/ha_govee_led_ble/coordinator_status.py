"""Coordinator status DTOs and semantic parsing."""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Literal, cast

from .const import (
    KELVIN_RANGE_1000_10000,
    PERCENT_BRIGHTNESS_STATUS_GRAMMARS,
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
        if effective_profile.status_grammar_has("custom_status")
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
        return profile.setting_grammar_has("device_info_status") and bool(profile.boolean_controls)
    if domain_name == "bar_enable":
        return profile.setting_grammar_has("paired_bar_settings") and bool(profile.boolean_controls)
    if domain_name == "zone_enable":
        return profile.setting_grammar_has("native_sources", "source_status") and bool(profile.light_sources)
    if domain_name == "source_info":
        return profile.setting_grammar_has("source_status") and bool(profile.boolean_controls)
    if domain_name == "power_off_memory" and profile.setting_grammar_has("paired_bar_settings"):
        return False
    if domain_name == "power_on_behaviour":
        return profile.supports_power_on_behaviour
    if decoded.domain is ReadDomain.DISPLAY_SETTING and profile.status_grammar_has("display_settings"):
        setting = getattr(decoded.generated.body.setting, "name", None)
        if setting == "sensitivity":
            return profile.supports_video_sensitivity
        if setting == "hdmi_input":
            return profile.supports_hdmi_input
        if setting == "colour_calibration":
            return profile.supports_video_color_calibration
        return setting in {"blank_screen", "black_border"}
    if decoded.domain is ReadDomain.LOW_BLUE_LIGHT:
        return profile.setting_grammar_has("low_blue_light") and profile.supports_low_blue_light
    control = boolean_control_name(domain_name)
    if control is not None:
        return boolean_control_is_authorized(control, profile)
    if decoded.domain in {ReadDomain.PHYSICAL_IC_COUNT, ReadDomain.SEGMENTS}:
        return profile.can_read(decoded.domain)
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
    static_fields: frozenset[Literal["rgb_color", "color_temp_kelvin", "static_gradual"]] | None = None
    color_temp_kelvin: int | None = None
    zero_kelvin_reported: bool = False
    color_temp_unknown: bool = False
    white_brightness: int | None = None
    multi_effect_flag: int | None = None
    left_bar_kelvin: int | None = None
    right_bar_kelvin: int | None = None
    segment_colors: tuple[tuple[int, int, int], ...] | None = None
    raw_mode: int | None = None
    source_values: dict[str, int] | None = None
    native_projector: bool = False
    gradient: int | None = None


def _readback_kelvin(reported: int) -> int:
    """Preserve observations independently of declared write bounds; reject impossible wire values."""
    if not KELVIN_RANGE_1000_10000[0] <= reported <= KELVIN_RANGE_1000_10000[1]:
        raise ValueError("Kelvin outside any device range")
    return reported


def parse_color_mode(generated: Any, model: str, *, profile: ModelProfile | None = None) -> ParsedColorModeResponse:
    profile = profile or get_profile(model)
    if profile.projector_grammar is not None:
        from .projector_protocol import projector_appearance_mode

        if (raw_mode := projector_appearance_mode(generated)) is not None:
            return ParsedColorModeResponse(
                mode=ParsedMode.COLOUR,
                raw_mode=raw_mode,
                static_fields=frozenset(),
                native_projector=True,
            )
    if profile.status_grammar_has("custom_status"):
        if not isinstance(generated, ParsedH6179Status) or generated.domain != "mode":
            return ParsedColorModeResponse()
        values = generated.values
        mode_name = values.get("mode")
        if mode_name == "static":
            if kelvin := int(values["kelvin"]):
                return ParsedColorModeResponse(
                    mode=ParsedMode.COLOUR,
                    color_temp_kelvin=_readback_kelvin(kelvin),
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
    if profile.status_grammar_has("source_status") and mode_name == "source_control":
        from .generated_protocol_adapter import source_readback

        return ParsedColorModeResponse(mode=ParsedMode.COLOUR, source_values=source_readback(detail))
    if mode_name in {"legacy_static", "legacy_colour", "whole_device_colour"}:
        mode_name = "static"
    elif mode_name in {"legacy_music", "modern_music"}:
        mode_name = "music"
    if profile.bulk_status_grammar_has("bulk_compact") and mode_name == "music":
        return ParsedColorModeResponse(mode=ParsedMode.MUSIC)
    if mode_name == "music":
        return _parse_music_mode(detail, model, profile)
    if mode_name in {"static", "static_colour"}:
        return _parse_static_mode(detail, profile)
    if mode_name == "observed_static":
        if detail is None:
            raise ValueError("RGB status has no details")
        return ParsedColorModeResponse(
            mode=ParsedMode.COLOUR, rgb_color=_rgb_values(detail.rgb), static_fields=frozenset({"rgb_color"})
        )
    if mode_name == "video":
        return _parse_video_mode(detail, profile)
    detail = body if detail is None else detail
    if mode_name == "scene":
        scene_code = int(detail.scene_id)
        return ParsedColorModeResponse(
            mode=ParsedMode.SCENE, effect=scene_key_for_code(model, scene_code, profile=profile), scene_code=scene_code
        )
    if mode_name in {"diy", "inline_diy"}:
        return ParsedColorModeResponse(
            mode=ParsedMode.DIY, diy_code=int(detail.code), diy_companion=getattr(detail, "companion", None)
        )
    return ParsedColorModeResponse()


def _rgb_values(rgb: Any) -> tuple[int, int, int]:
    return int(rgb.red), int(rgb.green), int(rgb.blue)


def _parse_music_mode(detail: Any, model: str, profile: ModelProfile) -> ParsedColorModeResponse:
    if detail is None:
        raise ValueError("Music status has no details")
    reported_sensitivity = int(detail.sensitivity)
    sensitivity = (
        reported_sensitivity
        if profile.music_sensitivity_min <= reported_sensitivity <= profile.music_sensitivity_max
        else None
    )
    if profile.status_grammar_has("native_music_status"):
        from .music_protocol import music_slug_for

        mode = music_slug_for(model, int(detail.mode), profile=profile)
        if mode not in profile.music_modes:
            raise ValueError("Invalid native music status")
        return ParsedColorModeResponse(
            mode=ParsedMode.MUSIC, music_mode=mode, music_sensitivity=sensitivity, music_color_present=False
        )
    if profile.music_readback_ambiguous:
        selector = getattr(detail.observed_selector, "name", None)
        return ParsedColorModeResponse(
            mode=ParsedMode.MUSIC,
            music_mode=selector if selector in profile.music_modes else None,
            music_sensitivity=sensitivity,
            music_color_present=False,
        )
    mode_id = detail.mode if hasattr(detail, "mode") else getattr(detail, "mode_id", -1)
    music_mode = getattr(mode_id, "name", None)
    if music_mode not in (profile.readback_music_modes or profile.music_modes):
        raise ValueError("music selector is unsupported for model")
    if hasattr(detail, "is_base"):
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
            music_sensitivity=sensitivity,
            music_calm=bool(detail.is_calm) if music_mode == "rhythm" else None,
            music_color_present=bool(detail.is_base),
            **music_values,
        )
    if not getattr(detail, "is_legacy", True):
        return ParsedColorModeResponse(
            mode=ParsedMode.MUSIC,
            music_mode=music_mode,
            music_sensitivity=sensitivity,
            music_color_present=False,
        )
    percent = profile.status_grammar in PERCENT_BRIGHTNESS_STATUS_GRAMMARS or profile.status_grammar_has(
        "percent_brightness"
    )
    colour = None
    if getattr(detail, "has_fixed_colour", False):
        colour = detail.fixed_colour if percent else detail.rgb
    style = getattr(detail, "is_calm" if percent else "style", None)
    return ParsedColorModeResponse(
        mode=ParsedMode.MUSIC,
        music_mode=music_mode,
        music_sensitivity=sensitivity,
        music_calm=bool(style) if music_mode == "rhythm" and style is not None else None,
        music_color=_rgb_values(colour) if colour is not None else None,
    )


def _parse_static_mode(detail: Any, profile: ModelProfile) -> ParsedColorModeResponse:
    if profile.status_grammar_has("source_only_static"):
        return ParsedColorModeResponse(mode=ParsedMode.COLOUR)
    if detail is None:
        raise ValueError("Static status has no details")
    sources = getattr(detail, "sources", None)
    if sources is not None:
        if len(sources) != len(profile.light_sources):
            raise ValueError("Static source count does not match the profile")
        colours: dict[int, tuple[int, int, int]] = {}
        temperatures = []
        for source, record in zip(profile.light_sources, sources, strict=True):
            temperatures.append(_readback_kelvin(int(record.kelvin)) if record.kelvin else 0)
            colours.update((index, _rgb_values(record.colour)) for index in source.segments)
        if set(colours) != set(range(1, profile.segment_count + 1)) or len(temperatures) != 2:
            raise ValueError("Static source colours do not cover the current geometry")
        left, right = temperatures
        return ParsedColorModeResponse(
            mode=ParsedMode.COLOUR,
            color_temp_kelvin=left if left == right and left else None,
            left_bar_kelvin=left,
            right_bar_kelvin=right,
            segment_colors=tuple(colours[index] for index in range(1, profile.segment_count + 1)),
        )
    if hasattr(detail, "left_kelvin") and hasattr(detail, "right_kelvin"):
        left, right = (
            _readback_kelvin(value) if value else 0 for value in (int(detail.left_kelvin), int(detail.right_kelvin))
        )
        return ParsedColorModeResponse(
            mode=ParsedMode.COLOUR,
            color_temp_kelvin=left if left == right and left else None,
            left_bar_kelvin=left,
            right_bar_kelvin=right,
        )
    if hasattr(detail, "temperature_flag"):
        if detail.temperature_flag not in (0, 1):
            raise ValueError("Invalid legacy colour-temperature flag")
        if detail.temperature_flag:
            companion = _rgb_values(detail.companion_rgb)
            if companion == (0, 0, 0):
                return ParsedColorModeResponse(mode=ParsedMode.COLOUR, color_temp_unknown=True)
            kelvin = table_rgb_kelvin(companion)
            if kelvin is None or not profile.min_color_temp_kelvin <= kelvin <= profile.max_color_temp_kelvin:
                raise ValueError("Unrecognised legacy colour-temperature companion")
            return ParsedColorModeResponse(mode=ParsedMode.COLOUR, color_temp_kelvin=kelvin)
        return ParsedColorModeResponse(mode=ParsedMode.COLOUR, rgb_color=_rgb_values(detail.rgb))
    reported = getattr(detail, "kelvin", None)
    kelvin = _readback_kelvin(int(reported)) if reported else None
    rgb = getattr(detail, "rgb", None)
    return ParsedColorModeResponse(
        mode=ParsedMode.COLOUR,
        rgb_color=_rgb_values(rgb)
        if rgb is not None and not (profile.static_readback_kelvin_suppresses_rgb and kelvin is not None)
        else None,
        color_temp_kelvin=kelvin,
        zero_kelvin_reported=reported == 0,
        multi_effect_flag=getattr(detail, "sub", None),
        gradient=int(detail.gradient)
        if profile.status_grammar_has("gradient_status") and detail.gradient in (0, 1)
        else None,
    )


def _parse_video_mode(detail: Any, profile: ModelProfile) -> ParsedColorModeResponse:
    if not profile.video_modes:
        return ParsedColorModeResponse()
    source = getattr(detail.source, "name", None)
    if source not in profile.video_modes:
        return ParsedColorModeResponse()
    full_screen = None
    if profile.video_grammar_has("video_picture_preset"):
        if detail.sound_effects not in (0, 1) or not 0 <= detail.softness <= 100:
            raise ValueError("invalid video sound effects or softness")
    else:
        region = getattr(detail.region, "name", None)
        if region not in {"part", "all"}:
            return ParsedColorModeResponse()
        if profile.supports_video_capture_region:
            full_screen = region == "all"
        if detail.sound_effects not in (0, 1) or (
            profile.video_softness_min == 0
            and not profile.video_softness_min <= detail.softness <= profile.video_softness_max
        ):
            raise ValueError("invalid video sound effects or softness")
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
