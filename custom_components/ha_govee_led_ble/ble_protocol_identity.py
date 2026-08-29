"""Non-identifying protocol metadata derived from BLE advertisements."""

from collections.abc import Mapping

H6125_PACTS = frozenset({(1, 1), (1, 2), (10, 1), (10, 2), (10, 3)})


def h6125_pact_from_manufacturer_data(
    manufacturer_data: Mapping[int, bytes],
) -> tuple[int, int] | None:
    for manufacturer_id, payload in manufacturer_data.items():
        header = manufacturer_id & 0xFF
        if manufacturer_id >> 8 != 0x88 or header & 0x0F < 1:
            continue
        if len(payload) < 4 or payload[0] != 0xEC:
            continue
        pact = int.from_bytes(payload[1:3], "big"), payload[3]
        if pact in H6125_PACTS:
            return pact
    return None
