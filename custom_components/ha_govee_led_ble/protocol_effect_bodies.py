"""Effect body encoding, upload framing and acknowledgement semantics."""

from __future__ import annotations

import io
import math
from collections.abc import Sequence
from typing import Any

from kaitaistruct import KaitaiStream, KaitaiStructError

from .const import WHOLE_BULB_GRAMMARS, ModelProfile, get_profile
from .native_effect_codecs import (
    NativeEffectCarrier,
    native_effect_codec_for_grammar,
    native_effect_codec_for_profile,
)
from .protocol_core import (
    _COMMAND_ACK_ROOTS,
    _COMMAND_ROOTS,
    MAX_SCENE_PARAM_BYTES,
    CommandWrite,
    DiyType03,
    DiyType04,
    GoveeCommon,
    H60b0CommandAck,
    H60b0CommandWrite,
    H60b0EffectUpload,
    H607cCommandAck,
    H607cCommandWrite,
    H607cMusicBody,
    H607cSceneBody,
    H1771CommandWrite,
    H6046CommandAck,
    H6046EffectUpload,
    H6046MusicBody,
    H6053CommandAck,
    H6053EffectUpload,
    H6072MusicAck,
    H6072MusicBody,
    H6076MusicAck,
    H6076MusicBody,
    H6099CommandWrite,
    H6099EffectUpload,
    H6127WireWrite,
    H6181DiyBody,
    H6199DiySelector,
    H6199EffectUpload,
    SceneBody,
    SceneParameterTooLargeError,
    SceneType1Body,
    WorkshopBody,
    _a3_header,
    _child,
    _parse_xor_frame,
    _rgb,
    _serialize_a3_scene_param,
    _serialize_xor,
    _set_effect_layer_lengths,
    _write,
    check_generated_tree,
    serialize_native_body,
)
from .protocol_h6179 import build_h6179_diy_activation, build_h6179_scene
from .protocol_h6199 import build_h6199_scene
from .transport import (
    A1_02_COMMAND,
    A1_02_PREFIX,
    A3_CHUNK_SIZE,
    A3_PREFIX,
    A4_PREFIX,
    reassemble_a1_02_upload,
    reassemble_a3,
    reassemble_a4_upload,
)


def build_dedicated_diy(content: Any, code: int, profile: ModelProfile) -> list[bytes]:
    if profile.effect_grammar == "H6181":
        from .h6181_effects import build_diy

        return build_diy(content, code, profile)
    raise ValueError("No dedicated palette DIY codec is available")


class A3Sequence:
    """Own complete upload framing and the header authorising each physical chunk."""

    def __init__(self, packets: Sequence[bytes]) -> None:
        chunks: list[tuple[bytes, bytes]] = []
        pending: list[bytes] = []
        for packet in packets:
            if not self.is_frame(packet):
                if pending:
                    raise ValueError("A3 upload was interrupted before its final frame")
                continue
            parsed = _parse_xor_frame(
                packet, "A3", {"A3": ("command_write.upload_frame", CommandWrite.UploadFrame)}
            ).parsed
            if parsed is None:
                raise ValueError("Invalid A3 upload frame")
            pending.append(packet)
            if parsed.is_final:
                reassemble_a3(pending)
                chunks.extend((frame, pending[0]) for frame in pending)
                pending = []
        if pending:
            raise ValueError("A3 upload is missing its final frame")
        self._chunks = tuple(chunks)
        self._index = 0

    @staticmethod
    def is_frame(packet: bytes) -> bool:
        return packet[:1] == bytes((A3_PREFIX,))

    def reset(self) -> None:
        self._index = 0

    def header_for(self, packet: bytes) -> bytes | None:
        if not self.is_frame(packet):
            return None
        if self._index >= len(self._chunks) or self._chunks[self._index][0] != packet:
            raise ValueError("A3 frame is outside the current ordered upload")
        return self._chunks[self._index][1]

    def note_write(self, packet: bytes) -> None:
        if self.header_for(packet) is not None:
            self._index += 1


def require_a3_sequence_frame(packet: bytes, sequence: A3Sequence | None) -> bytes | None:
    if not A3Sequence.is_frame(packet):
        return None
    if sequence is None:
        raise ValueError("A3 uploads require a complete ordered effect sequence")
    return sequence.header_for(packet)


