"""Positive Pact 1 evidence narrows H6199; hardware versions never choose Pact."""

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.light import ColorMode
from homeassistant.config_entries import ConfigEntryState

from custom_components.ha_govee_led_ble.const import (
    DOMAIN,
    H6199_PACT1_PROFILE,
    MODEL_PROFILES,
    device_profile,
)
from custom_components.ha_govee_led_ble.control_arbiter import ControlIntent
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_expectations import expectations_from_packet
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode, parse_color_mode
from custom_components.ha_govee_led_ble.effect_catalogue import MODEL_EFFECT_CATALOGUES, resolve_catalogue_template
from custom_components.ha_govee_led_ble.effect_compiler import compatibility, compile_application, compile_video_profile
from custom_components.ha_govee_led_ble.effect_contracts import device_effect_capabilities
from custom_components.ha_govee_led_ble.effect_deployments import PriorControlState
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem, MusicProfile, PaletteDiyEffect, VideoProfile
from custom_components.ha_govee_led_ble.effect_storage import LibrarySnapshot
from custom_components.ha_govee_led_ble.effect_websocket import ws_scene_catalogue_list
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_brightness,
    build_brightness_query,
    build_colour_mode_query,
    build_firmware_query,
    build_hardware_query,
    build_power,
    build_power_query,
    build_segment_query,
    build_subordinate_query,
    build_video_mode,
    build_white_balance,
    parse_status_result,
    require_profile_packet,
    table_kelvin_rgb,
)
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.light_commands import (
    build_color_rgb,
    build_segment_brightness,
    build_segment_color,
)
from custom_components.ha_govee_led_ble.native_scenes import build_native_scene_packets
from custom_components.ha_govee_led_ble.protocol_commands import build_colour_temperature
from custom_components.ha_govee_led_ble.protocol_h6199 import build_h6199_control
from custom_components.ha_govee_led_ble.scenes import MODEL_SCENES
from custom_components.ha_govee_led_ble.transport import WRITE_UUID
from tests.coordinator_test_support import frame
from tests.test_h6199_capabilities import lifecycle as pact_lifecycle  # noqa: F401


def advertise(c, pact):
    c._note_advertisement(SimpleNamespace(manufacturer_data={34818: bytes((0xEC, 0, pact, 1, 0))}))


def test_passive_replay_cannot_replace_a_newer_h6199_pact(hass):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url=None)
    now = time.monotonic()
    coordinator._note_advertisement(
        SimpleNamespace(
            source="connectable",
            time=now,
            manufacturer_data={34818: bytes((0xEC, 0, 1, 1, 0))},
        )
    )
    assert (coordinator.pact_type, coordinator.pact_code) == (1, 1)

    coordinator._note_advertisement(
        SimpleNamespace(
            source="passive",
            time=now - 1,
            manufacturer_data={34818: bytes((0xEC, 0, 2, 1, 0))},
        )
    )

    assert (coordinator.pact_type, coordinator.pact_code) == (1, 1)
    assert coordinator.profile is H6199_PACT1_PROFILE
    coordinator._prune_pact_advertisements()
    assert (coordinator.pact_type, coordinator.pact_code) == (1, 1)
    assert coordinator.profile is H6199_PACT1_PROFILE
    coordinator._client = MagicMock(is_connected=True)
    coordinator._notification_token = object()
    coordinator._notify_started_monotonic = now - 2
    coordinator._resolve_pact_identity()
    assert (coordinator.pact_type, coordinator.pact_code) == (1, 1)
    assert coordinator.profile is H6199_PACT1_PROFILE


@pytest.mark.parametrize("model", ["H6199", "H6099", "H617A"])
def test_only_exact_model_and_positive_pact_select_restriction(model):
    for pact in ((None, None), (2, 1)):
        profile = device_profile(model, *pact)
        assert profile.command_operations == MODEL_PROFILES[model].command_operations
        assert profile.supports_video_mode == MODEL_PROFILES[model].supports_video_mode
    assert device_profile(model, 1, 1) == (
        H6199_PACT1_PROFILE if model == "H6199" else device_profile(model, None, None)
    )


@pytest.mark.parametrize(
    "builder",
    [
        lambda: build_power(True, "H6199"),
        lambda: build_power(False, "H6199"),
        lambda: build_power_query("H6199"),
        lambda: build_firmware_query("H6199"),
        lambda: build_hardware_query("H6199"),
    ],
)
def test_generated_guard_permits_power_and_main_identity(builder):
    packet = builder()
    require_profile_packet(packet, H6199_PACT1_PROFILE)
    transform = H6199_PACT1_PROFILE.outbound_transform
    assert transform is not None and transform(packet) == packet


