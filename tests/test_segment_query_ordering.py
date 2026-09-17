"""Uncorrelated segment replies must finish before another transaction writes."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError

from custom_components.ha_govee_led_ble import coordinator as coordinator_module
from custom_components.ha_govee_led_ble.control_arbiter import ControlIntent
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_brightness_query,
    build_colour_mode_query,
    build_power_query,
    build_segment_query,
)
from custom_components.ha_govee_led_ble.govee_encryption.session import GoveeEncryptionSession
from custom_components.ha_govee_led_ble.light_commands import build_segment_brightness
from tests.test_coordinator import _packet


@pytest.fixture
async def device(hass, monkeypatch):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H617A", configuration_url=None)
    c.fw_version, c.hw_version = "3.02.24", "3.01.01"
    client = MagicMock(is_connected=True, start_notify=AsyncMock(), disconnect=AsyncMock())
    c._client = client
    await c._start_notify()
    receive = client.start_notify.call_args.args[1]
    monkeypatch.setattr(c, "_renew_foreground_lease", MagicMock())
    yield c, client, receive
    await c.disconnect()


def pages(levels):
    return [
        _packet(0xAA, 0xA5, [group, *(v for i in range((group - 1) * 3, group * 3) for v in (levels[i], i, 96, 160))])
        for group in range(1, 6)
    ]


@pytest.mark.parametrize("producer", ["keepalive", "refresh", "observe", "segments"])
@pytest.mark.parametrize("applied", [True, False])
async def test_old_poll_gates_control_until_all_pages_arrive(device, monkeypatch, producer, applied):
    c, client, receive = device
    levels = [0, 50, 75, 25, 50, 75, 25, 50, 75, 25, 50, 75, 25, 50, 0]
    old_pages = pages(levels)
    for reply in old_pages:
        receive(None, bytearray(reply))
    colors = list(c.segment_colors)
    sent, control_started = asyncio.Event(), asyncio.Event()
    control_writes = []
    query_count = 0
    command = build_segment_brightness([2, 7, 14], 100)
    basic = {
        build_power_query(): _packet(0xAA, 1, [1]),
        build_brightness_query(): _packet(0xAA, 4, [15]),
        build_colour_mode_query(): _packet(0xAA, 5, [0x15]),
    }

    async def write(_uuid, packet, **kwargs):
        nonlocal query_count
        if packet == command:
            control_writes.append(packet)
            if applied:
                for index in (1, 6, 13):
                    levels[index] = 100
        elif packet in basic:
            receive(None, bytearray(basic[packet]))
        else:
            assert packet in [build_segment_query(g) for g in range(1, 6)]
            query_count += 1
            if query_count == 5:
                sent.set()
            elif query_count > 5:
                receive(None, bytearray(pages(levels)[packet[2] - 1]))

    client.write_gatt_char = AsyncMock(side_effect=write)
    # One real keep-alive iteration, then park until test cleanup.
    sleep = asyncio.sleep
    ticks = 0

    async def tick(delay):
        nonlocal ticks
        if delay == 5:
            ticks += 1
            if ticks > 1:
                await asyncio.Event().wait()
        else:
            await sleep(delay)

    monkeypatch.setattr("custom_components.ha_govee_led_ble.coordinator.asyncio.sleep", tick)
    c._keep_alive_ticks = 2
    poll = asyncio.create_task(
        c._keep_alive_loop()
        if producer == "keepalive"
        else c.refresh_state(refresh_all=True)
        if producer == "refresh"
        else c.async_observe_effect({"is_on": True, "brightness_pct": 15, "color_mode": c.color_mode})
        if producer == "observe"
        else c.async_refresh_segments()
    )

    async def control():
        control_started.set()
        await c.async_set_segment_brightness([2, 7, 14], 100)

    task = None
    try:
        await asyncio.wait_for(sent.wait(), 1)
        task = asyncio.create_task(control())
        await control_started.wait()
        await sleep(0)
        assert not control_writes and not task.done()
        revision = c._field_revisions["segment_colors"]
        for reply in old_pages[:4] + old_pages[:1]:  # a duplicate is not page five
            receive(None, bytearray(reply))
        corrupt = bytearray(old_pages[4])
        corrupt[-1] ^= 1
        receive(None, corrupt)
        await sleep(0)
        assert c._field_revisions["segment_colors"] == revision
        assert not control_writes and not task.done()
        receive(None, bytearray(old_pages[4]))
        if applied:
            await asyncio.wait_for(task, 1)
        else:
            with pytest.raises(RuntimeError, match="Failed to confirm segment brightness"):
                await asyncio.wait_for(task, 1)
        assert control_writes == [command] and c.control_write_attempts == 1
        assert query_count == 10
        assert c.segment_colors == colors and c.segment_brightness == levels
        assert c.segment_state_source == "observed"
        assert not c._segment_query_incomplete
    finally:
        for pending in (poll, task):
            if pending is not None:
                pending.cancel()
        await asyncio.gather(*(p for p in (poll, task) if p is not None), return_exceptions=True)


@pytest.mark.parametrize("ending", ["timeout", "cancel", "write_error"])
async def test_abandoned_batch_requires_new_connection_even_after_late_pages(device, monkeypatch, ending):
    c, client, receive = device
    old_pages = pages([50] * 15)
    sent = asyncio.Event()

    async def write(_uuid, packet, **kwargs):
        if packet == build_segment_query(5):
            sent.set()
            if ending == "write_error":
                raise TimeoutError("ambiguous query write")
        else:
            receive(None, bytearray(old_pages[packet[2] - 1]))

    client.write_gatt_char = AsyncMock(side_effect=write)
    task = asyncio.create_task(c.async_refresh_segments(timeout=0.01 if ending == "timeout" else 1))
    await asyncio.wait_for(sent.wait(), 1)
    if ending == "cancel":
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    elif ending == "write_error":
        with pytest.raises(TimeoutError, match="ambiguous"):
            await task
    else:
        assert await task is False
    assert c._segment_query_incomplete
    # A late complete set is not permission to reuse the abandoned connection.
    receive(None, bytearray(old_pages[4]))
    assert c._segment_query_incomplete
    attempts = client.write_gatt_char.await_count
    async with c._control_arbiter.hold(ControlIntent.USER):
        assert not await c._send_state_queries()
    with pytest.raises(BleakError, match="Incomplete segment query"):
        await c.async_preview_write(build_segment_brightness([1], 100))
    assert client.write_gatt_char.await_count == attempts and c.control_write_attempts == 0

    # Exercise the normal reconnect decision, stopping at the connection provider.
    connect = AsyncMock(side_effect=BleakError("offline test boundary"))
    monkeypatch.setattr("custom_components.ha_govee_led_ble.coordinator.async_establish_ble_connection", connect)
    async with c._control_arbiter.hold(ControlIntent.USER):
        async with c._lock:
            with pytest.raises(BleakError, match="offline test boundary"):
                await c._ensure_connected()
    client.disconnect.assert_awaited_once()
    connect.assert_awaited_once()
    assert connect.call_args.kwargs["use_services_cache"] is True
    assert not c.fresh_services_required and not c._segment_query_incomplete
    assert c._segment_query_colors is None and not c._segment_groups_observed
    # The old subscription cannot publish into a replacement connection.
    revision = c._field_revisions["segment_colors"]
    c._client = MagicMock(is_connected=True, disconnect=AsyncMock())
    for reply in pages([100] * 15):
        receive(None, bytearray(reply))
    assert c._field_revisions["segment_colors"] == revision


async def test_optional_segment_timeout_keeps_basic_poll_but_not_connection_reusable(device):
    c, client, receive = device
    c._present = True
    replies = {
        build_power_query(): _packet(0xAA, 1, [1]),
        build_brightness_query(): _packet(0xAA, 4, [15]),
        build_colour_mode_query(): _packet(0xAA, 5, [0x15]),
    }

    async def write(_uuid, packet, **kwargs):
        if packet in replies:
            receive(None, bytearray(replies[packet]))

    client.write_gatt_char = AsyncMock(side_effect=write)
    async with c._control_arbiter.hold(ControlIntent.BACKGROUND):
        assert await c.refresh_state(
            refresh_all=True, required_domains=c.profile.setup_required_read_domains, timeout=0.01
        )
    assert c.is_on and c.brightness_pct == 15 and c.available
    assert c._segment_query_incomplete and c.segment_state_source == "initial"
    assert c._field_revisions.get("segment_colors", 0) == 0
    client.disconnect.assert_not_awaited()
    c._renew_foreground_lease.assert_called_once()
    assert c.control_write_attempts == 0


@pytest.mark.parametrize("producer", ["segments", "refresh", "observe", "background"])
@pytest.mark.parametrize("phase", ["collection", "write", "healthy"])
async def test_one_deadline_rejects_late_pages_even_before_timeout_waiter(device, monkeypatch, producer, phase):
    c, client, receive = device
    start = asyncio.get_running_loop().time()
    clock = [start]
    monkeypatch.setattr(coordinator_module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    basic = {
        build_power_query(): _packet(0xAA, 1, [1]),
        build_brightness_query(): _packet(0xAA, 4, [15]),
        build_colour_mode_query(): _packet(0xAA, 5, [0x15]),
    }
    replies = pages([50] * 15)

    def complete():
        # Model an event-loop stall: callbacks deliver the complete batch before
        # asyncio gets to run its expired timer. No real settling delay is needed.
        clock[0] = start + (0.005 if phase == "healthy" else 0.043)
        for reply in replies:
            receive(None, bytearray(reply))

    async def write(_uuid, packet, **kwargs):
        if packet in basic:
            receive(None, bytearray(basic[packet]))
        elif packet == build_segment_query(5):
            if phase == "write":
                complete()  # synchronous write completion already exceeded the budget
            else:
                asyncio.get_running_loop().call_soon(complete)

    client.write_gatt_char = AsyncMock(side_effect=write)
    if producer == "segments":
        result = await c.async_refresh_segments(timeout=0.01)
    elif producer == "refresh":
        result = await c.refresh_state(refresh_all=True, timeout=0.01)
    elif producer == "observe":
        result = await c.async_observe_effect(
            {"is_on": True, "brightness_pct": 15, "color_mode": coordinator_module.ParsedMode.COLOUR}, timeout=0.01
        )
    else:
        async with c._control_arbiter.hold(ControlIntent.BACKGROUND):
            result = await c._send_state_queries(deadline=start + 0.01)
    # Basic observations were timely even when optional segment collection expires.
    if producer == "segments":
        assert result is (phase == "healthy")
    else:
        assert result is True
    assert c._segment_query_incomplete is (phase != "healthy")
    assert c.control_write_attempts == 0
    assert not c._lock.locked() and not c._control_arbiter.locked()


@pytest.mark.parametrize("producer", ["segments", "refresh", "observe", "background"])
async def test_stalled_segment_query_write_is_bounded_and_releases_locks(device, producer):
    c, client, receive = device
    cancelled = asyncio.Event()
    basic = {
        build_power_query(): _packet(0xAA, 1, [1]),
        build_brightness_query(): _packet(0xAA, 4, [15]),
        build_colour_mode_query(): _packet(0xAA, 5, [0x15]),
    }

    async def write(_uuid, packet, **kwargs):
        if packet in basic:
            receive(None, bytearray(basic[packet]))
        else:
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

    client.write_gatt_char = AsyncMock(side_effect=write)
    async with asyncio.timeout(1):  # watchdog, not a settling delay
        if producer == "segments":
            assert not await c.async_refresh_segments(timeout=0.01)
        elif producer == "refresh":
            assert await c.refresh_state(refresh_all=True, timeout=0.01)
        elif producer == "observe":
            assert (
                await c.async_observe_effect(
                    {"is_on": True, "brightness_pct": 15, "color_mode": coordinator_module.ParsedMode.COLOUR},
                    timeout=0.01,
                )
                is True
            )
        else:
            async with c._control_arbiter.hold(ControlIntent.BACKGROUND):
                assert await c._send_state_queries(deadline=asyncio.get_running_loop().time() + 0.01)
    assert cancelled.is_set() and c._segment_query_incomplete
    assert c.control_write_attempts == 0
    assert not c._lock.locked() and not c._control_arbiter.locked()


async def test_observation_does_not_restart_timeout_after_segment_collection(device, monkeypatch):
    c, client, receive = device
    start = asyncio.get_running_loop().time()
    clock = [start]
    monkeypatch.setattr(coordinator_module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    replies = pages([50] * 15)

    async def write(_uuid, packet, **kwargs):
        if packet == build_brightness_query():
            receive(None, bytearray(_packet(0xAA, 4, [15])))
        elif packet == build_colour_mode_query():
            receive(None, bytearray(_packet(0xAA, 5, [0x15])))
        elif packet == build_segment_query(5):
            clock[0] = start + 0.03
            for reply in replies:
                receive(None, bytearray(reply))

    wait = c._wait_for_revisions
    deadlines = []

    async def wait_with_late_power(fields, domains, deadline, **kwargs):
        deadlines.append(deadline)
        if "is_on" in fields:
            clock[0] = start + 0.05
            receive(None, bytearray(_packet(0xAA, 1, [1])))
        return await wait(fields, domains, deadline, **kwargs)

    monkeypatch.setattr(c, "_wait_for_revisions", wait_with_late_power)
    client.write_gatt_char = AsyncMock(side_effect=write)
    assert (
        await c.async_observe_effect(
            {"is_on": True, "brightness_pct": 15, "color_mode": coordinator_module.ParsedMode.COLOUR}, timeout=0.04
        )
        is None
    )
    assert deadlines == [start + 0.04, start + 0.04]
    assert not c._segment_query_incomplete


@pytest.mark.parametrize("producer", ["refresh", "observe"])
async def test_transmission_time_is_subtracted_from_collection_budget(device, monkeypatch, producer):
    c, client, receive = device
    start = asyncio.get_running_loop().time()
    clock = [start]
    monkeypatch.setattr(coordinator_module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    replies = pages([50] * 15)
    basic = {
        build_power_query(): _packet(0xAA, 1, [1]),
        build_brightness_query(): _packet(0xAA, 4, [15]),
        build_colour_mode_query(): _packet(0xAA, 5, [0x15]),
    }

    async def write(_uuid, packet, **kwargs):
        if packet in basic:
            receive(None, bytearray(basic[packet]))
        elif packet == build_segment_query(5):
            clock[0] = start + 0.03

    wait = c._wait_for_revisions
    deadlines = []

    async def collect(fields, domains, deadline, **kwargs):
        deadlines.append(deadline)
        if "segment_colors" in fields:
            clock[0] = start + 0.05  # beyond original .04, inside a restarted .03+.04
            for reply in replies:
                receive(None, bytearray(reply))
        return await wait(fields, domains, deadline, **kwargs)

    monkeypatch.setattr(c, "_wait_for_revisions", collect)
    client.write_gatt_char = AsyncMock(side_effect=write)
    if producer == "refresh":
        assert await c.refresh_state(refresh_all=True, timeout=0.04)
    else:
        assert await c.async_observe_effect(
            {"is_on": True, "brightness_pct": 15, "color_mode": coordinator_module.ParsedMode.COLOUR}, timeout=0.04
        )
    assert deadlines and all(d == start + 0.04 for d in deadlines)
    assert c._segment_query_incomplete and c.control_write_attempts == 0


@pytest.mark.parametrize("change", ["disconnect", "subscription", "profile"])
async def test_complete_pages_cannot_confirm_changed_connection_or_profile(device, change):
    c, client, receive = device
    sent = asyncio.Event()

    async def write(_uuid, packet, **kwargs):
        if packet == build_segment_query(5):
            sent.set()

    client.write_gatt_char = AsyncMock(side_effect=write)
    task = asyncio.create_task(c.async_refresh_segments(timeout=0.02))
    await asyncio.wait_for(sent.wait(), 1)
    for reply in pages([50] * 15):
        receive(None, bytearray(reply))
    if change == "disconnect":
        c._disconnected_callback(client)
    elif change == "subscription":
        c._notification_token = object()
    else:
        c._profile_generation += 1
    assert await task is False
    assert not c._control_arbiter.locked() and not c._lock.locked()
    assert c.control_write_attempts == 0


@pytest.mark.parametrize("external_cancel", [False, True])
async def test_plaintext_query_cancellation_bounds_stalled_disconnect(device, external_cancel):
    c, client, receive = device
    session = c._encryption = GoveeEncryptionSession()
    client.services = []
    await session.async_select(client, advertised=False)
    assert session.ready and session.version == 0
    writing, disconnecting, disconnected = asyncio.Event(), asyncio.Event(), asyncio.Event()
    revision = c._field_revisions.get("segment_colors", 0)

    async def write(*args, **kwargs):
        writing.set()
        await asyncio.Event().wait()

    async def disconnect():
        disconnecting.set()
        # Invalidation must precede the first potentially stalled cleanup await.
        assert c._notification_token is None
        assert not session.ready and session._key is session._client_iv is session._device_iv is None
        for reply in pages([50] * 15):
            receive(None, bytearray(reply))
        assert c._field_revisions.get("segment_colors", 0) == revision
        try:
            await asyncio.Event().wait()
        finally:
            disconnected.set()

    client.write_gatt_char = AsyncMock(side_effect=write)
    client.disconnect.side_effect = disconnect
    task = asyncio.create_task(c.async_refresh_segments(timeout=0.005))
    try:
        await asyncio.wait_for(writing.wait(), 1)
        if external_cancel:
            task.cancel()
        # asyncio.wait does not cancel the query: a watchdog cancellation must not
        # accidentally rescue the unbounded cleanup being tested.
        done, _ = await asyncio.wait({task}, timeout=0.1)
        assert task in done, "query deadline left cleanup holding the locks"
        if external_cancel:
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            assert await task is False
        assert disconnecting.is_set() and disconnected.is_set()
        client.disconnect.assert_awaited_once()
        assert c._client is None and c._intentional_disconnect_client is None
        assert not c._segment_query_incomplete and c._segment_query_colors is None
        assert not c._lock.locked() and not c._control_arbiter.locked()
        assert c.control_write_attempts == 0
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("page", [1, 2])
async def test_query_transform_rejection_only_latches_after_physical_attempt(device, monkeypatch, page):
    c, client, receive = device
    replies = pages([50] * 15)

    def transform(packet):
        if packet == build_segment_query(page):
            raise ValueError("rejected query transform")
        return packet

    async def write(_uuid, packet, **kwargs):
        assert c._segment_query_incomplete  # installed before even synchronous RX
        receive(None, bytearray(replies[packet[2] - 1]))

    c.profile = replace(c.profile, outbound_transform=transform)
    client.write_gatt_char = AsyncMock(side_effect=write)
    with pytest.raises(ValueError, match="rejected query transform"):
        await c.async_refresh_segments()
    assert client.write_gatt_char.await_count == page - 1
    assert c._segment_query_incomplete is (page > 1)
    client.disconnect.assert_not_awaited()
    if page == 1:
        connect = AsyncMock(side_effect=AssertionError("no reconnect for a rejected first page"))
        monkeypatch.setattr(coordinator_module, "async_establish_ble_connection", connect)
        async with c._control_arbiter.hold(ControlIntent.USER):
            async with c._lock:
                assert await c._ensure_connected() is client
        connect.assert_not_awaited()
    assert c.control_write_attempts == 0
