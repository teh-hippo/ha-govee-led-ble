"""Transactions and observations for independently addressable light sources."""

from __future__ import annotations

from collections.abc import Callable, Generator
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN, LightSource, ModelProfile, ReadDomain
from .control_arbiter import ControlIntent, async_control_intent
from .coordinator_refresh import RefreshRequest
from .coordinator_status import ParsedMode
from .generated_protocol_adapter import build_brightness, build_power, build_source_value, require_profile_packet
from .light_commands import (
    build_segment_brightness,
    build_segment_color_temp,
    build_segment_paint,
    kelvin_rendering_matches,
    normalize_kelvin,
    scale_segment_groups,
)

if TYPE_CHECKING:
    from .coordinator import GoveeBLECoordinator


@dataclass(frozen=True, slots=True)
class SourceTurnOnRequest:
    brightness_pct: int | None = None
    rgb_color: tuple[int, int, int] | None = None
    kelvin: int | None = None


@dataclass(frozen=True, slots=True)
class PreparedSourceValue:
    profile: ModelProfile
    source: str
    attribute: str
    value: int
    packet: bytes

    @classmethod
    def prepare(cls, source: str, attribute: str, value: int, profile: ModelProfile) -> PreparedSourceValue:
        return cls(profile, source, attribute, value, build_source_value(source, attribute, value, profile))


@dataclass(frozen=True, slots=True)
class _SourceColourWrite:
    source: LightSource
    rgb: tuple[int, int, int] | None
    kelvin: int | None
    packets: tuple[bytes, ...]
    native: PreparedSourceValue | None = None


@dataclass(frozen=True, slots=True)
class PreparedSourceColour:
    profile: ModelProfile
    writes: tuple[_SourceColourWrite, ...]

    async def apply(self, coordinator: GoveeBLECoordinator, guard: Callable[[], None]) -> None:
        client, token = coordinator._client, coordinator._notification_token
        generation, authorization = coordinator._profile_generation, coordinator._authorization_generation

        def check() -> None:
            guard()
            if (
                coordinator.profile != self.profile
                or coordinator._profile_generation != generation
                or coordinator._authorization_generation != authorization
            ):
                raise ValueError("The source colour profile changed")
            if coordinator._client is not client or coordinator._notification_token is not token:
                raise ValueError("The source colour subscription changed")

        async with async_control_intent(coordinator, ControlIntent.USER):
            attempts = coordinator.control_write_attempts
            try:
                async with (
                    coordinator.async_mask_transaction()
                    if any(write.source.segments for write in self.writes)
                    else nullcontext()
                ):
                    for write in self.writes:
                        check()
                        if write.native is not None:
                            await coordinator.async_apply_source_value(write.native, write_guard=check)
                        elif write.kelvin is not None:
                            await coordinator.async_set_segment_kelvin(
                                write.packets[0], requested_kelvin=write.kelvin, write_guard=check
                            )
                        else:
                            assert write.rgb is not None
                            await coordinator._async_write_segment_batch(
                                list(write.packets),
                                {segment - 1: write.rgb for segment in write.source.segments},
                                {},
                                "paint",
                                write_guard=check,
                            )
            except Exception as error:
                if coordinator.control_write_attempts != attempts:
                    raise HomeAssistantError(translation_domain=DOMAIN, translation_key="partial_command") from error
                raise


