"""Profile-selected command, status and acknowledgement parsing."""

from __future__ import annotations

from typing import Any

from .const import ModelProfile, get_profile
from .protocol_commands import _extended_static_root, video_parameters_from_detail
from .protocol_core import (
    _COMMAND_ACK_ROOTS,
    _COMMAND_ROOTS,
    _EXTENDED_STATIC_ROOTS,
    _H6076_ACK_ROOTS,
    _MUSIC_WRITE_ROOTS,
    _STATUS_ROOTS,
    H66a0VideoCommand,
    H605cVideoCommand,
    ProtocolParseRejection,
    ProtocolParseResult,
    _has_unknown_discriminator,
    _parse_xor_frame,
)
from .protocol_settings import _NATIVE_SETTING_ROOTS


def parse_status_result(
    frame: bytes, model: str = "H617A", *, profile: ModelProfile | None = None
) -> ProtocolParseResult:
    from .low_blue_light import parse_setting

    profile = profile or get_profile(model)
    setting = parse_setting(frame, profile)
    if setting.parsed is not None:
        return setting
    return _parse_xor_frame(frame, profile.status_grammar, _STATUS_ROOTS)


def parse_status(frame: bytes, model: str = "H617A", *, profile: ModelProfile | None = None) -> Any | None:
    return parse_status_result(frame, model, profile=profile).parsed


def parse_command_result(
    frame: bytes, model: str = "H617A", *, profile: ModelProfile | None = None
) -> ProtocolParseResult:
    effective_profile = profile or get_profile(model)
    if effective_profile.setting_grammar in _NATIVE_SETTING_ROOTS:
        root_type = _NATIVE_SETTING_ROOTS[effective_profile.setting_grammar][1]
        setting = _parse_xor_frame(frame, effective_profile.setting_grammar, _NATIVE_SETTING_ROOTS)
        if setting.parsed is not None and getattr(setting.parsed.opcode, "name", None) is not None:
            if (
                setting.parsed.opcode == root_type.Command.zone_enable
                and getattr(setting.parsed.body.zone, "name", None) is None
            ) or (
                setting.parsed.opcode == root_type.Command.power_on_behaviour
                and getattr(setting.parsed.body.state, "name", None) is None
            ):
                return ProtocolParseResult(None, setting.parser, ProtocolParseRejection.SEMANTIC_REJECTED)
            return setting
    if (
        effective_profile.video_grammar in {"H66A0-video", "H605C-video"}
        and effective_profile.supports_video_mode
        and frame[:3] == b"\x33\x05\x00"
    ):
        video = _parse_xor_frame(
            frame,
            effective_profile.video_grammar,
            {
                "H66A0-video": ("h66a0_video_command", H66a0VideoCommand),
                "H605C-video": ("h605c_video_command", H605cVideoCommand),
            },
        )
        if video.parsed is not None:
            if (
                getattr(video.parsed.detail.source, "name", None) not in effective_profile.video_modes
                or video.parsed.detail.sound_effects not in (0, 1)
                or not effective_profile.video_softness_min
                <= video.parsed.detail.softness
                <= effective_profile.video_softness_max
            ):
                return ProtocolParseResult(None, video.parser, ProtocolParseRejection.SEMANTIC_REJECTED)
            try:
                effective_profile.validate_video_saturation(int(video.parsed.detail.saturation))
                video_parameters_from_detail(video.parsed.detail, effective_profile.video_grammar)
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
    extended_root = _extended_static_root(effective_profile)
    if extended_root is not None and frame.startswith(bytes(extended_root[1](None).static_prefix)):
        result = _parse_xor_frame(frame, effective_profile.extended_static_grammar, _EXTENDED_STATIC_ROOTS)
    else:
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
    if profile.music_grammar in _H6076_ACK_ROOTS:
        music = _parse_xor_frame(frame, profile.music_grammar, _H6076_ACK_ROOTS)
        if music.parsed is not None and (profile.music_grammar != "H1771" or music.parsed.is_upload):
            return music
    return _parse_xor_frame(frame, profile.command_ack_grammar or profile.command_grammar, _COMMAND_ACK_ROOTS)


def parse_command(frame: bytes, model: str = "H617A", *, profile: ModelProfile | None = None) -> Any | None:
    return parse_command_result(frame, model, profile=profile).parsed
