"""Reconstructed H607C codec checks, not hardware qualification."""

import time
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError
from homeassistant.core import ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.ha_govee_led_ble import generated_protocol_adapter as adapter
from custom_components.ha_govee_led_ble.const import DOMAIN, ModelProfile, ReadDomain, get_profile
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.dreamview import (
    DreamviewMember,
    MusicGroup,
    build_dreamview_command,
    build_dreamview_group,
    build_dreamview_query,
    parse_dreamview_ack,
    parse_dreamview_status,
)
from custom_components.ha_govee_led_ble.dreamview_services import _async_dreamview_service
from custom_components.ha_govee_led_ble.effect_application import EffectStudioApplication
from custom_components.ha_govee_led_ble.effect_catalogue import MODEL_EFFECT_CATALOGUES
from custom_components.ha_govee_led_ble.effect_commands import DiyPaintGroup, build_h607c_diy_painted
from custom_components.ha_govee_led_ble.effect_compiler import compile_application, compile_music_profile
from custom_components.ha_govee_led_ble.effect_deployments import PriorControlState
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem, MusicProfile, effect_content_to_dict
from custom_components.ha_govee_led_ble.effect_runtime import (
    async_apply_compiled_profile,
    async_prepare_effect_control_state,
)
from custom_components.ha_govee_led_ble.effect_websocket_payloads import item_summary
from custom_components.ha_govee_led_ble.h607c_effects import decode_zoned_diy, encode_zoned_diy
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.light_commands import build_segment_color, build_segment_color_temp
from custom_components.ha_govee_led_ble.music_commands import (
    build_zoned_music_body,
    default_music_zones,
    prepare_music_request,
)
from custom_components.ha_govee_led_ble.music_semantics import MusicParamSpec, MusicVariant, MusicZone, music_variant
from custom_components.ha_govee_led_ble.native_effect import native_effect_from_value, native_effect_to_value
from custom_components.ha_govee_led_ble.protocol_core import H607cMusicWrite, H607cPaintBody
from custom_components.ha_govee_led_ble.protocol_music_params import (
    encode_music_parameters,
    native_music_zone_body,
    parse_music_parameters,
)
from custom_components.ha_govee_led_ble.transport import fragment_a3, reassemble_a3, xor_checksum

HOPPING = bytes.fromhex("3302ff00000000ff00000019620103123a")
PAIRED = bytes.fromhex("82331002ff00000000ff00000019620103123a4f070200ff00ffffff")


@pytest.fixture
def profile():
    return ModelProfile(
        "H607C codec fixture",
        command_grammar="H607C",
        command_ack_grammar="H607C",
        status_grammar="H607C",
        setting_grammar="H607C",
        effect_grammar="H607C",
        music_grammar="H607C",
        command_operations=frozenset({"power", "brightness", "static", "scene", "diy", "music", "effect_upload"}),
        read_domains=frozenset(
            {ReadDomain.POWER, ReadDomain.BRIGHTNESS, ReadDomain.COLOUR_MODE, ReadDomain.FIRMWARE, ReadDomain.HARDWARE}
        ),
        supports_rgb=True,
        supports_color_temperature=True,
        min_color_temp_kelvin=2200,
        max_color_temp_kelvin=6500,
        whole_device_mask=0x1FFF,
        segment_count=13,
        supports_segment_writes=True,
        supports_segment_brightness=True,
        supports_segment_color_temperature=True,
        boolean_controls=frozenset({"pole_enabled", "base_enabled", "gradual"}),
        supports_power_on_behaviour=True,
        supports_scenes=True,
        supports_custom_effects=True,
        physical_ic_count=144,
        music_modes=tuple(mode.name for mode in H607cMusicWrite.MusicMode),
        music_upload_before_selector=True,
        music_requires_upload_ack=True,
        music_variants=(
            MusicVariant(
                51,
                "H607C reconstructed palette companion",
                "h607c_music_body",
                HOPPING,
                (
                    MusicParamSpec("music_background", "background", "background", "number", 0, 0, 0xFFFFFF),
                    MusicParamSpec(
                        "music_background_brightness",
                        "relative_brightness",
                        "background_brightness",
                        "number",
                        25,
                        0,
                        50,
                    ),
                ),
                palette_bounds=(1, 8),
                requires_physical_ic_count=True,
                supports_fixed_colour=False,
            ),
            MusicVariant(130, "H607C reconstructed paired companion", "h607c_music_body", PAIRED),
        ),
        dreamview_grammar="H607C",
        dreamview_operations=frozenset(
            {
                "replace_group",
                "switch_group",
                "member_brightness",
                "same_brightness",
                "member_connect",
                "delete_group",
                "music",
                "scene",
            }
        ),
        dreamview_reads=frozenset({"switch_group", "member_brightness", "same_brightness", "member_connect", "music"}),
        dreamview_max_sub_devices=10,
        dreamview_requires_group_ack=True,
    )