@pytest.mark.parametrize(("percent", "register"), [(1, 20), (50, 136), (100, 254)])
def test_brightness_reencodes_the_register_without_changing_logical_expectations(percent, register):
    profile = H6199_PACT1_PROFILE
    packet = build_brightness(percent, "H6199", profile=profile)
    transform = profile.outbound_transform
    assert transform is not None
    assert transform(packet) == frame(f"3304{register:02x}")
    assert expectations_from_packet(packet, "H6199", profile=profile) == {"brightness_pct": percent}


def test_rgb_reuses_the_shared_logical_command_and_expectations():
    profile = H6199_PACT1_PROFILE
    packet = build_color_rgb(32, 96, 160, "H6199", profile=profile)
    assert packet == build_color_rgb(32, 96, 160, "H6199")
    require_profile_packet(packet, profile)
    transform = profile.outbound_transform
    assert transform is not None
    assert transform(packet) == bytes.fromhex("33050b2060a00000ff7f0000000000000000005d")
    assert expectations_from_packet(packet, "H6199", profile=profile) == {
        "color_mode": (ParsedMode.COLOUR, None),
        "rgb_color": (32, 96, 160),
    }


@pytest.mark.parametrize(
    "packet",
    [
        build_colour_mode_query("H6199"),
        build_colour_temperature(4000, 1, "H6199"),
        build_segment_brightness([1], 50, "H6199"),
        frame("330515ff"),
        build_brightness(0, "H6199"),
        frame("330465"),
        build_brightness(50, "H6199")[:-1] + b"\x00",
        build_h6199_control("gradient", 1),
        build_white_balance(21, 5, "H6199"),
        build_segment_query(1, "H6199"),
        build_subordinate_query(0x20, "H6199"),
        frame("330504d400"),
        frame("33050401000200"),
        frame("330513036400000000"),
        b"invalid upload",
    ],
)
async def test_physical_boundary_rejects_before_optimism(hass, monkeypatch, packet):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url=None)
    advertise(c, 1)
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    c._client = client
    monkeypatch.setattr(c, "_ensure_connected", AsyncMock(return_value=client))
    before = c.capture_effect_control_state()
    with pytest.raises(ValueError):
        await c.async_write_effect_sequence((packet,), intent=ControlIntent.USER, state_values={"brightness_pct": 254})
    assert c.capture_effect_control_state() == before
    assert c.control_write_attempts == 0 and not c._expected_state
    client.write_gatt_char.assert_not_awaited()


