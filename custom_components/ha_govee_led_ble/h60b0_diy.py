"""Revision-qualified H60B0 native DIY semantics."""

from importlib import import_module
from typing import Any, cast

from .native_effect import NativeDiyLayer, NativeEffect, NativeOpaqueLayer
from .protocol_core import new_child, new_rgb, serialize_native_body

H60b0DiyBody = cast(
    Any, import_module("custom_components.ha_govee_led_ble.generated_protocol.h60b0_diy_body").H60b0DiyBody
)
H60b0DiyV3 = cast(Any, import_module("custom_components.ha_govee_led_ble.generated_protocol.h60b0_diy_v3").H60b0DiyV3)


def _palette(parent: Any, colours: tuple[tuple[int, int, int], ...]) -> Any:
    value = new_child(H60b0DiyBody.Palette, parent)
    value.num_colours = len(colours)
    value.colours = [new_rgb(value, rgb) for rgb in colours]
    return value


def validate_h60b0_diy(content: NativeEffect, revision: int) -> None:
    content.__post_init__()
    if content.model == "H60B0" and content.family == 81:
        if revision not in (1, 2, 3):
            raise ValueError("Native combination requires a freshly resolved device Pact")
        return
    if content.revision == 1 and content.section_tail:
        raise ValueError("Older native DIY has no additional section extension")
    if content.model != "H60B0" or (revision not in (1, 2) if content.revision == 1 else revision != 3):
        raise ValueError("Native DIY revision does not match the freshly resolved device Pact")
    if any(isinstance(layer, NativeOpaqueLayer) for layer in content.layers):
        raise ValueError("Unqualified native parameters cannot be newly authored")
    for index, layer in enumerate(content.layers):
        if isinstance(layer, NativeOpaqueLayer):
            continue
        if not isinstance(layer, NativeDiyLayer) or layer.parameters:
            raise ValueError("Native DIY contains unrepresented parameters")
        layer.__post_init__()
        if content.revision == 1:
            ripple = content.family == 13 and index == 0
            admitted = {1, 2, 4, 11, 12} if ripple else set(range(1, 11))
            minimum = 1 if layer.kind in ({2, 11, 12} if ripple else {5, 8}) else 2
            if layer.enabled and (
                layer.kind not in admitted
                or not minimum <= len(layer.palette) <= 8
                or not 1 <= layer.speed <= 100
                or (ripple and (layer.direction not in (1, 2, 3) or layer.flag > 100))
                or (ripple and (layer.angle or layer.points or layer.temperatures or layer.secondary_palette))
                or (not ripple and (layer.flag or layer.direction or layer.angle or layer.points or layer.temperatures))
                or (layer.kind != 8 and layer.secondary_palette)
                or (layer.kind == 8 and not ripple and len(layer.secondary_palette) != 1)
            ):
                raise ValueError("Native DIY parameters do not match the selected source family")
        else:
            admitted = set(range(1, 8)) if index == 0 else set(range(1, 14)) if index == 1 else {1, 2, 3}
            if layer.kind not in admitted:
                raise ValueError("Native DIY family is not available on this source")
            directions = (
                (1, 2, 3)
                if index == 0
                else (1, 2)
                if index == 1 and layer.kind in (7, 10)
                else (3,)
                if index == 1 and layer.kind == 12
                else (0,)
            )
            if (
                index != 0
                and not layer.enabled
                or index != 0
                and layer.parameter
                or index != 2
                and layer.temperatures
                or not (index == 0 and layer.kind == 7)
                and layer.angle
                or not (index == 1 and layer.kind == 9)
                and layer.secondary_palette
                or layer.direction not in directions
                or index == 0
                and layer.parameter > 100
                or not (index == 1 and layer.kind in (9, 13) or index == 0 and layer.kind == 7)
                and layer.flag
                or index != 2
                and layer.kind not in (3, 5)
                and layer.points
            ):
                raise ValueError("Native source contains parameters its family does not encode")
            if layer.kind == 1 or index == 0 and not layer.enabled:
                continue
            if index == 0 and layer.kind == 7:
                if not 2700 <= layer.angle <= 6500 or not 0 <= layer.flag <= 100:
                    raise ValueError("Native top temperature is outside its supported range")
            elif index == 2:
                if (
                    not 1 <= len(layer.temperatures) <= 8
                    or len(layer.palette) != len(layer.temperatures)
                    or any(not 2700 <= value <= 6500 for value in layer.temperatures)
                    or not 1 <= layer.speed <= 100
                    or any(not 0 <= value <= 100 for value in layer.points)
                    or len(layer.points) == 2
                    and layer.points[0] > layer.points[1]
                ):
                    raise ValueError("Native bottom effect requires qualified temperature records")
            elif not 1 <= len(layer.palette) <= 8 or not 1 <= layer.speed <= 100:
                raise ValueError("Native colour effect requires speed and a palette")
    if content.revision == 3:
        top, side, bottom = cast(tuple[NativeDiyLayer, ...], content.layers)
        side_on, bottom_on = side.kind != 1, bottom.kind != 1
        top_on = top.kind != 1 if top.enabled else side_on
        if top_on and side_on and bottom_on:
            raise ValueError("Native DIY cannot enable all three sources together")


