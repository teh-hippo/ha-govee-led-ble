"""Capture-backed music parameter encoding."""

from .transport import fragment_a3

_MUSIC_PARAM_TEMPLATE: dict[int, bytes] = {
    0x30: bytes.fromhex("3007ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0a50000000000000"),
    0x31: bytes.fromhex("3105ff0000ff7f00ffff0000ff000000ff05640a0000000000000000000000"),
    0x32: bytes.fromhex("3205ff7f00ff0000ffff000000ff00ff0001015e0000000000000000000000"),
    0x33: bytes.fromhex(
        "3307ff0000ff7f00ffff0000ff000000ff00ffff8b00ffff000032620103020600000000000000000000000000000000"
    ),
    0x34: bytes.fromhex("3407ff0000ff7f00ffff0000ff000000ff00ffff8b00ff000f0a0407000000"),
    0x35: bytes.fromhex("3507ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0001055000000000"),
    0x37: bytes.fromhex("3707ff0000ff7f00ffff0000ff000000ff00ffff8b00ff010a000000000000"),
}
_MUSIC_PARAM_COUNT = {mode: body[1] for mode, body in _MUSIC_PARAM_TEMPLATE.items()}
_MUSIC_PARAM_BASE = 3


def build_music_params(
    mode: int,
    overrides: dict[int, int],
    palette: list[tuple[int, int, int]] | None = None,
) -> list[bytes]:
    """Overlay decoded fields on a captured per-mode template and fragment it."""
    body = bytearray(_MUSIC_PARAM_TEMPLATE[mode])
    if palette is not None:
        if len(palette) != _MUSIC_PARAM_COUNT[mode]:
            raise ValueError("palette count does not match the captured mode template")
        body[2 : 2 + 3 * len(palette)] = bytes(channel for rgb in palette for channel in rgb)
    for offset, value in overrides.items():
        body[offset - _MUSIC_PARAM_BASE] = max(0, min(255, value))
    return fragment_a3(0x41, bytes(body))
