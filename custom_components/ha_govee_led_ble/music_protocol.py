"""Model-specific music mode protocol metadata."""

from collections.abc import Mapping
from importlib import import_module
from types import MappingProxyType
from typing import Any, Final, cast

from .const import MUSIC_MODE_SLUGS, ModelProfile, get_profile

H6179CommandWrite = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6179_command_write").H6179CommandWrite,
)

H6076MusicBody = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6076_music_body").H6076MusicBody,
)
H6076MusicWrite = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6076_music_write").H6076MusicWrite,
)

H6125StatusReply = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6125_status_reply").H6125StatusReply,
)

_H617A_MODE_CODES: Final[Mapping[str, int]] = MappingProxyType(MUSIC_MODE_SLUGS)
_H6179_MODE_CODES: Final[Mapping[str, int]] = MappingProxyType(
    {mode.name: int(mode) for mode in H6179CommandWrite.MusicEffect}
)
_H6076_MODE_CODES: Final[Mapping[str, int]] = MappingProxyType(
    {mode.name: int(mode) for mode in H6076MusicWrite.MusicMode}
)
# Replies use the submode 0x11 numbering; commands keep the shared H617A logical codes.
_H6125_STATUS_MODE_SLUGS: Final[Mapping[int, str]] = MappingProxyType(
    {int(mode): mode.name for mode in H6125StatusReply.MusicMode}
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
        "H6099": _H617A_MODE_CODES,
        "H6102": _H617A_MODE_CODES,
        "H6125": _H617A_MODE_CODES,
        "H6076": _H6076_MODE_CODES,
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
        "H6099": frozenset({0x03, 0x30, 0x31}),
        "H6102": frozenset({0x03, 0x30, 0x31}),
        "H6125": frozenset({0x03, 0x30, 0x31}),
        "H6076": frozenset({int(H6076MusicWrite.MusicMode.rhythm)}),
        "H6179": frozenset(),
        "H6199": frozenset({0x03}),
    }
)
_MUSIC_PARAMETER_WRITE_CODES_BY_MODEL: Final[Mapping[str, frozenset[int]]] = MappingProxyType(
    {
        "H617A": frozenset({0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x37}),
        "H617E": frozenset({0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x37}),
        "H6099": frozenset({0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x37}),
        "H6102": frozenset({0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x37}),
        "H6125": frozenset({0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x37}),
        "H6076": frozenset(int(mode) for mode in H6076MusicBody.MusicMode),
        "H6179": frozenset(),
        "H6199": frozenset(),
    }
)


def _protocol_model(
    model: str,
    direction: str = "command",
    *,
    profile: ModelProfile | None = None,
) -> str | None:
    profile = get_profile(model) if profile is None else profile
    grammar = profile.status_grammar
    if direction == "command":
        grammar = profile.music_grammar or profile.command_grammar
    return grammar if grammar in MUSIC_MODE_CODES_BY_MODEL else None


def music_codebook(profile: ModelProfile) -> Mapping[str, int]:
    """Return the mode codebook selected by the profile's music grammar."""
    grammar = profile.music_grammar or profile.command_grammar
    codebook = MUSIC_MODE_CODES_BY_MODEL.get(grammar) if grammar is not None else None
    if codebook is None:
        raise ValueError(f"{profile.name} has no music mode codebook")
    return codebook


def music_code_for(model: str, slug: str, *, profile: ModelProfile | None = None) -> int:
    """Return the raw mode code used by a model."""
    protocol_model = _protocol_model(model, profile=profile)
    codebook = MUSIC_MODE_CODES_BY_MODEL.get(protocol_model) if protocol_model is not None else None
    if codebook is None:
        raise ValueError(f"{model} has no music mode codebook")
    try:
        return codebook[slug]
    except KeyError:
        raise ValueError(f"{model} does not support music mode {slug!r}") from None


def music_slug_for(
    model: str,
    code: int,
    *,
    direction: str = "command",
    profile: ModelProfile | None = None,
) -> str | None:
    """Return the model-specific slug for a raw mode code."""
    profile = get_profile(model) if profile is None else profile
    if direction == "status" and profile.status_grammar == "H6125":
        return _H6125_STATUS_MODE_SLUGS.get(code)
    protocol_model = _protocol_model(model, direction, profile=profile)
    codebook = _MUSIC_MODE_SLUGS_BY_MODEL.get(protocol_model) if protocol_model is not None else None
    return codebook.get(code) if codebook is not None else None


def music_mode_supports_style(model: str, code: int, *, profile: ModelProfile | None = None) -> bool:
    """Return whether the mode's primary command carries Dynamic/Calm style."""
    protocol_model = _protocol_model(model, profile=profile)
    return protocol_model is not None and code in _MUSIC_STYLE_CODES_BY_MODEL.get(protocol_model, ())


def music_mode_has_parameter_write(model: str, code: int, *, profile: ModelProfile | None = None) -> bool:
    """Return whether the mode requires a companion parameter write."""
    protocol_model = _protocol_model(model, profile=profile)
    return protocol_model is not None and code in _MUSIC_PARAMETER_WRITE_CODES_BY_MODEL.get(protocol_model, ())


__all__ = (
    "MUSIC_MODE_CODES_BY_MODEL",
    "music_codebook",
    "music_code_for",
    "music_mode_has_parameter_write",
    "music_mode_supports_style",
    "music_slug_for",
)
