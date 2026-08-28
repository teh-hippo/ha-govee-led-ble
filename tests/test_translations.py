"""Consistency checks for the user-facing metadata."""

import ast
import json
from pathlib import Path

_COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "ha_govee_led_ble"
_STRINGS = _COMPONENT / "strings.json"
_EN = _COMPONENT / "translations" / "en.json"


def test_strings_and_en_are_byte_identical():
    assert _STRINGS.read_bytes() == _EN.read_bytes()


def test_effect_category_options_have_direct_labels():
    strings = json.loads(_STRINGS.read_text(encoding="utf-8"))

    assert strings["options"]["step"]["init"]["data"] == {
        "scenes": "Scenes",
        "video": "Video",
        "effects": "Effects",
        "multi_layered": "Multi-Layered",
        "reactive": "Reactive",
        "advanced": "Advanced",
        "prefix_effect_names": 'Prefix effects with their category (e.g., "Scene: Aurora")',
        "always_include_custom_effects": "Always include my custom effects",
    }
    assert "data_description" not in strings["options"]["step"]["init"]


def test_home_assistant_exceptions_declare_translation_metadata():
    missing: list[str] = []
    for path in sorted(_COMPONENT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr
                if isinstance(node.func, ast.Attribute)
                else ""
            )
            if name not in {"HomeAssistantError", "ServiceValidationError"}:
                continue
            keywords = {keyword.arg for keyword in node.keywords}
            if node.args or not {"translation_domain", "translation_key"} <= keywords:
                missing.append(f"{path.name}:{node.lineno}")
    assert missing == []
