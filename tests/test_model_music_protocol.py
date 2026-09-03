"""Tests for model-specific music protocol metadata."""

import pytest

from custom_components.ha_govee_led_ble.music_protocol import (
    MUSIC_MODE_CODES_BY_MODEL,
    music_code_for,
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
    assert MUSIC_MODE_CODES_BY_MODEL["H617E"] == _H617A_CODES
    assert MUSIC_MODE_CODES_BY_MODEL["H6179"] == {"mode_0": 0x00, "mode_1": 0x01}
    assert MUSIC_MODE_CODES_BY_MODEL["H6199"] == {
        "energetic": 0x05,
        "rhythm": 0x03,
        "spectrum": 0x04,
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


def test_music_parameter_writes_are_model_specific() -> None:
    parameter_codes = {0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x37}
    for model in ("H617A", "H617E"):
        assert all(music_mode_has_parameter_write(model, code) for code in parameter_codes)
        assert not music_mode_has_parameter_write(model, 0x03)

    assert not any(music_mode_has_parameter_write("H6199", code) for code in _H617A_CODES.values())
    assert not music_mode_has_parameter_write("H6179", 0x00)
    assert not music_mode_has_parameter_write("H6179", 0x01)
