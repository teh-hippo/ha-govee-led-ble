"""Owned native projector appearance writes and independently qualified readback."""

from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN, ReadDomain, same_control_profile
from .control_arbiter import ControlIntent, async_control_intent
from .coordinator_refresh import STATE_QUERY_TIMEOUT, RefreshRequest
from .generated_protocol_adapter import BulkStatusCollector, build_brightness, build_power, require_profile_packet
from .projector import ProjectorAppearance, ProjectorControl, ProjectorStars
from .projector_protocol import build_appearance, build_appearance_query, decode_appearance

if TYPE_CHECKING:
    from .const import ModelProfile
    from .coordinator import GoveeBLECoordinator
    from .coordinator_sources import SourceTurnOnRequest

_CONTROL_FIELDS = {
    ProjectorControl.AURORA_MOVEMENT: (None, "movement_speed"),
    ProjectorControl.AURORA_EFFECT_SPEED: (None, "effect_speed"),
    ProjectorControl.AURORA_PATTERN: (None, "pattern"),
    ProjectorControl.STAR_FLICKER: ("stars", "flicker_enabled"),
    ProjectorControl.STAR_FLICKER_SPEED: ("stars", "flicker_speed"),
    ProjectorControl.STAR_MOVEMENT: ("stars", "movement_enabled"),
    ProjectorControl.STAR_MOVEMENT_SPEED: ("stars", "movement_speed"),
}


def control_value(coordinator: GoveeBLECoordinator, control: ProjectorControl) -> int | bool | None:
    value = current_appearance(coordinator)
    if value is None:
        return None
    group, field = _CONTROL_FIELDS[control]
    selected = getattr(value.stars if group else value, field)
    return selected if isinstance(selected, int | bool) else None


async def required_appearance(coordinator: GoveeBLECoordinator) -> ProjectorAppearance:
    value = current_appearance(coordinator)
    if value is None and coordinator.projector_appearance is not None:
        await prepare_baseline(coordinator)
        value = current_appearance(coordinator)
    if value is None and coordinator._pre_mode_snapshot is not None:
        async with coordinator._async_qualified_static_history():
            value = coordinator.require_static_baseline().projector_appearance
    if value is None and qualified_profile(coordinator).projector_control_revision == 0:
        value = await read_appearance(coordinator)
    if value is None:
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="recovery_not_ready")
    return value


async def set_control(coordinator: GoveeBLECoordinator, control: ProjectorControl, selected: int | bool) -> None:
    group, field = _CONTROL_FIELDS[control]
    if field.endswith("enabled"):
        if type(selected) is not bool:
            raise ValueError("Projector switch requires a boolean")
    elif type(selected) is not int or not (1 if field == "pattern" else 0) <= selected <= (
        4 if field == "pattern" else 100
    ):
        raise ValueError("Projector level is outside its bounds")
    async with async_control_intent(coordinator, ControlIntent.USER):
        async with coordinator._lock:
            client = await coordinator._ensure_connected()
            await coordinator._async_confirm_pact(client)
            qualified_profile(coordinator)
        value = await required_appearance(coordinator)
        changes: dict[str, Any] = {field: selected}
        updated = replace(value, stars=replace(value.stars, **changes)) if group else replace(value, **changes)
        await apply_appearance(coordinator, updated)


def current_appearance(coordinator: GoveeBLECoordinator) -> ProjectorAppearance | None:
    return (
        coordinator.projector_appearance
        if coordinator.projector_mode_active
        and coordinator._projector_token is coordinator._notification_token
        and coordinator._notification_token is not None
        and coordinator._projector_generation == coordinator._profile_generation
        else None
    )


def source_state(
    coordinator: GoveeBLECoordinator, key: str
) -> tuple[bool | None, int | None, tuple[int, int, int] | None]:
    if key not in {source.key for source in coordinator.profile.light_sources}:
        return None, None, None
    if not coordinator.is_on:
        return (
            (False, None, None)
            if coordinator._power_known or coordinator.source_field_fresh("is_on")
            else (None, None, None)
        )
    value = current_appearance(coordinator)
    if value is None and coordinator.projector_mode_active and coordinator._projector_profile is not None:
        if same_control_profile(coordinator._projector_profile, coordinator.profile):
            value = coordinator.projector_appearance
    if value is None:
        return None, None, None
    if key == "stars":
        return value.stars.enabled, value.stars.brightness, None
    if key == "coarse_aurora":
        return value.enabled and value.coarse_enabled, None, None
    if key == "fine_aurora":
        return value.enabled and value.fine_enabled, None, None
    colours = (*value.coarse, *(value.fine or ()))
    return value.enabled, value.brightness, colours[0] if colours and len(set(colours)) == 1 else None


