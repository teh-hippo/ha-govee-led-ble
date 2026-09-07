"""Parse Govee manufacturer data advertised before a connection."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

_GOVEE_ADVERTISEMENT_MAGIC = b"\x88\xec"
_GOVEE_ADVERTISEMENT_LENGTH = 6
ADVERTISEMENT_ENCRYPTION_BIT = 0x40


@dataclass(frozen=True, slots=True)
class GoveeAdvertisement:
    """Protocol keys and flags broadcast by a Govee device."""

    pact_type: int
    pact_code: int
    broadcast_version: int
    supports_encryption: bool


def parse_govee_advertisement(
    manufacturer_data: Mapping[int, bytes],
) -> GoveeAdvertisement | None:
    """Return the first valid Govee manufacturer-data element."""
    for company_id, payload in manufacturer_data.items():
        if not 0 <= company_id <= 0xFFFF:
            continue
        wire = company_id.to_bytes(2, "little") + bytes(payload)
        if len(wire) < _GOVEE_ADVERTISEMENT_LENGTH or wire[1:3] != _GOVEE_ADVERTISEMENT_MAGIC:
            continue
        return GoveeAdvertisement(
            pact_type=int.from_bytes(wire[3:5], "big"),
            pact_code=wire[5],
            broadcast_version=wire[0] & 0x0F,
            supports_encryption=bool(wire[0] & ADVERTISEMENT_ENCRYPTION_BIT),
        )
    return None
