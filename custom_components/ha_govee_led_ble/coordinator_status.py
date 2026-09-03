"""Coordinator status DTOs and semantic parsing."""

from dataclasses import dataclass
from enum import Enum, StrEnum, auto
from types import MappingProxyType
from typing import Any, cast

from .const import wire_model
from .generated_protocol_adapter import (
    ParsedH6179Status,
    ProtocolParseResult,
    parse_h6179_status_result,
    parse_status_result,
)
from .music_protocol import music_slug_for
from .scenes import scene_key_for_code


def _music_slug(model: str, mode_id: int) -> str | None:
    return music_slug_for(wire_model(model) or model, mode_id)


class StatusDomain(Enum):
    POWER = auto()
    BRIGHTNESS = auto()
    COLOUR_MODE = auto()
    FIRMWARE = auto()
    HARDWARE = auto()
    SUBORDINATE_20 = auto()
    SUBORDINATE_21 = auto()
    DISPLAY_SETTING = auto()
    RELATIVE_BRIGHTNESS = auto()
    SEGMENTS = auto()
    OTHER = auto()


_STATUS_DOMAIN_NAMES = {
    "power": StatusDomain.POWER,
    "brightness": StatusDomain.BRIGHTNESS,
    "colormode": StatusDomain.COLOUR_MODE,
    "colour_mode": StatusDomain.COLOUR_MODE,
    "mode": StatusDomain.COLOUR_MODE,
    "fw_version": StatusDomain.FIRMWARE,
    "firmware": StatusDomain.FIRMWARE,
    "hw_version": StatusDomain.HARDWARE,
    "hardware": StatusDomain.HARDWARE,
    "subordinate_20": StatusDomain.SUBORDINATE_20,
    "subordinate_21": StatusDomain.SUBORDINATE_21,
    "display_setting": StatusDomain.DISPLAY_SETTING,
    "relative_brightness": StatusDomain.RELATIVE_BRIGHTNESS,
    "segments": StatusDomain.SEGMENTS,
}


@dataclass(frozen=True, slots=True)
class ParsedStatusEnvelope:
    domain: StatusDomain
    raw_domain: int
    payload: bytes
    generated: Any


def decode_status_frame_result(frame: bytes, model: str = "H617A") -> ProtocolParseResult:
    result = parse_h6179_status_result(frame) if wire_model(model) == "H6179" else parse_status_result(frame, model)
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


def decode_status_frame(frame: bytes, model: str = "H617A") -> ParsedStatusEnvelope | None:
    """Parse one fixed-size status notification with its model-specific Kaitai class."""
    return cast(ParsedStatusEnvelope | None, decode_status_frame_result(frame, model).parsed)


class ParsedMode(Enum):
    """Operating mode from a colour-mode reply."""

    UNKNOWN = auto()
    COLOUR = auto()
    SCENE = auto()
    DIY = auto()
    MUSIC = auto()
    VIDEO = auto()


class FieldAuthority(StrEnum):
    """Authority of a coordinator field value."""

    AUTHORITATIVE = "authoritative"
    OPTIMISTIC = "optimistic"
    PROVISIONAL = "provisional"


H6179_STATUS_FIELD_AUTHORITY = MappingProxyType(
    {
        "is_on": FieldAuthority.AUTHORITATIVE,
        "brightness_pct": FieldAuthority.AUTHORITATIVE,
        "fw_version": FieldAuthority.AUTHORITATIVE,
        "hw_version": FieldAuthority.AUTHORITATIVE,
        "color_mode": FieldAuthority.PROVISIONAL,
        "rgb_color": FieldAuthority.PROVISIONAL,
        "color_temp_kelvin": FieldAuthority.PROVISIONAL,
        "effect": FieldAuthority.PROVISIONAL,
        "unknown_scene_code": FieldAuthority.PROVISIONAL,
        "diy_code": FieldAuthority.PROVISIONAL,
        "music_mode": FieldAuthority.PROVISIONAL,
        "music_mode_id": FieldAuthority.PROVISIONAL,
        "music_sensitivity": FieldAuthority.PROVISIONAL,
        "music_color": FieldAuthority.PROVISIONAL,
    }
)
H6179_WRITE_FIELD_AUTHORITY = MappingProxyType(
    {
        "is_on": FieldAuthority.OPTIMISTIC,
        "brightness_pct": FieldAuthority.OPTIMISTIC,
        "color_mode": FieldAuthority.OPTIMISTIC,
        "rgb_color": FieldAuthority.OPTIMISTIC,
        "color_temp_kelvin": FieldAuthority.OPTIMISTIC,
    }
)


@dataclass(frozen=True)
class ParsedColorModeResponse:
    mode: ParsedMode = ParsedMode.UNKNOWN
    effect: str | None = None
    scene_code: int | None = None
    diy_code: int | None = None
    music_mode: str | None = None
    music_mode_id: int | None = None
    video_mode: str | None = None
    video_full_screen: bool | None = None
    video_saturation: int | None = None
    video_sound_effects: bool | None = None
    video_sound_effects_softness: int | None = None
    music_sensitivity: int | None = None
    music_calm: bool | None = None
    music_color: tuple[int, int, int] | None = None
    rgb_color: tuple[int, int, int] | None = None
    color_temp_kelvin: int | None = None
    white_brightness: int | None = None
    multi_effect_flag: int | None = None
    raw_mode: int | None = None
    opaque: bytes | None = None


