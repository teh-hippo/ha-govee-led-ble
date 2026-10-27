"""Profile-qualified native configuration levels."""

from bleak.exc import BleakError
from homeassistant.components.number import NumberEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import GoveeBLEConfigEntry
from .const import DOMAIN
from .entity import GoveeBLEEntity
from .low_blue_light import Setting

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: GoveeBLEConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    added = False

    def add_qualified() -> None:
        nonlocal added
        if not added and entry.runtime_data.profile.supports_low_blue_light:
            added = True
            async_add_entities([GoveeBLELowBlueLightLevel(entry)])

    add_qualified()
    entry.async_on_unload(entry.runtime_data.async_add_listener(add_qualified))


class GoveeBLELowBlueLightLevel(GoveeBLEEntity, NumberEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "low_blue_light_level"
    _attr_native_min_value = Setting.State().minimum_level
    _attr_native_max_value = Setting.State().maximum_level
    _attr_native_step = 1

    def __init__(self, entry: GoveeBLEConfigEntry) -> None:
        super().__init__(entry.runtime_data)
        self._attr_unique_id = f"{self.coordinator.address.replace(':', '').lower()}_low_blue_light_level"
        self._attr_device_info = self.coordinator.device_info

    @property
    def available(self) -> bool:
        return self.coordinator.profile.supports_low_blue_light and super().available

    @property
    def native_value(self) -> float | None:
        state = self.coordinator.low_blue_light
        return state.level if state is not None else None

    async def async_set_native_value(self, value: float) -> None:
        if not self.native_min_value <= value <= self.native_max_value or int(value) != value:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="invalid_control_request")
        try:
            await self.coordinator.async_set_low_blue_light(level=int(value))
        except (BleakError, ValueError, TimeoutError) as error:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="device_command_failed") from error
