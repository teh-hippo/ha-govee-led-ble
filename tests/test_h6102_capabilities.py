"""H6102 capability resolution tests."""

import pytest

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, ModelProfile
from custom_components.ha_govee_led_ble.h6102_capabilities import (
    H6102FirmwareSource,
    resolve_h6102_capabilities,
)
from custom_components.ha_govee_led_ble.h6102_protocol import H6102RgbVariant


def _assert_advanced_surfaces_disabled(profile: ModelProfile) -> None:
    assert not profile.read_domains
    assert not profile.requires_notifications
    assert not profile.state_readable
    assert not profile.supports_color_mode_readback
    assert not profile.supports_color_temperature
    assert not profile.supports_segments
    assert not profile.supports_segment_colour_writes
    assert not profile.supports_segment_brightness_writes
    assert not profile.supports_custom_effects
    assert not profile.supports_scenes
    assert not profile.supports_music_mode
    assert not profile.supports_music_color
    assert not profile.supports_video_mode
    assert not profile.supports_video_sound_effects
    assert not profile.supports_advanced_effects
    assert not profile.supports_multi_layered_effects
    assert not profile.supports_white_balance
    assert not profile.supports_relative_brightness
    assert not profile.supports_blank_screen
    assert not profile.supports_white_brightness
    assert not profile.static_readback_echoes_color


def test_base_profile_is_unresolved_manual_only() -> None:
    profile = MODEL_PROFILES["H6102"]

    assert profile.name == "H6102 LED Strip"
    assert profile.wire_model == "H6102"
    assert profile.connection_idle_timeout == 3.0
    assert not profile.supports_rgb
    assert profile.whole_device_mask == 0
    assert profile.segment_count == 0
    _assert_advanced_surfaces_disabled(profile)


@pytest.mark.parametrize(
    ("firmware", "firmware_source"),
    [
        (None, None),
        ("", "configured"),
        ("1..3", "configured"),
        ("1.03.x", "ble"),
        ("1.03.01", None),
    ],
)
def test_unknown_or_invalid_firmware_fails_closed(
    firmware: str | None,
    firmware_source: H6102FirmwareSource | None,
) -> None:
    resolution = resolve_h6102_capabilities(firmware, firmware_source)

    assert resolution.profile is MODEL_PROFILES["H6102"]
    assert resolution.rgb_variant is None
    assert resolution.firmware_source == firmware_source
    assert resolution.capability_resolution_reason == "firmware_unknown"


@pytest.mark.parametrize("firmware_source", ["configured", "ble"])
@pytest.mark.parametrize("firmware", ["1.03.00", "1.3", "1.2.9999"])
def test_legacy_firmware_is_classified_but_rgb_remains_disabled(
    firmware: str,
    firmware_source: H6102FirmwareSource,
) -> None:
    resolution = resolve_h6102_capabilities(firmware, firmware_source)

    assert resolution.profile is MODEL_PROFILES["H6102"]
    assert resolution.rgb_variant is H6102RgbVariant.LEGACY
    assert resolution.firmware_source == firmware_source
    assert resolution.capability_resolution_reason == "legacy_capture_required"


@pytest.mark.parametrize("firmware_source", ["configured", "ble"])
@pytest.mark.parametrize("firmware", ["1.03.01", "1.3.1", "1.10.00"])
def test_extended_firmware_enables_only_whole_device_rgb(
    firmware: str,
    firmware_source: H6102FirmwareSource,
) -> None:
    resolution = resolve_h6102_capabilities(firmware, firmware_source)
    profile = resolution.profile

    assert profile is not MODEL_PROFILES["H6102"]
    assert profile.supports_rgb
    assert profile.whole_device_mask == 0x7FFF
    assert profile.segment_count == 0
    _assert_advanced_surfaces_disabled(profile)
    assert profile.connection_idle_timeout == 3.0
    assert resolution.rgb_variant is H6102RgbVariant.EXTENDED
    assert resolution.firmware_source == firmware_source
    assert resolution.capability_resolution_reason is None


def test_firmware_source_remains_explicit_without_changing_capabilities() -> None:
    configured = resolve_h6102_capabilities("1.03.01", "configured")
    observed = resolve_h6102_capabilities("1.03.01", "ble")

    assert configured.profile is observed.profile
    assert configured.rgb_variant is observed.rgb_variant is H6102RgbVariant.EXTENDED
    assert configured.firmware_source == "configured"
    assert observed.firmware_source == "ble"
