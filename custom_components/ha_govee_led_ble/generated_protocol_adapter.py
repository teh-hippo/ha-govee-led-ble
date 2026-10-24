"""Semantic helpers over generated Kaitai protocol classes."""

from __future__ import annotations

import io
import math
from collections.abc import Mapping, Sequence
from typing import Any

from kaitaistruct import KaitaiStream, KaitaiStructError

from .const import ModelProfile, ReadDomain, get_profile
from .music_protocol import music_slug_for
from .music_semantics import music_variant
from .protocol_core import (
    _BLANK_SCREEN_LOW_BRIGHTNESS_SECONDS,
    _BLANK_SCREEN_SAME_TONE_SECONDS,
    _COMMAND_ACK_ROOTS,
    _COMMAND_ROOTS,
    _H6076_ACK_ROOTS,
    _MUSIC_WRITE_ROOTS,
    _STATUS_QUERY_ROOTS,
    _STATUS_ROOTS,
    CommandWrite,
    DiyType03,
    DiyType04,
    GoveeCommon,
    H1a42MusicWrite,
    H60a6Control,
    H60a6EffectFrame,
    H60aBulk,
    H61f5MusicWrite,
    H66a0MusicWrite,
    H66a0VideoCommand,
    H601cCommandWrite,
    H6076MusicAck,
    H6076MusicBody,
    H6076MusicWrite,
    H6097Control,
    H6097MusicWrite,
    H6099CommandWrite,
    H6099EffectUpload,
    H6179CommandWrite,
    H6199EffectUpload,
    H7020CommandWrite,
    H7025MusicWrite,
    ProtocolParseRejection,
    ProtocolParseResult,
    SceneBody,
    SceneType1Body,
    StatusQuery,
    WorkshopBody,
    _a3_header,
    _child,
    _has_unknown_discriminator,
    _parse_xor_frame,
    _rgb,
    _serialize_a3_scene_param,
    _serialize_xor,
    _set_effect_layer_lengths,
    _write,
    check_generated_tree,
)
from .protocol_h6179 import (
    _build_h6179_static_colour,
    build_h6179_diy_activation,
    build_h6179_scene,
    encode_h6179_brightness,
)
from .protocol_h6199 import (
    INSTALLATION_DIRECTIONS,
    build_h6199_scene,
)
from .protocol_transforms import (
    h6102_outbound_transform_for,
)
from .transport import (
    A1_02_COMMAND,
    A1_02_PREFIX,
    A3_CHUNK_SIZE,
    A4_PREFIX,
    reassemble_a1_02_upload,
    reassemble_a3,
    reassemble_a4_upload,
    xor_checksum,
)


def parse_status_result(
    frame: bytes, model: str = "H617A", *, profile: ModelProfile | None = None
) -> ProtocolParseResult:
    return _parse_xor_frame(frame, (profile or get_profile(model)).status_grammar, _STATUS_ROOTS)


def parse_status(frame: bytes, model: str = "H617A", *, profile: ModelProfile | None = None) -> Any | None:
    return parse_status_result(frame, model, profile=profile).parsed


def parse_command_result(
    frame: bytes, model: str = "H617A", *, profile: ModelProfile | None = None
) -> ProtocolParseResult:
    effective_profile = profile or get_profile(model)
    if (
        effective_profile.video_grammar == "H66A0-video"
        and effective_profile.supports_video_mode
        and frame[:3] == b"\x33\x05\x00"
    ):
        video = _parse_xor_frame(frame, "H66A0-video", {"H66A0-video": ("h66a0_video_command", H66a0VideoCommand)})
        if video.parsed is not None:
            if (
                getattr(video.parsed.detail.source, "name", None) not in effective_profile.video_modes
                or getattr(video.parsed.detail.picture_preset, "name", None) is None
                or video.parsed.detail.sound_effects not in (0, 1)
                or not 0 <= video.parsed.detail.softness <= 100
            ):
                return ProtocolParseResult(None, video.parser, ProtocolParseRejection.SEMANTIC_REJECTED)
            try:
                effective_profile.validate_video_saturation(int(video.parsed.detail.saturation))
            except ValueError:
                return ProtocolParseResult(None, video.parser, ProtocolParseRejection.SEMANTIC_REJECTED)
            return video
        return video
    if effective_profile.music_grammar in _MUSIC_WRITE_ROOTS:
        music = _parse_xor_frame(frame, effective_profile.music_grammar, _MUSIC_WRITE_ROOTS)
        if music.parsed is not None:
            if getattr(music.parsed.selector.mode_id, "name", None) is None:
                return ProtocolParseResult(None, music.parser, ProtocolParseRejection.SEMANTIC_REJECTED)
            return music
    result = _parse_xor_frame(frame, effective_profile.command_grammar, _COMMAND_ROOTS)
    if result.parsed is not None and (
        _has_unknown_discriminator(result.parsed, result.parser or "")
        or (
            effective_profile.music_grammar in _MUSIC_WRITE_ROOTS
            and getattr(result.parsed.opcode, "name", None) in {"multi", "mode"}
            and getattr(
                getattr(result.parsed.body, "sub", getattr(result.parsed.body, "sub_mode", None)),
                "name",
                None,
            )
            == "music"
        )
    ):
        return ProtocolParseResult(None, result.parser, ProtocolParseRejection.SEMANTIC_REJECTED)
    return result


def parse_command_ack_result(frame: bytes, model: str, *, profile: ModelProfile | None = None) -> ProtocolParseResult:
    profile = profile or get_profile(model)
    # Video companions retain their independently selected ACK codec. SDK ACKs
    # also exist on devices with no video grammar (notably H617A A3 uploads).
    if profile.video_grammar is not None:
        video = _parse_xor_frame(frame, profile.video_grammar, _COMMAND_ACK_ROOTS)
        if video.parsed is not None:
            return video
    if profile.music_grammar == "H6076":
        music = _parse_xor_frame(frame, "H6076", _H6076_ACK_ROOTS)
        if music.parsed is not None:
            return music
    return _parse_xor_frame(frame, profile.command_ack_grammar or profile.command_grammar, _COMMAND_ACK_ROOTS)


