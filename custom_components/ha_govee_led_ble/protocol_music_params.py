"""Music-parameter codecs for the profile-declared music variants."""

from __future__ import annotations

from enum import IntEnum
from importlib import import_module
from typing import Any

from .music_semantics import COMPANION_MUSIC_LAYOUTS, MusicVariant
from .protocol_core import (
    H617aControlPayload,
    H6076MusicBody,
    H7025MusicBody,
    MusicBody,
    _check_tree,
    _rgb,
    _write,
)


def music_default_palette(variant: MusicVariant | None) -> tuple[tuple[int, int, int], ...]:
    """Read the qualified default through its schema, not palette byte offsets."""
    if variant is None or not variant.template:
        raise ValueError("music palette layout is unqualified")
    root = parse_music_parameters(variant, variant.template)
    return tuple((int(rgb.red), int(rgb.green), int(rgb.blue)) for rgb in root.palette)


def parse_music_parameters(variant: MusicVariant, body: bytes) -> Any:
    """Validate a complete retained body with the selected KSY, independent of authoring bounds."""
    if not isinstance(body, bytes) or not body or len(body) > 255 * 17 - 3:
        raise ValueError("invalid music body length")
    if variant.layout in {
        "h6097_music_parameters",
        "h6099_music_parameters",
        "h66a0_music_parameters",
        "h1a42_music_parameters",
        "h61f5_music_parameters",
    }:
        root_type = (
            import_module(
                "custom_components.ha_govee_led_ble.generated_protocol.h6097_music_parameters"
            ).H6097MusicParameters
            if variant.layout == "h6097_music_parameters"
            else import_module(
                "custom_components.ha_govee_led_ble.generated_protocol.h61f5_music_parameters"
            ).H61f5MusicParameters
            if variant.layout == "h61f5_music_parameters"
            else import_module(
                "custom_components.ha_govee_led_ble.generated_protocol.h1a42_music_parameters"
            ).H1a42MusicParameters
            if variant.layout == "h1a42_music_parameters"
            else import_module(
                "custom_components.ha_govee_led_ble.generated_protocol.h66a0_music_parameters"
            ).H66a0MusicParameters
            if variant.layout == "h66a0_music_parameters"
            else import_module(
                "custom_components.ha_govee_led_ble.generated_protocol.h6099_music_parameters"
            ).H6099MusicParameters
        )
        root = root_type.from_bytes(body)
    elif variant.layout in COMPANION_MUSIC_LAYOUTS:
        root_type = {
            "music_body": MusicBody,
            "h6076_music_body": H6076MusicBody,
            "h7025_music_body": H7025MusicBody,
        }[variant.layout]
        root = root_type.from_bytes(b"\x01\x02\x41" + body)
    else:
        raise ValueError("music palette layout is unqualified")
    root._read()
    if int(root.mode) != variant.mode_code or root.tail is None or not root._io.is_eof():
        raise ValueError("music body does not match qualified layout")
    return root


