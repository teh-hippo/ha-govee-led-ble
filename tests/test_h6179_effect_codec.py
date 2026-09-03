"""H6179 DIY effect codec and compiled transport vectors."""

from __future__ import annotations

import io

import pytest
from kaitaistruct import KaitaiStream

from custom_components.ha_govee_led_ble.effect_compiler import (
    ActivationMode,
    ActivationObservation,
    ActivationPolicy,
    CompiledEffect,
    UploadTransport,
    compile_effect,
)
from custom_components.ha_govee_led_ble.effect_domain import (
    EffectPair,
    H6179MixedDiyEffect,
    H6179SingleDiyEffect,
    LibraryItem,
)
from custom_components.ha_govee_led_ble.effect_protocol_decoder import decode_effect_frames
from custom_components.ha_govee_led_ble.generated_protocol_adapter import H6179DiyBody
from custom_components.ha_govee_led_ble.h6179_effect_codec import (
    H6179EffectCodecError,
    decode_h6179_effect,
    encode_h6179_effect,
)

H = bytes.fromhex
RED = (255, 0, 0)
BLUE = (0, 0, 255)


def _round_trip_generated(body: bytes):
    parsed = H6179DiyBody(KaitaiStream(io.BytesIO(body)))
    parsed._read()
    parsed._fetch_instances()
    parsed._check()
    output = KaitaiStream(io.BytesIO(bytes(len(body))))
    parsed._write(output)
    assert output.to_byte_array() == body
    return parsed


@pytest.mark.parametrize(
    ("content", "body", "frames"),
    [
        (
            H6179SingleDiyEffect("H6179", 0, 0, 100, (RED,)),
            H("fe00006403ff0000"),
            (
                H("a1020001000000000000000000000000000000a2"),
                H("a10201fe00006403ff00000000000000000000c4"),
                H("a102ff000000000000000000000000000000005c"),
            ),
        ),
        (
            H6179MixedDiyEffect("H6179", (EffectPair(0, 0), EffectPair(2, 0)), 50, (RED, BLUE)),
            H("feff003206ff00000000ff0400000200"),
            (
                H("a1020001000000000000000000000000000000a2"),
                H("a10201feff003206ff00000000ff040000020091"),
                H("a102ff000000000000000000000000000000005c"),
            ),
        ),
    ],
)
def test_h6179_effect_body_frames_and_round_trip_are_deterministic(
    content: H6179SingleDiyEffect | H6179MixedDiyEffect,
    body: bytes,
    frames: tuple[bytes, ...],
) -> None:
    assert encode_h6179_effect(content) == body
    assert decode_h6179_effect(body) == content

    compiled = compile_effect(LibraryItem.new("DIY", content), "H6179", diy_code=0x1234)

    assert compiled.upload_packets == frames
    assert compiled.activation_packet == H("33050a341200000000000000000000000000001a")
    assert compiled.upload_transport is UploadTransport.H6179_A1_02
    assert compiled.activation_observation is ActivationObservation.DIY_CODE
    assert compiled.activation_policy is ActivationPolicy.OBSERVED_DISPOSABLE_APPROVAL
    assert compiled.overwrite_risk is True
    assert compiled.activation_evidence == (
        "h6179_diy_code_observed",
        "h6179_diy_code_approved_disposable",
    )
    assert (
        decode_effect_frames(
            compiled.upload_packets,
            compiled.model,
            compiled.upload_transport.value,
        )
        == content
    )
    assert all(packet[0] == 0xA1 for packet in compiled.upload_packets)


def test_h6179_decoder_rejects_cross_transport_and_invalid_body() -> None:
    content = H6179SingleDiyEffect("H6179", 0, 0, 50, (RED,))
    compiled = compile_effect(LibraryItem.new("DIY", content), "H6179", diy_code=1)

    with pytest.raises(ValueError, match="cannot decode"):
        decode_effect_frames(compiled.upload_packets, "H617A", compiled.upload_transport.value)
    with pytest.raises(ValueError, match="invalid prefix"):
        decode_effect_frames(compiled.upload_packets, "H6179", UploadTransport.A3.value)
    with pytest.raises(H6179EffectCodecError, match="invalid H6179 DIY body"):
        decode_h6179_effect(H("fd00003203ff0000"))


@pytest.mark.parametrize(
    "body",
    [
        H("fe7f102030"),
        H("fe00016403ff0000"),
        H("fe00006503ff0000"),
        H("fe00006400"),
        H("fe00006403ff000001"),
        H("feff003203ff000000"),
        H("feff003203ff000003000001"),
    ],
)
def test_h6179_diy_raw_values_and_opaque_bytes_round_trip_but_semantics_fail_closed(body: bytes) -> None:
    _round_trip_generated(body)

    with pytest.raises(H6179EffectCodecError, match="unsupported semantics"):
        decode_h6179_effect(body)


def test_h6179_diy_unknown_family_uses_generated_opaque_body() -> None:
    parsed = _round_trip_generated(H("fe7f102030"))

    assert isinstance(parsed.body, H6179DiyBody.OpaqueBody)
    assert parsed.body.data == H("102030")
    assert parsed.opaque == b""


def test_h6179_diy_zero_opaque_transport_padding_is_semantically_ignored() -> None:
    assert decode_h6179_effect(H("fe00006403ff000000000000")) == H6179SingleDiyEffect("H6179", 0, 0, 100, (RED,))


def test_compiled_effect_preserves_legacy_positional_custom_constructor() -> None:
    compiled = CompiledEffect(
        "item",
        2,
        "H617A",
        "h617a_single",
        24,
        ActivationMode.CUSTOM,
        None,
        (b"upload",),
        b"activate",
        "0" * 64,
        ("legacy_evidence",),
        7,
    )

    assert compiled.evidence_codes == ("legacy_evidence",)
    assert compiled.compiler_version == 7
    assert compiled.activation_observation is ActivationObservation.DIY_CODE
    assert compiled.upload_transport is UploadTransport.A3


@pytest.mark.parametrize(
    ("model", "content_kind", "activation_mode", "expected"),
    [
        ("H6199", "scene_builtin", ActivationMode.SCENE, ActivationObservation.EFFECT),
        ("H6199", "palette_diy", ActivationMode.CUSTOM, ActivationObservation.UNKNOWN_SCENE_CODE),
        ("H617A", "h617a_single", ActivationMode.CUSTOM, ActivationObservation.DIY_CODE),
    ],
)
def test_compiled_effect_derives_legacy_keyword_activation_observation(
    model: str,
    content_kind: str,
    activation_mode: ActivationMode,
    expected: ActivationObservation,
) -> None:
    compiled = CompiledEffect(
        item_id="item",
        item_version=1,
        model=model,
        content_kind=content_kind,
        diy_code=24,
        activation_mode=activation_mode,
        expected_effect="Scene" if activation_mode is ActivationMode.SCENE else None,
        upload_packets=(),
        activation_packet=b"activate",
        artifact_sha256="0" * 64,
    )

    assert compiled.activation_observation is expected
