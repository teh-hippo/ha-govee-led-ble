"""Shared base entity for the Govee BLE integration."""

import logging
from collections.abc import Awaitable, Callable, Hashable

from bleak.exc import BleakError
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .ble_connection import gatt_protocol_error_code
from .coordinator import GoveeBLECoordinator

_LOGGER = logging.getLogger(__name__)


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

    async def _async_latest(self, operation: Callable[[], Awaitable[None]], *key: Hashable) -> None:
        """Send this request unless a newer request for the same control replaces it while queued."""
        try:
            await self.coordinator.latest_requests.run((self.unique_id, *key), operation)
        except (BleakError, ValueError, TimeoutError, HomeAssistantError) as error:
            cause = error.__cause__ if isinstance(error, HomeAssistantError) else error
            if isinstance(cause, BleakError | ValueError | TimeoutError):
                protocol_code = gatt_protocol_error_code(cause)
                _LOGGER.warning(
                    "Device command failed operation=%s model=%s failure=%s%s",
                    type(self).__name__,
                    self.coordinator.model,
                    type(cause).__name__,
                    f" code={protocol_code}" if protocol_code is not None else "",
                )
            raise