def encode_music_parameters(
    variant: MusicVariant,
    parameters: dict[str, int | bool | str],
    *,
    palette: list[tuple[int, int, int]] | None,
    calm: bool | None,
    physical_ic_count: int | None = None,
    preserve_companions: bool = False,
) -> bytes:
    """Edit named Kaitai fields; palette length never becomes an absolute tail offset."""
    if variant.layout in {
        "h6097_music_parameters",
        "h6099_music_parameters",
        "h66a0_music_parameters",
        "h1a42_music_parameters",
        "h61f5_music_parameters",
    }:
        return _encode_h6099_music_parameters(
            variant, parameters, palette, calm, physical_ic_count, preserve_companions
        )
    if variant.layout not in COMPANION_MUSIC_LAYOUTS or not variant.evidence or not variant.template:
        raise ValueError("music parameter layout is unqualified")
    root = parse_music_parameters(variant, variant.template)
    length = len(variant.template) + 3
    if palette is not None:
        if variant.palette_bounds is None or not variant.palette_bounds[0] <= len(palette) <= variant.palette_bounds[1]:
            raise ValueError("palette count is outside music variant bounds")
        if any(
            len(rgb) != 3 or any(type(channel) is not int or not 0 <= channel <= 255 for channel in rgb)
            for rgb in palette
        ):
            raise ValueError("invalid music palette")
        length += 3 * (len(palette) - root.num_palette)
        root.num_palette = len(palette)
        root.palette = [_rgb(root, *rgb) for rgb in palette]
    tail = root.tail
    for spec in variant.parameters:
        if spec.profile_key not in parameters:
            continue
        if spec.requires_physical_ic_count and physical_ic_count is None:
            raise ValueError("music parameter requires known physical IC count")
        value = parameters[spec.profile_key]
        if not hasattr(tail, spec.wire_field):
            raise ValueError("music parameter field is absent from qualified layout")
        if spec.wire_field == "background":
            rgb = int(value)
            tail.background = _rgb(tail, rgb >> 16, (rgb >> 8) & 255, rgb & 255)
        elif spec.kind != "select":
            setattr(tail, spec.wire_field, int(value))
        elif not variant.direction_values:
            current = getattr(tail, spec.wire_field)
            if not isinstance(current, IntEnum) or str(value) not in spec.options:
                raise ValueError("music parameter requires a qualified enum value")
            setattr(tail, spec.wire_field, type(current)[str(value)])
    if (
        isinstance(tail, H617aControlPayload.HoppingTail)
        and physical_ic_count is not None
        and not preserve_companions
        and (variant.requires_physical_ic_count or any(spec.requires_physical_ic_count for spec in variant.parameters))
    ):
        from math import ceil

        tail.piece_count_min = max(1, ceil(physical_ic_count * 3 / 25))
        tail.piece_count_max = max(1, ceil(physical_ic_count * 2 / 5))
    if variant.gradient_companions is not None and "gradient" in parameters:
        tail.speed = variant.gradient_companions[bool(parameters["gradient"])]
    if variant.piano_derived_half and "key_count" in parameters:
        if (
            physical_ic_count is not None
            and not preserve_companions
            and any(spec.profile_key == "key_count" and spec.requires_physical_ic_count for spec in variant.parameters)
        ):
            from math import ceil

            tail.speed = (
                (10 if physical_ic_count <= 30 else 35)
                if variant.physical_defaults == "rgbic"
                else (10 if physical_ic_count < 30 else 35)
            )
            tail.off_minimum = ceil(physical_ic_count / 4) if physical_ic_count < 30 else 1
        tail.off_maximum = max(tail.off_minimum, tail.key_count // 2)
    if variant.direction_values and "direction" in parameters:
        tail.start_point, tail.piece_num = {name: (start, pieces) for name, start, pieces in variant.direction_values}[
            str(parameters["direction"])
        ]
        if physical_ic_count is not None and any(
            spec.profile_key == "direction" and spec.requires_physical_ic_count for spec in variant.parameters
        ):
            tail.piece_len = 1 if physical_ic_count < 30 else 2 if tail.start_point == 1 else 3
            if not preserve_companions:
                tail.speed = 80 if physical_ic_count < 30 else 85
    if variant.style_companions is not None and calm is not None:
        value = variant.style_companions[calm]
        if isinstance(tail, H617aControlPayload.ShinyTail):
            tail.minimum_brightness, tail.maximum_brightness = value >> 8, value & 255
        else:
            tail.no_rhythm_speed, tail.rhythm_speed = 10, value
    _check_tree(root)
    return _write(root, length)[3:]


def _encode_h6099_music_parameters(
    variant: MusicVariant,
    parameters: dict[str, int | bool | str],
    palette: list[tuple[int, int, int]] | None,
    calm: bool | None,
    ic: int | None,
    preserve_companions: bool = False,
) -> bytes:
    from math import ceil

    root = parse_music_parameters(variant, variant.template)
    if not variant.evidence:
        raise ValueError("music template does not match qualified variant")
    length = len(variant.template)
    if palette is not None:
        if variant.palette_bounds is None or not variant.palette_bounds[0] <= len(palette) <= variant.palette_bounds[1]:
            raise ValueError("palette count is outside music variant bounds")
        if any(len(rgb) != 3 or any(type(c) is not int or not 0 <= c <= 255 for c in rgb) for rgb in palette):
            raise ValueError("invalid music palette")
        length += 3 * (len(palette) - root.num_palette)
        root.num_palette = len(palette)
        root.palette = [_rgb(root, *rgb) for rgb in palette]
    tail = root.tail
    for spec in variant.parameters:
        if spec.profile_key not in parameters:
            continue
        value = parameters[spec.profile_key]
        if spec.wire_field == "background":
            rgb = int(value)
            tail.background = _rgb(tail, rgb >> 16, (rgb >> 8) & 255, rgb & 255)
        elif spec.kind != "select":
            setattr(tail, spec.wire_field, int(value))
    if variant.requires_physical_ic_count and ic is None:
        raise ValueError("music parameters require known physical IC count")
    mode_name = getattr(root.mode, "name", None)
    if mode_name == "bloom" and calm is not None:
        tail.no_rhythm_speed, tail.rhythm_speed = 10, 20 if calm else 80
    elif mode_name == "shiny" and calm is not None:
        tail.minimum_brightness, tail.maximum_brightness = (20, 70) if calm else (5, 100)
    elif ic is not None:
        if mode_name == "separation" and (not preserve_companions or "gradient" in parameters):
            tail.companion = (99, 98)[bool(tail.gradient)] if ic >= 30 else (97, 94)[bool(tail.gradient)]
        elif mode_name == "hopping" and not preserve_companions:
            tail.piece_count_min = max(1, ceil(ic * 3 / 25))
            tail.piece_count_max = max(1, ceil(ic * 2 / 5))
        elif mode_name == "piano_keys" and (not preserve_companions or "key_count" in parameters):
            if not preserve_companions:
                tail.speed = (
                    (10 if ic <= 30 else 35) if variant.physical_defaults == "rgbic" else (10 if ic < 30 else 35)
                )
                tail.off_minimum = ceil(ic / 4) if ic < 30 else 1
            tail.off_maximum = max(tail.off_minimum, tail.key_count // 2)
        elif mode_name == "fountain" and (not preserve_companions or "direction" in parameters):
            tail.start_point = {"clockwise": 0, "counterclockwise": 2, "two_way": 1}[str(parameters["direction"])]
            two_way = tail.start_point == 1
            tail.piece_length = 1 if ic < 30 else 2 if two_way else 3
            tail.piece_count = (
                (ic // 4 if two_way else ic // 3) if ic < 30 else ceil(ic / 10 if two_way else ic * 4 / 25)
            )
            if not preserve_companions:
                tail.speed = 80 if ic < 30 else 85
        elif mode_name == "day_and_night" and not preserve_companions:
            if not variant.parameters:
                tail.piece_count = max(1, ic // 2) if ic < 30 else ceil(ic * 7 / 50)
                # MusicMode.d uses default subEffect[0] (piece) as speed and [1] (10/20) as fade.
                tail.speed = max(1, min(50, tail.piece_count))
                tail.gradient = 0
            else:
                if "segment_count" not in parameters:
                    tail.piece_count = max(1, ic // 2) if ic < 30 else ceil(ic * 7 / 50)
                if "speed" not in parameters:
                    tail.speed = 10 if ic < 30 else 20
    if any(
        type(value) is int and not 0 <= value <= 255 for key, value in vars(tail).items() if not key.startswith("_")
    ):
        raise ValueError("physical IC geometry exceeds music wire bounds")
    _check_tree(root)
    return _write(root, length)
