"""AA0F is optional diagnostic evidence, never IC metadata or setup authority."""

import io

import pytest
from kaitaistruct import KaitaiStream
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_govee_led_ble.const import DOMAIN
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_status import decode_status_frame
from custom_components.ha_govee_led_ble.diagnostics import async_get_config_entry_diagnostics
from custom_components.ha_govee_led_ble.generated_protocol.status_query import StatusQuery
from custom_components.ha_govee_led_ble.transport import xor_checksum


@pytest.mark.parametrize("value", [15, 1, 127, 0, 128, 255])
async def test_optional_count_is_diagnostic_only(hass, value):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617A", configuration_url=None)
    entry = MockConfigEntry(domain=DOMAIN)
    entry.runtime_data = coordinator
    before = coordinator.profile
    diagnostic = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostic["coordinator"]["light_count_observation"] is None
    # 15 is direct-device evidence; other values exercise the APK signed-byte boundary.
    payload = bytes([0xAA, 0x0F, value]) + bytes(16)
    packet = payload + bytes([xor_checksum(payload)])
    decoded = decode_status_frame(packet)
    assert decoded is not None and decoded.generated.body.light_count == value
    assert type(decoded.generated.body).__module__.endswith(".h617a_control_payload")
    coordinator._notify_callback(None, bytearray(packet))
    diagnostic = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostic["coordinator"]["light_count_observation"] == {
        "value": value if 0 < value <= 127 else None,
        "received_at": coordinator.packet_log[-1]["ts"],
    }
    assert coordinator.profile is before
    assert coordinator.profile.physical_ic_count is None
    assert coordinator.profile.segment_count == 15
    assert coordinator.control_write_attempts == 0
    assert all(item["dir"] == "rx" for item in coordinator.packet_log)
    # A corrupt later frame cannot replace valid diagnostic evidence.
    coordinator._notify_callback(None, bytearray(packet[:-1] + bytes([packet[-1] ^ 1])))
    assert (await async_get_config_entry_diagnostics(hass, entry))["coordinator"]["light_count_observation"] == (
        diagnostic["coordinator"]["light_count_observation"]
    )


def test_query_and_unknown_tail_have_generated_coverage():
    query = StatusQuery(KaitaiStream(io.BytesIO(bytes.fromhex("aa0f0000000000000000000000000000000000a5"))))
    query._read()
    assert query.domain.name == "light_count" and query.body.zeros == [0] * 17
    payload = bytes([0xAA, 0x0F, 15]) + bytes(range(16))
    decoded = decode_status_frame(payload + bytes([xor_checksum(payload)]))
    assert decoded is not None and decoded.generated.body.unknown == bytes(range(16))
