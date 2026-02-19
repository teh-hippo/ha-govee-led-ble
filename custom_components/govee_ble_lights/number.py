"""Number entities for Govee BLE Lights."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import GoveeBLECoordinator
from .light import apply_active_music_mode, apply_active_video_mode

_PARAMS = ["video_saturation", "video_sound_effects_softness", "music_sensitivity"]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: GoveeBLECoordinator = config_entry.runtime_data
    if coordinator.model == "H6199":
        async_add_entities([H6199ParameterNumber(coordinator, key=key) for key in _PARAMS])


class H6199ParameterNumber(CoordinatorEntity[GoveeBLECoordinator], NumberEntity):
    _attr_has_entity_name = True
    _attr_mode = NumberMode.SLIDER
    _attr_native_step = 1
    _attr_native_min_value = 0
    _attr_native_max_value = 100

    def __init__(self, coordinator: GoveeBLECoordinator, *, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_translation_key = key
        self._attr_unique_id = f"{coordinator.address.replace(':', '').lower()}_{key}"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> float:
        return float(getattr(self.coordinator, self._key))

    async def async_set_native_value(self, value: float) -> None:
        prev, nxt = int(getattr(self.coordinator, self._key)), int(round(value))
        if nxt == prev:
            return
        setattr(self.coordinator, self._key, nxt)
        try:
            if self._key in {"video_saturation", "video_sound_effects_softness"}:
                await apply_active_video_mode(self.coordinator)
            elif self._key == "music_sensitivity":
                await apply_active_music_mode(self.coordinator)
        except Exception:
            setattr(self.coordinator, self._key, prev)
            raise
        self.coordinator.async_set_updated_data(getattr(self.coordinator, "data", {}) or {})
