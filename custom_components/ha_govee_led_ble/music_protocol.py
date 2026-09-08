"""Model-specific music mode protocol metadata."""

from collections.abc import Mapping
from importlib import import_module
from types import MappingProxyType
from typing import Any, Final, cast

from .const import MUSIC_MODE_SLUGS

H6179CommandWrite = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6179_command_write").H6179CommandWrite,
)

_H617A_MODE_CODES: Final[Mapping[str, int]] = MappingProxyType(MUSIC_MODE_SLUGS)
_H6179_MODE_CODES: Final[Mapping[str, int]] = MappingProxyType(
    {mode.name: int(mode) for mode in H6179CommandWrite.MusicEffect}
)
_H6199_MODE_CODES: Final[Mapping[str, int]] = MappingProxyType(
    {
        "energetic": 0x05,
        "rhythm": 0x03,
        "spectrum": 0x04,
        "rolling": 0x06,
    }
)

MUSIC_MODE_CODES_BY_MODEL: Final[Mapping[str, Mapping[str, int]]] = MappingProxyType(
    {
        "H617A": _H617A_MODE_CODES,
        "H617E": _H617A_MODE_CODES,
        "H6179": _H6179_MODE_CODES,
        "H6199": _H6199_MODE_CODES,
    }
)

_MUSIC_MODE_SLUGS_BY_MODEL: Final[Mapping[str, Mapping[int, str]]] = MappingProxyType(
    {
        model: MappingProxyType({code: slug for slug, code in codes.items()})
        for model, codes in MUSIC_MODE_CODES_BY_MODEL.items()
    }
)
_MUSIC_STYLE_CODES_BY_MODEL: Final[Mapping[str, frozenset[int]]] = MappingProxyType(
    {
        "H617A": frozenset({0x03, 0x30, 0x31}),
        "H617E": frozenset({0x03, 0x30, 0x31}),
        "H6179": frozenset(),
        "H6199": frozenset({0x03}),
    }
)
_MUSIC_PARAMETER_WRITE_CODES_BY_MODEL: Final[Mapping[str, frozenset[int]]] = MappingProxyType(
    {
        "H617A": frozenset({0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x37}),
        "H617E": frozenset({0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x37}),
        "H6179": frozenset(),
        "H6199": frozenset(),
    }
)


def music_code_for(model: str, slug: str) -> int:
    """Return the raw mode code used by a model."""
    codebook = MUSIC_MODE_CODES_BY_MODEL.get(model)
    if codebook is None:
        raise ValueError(f"{model} has no music mode codebook")
    try:
        return codebook[slug]
    except KeyError:
        raise ValueError(f"{model} does not support music mode {slug!r}") from None


def music_slug_for(model: str, code: int) -> str | None:
    """Return the model-specific slug for a raw mode code."""
    codebook = _MUSIC_MODE_SLUGS_BY_MODEL.get(model)
    return codebook.get(code) if codebook is not None else None


def music_mode_supports_style(model: str, code: int) -> bool:
    """Return whether the mode's primary command carries Dynamic/Calm style."""
    return code in _MUSIC_STYLE_CODES_BY_MODEL.get(model, ())


def music_mode_has_parameter_write(model: str, code: int) -> bool:
    """Return whether the mode requires a companion parameter write."""
    return code in _MUSIC_PARAMETER_WRITE_CODES_BY_MODEL.get(model, ())


__all__ = (
    "MUSIC_MODE_CODES_BY_MODEL",
    "music_code_for",
    "music_mode_has_parameter_write",
    "music_mode_supports_style",
    "music_slug_for",
)
