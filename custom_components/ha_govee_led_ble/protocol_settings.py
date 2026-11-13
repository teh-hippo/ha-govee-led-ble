"""Setting commands, qualified status queries and bulk response collection."""

from __future__ import annotations

from typing import Any

from kaitaistruct import KaitaiStructError

from .const import WHOLE_BULB_GRAMMARS, ModelProfile, ReadDomain, get_profile
from .protocol_commands import _video_command_grammar, table_kelvin_rgb
from .protocol_core import (
    _COMMAND_ROOTS,
    _STATUS_QUERY_ROOTS,
    CommandWrite,
    H60a6Control,
    H60aBulk,
    H60b0CommandWrite,
    H60b0StatusReply,
    H60b2Control,
    H605cVideoSettings,
    H607cControl,
    H1771Bulk,
    H1771CommandWrite,
    H1771StatusQuery,
    H6046CommandWrite,
    H6072CommandWrite,
    H6072StatusQuery,
    H6097Control,
    H6099CommandWrite,
    H6179CommandWrite,
    H7020CommandWrite,
    ProtocolParseRejection,
    ProtocolParseResult,
    StatusQuery,
    _child,
    _parse_xor_frame,
    _serialize_xor,
)
from .protocol_h6199 import INSTALLATION_DIRECTIONS

_NATIVE_SETTING_ROOTS = {"H607C": ("h607c_control", H607cControl), "H60B2": ("h60b2_control", H60b2Control)}


def boolean_control_name(operation: str) -> str | None:
    """Map named shared register semantics, never byte offsets or SKU identity."""
    return {
        "multi_effect": "gradual",
        "gradual": "gradual",
        "limit": "limit",
        "power_off_memory": "power_off_memory",
    }.get(operation)


def boolean_control_is_authorized(control: str, profile: ModelProfile) -> bool:
    """Retain the shipped H617A raw gradual register alongside explicit controls."""
    return control in profile.boolean_controls or (
        control == "gradual" and profile.status_grammar == "H617A" and profile.command_operations is None
    )


def _build_status_query(
    domain: str,
    grammar: str | None,
    *,
    display_setting: str | None = None,
    segment_group: int | None = None,
    colour_mode_selector: int = 0,
) -> bytes:
    if grammar not in _STATUS_QUERY_ROOTS:
        raise ValueError(f"{grammar} has no generated status-query grammar")
    if grammar == "H1771":
        root = H1771StatusQuery()
        root.header = b"\xaa"
        root.domain = getattr(H1771StatusQuery.QueryDomain, domain)
        if domain == "colour_mode":
            body = _child(H1771StatusQuery.ModeQuery, root)
            body.selector = colour_mode_selector
            body.unknown_tail = bytes(16)
        elif domain == "segments":
            body = _child(H1771StatusQuery.SegmentQueryBody, root)
            body.group = segment_group
            body.unknown_tail = bytes(16)
        else:
            body = _child(H1771StatusQuery.Opaque, root)
            body.unknown_tail = bytes(17)
        root.body = body
        return _serialize_xor(root)
    root_type = _STATUS_QUERY_ROOTS[grammar][1]
    body_types = StatusQuery if grammar in {"H6072", "H6072-legacy", "H607C", "H60B0", "H7020", "H705A"} else root_type
    root = root_type()
    root.header = b"\xaa"
    generated_domain = "mode" if grammar == "H6179" and domain == "colour_mode" else domain
    root.domain = getattr(
        root_type.StatusDomain if grammar == "H6179" else root_type.QueryDomain,
        generated_domain,
    )
    if display_setting is not None:
        body = _child(root_type.DisplaySettingQueryBody, root)
        body.setting = getattr(root_type.DisplaySetting, display_setting)
        body.zeros = [0] * 16
    elif segment_group is not None:
        if grammar == "H6179":
            raise ValueError("H6179 has no segment status-query operation")
        body = _child(
            H6072StatusQuery.SegmentQueryBody
            if grammar == "H6072-legacy"
            else StatusQuery.SegmentQueryBody
            if grammar == "H60B0"
            else root_type.SegmentQueryBody,
            root,
        )
        body.group = segment_group
        body.zeros = [0] * 16
    elif domain == "hardware":
        body = _child(body_types.HardwareQueryBody, root)
        if grammar == "H6179":
            body.selector = root_type.HardwareQuerySelector.primary
            body.opaque = bytes(16)
        else:
            body.selector = b"\x03"
            body.zeros = [0] * 16
    elif domain == "relative_brightness":
        body = _child(root_type.RelativeBrightnessQueryBody, root)
        body.selector = b"\x01"
        body.zeros = [0] * 16
    elif domain == "colour_mode" and grammar == "H6099":
        body = _child(root_type.ColourModeQueryBody, root)
        body.selector = b"\x01"
        body.zeros = [0] * 16
    elif domain == "colour_mode" and grammar in WHOLE_BULB_GRAMMARS | {
        "H6072",
        "H6072-legacy",
        "H607C",
        "H60B0",
        "H617A",
        "H7020",
        "H705A",
    }:
        body = _child(body_types.ColourModeQueryBody, root)
        body.selector = colour_mode_selector
        body.zeros = [0] * 16
    elif domain == "colour_mode" and grammar == "H6179":
        body = _child(root_type.ModeQueryBody, root)
        body.selector = root_type.ModeQuerySelector.current
        body.opaque = bytes(16)
    else:
        if grammar == "H6179":
            body = _child(root_type.OpaqueBody, root)
            body.opaque = bytes(17)
        else:
            body = _child(body_types.ZeroBody, root)
            body.zeros = [0] * 17
    root.body = body
    return _serialize_xor(root)


