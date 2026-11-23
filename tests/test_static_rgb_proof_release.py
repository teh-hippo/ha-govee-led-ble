"""A clean planned release keeps the whole-strip RGB proof; any other release revokes it."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError

from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode
from tests.coordinator_test_support import _CONFIGURATION_URL


def _coordinator(hass, disconnect):
    coord = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H7025", configuration_url=_CONFIGURATION_URL)
    coord.pact_type, coord.pact_code = 1, 1
    coord._resolve_device_profile()
    client = MagicMock(is_connected=True, disconnect=AsyncMock(side_effect=disconnect), start_notify=AsyncMock())
    coord._client = client
    coord._notification_token = object()
    coord.color_mode = ParsedMode.COLOUR
    coord.segment_colors = [(255, 0, 128)] * coord.profile.segment_count
    coord.segment_state_source = "observed"
    coord._static_rgb_known = True
    return coord, client


async def test_clean_planned_release_keeps_static_rgb_proof(hass):
    coord, client = _coordinator(hass, lambda: setattr(client, "is_connected", False))
    await coord._disconnect_locked(planned_release=True)
    assert coord._client is None
    assert coord._static_rgb_known
    assert coord.capture_effect_control_state().static_rgb_known


@pytest.mark.parametrize("release", ["unplanned", "failed"])
async def test_other_releases_revoke_static_rgb_proof(hass, release):
    def disconnect():
        if release == "failed":
            raise BleakError("Disconnect failed")
        client.is_connected = False

    coord, client = _coordinator(hass, disconnect)
    await coord._disconnect_locked(planned_release=release == "planned")
    assert not coord._static_rgb_known


async def test_segment_readback_mismatch_still_revokes_kept_proof(hass):
    coord, client = _coordinator(hass, lambda: setattr(client, "is_connected", False))
    await coord._disconnect_locked(planned_release=True)
    assert coord._static_rgb_known
    coord._apply_segment_palette([(255, 255, 255)] * coord.profile.segment_count, None)
    assert not coord._static_rgb_known
