"""HA Govee LED BLE integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_EFFECT_FAMILIES,
    CONF_MODEL,
    DOMAIN,
    EFFECT_FAMILIES,
    MODEL_PROFILES,
    default_effect_families,
    effect_families_from_options,
    resolve_model,
)
from .coordinator import GoveeBLECoordinator
from .editor import async_register_editor_panel, editor_url

type GoveeBLEConfigEntry = ConfigEntry[GoveeBLECoordinator]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS = [
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SWITCH,
]
_LEGACY_ENTITY_SUFFIXES = {
    "_active_mode",
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
    "_sleep_timer",
    "_sleep_timer_duration",
    "_video_brightness",
    "_wakeup_timer",
    "_wakeup_timer_time",
    "_white_brightness",
    "_white_balance_blue",
    "_white_balance_preset",
    "_white_balance_red",
    "_music_calm",
    "_music_mode",
}
# The 2.x experimental options flag, removed in 3.0.0; stripped from migrated entries.
_LEGACY_EXPERIMENTAL_OPTION = "experimental"
_RELATIVE_BRIGHTNESS_SUFFIXES = {
    "_relative_brightness",
    "_relative_brightness_left",
    "_relative_brightness_top",
    "_relative_brightness_right",
    "_relative_brightness_bottom",
}


def _unsupported_model_issue_id(entry: GoveeBLEConfigEntry) -> str:
    return f"unsupported_model_{entry.entry_id}"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    await async_register_editor_panel(hass)
    return True


async def _async_cleanup_legacy_entities(hass: HomeAssistant, entry: GoveeBLEConfigEntry) -> None:
    registry = er.async_get(hass)
    replaced_white_balance: list[str] = []
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.unique_id and any(entity.unique_id.endswith(suffix) for suffix in _LEGACY_ENTITY_SUFFIXES):
            if entity.unique_id.endswith(("_white_balance_blue", "_white_balance_preset", "_white_balance_red")):
                replaced_white_balance.append(entity.entity_id)
            registry.async_remove(entity.entity_id)
    if replaced_white_balance:
        hass.data.setdefault(DOMAIN, {})[f"{entry.entry_id}_white_balance_from"] = replaced_white_balance


def _addr(entry: GoveeBLEConfigEntry) -> str:
    assert entry.unique_id is not None
    return entry.unique_id.replace(":", "").lower()


async def async_migrate_entry(hass: HomeAssistant, entry: GoveeBLEConfigEntry) -> bool:
    options = dict(entry.options)
    if entry.version < 2:
        options = {k: v for k, v in options.items() if k != _LEGACY_EXPERIMENTAL_OPTION}
    if entry.version < 4:
        enabled_relative_brightness = [
            entity.entity_id
            for entity in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
            if entity.unique_id
            and any(entity.unique_id.endswith(suffix) for suffix in _RELATIVE_BRIGHTNESS_SUFFIXES)
            and entity.disabled_by is None
        ]
        if enabled_relative_brightness:
            hass.data.setdefault(DOMAIN, {})[f"{entry.entry_id}_relative_brightness_enabled"] = (
                enabled_relative_brightness
            )
    data = dict(entry.data)
    raw_model = data.get(CONF_MODEL)
    model = resolve_model(raw_model) if isinstance(raw_model, str) else None
    if model is None and isinstance(entry.title, str):
        model = next((candidate for candidate in MODEL_PROFILES if candidate in entry.title.upper()), None)
    if model is not None:
        data[CONF_MODEL] = model
        defaults = default_effect_families(model)
        options.setdefault(CONF_EFFECT_FAMILIES, [family for family in EFFECT_FAMILIES if family in defaults])
    hass.config_entries.async_update_entry(entry, data=data, options=options, version=5)
    return True


def _maybe_flag_music_mode_replaced(hass: HomeAssistant, entry: GoveeBLEConfigEntry) -> None:
    """Warn that select.music_mode is gone: music is now chosen from the light effect list."""
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


def _maybe_flag_white_balance_replaced(hass: HomeAssistant, entry: GoveeBLEConfigEntry) -> None:
    """Warn that three H6199 white-balance controls became one position slider."""
    old_ids = hass.data.get(DOMAIN, {}).pop(f"{entry.entry_id}_white_balance_from", None)
    if old_ids is None:
        return
    new_id = er.async_get(hass).async_get_entity_id("number", DOMAIN, f"{_addr(entry)}_white_balance")
    ir.async_create_issue(
        hass,
        DOMAIN,
        f"white_balance_controls_replaced_{entry.entry_id}",
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="white_balance_controls_replaced",
        translation_placeholders={
            "old": ", ".join(old_ids),
            "new": new_id or "number.white_balance",
        },
    )


def _restore_relative_brightness_enablement(hass: HomeAssistant, entry: GoveeBLEConfigEntry) -> None:
    """Keep existing enabled entities enabled while changing the default for new registries."""
    entity_ids = hass.data.get(DOMAIN, {}).pop(f"{entry.entry_id}_relative_brightness_enabled", None)
    if entity_ids is None:
        return
    registry = er.async_get(hass)
    for entity_id in entity_ids:
        registry.async_update_entity(entity_id, disabled_by=None)


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
    ir.async_delete_issue(hass, DOMAIN, issue_id)
    coordinator = GoveeBLECoordinator(
        hass,
        entry.unique_id,
        model,
        configuration_url=editor_url(entry.entry_id),
        effect_families=effect_families_from_options(model, entry.options),
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    _maybe_flag_music_mode_replaced(hass, entry)
    await _async_cleanup_legacy_entities(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _restore_relative_brightness_enablement(hass, entry)
    _maybe_flag_white_balance_replaced(hass, entry)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: GoveeBLEConfigEntry) -> bool:
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.disconnect()
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: GoveeBLEConfigEntry) -> None:
    ir.async_delete_issue(hass, DOMAIN, _unsupported_model_issue_id(entry))
