"""Capture-backed music parameter tests."""

import pytest

from custom_components.ha_govee_led_ble.generated_protocol_adapter import build_music_mode
from custom_components.ha_govee_led_ble.music_commands import build_h6125_music_params, build_music_params
from custom_components.ha_govee_led_ble.transport import xor_checksum

H = bytes.fromhex

_CAPTURED_BODIES = {
    (0x30, ()): "0102413007ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0a50000000000000",
    (0x30, ((27, 0x14),)): "0102413007ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0a14000000000000",
    (0x31, ((20, 0x14), (21, 0x46))): ("0102413105ff0000ff7f00ffff0000ff000000ff14460a0000000000000000000000"),
    (0x32, ((20, 0x05),)): "0102413205ff7f00ff0000ffff000000ff00ff0005015e0000000000000000000000",
    (0x33, ((29, 0),)): (
        "0103413307ff0000ff7f00ffff0000ff000000ff00ffff8b00ffff000000620103020600000000000000000000000000000000"
    ),
    (0x34, ()): "0102413407ff0000ff7f00ffff0000ff000000ff00ffff8b00ff000f0a0407000000",
    (0x35, ((26, 1), (28, 3))): ("0102413507ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0101035000000000"),
    (0x37, ((26, 7), (27, 0x32))): ("0102413707ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0732000000000000"),
}


def _assemble(frames: list[bytes]) -> bytes:
    for frame in frames:
        assert len(frame) == 20 and xor_checksum(frame[:19]) == frame[19]
    return b"".join(frame[2:19] for frame in frames)


def test_music_parameter_templates_reproduce_captured_bodies() -> None:
    for (mode, overrides), body in _CAPTURED_BODIES.items():
        assert _assemble(build_music_params(mode, dict(overrides))) == H(body)


def test_music_parameter_overlay_changes_only_named_offsets() -> None:
    base = _assemble(build_music_params(0x31, {}))
    changed = _assemble(build_music_params(0x31, {20: 0x14, 21: 0x46}))
    assert [index for index, values in enumerate(zip(base, changed, strict=True)) if values[0] != values[1]] == [20, 21]


def test_music_palette_count_guards_downstream_offsets() -> None:
    with pytest.raises(ValueError, match="palette count"):
        build_music_params(0x32, {}, palette=[(1, 2, 3)])
    assembled = _assemble(build_music_params(0x32, {}, palette=[(1, 2, 3)] * 5))
    assert assembled[5:20] == bytes([1, 2, 3] * 5)
    assert assembled[20] == 1


def test_h6125_basic_music_selectors_use_the_pact_one_layout() -> None:
    assert {mode: build_music_mode(mode, 99, None, False, "H6125") for mode in range(0x10, 0x14)} == {
        0x10: H("3305111063000000000000000000000000000054"),
        0x11: H("3305111163000000000000000000000000000055"),
        0x12: H("3305111263000000000000000000000000000056"),
        0x13: H("3305111363000000000000000000000000000057"),
    }


@pytest.mark.parametrize(
    ("mode", "body"),
    [
        (0x30, "3007ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0a50"),
        (0x31, "3107ff0000ff7f00ffff0000ff000000ff00ffff8b00ff05640a"),
        (0x32, "3207ff0000ff7f00ffff0000ff000000ff00ffff8b00ff030063"),
        (0x33, "3307ff0000ff7f00ffff0000ff000000ff00ffff8b00ff010101196201030614"),
        (0x34, "3407ff0000ff7f00ffff0000ff000000ff00ffff8b00ff000f230107"),
        (0x35, "3507ff0000ff7f00ffff0000ff000000ff00ffff8b00ff01020555"),
        (0x37, "3707ff0000ff7f00ffff0000ff000000ff00ffff8b00ff071400"),
    ],
)
def test_h6125_expanded_music_bodies_use_the_50_ic_formulas(mode: int, body: str) -> None:
    frames = build_h6125_music_params(
        mode,
        calm=False,
        separation_point=3,
        separation_gradient=False,
        hopping_brightness=25,
        piano_key_count=15,
        fountain_direction="clockwise",
        daynight_segments=7,
        daynight_speed=20,
        daynight_gradient=False,
    )
    expected = b"\x01" + bytes([len(frames)]) + b"\x41" + H(body)
    assert _assemble(frames) == expected + bytes(len(frames) * 17 - len(expected))
