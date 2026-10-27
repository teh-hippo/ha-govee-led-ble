"""Synthetic low-blue-light setting frames, not hardware confirmation."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ha_govee_led_ble.const import ReadDomain, device_profile, get_profile
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.generated_protocol_adapter import require_profile_packet
from custom_components.ha_govee_led_ble.low_blue_light import (
    LowBlueLightState,
    build_query,
    build_setting,
    parse_setting,
    setting_state,
)
from custom_components.ha_govee_led_ble.number import GoveeBLELowBlueLightLevel
from custom_components.ha_govee_led_ble.switch import GoveeBLEControlSwitch
from custom_components.ha_govee_led_ble.transport import xor_checksum


def frame(prefix: str) -> bytes:
    body = bytes.fromhex(prefix).ljust(19, b"\0")
    return body + bytes((xor_checksum(body),))


@pytest.fixture
def profile():
    return replace(
        get_profile("H617A"),
        setting_grammar="H6072",
        supports_low_blue_light=True,
        profile_identity_fields=frozenset({"fw_version", "hw_version"}),
        read_domains=get_profile("H617A").read_domains | {ReadDomain.LOW_BLUE_LIGHT},
    )


@pytest.fixture
def coordinator(hass, monkeypatch, profile):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H617A", configuration_url=None)
    c.profile = profile
    c._confirmed_identity_fields.add("fw_version")
    c._client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(), start_notify=AsyncMock())
    c._notification_token = object()
    monkeypatch.setattr(c, "_ensure_connected", AsyncMock(return_value=c._client))
    monkeypatch.setattr(c, "_renew_foreground_lease", lambda: None)
    return c


def test_setting_direct_bytes_bounds_and_profile_admission(profile):
    state = LowBlueLightState(True, 37, 86, 20)
    write = build_setting(state, profile)
    assert write == frame("33ba0101255614")
    assert build_query(profile) == frame("aaba01")
    for level in (20, 100):
        require_profile_packet(build_setting(replace(state, level=level), profile), profile)
    for level in (19, 101, True, 20.0):
        with pytest.raises(ValueError):
            build_setting(replace(state, level=level), profile)
    for packet in (write, build_query(profile)):
        require_profile_packet(packet, profile)
        with pytest.raises(ValueError):
            require_profile_packet(packet, replace(profile, supports_low_blue_light=False))
    parsed = parse_setting(frame("aaba0101255614"), profile).parsed
    assert setting_state(parsed) == state
    assert parse_setting(frame("aaba0101255614")[:-1], profile).parsed is None


@pytest.mark.parametrize("prefix", ["33ba0201646464", "33ba0102646464", "33ba0101646413", "aaba02", "aaba0101"])
def test_invalid_setting_packets_cannot_fall_back_to_generic_opaque_commands(profile, prefix):
    with pytest.raises(ValueError):
        require_profile_packet(frame(prefix), profile)


@pytest.mark.parametrize("body", ["0201255614", "0102255614", "0101255613", "0101255665"])
def test_unknown_setting_never_becomes_supported(coordinator, body):
    coordinator.low_blue_light = LowBlueLightState(True, 37, 86, 20)
    coordinator._notify_callback(None, bytearray(frame("aaba" + body)))
    assert coordinator.low_blue_light is None
    assert coordinator._field_revisions["low_blue_light"] == 1
    assert setting_state(parse_setting(frame("aaba" + body), coordinator.profile).parsed) is None


@pytest.mark.parametrize("change", [{"enabled": True}, {"level": 20}])
async def test_partial_change_preserves_fresh_sibling_fields(coordinator, change):
    c = coordinator
    before = LowBlueLightState(False, 37, 86, 80)
    expected = replace(before, **change)
    query = build_query(c.profile)
    write = build_setting(expected, c.profile)
    queries = 0

    async def respond(_uuid, packet, **kwargs):
        nonlocal queries
        if packet == query:
            queries += 1
            state = before if queries == 1 else expected
            c._notify_callback(
                None,
                bytearray(
                    frame(f"aaba01{int(state.enabled):02x}{state.sibling_1:02x}{state.sibling_2:02x}{state.level:02x}")
                ),
            )
        else:
            assert c.low_blue_light == before

    c._client.write_gatt_char.side_effect = respond
    await c.async_set_low_blue_light(**change)
    assert [call.args[1] for call in c._client.write_gatt_char.await_args_list] == [query, write, query]
    assert c.low_blue_light == expected


@pytest.mark.parametrize("reply", ["missing", "unknown", "mismatched_level", "mismatched_sibling"])
async def test_missing_or_unmatched_readback_does_not_confirm(coordinator, monkeypatch, reply):
    c = coordinator
    query = build_query(c.profile)
    queries = 0

    async def respond(_uuid, packet, **kwargs):
        nonlocal queries
        if packet == query:
            queries += 1
            body = "0100255650"
            if queries == 2:
                body = {
                    "missing": None,
                    "unknown": "0201255650",
                    "mismatched_level": "0101255651",
                    "mismatched_sibling": "0101265650",
                }[reply]
            if body is not None:
                c._notify_callback(None, bytearray(frame("aaba" + body)))

    c._client.write_gatt_char.side_effect = respond
    if reply == "missing":
        monkeypatch.setattr(c, "_wait_for_revisions", AsyncMock(side_effect=[True, False]))
        monkeypatch.setattr(c, "_disconnect_if_current_locked", AsyncMock())
    with pytest.raises(ValueError, match="(fresh|unknown|confirm)"):
        await c.async_set_low_blue_light(enabled=True)
    assert c.low_blue_light != LowBlueLightState(True, 37, 86, 80)


async def test_stale_cached_state_cannot_supply_siblings(coordinator, monkeypatch):
    c = coordinator
    client = c._client
    c.low_blue_light = LowBlueLightState(False, 100, 100, 100)
    monkeypatch.setattr(c, "_wait_for_revisions", AsyncMock(return_value=False))
    monkeypatch.setattr(c, "_disconnect_if_current_locked", AsyncMock())
    with pytest.raises(ValueError, match="fresh"):
        await c.async_set_low_blue_light(enabled=True)
    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == [build_query(c.profile)]
    c._disconnect_if_current_locked.assert_awaited_once_with(client)


@pytest.mark.parametrize(
    "values", [{}, {"enabled": 1}, {"level": True}, {"level": 19}, {"level": 101}, {"level": 20.5}]
)
async def test_invalid_requests_have_no_control_side_effects(coordinator, monkeypatch, values):
    supersede = AsyncMock()
    monkeypatch.setattr(coordinator, "_async_supersede_effect_preview", supersede)
    with pytest.raises(ValueError):
        await coordinator.async_set_low_blue_light(**values)
    supersede.assert_not_awaited()
    coordinator._client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("change", ["subscription", "firmware", "profile"])
async def test_identity_changes_during_preflight_cannot_reach_a_setting_write(coordinator, monkeypatch, change):
    c = coordinator
    query = build_query(c.profile)
    client = c._client
    monkeypatch.setattr(c, "_disconnect_if_current_locked", AsyncMock())

    async def respond(_uuid, packet, **kwargs):
        assert packet == query
        c._notify_callback(None, bytearray(frame("aaba0100255650")))
        if change == "subscription":
            c._notification_token = object()
        elif change == "firmware":
            c._confirmed_identity_fields.clear()
        else:
            c.profile = replace(c.profile, supports_low_blue_light=False)

    client.write_gatt_char.side_effect = respond
    with pytest.raises(ValueError):
        await c.async_set_low_blue_light(enabled=True)
    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == [query]


async def test_fresh_firmware_and_subscription_required_at_physical_boundary(coordinator):
    c = coordinator
    query = build_query(c.profile)
    await c._async_write_packet(c._client, query)
    c._confirmed_identity_fields.clear()
    with pytest.raises(ValueError, match="firmware"):
        await c._async_write_packet(c._client, query)
    c._notify_callback(None, bytearray(frame("aaba0101646464")))
    assert c.low_blue_light is None
    c._confirmed_identity_fields.add("fw_version")
    await c._start_notify()
    previous_receive = c._client.start_notify.await_args.args[1]
    await c._start_notify()
    previous_receive(None, bytearray(frame("aaba0101646464")))
    assert c.low_blue_light is None
    c._client.start_notify.await_args.args[1](None, bytearray(frame("aaba0101646464")))
    assert c.low_blue_light == LowBlueLightState(True, 100, 100, 100)
    c._clear_client_state(c._client)
    assert c.low_blue_light is None


async def test_firmware_is_rechecked_after_physical_write_hook(coordinator):
    c = coordinator
    packet = build_setting(LowBlueLightState(True, 37, 86, 20), c.profile)
    with pytest.raises(ValueError, match="firmware"):
        await c._async_write_packet(c._client, packet, before_write=c._confirmed_identity_fields.clear)
    c._client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("confirmed", [True, False])
async def test_polling_requires_fresh_firmware_but_not_hardware(coordinator, monkeypatch, confirmed):
    c = coordinator
    c._confirmed_identity_fields = {"fw_version"} if confirmed else set()
    monkeypatch.setattr(c, "refresh_state", AsyncMock(return_value=True))

    async def respond(_client, packet, **kwargs):
        if packet == build_query(c.profile):
            c._notify_callback(None, bytearray(frame("aaba0100255650")))

    write = AsyncMock(side_effect=respond)
    monkeypatch.setattr(c, "_async_write_packet", write)
    await c._async_update_data()
    assert (build_query(c.profile) in [call.args[1] for call in write.await_args_list]) is confirmed


async def test_unanswered_poll_cannot_supply_stale_siblings_to_a_later_setting_change(coordinator, monkeypatch):
    c = coordinator
    c.profile = replace(c.profile, profile_identity_fields=frozenset())
    old_client = c._client
    old_client.disconnect = AsyncMock()
    old_client.stop_notify = AsyncMock()
    await c._start_notify()
    old_receive = old_client.start_notify.await_args.args[1]
    wait = c._wait_for_revisions
    monkeypatch.setattr(c, "_wait_for_revisions", AsyncMock(return_value=False))
    monkeypatch.setattr(c, "refresh_state", AsyncMock(return_value=True))
    await c._async_update_data()
    assert c._client is None
    old_client.disconnect.assert_awaited_once()

    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(), start_notify=AsyncMock())
    c._client = client
    c._ensure_connected.return_value = client
    c._confirmed_identity_fields.add("fw_version")
    await c._start_notify()
    monkeypatch.setattr(c, "_wait_for_revisions", wait)
    query = build_query(c.profile)
    expected = LowBlueLightState(True, 99, 22, 60)
    queries = 0

    async def respond(_uuid, packet, **kwargs):
        nonlocal queries
        if packet == query:
            queries += 1
            old_receive(None, bytearray(frame("aaba0100255650")))
            c._notify_callback(None, bytearray(frame("aaba010063163c" if queries == 1 else "aaba010163163c")))

    client.write_gatt_char.side_effect = respond
    await c.async_set_low_blue_light(enabled=True)
    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == [
        query,
        build_setting(expected, c.profile),
        query,
    ]


def test_native_entities_keep_unknown_state_and_share_coordinator(coordinator):
    entry = SimpleNamespace(runtime_data=coordinator)
    switch = GoveeBLEControlSwitch(entry, "low_blue_light")
    number = GoveeBLELowBlueLightLevel(entry)
    assert switch.is_on is None and number.native_value is None
    coordinator.low_blue_light = LowBlueLightState(False, 37, 86, 80)
    assert switch.is_on is False and number.native_value == 80
    assert number.native_min_value == 20 and number.native_max_value == 100


@pytest.mark.parametrize("firmware,expected", [(None, False), ("2.04.06", False), ("2.04.07", True), ("2.04.10", True)])
@pytest.mark.parametrize("pact", [(None, None), (1, 1), (2, 1)])
@pytest.mark.parametrize("hardware", [None, "0.00.00"])
def test_h6072_effective_profile_firmware_threshold_independent_of_pact_and_hardware(
    firmware, expected, pact, hardware
):
    profile = device_profile("H6072", *pact, firmware=firmware, hardware=hardware)
    assert profile.supports_low_blue_light is expected
