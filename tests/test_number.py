from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak import BleakError
from homeassistant.const import EntityCategory

from custom_components.ha_govee_led_ble.coordinator_modes import MUSIC_PARAM_SPECS
from custom_components.ha_govee_led_ble.h6199_controls import H6199ParameterNumber as N
from custom_components.ha_govee_led_ble.h6199_controls import MusicParamNumber as MPNumber
from custom_components.ha_govee_led_ble.h6199_controls import (
    _set_with_rollback,
    _supports_number_param,
    async_setup_number_entry,
)
from custom_components.ha_govee_led_ble.protocol import build_video_white_balance as bvw


async def test_video_white_balance(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    assert c.video_white_balance is None
    await N(c, key="video_white_balance", name="T").async_set_native_value(100)
    assert c.video_white_balance == 100
    c.send_command.assert_called_once_with(bvw(100))


def test_native_value_property(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    c.music_sensitivity = 42
    assert N(c, key="music_sensitivity", name="T").native_value == 42.0
    c.video_white_balance = None
    assert N(c, key="video_white_balance", name="T").native_value is None


def test_video_white_balance_disabled_music_sensitivity_enabled(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    assert N(c, key="video_white_balance", name="T").entity_registry_enabled_default is False
    assert N(c, key="music_sensitivity", name="T").entity_registry_enabled_default is True


async def test_video_white_balance_restore(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    entity = N(c, key="video_white_balance", name="T")
    entity.async_get_last_state = AsyncMock(return_value=MagicMock(state="73"))
    await entity._async_restore_value()
    assert c.video_white_balance == 73
    c.async_set_updated_data.assert_called_once_with(c.data)


async def test_video_white_balance_restore_default_on_unknown(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    entity = N(c, key="video_white_balance", name="T")
    entity.async_get_last_state = AsyncMock(return_value=MagicMock(state="unknown"))
    await entity._async_restore_value()
    assert c.video_white_balance == 100
    c.async_set_updated_data.assert_called_once_with(c.data)


async def test_video_white_balance_restore_default_without_last_state(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    entity = N(c, key="video_white_balance", name="T")
    entity.async_get_last_state = AsyncMock(return_value=None)
    await entity._async_restore_value()
    assert c.video_white_balance == 100
    c.async_set_updated_data.assert_called_once_with(c.data)


async def test_video_white_balance_restore_clamps_out_of_range(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    entity = N(c, key="video_white_balance", name="T")
    entity.async_get_last_state = AsyncMock(return_value=MagicMock(state="999"))
    await entity._async_restore_value()
    assert c.video_white_balance == 100
    c.async_set_updated_data.assert_called_once_with(c.data)


async def test_video_white_balance_restore_skips_when_already_set(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    c.video_white_balance = 55
    entity = N(c, key="video_white_balance", name="T")
    entity.async_get_last_state = AsyncMock()
    await entity._async_restore_value()
    entity.async_get_last_state.assert_not_called()
    c.async_set_updated_data.assert_not_called()


async def test_restore_value_skips_non_white_balance(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    entity = N(c, key="music_sensitivity", name="T")
    entity.async_get_last_state = AsyncMock()
    await entity._async_restore_value()
    entity.async_get_last_state.assert_not_called()
    c.async_set_updated_data.assert_not_called()


async def test_music_sensitivity(mock_h6199_coordinator):
    (c := mock_h6199_coordinator).music_mode, c.music_color = "rolling", (10, 20, 30)
    entity = N(c, key="music_sensitivity", name="T")
    assert entity.native_max_value == 99  # device caps sensitivity at 99, not 100
    await entity.async_set_native_value(77)
    assert c.music_sensitivity == 77
    c.async_select_music_slug.assert_awaited_once_with("rolling")


async def test_rollback(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    c.video_white_balance = 55
    c.send_command = AsyncMock(side_effect=BleakError("timeout"))
    with pytest.raises(BleakError):
        await N(c, key="video_white_balance", name="T").async_set_native_value(20)
    assert c.video_white_balance == 55


def test_supports_number_param_unknown_key(mock_h6199_coordinator):
    assert _supports_number_param(mock_h6199_coordinator, "unknown") is False


async def test_set_with_rollback_noop(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    reapply = AsyncMock()
    await _set_with_rollback(c, key="music_sensitivity", value=c.music_sensitivity, reapply=reapply)
    reapply.assert_not_called()
    c.async_set_updated_data.assert_not_called()


async def test_setup_number_entry_h617a(mock_coordinator):
    add = MagicMock()
    await async_setup_number_entry(MagicMock(), MagicMock(runtime_data=mock_coordinator), add)
    keys = [entity._key for entity in add.call_args.args[0]]
    assert keys == [
        "music_sensitivity",
        "music_separation_point",
        "music_hopping_brightness",
        "music_piano_key_count",
        "music_daynight_segments",
        "music_daynight_speed",
    ]


async def test_setup_number_entry_h6199(mock_h6199_coordinator):
    add = MagicMock()
    await async_setup_number_entry(MagicMock(), MagicMock(runtime_data=mock_h6199_coordinator), add)
    keys = [entity._key for entity in add.call_args.args[0]]
    assert keys == [
        "video_white_balance",
        "music_sensitivity",
    ]


async def test_setup_number_entry_without_supported_params(mock_h6199_coordinator):
    c = mock_h6199_coordinator
    c.profile = replace(c.profile, supports_video_mode=False, supports_music_mode=False)
    add = MagicMock()
    await async_setup_number_entry(MagicMock(), MagicMock(runtime_data=c), add)
    add.assert_not_called()


def _mspec(key):
    return next(s for s in MUSIC_PARAM_SPECS if s.key == key)


async def test_music_param_number_is_experimental_and_config(mock_coordinator):
    ent = MPNumber(mock_coordinator, _mspec("music_daynight_speed"))
    assert ent._attr_entity_registry_enabled_default is False
    assert ent._attr_entity_category is EntityCategory.CONFIG
    assert (ent.native_min_value, ent.native_max_value) == (1, 50)
    assert ent.native_value == 10.0


async def test_music_param_number_reapplies_when_mode_active(mock_coordinator):
    c = mock_coordinator
    c.is_on, c.music_mode = True, "day_and_night"
    await MPNumber(c, _mspec("music_daynight_speed")).async_set_native_value(30)
    assert c.music_daynight_speed == 30
    c.async_apply_music_params.assert_awaited_once_with(0x37)


async def test_music_param_number_stores_only_when_inactive(mock_coordinator):
    c = mock_coordinator
    c.is_on, c.music_mode = True, "off"
    await MPNumber(c, _mspec("music_separation_point")).async_set_native_value(4)
    assert c.music_separation_point == 4
    c.async_apply_music_params.assert_not_awaited()
