"""Semantic source controls over the exact-model generated command grammar."""

from typing import Any

from .const import ModelProfile
from .protocol_core import H60b0CommandWrite as Command
from .protocol_core import _serialize_xor, new_child, new_rgb


def build_source(
    source: str,
    operation: str,
    *,
    value: int = 0,
    rgb: tuple[int, int, int] = (0, 0, 0),
    kelvin: int = 0,
    mask: int = 0,
) -> bytes:
    root = Command()
    root.header, root.opcode = b"\x33", Command.CommandOp.multi
    root.body = new_child(Command.MultiCmd, root)
    root.body.sub = Command.MultiSub.source_control
    command = new_child(Command.SourceCmd, root.body)
    root.body.sub_body = command
    command.source, command.operation = Command.Source[source], Command.Operation[operation]
    body_type = {
        "top_enabled": Command.TopBody,
        "side_enabled": Command.MaskedBody,
        "bottom_enabled": Command.BottomBody,
        "all": Command.PagedBody,
        "colour_sources": Command.PagedBody,
    }[source]
    body = body_type(command.operation, _parent=command, _root=root)
    command.detail = body
    if source == "bottom_enabled":
        if operation == "brightness":
            body.value, length = value, 1
        else:
            body.kelvin, length = kelvin, 2
    elif operation == "colour":
        body.colour = new_child(Command.Colour, body)
        body.colour.rgb = new_rgb(body.colour, rgb)
        body.colour.kelvin = kelvin
        length = 5
    elif source in {"all", "colour_sources"} and operation == "brightness":
        body.levels, length = [value] * 9, 9
    else:
        body.value, length = value, 1
    if source == "side_enabled" or source in {"all", "colour_sources"} and operation == "colour":
        body.mask = mask
        length += 2
    body.unknown_tail = bytes(14 - length)
    return _serialize_xor(root)


def build_static(mask: int, *, rgb: tuple[int, int, int], kelvin: int = 0) -> bytes:
    if mask == (1 << 9) - 1:
        from .generated_protocol_adapter import table_kelvin_rgb

        root = Command()
        root.header, root.opcode = b"\x33", Command.CommandOp.multi
        root.body = new_child(Command.MultiCmd, root)
        root.body.sub = Command.MultiSub.static
        detail = new_child(Command.WholeColour, root.body)
        root.body.sub_body = detail
        detail.rgb = new_rgb(detail, (255, 255, 255) if kelvin else rgb)
        detail.kelvin = kelvin
        detail.companion_rgb = new_rgb(detail, table_kelvin_rgb(kelvin) if kelvin else (0, 0, 0))
        detail.unknown_tail = bytes(8)
        return _serialize_xor(root)
    if mask == 1 << 8:
        return build_source("top_enabled", "colour", rgb=rgb, kelvin=kelvin)
    if mask & (1 << 8):
        raise ValueError("Mixed source colour requires separate source writes")
    return build_source("side_enabled", "colour", rgb=rgb, kelvin=kelvin, mask=mask)


def build_level(mask: int, value: int) -> bytes:
    if mask == 1 << 8:
        return build_source("top_enabled", "brightness", value=value)
    if mask == (1 << 9) - 1:
        return build_source("colour_sources", "brightness", value=value)
    if mask & (1 << 8):
        raise ValueError("Mixed source brightness requires separate source writes")
    return build_source("side_enabled", "brightness", value=value, mask=mask)