def frame(prefix: str) -> bytes:
    payload = bytes.fromhex(prefix).ljust(19, b"\x00")
    return payload + bytes((xor_checksum(payload),))


def test_native_controls_are_independent_and_queries_use_exact_selectors(profile):
    pole = adapter.build_boolean_control("pole_enabled", True, "H607C", profile=profile)
    base = adapter.build_boolean_control("base_enabled", False, "H607C", profile=profile)
    memory = adapter.build_power_on_behaviour("off", profile)
    assert pole == frame("33300001")
    assert base == frame("33300100")
    assert memory == frame("33410202")
    assert adapter.build_boolean_control_query("base_enabled", "H607C", profile=profile) == frame("aa0708")
    assert adapter.build_power_on_behaviour_query(profile) == frame("aa4100")
    for packet in (pole, base, memory, frame("aa0708"), frame("aa4100")):
        adapter.require_profile_packet(packet, profile)
    for packet in (pole, base, frame("aa0708")):
        with pytest.raises(ValueError):
            adapter.require_profile_packet(packet, replace(profile, boolean_controls=frozenset()))
    with pytest.raises(ValueError):
        adapter.require_profile_packet(memory, replace(profile, supports_power_on_behaviour=False))
    for packet in (pole, base, memory):
        assert adapter.parse_command(packet, "H607C", profile=profile) is not None
    gradual = adapter.build_boolean_control("gradual", True, "H607C", profile=profile)
    assert gradual == bytes.fromhex("33a3010000000000000000000000000000000091")
    assert adapter.build_boolean_control_query("gradual", "H607C", profile=profile) == bytes.fromhex(
        "aaa3000000000000000000000000000000000009"
    )
    adapter.require_profile_packet(gradual, profile)
    assert adapter.parse_command(gradual, "H607C", profile=profile) is not None


def test_native_diy_zone_edits_preserve_sibling_disable_state_and_extensions():
    raw = bytes.fromhex("0b996a0b593202ff00000000ffaabb0000dead")
    content = decode_zoned_diy(raw)
    restored = native_effect_from_value(native_effect_to_value(content))
    assert restored == content and encode_zoned_diy(restored) == raw
    assert content.layers[0].opaque == b"\xaa\xbb"
    assert not content.layers[1].enabled
    changed = replace(content, layers=(replace(content.layers[0], speed=73), content.layers[1]))
    encoded = encode_zoned_diy(changed)
    assert [
        (index, before, after)
        for index, (before, after) in enumerate(zip(raw, encoded, strict=True))
        if before != after
    ] == [(5, 50, 73)]
    assert decode_zoned_diy(encoded) == changed


def test_native_diy_two_palettes_round_trip_without_treating_them_as_global_power():
    raw = bytes.fromhex("0b71003201ff00000200ff000000ff")
    content = decode_zoned_diy(raw)
    layer = content.layers[0]
    assert layer.palette == ((255, 0, 0),)
    assert layer.secondary_palette == ((0, 255, 0), (0, 0, 255))
    assert encode_zoned_diy(content) == raw


