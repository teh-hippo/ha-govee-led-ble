"""Coordinator status DTOs and semantic parsing."""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

from .const import MUSIC_MODE_SLUGS
from .generated_protocol_adapter import parse_status
from .scenes import MODEL_SCENES

_MUSIC_SLUG_BY_ID = {code: slug for slug, code in MUSIC_MODE_SLUGS.items()}
_SCENE_EFFECT_BY_MODEL_ID = {
    model: {scene.code: name for name, scene in scenes.items()} for model, scenes in MODEL_SCENES.items()
}
_RHYTHM_MODE_ID = MUSIC_MODE_SLUGS["rhythm"]


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


def decode_status_frame(frame: bytes, model: str = "H617A") -> ParsedStatusEnvelope | None:
    """Parse one fixed-size status notification with its model-specific Kaitai class."""
    parsed = parse_status(frame, model)
    if parsed is None:
        return None
    return ParsedStatusEnvelope(
        domain=_STATUS_DOMAIN_NAMES.get(getattr(parsed.domain, "name", ""), StatusDomain.OTHER),
        raw_domain=int(parsed.domain),
        payload=bytes(frame[2:-1]),
        generated=parsed,
    )


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
    video_full_screen: bool | None = None
    video_saturation: int | None = None
    video_sound_effects: bool | None = None
    video_sound_effects_softness: int | None = None
    music_sensitivity: int | None = None
    music_calm: bool | None = None
    music_color: tuple[int, int, int] | None = None
    rgb_color: tuple[int, int, int] | None = None
    white_brightness: int | None = None
    multi_effect_flag: int | None = None


def parse_color_mode(generated: Any, model: str) -> ParsedColorModeResponse:
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
            fixed_colour = None
            if detail.has_fixed_colour:
                fixed_colour = (
                    int(detail.fixed_colour.red),
                    int(detail.fixed_colour.green),
                    int(detail.fixed_colour.blue),
                )
            return ParsedColorModeResponse(
                mode=ParsedMode.MUSIC,
                music_mode=_MUSIC_SLUG_BY_ID.get(int(detail.mode)),
                music_sensitivity=int(detail.sensitivity),
                music_calm=bool(detail.is_calm),
                music_color=fixed_colour,
            )
        if mode_name == "scene":
            scene_code = int(body.detail.scene_id)
            return ParsedColorModeResponse(
                mode=ParsedMode.SCENE,
                effect=_SCENE_EFFECT_BY_MODEL_ID["H6199"].get(scene_code),
                scene_code=scene_code,
            )
        if mode_name == "static_colour":
            return ParsedColorModeResponse(mode=ParsedMode.COLOUR)
        return ParsedColorModeResponse()

    if mode_name == "scene":
        scene_code = int(body.mode_body.scene_id)
        return ParsedColorModeResponse(
            mode=ParsedMode.SCENE,
            effect=_SCENE_EFFECT_BY_MODEL_ID["H617A"].get(scene_code),
            scene_code=scene_code,
        )
    if mode_name == "diy":
        return ParsedColorModeResponse(mode=ParsedMode.DIY, diy_code=int(body.mode_body.code))
    if mode_name == "music":
        detail = body.mode_body
        music_color = None
        if detail.manual_color_count >= 1:
            music_color = (int(detail.rgb.red), int(detail.rgb.green), int(detail.rgb.blue))
        return ParsedColorModeResponse(
            mode=ParsedMode.MUSIC,
            music_mode=_MUSIC_SLUG_BY_ID.get(int(detail.mode_id)),
            music_sensitivity=int(detail.sensitivity),
            music_calm=bool(detail.style) if int(detail.mode_id) == _RHYTHM_MODE_ID else None,
            music_color=music_color,
        )
    if mode_name == "static":
        return ParsedColorModeResponse(mode=ParsedMode.COLOUR, multi_effect_flag=int(body.mode_body.sub))
    return ParsedColorModeResponse()
