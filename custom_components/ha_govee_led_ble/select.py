"""Profile-qualified native configuration controls."""

from bleak.exc import BleakError
from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import GoveeBLEConfigEntry
from .const import DOMAIN
from .control_arbiter import ControlIntent, async_control_intent
from .effect_contracts import CapabilityState
from .effect_setup import get_effect_backend
from .entity import GoveeBLEEntity
from .video_applicability import h6199_camera_controls_state

PARALLEL_UPDATES = 0
_OPTIONS = {
    "strip_direction": ["clockwise", "anticlockwise"],
    "camera_position": ["top", "bottom"],
    "gradient": ["off", "on"],
}


async def async_setup_entry(
    hass: HomeAssistant, entry: GoveeBLEConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    added = False
    strings_added = False
    power_on_added = False

    def add_qualified() -> None:
        nonlocal added, strings_added, power_on_added
        if not power_on_added and coordinator.profile.supports_power_on_behaviour:
            power_on_added = True
            async_add_entities([GoveeBLEPowerOnBehaviourSelect(entry)])
        if not strings_added and coordinator.profile.configured_string_counts:
            strings_added = True
            async_add_entities([GoveeBLEConfiguredStringsSelect(entry)])
        if (
            coordinator.model == "H6199"
            and not added
            and h6199_camera_controls_state(coordinator.model, coordinator) is CapabilityState.SUPPORTED
        ):
            added = True
            async_add_entities([GoveeBLEControlSelect(entry, key) for key in _OPTIONS])

    add_qualified()
    entry.async_on_unload(coordinator.async_add_listener(add_qualified))


class GoveeBLEControlSelect(GoveeBLEEntity, SelectEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False

    def __init__(self, entry: GoveeBLEConfigEntry, control: str) -> None:
        super().__init__(entry.runtime_data)
        self._entry = entry
        self._control = control
        self._attr_translation_key = control
        self._attr_unique_id = f"{self.coordinator.address.replace(':', '').lower()}_{control}"
        self._attr_device_info = self.coordinator.device_info
        self._attr_options = _OPTIONS[control]

    @property
    def available(self) -> bool:
        return (
            h6199_camera_controls_state(self.coordinator.model, self.coordinator) is CapabilityState.SUPPORTED
            and super().available
        )

    @property
    def current_option(self) -> str | None:
        value = getattr(self.coordinator, self._control)
        return self.options[value] if type(value) is int and value in (0, 1) else None

    async def async_select_option(self, option: str) -> None:
        if option not in self.options:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="invalid_control_request")
        async with async_control_intent(self.coordinator, ControlIntent.USER):
            if h6199_camera_controls_state(self.coordinator.model, self.coordinator) is not CapabilityState.SUPPORTED:
                raise ServiceValidationError(translation_domain=DOMAIN, translation_key="invalid_control_request")
            if backend := get_effect_backend(self.hass):
                await backend.preview.async_supersede_device(self._entry.entry_id, reason="home_assistant_control")
            try:
                await self.coordinator.async_set_h6199_control(self._control, self.options.index(option))
            except (BleakError, ValueError, TimeoutError) as err:
                raise HomeAssistantError(translation_domain=DOMAIN, translation_key="device_command_failed") from err


class GoveeBLEConfiguredStringsSelect(GoveeBLEEntity, SelectEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "configured_strings"

    def __init__(self, entry: GoveeBLEConfigEntry) -> None:
        super().__init__(entry.runtime_data)
        self._attr_unique_id = f"{self.coordinator.address.replace(':', '').lower()}_configured_strings"
        self._attr_device_info = self.coordinator.device_info

    @property
    def options(self) -> list[str]:
        return [str(count) for count in self.coordinator.profile.configured_string_counts]

    @property
    def available(self) -> bool:
        return bool(self.options) and super().available

    @property
    def current_option(self) -> str | None:
        count = self.coordinator.configured_strings
        return str(count) if count in self.coordinator.profile.configured_string_counts else None

    async def async_select_option(self, option: str) -> None:
        if option not in self.options:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="invalid_control_request")
        try:
            await self.coordinator.async_set_configured_strings(int(option))
        except (BleakError, ValueError, TimeoutError) as error:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="device_command_failed") from error


class GoveeBLEPowerOnBehaviourSelect(GoveeBLEEntity, SelectEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "power_on_behaviour"
    _attr_entity_registry_visible_default = False
    _attr_options = ["previous", "on", "off"]

    def __init__(self, entry: GoveeBLEConfigEntry) -> None:
        super().__init__(entry.runtime_data)
        self._attr_unique_id = f"{self.coordinator.address.replace(':', '').lower()}_power_on_behaviour"
        self._attr_device_info = self.coordinator.device_info

    @property
    def available(self) -> bool:
        return self.coordinator.profile.supports_power_on_behaviour and super().available

    @property
    def current_option(self) -> str | None:
        return self.coordinator.power_on_behaviour

    async def async_select_option(self, option: str) -> None:
        if option not in self.options:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="invalid_control_request")
        try:
            await self.coordinator.async_set_power_on_behaviour(option)
        except (BleakError, ValueError, TimeoutError) as error:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="device_command_failed") from error