def prepare_source_colour(
    coordinator: GoveeBLECoordinator,
    keys: tuple[str, ...],
    values: SourceTurnOnRequest,
) -> PreparedSourceColour:
    profile = coordinator.profile
    if values.rgb_color is not None and values.kelvin is not None:
        raise ValueError("A source cannot select RGB and colour temperature together")
    if values.rgb_color is None and values.kelvin is None:
        raise ValueError("A source colour is required")
    mode = "rgb" if values.rgb_color is not None else "color_temp"
    writes = []
    for key in keys:
        source = _source(profile, key)
        if source is None or source.control not in profile.boolean_controls:
            raise ValueError("This source is unavailable")
        if mode not in source_color_modes(source, profile):
            continue
        if source.native_control:
            if values.kelvin is None:
                raise ValueError("Native source RGB is unavailable")
            native = PreparedSourceValue.prepare(key, "kelvin", values.kelvin, profile)
            writes.append(_SourceColourWrite(source, None, values.kelvin, (), native))
        else:
            if values.rgb_color is not None:
                packets = tuple(
                    build_segment_paint(
                        scale_segment_groups([(source.segments, values.rgb_color)]), coordinator.model, profile=profile
                    )
                )
            else:
                assert values.kelvin is not None
                packets = (
                    build_segment_color_temp(source.segments, values.kelvin, coordinator.model, profile=profile),
                )
            for packet in packets:
                require_profile_packet(packet, profile)
            writes.append(_SourceColourWrite(source, values.rgb_color, values.kelvin, packets))
    if not writes:
        raise ValueError("No source supports the requested colour")
    return PreparedSourceColour(profile, tuple(writes))


def main_source_colour(coordinator: GoveeBLECoordinator) -> int | tuple[int, int, int] | None:
    if coordinator.color_mode is not ParsedMode.COLOUR:
        return None
    profile = coordinator.profile
    colours: list[int | tuple[int, int, int]] = []
    native_colours: list[int | None] = []
    for key in profile.main_colour_sources:
        source = _source(profile, key)
        if source is None or f"source_colour_{key}" in coordinator._h607c_uncertain_state_fields:
            return None
        if source.native_control:
            native_colours.append(getattr(coordinator, f"{key}_kelvin", None))
            continue
        if not source_segments_available(source, profile) or len(coordinator.segment_colors) < max(source.segments):
            return None
        rendered = [coordinator.segment_colors[segment - 1] for segment in source.segments]
        intent = coordinator.source_static_intents.get(key)
        if type(intent) is int:
            if not all(kelvin_rendering_matches(rgb, intent, profile) for rgb in rendered):
                return None
            colours.append(intent)
        elif coordinator.segment_state_source != "initial" and len(set(rendered)) == 1:
            colours.append(rendered[0])
        else:
            return None
    if not colours or len(set(colours)) != 1:
        return None
    value = colours[0]
    if type(value) is int and any(kelvin != value for kelvin in native_colours):
        return None
    return value


@dataclass(frozen=True, slots=True)
class _PreparedSourceRequest:
    profile: ModelProfile
    source: LightSource
    values: SourceTurnOnRequest
    brightness_packet: bytes | None
    colour: PreparedSourceColour | None


def _source(profile: ModelProfile, key: str) -> LightSource | None:
    return next((source for source in profile.light_sources if source.key == key), None)


def source_segments_available(source: LightSource, profile: ModelProfile) -> bool:
    return (
        bool(source.segments)
        and profile.supports_segments
        and all(segment <= profile.segment_count for segment in source.segments)
    )


def source_color_modes(source: LightSource | None, profile: ModelProfile) -> frozenset[str]:
    if source is not None and source.color_modes is not None:
        return source.color_modes
    modes: set[str] = set()
    if (
        source is not None
        and source.master_brightness
        and (profile.command_operations is None or "brightness" in profile.command_operations)
    ):
        if source_segments_available(source, profile):
            if profile.supports_rgb:
                modes.add("rgb")
            if profile.supports_color_temperature and profile.supports_segment_color_temperature:
                modes.add("color_temp")
        return frozenset(modes or {"brightness"})
    if source is None or not source_segments_available(source, profile) or not profile.supports_segment_brightness:
        return frozenset({"onoff"})
    if profile.supports_rgb:
        modes.add("rgb")
    if profile.supports_color_temperature and profile.supports_segment_color_temperature:
        modes.add("color_temp")
    return frozenset(modes or {"brightness"})