def test_native_info_and_async_flags_use_different_positions_and_preserve_unknowns(profile):
    info = adapter.parse_status(frame("aa07082585"), "H607C", profile=profile)
    notification = adapter.parse_zone_notification(frame("ee302585"), profile).parsed
    assert info is not None and notification is not None
    assert info.body.detail.brightness == 37
    assert notification.body.unknown_prefix == 37
    for root, flags in ((info, info.body.detail.flags), (notification, notification.body.flags)):
        assert adapter.parse_boolean_control(root, "H607C", profile=profile) == {
            "pole_enabled": False,
            "base_enabled": True,
        }
        assert flags.master_enabled and flags.unknown_mask == 0x80
    assert adapter.parse_zone_notification(frame("aa07082585"), profile).parsed is None
    assert adapter.parse_zone_notification(frame("aa302585"), profile).parsed is None
    memory = adapter.parse_status(frame("aa410102"), "H607C", profile=profile)
    assert memory.body.open_flag == 1 and memory.body.state.name == "off"


def test_static_writes_keep_high_mask_bits_and_bound_the_thirteenth_segment(profile):
    colour = build_segment_color((1, 13), 17, 34, 51, "H607C", profile=profile)
    assert colour == frame("3305150111223300000000000110")
    white = build_segment_color_temp((13,), 2200, "H607C", profile=profile)
    parsed = adapter.parse_command(white, "H607C", profile=profile)
    assert parsed.body.sub_body.static_body.mask.bits == 0x1000
    assert parsed.body.sub_body.static_body.kelvin == 2200
    for packet in (colour, white):
        adapter.require_profile_packet(packet, profile)
    with pytest.raises(ValueError, match="geometry"):
        adapter.require_profile_packet(colour, replace(profile, segment_count=12, whole_device_mask=0xFFF))
    vector = frame("330515030102030405060708090a0b0c0daabb")
    adapter.require_profile_packet(vector, profile)
    parsed_vector = adapter.parse_command(vector, "H607C", profile=profile)
    assert parsed_vector.body.sub_body.static_body.segment_percent == list(range(1, 14))
    assert parsed_vector.body.sub_body.static_body.unknown_tail == b"\xaa\xbb"
    with pytest.raises(ValueError, match="geometry"):
        adapter.require_profile_packet(vector, replace(profile, segment_count=12, whole_device_mask=0xFFF))


def test_music_uses_two_header_bytes_upload_before_selection_and_mode_specific_results(profile):
    packets = prepare_music_request(
        "H607C",
        "hopping",
        73,
        None,
        False,
        {"relative_brightness": 31},
        profile=profile,
        palette=((1, 2, 3), (4, 5, 6), (7, 8, 9)),
    )
    assert packets[-1] == frame("3305133349")
    envelope = reassemble_a3(packets[1:-1])
    assert envelope[2:4] == b"\x41\x33"
    root = adapter.parse_a3_effect_envelope(envelope, "H607C", profile=profile)
    assert root.content.body.num_palette == 3
    assert root.content.body.tail.background_brightness == 31
    assert root.content.body.tail.piece_count_max == 58
    assert adapter.upload_ack_mode(packets, len(packets) - 2, "H607C", profile=profile) == 51
    for packet in packets:
        adapter.require_profile_packet(packet, profile)
    for raw, expected in (("a3413300", True), ("a3413301", False)):
        result = adapter.parse_command_ack_result(frame(raw), "H607C", profile=profile).parsed
        assert adapter.upload_ack_success(result, 0x41, 51, protocol=0xA3) is expected
        assert adapter.upload_ack_success(result, 0x41, 130, protocol=0xA3) is None
    ordinary = adapter.parse_command_ack_result(frame("a35600"), "H607C", profile=profile).parsed
    assert adapter.upload_ack_success(ordinary, 0x56, protocol=0xA3) is True
    variant = profile.music_variants[0]
    edited = encode_music_parameters(
        variant,
        {"background": 0x102030},
        palette=None,
        calm=None,
        physical_ic_count=30,
    )
    decoded = parse_music_parameters(variant, edited)
    assert decoded.tail.piece_count_min == 4 and decoded.tail.piece_count_max == 12
    assert (decoded.tail.background.red, decoded.tail.background.green, decoded.tail.background.blue) == (16, 32, 48)
    paired = parse_music_parameters(profile.music_variants[1], PAIRED)
    assert paired.body.pole.mode.name == "hopping" and paired.body.base.mode.name == "fusion"
    assert paired.body.pole.body.tail.piece_count_max == 58


