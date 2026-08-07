"""Consistency checks for the user-facing metadata (strings, translations, icons)."""

import json
from pathlib import Path

_COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "ha_govee_led_ble"
_STRINGS = _COMPONENT / "strings.json"
_EN = _COMPONENT / "translations" / "en.json"
_ICONS = _COMPONENT / "icons.json"


def test_strings_and_en_are_byte_identical():
    assert _STRINGS.read_bytes() == _EN.read_bytes()


def test_entity_translation_keys_have_names():
    entity = json.loads(_STRINGS.read_text())["entity"]
    for platform, entries in entity.items():
        for key, metadata in entries.items():
            assert metadata["name"], f"{platform}.{key} has no name"


def test_every_icon_key_maps_to_a_translation():
    strings = json.loads(_STRINGS.read_text())["entity"]
    icons = json.loads(_ICONS.read_text())["entity"]
    for platform, entries in icons.items():
        for key in entries:
            assert key in strings.get(platform, {}), f"icon {platform}.{key} has no matching translation"
