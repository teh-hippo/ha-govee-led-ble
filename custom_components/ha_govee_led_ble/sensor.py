"""Camera register diagnostic, independent of light availability."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import GoveeBLEConfigEntry
from .coordinator import GoveeBLECoordinator
from .effect_contracts import CapabilityState
from .entity import GoveeBLEEntity
from .video_applicability import h6199_camera_controls_state

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: GoveeBLEConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    if coordinator.model != "H6199":
        return
    added = False

    def add_qualified() -> None:
        nonlocal added
        if not added and h6199_camera_controls_state(coordinator.model, coordinator) is CapabilityState.SUPPORTED:
            added = True
            async_add_entities([GoveeBLECameraStatus(coordinator)])

    add_qualified()
    entry.async_on_unload(coordinator.async_add_listener(add_qualified))


class GoveeBLECameraStatus(GoveeBLEEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_translation_key = "camera_status"
    _attr_options = ["absent", "healthy", "incompatible", "unknown"]

    def __init__(self, coordinator: GoveeBLECoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address.replace(':', '').lower()}_camera_status"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> str:
        if h6199_camera_controls_state(self.coordinator.model, self.coordinator) is not CapabilityState.SUPPORTED:
            return "unknown"
        return self.coordinator.camera_status
