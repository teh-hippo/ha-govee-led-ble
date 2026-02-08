"""Tests for the scene catalogue."""

from __future__ import annotations

from custom_components.govee_ble_lights.scenes import SCENES, SceneEntry, get_scene_names


def test_scene_count():
    """Catalogue has the expected number of scenes."""
    assert len(SCENES) >= 79


def test_all_entries_are_scene_entry():
    """Every value is a SceneEntry."""
    for key, entry in SCENES.items():
        assert isinstance(entry, SceneEntry), f"{key} is not SceneEntry"


def test_keys_are_lowercase():
    """All keys are lowercase."""
    for key in SCENES:
        assert key == key.lower(), f"{key} is not lowercase"


def test_simple_scenes():
    """Known simple scenes have empty param."""
    simple_names = [
        "sunrise",
        "sunset",
        "rainbow",
        "candlelight",
        "romantic",
        "movie",
        "energetic",
        "twinkle",
        "breathe",
    ]
    for name in simple_names:
        assert name in SCENES, f"Missing simple scene: {name}"
        assert SCENES[name].is_simple, f"{name} should be simple"


def test_complex_scenes():
    """Known complex scenes have non-empty param."""
    complex_names = ["forest", "aurora", "fire", "christmas", "disco"]
    for name in complex_names:
        assert name in SCENES, f"Missing complex scene: {name}"
        assert not SCENES[name].is_simple, f"{name} should be complex"


def test_get_scene_names_sorted():
    """get_scene_names returns sorted list."""
    names = get_scene_names()
    assert names == sorted(names)
    assert len(names) == len(SCENES)


def test_forest_code():
    """Forest has correct scene code."""
    assert SCENES["forest"].code == 2163


def test_rainbow_code():
    """Rainbow has correct simple scene code."""
    assert SCENES["rainbow"].code == 22


def test_no_duplicate_codes_in_simple():
    """Simple scenes have unique codes."""
    simple = [e for e in SCENES.values() if e.is_simple]
    codes = [e.code for e in simple]
    assert len(codes) == len(set(codes))
