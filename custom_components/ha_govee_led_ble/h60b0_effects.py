"""Semantic encoding for combined RGBIC and ripple effects."""

from importlib import import_module
from math import ceil
from typing import Any, cast

from kaitaistruct import KaitaiStructError

from .layered_scene import CatalogueRef, LayeredEffect, LayeredScene, RippleLayer
from .music_semantics import H60B0_ZONE_MUSIC_MODES, MusicVariant, MusicZone
from .protocol_core import adopt_native_body, native_body_length, new_child, new_rgb, serialize_native_body
from .scenes import SceneSpeed

H60b0SceneBody = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h60b0_scene_body").H60b0SceneBody,
)


def parse_combined_scene(payload: bytes) -> Any:
    try:
        root = H60b0SceneBody.from_bytes(payload)
        root._read()
        if not root.rgbic.num_records or not root.ripple.num_records:
            raise ValueError("Combined scene requires both effect engines")
        return root
    except (KaitaiStructError, EOFError, ValueError) as error:
        raise ValueError("Invalid combined RGBIC/ripple scene") from error


def combined_upload_body(payload: bytes) -> bytes:
    """Convert a canonical body without changing its input or section contents."""
    root = parse_combined_scene(payload)
    if root.len_rgbic < 2:
        raise ValueError("Combined scene has no RGBIC container")
    return (int(root.len_rgbic) - 1).to_bytes(2, "big") + payload[4:]


def decode_combined_scene(template: CatalogueRef, payload: bytes, *, speed_index: int | None = None) -> LayeredScene:
    from .layered_scene_decoder import _decode_layer

    root = parse_combined_scene(payload)
    return LayeredScene(
        template=template,
        effect=LayeredEffect(tuple(_decode_layer(record.body) for record in root.rgbic.records)),
        ripple_layers=tuple(
            RippleLayer(
                effect=int(body.effect),
                duration=int(body.duration),
                movement_speed=int(body.movement_speed),
                movement=int(body.movement),
                colour_mode=int(body.colour_mode),
                colour_speed=int(body.colour_speed),
                retention=int(body.retention),
                palette=tuple((int(c.red), int(c.green), int(c.blue)) for c in body.colours),
                opaque=body.unknown_tail,
            )
            for record in root.ripple.records
            for body in (record.body,)
        ),
        raw_param=payload,
        speed_index=speed_index,
    )


def encode_combined_scene(scene: LayeredScene) -> bytes:
    from .layered_scene_decoder import _encode_record

    if scene.template.sku != "H60B0" or scene.trailing_padding:
        raise ValueError("Combined scenes require an exact model and bounded sections")
    if not scene.ripple_layers or not scene.effect.layers:
        raise ValueError("Combined scene requires both effect engines")
    root = parse_combined_scene(scene.raw_param) if scene.raw_param else H60b0SceneBody()
    root.marker = b"\x51"
    if not scene.raw_param:
        root.rgbic = new_child(H60b0SceneBody.RgbicSection, root)
        root.rgbic.marker, root.rgbic.unknown_tail = b"\x0a", b""
        root.ripple = new_child(H60b0SceneBody.RippleSection, root)
        root.ripple.unknown_tail = root.unknown_tail = b""
    root.rgbic.num_records = len(scene.effect.layers)
    root.rgbic.records = [
        _encode_record(H60b0SceneBody.RgbicRecord, root.rgbic, layer) for layer in scene.effect.layers
    ]
    for record in root.rgbic.records:
        record.len_body = len(serialize_native_body(record.body))
        if record.len_body > 255:
            raise ValueError("Combined RGBIC record exceeds its length field")
    root.ripple.num_records = len(scene.ripple_layers)
    root.ripple.records = []
    for layer in scene.ripple_layers:
        layer.__post_init__()
        record = new_child(H60b0SceneBody.RippleRecord, root.ripple)
        body = new_child(H60b0SceneBody.RippleParameters, record)
        for name in ("effect", "duration", "movement_speed", "movement", "colour_mode", "colour_speed", "retention"):
            setattr(body, name, getattr(layer, name))
        body.num_colours = len(layer.palette)
        body.colours = [new_rgb(body, colour) for colour in layer.palette]
        body.unknown_tail = layer.opaque
        record.body = body
        record.len_body = len(serialize_native_body(body))
        if record.len_body > 255:
            raise ValueError("Combined ripple record exceeds its length field")
        root.ripple.records.append(record)
    root.len_rgbic = len(serialize_native_body(root.rgbic))
    root.len_ripple = len(serialize_native_body(root.ripple))
    return serialize_native_body(root)


def apply_combined_speed(payload: bytes, speed: SceneSpeed, index: int) -> bytes:
    from .native_scenes import _speed_value

    if not 0 <= index < speed.option_count:
        raise ValueError("Scene speed index is outside its documented options")
    root = parse_combined_scene(payload)
    for page in speed.pages:
        if not (page.move_in or page.move_all or page.colour_speed or page.brightness_speeds):
            continue
        if not 0 <= page.page < len(root.rgbic.records):
            raise ValueError("Speed targets a missing RGBIC page")
        body = root.rgbic.records[page.page].body
        for values, target, field in (
            (page.move_in, body.selected_area_movement, "speed"),
            (page.move_all, body.overall_movement, "speed"),
            (page.colour_speed, body, "colour_speed"),
        ):
            if values:
                setattr(target, field, _speed_value(values, index))
        for brightness in page.brightness_speeds:
            if not 0 <= brightness.block < len(body.brightness_blocks):
                raise ValueError("Speed targets a missing brightness block")
            body.brightness_blocks[brightness.block].brightness_speed = _speed_value(brightness.values, index)
    for ripple_index, record in enumerate(root.ripple.records):
        selected = next((page for page in reversed(speed.pages) if page.page == ripple_index), None)
        if selected is not None:
            if selected.ripple_colour_speed:
                record.body.colour_speed = _speed_value(selected.ripple_colour_speed, index)
            if selected.ripple_movement_speed:
                record.body.movement_speed = _speed_value(selected.ripple_movement_speed, index)
    return serialize_native_body(root)


