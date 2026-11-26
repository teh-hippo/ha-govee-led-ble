"""Capability and geometry admission for physical protocol writes."""

from __future__ import annotations

from typing import Any

from kaitaistruct import KaitaiStructError

from .const import WHOLE_BULB_GRAMMARS, ModelProfile, ReadDomain
from .music_protocol import music_slug_for
from .music_semantics import music_variant
from .native_effect_codecs import native_effect_codec_for_profile
from .protocol_commands import (
    _TABLE_KELVIN_RGB,
    _extended_static_root,
    parse_video_command,
    video_parameters_from_detail,
)
from .protocol_core import (
    _COMMAND_ROOTS,
    _H8604_VIDEO_ROOTS,
    _MUSIC_WRITE_ROOTS,
    _STATUS_QUERY_ROOTS,
    CommandWrite,
    H60a6Control,
    H60aBulk,
    H605cVideoSettings,
    H607cControl,
    H1771Bulk,
    H6093Projector,
    H6181DiyBody,
    StatusQuery,
    _parse_xor_frame,
)
from .protocol_parsing import parse_command_result
from .protocol_settings import (
    _NATIVE_SETTING_ROOTS,
    _ORDINARY_SETTING_ROOTS,
    _POWER_ON_QUERY_ROOTS,
    boolean_control_is_authorized,
    boolean_control_name,
    bulk_status_domains,
)
from .transport import A4_PREFIX, xor_checksum


def _check_low_blue_light_packet(frame: bytes, profile: ModelProfile) -> bool:
    """Native low-blue-light setting frames."""
    from .low_blue_light import parse_setting, require_low_blue_light

    if parse_setting(frame, profile, "envelope").parsed is not None:
        require_low_blue_light(profile)
        if not any(parse_setting(frame, profile, kind).parsed is not None for kind in ("write", "query")):
            raise ValueError("Invalid low-blue-light setting packet")
        return True
    return False


def _check_projector_packet(frame: bytes, profile: ModelProfile) -> bool:
    if profile.projector_grammar != "H6093" and profile.setting_grammar != "H6093":
        return False
    power = _parse_xor_frame(
        frame, "power", {"power": ("h6093_projector.setting_write", H6093Projector.SettingWrite)}
    ).parsed
    if power is not None:
        setting = getattr(power.body.selector, "name", None)
        if not (
            setting == "projection_power"
            and "power" in (profile.command_operations or ())
            or profile.setting_grammar == "H6093"
            and setting in profile.boolean_controls
        ):
            raise ValueError("Projector setting is outside the profile")
        return True
    audio = _parse_xor_frame(
        frame, "audio", {"audio": ("h6093_projector.audio_write", H6093Projector.AudioWrite)}
    ).parsed
    if audio is not None:
        if profile.setting_grammar != "H6093":
            raise ValueError("Local audio is outside the profile")
        if audio.opcode == H6093Projector.Command.local_sound:
            allowed = 1 <= audio.body.code <= len(profile.local_sound_options)
        else:
            allowed = (
                profile.local_volume_range is not None
                and profile.local_volume_range[0] <= audio.body.level <= profile.local_volume_range[1]
            )
        if not allowed:
            raise ValueError("Local audio is outside the product bounds")
        return True
    query = _parse_xor_frame(
        frame, "query", {"query": ("h6093_projector.power_query", H6093Projector.PowerQuery)}
    ).parsed
    if query is not None:
        if not profile.can_read(ReadDomain.POWER):
            raise ValueError("Projection power readback is outside the profile")
        return True
    for kind, allowed, root in (
        ("activation", profile.projector_control_revision is not None, H6093Projector.Activation),
        ("query", profile.projector_control_revision == 0, H6093Projector.ReadQuery),
    ):
        parsed = _parse_xor_frame(frame, kind, {kind: (f"h6093_projector.{kind}", root)}).parsed
        if parsed is not None:
            if not allowed or "projector" not in (profile.command_operations or ()):
                raise ValueError("Projector operation requires the qualified revision")
            return True
    return False


