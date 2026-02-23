from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.ha_govee_led_ble import _async_cleanup_legacy_entities, async_setup_entry, async_unload_entry
from custom_components.ha_govee_led_ble.const import CONF_MODEL, DOMAIN


def _entry(**kw):
    d = dict(entry_id="test_entry_id", unique_id="AA:BB:CC:DD:EE:FF", data={CONF_MODEL: "H617A"})
    return MagicMock(**({**d, "domain": DOMAIN, "state": ConfigEntryState.LOADED, "runtime_data": None} | kw))


@pytest.mark.parametrize("data", [{CONF_MODEL: "H617A"}, {}])
async def test_setup_entry(hass: HomeAssistant, data):
    entry = _entry(data=data)
    with (
        patch("custom_components.ha_govee_led_ble.GoveeBLECoordinator", autospec=True) as cls,
        patch("custom_components.ha_govee_led_ble._async_cleanup_legacy_entities", new_callable=AsyncMock) as cleanup,
        patch.object(hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock) as fwd,
    ):
        cls.return_value.async_config_entry_first_refresh = AsyncMock()
        assert await async_setup_entry(hass, entry) is True
    cls.assert_called_once_with(hass, "AA:BB:CC:DD:EE:FF", "H617A")
    assert entry.runtime_data is cls.return_value
    cleanup.assert_awaited_once_with(hass, entry)
    fwd.assert_awaited_once()


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
    keep = MagicMock(unique_id="112233445566_video_saturation", entity_id="number.govee_video_saturation")
    with (
        patch("custom_components.ha_govee_led_ble.er.async_get", return_value=registry),
        patch(
            "custom_components.ha_govee_led_ble.er.async_entries_for_config_entry",
            return_value=[stale, stale2, keep],
        ),
    ):
        await _async_cleanup_legacy_entities(hass, entry)
    registry.async_remove.assert_has_calls(
        [call("number.govee_video_brightness"), call("number.govee_white_brightness")]
    )
    assert registry.async_remove.call_count == 2
