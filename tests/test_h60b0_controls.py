import time
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.light import ColorMode

from custom_components.ha_govee_led_ble.const import ReadDomain, device_profile
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.effect_catalogue import MODEL_EFFECT_CATALOGUES
from custom_components.ha_govee_led_ble.effect_compiler import compile_effect, validate_compiled_geometry
from custom_components.ha_govee_led_ble.effect_deployments import PriorControlState
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem
from custom_components.ha_govee_led_ble.effect_runtime import async_prepare_effect_control_state
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_boolean_control,
    build_boolean_control_query,
    build_brightness,
    build_colour_mode_query,
    build_hardware_query,
    build_pact_query,
    build_power_on_behaviour,
    build_segment_query,
    build_source_value,
    parse_a3_effect_envelope,
    parse_command_ack_result,
    require_profile_packet,
    upload_ack_mode,
    upload_ack_subtype,
    upload_ack_success,
)
from custom_components.ha_govee_led_ble.light_commands import (
    build_color_rgb,
    build_color_temp,
    build_segment_brightness,
    build_segment_brightness_packets,
    build_segment_color,
    build_segment_color_temp,
    build_segment_paint,
    parse_static_write,
)
from custom_components.ha_govee_led_ble.light_source import GoveeBLESourceLight
from custom_components.ha_govee_led_ble.music_commands import prepare_music_request
from custom_components.ha_govee_led_ble.protocol_core import serialize_native_body
from custom_components.ha_govee_led_ble.transport import reassemble_a3, xor_checksum

PROFILE = device_profile("H60B0", 1, 2)


def frame(prefix: str) -> bytes:
    content = bytes.fromhex(prefix).ljust(19, b"\x00")
    return content + bytes((xor_checksum(content),))


@pytest.mark.parametrize(
    ("packet", "prefix"),
    [
        (build_brightness(50, profile=PROFILE), "330432"),
        (build_color_rgb(1, 2, 3, profile=PROFILE), "33050d0102030000000000"),
        (build_color_temp(4000, profile=PROFILE), "33050dffffff0fa0ffd5a1"),
        (build_segment_color([9], 1, 2, 3, profile=PROFILE), "33052c01010102030000"),
        (build_segment_color([1, 8], 1, 2, 3, profile=PROFILE), "33052c020101020300008100"),
        (build_segment_color_temp([9], 4000, profile=PROFILE), "33052c0101ffd5a10fa0"),
        (build_segment_brightness([9], 40, profile=PROFILE), "33052c010228"),
        (build_segment_brightness([1, 8], 40, profile=PROFILE), "33052c0202288100"),
        (build_source_value("bottom", "brightness", 40, PROFILE), "33052c030228"),
        (build_source_value("bottom", "kelvin", 4000, PROFILE), "33052c03010fa0"),
        (build_source_value("top", "ripple_speed", 30, PROFILE), "33052c01031e"),
        (build_boolean_control("side_enabled", True, "H60B0", profile=PROFILE), "33300201"),
        (build_power_on_behaviour("off", PROFILE), "33410202"),
        (build_boolean_control_query("top_enabled", "H60B0", profile=PROFILE), "aa42"),
        (build_colour_mode_query(profile=PROFILE), "aa05"),
        (build_hardware_query(profile=PROFILE), "aa0703"),
        (build_pact_query(PROFILE), "aaef"),
        (build_segment_query(3, profile=PROFILE), "aaa503"),
    ],
)
def test_source_and_ordinary_commands_match_exact_model_contract(packet, prefix):
    assert packet == frame(prefix)
    require_profile_packet(packet, PROFILE)


def test_mixed_source_writes_partition_without_touching_bottom_or_other_segments():
    colour = build_segment_paint([([1, 9], (1, 2, 3))], "H60B0", profile=PROFILE)
    brightness = build_segment_brightness_packets([1, 9], 40, "H60B0", profile=PROFILE)
    assert colour == [frame("33052c01010102030000"), frame("33052c020101020300000100")]
    assert brightness == [frame("33052c010228"), frame("33052c0202280100")]
    for packets in (colour, brightness):
        assert [parse_static_write(packet, profile=PROFILE).segment_mask for packet in packets] == [256, 1]
        for packet in packets:
            require_profile_packet(packet, PROFILE)


