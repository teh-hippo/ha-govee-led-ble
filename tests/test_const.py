from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, ModelProfile, get_profile


def test_segment_count_and_supports_segments():
    assert MODEL_PROFILES["H617A"].segment_count == 15
    assert MODEL_PROFILES["H6199"].segment_count == 15
    assert MODEL_PROFILES["H617A"].supports_segments
    assert MODEL_PROFILES["H6199"].supports_segments


def test_supports_segments_defaults_false():
    assert ModelProfile("x").segment_count == 0
    assert not ModelProfile("x").supports_segments


def test_get_profile_unknown_falls_back_to_h617a():
    assert get_profile("nope") is MODEL_PROFILES["H617A"]


def test_timer_and_poweroff_capabilities():
    for model in ("H617A", "H6199"):
        assert MODEL_PROFILES[model].supports_timers
    # Power-off memory: H6199 exposes it; the H617A app has no such setting (confirmed 2026-07-10).
    assert MODEL_PROFILES["H6199"].supports_poweroff_memory
    assert not MODEL_PROFILES["H617A"].supports_poweroff_memory


def test_timer_and_poweroff_capabilities_default_false():
    assert not ModelProfile("x").supports_timers
    assert not ModelProfile("x").supports_poweroff_memory