def _check_ordinary_setting_packet(frame: bytes, profile: ModelProfile) -> bool:
    """Admit independently declared register settings and installation operations."""
    if profile.setting_grammar in _ORDINARY_SETTING_ROOTS:
        setting = _parse_xor_frame(frame, profile.setting_grammar, _ORDINARY_SETTING_ROOTS).parsed
        if setting is not None:
            operation = getattr(setting.opcode, "name", None)
            if operation == "power_on_behaviour":
                if not profile.supports_power_on_behaviour or getattr(setting.body.state, "name", None) is None:
                    raise ValueError("Power-on setting is outside profile capabilities")
                return True
            if operation == "strip_calibration" and profile.strip_length_metres:
                body = setting.body
                action = getattr(body.operation, "name", None)
                if profile.setting_grammar == "H612A":
                    if action in {"start", "cancel", "confirm"}:
                        if body.source != 0 or body.ic_count != 0:
                            raise ValueError("H612A calibration boundary command is invalid")
                        return True
                    capacity = (
                        profile.physical_ic_capacity or max(profile.strip_length_metres) * profile.strip_ics_per_metre
                    )
                    if action == "locate" and body.source == 0 and 1 <= body.ic_count <= capacity:
                        return True
                    raise ValueError("H612A strip calibration is outside product capacity")
                if action in {"start", "cancel", "confirm"}:
                    return True
                capacity = max(profile.strip_length_metres) * profile.strip_ics_per_metre
                if action == "locate" and body.detail.source == 0 and 1 <= body.detail.ic_count <= capacity:
                    return True
                if (
                    action in {"cut", "restore"}
                    and body.detail.count == 1
                    and body.detail.ic_counts[0]
                    in {length * profile.strip_ics_per_metre for length in profile.strip_length_metres}
                ):
                    return True
            raise ValueError("Ordinary setting is outside profile capabilities")
        query = _parse_xor_frame(frame, profile.setting_grammar, _POWER_ON_QUERY_ROOTS).parsed
        if query is not None:
            if not profile.supports_power_on_behaviour:
                raise ValueError("Power-on setting is outside profile capabilities")
            return True
    return False


def _check_native_setting_packet(frame: bytes, profile: ModelProfile) -> bool:
    """Independent source registers with codec-selected query shapes."""
    if profile.setting_grammar in _NATIVE_SETTING_ROOTS:
        root_type = _NATIVE_SETTING_ROOTS[profile.setting_grammar][1]
        setting = _parse_xor_frame(frame, profile.setting_grammar, _NATIVE_SETTING_ROOTS).parsed
        if setting is not None and (operation := getattr(setting.opcode, "name", None)) is not None:
            if (
                operation == "zone_enable"
                and getattr(setting.body.zone, "name", None) in profile.boolean_controls
                or operation == "power_on_behaviour"
                and profile.supports_power_on_behaviour
                and getattr(setting.body.state, "name", None) is not None
                or operation == "gradual"
                and "gradual" in profile.boolean_controls
                or operation == "box_light"
                and profile.supports_hdmi_box_light
            ):
                return True
            raise ValueError("Native setting is outside profile capabilities")
        query_checks = [
            (getattr(root_type, "PowerOnQuery", H607cControl.PowerOnQuery), profile.supports_power_on_behaviour),
            (getattr(root_type, "GradualQuery", H607cControl.GradualQuery), "gradual" in profile.boolean_controls),
        ]
        if hasattr(root_type, "DeviceInfoQuery") and hasattr(root_type, "Zone"):
            query_checks.append(
                (root_type.DeviceInfoQuery, bool(profile.boolean_controls & root_type.Zone.__members__.keys()))
            )
        for query_type, query_allowed in query_checks:
            query = _parse_xor_frame(frame, "native", {"native": ("native_setting.query", query_type)}).parsed
            if query is not None:
                if query_allowed:
                    return True
                raise ValueError("Native setting query is outside profile capabilities")
    return False


def _check_bulk_query_packet(frame: bytes, profile: ModelProfile) -> bool:
    """Qualified bulk status queries."""
    roots = {"H60A": ("h60a_bulk.query", H60aBulk.Query), "H1771": ("h1771_bulk.query", H1771Bulk.Query)}
    if profile.bulk_status_grammar in roots:
        query = _parse_xor_frame(frame, profile.bulk_status_grammar, roots).parsed
        if query is not None:
            bulk_allowed = bulk_status_domains(profile)
            if all(getattr(domain, "name", None) in bulk_allowed for domain in query.domains):
                return True
            raise ValueError("Bulk query domains are outside profile capabilities")
    return False


