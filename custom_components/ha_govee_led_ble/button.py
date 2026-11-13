"""Profile-qualified installation maintenance controls."""

from bleak.exc import BleakError
from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import GoveeBLEConfigEntry
from .const import DOMAIN
from .entity import GoveeBLEEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: GoveeBLEConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    added = False

    def add_qualified() -> None:
        nonlocal added
        if not added and coordinator.profile.supports_ic_refresh:
            added = True
            async_add_entities([GoveeBLERefreshInstallationButton(entry)])

    add_qualified()
    entry.async_on_unload(coordinator.async_add_listener(add_qualified))


class GoveeBLERefreshInstallationButton(GoveeBLEEntity, ButtonEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "refresh_installation"

    def __init__(self, entry: GoveeBLEConfigEntry) -> None:
        super().__init__(entry.runtime_data)
        self._attr_unique_id = f"{self.coordinator.address.replace(':', '').lower()}_refresh_installation"
        self._attr_device_info = self.coordinator.device_info

    @property
    def available(self) -> bool:
        return self.coordinator.profile.supports_ic_refresh and super().available

    async def async_press(self) -> None:
        try:
            await self._async_latest(self.coordinator.async_refresh_ic)
        except (BleakError, ValueError, TimeoutError) as error:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="device_command_failed") from error
