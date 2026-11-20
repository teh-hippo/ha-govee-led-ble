"""Generated codecs for complete native projector effects."""

from typing import Any

from kaitaistruct import KaitaiStructError

from .const import ModelProfile
from .native_effect import NativeEffect
from .projector import ProjectorAppearance, ProjectorLayer, ProjectorSource, ProjectorStars
from .protocol_core import (
    H600aCommandWrite,
    StatusQuery,
    _parse_xor_frame,
    _serialize_xor,
    new_child,
    new_rgb,
    serialize_native_body,
)
from .protocol_core import H6093Projector as Wire
from .scenes import SceneSpeed
from .transport import fragment_a3


def _boolean(value: int) -> bool:
    if value not in (0, 1):
        raise ValueError("Invalid projector switch")
    return bool(value)


def _source(value: Any) -> ProjectorSource:
    return ProjectorSource(
        _boolean(value.enabled),
        int(value.brightness),
        int(value.pattern),
        int(value.speed),
        tuple((int(rgb.red), int(rgb.green), int(rgb.blue)) for rgb in value.palette.colours),
    )


def _stars(value: Any) -> ProjectorStars:
    return ProjectorStars(
        enabled=_boolean(value.enabled),
        brightness=int(value.brightness),
        flicker_enabled=_boolean(value.flicker_enabled),
        flicker_speed=int(value.flicker_speed),
        movement_enabled=_boolean(value.movement_enabled),
        movement_speed=int(value.movement_speed),
    )


def decode_projector(payload: bytes) -> NativeEffect:
    try:
        root = Wire.from_bytes(payload)
        root._read()
        layers = tuple(
            ProjectorLayer(
                movement_speed=int(record.body.aurora.movement_speed),
                direction=int(record.body.aurora.direction),
                coarse=_source(record.body.aurora.first),
                fine=_source(record.body.aurora.second)
                if record.body.aurora.control == Wire.PaletteControl.separate
                else None,
                stars=_stars(record.body.stars),
                duration=int(record.body.duration),
                opaque=bytes(record.body.opaque_tail),
            )
            for record in root.layers
        )
        return NativeEffect(
            model="H6093",
            family=int(Wire.CatalogueFamily.projector),
            layers=(),
            projector_layers=layers,
            opaque=bytes(root.opaque_tail),
        )
    except (EOFError, ValueError, KaitaiStructError) as error:
        raise ValueError("Invalid native projector body") from error


def _palette(colours: tuple[tuple[int, int, int], ...], parent: Any) -> Any:
    palette = new_child(Wire.Palette, parent)
    palette.num_colours = len(colours)
    palette.colours = [new_rgb(palette, rgb) for rgb in colours]
    return palette


def _write_source(value: ProjectorSource, parent: Any) -> Any:
    source = new_child(Wire.Source, parent)
    source.enabled = int(value.enabled)
    source.brightness, source.pattern, source.speed = value.brightness, value.pattern, value.speed
    source.palette = _palette(value.palette, source)
    return source


def _write_stars(value: ProjectorStars, parent: Any) -> Any:
    stars = new_child(Wire.Stars, parent)
    stars.enabled, stars.brightness = int(value.enabled), value.brightness
    stars.flicker_enabled, stars.flicker_speed = int(value.flicker_enabled), value.flicker_speed
    stars.movement_enabled, stars.movement_speed = int(value.movement_enabled), value.movement_speed
    return stars


def encode_projector(content: NativeEffect) -> bytes:
    content.__post_init__()
    if content.model != "H6093":
        raise ValueError("Projector content does not match the model")
    root = Wire()
    root.marker = b"\x48"
    root.num_layers = len(content.projector_layers)
    root.layers = []
    root.opaque_tail = content.opaque
    for layer in content.projector_layers:
        record = new_child(Wire.LayerRecord, root)
        body = new_child(Wire.Layer, record)
        record.body = body
        body.aurora = new_child(Wire.Aurora, body)
        body.aurora.movement_speed, body.aurora.direction = layer.movement_speed, layer.direction
        body.aurora.control = Wire.PaletteControl.unified if layer.fine is None else Wire.PaletteControl.separate
        body.aurora.first = _write_source(layer.coarse, body.aurora)
        if layer.fine is not None:
            body.aurora.second = _write_source(layer.fine, body.aurora)
        body.stars = _write_stars(layer.stars, body)
        body.duration, body.opaque_tail = layer.duration, layer.opaque
        record.len_body = len(serialize_native_body(body))
        root.layers.append(record)
    return serialize_native_body(root)


