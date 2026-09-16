"""Qualified music requests, prepared in full before any control side effects."""

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from kaitaistruct import KaitaiStructError

from .const import MUSIC_MODE_SLUGS, ModelProfile, get_profile
from .generated_protocol_adapter import (
    build_music_mode,
    build_power,
    encode_music_parameters,
    music_default_palette,
    parse_music_parameters,
)
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
        body = encode_music_parameters(
            variant, compiled, palette=palette, calm=calm, physical_ic_count=profile.physical_ic_count
        )
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
    profile: ModelProfile | None = None,
    palette: Sequence[tuple[int, int, int]] | None = None,
) -> tuple[bytes, ...]:
    profile = get_profile(model) if profile is None else profile
    if mode not in profile.music_modes:
        raise ValueError(f"{model} does not support music mode {mode}")
    mode_code = MUSIC_MODE_SLUGS[mode]
    variant = music_variant(profile, mode_code)
    if palette is not None and (variant is None or variant.palette_bounds is None):
        raise ValueError("music mode does not support an authored palette")
    if palette is not None and not include_parameters:
        raise ValueError("music palette requires a parameter upload")
    companion = (
        build_music_params(
            mode_code, parameters, None if palette is None else list(palette), profile=profile, calm=calm
        )
        if include_parameters
        else []
    )
    selector = build_music_mode(mode_code, sensitivity, colour, calm, model)
    control = (*companion, selector) if profile.music_upload_before_selector else (selector, *companion)
    return (build_power(True, model), *control)


def resolve_music_profile(
    model: str,
    mode: str,
    sensitivity: int,
    colour: tuple[int, int, int] | None,
    calm: bool | None,
    parameters: Mapping[str, Any],
    *,
    profile: ModelProfile | None = None,
    palette: Sequence[tuple[int, int, int]] | None = None,
) -> tuple[bool, dict[str, int | bool | str], tuple[bytes, ...]]:
    """Resolve and validate the complete target request without changing device state."""
    profile = get_profile(model) if profile is None else profile
    if mode not in profile.music_modes:
        raise ValueError(f"{model} does not support music mode {mode}")
    variant = music_variant(profile, MUSIC_MODE_SLUGS[mode])
    if calm is not None and (variant is None or not variant.supports_style):
        raise ValueError(f"music mode {mode} does not support a style setting")
    if colour is not None and not (profile.supports_music_color and (variant is None or variant.supports_fixed_colour)):
        raise ValueError(f"{model} does not support a fixed music colour")
    resolved_calm = calm if calm is not None else variant.calm_default if variant and variant.supports_style else False
    compiled = compile_music_parameters(parameters, MUSIC_MODE_SLUGS[mode], profile)
    packets = prepare_music_request(
        model, mode, sensitivity, colour, resolved_calm, compiled, profile=profile, palette=palette
    )
    return resolved_calm, compiled, packets


def prepare_music_profile_writes(
    model: str,
    mode: str,
    sensitivity: int,
    colour: tuple[int, int, int] | None,
    calm: bool,
    parameters: Mapping[str, Any],
    *,
    profile: ModelProfile | None = None,
    include_parameters: bool = True,
    palette: Sequence[tuple[int, int, int]] | None = None,
    original_body: bytes | None = None,
) -> tuple[tuple[bytes, dict[str, Any]], ...]:
    """Pair validated packets with retained state installed at their physical attempt."""
    profile = get_profile(model) if profile is None else profile
    if original_body is not None:
        if not include_parameters or palette is not None or parameters:
            raise ValueError("original music body cannot be combined with authored parameters")
        validate_music_body(original_body, mode, profile=profile)
    packets = prepare_music_request(
        model,
        mode,
        sensitivity,
        colour,
        calm,
        parameters,
        profile=profile,
        include_parameters=include_parameters and original_body is None,
        palette=palette,
    )
    if original_body is not None:
        power, selector = packets
        upload = fragment_a3(0x41, original_body)
        packets = (power, *upload, selector) if profile.music_upload_before_selector else (power, selector, *upload)
    states: list[dict[str, Any]] = [{} for _ in packets]
    states[0] = {"is_on": True}
    selector_index = len(packets) - 1 if profile.music_upload_before_selector else 1
    states[selector_index] = {
        "music_sensitivity": sensitivity,
        "music_color": colour,
        "music_calm": calm,
        "music_mode": mode,
        "video_mode": "off",
        "effect": None,
        "diy_code": None,
    }
    variant = music_variant(profile, MUSIC_MODE_SLUGS[mode])
    if variant and variant.layout in {"music_body", "h6099_music_parameters"}:
        # New selectors carry neither style nor fixed colour, even without an upload.
        del states[selector_index]["music_calm"]
        del states[selector_index]["music_color"]
    if len(packets) > 2:
        # Earlier fragments cannot complete the companion; a final attempt may.
        companion_index = len(packets) - 2 if profile.music_upload_before_selector else len(packets) - 1
        states[companion_index] = {
            spec.key: parameters.get(spec.profile_key, spec.default)
            for spec in music_params_for_mode(MUSIC_MODE_SLUGS[mode], profile)
            if original_body is None
        }
        if original_body is None and variant and variant.supports_style:
            states[companion_index]["music_calm"] = calm
        assert variant is not None
        body = (
            original_body
            if original_body is not None
            else encode_music_parameters(
                variant,
                compile_music_parameters(parameters, MUSIC_MODE_SLUGS[mode], profile),
                palette=None if palette is None else list(palette),
                calm=calm,
                physical_ic_count=profile.physical_ic_count,
            )
        )
        if original_body is not None:
            decoded = music_body_parameters(body, mode, profile=profile)
            states[companion_index].update(
                {spec.key: decoded[spec.profile_key] for spec in variant.parameters if spec.profile_key in decoded}
            )
            if variant.supports_style:
                # Unknown companion pairs must not inherit the previous effect's style.
                style = music_body_style(body, mode, profile=profile)
                states[companion_index]["_music_calm" if style is None else "music_calm"] = style
            # Retained display fields are not edit intent or geometry-dependent writes.
            states[companion_index]["_music_parameter_keys"] = ()
        first_companion = 1 if profile.music_upload_before_selector else 2
        states[first_companion]["_music_body"] = None
        # Candidate only: async_write_music_sequence defers this until successful completion.
        states[companion_index]["_music_body"] = (mode, body)
        if variant and variant.palette_bounds:
            # An incomplete upload invalidates retained knowledge. Neither assignment is readback.
            states[first_companion]["_music_palette"] = None
            retained = music_default_palette(replace(variant, template=body))
            states[companion_index]["_music_palette"] = (mode, retained)
    return tuple(zip(packets, states, strict=True))


