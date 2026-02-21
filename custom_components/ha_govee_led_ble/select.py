"""Select entities for HA Govee LED BLE."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import GoveeBLECoordinator
from .light import apply_active_video_mode

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: GoveeBLECoordinator = config_entry.runtime_data
    if coordinator.model == "H6199":
        async_add_entities([H6199VideoCaptureSelect(coordinator)])


class H6199VideoCaptureSelect(CoordinatorEntity[GoveeBLECoordinator], SelectEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "video_capture_region"
    _attr_options = ["full", "part"]

    def __init__(self, coordinator: GoveeBLECoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address.replace(':', '').lower()}_video_capture_region"
        self._attr_device_info = coordinator.device_info

    @property
    def current_option(self) -> str:
        return "full" if self.coordinator.video_full_screen else "part"

    async def async_select_option(self, option: str) -> None:
        full_screen = option == "full"
        prev = self.coordinator.video_full_screen
        if prev == full_screen:
            return
        self.coordinator.video_full_screen = full_screen
        try:
            await apply_active_video_mode(self.coordinator)
        except Exception:
            self.coordinator.video_full_screen = prev
            raise
        self.coordinator.async_set_updated_data(getattr(self.coordinator, "data", {}) or {})