def test_music_dreamview_members_have_scalar_areas_and_reject_camera_forms(profile):
    members = (
        DreamviewMember(cmd_ver=7, mark=3, area_num=13, address="11:22:33:44:55:66"),
        DreamviewMember(cmd_ver=8, mark=1, area_num=5, name="base"),
    )
    envelope = reassemble_a3(build_dreamview_group(members, profile))
    expected = bytes.fromhex("020300076655443322110d010108046261736505")
    assert envelope[2] == 0x60 and envelope[3 : 3 + len(expected)] == expected
    parsed = MusicGroup.from_bytes(envelope[3:])
    parsed._read()
    assert parsed.members[0].area_num == 13 and not hasattr(parsed.members[0], "area_values")
    assert members[0].as_dict()["area_num"] == 13 and "zones" not in members[0].as_dict()
    camera = DreamviewMember(cmd_ver=7, is_rgbic=True, zones=(1,), name="camera")
    for member, target in ((camera, profile), (members[0], get_profile("H6099"))):
        with pytest.raises(ValueError, match="form"):
            build_dreamview_group((member,), target)
    with pytest.raises(ValueError, match="without camera"):
        DreamviewMember(cmd_ver=7, mark=1, area_num=3, is_rgbic=True, zones=(1,), name="mixed")
    ten = tuple(DreamviewMember(cmd_ver=1, mark=1, area_num=1, name=f"member-{index}") for index in range(10))
    assert build_dreamview_group(ten, profile)
    with pytest.raises(ValueError, match="capacity"):
        build_dreamview_group((*ten, DreamviewMember(cmd_ver=1, mark=1, area_num=1, name="extra")), profile)


@pytest.mark.parametrize(
    ("kind", "body", "expected_kind"),
    [
        (0x03, "0900640000000102ff0000008f", "paint"),
        (0x41, PAIRED.hex(), "music"),
        (0x51, "02ff00000000ff", "dreamview_palette"),
        (0x55, "0201020304", "dreamview_protocols"),
        (0x56, "0b996a09593202ff00000000ff0000", "native_diy"),
        (0x58, "01016655443322110a01007f03043412", "dreamview_scene"),
        (0x60, "010100076655443322110d", "dreamview_group"),
    ],
)
def test_native_uploads_keep_transport_commands_separate_from_body_families(profile, kind, body, expected_kind):
    """Reconstructed complete uploads, without asserting rendering or catalogue eligibility."""
    packets = tuple(fragment_a3(kind, bytes.fromhex(body)))
    envelope = reassemble_a3(packets)
    parsed = adapter.parse_a3_effect_envelope(envelope, "H607C", profile=profile)
    assert parsed.kind.name == expected_kind
    for packet in packets:
        adapter.require_profile_packet(packet, profile)
    denied = replace(
        profile,
        command_operations=profile.command_operations - {"music"},
        supports_scenes=False,
        supports_custom_effects=False,
        music_modes=(),
        music_variants=(),
        dreamview_operations=frozenset(),
    )
    with pytest.raises(ValueError, match="outside profile"):
        adapter.require_profile_packet(packets[0], denied)


def test_music_dreamview_commands_do_not_inherit_camera_discriminators(profile):
    assert build_dreamview_command("switch_group", {"enabled": True}, profile) == frame("33600101")
    assert build_dreamview_command("delete_group", {}, profile) == frame("336007ff")
    assert build_dreamview_query("switch_group", profile) == frame("aa6001")
    assert parse_dreamview_ack(frame("33600100"), profile) == ("switch_group", True)
    assert parse_dreamview_ack(frame("33600701"), profile) == ("delete_group", False)
    values = {"music_type": 1, "selector": 0x1234, "second_parameter": 2, "sensitivity": 73}
    assert build_dreamview_command("music", values, profile) == frame("3360020134120249")
    assert parse_dreamview_status(frame("aa60020134120249"), profile) == (
        "music",
        {**values, "unknown": [0] * 11},
    )
    for setting, values in (
        ("saturation", {"saturation": 50}),
        ("video_settings", {"apply_area": 0, "content_mode": 0}),
    ):
        with pytest.raises(ValueError, match="not supported"):
            build_dreamview_command(setting, values, profile)


