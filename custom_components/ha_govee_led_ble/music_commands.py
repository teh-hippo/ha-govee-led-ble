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
_H6125_MUSIC_PARAM_TEMPLATE: dict[int, bytes] = {
    0x30: bytes.fromhex("3007ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0a50"),
    0x31: bytes.fromhex("3107ff0000ff7f00ffff0000ff000000ff00ffff8b00ff05640a"),
    0x32: bytes.fromhex("3207ff0000ff7f00ffff0000ff000000ff00ffff8b00ff030063"),
    0x33: bytes.fromhex("3307ff0000ff7f00ffff0000ff000000ff00ffff8b00ff010101196201030614"),
    0x34: bytes.fromhex("3407ff0000ff7f00ffff0000ff000000ff00ffff8b00ff000f230107"),
    0x35: bytes.fromhex("3507ff0000ff7f00ffff0000ff000000ff00ffff8b00ff01020555"),
    0x37: bytes.fromhex("3707ff0000ff7f00ffff0000ff000000ff00ffff8b00ff071400"),
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


def build_h6125_music_params(
    mode: int,
    *,
    calm: bool,
    separation_point: int,
    separation_gradient: bool,
    hopping_brightness: int,
    piano_key_count: int,
    fountain_direction: str,
    daynight_segments: int,
    daynight_speed: int,
    daynight_gradient: bool,
) -> list[bytes]:
    if mode not in _H6125_MUSIC_PARAM_TEMPLATE:
        return []
    body = bytearray(_H6125_MUSIC_PARAM_TEMPLATE[mode])
    if mode == 0x30:
        body[-1] = 20 if calm else 80
    elif mode == 0x31:
        body[-3:-1] = (0x1446 if calm else 0x0564).to_bytes(2, "big")
    elif mode == 0x32:
        body[-3:] = bytes((separation_point, int(separation_gradient), 98 if separation_gradient else 99))
    elif mode == 0x33:
        body[-6] = hopping_brightness
    elif mode == 0x34:
        body[-4] = piano_key_count
        body[-1] = max(1, piano_key_count // 2)
    elif mode == 0x35:
        direction = {"clockwise": 1, "counterclockwise": 0}.get(fountain_direction)
        if direction is None:
            raise ValueError("H6125 fountain direction must be clockwise or counterclockwise")
        body[-4:-1] = bytes((direction, 2 if direction else 3, 5 if direction else 8))
    else:
        body[-3:] = bytes((daynight_segments, daynight_speed, int(daynight_gradient)))
    return fragment_a3(0x41, bytes(body))
