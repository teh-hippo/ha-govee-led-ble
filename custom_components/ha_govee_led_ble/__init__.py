"""HA Govee LED BLE integration."""

import asyncio
import logging
from typing import Any

from homeassistant.components import bluetooth, frontend
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS,
    CONF_EFFECT_CATEGORIES,
    CONF_EFFECT_FAMILIES,
    CONF_MODEL,
    CONF_PREFIX_EFFECT_NAMES,
    DOMAIN,
    MODEL_PROFILES,
    always_include_custom_effects_from_options,
    default_effect_categories,
    effect_categories_from_options,
    effect_families_from_options,
    model_from_ble_name,
    prefix_effect_names_from_options,
    resolve_model,
    supported_effect_categories,
)
from .coordinator import GoveeBLECoordinator, clear_availability_log_state
from .editor import EDITOR_PANEL_PATH, async_register_editor_panel, editor_url
from .effect_setup import async_setup_effects, get_effect_backend
from .light_services import async_register_light_services

type GoveeBLEConfigEntry = ConfigEntry[GoveeBLECoordinator]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS = [Platform.LIGHT]
_LEGACY_ENTITY_SUFFIXES = {
    "_active_mode",
    "_blank_screen",
    "_effect_preview",
    "_music_daynight_segments",
    "_music_daynight_speed",
    "_music_fountain_direction",
    "_music_hopping_brightness",
    "_music_piano_key_count",
    "_music_sensitivity",
    "_music_separation_gradient",
    "_music_separation_point",
    "_music_style",
    "_poweroff_memory",
    "_reduce_motion",
    "_relative_brightness",
    "_relative_brightness_bottom",
    "_relative_brightness_left",
    "_relative_brightness_right",
    "_relative_brightness_top",
    "_scene_speed",
    "_sleep_timer",
    "_sleep_timer_duration",
    "_video_brightness",
    "_video_capture_region",
    "_video_saturation",
    "_video_sound_effects",
    "_video_sound_effects_softness",
    "_wakeup_timer",
    "_wakeup_timer_time",
    "_white_brightness",
    "_white_balance_blue",
    "_white_balance",
    "_white_balance_preset",
    "_white_balance_red",
    "_music_calm",
    "_music_mode",
}
# Config entry versions below 2 can contain this unsupported option.
_LEGACY_EXPERIMENTAL_OPTION = "experimental"
_LOGGER = logging.getLogger(__name__)


def _unsupported_model_issue_id(entry: GoveeBLEConfigEntry) -> str:
    return f"unsupported_model_{entry.entry_id}"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async_register_light_services(hass)
    await async_setup_effects(hass)
    await _async_update_editor_panel(hass)
    return True


def _effect_studio_sidebar_visible(
    hass: HomeAssistant,
    *,
    excluding_entry_id: str | None = None,
) -> bool:
    return any(
        entry.entry_id != excluding_entry_id
        and entry.disabled_by is None
        and isinstance(model := entry.data.get(CONF_MODEL), str)
        and bool(supported_effect_categories(model))
        for entry in hass.config_entries.async_entries(DOMAIN)
    )


async def _async_update_editor_panel(
    hass: HomeAssistant,
    *,
    excluding_entry_id: str | None = None,
) -> None:
    if hass.is_stopping:
        return
    if not _effect_studio_sidebar_visible(hass, excluding_entry_id=excluding_entry_id):
        frontend.async_remove_panel(hass, EDITOR_PANEL_PATH, warn_if_unknown=False)
        return
    await async_register_editor_panel(
        hass,
        advanced_available=get_effect_backend(hass) is not None,
    )


async def _async_cleanup_legacy_entities(hass: HomeAssistant, entry: GoveeBLEConfigEntry) -> None:
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.unique_id and any(entity.unique_id.endswith(suffix) for suffix in _LEGACY_ENTITY_SUFFIXES):
            registry.async_remove(entity.entity_id)


def _addr(entry: GoveeBLEConfigEntry) -> str:
    assert entry.unique_id is not None
    return entry.unique_id.replace(":", "").lower()


async def async_migrate_entry(hass: HomeAssistant, entry: GoveeBLEConfigEntry) -> bool:
    options = dict(entry.options)
    if entry.version < 2:
        options = {k: v for k, v in options.items() if k != _LEGACY_EXPERIMENTAL_OPTION}
    data = dict(entry.data)
    raw_model = data.get(CONF_MODEL)
    model = resolve_model(raw_model) if isinstance(raw_model, str) else None
    if model is None and isinstance(entry.title, str):
        model = next((candidate for candidate in MODEL_PROFILES if candidate in entry.title.upper()), None)
    if model is not None:
        data[CONF_MODEL] = model
        options.pop(CONF_EFFECT_FAMILIES, None)
        options.setdefault(CONF_EFFECT_CATEGORIES, list(default_effect_categories(model)))
        options.setdefault(CONF_PREFIX_EFFECT_NAMES, False)
        options.setdefault(CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS, False)
    hass.config_entries.async_update_entry(entry, data=data, options=options, version=8)
    return True