def _check_h60a6_setting_packet(frame: bytes, profile: ModelProfile) -> bool:
    """H60A6 native setting writes."""
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
                return True
            raise ValueError("Native setting is outside profile capabilities")
    return False


def _check_native_effect_frame(frame: bytes, profile: ModelProfile) -> bool:
    """Native effect frames through their profile-selected carrier."""
    codec = native_effect_codec_for_profile(profile)
    if (
        codec is not None
        and codec.a4_frame_type is not None
        and profile.command_operation_supported("effect_upload")
        and frame[:1] == bytes((A4_PREFIX,))
    ):
        if not 4 <= len(frame) <= 500 or xor_checksum(frame[:-1]) != frame[-1]:
            raise ValueError("Invalid native effect frame")
        try:
            native_frame = codec.a4_frame_type.from_bytes(frame)
            native_frame._read()
        except KaitaiStructError as error:
            raise ValueError("Invalid native effect frame") from error
        if native_frame.index == 0 and codec.admits_upload(profile, int(native_frame.body.subtype)) is not True:
            raise ValueError("Native effect subtype is outside profile capabilities")
        return True
    return False


def _check_music_write_packet(frame: bytes, profile: ModelProfile) -> bool:
    """Music mode writes."""
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
            return True
    return False


def _check_video_write_packet(frame: bytes, profile: ModelProfile) -> bool:
    """Video mode writes."""
    if profile.video_grammar == "H605C-video":
        scalar = _parse_xor_frame(frame, "scalar", {"scalar": ("h605c_video_settings", H605cVideoSettings)}).parsed
        if scalar is not None and scalar.header in {scalar.FrameHeader.write, scalar.FrameHeader.query}:
            if not profile.supports_whole_relative_brightness:
                raise ValueError("whole-video brightness is outside profile capabilities")
            return True
        for grammar, roots in (("H6199", _COMMAND_ROOTS), ("H6199", _STATUS_QUERY_ROOTS)):
            parsed = _parse_xor_frame(frame, grammar, roots).parsed
            if parsed is None:
                continue
            operation = getattr(getattr(parsed, "opcode", getattr(parsed, "domain", None)), "name", None)
            if operation == "display_setting":
                setting = getattr(parsed.body.setting, "name", None)
                if setting in {
                    name
                    for name, supported in (
                        ("white_balance", profile.supports_white_balance),
                        ("blank_screen", profile.supports_blank_screen),
                    )
                    if supported
                }:
                    return True
    if profile.video_control_grammar is not None:
        for roots in (_COMMAND_ROOTS, _STATUS_QUERY_ROOTS):
            display = _parse_xor_frame(frame, profile.video_control_grammar, roots).parsed
            if display is None:
                continue
            operation = getattr(getattr(display, "opcode", getattr(display, "domain", None)), "name", None)
            if operation != "display_setting":
                continue
            setting = getattr(display.body.setting, "name", None)
            if setting == "hdr_contrast" and profile.supports_hdr_contrast:
                if roots is _COMMAND_ROOTS:
                    enabled = int(display.body.payload.is_enabled)
                    contrast = int(display.body.payload.contrast)
                    if enabled not in (0, 1) or not (
                        profile.video_hdr_contrast_min <= contrast <= profile.video_hdr_contrast_max
                    ):
                        raise ValueError("HDR contrast is outside profile capabilities")
                return True
            if setting == "hdr_contrast":
                raise ValueError("HDR contrast is outside profile capabilities")
    if profile.video_grammar in {"H66A0-video", "H605C-video"} and profile.supports_video_mode:
        video = parse_video_command(frame, "", profile=profile)
        if video is not None:
            if profile.command_operations is not None and "video" not in profile.command_operations:
                raise ValueError(f"{profile.name} does not support video")
            if getattr(video.detail.source, "name", None) not in profile.video_modes:
                raise ValueError("video mode source is outside profile capabilities")
            video_parameters_from_detail(video.detail, profile.video_grammar)
            profile.validate_video_saturation(int(video.detail.saturation))
            if (
                video.detail.sound_effects not in (0, 1)
                or not profile.video_softness_min <= video.detail.softness <= profile.video_softness_max
            ):
                raise ValueError("invalid video sound effects or softness")
            return True
    return False


