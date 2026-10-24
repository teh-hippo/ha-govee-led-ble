"""Tests for model-specific music protocol metadata."""

from dataclasses import replace

import pytest

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, device_profile
from custom_components.ha_govee_led_ble.music_protocol import (
    _MUSIC_PARAMETER_WRITE_CODES_BY_MODEL,
    MUSIC_MODE_CODES_BY_MODEL,
    GoveeCommon,
    H1a42MusicParameters,
    H1a42MusicWrite,
    H61f5MusicParameters,
    H61f5MusicWrite,
    H66a0MusicParameters,
    H66a0MusicWrite,
    H6076MusicBody,
    H6076MusicWrite,
    H6097MusicParameters,
    H6097MusicWrite,
    H6099CommandWrite,
    H6099MusicParameters,
    H6179CommandWrite,
    H6199CommandWrite,
    H7020CommandWrite,
    H7025MusicBody,
    H7025MusicWrite,
    MusicBody,
    music_code_for,
    music_codebook,
    music_mode_has_parameter_write,
    music_mode_supports_style,
    music_slug_for,
)

_H617A_CODES = {
    "energetic": 0x05,
    "rhythm": 0x03,
    "spectrum": 0x04,
    "rolling": 0x06,
    "separation": 0x32,
    "hopping": 0x33,
    "piano_keys": 0x34,
    "fountain": 0x35,
    "day_and_night": 0x37,
    "bloom": 0x30,
    "shiny": 0x31,
}


def test_model_music_codebooks_preserve_existing_models_and_add_h6179() -> None:
    assert MUSIC_MODE_CODES_BY_MODEL["H617A"] == _H617A_CODES
    assert music_codebook(MODEL_PROFILES["H617E"]) == _H617A_CODES
    assert MUSIC_MODE_CODES_BY_MODEL["H6099"] == _H617A_CODES
    assert MUSIC_MODE_CODES_BY_MODEL["H6179"] == {"mode_0": 0x00, "mode_1": 0x01}
    assert MUSIC_MODE_CODES_BY_MODEL["H6199"] == {
        "energetic": 0x05,
        "rhythm": 0x03,
        "spectrum": 0x04,
        "rolling": 0x06,
    }
    assert MUSIC_MODE_CODES_BY_MODEL["H7020"] == {
        "rhythm": 0x03,
        "spectrum": 0x04,
        "energetic": 0x05,
        "rolling": 0x06,
    }


def test_music_code_lookup_and_reverse_lookup_are_model_specific() -> None:
    for model, codes in MUSIC_MODE_CODES_BY_MODEL.items():
        for slug, code in codes.items():
            assert music_code_for(model, slug) == code
            assert music_slug_for(model, code) == slug

    assert music_code_for("H6179", "mode_1") == 0x01
    assert music_slug_for("H617A", 0x01) is None
    assert music_slug_for("H6179", 0x03) is None


def test_unknown_music_models_modes_and_codes_fail_closed() -> None:
    with pytest.raises(ValueError, match="no music mode codebook"):
        music_code_for("H9999", "rhythm")
    with pytest.raises(ValueError, match="does not support music mode"):
        music_code_for("H6199", "bloom")
    with pytest.raises(ValueError, match="does not support music mode"):
        music_code_for("H6179", "rhythm")

    assert music_slug_for("H9999", 0x03) is None
    assert music_slug_for("H6179", 0xFF) is None
    assert not music_mode_supports_style("H9999", 0x03)
    assert not music_mode_has_parameter_write("H9999", 0x32)


def test_music_style_support_is_model_specific() -> None:
    for model in ("H617A", "H617E"):
        assert music_mode_supports_style(model, 0x03)
        assert music_mode_supports_style(model, 0x30)
        assert music_mode_supports_style(model, 0x31)
        assert not music_mode_supports_style(model, 0x05)

    assert music_mode_supports_style("H6199", 0x03)
    assert not music_mode_supports_style("H6199", 0x30)
    assert not music_mode_supports_style("H6179", 0x00)
    assert not music_mode_supports_style("H6179", 0x01)
    assert not music_mode_supports_style("H7020", 0x03)


def test_music_parameter_writes_are_model_specific() -> None:
    parameter_codes = {0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x37}
    for model in ("H617A", "H617E"):
        assert all(music_mode_has_parameter_write(model, code) for code in parameter_codes)
        assert not music_mode_has_parameter_write(model, 0x03)

    assert not any(music_mode_has_parameter_write("H6199", code) for code in _H617A_CODES.values())
    assert not music_mode_has_parameter_write("H6179", 0x00)
    assert not music_mode_has_parameter_write("H6179", 0x01)
    assert not music_mode_has_parameter_write("H7020", 0x03)