def _maybe_flag_music_mode_replaced(hass: HomeAssistant, entry: GoveeBLEConfigEntry) -> None:
    """Warn when a legacy music-mode select remains in the entity registry."""
    old_id = er.async_get(hass).async_get_entity_id("select", DOMAIN, f"{_addr(entry)}_music_mode")
    if old_id is None:
        return
    ir.async_create_issue(
        hass,
        DOMAIN,
        "music_mode_replaced",
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="music_mode_replaced",
        translation_placeholders={"old": old_id},
    )


async def async_setup_entry(hass: HomeAssistant, entry: GoveeBLEConfigEntry) -> bool:
    assert entry.unique_id is not None
    raw_model = entry.data.get(CONF_MODEL)
    model = resolve_model(raw_model) if isinstance(raw_model, str) else None
    issue_id = _unsupported_model_issue_id(entry)
    if model is None:
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key="unsupported_model",
            translation_placeholders={"model": str(raw_model or "missing")},
        )
        return False
    service_info = bluetooth.async_last_service_info(hass, entry.unique_id, connectable=True)
    advertised_model = model_from_ble_name(service_info.name) if service_info is not None else None
    if advertised_model is not None and advertised_model != model:
        _LOGGER.error(
            "Configured model %s does not match advertised model %s for config entry %s; reconfigure the entry",
            model,
            advertised_model,
            entry.entry_id,
        )
        return False
    ir.async_delete_issue(hass, DOMAIN, issue_id)
    coordinator = GoveeBLECoordinator(
        hass,
        entry.unique_id,
        model,
        configuration_url=editor_url(entry.entry_id) if supported_effect_categories(model) else None,
        effect_families=effect_families_from_options(model, entry.options),
        effect_categories=effect_categories_from_options(model, entry.options),
        prefix_effect_names=prefix_effect_names_from_options(entry.options),
        always_include_custom_effects=always_include_custom_effects_from_options(entry.options),
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    if effect_backend := get_effect_backend(hass):
        await effect_backend.preview.async_load_device(entry.entry_id)
        effect_backend.engine.reconcile_current(
            coordinator,
            config_entry_id=entry.entry_id,
            observed_at=dt_util.utcnow().isoformat(),
            refreshed=True,
        )

        cancel_sync: CALLBACK_TYPE | None = None

        @callback
        def sync_effect_observation() -> None:
            nonlocal cancel_sync
            cancel_sync = None
            effect_backend.engine.reconcile_current(
                coordinator,
                config_entry_id=entry.entry_id,
                observed_at=dt_util.utcnow().isoformat(),
                refreshed=False,
            )

        @callback
        def delayed_effect_observation(_now: Any) -> None:
            sync_effect_observation()

        @callback
        def schedule_effect_observation() -> None:
            nonlocal cancel_sync
            if cancel_sync is None:
                cancel_sync = async_call_later(
                    hass,
                    0.1,
                    delayed_effect_observation,
                )

        unsubscribe_observation = coordinator.async_add_listener(
            schedule_effect_observation,
        )

        @callback
        def unsubscribe_effect_observation() -> None:
            nonlocal cancel_sync
            unsubscribe_observation()
            if cancel_sync is not None:
                cancel_sync()
                cancel_sync = None

        entry.async_on_unload(unsubscribe_effect_observation)
    _maybe_flag_music_mode_replaced(hass, entry)
    await _async_cleanup_legacy_entities(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await _async_update_editor_panel(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: GoveeBLEConfigEntry) -> bool:
    effect_backend = get_effect_backend(hass)
    if effect_backend is not None:
        await effect_backend.preview.async_unload_device(entry.entry_id)
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.disconnect()
        await _async_update_editor_panel(hass)
    elif effect_backend is not None:
        await effect_backend.preview.async_load_device(entry.entry_id)
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: GoveeBLEConfigEntry) -> None:
    effect_backend = get_effect_backend(hass)
    if effect_backend is not None:
        await asyncio.gather(
            effect_backend.scene_defaults.async_delete_device(entry.entry_id),
            effect_backend.template_defaults.async_delete_device(entry.entry_id),
            effect_backend.active_workspaces.async_delete_device(entry.entry_id),
            effect_backend.device_cache.async_delete_device(entry.entry_id),
            effect_backend.deployments.async_delete_device(entry.entry_id),
            effect_backend.user_state.async_clear_config_entry(entry.entry_id),
        )
    ir.async_delete_issue(hass, DOMAIN, _unsupported_model_issue_id(entry))
    if entry.unique_id is not None:
        clear_availability_log_state(hass, entry.unique_id)
    await _async_update_editor_panel(hass, excluding_entry_id=entry.entry_id)
