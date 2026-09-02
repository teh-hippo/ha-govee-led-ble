from custom_components.ha_govee_led_ble.ble_protocol_identity import h6125_pact_from_manufacturer_data


def test_h6125_pact_from_manufacturer_data():
    assert h6125_pact_from_manufacturer_data({0x8801: b"\xec\x00\x0a\x01"}) == (10, 1)
    assert h6125_pact_from_manufacturer_data({0x8842: b"\xec\x00\x01\x02"}) == (1, 2)


def test_h6125_pact_rejects_unknown_or_malformed_advertisements():
    assert h6125_pact_from_manufacturer_data({0x8800: b"\xec\x00\x0a\x01"}) is None
    assert h6125_pact_from_manufacturer_data({0x8801: b"\x00\x00\x0a\x01"}) is None
    assert h6125_pact_from_manufacturer_data({0x8801: b"\xec\x00\x0a"}) is None
    assert h6125_pact_from_manufacturer_data({0x8801: b"\xec\x00\x0b\x01"}) is None
