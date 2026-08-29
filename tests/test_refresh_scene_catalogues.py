import hashlib
import json
from types import SimpleNamespace

import pytest

from tools.ble.refresh_scene_catalogues import (
    DEFAULT_SKUS,
    SNAPSHOT_DIR,
    _resolved_effect,
    _snapshot_speed,
    build_snapshot,
)


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
    speed_info = {
        "supSpeed": True,
        "config": '[{"page":0,"moveIn":[200,225,250],"defaultIndex":2}]',
    }
    effect["specialEffect"] = [
        {
            "supportSku": ["H6199"],
            "scenceParamId": 99,
            "sceneCode": 123,
            "sceneType": 2,
            "scenceParam": "payload",
            "speedInfo": speed_info,
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
    assert _resolved_effect(effect, "H6199")["speedInfo"] == speed_info


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


def _speed_record(*, brightness_speed: int = 250):
    return SimpleNamespace(
        body=SimpleNamespace(
            num_brightness_blocks=1,
            selected_area_movement=SimpleNamespace(speed=250),
            overall_movement=SimpleNamespace(speed=250),
            colour_speed=250,
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

    assert _snapshot_speed(effect, "Captured rewrite", allow_default_rewrite=True) == {
        "default_index": 2,
        "pages": [
            {
                "page": 0,
                "brightness": [{"block": 0, "values": [204, 229, 250]}],
            }
        ],
    }


@pytest.mark.parametrize(
    ("sku", "categories", "effects", "digest"),
    [
        (
            "H6125",
            12,
            240,
            "bbc6ea0e5b7a8b68b66bf703fa21f0ec73816123b0f294bf994baacc57d7186d",
        ),
        (
            "H617A",
            5,
            83,
            "4e76c0bc2057f293ffa73f3540110fb9e978829c0f0d4edde62207a1912c8a35",
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


def test_default_refresh_scope_includes_each_committed_product_catalogue():
    assert DEFAULT_SKUS == ("H6125", "H617A", "H6199")