def _legacy_parameters(layer: NativeDiyLayer, parent: Any, ripple: bool) -> Any:
    value = H60b0DiyBody.Parameters(layer.kind, ripple, _parent=parent, _root=parent._root)
    value.variant, value.speed = layer.parameter, layer.speed
    value.palette = _palette(value, layer.palette)
    if layer.kind == 8 and not ripple:
        value.secondary_palette = _palette(value, layer.secondary_palette)
    if ripple:
        value.direction, value.flow_speed = layer.direction, layer.flag
    value.unknown_tail = layer.opaque
    return value


def _v3_colour(layer: NativeDiyLayer, parent: Any, side: bool) -> Any:
    value = H60b0DiyV3.ColourParameters(layer.kind, side, _parent=parent, _root=parent._root)
    value.speed = layer.speed
    if layer.kind in (3, 5):
        if len(layer.points) != 2 or not 0 <= layer.points[0] <= layer.points[1] <= 100:
            raise ValueError("Native pulse requires minimum and maximum brightness")
        value.minimum_brightness, value.maximum_brightness = layer.points
    if side and layer.kind in (7, 10, 12):
        value.direction = layer.direction
    if side and layer.kind == 9:
        if len(layer.secondary_palette) != 1:
            raise ValueError("Native shimmer requires one background colour")
        value.background = new_rgb(value, layer.secondary_palette[0])
    if side and layer.kind in (9, 13):
        if layer.flag not in (0, 1):
            raise ValueError("Native colourful setting must be a boolean")
        value.colourful = layer.flag
    value.num_colours = len(layer.palette)
    value.colours = [new_rgb(value, colour) for colour in layer.palette]
    value.unknown_tail = layer.opaque
    return value


def _v3_top(layer: NativeDiyLayer, parent: Any) -> Any:
    value = new_child(H60b0DiyV3.Top, parent)
    value.flow_speed, value.direction, value.enabled = layer.parameter, layer.direction, int(layer.enabled)
    value.unknown_tail = layer.opaque if not layer.enabled or layer.kind == 1 else b""
    if layer.enabled:
        value.family = layer.kind
        if layer.kind == 7:
            from .generated_protocol_adapter import table_kelvin_rgb

            value.body = new_child(H60b0DiyV3.Temperature, value)
            value.body.brightness, value.body.kelvin = layer.flag, layer.angle
            companion = table_kelvin_rgb(layer.angle)
            if companion == (0, 0, 0):
                raise ValueError("Native temperature requires a qualified Kelvin step")
            value.body.companion = new_rgb(value.body, companion)
            value.body.unknown_tail = layer.opaque
        elif layer.kind != 1:
            value.body = _v3_colour(layer, value, False)
    return value


