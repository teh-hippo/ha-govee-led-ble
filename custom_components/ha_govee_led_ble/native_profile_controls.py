"""Coordinator-native writers for music and video profile settings."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

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


async def apply_video_mode_from_state(
    coordinator: GoveeBLECoordinator,
    *,
    writer: Callable[[bytes], Awaitable[None]] | None = None,
) -> None:
    sound_effects = coordinator.video_sound_effects and coordinator.profile.supports_video_sound_effects
    send = coordinator.send_command if writer is None else writer
    await send(
        build_video_mode(
            coordinator.video_mode,
            coordinator.video_full_screen,
            coordinator.video_saturation,
            sound_effects,
            coordinator.video_sound_effects_softness,
            coordinator.model,
        )
    )
    if not coordinator.profile.supports_video_sound_effects:
        coordinator.video_sound_effects = False


async def apply_active_video_mode(
    coordinator: GoveeBLECoordinator,
    *,
    writer: Callable[[bytes], Awaitable[None]] | None = None,
    verify: bool = True,
    requested_fields: frozenset[str] | None = None,
) -> bool:
    if coordinator.video_mode not in ("movie", "game"):
        return False
    if requested_fields is not None:
        require_video_controls(
            coordinator.profile,
            coordinator,
            {
                "capture_region"
                if field == "full_screen"
                else "sound_effects"
                if field == "sound_effects_softness"
                else field
                for field in requested_fields
            },
        )
    send = coordinator.send_command if writer is None else writer
    for _ in range(2 if verify else 1):
        if not coordinator.is_on:
            await send(build_power(True, coordinator.model))
            coordinator.is_on = True
        await apply_video_mode_from_state(
            coordinator,
            writer=send,
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


async def apply_white_balance(
    coordinator: GoveeBLECoordinator,
    *,
    writer: Callable[[bytes], Awaitable[None]] | None = None,
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
    send = coordinator.send_command if writer is None else writer
    for _ in range(2 if verify else 1):
        if verify:
            coordinator._arm_expected_values(fields)
        await send(packet)
        if not verify:
            return True
        if await coordinator.refresh_state(expected_white_balance=expected):
            return True
    raise RuntimeError("White-balance write was not confirmed by the device")


async def apply_relative_brightness(
    coordinator: GoveeBLECoordinator,
    *,
    writer: Callable[[bytes], Awaitable[None]] | None = None,
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
    send = coordinator.send_command if writer is None else writer
    for _ in range(2 if verify else 1):
        if verify:
            coordinator._arm_expected_values(fields)
        await send(packet)
        if not verify:
            return True
        if await coordinator.refresh_state(expected_relative_brightness=expected):
            return True
    raise RuntimeError("Relative-brightness write was not confirmed by the device")


async def apply_blank_screen(
    coordinator: GoveeBLECoordinator,
    *,
    writer: Callable[[bytes], Awaitable[None]] | None = None,
    verify: bool = True,
) -> bool:
    require_video_controls(coordinator.profile, coordinator, ("blank_screen",))
    expected = bool(coordinator.blank_screen)
    detection = coordinator.blank_screen_detection
    low_duration = coordinator.blank_screen_low_brightness_duration_seconds
    same_duration = coordinator.blank_screen_same_tone_duration_seconds
    if detection is None or low_duration is None or same_duration is None:
        raise ValueError("Blank-screen policy state has not been read; refresh the device first")
    send = coordinator.send_command if writer is None else writer
    for _ in range(2 if verify else 1):
        if verify:
            coordinator._arm_expected_values({"blank_screen": expected})
        await send(build_blank_screen(expected, coordinator.model, detection, low_duration, same_duration))
        if not verify:
            return True
        if await coordinator.refresh_state(expected_blank_screen=expected):
            return True
    raise RuntimeError("Blank-screen write was not confirmed by the device")