async def test_paired_music_saves_compiles_and_applies_independent_zone_edits():
    profile = get_profile("H607C")
    zones = default_music_zones(profile, "paired")
    assert zones is not None
    edited = (replace(zones[0], parameters={"background": 0x112233}), zones[1])
    item = LibraryItem.new("Paired", MusicProfile("H607C", "paired", 73, zones=edited))
    restored = LibraryItem.from_dict(item.to_dict())
    assert restored.content == item.content
    compiled = compile_music_profile(restored, "H607C", profile=profile)
    assert compiled.music_body is not None
    variant = music_variant(profile, int(H607cMusicWrite.MusicMode.paired))
    assert variant is not None
    root = parse_music_parameters(variant, compiled.music_body)
    assert native_music_zone_body(root.body.base) == zones[1].body
    assert native_music_zone_body(root.body.pole) != zones[0].body
    assert (
        root.body.pole.body.tail.background.red,
        root.body.pole.body.tail.background.green,
        root.body.pole.body.tail.background.blue,
    ) == (17, 34, 51)
    coordinator = SimpleNamespace(model="H607C", profile=profile, async_write_music_sequence=AsyncMock())
    await async_apply_compiled_profile(coordinator, compiled)
    writes = coordinator.async_write_music_sequence.await_args.args[0]
    assert tuple(packet for packet, _ in writes) == compiled.packets
    assert writes[-2][1]["_music_body"] == ("paired", compiled.music_body)
    assert compiled.packets[-1] == frame("3305138249")
    for packet in compiled.packets:
        adapter.require_profile_packet(packet, profile)


def test_paired_music_uses_the_base_budget_and_preserves_unknown_sibling_parameters():
    profile = get_profile("H607C")
    zones = default_music_zones(profile, "paired")
    assert zones is not None and zones[0].body is not None
    hopping = music_variant(profile, int(H607cMusicWrite.MusicMode.hopping))
    assert hopping is not None
    source = parse_music_parameters(hopping, zones[0].body)
    source.body.tail.background_brightness = 70
    original = native_music_zone_body(SimpleNamespace(mode=source.mode, body=source.body)) + b"\xaa\xbb"
    pole = replace(zones[0], body=original)
    base = MusicZone("base", "hopping", palette=((1, 2, 3),))
    body = build_zoned_music_body(profile, "paired", (pole, base))
    variant = music_variant(profile, int(H607cMusicWrite.MusicMode.paired))
    assert variant is not None
    root = parse_music_parameters(variant, body)
    assert native_music_zone_body(root.body.pole) == original
    assert root.body.pole.body.tail.background_brightness == 70
    assert root.body.base.body.tail.piece_count_min == 4
    assert root.body.base.body.tail.piece_count_max == 12
    assert root.body.base.body.num_palette == 1


@pytest.mark.parametrize("problem", ["nested", "identity", "palette", "rate", "length"])
def test_paired_music_rejects_unqualified_zone_requests_before_compilation(problem):
    profile = get_profile("H607C")
    zones = default_music_zones(profile, "paired")
    assert zones is not None
    invalid = {
        "nested": replace(zones[1], mode="paired", body=None),
        "identity": replace(zones[1], id="pole"),
        "palette": replace(zones[1], mode="shiny", body=None, palette=((1, 2, 3),)),
        "rate": replace(zones[1], mode="hopping", body=None, parameters={"relative_brightness": 51}),
        "length": replace(zones[1], body=zones[1].body + b"\xff" * 255),
    }[problem]
    with pytest.raises(ValueError):
        build_zoned_music_body(profile, "paired", (zones[0], invalid))


def test_native_paint_rejects_duplicate_positions_inside_one_group():
    with pytest.raises(ValueError, match="duplicated"):
        build_h607c_diy_painted(
            H607cPaintBody.Direction.upward.name,
            50,
            100,
            (0, 0, 0),
            [DiyPaintGroup((1, 2, 3), (1, 1))],
            segment_count=144,
        )


