"""Number entities for HA Govee LED BLE."""

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import h6199_controls as c
from .coordinator import GoveeBLECoordinator
from .entity import GoveeBLEEntity

PARALLEL_UPDATES = 0


class SleepTimerNumber(GoveeBLEEntity, NumberEntity):
    _attr_translation_key = "sleep_timer_duration"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = 255
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(self, coordinator: GoveeBLECoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address.replace(':', '').lower()}_sleep_timer_duration"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> float | None:
        value = self.coordinator.sleep_timer_minutes
        return float(value) if value is not None else None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_sleep_timer(minutes=int(value))


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    await c.async_setup_number_entry(hass, config_entry, async_add_entities)
    coordinator = config_entry.runtime_data
    if coordinator.profile.supports_timers:
        async_add_entities([SleepTimerNumber(coordinator)])