def _complete_a3_upload(
    packets: Sequence[bytes], index: int, model: str, profile: ModelProfile | None
) -> tuple[int, bytes]:
    active_profile = profile or get_profile(model)
    if active_profile.command_grammar not in {"H617A", "H7020"} and active_profile.command_ack_grammar != "H617A":
        raise ValueError("Upload ACK semantics are not qualified for this command grammar")
    roots = {"H617A": ("command_write.upload_frame", CommandWrite.UploadFrame)}
    for start in range(index, -1, -1):
        frame = _parse_xor_frame(packets[start], "H617A", roots).parsed
        if frame is None or (start == index and not frame.is_final):
            break
        if frame.index == 0:
            return int(frame.body.subtype), reassemble_a3(packets[start : index + 1])
    raise ValueError("Upload ACK index must end a complete A3 upload")


def upload_ack_subtype(packets: Sequence[bytes], index: int, model: str, *, profile: ModelProfile | None = None) -> int:
    """Validate a complete upload ending at index, returning its ACK command."""
    profile = profile or get_profile(model)
    if packets[index][0] == A4_PREFIX:
        if profile.effect_grammar != "H60A6":
            raise ValueError("A4 upload acknowledgement is not qualified for this profile")
        subtype, _body = reassemble_a4_upload(packets, index)
        if subtype != int(H60a6EffectFrame.Subtype.native_effect):
            raise ValueError("A4 upload subtype is outside profile capabilities")
        return subtype
    if packets[index][0] == A1_02_PREFIX:
        if profile.a1_diy_selector is None or profile.command_ack_grammar not in _COMMAND_ACK_ROOTS:
            raise ValueError("A1 upload acknowledgement is not qualified for this profile")
        body = reassemble_a1_02_upload(packets, index)
        if body[0] != profile.a1_diy_selector:
            raise ValueError("A1 upload selector does not match the profile")
        return A1_02_COMMAND
    return _complete_a3_upload(packets, index, model, profile)[0]


def upload_ack_mode(
    packets: Sequence[bytes], index: int, model: str, *, profile: ModelProfile | None = None
) -> int | None:
    """Return the music mode an exact-model acknowledgement must repeat, if its schema carries one."""
    if (profile or get_profile(model)).music_grammar != "H6076":
        return None
    subtype, envelope = _complete_a3_upload(packets, index, model, profile)
    if subtype != 0x41:
        return None
    body = H6076MusicBody.from_bytes(envelope)
    body._read()
    return int(body.mode)


def upload_ack_success(
    parsed: Any, subtype: int, mode: int | None = None, *, protocol: int | None = None
) -> bool | None:
    """Return a matching upload result, never treating an ordinary ACK as upload acceptance."""
    if protocol is not None and getattr(parsed, "protocol_id", None) != protocol:
        return None
    if isinstance(parsed, H6076MusicAck):
        return (
            bool(parsed.is_success)
            if mode is not None and parsed.opcode == subtype and int(parsed.mode) == mode
            else None
        )
    if getattr(parsed, "is_upload", False) and parsed.opcode == subtype:
        return bool(parsed.is_success)
    return None


def parse_command(frame: bytes, model: str = "H617A", *, profile: ModelProfile | None = None) -> Any | None:
    return parse_command_result(frame, model, profile=profile).parsed


def boolean_control_name(operation: str) -> str | None:
    """Map named shared register semantics, never byte offsets or SKU identity."""
    return {"multi_effect": "gradual", "limit": "limit", "power_off_memory": "power_off_memory"}.get(operation)


def boolean_control_is_authorized(control: str, profile: ModelProfile) -> bool:
    """Retain the shipped H617A raw gradual register alongside explicit controls."""
    return control in profile.boolean_controls or (
        control == "gradual" and profile.status_grammar == "H617A" and profile.command_operations is None
    )