def test_h6076_codebook_is_its_own_numbering_not_the_h617a_one() -> None:
    codes = {
        "energetic": 0x00,
        "hopping": 0x02,
        "rhythm": 0x04,
        "beat": 0x06,
        "spray": 0x07,
        "bounce": 0x08,
        "separation": 0x32,
        "skittles": 0x4D,
        "candy_crush": 0x4E,
        "fusion": 0x4F,
        "torch": 0x50,
        "shiny": 0x51,
    }
    assert MUSIC_MODE_CODES_BY_MODEL["H6076"] == codes
    assert set(MODEL_PROFILES["H6076"].music_modes) == set(codes)
    assert music_code_for("H6076", "shiny") == 0x51 != music_code_for("H617A", "shiny")
    assert music_slug_for("H6076", 0x06) == "beat" and music_slug_for("H617A", 0x06) == "rolling"
    assert [code for code in codes.values() if music_mode_supports_style("H6076", code)] == [0x04]
    assert {code for code in codes.values() if music_mode_has_parameter_write("H6076", code)} == {
        0x32,
        0x4D,
        0x4E,
        0x4F,
        0x50,
        0x51,
    }


def test_codebooks_match_generated_kaitai_enums_and_gate_on_effective_profile() -> None:
    expected_enums = {
        "H6097": H6097MusicWrite.MusicMode,
        "H617A": GoveeCommon.MusicMode,
        "H6099": H6099CommandWrite.MusicMode,
        "H66A0": H66a0MusicWrite.MusicMode,
        "H1A42": H1a42MusicWrite.MusicMode,
        "H61F5": H61f5MusicWrite.MusicMode,
        "H6076": H6076MusicWrite.MusicMode,
        "H6179": H6179CommandWrite.MusicEffect,
        "H6199": H6199CommandWrite.MusicMode,
        "H7020": H7020CommandWrite.MusicMode,
        "H7025": H7025MusicWrite.MusicMode,
    }
    assert set(MUSIC_MODE_CODES_BY_MODEL) == set(expected_enums)
    for grammar, enum_type in expected_enums.items():
        assert MUSIC_MODE_CODES_BY_MODEL[grammar] == {mode.name: int(mode) for mode in enum_type}

    expected_parameter_enums = {
        "H6097": H6097MusicParameters.CompanionMode,
        "H617A": MusicBody.MusicMode,
        "H6099": H6099MusicParameters.MusicMode,
        "H66A0": H66a0MusicParameters.MusicMode,
        "H1A42": H1a42MusicParameters.MusicMode,
        "H61F5": H61f5MusicParameters.MusicMode,
        "H6076": H6076MusicBody.MusicMode,
        "H7025": H7025MusicBody.MusicMode,
    }
    for grammar, enum_type in expected_parameter_enums.items():
        assert _MUSIC_PARAMETER_WRITE_CODES_BY_MODEL[grammar] == {int(mode) for mode in enum_type}

    effective_profiles = [
        *((model, profile) for model, profile in MODEL_PROFILES.items()),
        ("H6076", device_profile("H6076", None, None)),
        ("H6102", device_profile("H6102", None, None)),
        ("H6102", device_profile("H6102", 10, 1)),
        ("H6125", device_profile("H6125", None, None)),
        ("H6125", device_profile("H6125", 1, 1, firmware="1.00.11", hardware="1.00.01")),
        ("H6125", device_profile("H6125", 1, 1, firmware="1.04.08", hardware="1.00.04")),
        ("H6125", device_profile("H6125", 1, 2, firmware="1.06.00", hardware="1.00.03")),
        ("H6125", device_profile("H6125", 1, 2, firmware="1.07.00", hardware="1.00.03")),
        ("H6125", device_profile("H6125", 10, 1, firmware="2.03.99", hardware="2.01.01")),
        ("H6125", device_profile("H6125", 10, 2, firmware="3.04.37", hardware="3.01.10")),
        ("H6199", device_profile("H6199", 1, 1)),
        ("H7020", device_profile("H7020", None, None)),
    ]
    for model, profile in effective_profiles:
        selected_grammar = profile.music_grammar or profile.command_grammar
        if selected_grammar not in MUSIC_MODE_CODES_BY_MODEL:
            continue
        codebook = music_codebook(profile)
        for slug, code in codebook.items():
            assert music_slug_for(model, code, profile=profile) == slug
            if slug in profile.music_modes:
                assert music_code_for(model, slug, profile=profile) == code
            else:
                with pytest.raises(ValueError, match="does not support music mode"):
                    music_code_for(model, slug, profile=profile)


def test_h7020_music_grammar_is_independent_of_basic_command_grammar(monkeypatch) -> None:
    model = "TEST-H7020-MUSIC"
    profile = replace(
        MODEL_PROFILES["H7020"],
        name="Synthetic H7020 music",
        command_grammar="H617A",
        music_grammar="H7020",
    )
    monkeypatch.setitem(MODEL_PROFILES, model, profile)

    assert music_code_for(model, "rhythm") == 0x03
    assert music_slug_for(model, 0x04) == "spectrum"
    assert not music_mode_supports_style(model, 0x03)
    assert not music_mode_has_parameter_write(model, 0x03)