def build_power_query(model: str = "H617A", *, profile: ModelProfile | None = None) -> bytes:
    return _build_status_query("power", (profile or get_profile(model)).command_grammar)


def build_brightness_query(model: str = "H617A", *, profile: ModelProfile | None = None) -> bytes:
    return _build_status_query("brightness", (profile or get_profile(model)).command_grammar)


def build_colour_mode_query(
    model: str = "H617A", *, profile: ModelProfile | None = None, selector: int | None = None
) -> bytes:
    """Select the profile's AA05 query form, with an explicit override."""
    profile = profile or get_profile(model)
    if profile.bulk_status_grammar == "H60A":
        if selector is not None:
            raise ValueError("Bulk mode queries do not have an AA05 selector")
        return build_bulk_status_query(profile)
    if selector is None:
        selector = profile.colour_mode_query_selector
    if type(selector) is not int or selector not in (0, 1):
        raise ValueError("colour-mode query selector must be 0 or 1")
    return _build_status_query("colour_mode", profile.command_grammar, colour_mode_selector=selector)


def build_firmware_query(model: str = "H617A", *, profile: ModelProfile | None = None) -> bytes:
    return _build_status_query("firmware", (profile or get_profile(model)).command_grammar)


def build_hardware_query(model: str = "H617A", *, profile: ModelProfile | None = None) -> bytes:
    return _build_status_query("hardware", (profile or get_profile(model)).command_grammar)


def build_pact_query(profile: ModelProfile) -> bytes:
    if not profile.can_read(ReadDomain.PACT):
        raise ValueError("Protocol identity readback is outside the profile")
    return _build_status_query("pact", profile.command_grammar)


