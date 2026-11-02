"""Non-identifying Govee advertisement Pact and encryption evidence."""

from collections.abc import Mapping
from dataclasses import dataclass

from .govee_encryption import GoveeCryptoError, parse_wire


@dataclass(frozen=True, slots=True)
class GoveeAdvertisement:
    pacts: frozenset[tuple[int, int]]
    supports_encryption: bool
    supports_plaintext: bool
    invalid_version_seen: bool


def parse_govee_advertisement(manufacturer_data: Mapping[int, bytes]) -> GoveeAdvertisement | None:
    pacts: set[tuple[int, int]] = set()
    supports_encryption = supports_plaintext = invalid_version_seen = found = False
    for company_id, payload in manufacturer_data.items():
        if not 0 <= company_id <= 0xFFFF:
            continue
        try:
            parsed = parse_wire("Advertisement", company_id.to_bytes(2, "little") + bytes(payload))
        except GoveeCryptoError:
            continue
        if parsed.magic != b"\x88\xec":
            continue
        found = True
        encrypted = bool(parsed.flags & 0x40)
        supports_encryption |= encrypted
        if parsed.broadcast_version == 0:
            invalid_version_seen = True
            continue
        pacts.add((parsed.pact_type, parsed.pact_code))
        supports_plaintext |= not encrypted
    if not found:
        return None
    return GoveeAdvertisement(frozenset(pacts), supports_encryption, supports_plaintext, invalid_version_seen)