def test_combined_music_ack_tracks_the_outer_mode_and_preserves_envelope_fill():
    packets = prepare_music_request("H60B0", "combined", 50, None, False, {}, profile=PROFILE)
    index = len(packets) - 2
    assert upload_ack_subtype(packets, index, "H60B0", profile=PROFILE) == 0x41
    assert upload_ack_mode(packets, index, "H60B0", profile=PROFILE) == 130
    envelope = reassemble_a3(tuple(packet for packet in packets if packet[0] == 0xA3))
    assert serialize_native_body(parse_a3_effect_envelope(envelope, "H60B0", profile=PROFILE)) == envelope
    for prefix, expected in (("a3418200", True), ("a3418201", False), ("a3413000", None)):
        parsed = parse_command_ack_result(frame(prefix), "H60B0", profile=PROFILE).parsed
        assert parsed is not None
        assert upload_ack_success(parsed, 0x41, 130, protocol=0xA3) is expected


@pytest.mark.parametrize("pact", [(1, 1), (1, 2), (1, 3)])
def test_revision_qualification_does_not_infer_firmware_thresholds(pact):
    profile = device_profile("H60B0", *pact, firmware="1.00.12", hardware="3.05.01")
    assert profile.native_effect_revision == pact[1]
    assert profile.supports_rgb and profile.supports_scenes and profile.supports_ripple_speed
    unknown = device_profile("H60B0", None, None, firmware="1.00.12", hardware="3.05.01")
    with pytest.raises(ValueError):
        require_profile_packet(build_source_value("bottom", "kelvin", 4000, profile), unknown)
    with pytest.raises(ValueError):
        require_profile_packet(build_segment_color([9], 1, 2, 3, profile=profile), unknown)


@pytest.mark.parametrize(
    "prefix",
    [
        "33300401",
        "33300102",
        "33052c0202010001",
        "33052c010365",
        "33052c030265",
        "33052c03010fa1",
        "33052c050101020300000100",
    ],
)
def test_unqualified_sources_masks_and_levels_are_rejected(prefix):
    with pytest.raises(ValueError):
        require_profile_packet(frame(prefix), PROFILE)


async def test_source_readback_is_independent_and_invalid_state_cannot_update_flags(hass, monkeypatch):
    from custom_components.ha_govee_led_ble import coordinator_notifications, h60b0_controls

    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H60B0", configuration_url=None)
    coordinator.profile = PROFILE
    decode = MagicMock(wraps=h60b0_controls.source_readback)
    monkeypatch.setattr(h60b0_controls, "source_readback", decode)
    monkeypatch.setattr(coordinator_notifications, "source_readback", decode)
    coordinator._notify_callback(None, bytearray(frame("aa42d00bb81e0fa028")))
    decode.assert_called_once()
    assert coordinator.boolean_control_state == {"top_enabled": True, "side_enabled": False, "bottom_enabled": True}
    assert (coordinator.bottom_kelvin, coordinator.bottom_brightness, coordinator.ripple_speed) == (4000, 40, 30)
    coordinator._notify_callback(None, bytearray(frame("aa42200bb81e0fa065")))
    assert coordinator.boolean_control_state["top_enabled"] is True
    assert coordinator.bottom_brightness == 40
    bottom = GoveeBLESourceLight(coordinator, "bottom")
    assert bottom.supported_color_modes == {ColorMode.COLOR_TEMP}
    assert bottom.color_temp_kelvin == 4000 and bottom.brightness == 102
    assert bottom.rgb_color is None


@pytest.mark.parametrize("pact_code", [1, 2, 3])
@pytest.mark.parametrize("prefix", ["aa42b0", "aa052c"])
async def test_reported_source_state_keeps_bottom_values_separate_from_ripple(hass, pact_code, prefix):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H60B0", configuration_url=None)
    coordinator.profile = device_profile("H60B0", 1, pact_code)
    coordinator._notify_callback(None, bytearray(frame(prefix + "000032196464")))
    assert (coordinator.top_kelvin, coordinator.ripple_speed) == (0, 50)
    assert (coordinator.bottom_kelvin, coordinator.bottom_brightness) == (6500, 100)
    bottom = GoveeBLESourceLight(coordinator, "bottom")
    assert bottom.color_temp_kelvin == 6500
    assert bottom.brightness == 255