def _parse_h6179_color_mode(status: ParsedH6179Status) -> ParsedColorModeResponse:
    if status.domain != "mode":
        return ParsedColorModeResponse()
    values = status.values
    mode_name = values.get("mode")
    if mode_name == "static":
        kelvin = int(values["kelvin"])
        if kelvin:
            return ParsedColorModeResponse(
                mode=ParsedMode.COLOUR,
                color_temp_kelvin=kelvin,
            )
        red, green, blue = values["rgb"]
        return ParsedColorModeResponse(
            mode=ParsedMode.COLOUR,
            rgb_color=(int(red), int(green), int(blue)),
        )
    if mode_name == "scene":
        scene_code = int(values["scene_code"])
        return ParsedColorModeResponse(
            mode=ParsedMode.SCENE,
            effect=scene_key_for_code("H6179", scene_code),
            scene_code=scene_code,
        )
    if mode_name == "diy":
        return ParsedColorModeResponse(
            mode=ParsedMode.DIY,
            diy_code=int(values["diy_code"]),
        )
    if mode_name == "music":
        mode_id = int(values["music_mode_id"])
        colour = values["colour"]
        music_color = None
        if colour is not None:
            red, green, blue = colour
            music_color = (int(red), int(green), int(blue))
        return ParsedColorModeResponse(
            mode=ParsedMode.MUSIC,
            music_mode=_music_slug("H6179", mode_id),
            music_mode_id=mode_id,
            music_sensitivity=int(values["sensitivity"]),
            music_color=music_color,
        )
    return ParsedColorModeResponse(
        raw_mode=int(values["raw_mode"]),
        opaque=bytes(values["opaque"]),
    )


def parse_color_mode(generated: Any, model: str) -> ParsedColorModeResponse:
    if model == "H6179":
        if not isinstance(generated, ParsedH6179Status):
            return ParsedColorModeResponse()
        return _parse_h6179_color_mode(generated)
    body = generated.body
    mode_name = getattr(body.mode, "name", None)
    if model == "H6199":
        if mode_name == "video":
            detail = body.detail
            source_name = getattr(detail.source, "name", None)
            region_name = getattr(detail.region, "name", None)
            if source_name not in {"movie", "game"} or region_name not in {"part", "all"}:
                return ParsedColorModeResponse()
            return ParsedColorModeResponse(
                mode=ParsedMode.VIDEO,
                video_mode=source_name,
                video_full_screen=region_name == "all",
                video_saturation=int(detail.saturation),
                video_sound_effects=bool(detail.sound_effects),
                video_sound_effects_softness=int(detail.softness),
            )
        if mode_name == "music":
            detail = body.detail
            mode_id = int(detail.mode)
            fixed_colour = None
            if detail.has_fixed_colour:
                fixed_colour = (
                    int(detail.fixed_colour.red),
                    int(detail.fixed_colour.green),
                    int(detail.fixed_colour.blue),
                )
            return ParsedColorModeResponse(
                mode=ParsedMode.MUSIC,
                music_mode=_music_slug(model, mode_id),
                music_mode_id=mode_id,
                music_sensitivity=int(detail.sensitivity),
                music_calm=bool(detail.is_calm),
                music_color=fixed_colour,
            )
        if mode_name == "scene":
            scene_code = int(body.detail.scene_id)
            return ParsedColorModeResponse(
                mode=ParsedMode.SCENE,
                effect=scene_key_for_code("H6199", scene_code),
                scene_code=scene_code,
            )
        if mode_name == "static_colour":
            return ParsedColorModeResponse(mode=ParsedMode.COLOUR)
        return ParsedColorModeResponse()

    if mode_name == "scene":
        scene_code = int(body.mode_body.scene_id)
        return ParsedColorModeResponse(
            mode=ParsedMode.SCENE,
            effect=scene_key_for_code("H617A", scene_code),
            scene_code=scene_code,
        )
    if mode_name == "diy":
        return ParsedColorModeResponse(mode=ParsedMode.DIY, diy_code=int(body.mode_body.code))
    if mode_name == "music":
        detail = body.mode_body
        mode_id = int(detail.mode_id)
        music_mode = _music_slug(model, mode_id)
        music_color = None
        if detail.manual_color_count >= 1:
            music_color = (int(detail.rgb.red), int(detail.rgb.green), int(detail.rgb.blue))
        return ParsedColorModeResponse(
            mode=ParsedMode.MUSIC,
            music_mode=music_mode,
            music_mode_id=mode_id,
            music_sensitivity=int(detail.sensitivity),
            music_calm=bool(detail.style) if music_mode == "rhythm" else None,
            music_color=music_color,
        )
    if mode_name == "static":
        return ParsedColorModeResponse(mode=ParsedMode.COLOUR, multi_effect_flag=int(body.mode_body.sub))
    return ParsedColorModeResponse()