def validate_command(root: Any, profile: ModelProfile) -> bool:
    if profile.command_grammar != "H60B0":
        return False
    operation = getattr(root.opcode, "name", None)
    if operation == "zone_enable":
        if getattr(root.body.source, "name", None) not in profile.boolean_controls or root.body.enabled not in (0, 1):
            raise ValueError("Source power is outside the profile")
        return True
    if operation == "power_on_behaviour":
        if not profile.supports_power_on_behaviour or getattr(root.body.state, "name", None) is None:
            raise ValueError("Power-on behaviour is outside the profile")
        return True
    if operation != "multi" or root.body.sub != Command.MultiSub.source_control:
        return False
    if "source_control" not in (profile.command_operations or ()):
        raise ValueError("Source control is outside the profile")
    command = root.body.sub_body
    source, action = getattr(command.source, "name", None), getattr(command.operation, "name", None)
    if (
        source is None
        or action is None
        or source in {"top_enabled", "side_enabled", "bottom_enabled"}
        and source not in profile.boolean_controls
    ):
        raise ValueError("Unknown or unavailable source operation")
    if source == "colour_sources" and action == "colour":
        raise ValueError("Masked colour is not qualified for this source selector")
    detail = command.detail
    if source == "bottom_enabled":
        if (
            action != "brightness"
            and not profile.min_color_temp_kelvin <= detail.kelvin <= profile.max_color_temp_kelvin
        ):
            raise ValueError("Bottom Kelvin is outside the profile")
    elif action == "colour":
        if not profile.supports_rgb:
            raise ValueError("Source colour is outside the profile")
        if detail.colour.kelvin and (
            not profile.supports_color_temperature
            or not profile.min_color_temp_kelvin <= detail.colour.kelvin <= profile.max_color_temp_kelvin
            or detail.colour.kelvin % 100
        ):
            raise ValueError("Source Kelvin is outside the profile")
    elif action == "secondary" and source != "top_enabled":
        if source not in {"all", "colour_sources"} or not 1 <= detail.page <= 3:
            raise ValueError("Invalid source page")
    if action == "brightness":
        levels = detail.levels if source in {"all", "colour_sources"} else (detail.value,)
        if any(not 0 <= level <= 100 for level in levels):
            raise ValueError("Source brightness is outside 0-100")
    if source == "top_enabled" and action == "secondary" and not 0 <= detail.value <= 100:
        raise ValueError("Ripple speed is outside 0-100")
    if source == "side_enabled":
        if action == "secondary" or not 0 < detail.mask < 1 << 8:
            raise ValueError("Side mask is outside its eight positions")
    elif source in {"all", "colour_sources"} and action == "colour" and not 0 < detail.mask < 1 << 9:
        raise ValueError("Colour mask is outside its nine positions")
    return True


def source_values(root: Any) -> dict[str, int]:
    if root.opcode != Command.CommandOp.multi or root.body.sub != Command.MultiSub.source_control:
        return {}
    command = root.body.sub_body
    if command.source == Command.Source.bottom_enabled:
        return (
            {"bottom_brightness": int(command.detail.value)}
            if command.operation == Command.Operation.brightness
            else {"bottom_kelvin": int(command.detail.kelvin)}
        )
    if command.source == Command.Source.top_enabled and command.operation == Command.Operation.secondary:
        return {"ripple_speed": int(command.detail.value)}
    if command.source == Command.Source.top_enabled and command.operation == Command.Operation.colour:
        return {"top_kelvin": int(command.detail.colour.kelvin)}
    return {}


def source_readback(operation: Any, profile: ModelProfile) -> dict[str, int]:
    values = {
        "top_kelvin": int(operation.top_kelvin),
        "bottom_kelvin": int(operation.bottom_kelvin),
        "bottom_brightness": int(operation.bottom_brightness),
        "ripple_speed": int(operation.ripple_speed),
    }
    if (
        not 0 <= values["bottom_brightness"] <= 100
        or not 0 <= values["ripple_speed"] <= 100
        or values["bottom_kelvin"]
        and not profile.min_color_temp_kelvin <= values["bottom_kelvin"] <= profile.max_color_temp_kelvin
        or values["top_kelvin"]
        and not profile.min_color_temp_kelvin <= values["top_kelvin"] <= profile.max_color_temp_kelvin
    ):
        raise ValueError("Invalid native source state")
    return values
