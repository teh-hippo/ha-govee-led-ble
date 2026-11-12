"""H60B2 wire shapes confirmed against hardware on 2026-11-12."""

from custom_components.ha_govee_led_ble.const import device_profile
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_brightness,
    build_power,
    build_segment_colour,
    parse_status,
)

PROFILE = device_profile("H60B2", 1, 1)


def test_profile_requires_legacy_encryption() -> None:
    assert PROFILE.requires_legacy_encryption is True
    assert PROFILE.supports_color_temperature is False
    assert PROFILE.whole_device_mask == 0x07


def test_power_brightness_and_segment_frames() -> None:
    assert build_power(True, "H60B2", profile=PROFILE).hex() == "3301010000000000000000000000000000000033"
    assert build_power(False, "H60B2", profile=PROFILE).hex() == "3301000000000000000000000000000000000032"
    # AA04 carries 0-100, confirmed with aa 04 3a on the device.
    assert build_brightness(58, "H60B2", profile=PROFILE).hex() == "33043a000000000000000000000000000000000d"
    # Head masks: 0x01 bottom, 0x02 middle, 0x04 top, 0x07 whole lamp.
    assert (
        build_segment_colour(0x01, 255, 0, 0, "H60B2", profile=PROFILE).hex()
        == "33051501ff0000000000000001000000000000dc"
    )
    assert (
        build_segment_colour(0x07, 0, 0, 255, "H60B2", profile=PROFILE).hex()
        == "330515010000ff000000000007000000000000da"
    )


def test_captured_status_replies_parse() -> None:
    power = parse_status(bytes.fromhex("aa010100000000000000000000000000000000aa"), "H60B2", profile=PROFILE)
    brightness = parse_status(bytes.fromhex("aa043a0000000000000000000000000000000094"), "H60B2", profile=PROFILE)
    colour = parse_status(bytes.fromhex("aa051500000000000000000000000000000000ba"), "H60B2", profile=PROFILE)
    firmware = parse_status(bytes.fromhex("aa06312e30302e3037000000000000000000009a"), "H60B2", profile=PROFILE)

    assert power is not None and power.body.is_on == 1
    assert brightness is not None and brightness.body.brightness_pct == 58
    assert colour is not None and colour.body.mode.name == "static"
    assert firmware is not None and firmware.body.text == "1.00.07"
