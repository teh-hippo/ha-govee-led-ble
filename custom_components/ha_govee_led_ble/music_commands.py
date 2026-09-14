"""Qualified music requests, prepared in full before any control side effects."""

from collections.abc import Mapping
from typing import Any

from kaitaistruct import KaitaiStructError

from .const import MUSIC_MODE_SLUGS, ModelProfile, get_profile
from .generated_protocol_adapter import build_music_mode, build_power, encode_music_parameters
from .music_semantics import compile_music_parameters, music_parameters_available, music_variant
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
    mode_code = MUSIC_MODE_SLUGS[mode]
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
    variant = music_variant(profile, MUSIC_MODE_SLUGS[mode])
    if calm is not None and (variant is None or not variant.supports_style):
        raise ValueError(f"music mode {mode} does not support a style setting")
    if colour is not None and not profile.supports_music_color:
        raise ValueError(f"{model} does not support a fixed music colour")
    resolved_calm = calm if calm is not None else variant.calm_default if variant and variant.supports_style else False
    compiled = compile_music_parameters(parameters, MUSIC_MODE_SLUGS[mode], profile)
    packets = prepare_music_request(model, mode, sensitivity, colour, resolved_calm, compiled)
    return resolved_calm, compiled, packets


def music_default_available(model: str, mode: str) -> bool:
    try:
        resolve_music_profile(model, mode, get_profile(model).music_sensitivity_max, None, None, {})
    except ValueError:
        return False
    return True
