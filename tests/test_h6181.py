from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.ha_govee_led_ble.const import device_profile
from custom_components.ha_govee_led_ble.control_arbiter import ControlIntent
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_base import async_prepare_effect_profile
from custom_components.ha_govee_led_ble.coordinator_refresh import RefreshRequest
from custom_components.ha_govee_led_ble.coordinator_status import decode_status_frame, parse_color_mode
from custom_components.ha_govee_led_ble.effect_compiler import compile_effect, validate_compiled_geometry
from custom_components.ha_govee_led_ble.effect_domain import (
    BuiltinScene,
    CatalogueRef,
    EffectPair,
    LibraryItem,
    MultiEffect,
    MusicProfile,
    SingleEffect,
)
from custom_components.ha_govee_led_ble.effect_protocol_decoder import decode_effect_frames
from custom_components.ha_govee_led_ble.effect_runtime import async_prepare_application
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_brightness,
    build_colour_mode_query,
    build_firmware_query,
    build_hardware_query,
    build_power,
    require_profile_packet,
    table_kelvin_rgb,
)
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.light_commands import build_color_rgb, build_color_temp
from custom_components.ha_govee_led_ble.music_commands import resolve_music_profile
from custom_components.ha_govee_led_ble.music_semantics import music_variant
from custom_components.ha_govee_led_ble.native_scenes import build_native_scene_packets
from custom_components.ha_govee_led_ble.palette_scene_decoder import decode_catalogue_palette_scene
from custom_components.ha_govee_led_ble.protocol_core import H6181DiyBody
from custom_components.ha_govee_led_ble.protocol_music_params import parse_music_parameters
from custom_components.ha_govee_led_ble.scenes import MODEL_SCENES, SCENE_ENTRIES, scene_supported
from custom_components.ha_govee_led_ble.transport import fragment_a3, reassemble_a1_02, xor_checksum
from tests.test_h6199_capabilities import lifecycle  # noqa: F401


def frame(payload: bytes) -> bytes:
    body = payload.ljust(19, b"\0")
    return body + bytes([xor_checksum(body)])


def test_ordinary_colour_and_raw_brightness_match_their_distinct_contracts():
    profile = device_profile("H6181", None, None, firmware="1.03.00", hardware="1.00.03")
    assert build_color_rgb(12, 34, 56, "H6181") == frame(bytes.fromhex("33050d0c2238"))
    assert build_color_temp(2700, "H6181") == frame(bytes.fromhex("33050dffffff0a8c") + bytes(table_kelvin_rgb(2700)))
    assert profile.outbound_transform is not None
    for percent, raw in ((1, 20), (50, 136), (100, 254)):
        assert profile.outbound_transform(build_brightness(percent, "H6181")) == frame(bytes([0x33, 4, raw]))


@pytest.mark.parametrize(
    "pact,firmware,hardware",
    [
        ((None, None), None, None),
        ((None, None), "1.03.00", None),
        ((None, None), None, "1.00.03"),
        ((None, None), "1.03.01", "1.00.03"),
        ((None, None), "1.03.00", "1.00.04"),
        ((10, 1), "1.03.00", "1.00.03"),
        ((10, 2), "1.03.00", "1.00.03"),
        ((10, 3), "1.03.00", "1.00.03"),
    ],
)
def test_legacy_colour_does_not_change_other_revision_contexts(pact, firmware, hardware):
    profile = device_profile("H6181", *pact, firmware=firmware, hardware=hardware)
    for packet in (build_color_rgb(255, 0, 0, "H6181"), build_color_temp(4000, "H6181")):
        assert (profile.outbound_transform(packet) if profile.outbound_transform else packet) == packet


@pytest.fixture
async def legacy_colour(hass):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6181", configuration_url=None)
    client = MagicMock(is_connected=True, start_notify=AsyncMock(), write_gatt_char=AsyncMock())
    coordinator._client = client
    coordinator._reply_gate.timeout = 0
    coordinator._note_identity(fw_version="1.03.00", hw_version="1.00.03")
    await coordinator._start_notify()
    return coordinator, client


def confirm_legacy_identity(client):
    receive = client.start_notify.call_args.args[1]
    receive(None, bytearray(frame(b"\xaa\x06" + b"1.03.00")))
    receive(None, bytearray(frame(b"\xaa\x07\x03" + b"1.00.03")))


@pytest.mark.parametrize(
    "packet,wire,field,value,reply",
    [
        (
            build_color_rgb(255, 0, 0, "H6181"),
            "330502ff000000000000",
            "rgb_color",
            (255, 0, 0),
            "aa0502ff000000000000",
        ),
        (
            build_color_temp(4000, "H6181"),
            "330502ffffff01ffd5a1",
            "color_temp_kelvin",
            4000,
            "aa0502ffffff01ffd1a3",
        ),
    ],
)
async def test_legacy_colour_preserves_logical_expectations_and_strict_readback(
    legacy_colour, packet, wire, field, value, reply
):
    coordinator, client = legacy_colour
    confirm_legacy_identity(client)
    await coordinator._async_write_packet(client, packet, arm_expected=True)
    client.write_gatt_char.assert_awaited_once()
    assert client.write_gatt_char.call_args.args[1] == frame(bytes.fromhex(wire))
    assert coordinator._expected_state[field][0] == value
    receive = client.start_notify.call_args.args[1]
    receive(None, bytearray(frame(bytes.fromhex("aa050d000000"))))
    assert field not in coordinator._field_revisions
    receive(None, bytearray(frame(bytes.fromhex(reply))))
    assert getattr(coordinator, field) == value
    assert getattr(coordinator, f"{field}_source") == "observed"