def _complete_a3_upload(
    packets: Sequence[bytes], index: int, model: str, profile: ModelProfile | None
) -> tuple[int, bytes]:
    active_profile = profile or get_profile(model)
    ack_grammar = active_profile.command_ack_grammar or active_profile.command_grammar
    if (
        active_profile.command_grammar not in {"H600A", "H6046", "H607C", "H60B0", "H617A", "H6181", "H7020"}
        and ack_grammar not in {"H6099", "H617A"}
        and not (ack_grammar == "H6199" and active_profile.effect_grammar == "H6199")
    ):
        raise ValueError("Upload ACK semantics are not qualified for this command grammar")
    roots = {"H617A": ("command_write.upload_frame", CommandWrite.UploadFrame)}
    for start in range(index, -1, -1):
        frame = _parse_xor_frame(packets[start], "H617A", roots).parsed
        if frame is None or (start == index and not frame.is_final):
            break
        if frame.index == 0:
            envelope = reassemble_a3(packets[start : index + 1])
            if ack_grammar == "H6199":
                upload = parse_a3_effect_envelope(envelope, model, profile=active_profile)
                if upload.kind != H6199EffectUpload.BodyKind.diy or upload.chunk_count != upload.diy_chunk_count:
                    raise ValueError("Upload ACK is qualified only for the H6199 palette DIY body")
            return int(frame.body.subtype), envelope
    raise ValueError("Upload ACK index must end a complete A3 upload")


def upload_ack_subtype(packets: Sequence[bytes], index: int, model: str, *, profile: ModelProfile | None = None) -> int:
    """Validate a complete upload ending at index, returning its ACK command."""
    profile = profile or get_profile(model)
    if packets[index][0] == A4_PREFIX:
        codec = native_effect_codec_for_profile(profile)
        if codec is None:
            raise ValueError("A4 upload acknowledgement is not qualified for this profile")
        subtype, _body = reassemble_a4_upload(packets, index)
        if codec.admits_upload(profile, subtype) is not True or not any(
            route.carrier is NativeEffectCarrier.A4 and route.subtype == subtype for route in codec.routes
        ):
            raise ValueError("A4 upload subtype is outside profile capabilities")
        return subtype
    if packets[index][0] == A1_02_PREFIX:
        if profile.effect_grammar == "H6181" and profile.diy_upload_transport == "a1_02":
            body = reassemble_a1_02_upload(packets, index)
            parsed = H6181DiyBody.from_bytes(body)
            parsed._read()
            return A1_02_COMMAND
        prefix = profile.a1_diy_prefix if profile.a1_diy_prefix is not None else profile.a1_diy_selector
        if prefix is None or profile.command_ack_grammar not in _COMMAND_ACK_ROOTS:
            raise ValueError("A1 upload acknowledgement is not qualified for this profile")
        body = reassemble_a1_02_upload(packets, index)
        if body[0] != prefix:
            raise ValueError("A1 upload selector does not match the profile")
        return A1_02_COMMAND
    subtype, _envelope = _complete_a3_upload(packets, index, model, profile)
    return subtype


def upload_ack_mode(
    packets: Sequence[bytes], index: int, model: str, *, profile: ModelProfile | None = None
) -> int | None:
    """Return the music mode an exact-model acknowledgement must repeat, if its schema carries one."""
    if packets[index][0] != A3_PREFIX:
        return None
    grammar = (profile or get_profile(model)).music_grammar
    if grammar not in {"H6072", "H6076", "H6046", "H607C", "H60B0"}:
        return None
    subtype, envelope = _complete_a3_upload(packets, index, model, profile)
    if subtype != 0x41:
        return None
    if grammar == "H60B0":
        upload = H60b0EffectUpload.from_bytes(envelope)
        upload._read()
        return int(upload.mode)
    body = (
        H607cMusicBody
        if grammar == "H607C"
        else H6046MusicBody
        if grammar == "H6046"
        else H6072MusicBody
        if grammar == "H6072"
        else H6076MusicBody
    ).from_bytes(envelope)
    body._read()
    return int(body.mode)