def encode_h60b0_music_parameters(
    variant: MusicVariant,
    parameters: dict[str, int | bool | str],
    palette: list[tuple[int, int, int]] | None,
    calm: bool | None,
    physical_ic_count: int | None,
    *,
    preserve_companions: bool = False,
) -> bytes:
    from .music_protocol import H60b0MusicBody
    from .protocol_music_params import parse_music_parameters

    root = parse_music_parameters(variant, variant.template)
    if root.mode == H60b0MusicBody.MusicMode.combined:
        if parameters or palette is not None or calm:
            raise ValueError("Combined music requires independent side/ripple edits")
        return variant.template
    fields = root.body
    if palette is not None:
        if (
            variant.palette_bounds is None
            or not variant.palette_bounds[0] <= len(palette) <= variant.palette_bounds[1]
            or any(len(rgb) != 3 or any(type(c) is not int or not 0 <= c <= 255 for c in rgb) for rgb in palette)
        ):
            raise ValueError("Invalid exact-model music palette")
        fields.num_palette = len(palette)
        fields.palette = [new_rgb(fields, rgb) for rgb in palette]
    if variant.supports_style:
        if calm is not None:
            fields.tail.style = H60b0MusicBody.Style.calm if calm else H60b0MusicBody.Style.dynamic
    elif calm:
        raise ValueError("Music mode does not support a style")
    for spec in variant.parameters:
        if spec.profile_key not in parameters:
            continue
        value = int(parameters[spec.profile_key])
        if spec.wire_field == "background":
            fields.tail.background = new_rgb(fields.tail, (value >> 16, (value >> 8) & 255, value & 255))
        else:
            setattr(fields.tail, spec.wire_field, value)
    if root.mode == H60b0MusicBody.MusicMode.hopping and not preserve_companions:
        if physical_ic_count is None or physical_ic_count < 1:
            raise ValueError("Hopping requires an observed physical IC count")
        fields.tail.piece_count_min = max(1, ceil(physical_ic_count * 3 / 25))
        fields.tail.piece_count_max = max(1, ceil(physical_ic_count * 2 / 5))
    return serialize_native_body(root)


def h60b0_music_zones(body: bytes) -> tuple[MusicZone, ...]:
    from .music_protocol import H60b0MusicBody

    root = H60b0MusicBody.from_bytes(body)
    root._read()
    if root.mode != H60b0MusicBody.MusicMode.combined:
        raise ValueError("Music is not a combined body")
    if root.body.unknown_tail:
        raise ValueError("Source editing cannot discard an unqualified combined-music suffix")
    return tuple(
        MusicZone(
            name,
            zone.mode.name,
            body=bytes((int(zone.mode),)) + serialize_native_body(zone.body),
            calm=bool(zone.body.tail.style == H60b0MusicBody.Style.calm) if zone.mode in (48, 49) else None,
        )
        for name, zone in (("side", root.body.side), ("ripple", root.body.ripple))
    )


def encode_h60b0_music_zones(profile: Any, zones: tuple[MusicZone, ...]) -> bytes:
    from dataclasses import replace

    from .music_protocol import H60b0MusicBody, music_codebook
    from .music_semantics import compile_music_parameters, music_variant
    from .protocol_music_params import encode_music_parameters, parse_music_parameters

    if len(zones) != 2 or tuple(zone.id for zone in zones) != ("side", "ripple"):
        raise ValueError("Combined music requires side then ripple")
    root = H60b0MusicBody()
    root.mode = H60b0MusicBody.MusicMode.combined
    root.body = new_child(H60b0MusicBody.CombinedParameters, root)
    root.body.unknown_tail = b""
    codebook = music_codebook(profile)
    for (name, modes), zone in zip(H60B0_ZONE_MUSIC_MODES, zones, strict=True):
        code = codebook.get(zone.mode, -1)
        if zone.mode not in modes:
            raise ValueError("Music mode is not eligible for this source")
        variant = music_variant(profile, code)
        if variant is None:
            raise ValueError("Music zone has no qualified parameter body")
        if zone.calm is not None and not variant.supports_style:
            raise ValueError("Music source does not expose a style control")
        if zone.body is not None:
            parse_music_parameters(variant, zone.body)
            variant = replace(variant, template=zone.body)
        parameters = compile_music_parameters(zone.parameters, code, profile)
        if zone.body is not None:
            parameters = {key: parameters[key] for key in zone.parameters}
        body = encode_music_parameters(
            variant,
            parameters,
            palette=None if zone.palette is None else list(zone.palette),
            calm=zone.calm,
            physical_ic_count=profile.physical_ic_count,
            preserve_companions=zone.body is not None,
        )
        child = parse_music_parameters(variant, body)
        section = new_child(H60b0MusicBody.Zone, root.body)
        section.mode = child.mode
        section.body = adopt_native_body(child.body, section)
        section.len_parameters = native_body_length(section.body)
        if section.len_parameters > 255:
            raise ValueError("Music source exceeds its length field")
        setattr(root.body, name, section)
    return serialize_native_body(root)
