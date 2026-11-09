"""Reconstructed H619A contracts, not hardware confirmation."""

from dataclasses import replace

import pytest

from custom_components.ha_govee_led_ble.const import device_profile
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.effect_catalogue import MODEL_EFFECT_CATALOGUES
from custom_components.ha_govee_led_ble.effect_compiler import compile_application, validate_compiled_geometry
from custom_components.ha_govee_led_ble.effect_domain import BuiltinScene, CatalogueRef, LibraryItem
from custom_components.ha_govee_led_ble.layered_scene import AppliedArea, Distribution, Selection
from custom_components.ha_govee_led_ble.layered_scene_decoder import (
    decode_catalogue_layered_scene,
    decode_layered_scene,
    encode_layered_scene,
)
from custom_components.ha_govee_led_ble.light_commands import (
    build_color_rgb,
    build_color_temp,
    build_segment_brightness,
    build_segment_color_temp,
)
from custom_components.ha_govee_led_ble.music_commands import prepare_music_request
from custom_components.ha_govee_led_ble.native_scenes import build_native_scene_packets
from custom_components.ha_govee_led_ble.scenes import SCENE_ENTRIES
from custom_components.ha_govee_led_ble.transport import reassemble_a3, xor_checksum


def _frame(prefix: str) -> bytes:
    data = bytes.fromhex(prefix).ljust(19, b"\x00")
    return data + bytes((xor_checksum(data),))


def test_static_writes_select_ten_logical_segments_not_twenty_physical_ics():
    assert build_color_rgb(17, 34, 51, "H619A") == _frame("330515011122330000000000ff03")
    assert build_color_temp(4000, "H619A") == _frame("33051501ffffff0fa0ffd5a1ff03")
    assert build_segment_color_temp([10], 4000, "H619A") == _frame("33051501ffffff0fa0ffd5a10002")
    assert build_segment_brightness([10], 37, "H619A") == _frame("33051502250002")
    with pytest.raises(ValueError):
        build_segment_color_temp([11], 4000, "H619A")


@pytest.mark.parametrize(
    ("mode", "code", "tail"),
    [
        ("bloom", 48, "0a50"),
        ("shiny", 49, "05640a"),
        ("separation", 50, "030061"),
        ("hopping", 51, "010101196201030308"),
        ("piano_keys", 52, "000f0a0507"),
        ("fountain", 53, "01010550"),
        ("day_and_night", 55, "0a0a00"),
    ],
)
def test_music_uses_twenty_ic_defaults_and_uploads_before_selector(mode, code, tail):
    writes = prepare_music_request("H619A", mode, 42, None, False, {})
    assert writes[0] == _frame("330101")
    assert writes[-1] == _frame(f"330513{code:02x}2a")
    envelope = reassemble_a3(writes[1:-1])
    expected = bytes((0x41, code, 7)) + bytes.fromhex("ff0000ff7f00ffff0000ff000000ff00ffff8b00ff" + tail)
    assert envelope[2 : 2 + len(expected)] == expected
    assert not any(envelope[2 + len(expected) :])


@pytest.mark.parametrize(
    ("firmware", "hardware", "legacy"),
    [
        (None, None, True),
        ("1.06.00", "1.00.01", True),
        ("1.05.99", "1.00.02", True),
        ("1.06.00", "1.00.02", False),
        ("2.07.01", "2.01.02", False),
    ],
)
def test_scene_revision_conversion_preserves_source_and_uses_physical_geometry(firmware, hardware, legacy):
    profile = device_profile("H619A", 2, 1, firmware=firmware, hardware=hardware)
    entry = next(entry for entry in SCENE_ENTRIES["H619A"] if entry.scene_type == 2)
    scene = decode_catalogue_layered_scene("H619A", entry)
    assert scene is not None
    layer = replace(
        scene.effect.layers[0],
        area=AppliedArea(0, 0),
        selection=Selection(3, 4, 2),
        unknown_flags=0x20,
        distribution=Distribution(3, True),
    )
    authored = replace(scene, effect=replace(scene.effect, layers=(layer,)))
    raw = encode_layered_scene(authored)
    packets = build_native_scene_packets("H619A", entry, canonical_body=raw, profile=profile)
    envelope = reassemble_a3(packets[:-1])
    parsed = decode_layered_scene(authored.template, envelope[3:])
    actual = parsed.effect.layers[0]
    assert actual.selection == (Selection(0, 0, 5) if legacy else layer.selection)
    assert actual.distribution == (Distribution(2, False) if legacy else layer.distribution)
    assert actual.unknown_flags == (0 if legacy else 0x20)
    assert encode_layered_scene(authored) == raw
    assert packets[-1] == _frame(f"330504{entry.code.to_bytes(2, 'little').hex()}")


