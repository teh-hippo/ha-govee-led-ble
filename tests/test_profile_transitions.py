"""Profile changes invalidate batches and control completion, not accepted power."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.ha_govee_led_ble.const import H6199_PACT1_PROFILE
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_brightness_query,
    build_firmware_query,
    build_hardware_query,
    build_power,
    build_power_query,
    build_white_balance_query,
)
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from tests.test_h6199_capabilities import QUALIFIED
from tests.test_h6199_capabilities import lifecycle as transition_lifecycle  # noqa: F401
from tests.test_h6199_native_controls import frame
from tests.test_h6199_pact1 import advertise


@pytest.fixture
def device(hass, monkeypatch):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url=None)
    vars(c).update(QUALIFIED)
    c._present = True
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(), disconnect=AsyncMock())
    c._client = client
    monkeypatch.setattr(c, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(c, "_renew_foreground_lease", lambda: None)
    return c, client


async def test_setup_rebuilds_after_narrowing_during_power_query(device):
    c, client = device

    async def write(_uuid, packet, **kwargs):
        assert packet == build_power_query(c.model)
        advertise(c, 1)
        c._notify_callback(None, bytearray(frame("aa0101")))

    client.write_gatt_char.side_effect = write
    await c._async_update_data()
    assert c.profile is H6199_PACT1_PROFILE and c.is_on and c.available
    assert client.write_gatt_char.await_count == 2
    assert c._client is client and not c._lock.locked() and not c._control_arbiter.locked()


async def test_setup_transition_retry_is_bounded(device):
    c, client = device

    async def write(_uuid, packet, **kwargs):
        assert packet == build_power_query(c.model)
        advertise(c, 2 if c.profile is H6199_PACT1_PROFILE else 1)
        c._notify_callback(None, bytearray(frame("aa0101")))

    client.write_gatt_char.side_effect = write
    with pytest.raises(UpdateFailed):
        await c._async_update_data()
    assert client.write_gatt_char.await_count == 2
    assert c._client is None and client.disconnect.await_count == 1


async def test_identity_batch_rebuilds_with_real_setup(transition_lifecycle):  # noqa: F811
    c, replies, clients, packets = transition_lifecycle
    original = c._async_write_packet
    changed = False

    async def write(client, packet, **kwargs):
        nonlocal changed
        await original(client, packet, **kwargs)
        if packet == build_hardware_query(c.model) and not changed:
            advertise(c, 1)
            changed = True

    c._async_write_packet = write
    await c._async_update_data()
    assert c.is_on and c.available and c.profile is H6199_PACT1_PROFILE
    assert set(packets) == {build_power_query(c.model), build_hardware_query(c.model), build_firmware_query(c.model)}
    assert len(clients) == 1 and c._client is None


@pytest.mark.parametrize("roundtrip", [False, True])
@pytest.mark.parametrize("operation", ["scene", "brightness", "power"])
async def test_transition_during_awaited_control_does_not_reinstall_state(device, roundtrip, operation):
    c, client = device
    c.is_on = True
    c.brightness_pct = 20
    light = GoveeBLELight(c)
    started, finish = asyncio.Event(), asyncio.Event()

    async def write(_uuid, packet, **kwargs):
        started.set()
        await finish.wait()

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(
        c.async_apply_native_scene("forest", verify=False)
        if operation == "scene"
        else light._async_turn_on(brightness=128)
        if operation == "brightness"
        else c.send_command(build_power(False, c.model))
    )
    await started.wait()
    advertise(c, 1)
    c._notify_callback(None, bytearray(frame("aa0100")))
    if roundtrip:
        advertise(c, 2)
    finish.set()
    with pytest.raises(
        HomeAssistantError if operation == "brightness" else ValueError,
        match=None if operation == "brightness" else "profile changed",
    ):
        await task
    assert not c.is_on  # Accepted power must survive the failed control transaction.
    assert c.brightness_pct == 100 and c.effect is None and c.scene_code is None
    assert c.color_mode is None
    assert client.write_gatt_char.await_count == 1
    assert not c._lock.locked() and not c._control_arbiter.locked()


@pytest.mark.parametrize("failure", ["optional", "required", "disconnect", "value"])
async def test_keepalive_uses_basic_required_policy(device, monkeypatch, failure):
    c, client = device
    c._keep_alive_ticks = 2
    ticks = 0

    async def tick(_delay):
        nonlocal ticks
        ticks += 1
        if ticks > 1:
            raise asyncio.CancelledError

    async def write(_uuid, packet, **kwargs):
        if packet == build_power_query(c.model):
            c._notify_callback(None, bytearray(frame("aa0101")))
        bad = build_brightness_query(c.model) if failure == "required" else build_white_balance_query(c.model)
        if packet == bad:
            if failure == "disconnect":
                client.is_connected = False
            raise ValueError("unexpected failure") if failure == "value" else BleakError("query failed")

    monkeypatch.setattr("custom_components.ha_govee_led_ble.coordinator.asyncio.sleep", tick)
    client.write_gatt_char.side_effect = write
    try:
        if failure == "value":
            with pytest.raises(ValueError, match="unexpected"):
                await c._keep_alive_loop()
        else:
            await c._keep_alive_loop()
            assert (c._client is None) is (failure in {"required", "disconnect"})
    finally:
        monkeypatch.undo()
    if failure == "optional":
        assert c._client is client and c.is_on and ticks == 2
    assert not c._lock.locked() and not c._control_arbiter.locked()


async def test_targeted_register_remains_strict(device):
    c, client = device
    client.write_gatt_char.side_effect = BleakError("white balance failed")
    assert not await c.refresh_state(refresh_display_settings=frozenset({"white_balance"}))
    assert client.write_gatt_char.await_count == 1 and c._client is None


async def test_refresh_transition_never_confirms_old_expectation(device):
    c, client = device

    async def write(_uuid, packet, **kwargs):
        assert packet == build_brightness_query(c.model)
        c._notify_callback(None, bytearray(frame("aa0432")))
        advertise(c, 1)

    client.write_gatt_char.side_effect = write
    assert not await c.refresh_state(expected_brightness=50)
    assert c.brightness_pct == 100 and c._client is client
