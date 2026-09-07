"""Bluetooth discovery matchers for the models this branch adds.

Every assertion goes through Home Assistant's own ``ble_device_matches`` against the real
``manifest.json``, rather than reimplementing the matcher here.
"""

import json
import time
from pathlib import Path

import pytest
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from habluetooth.models import BluetoothServiceInfoBleak
from homeassistant.components.bluetooth.match import ble_device_matches

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, model_from_ble_name

TEST_ADDRESS = "AA:BB:CC:DD:EE:FF"


def make_ble_device(address: str = TEST_ADDRESS) -> BLEDevice:
    return BLEDevice(address, f"Govee_mock_{address}", {})


# The advertisement an H66A0 really broadcasts, as read off the air on 2026-08-23. The
# manufacturer id is not a Bluetooth SIG company: Govee packs its own flags byte into the
# low half, so 0x8843 decodes as flags 0x43 -- broadcast protocol version 3 in bits 0-3, and
# bit 6 set, which is the app's "device supports encryption" bit -- followed by the literal
# 0x88 0xEC magic, pactType 0x0002 and pactCode 0x01. The trailing byte is unidentified.
# Documented in COMMANDS.md section 3.5. The address here is invented.
H66A0_MANUFACTURER_DATA = {0x8843: bytes.fromhex("ec00020101")}


def _service_info(name: str, manufacturer_data: dict[int, bytes] | None = None) -> BluetoothServiceInfoBleak:
    """One advertisement, in the shape Home Assistant's matcher actually consumes."""
    advertisement = AdvertisementData(
        local_name=name,
        manufacturer_data=manufacturer_data or {},
        service_data={},
        service_uuids=[],
        tx_power=None,
        rssi=-59,
        platform_data=(),
    )
    return BluetoothServiceInfoBleak.from_device_and_advertisement_data(
        make_ble_device(), advertisement, "local", time.monotonic(), True
    )


H66A0_ADVERTISEMENT = _service_info("Govee_H66A0_ABCD", H66A0_MANUFACTURER_DATA)


def _manifest_matchers() -> list[dict[str, object]]:
    manifest = Path(__file__).parents[1] / "custom_components" / "ha_govee_led_ble" / "manifest.json"
    return list(json.loads(manifest.read_text())["bluetooth"])


def _matches(service_info: BluetoothServiceInfoBleak) -> bool:
    """Ask Home Assistant's own matcher, rather than reimplementing it here."""
    return any(ble_device_matches(matcher, service_info) for matcher in _manifest_matchers())


@pytest.mark.parametrize(
    "name",
    ["Govee_H66A0_ABCD", "ihoment_H66A0_ABCD", "GBK_H66A0_ABCD", "GVH_H66A0_ABCD"],
)
def test_every_vendor_prefix_of_an_h66a0_is_discovered(name):
    assert _matches(_service_info(name))


def test_the_real_h66a0_advertisement_is_discovered():
    assert _matches(H66A0_ADVERTISEMENT)


@pytest.mark.parametrize(
    "name",
    ["Govee_H617A_ABCD", "ihoment_H617A_ABCD", "Govee_H6199_ABCD", "GVH_H6199_ABCD"],
)
def test_the_existing_models_still_match(name):
    assert _matches(_service_info(name))


def test_an_unrelated_device_is_not_discovered():
    assert not _matches(_service_info("SomeOtherDevice"))


def test_a_discovered_h66a0_resolves_to_the_h66a0_profile():
    """The manifest match is only half of it: the flow aborts on an unresolvable model."""
    assert model_from_ble_name(H66A0_ADVERTISEMENT.name) == "H66A0"
    assert MODEL_PROFILES["H66A0"].state_readable


def test_the_advertisement_flags_byte_says_the_device_wants_encryption():
    """Cross-checks the AD decode against what the device reports over the connection.

    ``aa ef`` on the real device answers ``00 02 01``, the same pactType and pactCode this
    advertisement carries, which is what makes the layout an identification rather than a
    plausible reading. Bit 6 of the flags byte is the app's encryption-support bit
    (BleUtil.parseBleBroadcastPact); this device sets it and does require encryption.
    """
    (company_id,) = H66A0_ADVERTISEMENT.manufacturer_data
    payload = H66A0_ADVERTISEMENT.manufacturer_data[company_id]
    flags, magic_high = company_id & 0xFF, company_id >> 8
    assert (magic_high, payload[0]) == (0x88, 0xEC), "Govee's literal magic"
    assert flags & 0x40, "encryption-support bit"
    assert flags & 0x0F == 3, "broadcast protocol version"
    assert (payload[1] << 8 | payload[2], payload[3]) == (2, 1), "pactType, pactCode -- matches aa ef"


# Parametrised over the models this integration actually declares, so a model added
# later is covered without editing the test.
@pytest.mark.parametrize("sku", sorted(set(MODEL_PROFILES) - {"H617A", "H617E", "H6076", "H6199"}))
def test_each_added_model_is_matched_on_every_vendor_prefix(sku):
    """Enumerated per model, matching the manifest style already here.

    Deliberately NOT a `Govee_*` wildcard. A wildcard would raise a discovery card for every
    Govee BLE device in range, including the ones this integration cannot drive, and the README
    says the integration auto-discovers exact listed models.
    """
    for prefix in ("ihoment", "Govee", "GBK", "GVH"):
        service_info = _service_info(f"{prefix}_{sku}_ABCD")
        assert _matches(service_info)
        assert model_from_ble_name(service_info.name) == sku
