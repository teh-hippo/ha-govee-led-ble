"""Camera register diagnostic, independent of light availability."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
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
    last_unqualified_revision = 0

    def add_qualified() -> None:
        nonlocal added, last_unqualified_revision
        if added:
            return
        if h6199_camera_controls_state(coordinator.model, coordinator) is not CapabilityState.SUPPORTED:
            last_unqualified_revision = coordinator._field_revisions.get("camera_status", 0)
            return
        added = True
        async_add_entities([GoveeBLECameraStatus(coordinator, camera_status_revision=last_unqualified_revision)])

    add_qualified()
    entry.async_on_unload(coordinator.async_add_listener(add_qualified))


class GoveeBLECameraStatus(GoveeBLEEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_translation_key = "camera_status"
    _attr_options = ["absent", "healthy", "incompatible", "unknown"]

    def __init__(self, coordinator: GoveeBLECoordinator, *, camera_status_revision: int = 0) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address.replace(':', '').lower()}_camera_status"
        self._attr_device_info = coordinator.device_info
        self._camera_status_revision = camera_status_revision
        self._reported_camera_status = "unknown"
        self._update_camera_status()

    def _update_camera_status(self) -> None:
        revision = self.coordinator._field_revisions.get("camera_status", 0)
        if h6199_camera_controls_state(self.coordinator.model, self.coordinator) is not CapabilityState.SUPPORTED:
            self._reported_camera_status = "unknown"
        elif revision > self._camera_status_revision:
            # Missing replies clear coordinator state without adding a camera observation.
            self._reported_camera_status = self.coordinator.camera_status
        self._camera_status_revision = revision

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_camera_status()
        super()._handle_coordinator_update()

    @property
    def native_value(self) -> str:
        if h6199_camera_controls_state(self.coordinator.model, self.coordinator) is not CapabilityState.SUPPORTED:
            return "unknown"
        return self._reported_camera_status
