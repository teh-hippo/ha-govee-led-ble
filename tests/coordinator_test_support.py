"""Shared frame construction for coordinator tests."""

from unittest.mock import AsyncMock, MagicMock

from custom_components.ha_govee_led_ble.const import get_profile
from custom_components.ha_govee_led_ble.effect_catalogue import diy_destination_range, diy_destination_route
from custom_components.ha_govee_led_ble.effect_diy_destination import (
    DiyDestinationConsent,
    diy_destination_authority,
)
from custom_components.ha_govee_led_ble.transport import xor_checksum

_CONFIGURATION_URL = "homeassistant://ha-govee-led-ble/editor/test-entry"


def _packet(header: int, action: int, params: list[int]) -> bytes:
    payload = bytearray([header, action, *params][:19])
    payload.extend(b"\x00" * (19 - len(payload)))
    payload.append(xor_checksum(payload))
    return bytes(payload)


def _c(**kw):
    kw.setdefault("disconnect", AsyncMock())
    return MagicMock(is_connected=True, **kw)


def _confirm_identity(coordinator, firmware="3.02.24", hardware="3.01.01"):
    coordinator._note_identity(fw_version=firmware, hw_version=hardware)
    coordinator._observe_identity_field("fw_version", firmware)
    coordinator._observe_identity_field("hw_version", hardware)


def qualify_coordinator_identity(
    coordinator,
    *,
    pact=(2, 1),
    firmware="1.10.04",
    hardware="3.02.01",
    subordinate_20="1.03.00",
    subordinate_21="1.00.33",
):
    coordinator.fw_version = firmware
    coordinator.hw_version = hardware
    coordinator.subordinate_20_version = subordinate_20
    coordinator.subordinate_21_version = subordinate_21
    coordinator._confirmed_identity_fields.update(
        {"fw_version", "hw_version", "subordinate_20_version", "subordinate_21_version"}
    )
    if get_profile(coordinator.model).requires_pact_confirmation and pact is not None:
        coordinator.pact_type, coordinator.pact_code = pact
        coordinator._confirmed_identity_fields.add("pact")
    coordinator._resolve_device_profile(preserve_state=True)


def approve_diy_destination_operation(coordinator, config_entry_id: str, destination: int) -> DiyDestinationConsent:
    return DiyDestinationConsent.bind(
        coordinator,
        config_entry_id,
        {
            "config_entry_id": config_entry_id,
            "model": coordinator.model,
            "destination": destination,
            "minimum": diy_destination_range(coordinator.model)[0],
            "maximum": diy_destination_range(coordinator.model)[1],
            "route": diy_destination_route(coordinator.model, coordinator.effect_authorization_profile),
            "authority": diy_destination_authority(coordinator),
            "overwrite_confirmed": True,
        },
    )


def frame(prefix: str) -> bytes:
    """Pad a synthetic hexadecimal prefix to a checksummed 20-byte frame."""
    body = bytes.fromhex(prefix).ljust(19, b"\x00")
    assert len(body) == 19
    return body + bytes([xor_checksum(body)])
