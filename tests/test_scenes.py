"""Tests for the scene catalogue."""

from custom_components.govee_ble_lights.scenes import SCENES, SceneEntry, get_scene_names


def test_scene_count():
    assert len(SCENES) >= 79


def test_all_entries_valid():
    for key, entry in SCENES.items():
        assert isinstance(entry, SceneEntry)
        assert key == key.lower()


def test_simple_scenes():
    for name in ["sunrise", "sunset", "rainbow", "candlelight", "romantic", "movie", "energetic", "twinkle", "breathe"]:
        assert SCENES[name].is_simple, f"{name} should be simple"


def test_complex_scenes():
    for name in ["forest", "aurora", "fire", "christmas", "disco"]:
        assert not SCENES[name].is_simple, f"{name} should be complex"


def test_get_scene_names_sorted():
    names = get_scene_names()
    assert names == sorted(names)
    assert len(names) == len(SCENES)


def test_known_codes():
    assert SCENES["forest"].code == 2163
    assert SCENES["rainbow"].code == 22


def test_no_duplicate_simple_codes():
    codes = [e.code for e in SCENES.values() if e.is_simple]
    assert len(codes) == len(set(codes))