async def test_known_pact1_real_setup_and_basic_controls(
    pact_lifecycle,  # noqa: F811
    monkeypatch,
):
    c, replies, clients, packets = pact_lifecycle
    advertise(c, 1)
    replies[build_hardware_query(c.model)] = frame("aa0703" + b"1.00.01".hex())
    replies[build_firmware_query(c.model)] = frame("aa06" + b"1.07.02".hex())
    replies[build_brightness_query(c.model)] = frame("aa0488")
    replies[frame("aa0501")] = frame("aa050b00")
    for group in range(1, 5):
        replies[frame(f"aaa2{group:02x}")] = frame(f"aaa2{group:02x}" + "2060a0" * 4)
    await c._async_update_data()
    assert c.available and c.is_on
    assert c.profile.supports_custom_effects and c.profile.diy_upload_transport == "a1_02"
    assert set(packets) == {
        build_power_query(c.model),
        build_hardware_query(c.model),
        build_firmware_query(c.model),
        build_brightness_query(c.model),
        frame("aa0501"),
        *(frame(f"aaa2{group:02x}") for group in range(1, 5)),
    }
    assert c.hw_version == "1.00.01" and c.fw_version == "1.07.02"
    assert c.brightness_pct == 50 and c.color_mode is ParsedMode.COLOUR
    assert c.segment_colors == [(32, 96, 160)] * 15 and not c.segment_brightness_readable
    assert c.color_temp_kelvin is None
    c.effect_families = frozenset({"scenes", "music"})
    light = GoveeBLELight(c)
    assert light.supported_color_modes == {ColorMode.RGB, ColorMode.COLOR_TEMP}
    before = c.capture_effect_control_state()
    for reply in ("aaa500", "aaa90006011003001505", "aaae0104141e2832"):
        c._notify_callback(None, bytearray(frame(reply)))
    assert c.capture_effect_control_state() == before
    assert PriorControlState.from_dict(before.to_dict()) == before
    monkeypatch.setattr(light, "_notify_state_changed", MagicMock())
    packets.clear()
    await light._async_turn_on(brightness=128, rgb_color=(32, 96, 160))
    assert [packet for packet in packets if packet[0] == 0x33] == [
        frame("330488"),
        bytes.fromhex("33050b2060a00000ff7f0000000000000000005d"),
    ]
    assert frame("aa0501") in packets
    assert all(frame(f"aaa2{group:02x}") in packets for group in range(1, 5))
    assert c.brightness_pct == 50 and c.rgb_color == (32, 96, 160)
    assert c.rgb_color_source == "segment" and c.color_mode is ParsedMode.COLOUR
    assert c.segment_state_source == "observed"
    assert c._expected_state["brightness_pct"][0] == 50
    assert c._expected_state["rgb_color"][0] == (32, 96, 160)
    await light._async_handle_turn_on(effect="sunset")
    assert packets[-1] == frame("3305040100")
    c.music_calm = True
    c.music_color = (32, 96, 160)
    await light._async_handle_turn_on(effect="rhythm")
    music = frame("33050c056301012060a0")
    assert packets[-1] == music
    c._notify_callback(None, bytearray(frame("aa050c056301012060a0")))
    assert c.music_mode == "rhythm" and c._field_revisions["music_sensitivity"] > 0
    assert c.music_calm and c.music_color == (32, 96, 160)
    await light._async_handle_turn_on(effect="off")
    assert frame("33050b2060a00000ff7f") in packets[packets.index(music) + 1 :]
    assert c.color_mode is ParsedMode.COLOUR
    await c.send_command(build_segment_color([1, 15], 1, 2, 3, c.model, profile=c.profile))
    assert packets[-1] == frame("33050b01020300000140")
    rendered = table_kelvin_rgb(4000)
    for group in range(1, 5):
        replies[frame(f"aaa2{group:02x}")] = frame(f"aaa2{group:02x}" + bytes(rendered).hex() * 4)
    await light._async_turn_on(color_temp_kelvin=4000)
    assert frame("33050bffd5a10fa0ff7f") in packets
    assert c.color_temp_kelvin == 4000 and c.color_temp_kelvin_source == "retained"
    assert c.segment_state_source == "observed"
    await c.send_command(build_power(False, c.model))
    assert packets[-1] == build_power(False, c.model)


async def test_late_pact_changes_capabilities_without_destroying_library(hass):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url=None)
    c.hw_version, c.fw_version = "1.00.01", "1.07.02"
    assert c.profile == device_profile(c.model, None, None)
    light = GoveeBLELight(c)
    items = tuple(LibraryItem.new(t.label, t.content) for t in MODEL_EFFECT_CATALOGUES[c.model].templates)
    light._library_snapshot = LibrarySnapshot(items)
    before = [item.to_dict() for item in items]
    c.brightness_pct = 254
    advertise(c, 1)
    assert c.brightness_pct == 100 and light.brightness == 255 and light.color_mode is ColorMode.RGB
    assert c.profile.supports_custom_effects
    assert c.profile.diy_upload_transport == "a1_02"
    assert c.profile.scene_type_selectors == ((1, 199), (2, 401))
    assert any(compatibility(item, c.model, profile=c.profile).state == "compatible" for item in items)
    catalogue = MODEL_EFFECT_CATALOGUES[c.model].to_dict(profile=c.profile)
    assert catalogue["templates"] and catalogue["music_modes"]
    for template in MODEL_EFFECT_CATALOGUES[c.model].templates:
        if isinstance(template.content, MusicProfile):
            resolved = resolve_catalogue_template(c.model, template.id, profile=c.profile)
            compile_application(LibraryItem.new(resolved.label, resolved.content), c.model, profile=c.profile)
    capabilities = device_effect_capabilities("entry", c.model, "Test", 0, profile=c.profile).to_dict()
    assert "supported" in capabilities["custom_effects"].values()
    c._note_advertisement(SimpleNamespace(manufacturer_data={}))
    assert c.profile.supports_custom_effects
    advertise(c, 2)
    assert c.profile == device_profile(c.model, 2, 1, firmware=c.fw_version, hardware=c.hw_version)
    assert ColorMode.RGB in light.supported_color_modes and light.color_mode is ColorMode.RGB
    assert len(c.segment_colors) == 15 and c.segment_state_source == "initial"
    assert light.effect_list
    assert [item.to_dict() for item in items] == before