def _check_h8604_video_setting_packet(frame: bytes, profile: ModelProfile) -> bool:
    if profile.setting_grammar != "H8604":
        return False
    root = _H8604_VIDEO_ROOTS["H8604-video"][1]
    if frame[:1] == b"\x33":
        setting = _parse_xor_frame(frame, "H8604-video", _H8604_VIDEO_ROOTS).parsed
        if setting is None:
            return False
        name = getattr(setting.body.setting, "name", None)
        if name == "sensitivity" and profile.supports_video_sensitivity:
            value = int(setting.body.payload.value)
            if profile.video_sensitivity_min <= value <= profile.video_sensitivity_max:
                return True
            raise ValueError("Video sensitivity is outside profile capabilities")
        if name == "hdmi_input" and profile.supports_hdmi_input:
            if 1 <= int(setting.body.payload.selected) <= profile.hdmi_input_count:
                return True
            raise ValueError("HDMI input is outside profile capabilities")
        if name == "colour_calibration" and profile.supports_video_color_calibration:
            values = [
                int(setting.body.payload.yellow),
                int(setting.body.payload.blue),
                int(setting.body.payload.purple),
            ]
            if setting.body.length == 4:
                values.append(int(setting.body.payload.red))
            if all(
                profile.video_color_calibration_min <= value <= profile.video_color_calibration_max for value in values
            ):
                return True
            raise ValueError("Video colour calibration is outside profile capabilities")
        raise ValueError("H8604 video register is outside profile capabilities")
    query = _parse_xor_frame(
        frame, "H8604-video.query", {"H8604-video.query": ("h8604_video_settings.query", root.Query)}
    ).parsed
    if query is None:
        return False
    name = getattr(query.setting, "name", None)
    if (
        name == "sensitivity"
        and profile.supports_video_sensitivity
        or name == "hdmi_input"
        and profile.supports_hdmi_input
        or name == "colour_calibration"
        and profile.supports_video_color_calibration
    ):
        return True
    return False


def _command_mode_parts(command: Any, grammar: str | None) -> tuple[str, Any]:
    operation = getattr(command.opcode, "name", "")
    if operation == "multi":
        return getattr(command.body.sub, "name", ""), command.body.sub_body
    if operation == "mode":
        if grammar == "H6179":
            return getattr(command.body.mode, "name", ""), command.body.payload
        return getattr(command.body.sub_mode, "name", ""), command.body.detail
    return "", None


