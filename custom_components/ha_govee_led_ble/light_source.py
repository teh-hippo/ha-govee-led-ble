"""Lights for independently controllable sources of a shared device."""

from typing import Any

from homeassistant.components.light import (  # type: ignore[attr-defined]
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util.color import brightness_to_value

from .const import DOMAIN, LightSource, ModelProfile, ReadDomain, light_unique_id
from .coordinator import GoveeBLECoordinator
from .coordinator_sources import SourceTurnOnRequest, source_color_modes, source_segments_available
from .coordinator_status import ParsedMode
from .entity import GoveeBLEEntity
from .light_commands import (
    kelvin_rendering_matches,
)


class GoveeBLESourceLight(GoveeBLEEntity, LightEntity):
    def __init__(
        self, coordinator: GoveeBLECoordinator, key: str, device_service_owner: LightEntity | None = None
    ) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_translation_key = key
        self._attr_unique_id = light_unique_id(coordinator.address, key)
        self._attr_device_info = coordinator.device_info
        self.device_service_owner = device_service_owner
        self._pending_turn_on: dict[str, Any] | None = None

    def _source(self, profile: ModelProfile) -> LightSource | None:
        return next((source for source in profile.light_sources if source.key == self._key), None)

    @property
    def available(self) -> bool:
        source = self._source(self.coordinator.profile)
        return source is not None and source.control in self.coordinator.profile.boolean_controls and super().available

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.source_power_state(self._key)

    @property
    def assumed_state(self) -> bool:
        source = self._source(self.coordinator.profile)
        if source is not None and source.native_control:
            return not all(
                self.coordinator.source_field_fresh(field)
                for field in ("is_on", f"boolean_{source.control}", f"{source.key}_brightness", f"{source.key}_kelvin")
            )
        return (
            self.coordinator.control_state_uncertain("is_on")
            or self.coordinator.control_state_uncertain("color", "color_mode")
            and bool(self.supported_color_modes & {ColorMode.RGB, ColorMode.COLOR_TEMP})
            or source is None
            or self.coordinator.boolean_control_state.get(source.control) is None
            or not self.coordinator.profile.can_read(ReadDomain.POWER)
            or not self.coordinator.source_field_fresh("is_on")
            or not self.coordinator.source_field_fresh(f"boolean_{source.control}")
            or source.master_brightness
            and not self.coordinator.profile.can_read(ReadDomain.BRIGHTNESS)
            or self.supported_color_modes != {ColorMode.ONOFF}
            and not source.master_brightness
            and self.coordinator.segment_state_source != "observed"
        )

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        profile = self.coordinator.native_presentation_profile
        return {ColorMode(mode) for mode in source_color_modes(self._source(profile), profile)}

    def _values(self, values: list[Any]) -> list[Any] | None:
        source = self._source(self.coordinator.profile)
        if source is None or not source_segments_available(source, self.coordinator.profile):
            return None
        if len(values) < max(source.segments):
            return None
        return [values[index - 1] for index in source.segments]

    @property
    def brightness(self) -> int | None:
        source = self._source(self.coordinator.profile)
        if source is not None and source.native_control:
            value = getattr(self.coordinator, f"{source.key}_brightness", None)
            return round(value * 255 / 100) if value is not None else None
        if (
            source is not None
            and source.master_brightness
            and self.coordinator.control_state_uncertain("brightness_pct")
        ):
            return None
        if source is not None and source.master_brightness and self.supported_color_modes != {ColorMode.ONOFF}:
            return round(self.coordinator.brightness_pct * 255 / 100)
        if self.supported_color_modes == {ColorMode.ONOFF} or self.coordinator.segment_state_source == "initial":
            return None
        values = self._values(self.coordinator.segment_brightness)
        return round(values[0] * 255 / 100) if values and len(set(values)) == 1 else None

    @property
    def color_mode(self) -> ColorMode | None:
        modes = self.supported_color_modes
        source = self._source(self.coordinator.profile)
        if source is not None and source.native_control:
            return (
                ColorMode.COLOR_TEMP if getattr(self.coordinator, f"{source.key}_kelvin", None) else ColorMode.UNKNOWN
            )
        if self.coordinator.control_state_uncertain("color_mode") and modes & {
            ColorMode.RGB,
            ColorMode.COLOR_TEMP,
        }:
            return ColorMode.UNKNOWN
        if modes == {ColorMode.ONOFF}:
            return ColorMode.ONOFF
        if modes == {ColorMode.BRIGHTNESS}:
            return ColorMode.BRIGHTNESS
        if self.coordinator.color_mode not in (None, ParsedMode.COLOUR):
            return ColorMode.UNKNOWN
        intent = self.coordinator.source_static_intents.get(self._key)
        if type(intent) is int and ColorMode.COLOR_TEMP in modes:
            colours = self._values(self.coordinator.segment_colors)
            if colours and all(
                kelvin_rendering_matches(colour, intent, self.coordinator.profile) for colour in colours
            ):
                return ColorMode.COLOR_TEMP
        return ColorMode.RGB if ColorMode.RGB in modes else None

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        if self.color_mode is not ColorMode.RGB or self.coordinator.segment_state_source == "initial":
            return None
        values = self._values(self.coordinator.segment_colors)
        return values[0] if values and len(set(values)) == 1 else None

    @property
    def min_color_temp_kelvin(self) -> int:
        return self.coordinator.profile.min_color_temp_kelvin

    @property
    def max_color_temp_kelvin(self) -> int:
        return self.coordinator.profile.max_color_temp_kelvin

    @property
    def color_temp_kelvin(self) -> int | None:
        source = self._source(self.coordinator.profile)
        if source is not None and source.native_control:
            return getattr(self.coordinator, f"{source.key}_kelvin", None) or None
        intent = self.coordinator.source_static_intents.get(self._key)
        return intent if type(intent) is int and self.color_mode is ColorMode.COLOR_TEMP else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        pending = self._pending_turn_on or {}
        if ATTR_RGB_COLOR in kwargs or ATTR_COLOR_TEMP_KELVIN in kwargs:
            pending = {
                key: value for key, value in pending.items() if key not in (ATTR_RGB_COLOR, ATTR_COLOR_TEMP_KELVIN)
            }
        self._pending_turn_on = {**pending, **kwargs}
        await self._async_latest(self._send_pending_turn_on, "power")

    async def _send_pending_turn_on(self) -> None:
        kwargs, self._pending_turn_on = self._pending_turn_on or {}, None
        if kwargs.get(ATTR_BRIGHTNESS) == 0:
            await self._set_source(False)
            return
        try:
            colour = kwargs.get(ATTR_RGB_COLOR)
            request = SourceTurnOnRequest(
                brightness_pct=max(1, round(brightness_to_value((1, 100), kwargs[ATTR_BRIGHTNESS])))
                if ATTR_BRIGHTNESS in kwargs
                else None,
                rgb_color=tuple(colour) if colour is not None else None,
                kelvin=kwargs.get(ATTR_COLOR_TEMP_KELVIN),
            )
        except HomeAssistantError:
            raise
        except Exception as error:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="device_command_failed") from error
        await self.coordinator.async_turn_on_source(self._key, request)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._pending_turn_on = None
        await self._async_latest(lambda: self._set_source(False), "power")

    async def _set_source(self, enabled: bool) -> None:
        await self.coordinator.async_set_source_enabled(self._key, enabled)