def require_profile_packet(frame: bytes, profile: ModelProfile) -> None:
    """Revalidate operation capabilities and geometry at each physical attempt."""
    from .light_commands import parse_static_write

    if profile.setting_grammar == "H6097":
        roots = {"write": ("h6097_control", H6097Control), "query": ("h6097_control.query", H6097Control.Query)}
        for grammar in roots:
            setting = _parse_xor_frame(frame, grammar, roots).parsed
            if setting is not None:
                if not profile.supports_power_on_behaviour or (
                    grammar == "write" and getattr(setting.body.state, "name", None) is None
                ):
                    raise ValueError("Power-on setting is outside profile capabilities")
                return
    if profile.bulk_status_grammar == "H60A":
        query = _parse_xor_frame(frame, "bulk", {"bulk": ("h60a_bulk.query", H60aBulk.Query)}).parsed
        if query is not None:
            bulk_allowed = bulk_status_domains(profile)
            if all(getattr(domain, "name", None) in bulk_allowed for domain in query.domains):
                return
            raise ValueError("Bulk query domains are outside profile capabilities")
    if profile.setting_grammar == "H60A6":
        setting = _parse_xor_frame(frame, "setting", {"setting": ("h60a6_control", H60a6Control)}).parsed
        if setting is not None:
            operation = setting.opcode.name
            if (
                operation == "zone_enable"
                and setting.body.zone.name in profile.boolean_controls
                or operation == "power_on_behaviour"
                and profile.supports_power_on_behaviour
            ):
                return
            raise ValueError("Native setting is outside profile capabilities")
    if (
        profile.effect_grammar == "H60A6"
        and profile.command_operations is not None
        and "effect_upload" in profile.command_operations
        and frame[:1] == bytes((A4_PREFIX,))
    ):
        if not 4 <= len(frame) <= 500 or xor_checksum(frame[:-1]) != frame[-1]:
            raise ValueError("Invalid native effect frame")
        try:
            native_frame = H60a6EffectFrame.from_bytes(frame)
            native_frame._read()
        except KaitaiStructError as error:
            raise ValueError("Invalid native effect frame") from error
        if native_frame.index == 0 and native_frame.body.subtype != H60a6EffectFrame.Subtype.native_effect:
            raise ValueError("Native effect subtype is outside profile capabilities")
        return
    if profile.music_grammar in _MUSIC_WRITE_ROOTS:
        music = _parse_xor_frame(frame, profile.music_grammar, _MUSIC_WRITE_ROOTS).parsed
        if music is not None:
            if profile.command_operations is not None and "music" not in profile.command_operations:
                raise ValueError(f"{profile.name} does not support music")
            slug = getattr(music.selector.mode_id, "name", None)
            if slug not in profile.music_modes:
                raise ValueError("music mode selector is outside profile capabilities")
            variant = music_variant(profile, int(music.selector.mode_id))
            if getattr(music.selector, "has_fixed_colour", 0) and (
                not profile.supports_music_color or (variant is not None and not variant.supports_fixed_colour)
            ):
                raise ValueError("fixed music colour is outside profile capabilities")
            return
    if profile.video_grammar == "H66A0-video" and profile.supports_video_mode:
        video = parse_video_command(frame, "", profile=profile)
        if video is not None:
            if profile.command_operations is not None and "video" not in profile.command_operations:
                raise ValueError(f"{profile.name} does not support video")
            if getattr(video.detail.source, "name", None) not in profile.video_modes:
                raise ValueError("video mode source is outside profile capabilities")
            validate_video_parameters(
                profile.video_grammar,
                {
                    "picture_preset": getattr(video.detail.picture_preset, "name", None),
                    "opaque": int(video.detail.opaque),
                },
            )
            profile.validate_video_saturation(int(video.detail.saturation))
            if video.detail.sound_effects not in (0, 1) or not 0 <= video.detail.softness <= 100:
                raise ValueError("invalid video sound effects or softness")
            return
    command = _parse_xor_frame(frame, profile.command_grammar, _COMMAND_ROOTS).parsed
    if command is not None:
        operation = getattr(command.opcode, "name", "")
        if operation in {"multi", "mode"}:
            sub_attr = getattr(command.body, "sub", getattr(command.body, "sub_mode", None))
            sub_operation = getattr(sub_attr, "name", "")
            if profile.command_operations is not None and sub_operation not in {"static", "static_colour"}:
                operation = sub_operation
            if sub_operation == "music" and getattr(command.opcode, "name", "") in {"multi", "mode"}:
                if (
                    profile.music_grammar in _MUSIC_WRITE_ROOTS
                    or music_slug_for(
                        profile.command_grammar or "",
                        int(
                            getattr(
                                getattr(command.body, "sub_body", getattr(command.body, "detail", None)),
                                "mode_id",
                                getattr(
                                    getattr(command.body, "sub_body", getattr(command.body, "detail", None)),
                                    "mode",
                                    -1,
                                ),
                            )
                        ),
                        profile=profile,
                    )
                    not in profile.music_modes
                ):
                    raise ValueError("music mode selector is outside profile capabilities")
        control = boolean_control_name(operation)
        if control is not None:
            if boolean_control_is_authorized(control, profile):
                return
            raise ValueError(f"{profile.name} does not support boolean control {control}")
        static = parse_static_write(frame, profile=profile)
        if (
            profile.command_operations is None
            or operation in profile.command_operations
            or "static" in profile.command_operations
            and (static is not None or getattr(command, "is_static", False))
        ):
            if static is None and getattr(command, "is_static", False) and profile.command_grammar == "H617A":
                levels = getattr(command.body.sub_body.static_body, "segment_percent", None)
                if levels is not None:
                    if not profile.supports_segments or not profile.supports_segment_brightness:
                        raise ValueError(f"{profile.name} does not support segment brightness")
                    if len(levels) != profile.segment_count or ((1 << len(levels)) - 1) & ~profile.whole_device_mask:
                        raise ValueError("segment brightness outside profile geometry")
            if static is not None:
                if profile.command_grammar == "H601C":
                    detail = command.body.detail
                    companion = bytes((detail.companion_rgb.red, detail.companion_rgb.green, detail.companion_rgb.blue))
                    expected_companion = _TABLE_KELVIN_RGB.get(static.kelvin or 0, bytes(3))
                    if companion != expected_companion:
                        raise ValueError("H601C authored companion RGB does not match Kelvin")
                if static.segment_mask is not None and not static.segment_mask:
                    raise ValueError("no segments selected")
                if static.segment_mask is not None and (
                    not static.whole_strip
                    or (static.brightness_pct is not None and not profile.supports_white_brightness)
                ):
                    if not profile.supports_segments:
                        raise ValueError(f"{profile.name} does not support per-segment control")
                    if static.segment_mask & ~((1 << profile.segment_count) - 1) or (
                        static.segment_mask & ~profile.whole_device_mask
                    ):
                        raise ValueError("segment mask outside profile geometry")
                if static.rgb is not None and not profile.supports_rgb:
                    raise ValueError(f"{profile.name} does not support RGB colour")
                if static.kelvin is not None:
                    if not profile.supports_color_temperature:
                        raise ValueError(f"{profile.name} does not support colour temperature")
                    if not static.whole_strip and not profile.supports_segment_color_temperature:
                        raise ValueError(f"{profile.name} does not support segment colour temperature")
                    if not profile.min_color_temp_kelvin <= static.kelvin <= profile.max_color_temp_kelvin:
                        raise ValueError("static Kelvin outside profile range")
                if static.brightness_pct is not None and not (
                    profile.supports_segments
                    and profile.supports_segment_brightness
                    or static.whole_strip
                    and profile.supports_white_brightness
                ):
                    raise ValueError(f"{profile.name} does not support segment brightness")
            return
    query = _parse_xor_frame(
        frame,
        profile.command_grammar,
        _STATUS_QUERY_ROOTS,
    ).parsed
    if query is not None:
        domain = getattr(query.domain, "name", "")
        control = boolean_control_name(domain)
        if control is not None:
            if boolean_control_is_authorized(control, profile):
                return
            raise ValueError(f"{profile.name} does not support boolean control {control}")
        if domain in {"physical_ic_count", "subordinate_20", "subordinate_21"}:
            if profile.can_read(ReadDomain(domain)):
                return
            raise ValueError(f"{profile.name} does not support {domain} readback")
        if profile.command_operations is None or domain in profile.read_domains:
            return
    upload = _parse_xor_frame(frame, "A3", {"A3": ("command_write.upload_frame", CommandWrite.UploadFrame)}).parsed
    if upload is not None and upload.index == 0 and upload.body.subtype == 0x41:
        if (profile.command_operations is not None and "music" not in profile.command_operations) or not any(
            variant.template for variant in profile.music_variants
        ):
            raise ValueError("music parameter upload is outside profile capabilities")
        return
    if profile.command_operations is not None and "effect_upload" in profile.command_operations:
        if upload is not None and profile.effect_grammar == "H60A6":
            if upload.index == 0 and upload.body.subtype != H60a6EffectFrame.Subtype.native_effect:
                raise ValueError("Native effect subtype is outside profile capabilities")
            return
        if upload is not None and profile.effect_grammar == "H617A":
            if upload.index == 0:
                from .scenes import SCENE_ENTRIES

                scene_types = {
                    entry.scene_type
                    for entry in SCENE_ENTRIES.get(profile.scene_catalogue_sku or "", ())
                    if not entry.selector_only
                }
                allowed = {
                    1: profile.supports_scenes and 1 in scene_types,
                    2: (profile.supports_scenes and 2 in scene_types)
                    or profile.supports_advanced_effects
                    or profile.command_grammar == "H7020",
                    4: profile.supports_custom_effects,
                }
                if not allowed.get(upload.body.subtype, False):
                    raise ValueError("effect upload subtype is outside profile capabilities")
            return
    if profile.command_operations is None:
        return
    raise ValueError(f"{profile.name} does not support this operation")


