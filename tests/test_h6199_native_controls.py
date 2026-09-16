"""Direct-register replay and software qualification; not official-app captures."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.const import EntityCategory, Platform
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.ha_govee_led_ble import PLATFORMS, select, sensor
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    H6199_NATIVE_CONTROLS,
    H6199StatusQuery,
    build_h6199_control,
    build_h6199_control_query,
    parse_command,
    parse_command_ack_result,
    parse_h6199_control,
    parse_status,
)
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.transport import xor_checksum


def frame(prefix):
    body = bytes.fromhex(prefix).ljust(19, b"\0")
    return body + bytes((xor_checksum(body),))


def qualify(c):
    c.fw_version, c.hw_version = "1.10.04", "3.02.01"
    c.subordinate_20_version, c.subordinate_21_version = "1.03.00", "1.00.33"
    c.pact_type, c.pact_code = 2, 1


@pytest.fixture
def coordinator(hass, monkeypatch):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url=None)
    qualify(c)
    c._client = SimpleNamespace(is_connected=True, write_gatt_char=AsyncMock(), disconnect=AsyncMock())
    monkeypatch.setattr(c, "_ensure_connected", AsyncMock(return_value=c._client))
    monkeypatch.setattr(c, "_renew_foreground_lease", lambda: None)
    return c


@pytest.mark.parametrize("control,opcode", [("strip_direction", "30"), ("camera_position", "31"), ("gradient", "a3")])
def test_generated_builders_replies_acks(control, opcode):
    query = build_h6199_control_query(control)
    assert query == frame(f"aa{opcode}")
    parsed_query = H6199StatusQuery.from_bytes(query)
    parsed_query._read()
    assert parsed_query.domain.name == control
    for value in (0, 1):
        packet = build_h6199_control(control, value)
        assert packet == frame(f"33{opcode}{value:02x}")
        assert parse_command(packet, "H6199").body.value == value
        reply = parse_status(frame(f"aa{opcode}{value:02x}abcd"), "H6199")
        assert parse_h6199_control(reply) == {control: value}
        assert reply.body.unknown_tail.startswith(bytes.fromhex("abcd"))
    assert parse_h6199_control(parse_status(frame(f"aa{opcode}ff"), "H6199")) == {control: None}
    ack = parse_command_ack_result(frame(f"33{opcode}00"), "H6199")
    assert ack.parsed.opcode.name == control
    assert parse_status(query[:-1], "H6199") is None
    assert parse_status(query[:-1] + bytes((query[-1] ^ 1,)), "H6199") is None


@pytest.mark.parametrize("value", [True, False, -1, 2, 1.0, "1", None])
def test_invalid_writes(value):
    with pytest.raises(ValueError):
        build_h6199_control("gradient", value)
    with pytest.raises(ValueError):
        build_h6199_control("camera_status", 1)
    with pytest.raises(ValueError):
        build_h6199_control_query("dreamview")


async def test_diy_static_and_camera_observation_preserve_light(coordinator):
    c = coordinator
    c.is_on = True
    c._notify_callback(None, bytearray(bytes.fromhex("aa050afe0000000000000000000000000000005b")))
    assert c.color_mode is ParsedMode.DIY and c.diy_code == 254 and c.active_mode == "custom"
    assert parse_command(frame("33050afe00"), "H6199").body.detail.code == 254
    assert parse_command(frame("33050affff"), "H6199").body.detail.code == 65535
    c._notify_callback(None, bytearray(bytes.fromhex("aa051501000000000000000000000000000000bb")))
    assert c.gradient == 1 and c.color_mode is ParsedMode.COLOUR
    assert c.color_temp_kelvin_source != "observed" and c.rgb_color_source != "observed"
    light = GoveeBLELight(c)
    diagnostic = sensor.GoveeBLECameraStatus(c)
    assert build_h6199_control_query("camera_status") == frame("aa32")
    for value, expected in ((0, "absent"), (1, "healthy"), (2, "incompatible"), (255, "unknown")):
        c._notify_callback(None, bytearray(frame(f"aa32{value:02x}")))
        assert diagnostic.native_value == expected
        assert light.available and c.is_on
    c.camera_status = "healthy"
    await c._send_state_queries()
    assert diagnostic.native_value == "unknown" and light.available
    c._clear_client_state(c._client)
    assert c.camera_status == "unknown" and c.gradient is None


@pytest.mark.parametrize("control,opcode", [("strip_direction", "30"), ("camera_position", "31"), ("gradient", "a3")])
@pytest.mark.parametrize("reply", ["fresh", "missing", "wrong", "ack_only"])
async def test_native_write_requires_fresh_matching_readback(coordinator, control, opcode, reply):
    c = coordinator
    for key in H6199_NATIVE_CONTROLS[:-1]:
        setattr(c, key, 1)
    before = c.capture_effect_control_state()
    segments = (list(c.segment_colors), list(c.segment_brightness), c.segment_state_source)

    async def respond(_uuid, packet, **kwargs):
        if packet == build_h6199_control(control, 1):
            c._notify_callback(None, bytearray(frame(f"33{opcode}00")))
        elif packet == build_h6199_control_query(control):
            if reply in ("fresh", "wrong"):
                c._notify_callback(None, bytearray(frame(f"aa{opcode}{1 if reply == 'fresh' else 0:02x}")))
            elif reply == "ack_only":
                c._notify_callback(None, bytearray(frame(f"33{opcode}00")))

    c._client.write_gatt_char.side_effect = respond
    if reply == "fresh":
        await c.async_set_h6199_control(control, 1, timeout=0.01)
        assert getattr(c, control) == 1
    else:
        with pytest.raises((ValueError, TimeoutError)):
            await c.async_set_h6199_control(control, 1, timeout=0.01)
        assert getattr(c, control) == (0 if reply == "wrong" else None)
    assert [call.args[1] for call in c._client.write_gatt_char.await_args_list] == [
        build_h6199_control(control, 1),
        build_h6199_control_query(control),
    ]
    assert c.capture_effect_control_state() == before
    assert (c.segment_colors, c.segment_brightness, c.segment_state_source) == segments
    assert all(getattr(c, key) == 1 for key in H6199_NATIVE_CONTROLS[:-1] if key != control)
    c._client.disconnect.assert_not_awaited()


async def test_query_timeout_and_revision_change_fail_closed(coordinator):
    c = coordinator

    async def hang(_uuid, packet, **kwargs):
        if packet == build_h6199_control_query("gradient"):
            await asyncio.Event().wait()

    c._client.write_gatt_char.side_effect = hang
    with pytest.raises(TimeoutError):
        await c.async_set_h6199_control("gradient", 1, timeout=0.01)
    assert c.gradient is None
    c._client.write_gatt_char.reset_mock()
    c.hw_version = None
    with pytest.raises(ValueError, match="not qualified"):
        await c.async_set_h6199_control("gradient", 1)
    c._client.write_gatt_char.assert_not_awaited()
    await c._send_state_queries()
    packets = [call.args[1] for call in c._client.write_gatt_char.await_args_list]
    assert not any(build_h6199_control_query(key) in packets for key in H6199_NATIVE_CONTROLS)


async def test_reconnect_identity_guard_blocks_physical_write(coordinator, monkeypatch):
    c = coordinator
    c.gradient = 1

    async def reconnect():
        c.hw_version = None
        return c._client

    monkeypatch.setattr(c, "_ensure_connected", reconnect)
    with pytest.raises(ValueError, match="not qualified"):
        await c.async_set_h6199_control("gradient", 0)
    c._client.write_gatt_char.assert_not_awaited()
    assert c.gradient == 1


async def test_native_entity_to_generated_wire_and_fresh_notification(coordinator, hass, monkeypatch):
    c = coordinator
    entry = SimpleNamespace(runtime_data=c, entry_id="test")
    entity = select.GoveeBLEControlSelect(entry, "camera_position")
    entity.hass = hass
    monkeypatch.setattr(select, "get_effect_backend", lambda hass: None)

    async def respond(_uuid, packet, **kwargs):
        if packet == frame("333101"):
            assert entity.current_option is None
            c._notify_callback(None, bytearray(frame("333100")))
            assert entity.current_option is None
        elif packet == frame("aa31"):
            c._notify_callback(None, bytearray(frame("aa3101")))

    c._client.write_gatt_char.side_effect = respond
    await entity.async_select_option("bottom")
    assert entity.current_option == "bottom" and c._field_revisions["camera_position"] > 0
    assert not c.is_on and c.video_mode == "off"
    assert [call.args[1] for call in c._client.write_gatt_char.await_args_list] == [frame("333101"), frame("aa31")]


async def test_optional_camera_silence_does_not_fail_basic_refresh(coordinator):
    c = coordinator
    c.camera_status = "healthy"

    async def respond(_uuid, packet, **kwargs):
        replies = {frame("aa01"): frame("aa0101"), frame("aa04"): frame("aa042a"), frame("aa05"): frame("aa051500")}
        if packet in replies:
            c._notify_callback(None, bytearray(replies[packet]))

    c._client.write_gatt_char.side_effect = respond
    assert await c.refresh_state(refresh_all=True, required_domains=c.profile.setup_required_read_domains, timeout=0.01)
    packets = [call.args[1] for call in c._client.write_gatt_char.await_args_list]
    assert all(build_h6199_control_query(key) in packets for key in H6199_NATIVE_CONTROLS)
    assert c.camera_status == "unknown" and c.is_on and GoveeBLELight(c).available
    c._client.disconnect.assert_not_awaited()


async def test_platform_setup_late_identity_and_native_dispatch(coordinator, hass, monkeypatch):
    c = coordinator
    assert {Platform.SELECT, Platform.SENSOR} <= set(PLATFORMS)
    entry = SimpleNamespace(runtime_data=c, entry_id="test", async_on_unload=Mock())
    added_selects, added_sensors = [], []
    c.hw_version = None
    await select.async_setup_entry(hass, entry, added_selects.extend)
    await sensor.async_setup_entry(hass, entry, added_sensors.extend)
    assert not added_selects and not added_sensors
    qualify(c)
    c.async_update_listeners()
    assert len(added_selects) == 3 and len(added_sensors) == 1
    c.async_update_listeners()
    assert len(added_selects) == 3 and len(added_sensors) == 1
    for entity in added_selects:
        assert entity.entity_category is EntityCategory.CONFIG
        assert entity.entity_registry_enabled_default is False
    entity = added_selects[0]
    entity.hass = hass
    c.strip_direction = 0
    assert entity.current_option == "clockwise"
    backend = SimpleNamespace(preview=SimpleNamespace(async_supersede_device=AsyncMock()))
    monkeypatch.setattr(select, "get_effect_backend", lambda hass: backend)
    monkeypatch.setattr(c, "async_set_h6199_control", AsyncMock())
    await entity.async_select_option("anticlockwise")
    c.async_set_h6199_control.assert_awaited_once_with("strip_direction", 1)
    c.async_set_h6199_control.side_effect = ValueError("missing readback")
    with pytest.raises(HomeAssistantError):
        await entity.async_select_option("clockwise")
    backend.preview.async_supersede_device.reset_mock()
    c.hw_version = None
    assert not entity.available and added_sensors[0].native_value == "unknown"
    with pytest.raises(ServiceValidationError):
        await entity.async_select_option("clockwise")
    backend.preview.async_supersede_device.assert_not_awaited()
    for model in ("H6099", "H617A", "H617E"):
        c.model = model
        await select.async_setup_entry(hass, entry, added_selects.extend)
        await sensor.async_setup_entry(hass, entry, added_sensors.extend)
    assert len(added_selects) == 3 and len(added_sensors) == 1
    for call in entry.async_on_unload.call_args_list:
        call.args[0]()
