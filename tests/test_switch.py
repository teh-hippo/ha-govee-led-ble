from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak import BleakError
from homeassistant.const import EntityCategory

from custom_components.ha_govee_led_ble.coordinator_modes import MUSIC_PARAM_SPECS as _MPS
from custom_components.ha_govee_led_ble.h6199_controls import MusicParamSwitch as MPSwitch
from custom_components.ha_govee_led_ble.h6199_controls import (
    PowerOffMemorySwitch,
    async_setup_switch_entry,
)
from custom_components.ha_govee_led_ble.protocol import build_poweroff_memory as bpm
from custom_components.ha_govee_led_ble.switch import (
    EffectPreviewReduceMotionSwitch,
    SleepTimerSwitch,
    WakeupTimerSwitch,
)
from custom_components.ha_govee_led_ble.switch import async_setup_entry as switch_setup


def _entry(coordinator):
    return MagicMock(runtime_data=coordinator)


async def test_setup_switch_entry_h617a(mock_coordinator):
    add = MagicMock()
    await async_setup_switch_entry(MagicMock(), _entry(mock_coordinator), add)
    keys = [entity._key for entity in add.call_args.args[0]]
    assert keys == ["music_separation_gradient"]


async def test_setup_switch_entry_h6199(mock_h6199_coordinator):
    add = MagicMock()
    await async_setup_switch_entry(MagicMock(), _entry(mock_h6199_coordinator), add)
    keys = [entity._key for entity in add.call_args.args[0]]
    assert keys == ["poweroff_memory"]


async def test_setup_switch_entry_without_supported_controls(mock_coordinator):
    c = mock_coordinator
    c.profile = replace(
        c.profile, supports_music_style=False, supports_music_params=False, supports_poweroff_memory=False
    )
    add = MagicMock()
    await async_setup_switch_entry(MagicMock(), _entry(c), add)
    add.assert_not_called()


async def test_setup_switch_entry_poweroff_memory_created_disabled(mock_h6199_coordinator):
    add = MagicMock()
    await async_setup_switch_entry(MagicMock(), _entry(mock_h6199_coordinator), add)
    keys = [entity._key for entity in add.call_args.args[0]]
    assert keys == ["poweroff_memory"]
    poweroff = add.call_args.args[0][-1]
    assert isinstance(poweroff, PowerOffMemorySwitch)
    assert poweroff._attr_entity_registry_enabled_default is False


async def test_setup_switch_entry_no_poweroff_on_h617a(mock_coordinator):
    """The H617A app has no power-off-memory setting, so no such switch is created."""
    add = MagicMock()
    await async_setup_switch_entry(MagicMock(), _entry(mock_coordinator), add)
    entities = add.call_args.args[0] if add.call_args else []
    assert all(not isinstance(entity, PowerOffMemorySwitch) for entity in entities)


