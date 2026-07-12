from tools.ble.fetch_effect_library import distil


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
