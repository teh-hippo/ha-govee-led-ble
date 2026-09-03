"""H6179 DIY body and protocol-1.1 A1 command-02 transport tests."""

from __future__ import annotations

import io
import os
import sys
from importlib import import_module
from typing import Any

import pytest
from kaitaistruct import KaitaiStream, KaitaiStructError

from custom_components.ha_govee_led_ble.transport import (
    H6179_A1_02_CHUNK_SIZE,
    H6179_A1_02_MAX_BODY_SIZE,
    H6179_A1_02_MAX_DATA_FRAMES,
    H6179_A1_02_MAX_FRAME_COUNT,
    fragment_a3,
    fragment_h6179_a1_02,
    reassemble_a3,
    reassemble_h6179_a1_02,
    xor_checksum,
)

H = bytes.fromhex

SINGLE_BODY = H("fe00006403ff0000")
MAX_SINGLE_BODY = H("fe02006418000102030405060708090a0b0c0d0e0f1011121314151617")
MIN_MIXED_BODY = H("feff000003000000020000")
MIXED_BODY = H("feff003206ff00000000ff0400000200")
MAX_MIXED_BODY = H("feff006418000102030405060708090a0b0c0d0e0f1011121314151617080000010002000000")

SINGLE_FRAMES = [
    H("a1020001000000000000000000000000000000a2"),
    H("a10201fe00006403ff00000000000000000000c4"),
    H("a102ff000000000000000000000000000000005c"),
]
MAX_MIXED_FRAMES = [
    H("a1020003000000000000000000000000000000a0"),
    H("a10201feff006418000102030405060708090ad4"),
    H("a102020b0c0d0e0f1011121314151617080000a2"),
    H("a1020301000200000000000000000000000000a3"),
    H("a102ff000000000000000000000000000000005c"),
]

_GENERATED_DIR = os.environ.get("KAITAI_GENERATED_DIR")
H6179DiyBody: type[Any] | None = None
if _GENERATED_DIR:
    sys.path.insert(0, _GENERATED_DIR)
    H6179DiyBody = import_module("h6179_diy_body").H6179DiyBody


def _parse_body(data: bytes) -> Any:
    root_type = H6179DiyBody
    if root_type is None:
        pytest.skip("requires a task-local all-schema Kaitai generation")
    stream = KaitaiStream(io.BytesIO(data))
    parsed = root_type(stream)
    parsed._read()
    assert stream.pos() == len(data)
    return parsed


def _round_trip_body(data: bytes) -> Any:
    parsed = _parse_body(data)
    parsed._fetch_instances()
    parsed._check()
    output = KaitaiStream(io.BytesIO(bytes(len(data))))
    parsed._write(output)
    assert output.to_byte_array() == data
    return parsed


def _replace(frame: bytes, offset: int, value: int) -> bytes:
    changed = bytearray(frame)
    changed[offset] = value
    changed[19] = xor_checksum(changed[:19])
    return bytes(changed)


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(SINGLE_BODY, id="minimum single family 0"),
        pytest.param(SINGLE_BODY[:1] + b"\x01" + SINGLE_BODY[2:], id="minimum single family 1"),
        pytest.param(SINGLE_BODY[:1] + b"\x02" + SINGLE_BODY[2:], id="minimum single family 2"),
        pytest.param(MAX_SINGLE_BODY, id="maximum single"),
        pytest.param(MIN_MIXED_BODY, id="minimum mixed"),
        pytest.param(MIXED_BODY, id="mixed"),
        pytest.param(MAX_MIXED_BODY, id="maximum mixed"),
    ],
)
def test_diy_body_vectors_round_trip(body: bytes) -> None:
    _round_trip_body(body)


def test_diy_body_candidate_fields_and_sizes() -> None:
    single = _parse_body(SINGLE_BODY)
    mixed = _parse_body(MIXED_BODY)
    maximum = _parse_body(MAX_MIXED_BODY)

    assert (single.marker, single.family, single.body.variant, single.body.speed, single.body.len_palette) == (
        b"\xfe",
        0,
        0,
        100,
        3,
    )
    assert [(colour.red, colour.green, colour.blue) for colour in single.body.palette.colours] == [(255, 0, 0)]
    assert (mixed.family, mixed.body.variant, mixed.body.speed, mixed.body.mix_bytes) == (0xFF, 0, 50, 4)
    assert [(pair.family, pair.variant) for pair in mixed.body.pairs] == [(0, 0), (2, 0)]
    assert (len(SINGLE_BODY), len(MAX_SINGLE_BODY), len(MIN_MIXED_BODY), len(MAX_MIXED_BODY)) == (8, 29, 11, 38)
    assert (len(maximum.body.palette.colours), len(maximum.body.pairs)) == (8, 4)


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(H("fe03006403ff0000"), id="unknown family"),
        pytest.param(H("fe00016403ff0000"), id="unknown single variant"),
        pytest.param(H("fe00006503ff0000"), id="speed over 100"),
        pytest.param(H("fe00006400"), id="empty palette"),
        pytest.param(H("feff013203ff0000020000"), id="mixed variant"),
        pytest.param(H("feff003203ff000000"), id="empty mix"),
        pytest.param(H("feff003203ff000003000100"), id="partial mix pair"),
        pytest.param(H("feff0000030000000a") + bytes(10), id="over four mix pairs"),
        pytest.param(H("feff003203ff000002ff00"), id="nested mixed family"),
        pytest.param(H("feff003203ff0000020001"), id="unknown component variant"),
        pytest.param(SINGLE_BODY + b"\x01", id="non-zero padding"),
    ],
)
def test_diy_body_preserves_uncertain_values_and_opaque_bytes(body: bytes) -> None:
    _round_trip_body(body)


