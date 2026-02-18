from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.govee_ble_lights import async_setup_entry, async_unload_entry
from custom_components.govee_ble_lights.const import CONF_MODEL, DOMAIN


def _entry(**kw):
    d = dict(entry_id="test_entry_id", unique_id="AA:BB:CC:DD:EE:FF", data={CONF_MODEL: "H617A"})
    return MagicMock(**({**d, "domain": DOMAIN, "state": ConfigEntryState.LOADED, "runtime_data": None} | kw))


@pytest.mark.parametrize("data", [{CONF_MODEL: "H617A"}, {}])
async def test_setup_entry(hass: HomeAssistant, data):
    entry = _entry(data=data)
    with (
        patch("custom_components.govee_ble_lights.GoveeBLECoordinator", autospec=True) as cls,
        patch.object(hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock) as fwd,
    ):
        cls.return_value.async_config_entry_first_refresh = AsyncMock()
        assert await async_setup_entry(hass, entry) is True
    cls.assert_called_once_with(hass, "AA:BB:CC:DD:EE:FF", "H617A")
    if data:
        assert entry.runtime_data is cls.return_value
        fwd.assert_awaited_once()


@pytest.mark.parametrize("unload_ok,disc", [(True, "assert_awaited_once"), (False, "assert_not_awaited")])
async def test_unload_entry(hass: HomeAssistant, unload_ok, disc):
    entry = _entry(runtime_data=MagicMock(disconnect=AsyncMock()))
    with patch.object(hass.config_entries, "async_unload_platforms", new_callable=AsyncMock, return_value=unload_ok):
        assert await async_unload_entry(hass, entry) is unload_ok
    getattr(entry.runtime_data.disconnect, disc)()
