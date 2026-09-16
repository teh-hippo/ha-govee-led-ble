"""APK-derived standalone controls; no hardware or calibration-display qualification."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import voluptuous as vol
from homeassistant.const import Platform
from homeassistant.core import ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.ha_govee_led_ble.const import DOMAIN, MODEL_PROFILES, ReadDomain, get_profile
from custom_components.ha_govee_led_ble.control_arbiter import BLEControlArbiter, ControlIntent
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_status import decode_status_frame
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_camera_health_query,
    build_installation_direction,
    build_installation_direction_query,
    parse_command,
)
from custom_components.ha_govee_led_ble.h6099_controls import (
    async_read_h6099_controls,
    async_read_installation_controls,
    async_set_installation_direction,
    h6099_control_queries,
    h6099_control_status,
    installation_direction_value,
)
from custom_components.ha_govee_led_ble.light_services import async_register_light_services
from custom_components.ha_govee_led_ble.transport import xor_checksum


def frame(prefix: str) -> bytes:
    body = bytes.fromhex(prefix).ljust(19, b"\0")
    return body + bytes((xor_checksum(body),))


def test_exact_builders_and_generic_status_root() -> None:
    profile = get_profile("H6099")
    domains = {ReadDomain.INSTALLATION_DIRECTION, ReadDomain.CAMERA_HEALTH}
    assert domains <= profile.read_domains
    assert not domains & profile.setup_required_read_domains
    assert build_installation_direction_query("H6099") == frame("aa30")
    assert build_camera_health_query("H6099") == frame("aa32")
    assert h6099_control_queries("H6099", profile) == (frame("aa30"), frame("aa32"))
    assert h6099_control_queries("H6199", get_profile("H6199")) == ()
    for value in (2, 3, 4, 5):
        packet = build_installation_direction(value, "H6099")
        assert packet == frame(f"3330{value:02x}")
        parsed = parse_command(packet, "H6099")
        assert parsed is not None
        assert parsed.opcode.name == "installation_direction" and parsed.body.value == value
        decoded = decode_status_frame(frame(f"aa30{value:02x}abcd"), "H6099")
        assert decoded is not None
        assert decoded.domain is ReadDomain.INSTALLATION_DIRECTION
        assert decoded.generated.body.unknown_tail.startswith(bytes.fromhex("abcd"))
        assert h6099_control_status(decoded, profile) == {"installation_direction": value}
    for value, expected in ((0, "absent"), (1, "healthy"), (2, "incompatible"), (3, "unknown"), (255, "unknown")):
        decoded = decode_status_frame(frame(f"aa32{value:02x}"), "H6099")
        assert decoded is not None
        assert decoded.domain is ReadDomain.CAMERA_HEALTH
        assert h6099_control_status(decoded, profile) == {"camera_health": expected}
    for prefix in ("aa3000", "aa3001", "aa30ff"):
        assert h6099_control_status(decode_status_frame(frame(prefix), "H6099"), profile) == {
            "installation_direction": None
        }
    assert h6099_control_status(decode_status_frame(frame("aa3101"), "H6099"), profile) == {}
    assert decode_status_frame(frame("aa3201")[:-1], "H6099") is None
    assert decode_status_frame(frame("aa3201")[:-1] + b"\0", "H6099") is None


@pytest.mark.parametrize("value", [True, False, 2.0, 2.5, None, -1, 0, 1, 6, 255, "2.0", "02", "left"])
def test_invalid_values_are_not_coerced(value) -> None:
    with pytest.raises(vol.Invalid):
        installation_direction_value(value)
    with pytest.raises(ValueError):
        build_installation_direction(value, "H6099")


def test_profile_gates_and_grammar_direction(monkeypatch) -> None:
    for model in ("H617A", "H6199", "H9999"):
        for builder in (build_installation_direction_query, build_camera_health_query):
            with pytest.raises(ValueError):
                builder(model)
        with pytest.raises(ValueError):
            build_installation_direction(2, model)
    profile = replace(get_profile("H6099"), supports_installation_direction=False)
    monkeypatch.setitem(MODEL_PROFILES, "H6099", profile)
    with pytest.raises(ValueError):
        build_installation_direction(2, "H6099")
    assert build_installation_direction_query("H6099") == frame("aa30")
    monkeypatch.setitem(MODEL_PROFILES, "H6099", replace(profile, command_grammar="H6199"))
    with pytest.raises(ValueError):
        build_camera_health_query("H6099")
    decoded = decode_status_frame(frame("aa3201"), "H6099")
    assert h6099_control_status(decoded, profile) == {"camera_health": "healthy"}
    assert (
        h6099_control_status(
            decoded, replace(profile, read_domains=frozenset(), setup_required_read_domains=frozenset())
        )
        == {}
    )


def test_light_service_registration(hass) -> None:
    with patch(
        "custom_components.ha_govee_led_ble.light_services.service.async_register_platform_entity_service"
    ) as register:
        async_register_light_services(hass)
    calls = {call.args[2]: call.kwargs for call in register.call_args_list}
    write = calls["set_installation_direction"]
    assert write["entity_domain"] is Platform.LIGHT
    assert write["func"] is async_set_installation_direction
    schema = vol.Schema(write["schema"])
    for value in (2, 3, 4, 5):
        assert schema({"value": str(value)}) == {"value": value}
    for data in ({}, {"value": 1}, {"value": 2.5}, {"value": 2, "corner": "left"}):
        with pytest.raises(vol.Invalid):
            schema(data)
    assert calls["read_installation_controls"]["supports_response"] is SupportsResponse.ONLY
    assert calls["read_installation_controls"]["func"] is async_read_installation_controls


async def test_services_preflight_freshness_and_no_optimistic_state(hass, mock_coordinator) -> None:
    coordinator = mock_coordinator
    coordinator.model = "H6099"
    coordinator.profile = get_profile("H6099")
    coordinator._control_arbiter = BLEControlArbiter()
    coordinator.installation_direction = 3
    coordinator.camera_health = "healthy"
    entity = SimpleNamespace(coordinator=coordinator, _async_supersede_preview=AsyncMock())
    call = ServiceCall(hass, DOMAIN, "set_installation_direction", {"value": 4})
    with pytest.raises(ServiceValidationError) as exc:
        await async_set_installation_direction(
            entity, ServiceCall(hass, DOMAIN, "set_installation_direction", {"value": 2.5})
        )
    assert exc.value.translation_domain == DOMAIN
    assert exc.value.translation_key == "invalid_control_request"
    entity._async_supersede_preview.assert_not_awaited()
    coordinator.async_write_effect_sequence.assert_not_awaited()
    assert await async_read_installation_controls(entity, call) == {
        "installation_direction": None,
        "camera_health": "unknown",
    }
    with pytest.raises(HomeAssistantError) as command_exc:
        await async_set_installation_direction(entity, call)
    assert command_exc.value.translation_domain == DOMAIN
    assert command_exc.value.translation_key == "device_command_failed"
    assert coordinator.installation_direction == 3
    coordinator.async_write_effect_sequence.assert_awaited_once_with((frame("333004"),), intent=ControlIntent.USER)

    async def refresh(**kwargs):
        assert kwargs == {
            "refresh_all": True,
            "required_domains": frozenset({ReadDomain.INSTALLATION_DIRECTION, ReadDomain.CAMERA_HEALTH}),
        }
        for prefix in ("aa3004", "aa3200"):
            decoded = decode_status_frame(frame(prefix), "H6099")
            for key, value in h6099_control_status(decoded, coordinator.profile).items():
                setattr(coordinator, key, value)
            coordinator._domain_revisions[decoded.domain] = coordinator._domain_revisions.get(decoded.domain, 0) + 1
        return True

    coordinator.refresh_state.side_effect = refresh
    await async_set_installation_direction(entity, call)
    assert coordinator.installation_direction == 4 and coordinator.camera_health == "absent"
    coordinator.refresh_state.side_effect = None
    assert await async_read_installation_controls(entity, call) == {
        "installation_direction": None,
        "camera_health": "unknown",
    }

    async def direction_only(**kwargs):
        coordinator._domain_revisions[ReadDomain.INSTALLATION_DIRECTION] += 1
        return False

    coordinator.refresh_state.side_effect = direction_only
    assert await async_read_installation_controls(entity, call) == {
        "installation_direction": 4,
        "camera_health": "unknown",
    }
    coordinator.async_write_effect_sequence.side_effect = RuntimeError("transport failed")
    with pytest.raises(RuntimeError, match="transport failed"):
        await async_set_installation_direction(entity, call)
    assert coordinator.installation_direction == 4
    coordinator.profile = get_profile("H6199")
    entity._async_supersede_preview.reset_mock()
    with pytest.raises(ServiceValidationError) as exc:
        await async_read_installation_controls(entity, call)
    assert exc.value.translation_domain == DOMAIN
    assert exc.value.translation_key == "unsupported_model"
    assert exc.value.translation_placeholders == {"service": "read_installation_controls", "model": "H6099"}
    with pytest.raises(ServiceValidationError):
        await async_set_installation_direction(entity, call)
    entity._async_supersede_preview.assert_not_awaited()


@pytest.mark.parametrize("replies", [("aa3004", "aa3201"), ("aa3004",), ("aa3202",), ()])
async def test_concrete_controls_optional_refresh_and_independent_freshness(hass, monkeypatch, replies):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6099", configuration_url="test")
    client = SimpleNamespace(is_connected=True, write_gatt_char=AsyncMock(), disconnect=AsyncMock())
    c._client = client
    monkeypatch.setattr(c, "_ensure_connected", AsyncMock(return_value=client))
    refresh = c.refresh_state

    async def immediate_refresh(**kwargs):
        return await refresh(**kwargs, timeout=0.1)

    monkeypatch.setattr(c, "refresh_state", immediate_refresh)
    for prefix in ("aa3002", "aa3201"):
        c._notify_callback(None, bytearray(frame(prefix)))

    async def respond(_uuid, packet, **kwargs):
        for prefix in ("aa0101", "aa042a", "aa0515011194", *replies):
            c._notify_callback(None, bytearray(frame(prefix)))
        if packet[:2] == b"\xaa\xa5":
            count = min(4, 15 - (packet[2] - 1) * 4)
            c._notify_callback(None, bytearray(frame(packet[:3].hex() + "64010203" * count)))

    client.write_gatt_char.side_effect = respond
    assert await c.refresh_state(refresh_all=True, required_domains=c.profile.setup_required_read_domains)
    packets = [call.args[1] for call in client.write_gatt_char.await_args_list]
    assert frame("aa30") in packets and frame("aa32") in packets
    assert await async_read_h6099_controls(c) == {
        "installation_direction": 4 if "aa3004" in replies else None,
        "camera_health": "healthy" if "aa3201" in replies else "incompatible" if "aa3202" in replies else "unknown",
    }
    client.disconnect.assert_not_awaited()
    for prefix in ("aa30ff", "aa32ff"):
        c._notify_callback(None, bytearray(frame(prefix)))
    assert c.installation_direction is None and c.camera_health == "unknown"
    revisions = dict(c._field_revisions)
    c._notify_callback(None, bytearray(frame("333004")))
    assert c._field_revisions == revisions
    c._clear_client_state(client)
    assert c.installation_direction is None and c.camera_health == "unknown"


@pytest.mark.parametrize("reply", [True, False])
async def test_concrete_direction_write_requires_fresh_readback(hass, monkeypatch, reply):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6099", configuration_url="test")
    c.installation_direction = 4
    client = SimpleNamespace(is_connected=True, write_gatt_char=AsyncMock(), disconnect=AsyncMock())
    c._client = client
    monkeypatch.setattr(c, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(c, "_renew_foreground_lease", lambda: None)
    refresh = c.refresh_state

    async def immediate_refresh(**kwargs):
        return await refresh(**kwargs, timeout=0.01)

    monkeypatch.setattr(c, "refresh_state", immediate_refresh)

    async def respond(_uuid, packet, **kwargs):
        if packet[0] == 0x33:
            assert c.installation_direction == 4 and not c._field_revisions
        elif reply and packet == frame("aa30"):
            c._notify_callback(None, bytearray(frame("aa3004")))

    client.write_gatt_char.side_effect = respond
    entity = SimpleNamespace(coordinator=c, _async_supersede_preview=AsyncMock())
    call = ServiceCall(hass, DOMAIN, "set_installation_direction", {"value": 4})
    if reply:
        await async_set_installation_direction(entity, call)
    else:
        with pytest.raises(HomeAssistantError) as exc:
            await async_set_installation_direction(entity, call)
        assert exc.value.translation_domain == DOMAIN
        assert exc.value.translation_key == "device_command_failed"
    assert [call.args[1] for call in client.write_gatt_char.await_args_list if call.args[1][0] == 0x33] == [
        frame("333004")
    ]
    assert c.control_write_attempts == 1 and not c.is_on and c.video_mode == "off"


async def test_queued_read_does_not_claim_external_replies(hass, monkeypatch):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6099", configuration_url="test")
    client = SimpleNamespace(is_connected=True, write_gatt_char=AsyncMock(), disconnect=AsyncMock())
    c._client = client
    monkeypatch.setattr(c, "_ensure_connected", AsyncMock(return_value=client))
    refresh = c.refresh_state

    async def immediate_refresh(**kwargs):
        return await refresh(**kwargs, timeout=0.01)

    monkeypatch.setattr(c, "refresh_state", immediate_refresh)
    async with c._control_arbiter.hold(ControlIntent.USER):
        read = asyncio.create_task(async_read_h6099_controls(c))
        await asyncio.sleep(0)
        assert not read.done() and c._control_arbiter._waiters
        client.write_gatt_char.assert_not_awaited()
        for prefix in ("aa3004", "aa3201"):
            c._notify_callback(None, bytearray(frame(prefix)))
        assert c.installation_direction == 4 and c.camera_health == "healthy"
    assert await read == {"installation_direction": None, "camera_health": "unknown"}
    packets = [call.args[1] for call in client.write_gatt_char.await_args_list]
    assert frame("aa30") in packets and frame("aa32") in packets