def source_power_state(coordinator: GoveeBLECoordinator, key: str) -> bool | None:
    source = _source(coordinator.profile, key)
    if (
        source is None
        or coordinator.is_on is None
        or "is_on" in coordinator._h607c_uncertain_state_fields
        or coordinator._field_revisions.get("is_on", 0) == 0
        and "is_on" not in coordinator._expected_state
    ):
        return None
    return coordinator.boolean_control_state.get(source.control) if coordinator.is_on else False


def source_field_fresh(coordinator: GoveeBLECoordinator, field: str) -> bool:
    started = coordinator._notify_started_monotonic
    received = coordinator._field_received_at.get(field)
    if not (
        coordinator._client is not None
        and coordinator._client.is_connected
        and started is not None
        and received is not None
        and received >= started
    ):
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


async def async_set_source_enabled(coordinator: GoveeBLECoordinator, key: str, enabled: bool) -> None:
    source = _source(coordinator.profile, key)
    if source is None or source.control not in coordinator.profile.boolean_controls:
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="device_command_failed")
    try:
        await coordinator.async_set_boolean_control(source.control, enabled)
        coordinator.async_set_updated_data(coordinator.data or {})
    except HomeAssistantError:
        raise
    except Exception as error:
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="device_command_failed") from error


class SourceTurnOnTransaction:
    def __init__(self, coordinator: GoveeBLECoordinator, key: str, request: SourceTurnOnRequest) -> None:
        self._coordinator = coordinator
        self._key = key
        self._request = request

    def _prepare(self) -> _PreparedSourceRequest:
        coordinator = self._coordinator
        profile = coordinator.profile
        source = _source(profile, self._key)
        if source is None or source.control not in profile.boolean_controls:
            raise ValueError("This source is unavailable")
        presentation = coordinator.native_presentation_profile
        modes = source_color_modes(_source(presentation, self._key), presentation)
        values = self._request
        segments = list(source.segments)
        brightness_packet = None
        if (brightness := values.brightness_pct) is not None:
            if modes == {"onoff"}:
                raise ValueError("This source does not support brightness")
            if source.native_control:
                build_source_value(source.key, "brightness", brightness, profile)
            elif source.master_brightness:
                brightness_packet = build_brightness(brightness, coordinator.model, profile=profile)
                require_profile_packet(brightness_packet, profile)
            else:
                build_segment_brightness(segments, brightness, coordinator.model, profile=profile)
        if values.rgb_color is not None and "rgb" not in modes:
            raise ValueError("This source does not support RGB")
        kelvin = values.kelvin
        if kelvin is not None and source.native_control:
            if type(kelvin) is not int or not profile.min_color_temp_kelvin <= kelvin <= profile.max_color_temp_kelvin:
                raise ValueError("Source Kelvin is outside the profile")
            values = replace(values, kelvin=normalize_kelvin(kelvin, profile))
        if kelvin is not None and "color_temp" not in modes:
            raise ValueError("This source does not support colour temperature")
        colour = (
            prepare_source_colour(coordinator, (source.key,), values)
            if values.rgb_color is not None or values.kelvin is not None
            else None
        )
        return _PreparedSourceRequest(profile, source, values, brightness_packet, colour)

    @contextmanager
    def _track_write(
        self, field: str, guard: Callable[[], None], *, refresh_revision: bool = False
    ) -> Generator[Callable[[], None]]:
        coordinator = self._coordinator
        attempts = coordinator.control_write_attempts
        revision = coordinator._field_revisions.get(field, 0)

        def before_write() -> None:
            nonlocal revision
            guard()
            if refresh_revision:
                revision = coordinator._field_revisions.get(field, 0)

        try:
            yield before_write
        except BaseException:
            if (
                coordinator.control_write_attempts != attempts
                and coordinator._field_revisions.get(field, 0) <= revision
            ):
                coordinator._h607c_uncertain_state_fields.add(field)
                coordinator._expected_state.pop(field, None)
                coordinator.async_set_updated_data(coordinator.data or {})
            raise

    async def _ensure_power(self, prepared: _PreparedSourceRequest, guard: Callable[[], None]) -> None:
        coordinator, profile, source = self._coordinator, prepared.profile, prepared.source
        if profile.can_read(ReadDomain.POWER) and (
            not source_field_fresh(coordinator, "is_on") or "is_on" in coordinator._h607c_uncertain_state_fields
        ):
            revision = coordinator._field_revisions.get("is_on", 0)
            if not await coordinator.refresh_state(
                RefreshRequest(refresh_all=True, query_segments=False, required_domains=frozenset({ReadDomain.POWER}))
            ) or (
                not source_field_fresh(coordinator, "is_on")
                or coordinator._field_revisions.get("is_on", 0) <= revision
                or "is_on" in coordinator._h607c_uncertain_state_fields
            ):
                raise ValueError("The device did not provide fresh master power")
            guard()
        master_off = coordinator.is_on is not True or "is_on" in coordinator._h607c_uncertain_state_fields
        await coordinator.async_validate_source_power(source.control, True)
        if master_off:
            for sibling in profile.light_sources:
                if (
                    not profile.minimum_enabled_sources
                    and sibling.key != source.key
                    and (
                        coordinator.boolean_control_state.get(sibling.control) is not False
                        or not source_field_fresh(coordinator, f"boolean_{sibling.control}")
                    )
                ):
                    guard()
                    await coordinator.async_set_boolean_control(sibling.control, False)
            with self._track_write("is_on", guard, refresh_revision=True) as power_guard:
                await coordinator.send_command(
                    build_power(True, coordinator.model, profile=profile), write_guard=power_guard
                )
                if profile.can_read(ReadDomain.POWER) and not await coordinator.refresh_state(RefreshRequest(on=True)):
                    raise ValueError("The device did not confirm master power")
        if (
            master_off
            or coordinator.boolean_control_state.get(source.control) is not True
            or not source_field_fresh(coordinator, f"boolean_{source.control}")
        ):
            guard()
            await coordinator.async_set_boolean_control(source.control, True)

    async def _apply_values(self, prepared: _PreparedSourceRequest, guard: Callable[[], None]) -> None:
        coordinator, source, values = self._coordinator, prepared.source, prepared.values
        if values.brightness_pct is None and prepared.colour is None:
            return
        needs_segments = values.rgb_color is not None or (
            not source.native_control
            and (
                prepared.colour is not None or values.brightness_pct is not None and prepared.brightness_packet is None
            )
        )
        async with coordinator.async_mask_transaction() if needs_segments else nullcontext():
            guard()
            segments = list(source.segments)
            if values.brightness_pct is not None:
                if source.native_control:
                    await coordinator.async_set_source_value(source.key, "brightness", values.brightness_pct)
                elif prepared.brightness_packet is not None:
                    with self._track_write("brightness_pct", guard) as brightness_guard:
                        await coordinator.send_command(prepared.brightness_packet, write_guard=brightness_guard)
                else:
                    await coordinator.async_set_segment_brightness(segments, values.brightness_pct, write_guard=guard)
            if prepared.colour is not None:
                await prepared.colour.apply(coordinator, guard)

    async def run(self) -> None:
        coordinator = self._coordinator
        partial = False
        try:
            prepared = self._prepare()
            identity_guard = (
                await coordinator.async_prepare_identity_gated_control()
                if coordinator.identity_gated_controls
                else None
            )

            def guard() -> None:
                if identity_guard is not None:
                    identity_guard()
                if coordinator.profile is not prepared.profile and coordinator.profile != prepared.profile:
                    raise ValueError("The device profile changed")

            await coordinator._async_supersede_effect_preview()
            async with async_control_intent(coordinator, ControlIntent.USER):
                attempts = coordinator.control_write_attempts
                try:
                    guard()
                    await self._ensure_power(prepared, guard)
                    await self._apply_values(prepared, guard)
                finally:
                    partial = coordinator.control_write_attempts != attempts
            coordinator.async_set_updated_data(coordinator.data or {})
        except Exception as error:
            if isinstance(error, HomeAssistantError) and not partial:
                raise
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="partial_command" if partial else "device_command_failed"
            ) from error