def upload_ack_success(
    parsed: Any, subtype: int, mode: int | None = None, *, protocol: int | None = None
) -> bool | None:
    """Return a matching upload result, never treating an ordinary ACK as upload acceptance."""
    upload = getattr(parsed, "upload", None)
    if upload is not None:
        if upload.opcode != subtype or (protocol is not None and parsed.header != protocol):
            return None
        return bool(upload.is_success)
    if protocol == 0xA1 and getattr(parsed, "header", None) == 0xA1:
        return bool(parsed.status == 0) if parsed.opcode == subtype else None
    if protocol is not None and getattr(parsed, "protocol_id", None) != protocol:
        return None
    if (
        isinstance(parsed, H6076MusicAck | H6072MusicAck)
        or isinstance(parsed, H60b0CommandAck)
        and getattr(parsed, "mode", None) is not None
        or (isinstance(parsed, H607cCommandAck) and getattr(parsed, "mode", None) is not None)
        or (isinstance(parsed, H6046CommandAck | H6053CommandAck) and getattr(parsed, "mode", None) is not None)
    ):
        return (
            bool(parsed.is_success)
            if mode is not None and parsed.opcode == subtype and int(parsed.mode) == mode
            else None
        )
    if getattr(parsed, "is_upload", False) and parsed.opcode == subtype:
        return bool(parsed.is_success)
    return None


def parse_a3_effect_envelope(envelope: bytes, model: str, *, profile: ModelProfile | None = None) -> Any:
    """Parse one validated, padded A3 effect envelope through its generated root."""
    if not isinstance(envelope, bytes):
        raise TypeError("A3 effect envelope must be bytes")
    if len(envelope) < A3_CHUNK_SIZE or len(envelope) % A3_CHUNK_SIZE:
        raise ValueError("A3 effect envelope must contain complete 17-byte chunks")
    if envelope[0] != 0x01:
        raise ValueError("A3 effect envelope has an invalid marker")
    if envelope[1] != len(envelope) // A3_CHUNK_SIZE:
        raise ValueError("A3 effect envelope does not match its chunk count")

    effective_profile = profile or get_profile(model)
    grammar = effective_profile.effect_grammar
    native_codec = native_effect_codec_for_profile(effective_profile)
    native_root = (
        native_codec.a3_root_for_subtype(envelope[2])
        if native_codec is not None and native_codec.qualifies_upload_subtype(effective_profile, envelope[2])
        else None
    )
    root_type: type[Any] | None
    if native_root is not None:
        root_type = native_root
    elif grammar == "H6179":
        if envelope[2] != 0x04:
            raise ValueError("H6179 A3 uploads require a type-04 DIY body")
        root_type = DiyType04
    elif grammar in {"H617A", "H6181"}:
        root_type = {
            0x01: SceneType1Body,
            0x02: SceneBody,
            0x03: DiyType03,
            0x04: DiyType04,
        }.get(envelope[2])
        if root_type is None:
            raise ValueError(f"H617A A3 body type 0x{envelope[2]:02x} is not supported")
    elif grammar == "H6099":
        root_type = H6099EffectUpload
    elif grammar == "H6199":
        root_type = H6199EffectUpload
    elif grammar == "H6046":
        root_type = H6046EffectUpload
    elif grammar == "H6053":
        root_type = H6053EffectUpload
    else:
        raise ValueError(f"{model} has no generated A3 effect grammar")
    assert root_type is not None

    try:
        parsed = root_type(KaitaiStream(io.BytesIO(envelope)))
        parsed._read()
        if native_codec is not None and native_codec.validate_tree is not None and native_root is not None:
            native_codec.validate_tree(parsed, effective_profile)
        if grammar == "H6099" and int(parsed.kind) in (3, 4):
            _ = parsed.diy
        if grammar == "H6053" and parsed.kind == H6053EffectUpload.BodyKind.scene_v2:
            validate_h6053_workshop_v2(parsed.content)
    except KaitaiStructError as error:
        raise ValueError(f"invalid {model} A3 effect envelope") from error
    if not parsed._io.is_eof():
        raise ValueError(f"{model} A3 effect grammar did not consume the envelope")
    if (
        native_codec is not None
        and native_root is not None
        and native_codec.requires_zero_padding_for(envelope[2], root_type)
        and any(parsed.padding)
    ):
        raise ValueError("Native A3 effect envelope contains non-zero transport fill")
    return parsed


