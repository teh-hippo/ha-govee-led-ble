from custom_components.ha_govee_led_ble.const import (
    BLE_DISCOVERABLE_MODELS,
    CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS,
    CONF_EFFECT_FAMILIES,
    CONF_PREFIX_EFFECT_NAMES,
    MODEL_PROFILES,
    UNSUPPORTED_PROFILE,
    ModelProfile,
    ReadDomain,
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


def test_existing_model_read_domains_preserve_current_behaviour():
    all_domains = frozenset(ReadDomain)
    h617a = MODEL_PROFILES["H617A"]

    assert h617a.read_domains == all_domains
    assert MODEL_PROFILES["H617E"] is h617a
    assert MODEL_PROFILES["H6076"].read_domains == {
        ReadDomain.IDENTITY,
        ReadDomain.POWER,
        ReadDomain.BRIGHTNESS,
    }
    assert MODEL_PROFILES["H6199"].read_domains == all_domains


def test_read_domain_properties_distinguish_identity_from_state():
    identity_only = ModelProfile("identity", read_domains=frozenset({ReadDomain.IDENTITY}))
    power_only = ModelProfile("power", read_domains=frozenset({ReadDomain.POWER}))
    mode_only = ModelProfile("mode", read_domains=frozenset({ReadDomain.MODE}))

    assert identity_only.can_read(ReadDomain.IDENTITY)
    assert identity_only.requires_notifications
    assert not identity_only.state_readable
    assert not identity_only.supports_color_mode_readback
    assert power_only.requires_notifications and power_only.state_readable
    assert mode_only.supports_color_mode_readback
    assert not ModelProfile("none").requires_notifications
    assert not ModelProfile("none").state_readable


def test_existing_segment_write_capabilities_remain_enabled():
    h617a = MODEL_PROFILES["H617A"]
    h6199 = MODEL_PROFILES["H6199"]

    assert h617a.segment_count == h6199.segment_count == 15
    assert h617a.supports_segment_colour_writes
    assert h617a.supports_segment_brightness_writes
    assert h617a.supports_segments
    # Both models paint segments. The H6199 was gated off until captured app writes on it were
    # reproduced byte for byte, whole-strip and per-segment, including the union frame that proves
    # the field is a mask and not an index.
    assert h6199.supports_segment_colour_writes
    assert h6199.supports_segment_brightness_writes
    assert h6199.supports_segments


def test_segment_write_capabilities_are_independent_and_default_false():
    unsupported = ModelProfile("x")
    colour_only = ModelProfile("colour", segment_count=15, supports_segment_colour_writes=True)
    brightness_only = ModelProfile("brightness", segment_count=15, supports_segment_brightness_writes=True)

    assert unsupported.segment_count == 0
    assert not unsupported.supports_segment_colour_writes
    assert not unsupported.supports_segment_brightness_writes
    assert not unsupported.supports_segments
    assert colour_only.supports_segments
    assert brightness_only.supports_segments


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
    assert not profile.supports_segment_colour_writes
    assert not profile.supports_segment_brightness_writes
    assert not profile.supports_segments
    assert profile.whole_device_mask == 0x007F
    assert wire_model("H6076") == "H617A"
    assert protocol_model("H6076") == "H6076"


def test_unknown_models_fail_closed():
    assert get_profile("nope") is UNSUPPORTED_PROFILE
    assert not UNSUPPORTED_PROFILE.supports_segment_colour_writes
    assert not UNSUPPORTED_PROFILE.supports_segment_brightness_writes
    assert not UNSUPPORTED_PROFILE.supports_segments
    assert not UNSUPPORTED_PROFILE.supports_music_mode
    assert resolve_model("H617A-extra") is None
    assert resolve_model("H9999") is None
    assert wire_model("H9999") is None


def test_h6102_is_manually_supported_but_not_ble_discoverable():
    assert resolve_model("H6102") == "H6102"
    assert "H6102" not in BLE_DISCOVERABLE_MODELS
    assert model_from_ble_name("Govee_H6102_ABCD") is None


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