async def test_scene_catalogue_limits_pact1_to_built_in_scenes(hass, monkeypatch):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url=None)
    advertise(c, 1)
    entry = SimpleNamespace(runtime_data=c, state=ConfigEntryState.LOADED, domain=DOMAIN, entry_id="entry")
    monkeypatch.setattr(hass.config_entries, "async_get_entry", lambda _: entry)
    connection = MagicMock()
    ws_scene_catalogue_list(hass, connection, {"id": 2, "config_entry_id": "entry"})
    scenes = connection.send_result.call_args.args[1]["catalogue"]["scenes"]
    names = {scene["name"] for scene in scenes}
    assert len(names) == 12 and {"Sunrise", "Sunset"} <= names and "Forest" not in names
    assert all(scene["selector_only"] for scene in scenes)
    assert build_native_scene_packets(c.model, MODEL_SCENES[c.model]["sunset"], profile=c.profile) == [
        frame("3305040100")
    ]


@pytest.mark.parametrize("change_at", ["connect", "guard"])
async def test_late_pact_identification_blocks_unsupported_prepared_write(hass, monkeypatch, change_at):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url=None)
    packet = build_h6199_control("gradient", 1)
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    c._client = client

    async def connect():
        if change_at == "connect":
            advertise(c, 1)
        return client

    def guard():
        if change_at == "guard":
            advertise(c, 1)

    monkeypatch.setattr(c, "_ensure_connected", connect)
    with pytest.raises(ValueError, match="profile changed|does not support this operation"):
        await c.async_write_effect_sequence(
            (packet,), intent=ControlIntent.USER, write_guard=guard, state_values={"brightness_pct": 254}
        )
    assert c.brightness_pct == 100 and c.control_write_attempts == 0
    client.write_gatt_char.assert_not_awaited()


async def test_public_pact1_video_admission_transmission_observation_and_restoration(
    pact_lifecycle,  # noqa: F811
    monkeypatch,
):
    c, _replies, _clients, packets = pact_lifecycle
    advertise(c, 1)
    c.is_on = True
    c.effect_families = frozenset({"video"})
    c.video_full_screen = True
    c.video_saturation = 50
    c.video_sound_effects = False
    c.video_sound_effects_softness = 50
    monkeypatch.setattr(
        c,
        "async_prepare_static_baseline",
        AsyncMock(
            return_value=PriorControlState(
                mode="colour",
                is_on=True,
                brightness_pct=50,
                rgb_color=(32, 96, 160),
                static_rgb_known=True,
                segment_colors=((32, 96, 160),) * 15,
                segment_brightness=(50,) * 15,
            )
        ),
    )
    light = GoveeBLELight(c)
    monkeypatch.setattr(light, "_notify_state_changed", MagicMock())
    expected = build_video_mode("movie", True, 50, False, 50, c.model, profile=c.profile)
    assert expected == bytes.fromhex("3305000100320032000000000000000000000037")

    assert "Movie" in light.effect_list
    content = VideoProfile(
        "H6199",
        "movie",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )
    compiled = compile_video_profile(LibraryItem.new("Resident movie", content), c.model, profile=c.profile)
    assert compiled.mode == "movie"
    require_profile_packet(expected, c.profile)
    assert c.profile.outbound_transform is not None and c.profile.outbound_transform(expected) == expected
    public_expected = bytes.fromhex("3305000100640064000000000000000000000037")

    await light._async_handle_turn_on(effect="movie")

    assert [packet.hex() for packet in packets if packet[:1] == b"\x33"] == [public_expected.hex()]
    status = parse_status_result(frame("aa0500010032000032"), c.model, profile=c.profile)
    assert status.parsed is not None
    parsed = parse_color_mode(status.parsed, c.model, profile=c.profile)
    assert parsed.mode is ParsedMode.VIDEO and parsed.video_mode == "movie"
    c._notify_callback(None, bytearray(frame("aa0500010032000032")))
    assert c.color_mode is ParsedMode.VIDEO and c.video_mode == "movie"

    c.send_command = AsyncMock()
    c.refresh_state = AsyncMock(return_value=True)
    await c.async_restore_effect_control_state(
        PriorControlState(
            mode="scene",
            is_on=True,
            brightness_pct=50,
            rgb_color=(32, 96, 160),
            effect="sunset",
        ),
        overwritten_diy_code=None,
    )
    assert [item.args[0] for item in c.send_command.await_args_list] == [
        build_power(True, c.model),
        build_brightness(50, c.model),
        frame("3305040100"),
    ]