async def test_bottom_source_uses_native_attributes_without_segment_writes(mock_coordinator):
    coordinator = mock_coordinator
    coordinator.model, coordinator.profile = "H60B0", PROFILE
    coordinator.is_on = True
    coordinator.boolean_control_state = {"top_enabled": True, "side_enabled": False, "bottom_enabled": True}
    coordinator._async_supersede_effect_preview = AsyncMock()
    coordinator.async_prepare_identity_gated_control = AsyncMock(return_value=lambda: None)
    coordinator.refresh_state = AsyncMock(return_value=True)
    coordinator.async_set_boolean_control = AsyncMock()
    coordinator.async_set_source_value = AsyncMock()
    coordinator.async_set_segment_brightness = AsyncMock()
    coordinator.async_set_segment_kelvin = AsyncMock()
    coordinator._notify_started_monotonic = 1.0
    coordinator._field_revisions["is_on"] = 1
    coordinator._field_received_at.update({"is_on": 2.0, "boolean_bottom_enabled": 2.0})
    coordinator._observed_power_write_generation = coordinator._power_write_generation
    coordinator._observed_power_profile_generation = coordinator._profile_generation
    coordinator._source_power_observation_generation["boolean_bottom_enabled"] = (
        coordinator._power_write_generation,
        coordinator._profile_generation,
    )
    coordinator.async_mask_transaction = MagicMock(
        side_effect=AssertionError("Native source controls do not address segments")
    )
    source = GoveeBLESourceLight(coordinator, "bottom")
    await source.async_turn_on(brightness=102, color_temp_kelvin=4000)
    assert coordinator.async_set_source_value.await_args_list[0].args == ("bottom", "brightness", 40)
    assert coordinator.async_set_source_value.await_args_list[1].args == ("bottom", "kelvin", 4000)
    coordinator.async_set_segment_brightness.assert_not_awaited()
    coordinator.async_set_segment_kelvin.assert_not_awaited()
    coordinator.async_set_boolean_control.assert_not_awaited()


@pytest.mark.parametrize(
    ("source", "attribute", "value", "prefix", "matching_body", "mismatched_body"),
    [
        ("bottom", "brightness", 100, "33052c030264", "000032196464", "000032196432"),
        ("bottom", "kelvin", 6500, "33052c03011964", "000032196464", "0000320fa064"),
        ("top", "ripple_speed", 30, "33052c01031e", "00001e196464", "000032196464"),
    ],
)
@pytest.mark.parametrize("matching", [True, False])
async def test_native_source_setting_requires_fresh_matching_readback(
    hass, source, attribute, value, prefix, matching_body, mismatched_body, matching
):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H60B0", configuration_url=None)
    coordinator.profile = PROFILE
    coordinator.pact_type, coordinator.pact_code = 1, 2
    client = MagicMock(is_connected=True)
    coordinator._client = client
    coordinator._notification_token = object()
    coordinator._ensure_connected = AsyncMock(return_value=client)
    coordinator._async_supersede_effect_preview = AsyncMock()
    body = matching_body if matching else mismatched_body

    async def write(_client, packet, **kwargs):
        if guard := kwargs.get("before_write"):
            guard()
        if callback := kwargs.get("on_write"):
            callback()
        if packet == frame("aa42"):
            coordinator._notify_callback(None, bytearray(frame("aa42f0" + body)))
        if packet == frame("aa05"):
            coordinator._notify_callback(None, bytearray(frame("aa052c" + body)))

    coordinator._async_write_packet = AsyncMock(side_effect=write)
    if matching:
        await coordinator.async_set_source_value(source, attribute, value)
        field = "ripple_speed" if attribute == "ripple_speed" else f"{source}_{attribute}"
        assert getattr(coordinator, field) == value
    else:
        with pytest.raises(ValueError, match="did not confirm"):
            await coordinator.async_set_source_value(source, attribute, value)
    assert [call.args[1] for call in coordinator._async_write_packet.await_args_list] == [
        frame(prefix),
        frame("aa42"),
        *([frame("aa05")] if matching else []),
    ]