def build_boolean_control(
    control: str,
    enabled: bool,
    model: str,
    *,
    profile: ModelProfile | None = None,
    sibling_enabled: bool | None = None,
    native_mask: int = 0,
) -> bytes:
    """Build a qualified shared register write; revision gating belongs to the profile."""
    profile = profile or get_profile(model)
    if profile.setting_grammar == "H60B0":
        if control not in profile.boolean_controls or type(enabled) is not bool:
            raise ValueError("Unsupported native source control")
        root = H60b0CommandWrite()
        root.header, root.opcode = b"\x33", H60b0CommandWrite.CommandOp.zone_enable
        root.body = _child(H60b0CommandWrite.ZoneEnable, root)
        root.body.source = H60b0CommandWrite.Source[control]
        root.body.enabled = int(enabled)
        root.body.unknown_tail = bytes(15)
        return _serialize_xor(root)
    if profile.setting_grammar == "H1771":
        if control not in profile.boolean_controls or type(enabled) is not bool:
            raise ValueError("Unsupported native source control")
        root = H1771CommandWrite()
        root.header = b"\x33"
        if control == "gradual":
            root.opcode = H1771CommandWrite.CommandOp.gradual
            root.body = _child(H1771CommandWrite.GradualCmd, root)
            root.body.flag = int(enabled)
            root.body.unknown_tail = bytes(16)
        elif control in H1771CommandWrite.Source.__members__:
            root.opcode = H1771CommandWrite.CommandOp.zone_enable
            root.body = _child(H1771CommandWrite.ZoneEnable, root)
            root.body.source = H1771CommandWrite.Source[control]
            root.body.enabled = int(enabled)
            root.body.unknown_tail = bytes(15)
        else:
            raise ValueError("Unsupported native source control")
        return _serialize_xor(root)
    if profile.setting_grammar in _NATIVE_SETTING_ROOTS:
        root_type = _NATIVE_SETTING_ROOTS[profile.setting_grammar][1]
        if (
            control not in profile.boolean_controls
            or control not in {*root_type.Zone.__members__, "gradual"}
            or type(enabled) is not bool
        ):
            raise ValueError("Unsupported native zone control")
        root = root_type()
        root.header = b"\x33"
        if control == "gradual":
            root.opcode = root_type.Command.gradual
            root.body = _child(H607cControl.GradualState, root)
            root.body.flag = int(enabled)
            root.body.unknown_tail = bytes(16)
        else:
            root.opcode = root_type.Command.zone_enable
            root.body = _child(root_type.ZoneEnable, root)
            root.body.zone = root_type.Zone[control]
            root.body.enabled = int(enabled)
            root.body.unknown_tail = bytes(15)
        return _serialize_xor(root)
    if profile.setting_grammar == "H6046":
        if control not in profile.boolean_controls or type(enabled) is not bool or type(sibling_enabled) is not bool:
            raise ValueError("Bar control requires both native bar states")
        flags = H6046CommandWrite.BarFlag
        left, right = (enabled, sibling_enabled) if control == "left_bar_enabled" else (sibling_enabled, enabled)
        root = H6046CommandWrite()
        root.header = b"\x33"
        root.opcode = H6046CommandWrite.CommandOp.bar_enable
        root.body = _child(H6046CommandWrite.BarEnableBody, root)
        if type(native_mask) is not int or not 0 <= native_mask <= 255:
            raise ValueError("Native bar flags must be one byte")
        known_flags = int(flags.left) | int(flags.right)
        root.body.mask = (
            (native_mask & ~known_flags) | (int(flags.left) if left else 0) | (int(flags.right) if right else 0)
        )
        root.body.unknown_tail = bytes(16)
        return _serialize_xor(root)
    if control not in profile.boolean_controls or profile.command_grammar not in {
        "H6072",
        "H6072-legacy",
        "H617A",
        "H6179",
        "H6181",
        "H7020",
        "H705A",
    }:
        raise ValueError(f"{model} does not support boolean control {control}")
    if type(enabled) is not bool:
        raise ValueError("boolean control requires a boolean")
    if profile.command_grammar == "H6179":
        if control != "limit":
            raise ValueError("Unsupported H6179 boolean control")
        root = H6179CommandWrite()
        root.header = b"\x33"
        root.opcode = H6179CommandWrite.CommandOpcode.limit
        root.body = _child(H6179CommandWrite.LimitBody, root)
        root.body.value = int(enabled)
        root.body.opaque = bytes(16)
        return _serialize_xor(root)
    if profile.setting_grammar == "H60A6" and control in H60a6Control.Zone.__members__:
        root = H60a6Control()
        root.header = b"\x33"
        root.opcode = H60a6Control.Command.zone_enable
        root.body = _child(H60a6Control.ZoneCommand, root)
        root.body.zone = H60a6Control.Zone[control]
        root.body.enabled = int(enabled)
        root.body.unknown_tail = bytes(15)
        return _serialize_xor(root)
    operation = {"gradual": "multi_effect", "limit": "limit", "power_off_memory": "power_off_memory"}.get(control)
    root_type = _COMMAND_ROOTS[profile.command_grammar][1]
    if operation is None or operation not in root_type.CommandOp.__members__:
        raise ValueError("unknown boolean control")
    root = root_type()
    root.header = b"\x33"
    root.opcode = getattr(root_type.CommandOp, operation)
    root.body = _child(
        root_type.BooleanCmd
        if root_type is H7020CommandWrite
        else CommandWrite.MultiEffectCmd
        if root_type is H6072CommandWrite
        else root_type.MultiEffectCmd,
        root,
    )
    root.body.flag = int(enabled)
    if root_type is H7020CommandWrite:
        root.body.unknown_tail = bytes(16)
    else:
        root.body.padding = [0] * 16
    return _serialize_xor(root)


