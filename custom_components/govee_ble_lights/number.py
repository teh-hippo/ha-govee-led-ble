"""Number entities for Govee BLE Lights."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import GoveeBLECoordinator
from .h6199_effects import (
    apply_active_music_mode_from_state,
    apply_active_video_mode_from_state,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Govee BLE number entities."""
    coordinator: GoveeBLECoordinator = config_entry.runtime_data
    if coordinator.model != "H6199":
        return

    entity_registry = er.async_get(hass)
    for entry in er.async_entries_for_config_entry(entity_registry, config_entry.entry_id):
        if entry.domain != "number":
            continue
        if entry.unique_id.endswith("_video_brightness") or entry.unique_id.endswith("_white_brightness"):
            entity_registry.async_remove(entry.entity_id)

    async_add_entities(
        [
            H6199ParameterNumber(
                coordinator,
                key="video_saturation",
                name="Video saturation",
                minimum=0,
                maximum=100,
            ),
            H6199ParameterNumber(
                coordinator,
                key="video_sound_effects_softness",
                name="Video sound effects softness",
                minimum=0,
                maximum=100,
            ),
            H6199ParameterNumber(
                coordinator,
                key="music_sensitivity",
                name="Music sensitivity",
                minimum=0,
                maximum=100,
            ),
        ]
    )


class H6199ParameterNumber(CoordinatorEntity[GoveeBLECoordinator], NumberEntity):
    """Number entity for H6199 per-effect parameters."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.SLIDER
    _attr_native_step = 1

    def __init__(
        self,
        coordinator: GoveeBLECoordinator,
        *,
        key: str,
        name: str,
        minimum: int,
        maximum: int,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_native_min_value = minimum
        self._attr_native_max_value = maximum
        addr = coordinator.address.replace(":", "").lower()
        self._attr_unique_id = f"{addr}_{key}"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> float:
        """Return the current parameter value."""
        return float(getattr(self.coordinator, self._key))

    async def async_set_native_value(self, value: float) -> None:
        """Set a parameter and apply it to the active compatible effect."""
        prev_value = int(getattr(self.coordinator, self._key))
        next_value = int(round(value))
        if next_value == prev_value:
            return

        setattr(self.coordinator, self._key, next_value)
        try:
            await self._async_apply_if_active_effect()
        except Exception:
            setattr(self.coordinator, self._key, prev_value)
            raise

        self.coordinator.async_set_updated_data(getattr(self.coordinator, "data", {}) or {})

    async def _async_apply_if_active_effect(self) -> None:
        """Apply updated number values when the corresponding mode is active."""
        if self._key in {"video_saturation", "video_sound_effects_softness"}:
            await apply_active_video_mode_from_state(self.coordinator)
            return

        if self._key == "music_sensitivity":
            await apply_active_music_mode_from_state(self.coordinator)
