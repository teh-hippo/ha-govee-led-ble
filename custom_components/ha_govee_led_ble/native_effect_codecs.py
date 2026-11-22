from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .const import ModelProfile
from .h7025_effects import decode_h7025_diy, encode_h7025_diy, validate_h7025_diy
from .native_effect import NativeEffect
from .protocol_core import H7025DiyBody


@dataclass(frozen=True, slots=True)
class NativeA3Codec:
    effect_grammar: str
    upload_subtype: int
    root_type: type[Any]
    canonical_model: str
    encode: Callable[[NativeEffect], bytes]
    decode: Callable[[bytes], NativeEffect]
    validate: Callable[[NativeEffect], None]


NATIVE_A3_CODECS = (
    NativeA3Codec(
        effect_grammar="H617A",
        upload_subtype=0x58,
        root_type=H7025DiyBody,
        canonical_model="H7025",
        encode=encode_h7025_diy,
        decode=decode_h7025_diy,
        validate=validate_h7025_diy,
    ),
)


def native_a3_codec_for_profile(profile: ModelProfile) -> NativeA3Codec | None:
    return native_a3_codec_for_route(profile.effect_grammar, profile.native_diy_upload_subtype)


def native_a3_codec_for_route(effect_grammar: str | None, upload_subtype: int | None) -> NativeA3Codec | None:
    return next(
        (
            codec
            for codec in NATIVE_A3_CODECS
            if codec.effect_grammar == effect_grammar and codec.upload_subtype == upload_subtype
        ),
        None,
    )


def native_a3_codec_for_tree(tree: Any) -> NativeA3Codec | None:
    return next((codec for codec in NATIVE_A3_CODECS if isinstance(tree, codec.root_type)), None)