def build_boolean_control_query(control: str, model: str, *, profile: ModelProfile | None = None) -> bytes:
    """Read a declared boolean register independently of ordinary read domains."""
    profile = profile or get_profile(model)
    if profile.setting_grammar == "H60B0":
        if control not in profile.boolean_controls:
            raise ValueError("Unsupported native source control")
        return _build_status_query("source_info", profile.command_grammar)
    if profile.setting_grammar == "H1771":
        if control not in profile.boolean_controls:
            raise ValueError("Unsupported native source control")
        bulk_domain = "gradual" if control == "gradual" else "zone_enable"
        if bulk_domain == "zone_enable" and control not in H1771CommandWrite.Source.__members__:
            raise ValueError("Unsupported native source control")
        return build_bulk_status_query(profile, domains=(bulk_domain,))
    if profile.setting_grammar in _NATIVE_SETTING_ROOTS:
        root_type = _NATIVE_SETTING_ROOTS[profile.setting_grammar][1]
        if control == "gradual" and control in profile.boolean_controls:
            root = H607cControl.GradualQuery()
            root.header = b"\xaa\xa3"
            root.unknown_tail = bytes(17)
            return _serialize_xor(root)
        if control not in profile.boolean_controls or control not in root_type.Zone.__members__:
            raise ValueError("Unsupported native zone control")
        root = root_type.DeviceInfoQuery()
        root.header = b"\xaa\x36" if root_type is H60b2Control else b"\xaa\x07\x08"
        root.unknown_tail = bytes(17 if root_type is H60b2Control else 16)
        return _serialize_xor(root)
    if profile.setting_grammar == "H6046":
        if control not in profile.boolean_controls:
            raise ValueError("Bar control is outside profile capabilities")
        return _build_status_query("bar_enable", profile.command_grammar)
    if control not in profile.boolean_controls or profile.command_grammar not in {
        "H6072",
        "H6072-legacy",
        "H617A",
        "H6179",
        "H6181",
        "H7020",
        "H705A",
    }:
        raise ValueError(f"{model} does not support boolean control {control}")
    if profile.setting_grammar == "H60A6" and control in H60a6Control.Zone.__members__:
        return build_bulk_status_query(profile, domains=("zone_enable",))
    domain = {"gradual": "multi_effect", "limit": "limit", "power_off_memory": "power_off_memory"}.get(control)
    root_type = _STATUS_QUERY_ROOTS[profile.command_grammar][1]
    domain_enum = root_type.StatusDomain if profile.command_grammar == "H6179" else root_type.QueryDomain
    if domain is None or domain not in domain_enum.__members__:
        raise ValueError("unknown boolean control")
    return _build_status_query(domain, profile.command_grammar)


def build_source_value(source: str, attribute: str, value: int, profile: ModelProfile) -> bytes:
    if type(value) is not int:
        raise ValueError("Source value must be an integer")
    if profile.setting_grammar != "H60B0":
        raise ValueError("No native source-value grammar")
    from .h60b0_controls import build_source

    if attribute == "ripple_speed":
        if source != "top" or not profile.supports_ripple_speed or not 0 <= value <= 100:
            raise ValueError("Unsupported ripple speed")
        return build_source("top_enabled", "secondary", value=value)
    if source == "top" and attribute == "kelvin" and "top_enabled" in profile.boolean_controls:
        if not profile.min_color_temp_kelvin <= value <= profile.max_color_temp_kelvin or value % 100:
            raise ValueError("Unsupported native Kelvin")
        return build_source("top_enabled", "colour", rgb=table_kelvin_rgb(value), kelvin=value)
    if source != "bottom" or "bottom_enabled" not in profile.boolean_controls:
        raise ValueError("Unsupported native source")
    if attribute == "brightness" and 0 <= value <= 100:
        return build_source("bottom_enabled", "brightness", value=value)
    if (
        attribute == "kelvin"
        and profile.min_color_temp_kelvin <= value <= profile.max_color_temp_kelvin
        and value % 100 == 0
    ):
        return build_source("bottom_enabled", "colour", kelvin=value)
    raise ValueError("Unsupported native source value")


def build_swap_bars(profile: ModelProfile) -> bytes:
    if profile.setting_grammar != "H6046" or not profile.boolean_controls:
        raise ValueError("Device profile does not support swapping light bars")
    root = H6046CommandWrite()
    root.header = b"\x33"
    root.opcode = H6046CommandWrite.CommandOp.swap_bars
    root.body = _child(H6046CommandWrite.SwapBody, root)
    root.body.unknown_tail = bytes(17)
    return _serialize_xor(root)


def bulk_status_domains(profile: ModelProfile) -> frozenset[str]:
    domains: set[str] = set()
    if profile.bulk_status_grammar == "H1771":
        if profile.boolean_controls & H1771CommandWrite.Source.__members__.keys():
            domains.add("zone_enable")
        if "gradual" in profile.boolean_controls:
            domains.add("gradual")
        if profile.can_read(ReadDomain.SEGMENTS) and profile.supports_segments:
            domains.add("segments")
    if profile.boolean_controls & H60a6Control.Zone.__members__.keys():
        domains.add("zone_enable")
    if profile.supports_power_on_behaviour:
        domains.add("power_on_behaviour")
    return frozenset(domains)


