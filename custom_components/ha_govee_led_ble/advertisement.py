"""Non-identifying Govee advertisement Pact and encryption evidence."""

from collections.abc import Mapping
from dataclasses import dataclass

from .govee_encryption import GoveeCryptoError, parse_wire


@dataclass(frozen=True, slots=True)
class GoveeAdvertisement:
    pact_type: int
    pact_code: int
    broadcast_version: int
    supports_encryption: bool


def parse_govee_advertisement(manufacturer_data: Mapping[int, bytes]) -> GoveeAdvertisement | None:
    result = None
    for company_id, payload in manufacturer_data.items():
        if not 0 <= company_id <= 0xFFFF:
            continue
        try:
            parsed = parse_wire("Advertisement", company_id.to_bytes(2, "little") + bytes(payload))
        except GoveeCryptoError:
            continue
        if parsed.magic != b"\x88\xec":
            continue
        result = GoveeAdvertisement(parsed.pact_type, parsed.pact_code, parsed.flags & 0x0F, bool(parsed.flags & 0x40))
        if result.supports_encryption:
            return result
    return result
