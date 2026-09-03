import pytest

from custom_components.ha_govee_led_ble.const import (
    BLE_DISCOVERABLE_MODELS,
    CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS,
    CONF_EFFECT_FAMILIES,
    CONF_PREFIX_EFFECT_NAMES,
    MODEL_PROFILES,
    UNSUPPORTED_PROFILE,
    ModelProfile,
    ReadDomain,
    SupportQuality,
    always_include_custom_effects_from_options,
    default_effect_families,
    effect_families_from_options,
    get_profile,
    model_from_ble_name,
    prefix_effect_names_from_options,
    protocol_model,
    resolve_model,
    wire_model,
)


def test_segment_count_and_supports_segments():
    assert MODEL_PROFILES["H617A"].segment_count == 15
    assert MODEL_PROFILES["H6199"].segment_count == 15
    assert MODEL_PROFILES["H617A"].segment_group_count == 5
    assert MODEL_PROFILES["H6199"].segment_group_count == 4
    assert MODEL_PROFILES["H617A"].supports_segments
    # Both models paint segments. The H6199 was gated off until captured app writes on it were
    # reproduced byte for byte, whole-strip and per-segment, including the union frame that proves
    # the field is a mask and not an index.
    assert MODEL_PROFILES["H6199"].supports_segments


def test_supports_segments_defaults_false():
    assert ModelProfile("x").segment_count == 0
    assert not ModelProfile("x").supports_segments


def test_h617a_and_h617e_share_wire_behaviour_but_keep_exact_product_profiles():
    h617a = MODEL_PROFILES["H617A"]
    h617e = MODEL_PROFILES["H617E"]
    assert h617e is not h617a
    assert h617e.name == "H617E LED Strip"
    assert h617e.support_quality is SupportQuality.COMPATIBLE
    assert h617e.scene_catalogue_sku == "H617E"
    assert h617e.read_domains == h617a.read_domains
    assert h617e.supports_scenes
    assert h617e.supports_music_mode
    assert len(h617e.music_modes) == 11
    assert h617e.segment_count == 15
    assert h617e.supports_segments
    assert h617e.supports_advanced_effects
    assert h617e.supports_multi_layered_effects
    assert h617e.connection_idle_timeout == 3.0
    assert resolve_model("H617E") == "H617E"
    assert protocol_model("H617E") == "H617A"
    assert wire_model("H617E") == "H617A"


def test_h6076_profile_is_basic_and_fail_closed():
    profile = MODEL_PROFILES["H6076"]
    assert profile.support_quality is SupportQuality.PARTIAL
    assert profile.state_readable
    assert profile.read_domains == {
        ReadDomain.POWER,
        ReadDomain.BRIGHTNESS,
        ReadDomain.FIRMWARE,
        ReadDomain.HARDWARE,
    }
    assert profile.setup_required_read_domains == {ReadDomain.POWER, ReadDomain.BRIGHTNESS}
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


def test_h6102_profile_is_manual_only_and_fail_closed():
    profile = MODEL_PROFILES["H6102"]

    assert profile.support_quality is SupportQuality.EXPERIMENTAL
    assert profile.wire_model == "H6102"
    assert profile.scene_catalogue_sku == "H6102"
    assert not profile.read_domains
    assert not profile.supports_rgb
    assert "H6102" not in BLE_DISCOVERABLE_MODELS
    assert model_from_ble_name("Govee_H6102_ABCD") is None


def test_setup_required_domains_must_be_readable():
    with pytest.raises(ValueError, match="setup-required"):
        ModelProfile("x", setup_required_read_domains=frozenset({ReadDomain.POWER}))


def test_unknown_models_fail_closed():
    assert get_profile("nope") is UNSUPPORTED_PROFILE
    assert not UNSUPPORTED_PROFILE.supports_segments
    assert not UNSUPPORTED_PROFILE.supports_music_mode
    assert resolve_model("H617A-extra") is None
    assert resolve_model("H9999") is None
    assert wire_model("H9999") is None


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