def validate_h6053_workshop_v2(content: Any) -> None:
    """Validate explicit V2 extensions without reclassifying V1 layer excess."""
    for record in content.blocks:
        extension = H6053EffectUpload.V2Extension.from_bytes(record.body.excess)
        extension._read()


def parse_h6053_workshop_body(raw_param: bytes, carrier: str) -> Any:
    """Parse an explicitly identified retained carrier without guessing from layer tails."""
    root_type = {
        "rgb": H6053EffectUpload.RgbContent,
        "rgbic_v1": H6053EffectUpload.SceneContent,
        "rgbic_v2": H6053EffectUpload.SceneV2Source,
    }.get(carrier)
    if root_type is None or not isinstance(raw_param, bytes) or len(raw_param) > MAX_SCENE_PARAM_BYTES:
        raise ValueError("Invalid retained Workshop carrier or parameter")
    try:
        parsed = root_type(KaitaiStream(io.BytesIO(raw_param)))
        parsed._read()
        if not parsed._io.is_eof():
            raise ValueError("Workshop carrier has unrepresented trailing data")
        if carrier == "rgbic_v2":
            parsed = parsed.content
            validate_h6053_workshop_v2(parsed)
    except (KaitaiStructError, EOFError) as error:
        raise ValueError("Invalid retained Workshop body") from error
    return parsed


def _parse_a3_scene(
    root_type: Any,
    scene_type_byte: int,
    raw_param: bytes,
    trailing_padding_of: Any,
) -> tuple[Any, int]:
    """Frame a stripped catalogue parameter and parse it through a generated A3 root.

    The parameter carries the real bytes only, so an unpadded read first measures the
    genuine trailing padding before the synthetic envelope padding a reassembled frame
    would carry is appended for the returned tree.
    """
    if not isinstance(raw_param, bytes):
        raise TypeError("scene parameter must be bytes")
    synthetic = root_type()
    header = _a3_header(synthetic)
    header_length = len(header.marker) + 1
    header.linecount = max(header.linecount, math.ceil((header_length + 1 + len(raw_param)) / A3_CHUNK_SIZE))
    check_generated_tree(header)
    header_bytes = _write(header, header_length)
    envelope = header_bytes + bytes((scene_type_byte,)) + raw_param
    unpadded = root_type(KaitaiStream(io.BytesIO(envelope)))
    unpadded._read()
    trailing_padding = len(trailing_padding_of(unpadded))
    envelope = envelope.ljust(header.linecount * A3_CHUNK_SIZE, b"\x00")
    parsed = root_type(KaitaiStream(io.BytesIO(envelope)))
    parsed._read()
    return parsed, trailing_padding


def parse_scene_body(raw_param: bytes, *, scene_type: int = 2) -> tuple[Any, int]:
    """Parse a layered catalogue parameter without conflating its type and upload subtype."""
    if scene_type == int(H607cSceneBody.CatalogueType.layered_scene):
        parsed = H607cSceneBody.from_bytes(raw_param)
        parsed._read()
        for record in parsed.records:
            trailer = H607cSceneBody.LayerTrailer.from_bytes(record.body.excess)
            trailer._read()
        return parsed, len(parsed.padding)
    if scene_type != int(SceneBody.SceneType.scene_v2):
        raise ValueError(f"Unsupported layered scene type {scene_type}")
    return _parse_a3_scene(SceneBody, scene_type, raw_param, lambda root: root.padding)


def parse_scene_body_param(raw_param: bytes) -> Any:
    """Parse a catalogue type-2 parameter through the generated SceneBody root."""
    return parse_scene_body(raw_param)[0]


def parse_workshop_body(raw_param: bytes) -> tuple[Any, int]:
    """Parse an H617A Workshop parameter through the generated WorkshopBody root."""
    return _parse_a3_scene(WorkshopBody, 2, raw_param, lambda root: root.padding)


def parse_scene_type1_body(raw_param: bytes) -> tuple[Any, int]:
    """Parse a catalogue type-1 parameter, returning its tree and real trailing padding."""
    return _parse_a3_scene(SceneType1Body, 1, raw_param, lambda root: root.content.padding)