def parse_a3_effect_envelope(envelope: bytes, model: str, *, profile: ModelProfile | None = None) -> Any:
    """Parse one validated, padded A3 effect envelope through its generated root."""
    if not isinstance(envelope, bytes):
        raise TypeError("A3 effect envelope must be bytes")
    if len(envelope) < A3_CHUNK_SIZE or len(envelope) % A3_CHUNK_SIZE:
        raise ValueError("A3 effect envelope must contain complete 17-byte chunks")
    if envelope[0] != 0x01:
        raise ValueError("A3 effect envelope has an invalid marker")
    if envelope[1] != len(envelope) // A3_CHUNK_SIZE:
        raise ValueError("A3 effect envelope does not match its chunk count")

    grammar = (profile or get_profile(model)).effect_grammar
    if grammar == "H617A":
        root_type = {
            0x01: SceneType1Body,
            0x02: SceneBody,
            0x03: DiyType03,
            0x04: DiyType04,
        }.get(envelope[2])
        if root_type is None:
            raise ValueError(f"H617A A3 body type 0x{envelope[2]:02x} is not supported")
    elif grammar == "H6099":
        root_type = H6099EffectUpload
    elif grammar == "H6199":
        root_type = H6199EffectUpload
    elif grammar == "H60A6":
        root_type = H60a6EffectFrame.A3Envelope
    else:
        raise ValueError(f"{model} has no generated A3 effect grammar")

    try:
        parsed = root_type(KaitaiStream(io.BytesIO(envelope)))
        parsed._read()
        if grammar == "H6099" and int(parsed.kind) in (3, 4):
            _ = parsed.diy
    except KaitaiStructError as error:
        raise ValueError(f"invalid {model} A3 effect envelope") from error
    if not parsed._io.is_eof():
        raise ValueError(f"{model} A3 effect grammar did not consume the envelope")
    if grammar == "H60A6" and any(parsed.padding):
        raise ValueError("Native A3 effect envelope contains non-zero transport fill")
    return parsed


def _command_types(model: str, profile: ModelProfile | None = None) -> tuple[Any, Any, Any]:
    resolved = (profile or get_profile(model)).command_grammar
    if resolved == "H7020":
        return H7020CommandWrite, CommandWrite.PowerCmd, CommandWrite.BrightnessCmd
    if resolved in {"H601C", "H6099", "H6179", "H6199"}:
        root_type = _COMMAND_ROOTS[resolved][1]
        return root_type, root_type.PowerBody, root_type.BrightnessBody
    if resolved != "H617A":
        raise ValueError(f"{model} has no generated command grammar")
    return CommandWrite, CommandWrite.PowerCmd, CommandWrite.BrightnessCmd


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
    root_type = _STATUS_QUERY_ROOTS[grammar][1]
    body_types = StatusQuery if grammar == "H7020" else root_type
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
        body = _child(root_type.SegmentQueryBody, root)
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
    elif domain == "colour_mode" and grammar in {"H601C", "H617A", "H7020"}:
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


def build_boolean_control(control: str, enabled: bool, model: str, *, profile: ModelProfile | None = None) -> bytes:
    """Build a qualified shared register write; revision gating belongs to the profile."""
    profile = profile or get_profile(model)
    if control not in profile.boolean_controls or profile.command_grammar not in {"H617A", "H7020"}:
        raise ValueError(f"{model} does not support boolean control {control}")
    if type(enabled) is not bool:
        raise ValueError("boolean control requires a boolean")
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
    root.body = _child(root_type.BooleanCmd if root_type is H7020CommandWrite else root_type.MultiEffectCmd, root)
    root.body.flag = int(enabled)
    if root_type is H7020CommandWrite:
        root.body.unknown_tail = bytes(16)
    else:
        root.body.padding = [0] * 16
    return _serialize_xor(root)


def build_boolean_control_query(control: str, model: str, *, profile: ModelProfile | None = None) -> bytes:
    """Read a declared boolean register independently of ordinary read domains."""
    profile = profile or get_profile(model)
    if control not in profile.boolean_controls or profile.command_grammar not in {"H617A", "H7020"}:
        raise ValueError(f"{model} does not support boolean control {control}")
    if profile.setting_grammar == "H60A6" and control in H60a6Control.Zone.__members__:
        return build_bulk_status_query(profile, domains=("zone_enable",))
    domain = {"gradual": "multi_effect", "limit": "limit", "power_off_memory": "power_off_memory"}.get(control)
    root_type = _STATUS_QUERY_ROOTS[profile.command_grammar][1]
    if domain is None or domain not in root_type.QueryDomain.__members__:
        raise ValueError("unknown boolean control")
    return _build_status_query(domain, profile.command_grammar)


def bulk_status_domains(profile: ModelProfile) -> frozenset[str]:
    domains: set[str] = set()
    if profile.boolean_controls & H60a6Control.Zone.__members__.keys():
        domains.add("zone_enable")
    if profile.supports_power_on_behaviour:
        domains.add("power_on_behaviour")
    return frozenset(domains)


def build_bulk_status_query(profile: ModelProfile, *, domains: tuple[str, ...] | None = None) -> bytes:
    """Request independently admitted extension records alongside the base observations."""
    if profile.bulk_status_grammar != "H60A":
        raise ValueError("Device profile does not support bulk observations")
    allowed = bulk_status_domains(profile)
    domains = tuple(sorted(allowed)) if domains is None else domains
    if not set(domains) <= allowed:
        raise ValueError("Bulk query domains are outside profile capabilities")
    root = H60aBulk.Query()
    root.header = b"\xac\x03"
    root.domain_count = len(domains)
    root.domains = [H60aBulk.Domain[name] for name in domains]
    root.padding = bytes(16 - root.domain_count)
    return _serialize_xor(root)


