import json

import pytest

from custom_components.ha_govee_led_ble.protocol import build_scene_multi
from custom_components.ha_govee_led_ble.scenes import SCENES, SceneEntry, get_scene_names
from tools.ble.fetch_effect_library import CATALOGUE_DIR
from tools.ble.generate_scenes import build_runtime_catalogue


def test_catalogue_valid():
    assert len(SCENES) == 83
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
    assert SCENES["aurora b"].code == 16160


def test_scene_type_prefix():
    assert SCENES["halloween"].scene_type == 1 and SCENES["sweet"].scene_type == 1
    assert SCENES["forest"].scene_type == 2
    assert SCENES["sunrise"].scene_type == 0


def test_runtime_catalogue_matches_frozen_snapshot():
    catalogue = json.loads((CATALOGUE_DIR / "effect-library-H617A.json").read_text())
    expected = {
        name: SceneEntry(
            data[0],
            data[1] if len(data) > 1 else "",
            data[2] if len(data) > 2 else 2,
        )
        for name, data in build_runtime_catalogue(catalogue).items()
    }

    assert SCENES == expected


def test_aurora_b_matches_current_ios_capture():
    scene = SCENES["aurora b"]

    assert [packet.hex() for packet in build_scene_multi(scene.param, scene.code, scene.scene_type)] == [
        "a3000109020423400000010201ff1903c20a03e2",
        "a30102e632040fff080b07ff07f8ffff06e9006b",
        "a30202f80100800023420000010001ff1803bbe4",
        "a3030a0382e73204ffd372cb85ff0d4bff52ff01",
        "a304991201cd0003e40023440000010001ff1887",
        "a30503bb0a0302e532040b07ff0fff08ff06e9dd",
        "a30607f8ff1001cc010080002646000001000199",
        "a307ff1803bb0a0302e5320507f8ff0b07ffff2e",
        "a3ff06e90fff08dcff111201dd01008000000036",
        "330504203f00000000000000000000000000002d",
    ]
