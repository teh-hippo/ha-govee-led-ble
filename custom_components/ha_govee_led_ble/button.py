"""Temporary H6199 readback button for #532."""

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import GoveeBLEConfigEntry
from .const import DOMAIN
from .coordinator import GoveeBLECoordinator
from .entity import GoveeBLEEntity
from .video_test_controls import async_read_video_test_state, video_test_snapshot_current

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: GoveeBLEConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if entry.runtime_data.model == "H6199":
        async_add_entities([GoveeBLEVideoTestReadButton(entry.runtime_data)])


class GoveeBLEVideoTestReadButton(GoveeBLEEntity, ButtonEntity):
    _attr_translation_key = "video_test_read"

    def __init__(self, coordinator: GoveeBLECoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address.replace(':', '').lower()}_video_test_read"
        self._attr_device_info = coordinator.device_info

    @property
    def available(self) -> bool:
        return (
            self.coordinator.model == "H6199" and bool(self.coordinator.profile.dreamview_reads) and super().available
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        snapshot = self.coordinator.video_test_readback
        return {
            **(
                {key: value for key, value in snapshot.items() if not key.startswith("_")}
                if snapshot is not None
                else {}
            ),
            "current_subscription": video_test_snapshot_current(self.coordinator),
        }

    async def async_press(self) -> None:
        try:
            await async_read_video_test_state(self.coordinator)
        except Exception as err:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="device_command_failed") from err
