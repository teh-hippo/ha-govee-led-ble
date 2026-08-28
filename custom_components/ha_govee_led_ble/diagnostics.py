"""Diagnostics for HA Govee LED BLE."""

from collections.abc import Mapping
from typing import Any, cast

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import GoveeBLEConfigEntry
from .coordinator import PACKET_LOG_LIMIT, PACKET_LOG_RAW_BYTES_LIMIT
from .effect_contracts import diagnostics_release_capabilities
from .effect_diagnostics import empty_effect_diagnostic_snapshot
from .h6199_calibration import WHITE_BALANCE_POSITIONS

REDACT_KEYS = {"address", "unique_id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: GoveeBLEConfigEntry,
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    packet_log = [_bounded_packet_entry(entry) for entry in coordinator.packet_log[-PACKET_LOG_LIMIT:]]
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
        "release_capabilities": diagnostics_release_capabilities(coordinator.model),
        "effect_families": sorted(coordinator.effect_families),
        "effect_categories": sorted(coordinator.effect_categories),
        "prefix_effect_names": coordinator.prefix_effect_names,
        "always_include_custom_effects": coordinator.always_include_custom_effects,
        "state_readable": coordinator.profile.state_readable,
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
        "subordinate_20_version": coordinator.subordinate_20_version,
        "subordinate_21_version": coordinator.subordinate_21_version,
        "lock_locked": lock.locked(),
        "is_on": coordinator.is_on,
        "brightness_pct": coordinator.brightness_pct,
        "rgb_color": coordinator.rgb_color,
        "segment_colors": coordinator.segment_colors,
        "segment_brightness": coordinator.segment_brightness,
        "segment_state_source": coordinator.segment_state_source,
        "segment_state_observed_at": coordinator.segment_state_observed_at,
        "color_temp_kelvin": coordinator.color_temp_kelvin,
        "effect": coordinator.effect,
        "diy_code": coordinator.diy_code,
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
        "blank_screen_policy": {
            "detection": coordinator.blank_screen_detection,
            "low_brightness_duration_seconds": coordinator.blank_screen_low_brightness_duration_seconds,
            "same_tone_duration_seconds": coordinator.blank_screen_same_tone_duration_seconds,
        },
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
        "active_effect_state": _active_effect_state(hass, entry.entry_id),
        "effect_deployment_diagnostics": _effect_deployment_diagnostics(hass, entry.entry_id),
    }


def _bounded_packet_entry(entry: dict[str, Any]) -> dict[str, Any]:
    bounded = dict(entry)
    raw = bounded.get("raw")
    maximum = PACKET_LOG_RAW_BYTES_LIMIT * 2
    if isinstance(raw, str) and len(raw) > maximum:
        bounded["raw"] = raw[:maximum]
        bounded["truncated"] = True
    return bounded


def _effect_deployment_diagnostics(hass: HomeAssistant, config_entry_id: str) -> dict[str, Any]:
    data = getattr(hass, "data", None)
    if not isinstance(data, Mapping):
        return empty_effect_diagnostic_snapshot()
    from .effect_setup import get_effect_backend

    backend = get_effect_backend(hass)
    if backend is None:
        return empty_effect_diagnostic_snapshot()
    return backend.diagnostics.snapshot(config_entry_id=config_entry_id)


def _active_effect_state(hass: HomeAssistant, config_entry_id: str) -> dict[str, Any] | None:
    from .effect_setup import get_effect_backend

    backend = get_effect_backend(hass)
    cache = getattr(backend, "device_cache", None)
    if cache is None or (state := cache.get(config_entry_id)) is None:
        return None
    return cast(dict[str, Any], state.to_public_dict())