def validate_music_body(body: bytes, mode: str, *, profile: ModelProfile) -> Any:
    """Validate restored bytes structurally; authoring bounds cannot discard original companions."""
    variant = music_variant(profile, MUSIC_MODE_SLUGS.get(mode, -1))
    if mode not in profile.music_modes or variant is None or not variant.evidence:
        raise ValueError("music body mode is unqualified")
    try:
        return parse_music_parameters(variant, body)
    except (KaitaiStructError, EOFError) as error:
        raise ValueError("invalid original music body") from error


def prepare_music_body_writes(
    model: str,
    mode: str,
    sensitivity: int,
    body: bytes,
    *,
    profile: ModelProfile | None = None,
) -> tuple[tuple[bytes, dict[str, Any]], ...]:
    """Replay a complete known body verbatim; the new selector carries only mode/sensitivity."""
    return prepare_music_profile_writes(model, mode, sensitivity, None, False, {}, profile=profile, original_body=body)


def edit_music_body(
    body: bytes,
    mode: str,
    parameters: Mapping[str, Any],
    *,
    profile: ModelProfile,
    calm: bool | None = None,
) -> bytes:
    """Overlay only requested fields on a validated original, never fill missing fields from defaults."""
    validate_music_body(body, mode, profile=profile)
    mode_code = MUSIC_MODE_SLUGS[mode]
    variant = music_variant(profile, mode_code)
    assert variant is not None
    if calm is not None and (type(calm) is not bool or not variant.supports_style):
        raise ValueError("music style is unsupported or invalid")
    compiled = compile_music_parameters(parameters, mode_code, profile)
    return encode_music_parameters(
        replace(variant, template=body),
        {key: compiled[key] for key in parameters},
        palette=None,
        calm=calm,
        physical_ic_count=profile.physical_ic_count,
        preserve_companions=True,
    )


def music_body_parameters(body: bytes, mode: str, *, profile: ModelProfile) -> dict[str, int | bool | str]:
    """Read declared fields from the known body so an edit can distinguish unchanged siblings."""
    root = validate_music_body(body, mode, profile=profile)
    variant = music_variant(profile, MUSIC_MODE_SLUGS[mode])
    assert variant is not None
    result: dict[str, int | bool | str] = {}
    # Decoding known fields does not require permission to author geometry-dependent values.
    for spec in variant.parameters:
        value = getattr(root.tail, spec.wire_field)
        if spec.wire_field == "background":
            result[spec.profile_key] = (int(value.red) << 16) | (int(value.green) << 8) | int(value.blue)
        elif spec.kind == "switch":
            result[spec.profile_key] = bool(value)
        elif spec.kind == "select":
            directions = (
                ((name, start) for name, start, _ in variant.direction_values)
                if variant.direction_values
                else (("clockwise", 0), ("counterclockwise", 2), ("two_way", 1))
            )
            for name, start in directions:
                if root.tail.start_point == start and name in spec.options:
                    result[spec.profile_key] = name
        else:
            result[spec.profile_key] = int(value)
    return result


def music_body_style(body: bytes, mode: str, *, profile: ModelProfile) -> bool | None:
    """Only recognized companion pairs establish a style; unknown pairs stay unknown."""
    root = validate_music_body(body, mode, profile=profile)
    variant = music_variant(profile, MUSIC_MODE_SLUGS[mode])
    if variant is None or not variant.supports_style:
        return None
    if hasattr(root.tail, "rhythm_speed") and root.tail.no_rhythm_speed == 10:
        return {80: False, 20: True}.get(root.tail.rhythm_speed)
    if hasattr(root.tail, "minimum_brightness"):
        return {(5, 100): False, (20, 70): True}.get((root.tail.minimum_brightness, root.tail.maximum_brightness))
    return None


def music_default_available(model: str, mode: str, *, profile: ModelProfile | None = None) -> bool:
    profile = get_profile(model) if profile is None else profile
    try:
        resolve_music_profile(model, mode, profile.music_sensitivity_max, None, None, {}, profile=profile)
    except ValueError:
        return False
    return True
