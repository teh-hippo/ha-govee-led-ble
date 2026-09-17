"""Static companions are presentation evidence, not direct Gradient-register confirmation."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ha_govee_led_ble.const import ReadDomain
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode
from custom_components.ha_govee_led_ble.generated_protocol_adapter import build_h6199_control_query, build_video_mode
from tests.test_h6199_capabilities import QUALIFIED
from tests.test_h6199_native_controls import frame


def test_stale_mode_does_not_publish_gradient_but_accepted_static_does(hass):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url=None)
    c.gradient = 0
    c._arm_expected(build_video_mode("movie", True, 50, False, 50, c.model))
    before = c._domain_revisions.get(ReadDomain.COLOUR_MODE, 0)
    c._notify_callback(None, frame("aa051501"))
    assert c.gradient == 0
    assert "gradient" not in c._field_revisions
    assert c._domain_revisions[ReadDomain.COLOUR_MODE] == before + 1
    c._expected_state.clear()
    c._notify_callback(None, frame("aa051501"))
    assert c.color_mode is ParsedMode.COLOUR and c.gradient == 1
    assert c._field_revisions["gradient"] == c._field_revisions["color_mode"]
    assert c._domain_revisions[ReadDomain.COLOUR_MODE] == before + 2
    assert "gradient_register" not in c._field_revisions
    before = c._domain_revisions.get(ReadDomain.OTHER, 0)
    c._notify_callback(None, frame("aaa300"))
    assert c.gradient == 0
    assert c._field_revisions["gradient_register"] == 1
    assert c._field_revisions["gradient"] == 2
    assert c._domain_revisions[ReadDomain.OTHER] == before + 1


@pytest.mark.parametrize("direct", [None, 0, 1])
async def test_gradient_write_requires_matching_direct_register_reply(hass, monkeypatch, direct):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url=None)
    vars(c).update(QUALIFIED)
    # A previous matching A3 reply must not qualify the next write.
    c._notify_callback(None, frame("aaa301"))
    baseline = c._field_revisions["gradient_register"]

    async def transmit(_uuid, packet, **kwargs):
        if packet == build_h6199_control_query("gradient"):
            if direct is not None:
                c._notify_callback(None, frame(f"aaa3{direct:02x}"))
            c._notify_callback(None, frame("aa051501"))
            assert c.gradient == 1 and c.color_mode is ParsedMode.COLOUR

    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=transmit))
    c._client = client
    monkeypatch.setattr(c, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(c, "_renew_foreground_lease", MagicMock())
    if direct == 1:
        await c.async_set_h6199_control("gradient", 1, timeout=0.01)
    else:
        with pytest.raises((ValueError, TimeoutError)):
            await c.async_set_h6199_control("gradient", 1, timeout=0.01)
    assert c.gradient == 1
    assert c._field_revisions["gradient_register"] == baseline + (direct is not None)
    assert client.write_gatt_char.await_count == 2