def build_power_on_behaviour(value: str, profile: ModelProfile) -> bytes:
    if (
        profile.setting_grammar not in {"H60A6", "H6097"}
        or not profile.supports_power_on_behaviour
        or value not in H60aBulk.PowerOnState.__members__
    ):
        raise ValueError("Unsupported power-on behaviour")
    root_type = H60a6Control if profile.setting_grammar == "H60A6" else H6097Control
    root = root_type()
    root.header = b"\x33"
    root.opcode = root_type.Command.power_on_behaviour
    root.body = _child(root_type.PowerOnCommand, root)
    root.body.selector = b"\x02"
    root.body.state = H60aBulk.PowerOnState[value]
    root.body.unknown_tail = bytes(15)
    return _serialize_xor(root)


def build_power_on_behaviour_query(profile: ModelProfile) -> bytes:
    if not profile.supports_power_on_behaviour:
        raise ValueError("Unsupported power-on behaviour")
    if profile.setting_grammar == "H60A6":
        return build_bulk_status_query(profile, domains=("power_on_behaviour",))
    if profile.setting_grammar != "H6097":
        raise ValueError("Unsupported power-on setting grammar")
    root = H6097Control.Query()
    root.header = b"\xaa\x41\x02"
    root.unknown_tail = bytes(16)
    return _serialize_xor(root)


def parse_zone_notification(frame: bytes, profile: ModelProfile) -> ProtocolParseResult:
    grammar = "H60A6" if profile.setting_grammar == "H60A6" else None
    return _parse_xor_frame(
        frame, grammar, {"H60A6": ("h60a6_control.zone_notification", H60a6Control.ZoneNotification)}
    )


def is_bulk_status_frame(frame: bytes, profile: ModelProfile) -> bool:
    return profile.bulk_status_grammar == "H60A" and frame[:1] == b"\xac"


class BulkStatusCollector:
    """Collect one bounded subscription-local response before interpreting any records."""

    def __init__(self) -> None:
        self._count: int | None = None
        self._final_size = 0
        self._position = 0
        self._payload = bytearray()
        self.complete = False
        self.failed = False

    def feed(self, frame: bytes) -> ProtocolParseResult:
        if self.failed:
            return ProtocolParseResult(None, "h60a_bulk", ProtocolParseRejection.SCHEMA_REJECTED)
        result = _parse_xor_frame(frame, "H60A", {"H60A": ("h60a_bulk", H60aBulk)})
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
            payload = H60aBulk.Payload.from_bytes(bytes(self._payload))
            payload._read()
            domains = [int(record.domain) for record in payload.records]
            if len(domains) != len(set(domains)):
                raise ValueError("Bulk response has duplicate domains")
            self.complete = True
            return ProtocolParseResult(payload, "h60a_bulk.payload", None)
        except KaitaiStructError, ValueError:
            self.failed = True
            return ProtocolParseResult(None, result.parser, ProtocolParseRejection.SCHEMA_REJECTED)


def parse_boolean_control(generated: Any, model: str, *, profile: ModelProfile | None = None) -> dict[str, bool]:
    """Decode register replies only; mode flags and command ACKs are not confirmation."""
    profile = profile or get_profile(model)
    domain = getattr(getattr(generated, "domain", None), "name", "")
    control = boolean_control_name(domain)
    if control is None or control not in profile.boolean_controls:
        return {}
    flag = generated.body.flag
    if flag not in (0, 1):
        raise ValueError("boolean register reply must be 0 or 1")
    return {control: bool(flag)}


def build_configured_strings_query(profile: ModelProfile) -> bytes:
    """Read configured strings, independently of physical IC count."""
    if not profile.configured_string_counts or profile.command_grammar != "H7020":
        raise ValueError(f"{profile.name} does not support configured strings")
    return _build_status_query("configured_strings", profile.command_grammar)


def build_configured_strings(count: int, profile: ModelProfile) -> bytes:
    if type(count) is not int or count not in profile.configured_string_counts or profile.command_grammar != "H7020":
        raise ValueError("unsupported configured string count")
    root = H7020CommandWrite()
    root.header = b"\x33"
    root.opcode = H7020CommandWrite.CommandOp.configured_strings
    root.body = _child(H7020CommandWrite.ConfiguredStringsCmd, root)
    root.body.count = count
    root.body.unknown_tail = bytes(16)
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


def _video_grammar(model: str, profile: ModelProfile | None = None) -> str:
    profile = profile or get_profile(model)
    if not profile.supports_video_mode or profile.video_grammar is None:
        raise ValueError(f"{model} does not support video mode")
    return profile.video_grammar


def _video_command_grammar(model: str, profile: ModelProfile | None = None) -> str:
    profile = profile or get_profile(model)
    grammar = _video_grammar(model, profile)
    if grammar == "H66A0-video" and profile.command_grammar in {"H6099", "H6199"}:
        return profile.command_grammar
    return grammar


def build_white_balance_query(model: str, *, profile: ModelProfile | None = None) -> bytes:
    profile = profile or get_profile(model)
    if not profile.supports_white_balance_readback or not profile.can_read(ReadDomain.DISPLAY_SETTING):
        raise ValueError(f"{model} does not support white-balance readback")
    if (grammar := profile.command_grammar) in {"H6099", "H6199"} or (
        grammar == "H617A" and profile.video_white_balance_representation == "scalar"
    ):
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
    if resolved not in _STATUS_QUERY_ROOTS or not hasattr(_STATUS_QUERY_ROOTS[resolved][1], "SegmentQueryBody"):
        raise ValueError(f"{model} has no generated segment-query grammar")
    if type(group) is not int:
        raise ValueError("segment query group must be an integer")
    try:
        return _build_status_query("segments", resolved, segment_group=group)
    except KaitaiStructError as error:
        raise ValueError("segment query group is outside the selected grammar") from error


def _parse_a3_scene(
    root_type: Any,
    scene_type_byte: int,
    raw_param: bytes,
    trailing_padding_of: Any,
) -> tuple[Any, int]:
    """Frame a stripped catalogue parameter and parse it through a generated A3 root.

    The parameter carries the real bytes only, so an unpadded read first measures the
    genuine trailing padding before the synthetic envelope padding a reassembled capture
    would carry is appended for the returned tree.
    """
    if not isinstance(raw_param, bytes):
        raise TypeError("scene parameter must be bytes")
    synthetic = root_type()
    header = _a3_header(synthetic)
    header_length = len(header.marker) + 1
    header.linecount = max(header.linecount, math.ceil((header_length + 1 + len(raw_param)) / A3_CHUNK_SIZE))
    check_generated_tree(header)
    header_bytes = _write(header, header_length)
    envelope = header_bytes + bytes((scene_type_byte,)) + raw_param
    unpadded = root_type(KaitaiStream(io.BytesIO(envelope)))
    unpadded._read()
    trailing_padding = len(trailing_padding_of(unpadded))
    envelope = envelope.ljust(header.linecount * A3_CHUNK_SIZE, b"\x00")
    parsed = root_type(KaitaiStream(io.BytesIO(envelope)))
    parsed._read()
    return parsed, trailing_padding