@pytest.mark.parametrize("confirmed", [(), ("fw_version",), ("hw_version",), ("reconnect",)])
@pytest.mark.parametrize("arm_expected", [False, True])
async def test_legacy_colour_cannot_use_cached_or_partially_confirmed_identity(legacy_colour, confirmed, arm_expected):
    coordinator, client = legacy_colour
    if confirmed == ("reconnect",):
        confirm_legacy_identity(client)
        coordinator._clear_client_state(client)
        coordinator._client = client
        await coordinator._start_notify()
    else:
        for field in confirmed:
            coordinator._observe_identity_field(field, getattr(coordinator, field))
    with pytest.raises(ValueError, match="current-subscription device identity"):
        await coordinator._async_write_packet(client, build_color_rgb(255, 0, 0, "H6181"), arm_expected=arm_expected)
    client.write_gatt_char.assert_not_awaited()
    assert coordinator._expected_state == {}
    assert coordinator.control_write_attempts == 0


@pytest.mark.parametrize("change", ["identity", "profile", "subscription", "client"])
async def test_legacy_colour_rechecks_authorisation_after_the_write_guard(legacy_colour, change):
    coordinator, client = legacy_colour
    confirm_legacy_identity(client)

    def revoke():
        if change == "identity":
            coordinator._confirmed_identity_fields.discard("hw_version")
        elif change == "profile":
            coordinator._note_identity(fw_version="1.03.01")
        elif change == "subscription":
            coordinator._notification_token = object()
        else:
            coordinator._client = MagicMock(is_connected=True)

    with pytest.raises(ValueError, match="current-subscription device identity"):
        await coordinator._async_write_packet(client, build_color_rgb(255, 0, 0, "H6181"), before_write=revoke)
    client.write_gatt_char.assert_not_awaited()
    assert coordinator._expected_state == {}


async def test_legacy_colour_allows_untransformed_identity_queries_and_power(legacy_colour):
    coordinator, client = legacy_colour
    packets = (
        build_firmware_query("H6181"),
        build_hardware_query("H6181"),
        build_power(True, "H6181"),
    )
    for packet in packets:
        await coordinator._async_write_packet(client, packet)
    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == list(packets)


@pytest.mark.parametrize("lifecycle", ["H6139", "H6159", "H6182"], indirect=True)
@pytest.mark.parametrize("control", ["studio", "rgb", "kelvin", "music"])
@pytest.mark.parametrize("identity_returns", ["none", "hardware", "complete"])
async def test_whole_strip_controls_prepare_identity_after_basic_setup(
    lifecycle,  # noqa: F811
    monkeypatch,
    control,
    identity_returns,
):
    coordinator, replies, _clients, packets = lifecycle
    monkeypatch.setattr(
        "custom_components.ha_govee_led_ble.coordinator.bluetooth.async_last_service_info",
        lambda *_args, **_kwargs: None,
    )
    identity = {
        query: replies.pop(query)
        for query in (build_firmware_query(coordinator.model), build_hardware_query(coordinator.model))
    }
    await coordinator._async_update_data()
    assert coordinator.available
    assert coordinator.profile.supports_custom_effects is (coordinator.model == "H6139")
    if identity_returns == "complete":
        replies.update(identity)
    elif identity_returns == "hardware":
        query = build_hardware_query(coordinator.model)
        replies[query] = identity[query]
    if control == "kelvin":
        replies[build_colour_mode_query(coordinator.model)] = frame(bytes.fromhex("aa0502ffffff01ffae54"))
    packets.clear()
    light = GoveeBLELight(coordinator)
    monkeypatch.setattr(light, "_notify_state_changed", MagicMock())

    async def apply():
        if control == "studio":
            await async_prepare_effect_profile(
                coordinator, intent=ControlIntent.APPLY, content=SingleEffect(0, 0, 50, ((255, 0, 0),))
            )
        elif control == "music":
            await async_prepare_application(
                coordinator, LibraryItem.new("Onboard music", MusicProfile(coordinator.model, "dynamic", 42))
            )
        else:
            await light.async_turn_on(
                **({"rgb_color": (12, 34, 56)} if control == "rgb" else {"color_temp_kelvin": 2700})
            )

    if (
        coordinator.model == "H6159"
        and identity_returns != "complete"
        or coordinator.model == "H6182"
        and identity_returns == "none"
        or coordinator.model == "H6139"
        and control == "music"
        and identity_returns != "complete"
    ):
        with pytest.raises(HomeAssistantError):
            await apply()
        assert packets and all(packet[0] == 0xAA for packet in packets)
        return
    await apply()
    assert coordinator.profile.supports_custom_effects
    if coordinator.model != "H6139":
        assert coordinator.identity_fields_confirmed(coordinator.profile.profile_identity_fields)
    if identity_returns == "hardware":
        assert coordinator.fw_version is None
    if control in {"studio", "music"}:
        if coordinator.model == "H6139" and control == "studio":
            assert packets == []
        else:
            assert packets and all(packet[0] == 0xAA for packet in packets)
    else:
        payload = "3305020c2238" if control == "rgb" else "330502ffffff01ffae54"
        assert frame(bytes.fromhex(payload)) in packets


