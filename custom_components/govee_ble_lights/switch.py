"""Switch entities for Govee BLE Lights."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import GoveeBLECoordinator
from .light import apply_active_video_mode


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: GoveeBLECoordinator = config_entry.runtime_data
    if coordinator.model == "H6199":
        async_add_entities([H6199ParameterSwitch(coordinator, key="video_sound_effects", name="Video sound effects")])


class H6199ParameterSwitch(CoordinatorEntity[GoveeBLECoordinator], SwitchEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: GoveeBLECoordinator, *, key: str, name: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.address.replace(':', '').lower()}_{key}"
        self._attr_device_info = coordinator.device_info

    @property
    def is_on(self) -> bool:
        return bool(getattr(self.coordinator, self._key))

    async def async_turn_on(self, **kwargs: object) -> None:
        await self._async_set_state(True)

    async def async_turn_off(self, **kwargs: object) -> None:
        await self._async_set_state(False)

    async def _async_set_state(self, value: bool) -> None:
        prev = bool(getattr(self.coordinator, self._key))
        if prev == value:
            return
        setattr(self.coordinator, self._key, value)
        try:
            await apply_active_video_mode(self.coordinator)
        except Exception:
            setattr(self.coordinator, self._key, prev)
            raise
        self.coordinator.async_set_updated_data(getattr(self.coordinator, "data", {}) or {})