def qualified_profile(coordinator: GoveeBLECoordinator) -> ModelProfile:
    coordinator._reconcile_authorization()
    if (
        coordinator.profile.projector_grammar != "H6093"
        or coordinator.profile.projector_control_revision is None
        or coordinator._h607c_pact_conflict
        or not coordinator.identity_fields_confirmed(frozenset({"pact"}))
    ):
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="recovery_not_ready")
    return coordinator.profile


def install_appearance(coordinator: GoveeBLECoordinator, value: ProjectorAppearance, *, observed: bool) -> None:
    coordinator.projector_appearance = value
    coordinator.projector_mode_active = True
    coordinator._projector_token = coordinator._notification_token
    coordinator._projector_generation = coordinator._profile_generation
    coordinator._projector_profile = coordinator.profile
    coordinator.projector_appearance_observed = observed
    coordinator._static_colour_known = True
    coordinator._static_rgb_known = False
    coordinator.color_temp_kelvin = None
    coordinator.color_temp_unknown = False
    if observed:
        coordinator._mark_received(ReadDomain.OTHER, "projector_appearance")


def invalidate_appearance(coordinator: GoveeBLECoordinator, *, retain: bool = False) -> None:
    if not retain:
        coordinator.projector_appearance = None
        coordinator._projector_profile = None
    coordinator._projector_token = None
    coordinator.projector_appearance_observed = False
    collector = coordinator._projector_collector
    if collector is not None and not collector.complete:
        coordinator._bulk_query_incomplete = True
    pending = coordinator._projector_reply
    if pending is not None and not pending.done():
        pending.set_exception(ValueError("Projector appearance authority changed"))
    coordinator._projector_collector = None


def handle_reply(coordinator: GoveeBLECoordinator, frame: bytes) -> bool:
    collector, pending = coordinator._projector_collector, coordinator._projector_reply
    if collector is None or pending is None or pending.done() or frame[:1] != b"\xac":
        return False
    result = collector.feed(frame)
    if result.rejection is not None:
        pending.set_exception(ValueError("Invalid projector appearance reply"))
    elif result.parsed is not None:
        try:
            pending.set_result(decode_appearance(result.parsed.records[0].body))
        except ValueError, TypeError, AttributeError:
            pending.set_exception(ValueError("Invalid projector appearance reply"))
    return True


async def read_appearance(coordinator: GoveeBLECoordinator) -> ProjectorAppearance:
    async with coordinator._lock:
        client = await coordinator._ensure_connected()
        await coordinator._async_confirm_pact(client)
        profile = qualified_profile(coordinator)
        query = build_appearance_query(profile)
        token, generation = coordinator._notification_token, coordinator._profile_generation
        deadline = time.monotonic() + STATE_QUERY_TIMEOUT
        pending: asyncio.Future[ProjectorAppearance] = asyncio.get_running_loop().create_future()
        coordinator._projector_reply = pending
        coordinator._projector_collector = BulkStatusCollector("H6093")

        def guard() -> None:
            if (
                qualified_profile(coordinator) != profile
                or coordinator._notification_token is not token
                or coordinator._profile_generation != generation
            ):
                raise ValueError("Projector appearance authority changed")

        try:
            async with asyncio.timeout_at(deadline):
                await coordinator._async_write_packet(client, query, before_write=guard, cleanup_deadline=deadline)
                value = await pending
            guard()
            if coordinator.projector_mode_active:
                install_appearance(coordinator, value, observed=True)
            return value
        finally:
            collector = coordinator._projector_collector
            if collector is not None and not collector.complete:
                coordinator._bulk_query_incomplete = True
            coordinator._projector_collector = None
            coordinator._projector_reply = None
            if not pending.done():
                pending.cancel()
            elif not pending.cancelled():
                pending.exception()