@pytest.mark.parametrize("lifecycle", ["H6139", "H6159", "H6182"], indirect=True)
@pytest.mark.parametrize("fresh_identity", [False, True])
async def test_whole_strip_power_survives_disconnect_without_optional_revision_identity(
    lifecycle,  # noqa: F811
    monkeypatch,
    fresh_identity,
):
    coordinator, replies, clients, packets = lifecycle
    await coordinator._async_update_data()
    assert coordinator.available
    light = GoveeBLELight(coordinator)
    monkeypatch.setattr(light, "_notify_state_changed", MagicMock())
    await light._async_turn_on(brightness=128, rgb_color=(12, 34, 56))
    assert frame(bytes.fromhex("330480" if coordinator.model in {"H6139", "H6159"} else "330488")) in packets
    assert frame(bytes.fromhex("3305020c2238")) in packets
    await light.async_turn_off()
    await coordinator.disconnect()
    assert not clients[-1].is_connected
    if not fresh_identity:
        del replies[build_firmware_query(coordinator.model)]
        del replies[build_hardware_query(coordinator.model)]
    packets.clear()
    await light._async_turn_on()
    assert frame(bytes.fromhex("330101")) in packets
    assert coordinator.is_on
    assert coordinator.identity_fields_confirmed(coordinator.profile.profile_identity_fields) is fresh_identity


@pytest.mark.parametrize("lifecycle", ["H6182"], indirect=True)
@pytest.mark.parametrize("hardware_returns", [False, True])
async def test_whole_strip_recovery_qualifies_hardware_without_optional_firmware(
    lifecycle,  # noqa: F811
    monkeypatch,
    hardware_returns,
):
    coordinator, replies, clients, packets = lifecycle
    del replies[build_firmware_query(coordinator.model)]
    monkeypatch.setattr(
        "custom_components.ha_govee_led_ble.coordinator.bluetooth.async_last_service_info",
        lambda *_args, **_kwargs: None,
    )
    await coordinator._async_update_data()
    original_rgb, original_brightness = coordinator.rgb_color, coordinator.brightness_pct
    assert coordinator.fw_version is None
    await coordinator.async_apply_native_scene("movie")
    assert coordinator._pre_mode_snapshot is not None
    receive = clients[-1].start_notify.call_args.args[1]
    receive(None, bytearray(frame(b"\xaa\x06" + b"1.02.16")))
    assert coordinator.fw_version == "1.02.16" and coordinator._pre_mode_snapshot is not None
    await coordinator._async_disconnect_on_timeout(coordinator._disconnect_generation)
    assert coordinator._client is None and coordinator._pre_mode_needs_qualification
    if not hardware_returns:
        del replies[build_hardware_query(coordinator.model)]
    packets.clear()
    light = GoveeBLELight(coordinator)
    monkeypatch.setattr(light, "_notify_state_changed", MagicMock())
    if not hardware_returns:
        with pytest.raises(HomeAssistantError):
            await light.async_turn_on(effect="off")
        assert packets and all(packet[0] == 0xAA for packet in packets)
        return
    await light.async_turn_on(effect="off")
    assert build_hardware_query(coordinator.model) in packets
    assert coordinator.identity_fields_confirmed(frozenset({"hw_version"}))
    assert not coordinator.identity_fields_confirmed(frozenset({"fw_version"}))
    assert coordinator.static_mode_confirmed()
    assert (coordinator.rgb_color, coordinator.brightness_pct) == (original_rgb, original_brightness)
    assert coordinator.rgb_color_source == "observed" and coordinator._pre_mode_snapshot is None


@pytest.mark.parametrize(
    ("lifecycle", "pact", "identity_state"),
    [
        (("H6139", 1), 1, "same"),
        (("H6139", 10), 10, "same"),
        (("H6139", 1), 1, "changed"),
        (("H6139", 1), 1, "missing"),
    ],
    indirect=["lifecycle"],
)
@pytest.mark.parametrize("kelvin", [False, True])
async def test_planned_static_recovery_requires_its_wire_authority_not_optional_identity(
    lifecycle,  # noqa: F811
    monkeypatch,
    pact,
    kelvin,
    identity_state,
):
    coordinator, replies, clients, packets = lifecycle
    await coordinator._async_update_data()
    await coordinator._ensure_connected()
    coordinator._observe_pact(pact, 1)
    if kelvin:
        replies[build_colour_mode_query(coordinator.model)] = frame(
            bytes.fromhex("aa050dffffff0a8cffae54" if pact == 10 else "aa0502ffffff01ffae54")
        )
    assert await coordinator.refresh_state(
        RefreshRequest(
            brightness=50,
            rgb_color=None if kelvin else (12, 34, 56),
            color_temp_kelvin=2700 if kelvin else None,
        )
    )
    rgb, temperature, brightness = coordinator.rgb_color, coordinator.color_temp_kelvin, coordinator.brightness_pct
    scene_key = next(
        key for key, scene in MODEL_SCENES[coordinator.model].items() if not scene.param and not scene.local_only
    )
    await coordinator.async_apply_native_scene(scene_key)
    assert coordinator._pre_mode_snapshot is not None
    await coordinator._async_disconnect_on_timeout(coordinator._disconnect_generation)
    assert coordinator._client is None and coordinator._pre_mode_needs_qualification
    del replies[build_firmware_query(coordinator.model)]
    del replies[build_hardware_query(coordinator.model)]
    await coordinator._ensure_connected()
    if identity_state != "missing":
        coordinator._observe_pact(10 if identity_state == "changed" else pact, 1)
    assert coordinator.identity_fields_confirmed(frozenset({"pact"})) is (identity_state != "missing")
    assert not coordinator.identity_fields_confirmed(frozenset({"fw_version", "hw_version"}))
    packets.clear()
    light = GoveeBLELight(coordinator)
    monkeypatch.setattr(light, "_notify_state_changed", MagicMock())
    if identity_state != "same":
        with pytest.raises(HomeAssistantError) as error:
            await light.async_turn_on(effect="off")
        assert error.value.translation_key == "recovery_not_ready"
        assert all(packet[0] == 0xAA for packet in packets)
        return
    await light.async_turn_on(effect="off")
    assert coordinator.static_mode_confirmed()
    assert coordinator.brightness_pct == brightness
    assert coordinator._pre_mode_snapshot is None
    if kelvin:
        assert coordinator.color_temp_kelvin == temperature and coordinator.color_temp_kelvin_source == "observed"
    else:
        assert coordinator.rgb_color == rgb and coordinator.rgb_color_source == "observed"
    assert not coordinator.identity_fields_confirmed(frozenset({"fw_version", "hw_version"}))
    assert clients[-1].is_connected


