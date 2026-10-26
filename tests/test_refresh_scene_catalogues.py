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


@pytest.mark.parametrize("sku", ["H60A1", "H7020", "H7025"])
def test_snapshot_uses_metadata_defaults_without_enabling_other_skus(monkeypatch, sku):
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

    metadata_entry = build_snapshot(raw, sku)["effects"][0]
    unrelated = build_snapshot(raw, "H6199")["effects"][0]

    assert metadata_entry["speed"] == {
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
    assert build_snapshot(raw, sku)["effects"][0]["speed"] == metadata_entry["speed"]

    speed_info = effect["speedInfo"]
    assert isinstance(speed_info, dict)
    speed_info["config"] = json.dumps([{"page": 2, "color": [188, 198, 220], "defaultIndex": 2}])
    with pytest.warns(UserWarning, match="outside 2 records; omitting Speed"):
        assert "speed" not in build_snapshot(raw, sku)["effects"][0]


def _native_speed_effect(config: dict[str, object]) -> dict[str, object]:
    effect = _speed_effect([])
    effect.update(
        {
            "sceneType": 5,
            "diyEffectCode": [797],
            "speedInfo": {"supSpeed": True, "speedIndex": 0, "config": json.dumps(config)},
        }
    )
    return effect


def test_snapshot_native_speed_preserves_rows_and_metadata_default(monkeypatch):
    monkeypatch.setattr(
        "tools.ble.refresh_scene_catalogues._parse_native_scene_layers",
        lambda _param: [SimpleNamespace(body=SimpleNamespace(speed=50)) for _ in range(2)],
    )
    monkeypatch.setattr(
        "tools.ble.refresh_scene_catalogues._parse_scene_records",
        lambda _param: pytest.fail("native DIY must not use SceneBody"),
    )
    effect = _native_speed_effect({"defSpeedIndex": 1, "speeds": [[74, 47], [85, 58], [93, 70]]})

    assert _snapshot_speed(effect, "Firefly") == {
        "default_index": 1,
        "layer_speeds": [[74, 47], [85, 58], [93, 70]],
    }


@pytest.mark.parametrize(
    ("config", "message"),
    [
        ({"defSpeedIndex": 3, "speeds": [[65, 65], [85, 85], [100, 100]]}, "default Speed position"),
        ({"defSpeedIndex": 1, "speeds": [[65], [85], [100]]}, "each contain 2 layer values"),
        ({"defSpeedIndex": 1, "speeds": [[65, 65], [85], [100, 100]]}, "each contain 2 layer values"),
        ({"defSpeedIndex": 0, "speeds": [[]]}, "non-empty option rows"),
    ],
)
def test_snapshot_native_speed_rejects_invalid_rows_and_default(monkeypatch, config, message):
    monkeypatch.setattr(
        "tools.ble.refresh_scene_catalogues._parse_native_scene_layers",
        lambda _param: [SimpleNamespace(body=SimpleNamespace(speed=50)) for _ in range(2)],
    )

    with pytest.raises(ValueError, match=message):
        _snapshot_speed(_native_speed_effect(config), "Invalid native Speed")


def test_snapshot_native_speed_rejects_missing_family_and_opaque_layers(monkeypatch):
    effect = _native_speed_effect({"defSpeedIndex": 0, "speeds": [[65]]})
    effect["diyEffectCode"] = []
    with pytest.raises(ValueError, match="native DIY family metadata"):
        _snapshot_speed(effect, "Missing family")

    effect["diyEffectCode"] = [797]
    monkeypatch.setattr(
        "tools.ble.refresh_scene_catalogues._parse_native_scene_layers",
        lambda _param: [SimpleNamespace(body=SimpleNamespace(data=b"opaque"))],
    )
    with pytest.raises(ValueError, match="without a known speed field"):
        _snapshot_speed(effect, "Opaque layer")


def test_snapshot_keeps_native_routing_metadata_without_a_duplicate_body():
    effect = _effect(28629, 24001, "B")
    effect.update({"sceneType": 5, "diyEffectCode": [797], "scenceParam": "UCA=", "diyEffectStr": "UCA="})
    bodyless = _effect(47845, 25023)
    bodyless["sceneType"] = 5
    raw = {
        "status": 200,
        "data": {
            "categories": [
                {
                    "categoryId": 10,
                    "categoryName": "Natural",
                    "scenes": [
                        {"sceneId": 20, "sceneName": "Halloween", "lightEffects": [effect]},
                        {"sceneId": 35521, "sceneName": "Windy Day", "lightEffects": [bodyless]},
                    ],
                }
            ]
        },
    }

    entries = build_snapshot(raw, "H60A6")["effects"]

    assert entries[0]["diy_effect_codes"] == [797]
    assert entries[0]["param"] == "UCA="
    assert "diy_effect_str" not in entries[0]
    assert entries[1] == {
        "category_id": 10,
        "scene_id": 35521,
        "effect_id": 47845,
        "name": "Windy Day",
        "code": 25023,
        "scene_type": 5,
    }


def test_h60a6_snapshot_speed_rows_match_generated_native_layers():
    data = json.loads((SNAPSHOT_DIR / "H60A6.json").read_text(encoding="utf-8"))
    for entry in data["effects"]:
        if "speed" not in entry:
            continue
        speed = entry["speed"]
        effect = _native_speed_effect({"defSpeedIndex": speed["default_index"], "speeds": speed["layer_speeds"]})
        effect["scenceParam"] = entry["param"]
        effect["diyEffectCode"] = entry["diy_effect_codes"]

        assert _snapshot_speed(effect, entry["name"]) == speed


def test_h6102_candidate_uses_complete_exact_snapshot():
    assert MODEL_PROFILES["H6102"].supports_scenes
    assert "scenes" in supported_effect_categories("H6102")
    assert len(SCENE_ENTRIES["H6102"]) == 240


@pytest.mark.parametrize(
    ("sku", "categories", "effects", "digest"),
    [
        (
            "H60A1",
            5,
            79,
            "dfcf82121c2ca2ec446eb4ab72e798a32a612011229de9488c49992d91910529",
        ),
        (
            "H60A6",
            5,
            86,
            "be6a65d128cc68ee26e43df3dbfdcec4bcdee20638a9c287f1681ee0d29fa43c",
        ),
        (
            "H601C",
            6,
            66,
            "ef2a741a2adb962b299af393fda1c767898ca3097c5362cab574e7da70d1d07a",
        ),
        (
            "H6076",
            6,
            110,
            "a2fe1e022e8eb96c5786ebc380e4f3dcfff6fcc99b8644ab28a6ebae0cf9e8c3",
        ),
        (
            "H6102",
            12,
            240,
            "f0e6a21684b4a901e02298f3cfc016825a41b515ff8ab871e4926af590c6872b",
        ),
        (
            "H617A",
            5,
            83,
            "234f1a697106e4551a45e472b410910481ac15438f93470176be81a1bd4d2a81",
        ),
        (
            "H7020",
            4,
            51,
            "b757b37f971212b57510f5630eb6d20006cb9556b52cb267391e61a88551786e",
        ),
        (
            "H7025",
            7,
            114,
            "98df5e6f817b8f7a17d0126d9ee49cdbdfa3a3fdc04558ef62b150e6f9e174f0",
        ),
        (
            "H617E",
            12,
            240,
            "e1e33e70e6e41301d09189f52bd307f9fd2ace3483de87f92280666f87674657",
        ),
        (
            "H6199",
            12,
            240,
            "f3f8622a5b3f7aba0ab257c7377fea2f7a9b42f5bed5ce4918b2e4e502f6d8b5",
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
