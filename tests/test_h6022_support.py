import base64

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES
from custom_components.ha_govee_led_ble.effect_catalogue import MODEL_EFFECT_CATALOGUES
from custom_components.ha_govee_led_ble.effect_commands import build_h617a_diy_single
from custom_components.ha_govee_led_ble.effect_compiler import compile_effect
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem
from custom_components.ha_govee_led_ble.effect_scenes import scene_detail_payload
from custom_components.ha_govee_led_ble.native_scenes import build_native_scene_packets, native_scene_body_is_opaque
from custom_components.ha_govee_led_ble.protocol_admission import require_profile_packet
from custom_components.ha_govee_led_ble.protocol_core import H6022EffectUpload
from custom_components.ha_govee_led_ble.protocol_effect_bodies import parse_a3_effect_envelope
from custom_components.ha_govee_led_ble.scenes import SCENE_ENTRIES
from custom_components.ha_govee_led_ble.transport import reassemble_a3


def _scene(family: int):
    return next(entry for entry in SCENE_ENTRIES["H6022"] if entry.diy_effect_codes == (family,))


def test_h6022_declares_exact_scene_and_diy_catalogues():
    catalogue = MODEL_EFFECT_CATALOGUES["H6022"]

    assert {family.family for family in catalogue.effects} == {0, 5, 9, 14, 15, 82, 83}
    assert {mode.id for mode in catalogue.music_modes} == {
        "energetic",
        "rhythm",
        "spectrum",
        "rolling",
        "separation",
        "hopping",
        "piano_keys",
        "fountain",
        "day_and_night",
        "bloom",
        "shiny",
    }
    assert len(SCENE_ENTRIES["H6022"]) == 96


def test_h6022_opaque_family_classification_is_exact_model_scoped():
    scene = _scene(1)

    assert native_scene_body_is_opaque(scene, "H6022")
    assert not native_scene_body_is_opaque(scene, "H617A")


def test_h6022_opaque_scenes_round_trip_through_exact_upload_routes():
    professional = _scene(693)
    legacy = _scene(1)

    for scene, expected_subtype, expected_marker in ((professional, 0x58, 0x41), (legacy, 0x04, 0x00)):
        packets = build_native_scene_packets("H6022", scene)
        payload = base64.b64decode(scene.param, validate=True)
        envelope = reassemble_a3(packets[:-1])
        assert envelope[2] == expected_subtype
        assert envelope[3 : 3 + len(payload)] == payload
        assert envelope[3] == expected_marker
        detail = scene_detail_payload("H6022", scene.scene_id, scene.effect_id)
        assert detail["scene"]["parameter_kind"] == "opaque"
        assert detail["content"]["kind"] == "scene_builtin"


def test_h6022_family_zero_diy_is_not_inferred_from_legacy_scene_marker():
    custom = build_h617a_diy_single(0, 0, 50, ((255, 0, 0), (0, 255, 0)))
    legacy_scene = _scene(1)
    scene = build_native_scene_packets("H6022", legacy_scene)

    for packets, subtype in ((custom, 0x04), (scene[:-1], 0x04)):
        envelope = reassemble_a3(packets)
        parsed = parse_a3_effect_envelope(envelope, "H6022")
        assert isinstance(parsed, H6022EffectUpload)
        assert parsed.upload_type == subtype
        assert parsed.data == envelope[3:]
        for packet in packets:
            require_profile_packet(packet, MODEL_PROFILES["H6022"])

    template = next(item for item in MODEL_EFFECT_CATALOGUES["H6022"].templates if item.id == "template:single:0:0")
    compiled = compile_effect(LibraryItem.new("H6022 gradual", template.content), "H6022", diy_code=24)
    assert isinstance(parse_a3_effect_envelope(reassemble_a3(compiled.upload_packets), "H6022"), H6022EffectUpload)
