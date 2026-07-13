import hashlib
import json
from pathlib import Path

import pytest

from tools.ble.fetch_effect_library import CATALOGUE_DIR, catalogue_drift, distil


def test_distil_counts_scene_tiles_separately_from_effect_variants():
    raw = {
        "data": {
            "categories": [
                {
                    "categoryName": "Natural",
                    "scenes": [
                        {
                            "sceneName": "Lightning",
                            "lightEffects": [
                                {"sceneCode": 1, "scenceName": "A", "scenceParam": "one"},
                                {"sceneCode": 2, "scenceName": "B", "scenceParam": "two"},
                            ],
                        },
                        {
                            "sceneName": "Aurora",
                            "lightEffects": [{"sceneCode": 3, "scenceParam": "three"}],
                        },
                    ],
                }
            ]
        }
    }

    catalogue = distil(raw)

    assert catalogue["scene_count"] == 2
    assert catalogue["effect_count"] == 3
    assert [effect.get("variant") for effect in catalogue["scenes"]] == ["A", "B", None]


def test_catalogue_drift_reports_structural_changes():
    expected = {
        "sku": "H617A",
        "scene_count": 2,
        "effect_count": 2,
        "scenes": [
            {"category": "Natural", "name": "Aurora", "code": 1, "param": "one"},
            {"category": "Natural", "name": "Sunrise", "code": 2, "param": ""},
        ],
    }
    current = {
        "sku": "H617A",
        "scene_count": 2,
        "effect_count": 2,
        "scenes": [
            {"category": "Natural", "name": "Aurora", "code": 3, "param": "two"},
            {"category": "Natural", "name": "Sunset", "code": 4, "param": ""},
        ],
    }

    assert catalogue_drift(expected, current) == [
        "removed: Natural / Sunrise",
        "added: Natural / Sunset",
        "changed: Natural / Aurora (code, param)",
    ]


@pytest.mark.parametrize(
    "sku,scene_count,effect_count,digest",
    [
        ("H617A", 80, 83, "1a1e49f46f7735629351d72f82237d09ea3a2033f56c09470a5c7aaeb70bee56"),
        ("H6199", 149, 240, "f8675e1c452dacf655de643db79e0c1542fdcbb3d55ca3365af74b02f0d195bb"),
    ],
)
def test_frozen_catalogue_scope(sku: str, scene_count: int, effect_count: int, digest: str):
    path = Path(CATALOGUE_DIR) / f"effect-library-{sku}.json"
    data = json.loads(path.read_text())

    assert data["sku"] == sku
    assert data["scene_count"] == scene_count
    assert data["effect_count"] == effect_count
    assert catalogue_drift(data, data) == []
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
