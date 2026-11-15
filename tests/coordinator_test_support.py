"""Shared frame construction for coordinator tests."""

from unittest.mock import AsyncMock, MagicMock

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
