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

from .const import DOMAIN, LightSource, ModelProfile, ReadDomain
from .control_arbiter import ControlIntent, async_control_intent
from .coordinator import GoveeBLECoordinator
from .coordinator_status import ParsedMode
from .entity import GoveeBLEEntity
from .generated_protocol_adapter import build_brightness, build_power, build_source_value, require_profile_packet
from .light_commands import (
    build_segment_brightness,
    build_segment_color_temp,
    build_segment_paint,
    kelvin_rendering_matches,
    normalize_kelvin,
)


class GoveeBLESourceLight(GoveeBLEEntity, LightEntity):
    def __init__(
        self, coordinator: GoveeBLECoordinator, key: str, device_service_owner: LightEntity | None = None
    ) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_translation_key = key
        self._attr_unique_id = f"{coordinator.address.replace(':', '').lower()}_{key}"
        self._attr_device_info = coordinator.device_info
        self.device_service_owner = device_service_owner
        self._pending_turn_on: dict[str, Any] | None = None

    def _source(self, profile: ModelProfile) -> LightSource | None:
        return next((source for source in profile.light_sources if source.key == self._key), None)

    @staticmethod
    def _segments_available(source: LightSource, profile: ModelProfile) -> bool:
        return (
            bool(source.segments)
            and profile.supports_segments
            and all(segment <= profile.segment_count for segment in source.segments)
        )

    @property
    def available(self) -> bool:
        source = self._source(self.coordinator.profile)
        return source is not None and source.control in self.coordinator.profile.boolean_controls and super().available

    @property
    def is_on(self) -> bool | None:
        source = self._source(self.coordinator.profile)
        if (
            source is None
            or self.coordinator.is_on is None
            or "is_on" in self.coordinator._h607c_uncertain_state_fields
            or self.coordinator._field_revisions.get("is_on", 0) == 0
            and "is_on" not in self.coordinator._expected_state
        ):
            return None
        if not self.coordinator.is_on:
            return False
        return self.coordinator.boolean_control_state.get(source.control)

    @property
    def assumed_state(self) -> bool:
        source = self._source(self.coordinator.profile)
        if source is not None and source.native_control:
            return not all(
                self._fresh(field)
                for field in ("is_on", f"boolean_{source.control}", f"{source.key}_brightness", f"{source.key}_kelvin")
            )
        return (
            "is_on" in self.coordinator._h607c_uncertain_state_fields
            or bool(self.coordinator._h607c_uncertain_state_fields & {"color", "color_mode"})
            and bool(self.supported_color_modes & {ColorMode.RGB, ColorMode.COLOR_TEMP})
            or source is None
            or self.coordinator.boolean_control_state.get(source.control) is None
            or not self.coordinator.profile.can_read(ReadDomain.POWER)
            or not self._fresh("is_on")
            or not self._fresh(f"boolean_{source.control}")
            or source.master_brightness
            and not self.coordinator.profile.can_read(ReadDomain.BRIGHTNESS)
            or self.supported_color_modes != {ColorMode.ONOFF}
            and not source.master_brightness
            and self.coordinator.segment_state_source != "observed"
        )

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        profile = self.coordinator.native_presentation_profile
        source = self._source(profile)
        if source is not None and source.color_modes is not None:
            return {ColorMode(mode) for mode in source.color_modes}
        if (
            source is not None
            and source.master_brightness
            and (profile.command_operations is None or "brightness" in profile.command_operations)
        ):
            master_modes: set[ColorMode] = set()
            if self._segments_available(source, profile):
                if profile.supports_rgb:
                    master_modes.add(ColorMode.RGB)
                if profile.supports_color_temperature and profile.supports_segment_color_temperature:
                    master_modes.add(ColorMode.COLOR_TEMP)
            return master_modes or {ColorMode.BRIGHTNESS}
        if source is None or not self._segments_available(source, profile) or not profile.supports_segment_brightness:
            return {ColorMode.ONOFF}
        modes: set[ColorMode] = set()
        if profile.supports_rgb:
            modes.add(ColorMode.RGB)
        if profile.supports_color_temperature and profile.supports_segment_color_temperature:
            modes.add(ColorMode.COLOR_TEMP)
        return modes or {ColorMode.BRIGHTNESS}

    def _values(self, values: list[Any]) -> list[Any] | None:
        source = self._source(self.coordinator.profile)
        if source is None or not self._segments_available(source, self.coordinator.profile):
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
            and "brightness_pct" in self.coordinator._h607c_uncertain_state_fields
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
        if f"source_colour_{self._key}" in self.coordinator._h607c_uncertain_state_fields:
            return ColorMode.UNKNOWN
        if source is not None and source.native_control:
            return (
                ColorMode.COLOR_TEMP if getattr(self.coordinator, f"{source.key}_kelvin", None) else ColorMode.UNKNOWN
            )
        if "color_mode" in self.coordinator._h607c_uncertain_state_fields and modes & {
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
        coordinator = self.coordinator
        profile = coordinator.profile
        source = self._source(profile)
        if source is None or source.control not in profile.boolean_controls:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="device_command_failed")
        segments = list(source.segments)
        attempts = coordinator.control_write_attempts
        try:
            modes = self.supported_color_modes
            brightness = (
                max(1, round(brightness_to_value((1, 100), kwargs[ATTR_BRIGHTNESS])))
                if ATTR_BRIGHTNESS in kwargs
                else None
            )
            brightness_packet = None
            if brightness is not None:
                if modes == {ColorMode.ONOFF}:
                    raise ValueError("This source does not support brightness")
                if source.native_control:
                    build_source_value(source.key, "brightness", brightness, profile)
                elif source.master_brightness:
                    brightness_packet = build_brightness(brightness, coordinator.model, profile=profile)
                    require_profile_packet(brightness_packet, profile)
                else:
                    build_segment_brightness(segments, brightness, coordinator.model, profile=profile)
            colour = kwargs.get(ATTR_RGB_COLOR)
            if colour is not None:
                if ColorMode.RGB not in modes:
                    raise ValueError("This source does not support RGB")
                build_segment_paint([(segments, tuple(colour))], coordinator.model, profile=profile)
            kelvin = kwargs.get(ATTR_COLOR_TEMP_KELVIN)
            if kelvin is not None and source.native_control:
                if (
                    type(kelvin) is not int
                    or not profile.min_color_temp_kelvin <= kelvin <= profile.max_color_temp_kelvin
                ):
                    raise ValueError("Source Kelvin is outside the profile")
                kelvin = normalize_kelvin(kelvin, profile)
            if kelvin is not None and ColorMode.COLOR_TEMP not in modes:
                raise ValueError("This source does not support colour temperature")
            packet = None
            if kelvin is not None:
                packet = (
                    build_source_value(source.key, "kelvin", kelvin, profile)
                    if source.native_control
                    else build_segment_color_temp(segments, kelvin, coordinator.model, profile=profile)
                )
            if colour is not None and kelvin is not None:
                raise ValueError("A source cannot select RGB and colour temperature together")
            guard = (
                await coordinator.async_prepare_identity_gated_control()
                if coordinator.identity_gated_controls
                else None
            )
            await coordinator._async_supersede_effect_preview()
            async with async_control_intent(coordinator, ControlIntent.USER):
                if coordinator.profile != profile:
                    raise ValueError("The device profile changed")
                if guard is not None:
                    guard()
                if profile.can_read(ReadDomain.POWER) and (
                    not self._fresh("is_on") or "is_on" in coordinator._h607c_uncertain_state_fields
                ):
                    revision = coordinator._field_revisions.get("is_on", 0)
                    if not await coordinator.refresh_state(
                        refresh_all=True, query_segments=False, required_domains=frozenset({ReadDomain.POWER})
                    ) or (
                        not self._fresh("is_on")
                        or coordinator._field_revisions.get("is_on", 0) <= revision
                        or "is_on" in coordinator._h607c_uncertain_state_fields
                    ):
                        raise ValueError("The device did not provide fresh master power")
                    if coordinator.profile != profile:
                        raise ValueError("The device profile changed")
                    if guard is not None:
                        guard()
                master_off = coordinator.is_on is not True or "is_on" in coordinator._h607c_uncertain_state_fields
                await coordinator.async_validate_source_power(source.control, True)
                if master_off and not profile.minimum_enabled_sources:
                    for sibling in profile.light_sources:
                        if sibling.key != source.key and (
                            coordinator.boolean_control_state.get(sibling.control) is not False
                            or not self._fresh(f"boolean_{sibling.control}")
                        ):
                            await self._set_source_control(sibling.control, False)
                if master_off:
                    power = build_power(True, coordinator.model, profile=profile)
                    power_attempts = coordinator.control_write_attempts
                    power_revision = coordinator._field_revisions.get("is_on", 0)

                    def power_guard() -> None:
                        nonlocal power_revision
                        if guard is not None:
                            guard()
                        power_revision = coordinator._field_revisions.get("is_on", 0)

                    try:
                        await coordinator.send_command(power, write_guard=power_guard)
                        if profile.can_read(ReadDomain.POWER) and not await coordinator.refresh_state(expected_on=True):
                            raise ValueError("The device did not confirm master power")
                    except BaseException:
                        if (
                            coordinator.control_write_attempts != power_attempts
                            and coordinator._field_revisions.get("is_on", 0) <= power_revision
                        ):
                            coordinator._h607c_uncertain_state_fields.add("is_on")
                            coordinator._expected_state.pop("is_on", None)
                            coordinator.async_set_updated_data(coordinator.data or {})
                        raise
                if (
                    master_off
                    or coordinator.boolean_control_state.get(source.control) is not True
                    or not self._fresh(f"boolean_{source.control}")
                ):
                    await self._set_source_control(source.control, True)
                async with coordinator.async_mask_transaction():
                    if brightness is not None:
                        if source.native_control:
                            await coordinator.async_set_source_value(source.key, "brightness", brightness)
                        elif brightness_packet is not None:
                            brightness_attempts = coordinator.control_write_attempts
                            brightness_revision = coordinator._field_revisions.get("brightness_pct", 0)
                            try:
                                await coordinator.send_command(brightness_packet, write_guard=guard)
                            except BaseException:
                                if (
                                    coordinator.control_write_attempts != brightness_attempts
                                    and coordinator._field_revisions.get("brightness_pct", 0) <= brightness_revision
                                ):
                                    coordinator._h607c_uncertain_state_fields.add("brightness_pct")
                                    coordinator._expected_state.pop("brightness_pct", None)
                                    coordinator.async_set_updated_data(coordinator.data or {})
                                raise
                        else:
                            await coordinator.async_set_segment_brightness(
                                segments, brightness, **({"write_guard": guard} if guard is not None else {})
                            )
                    if colour is not None:
                        await coordinator.async_paint_segments(
                            [(segments, tuple(colour))], **({"write_guard": guard} if guard is not None else {})
                        )
                    if packet is not None:
                        assert kelvin is not None
                        if source.native_control:
                            await coordinator.async_set_source_value(source.key, "kelvin", kelvin)
                        else:
                            await coordinator.async_set_segment_kelvin(
                                packet, requested_kelvin=kelvin, **({"write_guard": guard} if guard is not None else {})
                            )
            coordinator.async_set_updated_data(coordinator.data or {})
        except Exception as error:
            partial = coordinator.control_write_attempts != attempts
            if isinstance(error, HomeAssistantError) and not partial:
                raise
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="partial_command" if partial else "device_command_failed"
            ) from error

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._pending_turn_on = None
        await self._async_latest(lambda: self._set_source(False), "power")

    async def _set_source(self, enabled: bool) -> None:
        source = self._source(self.coordinator.profile)
        if source is None or source.control not in self.coordinator.profile.boolean_controls:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="device_command_failed")
        try:
            await self._set_source_control(source.control, enabled)
            self.coordinator.async_set_updated_data(self.coordinator.data or {})
        except HomeAssistantError:
            raise
        except Exception as error:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="device_command_failed") from error

    def _fresh(self, field: str) -> bool:
        coordinator = self.coordinator
        started = coordinator._notify_started_monotonic
        received = coordinator._field_received_at.get(field)
        fresh = (
            coordinator._client is not None
            and coordinator._client.is_connected
            and started is not None
            and received is not None
            and received >= started
        )
        if not fresh:
            return False
        if field == "is_on":
            return (
                coordinator._observed_power_write_generation == coordinator._power_write_generation
                and coordinator._observed_power_profile_generation == coordinator._profile_generation
            )
        if field.startswith("boolean_"):
            return coordinator._source_power_observation_generation.get(field) == (
                coordinator._power_write_generation,
                coordinator._profile_generation,
            )
        return True

    async def _set_source_control(self, control: str, enabled: bool) -> None:
        attempts = self.coordinator.control_write_attempts
        try:
            await self.coordinator.async_set_boolean_control(control, enabled)
        except BaseException:
            if self.coordinator.control_write_attempts != attempts:
                self.coordinator.boolean_control_state.pop(control, None)
                self.coordinator._field_received_at.pop(f"boolean_{control}", None)
                self.coordinator.async_set_updated_data(self.coordinator.data or {})
            raise