@pytest.mark.parametrize("lifecycle", [("H6139", 10)], indirect=True)
@pytest.mark.parametrize("content_kind", ["programme", "palette_music"])
@pytest.mark.parametrize("hardware_returns", [False, True])
async def test_effect_preparation_completes_when_the_requested_authority_is_ready(
    lifecycle,  # noqa: F811
    content_kind,
    hardware_returns,
):
    coordinator, replies, _clients, packets = lifecycle
    firmware_reply = replies.pop(build_firmware_query(coordinator.model))
    hardware_reply = replies.pop(build_hardware_query(coordinator.model))
    await coordinator._async_update_data()
    await coordinator._ensure_connected()
    coordinator._observe_pact(10, 1)
    assert coordinator.pact_type == 10
    replies[build_firmware_query(coordinator.model)] = firmware_reply
    if hardware_returns:
        replies[build_hardware_query(coordinator.model)] = hardware_reply
    content = (
        next(
            decoded
            for scene in SCENE_ENTRIES[coordinator.model]
            if (decoded := decode_catalogue_palette_scene(coordinator.model, scene)) is not None
        )
        if content_kind == "programme"
        else MusicProfile(coordinator.model, "bloom", 42, palette=((1, 2, 3),))
    )
    packets.clear()
    item = LibraryItem.new("Qualified effect", content)
    if content_kind == "palette_music" and not hardware_returns:
        with pytest.raises(HomeAssistantError) as error:
            await async_prepare_application(coordinator, item)
        assert error.value.translation_key == "identity_not_ready"
    else:
        await async_prepare_application(coordinator, item)
    assert coordinator.identity_fields_confirmed(frozenset({"fw_version"}))
    if content_kind == "palette_music":
        assert coordinator.identity_fields_confirmed(frozenset({"hw_version"})) is hardware_returns
    elif not hardware_returns:
        assert not coordinator.identity_fields_confirmed(frozenset({"hw_version"}))
    assert all(packet[0] == 0xAA for packet in packets)
    assert coordinator.profile.supports_rgb


@pytest.mark.parametrize(
    "model,pact,firmware,hardware,colour_mode,music_mode,modes,transport",
    [
        ("H6159", (None, None), "1.02.02", "1.00.01", 2, 3, ("dynamic",), "a1_02"),
        ("H6159", (None, None), "1.03.00", "1.00.01", 2, 14, ("dynamic", "soft"), "a1_02"),
        ("H6159", (1, 1), "1.06.99", "1.00.02", 2, 14, ("dynamic", "soft"), "a1_02"),
        ("H6159", (1, 1), "1.07.00", "1.00.02", 2, 14, ("dynamic", "soft", "bloom", "radiant"), "a1_02"),
        ("H6159", (None, None), "2.04.00", "2.01.01", 2, 14, ("dynamic", "soft", "bloom", "radiant"), "a3"),
        ("H6159", (2, 1), "2.03.99", "2.01.01", 13, 19, ("dynamic", "soft"), "a3"),
        ("H6159", (2, 1), "2.04.00", "2.01.01", 13, 19, ("dynamic", "soft", "bloom", "radiant"), "a3"),
        ("H6159", (2, 1), "2.04.00", "3.04.01", 13, 19, ("dynamic", "soft"), "a3"),
        ("H6159", (2, 1), "2.04.00", "3.05.01", 13, 19, ("dynamic", "soft", "bloom", "radiant"), "a3"),
        ("H6139", (None, None), "1.02.99", "1.00.01", 2, 3, ("dynamic",), "a1_02"),
        ("H6139", (1, 1), "1.03.00", "1.00.01", 2, 14, ("dynamic", "soft"), "a1_02"),
        ("H6139", (None, None), "1.06.99", "1.00.01", 2, 14, ("dynamic", "soft"), "a1_02"),
        ("H6139", (None, None), "1.07.00", "1.00.01", 2, 14, ("dynamic", "soft", "bloom", "radiant"), "a1_02"),
        ("H6139", (None, None), "1.07.02", "1.00.01", 2, 14, ("dynamic", "soft", "bloom", "radiant"), "a1_02"),
        ("H6139", (None, None), "1.07.02", None, 2, 14, ("dynamic", "soft", "bloom", "radiant"), "a1_02"),
        ("H6139", (1, 1), "1.07.02", "2.01.01", 2, 14, ("dynamic", "soft", "bloom", "radiant"), "a1_02"),
        ("H6139", (1, 1), "1.07.02", "3.04.01", 2, 14, ("dynamic", "soft", "bloom", "radiant"), "a1_02"),
        ("H6139", (None, None), None, "1.00.01", 2, None, (), "a1_02"),
        ("H6139", (10, 1), None, "2.01.01", 13, 19, ("dynamic", "soft"), "a3"),
        ("H6139", (10, 1), "2.04.00", None, 13, 19, ("dynamic", "soft"), "a3"),
        ("H6139", (2, 1), "1.07.02", "1.00.01", 2, 14, ("dynamic", "soft", "bloom", "radiant"), "a1_02"),
        ("H6139", (10, 1), "2.03.99", "2.01.01", 13, 19, ("dynamic", "soft"), "a3"),
        ("H6139", (10, 2), "2.04.00", "2.01.01", 13, 19, ("dynamic", "soft", "bloom", "radiant"), "a3"),
        ("H6139", (10, 2), "2.04.00", "3.04.01", 13, 19, ("dynamic", "soft"), "a3"),
        ("H6139", (10, 2), "2.04.00", "3.05.01", 13, 19, ("dynamic", "soft", "bloom", "radiant"), "a3"),
        ("H6139", (10, 3), "2.04.00", "2.01.01", 13, None, (), "a3"),
    ],
)
def test_whole_strip_revision_codecs_do_not_inherit_segment_commands(
    model, pact, firmware, hardware, colour_mode, music_mode, modes, transport
):
    profile = device_profile(model, *pact, firmware=firmware, hardware=hardware)
    assert profile.music_modes == modes and profile.diy_upload_transport == transport
    assert not profile.supports_segments
    transform = profile.outbound_transform
    assert transform is not None
    assert transform(build_color_rgb(12, 34, 56, model, profile=profile)) == frame(
        bytes([0x33, 5, colour_mode, 12, 34, 56])
    )
    temperature = bytes.fromhex("ffffff01ffae54" if colour_mode == 2 else "ffffff0a8cffae54")
    assert transform(build_color_temp(2700, model, profile=profile)) == frame(
        bytes([0x33, 5, colour_mode]) + temperature
    )
    for percent, raw in ((1, 6), (50, 128), (100, 254)):
        assert transform(build_brightness(percent, model, profile=profile)) == frame(
            bytes([0x33, 4, raw if colour_mode == 2 else percent])
        )
    if not modes:
        assert not profile.command_operation_supported("music")
        return
    _, _, packets = resolve_music_profile(model, "dynamic", 73, (12, 34, 56), None, {}, profile=profile)
    settings = bytes([1, 73]) if music_mode == 3 else bytes([0, 73, 1]) if music_mode == 14 else bytes([0, 73, 0, 1])
    assert transform(packets[-1]) == frame(bytes([0x33, 5, music_mode]) + settings + bytes([12, 34, 56]))
    decoded = decode_status_frame(frame(bytes([0xAA, 5, colour_mode]) + temperature), model, profile=profile)
    assert decoded is not None
    observed = parse_color_mode(decoded.generated, model, profile=profile)
    assert observed.color_temp_kelvin == 2700 and observed.rgb_color is None
    written = transform(packets[-1])
    decoded_music = decode_status_frame(frame(b"\xaa" + written[1:-1]), model, profile=profile)
    assert decoded_music is not None
    music = parse_color_mode(decoded_music.generated, model, profile=profile)
    assert music.music_mode == "dynamic" and music.music_sensitivity == 73 and music.music_color == (12, 34, 56)


