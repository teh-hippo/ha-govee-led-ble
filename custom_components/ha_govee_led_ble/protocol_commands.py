"""Command encoding over capability-selected generated Kaitai classes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .const import WHOLE_BULB_GRAMMARS, ModelProfile, ReadDomain, get_profile
from .music_protocol import H60b0MusicBody, music_slug_for
from .music_semantics import music_variant
from .protocol_core import (
    _BLANK_SCREEN_LOW_BRIGHTNESS_SECONDS,
    _BLANK_SCREEN_SAME_TONE_SECONDS,
    _COMMAND_ROOTS,
    _EXTENDED_STATIC_ROOTS,
    _MUSIC_WRITE_ROOTS,
    CommandWrite,
    GoveeCommon,
    H60b0CommandWrite,
    H60b2MusicBody,
    H60b2MusicWrite,
    H61f5ExtendedStaticWrite,
    H66a0VideoCommand,
    H600aCommandWrite,
    H601cCommandWrite,
    H605cVideoCommand,
    H607cCommandWrite,
    H607cMusicWrite,
    H1771CommandWrite,
    H1771MusicBody,
    H6046CommandWrite,
    H6072CommandWrite,
    H6076MusicBody,
    H6076MusicWrite,
    H6179CommandWrite,
    H6181CommandWrite,
    H7020CommandWrite,
    _child,
    _parse_xor_frame,
    _rgb,
    _serialize_xor,
)
from .protocol_h6179 import _build_h6179_static_colour, encode_h6179_brightness


def _command_types(model: str, profile: ModelProfile | None = None) -> tuple[Any, Any, Any]:
    resolved = (profile or get_profile(model)).command_grammar
    if resolved == "H60B0":
        return H60b0CommandWrite, H60b0CommandWrite.PowerCmd, H60b0CommandWrite.BrightnessCmd
    if resolved == "H1771":
        return H1771CommandWrite, H1771CommandWrite.PowerCmd, H1771CommandWrite.BrightnessCmd
    if resolved in {"H6072", "H6072-legacy", "H607C"}:
        return _COMMAND_ROOTS[resolved][1], CommandWrite.PowerCmd, CommandWrite.BrightnessCmd
    if resolved in {"H7020", "H705A"}:
        return _COMMAND_ROOTS[resolved][1], CommandWrite.PowerCmd, CommandWrite.BrightnessCmd
    if resolved in WHOLE_BULB_GRAMMARS | {"H6046", "H6099", "H6179", "H6199"}:
        root_type = _COMMAND_ROOTS[resolved][1]
        return root_type, root_type.PowerBody, root_type.BrightnessBody
    if resolved != "H617A":
        raise ValueError(f"{model} has no generated command grammar")
    return CommandWrite, CommandWrite.PowerCmd, CommandWrite.BrightnessCmd


def _video_grammar(model: str, profile: ModelProfile | None = None) -> str:
    profile = profile or get_profile(model)
    if not profile.supports_video_mode or profile.video_grammar is None:
        raise ValueError(f"{model} does not support video mode")
    return profile.video_grammar


def _video_command_grammar(model: str, profile: ModelProfile | None = None) -> str:
    profile = profile or get_profile(model)
    grammar = _video_grammar(model, profile)
    if grammar == "H605C-video":
        return "H6199"
    if grammar == "H66A0-video" and profile.command_grammar in {"H6099", "H6199"}:
        return profile.command_grammar
    return grammar


def build_power(on: bool, model: str = "H617A", *, profile: ModelProfile | None = None) -> bytes:
    root_type, power_type, _ = _command_types(model, profile)
    root = root_type()
    root.header = b"\x33"
    root.opcode = root_type.CommandOpcode.power if root_type is H6179CommandWrite else root_type.CommandOp.power
    body = power_type(None, root, root._root)
    body.is_on = int(on)
    if root_type in {H1771CommandWrite, H6046CommandWrite, H60b0CommandWrite}:
        body.unknown_tail = bytes(16)
    if root_type is H6179CommandWrite:
        body.opaque = bytes(16)
    elif root_type in {H600aCommandWrite, H601cCommandWrite, H6181CommandWrite}:
        body.padding = bytes(16)
    root.body = body
    return _serialize_xor(root)


def build_brightness(percent: int, model: str = "H617A", *, profile: ModelProfile | None = None) -> bytes:
    profile = profile or get_profile(model)
    root_type, _, brightness_type = _command_types(model, profile)
    root = root_type()
    root.header = b"\x33"
    root.opcode = (
        root_type.CommandOpcode.brightness if root_type is H6179CommandWrite else root_type.CommandOp.brightness
    )
    body = brightness_type(None, root, root._root)
    if root_type is H6179CommandWrite:
        body.raw = encode_h6179_brightness(percent)
        body.opaque = bytes(16)
    else:
        body.percent = max(0, min(100, percent))
    if root_type in {H1771CommandWrite, H6046CommandWrite, H60b0CommandWrite}:
        body.unknown_tail = bytes(16)
    if root_type in {H600aCommandWrite, H601cCommandWrite, H6181CommandWrite}:
        body.padding = bytes(16)
    root.body = body
    return _serialize_xor(root)


def _extended_static_root(profile: ModelProfile) -> tuple[str, Any] | None:
    root = _EXTENDED_STATIC_ROOTS.get(profile.extended_static_grammar or "")
    return root if root is not None and profile.segment_count >= root[1]().minimum_segment_count else None


def _build_h617a_static_colour(
    mask: int,
    *,
    direct: tuple[int, int, int],
    kelvin: int,
    preview: tuple[int, int, int],
    root_type: Any = CommandWrite,
) -> bytes:
    extended = root_type is H61f5ExtendedStaticWrite
    component = (
        CommandWrite if root_type in {H6072CommandWrite, H607cCommandWrite, H61f5ExtendedStaticWrite} else root_type
    )
    root = root_type()
    root.header = b"\x33"
    root.opcode = root_type.CommandOp.multi
    multi = _child(root_type.MultiCmd, root)
    multi.sub = root_type.MultiSub.static
    static = (
        component.StaticCmd(extended, None, multi, multi._root)
        if component is CommandWrite
        else _child(component.StaticCmd, multi)
    )
    static.static_sub = 1
    colour = (
        component.StaticColor(extended, None, static, static._root)
        if component is CommandWrite
        else _child(component.StaticColor, static)
    )
    colour.rgb_direct = _rgb(colour, *direct)
    colour.kelvin = kelvin
    colour.rgb_preview = _rgb(colour, *preview)
    segment_mask = _child(component.ExtendedSegmentMask if extended else component.SegmentMask, colour)
    segment_mask.bits = mask
    colour.mask = segment_mask
    if hasattr(colour, "tail_size"):
        colour.unknown_tail = bytes(colour.tail_size)
    elif root_type is H7020CommandWrite:
        colour.unknown_tail = bytes(3)
    elif root_type is H1771CommandWrite:
        colour.unknown_tail = bytes(5)
    static.static_body = colour
    multi.sub_body = static
    root.body = multi
    return _serialize_xor(root)


# The lamps ignore the direct RGB of a Kelvin write; it is constant white and only the companion colour is stored.
KELVIN_DIRECT_RGB: tuple[int, int, int] = (255, 255, 255)

# Ordered first-match companion lookup; non-table values do not interpolate.
_TABLE_KELVIN_RGB = {
    1000 + index * 100: bytes.fromhex(rgb)
    for index, rgb in enumerate(
        (
            "ff3300 ff4500 ff5200 ff5d00 ff6600 ff6f00 ff7600 ff7c00 ff8200 ff8700 "
            "ff8d0b ff921d ff9829 ff9d33 ffa23c ffa645 ffaa4d "
            "ffae54 ffb25b ffb662 ffb969 ffbd6f ffc076 ffc37c ffc682 ffc987 ffcb8d "
            "ffce92 ffd097 ffd39c ffd5a1 ffd7a6 ffd9ab ffdbaf ffddb4 ffdfb8 ffe1bc "
            "ffe2c0 ffe4c4 ffe5c8 ffe7cc ffe8d0 ffead3 ffebd7 ffedda ffeede ffefe1 "
            "fff0e4 fff1e7 fff3ea fff4ed fff5f0 fff6f3 fff7f7 fff8f8 fff9fb "
            "fff9fd fefaff fcf8ff faf7ff f7f5ff f5f4ff f3f3ff f1f1ff eff0ff "
            "eeefff eceeff eaedff e9ecff e7eaff e5e9ff e4e9ff e3e8ff e1e7ff e0e6ff "
            "dfe5ff dde4ff dce3ff dbe2ff dae2ff d9e1ff "
            "d8e0ff d7dfff d6dfff d5deff d4ddff d3ddff d2dcff d1dcff d0dbff cfdaff"
        ).split()
    )
}

_TABLE_RGB_KELVIN = {
    bytes.fromhex(rgb): 2000 + index * 100
    for index, rgb in enumerate(
        (
            "ff8912 ff8e21 ff932c ff9836 ff9d3f ffa148 ffa54f ffa957 ffad5e ffb165 "
            "ffb46b ffb872 ffbb78 ffbe7e ffc184 ffc489 ffc78f ffc994 ffcc99 ffce9f "
            "ffd1a3 ffd3a8 ffd5ad ffd7b1 ffd9b6 ffdbba ffddbe ffdfc2 ffe1c6 ffe3ca "
            "ffe4ce ffe6d2 ffe8d5 ffe9d9 ffebdc ffece0 ffeee3 ffefe6 fff0e9 fff2ec "
            "fff3ef fff4f2 fff5f5 fff6f8 fff8fb fff9fd fef9ff fcf7ff f9f6ff f7f5ff "
            "f5f3ff f3f2ff f0f1ff eff0ff edefff ebeeff e9edff e7ecff e6ebff e4eaff "
            "e3e9ff e1e8ff e0e7ff dee6ff dde6ff dce5ff dae4ff d9e3ff d8e3ff d7e2ff d6e1ff"
        ).split()
    )
}
# An alias overlapping a later canonical companion retains the later Kelvin value.
_TABLE_RGB_KELVIN.update((rgb, kelvin) for kelvin, rgb in _TABLE_KELVIN_RGB.items())


def table_kelvin_rgb(kelvin: int) -> tuple[int, int, int]:
    red, green, blue = _TABLE_KELVIN_RGB.get(kelvin, bytes(3))
    return red, green, blue


def table_rgb_kelvin(rgb: tuple[int, int, int]) -> int | None:
    return _TABLE_RGB_KELVIN.get(bytes(rgb))


def _build_h6072_legacy_colour(
    mask: int, direct: tuple[int, int, int], kelvin: int, preview: tuple[int, int, int]
) -> bytes:
    root = H6072CommandWrite()
    root.header = b"\x33"
    root.opcode = H6072CommandWrite.CommandOp.multi
    multi = _child(H6072CommandWrite.MultiCmd, root)
    multi.sub = H6072CommandWrite.MultiSub.legacy_static
    colour = _child(H6072CommandWrite.LegacyColour, multi)
    colour.rgb_direct = _rgb(colour, *direct)
    colour.kelvin = kelvin
    colour.rgb_preview = _rgb(colour, *preview)
    colour.unknown = 0
    colour.mask = mask
    colour.unknown_tail = bytes(6)
    multi.sub_body = colour
    root.body = multi
    return _serialize_xor(root)


def _build_whole_bulb_static_colour(
    mask: int, direct: tuple[int, int, int], kelvin: int, profile: ModelProfile
) -> bytes:
    if mask != profile.whole_device_mask:
        raise ValueError(f"{profile.command_grammar} supports whole-device colour only")
    if kelvin and kelvin not in _TABLE_KELVIN_RGB:
        raise ValueError(f"{profile.command_grammar} Kelvin must use the 100 K grid")
    root_type = _COMMAND_ROOTS[profile.command_grammar or ""][1]
    root = root_type()
    root.header = b"\x33"
    root.opcode = root_type.CommandOp.mode
    mode = _child(root_type.ModeBody, root)
    mode.sub_mode = root_type.ModeSel.static_colour
    detail = _child(root_type.StaticColourBody, mode)
    detail.rgb = _rgb(detail, *direct)
    detail.kelvin = kelvin
    detail.companion_rgb = _rgb(detail, *_TABLE_KELVIN_RGB.get(kelvin, bytes(3)))
    detail.padding = bytes(8)
    mode.detail = detail
    root.body = mode
    return _serialize_xor(root)


def build_segment_colour(
    mask: int,
    red: int,
    green: int,
    blue: int,
    model: str = "H617A",
    *,
    profile: ModelProfile | None = None,
) -> bytes:
    profile = profile or get_profile(model)
    resolved = profile.command_grammar
    if resolved == "H60B0":
        from .h60b0_controls import build_static

        return build_static(mask, rgb=(red, green, blue))
    if resolved == "H6072-legacy":
        return _build_h6072_legacy_colour(mask, (red, green, blue), 0, (0, 0, 0))
    if resolved in WHOLE_BULB_GRAMMARS:
        return _build_whole_bulb_static_colour(mask, (red, green, blue), 0, profile)
    if resolved == "H6179":
        if mask != 0:
            raise ValueError("H6179 static colour is inherently whole-device and has no segment mask")
        return _build_h6179_static_colour(
            direct=(red, green, blue),
            kelvin=0,
            preview=(0, 0, 0),
        )
    if resolved in {"H6046", "H6099", "H6199"}:
        root_type = _COMMAND_ROOTS[resolved][1]
        root = root_type()
        root.header = b"\x33"
        root.opcode = root_type.CommandOp.mode
        mode = _child(root_type.ModeBody, root)
        mode.sub_mode = root_type.ModeSel.static_colour
        detail = _child(root_type.StaticColourBody, mode)
        detail.operation = root_type.StaticOperation.colour
        detail.red = max(0, min(255, red))
        detail.green = max(0, min(255, green))
        detail.blue = max(0, min(255, blue))
        detail.kelvin = 0
        detail.preview = _rgb(detail, 0, 0, 0)
        detail.segment_mask = mask
        if resolved == "H6046":
            detail.unknown_tail = bytes(5)
        mode.detail = detail
        root.body = mode
        return _serialize_xor(root)

    if resolved not in {"H1771", "H6072", "H607C", "H617A", "H7020", "H705A"}:
        raise ValueError(f"{model} has no generated static-colour grammar")
    return _build_h617a_static_colour(
        mask,
        direct=(red, green, blue),
        kelvin=0,
        preview=(0, 0, 0),
        root_type=(_extended_static_root(profile) or _COMMAND_ROOTS[resolved])[1],
    )


def build_colour_temperature(
    kelvin: int,
    mask: int,
    model: str = "H617A",
    *,
    profile: ModelProfile | None = None,
) -> bytes:
    profile = profile or get_profile(model)
    value = max(profile.min_color_temp_kelvin, min(profile.max_color_temp_kelvin, kelvin))
    preview = table_kelvin_rgb(value)
    resolved = profile.command_grammar
    if resolved == "H60B0":
        from .h60b0_controls import build_static

        return build_static(mask, rgb=preview, kelvin=value)
    if resolved == "H6072-legacy":
        return _build_h6072_legacy_colour(mask, KELVIN_DIRECT_RGB, value, preview)
    if resolved in WHOLE_BULB_GRAMMARS:
        return _build_whole_bulb_static_colour(mask, KELVIN_DIRECT_RGB, value, profile)
    if resolved == "H6179":
        if mask != 0:
            raise ValueError("H6179 colour temperature is inherently whole-device and has no segment mask")
        return _build_h6179_static_colour(
            direct=KELVIN_DIRECT_RGB,
            kelvin=value,
            preview=preview,
        )
    if resolved in {"H6046", "H6099", "H6199"}:
        root_type = _COMMAND_ROOTS[resolved][1]
        root = root_type()
        root.header = b"\x33"
        root.opcode = root_type.CommandOp.mode
        mode = _child(root_type.ModeBody, root)
        mode.sub_mode = root_type.ModeSel.static_colour
        detail = _child(root_type.StaticColourBody, mode)
        detail.operation = root_type.StaticOperation.colour
        detail.red, detail.green, detail.blue = KELVIN_DIRECT_RGB
        detail.kelvin = value
        detail.preview = _rgb(detail, *preview)
        detail.segment_mask = mask
        if resolved == "H6046":
            detail.unknown_tail = bytes(5)
        mode.detail = detail
        root.body = mode
        return _serialize_xor(root)

    if resolved not in {"H1771", "H6072", "H607C", "H617A", "H7020", "H705A"}:
        raise ValueError(f"{model} has no generated colour-temperature grammar")
    return _build_h617a_static_colour(
        mask,
        direct=tuple(getattr(_COMMAND_ROOTS[resolved][1](), "kelvin_direct_rgb", KELVIN_DIRECT_RGB)),
        kelvin=value,
        preview=preview,
        root_type=(_extended_static_root(profile) or _COMMAND_ROOTS[resolved])[1],
    )


def build_segment_brightness(
    mask: int,
    percent: int,
    model: str = "H617A",
    *,
    profile: ModelProfile | None = None,
) -> bytes:
    value = max(0, min(100, percent))
    profile = profile or get_profile(model)
    resolved = profile.command_grammar
    if resolved == "H60B0":
        from .h60b0_controls import build_level

        return build_level(mask, value)
    if resolved == "H6179":
        raise ValueError("H6179 has no segment-brightness operation")
    if resolved in {"H6046", "H6099", "H6199"}:
        root_type = _COMMAND_ROOTS[resolved][1]
        root = root_type()
        root.header = b"\x33"
        root.opcode = root_type.CommandOp.mode
        mode = _child(root_type.ModeBody, root)
        mode.sub_mode = root_type.ModeSel.static_colour
        detail = _child(root_type.StaticColourBody, mode)
        detail.operation = root_type.StaticOperation.brightness
        detail.brightness_percent = value
        detail.brightness_segment_mask = mask
        if resolved == "H6046":
            detail.unknown_tail = bytes(12)
        mode.detail = detail
        root.body = mode
        return _serialize_xor(root)

    if resolved not in {"H1771", "H6072", "H607C", "H617A", "H7020", "H705A"}:
        raise ValueError(f"{model} has no generated segment-brightness grammar")
    root_type = (_extended_static_root(profile) or _COMMAND_ROOTS[resolved])[1]
    root = root_type()
    root.header = b"\x33"
    root.opcode = root_type.CommandOp.multi
    multi = _child(root_type.MultiCmd, root)
    multi.sub = root_type.MultiSub.static
    extended = root_type is H61f5ExtendedStaticWrite
    component = (
        CommandWrite if root_type in {H6072CommandWrite, H607cCommandWrite, H61f5ExtendedStaticWrite} else root_type
    )
    static = (
        component.StaticCmd(extended, None, multi, multi._root)
        if component is CommandWrite
        else _child(component.StaticCmd, multi)
    )
    static.static_sub = 2
    brightness = (
        component.StaticBrightness(extended, None, static, static._root)
        if component is CommandWrite
        else _child(component.StaticBrightness, static)
    )
    brightness.percent = value
    segment_mask = _child(component.ExtendedSegmentMask if extended else component.SegmentMask, brightness)
    segment_mask.bits = mask
    brightness.mask = segment_mask
    if hasattr(brightness, "tail_size"):
        brightness.unknown_tail = bytes(brightness.tail_size)
    elif root_type is H7020CommandWrite:
        brightness.unknown_tail = bytes(10)
    elif root_type is H1771CommandWrite:
        brightness.unknown_tail = bytes(12)
    static.static_body = brightness
    multi.sub_body = static
    root.body = multi
    return _serialize_xor(root)


def build_video_mode(
    video_mode: str,
    full_screen: bool,
    saturation: int,
    sound_effects: bool,
    softness: int,
    model: str,
    *,
    values: Mapping[str, Any] | None = None,
    profile: ModelProfile | None = None,
) -> bytes:
    profile = profile or get_profile(model)
    if video_mode not in profile.video_modes:
        raise ValueError(f"{model} does not support video mode {video_mode}")
    profile.validate_video_saturation(saturation)
    grammar = profile.video_grammar
    parameters = validate_video_parameters(grammar, values or {})
    if grammar == "H605C-video":
        if type(full_screen) is not bool or type(sound_effects) is not bool:
            raise ValueError("video region and sound effects require booleans")
        if type(softness) is not int or not profile.video_softness_min <= softness <= profile.video_softness_max:
            raise ValueError("video softness is outside model limits")
        root = H605cVideoCommand()
        root.header, root.opcode, root.mode = b"\x33", b"\x05", b"\x00"
        detail = _child(H605cVideoCommand.VideoBody, root)
        detail.region = root.VideoRegion.all if full_screen else root.VideoRegion.part
        detail.source = root.VideoSource[video_mode]
        detail.saturation, detail.sound_effects, detail.softness = saturation, int(sound_effects), softness
        detail.reserved, detail.reserved_end, detail.unknown_tail = 0, 0, bytes(5)
        for field, value in parameters.items():
            setattr(detail, field, value)
        root.detail = detail
        return _serialize_xor(root)
    if grammar == "H66A0-video":
        if video_mode not in H66a0VideoCommand.VideoSource.__members__:
            raise ValueError("invalid video source")
        root = H66a0VideoCommand()
        root.header, root.opcode, root.mode = b"\x33", b"\x05", b"\x00"
        detail = _child(H66a0VideoCommand.VideoBody, root)
        detail.source = H66a0VideoCommand.VideoSource[video_mode]
        detail.picture_preset = H66a0VideoCommand.PicturePreset[parameters["picture_preset"]]
        detail.opaque = parameters["opaque"]
        detail.saturation = saturation
        if type(sound_effects) is not bool or type(softness) is not int or not 0 <= softness <= 100:
            raise ValueError("invalid video sound effects or softness")
        detail.sound_effects, detail.softness = int(sound_effects), softness
        root.detail = detail
        return _serialize_xor(root)
    if grammar not in {"H6099", "H6199"}:
        raise ValueError(f"{model} has no generated video-mode grammar")
    if video_mode not in {"movie", "game"}:
        raise ValueError(f"{model} video mode {video_mode} is not supported by the H6199 grammar")
    root_type = _COMMAND_ROOTS[grammar][1]
    root = root_type()
    root.header = b"\x33"
    root.opcode = root_type.CommandOp.mode
    mode = _child(root_type.ModeBody, root)
    mode.sub_mode = root_type.ModeSel.video
    detail = _child(root_type.VideoBody, mode)
    detail.region = root_type.VideoRegion.all if full_screen else root_type.VideoRegion.part
    detail.source = root_type.VideoSource.game if video_mode == "game" else root_type.VideoSource.movie
    detail.saturation = saturation
    detail.sound_effects = int(sound_effects)
    detail.softness = max(1, min(100, softness))
    if grammar == "H6099":
        detail.sound_type = b"\x02"
    else:
        detail.relative_brightness_percent = 0
    mode.detail = detail
    root.body = mode
    return _serialize_xor(root)


def validate_video_parameters(grammar: str | None, values: Mapping[str, Any]) -> dict[str, Any]:
    """Validate complete grammar-specific values; unknown bytes have no defaults."""
    if grammar == "H605C-video":
        fields = {"left_percent", "top_percent", "right_percent", "bottom_percent"}
        if set(values) != fields:
            raise ValueError("video requires complete edge brightness values; refresh the device first")
        if any(type(value) is not int or not 0 <= value <= 100 for value in values.values()):
            raise ValueError("video edge brightness must be from 0 to 100")
    elif grammar == "H66A0-video":
        if set(values) != {"picture_preset", "opaque"}:
            raise ValueError("video requires picture_preset and opaque values; refresh the device first")
        if (
            not isinstance(values["picture_preset"], str)
            or values["picture_preset"] not in H66a0VideoCommand.PicturePreset.__members__
        ):
            raise ValueError("invalid video picture_preset")
        if type(values["opaque"]) is not int or not 0 <= values["opaque"] <= 255:
            raise ValueError("video opaque value must be a byte")
    elif values:
        raise ValueError("video grammar does not support these values")
    return dict(values)


def video_parameter_read_domain(grammar: str | None) -> ReadDomain | None:
    """The independent register that can recover mandatory inline values."""
    return ReadDomain.RELATIVE_BRIGHTNESS if grammar == "H605C-video" else None


def video_parameters_from_brightness(grammar: str | None, values: tuple[int, ...]) -> dict[str, Any] | None:
    if video_parameter_read_domain(grammar) is not ReadDomain.RELATIVE_BRIGHTNESS:
        return None
    fields = ("left_percent", "top_percent", "right_percent", "bottom_percent")
    return validate_video_parameters(grammar, dict(zip(fields, values, strict=True)))


def video_parameters_from_detail(detail: Any, grammar: str | None) -> dict[str, Any] | None:
    if grammar == "H605C-video":
        return validate_video_parameters(
            grammar,
            {f"{zone}_percent": int(getattr(detail, f"{zone}_percent")) for zone in ("left", "top", "right", "bottom")},
        )
    if grammar != "H66A0-video":
        return None
    return validate_video_parameters(
        grammar, {"picture_preset": getattr(detail.picture_preset, "name", None), "opaque": int(detail.opaque)}
    )


def parse_video_command(frame: bytes, model: str, *, profile: ModelProfile | None = None) -> Any | None:
    return _parse_xor_frame(
        frame,
        (profile or get_profile(model)).video_grammar,
        {
            "H66A0-video": ("h66a0_video_command", H66a0VideoCommand),
            "H605C-video": ("h605c_video_command", H605cVideoCommand),
        },
    ).parsed


def build_white_balance(red: int, blue: int | None, model: str, *, flag: int = 1) -> bytes:
    profile = get_profile(model)
    if not profile.supports_white_balance:
        raise ValueError(f"{model} does not support white balance")
    if (grammar := _video_command_grammar(model, profile)) not in {"H6099", "H6199"}:
        raise ValueError(f"{model} has no generated white-balance grammar")
    root_type = _COMMAND_ROOTS[grammar][1]
    root = root_type()
    root.header = b"\x33"
    root.opcode = root_type.CommandOp.display_setting
    body = _child(root_type.DisplaySettingBody, root)
    if profile.video_white_balance_representation == "scalar":
        if blue is not None or type(red) is not int or not 0 <= red <= 255:
            raise ValueError("scalar white balance requires one byte")
        body.setting = root_type.DisplaySetting.scalar_white_balance
        body.len = 1
        payload = _child(root_type.ScalarWhiteBalancePayload, body)
        payload.value = red
    else:
        if type(flag) is not int or flag not in (0, 1):
            raise ValueError("position white balance requires a known auto/manual flag")
        if any(type(value) is not int or not 0 <= value <= 255 for value in (red, blue)):
            raise ValueError("position white balance requires red and blue bytes")
        body.setting = root_type.DisplaySetting.white_balance
        body.len = 3
        payload = _child(root_type.WhiteBalancePayload, body)
        payload.manual = flag
        payload.red = red
        payload.blue = blue
    payload.unknown_tail = b""
    body.payload = payload
    body.unknown_tail = bytes(15 - body.len)
    root.body = body
    return _serialize_xor(root)


def build_blank_screen(
    enabled: bool,
    model: str,
    detection: int = 2,
    low_brightness_duration_seconds: int = _BLANK_SCREEN_LOW_BRIGHTNESS_SECONDS,
    same_tone_duration_seconds: int = _BLANK_SCREEN_SAME_TONE_SECONDS,
) -> bytes:
    profile = get_profile(model)
    if not profile.supports_blank_screen:
        raise ValueError(f"{model} does not support blank-screen detection")
    if type(enabled) is not bool or type(detection) is not int or detection not in (1, 2):
        raise ValueError("blank-screen policy requires a boolean and detection 1 or 2")
    if any(
        type(value) is not int or not 0 <= value <= 0xFFFF
        for value in (low_brightness_duration_seconds, same_tone_duration_seconds)
    ):
        raise ValueError("blank-screen durations must be integer seconds in 0..65535")
    if (grammar := _video_command_grammar(model, profile)) not in {"H6099", "H6199"}:
        raise ValueError(f"{model} has no generated blank-screen grammar")
    root_type = _COMMAND_ROOTS[grammar][1]
    root = root_type()
    root.header = b"\x33"
    root.opcode = root_type.CommandOp.display_setting
    body = _child(root_type.DisplaySettingBody, root)
    body.setting = root_type.DisplaySetting.blank_screen
    body.len = 6
    payload = _child(root_type.BlankScreenPayload, body)
    payload.is_on = int(enabled)
    payload.detection = root_type.BlankScreenDetection(detection)
    payload.low_brightness_duration_seconds = low_brightness_duration_seconds
    payload.same_tone_duration_seconds = same_tone_duration_seconds
    payload.unknown_tail = b""
    body.payload = payload
    body.unknown_tail = bytes(15 - body.len)
    root.body = body
    return _serialize_xor(root)


def build_black_border(enabled: bool, model: str) -> bytes:
    profile = get_profile(model)
    if not profile.supports_black_border:
        raise ValueError(f"{model} does not support black-border removal")
    if type(enabled) is not bool:
        raise ValueError("black-border removal requires a boolean")
    grammar = _video_command_grammar(model, profile)
    if grammar != "H6099":
        raise ValueError(f"{model} has no generated black-border grammar")
    root_type = _COMMAND_ROOTS[grammar][1]
    root = root_type()
    root.header = b"\x33"
    root.opcode = root_type.CommandOp.display_setting
    body = _child(root_type.DisplaySettingBody, root)
    body.setting = root_type.DisplaySetting.black_border
    body.len = 1
    payload = _child(root_type.BlackBorderPayload, body)
    payload.is_on = int(enabled)
    payload.unknown_tail = b""
    body.payload = payload
    body.unknown_tail = bytes(15 - body.len)
    root.body = body
    return _serialize_xor(root)


def build_relative_brightness(
    left: int,
    top: int,
    right: int,
    bottom: int,
    model: str,
    strip_left: int | None = None,
    strip_right: int | None = None,
) -> bytes:
    profile = get_profile(model)
    if not profile.supports_relative_brightness:
        raise ValueError(f"{model} does not support relative brightness")
    if (grammar := _video_command_grammar(model, profile)) not in {"H6099", "H6199"}:
        raise ValueError(f"{model} has no generated relative-brightness grammar")
    root_type = _COMMAND_ROOTS[grammar][1]
    root = root_type()
    root.header = b"\x33"
    root.opcode = root_type.CommandOp.relative_brightness
    body = _child(root_type.RelativeBrightnessBody, root)
    body.selector = b"\x01"
    body.edge_count = len(profile.video_brightness_zones)
    if any((value is not None) != (body.edge_count == 6) for value in (strip_left, strip_right)):
        raise ValueError("brightness values must match the model topology")
    body.left_percent = max(0, min(100, left))
    body.top_percent = max(0, min(100, top))
    body.right_percent = max(0, min(100, right))
    body.bottom_percent = max(0, min(100, bottom))
    body.strip_left_percent = 0 if strip_left is None else max(0, min(100, strip_left))
    body.strip_right_percent = 0 if strip_right is None else max(0, min(100, strip_right))
    root.body = body
    return _serialize_xor(root)


def _music_mode_command(root_type: Any) -> tuple[Any, Any]:
    root = root_type()
    root.header = b"\x33"
    root.opcode = root_type.CommandOp.mode
    root.body = _child(root_type.ModeBody, root)
    root.body.sub_mode = root_type.ModeSel.music
    detail = _child(root_type.MusicBody, root.body)
    root.body.detail = detail
    return root, detail


def build_music_mode(
    mode_id: int,
    sensitivity: int,
    colour: tuple[int, int, int] | None,
    calm: bool,
    model: str = "H617A",
    *,
    profile: ModelProfile | None = None,
    selector_parameters: Mapping[str, int] | None = None,
) -> bytes:
    profile = profile or get_profile(model)
    if type(mode_id) is not int or music_slug_for(model, mode_id, profile=profile) not in profile.music_modes:
        raise ValueError(f"{model} does not support music mode {mode_id}")
    if (
        type(sensitivity) is not int
        or not profile.music_sensitivity_min <= sensitivity <= profile.music_sensitivity_max
    ):
        raise ValueError("music sensitivity is outside model limits")
    variant = music_variant(profile, mode_id)
    if not isinstance(calm, bool) or (calm and (variant is None or not variant.supports_style)):
        raise ValueError("music style is unsupported or invalid")
    if colour is not None and (
        not profile.supports_music_color
        or (variant is not None and not variant.supports_fixed_colour)
        or len(colour) != 3
        or any(type(channel) is not int or not 0 <= channel <= 255 for channel in colour)
    ):
        raise ValueError("fixed music colour is unsupported or invalid")
    resolved = profile.music_grammar or profile.command_grammar
    selector_parameters = selector_parameters or {}
    if resolved == "H6181":
        if selector_parameters:
            raise ValueError("Unsupported music selector parameter")
        root, detail = _music_mode_command(H6181CommandWrite)
        detail.mode = H6181CommandWrite.MusicMode(mode_id)
        detail.sensitivity = sensitivity
        if mode_id in (0, 1):
            detail.reserved = 0
            detail.has_fixed_colour = int(colour is not None)
            if colour is not None:
                detail.fixed_colour = _rgb(detail, *colour)
        detail.padding = bytes(detail.write_tail_size)
        return _serialize_xor(root)
    if resolved in {"H1771", "H60B0"}:
        if colour is not None or selector_parameters:
            raise ValueError("Native music selectors carry only mode and sensitivity")
        root_type = _COMMAND_ROOTS[resolved][1]
        root = root_type()
        root.header = b"\x33"
        root.opcode = root_type.CommandOp.multi
        root.body = _child(root_type.MultiCmd, root)
        root.body.sub = root_type.MultiSub.music
        root.body.sub_body = _child(root_type.MusicSelector, root.body)
        root.body.sub_body.mode = (H1771MusicBody if resolved == "H1771" else H60b0MusicBody).MusicMode(mode_id)
        root.body.sub_body.sensitivity = sensitivity
        root.body.sub_body.unknown_tail = bytes(14)
        return _serialize_xor(root)
    if resolved in {"H607C", "H60B2"}:
        if colour is not None or selector_parameters:
            raise ValueError("Native music selectors carry only mode and sensitivity")
        root_type = H607cMusicWrite if resolved == "H607C" else H60b2MusicWrite
        root = root_type()
        root.header = b"\x33\x05\x13"
        root.selector = _child(root_type.MusicSelector, root)
        root.selector.mode_id = (H607cMusicWrite if resolved == "H607C" else H60b2MusicBody).MusicMode(mode_id)
        root.selector.sensitivity = sensitivity
        root.selector.unknown_tail = bytes(14)
        return _serialize_xor(root)
    if resolved not in {"H7020", "H6046"} and selector_parameters:
        raise ValueError("Music selector parameters are unsupported by this grammar")
    if resolved in {"H6072", "H6076"}:
        return _build_h6076_music_selector(
            mode_id, sensitivity, colour, calm, root_type=_MUSIC_WRITE_ROOTS[resolved][1]
        )
    if resolved == "H6046":
        if selector_parameters.keys() - {"bar_mask"}:
            raise ValueError("Unsupported music selector parameter")
        root_type = _COMMAND_ROOTS[resolved][1]
        left, right = int(root_type.BarFlag.left), int(root_type.BarFlag.right)
        mask = selector_parameters.get("bar_mask", left | right)
        if type(mask) is not int or mask not in (left, right, left | right):
            raise ValueError("Music bar mask must target left, right or both")
        root, detail = _music_mode_command(root_type)
        detail.mode = root_type.MusicMode(mode_id)
        detail.sensitivity = sensitivity
        if variant is not None and variant.supports_fixed_colour:
            detail.is_calm = int(calm)
            detail.has_fixed_colour = int(colour is not None)
            if colour is not None:
                detail.bar_mask = mask
                detail.fixed_colour = _rgb(detail, *colour)
        detail.unknown_tail = bytes(detail.write_tail_size)
        return _serialize_xor(root)
    if resolved == "H7020":
        allowed = {"rhythm_response"} if mode_id == 3 else set()
        if selector_parameters.keys() - allowed:
            raise ValueError("Unsupported music selector parameter")
        response = selector_parameters.get("rhythm_response", 1 if mode_id == 3 else 0)
        if type(response) is not int or response not in (0, 1):
            raise ValueError("Rhythm response must be 0 or 1")
        root = H7020CommandWrite()
        root.header = b"\x33"
        root.opcode = H7020CommandWrite.CommandOp.multi
        multi = _child(H7020CommandWrite.MultiCmd, root)
        multi.sub = H7020CommandWrite.MultiSub.music
        selector = _child(H7020CommandWrite.MusicSelector, multi)
        selector.mode_id = H7020CommandWrite.MusicMode(mode_id)
        selector.sensitivity = sensitivity
        selector.rhythm_response = response
        selector.has_fixed_colour = int(colour is not None)
        selector.rgb = _rgb(selector, *(colour or (0, 0, 0)))
        selector.unknown_tail = bytes(9)
        multi.sub_body = selector
        root.body = multi
        return _serialize_xor(root)
    if resolved in {"H6097", "H1A42", "H61F5", "H66A0", "H7025", "H705A"}:
        root_cls = _MUSIC_WRITE_ROOTS[resolved][1]
        root = root_cls()
        root.header, root.opcode, root.sub = b"\x33", b"\x05", b"\x13"
        selector = _child(root_cls.MusicSelector, root)
        selector.mode_id = root_cls.MusicMode(mode_id)
        selector.sensitivity = max(0, min(100, sensitivity)) if resolved in {"H1A42", "H61F5", "H66A0"} else sensitivity
        if selector.is_legacy:
            selector.style = int(calm)
            selector.has_fixed_colour = int(colour is not None)
            if colour is not None:
                selector.rgb = _rgb(selector, *colour)
        elif resolved in {"H6097", "H1A42", "H61F5", "H66A0"} and colour is not None:
            raise ValueError(f"new {resolved} music selectors omit fixed colour")
        selector.unknown_tail = bytes(selector.write_tail_size)
        root.selector = selector
        return _serialize_xor(root)
    if resolved == "H6179":
        root = H6179CommandWrite()
        root.header = b"\x33"
        root.opcode = H6179CommandWrite.CommandOpcode.mode
        mode = _child(H6179CommandWrite.ModeBody, root)
        mode.mode = H6179CommandWrite.ModeSelector.music
        detail = _child(H6179CommandWrite.MusicBody, mode)
        detail.effect_id = mode_id
        detail.sensitivity = sensitivity
        detail.colour_mode = int(colour is not None)
        if colour is not None:
            detail.fixed_colour = _rgb(detail, *colour)
        detail.opaque = bytes(detail.write_tail_size)
        mode.payload = detail
        root.body = mode
        return _serialize_xor(root)
    if resolved in {"H6099", "H6199"}:
        root_type = _COMMAND_ROOTS[resolved][1]
        root, detail = _music_mode_command(root_type)
        detail.mode = root_type.MusicMode(mode_id)
        detail.sensitivity = max(0, min(100, sensitivity))
        if resolved == "H6199" or detail.is_legacy:
            detail.is_calm = int(calm)
            detail.has_fixed_colour = int(colour is not None)
            detail.fixed_colour = _rgb(detail, *(colour or (0, 0, 0)))
        elif colour is not None:
            raise ValueError("new H6099 music selectors omit fixed colour")
        return _serialize_xor(root)

    if resolved != "H617A":
        raise ValueError(f"{model} has no generated music grammar")
    root = CommandWrite()
    root.header = b"\x33"
    root.opcode = CommandWrite.CommandOp.multi
    multi = _child(CommandWrite.MultiCmd, root)
    multi.sub = CommandWrite.MultiSub.music
    selector = _child(GoveeCommon.MusicSelector, multi)
    selector.mode_id = GoveeCommon.MusicMode(mode_id)
    selector.sensitivity = max(0, min(100, sensitivity))
    if selector.is_legacy:
        selector.style = int(calm)
        selector.has_fixed_colour = int(colour is not None)
        if colour is not None:
            selector.rgb = _rgb(selector, *colour)
    elif colour is not None:
        raise ValueError("new H617A music selectors omit fixed colour")
    multi.sub_body = selector
    root.body = multi
    return _serialize_xor(root)


def _build_h6076_music_selector(
    mode_id: int, sensitivity: int, colour: tuple[int, int, int] | None, calm: bool, *, root_type: Any = H6076MusicWrite
) -> bytes:
    root = root_type()
    root.header = b"\x33"
    root.opcode = b"\x05"
    root.sub = b"\x0f"
    selector = _child(H6076MusicWrite.MusicSelector, root)
    mode = H6076MusicWrite.MusicMode(mode_id)
    selector.mode_id = mode
    selector.sensitivity = sensitivity
    if mode.name in H6076MusicBody.MusicMode.__members__:
        settings = _child(H6076MusicWrite.OpaqueSettings, selector)
        settings.padding = bytes(14)
    else:
        rhythm = mode == H6076MusicWrite.MusicMode.rhythm
        settings = _child(H6076MusicWrite.RhythmSettings if rhythm else H6076MusicWrite.ColourSettings, selector)
        if rhythm:
            settings.dynamic = int(not calm)
        settings.has_fixed_colour = int(colour is not None)
        if colour is not None:
            settings.rgb = _rgb(settings, *colour)
        settings.padding = bytes(14 - (2 if rhythm else 1) - (3 if colour is not None else 0))
    selector.settings = settings
    root.selector = selector
    return _serialize_xor(root)
