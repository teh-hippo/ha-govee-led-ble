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
    coordinator = entry.runtime_data
    packet_log = coordinator.packet_log
    last_rx_aa05_raw = next(
        (
            raw
            for e in reversed(packet_log)
            if e.get("dir") == "rx" and isinstance((raw := e.get("raw")), str) and raw.startswith("aa05")
        ),
        None,
    )
    client = coordinator._client
    lock = coordinator._lock
    expected_brightness = coordinator._expected_state.get("brightness_pct")
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
            "address": coordinator.address,
            "model": coordinator.model,
            "state_readable": coordinator.profile.state_readable,
            "supports_video_mode": coordinator.profile.supports_video_mode,
            "supports_video_sound_effects": coordinator.profile.supports_video_sound_effects,
            "supports_music_mode": coordinator.profile.supports_music_mode,
            "music_modes": list(coordinator.profile.music_modes),
            "supports_white_brightness": coordinator.profile.supports_white_brightness,
            "supports_diy": coordinator.profile.supports_diy,
            "custom_effect_kinds": sorted(coordinator.profile.custom_effect_kinds),
            "supports_segments": coordinator.profile.supports_segments,
            "supports_timers": coordinator.profile.supports_timers,
            "supports_poweroff_memory": coordinator.profile.supports_poweroff_memory,
            "segment_count": coordinator.profile.segment_count,
            "connected": bool(client and client.is_connected),
            "available": coordinator.available,
            "fw_version": coordinator.fw_version,
            "hw_version": coordinator.hw_version,
            "lock_locked": lock.locked(),
            "is_on": coordinator.is_on,
            "brightness_pct": coordinator.brightness_pct,
            "rgb_color": coordinator.rgb_color,
            "segment_colors": coordinator.segment_colors,
            "color_temp_kelvin": coordinator.color_temp_kelvin,
            "effect": coordinator.effect,
            "active_custom_id": coordinator.active_custom_id,
            "custom_effect_count": len(coordinator.custom_effects),
            "video_saturation": coordinator.video_saturation,
            "video_white_balance": coordinator.video_white_balance,
            "video_sound_effects": coordinator.video_sound_effects,
            "video_sound_effects_softness": coordinator.video_sound_effects_softness,
            "music_sensitivity": coordinator.music_sensitivity,
            "music_calm": coordinator.music_calm,
            "music_color": coordinator.music_color,
            "white_brightness": coordinator.white_brightness,
            "video_full_screen": coordinator.video_full_screen,
            "expected_brightness_pct": expected_brightness[0] if expected_brightness is not None else None,
            "packet_log": packet_log,
            "last_rx_aa05_raw": last_rx_aa05_raw,
        },
    }
