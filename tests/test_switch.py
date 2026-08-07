from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak import BleakError

from custom_components.ha_govee_led_ble.h6199_controls import (
    H6199ControlSwitch,
    async_setup_switch_entry,
)
from custom_components.ha_govee_led_ble.protocol import build_blank_screen


def _entry(coordinator):
    return MagicMock(runtime_data=coordinator)


async def test_setup_switch_entry_h617a(mock_coordinator):
    add = MagicMock()
    await async_setup_switch_entry(MagicMock(), _entry(mock_coordinator), add)
    add.assert_not_called()


async def test_setup_switch_entry_h6199(mock_h6199_coordinator):
    add = MagicMock()
    await async_setup_switch_entry(MagicMock(), _entry(mock_h6199_coordinator), add)
    keys = [entity._key for entity in add.call_args.args[0]]
    assert keys == ["video_sound_effects", "blank_screen"]


async def test_setup_switch_entry_h6199_controls_are_capability_gated(mock_h6199_coordinator):
    """The H617A must not grow a blank screen just because the switch table is shared."""
    c = mock_h6199_coordinator
    c.profile = replace(c.profile, supports_video_sound_effects=False, supports_blank_screen=False)
    add = MagicMock()
    await async_setup_switch_entry(MagicMock(), _entry(c), add)
    add.assert_not_called()


async def test_blank_screen_turn_on_and_off_send_the_register(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    c.blank_screen = None
    entity = H6199ControlSwitch(c, key="blank_screen")
    assert entity.is_on is None
    await entity.async_turn_on()
    assert c.blank_screen is True
    c.send_command.assert_awaited_once_with(build_blank_screen(True))
    c.refresh_state.assert_awaited_once_with(expected_blank_screen=True)
    c.send_command.reset_mock()
    c.refresh_state.reset_mock()
    await entity.async_turn_off()
    assert c.blank_screen is False
    c.send_command.assert_awaited_once_with(build_blank_screen(False))
    c.refresh_state.assert_awaited_once_with(expected_blank_screen=False)


async def test_blank_screen_rolls_back_when_the_write_fails(mock_h6199_coordinator):
    """Nothing here parses 33 a9 back, so a failed write leaving the switch on would never correct."""
    c = mock_h6199_coordinator
    c.blank_screen = False
    c.send_command = AsyncMock(side_effect=BleakError("timeout"))
    with pytest.raises(BleakError):
        await H6199ControlSwitch(c, key="blank_screen").async_turn_on()
    assert c.blank_screen is False
    c.async_set_updated_data.assert_not_called()


async def test_blank_screen_verification_failure_rolls_back(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    c.blank_screen = False
    c.refresh_state = AsyncMock(return_value=False)
    with pytest.raises(RuntimeError, match="not confirmed"):
        await H6199ControlSwitch(c, key="blank_screen").async_turn_on()
    assert c.blank_screen is False
    assert c.send_command.await_count == 2


async def test_control_switch_does_not_restore_read_backed_state(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    c.blank_screen = None
    entity = H6199ControlSwitch(c, key="blank_screen")
    entity.async_get_last_state = AsyncMock(return_value=MagicMock(state="on"))
    with patch(
        "custom_components.ha_govee_led_ble.entity.GoveeBLEEntity.async_added_to_hass",
        new_callable=AsyncMock,
    ):
        await entity.async_added_to_hass()
    assert c.blank_screen is None
    entity.async_get_last_state.assert_not_called()
    c.send_command.assert_not_called()


async def test_control_switch_restore_skips_known_and_unusable_states(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    c.blank_screen = True
    entity = H6199ControlSwitch(c, key="blank_screen")
    entity.async_get_last_state = AsyncMock()
    with patch(
        "custom_components.ha_govee_led_ble.entity.GoveeBLEEntity.async_added_to_hass",
        new_callable=AsyncMock,
    ):
        await entity.async_added_to_hass()
    entity.async_get_last_state.assert_not_called()

    c.blank_screen = None
    entity = H6199ControlSwitch(c, key="blank_screen")
    entity.async_get_last_state = AsyncMock(return_value=MagicMock(state="unavailable"))
    with patch(
        "custom_components.ha_govee_led_ble.entity.GoveeBLEEntity.async_added_to_hass",
        new_callable=AsyncMock,
    ):
        await entity.async_added_to_hass()
    assert c.blank_screen is None

    c.blank_screen = None
    entity = H6199ControlSwitch(c, key="blank_screen")
    entity.async_get_last_state = AsyncMock(return_value=None)
    with patch(
        "custom_components.ha_govee_led_ble.entity.GoveeBLEEntity.async_added_to_hass",
        new_callable=AsyncMock,
    ):
        await entity.async_added_to_hass()
    assert c.blank_screen is None


async def test_setup_switch_entry_without_supported_controls(mock_coordinator):
    add = MagicMock()
    await async_setup_switch_entry(MagicMock(), _entry(mock_coordinator), add)
    add.assert_not_called()
