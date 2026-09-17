"""Optional queries cannot invalidate basic state or historical segment siblings."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.ha_govee_led_ble.const import ReadDomain
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_blank_screen_query,
    build_brightness_query,
    build_camera_health_query,
    build_colour_mode_query,
    build_h6199_control_query,
    build_installation_direction_query,
    build_power_query,
    build_relative_brightness_query,
    build_segment_query,
    build_white_balance_query,
)
from tests.test_h6199_capabilities import QUALIFIED
from tests.test_h6199_native_controls import frame


@pytest.fixture
def device(hass, monkeypatch):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url=None)
    vars(c).update(QUALIFIED)
    c._present = True
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(), disconnect=AsyncMock())
    c._client = client
    monkeypatch.setattr(c, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(c, "_renew_foreground_lease", lambda: None)
    refresh = c.refresh_state

    async def short_refresh(**kwargs):
        return await refresh(**{"timeout": 0.05, **kwargs})

    monkeypatch.setattr(c, "refresh_state", short_refresh)
    return c, client


@pytest.mark.parametrize("query", ["segment", "white_balance", "native", "power"])
@pytest.mark.parametrize("failure", ["bleak", "disconnect", "value", "timeout"])
async def test_query_errors_respect_required_domains(device, query, failure):
    c, client = device
    bad = {
        "segment": build_segment_query(1, c.model),
        "white_balance": build_white_balance_query(c.model),
        "native": build_h6199_control_query("strip_direction"),
        "power": build_power_query(c.model),
    }[query]
    replies = {
        build_power_query(c.model): frame("aa0101"),
        build_brightness_query(c.model): frame("aa0432"),
        build_colour_mode_query(c.model): frame("aa051500"),
    }

    async def write(_uuid, packet, **kwargs):
        if packet in replies:
            c._notify_callback(None, bytearray(replies[packet]))
        if packet == bad:
            if failure == "disconnect":
                client.is_connected = False
            raise {"value": ValueError, "timeout": TimeoutError}.get(failure, BleakError)("query failed")

    client.write_gatt_char.side_effect = write
    if failure in {"value", "timeout"}:
        with pytest.raises(ValueError if failure == "value" else TimeoutError):
            await c._async_update_data()
    elif query == "power" or failure == "disconnect":
        with pytest.raises(UpdateFailed):
            await c._async_update_data()
        assert c._client is None
    else:
        await c._async_update_data()
        assert c.is_on and c.available
        client.disconnect.assert_not_awaited()


@pytest.mark.parametrize("target", ["power", "white_balance", "segments"])
async def test_targeted_queries_do_not_send_native_registers(device, target):
    c, client = device
    c.camera_status = "healthy"
    await c._send_state_queries(
        query_power=target == "power",
        query_brightness=False,
        query_color_mode=False,
        query_white_balance=target == "white_balance",
        query_segments=target == "segments",
    )
    expected = {
        "power": [build_power_query(c.model)],
        "white_balance": [build_white_balance_query(c.model)],
        "segments": [build_segment_query(g, c.model) for g in range(1, c._segment_group_count + 1)],
    }[target]
    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == expected
    assert c.camera_status == "healthy"


@pytest.mark.parametrize("disconnect", [False, True])
async def test_setup_collects_delayed_optional_registers(device, disconnect):
    c, client = device
    timers = []
    replies = {
        build_power_query(c.model): frame("aa0101"),
        build_brightness_query(c.model): frame("aa0432"),
        build_colour_mode_query(c.model): frame("aa051500"),
    }
    optional = {
        build_white_balance_query(c.model): frame("aaa90006011003001505"),
        build_blank_screen_query(c.model): frame("aaa90a0601020a007800"),
        build_relative_brightness_query(c.model): frame("aaae0104141e2832"),
        build_h6199_control_query("camera_status"): frame("aa3201"),
    }

    async def write(_uuid, packet, **kwargs):
        if packet in replies:
            c._notify_callback(None, bytearray(replies[packet]))
        if packet in optional:
            timers.append(
                asyncio.get_running_loop().call_later(0.02, c._notify_callback, None, bytearray(optional[packet]))
            )
        if disconnect and packet == build_h6199_control_query("camera_status"):
            timers.append(asyncio.get_running_loop().call_later(0.01, setattr, client, "is_connected", False))

    client.write_gatt_char.side_effect = write
    try:
        result = await c.refresh_state(refresh_all=True, required_domains=c.profile.setup_required_read_domains)
        assert result is not disconnect
        assert c.white_balance_flag == 0 and c.white_balance_red == 21
        assert c.blank_screen and c.relative_brightness_bottom == 50 and c.camera_status == "healthy"
    finally:
        for timer in timers:
            timer.cancel()


async def test_explicit_optional_domain_error_is_fatal(device):
    c, client = device
    client.write_gatt_char.side_effect = BleakError("required display query failed")
    assert not await c._send_state_queries(
        query_power=False,
        query_brightness=False,
        query_color_mode=False,
        query_white_balance=True,
        required_domains=frozenset({ReadDomain.DISPLAY_SETTING}),
    )


async def test_older_h6199_setup_ignores_isolated_segment_error(device):
    c, client = device
    c.hw_version, c.fw_version = "1.00.01", "1.07.02"
    c.subordinate_20_version = c.subordinate_21_version = None
    c.pact_type = c.pact_code = None
    replies = {
        build_power_query(c.model): frame("aa0101"),
        build_brightness_query(c.model): frame("aa0432"),
        build_colour_mode_query(c.model): frame("aa051500"),
    }

    async def write(_uuid, packet, **kwargs):
        if packet in replies:
            c._notify_callback(None, bytearray(replies[packet]))
        else:
            assert packet in [build_segment_query(g, c.model) for g in range(1, 5)]
            raise BleakError("unsupported optional query")

    client.write_gatt_char.side_effect = write
    await c._async_update_data()
    assert c.available and c.is_on
    client.disconnect.assert_not_awaited()


async def test_only_successfully_sent_fields_are_collected(device):
    c, client = device
    client.write_gatt_char.side_effect = BleakError("optional register failed")
    baselines = {}
    assert await c._send_state_queries(
        query_power=False,
        query_brightness=False,
        query_color_mode=False,
        query_white_balance=True,
        required_domains=frozenset(),
        optional_baselines=baselines,
    )
    assert baselines == {}


async def test_h6099_targeted_queries_and_optional_collection(hass, monkeypatch):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6099", configuration_url=None)
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    c._client = client
    monkeypatch.setattr(c, "_ensure_connected", AsyncMock(return_value=client))
    await c._send_state_queries(query_power=True, query_brightness=False, query_color_mode=False)
    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == [build_power_query(c.model)]
    replies = {
        build_power_query(c.model): frame("aa0101"),
        build_brightness_query(c.model): frame("aa0432"),
        build_colour_mode_query(c.model): frame("aa0515010000"),
    }
    delayed = {
        build_white_balance_query(c.model): frame("aaa9060132"),
        build_camera_health_query(c.model): frame("aa3201"),
        build_installation_direction_query(c.model): frame("aa3003"),
    }
    timers = []

    async def write(_uuid, packet, **kwargs):
        if packet in replies:
            c._notify_callback(None, bytearray(replies[packet]))
        if packet in delayed:
            timers.append(
                asyncio.get_running_loop().call_later(0.01, c._notify_callback, None, bytearray(delayed[packet]))
            )

    client.write_gatt_char.side_effect = write
    try:
        assert await c.refresh_state(
            refresh_all=True,
            required_domains=c.profile.setup_required_read_domains,
            timeout=0.03,
        )
        assert c.white_balance_scalar == 50 and c.installation_direction == 3 and c.camera_health == "healthy"
    finally:
        for timer in timers:
            timer.cancel()


@pytest.mark.parametrize("model", ["H6199", "H6099", "H617A"])
@pytest.mark.parametrize("operation", ["paint", "brightness"])
@pytest.mark.parametrize("fresh", [False, True])
async def test_segment_siblings_need_transaction_observation(hass, monkeypatch, model, operation, fresh):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", model, configuration_url=None)
    count, size = c.profile.segment_count, c.profile.segment_group_size

    def pages(colors, brightness):
        return {
            build_segment_query(group, model): frame(
                "aaa5"
                + bytes(
                    [
                        group,
                        *(
                            value
                            for index in range((group - 1) * size, min(group * size, count))
                            for value in (brightness[index], *colors[index])
                        ),
                    ]
                ).hex()
            )
            for group in range(1, c._segment_group_count + 1)
        }

    old = pages([(10, 20, 30)] * count, [100] * count)
    for reply in old.values():
        c._notify_callback(None, bytearray(reply))
    await c.disconnect()
    colors, brightness = [(9, 8, 7)] * count, [40] * count
    if operation == "paint":
        colors[0] = (255, 0, 0)
    else:
        brightness[0] = 60
    replies = pages(colors, brightness)

    async def write(_uuid, packet, **kwargs):
        if packet in replies:
            c._notify_callback(None, bytearray(replies[packet]))

    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=write))
    c._client = client

    async def connect():
        if fresh and client.write_gatt_char.await_count == 0:
            for reply in old.values():
                c._notify_callback(None, bytearray(reply))
        return client

    monkeypatch.setattr(c, "_ensure_connected", connect)
    monkeypatch.setattr(c, "_renew_foreground_lease", lambda: None)
    apply = (
        c.async_paint_segments([([1], (255, 0, 0))])
        if operation == "paint"
        else c.async_set_segment_brightness([1], 60)
    )
    if fresh:
        with pytest.raises(RuntimeError, match="confirm segment"):
            await apply
    else:
        await apply
    assert c.segment_colors == colors and c.segment_brightness == brightness
    assert c.segment_state_source == "observed"