@pytest.mark.parametrize("verdict", ["accepted", "missing", "rejected", "stale", "wrong_subtype"])
async def test_pact1_a1_diy_requires_current_positive_ack_before_activation_and_restores(hass, monkeypatch, verdict):
    from custom_components.ha_govee_led_ble import coordinator as coordinator_module

    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url=None)
    c._note_advertisement(SimpleNamespace(manufacturer_data={34818: bytes((0xEC, 0, 1, 1, 0))}))
    c._observe_identity_field("fw_version", "1.06.00")
    c._observe_identity_field("hw_version", "1.00.01")
    profile = c.profile
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    c._client = client
    c._notification_token = object()
    monkeypatch.setattr(c, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(coordinator_module, "UPLOAD_ACK_TIMEOUT", 0.02)
    monkeypatch.setattr(coordinator_module, "EFFECT_SEQUENCE_ATTEMPTS", 1)
    item = LibraryItem.new(
        "Pact 1 DIY",
        PaletteDiyEffect("H6199", 0, 0, 20, ((30, 0, 0), (0, 30, 0))),
    )
    compiled = compile_application(item, c.model, diy_code=73, profile=profile)
    assert compiled.upload_packets[0][:2] == b"\xa1\x02"

    async def write(_uuid, packet, **_kwargs):
        if packet == compiled.upload_packets[0] and verdict == "stale":
            c._notify_callback(None, bytearray(frame("a10200")))
        if packet == compiled.upload_packets[-1]:
            response = {
                "accepted": "a10200",
                "rejected": "a10201",
                "wrong_subtype": "a10100",
            }.get(verdict)
            if response is not None:
                c._notify_callback(None, bytearray(frame(response)))

    client.write_gatt_char.side_effect = write
    operation = c.async_write_effect_sequence(
        compiled.upload_packets,
        intent=ControlIntent.APPLY,
        require_upload_ack=True,
        upload_ack_index=len(compiled.upload_packets) - 1,
        final_packet=compiled.activation_packet,
    )
    if verdict == "accepted":
        await operation
        assert [call.args[1] for call in client.write_gatt_char.await_args_list][-1] == compiled.activation_packet
    else:
        with pytest.raises((TimeoutError, RuntimeError)):
            await operation
        assert compiled.activation_packet not in [call.args[1] for call in client.write_gatt_char.await_args_list]
        c._disconnect_locked = AsyncMock()
        c.send_command = AsyncMock()
        c.refresh_state = AsyncMock(return_value=True)
        await c.async_restore_effect_control_state(
            PriorControlState(
                mode="scene",
                is_on=True,
                brightness_pct=50,
                rgb_color=(32, 96, 160),
                effect="sunset",
            ),
            overwritten_diy_code=None,
        )
        assert [call.args[0] for call in c.send_command.await_args_list] == [
            build_power(True, c.model),
            build_brightness(50, c.model),
            frame("3305040100"),
        ]


async def test_prepared_rgb_reencodes_after_pact_identification_during_connect(hass, monkeypatch):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url=None)
    packet = build_color_rgb(32, 96, 160, c.model)
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    c._client = client

    async def connect():
        advertise(c, 1)
        return client

    monkeypatch.setattr(c, "_ensure_connected", connect)
    await c.send_command(packet)
    client.write_gatt_char.assert_awaited_once_with(
        WRITE_UUID, bytes.fromhex("33050b2060a00000ff7f0000000000000000005d"), response=False
    )
    assert c.rgb_color == (32, 96, 160) and c.rgb_color_source == "optimistic"


@pytest.mark.parametrize("packet", [build_brightness(50, "H6199"), build_color_rgb(32, 96, 160, "H6199")])
async def test_pact_change_after_encoding_rejects_before_optimism(hass, packet):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url=None)
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    c._client = client
    with pytest.raises(ValueError, match="profile changed"):
        await c._async_write_packet(client, packet, arm_expected=True, before_write=lambda: advertise(c, 1))
    client.write_gatt_char.assert_not_awaited()
    assert c.control_write_attempts == 0 and not c._expected_state
    assert c.brightness_pct == 100 and c.rgb_color_source == "initial"
