"""MovieFeastV2 semantics over explicitly compatible generated wire structures.

Selectively reuses issue #257's immutable member model and group framing, not
its default cmd_ver, digest, camera assumptions or active member identification.
"""

from __future__ import annotations

import io
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from importlib import import_module
from typing import Any, cast

from kaitaistruct import KaitaiStream, KaitaiStructError

from .const import ModelProfile
from .generated_protocol_adapter import _check_tree, _serialize_xor, _serialized_length, _write
from .transport import A3_CHUNK_SIZE, fragment_a3, xor_checksum

Frame = cast(Any, import_module(f"{__package__}.generated_protocol.h6099_dreamview_frame").H6099DreamviewFrame)
Group = cast(Any, import_module(f"{__package__}.generated_protocol.h6099_dreamview_group").H6099DreamviewGroup)
DREAMVIEW_READ_SETTINGS = tuple(command.name for command in Frame.Command if command != Frame.Command.delete_group)


def require_dreamview(
    profile: ModelProfile, operation: str, *, read: bool = False, member_count: int | None = None
) -> None:
    """No related-model or camera-based capability inference."""
    operations = profile.dreamview_reads if read else profile.dreamview_operations
    if profile.dreamview_grammar != "H6099" or operation not in operations:
        raise ValueError("DreamView operation is not supported by this profile")
    if member_count is not None and not 1 <= member_count <= profile.dreamview_max_sub_devices:
        raise ValueError("DreamView member count exceeds this profile's capacity; use explicit delete for removal")


def integer(value: Any, maximum: int = 255) -> int:
    """Reject booleans, fractions and strings rather than silently changing bytes."""
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f"Expected an integer in 0..{maximum}")
    return value


@dataclass(frozen=True)
class DreamviewMember:
    """Explicit known member metadata; identity is never included in repr/errors."""

    cmd_ver: int
    is_rgbic: bool
    zones: tuple[int, ...]
    address: str | None = field(default=None, repr=False)
    name: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        integer(self.cmd_ver)
        if type(self.is_rgbic) is not bool:
            raise ValueError("is_rgbic must be a boolean")
        if (self.address is None) == (self.name is None):
            raise ValueError("Supply exactly one BLE address or BLE name")
        if self.address is not None:
            if (
                not isinstance(self.address, str)
                or re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", self.address) is None
            ):
                raise ValueError("Invalid BLE address format")
            object.__setattr__(self, "address", self.address.upper())
        if self.name is not None:
            if not isinstance(self.name, str) or not 1 <= len(self.name.encode("utf-8")) <= 255:
                raise ValueError("BLE name must encode to 1..255 UTF-8 bytes")
        if not isinstance(self.zones, tuple) or not 1 <= len(self.zones) <= 255:
            raise ValueError("Supply 1..255 explicit areas")
        for zone in self.zones:
            if integer(zone) not in (*range(11), 255):
                raise ValueError("Areas must be wire 1..10, 0 (unassigned), or 255 (disabled)")
        if self.zones == (255,):
            raise ValueError("The APK does not establish disabling a single-area member")

    def as_dict(self) -> dict[str, Any]:
        """Private persistence only; do not include this in diagnostics."""
        return {
            "cmd_ver": self.cmd_ver,
            "is_rgbic": self.is_rgbic,
            "zones": list(self.zones),
            **({"address": self.address} if self.address is not None else {"name": self.name}),
        }


