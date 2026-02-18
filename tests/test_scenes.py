import pytest

from custom_components.govee_ble_lights.scenes import SCENES, SceneEntry, get_scene_names


def test_catalogue_valid():
    assert len(SCENES) >= 79
    assert all(isinstance(e, SceneEntry) and k == k.lower() for k, e in SCENES.items())
    names = get_scene_names()
    assert names == sorted(names) and len(names) == len(SCENES)
    codes = [e.code for e in SCENES.values() if e.is_simple]
    assert len(codes) == len(set(codes))


_SIMPLE = ["sunrise", "sunset", "rainbow", "candlelight", "romantic", "movie", "energetic", "twinkle", "breathe"]
_COMPLEX = ["forest", "aurora", "fire", "christmas", "disco"]


@pytest.mark.parametrize("name,simple", [*((n, True) for n in _SIMPLE), *((n, False) for n in _COMPLEX)])
def test_scene_type(name, simple):
    assert SCENES[name].is_simple is simple


def test_known_codes():
    assert SCENES["forest"].code == 2163 and SCENES["rainbow"].code == 22
