import base64
import hashlib
import json
from types import SimpleNamespace

import pytest

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, supported_effect_categories
from custom_components.ha_govee_led_ble.native_scenes import apply_scene_speed
from custom_components.ha_govee_led_ble.scenes import SCENE_ENTRIES, _load_speed
from tools.ble.refresh_scene_catalogues import SNAPSHOT_DIR, _snapshot_speed, build_snapshot


def _effect(effect_id: int, code: int, variant: str = "") -> dict[str, object]:
    return {
        "scenceParamId": effect_id,
        "sceneCode": code,
        "scenceName": variant,
        "scenceParam": "",
        "sceneType": 0,
        "specialEffect": [],
        "speedInfo": {},
    }


def test_snapshot_preserves_scene_effect_and_category_identity():
    raw = {
        "status": 200,
        "data": {
            "categories": [
                {
                    "categoryId": 10,
                    "categoryName": "Natural",
                    "scenes": [
                        {
                            "sceneId": 20,
                            "sceneName": "Lightning",
                            "sceneType": 0,
                            "lightEffects": [
                                _effect(30, 1, "A"),
                                _effect(31, 2, "B"),
                            ],
                        }
                    ],
                }
            ]
        },
    }

    snapshot = build_snapshot(raw, "H617A")

    assert snapshot["categories"] == [{"id": 10, "name": "Natural"}]
    assert snapshot["effects"] == [
        {
            "category_id": 10,
            "scene_id": 20,
            "effect_id": 30,
            "name": "Lightning",
            "code": 1,
            "scene_type": 0,
            "variant": "A",
        },
        {
            "category_id": 10,
            "scene_id": 20,
            "effect_id": 31,
            "name": "Lightning",
            "code": 2,
            "scene_type": 0,
            "variant": "B",
        },
    ]


def test_snapshot_resolves_the_requested_sku_override():
    effect = _effect(30, 1)
    effect["specialEffect"] = [
        {
            "supportSku": ["H6199"],
            "scenceParamId": 99,
            "sceneCode": 123,
            "sceneType": 2,
            "scenceParam": "payload",
        }
    ]
    raw = {
        "status": 200,
        "data": {
            "categories": [
                {
                    "categoryId": 10,
                    "categoryName": "Natural",
                    "scenes": [
                        {
                            "sceneId": 20,
                            "sceneName": "Forest",
                            "sceneType": 0,
                            "lightEffects": [effect],
                        }
                    ],
                }
            ]
        },
    }

    entry = build_snapshot(raw, "H6199")["effects"][0]

    assert (entry["effect_id"], entry["code"], entry["scene_type"], entry["param"]) == (
        99,
        123,
        2,
        "payload",
    )
    assert entry["music_code"] == 0


def test_snapshot_rejects_duplicate_vendor_identity():
    effect = _effect(30, 1)
    raw = {
        "status": 200,
        "data": {
            "categories": [
                {
                    "categoryId": 10,
                    "categoryName": "Natural",
                    "scenes": [
                        {
                            "sceneId": 20,
                            "sceneName": "Forest",
                            "sceneType": 0,
                            "lightEffects": [effect, effect],
                        }
                    ],
                }
            ]
        },
    }

    with pytest.raises(ValueError, match="duplicate scene/effect identity"):
        build_snapshot(raw, "H617A")


def _speed_record(*, colour_speed: int = 250, brightness_speed: int = 250):
    return SimpleNamespace(
        body=SimpleNamespace(
            num_brightness_blocks=1,
            selected_area_movement=SimpleNamespace(speed=250),
            overall_movement=SimpleNamespace(speed=250),
            colour_speed=colour_speed,
            brightness_blocks=[SimpleNamespace(brightness_speed=brightness_speed)],
        )
    )


def _speed_effect(config: list[dict[str, object]]) -> dict[str, object]:
    return {
        "sceneCode": 1,
        "sceneType": 2,
        "scenceParam": "unused",
        "speedInfo": {
            "supSpeed": True,
            "config": json.dumps(config),
        },
    }


def test_snapshot_omits_speed_with_an_out_of_range_page(monkeypatch):
    monkeypatch.setattr(
        "tools.ble.refresh_scene_catalogues._parse_scene_records",
        lambda _param: [_speed_record()],
    )
    effect = _speed_effect([{"page": 1, "moveIn": [200, 225, 250], "defaultIndex": 2}])

    with pytest.warns(UserWarning, match="outside 1 records; omitting Speed"):
        assert _snapshot_speed(effect, "Broken page") is None


def test_snapshot_omits_an_unverified_default_rewrite(monkeypatch):
    monkeypatch.setattr(
        "tools.ble.refresh_scene_catalogues._parse_scene_records",
        lambda _param: [_speed_record(brightness_speed=255)],
    )
    effect = _speed_effect(
        [
            {
                "page": 0,
                "bright": [{"brightPage": 0, "brightValue": [204, 229, 250]}],
                "defaultIndex": 2,
            }
        ]
    )

    with pytest.warns(UserWarning, match="does not reproduce the stored scene body"):
        assert _snapshot_speed(effect, "Stale default") is None

    assert _snapshot_speed(effect, "Metadata default", metadata_default_applied=True) == {
        "default_index": 2,
        "pages": [
            {
                "page": 0,
                "brightness": [{"block": 0, "values": [204, 229, 250]}],
            }
        ],
    }