def build_bulk_status_query(profile: ModelProfile, *, domains: tuple[str, ...] | None = None) -> bytes:
    """Request independently admitted extension records alongside the base observations."""
    if profile.bulk_status_grammar not in {"H1771", "H60A"}:
        raise ValueError("Device profile does not support bulk observations")
    allowed = bulk_status_domains(profile)
    if domains is None:
        domains = (
            tuple(name for name in ("power_on_behaviour", "zone_enable", "gradual", "segments") if name in allowed)
            if profile.bulk_status_grammar == "H1771"
            else tuple(sorted(allowed))
        )
    if not set(domains) <= allowed:
        raise ValueError("Bulk query domains are outside profile capabilities")
    if profile.bulk_status_grammar == "H1771":
        root = H1771Bulk.Query()
        root.header = b"\xac\x03"
        root.num_domains = len(domains)
        root.domains = [H1771Bulk.Domain[name] for name in domains]
        root.unknown_tail = bytes(16 - root.num_domains)
        return _serialize_xor(root)
    root = H60aBulk.Query()
    root.header = b"\xac\x03"
    root.domain_count = len(domains)
    root.domains = [H60aBulk.Domain[name] for name in domains]
    root.padding = bytes(16 - root.domain_count)
    return _serialize_xor(root)


def build_power_on_behaviour(value: str, profile: ModelProfile) -> bytes:
    if profile.setting_grammar == "H60B0":
        if not profile.supports_power_on_behaviour or value not in H60b0CommandWrite.PowerOnState.__members__:
            raise ValueError("Unsupported power-on behaviour")
        root = H60b0CommandWrite()
        root.header, root.opcode = b"\x33", H60b0CommandWrite.CommandOp.power_on_behaviour
        root.body = _child(H60b0CommandWrite.PowerOnCmd, root)
        root.body.selector = b"\x02"
        root.body.state = H60b0CommandWrite.PowerOnState[value]
        root.body.unknown_tail = bytes(15)
        return _serialize_xor(root)
    if profile.setting_grammar == "H1771":
        if not profile.supports_power_on_behaviour or value not in H1771CommandWrite.PowerOnState.__members__:
            raise ValueError("Unsupported power-on behaviour")
        root = H1771CommandWrite()
        root.header = b"\x33"
        root.opcode = H1771CommandWrite.CommandOp.power_on_behaviour
        root.body = _child(H1771CommandWrite.PowerOnCmd, root)
        root.body.selector = H1771CommandWrite.PowerOnSelector.state
        root.body.state = H1771CommandWrite.PowerOnState[value]
        root.body.unknown_tail = bytes(15)
        return _serialize_xor(root)
    if (
        profile.setting_grammar not in {"H60A6", "H6097", *_NATIVE_SETTING_ROOTS}
        or not profile.supports_power_on_behaviour
        or value not in H60aBulk.PowerOnState.__members__
    ):
        raise ValueError("Unsupported power-on behaviour")
    root_type = {
        "H60A6": H60a6Control,
        "H6097": H6097Control,
        **{key: value[1] for key, value in _NATIVE_SETTING_ROOTS.items()},
    }[profile.setting_grammar]
    root = root_type()
    root.header = b"\x33"
    root.opcode = root_type.Command.power_on_behaviour
    root.body = _child(H607cControl.PowerOnCommand if root_type is H60b2Control else root_type.PowerOnCommand, root)
    root.body.selector = b"\x02"
    root.body.state = H60aBulk.PowerOnState[value]
    root.body.unknown_tail = bytes(15)
    return _serialize_xor(root)


def build_power_on_behaviour_query(profile: ModelProfile) -> bytes:
    if not profile.supports_power_on_behaviour:
        raise ValueError("Unsupported power-on behaviour")
    if profile.setting_grammar == "H60B0":
        return _build_status_query("power_on_behaviour", profile.command_grammar)
    if profile.setting_grammar in {"H1771", "H60A6"}:
        return build_bulk_status_query(profile, domains=("power_on_behaviour",))
    if profile.setting_grammar in _NATIVE_SETTING_ROOTS:
        root = H607cControl.PowerOnQuery()
        root.header = b"\xaa\x41\x00"
        root.unknown_tail = bytes(16)
        return _serialize_xor(root)
    if profile.setting_grammar != "H6097":
        raise ValueError("Unsupported power-on setting grammar")
    root = H6097Control.Query()
    root.header = b"\xaa\x41\x02"
    root.unknown_tail = bytes(16)
    return _serialize_xor(root)