def parse_scene_type1_body_param(raw_param: bytes) -> Any:
    """Parse a catalogue type-1 parameter through the generated SceneType1Body root."""
    return parse_scene_type1_body(raw_param)[0]


def serialize_scene_body_param(root: Any) -> bytes:
    """Serialize layered fields, preserving the catalogue's original container grammar."""
    _set_effect_layer_lengths(root.records)
    if isinstance(root, H607cSceneBody):
        payload = serialize_native_body(root)
        header = _a3_header(root)
        if len(payload) + len(header.marker) + 1 > MAX_SCENE_PARAM_BYTES:
            raise SceneParameterTooLargeError("Layered scene exceeds the catalogue parameter bound")
        parse_scene_body(payload, scene_type=int(H607cSceneBody.CatalogueType.layered_scene))
        return payload
    return _serialize_a3_scene_param(root)


def serialize_workshop_body_param(root: Any) -> bytes:
    """Serialize a built H617A WorkshopBody root and return its parameter bytes."""
    _set_effect_layer_lengths(root.layers)
    return _serialize_a3_scene_param(root)


def serialize_scene_type1_body_param(root: Any) -> bytes:
    """Serialize a built type-1 SceneType1Body root and return its catalogue parameter bytes."""
    return _serialize_a3_scene_param(root)


def build_h617a_diy_painted_body(
    effect: str,
    speed: int,
    brightness: int,
    background: tuple[int, int, int],
    groups: list[tuple[tuple[int, int, int], list[int]]],
    *,
    grammar: str = "H617A",
) -> bytes:
    """Serialize the diy_type03 fields after its A3 type byte."""
    codec = native_effect_codec_for_grammar(grammar)
    root_type = codec.a3_root_for_subtype(3) if codec is not None else DiyType03
    if root_type is None:
        root_type = DiyType03
    root = root_type()
    root.header = _a3_header(root)
    root.body_type = b"\x03"
    root.effect = getattr(root_type.Effect, effect)
    root.speed = speed
    root.brightness = brightness
    root.background = _rgb(root, *background)
    root.num_groups = len(groups)
    root.groups = []
    for fill, segments in groups:
        group = _child(DiyType03.PaintGroup, root)
        group.num_segment_indices = len(segments)
        group.fill = _rgb(group, *fill)
        group.segment_indices = segments
        root.groups.append(group)
    root.padding = []
    return _serialize_a3_scene_param(root)


def _diy_type04_palette(parent: Any, colours: list[tuple[int, int, int]]) -> Any:
    palette = _child(DiyType04.Palette, parent)
    palette.colours = [_rgb(palette, *colour) for colour in colours]
    return palette


def build_inline_diy(
    code: int, family: int, variant: int, speed: int, palette: tuple[tuple[int, int, int], ...]
) -> bytes:
    if not 0 <= code <= 255 or not 1 <= len(palette) <= 4:
        raise ValueError("Inline DIY requires a byte selector and one to four colours")
    root = CommandWrite()
    root.header = b"\x33"
    root.opcode = CommandWrite.CommandOp.multi
    mode = _child(CommandWrite.MultiCmd, root)
    mode.sub = CommandWrite.MultiSub.inline_diy
    body = _child(H6127WireWrite.InlineDiy, mode)
    body.code, body.family, body.variant, body.speed = code, family, variant, speed
    body.colours = [_rgb(body, *colour) for colour in (*palette, *((0, 0, 0),) * (4 - len(palette)))]
    mode.sub_body, root.body = body, mode
    return _serialize_xor(root)


def build_h617a_diy_single_body(
    family: int,
    variant: int,
    speed: int,
    palette: list[tuple[int, int, int]],
) -> bytes:
    """Serialize the diy_type04 Flat fields after the A3 type byte."""
    root = DiyType04()
    root.header = _a3_header(root)
    root.a3_type = b"\x04"
    root.family = family
    body = _child(DiyType04.FlatBody, root)
    body.variant = variant
    body.speed = speed
    body.len_palette = len(palette) * 3
    body.palette = _diy_type04_palette(body, palette)
    body.padding = []
    root.body = body
    return _serialize_a3_scene_param(root)


