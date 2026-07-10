"""Time entities for HA Govee LED BLE."""

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import GoveeBLECoordinator
from .entity import GoveeBLEEntity

PARALLEL_UPDATES = 0


class WakeupTimerTime(GoveeBLEEntity, TimeEntity):
    _attr_translation_key = "wakeup_time"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: GoveeBLECoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address.replace(':', '').lower()}_wakeup_timer_time"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> time | None:
        return self.coordinator.wakeup_timer_time

    async def async_set_value(self, value: time) -> None:
        await self.coordinator.async_set_wakeup_timer(wake_time=value)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = config_entry.runtime_data
    if coordinator.profile.supports_timers:
        async_add_entities([WakeupTimerTime(coordinator)])