def _check_command_packet(frame: bytes, profile: ModelProfile) -> bool:
    """Ordinary command writes."""
    from .light_commands import static_write_from_command

    result = parse_command_result(frame, profile=profile)
    command = result.parsed
    extended_root = _extended_static_root(profile)
    if command is None and extended_root is not None and result.parser == extended_root[0]:
        raise ValueError("Invalid extended static command")
    if command is not None:
        if profile.command_grammar == "H60B0":
            from .h60b0_controls import validate_command

            if validate_command(command, profile):
                return True
        operation = getattr(command.opcode, "name", "")
        if operation == "zone_enable" and profile.setting_grammar == "H1771":
            control = getattr(command.body.source, "name", None)
            if control in profile.boolean_controls and command.body.enabled in (0, 1):
                return True
            raise ValueError("Source control is outside profile capabilities")
        if operation == "power_on_behaviour" and profile.setting_grammar == "H1771":
            if (
                profile.supports_power_on_behaviour
                and getattr(command.body.selector, "name", None) == "state"
                and getattr(command.body.state, "name", None) is not None
            ):
                return True
            raise ValueError("Power-on behaviour is outside profile capabilities")
        if operation in {"bar_enable", "swap_bars"}:
            if (
                profile.setting_grammar == "H6046"
                and profile.command_operation_supported(operation)
                and profile.boolean_controls
                == {
                    "left_bar_enabled",
                    "right_bar_enabled",
                }
            ):
                return True
            raise ValueError("Bar control is outside profile capabilities")
        if operation in {"multi", "mode"}:
            sub_operation, detail = _command_mode_parts(command, profile.command_grammar)
            if sub_operation == "inline_diy":
                if profile.diy_upload_transport != "single" or not profile.supports_custom_effects:
                    raise ValueError("Inline DIY is outside profile capabilities")
                allowed = dict(profile.diy_family_variants or ())
                if detail.variant not in allowed.get(int(detail.family), ()) or not 1 <= detail.speed <= 100:
                    raise ValueError("Inline DIY family, variation or speed is outside profile capabilities")
                sub_operation = "diy"
            elif sub_operation == "diy" and profile.diy_upload_transport == "single":
                raise ValueError("Inline DIY cannot be replaced by a resident selector")
            if profile.command_operations is not None and sub_operation not in {"static", "static_colour"}:
                operation = sub_operation
            if sub_operation == "music":
                mode_id = (
                    detail.effect_id
                    if profile.command_grammar == "H6179"
                    else detail.mode_id
                    if profile.command_grammar in {"H617A", "H7020"}
                    else detail.mode
                )
                if (
                    music_slug_for(profile.command_grammar or "", int(mode_id), profile=profile)
                    not in profile.music_modes
                ):
                    raise ValueError("music mode selector is outside profile capabilities")
                if not profile.music_sensitivity_min <= detail.sensitivity <= profile.music_sensitivity_max:
                    raise ValueError("music sensitivity is outside profile capabilities")
                variant = music_variant(profile, int(mode_id))
                if variant is not None and variant.fixed_colour_default is not None and not detail.has_fixed_colour:
                    raise ValueError("This music mode requires a fixed colour")
        control = boolean_control_name(operation)
        if control is not None:
            if control in profile.boolean_controls:
                if profile.command_grammar == "H1771" and command.body.flag not in (0, 1):
                    raise ValueError("Invalid boolean control value")
                return True
            raise ValueError(f"{profile.name} does not support boolean control {control}")
        if (
            operation == "scene" or operation in {"multi", "mode"} and sub_operation == "scene"
        ) and profile.scene_codes is not None:
            _sub_operation, detail = _command_mode_parts(command, profile.command_grammar)
            code = getattr(detail, "code", getattr(detail, "scene_id", None))
            if code not in profile.scene_codes:
                raise ValueError("scene selector is outside the confirmed revision")
            if profile.selector_only_scene_bits is not None and getattr(detail, "music_code", 0) != 0:
                raise ValueError("selector-only scene does not accept a companion music code")
        static = static_write_from_command(command, profile)
        if (
            profile.command_operations is None
            or operation in profile.command_operations
            or "static" in profile.command_operations
            and (static is not None or getattr(command, "is_static", False))
        ):
            if (
                static is None
                and getattr(command, "is_static", False)
                and profile.command_grammar in {"H1771", "H617A", "H607C"}
            ):
                levels = getattr(command.body.sub_body.static_body, "segment_percent", None)
                if levels is not None:
                    if not profile.supports_segments or not profile.supports_segment_brightness:
                        raise ValueError(f"{profile.name} does not support segment brightness")
                    if len(levels) != profile.segment_count or ((1 << len(levels)) - 1) & ~profile.whole_device_mask:
                        raise ValueError("segment brightness outside profile geometry")
                    if profile.command_grammar == "H1771" and (
                        command.body.sub_body.static_body.page != 1 or any(level > 100 for level in levels)
                    ):
                        raise ValueError("invalid H1771 brightness page")
            if static is not None:
                if profile.command_grammar in WHOLE_BULB_GRAMMARS:
                    detail = command.body.detail
                    companion = bytes((detail.companion_rgb.red, detail.companion_rgb.green, detail.companion_rgb.blue))
                    expected_companion = _TABLE_KELVIN_RGB.get(static.kelvin or 0, bytes(3))
                    if companion != expected_companion:
                        raise ValueError(f"{profile.command_grammar} authored companion RGB does not match Kelvin")
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
                    if (
                        not profile.min_color_temp_kelvin <= static.kelvin <= profile.max_color_temp_kelvin
                        or static.kelvin not in _TABLE_KELVIN_RGB
                    ):
                        raise ValueError("static Kelvin outside profile range or off the 100 K grid")
                if static.brightness_pct is not None and not (
                    profile.supports_segments
                    and profile.supports_segment_brightness
                    or static.whole_strip
                    and profile.supports_white_brightness
                ):
                    raise ValueError(f"{profile.name} does not support segment brightness")
            return True
    return False


