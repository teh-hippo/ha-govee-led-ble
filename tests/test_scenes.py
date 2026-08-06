import base64
import json
from typing import Any

import pytest

from custom_components.ha_govee_led_ble.protocol import (
    MOVE_ALL_OFFSET,
    MOVE_IN_OFFSET,
    apply_scene_speed,
    build_scene_multi,
    scene_record_spans,
)
from custom_components.ha_govee_led_ble.scenes import (
    SCENES,
    SceneBrightnessSpeed,
    SceneEntry,
    ScenePage,
    SceneSpeed,
    get_scene_names,
)
from tools.ble.fetch_effect_library import CATALOGUE_DIR
from tools.ble.generate_scenes import build_runtime_catalogue


def test_catalogue_valid():
    assert len(SCENES) == 83
    assert all(isinstance(e, SceneEntry) and k == k.lower() for k, e in SCENES.items())
    names = get_scene_names()
    assert names == sorted(names) and len(names) == len(SCENES)
    codes = [e.code for e in SCENES.values() if e.is_simple]
    assert len(codes) == len(set(codes))
    assert {scene.speed.option_count for scene in SCENES.values() if scene.speed is not None} == {3, 4}


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


def _expected_entry(data: list[Any]) -> SceneEntry:
    speed = None
    if len(data) > 3:
        default_index, pages = data[3]
        speed = SceneSpeed(
            default_index,
            tuple(
                ScenePage(
                    p,
                    tuple(mi),
                    tuple(ma),
                    tuple(colour),
                    tuple(SceneBrightnessSpeed(block, tuple(values)) for block, values in brightness),
                )
                for p, mi, ma, colour, brightness in pages
            ),
        )
    return SceneEntry(data[0], data[1] if len(data) > 1 else "", data[2] if len(data) > 2 else 2, speed)


def test_runtime_catalogue_matches_frozen_snapshot():
    catalogue = json.loads((CATALOGUE_DIR / "effect-library-H617A.json").read_text())
    expected = {name: _expected_entry(data) for name, data in build_runtime_catalogue(catalogue).items()}

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


def test_glacier_speed_default_rewrites_the_stale_param_bytes():
    """Glacier 2175 ships 0xff where its own option list says 250, and the app rewrites it."""
    scene = SCENES["glacier"]
    stored = base64.b64decode(scene.param)
    spans = scene_record_spans(stored)
    assert scene.speed is not None and scene.speed.default_index == 2

    uploaded = apply_scene_speed(stored, scene.speed, scene.speed.default_index)

    for page in scene.speed.pages:
        position = spans[page.page][1] + MOVE_IN_OFFSET
        assert stored[position] == 0xFF and uploaded[position] == 250
    assert sum(before != after for before, after in zip(stored, uploaded, strict=True)) == 2


def test_speed_default_position_reproduces_every_other_stored_param():
    differing = set()
    for name, scene in SCENES.items():
        if scene.speed is None:
            continue
        stored = base64.b64decode(scene.param)
        if apply_scene_speed(stored, scene.speed, scene.speed.default_index) != stored:
            differing.add(name)

    assert differing == {"glacier", "mysterious"}


@pytest.mark.parametrize("index,expected", [(-1, 237), (0, 237), (1, 244), (2, 250), (7, 250)])
def test_speed_position_selects_the_option_list_value(index, expected):
    scene = SCENES["glacier"]
    stored = base64.b64decode(scene.param)
    spans = scene_record_spans(stored)

    uploaded = apply_scene_speed(stored, scene.speed, index)

    assert [uploaded[spans[p.page][1] + MOVE_IN_OFFSET] for p in scene.speed.pages] == [expected, expected]


def test_speed_position_writes_the_overall_movement_byte():
    """Pages carrying moveAll write overall_movement.speed, two bytes from the record end."""
    scene = SCENES["lightning b"]
    stored = base64.b64decode(scene.param)
    spans = scene_record_spans(stored)

    uploaded = apply_scene_speed(stored, scene.speed, 0)

    assert [uploaded[spans[p.page][1] + MOVE_ALL_OFFSET] for p in scene.speed.pages] == [237, 242]
    assert [stored[spans[p.page][1] + MOVE_ALL_OFFSET] for p in scene.speed.pages] == [243, 248]