def test_every_h619a_template_and_scene_compiles_for_each_scene_revision():
    for firmware, hardware in ((None, None), ("1.06.00", "1.00.02")):
        profile = device_profile("H619A", 2, 1, firmware=firmware, hardware=hardware)
        for template in MODEL_EFFECT_CATALOGUES["H619A"].templates:
            compiled = compile_application(
                LibraryItem.new(template.label, template.content),
                "H619A",
                diy_code=getattr(template.content, "native_diy", None) or 24,
                profile=profile,
            )
            assert compiled.packets
        for entry in SCENE_ENTRIES["H619A"]:
            packets = build_native_scene_packets("H619A", entry, profile=profile)
            assert packets[-1] == _frame(f"330504{entry.code.to_bytes(2, 'little').hex()}")
            if entry.speed is not None:
                bodies = {
                    b"".join(build_native_scene_packets("H619A", entry, speed_index=index, profile=profile))
                    for index in range(entry.speed.option_count)
                }
                assert len(bodies) == entry.speed.option_count


def test_prepared_scene_rejects_stale_cached_identity_and_changed_revision(hass):
    profile = device_profile("H619A", 2, 1, firmware="2.07.01", hardware="2.01.02")
    entry = next(entry for entry in SCENE_ENTRIES["H619A"] if entry.scene_type == 2)
    item = LibraryItem.new("Scene", BuiltinScene(CatalogueRef("H619A", entry.scene_id, entry.effect_id)))
    compiled = compile_application(item, "H619A", profile=profile)
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", model="H619A", configuration_url=None)
    coordinator.profile = profile
    coordinator.fw_version, coordinator.hw_version = "2.07.01", "2.01.02"
    with pytest.raises(ValueError, match="scene format changed"):
        validate_compiled_geometry(compiled, coordinator.effect_authorization_profile)
    coordinator._confirmed_identity_fields.update({"fw_version", "hw_version"})
    validate_compiled_geometry(compiled, coordinator.effect_authorization_profile)
    coordinator.hw_version = "1.00.01"
    coordinator._resolve_device_profile()
    with pytest.raises(ValueError, match="scene format changed"):
        validate_compiled_geometry(compiled, coordinator.effect_authorization_profile)


@pytest.mark.parametrize(
    ("selection", "expected"),
    [
        (Selection(0, 0, 40), Selection(0, 0, 10)),
        (Selection(1, 0, 40), Selection(1, 0, 20)),
        (Selection(2, 25, 24), Selection(2, 20, 20)),
        (Selection(3, 30, 30), Selection(3, 20, 18)),
    ],
)
def test_scene_geometry_rewrites_out_of_budget_fields_without_mutating_authored_content(selection, expected):
    profile = device_profile("H619A", 2, 1, firmware="1.06.00", hardware="1.00.02")
    entry = next(entry for entry in SCENE_ENTRIES["H619A"] if entry.scene_type == 2)
    scene = decode_catalogue_layered_scene("H619A", entry)
    assert scene is not None
    layer = replace(scene.effect.layers[0], area=AppliedArea(0, 0), selection=selection)
    layer = replace(
        layer,
        selected_movement=replace(layer.selected_movement, distance=255),
        overall_movement=replace(layer.overall_movement, distance=254),
    )
    authored = replace(scene, effect=replace(scene.effect, layers=(layer,)))
    parsed = decode_layered_scene(scene.template, encode_layered_scene(authored, profile=profile))
    assert parsed.effect.layers[0].selection == expected
    assert parsed.effect.layers[0].selected_movement.distance == 18
    assert parsed.effect.layers[0].overall_movement.distance == 18
    assert authored.effect.layers[0] == layer
