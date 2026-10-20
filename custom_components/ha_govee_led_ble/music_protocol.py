"""Model-specific music mode protocol metadata."""

from collections.abc import Mapping
from importlib import import_module
from types import MappingProxyType
from typing import Any, Final, cast

from .const import ModelProfile, get_profile

GoveeCommon = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.govee_common").GoveeCommon,
)
H6099CommandWrite = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6099_command_write").H6099CommandWrite,
)
H6179CommandWrite = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6179_command_write").H6179CommandWrite,
)
H6199CommandWrite = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6199_command_write").H6199CommandWrite,
)
H7020CommandWrite = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h7020_command_write").H7020CommandWrite,
)

H6076MusicBody = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6076_music_body").H6076MusicBody,
)
H6076MusicWrite = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6076_music_write").H6076MusicWrite,
)
H7025MusicBody = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h7025_music_body").H7025MusicBody,
)
H7025MusicWrite = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h7025_music_write").H7025MusicWrite,
)

H6099MusicParameters = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6099_music_parameters").H6099MusicParameters,
)
MusicBody = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.music_body").MusicBody,
)

_H617A_MODE_CODES: Final[Mapping[str, int]] = MappingProxyType({mode.name: int(mode) for mode in GoveeCommon.MusicMode})
_H6099_MODE_CODES: Final[Mapping[str, int]] = MappingProxyType(
    {mode.name: int(mode) for mode in H6099CommandWrite.MusicMode}
)
_H6179_MODE_CODES: Final[Mapping[str, int]] = MappingProxyType(
    {mode.name: int(mode) for mode in H6179CommandWrite.MusicEffect}
)
_H6076_MODE_CODES: Final[Mapping[str, int]] = MappingProxyType(
    {mode.name: int(mode) for mode in H6076MusicWrite.MusicMode}
)
_H6199_MODE_CODES: Final[Mapping[str, int]] = MappingProxyType(
    {mode.name: int(mode) for mode in H6199CommandWrite.MusicMode}
)
_H617A_STYLE_CODES: Final[frozenset[int]] = frozenset(
    int(mode)
    for mode in (
        GoveeCommon.MusicMode.rhythm,
        GoveeCommon.MusicMode.bloom,
        GoveeCommon.MusicMode.shiny,
    )
)
_H617A_PARAMETER_WRITE_CODES: Final[frozenset[int]] = frozenset(int(mode) for mode in MusicBody.MusicMode)
_H6099_PARAMETER_WRITE_CODES: Final[frozenset[int]] = frozenset(int(mode) for mode in H6099MusicParameters.MusicMode)
_H7020_MODE_CODES: Final[Mapping[str, int]] = MappingProxyType(
    {mode.name: int(mode) for mode in H7020CommandWrite.MusicMode}
)

MUSIC_MODE_CODES_BY_MODEL: Final[Mapping[str, Mapping[str, int]]] = MappingProxyType(
    {
        "H617A": _H617A_MODE_CODES,
        "H6099": _H6099_MODE_CODES,
        "H6076": _H6076_MODE_CODES,
        "H7025": MappingProxyType({mode.name: int(mode) for mode in H7025MusicWrite.MusicMode}),
        "H6179": _H6179_MODE_CODES,
        "H6199": _H6199_MODE_CODES,
        "H7020": _H7020_MODE_CODES,
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
        "H617A": _H617A_STYLE_CODES,
        "H6099": _H617A_STYLE_CODES,
        "H6076": frozenset({int(H6076MusicWrite.MusicMode.rhythm)}),
        "H7025": frozenset({int(H7025MusicWrite.MusicMode.rhythm)}),
        "H6179": frozenset(),
        "H6199": frozenset({int(H6199CommandWrite.MusicMode.rhythm)}),
        "H7020": frozenset(),
    }
)
_MUSIC_PARAMETER_WRITE_CODES_BY_MODEL: Final[Mapping[str, frozenset[int]]] = MappingProxyType(
    {
        "H617A": _H617A_PARAMETER_WRITE_CODES,
        "H6099": _H6099_PARAMETER_WRITE_CODES,
        "H6076": frozenset(int(mode) for mode in H6076MusicBody.MusicMode),
        "H7025": frozenset(int(mode) for mode in H7025MusicBody.MusicMode),
        "H6179": frozenset(),
        "H6199": frozenset(),
        "H7020": frozenset(),
    }
)


def _protocol_model(
    model: str,
    *,
    profile: ModelProfile | None = None,
) -> str | None:
    """Resolve the command music codebook grammar for a profile."""
    profile = get_profile(model) if profile is None else profile
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
    profile = get_profile(model) if profile is None else profile
    protocol_model = _protocol_model(model, profile=profile)
    codebook = MUSIC_MODE_CODES_BY_MODEL.get(protocol_model) if protocol_model is not None else None
    if codebook is None:
        raise ValueError(f"{model} has no music mode codebook")
    if slug not in profile.music_modes:
        raise ValueError(f"{model} does not support music mode {slug!r}")
    try:
        return codebook[slug]
    except KeyError:
        raise ValueError(f"{model} does not support music mode {slug!r}") from None


def music_slug_for(
    model: str,
    code: int,
    *,
    profile: ModelProfile | None = None,
) -> str | None:
    """Return the model-specific slug for a raw command mode code."""
    protocol_model = _protocol_model(model, profile=profile)
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
