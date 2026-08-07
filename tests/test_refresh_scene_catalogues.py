import hashlib
import json

import pytest

from tools.ble.refresh_scene_catalogues import SNAPSHOT_DIR, build_snapshot


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


@pytest.mark.parametrize(
    ("sku", "categories", "effects", "digest"),
    [
        (
            "H617A",
            5,
            83,
            "6625afeddb0d6495abf80bad9f3997909cb837acb6f590cc31c7ad8b8e33444b",
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
