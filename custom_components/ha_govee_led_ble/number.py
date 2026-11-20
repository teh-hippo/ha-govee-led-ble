"""Profile-qualified native configuration levels."""

from collections.abc import Awaitable, Callable
from functools import partial

from bleak.exc import BleakError
from homeassistant.components.number import NumberEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import GoveeBLEConfigEntry
from .const import DOMAIN
from .entity import GoveeBLEEntity
from .low_blue_light import Setting
from .projector import ProjectorControl
from .projector_runtime import control_value, set_control

_PROJECTOR_LEVELS = (
    ProjectorControl.AURORA_MOVEMENT,
    ProjectorControl.AURORA_EFFECT_SPEED,
    ProjectorControl.STAR_FLICKER_SPEED,
    ProjectorControl.STAR_MOVEMENT_SPEED,
)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: GoveeBLEConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    added: set[str] = set()

    def add_qualified() -> None:
        if "local_volume" not in added and entry.runtime_data.profile.local_volume_range is not None:
            added.add("local_volume")
            async_add_entities([GoveeBLELocalVolume(entry)])
        if entry.runtime_data.profile.projector_grammar is not None:
            for control in _PROJECTOR_LEVELS:
                if control not in added:
                    added.add(control)
                    async_add_entities([GoveeBLEProjectorLevel(entry, control)])
        if "low_blue_light" not in added and entry.runtime_data.profile.supports_low_blue_light:
            added.add("low_blue_light")
            async_add_entities([GoveeBLELowBlueLightLevel(entry)])
        if "ripple_speed" not in added and entry.runtime_data.profile.supports_ripple_speed:
            added.add("ripple_speed")
            async_add_entities([GoveeBLERippleSpeed(entry)])

    add_qualified()
    entry.async_on_unload(entry.runtime_data.async_add_listener(add_qualified))


class _GoveeBLELevel(GoveeBLEEntity, NumberEntity):
    _attr_native_step = 1

    def __init__(self, entry: GoveeBLEConfigEntry) -> None:
        super().__init__(entry.runtime_data)
        self._attr_unique_id = f"{self.coordinator.address.replace(':', '').lower()}_{self.translation_key}"
        self._attr_device_info = self.coordinator.device_info

    async def _async_set_level(self, value: float, write: Callable[[int], Awaitable[None]]) -> None:
        if not self.native_min_value <= value <= self.native_max_value or int(value) != value:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="invalid_control_request")
        try:
            await self._async_latest(partial(write, int(value)))
        except (BleakError, ValueError, TimeoutError) as error:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="device_command_failed") from error


class GoveeBLELowBlueLightLevel(_GoveeBLELevel):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "low_blue_light_level"
    _attr_native_min_value = Setting.State().minimum_level
    _attr_native_max_value = Setting.State().maximum_level

    @property
    def available(self) -> bool:
        return self.coordinator.profile.supports_low_blue_light and super().available

    @property
    def native_value(self) -> float | None:
        state = self.coordinator.low_blue_light
        return state.level if state is not None else None

    async def async_set_native_value(self, value: float) -> None:
        await self._async_set_level(value, lambda level: self.coordinator.async_set_low_blue_light(level=level))


class GoveeBLERippleSpeed(_GoveeBLELevel):
    _attr_translation_key = "ripple_speed"
    _attr_native_min_value = 0
    _attr_native_max_value = 100

    @property
    def available(self) -> bool:
        return self.coordinator.profile.supports_ripple_speed and super().available

    @property
    def native_value(self) -> float | None:
        return self.coordinator.ripple_speed

    async def async_set_native_value(self, value: float) -> None:
        await self._async_set_level(value, partial(self.coordinator.async_set_source_value, "top", "ripple_speed"))


class GoveeBLEProjectorLevel(_GoveeBLELevel):
    _attr_native_min_value = 0
    _attr_native_max_value = 100

    def __init__(self, entry: GoveeBLEConfigEntry, control: ProjectorControl) -> None:
        self._attr_translation_key = control
        self._control = control
        super().__init__(entry)

    @property
    def available(self) -> bool:
        return self.coordinator.profile.projector_grammar is not None and super().available

    @property
    def native_value(self) -> float | None:
        return control_value(self.coordinator, self._control)

    async def async_set_native_value(self, value: float) -> None:
        await self._async_set_level(value, partial(set_control, self.coordinator, self._control))


class GoveeBLELocalVolume(_GoveeBLELevel):
    _attr_translation_key = "local_volume"
    _attr_native_unit_of_measurement = "%"

    @property
    def native_min_value(self) -> float:
        return (self.coordinator.profile.local_volume_range or (0, 0))[0]

    @property
    def native_max_value(self) -> float:
        return (self.coordinator.profile.local_volume_range or (0, 0))[1]

    @property
    def available(self) -> bool:
        return self.coordinator.profile.local_volume_range is not None and super().available

    @property
    def native_value(self) -> float | None:
        return self.coordinator.local_volume

    async def async_set_native_value(self, value: float) -> None:
        await self._async_set_level(value, partial(self.coordinator.async_set_local_audio, "local_volume"))