async def test_music_dreamview_service_admits_only_the_exact_member_form_before_preview(hass):
    coordinator = SimpleNamespace(
        profile=get_profile("H607C"),
        async_validate_dreamview_members=AsyncMock(),
        async_replace_dreamview_group=AsyncMock(),
    )
    entity = SimpleNamespace(coordinator=coordinator, _async_supersede_preview=AsyncMock())
    value = {"cmd_ver": 7, "mark": 3, "area_num": 13, "address": "11:22:33:44:55:66"}
    for invalid in (
        {**value, "zones": [1]},
        {**value, "area_num": 0},
        {key: item for key, item in value.items() if key != "mark"},
        {"cmd_ver": 7, "is_rgbic": True, "zones": [1], "name": "camera"},
    ):
        with pytest.raises(ServiceValidationError):
            await _async_dreamview_service(
                entity,
                ServiceCall(hass, DOMAIN, "replace_dreamview_group", {"members": [invalid]}),
                name="replace_dreamview_group",
            )
    entity._async_supersede_preview.assert_not_awaited()
    coordinator.async_replace_dreamview_group.assert_not_awaited()
    await _async_dreamview_service(
        entity,
        ServiceCall(hass, DOMAIN, "replace_dreamview_group", {"members": [value]}),
        name="replace_dreamview_group",
    )
    member = coordinator.async_replace_dreamview_group.await_args.args[0][0]
    assert member.as_dict() == value
    assert member.area_num == 13 and member.zones == ()
    coordinator.async_validate_dreamview_members.assert_awaited_once()
    entity._async_supersede_preview.assert_awaited_once()


@pytest.mark.parametrize("problem", ["pole", "base", "companion", "white-on", "white-off"])
async def test_native_preview_rejects_incomplete_recovery_state_before_writes(problem):
    state = PriorControlState(
        mode="custom",
        is_on=True,
        brightness_pct=50,
        rgb_color=(1, 2, 3),
        pole_enabled=True,
        base_enabled=False,
        diy_code=1234,
        diy_companion=5678,
    )
    if problem in {"pole", "base"}:
        state = replace(state, **{f"{problem}_enabled": None})
    elif problem == "companion":
        state = replace(state, diy_companion=None)
    else:
        state = replace(state, mode="colour", is_on=problem == "white-on", static_rgb_known=False)
    coordinator = SimpleNamespace(
        profile=get_profile("H607C"),
        capture_effect_control_state=lambda: state,
        _async_write_packet=AsyncMock(),
    )
    with pytest.raises(RuntimeError, match="restor"):
        await async_prepare_effect_control_state(coordinator, require_restorable_static=True)
    coordinator._async_write_packet.assert_not_awaited()


@pytest.mark.parametrize(
    ("control", "reply", "succeeds"), [("gradual", True, True), ("gradual", False, False), ("pole_enabled", True, True)]
)
async def test_h607c_settings_verify_only_their_own_fresh_register(hass, monkeypatch, control, reply, succeeds):
    c = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H607C", configuration_url=None)
    c.pact_type, c.pact_code = 1, 1
    c._resolve_device_profile()
    c._notification_token = object()
    c._notify_started_monotonic = time.monotonic()
    device = MagicMock(is_connected=True, disconnect=AsyncMock())
    c._client = device
    monkeypatch.setattr(c, "_ensure_connected", AsyncMock(return_value=device))
    monkeypatch.setattr(c, "_renew_foreground_lease", lambda: None)
    monkeypatch.setattr(c, "async_prepare_h607c_control", AsyncMock(return_value=lambda: None))

    async def write(_uuid, packet, **_kwargs):
        if packet == adapter.build_boolean_control_query("gradual", "H607C", profile=c.profile):
            c._notify_callback(None, bytearray(frame(f"aaa3{int(reply):02x}")))
        elif packet == adapter.build_boolean_control_query("pole_enabled", "H607C", profile=c.profile):
            c._notify_callback(None, bytearray(frame("aa07082507")))

    device.write_gatt_char = AsyncMock(side_effect=write)
    if succeeds:
        await c.async_set_boolean_control(control, True)
        assert c.boolean_control_state[control] is True
    else:
        with pytest.raises(ValueError, match="confirm"):
            await c.async_set_boolean_control(control, True)
        assert c.boolean_control_state[control] is False