def build_dreamview_group(members: Sequence[DreamviewMember], profile: ModelProfile) -> tuple[bytes, ...]:
    """Build the entire bounded upload before any device-control side effect."""
    require_dreamview(profile, "replace_group", member_count=len(members))
    seen: set[tuple[str | None, str | None]] = set()
    root = Group()
    root.num_members = len(members)
    root.members = []
    root.unknown = b""
    for member in members:
        identity = (member.address, member.name)
        if identity in seen:
            raise ValueError("Duplicate DreamView identity")
        seen.add(identity)
        record = Group.Member(_parent=root, _root=root)
        record.is_rgbic, record.cmd_ver = int(member.is_rgbic), member.cmd_ver
        record.identity_kind = Group.IdentityKind.mac if member.address is not None else Group.IdentityKind.name
        if member.address is not None:
            record.reversed_mac = bytes.fromhex(member.address.replace(":", ""))[::-1]
        else:
            record.name_bytes = cast(str, member.name).encode("utf-8")
            record.name_len = len(record.name_bytes)
        record.area_count, record.area_values = len(member.zones), list(member.zones)
        root.members.append(record)
    _check_tree(root)
    length = _serialized_length(root)
    # Include the A3 marker, frame count and type in the u1 frame-count bound.
    if length + 3 > 255 * A3_CHUNK_SIZE:
        raise ValueError("DreamView group exceeds the A3 frame-count limit")
    return tuple(fragment_a3(root.group_type, _write(root, length)))


def build_dreamview_command(setting: str, values: Mapping[str, Any], profile: ModelProfile) -> bytes:
    """Serialize only individually evidenced settings, with complete validation."""
    require_dreamview(profile, setting)
    fields: dict[str, dict[str, Any]] = {
        "switch_group": {"enabled": bool},
        "member_brightness": {"level": 100, "index": profile.dreamview_max_sub_devices - 1},
        "same_brightness": {"enabled": bool},
        "member_connect": {"index": profile.dreamview_max_sub_devices - 1, "connected": bool},
        "saturation": {"saturation": 100},
        "sample": {"sample_first": 255, "sample_second": 255},
        "sound": {"enabled": bool, "softness": 100},
        "delete_group": {},
    }
    if setting not in fields or values.keys() != fields[setting].keys():
        raise ValueError("Supply exactly the fields required by this DreamView setting")
    root = Frame(False)
    root.header, root.module, root.command = Frame.Header.write, b"\x60", Frame.Command[setting]
    root.body = Frame.WriteBody(_parent=root, _root=root)
    for name, bound in fields[setting].items():
        value = values[name]
        if bound is bool:
            if type(value) is not bool:
                raise ValueError("Expected an explicit boolean")
            value = int(value)
        else:
            value = integer(value, cast(int, bound))
        setattr(root.body, name, value)
    root.body.discriminator = b"\x01"
    root.body.unknown = bytes(16 - len(values) - (setting == "switch_group"))
    return _serialize_xor(root)


def build_dreamview_query(setting: str, profile: ModelProfile) -> bytes:
    require_dreamview(profile, setting, read=True)
    if setting not in DREAMVIEW_READ_SETTINGS:
        raise ValueError("Unsupported DreamView read")
    root = Frame(True)
    root.header, root.module, root.command = Frame.Header.read, b"\x60", Frame.Command[setting]
    root.body = Frame.QueryBody(_parent=root, _root=root)
    root.body.discriminator = b"\x01"
    root.body.unknown = bytes(15 if setting == "switch_group" else 16)
    return _serialize_xor(root)


def parse_dreamview_status(frame: bytes) -> tuple[str, dict[str, Any]] | None:
    """Return individual observations, never a group count, identity or ACK state."""
    if len(frame) != 20 or xor_checksum(frame[:-1]) != frame[-1]:
        return None
    root = Frame(False, KaitaiStream(io.BytesIO(frame)))
    try:
        root._read()
    except KaitaiStructError:
        return None
    if root.header != Frame.Header.read or root.command not in Frame.Command:
        return None
    setting = root.command.name
    if setting not in DREAMVIEW_READ_SETTINGS:
        return None
    body = root.body
    fields = {
        "switch_group": ("enabled",),
        "member_brightness": ("brightness_bytes",),
        "same_brightness": ("enabled",),
        "member_connect": ("connection_bytes",),
        "saturation": ("saturation",),
        "sample": ("sample_first", "sample_second"),
        "sound": ("enabled", "softness"),
    }
    observed = {name: getattr(body, name) for name in fields[setting]}
    # Keep raw slot bytes and uncertain tails. Zero is not proof that a slot is empty.
    observed["unknown"] = list(body.unknown)
    return setting, {name: list(value) if isinstance(value, bytes) else value for name, value in observed.items()}
