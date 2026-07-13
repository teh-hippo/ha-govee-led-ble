"""Consistency checks for the user-facing metadata (strings, translations, icons)."""

import json
from pathlib import Path

_COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "ha_govee_led_ble"
_STRINGS = _COMPONENT / "strings.json"
_EN = _COMPONENT / "translations" / "en.json"
_ICONS = _COMPONENT / "icons.json"


def test_strings_and_en_are_byte_identical():
    assert _STRINGS.read_bytes() == _EN.read_bytes()


def test_set_white_brightness_is_brightness_not_balance():
    service = json.loads(_STRINGS.read_text())["services"]["set_white_brightness"]
    assert service["name"] == "Set white brightness"
    assert service["fields"]["brightness"]["name"] == "Brightness"
    assert "balance" not in json.dumps(service).lower()


def test_entity_translation_keys_have_names():
    entity = json.loads(_STRINGS.read_text())["entity"]
    expected = {
        "image": {"effect_preview"},
        "number": {"sleep_timer_duration", "music_sensitivity", "music_daynight_speed"},
        "select": {"music_style", "music_fountain_direction", "video_capture_region"},
        "sensor": {"active_mode"},
        "switch": {"effect_preview_reduce_motion", "poweroff_memory", "sleep_timer", "wakeup_timer"},
        "time": {"wakeup_time"},
    }
    for platform, keys in expected.items():
        section = entity[platform]
        for key in keys:
            assert key in section, f"{platform}.{key} missing from strings.json"
            assert section[key]["name"], f"{platform}.{key} has no name"


def test_every_icon_key_maps_to_a_translation():
    strings = json.loads(_STRINGS.read_text())["entity"]
    icons = json.loads(_ICONS.read_text())["entity"]
    for platform, entries in icons.items():
        for key in entries:
            assert key in strings.get(platform, {}), f"icon {platform}.{key} has no matching translation"


def test_custom_effect_validation_errors_are_translated():
    exceptions = json.loads(_STRINGS.read_text())["exceptions"]
    keys = {
        "too_many_segments",
        "bad_rgb",
        "too_many_segment_brightness",
        "segment_brightness_range",
        "vibrant_stops_range",
        "vibrant_bad_rgb",
        "sketch_bad_background",
        "sketch_motion_invalid",
        "sketch_speed_range",
        "sketch_brightness_range",
        "flat_family_variant_invalid",
        "flat_speed_range",
        "palette_too_large",
        "flat_bad_rgb",
        "combo_variant_range",
        "combo_speed_range",
        "combo_too_many",
        "combo_family_variant_invalid",
        "combo_bad_rgb",
    }
    assert keys <= exceptions.keys()