def parse_zone_notification(frame: bytes, profile: ModelProfile) -> ProtocolParseResult:
    if profile.setting_grammar == "H60B2":
        return _parse_xor_frame(
            frame, "H60B2", {"H60B2": ("h60b2_control.zone_notification", H60b2Control.ZoneNotification)}
        )
    if profile.setting_grammar == "H60B0" and profile.boolean_controls:
        return _parse_xor_frame(
            frame, "H60B0", {"H60B0": ("h60b0_status_reply.source_notification", H60b0StatusReply.SourceNotification)}
        )
    if profile.setting_grammar == "H1771":
        result = _parse_xor_frame(
            frame, "H1771", {"H1771": ("h1771_bulk.source_notification", H1771Bulk.SourceNotification)}
        )
        if result.parsed is not None and result.parsed.kind != 1:
            return ProtocolParseResult(None, result.parser, ProtocolParseRejection.SEMANTIC_REJECTED)
        return result
    if profile.setting_grammar == "H607C":
        if not profile.boolean_controls.intersection(H607cControl.Zone.__members__):
            return ProtocolParseResult(
                None, "h607c_control.zone_notification", ProtocolParseRejection.UNSUPPORTED_MODEL
            )
        return _parse_xor_frame(
            frame, "H607C", {"H607C": ("h607c_control.zone_notification", H607cControl.ZoneNotification)}
        )
    grammar = "H60A6" if profile.setting_grammar == "H60A6" else None
    return _parse_xor_frame(
        frame, grammar, {"H60A6": ("h60a6_control.zone_notification", H60a6Control.ZoneNotification)}
    )


def is_bulk_status_frame(frame: bytes, profile: ModelProfile) -> bool:
    return profile.bulk_status_grammar in {"H1771", "H60A"} and frame[:1] == b"\xac"


class BulkStatusCollector:
    """Collect one bounded subscription-local response before interpreting any records."""

    def __init__(self, grammar: str = "H60A") -> None:
        roots = {"H60A": ("h60a_bulk", H60aBulk), "H1771": ("h1771_bulk", H1771Bulk)}
        if grammar not in roots:
            raise ValueError("Unknown bulk status grammar")
        self._grammar = grammar
        self._parser, self._root = roots[grammar]
        self._count: int | None = None
        self._final_size = 0
        self._position = 0
        self._payload = bytearray()
        self.complete = False
        self.failed = False

    def feed(self, frame: bytes) -> ProtocolParseResult:
        if self.failed:
            return ProtocolParseResult(None, self._parser, ProtocolParseRejection.SCHEMA_REJECTED)
        result = _parse_xor_frame(frame, self._grammar, {self._grammar: (self._parser, self._root)})
        if result.parsed is None:
            self.failed = True
            return result
        parsed = result.parsed
        try:
            if self.complete:
                raise ValueError("Bulk response is already complete")
            if self._position == 0:
                if parsed.index != 0:
                    raise ValueError("Bulk response has no start frame")
                count, final_size = int(parsed.body.frame_count), int(parsed.body.final_size)
                if not 1 <= count <= 256 or not 0 <= final_size <= (12 if count == 1 else 17):
                    raise ValueError("Bulk response exceeds frame bounds")
                self._count, self._final_size = count, final_size
                self._payload.extend(parsed.body.payload[:final_size] if count == 1 else parsed.body.payload)
            else:
                declared_count = self._count
                if declared_count is None:
                    raise ValueError("Bulk response has no frame count")
                expected = 255 if self._position == declared_count - 1 else self._position
                if parsed.index != expected:
                    raise ValueError("Bulk response is out of order")
                self._payload.extend(parsed.body[: self._final_size] if expected == 255 else parsed.body)
            self._position += 1
            if self._position != self._count:
                return ProtocolParseResult(None, result.parser, None)
            payload = self._root.Payload.from_bytes(bytes(self._payload))
            payload._read()
            records = [
                (
                    int(record.domain),
                    int(record.body.selector)
                    if self._grammar == "H1771" and record.domain == H1771Bulk.Domain.identity
                    else None,
                )
                for record in payload.records
            ]
            if len(records) != len(set(records)):
                raise ValueError("Bulk response has duplicate domains")
            self.complete = True
            return ProtocolParseResult(payload, f"{self._parser}.payload", None)
        except KaitaiStructError, ValueError, EOFError:
            self.failed = True
            return ProtocolParseResult(None, result.parser, ProtocolParseRejection.SCHEMA_REJECTED)


