"""Transport checksum and A3 fragmentation tests."""

import pytest

from custom_components.ha_govee_led_ble.transport import (
    fragment_a3,
    reassemble_a3,
    xor_checksum,
)

H = bytes.fromhex


def _assert_valid(frame: bytes) -> None:
    assert len(frame) == 20
    assert xor_checksum(frame[:19]) == frame[19]


def test_xor_checksum() -> None:
    assert xor_checksum(bytes(19)) == 0
    assert xor_checksum(bytearray([0x33, 0x01, 0x01] + [0] * 16)) == 0x33
    assert xor_checksum(bytearray([0xAA, 0x01] + [0] * 17)) == 0xAB


def test_a3_fragmentation_preserves_captured_forms() -> None:
    frames = fragment_a3(0x02, bytes(20))
    assert frames == [
        H("a3000102020000000000000000000000000000a2"),
        H("a3ff00000000000000000000000000000000005c"),
    ]
    single = fragment_a3(0x04, H("010064038b00ff"))
    assert single == [
        H("a300010204010064038b00ff00000000000000b6"),
        H("a3ff00000000000000000000000000000000005c"),
    ]
    for frame in (*frames, *single):
        _assert_valid(frame)


@pytest.mark.parametrize("terminator", [False, True])
def test_a3_reassembly_uses_line_count_not_the_final_index(terminator: bool) -> None:
    for length in range(120):
        frames = fragment_a3(0x02, bytes(length), terminator=terminator)
        body = b"".join(frame[2:19] for frame in frames)
        assert body[0] == 0x01
        assert len(body) == body[1] * 17
        assert body[1] >= 2


def test_plain_final_frame_can_carry_data() -> None:
    frames = fragment_a3(0x02, bytes(range(1, 81)))
    assert [frame[1] for frame in frames] == [0, 1, 2, 3, 0xFF]
    assert any(frames[-1][2:19])


def test_a3_reassembler_returns_the_padded_generated_envelope() -> None:
    frames = fragment_a3(0x04, H("09093206ff00000000ff"))

    envelope = reassemble_a3(frames)

    assert envelope == H("01020409093206ff00000000ff") + bytes(21)
    assert len(envelope) == envelope[1] * 17


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda frames: [frames[0][:-1], *frames[1:]], "exactly 20 bytes"),
        (
            lambda frames: [bytes([0xA2]) + frames[0][1:], *frames[1:]],
            "invalid prefix",
        ),
        (
            lambda frames: [frames[0][:-1] + bytes([frames[0][-1] ^ 1]), *frames[1:]],
            "invalid checksum",
        ),
        (
            lambda frames: [
                frames[0][:1]
                + b"\x01"
                + frames[0][2:-1]
                + bytes([xor_checksum(frames[0][:1] + b"\x01" + frames[0][2:-1])]),
                *frames[1:],
            ],
            "index 1, expected 0",
        ),
        (
            lambda frames: [
                frames[0][:3]
                + b"\x03"
                + frames[0][4:-1]
                + bytes([xor_checksum(frames[0][:3] + b"\x03" + frames[0][4:-1])]),
                *frames[1:],
            ],
            "declares 3 frames, received 2",
        ),
    ],
)
def test_a3_reassembler_rejects_invalid_generated_frames(mutate, message: str) -> None:
    frames = fragment_a3(0x04, H("09093206ff00000000ff"))

    with pytest.raises(ValueError, match=message):
        reassemble_a3(mutate(frames))
