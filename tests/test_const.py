import pytest

from custom_components.ha_govee_led_ble.const import (
    CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS,
    CONF_EFFECT_FAMILIES,
    CONF_PREFIX_EFFECT_NAMES,
    MODEL_PROFILES,
    UNSUPPORTED_PROFILE,
    ModelProfile,
    always_include_custom_effects_from_options,
    default_effect_categories,
    default_effect_families,
    effect_families_from_options,
    get_profile,
    h6125_rc3_variant_supported,
    prefix_effect_names_from_options,
    protocol_model,
    resolve_model,
    supported_effect_categories,
    wire_model,
)


def test_segment_count_and_supports_segments():
    assert MODEL_PROFILES["H617A"].segment_count == 15
    assert MODEL_PROFILES["H6199"].segment_count == 15
    assert MODEL_PROFILES["H617A"].supports_segments
    # Both models paint segments. The H6199 was gated off until captured app writes on it were
    # reproduced byte for byte, whole-strip and per-segment, including the union frame that proves
    # the field is a mask and not an index.
    assert MODEL_PROFILES["H6199"].supports_segments


def test_supports_segments_defaults_false():
    assert ModelProfile("x").segment_count == 0
    assert not ModelProfile("x").supports_segments


def test_h617a_and_h617e_share_complete_feature_profile():
    profile = MODEL_PROFILES["H617A"]
    assert MODEL_PROFILES["H617E"] is profile
    assert profile.supports_scenes
    assert profile.supports_music_mode
    assert len(profile.music_modes) == 11
    assert profile.segment_count == 15
    assert profile.supports_segments
    assert profile.supports_advanced_effects
    assert profile.supports_multi_layered_effects
    assert profile.connection_idle_timeout == 3.0
    assert resolve_model("H617E") == "H617E"
    assert protocol_model("H617E") == "H617A"
    assert wire_model("H617E") == "H617A"


def test_h6076_profile_is_basic_and_fail_closed():
    profile = MODEL_PROFILES["H6076"]
    assert profile.state_readable
    assert profile.supports_rgb and profile.supports_color_temperature
    assert (profile.min_color_temp_kelvin, profile.max_color_temp_kelvin) == (2700, 6500)
    assert not profile.supports_color_mode_readback
    assert not profile.supports_custom_effects
    assert not profile.supports_scenes
    assert not profile.supports_music_mode
    assert not profile.supports_segments
    assert profile.whole_device_mask == 0x007F
    assert wire_model("H6076") == "H617A"
    assert protocol_model("H6076") == "H6076"


def test_h6125_rc3_exposes_only_the_mapped_candidate_workflows():
    profile = MODEL_PROFILES["H6125"]

    assert profile.state_readable
    assert profile.supports_color_mode_readback
    assert profile.supports_rgb
    assert profile.supports_color_temperature
    assert profile.supports_scenes
    assert not profile.supports_scene_editing
    assert profile.supports_custom_effects
    assert not profile.supports_h617a_custom_effects
    assert profile.supports_h617a_type04_effects
    assert profile.supports_music_mode
    assert not profile.supports_advanced_effects
    assert profile.supports_multi_layered_effects
    assert profile.segment_count == 15
    assert profile.supports_segments
    assert profile.connection_idle_timeout == 3.0
    assert protocol_model("H6125") == "H6125"
    assert wire_model("H6125") == "H617A"
    assert supported_effect_categories("H6125") == ("scenes", "effects", "multi_layered", "reactive")
    assert default_effect_categories("H6125") == ("scenes", "effects", "multi_layered", "reactive")
    assert default_effect_families("H6125") == frozenset({"scenes", "music"})


def test_unknown_models_fail_closed():
    assert get_profile("nope") is UNSUPPORTED_PROFILE
    assert not UNSUPPORTED_PROFILE.supports_segments
    assert not UNSUPPORTED_PROFILE.supports_music_mode
    assert resolve_model("H617A-extra") is None
    assert resolve_model("H9999") is None
    assert wire_model("H9999") is None


@pytest.mark.parametrize(
    ("pact_type", "pact_code", "firmware", "hardware", "expected"),
    [
        (1, 2, "1.07.00", "1.00.03", True),
        (1, 2, "1.06.99", "1.00.03", False),
        (1, 2, "1.07.00", "1.00.02", False),
        (1, 2, "1.07.00", "4.00.00", False),
        (1, 1, "1.07.00", "1.00.03", False),
        (10, 1, "3.01.00", "1.00.03", False),
        (None, None, "1.07.00", "1.00.03", False),
        (1, 2, "unknown", "1.00.03", False),
    ],
)
def test_h6125_rc3_variant_support(
    pact_type: int | None,
    pact_code: int | None,
    firmware: str,
    hardware: str,
    expected: bool,
):
    assert (
        h6125_rc3_variant_supported(
            pact_type=pact_type,
            pact_code=pact_code,
            firmware=firmware,
            hardware=hardware,
        )
        is expected
    )


def test_effect_family_defaults_and_options():
    assert default_effect_families("H617A") == {"scenes", "music"}
    assert default_effect_families("H6199") == {"video"}
    assert effect_families_from_options("H6199", {}) == {"video"}
    assert effect_families_from_options(
        "H6199",
        {CONF_EFFECT_FAMILIES: ["scenes", "music", "unsupported"]},
    ) == {"scenes", "music"}
    assert prefix_effect_names_from_options({}) is False
    assert prefix_effect_names_from_options({CONF_PREFIX_EFFECT_NAMES: True}) is True
    assert prefix_effect_names_from_options({CONF_PREFIX_EFFECT_NAMES: 1}) is False
    assert always_include_custom_effects_from_options({}) is False
    assert always_include_custom_effects_from_options({CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS: True}) is True
    assert always_include_custom_effects_from_options({CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS: 1}) is False


def test_model_specific_music_capabilities():
    assert MODEL_PROFILES["H617A"].music_modes == (
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
    )
    assert MODEL_PROFILES["H6199"].music_modes == ("energetic", "rhythm", "spectrum", "rolling")
    assert MODEL_PROFILES["H617A"].supports_music_color
    assert MODEL_PROFILES["H6199"].supports_music_color
    assert (MODEL_PROFILES["H617A"].music_sensitivity_min, MODEL_PROFILES["H617A"].music_sensitivity_max) == (0, 99)
    assert (MODEL_PROFILES["H6199"].music_sensitivity_min, MODEL_PROFILES["H6199"].music_sensitivity_max) == (1, 100)
    assert not MODEL_PROFILES["H6199"].supports_white_brightness
    assert not MODEL_PROFILES["H6199"].static_readback_echoes_color
    assert MODEL_PROFILES["H6199"].supports_video_sound_effects
