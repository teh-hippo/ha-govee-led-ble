"""H60B2 wire shapes confirmed against hardware on 2026-11-12."""

from custom_components.ha_govee_led_ble.const import device_profile, supported_effect_categories
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_brightness,
    build_power,
    build_segment_colour,
    parse_status,
    require_profile_packet,
)
from custom_components.ha_govee_led_ble.native_scenes import build_native_scene_packets
from custom_components.ha_govee_led_ble.scenes import MODEL_SCENES

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


def _scene(name: str):
    return next(entry for entry in MODEL_SCENES["H60B2"].values() if entry.name == name)


def test_native_scene_packets_match_hardware_verified_frames() -> None:
    rainbow = build_native_scene_packets("H60B2", _scene("Rainbow"), profile=PROFILE)
    assert [p.hex() for p in rainbow] == ["3305041600000000000000000000000000000024"]

    fire = build_native_scene_packets("H60B2", _scene("Fire"), profile=PROFILE)
    assert len(fire) == 4
    assert fire[0].hex() == "a3000103020120000000030201ff7f01ff1414fc"
    assert fire[-1].hex() == "3305045336000000000000000000000000000057"


def test_every_scene_packet_passes_profile_validation() -> None:
    for name in ("Rainbow", "Fire", "Christmas Tree"):
        for packet in build_native_scene_packets("H60B2", _scene(name), profile=PROFILE):
            require_profile_packet(packet, PROFILE)
    for packet in (
        build_power(True, "H60B2", profile=PROFILE),
        build_brightness(58, "H60B2", profile=PROFILE),
        *(build_segment_colour(mask, 255, 0, 0, "H60B2", profile=PROFILE) for mask in (0x01, 0x02, 0x04)),
    ):
        require_profile_packet(packet, PROFILE)


def test_per_head_masks_each_have_a_colour_frame() -> None:
    assert (
        build_segment_colour(0x02, 0, 255, 0, "H60B2", profile=PROFILE).hex()
        == "3305150100ff00000000000002000000000000df"
    )
    assert (
        build_segment_colour(0x04, 0, 0, 255, "H60B2", profile=PROFILE).hex()
        == "330515010000ff000000000004000000000000d9"
    )


def test_only_catalogue_scenes_are_exposed() -> None:
    assert supported_effect_categories("H60B2", profile=PROFILE) == ("scenes",)
    assert PROFILE.supports_custom_effects is False
    assert PROFILE.supports_music_mode is False
    assert PROFILE.supports_video_mode is False
    assert PROFILE.supports_multi_layered_effects is False
    assert PROFILE.supports_advanced_effects is False
    assert PROFILE.command_operations == frozenset({"power", "brightness", "static", "scene", "effect_upload"})


def test_native_scene_application_is_authorized() -> None:
    from custom_components.ha_govee_led_ble.effect_compiler import require_native_scenes

    require_native_scenes("H60B2", PROFILE)


def test_per_head_brightness_frames() -> None:
    from custom_components.ha_govee_led_ble.light_commands import build_segment_brightness_packets

    assert PROFILE.supports_segment_brightness
    assert [p.hex() for p in build_segment_brightness_packets([2], 15, "H60B2", profile=PROFILE)] == [
        "330515020f02000000000000000000000000002c"
    ]
    assert [p.hex() for p in build_segment_brightness_packets([1, 2, 3], 100, "H60B2", profile=PROFILE)] == [
        "3305150264070000000000000000000000000042"
    ]
