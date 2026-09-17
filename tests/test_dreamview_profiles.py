"""Synthetic exact profiles prove reuse, not compatibility with real products."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.core import ServiceCall
from homeassistant.exceptions import ServiceValidationError

from custom_components.ha_govee_led_ble.const import DOMAIN, MODEL_PROFILES, ModelProfile, ReadDomain, get_profile
from custom_components.ha_govee_led_ble.dreamview import (
    DREAMVIEW_READ_SETTINGS,
    build_dreamview_command,
    build_dreamview_group,
    build_dreamview_query,
)
from custom_components.ha_govee_led_ble.dreamview_services import _async_dreamview_service
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    _STATUS_ROOTS,
    H6199StatusReply,
    build_brightness,
    build_power,
)
from custom_components.ha_govee_led_ble.transport import reassemble_a3
from tests.test_govee_encryption import client as ble_client
from tests.test_h6099_dreamview import coordinator, frame, member


@pytest.fixture
def profiles(monkeypatch):
    monkeypatch.setitem(_STATUS_ROOTS, "dreamview-test-status", ("dreamview-test-status", H6199StatusReply))
    for model, capacity in (("H9901", 2), ("H9902", 9)):
        monkeypatch.setitem(
            MODEL_PROFILES,
            model,
            ModelProfile(
                "Synthetic DreamView",
                command_grammar="H6199",
                command_operations=frozenset({"power"}),
                status_grammar="dreamview-test-status",
                read_domains=frozenset({ReadDomain.POWER}),
                dreamview_grammar="H6099",
                dreamview_operations=frozenset({"replace_group", "member_brightness", "member_connect"}),
                dreamview_reads=frozenset({"member_brightness", "member_connect", "sample"}),
                dreamview_max_sub_devices=capacity,
            ),
        )


@pytest.mark.parametrize("model", ["H9901", "H9902"])
async def test_capacity_service_and_restricted_physical_writer(hass, profiles, model):
    c = coordinator(hass, model)
    client = ble_client()
    c._client = client
    c._ensure_connected = AsyncMock(return_value=client)
    c._renew_foreground_lease = Mock()
    entity = SimpleNamespace(coordinator=c, _async_supersede_preview=AsyncMock())
    capacity = c.profile.dreamview_max_sub_devices
    members = [member(address=f"00:00:00:00:00:{i:02x}").as_dict() for i in range(capacity)]

    async def service(name, data):
        return await _async_dreamview_service(entity, ServiceCall(hass, DOMAIN, name, data), name=name)

    await service("replace_dreamview_group", {"members": members})
    packets = [call.args[1] for call in client.write_gatt_char.await_args_list]
    assert reassemble_a3(packets)[3] == capacity
    assert (await c._dreamview_store.async_load())["members"] == members
    await service("set_dreamview_member_brightness", {"index": capacity - 1, "level": 42})
    assert client.write_gatt_char.call_args.args[1] == frame(f"3360032a{capacity - 1:02x}")
    await service("set_dreamview_member_connect", {"index": capacity - 1, "connected": True})
    assert client.write_gatt_char.call_args.args[1] == frame(f"336005{capacity - 1:02x}01")
    await c._async_write_packet(client, build_power(True, model))
    with pytest.raises(ValueError):
        await c._async_write_packet(client, build_brightness(50, model))

    entity._async_supersede_preview.reset_mock()
    client.write_gatt_char.reset_mock()
    c._dreamview_store.async_save = AsyncMock()
    before = c._control_arbiter.preview_generation
    for name, data in (
        ("replace_dreamview_group", {"members": [*members, member().as_dict()]}),
        ("set_dreamview_member_brightness", {"index": capacity, "level": 42}),
        ("set_dreamview_member_connect", {"index": capacity, "connected": True}),
        ("set_dreamview_switch", {"enabled": True}),
        ("delete_dreamview_group", {}),
    ):
        with pytest.raises(ServiceValidationError):
            await service(name, data)
    entity._async_supersede_preview.assert_not_awaited()
    client.write_gatt_char.assert_not_awaited()
    c._dreamview_store.async_save.assert_not_awaited()
    assert c._control_arbiter.preview_generation == before


@pytest.mark.parametrize("basic_reads", [True, False])
async def test_partial_reads_connect_and_route_independently(hass, profiles, monkeypatch, basic_reads):
    profile = replace(
        get_profile("H9901"),
        dreamview_operations=frozenset(),
        dreamview_max_sub_devices=0,
        read_domains=frozenset({ReadDomain.POWER}) if basic_reads else frozenset(),
    )
    monkeypatch.setitem(MODEL_PROFILES, "H9901", profile)
    c = coordinator(hass, "H9901")
    client = ble_client()
    c._reset_disconnect_timer = Mock()
    c._start_keep_alive = Mock()
    with patch("custom_components.ha_govee_led_ble.coordinator.async_establish_ble_connection", return_value=client):
        await c._ensure_connected()
    client.start_notify.assert_awaited_once()
    receive = client.start_notify.call_args.args[1]

    async def transmit(_uuid, packet, **kwargs):
        if packet == build_dreamview_query("member_brightness", profile):
            receive(None, bytearray(frame("aa600301")))
        if packet == build_dreamview_query("member_connect", profile):
            receive(None, bytearray(frame("aa600501")))
        receive(None, bytearray(frame("aa600901")))  # Undeclared read must not become an observation.

    client.write_gatt_char.side_effect = transmit
    client.write_gatt_char.reset_mock()
    result = await c.async_read_dreamview_state(timeout=0)
    assert {call.args[1] for call in client.write_gatt_char.await_args_list} == {
        build_dreamview_query(setting, profile) for setting in profile.dreamview_reads
    }
    assert len(result["observed"]["member_brightness"]["brightness_bytes"]) == 16
    assert len(result["observed"]["member_connect"]["connection_bytes"]) == 10
    assert set(result["observed"]) == {"member_brightness", "member_connect"}
    assert result["missing_reads"] == ["sample"]
    assert result["unsupported_reads"] == sorted(set(DREAMVIEW_READ_SETTINGS) - profile.dreamview_reads)
    assert result["authored"] is None and not result["membership_confirmed"]
    assert result["slot_identities"] == "unknown"
    if basic_reads:
        receive(None, bytearray(frame("aa0101")))
        assert c.is_on


@pytest.mark.parametrize("operation", ["replace", "index", "write", "read"])
@pytest.mark.parametrize("change_at", ["connect", "transform"])
async def test_effective_profile_rechecked_before_physical_attempt(hass, profiles, operation, change_at):
    c = coordinator(hass, "H9902")
    client = ble_client()
    c._client = client
    c._renew_foreground_lease = Mock()
    c._ensure_connected = AsyncMock(return_value=client)
    original = c.profile
    reduced = (
        replace(original, dreamview_max_sub_devices=1)
        if operation in {"replace", "index"}
        else replace(original, dreamview_operations=frozenset(), dreamview_reads=frozenset())
    )

    async def connect():
        c.profile = reduced
        return client

    def transform(packet):
        c.profile = reduced
        return packet

    if change_at == "connect":
        c._ensure_connected.side_effect = connect
    else:
        c.profile = replace(original, outbound_transform=transform)
    with pytest.raises(ValueError):
        if operation == "replace":
            await c.async_replace_dreamview_group((member(), member(address=None, name="lamp")))
        elif operation in {"index", "write"}:
            await c.async_set_dreamview("member_brightness", {"index": 1, "level": 42})
        else:
            await c.async_read_dreamview_state(timeout=0)
    client.write_gatt_char.assert_not_awaited()

    if operation != "read":
        assert c._dreamview_last_write == "not_attempted"


async def test_empty_declarations_and_capacity_independent_settings(hass, profiles):
    c = coordinator(hass, "H9901")
    c.profile = replace(c.profile, dreamview_operations=frozenset(), dreamview_reads=frozenset())
    c.async_write_effect_sequence = AsyncMock()
    with pytest.raises(ValueError):
        build_dreamview_group((member(),), c.profile)
    with pytest.raises(ValueError):
        await c.async_read_dreamview_state(timeout=0)
    c.async_write_effect_sequence.assert_not_awaited()
    for setting, values in (
        ("switch_group", {"enabled": True}),
        ("same_brightness", {"enabled": True}),
        ("saturation", {"saturation": 50}),
        ("sample", {"sample_first": 1, "sample_second": 2}),
        ("sound", {"enabled": True, "softness": 50}),
        ("delete_group", {}),
    ):
        with pytest.raises(ValueError):
            build_dreamview_command(setting, values, c.profile)
        profile = replace(c.profile, dreamview_operations=frozenset({setting}), dreamview_max_sub_devices=0)
        assert build_dreamview_command(setting, values, profile) == build_dreamview_command(
            setting, values, get_profile("H6099")
        )


async def test_h6099_service_still_rejects_eighth_slot_before_preview(hass):
    c = coordinator(hass)
    entity = SimpleNamespace(coordinator=c, _async_supersede_preview=AsyncMock())
    with pytest.raises(ServiceValidationError):
        await _async_dreamview_service(
            entity,
            ServiceCall(hass, DOMAIN, "set_dreamview_member_brightness", {"index": 7, "level": 50}),
            name="set_dreamview_member_brightness",
        )
    entity._async_supersede_preview.assert_not_awaited()
