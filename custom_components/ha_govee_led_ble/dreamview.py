"""DreamView semantics over explicitly compatible generated wire structures.

Camera members retain their area-value vectors; Music members carry an
exclusive scalar-area form without inheriting camera controls.
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
from .protocol_core import H607cCommandAck, H607cEffectUpload, _check_tree, _serialize_xor, _serialized_length, _write
from .transport import A3_CHUNK_SIZE, fragment_a3, xor_checksum

Frame = cast(Any, import_module(f"{__package__}.generated_protocol.h6099_dreamview_frame").H6099DreamviewFrame)
LegacyFrame = cast(Any, import_module(f"{__package__}.generated_protocol.h6199_dreamview_frame").H6199DreamviewFrame)
Group = cast(Any, import_module(f"{__package__}.generated_protocol.h6099_dreamview_group").H6099DreamviewGroup)
MusicFrame = cast(Any, import_module(f"{__package__}.generated_protocol.h607c_dreamview_frame").H607cDreamviewFrame)
MusicGroup = cast(Any, import_module(f"{__package__}.generated_protocol.h607c_dreamview_group").H607cDreamviewGroup)
_FRAMES = {"H6099": Frame, "H6199": LegacyFrame, "H607C": MusicFrame}
DREAMVIEW_READ_SETTINGS = tuple(command.name for command in Frame.Command if command != Frame.Command.delete_group)
DREAMVIEW_VIDEO_FIELDS = {"apply_area": Frame.ApplyArea, "content_mode": Frame.ContentMode}


def require_dreamview(
    profile: ModelProfile, operation: str, *, read: bool = False, member_count: int | None = None
) -> None:
    """No related-model or camera-based capability inference."""
    operations = profile.dreamview_reads if read else profile.dreamview_operations
    if profile.dreamview_grammar not in _FRAMES or operation not in operations:
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
    is_rgbic: bool | None = None
    zones: tuple[int, ...] = ()
    address: str | None = field(default=None, repr=False)
    name: str | None = field(default=None, repr=False)
    mark: int | None = None
    area_num: int | None = None

    def __post_init__(self) -> None:
        integer(self.cmd_ver)
        music_member = self.mark is not None or self.area_num is not None
        if music_member:
            if self.mark is None or self.area_num is None or self.is_rgbic is not None or self.zones:
                raise ValueError("Music members require mark/area_num without camera fields")
            integer(self.mark)
            if integer(self.area_num) == 0:
                raise ValueError("Music member area_num must be from 1 to 255")
        elif type(self.is_rgbic) is not bool:
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
        if not isinstance(self.zones, tuple) or (not music_member and not 1 <= len(self.zones) <= 255):
            raise ValueError("Supply 1..255 explicit areas")
        for zone in self.zones:
            if integer(zone) not in (*range(11), 255):
                raise ValueError("Areas must be wire 1..10, 0 (unassigned), or 255 (disabled)")
        if self.zones == (255,):
            raise ValueError("The app does not establish disabling a single-area member")

    def as_dict(self) -> dict[str, Any]:
        """Private persistence only; do not include this in diagnostics."""
        return {
            "cmd_ver": self.cmd_ver,
            **(
                {"mark": self.mark, "area_num": self.area_num}
                if self.mark is not None
                else {"is_rgbic": self.is_rgbic, "zones": list(self.zones)}
            ),
            **({"address": self.address} if self.address is not None else {"name": self.name}),
        }


def build_dreamview_group(members: Sequence[DreamviewMember], profile: ModelProfile) -> tuple[bytes, ...]:
    """Build the entire bounded upload before any device-control side effect."""
    require_dreamview(profile, "replace_group", member_count=len(members))
    seen: set[tuple[str | None, str | None]] = set()
    group_type = MusicGroup if profile.dreamview_grammar == "H607C" else Group
    root = group_type()
    root.num_members = len(members)
    root.members = []
    root.unknown = b""
    for member in members:
        music_member = member.mark is not None
        if music_member != (group_type is MusicGroup):
            raise ValueError("DreamView member form does not match the group grammar")
        identity = (member.address, member.name)
        if identity in seen:
            raise ValueError("Duplicate DreamView identity")
        seen.add(identity)
        record = group_type.Member(_parent=root, _root=root)
        record.cmd_ver = member.cmd_ver
        if music_member:
            record.mark, record.area_num = member.mark, member.area_num
        else:
            record.is_rgbic = int(cast(bool, member.is_rgbic))
            record.area_count, record.area_values = len(member.zones), list(member.zones)
        record.identity_kind = (
            group_type.IdentityKind.mac if member.address is not None else group_type.IdentityKind.name
        )
        if member.address is not None:
            record.reversed_mac = bytes.fromhex(member.address.replace(":", ""))[::-1]
        else:
            record.name_bytes = cast(str, member.name).encode("utf-8")
            setattr(record, "len_name_bytes" if music_member else "name_len", len(record.name_bytes))
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
        "video_settings": {"apply_area": 255, "content_mode": 255},
        "sound": {"enabled": bool, "softness": 100},
        "delete_group": {},
        "music": {"music_type": 255, "selector": 65535, "second_parameter": 255, "sensitivity": 99},
    }
    frame_type = _FRAMES[cast(str, profile.dreamview_grammar)]
    if (
        setting not in fields
        or setting not in frame_type.Command.__members__
        or values.keys() != fields[setting].keys()
    ):
        raise ValueError("Supply exactly the fields required by this DreamView setting")
    root = frame_type(False)
    root.header, root.command = frame_type.Header.write, frame_type.Command[setting]
    if frame_type in {Frame, MusicFrame}:
        root.module = bytes((root.module_value,))
    root.body = frame_type.WriteBody(_parent=root, _root=root)
    target = root.body
    if setting == "music":
        root.body.music = frame_type.MusicParameters(_parent=root.body, _root=root)
        target = root.body.music
    for name, bound in fields[setting].items():
        value = values[name]
        if bound is bool:
            if type(value) is not bool:
                raise ValueError("Expected an explicit boolean")
            value = int(value)
        else:
            value = integer(value, cast(int, bound))
        setattr(target, name, value)
    if root.discriminator_size:
        root.body.discriminator = bytes((root.discriminator_value,))
    if frame_type is MusicFrame and setting == "delete_group":
        root.body.clear = b"\xff"
    root.body.unknown = b""
    _check_tree(root.body)
    root.body.unknown = bytes(root.body_size - _serialized_length(root.body))
    return _serialize_xor(root)


def build_dreamview_query(setting: str, profile: ModelProfile) -> bytes:
    require_dreamview(profile, setting, read=True)
    if setting not in DREAMVIEW_READ_SETTINGS and not (profile.dreamview_grammar == "H607C" and setting == "music"):
        raise ValueError("Unsupported DreamView read")
    frame_type = _FRAMES[cast(str, profile.dreamview_grammar)]
    if setting not in frame_type.Command.__members__:
        raise ValueError("Unsupported DreamView read")
    root = frame_type(True)
    root.header, root.command = frame_type.Header.read, frame_type.Command[setting]
    if frame_type in {Frame, MusicFrame}:
        root.module = bytes((root.module_value,))
    root.body = frame_type.QueryBody(_parent=root, _root=root)
    if root.discriminator_size:
        root.body.discriminator = bytes((root.discriminator_value,))
    root.body.unknown = bytes(root.body_size - root.discriminator_size)
    return _serialize_xor(root)


def dreamview_parser(profile: ModelProfile) -> str | None:
    frame_type = _FRAMES.get(cast(str, profile.dreamview_grammar))
    return frame_type.__module__.rsplit(".", 1)[-1] if frame_type is not None else None


def parse_dreamview_status(frame: bytes, profile: ModelProfile | None = None) -> tuple[str, dict[str, Any]] | None:
    """Return individual observations, never a group count, identity or ACK state."""
    if len(frame) != 20 or xor_checksum(frame[:-1]) != frame[-1]:
        return None
    frame_type = Frame if profile is None else _FRAMES.get(cast(str, profile.dreamview_grammar))
    if frame_type is None:
        return None
    root = frame_type(False, KaitaiStream(io.BytesIO(frame)))
    try:
        root._read()
    except KaitaiStructError:
        return None
    if root.header != frame_type.Header.read or root.command not in frame_type.Command:
        return None
    setting = root.command.name
    if setting not in DREAMVIEW_READ_SETTINGS and not (frame_type is MusicFrame and setting == "music"):
        return None
    body = root.body
    fields = {
        "switch_group": ("enabled",),
        "member_brightness": ("brightness_bytes",),
        "same_brightness": ("enabled",),
        "member_connect": ("connection_bytes",),
        "saturation": ("saturation",),
        "video_settings": ("apply_area", "content_mode"),
        "sound": ("enabled", "softness"),
        "music": ("music_type", "selector", "second_parameter", "sensitivity"),
    }
    observed = {name: getattr(body.music if setting == "music" else body, name) for name in fields[setting]}
    # Keep raw slot bytes and uncertain tails. Zero is not proof that a slot is empty.
    observed["unknown"] = list(body.unknown)
    return setting, {name: list(value) if isinstance(value, bytes) else value for name, value in observed.items()}


def parse_dreamview_ack(frame: bytes, profile: ModelProfile) -> tuple[str, bool] | None:
    frame_type = {"H6199": LegacyFrame, "H607C": MusicFrame}.get(cast(str, profile.dreamview_grammar))
    if frame_type is None or len(frame) != 20 or xor_checksum(frame):
        return None
    if frame_type is MusicFrame:
        try:
            upload = H607cCommandAck.from_bytes(frame)
            upload._read()
        except KaitaiStructError:
            pass
        else:
            if upload.is_upload and upload.opcode == H607cEffectUpload.Kind.dreamview_group:
                return "replace_group", bool(upload.is_success)
    root = frame_type.Acknowledgement(KaitaiStream(io.BytesIO(frame)))
    try:
        root._read()
    except KaitaiStructError:
        return None
    if getattr(root.operation, "name", None) is None:
        return None
    return root.operation.name, bool(root.is_success)


def is_legacy_dreamview_packet(frame: bytes) -> bool:
    """Recognise typed packets after the transaction's complete request validation."""
    if len(frame) != 20 or xor_checksum(frame):
        return False
    try:
        upload = LegacyFrame.UploadFrame(KaitaiStream(io.BytesIO(frame)))
        upload._read()
    except KaitaiStructError:
        pass
    else:
        return True
    for query in (False, True):
        root = LegacyFrame(query, KaitaiStream(io.BytesIO(frame)))
        try:
            root._read()
        except KaitaiStructError:
            continue
        if root.header == LegacyFrame.Header.read and query:
            return True
        if root.header == LegacyFrame.Header.write and not query:
            return True
    return False
