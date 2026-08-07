"""Number entities for HA Govee LED BLE."""

from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import h6199_controls as c
from .coordinator import GoveeBLECoordinator
from .entity import GoveeBLEEntity

PARALLEL_UPDATES = 0

_SCENE_CODE_ATTRIBUTE = "scene_code"


class SceneSpeedNumber(GoveeBLEEntity, RestoreEntity, NumberEntity):
    """The positional Speed slider for the active catalogue-backed H617A scene."""

    _attr_translation_key = "scene_speed"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = 1
    _attr_native_step = 1

    def __init__(self, coordinator: GoveeBLECoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address.replace(':', '').lower()}_scene_speed"
        self._attr_device_info = coordinator.device_info

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.scene_speed_context is not None

    @property
    def native_max_value(self) -> float:
        context = self.coordinator.scene_speed_context
        if context is None or context[1].speed is None:
            return 1
        return float(context[1].speed.option_count)

    @property
    def native_value(self) -> float | None:
        context = self.coordinator.scene_speed_context
        if context is None or self.coordinator.scene_speed_index is None:
            return None
        if self.coordinator.scene_speed_scene_code != context[1].code:
            return None
        return float(self.coordinator.scene_speed_index + 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        code = self.coordinator.scene_speed_scene_code
        return {_SCENE_CODE_ATTRIBUTE: code} if code is not None else {}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        await self._async_restore_state()

    async def _async_restore_state(self) -> None:
        context = self.coordinator.scene_speed_context
        if context is None or context[1].speed is None:
            return
        last_state = await self.async_get_last_state()
        if last_state is None or last_state.attributes.get(_SCENE_CODE_ATTRIBUTE) != context[1].code:
            return
        try:
            index = int(round(float(last_state.state))) - 1
        except TypeError, ValueError:
            return
        if not 0 <= index < context[1].speed.option_count:
            return
        self.coordinator._sync_scene_speed(context[0], speed_index=index)
        self.coordinator.async_set_updated_data(self.coordinator.data or {})

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_scene_speed(int(round(value)) - 1)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    await c.async_setup_number_entry(hass, config_entry, async_add_entities)
    coordinator = config_entry.runtime_data
    if coordinator.profile.supports_scene_speed:
        async_add_entities([SceneSpeedNumber(coordinator)])