async def apply_appearance(
    coordinator: GoveeBLECoordinator,
    value: ProjectorAppearance,
    *,
    turn_on: bool = False,
    master_brightness: int | None = None,
) -> None:
    value.__post_init__()
    async with async_control_intent(coordinator, ControlIntent.USER), coordinator.async_mode_transition():
        async with coordinator._lock:
            client = await coordinator._ensure_connected()
            await coordinator._async_confirm_pact(client)
            profile = qualified_profile(coordinator)
        appearance_packets = build_appearance(value, profile)
        packets = (
            *((build_power(True, coordinator.model),) if turn_on else ()),
            *((build_brightness(master_brightness, coordinator.model),) if master_brightness is not None else ()),
            *appearance_packets,
        )
        for packet in packets:
            require_profile_packet(packet, profile)
        token, generation = coordinator._notification_token, coordinator._profile_generation
        first_upload = len(packets) - len(appearance_packets)

        def guard() -> None:
            if (
                qualified_profile(coordinator) != profile
                or coordinator._notification_token is not token
                or coordinator._profile_generation != generation
            ):
                raise ValueError("Projector appearance authority changed")

        def attempted(index: int) -> None:
            if index == first_upload:
                coordinator.projector_appearance = None
                coordinator.projector_appearance_observed = False

        try:
            await coordinator.async_write_effect_sequence(
                packets,
                intent=ControlIntent.USER,
                write_guard=guard,
                packet_on_write=attempted,
                require_upload_ack=True,
                upload_ack_index=len(packets) - 2,
                retry_allowed=lambda: False,
            )
            guard()
            install_appearance(coordinator, value, observed=False)
        except BaseException:
            coordinator.projector_appearance = None
            coordinator.projector_appearance_observed = False
            raise
        coordinator.async_set_updated_data(coordinator.data or {})


async def initialise(coordinator: GoveeBLECoordinator) -> None:
    async with async_control_intent(coordinator, ControlIntent.USER):
        async with coordinator._lock:
            client = await coordinator._ensure_connected()
            await coordinator._async_confirm_pact(client)
            profile = qualified_profile(coordinator)
        value = ProjectorAppearance(
            ProjectorStars(True, 50, False, 50, False, 50),
            True,
            0,
            100,
            4,
            0,
            ((0, 0, 255),),
            ((0, 0, 255),) if profile.projector_control_revision else None,
        )
        await apply_appearance(coordinator, value, turn_on=True, master_brightness=100)


async def source_request(
    coordinator: GoveeBLECoordinator, key: str, enabled: bool, request: SourceTurnOnRequest | None = None
) -> None:
    async with async_control_intent(coordinator, ControlIntent.USER):
        async with coordinator._lock:
            client = await coordinator._ensure_connected()
            await coordinator._async_confirm_pact(client)
            profile = qualified_profile(coordinator)
        if key not in {source.key for source in profile.light_sources}:
            raise ValueError("Projector source is unavailable")
        value = await required_appearance(coordinator)
        if request is not None and request.kelvin is not None:
            raise ValueError("Projector source colour temperature is unavailable")
        if key == "stars":
            if request is not None and request.rgb_color is not None:
                raise ValueError("Star colour is fixed")
            value = replace(
                value,
                stars=replace(
                    value.stars,
                    enabled=enabled,
                    brightness=request.brightness_pct
                    if request is not None and request.brightness_pct is not None
                    else value.stars.brightness,
                ),
            )
        else:
            if (
                key != "aurora"
                and request is not None
                and (request.brightness_pct is not None or request.rgb_color is not None)
            ):
                raise ValueError("Pattern sources have shared aurora attributes")
            colour = request.rgb_color if request is not None else None
            brightness = request.brightness_pct if request is not None else None
            enabling_pattern = enabled and key in {"coarse_aurora", "fine_aurora"}
            value = replace(
                value,
                enabled=enabled if key == "aurora" else True if enabled else value.enabled,
                coarse_enabled=(
                    enabled
                    if key == "coarse_aurora"
                    else value.coarse_enabled and (value.enabled or not enabling_pattern)
                ),
                fine_enabled=(
                    enabled if key == "fine_aurora" else value.fine_enabled and (value.enabled or not enabling_pattern)
                ),
                brightness=value.brightness if brightness is None else brightness,
                coarse=value.coarse if colour is None else (colour,),
                fine=value.fine if colour is None or value.fine is None else (colour,),
            )
        await apply_appearance(coordinator, value, turn_on=enabled)


async def prepare_baseline(coordinator: GoveeBLECoordinator) -> None:
    async with coordinator._lock:
        client = await coordinator._ensure_connected()
        await coordinator._async_confirm_pact(client)
    profile = qualified_profile(coordinator)
    retained = coordinator.projector_appearance
    retained_profile = coordinator._projector_profile
    if profile.projector_control_revision == 0:
        await read_appearance(coordinator)
    refreshed = await coordinator.refresh_state(
        RefreshRequest(
            query_native_settings=False,
            query_segments=False,
            required_domains=frozenset({ReadDomain.POWER, ReadDomain.BRIGHTNESS, ReadDomain.COLOUR_MODE}),
        )
    )
    if (
        refreshed is True
        and current_appearance(coordinator) is None
        and coordinator.projector_mode_active
        and retained is not None
        and retained_profile is not None
        and same_control_profile(retained_profile, coordinator.profile)
    ):
        install_appearance(coordinator, retained, observed=False)
    if refreshed is not True or current_appearance(coordinator) is None:
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="recovery_not_ready")
