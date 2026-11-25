"""Profile-qualified native configuration controls."""

from functools import partial

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
from .projector import ProjectorControl
from .projector_runtime import control_value, set_control
from .video_applicability import camera_controls_state

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
    projector_added = False
    sound_added = False

    def add_qualified() -> None:
        nonlocal added, strings_added, power_on_added, projector_added, sound_added
        if not sound_added and coordinator.profile.local_sound_options:
            sound_added = True
            async_add_entities([GoveeBLELocalSoundSelect(entry)])
        if not projector_added and coordinator.profile.projector_grammar is not None:
            projector_added = True
            async_add_entities([GoveeBLEProjectorPatternSelect(entry)])
        if not power_on_added and coordinator.native_presentation_profile.supports_power_on_behaviour:
            power_on_added = True
            async_add_entities([GoveeBLEPowerOnBehaviourSelect(entry)])
        if not strings_added and coordinator.profile.configured_string_counts:
            strings_added = True
            async_add_entities([GoveeBLEConfiguredStringsSelect(entry)])
        if not added and camera_controls_state(coordinator.profile, coordinator) is CapabilityState.SUPPORTED:
            added = True
            async_add_entities([GoveeBLEControlSelect(entry, key) for key in _OPTIONS])

    add_qualified()
    entry.async_on_unload(coordinator.async_add_listener(add_qualified))


class GoveeBLEProjectorPatternSelect(GoveeBLEEntity, SelectEntity):
    _attr_translation_key = "projector_aurora_pattern"
    # Keep legacy option IDs stable for existing automations.
    _attr_options = ["fade", "breathe", "flash", "steady"]

    def __init__(self, entry: GoveeBLEConfigEntry) -> None:
        super().__init__(entry.runtime_data)
        self._attr_unique_id = f"{self.coordinator.address.replace(':', '').lower()}_projector_aurora_pattern"

    @property
    def available(self) -> bool:
        return self.coordinator.profile.projector_grammar is not None and super().available

    @property
    def current_option(self) -> str | None:
        value = control_value(self.coordinator, ProjectorControl.AURORA_PATTERN)
        return self.options[value - 1] if type(value) is int and 1 <= value <= len(self.options) else None

    async def async_select_option(self, option: str) -> None:
        if option not in self.options:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="invalid_control_request")
        try:
            await self._async_latest(
                partial(set_control, self.coordinator, ProjectorControl.AURORA_PATTERN, self.options.index(option) + 1)
            )
        except (BleakError, ValueError, TimeoutError) as error:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="device_command_failed") from error


class GoveeBLELocalSoundSelect(GoveeBLEEntity, SelectEntity):
    _attr_translation_key = "local_sound"

    def __init__(self, entry: GoveeBLEConfigEntry) -> None:
        super().__init__(entry.runtime_data)
        self._attr_unique_id = f"{self.coordinator.address.replace(':', '').lower()}_local_sound"

    @property
    def options(self) -> list[str]:
        return list(self.coordinator.profile.local_sound_options)

    @property
    def available(self) -> bool:
        return bool(self.options) and super().available

    @property
    def current_option(self) -> str | None:
        value = self.coordinator.local_sound
        return self.options[value - 1] if value is not None and 1 <= value <= len(self.options) else None

    async def async_select_option(self, option: str) -> None:
        if option not in self.options:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="invalid_control_request")
        try:
            await self._async_latest(
                partial(self.coordinator.async_set_local_audio, "local_sound", self.options.index(option) + 1)
            )
        except (BleakError, ValueError, TimeoutError) as error:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="device_command_failed") from error


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
            camera_controls_state(self.coordinator.profile, self.coordinator) is CapabilityState.SUPPORTED
            and super().available
        )

    @property
    def current_option(self) -> str | None:
        value = getattr(self.coordinator, self._control)
        return self.options[value] if type(value) is int and value in (0, 1) else None

    async def async_select_option(self, option: str) -> None:
        if option not in self.options:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="invalid_control_request")
        await self._async_latest(partial(self._async_select_control, option))

    async def _async_select_control(self, option: str) -> None:
        async with async_control_intent(self.coordinator, ControlIntent.USER):
            if camera_controls_state(self.coordinator.profile, self.coordinator) is not CapabilityState.SUPPORTED:
                raise ServiceValidationError(translation_domain=DOMAIN, translation_key="invalid_control_request")
            if backend := get_effect_backend(self.hass):
                await backend.preview.async_supersede_device(self._entry.entry_id, reason="home_assistant_control")
            try:
                await self.coordinator.async_set_native_camera_control(self._control, self.options.index(option))
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
            await self._async_latest(partial(self.coordinator.async_set_configured_strings, int(option)))
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
        return self.coordinator.native_presentation_profile.supports_power_on_behaviour and super().available

    @property
    def current_option(self) -> str | None:
        return self.coordinator.power_on_behaviour

    async def async_select_option(self, option: str) -> None:
        if option not in self.options:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="invalid_control_request")
        try:
            await self._async_latest(partial(self.coordinator.async_set_power_on_behaviour, option))
        except (BleakError, ValueError, TimeoutError) as error:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="device_command_failed") from error
