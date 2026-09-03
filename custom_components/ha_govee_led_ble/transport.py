"""BLE transport framing shared by commands and effect uploads."""

import math
from collections.abc import Sequence

WRITE_UUID = "00010203-0405-0607-0809-0a0b0c0d2b11"
READ_UUID = "00010203-0405-0607-0809-0a0b0c0d2b10"

_A3_FRAME_PREFIX = 0xA3
A3_CHUNK_SIZE = 17

_H6179_A1_PREFIX = 0xA1
_H6179_A1_COM_TYPE = 0x02
H6179_A1_02_CHUNK_SIZE = 16
H6179_A1_02_MAX_DATA_FRAMES = 0xFF
H6179_A1_02_MAX_BODY_SIZE = H6179_A1_02_CHUNK_SIZE * H6179_A1_02_MAX_DATA_FRAMES
H6179_A1_02_MAX_FRAME_COUNT = H6179_A1_02_MAX_DATA_FRAMES + 2


def xor_checksum(data: bytes | bytearray) -> int:
    checksum = 0
    for part in data:
        checksum ^= part
    return checksum


def _a3_frame(index: int, chunk: bytes) -> bytes:
    packet = bytearray([_A3_FRAME_PREFIX, index, *chunk])
    packet = (packet + bytearray(19 - len(packet)))[:19]
    packet.append(xor_checksum(packet))
    return bytes(packet)


def _h6179_a1_02_frame(index: int, chunk: bytes = b"") -> bytes:
    packet = bytearray([_H6179_A1_PREFIX, _H6179_A1_COM_TYPE, index, *chunk])
    packet.extend(bytes(19 - len(packet)))
    packet.append(xor_checksum(packet))
    return bytes(packet)


def fragment_h6179_a1_02(body: bytes) -> list[bytes]:
    """Fragment an H6179 protocol-1.1 DIY body into A1 command-02 frames."""
    if not isinstance(body, bytes) or not body:
        raise ValueError("H6179 A1 02 body must be non-empty bytes")
    if len(body) > H6179_A1_02_MAX_BODY_SIZE:
        raise ValueError(f"H6179 A1 02 body exceeds {H6179_A1_02_MAX_BODY_SIZE} bytes")

    chunks = [body[index : index + H6179_A1_02_CHUNK_SIZE] for index in range(0, len(body), H6179_A1_02_CHUNK_SIZE)]
    return [
        _h6179_a1_02_frame(0, bytes([len(chunks)])),
        *(_h6179_a1_02_frame(index, chunk) for index, chunk in enumerate(chunks, 1)),
        _h6179_a1_02_frame(0xFF),
    ]


def reassemble_h6179_a1_02(frames: Sequence[bytes]) -> bytes:
    """Validate H6179 A1 command-02 frames and return the padded DIY body."""
    if not frames:
        raise ValueError("H6179 A1 02 reassembly requires a non-empty frame sequence")
    if len(frames) > H6179_A1_02_MAX_FRAME_COUNT:
        raise ValueError(f"H6179 A1 02 transfer exceeds {H6179_A1_02_MAX_FRAME_COUNT} frames")

    for position, frame in enumerate(frames):
        if not isinstance(frame, bytes) or len(frame) != 20:
            raise ValueError(f"H6179 A1 02 frame {position} must be exactly 20 bytes")
        if frame[:2] != bytes([_H6179_A1_PREFIX, _H6179_A1_COM_TYPE]):
            raise ValueError(f"frame {position} is not an H6179 A1 02 frame")
        if xor_checksum(frame[:19]) != frame[19]:
            raise ValueError(f"H6179 A1 02 frame {position} has an invalid checksum")

    start = frames[0]
    final = frames[-1]
    if start[2] != 0:
        raise ValueError("H6179 A1 02 transfer has no start frame")
    if any(start[4:19]):
        raise ValueError("H6179 A1 02 start frame has non-zero reserved bytes")
    if final[2] != 0xFF:
        raise ValueError("H6179 A1 02 transfer has no final frame")
    if any(final[3:19]):
        raise ValueError("H6179 A1 02 final frame has non-zero reserved bytes")

    declared = start[3]
    if declared == 0:
        raise ValueError("H6179 A1 02 start frame declares no data frames")
    data_frames = frames[1:-1]
    if len(data_frames) != declared:
        raise ValueError(f"H6179 A1 02 start frame declares {declared} data frames, received {len(data_frames)}")

    for expected_index, frame in enumerate(data_frames, 1):
        if frame[2] != expected_index:
            raise ValueError(f"H6179 A1 02 data frame {expected_index} has index {frame[2]}, expected {expected_index}")

    return b"".join(frame[3:19] for frame in data_frames)


def fragment_a3(type_byte: int, body: bytes, *, terminator: bool = False) -> list[bytes]:
    """Fragment one A3 body using the app's data-frame and terminator rules."""
    data = bytes([type_byte]) + body
    chunk_count = math.ceil((len(data) + 2) / A3_CHUNK_SIZE)
    trailing_terminator = terminator or chunk_count == 1
    payload = bytes([0x01, chunk_count + (1 if trailing_terminator else 0)]) + data
    chunks = [payload[index : index + A3_CHUNK_SIZE] for index in range(0, len(payload), A3_CHUNK_SIZE)]
    last = len(chunks) - 1
    packets = [
        _a3_frame(index if trailing_terminator or index != last else 0xFF, chunk) for index, chunk in enumerate(chunks)
    ]
    if trailing_terminator:
        packets.append(_a3_frame(0xFF, b""))
    return packets


def fragment_a3_envelope(envelope: bytes) -> list[bytes]:
    """Fragment a generated A3 envelope whose line count already includes padding."""
    if len(envelope) < 2 or envelope[0] != 0x01 or len(envelope) != envelope[1] * A3_CHUNK_SIZE:
        raise ValueError("A3 envelope does not match its chunk count")
    chunks = [envelope[index : index + A3_CHUNK_SIZE] for index in range(0, len(envelope), A3_CHUNK_SIZE)]
    return [_a3_frame(index if index + 1 < len(chunks) else 0xFF, chunk) for index, chunk in enumerate(chunks)]


def reassemble_a3(frames: Sequence[bytes]) -> bytes:
    """Validate generated A3 frames and return their padded Kaitai envelope."""
    if not frames:
        raise ValueError("A3 reassembly requires a non-empty frame sequence")

    chunks: list[bytes] = []
    for position, frame in enumerate(frames):
        if not isinstance(frame, bytes) or len(frame) != 20:
            raise ValueError(f"A3 frame {position} must be exactly 20 bytes")
        if frame[0] != _A3_FRAME_PREFIX:
            raise ValueError(f"A3 frame {position} has an invalid prefix")
        if xor_checksum(frame[:19]) != frame[19]:
            raise ValueError(f"A3 frame {position} has an invalid checksum")
        expected_index = 0xFF if position + 1 == len(frames) else position
        if frame[1] != expected_index:
            raise ValueError(f"A3 frame {position} has index {frame[1]}, expected {expected_index}")
        chunks.append(frame[2:19])

    envelope = b"".join(chunks)
    if envelope[0] != 0x01:
        raise ValueError("A3 envelope has an invalid marker")
    if envelope[1] != len(frames):
        raise ValueError(f"A3 envelope declares {envelope[1]} frames, received {len(frames)}")
    return envelope