async def test_h607c_gradual_ack_does_not_confirm_a_missing_register_reply(hass, monkeypatch, virtual_clock):
    c = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H607C", configuration_url=None)
    c.pact_type, c.pact_code = 1, 1
    c._resolve_device_profile()
    c._notification_token = object()
    c._notify_started_monotonic = time.monotonic()
    device = MagicMock(is_connected=True, disconnect=AsyncMock())
    c._client = device
    monkeypatch.setattr(c, "_ensure_connected", AsyncMock(return_value=device))
    monkeypatch.setattr(c, "_renew_foreground_lease", lambda: None)
    monkeypatch.setattr(c, "async_prepare_h607c_control", AsyncMock(return_value=lambda: None))

    async def write(_uuid, packet, **_kwargs):
        if packet == adapter.build_boolean_control("gradual", True, "H607C", profile=c.profile):
            c._notify_callback(None, bytearray(frame("33a300")))

    async def disconnect(_client):
        device.is_connected = False
        c._clear_client_state(device)

    device.write_gatt_char = AsyncMock(side_effect=write)
    monkeypatch.setattr(c, "_disconnect_if_current_locked", disconnect)
    with pytest.raises(ValueError, match="readback"):
        await c.async_set_boolean_control("gradual", True)
    assert c._client is None
    assert "gradual" not in c.boolean_control_state
    assert device.write_gatt_char.await_count == 2


async def test_h607c_saved_effect_guard_prevents_kelvin_retry_on_new_connection(hass, monkeypatch):
    c = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H607C", configuration_url=None)
    c.pact_type, c.pact_code = 1, 1
    c._resolve_device_profile()
    c.is_on = True
    first = MagicMock(is_connected=True, disconnect=AsyncMock(), write_gatt_char=AsyncMock(side_effect=BleakError()))
    second = MagicMock(is_connected=True, disconnect=AsyncMock(), write_gatt_char=AsyncMock())
    c._client = first
    c._notification_token = object()

    async def ensure_connected():
        if c._client is None:
            c._client = second
            c._notification_token = object()
        return c._client

    def saved_effect_guard():
        if c._client is not first:
            raise HomeAssistantError("saved effect context changed")

    monkeypatch.setattr(c, "_ensure_connected", ensure_connected)
    monkeypatch.setattr(c, "_renew_foreground_lease", lambda: None)
    light = GoveeBLELight(c)
    light.hass = hass
    light.entity_id = "light.h607c"
    with pytest.raises(HomeAssistantError, match="context changed"):
        await light._async_turn_on(color_temp_kelvin=3200, video_write_guard=saved_effect_guard)
    first.write_gatt_char.assert_awaited_once()
    second.write_gatt_char.assert_not_awaited()


def test_native_paint_keeps_exact_model_identity_through_library_and_compilation():
    template = next(value for value in MODEL_EFFECT_CATALOGUES["H607C"].templates if value.id == "template:paint")
    item = EffectStudioApplication.new_authored_item(name="Paint", content=effect_content_to_dict(template.content))
    restored = LibraryItem.from_dict(item.to_dict())
    assert item_summary(restored)["model"] == "H607C"
    assert restored.content.model == "H607C"
    compiled = compile_application(restored, "H607C")
    assert compiled.diy_code == 900
    with pytest.raises(ValueError, match="identity"):
        compile_application(
            restored, "H6099", diy_code=900, profile=replace(get_profile("H6099"), physical_ic_count=144)
        )


def test_native_diy_selector_and_companion_cannot_be_observed_from_different_replies(hass):

    c = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H607C", configuration_url="test")
    c.pact_type, c.pact_code = 1, 1
    c._resolve_device_profile()
    c._notify_started_monotonic = time.monotonic()
    c._notify_callback(None, bytearray(frame("aa050a34120a00")))
    assert (c.diy_code, c.diy_companion) == (0x1234, 10)
    assert c.capture_effect_control_state().diy_companion == 10
    packet = adapter.build_diy_activation(0x4321, "H607C", companion=0, profile=c.profile)
    c._arm_expected(packet)
    c.diy_code, c.diy_companion = 0x4321, 0
    c._notify_callback(None, bytearray(frame("aa050a21431400")))
    assert c.capture_effect_control_state().diy_companion is None
    c._expected_state = {key: (value, 0) for key, (value, _) in c._expected_state.items()}
    c._notify_callback(None, bytearray(frame("aa050a21431400")))
    state = c.capture_effect_control_state()
    assert (state.diy_code, state.diy_companion) == (0x4321, 20)