def test_snapshot_uses_h7020_metadata_defaults_without_enabling_other_skus(monkeypatch):
    monkeypatch.setattr(
        "tools.ble.refresh_scene_catalogues._parse_scene_records",
        lambda _param: [
            _speed_record(colour_speed=81),
            _speed_record(brightness_speed=221),
        ],
    )
    effect = _speed_effect(
        [
            {"page": 0, "color": [188, 198, 220], "defaultIndex": 2},
            {
                "page": 1,
                "bright": [{"brightPage": "0", "brightValue": [201, 204, 215]}],
                "defaultIndex": 2,
            },
        ]
    )
    effect.update(
        {
            "scenceParamId": 5591,
            "scenceName": "",
            "specialEffect": [],
        }
    )
    raw = {
        "status": 200,
        "data": {
            "categories": [
                {
                    "categoryId": 223,
                    "categoryName": "Festival",
                    "scenes": [
                        {
                            "sceneId": 5041,
                            "sceneName": "Halloween",
                            "sceneType": 2,
                            "lightEffects": [effect],
                        }
                    ],
                }
            ]
        },
    }

    h7020 = build_snapshot(raw, "H7020")["effects"][0]
    unrelated = build_snapshot(raw, "H6199")["effects"][0]

    assert h7020["speed"] == {
        "default_index": 2,
        "pages": [
            {"page": 0, "colour_speed": [188, 198, 220]},
            {
                "page": 1,
                "brightness": [{"block": 0, "values": [201, 204, 215]}],
            },
        ],
    }
    assert "speed" not in unrelated

    raw["data"]["categories"][0]["scenes"][0]["sceneId"] = 5042
    assert build_snapshot(raw, "H7020")["effects"][0]["speed"] == h7020["speed"]

    speed_info = effect["speedInfo"]
    assert isinstance(speed_info, dict)
    speed_info["config"] = json.dumps([{"page": 2, "color": [188, 198, 220], "defaultIndex": 2}])
    with pytest.warns(UserWarning, match="outside 2 records; omitting Speed"):
        assert "speed" not in build_snapshot(raw, "H7020")["effects"][0]


def test_h6102_candidate_uses_complete_exact_snapshot():
    assert MODEL_PROFILES["H6102"].supports_scenes
    assert "scenes" in supported_effect_categories("H6102")
    assert len(SCENE_ENTRIES["H6102"]) == 240


@pytest.mark.parametrize(
    ("sku", "categories", "effects", "digest"),
    [
        (
            "H601C",
            6,
            66,
            "0f927f46ad370439a00064a9f332ebf650ce5292234f1455f229db6f571baa04",
        ),
        (
            "H6076",
            6,
            110,
            "9ad4449bfa310169928a791ccacf6b052a92a6b4263f6e4038cf13b8283c57b3",
        ),
        (
            "H6102",
            12,
            240,
            "a478385e7356d2d142ec30f08dd2c42ae9725589d95f4eb098271119b7e236c7",
        ),
        (
            "H617A",
            5,
            83,
            "4e76c0bc2057f293ffa73f3540110fb9e978829c0f0d4edde62207a1912c8a35",
        ),
        (
            "H7020",
            4,
            51,
            "f2250fce00ca04ae9cee00526c358d98f25e38e0a87c708d6d1b21a5825f548b",
        ),
        (
            "H617E",
            12,
            240,
            "495fd8cce44d10b821d3e818a0ffeab657eb03b1665fe6301c33d8ba0036c0db",
        ),
        (
            "H6199",
            12,
            240,
            "1a7f371bff44b9524e435eff8f2dfd9b66963bb0158a5164a75c92c83dab68d4",
        ),
    ],
)
def test_committed_snapshot_scope(
    sku: str,
    categories: int,
    effects: int,
    digest: str,
):
    path = SNAPSHOT_DIR / f"{sku}.json"
    data = json.loads(path.read_text(encoding="utf-8"))

    assert len(data["categories"]) == categories
    assert len(data["effects"]) == effects
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest


def test_h7020_snapshot_preserves_the_scene_2983_default_rewrite_contract():
    data = json.loads((SNAPSHOT_DIR / "H7020.json").read_text(encoding="utf-8"))
    effect = next(effect for effect in data["effects"] if effect["code"] == 2983)

    assert effect["param"] == (
        "AiMAAAACAgI1FgHEFBQxFQPGFBQDURQC/38AiwD/AACAAACAACAAAggGAAH/AADdBgUA9AoD/zcHAAAAiwD/AACAAACAAA=="
    )
    assert effect["speed"] == {
        "default_index": 2,
        "pages": [
            {"page": 0, "colour_speed": [188, 198, 220]},
            {
                "page": 1,
                "brightness": [{"block": 0, "values": [201, 204, 215]}],
            },
        ],
    }

    speed = _load_speed(effect["speed"])
    assert speed is not None
    stored = base64.b64decode(effect["param"], validate=True)
    rewritten = apply_scene_speed(stored, speed, speed.default_index)

    assert base64.b64encode(rewritten).decode() == (
        "AiMAAAACAgI1FgHEFBQxFQPGFBQD3BQC/38AiwD/AACAAACAACAAAggGAAH/AADXBgUA9AoD/zcHAAAAiwD/AACAAACAAA=="
    )
    changed = [
        (index, before, after)
        for index, (before, after) in enumerate(zip(stored, rewritten, strict=True))
        if before != after
    ]
    assert changed == [
        (21, 81, 220),
        (47, 221, 215),
    ]