def test_speed_position_writes_colour_and_brightness_fields():
    """Christmas position zero changes all eight fields named by its three config blocks."""
    scene = SCENES["christmas"]
    assert scene.speed is not None
    stored = base64.b64decode(scene.param)
    uploaded = apply_scene_speed(stored, scene.speed, 0)
    spans = scene_record_spans(stored)

    changed = {offset for offset, (before, after) in enumerate(zip(stored, uploaded, strict=True)) if before != after}
    expected: set[int] = set()
    for page in scene.speed.pages:
        start, stop = spans[page.page]
        if page.move_in:
            expected.add(stop + MOVE_IN_OFFSET)
        if page.move_all:
            expected.add(stop + MOVE_ALL_OFFSET)
        brightness_count = stored[start + 5]
        if page.colour_speed:
            expected.add(start + 7 + brightness_count * 6)
        expected.update(start + 9 + brightness.block * 6 for brightness in page.brightness_speeds)

    assert changed == expected
    assert len(changed) == 8


def test_speed_metadata_includes_colour_and_brightness_only_scenes():
    scene = SCENES["forest"]
    assert scene.speed is not None
    assert scene.speed.pages[0].colour_speed
    assert scene.speed.pages[0].brightness_speeds
    assert SCENES["heartbeat"].speed is None


def test_scene_record_spans_walks_every_type_2_body():
    """Only type-2 params are record containers; Halloween/Sweet (type 1) use another grammar."""
    walked = 0
    for scene in SCENES.values():
        if not scene.param or scene.scene_type != 2:
            continue
        payload = base64.b64decode(scene.param)
        spans = scene_record_spans(payload)
        assert len(spans) == payload[0]
        assert spans[-1][1] == len(payload)
        walked += 1

    assert walked == 72
    assert all(scene.scene_type == 2 for scene in SCENES.values() if scene.speed)


def test_build_scene_multi_uploads_the_corrected_glacier_body():
    scene = SCENES["glacier"]

    verbatim = build_scene_multi(scene.param, scene.code, scene.scene_type)
    corrected = build_scene_multi(scene.param, scene.code, scene.scene_type, scene.speed)

    assert corrected != verbatim
    assert len(corrected) == len(verbatim)
    assert corrected[-1] == verbatim[-1]  # the 33 05 04 activation is untouched


@pytest.mark.parametrize(
    "mutate,message",
    [
        (lambda config: config[0].update(page=99), "has no record"),
        (lambda config: config[1].update(defaultIndex=0), "disagree on defaultIndex"),
        (lambda config: config[0].update(moveIn=[250]), "outside"),
        (lambda config: config[0].update(moveIn=[237, 244, 250, 255]), "option count"),
    ],
)
def test_generator_rejects_a_catalogue_whose_speed_config_stops_resolving(mutate, message):
    catalogue = json.loads((CATALOGUE_DIR / "effect-library-H617A.json").read_text())
    scene = next(s for s in catalogue["scenes"] if s["code"] == 2175)
    mutate(scene["config"])

    with pytest.raises(ValueError, match=message):
        build_runtime_catalogue(catalogue)


def test_generator_rejects_a_speed_config_on_a_non_record_container_body():
    catalogue = json.loads((CATALOGUE_DIR / "effect-library-H617A.json").read_text())
    scene = next(s for s in catalogue["scenes"] if s["code"] == 2175)
    scene["scene_type"] = 1

    with pytest.raises(ValueError, match="only type-2 bodies"):
        build_runtime_catalogue(catalogue)


def test_scene_record_spans_stops_at_a_truncated_record():
    """A body whose last record claims more bytes than remain yields only the whole records."""
    assert scene_record_spans(bytes([2, 3, 0xAA, 0xBB, 0xCC, 9, 0x01])) == [(2, 5)]


def test_apply_scene_speed_skips_a_page_with_no_matching_record():
    payload = bytes([1, 8, *range(8)])
    speed = SceneSpeed(0, (ScenePage(page=4, move_in=(99,)),))

    assert apply_scene_speed(payload, speed, 0) == payload