def build_h617a_diy_multi_body(
    effects: list[tuple[int, int]],
    speed: int,
    palette: list[tuple[int, int, int]],
) -> bytes:
    """Serialize the diy_type04 Combo fields after the A3 type byte."""
    root = DiyType04()
    root.header = _a3_header(root)
    root.a3_type = b"\x04"
    root.family = 0xFF
    body = _child(DiyType04.ComboBody, root)
    body.variant = 0
    body.speed = speed
    body.len_palette = len(palette) * 3
    body.palette = _diy_type04_palette(body, palette)
    body.seqlen = len(effects) * 2
    body.pairs = []
    for family, variant in effects:
        pair = _child(DiyType04.FamilyVariant, body)
        pair.family = family
        pair.variant = variant
        body.pairs.append(pair)
    body.padding = []
    root.body = body
    return _serialize_a3_scene_param(root)


def build_scene_activation(
    model: str,
    scene_code: int,
    music_code: int = 0,
    *,
    scene_type: int = 0,
    profile: ModelProfile | None = None,
) -> bytes:
    """Encode a scene selector using only the target's evidenced command grammar."""
    grammar = (profile or get_profile(model)).command_grammar
    if grammar in {"H1771", "H60B0"}:
        if type(scene_code) is not int or not 0 <= scene_code <= 0xFFFF or music_code:
            raise ValueError("Invalid native scene selector")
        root_type = H1771CommandWrite if grammar == "H1771" else H60b0CommandWrite
        root = root_type()
        root.header = b"\x33"
        root.opcode = root_type.CommandOp.multi
        root.body = _child(root_type.MultiCmd, root)
        root.body.sub = root_type.MultiSub.scene
        root.body.sub_body = _child(root_type.Selector, root.body)
        root.body.sub_body.code = scene_code
        root.body.sub_body.unknown_tail = bytes(14)
        return _serialize_xor(root)
    if grammar in {"H6072", "H6072-legacy", "H607C", "H617A", "H7020", "H705A"}:
        return build_h617a_scene(scene_code, scene_type=scene_type, root_type=_COMMAND_ROOTS[grammar][1])
    if grammar == "H6179":
        if music_code or scene_type:
            raise ValueError("H6179 scene selector has no music-code or scene-type field")
        return build_h6179_scene(scene_code)
    if grammar == "H6199":
        return build_h6199_scene(scene_code, music_code)
    if grammar in WHOLE_BULB_GRAMMARS | {"H6046", "H6099"}:
        if music_code or scene_type:
            raise ValueError(f"{grammar} scene selector has no music-code or scene-type field")
        root_type = _COMMAND_ROOTS[grammar][1]
        root = root_type()
        root.header = b"\x33"
        root.opcode = root_type.CommandOp.mode
        mode = _child(root_type.ModeBody, root)
        mode.sub_mode = root_type.ModeSel.scene
        detail = _child(root_type.SceneBody, mode)
        detail.scene_id = max(0, min(0xFFFF, scene_code))
        if grammar in WHOLE_BULB_GRAMMARS:
            detail.padding = bytes(14)
        elif grammar == "H6046":
            detail.unknown_tail = bytes(14)
        mode.detail = detail
        root.body = mode
        return _serialize_xor(root)
    raise ValueError(f"{model} has no generated scene activation grammar")


def build_h617a_scene(scene_code: int, *, scene_type: int = 0, root_type: Any = CommandWrite) -> bytes:
    root = root_type()
    root.header = b"\x33"
    root.opcode = root_type.CommandOp.multi
    multi = _child(root_type.MultiCmd, root)
    multi.sub = root_type.MultiSub.scene
    detail = _child(CommandWrite.SceneActivate, multi)
    detail.code = max(0, min(0xFFFF, scene_code))
    detail.scene_type = max(0, min(0xFF, scene_type))
    multi.sub_body = detail
    root.body = multi
    return _serialize_xor(root)


def build_h617a_diy_activation(diy_code: int, *, root_type: Any = CommandWrite) -> bytes:
    root = root_type()
    root.header = b"\x33"
    root.opcode = root_type.CommandOp.multi
    multi = _child(root_type.MultiCmd, root)
    multi.sub = root_type.MultiSub.diy
    selector = _child(GoveeCommon.DiySelector, multi)
    selector.code = diy_code
    multi.sub_body = selector
    root.body = multi
    return _serialize_xor(root)