def parse_scene_body(raw_param: bytes) -> tuple[Any, int]:
    """Parse a catalogue type-2 parameter, returning its tree and real trailing padding."""
    return _parse_a3_scene(SceneBody, int(SceneBody.SceneType.scene_v2), raw_param, lambda root: root.padding)


def parse_scene_body_param(raw_param: bytes) -> Any:
    """Parse a catalogue type-2 parameter through the generated SceneBody root."""
    return parse_scene_body(raw_param)[0]


def parse_workshop_body(raw_param: bytes) -> tuple[Any, int]:
    """Parse an H617A Workshop parameter through the generated WorkshopBody root."""
    return _parse_a3_scene(WorkshopBody, 2, raw_param, lambda root: root.padding)


def parse_scene_type1_body(raw_param: bytes) -> tuple[Any, int]:
    """Parse a catalogue type-1 parameter, returning its tree and real trailing padding."""
    return _parse_a3_scene(SceneType1Body, 1, raw_param, lambda root: root.content.padding)


def parse_scene_type1_body_param(raw_param: bytes) -> Any:
    """Parse a catalogue type-1 parameter through the generated SceneType1Body root."""
    return parse_scene_type1_body(raw_param)[0]


def serialize_scene_body_param(root: Any) -> bytes:
    """Serialize a built type-2 SceneBody root and return its catalogue parameter bytes."""
    _set_effect_layer_lengths(root.records)
    return _serialize_a3_scene_param(root)


def serialize_workshop_body_param(root: Any) -> bytes:
    """Serialize a built H617A WorkshopBody root and return its parameter bytes."""
    _set_effect_layer_lengths(root.layers)
    return _serialize_a3_scene_param(root)


def serialize_scene_type1_body_param(root: Any) -> bytes:
    """Serialize a built type-1 SceneType1Body root and return its catalogue parameter bytes."""
    return _serialize_a3_scene_param(root)


def build_h617a_diy_painted_body(
    effect: str,
    speed: int,
    brightness: int,
    background: tuple[int, int, int],
    groups: list[tuple[tuple[int, int, int], list[int]]],
) -> bytes:
    """Serialize the diy_type03 fields after its A3 type byte."""
    root = DiyType03()
    root.header = _a3_header(root)
    root.body_type = b"\x03"
    root.effect = getattr(DiyType03.Effect, effect)
    root.speed = speed
    root.brightness = brightness
    root.background = _rgb(root, *background)
    root.num_groups = len(groups)
    root.groups = []
    for fill, segments in groups:
        group = _child(DiyType03.PaintGroup, root)
        group.num_segment_indices = len(segments)
        group.fill = _rgb(group, *fill)
        group.segment_indices = segments
        root.groups.append(group)
    root.padding = []
    length = 10 + sum(4 + len(segments) for _, segments in groups)
    check_generated_tree(root)
    return _write(root, length)[3:]


def _diy_type04_palette(parent: Any, colours: list[tuple[int, int, int]]) -> Any:
    palette = _child(DiyType04.Palette, parent)
    palette.colours = [_rgb(palette, *colour) for colour in colours]
    return palette


def build_h617a_diy_single_body(
    family: int,
    variant: int,
    speed: int,
    palette: list[tuple[int, int, int]],
) -> bytes:
    """Serialize the diy_type04 Flat fields after the A3 type byte."""
    root = DiyType04()
    root.header = _a3_header(root)
    root.a3_type = b"\x04"
    root.family = family
    body = _child(DiyType04.FlatBody, root)
    body.variant = variant
    body.speed = speed
    body.len_palette = len(palette) * 3
    body.palette = _diy_type04_palette(body, palette)
    body.padding = []
    root.body = body
    length = 7 + body.len_palette
    check_generated_tree(root)
    return _write(root, length)[3:]


def build_h617a_diy_multi_body(
    effects: list[tuple[int, int]],
    speed: int,
    palette: list[tuple[int, int, int]],
) -> bytes:
    """Serialize the diy_type04 Combo fields after the A3 type byte."""
    root = DiyType04()
    root.header = _a3_header(root)
    root.a3_type = b"\x04"
    root.family = 0xFF
    body = _child(DiyType04.ComboBody, root)
    body.variant = 0
    body.speed = speed
    body.len_palette = len(palette) * 3
    body.palette = _diy_type04_palette(body, palette)
    body.seqlen = len(effects) * 2
    body.pairs = []
    for family, variant in effects:
        pair = _child(DiyType04.FamilyVariant, body)
        pair.family = family
        pair.variant = variant
        body.pairs.append(pair)
    body.padding = []
    root.body = body
    length = 8 + body.len_palette + body.seqlen
    check_generated_tree(root)
    return _write(root, length)[3:]


def build_power(on: bool, model: str = "H617A", *, profile: ModelProfile | None = None) -> bytes:
    root_type, power_type, _ = _command_types(model, profile)
    root = root_type()
    root.header = b"\x33"
    root.opcode = root_type.CommandOpcode.power if root_type is H6179CommandWrite else root_type.CommandOp.power
    body = power_type(None, root, root._root)
    body.is_on = int(on)
    if root_type is H6179CommandWrite:
        body.opaque = bytes(16)
    elif root_type is H601cCommandWrite:
        body.padding = bytes(16)
    root.body = body
    return _serialize_xor(root)


def build_brightness(percent: int, model: str = "H617A", *, profile: ModelProfile | None = None) -> bytes:
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
    if root_type is H601cCommandWrite:
        body.padding = bytes(16)
    root.body = body
    return _serialize_xor(root)


