"""Shared base entity for the Govee BLE integration."""

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import GoveeBLECoordinator


class GoveeBLEEntity(CoordinatorEntity[GoveeBLECoordinator]):
    """Base entity whose availability follows BLE presence and the coordinator refresh.

    ``available`` combines the coordinator's presence signal (a live BLE link or a recent
    advertisement) with the standard DataUpdateCoordinator success flag, so entities go
    unavailable when the device drops off the air.
    """

    _attr_has_entity_name = True

    @property
    def available(self) -> bool:
        return self.coordinator.available and super().available
