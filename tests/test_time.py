from dataclasses import replace
from datetime import time as dtime
from unittest.mock import MagicMock

from custom_components.ha_govee_led_ble.time import WakeupTimerTime
from custom_components.ha_govee_led_ble.time import async_setup_entry as time_setup


def _entry(coordinator):
    return MagicMock(runtime_data=coordinator)


def test_native_value(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    c.wakeup_timer_time = None
    assert WakeupTimerTime(c).native_value is None
    c.wakeup_timer_time = dtime(6, 45)
    assert WakeupTimerTime(c).native_value == dtime(6, 45)


async def test_async_set_value(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    await WakeupTimerTime(c).async_set_value(dtime(7, 15))
    c.async_set_wakeup_timer.assert_awaited_once_with(wake_time=dtime(7, 15))


async def test_setup_adds_time_disabled_by_default(mock_h6199_coordinator):
    added: list = []
    await time_setup(MagicMock(), _entry(mock_h6199_coordinator), lambda e: added.extend(e))
    assert len(added) == 1 and isinstance(added[0], WakeupTimerTime)
    assert added[0]._attr_entity_registry_enabled_default is False


async def test_setup_omits_time_when_unsupported(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    c.profile = replace(c.profile, supports_timers=False)
    added: list = []
    await time_setup(MagicMock(), _entry(c), lambda e: added.extend(e))
    assert added == []