def apply_projector_speed(payload: bytes, speed: SceneSpeed, index: int) -> bytes:
    if not 0 <= index < speed.option_count:
        raise ValueError("Projector Speed position is outside the available options")
    root = Wire.from_bytes(payload)
    root._read()
    options = speed.projector_speeds[index]
    if len(options) > root.num_layers:
        raise ValueError("Projector Speed addresses an absent scene layer")
    for record, values in zip(root.layers, options, strict=False):
        body = record.body
        body.aurora.movement_speed = values.aurora[0]
        if len(values.aurora) > 1 and body.aurora.first.enabled:
            body.aurora.first.speed = values.aurora[1]
        if (
            len(values.aurora) > 2
            and body.aurora.control == Wire.PaletteControl.separate
            and body.aurora.second.enabled
        ):
            body.aurora.second.speed = values.aurora[2]
        if body.stars.flicker_enabled:
            body.stars.flicker_speed = values.stars[0]
        if body.stars.movement_enabled and len(values.stars) > 1:
            # Native scene preparation targets flicker again; preserve that distinct contract.
            body.stars.flicker_speed = values.stars[1]
    return serialize_native_body(root)


def decode_appearance(value: Any) -> ProjectorAppearance:
    if value.expanded and value.control not in (Wire.AppearanceControl.unified, Wire.AppearanceControl.separate):
        raise ValueError("Unknown projector appearance palette control")

    def palette(data: Any) -> tuple[tuple[int, int, int], ...]:
        return tuple((int(rgb.red), int(rgb.green), int(rgb.blue)) for rgb in data.colours)

    separate = value.expanded and value.control == Wire.AppearanceControl.separate
    return ProjectorAppearance(
        _stars(value.stars),
        _boolean(value.aurora_enabled),
        int(value.movement_speed),
        int(value.brightness),
        int(value.pattern),
        int(value.effect_speed),
        palette(value.coarse.palette if separate else value.palette),
        palette(value.fine.palette) if separate else None,
        _boolean(value.coarse.enabled) if separate else True,
        _boolean(value.fine.enabled) if separate else True,
        bytes(value.opaque_tail),
    )


def build_appearance(value: ProjectorAppearance, profile: ModelProfile) -> tuple[bytes, ...]:
    if profile.projector_grammar != "H6093" or profile.projector_control_revision is None:
        raise ValueError("Projector appearance requires a qualified control revision")
    expanded = profile.projector_control_revision == 1
    if value.fine is not None and not expanded:
        raise ValueError("Separate projector palettes are unavailable on this revision")
    root = Wire.Appearance(expanded, _root=Wire())
    root.stars = _write_stars(value.stars, root)
    root.aurora_enabled = int(value.enabled)
    root.movement_speed, root.brightness = value.movement_speed, value.brightness
    root.pattern, root.effect_speed = value.pattern, value.effect_speed
    root.opaque_tail = value.opaque
    if expanded:
        root.control = Wire.AppearanceControl.unified if value.fine is None else Wire.AppearanceControl.separate
    if value.fine is None:
        root.palette = _palette(value.coarse, root)
    else:
        for name, enabled, colours in (
            ("coarse", value.coarse_enabled, value.coarse),
            ("fine", value.fine_enabled, value.fine),
        ):
            source = new_child(Wire.AppearancePalette, root)
            source.enabled = int(enabled)
            source.palette = _palette(colours, source)
            setattr(root, name, source)
    activation = Wire.Activation()
    activation.header, activation.opcode = b"\x33", Wire.Command.mode
    activation.body = new_child(Wire.ActivationBody, activation)
    activation.body.sub_mode, activation.body.opaque_tail = Wire.UploadKind.appearance, bytes(16)
    return (
        *fragment_a3(int(Wire.UploadKind.appearance), serialize_native_body(root)),
        _serialize_xor(activation),
    )


def build_appearance_query(profile: ModelProfile) -> bytes:
    if profile.projector_grammar != "H6093" or profile.projector_control_revision != 0:
        raise ValueError("This projector revision has no qualified appearance readback")
    query = Wire.ReadQuery()
    query.header, query.opaque_tail = b"\xac\x03\x05\x0c", bytes(15)
    return _serialize_xor(query)


def projection_power_wire(packet: bytes) -> bytes:
    command = _parse_xor_frame(packet, "basic", {"basic": ("h600a_command_write", H600aCommandWrite)}).parsed
    if command is not None and command.opcode == H600aCommandWrite.CommandOp.power:
        wire = Wire.SettingWrite()
        wire.header, wire.opcode = b"\x33", Wire.Command.setting
        wire.body = new_child(Wire.SettingBody, wire)
        wire.body.selector, wire.body.enabled = Wire.Setting.projection_power, command.body.is_on
        wire.body.opaque_tail = bytes(15)
        return _serialize_xor(wire)
    query = _parse_xor_frame(packet, "query", {"query": ("status_query", StatusQuery)}).parsed
    if query is not None and getattr(query.domain, "name", None) == "power":
        wire = Wire.PowerQuery()
        wire.header, wire.opaque_tail = b"\xaa\x34", bytes(17)
        return _serialize_xor(wire)
    return packet
