from custom_components.ha_govee_led_ble.const import (
    MODEL_PROFILES,
    UNSUPPORTED_PROFILE,
    ModelProfile,
    get_profile,
    resolve_model,
)


def test_segment_count_and_supports_segments():
    assert MODEL_PROFILES["H617A"].segment_count == 15
    assert MODEL_PROFILES["H6199"].segment_count == 15
    assert MODEL_PROFILES["H617A"].supports_segments
    assert MODEL_PROFILES["H6199"].supports_segments


def test_supports_segments_defaults_false():
    assert ModelProfile("x").segment_count == 0
    assert not ModelProfile("x").supports_segments


def test_unknown_models_fail_closed():
    assert get_profile("nope") is UNSUPPORTED_PROFILE
    assert not UNSUPPORTED_PROFILE.supports_segments
    assert not UNSUPPORTED_PROFILE.supports_music_mode
    assert resolve_model("H617A-extra") == "H617A"
    assert resolve_model("H9999") is None


def test_timer_and_poweroff_capabilities():
    assert MODEL_PROFILES["H617A"].supports_timers
    assert not MODEL_PROFILES["H6199"].supports_timers
    assert all(not MODEL_PROFILES[model].supports_poweroff_memory for model in ("H617A", "H6199"))


def test_timer_and_poweroff_capabilities_default_false():
    assert not ModelProfile("x").supports_timers
    assert not ModelProfile("x").supports_poweroff_memory


def test_model_specific_music_and_custom_effect_capabilities():
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
    assert MODEL_PROFILES["H617A"].custom_effect_kinds == {
        "segments",
        "sketch",
        "vibrant",
        "flat",
        "combo",
    }
    assert MODEL_PROFILES["H6199"].custom_effect_kinds == {"segments"}
