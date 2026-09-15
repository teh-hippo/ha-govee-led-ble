"""Qualified music requests, prepared in full before any control side effects."""

from collections.abc import Mapping
from typing import Any

from kaitaistruct import KaitaiStructError

from .const import MUSIC_MODE_SLUGS, ModelProfile, get_profile
from .generated_protocol_adapter import build_music_mode, build_power, encode_music_parameters
from .music_protocol import music_code_for, music_mode_has_parameter_write
from .music_semantics import compile_music_parameters, music_parameters_available, music_params_for_mode, music_variant
from .transport import fragment_a3


def build_music_params(
    mode: int,
    parameters: Mapping[str, Any],
    palette: list[tuple[int, int, int]] | None = None,
    *,
    profile: ModelProfile,
    calm: bool = False,
) -> list[bytes]:
    if type(mode) is not int or mode not in (MUSIC_MODE_SLUGS[slug] for slug in profile.music_modes):
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
    mode_code = music_code_for(model, mode)
    companion = (
        build_music_params(mode_code, parameters, profile=profile, calm=calm)
        if include_parameters and music_mode_has_parameter_write(model, mode_code)
        else []
    )
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
    mode_code = music_code_for(model, mode)
    variant = music_variant(profile, mode_code)
    if calm is not None and (variant is None or not variant.supports_style):
        raise ValueError(f"music mode {mode} does not support a style setting")
    if colour is not None and not profile.supports_music_color:
        raise ValueError(f"{model} does not support a fixed music colour")
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
            for spec in music_params_for_mode(music_code_for(model, mode), get_profile(model))
        }
    return tuple(zip(packets, states, strict=True))


def music_default_available(model: str, mode: str) -> bool:
    try:
        resolve_music_profile(model, mode, get_profile(model).music_sensitivity_max, None, None, {})
    except ValueError:
        return False
    return True
