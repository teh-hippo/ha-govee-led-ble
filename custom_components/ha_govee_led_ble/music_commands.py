"""Qualified music requests, prepared in full before any control side effects."""

from collections.abc import Mapping
from typing import Any

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
        if compiled or palette is not None:
            raise ValueError("music parameter layout is unqualified")
        return []
    if not music_parameters_available(profile, variant):
        if palette is not None:
            raise ValueError("music parameters require known physical IC count")
        return []
    return fragment_a3(0x41, encode_music_parameters(variant, compiled, palette=palette, calm=calm))


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