@pytest.mark.parametrize(
    "pact,firmware,hardware,raw_brightness,modes,transport,scene_codes",
    [
        ((1, 1), None, "1.00.01", 136, ("dynamic",), "a1_02", {4, 5, 7, 8, 9, 10, 16}),
        ((None, None), "1.02.16", "1.00.01", 136, ("dynamic",), "a1_02", {4, 5, 7, 8, 9, 10, 16}),
        ((1, 1), "1.07.00", "1.02.07", 136, ("dynamic",), "a1_02", {4, 5, 7, 8, 9, 10, 16}),
        ((2, 1), "1.02.16", "1.00.01", 136, ("dynamic", "soft"), "a3", {4, 5, 7, 8, 9, 10, 16}),
        ((2, 1), "2.03.99", "2.01.01", 50, ("dynamic", "soft"), "a3", None),
        ((2, 1), "2.04.00", "2.01.01", 50, ("dynamic", "soft", "bloom", "radiant"), "a3", None),
        ((2, 1), "2.04.00", "3.04.01", 50, ("dynamic", "soft"), "a3", None),
    ],
)
def test_rgb_backlight_revision_controls_keep_independent_wire_contracts(
    pact, firmware, hardware, raw_brightness, modes, transport, scene_codes
):
    profile = device_profile("H6182", *pact, firmware=firmware, hardware=hardware)
    assert profile.music_modes == modes and profile.diy_upload_transport == transport
    assert profile.scene_codes == scene_codes
    assert not profile.supports_segments
    transform = profile.outbound_transform
    assert transform is not None
    assert transform(build_brightness(50, "H6182", profile=profile)) == frame(bytes([0x33, 4, raw_brightness]))
    legacy = pact in {(None, None), (1, 1)}
    rgb = "330502ff0714" if legacy else "33050dff0714"
    kelvin = "330502ffffff01ffae54" if legacy else "33050dffffff0a8cffae54"
    assert transform(build_color_rgb(255, 7, 20, "H6182", profile=profile)) == frame(bytes.fromhex(rgb))
    assert transform(build_color_temp(2700, "H6182", profile=profile)) == frame(bytes.fromhex(kelvin))
    _, _, packets = resolve_music_profile("H6182", "dynamic", 73, (12, 34, 56), None, {}, profile=profile)
    assert transform(packets[-1]) == frame(bytes.fromhex("33050301490c2238" if legacy else "330513004900010c2238"))
    if legacy:
        decoded = decode_status_frame(frame(bytes.fromhex("aa050301490c2238")), "H6182", profile=profile)
        assert decoded is not None
        music = parse_color_mode(decoded.generated, "H6182", profile=profile)
        assert (music.music_mode, music.music_sensitivity, music.music_color) == ("dynamic", 73, (12, 34, 56))
    for scene in SCENE_ENTRIES["H6182"]:
        if not scene_supported(scene, profile):
            continue
        scene_packets = build_native_scene_packets("H6182", scene, profile=profile)
        assert bool(len(scene_packets) > 1) is bool(scene.param and scene_codes is None)
        for packet in scene_packets:
            require_profile_packet(packet, profile)