def _v3_zone(layer: NativeDiyLayer, parent: Any, bottom: bool) -> Any:
    value = H60b0DiyV3.Zone(bottom, _parent=parent, _root=parent._root)
    value.family, value.unknown_tail = layer.kind, b""
    if layer.kind == 1:
        value.unknown_tail = layer.opaque
    elif bottom:
        body = H60b0DiyV3.TemperatureParameters(layer.kind, _parent=value, _root=value._root)
        if len(layer.points) != (2 if layer.kind == 3 else 1):
            raise ValueError("Native bottom effect requires its brightness bounds")
        body.speed, body.minimum_brightness = layer.speed, layer.points[0]
        if layer.kind == 3:
            body.maximum_brightness = layer.points[1]
        body.num_colours = len(layer.temperatures)
        body.colours = []
        from .generated_protocol_adapter import table_kelvin_rgb

        for kelvin in layer.temperatures:
            companion = table_kelvin_rgb(kelvin)
            if companion == (0, 0, 0):
                raise ValueError("Native temperature requires a qualified Kelvin step")
            colour = new_child(H60b0DiyV3.KelvinColour, body)
            colour.kelvin, colour.companion = kelvin, new_rgb(colour, companion)
            body.colours.append(colour)
        body.unknown_tail = layer.opaque
        value.body = body
    else:
        value.body = _v3_colour(layer, value, True)
    return value


def encode_h60b0_diy(content: NativeEffect) -> bytes:
    if content.family == 81:
        from .h60b0_effects import combined_upload_body, encode_combined_scene

        content.__post_init__()
        assert content.combined is not None
        return combined_upload_body(encode_combined_scene(content.combined))
    validate_h60b0_diy(content, content.revision)
    if any(isinstance(layer, NativeOpaqueLayer) for layer in content.layers):
        raise ValueError("Unqualified native parameters cannot be newly authored")
    layers = cast(tuple[NativeDiyLayer, ...], content.layers)
    if content.revision == 1:
        root = H60b0DiyBody()
        root.family = content.family
        if content.family == 13:
            root.body = new_child(H60b0DiyBody.Advanced, root)
            root.body.unknown_tail = content.opaque
            for name, layer, ripple in zip(("ripple", "side"), layers, (True, False), strict=True):
                section = H60b0DiyBody.Section(ripple, _parent=root.body, _root=root)
                section.family = layer.kind if layer.enabled else 0
                section.len_body = 0
                if layer.enabled:
                    section.body = _legacy_parameters(layer, section, ripple)
                    section.len_body = len(serialize_native_body(section.body))
                    if section.len_body > 255:
                        raise ValueError("Native DIY section exceeds its length field")
                setattr(root.body, name, section)
        else:
            if layers[0].kind != content.family or not layers[0].enabled or content.opaque:
                raise ValueError("Native single body must retain its enabled family")
            root.body = _legacy_parameters(layers[0], root, False)
            if content.family == 8:
                root.body.palette = _palette(root.body, layers[0].secondary_palette)
                root.body.secondary_palette = _palette(root.body, layers[0].palette)
        return serialize_native_body(root)
    root = H60b0DiyV3()
    root.body = new_child(H60b0DiyV3.Sections, root)
    root.unknown_tail, root.body.unknown_tail = content.opaque, content.section_tail
    root.body.top = _v3_top(layers[0], root.body)
    root.body.side = _v3_zone(layers[1], root.body, False)
    root.body.bottom = _v3_zone(layers[2], root.body, True)
    for name in ("top", "side", "bottom"):
        length = len(serialize_native_body(getattr(root.body, name)))
        if length > 255:
            raise ValueError("Native DIY section exceeds its length field")
        setattr(root.body, f"len_{name}", length)
    root.len_body = len(serialize_native_body(root.body))
    return serialize_native_body(root)