def build_diy_activation(
    diy_code: int, model: str, *, profile: ModelProfile | None = None, companion: int | None = None
) -> bytes:
    if type(diy_code) is not int or not 0 <= diy_code <= 0xFFFF:
        raise ValueError("DIY code must be an integer from 0 to 65535")
    profile = profile or get_profile(model)
    if profile.diy_upload_transport == "single":
        raise ValueError("Inline DIY requires its complete body, not a resident selector")
    grammar = profile.command_grammar
    if grammar == "H607C":
        if companion is not None and (type(companion) is not int or not 0 <= companion <= 65535):
            raise ValueError("native DIY companion must be an unsigned word")
        root = H607cCommandWrite()
        root.header = b"\x33"
        root.opcode = H607cCommandWrite.CommandOp.multi
        root.body = _child(H607cCommandWrite.MultiCmd, root)
        root.body.sub = H607cCommandWrite.MultiSub.diy
        root.body.sub_body = _child(H607cCommandWrite.DiySelector, root.body)
        root.body.sub_body.code = diy_code
        root.body.sub_body.companion = 0 if companion is None else companion
        root.body.sub_body.unknown_tail = bytes(12)
        return _serialize_xor(root)
    if companion is not None:
        raise ValueError("this DIY selector has no companion word")
    if grammar in {"H1771", "H60B0"}:
        root_type = _COMMAND_ROOTS[grammar][1]
        root = root_type()
        root.header = b"\x33"
        root.opcode = root_type.CommandOp.multi
        root.body = _child(root_type.MultiCmd, root)
        root.body.sub = root_type.MultiSub.diy
        root.body.sub_body = _child(root_type.Selector, root.body)
        root.body.sub_body.code = diy_code
        root.body.sub_body.unknown_tail = bytes(14)
        return _serialize_xor(root)
    if grammar in {"H6072", "H6072-legacy", "H617A", "H7020", "H705A"}:
        return build_h617a_diy_activation(diy_code, root_type=_COMMAND_ROOTS[grammar][1])
    if grammar == "H6199":
        root_type = _COMMAND_ROOTS[grammar][1]
        root = root_type()
        root.header = b"\x33"
        root.opcode = root_type.CommandOp.mode
        mode = _child(root_type.ModeBody, root)
        mode.sub_mode = root_type.ModeSel.diy
        detail = _child(H6199DiySelector.DiySelector, mode)
        detail.code = diy_code
        detail.unknown_tail = bytes(14)
        mode.detail = detail
        root.body = mode
        return _serialize_xor(root)
    if grammar in WHOLE_BULB_GRAMMARS | {"H6046"}:
        root_type = _COMMAND_ROOTS[grammar][1]
        root = root_type()
        root.header = b"\x33"
        root.opcode = root_type.CommandOp.mode
        mode = _child(root_type.ModeBody, root)
        mode.sub_mode = root_type.ModeSel.diy
        detail = _child(root_type.DiyBody, mode)
        detail.code = diy_code
        if grammar in WHOLE_BULB_GRAMMARS:
            detail.padding = bytes(14)
        else:
            detail.unknown_tail = bytes(14)
        mode.detail = detail
        root.body = mode
        return _serialize_xor(root)
    if grammar == "H6099":
        return build_h6099_diy_activation(diy_code)
    if grammar == "H6179":
        return build_h6179_diy_activation(diy_code)
    raise ValueError(f"{model} has no generated DIY activation grammar")


def build_h6099_diy_activation(diy_code: int = 254) -> bytes:
    """Select a device-resident DIY code; this does not authorize DIY upload."""
    if type(diy_code) is not int or not 0 <= diy_code <= 0xFFFF:
        raise ValueError("DIY code must be an integer from 0 to 65535")
    root = H6099CommandWrite()
    root.header = b"\x33"
    root.opcode = H6099CommandWrite.CommandOp.mode
    mode = _child(H6099CommandWrite.ModeBody, root)
    mode.sub_mode = H6099CommandWrite.ModeSel.diy
    detail = _child(H6099CommandWrite.DiyBody, mode)
    detail.code = diy_code
    mode.detail = detail
    root.body = mode
    return _serialize_xor(root)