def test_diy_body_preserves_unknown_family_as_opaque() -> None:
    parsed = _round_trip_body(H("fe7f1020304050"))

    assert parsed.family == 0x7F
    assert parsed.body.data == H("1020304050")


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(H("fd00006403ff0000"), id="wrong marker"),
        pytest.param(H("fe00006402ff00"), id="partial RGB"),
        pytest.param(H("fe00000019") + bytes(25), id="partial final RGB"),
    ],
)
def test_diy_body_rejects_only_fixed_or_structurally_incomplete_data(body: bytes) -> None:
    with pytest.raises(KaitaiStructError):
        _parse_body(body)


def test_a1_02_fragmentation_preserves_exact_vectors() -> None:
    assert fragment_h6179_a1_02(SINGLE_BODY) == SINGLE_FRAMES
    assert fragment_h6179_a1_02(MAX_MIXED_BODY) == MAX_MIXED_FRAMES
    assert len(MAX_MIXED_BODY) == 38
    assert len(MAX_MIXED_FRAMES) == 5
    for frame in (*SINGLE_FRAMES, *MAX_MIXED_FRAMES):
        assert len(frame) == 20
        assert xor_checksum(frame[:19]) == frame[19]


@pytest.mark.parametrize("length", [1, 16, 17, H6179_A1_02_MAX_BODY_SIZE])
def test_a1_02_transport_boundaries_round_trip_deterministically(length: int) -> None:
    body = bytes(index % 251 for index in range(length))
    frames = fragment_h6179_a1_02(body)
    padded = body + bytes(-len(body) % H6179_A1_02_CHUNK_SIZE)

    assert len(frames) == (length + 15) // 16 + 2
    assert reassemble_h6179_a1_02(frames) == padded
    assert fragment_h6179_a1_02(padded) == frames


def test_a1_02_transport_limits_are_explicit() -> None:
    assert H6179_A1_02_CHUNK_SIZE == 16
    assert H6179_A1_02_MAX_DATA_FRAMES == 255
    assert H6179_A1_02_MAX_BODY_SIZE == 4080
    assert H6179_A1_02_MAX_FRAME_COUNT == 257

    with pytest.raises(ValueError, match="non-empty bytes"):
        fragment_h6179_a1_02(b"")
    with pytest.raises(ValueError, match="exceeds 4080 bytes"):
        fragment_h6179_a1_02(bytes(4081))
    with pytest.raises(ValueError, match="exceeds 257 frames"):
        reassemble_h6179_a1_02([bytes(20)] * 258)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda frames: [frames[0][:-1], *frames[1:]], "exactly 20 bytes"),
        (lambda frames: [_replace(frames[0], 0, 0xA3), *frames[1:]], "not an H6179 A1 02 frame"),
        (lambda frames: [_replace(frames[0], 1, 0x03), *frames[1:]], "not an H6179 A1 02 frame"),
        (
            lambda frames: [frames[0][:-1] + bytes([frames[0][-1] ^ 1]), *frames[1:]],
            "invalid checksum",
        ),
        (lambda frames: [_replace(frames[0], 2, 1), *frames[1:]], "no start frame"),
        (lambda frames: [_replace(frames[0], 4, 1), *frames[1:]], "non-zero reserved bytes"),
        (lambda frames: [_replace(frames[0], 3, 0), *frames[1:]], "declares no data frames"),
        (lambda frames: [*frames[:-1], _replace(frames[-1], 2, 2)], "no final frame"),
        (lambda frames: [*frames[:-1], _replace(frames[-1], 3, 1)], "final frame has non-zero"),
    ],
)
def test_a1_02_reassembler_rejects_invalid_frames(mutate, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        reassemble_h6179_a1_02(mutate(SINGLE_FRAMES))


@pytest.mark.parametrize(
    "frames",
    [
        pytest.param([MAX_MIXED_FRAMES[0], *MAX_MIXED_FRAMES[2:]], id="missing"),
        pytest.param(
            [MAX_MIXED_FRAMES[0], MAX_MIXED_FRAMES[1], MAX_MIXED_FRAMES[1], *MAX_MIXED_FRAMES[3:]],
            id="duplicate",
        ),
        pytest.param(
            [MAX_MIXED_FRAMES[0], MAX_MIXED_FRAMES[2], MAX_MIXED_FRAMES[1], *MAX_MIXED_FRAMES[3:]],
            id="reordered",
        ),
    ],
)
def test_a1_02_reassembler_rejects_missing_duplicate_and_reordered_data(frames: list[bytes]) -> None:
    with pytest.raises(ValueError):
        reassemble_h6179_a1_02(frames)


def test_h6179_a1_02_and_a3_are_not_interchangeable() -> None:
    a1_frames = fragment_h6179_a1_02(SINGLE_BODY)
    a3_frames = fragment_a3(0x04, SINGLE_BODY)

    with pytest.raises(ValueError, match="not an H6179 A1 02 frame"):
        reassemble_h6179_a1_02(a3_frames)
    with pytest.raises(ValueError, match="invalid prefix"):
        reassemble_a3(a1_frames)
