"""Shared frame construction for coordinator tests."""

from unittest.mock import AsyncMock, MagicMock

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
