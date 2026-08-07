from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from custom_components.ha_govee_led_ble import (
    _async_cleanup_legacy_entities,
    _maybe_flag_white_balance_replaced,
    async_setup,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.ha_govee_led_ble.const import CONF_MODEL, DOMAIN, MODEL_PROFILES


def _entry(**kw):
    d = dict(entry_id="test_entry_id", unique_id="AA:BB:CC:DD:EE:FF", data={CONF_MODEL: "H617A"})
    return MagicMock(**({**d, "domain": DOMAIN, "state": ConfigEntryState.LOADED, "runtime_data": None} | kw))


async def test_setup_entry(hass: HomeAssistant):
    entry = _entry()
    with (
        patch("custom_components.ha_govee_led_ble.GoveeBLECoordinator", autospec=True) as cls,
        patch("custom_components.ha_govee_led_ble._async_cleanup_legacy_entities", new_callable=AsyncMock) as cleanup,
        patch.object(hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock) as fwd,
    ):
        cls.return_value.async_config_entry_first_refresh = AsyncMock()
        cls.return_value.profile = MODEL_PROFILES["H617A"]
        assert await async_setup_entry(hass, entry) is True
    cls.assert_called_once_with(hass, "AA:BB:CC:DD:EE:FF", "H617A")
    assert entry.runtime_data is cls.return_value
    cleanup.assert_awaited_once_with(hass, entry)
    fwd.assert_awaited_once()


@pytest.mark.parametrize("data", [{}, {CONF_MODEL: "H9999"}])
async def test_setup_entry_rejects_unknown_model(hass: HomeAssistant, data):
    entry = _entry(data=data)
    with patch("custom_components.ha_govee_led_ble.GoveeBLECoordinator", autospec=True) as cls:
        assert await async_setup_entry(hass, entry) is False
    cls.assert_not_called()
    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"unsupported_model_{entry.entry_id}")
    assert issue is not None
    assert issue.severity is ir.IssueSeverity.ERROR


@pytest.mark.parametrize("unload_ok,disc", [(True, "assert_awaited_once"), (False, "assert_not_awaited")])
async def test_unload_entry(hass: HomeAssistant, unload_ok, disc):
    entry = _entry(runtime_data=MagicMock(disconnect=AsyncMock()))
    with patch.object(hass.config_entries, "async_unload_platforms", new_callable=AsyncMock, return_value=unload_ok):
        assert await async_unload_entry(hass, entry) is unload_ok
    getattr(entry.runtime_data.disconnect, disc)()


async def test_cleanup_legacy_entities(hass: HomeAssistant):
    entry = _entry()
    registry = MagicMock()
    stale = MagicMock(unique_id="112233445566_video_brightness", entity_id="number.govee_video_brightness")
    stale2 = MagicMock(unique_id="112233445566_white_brightness", entity_id="number.govee_white_brightness")
    stale4 = MagicMock(unique_id="112233445566_music_calm", entity_id="switch.govee_music_calm")
    removed_surface = [
        MagicMock(unique_id="112233445566_effect_preview", entity_id="image.govee_effect_preview"),
        MagicMock(unique_id="112233445566_reduce_motion", entity_id="switch.govee_reduce_motion"),
        MagicMock(unique_id="112233445566_white_balance_red", entity_id="number.govee_white_balance_red"),
        MagicMock(unique_id="112233445566_white_balance_blue", entity_id="number.govee_white_balance_blue"),
        MagicMock(unique_id="112233445566_white_balance_preset", entity_id="select.govee_white_balance"),
    ]
    current = [
        MagicMock(unique_id="112233445566_video_saturation", entity_id="number.govee_video_saturation"),
        MagicMock(unique_id="112233445566_video_sound_effects", entity_id="switch.govee_video_sound_effects"),
        MagicMock(
            unique_id="112233445566_video_sound_effects_softness",
            entity_id="number.govee_video_sound_effects_softness",
        ),
    ]
    retired = MagicMock(unique_id="112233445566_music_sensitivity", entity_id="number.govee_music_sensitivity")
    with (
        patch("custom_components.ha_govee_led_ble.er.async_get", return_value=registry),
        patch(
            "custom_components.ha_govee_led_ble.er.async_entries_for_config_entry",
            return_value=[stale, stale2, stale4, *removed_surface, *current, retired],
        ),
    ):
        await _async_cleanup_legacy_entities(hass, entry)
    registry.async_remove.assert_has_calls(
        [
            call("number.govee_video_brightness"),
            call("number.govee_white_brightness"),
            call("switch.govee_music_calm"),
            *[call(entity.entity_id) for entity in removed_surface],
            call(retired.entity_id),
        ]
    )
    assert registry.async_remove.call_count == 4 + len(removed_surface)
    assert hass.data[DOMAIN][f"{entry.entry_id}_white_balance_from"] == [
        "number.govee_white_balance_red",
        "number.govee_white_balance_blue",
        "select.govee_white_balance",
    ]
    for entity in current:
        assert call(entity.entity_id) not in registry.async_remove.call_args_list


def test_white_balance_replacement_issue_names_old_and_new_entities(hass: HomeAssistant):
    entry = _entry()
    hass.data.setdefault(DOMAIN, {})[f"{entry.entry_id}_white_balance_from"] = [
        "number.old_red",
        "number.old_blue",
        "select.old_balance",
    ]
    registry = MagicMock()
    registry.async_get_entity_id.return_value = "number.govee_white_balance"
    with patch("custom_components.ha_govee_led_ble.er.async_get", return_value=registry):
        _maybe_flag_white_balance_replaced(hass, entry)

    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"white_balance_controls_replaced_{entry.entry_id}")
    assert issue is not None
    assert issue.translation_placeholders == {
        "old": "number.old_red, number.old_blue, select.old_balance",
        "new": "number.govee_white_balance",
    }


async def test_async_setup_needs_no_frontend_registration():
    hass = MagicMock()
    hass.data = {}
    assert await async_setup(hass, {}) is True
