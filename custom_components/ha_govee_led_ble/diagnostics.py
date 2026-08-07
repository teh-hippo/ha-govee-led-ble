"""Diagnostics for HA Govee LED BLE."""

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import GoveeBLEConfigEntry
from .protocol import WHITE_BALANCE_POSITIONS

REDACT_KEYS = {"address", "unique_id"}


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
    white_balance = (
        (coordinator.white_balance_red, coordinator.white_balance_blue)
        if coordinator.white_balance_red is not None and coordinator.white_balance_blue is not None
        else None
    )
    coordinator_data = {
        "address": coordinator.address,
        "model": coordinator.model,
        "effect_families": sorted(coordinator.effect_families),
        "state_readable": coordinator.profile.state_readable,
        "supports_scene_speed": coordinator.profile.supports_scene_speed,
        "supports_video_mode": coordinator.profile.supports_video_mode,
        "supports_video_sound_effects": coordinator.profile.supports_video_sound_effects,
        "supports_white_balance": coordinator.profile.supports_white_balance,
        "supports_relative_brightness": coordinator.profile.supports_relative_brightness,
        "supports_blank_screen": coordinator.profile.supports_blank_screen,
        "supports_music_mode": coordinator.profile.supports_music_mode,
        "music_modes": list(coordinator.profile.music_modes),
        "supports_music_color": coordinator.profile.supports_music_color,
        "supports_white_brightness": coordinator.profile.supports_white_brightness,
        "supports_segments": coordinator.profile.supports_segments,
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
        "scene_speed_scene_code": coordinator.scene_speed_scene_code,
        "scene_speed_position": (
            coordinator.scene_speed_index + 1 if coordinator.scene_speed_index is not None else None
        ),
        "diy_slot": coordinator.diy_slot,
        "color_mode": coordinator.color_mode.name.lower() if coordinator.color_mode is not None else None,
        "video_saturation": coordinator.video_saturation,
        "video_sound_effects": coordinator.video_sound_effects,
        "video_sound_effects_softness": coordinator.video_sound_effects_softness,
        "music_sensitivity": coordinator.music_sensitivity,
        "music_calm": coordinator.music_calm,
        "music_color": coordinator.music_color,
        "white_brightness": coordinator.white_brightness,
        "video_full_screen": coordinator.video_full_screen,
        "white_balance": white_balance,
        "white_balance_position": (
            WHITE_BALANCE_POSITIONS.index(white_balance) + 1
            if white_balance is not None and white_balance in WHITE_BALANCE_POSITIONS
            else None
        ),
        "relative_brightness": coordinator.relative_brightness,
        "relative_brightness_edges": {
            edge: getattr(coordinator, f"relative_brightness_{edge}") for edge in ("left", "top", "right", "bottom")
        },
        "blank_screen": coordinator.blank_screen,
        "expected_brightness_pct": expected_brightness[0] if expected_brightness is not None else None,
        "packet_log": packet_log,
        "last_rx_aa05_raw": last_rx_aa05_raw,
    }
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
        "coordinator": async_redact_data(coordinator_data, REDACT_KEYS),
    }
