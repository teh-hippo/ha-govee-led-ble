"""Coordinator-native writers for music and video profile settings."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import TYPE_CHECKING, Any, Protocol

from .control_arbiter import ControlIntent
from .generated_protocol_adapter import (
    build_blank_screen,
    build_power,
    build_relative_brightness,
    build_video_mode,
    build_white_balance,
)
from .video_applicability import require_video_controls

if TYPE_CHECKING:
    from .coordinator import GoveeBLECoordinator


class ProfileWriter(Protocol):
    """A custom writer must run the guard at its final physical-write boundary."""

    def __call__(self, packet: bytes, *, write_guard: Callable[[], None] | None = None) -> Awaitable[None]: ...


async def apply_video_mode_from_state(
    coordinator: GoveeBLECoordinator,
    *,
    writer: ProfileWriter | None = None,
    requested_fields: frozenset[str] | None = None,
) -> None:
    fields = (
        requested_fields
        if requested_fields is not None
        else frozenset(
            field
            for field, supported in (
                ("full_screen", coordinator.profile.supports_video_capture_region),
                ("saturation", coordinator.profile.supports_video_saturation),
                ("sound_effects", coordinator.profile.supports_video_sound_effects),
                ("sound_effects_softness", coordinator.profile.supports_video_sound_effects),
            )
            if supported
        )
    )
    controls = frozenset(
        "capture_region" if field == "full_screen" else "sound_effects" if field == "sound_effects_softness" else field
        for field in fields
    )
    retained = {
        field: getattr(coordinator, f"video_{field}")
        for field, supported in (
            ("full_screen", coordinator.profile.supports_video_capture_region),
            ("saturation", coordinator.profile.supports_video_saturation),
            ("sound_effects", coordinator.profile.supports_video_sound_effects),
            ("sound_effects_softness", coordinator.profile.supports_video_sound_effects),
        )
        if field not in fields and supported
    }

    def check_retained() -> None:
        if any(getattr(coordinator, f"video_{field}") != value for field, value in retained.items()):
            raise ValueError("Retained video settings changed before write; refresh and retry")

    sound_effects = coordinator.video_sound_effects and coordinator.profile.supports_video_sound_effects
    await _send_video_setting(
        coordinator,
        build_video_mode(
            coordinator.video_mode,
            coordinator.video_full_screen,
            coordinator.video_saturation,
            sound_effects,
            coordinator.video_sound_effects_softness,
            coordinator.model,
        ),
        controls,
        writer=writer,
        write_guard=check_retained if retained else None,
    )
    if not coordinator.profile.supports_video_sound_effects:
        coordinator.video_sound_effects = False


async def apply_active_video_mode(
    coordinator: GoveeBLECoordinator,
    *,
    writer: ProfileWriter | None = None,
    verify: bool = True,
    requested_fields: frozenset[str] | None = None,
) -> bool:
    if coordinator.video_mode not in ("movie", "game"):
        return False
    if requested_fields is None:
        requested_fields = frozenset(
            field
            for field, supported in (
                ("full_screen", coordinator.profile.supports_video_capture_region),
                ("saturation", coordinator.profile.supports_video_saturation),
                ("sound_effects", coordinator.profile.supports_video_sound_effects),
                ("sound_effects_softness", coordinator.profile.supports_video_sound_effects),
            )
            if supported
        )
    controls = frozenset(
        "capture_region" if field == "full_screen" else "sound_effects" if field == "sound_effects_softness" else field
        for field in requested_fields
    )
    for _ in range(2 if verify else 1):
        require_video_controls(coordinator.profile, coordinator, controls)
        if not coordinator.is_on:
            await _send_video_setting(coordinator, build_power(True, coordinator.model), controls, writer=writer)
            coordinator.is_on = True
        await apply_video_mode_from_state(
            coordinator,
            writer=writer,
            requested_fields=requested_fields,
        )
        if not verify:
            return True
        if await coordinator.refresh_state(
            expected_on=True,
            expected_video_mode=coordinator.video_mode,
            expected_video_full_screen=(
                coordinator.video_full_screen
                if coordinator.profile.supports_video_capture_region
                and (requested_fields is None or "full_screen" in requested_fields)
                else None
            ),
            expected_video_saturation=(
                coordinator.video_saturation
                if coordinator.profile.supports_video_saturation
                and (requested_fields is None or "saturation" in requested_fields)
                else None
            ),
            expected_video_sound_effects=(
                coordinator.video_sound_effects
                if coordinator.profile.supports_video_sound_effects
                and (requested_fields is None or "sound_effects" in requested_fields)
                else None
            ),
            expected_video_sound_effects_softness=(
                coordinator.video_sound_effects_softness
                if coordinator.profile.supports_video_sound_effects
                and (requested_fields is None or "sound_effects_softness" in requested_fields)
                else None
            ),
        ):
            return True
    raise RuntimeError("Video-mode write was not confirmed by the device")


async def _send_video_setting(
    coordinator: GoveeBLECoordinator,
    packet: bytes,
    controls: frozenset[str],
    *,
    writer: ProfileWriter | None,
    write_guard: Callable[[], None] | None = None,
    expected_values: Mapping[str, Any] | None = None,
) -> None:
    def check() -> None:
        require_video_controls(coordinator.profile, coordinator, controls)
        if write_guard is not None:
            write_guard()

    check()

    def before_write() -> None:
        check()
        if expected_values is not None:
            coordinator._arm_expected_values(dict(expected_values))

    if writer is None and (
        write_guard is not None
        or expected_values is not None
        or any(condition.control in controls for condition in coordinator.profile.video_firmware_conditions)
    ):
        # The sequence callback runs under the transport lock after every reconnect.
        await coordinator.async_write_effect_sequence(
            (packet,),
            intent=coordinator._control_arbiter.current_task_intent or ControlIntent.USER,
            write_guard=before_write,
        )
    elif writer is not None:
        await writer(packet, write_guard=before_write)
    else:
        await coordinator.send_command(packet)


async def apply_white_balance(
    coordinator: GoveeBLECoordinator,
    *,
    writer: ProfileWriter | None = None,
    verify: bool = True,
) -> bool:
    require_video_controls(coordinator.profile, coordinator, ("white_balance",))
    scalar = coordinator.profile.video_white_balance_representation == "scalar"
    if scalar and coordinator.white_balance_scalar is None:
        raise ValueError("Scalar white balance has not been read")
    expected: tuple[int, ...]
    if scalar:
        assert coordinator.white_balance_scalar is not None
        expected = (coordinator.white_balance_scalar,)
    else:
        expected = coordinator.white_balance
    fields = dict(
        zip(("white_balance_scalar",) if scalar else ("white_balance_red", "white_balance_blue"), expected, strict=True)
    )
    packet = build_white_balance(expected[0], expected[-1] if len(expected) == 2 else None, coordinator.model)
    for _ in range(2 if verify else 1):
        await _send_video_setting(
            coordinator, packet, frozenset({"white_balance"}), writer=writer, expected_values=fields if verify else None
        )
        if not verify:
            return True
        if await coordinator.refresh_state(expected_white_balance=expected):
            return True
    raise RuntimeError("White-balance write was not confirmed by the device")


async def apply_relative_brightness(
    coordinator: GoveeBLECoordinator,
    *,
    writer: ProfileWriter | None = None,
    verify: bool = True,
) -> bool:
    require_video_controls(coordinator.profile, coordinator, ("relative_brightness",))
    zones = coordinator.profile.video_brightness_zones
    values = tuple(getattr(coordinator, f"relative_brightness_{edge}") for edge in zones)
    if any(value is None for value in values):
        raise ValueError("Relative-brightness edge state has not been read; set all edges first")
    expected = tuple(int(value) for value in values)
    fields: dict[str, int | None] = {
        f"relative_brightness_{zone}": value for zone, value in zip(zones, expected, strict=True)
    }
    fields["relative_brightness"] = expected[0] if len(set(expected)) == 1 else None
    packet = build_relative_brightness(
        expected[0],
        expected[1],
        expected[2],
        expected[3],
        coordinator.model,
        expected[4] if len(expected) == 6 else None,
        expected[5] if len(expected) == 6 else None,
    )
    for _ in range(2 if verify else 1):
        await _send_video_setting(
            coordinator,
            packet,
            frozenset({"relative_brightness"}),
            writer=writer,
            expected_values=fields if verify else None,
        )
        if not verify:
            return True
        if await coordinator.refresh_state(expected_relative_brightness=expected):
            return True
    raise RuntimeError("Relative-brightness write was not confirmed by the device")


async def apply_blank_screen(
    coordinator: GoveeBLECoordinator,
    *,
    writer: ProfileWriter | None = None,
    verify: bool = True,
) -> bool:
    require_video_controls(coordinator.profile, coordinator, ("blank_screen",))
    expected = bool(coordinator.blank_screen)
    detection = coordinator.blank_screen_detection
    low_duration = coordinator.blank_screen_low_brightness_duration_seconds
    same_duration = coordinator.blank_screen_same_tone_duration_seconds
    if detection is None or low_duration is None or same_duration is None:
        raise ValueError("Blank-screen policy state has not been read; refresh the device first")
    for _ in range(2 if verify else 1):
        await _send_video_setting(
            coordinator,
            build_blank_screen(expected, coordinator.model, detection, low_duration, same_duration),
            frozenset({"blank_screen"}),
            writer=writer,
            expected_values={"blank_screen": expected} if verify else None,
        )
        if not verify:
            return True
        if await coordinator.refresh_state(expected_blank_screen=expected):
            return True
    raise RuntimeError("Blank-screen write was not confirmed by the device")