def _check_status_query_packet(frame: bytes, profile: ModelProfile) -> bool:
    """Status queries."""
    try:
        segment_query = StatusQuery.SegmentEnvelope.from_bytes(frame)
        segment_query._read()
    except EOFError, KaitaiStructError:
        segment_query = None
    if segment_query is not None:
        if not profile.can_read(ReadDomain.SEGMENTS):
            raise ValueError("Segment query requires qualified readback")
        if not segment_query.has_group or not 1 <= segment_query.group <= profile.segment_group_count:
            raise ValueError("segment query group is outside the selected geometry")
    query = _parse_xor_frame(
        frame,
        profile.command_grammar,
        _STATUS_QUERY_ROOTS,
    ).parsed
    if query is not None:
        domain = getattr(query.domain, "name", "")
        if domain == "colour_mode" and profile.command_grammar in {"H6046", "H6199", "H1771", "H60B0"}:
            if query.body.selector != profile.colour_mode_query_selector:
                raise ValueError("colour mode query selector is outside the profile")
        if domain in {"segments", "legacy_segments"}:
            if not profile.can_read(ReadDomain.SEGMENTS):
                raise ValueError("Segment query requires qualified readback")
            if not 1 <= query.body.group <= profile.segment_group_count:
                raise ValueError("segment query group is outside the selected geometry")
            if profile.command_grammar == "H6199" and (
                (domain == "legacy_segments") != (profile.status_grammar == "H6199-Pact1")
            ):
                raise ValueError("segment query format is outside the profile")
            return True
        if profile.command_grammar == "H60B0" and domain in {"source_info", "power_on_behaviour"}:
            if (
                domain == "source_info"
                and profile.boolean_controls
                or domain == "power_on_behaviour"
                and profile.supports_power_on_behaviour
            ):
                return True
            raise ValueError("Source setting query is outside the profile")
        if domain == "bar_enable":
            if profile.setting_grammar == "H6046" and profile.boolean_controls:
                return True
            raise ValueError("Bar control readback is outside profile capabilities")
        control = boolean_control_name(domain)
        if control is not None:
            if boolean_control_is_authorized(control, profile):
                return True
            raise ValueError(f"{profile.name} does not support boolean control {control}")
        if domain in {"physical_ic_count", "subordinate_20", "subordinate_21"}:
            if profile.can_read(ReadDomain(domain)):
                return True
            raise ValueError(f"{profile.name} does not support {domain} readback")
        if segment_query is None and (profile.command_operations is None or domain in profile.read_domains):
            return True
    if segment_query is not None:
        raise ValueError("Segment query is outside the declared command grammar")
    return False