def _build_h617a_static_colour(
    mask: int,
    *,
    direct: tuple[int, int, int],
    kelvin: int,
    preview: tuple[int, int, int],
    root_type: Any = CommandWrite,
) -> bytes:
    root = root_type()
    root.header = b"\x33"
    root.opcode = root_type.CommandOp.multi
    multi = _child(root_type.MultiCmd, root)
    multi.sub = root_type.MultiSub.static
    static = _child(root_type.StaticCmd, multi)
    static.static_sub = 1
    colour = _child(root_type.StaticColor, static)
    colour.rgb_direct = _rgb(colour, *direct)
    colour.kelvin = kelvin
    colour.rgb_preview = _rgb(colour, *preview)
    segment_mask = _child(root_type.SegmentMask, colour)
    segment_mask.bits = mask
    colour.mask = segment_mask
    if root_type is H7020CommandWrite:
        colour.unknown_tail = bytes(3)
    static.static_body = colour
    multi.sub_body = static
    root.body = multi
    return _serialize_xor(root)


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


def table_kelvin_rgb(kelvin: int) -> tuple[int, int, int]:
    red, green, blue = _TABLE_KELVIN_RGB.get(kelvin, bytes(3))
    return red, green, blue


def _build_h601c_static_colour(mask: int, direct: tuple[int, int, int], kelvin: int, profile: ModelProfile) -> bytes:
    if mask != profile.whole_device_mask or not mask:
        raise ValueError("H601C supports whole-device colour only")
    if kelvin and not 2700 <= kelvin <= 6500:
        raise ValueError("H601C Kelvin outside 2700..6500")
    if kelvin and kelvin not in _TABLE_KELVIN_RGB:
        raise ValueError("H601C Kelvin must use 100 K steps from 2700 to 6500")
    root = H601cCommandWrite()
    root.header = b"\x33"
    root.opcode = H601cCommandWrite.CommandOp.mode
    mode = _child(H601cCommandWrite.ModeBody, root)
    mode.sub_mode = H601cCommandWrite.ModeSel.static_colour
    detail = _child(H601cCommandWrite.StaticColourBody, mode)
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
    if resolved == "H601C":
        return _build_h601c_static_colour(mask, (red, green, blue), 0, profile)
    if resolved == "H6179":
        if mask != 0:
            raise ValueError("H6179 static colour is inherently whole-device and has no segment mask")
        return _build_h6179_static_colour(
            direct=(red, green, blue),
            kelvin=0,
            preview=(0, 0, 0),
        )
    if resolved in {"H6099", "H6199"}:
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
        mode.detail = detail
        root.body = mode
        return _serialize_xor(root)

    if resolved not in {"H617A", "H7020"}:
        raise ValueError(f"{model} has no generated static-colour grammar")
    return _build_h617a_static_colour(
        mask,
        direct=(red, green, blue),
        kelvin=0,
        preview=(0, 0, 0),
        root_type=_COMMAND_ROOTS[resolved][1],
    )


def build_colour_temperature(
    kelvin: int,
    preview: tuple[int, int, int],
    mask: int,
    model: str = "H617A",
    *,
    profile: ModelProfile | None = None,
) -> bytes:
    profile = profile or get_profile(model)
    value = max(profile.min_color_temp_kelvin, min(profile.max_color_temp_kelvin, kelvin))
    resolved = profile.command_grammar
    if resolved == "H601C":
        return _build_h601c_static_colour(mask, (255, 255, 255), kelvin, profile)
    if resolved == "H6179":
        if mask != 0:
            raise ValueError("H6179 colour temperature is inherently whole-device and has no segment mask")
        return _build_h6179_static_colour(
            direct=(255, 255, 255),
            kelvin=value,
            preview=preview,
        )
    if resolved in {"H6099", "H6199"}:
        root_type = _COMMAND_ROOTS[resolved][1]
        root = root_type()
        root.header = b"\x33"
        root.opcode = root_type.CommandOp.mode
        mode = _child(root_type.ModeBody, root)
        mode.sub_mode = root_type.ModeSel.static_colour
        detail = _child(root_type.StaticColourBody, mode)
        detail.operation = root_type.StaticOperation.colour
        detail.red, detail.green, detail.blue = profile.kelvin_direct_rgb
        detail.kelvin = value
        detail.preview = _rgb(detail, *preview)
        detail.segment_mask = mask
        mode.detail = detail
        root.body = mode
        return _serialize_xor(root)

    if resolved not in {"H617A", "H7020"}:
        raise ValueError(f"{model} has no generated colour-temperature grammar")
    return _build_h617a_static_colour(
        mask,
        direct=profile.kelvin_direct_rgb,
        kelvin=value,
        preview=table_kelvin_rgb(value) if profile.kelvin_direct_rgb == (255, 255, 255) else preview,
        root_type=_COMMAND_ROOTS[resolved][1],
    )


def build_segment_brightness(
    mask: int,
    percent: int,
    model: str = "H617A",
    *,
    profile: ModelProfile | None = None,
) -> bytes:
    value = max(0, min(100, percent))
    resolved = (profile or get_profile(model)).command_grammar
    if resolved == "H6179":
        raise ValueError("H6179 has no segment-brightness operation")
    if resolved in {"H6099", "H6199"}:
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
        mode.detail = detail
        root.body = mode
        return _serialize_xor(root)

    if resolved not in {"H617A", "H7020"}:
        raise ValueError(f"{model} has no generated segment-brightness grammar")
    root_type = _COMMAND_ROOTS[resolved][1]
    root = root_type()
    root.header = b"\x33"
    root.opcode = root_type.CommandOp.multi
    multi = _child(root_type.MultiCmd, root)
    multi.sub = root_type.MultiSub.static
    static = _child(root_type.StaticCmd, multi)
    static.static_sub = 2
    brightness = _child(root_type.StaticBrightness, static)
    brightness.percent = value
    segment_mask = _child(root_type.SegmentMask, brightness)
    segment_mask.bits = mask
    brightness.mask = segment_mask
    if root_type is H7020CommandWrite:
        brightness.unknown_tail = bytes(10)
    static.static_body = brightness
    multi.sub_body = static
    root.body = multi
    return _serialize_xor(root)


