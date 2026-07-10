from dataclasses import replace
from datetime import time as dtime
from unittest.mock import MagicMock

from custom_components.ha_govee_led_ble import protocol as proto
from custom_components.ha_govee_led_ble.number import SleepTimerNumber
from custom_components.ha_govee_led_ble.number import async_setup_entry as number_setup
from tests.mock_ble import (
    MockBle,
    mock_ble_fixture,  # noqa: F401
)
from tools.ble.mock_ble.mock_device import GoveeDeviceSim

_QUERY_UUID = "0000-timer"


def _entry(coordinator):
    return MagicMock(runtime_data=coordinator)


def test_sleep_number_native_value(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    c.sleep_timer_minutes = None
    assert SleepTimerNumber(c).native_value is None
    c.sleep_timer_minutes = 45
    assert SleepTimerNumber(c).native_value == 45.0


async def test_sleep_number_set_native_value(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    await SleepTimerNumber(c).async_set_native_value(30)
    c.async_set_sleep_timer.assert_awaited_once_with(minutes=30)


async def test_number_setup_adds_sleep_disabled_by_default(mock_h6199_coordinator):
    added: list = []
    await number_setup(MagicMock(), _entry(mock_h6199_coordinator), lambda e: added.extend(e))
    sleep = [e for e in added if isinstance(e, SleepTimerNumber)]
    assert len(sleep) == 1 and sleep[0]._attr_entity_registry_enabled_default is False


async def test_number_setup_omits_sleep_when_unsupported(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    c.profile = replace(c.profile, supports_timers=False)
    added: list = []
    await number_setup(MagicMock(), _entry(c), lambda e: added.extend(e))
    assert not any(isinstance(e, SleepTimerNumber) for e in added)


def _query(sim: GoveeDeviceSim, action: int) -> list[bytes]:
    return sim.handle_write(proto.build_packet(proto.STATUS_HEADER, action, []))


def test_sim_sleep_timer_write_query_roundtrip():
    # EXPERIMENTAL: harness=G encoding=decode-only
    sim = GoveeDeviceSim("H6199")
    sim.handle_write(proto.build_timer_sleep(True, 80, 45))
    (frame,) = _query(sim, 0x11)
    parsed = proto.parse_timer_sleep(bytes(frame)[2:-1])
    assert parsed.enabled is True and parsed.close_minutes == 45


def test_sim_wakeup_timer_write_query_roundtrip():
    # EXPERIMENTAL: harness=G encoding=decode-only
    sim = GoveeDeviceSim("H6199")
    sim.handle_write(proto.build_timer_wakeup(True, 100, 6, 30))
    (frame,) = _query(sim, 0x12)
    parsed = proto.parse_timer_wakeup(bytes(frame)[2:-1])
    assert parsed.enabled is True and (parsed.hour, parsed.minute) == (6, 30)


def test_sim_schedule_timer_write_query_roundtrip():
    sim = GoveeDeviceSim("H6199")
    sim.handle_write(proto.build_timer_schedule(1, True, True, 7, 15, [proto.Weekday.MON, proto.Weekday.FRI]))
    (frame,) = _query(sim, 0x23)
    parsed = proto.parse_timer_schedule_table(bytes(frame)[2:-1])[1]
    assert parsed.on_action is True and (parsed.hour, parsed.minute) == (7, 15)
    assert parsed.repeat_days == frozenset({proto.Weekday.MON, proto.Weekday.FRI})


def _slot(sim, index):
    return proto.parse_timer_schedule_table(bytes(_query(sim, 0x23)[0])[2:-1])[index]


def test_sim_schedule_clear_removes_slot():
    sim = GoveeDeviceSim("H6199")
    sim.handle_write(proto.build_timer_schedule(2, True, False, 8, 0))
    assert _slot(sim, 2).enabled
    sim.handle_write(proto.build_timer_schedule(2, False, False, 0, 0))
    assert not _slot(sim, 2).enabled


def test_sim_sleep_query_empty_before_write():
    sim = GoveeDeviceSim("H617A")
    assert _query(sim, 0x11) == []
    assert _query(sim, 0x12) == []


async def test_mock_ble_sleep_timer_write_then_decode(mock_ble: MockBle):
    # EXPERIMENTAL: harness=G encoding=decode-only
    coord, sim, client = mock_ble.coordinator, mock_ble.sim, mock_ble.client
    await coord._ensure_connected()
    await coord.async_set_sleep_timer(enabled=True, minutes=25)
    assert sim.sleep_timer == (1, coord.brightness_pct, 25, 0)
    sim.sleep_timer = (1, 80, 40, 0)
    await client.write_gatt_char(_QUERY_UUID, proto.build_packet(proto.STATUS_HEADER, 0x11, []))
    assert coord.sleep_timer_enabled is True and coord.sleep_timer_minutes == 40


async def test_mock_ble_wakeup_timer_write_then_decode(mock_ble: MockBle):
    # EXPERIMENTAL: harness=G encoding=decode-only
    coord, sim, client = mock_ble.coordinator, mock_ble.sim, mock_ble.client
    await coord._ensure_connected()
    await coord.async_set_wakeup_timer(enabled=True, wake_time=dtime(6, 30))
    assert sim.wakeup_timer == (1, 100, 6, 30, proto.TIMER_REPEAT_ONCE, 10)
    sim.wakeup_timer = (1, 100, 7, 45, proto.TIMER_REPEAT_ONCE, 10)
    await client.write_gatt_char(_QUERY_UUID, proto.build_packet(proto.STATUS_HEADER, 0x12, []))
    assert coord.wakeup_timer_enabled is True and coord.wakeup_timer_time == dtime(7, 45)


async def test_mock_ble_schedule_timer_write_then_decode(mock_ble: MockBle):
    # EXPERIMENTAL: harness=G encoding=decode-only
    coord, sim, client = mock_ble.coordinator, mock_ble.sim, mock_ble.client
    await coord._ensure_connected()
    await coord.async_set_schedule_timer(0, on_action=True, hour=9, minute=45, days=[proto.Weekday.SUN])
    assert sim.schedule_timers[0] == (0x81, 9, 45, proto.timer_repeat([proto.Weekday.SUN]))
    sim.schedule_timers[0] = (0x80, 10, 30, proto.timer_repeat([proto.Weekday.SAT]))
    await client.write_gatt_char(_QUERY_UUID, proto.build_packet(proto.STATUS_HEADER, 0x23, []))
    record = coord.schedule_timers[0]
    assert record is not None and (record.hour, record.minute) == (10, 30)
    assert record.on_action is False and record.repeat_days == frozenset({proto.Weekday.SAT})
