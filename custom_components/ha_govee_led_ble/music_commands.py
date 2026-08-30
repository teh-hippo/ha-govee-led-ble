"""Qualified music requests, prepared in full before any control side effects."""

from collections.abc import Mapping
from typing import Any

from kaitaistruct import KaitaiStructError

from .const import MUSIC_MODE_SLUGS, ModelProfile, get_profile, music_mode_code
from .generated_protocol_adapter import build_music_mode, build_power, encode_music_parameters
from .music_semantics import (
    MusicVariant,
    compile_music_parameters,
    music_parameters_available,
    music_params_for_mode,
    music_variant,
)
from .transport import fragment_a3


def _encode_h6125_music_parameters(
    variant: MusicVariant,
    parameters: Mapping[str, int | bool | str],
    *,
    calm: bool,
) -> bytes:
    body = bytearray(variant.template)
    mode = variant.mode_code
    if mode == 0x30:
        body[-1] = 20 if calm else 80
    elif mode == 0x31:
        body[-3:-1] = (0x1446 if calm else 0x0564).to_bytes(2, "big")
    elif mode == 0x32:
        gradient = bool(parameters["gradient"])
        body[-3:] = bytes((int(parameters["point"]), int(gradient), 98 if gradient else 99))
    elif mode == 0x33:
        body[-6] = int(parameters["relative_brightness"])
    elif mode == 0x34:
        key_count = int(parameters["key_count"])
        body[-4] = key_count
        body[-1] = max(1, key_count // 2)
    elif mode == 0x35:
        direction = {"clockwise": 1, "counterclockwise": 0}[str(parameters["direction"])]
        body[-4:-1] = bytes((direction, 2 if direction else 3, 5 if direction else 8))
    elif mode == 0x37:
        body[-3:] = bytes(
            (
                int(parameters["segment_count"]),
                int(parameters["speed"]),
                int(bool(parameters["gradient"])),
            )
        )
    return bytes(body)


def build_music_params(
    mode: int,
    parameters: Mapping[str, Any],
    palette: list[tuple[int, int, int]] | None = None,
    *,
    profile: ModelProfile,
    calm: bool = False,
) -> list[bytes]:
    valid_codes = (
        {code for _slug, code in profile.music_mode_codes}
        if profile.music_mode_codes
        else {MUSIC_MODE_SLUGS[slug] for slug in profile.music_modes}
    )
    if type(mode) is not int or mode not in valid_codes:
        raise ValueError("unsupported music mode")
    if not isinstance(calm, bool):
        raise ValueError("music style must be a boolean")
    variant = music_variant(profile, mode)
    compiled = compile_music_parameters(parameters, mode, profile)
    if variant is None or variant.layout is None:
        if compiled or palette is not None or (variant is not None and (variant.template or variant.parameters)):
            raise ValueError("music parameter layout is unqualified")
        return []
    if not music_parameters_available(profile, variant):
        if palette is not None:
            raise ValueError("music parameters require known physical IC count")
        return []
    if variant.layout == "h6125_music_body":
        if palette is not None:
            raise ValueError("H6125 music companions do not support palette overrides")
        return fragment_a3(0x41, _encode_h6125_music_parameters(variant, compiled, calm=calm))
    try:
        body = encode_music_parameters(variant, compiled, palette=palette, calm=calm)
    except (KaitaiStructError, EOFError) as error:
        raise ValueError("music parameter layout or palette is invalid") from error
    return fragment_a3(0x41, body)


def prepare_music_request(
    model: str,
    mode: str,
    sensitivity: int,
    colour: tuple[int, int, int] | None,
    calm: bool,
    parameters: Mapping[str, Any],
    *,
    include_parameters: bool = True,
) -> tuple[bytes, ...]:
    profile = get_profile(model)
    if mode not in profile.music_modes:
        raise ValueError(f"{model} does not support music mode {mode}")
    mode_code = music_mode_code(model, mode)
    companion = build_music_params(mode_code, parameters, profile=profile, calm=calm) if include_parameters else []
    return (build_power(True, model), build_music_mode(mode_code, sensitivity, colour, calm, model), *companion)


def resolve_music_profile(
    model: str,
    mode: str,
    sensitivity: int,
    colour: tuple[int, int, int] | None,
    calm: bool | None,
    parameters: Mapping[str, Any],
) -> tuple[bool, dict[str, int | bool | str], tuple[bytes, ...]]:
    """Resolve and validate the complete target request without changing device state."""
    profile = get_profile(model)
    if mode not in profile.music_modes:
        raise ValueError(f"{model} does not support music mode {mode}")
    mode_code = music_mode_code(model, mode)
    variant = music_variant(profile, mode_code)
    if calm is not None and (variant is None or not variant.supports_style):
        raise ValueError(f"music mode {mode} does not support a style setting")
    if colour is not None and not profile.supports_music_color:
        raise ValueError(f"{model} does not support a fixed music colour")
    if colour is not None and model == "H6125" and mode not in {"rhythm", "spectrum", "rolling"}:
        raise ValueError(f"H6125 music mode {mode} does not support a fixed colour")
    resolved_calm = calm if calm is not None else variant.calm_default if variant and variant.supports_style else False
    compiled = compile_music_parameters(parameters, mode_code, profile)
    packets = prepare_music_request(model, mode, sensitivity, colour, resolved_calm, compiled)
    return resolved_calm, compiled, packets


def prepare_music_profile_writes(
    model: str,
    mode: str,
    sensitivity: int,
    colour: tuple[int, int, int] | None,
    calm: bool,
    parameters: Mapping[str, Any],
) -> tuple[tuple[bytes, dict[str, Any]], ...]:
    """Pair validated packets with retained state installed at their physical attempt."""
    packets = prepare_music_request(model, mode, sensitivity, colour, calm, parameters)
    states: list[dict[str, Any]] = [{} for _ in packets]
    states[0] = {"is_on": True}
    states[1] = {
        "music_sensitivity": sensitivity,
        "music_color": colour,
        "music_calm": calm,
        "music_mode": mode,
        "video_mode": "off",
        "effect": None,
        "diy_code": None,
    }
    if len(packets) > 2:
        # Earlier fragments cannot complete the companion; a final attempt may.
        states[-1] = {
            spec.key: parameters.get(spec.profile_key, spec.default)
            for spec in music_params_for_mode(music_mode_code(model, mode), get_profile(model))
        }
    return tuple(zip(packets, states, strict=True))


def music_default_available(model: str, mode: str) -> bool:
    try:
        resolve_music_profile(model, mode, get_profile(model).music_sensitivity_max, None, None, {})
    except ValueError:
        return False
    return True
