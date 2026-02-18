"""Switch entities for Govee BLE Lights."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import GoveeBLECoordinator
from .h6199_effects import apply_active_video_mode_from_state


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Govee BLE switch entities."""
    coordinator: GoveeBLECoordinator = config_entry.runtime_data
    if coordinator.model != "H6199":
        return
    async_add_entities([H6199ParameterSwitch(coordinator, key="video_sound_effects", name="Video sound effects")])


class H6199ParameterSwitch(CoordinatorEntity[GoveeBLECoordinator], SwitchEntity):
    """Switch entity for H6199 video parameters."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: GoveeBLECoordinator,
        *,
        key: str,
        name: str,
    ) -> None:
        """Initialize the switch entity."""
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        addr = coordinator.address.replace(":", "").lower()
        self._attr_unique_id = f"{addr}_{key}"
        self._attr_device_info = coordinator.device_info

    @property
    def is_on(self) -> bool:
        """Return current switch state."""
        return bool(getattr(self.coordinator, self._key))

    async def async_turn_on(self, **kwargs) -> None:
        """Turn on the switch."""
        await self._async_set_state(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off the switch."""
        await self._async_set_state(False)

    async def _async_set_state(self, value: bool) -> None:
        """Set switch state and apply when a video effect is active."""
        prev_value = bool(getattr(self.coordinator, self._key))
        if prev_value == value:
            return

        setattr(self.coordinator, self._key, value)
        try:
            await self._async_apply_if_active_video_effect()
        except Exception:
            setattr(self.coordinator, self._key, prev_value)
            raise

        self.coordinator.async_set_updated_data(getattr(self.coordinator, "data", {}) or {})

    async def _async_apply_if_active_video_effect(self) -> None:
        """Apply updated switch values when a video mode is active."""
        await apply_active_video_mode_from_state(self.coordinator)