def build_scene_activation(
    model: str,
    scene_code: int,
    music_code: int = 0,
    *,
    scene_type: int = 0,
    profile: ModelProfile | None = None,
) -> bytes:
    """Encode a scene selector using only the target's evidenced command grammar."""
    grammar = (profile or get_profile(model)).command_grammar
    if grammar in {"H617A", "H7020"}:
        return build_h617a_scene(scene_code, scene_type=scene_type, root_type=_COMMAND_ROOTS[grammar][1])
    if grammar == "H6179":
        if music_code or scene_type:
            raise ValueError("H6179 scene selector has no music-code or scene-type field")
        return build_h6179_scene(scene_code)
    if grammar == "H6199":
        return build_h6199_scene(scene_code, music_code)
    if grammar in {"H601C", "H6099"}:
        if music_code or scene_type:
            raise ValueError(f"{grammar} scene selector has no music-code or scene-type field")
        root_type = _COMMAND_ROOTS[grammar][1]
        root = root_type()
        root.header = b"\x33"
        root.opcode = root_type.CommandOp.mode
        mode = _child(root_type.ModeBody, root)
        mode.sub_mode = root_type.ModeSel.scene
        detail = _child(root_type.SceneBody, mode)
        detail.scene_id = max(0, min(0xFFFF, scene_code))
        if grammar == "H601C":
            detail.padding = bytes(14)
        mode.detail = detail
        root.body = mode
        return _serialize_xor(root)
    raise ValueError(f"{model} has no generated scene activation grammar")


def build_h617a_scene(scene_code: int, *, scene_type: int = 0, root_type: Any = CommandWrite) -> bytes:
    root = root_type()
    root.header = b"\x33"
    root.opcode = root_type.CommandOp.multi
    multi = _child(root_type.MultiCmd, root)
    multi.sub = root_type.MultiSub.scene
    detail = _child(CommandWrite.SceneActivate, multi)
    detail.code = max(0, min(0xFFFF, scene_code))
    detail.scene_type = max(0, min(0xFF, scene_type))
    multi.sub_body = detail
    root.body = multi
    return _serialize_xor(root)


def build_h617a_diy_activation(diy_code: int, *, root_type: Any = CommandWrite) -> bytes:
    root = root_type()
    root.header = b"\x33"
    root.opcode = root_type.CommandOp.multi
    multi = _child(root_type.MultiCmd, root)
    multi.sub = root_type.MultiSub.diy
    selector = _child(GoveeCommon.DiySelector, multi)
    selector.code = diy_code
    multi.sub_body = selector
    root.body = multi
    return _serialize_xor(root)


def build_diy_activation(diy_code: int, model: str, *, profile: ModelProfile | None = None) -> bytes:
    if type(diy_code) is not int or not 0 <= diy_code <= 0xFFFF:
        raise ValueError("DIY code must be an integer from 0 to 65535")
    grammar = (profile or get_profile(model)).command_grammar
    if grammar in {"H617A", "H7020"}:
        return build_h617a_diy_activation(diy_code, root_type=_COMMAND_ROOTS[grammar][1])
    if grammar == "H601C":
        root = H601cCommandWrite()
        root.header = b"\x33"
        root.opcode = H601cCommandWrite.CommandOp.mode
        mode = _child(H601cCommandWrite.ModeBody, root)
        mode.sub_mode = H601cCommandWrite.ModeSel.diy
        detail = _child(H601cCommandWrite.DiyBody, mode)
        detail.code = diy_code
        detail.padding = bytes(14)
        mode.detail = detail
        root.body = mode
        return _serialize_xor(root)
    if grammar == "H6099":
        return build_h6099_diy_activation(diy_code)
    if grammar == "H6179":
        return build_h6179_diy_activation(diy_code)
    raise ValueError(f"{model} has no generated DIY activation grammar")


def build_h6099_diy_activation(diy_code: int = 254) -> bytes:
    """Select a device-resident DIY code; this does not authorize DIY upload."""
    if type(diy_code) is not int or not 0 <= diy_code <= 0xFFFF:
        raise ValueError("DIY code must be an integer from 0 to 65535")
    root = H6099CommandWrite()
    root.header = b"\x33"
    root.opcode = H6099CommandWrite.CommandOp.mode
    mode = _child(H6099CommandWrite.ModeBody, root)
    mode.sub_mode = H6099CommandWrite.ModeSel.diy
    detail = _child(H6099CommandWrite.DiyBody, mode)
    detail.code = diy_code
    mode.detail = detail
    root.body = mode
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
    if grammar == "H66A0-video":
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


def video_parameters_from_detail(detail: Any, grammar: str | None) -> dict[str, Any] | None:
    if grammar != "H66A0-video":
        return None
    return validate_video_parameters(
        grammar, {"picture_preset": getattr(detail.picture_preset, "name", None), "opaque": int(detail.opaque)}
    )


def parse_video_command(frame: bytes, model: str, *, profile: ModelProfile | None = None) -> Any | None:
    return _parse_xor_frame(
        frame,
        (profile or get_profile(model)).video_grammar,
        {"H66A0-video": ("h66a0_video_command", H66a0VideoCommand)},
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
    if resolved != "H7020" and selector_parameters:
        raise ValueError("Music selector parameters are unsupported by this grammar")
    if resolved == "H6076":
        return _build_h6076_music_selector(mode_id, sensitivity, colour, calm)
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
    if resolved in {"H6097", "H1A42", "H61F5", "H66A0", "H7025"}:
        root_cls = (
            H6097MusicWrite
            if resolved == "H6097"
            else H1a42MusicWrite
            if resolved == "H1A42"
            else H61f5MusicWrite
            if resolved == "H61F5"
            else H66a0MusicWrite
            if resolved == "H66A0"
            else H7025MusicWrite
        )
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
        selector.unknown_tail = bytes(14 - (2 + (3 if colour is not None else 0) if selector.is_legacy else 0))
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
        detail.opaque = bytes(10 if colour is not None else 13)
        mode.payload = detail
        root.body = mode
        return _serialize_xor(root)
    if resolved in {"H6099", "H6199"}:
        root_type = _COMMAND_ROOTS[resolved][1]
        root = root_type()
        root.header = b"\x33"
        root.opcode = root_type.CommandOp.mode
        mode = _child(root_type.ModeBody, root)
        mode.sub_mode = root_type.ModeSel.music
        detail = _child(root_type.MusicBody, mode)
        detail.mode = root_type.MusicMode(mode_id)
        detail.sensitivity = max(0, min(100, sensitivity))
        if resolved == "H6199" or detail.is_legacy:
            detail.is_calm = int(calm)
            detail.has_fixed_colour = int(colour is not None)
            detail.fixed_colour = _rgb(detail, *(colour or (0, 0, 0)))
        elif colour is not None:
            raise ValueError("new H6099 music selectors omit fixed colour")
        mode.detail = detail
        root.body = mode
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
    mode_id: int, sensitivity: int, colour: tuple[int, int, int] | None, calm: bool
) -> bytes:
    root = H6076MusicWrite()
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


h6102_outbound_transform = h6102_outbound_transform_for()
