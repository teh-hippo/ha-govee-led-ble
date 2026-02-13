"""Select entities for Govee BLE Lights."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GoveeBLECoordinator
from .h6199_effects import apply_active_video_mode_from_state


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Govee BLE select entities."""
    coordinator: GoveeBLECoordinator = hass.data[DOMAIN][config_entry.entry_id]
    if coordinator.model != "H6199":
        return

    async_add_entities([H6199VideoCaptureSelect(coordinator)])


class H6199VideoCaptureSelect(CoordinatorEntity[GoveeBLECoordinator], SelectEntity):
    """Select entity for H6199 video capture region."""

    _attr_has_entity_name = True
    _attr_name = "Video capture region"
    _attr_options = ["full", "part"]

    def __init__(self, coordinator: GoveeBLECoordinator) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        addr = coordinator.address.replace(":", "").lower()
        self._attr_unique_id = f"{addr}_video_capture_region"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            name=f"Govee {coordinator.model}",
            manufacturer="Govee",
            model=coordinator.model,
        )

    @property
    def current_option(self) -> str:
        """Return current capture region option."""
        return "full" if self.coordinator.video_full_screen else "part"

    async def async_select_option(self, option: str) -> None:
        """Select video capture region."""
        full_screen = option == "full"
        prev_value = self.coordinator.video_full_screen
        if prev_value == full_screen:
            return

        self.coordinator.video_full_screen = full_screen
        try:
            await self._async_apply_if_active_video_effect()
        except Exception:
            self.coordinator.video_full_screen = prev_value
            raise

        self.coordinator.async_set_updated_data(getattr(self.coordinator, "data", {}) or {})

    async def _async_apply_if_active_video_effect(self) -> None:
        """Apply updated region when a video mode is active."""
        await apply_active_video_mode_from_state(self.coordinator)