@pytest.mark.parametrize(
    "model,firmware,mixed",
    [
        ("H6159", "1.02.02", False),
        ("H6159", "1.02.03", True),
        ("H6159", "1.07.02", True),
        ("H6139", "1.02.02", True),
        ("H6139", "1.07.02", True),
    ],
)
@pytest.mark.parametrize("speed,palette_size,pair_count", [(0, 8, 4), (100, 1, 1)])
def test_palette_diy_mixed_gate_and_temporary_slot_are_independent_of_scene_uploads(
    model, firmware, mixed, speed, palette_size, pair_count
):
    profile = device_profile(model, None, None, firmware=firmware, hardware="1.00.01")
    palette = ((255, 0, 0),) * palette_size
    single = SingleEffect(0, 0, speed, palette)
    compiled = compile_effect(LibraryItem.new("Palette", single), model, profile=profile)
    expected = bytes([254, 0, 0, speed, 3 * palette_size]) + bytes([255, 0, 0]) * palette_size + b"\0"
    assert reassemble_a1_02(compiled.upload_packets) == expected.ljust(((len(expected) + 15) // 16) * 16, b"\0")
    assert compiled.activation_packet == frame(bytes.fromhex("33050afe00"))
    assert decode_effect_frames(compiled.upload_packets, model, compiled.upload_transport) == single
    for packet in (*compiled.upload_packets, compiled.activation_packet):
        require_profile_packet(packet, profile)
    item = LibraryItem.new(
        "Mixed", MultiEffect(tuple(EffectPair(index % 3, 0) for index in range(pair_count)), speed, palette)
    )
    if mixed:
        validate_compiled_geometry(compile_effect(item, model, profile=profile), profile)
    else:
        with pytest.raises(ValueError, match="workflow|Mixed|multi"):
            compile_effect(item, model, profile=profile)


@pytest.mark.parametrize("model", ["H6139", "H6159"])
def test_rgb_palette_programs_use_their_own_carrier_and_reject_a_changed_route(model):
    profile = device_profile(model, 1, 1, firmware="1.07.02", hardware="1.00.01")
    if model == "H6139":
        unqualified = replace(SCENE_ENTRIES[model][0], command_version=1)
        assert not scene_supported(unqualified, profile)
        with pytest.raises(ValueError, match="not supported"):
            build_native_scene_packets(model, unqualified, profile=profile)
    for scene in SCENE_ENTRIES[model]:
        builtin = compile_effect(
            LibraryItem.new("Scene", BuiltinScene(CatalogueRef(model, scene.scene_id, scene.effect_id))),
            model,
            profile=profile,
        )
        assert builtin.activation_packet == frame(bytes([0x33, 5, 4, scene.code & 255, scene.code >> 8]))
        validate_compiled_geometry(builtin, profile)
        content = decode_catalogue_palette_scene(model, scene)
        if content is None:
            continue
        authored = compile_effect(LibraryItem.new("Programme", content), model, profile=profile)
        assert authored.activation_packet == frame(bytes.fromhex("330504c600"))
        assert authored.expected_effect is None
        validate_compiled_geometry(authored, profile)
        for packet in (*authored.upload_packets, authored.activation_packet):
            require_profile_packet(packet, profile)
        with pytest.raises(ValueError, match="route changed"):
            validate_compiled_geometry(authored, replace(profile, authored_palette_scene_selector=None))


@pytest.mark.parametrize("selector", [2, 13])
@pytest.mark.parametrize("model", ["H6181", "H6182"])
def test_legacy_temperature_flag_is_not_misread_as_a_kelvin_integer(selector, model):
    packet = frame(bytes([0xAA, 5, selector, 255, 255, 255, 1, *table_kelvin_rgb(2700), 0x7B]))
    profile = device_profile(model, None, None, firmware="1.02.16", hardware="1.00.01")
    decoded = decode_status_frame(packet, model, profile=profile)
    assert decoded is not None
    result = parse_color_mode(decoded.generated, model, profile=profile)
    assert result.color_temp_kelvin == 2700 and result.rgb_color is None
    assert decoded.generated.body.detail.unknown_tail.startswith(b"\x7b")
    bad = decode_status_frame(frame(bytes([0xAA, 5, selector, 1, 2, 3, 2])), model, profile=profile)
    assert bad is not None
    with pytest.raises(ValueError, match="flag"):
        parse_color_mode(bad.generated, model, profile=profile)


@pytest.mark.parametrize("model,selector", [("H6139", 2), ("H6159", 2), ("H6182", 13)])
async def test_whole_strip_kelvin_observation_retires_previous_rgb_authority(hass, model, selector):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", model, configuration_url=None)
    client = MagicMock(is_connected=True, start_notify=AsyncMock())
    coordinator._client = client
    coordinator._note_identity(fw_version="1.02.16", hw_version="1.00.01")
    await coordinator._start_notify()
    receive = client.start_notify.call_args.args[1]
    receive(None, bytearray(frame(bytes([0xAA, 5, selector, 12, 34, 56, 0, 0, 0, 0]))))
    assert coordinator.rgb_color_source == "observed"
    receive(None, bytearray(frame(bytes([0xAA, 5, selector, 255, 255, 255, 1, *table_kelvin_rgb(2700)]))))
    assert coordinator.color_temp_kelvin == 2700 and coordinator.color_temp_kelvin_source == "observed"
    assert coordinator.rgb_color_source == "retained"
    assert not coordinator._static_rgb_known


@pytest.mark.parametrize("selector", [2, 13])
@pytest.mark.parametrize(
    "companion,kelvin",
    [
        ("ff8912", 2000),
        ("ffd1a3", 4000),
        ("d6e1ff", 9000),
        ("fff9fd", 6600),
        ("f7f5ff", 7000),
        ("eff0ff", 7400),
    ],
)
def test_legacy_temperature_accepts_aliases_without_reassigning_overlapping_colours(selector, companion, kelvin):
    profile = device_profile("H6181", None, None)
    packet = frame(bytes([0xAA, 5, selector, 255, 255, 255, 1]) + bytes.fromhex(companion))
    decoded = decode_status_frame(packet, "H6181", profile=profile)
    assert decoded is not None
    result = parse_color_mode(decoded.generated, "H6181", profile=profile)
    assert result.color_temp_kelvin == kelvin and result.rgb_color is None


@pytest.mark.parametrize("companion", ["ff8912", "d6e1ff", "fff9fd", "010203"])
def test_legacy_temperature_rejects_unknown_or_out_of_range_companions(companion):
    profile = replace(device_profile("H6181", None, None), color_temp_range=(2700, 6500))
    packet = frame(bytes.fromhex("aa050dffffff01") + bytes.fromhex(companion))
    decoded = decode_status_frame(packet, "H6181", profile=profile)
    assert decoded is not None
    with pytest.raises(ValueError, match="Unrecognised legacy colour-temperature companion"):
        parse_color_mode(decoded.generated, "H6181", profile=profile)


@pytest.mark.parametrize(
    "content",
    [
        SingleEffect(0, 0, 50, ((255, 0, 0),)),
        MultiEffect((EffectPair(0, 0), EffectPair(2, 0)), 75, ((255, 0, 0), (0, 0, 255))),
    ],
)
@pytest.mark.parametrize("model", ["H6181", "H6182"])
def test_legacy_diy_upload_uses_the_approved_selector_and_round_trips(content, model):
    profile = device_profile(model, None, None, firmware="1.02.16", hardware="1.00.01")
    compiled = compile_effect(LibraryItem.new("Palette", content), model, diy_code=42, profile=profile)
    assert compiled.upload_transport == "a1_02"
    body = reassemble_a1_02(compiled.upload_packets)
    parsed = H6181DiyBody.from_bytes(body)
    parsed._read()
    assert parsed.selector == 42 and parsed.speed == content.speed
    assert compiled.activation_packet == frame(bytes.fromhex("33050a2a00"))
    assert decode_effect_frames(compiled.upload_packets, model, compiled.upload_transport) == content
    with pytest.raises(ValueError, match="transport"):
        validate_compiled_geometry(compiled, replace(profile, diy_upload_transport="a3"))
    with pytest.raises(ValueError, match="one-byte"):
        compile_effect(LibraryItem.new("Palette", content), model, diy_code=256, profile=profile)


def test_diy_application_requires_owner_approval_of_a_disposable_slot():
    item = LibraryItem.new("Palette", SingleEffect(0, 0, 50, ((255, 0, 0),)))
    with pytest.raises(ValueError, match="requires a DIY code"):
        compile_effect(item, "H6181")


@pytest.mark.parametrize(
    "pact,firmware,hardware,brightness,modes,uploads",
    [
        ((None, None), "1.00.99", "1.00.03", (20, 254), (), False),
        ((10, 1), "1.02.99", "1.00.03", None, ("dynamic", "soft"), False),
        ((10, 1), "1.03.00", "1.00.03", None, ("dynamic", "soft"), True),
        ((10, 2), None, None, None, ("dynamic", "soft"), True),
        ((10, 3), "1.03.00", "1.00.03", (20, 254), (), True),
        ((10, 2), "2.03.99", "2.01.01", None, ("dynamic", "soft"), True),
        ((10, 2), "2.04.00", "2.01.01", None, ("dynamic", "soft", "bloom", "radiant"), True),
        ((10, 2), "2.04.00", "2.00.05", None, ("dynamic", "soft"), True),
        ((10, 2), "2.04.00", "2.02.01", None, ("dynamic", "soft"), True),
        ((10, 2), "2.04.00", "3.04.01", None, ("dynamic", "soft"), True),
        ((10, 2), "2.04.00", "3.05.01", None, ("dynamic", "soft", "bloom", "radiant"), True),
    ],
)
def test_revision_boundaries_resolve_independently(pact, firmware, hardware, brightness, modes, uploads):
    profile = device_profile("H6181", *pact, firmware=firmware, hardware=hardware)
    assert profile.brightness_wire_range == brightness
    assert profile.music_modes == modes
    assert (profile.selector_only_scene_bits is None) is uploads
    assert profile.supports_custom_effects
    assert profile.diy_upload_transport == ("a1_02" if pact[0] is None else "a3")
    for scene in SCENE_ENTRIES["H6181"]:
        if not scene_supported(scene, profile):
            continue
        packets = build_native_scene_packets("H6181", scene, profile=profile)
        assert packets[-1] == frame(bytes([0x33, 5, 4, scene.code & 255, scene.code >> 8]))
        assert bool(len(packets) > 1) is bool(uploads and scene.param)


@pytest.mark.parametrize(
    "code,mode,calm,tail",
    [
        (48, "bloom", False, b"\x0a\x50"),
        (48, "bloom", True, b"\x0a\x14"),
        (49, "radiant", False, b"\x05\x64\x0a"),
        (49, "radiant", True, b"\x14\x46\x0a"),
    ],
)
@pytest.mark.parametrize(
    "model,pact,firmware,hardware,selector",
    [
        ("H6181", (10, 2), "2.04.00", "2.01.01", 19),
        ("H6139", (None, None), "1.07.02", "1.00.01", 14),
        ("H6139", (10, 2), "2.04.00", "2.01.01", 19),
        ("H6159", (1, 1), "1.07.02", "1.00.02", 14),
        ("H6159", (2, 1), "2.04.00", "2.01.01", 19),
        ("H6182", (2, 1), "2.04.00", "2.01.01", 19),
    ],
)
def test_palette_music_preserves_the_evidenced_style_and_palette(
    code, mode, calm, tail, model, pact, firmware, hardware, selector
):
    from custom_components.ha_govee_led_ble.transport import reassemble_a3

    profile = device_profile(model, *pact, firmware=firmware, hardware=hardware)
    _, _, packets = resolve_music_profile(
        model, mode, 73, None, calm, {}, profile=profile, palette=((12, 34, 56), (78, 90, 12))
    )
    envelope = reassemble_a3(tuple(packet for packet in packets if packet[0] == 0xA3))
    assert envelope[2 : 2 + 3 + 6 + len(tail)] == bytes([0x41, code, 2, 12, 34, 56, 78, 90, 12]) + tail
    packet = profile.outbound_transform(packets[-1]) if profile.outbound_transform is not None else packets[-1]
    assert packet == frame(bytes([0x33, 5, selector, code, 73]))
    variant = music_variant(profile, code)
    assert variant is not None
    parsed = parse_music_parameters(variant, envelope[3:])
    assert [(rgb.red, rgb.green, rgb.blue) for rgb in parsed.palette] == [(12, 34, 56), (78, 90, 12)]


def test_music_status_does_not_invent_a_selector_from_conflicting_readback_fields():
    profile = device_profile("H6181", 10, 1, firmware="1.03.00", hardware="1.00.03")
    decoded = decode_status_frame(frame(bytes.fromhex("aa051300320101ff0000")), "H6181", profile=profile)
    assert decoded is not None
    parsed = parse_color_mode(decoded.generated, "H6181", profile=profile)
    assert parsed.music_mode is None and parsed.music_sensitivity == 50
    assert parsed.music_color is None and parsed.music_calm is None and not parsed.music_color_present


@pytest.mark.parametrize(
    "firmware,hardware,selector,sensitivity,mode,observed",
    [
        ("2.04.00", "2.01.01", 48, 0, "bloom", 0),
        ("2.04.00", "3.05.01", 49, 99, "radiant", 99),
        ("2.03.99", "2.01.01", 48, 73, None, 73),
        ("2.04.00", "3.04.01", 49, 73, None, 73),
        ("2.04.00", "2.01.01", 255, 73, None, 73),
        ("2.04.00", "2.01.01", 48, 100, "bloom", None),
    ],
)
def test_music_readback_qualifies_selector_and_sensitivity_independently(
    firmware, hardware, selector, sensitivity, mode, observed
):
    profile = device_profile("H6181", 10, 2, firmware=firmware, hardware=hardware)
    packet = frame(bytes([0xAA, 5, 0x13, selector, sensitivity, 0x7B, 1, 255, 0, 0]))
    decoded = decode_status_frame(packet, "H6181", profile=profile)
    assert decoded is not None
    result = parse_color_mode(decoded.generated, "H6181", profile=profile)
    assert result.music_mode == mode and result.music_sensitivity == observed
    assert result.music_calm is None and result.music_color is None and not result.music_color_present


@pytest.mark.parametrize("selector,mode", [(0, None), (48, "bloom")])
async def test_music_observes_qualified_fields_without_confirming_ambiguous_settings(hass, selector, mode):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6181", configuration_url=None)
    client = MagicMock(is_connected=True, start_notify=AsyncMock())
    coordinator._client = client
    coordinator.pact_type, coordinator.pact_code = 10, 2
    coordinator._note_identity(fw_version="2.04.00", hw_version="2.01.01")
    await coordinator._start_notify()
    coordinator._h607c_marker_pact = (10, 2)
    coordinator._resolve_h607c_pact(preserve_state=True)
    receive = client.start_notify.call_args.args[1]
    coordinator.music_mode, coordinator.music_sensitivity = "dynamic", 73
    coordinator.music_color, coordinator.music_calm = (12, 34, 56), True
    coordinator._arm_expected_values({"music_sensitivity": 73})
    for sensitivity in (42, 73):
        receive(None, bytearray(frame(bytes([0xAA, 5, 0x13, selector, sensitivity, 1, 1, 255, 0, 0]))))
        assert coordinator.music_sensitivity == 73
        assert ("music_sensitivity" in coordinator._field_revisions) is (sensitivity == 73)
    assert coordinator.music_mode == (mode or "dynamic")
    assert ("music_mode" in coordinator._field_revisions) is (mode is not None)
    assert coordinator.music_color == (12, 34, 56) and coordinator.music_calm
    assert not {"music_color", "music_calm"} & coordinator._field_revisions.keys()
    assert coordinator.profile.music_readback_ambiguous


@pytest.mark.parametrize("payload", ["3305047b", "3399", "334101"])
def test_legacy_packet_authorisation_rejects_unqualified_operations(payload):
    with pytest.raises(ValueError):
        require_profile_packet(frame(bytes.fromhex(payload)), device_profile("H6181", None, None))


@pytest.mark.parametrize("subtype", [1, 3, 4])
def test_legacy_profile_does_not_admit_later_or_painted_uploads(subtype):
    profile = device_profile("H6181", None, None)
    with pytest.raises(ValueError):
        require_profile_packet(fragment_a3(subtype, b"\0")[0], profile)