async def test_preview_requires_complete_source_values_and_preserves_them_in_storage(hass):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H60B0", configuration_url=None)
    coordinator.profile = PROFILE
    prior = PriorControlState("scene", True, 50, (1, 2, 3), top_enabled=True, side_enabled=False, bottom_enabled=True)
    coordinator.capture_effect_control_state = MagicMock(return_value=prior)
    with pytest.raises(RuntimeError, match="restorable source values"):
        await async_prepare_effect_control_state(coordinator, require_restorable_static=True)
    complete = replace(prior, bottom_kelvin=4000, bottom_brightness=40, ripple_speed=30)
    assert PriorControlState.from_dict(complete.to_dict()) == complete
    coordinator.capture_effect_control_state.return_value = complete
    assert await async_prepare_effect_control_state(coordinator, require_restorable_static=True)


async def test_reconnect_revokes_cached_pact_and_qualifies_the_current_marker(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H60B0", configuration_url=None)
    coordinator.pact_type, coordinator.pact_code = 1, 2
    coordinator.profile = PROFILE
    old_client = MagicMock(is_connected=True)
    coordinator._client = old_client
    coordinator._confirmed_identity_fields.add("pact")
    coordinator._h607c_marker_pact = (1, 2)
    coordinator._h607c_advertisement_observations = {"cached": (time.monotonic() - 10, frozenset({(1, 2)}))}
    template = next(
        template
        for template in MODEL_EFFECT_CATALOGUES["H60B0"].templates
        if template.id == "template:h60b0:1:single:1"
    )
    compiled = compile_effect(LibraryItem.new("Older native effect", template.content), "H60B0", profile=PROFILE)
    source_packet = build_source_value("bottom", "brightness", 40, PROFILE)
    coordinator._clear_client_state(old_client)
    assert coordinator.profile.native_effect_revision == 2
    assert not coordinator.identity_fields_confirmed()
    assert coordinator.h607c_pact_readiness == "stale"
    with pytest.raises(ValueError):
        coordinator._validate_authorized_packet(source_packet)
    with pytest.raises(ValueError):
        coordinator._validate_authorized_packet(compiled.upload_packets[0])

    client = MagicMock(is_connected=True, start_notify=AsyncMock(), write_gatt_char=AsyncMock(), disconnect=AsyncMock())
    coordinator._encryption = MagicMock(
        ready=True, version=0, marker_pact=(1, 3), async_select=AsyncMock(), async_negotiate=AsyncMock()
    )
    monkeypatch.setattr(
        "custom_components.ha_govee_led_ble.coordinator.async_establish_ble_connection", AsyncMock(return_value=client)
    )
    monkeypatch.setattr(coordinator, "_send_identity_queries", AsyncMock())
    monkeypatch.setattr(coordinator, "_start_keep_alive", MagicMock())
    try:
        await coordinator._ensure_connected()
        assert coordinator.profile.native_effect_revision == 3
        assert coordinator.identity_fields_confirmed()
        assert coordinator.h607c_pact_readiness == "ready"
        coordinator._validate_authorized_packet(source_packet)
        with pytest.raises(ValueError, match="revision"):
            validate_compiled_geometry(compiled, coordinator.profile)
        coordinator._clear_client_state(client)
        assert not coordinator.identity_fields_confirmed()
        with pytest.raises(ValueError):
            coordinator._validate_authorized_packet(source_packet)
        assert coordinator.profile.native_effect_revision == 3
    finally:
        await coordinator.disconnect()


async def test_only_current_subscription_advertisements_can_confirm_pact(hass):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H60B0", configuration_url=None)
    coordinator._client = MagicMock(is_connected=True)
    coordinator._notify_started_monotonic = time.monotonic()
    coordinator._h607c_advertisement_observations = {
        "proxy": (coordinator._notify_started_monotonic - 1, frozenset({(1, 2)}))
    }
    coordinator._resolve_h607c_pact()
    assert not coordinator.identity_fields_confirmed()
    coordinator._h607c_advertisement_observations["proxy"] = (
        coordinator._notify_started_monotonic + 1,
        frozenset({(1, 2)}),
    )
    coordinator._resolve_h607c_pact()
    assert coordinator.identity_fields_confirmed()
    coordinator._h607c_marker_pact = (1, 3)
    coordinator._resolve_h607c_pact()
    assert not coordinator.identity_fields_confirmed()
    assert not coordinator._authorization_profile().supports_custom_effects


async def test_pact_is_rechecked_after_reply_pacing_before_the_physical_write(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H60B0", configuration_url=None)
    coordinator.profile = PROFILE
    coordinator.pact_type, coordinator.pact_code = 1, 2
    coordinator._client = client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    coordinator._confirmed_identity_fields.add("pact")
    packet = build_source_value("bottom", "brightness", 40, PROFILE)

    async def lose_confirmation():
        coordinator._confirmed_identity_fields.discard("pact")

    monkeypatch.setattr(coordinator._reply_gate, "wait", lose_confirmation)
    with pytest.raises(ValueError):
        await coordinator._async_write_packet(client, packet, arm_expected=True)
    client.write_gatt_char.assert_not_awaited()


@pytest.fixture
def pact_connection(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H60B0", configuration_url=None)
    coordinator.pact_type, coordinator.pact_code = 1, 2
    coordinator.profile = PROFILE
    coordinator._h607c_advertisement_observations = {"cached": (time.monotonic() - 10, frozenset({(1, 2)}))}
    client = MagicMock(is_connected=True, start_notify=AsyncMock(), write_gatt_char=AsyncMock(), disconnect=AsyncMock())
    coordinator._encryption = MagicMock(
        ready=True,
        version=0,
        marker_pact=None,
        async_select=AsyncMock(),
        async_negotiate=AsyncMock(),
        encode=lambda packet: packet,
        decode=lambda packet: packet,
    )
    monkeypatch.setattr(
        "custom_components.ha_govee_led_ble.coordinator.async_establish_ble_connection", AsyncMock(return_value=client)
    )
    monkeypatch.setattr(coordinator, "_send_identity_queries", AsyncMock())
    monkeypatch.setattr(coordinator, "_start_keep_alive", MagicMock())
    return coordinator, client


@pytest.mark.parametrize(("revision", "cached"), [(1, True), (2, True), (3, True), (9, True), (2, False)])
async def test_live_pact_read_qualifies_without_marker_or_connected_advertisements(pact_connection, revision, cached):
    coordinator, client = pact_connection
    if not cached:
        coordinator.pact_type = coordinator.pact_code = None
        coordinator.profile = device_profile("H60B0", None, None)
        coordinator._h607c_advertisement_observations.clear()
    initial_profile = coordinator.profile
    source = GoveeBLESourceLight(coordinator, "top")
    packet = build_source_value("bottom", "brightness", 40, PROFILE)

    async def write(_uuid, query, **kwargs):
        assert query == frame("aaef")
        assert source.available is cached
        assert coordinator.profile == initial_profile
        assert not coordinator.identity_fields_confirmed()
        with pytest.raises(ValueError):
            coordinator._require_writable_packet(packet, require_profile_packet, arm_expected=True)
        receive = client.start_notify.await_args.args[1]
        receive(None, bytearray(frame(f"aaef0001{revision:02x}" + "55" * 14)))

    client.write_gatt_char.side_effect = write
    try:
        assert await coordinator._ensure_connected() is client
        client.write_gatt_char.assert_awaited_once()
        assert coordinator.identity_fields_confirmed()
        assert coordinator._authorization_profile().supports_rgb is (revision != 9)
        if revision != 9:
            assert source.available
            assert coordinator.profile.native_effect_revision == revision
            coordinator._validate_authorized_packet(packet)
        else:
            assert not source.available
            assert coordinator._pact_query_result == "unsupported"
            with pytest.raises(ValueError):
                await coordinator._async_write_packet(client, packet, arm_expected=True)
            client.write_gatt_char.assert_awaited_once()
    finally:
        await coordinator.disconnect()


async def test_pact_timeout_preserves_presentation_but_not_write_authority(pact_connection, virtual_clock):
    coordinator, client = pact_connection
    source = GoveeBLESourceLight(coordinator, "top")
    packet = build_source_value("bottom", "brightness", 40, PROFILE)
    try:
        assert await coordinator._ensure_connected() is client
        assert coordinator._pact_query_result == "timeout"
        assert coordinator.profile == PROFILE and source.available
        assert not coordinator.identity_fields_confirmed()
        assert not coordinator._authorization_profile().supports_rgb
        coordinator._validate_authorized_packet(build_brightness(50, profile=PROFILE))
        with pytest.raises(ValueError):
            coordinator._validate_authorized_packet(packet)
        receive = client.start_notify.await_args.args[1]
        malformed = bytearray(frame("aaef000102"))
        malformed[-1] ^= 1
        receive(None, malformed)
        assert not coordinator.identity_fields_confirmed()
        receive(None, bytearray(frame("aaef000102")))
        assert coordinator.identity_fields_confirmed()
        coordinator._clear_client_state(client)
        assert not coordinator.identity_fields_confirmed()
        receive(None, bytearray(frame("aaef000103")))
        assert not coordinator._connection_pacts
        client.write_gatt_char.side_effect = lambda *args, **kwargs: receive(None, bytearray(frame("aaef000103")))
        assert await coordinator._ensure_connected() is client
        assert not coordinator.identity_fields_confirmed()
        assert coordinator._pact_query_result == "timeout"
        assert coordinator.profile == PROFILE
    finally:
        await coordinator.disconnect()


@pytest.mark.parametrize("conflict", ["query", "marker", "advertisement"])
async def test_live_pact_conflicts_revoke_write_authority(pact_connection, conflict):
    coordinator, client = pact_connection
    client.write_gatt_char.side_effect = lambda *args, **kwargs: client.start_notify.await_args.args[1](
        None, bytearray(frame("aaef000102"))
    )
    try:
        await coordinator._ensure_connected()
        assert coordinator.identity_fields_confirmed()
        if conflict == "query":
            client.start_notify.await_args.args[1](None, bytearray(frame("aaef000103")))
        elif conflict == "marker":
            coordinator._h607c_marker_pact = (1, 3)
            coordinator._resolve_h607c_pact()
        else:
            coordinator._h607c_advertisement_observations["current"] = (time.monotonic(), frozenset({(1, 3)}))
            coordinator._resolve_h607c_pact()
        assert coordinator.h607c_pact_readiness == "conflicting"
        assert not coordinator.identity_fields_confirmed()
        assert not coordinator._authorization_profile().supports_rgb
        with pytest.raises(ValueError):
            await coordinator._async_write_packet(
                client, build_source_value("bottom", "brightness", 40, PROFILE), arm_expected=True
            )
        client.write_gatt_char.assert_awaited_once()
    finally:
        await coordinator.disconnect()


@pytest.mark.parametrize(
    ("flags", "expected"),
    [(0x30, (False, False, True, True)), (0xB0, (True, False, True, True)), (0xA0, (True, False, True, False))],
)
async def test_reported_source_notifications_update_only_power_fields(hass, flags, expected):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H60B0", configuration_url=None)
    coordinator.profile = PROFILE
    coordinator._notify_callback(None, bytearray(frame("aa42d00bb81e0fa028")))
    native_revisions = {field: coordinator._field_revisions[field] for field in ("bottom_kelvin", "ripple_speed")}
    notification = frame(f"ee3001{flags:02x}" + "ab" * 15)
    coordinator._notify_callback(None, bytearray(notification))
    controls = ("top_enabled", "side_enabled", "bottom_enabled")
    assert (coordinator.is_on, *(coordinator.boolean_control_state[name] for name in controls)) == expected
    assert (coordinator.bottom_kelvin, coordinator.bottom_brightness, coordinator.ripple_speed) == (4000, 40, 30)
    assert {field: coordinator._field_revisions[field] for field in native_revisions} == native_revisions
    assert not coordinator.identity_fields_confirmed()
    assert ReadDomain.PACT not in coordinator._domain_revisions
    broken = bytearray(notification)
    broken[3] ^= 0xF0
    coordinator._notify_callback(None, broken)
    assert (coordinator.is_on, *(coordinator.boolean_control_state[name] for name in controls)) == expected
    coordinator._expected_state["boolean_top_enabled"] = (True, time.monotonic() + 10)
    coordinator.boolean_control_state["top_enabled"] = True
    previous = coordinator._field_revisions["boolean_top_enabled"]
    coordinator._notify_callback(None, bytearray(notification))
    assert coordinator.boolean_control_state["top_enabled"] is True
    assert coordinator._field_revisions["boolean_top_enabled"] == previous