def parse_boolean_control(generated: Any, model: str, *, profile: ModelProfile | None = None) -> dict[str, bool]:
    """Decode register replies only; mode flags and command ACKs are not confirmation."""
    profile = profile or get_profile(model)
    domain = getattr(generated, "domain", None)
    domain = domain if isinstance(domain, str) else getattr(domain, "name", "")
    if profile.setting_grammar == "H60B2" and domain == "zone_enable":
        if any(getattr(generated.body, name) not in (0, 1) for name in ("bottom", "middle", "top")):
            raise ValueError("Invalid source power flags")
        return {
            name: bool(getattr(generated.body, name))
            for name in H60b2Control.Zone.__members__
            if name in profile.boolean_controls
        }
    if profile.setting_grammar == "H60B0" and domain == "source_info":
        from .h60b0_controls import source_readback

        source_readback(generated.body.operation, profile)
        return {name: bool(getattr(generated.body, name)) for name in profile.boolean_controls}
    if profile.setting_grammar == "H607C" and domain in {"zone_enable", "hw_version"}:
        flags = (
            generated.body.flags
            if domain == "zone_enable"
            else generated.body.detail.flags
            if domain == "hw_version" and getattr(generated.body.selector, "name", None) == "device_info"
            else None
        )
        return {
            name: bool(getattr(flags, name))
            for name in H607cControl.Zone.__members__
            if flags is not None and name in profile.boolean_controls
        }
    if domain == "bar_enable" and profile.setting_grammar == "H6046":
        values = {
            "left_bar_enabled": bool(generated.body.left_enabled),
            "right_bar_enabled": bool(generated.body.right_enabled),
        }
        return {key: value for key, value in values.items() if key in profile.boolean_controls}
    control = boolean_control_name(domain)
    if control is None or control not in profile.boolean_controls:
        return {}
    flag = generated.values["flag"] if profile.status_grammar == "H6179" else generated.body.flag
    if flag not in (0, 1):
        raise ValueError("boolean register reply must be 0 or 1")
    return {control: bool(flag)}


def build_configured_strings_query(profile: ModelProfile) -> bytes:
    """Read the product's independent installation observation."""
    if not profile.configured_string_counts:
        raise ValueError(f"{profile.name} does not support configured strings")
    if profile.configured_string_ic_count:
        return build_physical_ic_count_query(profile.name, profile=profile)
    return _build_status_query("configured_strings", profile.command_grammar)


def build_configured_strings(count: int, profile: ModelProfile) -> bytes:
    if type(count) is not int or count not in profile.configured_string_counts:
        raise ValueError("unsupported configured string count")
    root_type = _COMMAND_ROOTS[profile.command_grammar or ""][1]
    root = root_type()
    root.header = b"\x33"
    root.opcode = root_type.CommandOp.configured_strings
    root.body = _child(root_type.ConfiguredStringsCmd, root)
    root.body.count = count
    root.body.unknown_tail = bytes(16)
    return _serialize_xor(root)


def build_ic_refresh(profile: ModelProfile) -> bytes:
    if not profile.supports_ic_refresh:
        raise ValueError("IC refresh is not supported")
    root_type = _COMMAND_ROOTS[profile.command_grammar or ""][1]
    root = root_type()
    root.header, root.opcode = b"\x33", root_type.CommandOp.refresh_ic
    root.body = _child(root_type.ZeroBody, root)
    root.body.zeros = [0] * 17
    return _serialize_xor(root)


def build_physical_ic_count_query(model: str, *, profile: ModelProfile | None = None) -> bytes:
    profile = profile or get_profile(model)
    if not profile.can_read(ReadDomain.PHYSICAL_IC_COUNT) or profile.command_grammar is None:
        raise ValueError(f"{model} has no qualified physical IC query")
    return _build_status_query("physical_ic_count", profile.command_grammar)


def build_installation_direction(value: int, model: str, *, profile: ModelProfile | None = None) -> bytes:
    profile = profile or get_profile(model)
    if not profile.supports_installation_direction or profile.command_grammar != "H6099":
        raise ValueError(f"{model} has no qualified installation-direction writer")
    if type(value) is not int or value not in INSTALLATION_DIRECTIONS:
        raise ValueError("Installation direction must be 2, 3, 4, or 5")
    root = H6099CommandWrite()
    root.header = b"\x33"
    root.opcode = H6099CommandWrite.CommandOp.installation_direction
    root.body = _child(H6099CommandWrite.InstallationDirectionBody, root)
    root.body.value = value
    return _serialize_xor(root)


def build_installation_direction_query(model: str, *, profile: ModelProfile | None = None) -> bytes:
    profile = profile or get_profile(model)
    if not profile.can_read(ReadDomain.INSTALLATION_DIRECTION) or profile.command_grammar != "H6099":
        raise ValueError(f"{model} has no qualified installation-direction query")
    return _build_status_query("installation_direction", profile.command_grammar)


def build_camera_health_query(model: str, *, profile: ModelProfile | None = None) -> bytes:
    profile = profile or get_profile(model)
    if not profile.can_read(ReadDomain.CAMERA_HEALTH) or profile.command_grammar != "H6099":
        raise ValueError(f"{model} has no qualified camera-health query")
    return _build_status_query("camera_health", profile.command_grammar)


