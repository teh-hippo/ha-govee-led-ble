import base64
from collections import Counter
from typing import cast

import pytest
from kaitaistruct import KaitaiStructError

from custom_components.ha_govee_led_ble.generated_protocol.scene_body import SceneBody
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    _check_tree,
    _write,
    build_h617a_scene,
    parse_scene_body_param,
)
from custom_components.ha_govee_led_ble.layered_scene import CatalogueRef
from custom_components.ha_govee_led_ble.layered_scene_decoder import decode_layered_scene
from custom_components.ha_govee_led_ble.native_scenes import (
    apply_scene_speed,
    build_native_scene_packets,
)
from custom_components.ha_govee_led_ble.scenes import (
    MODEL_SCENES,
    SCENE_ENTRIES,
    SCENES,
    SceneEntry,
    ScenePage,
    SceneSpeed,
)
from custom_components.ha_govee_led_ble.transport import fragment_a3


def _decode_layered(payload: bytes):
    return decode_layered_scene(CatalogueRef("H617A", 0, 0), payload)


def test_catalogue_valid():
    assert len(SCENES) == 83
    assert all(isinstance(e, SceneEntry) and k == k.lower() for k, e in SCENES.items())
    names = sorted(SCENES)
    assert names == sorted(names) and len(names) == len(SCENES)
    codes = [e.code for e in SCENES.values() if not e.param]
    assert len(codes) == len(set(codes))
    assert {scene.speed.option_count for scene in SCENES.values() if scene.speed is not None} == {3, 4}


_SIMPLE = ["sunrise", "sunset", "rainbow", "candlelight", "romantic", "movie", "energetic", "twinkle", "breathe"]
_COMPLEX = ["forest", "aurora", "fire", "christmas", "disco"]


def test_scene_type_examples():
    assert all(not SCENES[name].param for name in _SIMPLE)
    assert all(SCENES[name].param for name in _COMPLEX)


def test_known_codes():
    assert SCENES["forest"].code == 2163 and SCENES["rainbow"].code == 22
    assert SCENES["aurora b"].code == 16160


def test_scene_type_prefix():
    assert SCENES["halloween"].scene_type == 1 and SCENES["sweet"].scene_type == 1
    assert SCENES["forest"].scene_type == 2
    assert SCENES["sunrise"].scene_type == 0


def test_per_model_snapshots_preserve_vendor_identity():
    assert len(SCENE_ENTRIES["H6125"]) == 240
    assert len(SCENE_ENTRIES["H617A"]) == 83
    assert len(SCENE_ENTRIES["H6199"]) == 240
    assert len({(scene.scene_id, scene.effect_id) for scene in SCENE_ENTRIES["H6125"]}) == 240
    assert len({(scene.scene_id, scene.effect_id) for scene in SCENE_ENTRIES["H6199"]}) == 240
    assert MODEL_SCENES["H6125"]["universe-a"].effect_id == 6355
    assert MODEL_SCENES["H6125"]["universe-a"].param != MODEL_SCENES["H6199"]["universe-a"].param
    assert MODEL_SCENES["H6199"]["dracarys"].category == "House of the Dragon"
    assert MODEL_SCENES["H6199"]["green reign"].code == 16183
    assert MODEL_SCENES["H6199"]["fire & blood"].code == 16184
    assert {"flash [emotion]", "flash [zootopia 2]"} <= MODEL_SCENES["H6199"].keys()