def _check_upload_packet(frame: bytes, profile: ModelProfile) -> bool:
    """A3 music-parameter and effect uploads."""
    if profile.diy_upload_transport == "a1_02":
        legacy = _parse_xor_frame(frame, "H6181", {"H6181": ("h6181_diy_body.frame", H6181DiyBody.Frame)}).parsed
        if legacy is not None:
            if profile.supports_custom_effects and (
                profile.command_operations is None or "effect_upload" in profile.command_operations
            ):
                return True
            raise ValueError("Palette DIY upload is outside profile capabilities")
    upload = _parse_xor_frame(frame, "A3", {"A3": ("command_write.upload_frame", CommandWrite.UploadFrame)}).parsed
    if upload is not None and upload.index == 0 and profile.scene_upload_subtypes is not None:
        subtype = int(upload.body.subtype)
        if subtype in profile.scene_upload_subtypes:
            if not profile.supports_advanced_effects:
                raise ValueError("scene upload is outside the confirmed revision")
            return True
    if upload is not None and upload.index == 0 and upload.body.subtype == 0x41:
        if (profile.command_operations is not None and "music" not in profile.command_operations) or not any(
            variant.template for variant in profile.music_variants
        ):
            raise ValueError("music parameter upload is outside profile capabilities")
        return True
    if (
        upload is not None
        and upload.index != 0
        and (
            (profile.command_operations is None or "music" in profile.command_operations)
            and any(variant.template for variant in profile.music_variants)
            or profile.supports_advanced_effects
            and profile.scene_upload_subtypes
        )
    ):
        return True
    if upload is not None and upload.index == 0:
        codec = native_effect_codec_for_profile(profile)
        if codec is not None:
            admitted = codec.admits_upload(profile, int(upload.body.subtype))
            if admitted is not None:
                if not admitted:
                    raise ValueError("Native effect upload is outside profile capabilities")
                return True
    if upload is not None and profile.command_operations is not None and "effect_upload" in profile.command_operations:
        codec = native_effect_codec_for_profile(profile)
        if upload is not None and codec is not None and upload.index == 0:
            admitted = codec.admits_upload(profile, int(upload.body.subtype))
            if admitted is not None:
                if not admitted:
                    raise ValueError("Native upload command is outside profile capabilities")
                return True
        if upload is not None and codec is not None and upload.index != 0:
            return True
        if upload is not None and (
            codec is not None
            or profile.effect_grammar
            in {
                "H6046",
                "H6053",
                "H617A",
                "H6181",
            }
        ):
            if upload.index == 0:
                from .scenes import SCENE_ENTRIES, scene_supported

                scene_types = {
                    entry.scene_type
                    for entry in SCENE_ENTRIES.get(profile.scene_catalogue_sku or "", ())
                    if not entry.selector_only
                    and scene_supported(entry, profile)
                    and profile.selector_only_scene_bits is None
                }
                allowed = {
                    **(
                        {profile.native_diy_upload_subtype: profile.supports_custom_effects}
                        if profile.native_diy_upload_subtype is not None
                        else {}
                    ),
                    **{subtype: profile.supports_advanced_effects for _, subtype, _ in profile.workshop_carriers},
                    1: profile.supports_scenes
                    and (1 in scene_types or any(subtype == 1 for _, subtype, _ in profile.shared_scene_carriers))
                    or profile.supports_advanced_effects
                    and any(subtype == 1 for _, subtype, _ in profile.workshop_carriers),
                    2: profile.supports_scenes
                    and (2 in scene_types or any(subtype == 2 for _, subtype, _ in profile.shared_scene_carriers))
                    or (
                        profile.supports_advanced_effects
                        or profile.effect_workflows is not None
                        and "advanced" in profile.effect_workflows
                    )
                    or profile.command_grammar == "H7020",
                    3: profile.supports_custom_effects
                    and profile.effect_workflows is not None
                    and "painted" in profile.effect_workflows,
                    4: profile.supports_custom_effects
                    and (profile.effect_grammar != "H6181" or profile.diy_upload_transport == "a3"),
                }
                if not allowed.get(upload.body.subtype, False):
                    raise ValueError("effect upload subtype is outside profile capabilities")
            return True
    return False


def require_profile_packet(frame: bytes, profile: ModelProfile) -> None:
    """Revalidate operation capabilities and geometry at each physical attempt.

    Each ``_check_*`` stage returns True when it accepted the frame and False to let the next
    stage try, either because the frame is not its grammar or because that grammar does not
    apply to this profile.
    """
    for check in (
        _check_projector_packet,
        _check_low_blue_light_packet,
        _check_ordinary_setting_packet,
        _check_native_setting_packet,
        _check_bulk_query_packet,
        _check_h60a6_setting_packet,
        _check_native_effect_frame,
        _check_music_write_packet,
        _check_video_write_packet,
        _check_h8604_video_setting_packet,
        _check_command_packet,
        _check_status_query_packet,
        _check_upload_packet,
    ):
        if check(frame, profile):
            return
    if profile.command_operations is None:
        return
    raise ValueError(f"{profile.name} does not support this operation")
