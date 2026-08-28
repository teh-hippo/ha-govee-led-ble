"""Capture-backed music parameter tests."""

import pytest

from custom_components.ha_govee_led_ble.music_commands import build_music_params
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