def test_aurora_b_matches_current_ios_capture():
    scene = SCENES["aurora b"]

    assert [packet.hex() for packet in build_native_scene_packets("H617A", scene)] == [
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
    assert scene.speed is not None and scene.speed.default_index == 2

    uploaded = apply_scene_speed(stored, scene.speed, scene.speed.default_index)
    stored_scene = _decode_layered(stored)
    uploaded_scene = _decode_layered(uploaded)

    for page in scene.speed.pages:
        assert stored_scene.effect.layers[page.page].selected_movement.speed == 0xFF
        assert uploaded_scene.effect.layers[page.page].selected_movement.speed == 250
    assert sum(before != after for before, after in zip(stored, uploaded, strict=True)) == 2


def test_speed_default_position_reproduces_every_other_stored_param():
    differing = set()
    for name, scene in SCENES.items():
        if scene.speed is None:
            continue
        stored = base64.b64decode(scene.param)
        if apply_scene_speed(stored, scene.speed, scene.speed.default_index) != stored:
            differing.add(name)

    assert differing == {"glacier"}


@pytest.mark.parametrize("index,expected", [(-1, 237), (0, 237), (1, 244), (2, 250), (7, 250)])
def test_speed_position_selects_the_option_list_value(index, expected):
    scene = SCENES["glacier"]
    stored = base64.b64decode(scene.param)
    uploaded = apply_scene_speed(stored, scene.speed, index)
    decoded = _decode_layered(uploaded)

    assert [decoded.effect.layers[page.page].selected_movement.speed for page in scene.speed.pages] == [
        expected,
        expected,
    ]


def test_speed_position_writes_the_overall_movement_byte():
    """Pages carrying moveAll write overall_movement.speed, two bytes from the record end."""
    scene = SCENES["lightning b"]
    stored = base64.b64decode(scene.param)
    uploaded = apply_scene_speed(stored, scene.speed, 0)
    original = _decode_layered(stored)
    decoded = _decode_layered(uploaded)

    assert [decoded.effect.layers[page.page].overall_movement.speed for page in scene.speed.pages] == [237, 242]
    assert [original.effect.layers[page.page].overall_movement.speed for page in scene.speed.pages] == [243, 248]


def test_speed_position_writes_colour_and_brightness_fields():
    """Christmas position zero changes all eight fields named by its three config blocks."""
    scene = SCENES["christmas"]
    assert scene.speed is not None
    stored = base64.b64decode(scene.param)
    uploaded = apply_scene_speed(stored, scene.speed, 0)
    decoded = _decode_layered(uploaded)
    changed = 0
    for page in scene.speed.pages:
        if page.move_in:
            assert decoded.effect.layers[page.page].selected_movement.speed == page.move_in[0]
            changed += 1
        if page.move_all:
            assert decoded.effect.layers[page.page].overall_movement.speed == page.move_all[0]
            changed += 1
        if page.colour_speed:
            assert decoded.effect.layers[page.page].colour_speed == page.colour_speed[0]
            changed += 1
        for brightness in page.brightness_speeds:
            assert (
                decoded.effect.layers[page.page].brightness_patterns[brightness.block].change_speed
                == brightness.values[0]
            )
            changed += 1

    assert changed == 8


def test_speed_metadata_includes_colour_and_brightness_only_scenes():
    scene = SCENES["forest"]
    assert scene.speed is not None
    assert scene.speed.pages[0].colour_speed
    assert scene.speed.pages[0].brightness_speeds
    assert SCENES["mysterious"].speed is None
    assert SCENES["heartbeat"].speed is None


def test_native_scene_packets_upload_the_corrected_glacier_body():
    scene = SCENES["glacier"]

    verbatim = [*fragment_a3(scene.scene_type, base64.b64decode(scene.param)), build_h617a_scene(scene.code)]
    corrected = build_native_scene_packets("H617A", scene)

    assert corrected != verbatim
    assert len(corrected) == len(verbatim)
    assert corrected[-1] == verbatim[-1]  # the 33 05 04 activation is untouched


def test_apply_scene_speed_skips_a_page_with_no_matching_record():
    payload = base64.b64decode(SCENES["forest"].param)
    speed = SceneSpeed(0, (ScenePage(page=4, move_in=(99,)),))

    assert apply_scene_speed(payload, speed, 0) == payload


def test_scene_speed_capability_matches_physical_model_behaviour():
    glacier = SCENES["glacier"]
    assert glacier.speed is not None
    assert glacier.speed.pages[0].move_in == (237, 244, 250)
    assert all(entry.speed is None for entry in SCENE_ENTRIES["H6125"])
    assert all(entry.speed is None for entry in SCENE_ENTRIES["H6199"])


def test_generated_scene_body_parser_round_trips_type_2_catalogues():
    scene_counts: Counter[str] = Counter()
    record_count = 0

    assert SCENE_ENTRIES["H617E"] is SCENE_ENTRIES["H617A"]
    for sku in ("H6125", "H617A", "H6199"):
        entries = SCENE_ENTRIES[sku]
        for entry in entries:
            if entry.scene_type != int(SceneBody.SceneType.scene_v2):
                continue
            raw_param = base64.b64decode(entry.param, validate=True)
            parsed = parse_scene_body_param(raw_param)
            envelope = cast(bytes, parsed._io.to_byte_array())
            header_length = len(parsed.header.marker) + 1
            parameter_start = header_length + 1

            assert parsed.scene_type is SceneBody.SceneType.scene_v2
            assert len(parsed.records) == int(parsed.num_records)
            assert envelope[parameter_start : parameter_start + len(raw_param)] == raw_param
            assert not any(envelope[parameter_start + len(raw_param) :])
            _check_tree(parsed)
            assert _write(parsed, len(envelope)) == envelope

            scene_counts[sku] += 1
            record_count += len(parsed.records)

    assert scene_counts == {"H6125": 226, "H617A": 72, "H6199": 226}
    assert record_count == 1535


@pytest.mark.parametrize("raw_param", [bytearray(b"\x00"), memoryview(b"\x00"), "\x00"])
def test_generated_scene_body_parser_requires_bytes(raw_param):
    with pytest.raises(TypeError, match="must be bytes"):
        parse_scene_body_param(raw_param)


@pytest.mark.parametrize("raw_param", [b"", b"\x01", b"\x01\x20"])
def test_generated_scene_body_parser_rejects_truncated_parameters(raw_param):
    with pytest.raises(KaitaiStructError):
        parse_scene_body_param(raw_param)