def parse_physical_ic_count(generated: Any) -> int | None:
    if getattr(generated.domain, "name", None) != "physical_ic_count":
        return None
    count = int(generated.body.count)
    return count if count > 0 else None


def build_white_balance_query(model: str, *, profile: ModelProfile | None = None) -> bytes:
    profile = profile or get_profile(model)
    if not profile.supports_white_balance_readback or not profile.can_read(ReadDomain.DISPLAY_SETTING):
        raise ValueError(f"{model} does not support white-balance readback")
    grammar = (
        _video_command_grammar(model, profile) if profile.video_grammar == "H605C-video" else profile.command_grammar
    )
    if grammar in {"H6099", "H6199"} or (grammar == "H617A" and profile.video_white_balance_representation == "scalar"):
        setting = "scalar_white_balance" if profile.video_white_balance_representation == "scalar" else "white_balance"
        return _build_status_query("display_setting", grammar, display_setting=setting)
    raise ValueError(f"{model} has no generated white-balance query grammar")


def build_blank_screen_query(model: str, *, profile: ModelProfile | None = None) -> bytes:
    profile = profile or get_profile(model)
    if not profile.supports_blank_screen:
        raise ValueError(f"{model} does not support blank-screen detection")
    if (grammar := _video_command_grammar(model, profile)) in {"H6099", "H6199"}:
        return _build_status_query("display_setting", grammar, display_setting="blank_screen")
    raise ValueError(f"{model} has no generated blank-screen query grammar")


def build_relative_brightness_query(model: str, *, profile: ModelProfile | None = None) -> bytes:
    profile = profile or get_profile(model)
    if not profile.supports_relative_brightness:
        raise ValueError(f"{model} does not support relative brightness")
    if (grammar := _video_command_grammar(model, profile)) in {"H6099", "H6199"}:
        return _build_status_query("relative_brightness", grammar)
    raise ValueError(f"{model} has no generated relative-brightness query grammar")


def build_whole_relative_brightness(value: int | None, model: str, *, profile: ModelProfile | None = None) -> bytes:
    """Build the independent scalar register or its query, not synthetic edges."""
    profile = profile or get_profile(model)
    if not profile.supports_whole_relative_brightness or profile.video_grammar != "H605C-video":
        raise ValueError(f"{model} has no qualified whole-video brightness grammar")
    if value is not None and (type(value) is not int or not 0 <= value <= 100):
        raise ValueError("whole-video brightness must be from 0 to 100")
    root = H605cVideoSettings()
    root.header = root.FrameHeader.query if value is None else root.FrameHeader.write
    root.opcode, root.setting = b"\xa9", b"\x02"
    if value is not None:
        root.length, root.value = 1, value
    root.unknown_tail = bytes(16 if value is None else 14)
    return _serialize_xor(root)


def build_subordinate_query(domain: int, model: str, *, profile: ModelProfile | None = None) -> bytes:
    if domain not in {0x20, 0x21}:
        raise ValueError("subordinate query domain must be 0x20 or 0x21")
    profile = profile or get_profile(model)
    if not profile.can_read(ReadDomain(f"subordinate_{domain:02x}")):
        raise ValueError(f"{model} does not support this subordinate identity query")
    return _build_status_query(f"subordinate_{domain:02x}", profile.command_grammar)


def build_black_border_query(model: str, *, profile: ModelProfile | None = None) -> bytes:
    profile = profile or get_profile(model)
    if not profile.supports_black_border:
        raise ValueError(f"{model} does not support black-border removal")
    return _build_status_query(
        "display_setting", _video_command_grammar(model, profile), display_setting="black_border"
    )


def build_segment_query(group: int, model: str = "H617A", *, profile: ModelProfile | None = None) -> bytes:
    profile = profile or get_profile(model)
    resolved = profile.command_grammar
    if resolved not in _STATUS_QUERY_ROOTS or (
        resolved not in {"H6072-legacy", "H60B0"} and not hasattr(_STATUS_QUERY_ROOTS[resolved][1], "SegmentQueryBody")
    ):
        raise ValueError(f"{model} has no generated segment-query grammar")
    if type(group) is not int:
        raise ValueError("segment query group must be an integer")
    if resolved in {"H1771", "H60B0", "H705A"} and not 1 <= group <= profile.segment_group_count:
        raise ValueError("segment query group is outside the selected geometry")
    try:
        return _build_status_query("segments", resolved, segment_group=group)
    except KaitaiStructError as error:
        raise ValueError("segment query group is outside the selected grammar") from error
