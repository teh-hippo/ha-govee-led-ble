"""Profile-qualified boolean device settings with fresh readback."""

from typing import Any

from bleak.exc import BleakError
from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import GoveeBLEConfigEntry
from .const import DOMAIN
from .entity import GoveeBLEEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GoveeBLEConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    added: set[str] = set()

    def add_qualified() -> None:
        controls = entry.runtime_data.profile.boolean_controls - added
        if controls:
            added.update(controls)
            async_add_entities([GoveeBLEControlSwitch(entry, control) for control in sorted(controls)])

    add_qualified()
    entry.async_on_unload(entry.runtime_data.async_add_listener(add_qualified))


class GoveeBLEControlSwitch(GoveeBLEEntity, SwitchEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: GoveeBLEConfigEntry, control: str) -> None:
        super().__init__(entry.runtime_data)
        self._control = control
        self._attr_translation_key = control
        self._attr_unique_id = f"{self.coordinator.address.replace(':', '').lower()}_{control}"
        self._attr_device_info = self.coordinator.device_info

    @property
    def available(self) -> bool:
        return self._control in self.coordinator.profile.boolean_controls and super().available

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.boolean_control_state.get(self._control)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)

    async def _set(self, enabled: bool) -> None:
        try:
            await self.coordinator.async_set_boolean_control(self._control, enabled)
        except (BleakError, ValueError, TimeoutError) as error:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="device_command_failed") from error