async def test_setup_switch_entry_poweroff_memory_absent_when_unsupported(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    c.profile = replace(c.profile, supports_poweroff_memory=False)
    add = MagicMock()
    await async_setup_switch_entry(MagicMock(), _entry(c), add)
    entities = add.call_args.args[0] if add.call_args else []
    assert all(not isinstance(entity, PowerOffMemorySwitch) for entity in entities)


def test_poweroff_memory_is_on_reflects_coordinator(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    switch = PowerOffMemorySwitch(c)
    c.poweroff_memory = None
    assert switch.is_on is None
    c.poweroff_memory = True
    assert switch.is_on is True
    c.poweroff_memory = False
    assert switch.is_on is False


async def test_poweroff_memory_turn_on_sends_command(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    c.poweroff_memory = False
    await PowerOffMemorySwitch(c).async_turn_on()
    assert c.poweroff_memory is True
    c.send_command.assert_called_once_with(bpm(True))


async def test_poweroff_memory_turn_off_sends_command(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    c.poweroff_memory = True
    await PowerOffMemorySwitch(c).async_turn_off()
    assert c.poweroff_memory is False
    c.send_command.assert_called_once_with(bpm(False))


async def test_poweroff_memory_rollback_on_failure(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    c.poweroff_memory = False
    c.send_command = AsyncMock(side_effect=BleakError("timeout"))
    with pytest.raises(BleakError):
        await PowerOffMemorySwitch(c).async_turn_on()
    assert c.poweroff_memory is False
    c.async_set_updated_data.assert_not_called()


async def test_poweroff_memory_restore_on(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    c.poweroff_memory = None
    entity = PowerOffMemorySwitch(c)
    entity.async_get_last_state = AsyncMock(return_value=MagicMock(state="on"))
    await entity._async_restore_state()
    assert c.poweroff_memory is True
    c.async_set_updated_data.assert_called_once_with(c.data)


async def test_poweroff_memory_restore_off(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    c.poweroff_memory = None
    entity = PowerOffMemorySwitch(c)
    entity.async_get_last_state = AsyncMock(return_value=MagicMock(state="off"))
    await entity._async_restore_state()
    assert c.poweroff_memory is False


async def test_poweroff_memory_restore_skips_when_known(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    c.poweroff_memory = True
    entity = PowerOffMemorySwitch(c)
    entity.async_get_last_state = AsyncMock()
    await entity._async_restore_state()
    entity.async_get_last_state.assert_not_called()
    c.async_set_updated_data.assert_not_called()


async def test_poweroff_memory_restore_ignores_unknown(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    c.poweroff_memory = None
    entity = PowerOffMemorySwitch(c)
    entity.async_get_last_state = AsyncMock(return_value=MagicMock(state="unknown"))
    await entity._async_restore_state()
    assert c.poweroff_memory is None
    c.async_set_updated_data.assert_not_called()


async def test_poweroff_memory_restore_without_last_state(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    c.poweroff_memory = None
    entity = PowerOffMemorySwitch(c)
    entity.async_get_last_state = AsyncMock(return_value=None)
    await entity._async_restore_state()
    assert c.poweroff_memory is None
    c.async_set_updated_data.assert_not_called()


async def test_poweroff_memory_added_to_hass_triggers_restore(mock_h6199_coordinator):
    entity = PowerOffMemorySwitch(mock_h6199_coordinator)
    entity._async_restore_state = AsyncMock()
    with patch(
        "custom_components.ha_govee_led_ble.entity.GoveeBLEEntity.async_added_to_hass",
        new_callable=AsyncMock,
    ) as super_added:
        await entity.async_added_to_hass()
    super_added.assert_awaited_once()
    entity._async_restore_state.assert_awaited_once()


def test_sleep_timer_switch_is_on(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    c.sleep_timer_enabled = None
    assert SleepTimerSwitch(c).is_on is None
    c.sleep_timer_enabled = True
    assert SleepTimerSwitch(c).is_on is True


async def test_sleep_timer_switch_turn_on_off(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    await SleepTimerSwitch(c).async_turn_on()
    c.async_set_sleep_timer.assert_awaited_once_with(enabled=True)
    c.async_set_sleep_timer.reset_mock()
    await SleepTimerSwitch(c).async_turn_off()
    c.async_set_sleep_timer.assert_awaited_once_with(enabled=False)


def test_wakeup_timer_switch_is_on(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    c.wakeup_timer_enabled = False
    assert WakeupTimerSwitch(c).is_on is False


async def test_wakeup_timer_switch_turn_on_off(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    await WakeupTimerSwitch(c).async_turn_on()
    c.async_set_wakeup_timer.assert_awaited_once_with(enabled=True)
    c.async_set_wakeup_timer.reset_mock()
    await WakeupTimerSwitch(c).async_turn_off()
    c.async_set_wakeup_timer.assert_awaited_once_with(enabled=False)


async def test_switch_setup_adds_timers_disabled_by_default(mock_h6199_coordinator):
    added: list = []
    await switch_setup(MagicMock(), _entry(mock_h6199_coordinator), lambda e: added.extend(e))
    timer_switches = [e for e in added if isinstance(e, (SleepTimerSwitch, WakeupTimerSwitch))]
    assert [type(e).__name__ for e in timer_switches] == ["SleepTimerSwitch", "WakeupTimerSwitch"]
    assert all(e._attr_entity_registry_enabled_default is False for e in timer_switches)


async def test_switch_setup_omits_timers_when_unsupported(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    c.profile = replace(c.profile, supports_timers=False)
    added: list = []
    await switch_setup(MagicMock(), _entry(c), lambda e: added.extend(e))
    assert not any(isinstance(e, (SleepTimerSwitch, WakeupTimerSwitch)) for e in added)


def _gradient_spec():
    return next(s for s in _MPS if s.key == "music_separation_gradient")


async def test_music_param_switch_gradient_reapplies_when_active(mock_coordinator):
    c = mock_coordinator
    c.is_on, c.music_mode = True, "separation"
    ent = MPSwitch(c, _gradient_spec())
    assert ent._attr_entity_registry_enabled_default is False
    assert ent.is_on is True
    await ent.async_turn_off()
    assert c.music_separation_gradient is False
    c.async_apply_music_params.assert_awaited_once_with(0x32)
    await ent.async_turn_on()
    assert c.music_separation_gradient is True


async def test_music_param_switch_stores_only_when_inactive(mock_coordinator):
    c = mock_coordinator
    c.is_on, c.music_mode = True, "off"
    await MPSwitch(c, _gradient_spec()).async_turn_off()
    assert c.music_separation_gradient is False
    c.async_apply_music_params.assert_not_awaited()


async def test_switch_setup_adds_reduce_motion_on_h6199(mock_h6199_coordinator):
    added: list = []
    await switch_setup(MagicMock(), _entry(mock_h6199_coordinator), lambda e: added.extend(e))
    motion = [e for e in added if isinstance(e, EffectPreviewReduceMotionSwitch)]
    assert len(motion) == 1


async def test_switch_setup_adds_reduce_motion_on_h617a(mock_coordinator):
    added: list = []
    await switch_setup(MagicMock(), _entry(mock_coordinator), lambda e: added.extend(e))
    assert sum(isinstance(e, EffectPreviewReduceMotionSwitch) for e in added) == 1


def test_reduce_motion_is_on_reflects_coordinator(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    switch = EffectPreviewReduceMotionSwitch(c)
    c.preview_reduce_motion = False
    assert switch.is_on is False
    c.preview_reduce_motion = True
    assert switch.is_on is True


def test_reduce_motion_metadata(mock_h6199_coordinator):
    switch = EffectPreviewReduceMotionSwitch(mock_h6199_coordinator)
    assert switch.unique_id == "112233445566_reduce_motion"
    assert switch.translation_key == "effect_preview_reduce_motion"
    assert switch._attr_entity_category == EntityCategory.CONFIG


async def test_reduce_motion_turn_on_sets_flag_without_device_command(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    c.preview_reduce_motion = False
    await EffectPreviewReduceMotionSwitch(c).async_turn_on()
    assert c.preview_reduce_motion is True
    c.send_command.assert_not_called()
    c.async_set_updated_data.assert_called_once_with(c.data)


async def test_reduce_motion_turn_off_sets_flag_without_device_command(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    c.preview_reduce_motion = True
    await EffectPreviewReduceMotionSwitch(c).async_turn_off()
    assert c.preview_reduce_motion is False
    c.send_command.assert_not_called()
    c.async_set_updated_data.assert_called_once_with(c.data)


async def test_reduce_motion_restore_on(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    c.preview_reduce_motion = False
    entity = EffectPreviewReduceMotionSwitch(c)
    entity.async_get_last_state = AsyncMock(return_value=MagicMock(state="on"))
    await entity._async_restore_state()
    assert c.preview_reduce_motion is True
    c.send_command.assert_not_called()


async def test_reduce_motion_restore_off(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    c.preview_reduce_motion = True
    entity = EffectPreviewReduceMotionSwitch(c)
    entity.async_get_last_state = AsyncMock(return_value=MagicMock(state="off"))
    await entity._async_restore_state()
    assert c.preview_reduce_motion is False


async def test_reduce_motion_restore_without_last_state(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    c.preview_reduce_motion = False
    entity = EffectPreviewReduceMotionSwitch(c)
    entity.async_get_last_state = AsyncMock(return_value=None)
    await entity._async_restore_state()
    assert c.preview_reduce_motion is False
    c.async_set_updated_data.assert_not_called()


async def test_reduce_motion_restore_ignores_unknown_state(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    c.preview_reduce_motion = False
    entity = EffectPreviewReduceMotionSwitch(c)
    entity.async_get_last_state = AsyncMock(return_value=MagicMock(state="unknown"))
    await entity._async_restore_state()
    assert c.preview_reduce_motion is False
    c.async_set_updated_data.assert_not_called()


async def test_reduce_motion_added_to_hass_triggers_restore(mock_h6199_coordinator):
    entity = EffectPreviewReduceMotionSwitch(mock_h6199_coordinator)
    entity._async_restore_state = AsyncMock()
    with patch(
        "custom_components.ha_govee_led_ble.entity.GoveeBLEEntity.async_added_to_hass",
        new_callable=AsyncMock,
    ) as super_added:
        await entity.async_added_to_hass()
    super_added.assert_awaited_once()
    entity._async_restore_state.assert_awaited_once()
