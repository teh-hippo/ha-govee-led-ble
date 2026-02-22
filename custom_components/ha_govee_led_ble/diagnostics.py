"""Diagnostics for HA Govee LED BLE."""

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import GoveeBLEConfigEntry

REDACT_KEYS = {"unique_id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: GoveeBLEConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(
            {
                "entry_id": entry.entry_id,
                "unique_id": entry.unique_id,
                "data": dict(entry.data),
                "options": dict(entry.options),
            },
            REDACT_KEYS,
        ),
        "coordinator": {
            "model": coordinator.model,
            "state_readable": coordinator.profile.state_readable,
            "supports_video_mode": coordinator.profile.supports_video_mode,
            "supports_music_mode": coordinator.profile.supports_music_mode,
            "supports_white_brightness": coordinator.profile.supports_white_brightness,
            "supports_advanced_controls": coordinator.profile.supports_advanced_controls,
            "is_on": coordinator.is_on,
            "brightness_pct": coordinator.brightness_pct,
            "rgb_color": coordinator.rgb_color,
            "color_temp_kelvin": coordinator.color_temp_kelvin,
            "effect": coordinator.effect,
            "video_saturation": coordinator.video_saturation,
            "video_sound_effects": coordinator.video_sound_effects,
            "video_sound_effects_softness": coordinator.video_sound_effects_softness,
            "music_sensitivity": coordinator.music_sensitivity,
            "music_calm": coordinator.music_calm,
            "music_color": coordinator.music_color,
            "white_brightness": coordinator.white_brightness,
            "video_full_screen": coordinator.video_full_screen,
            "packet_log": coordinator.packet_log,
        },
    }
