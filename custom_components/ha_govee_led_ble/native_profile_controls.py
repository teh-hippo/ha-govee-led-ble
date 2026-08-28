"""Coordinator-native writers for music and video profile settings."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from .generated_protocol_adapter import (
    build_h6199_blank_screen,
    build_h6199_relative_brightness,
    build_h6199_video,
    build_h6199_white_balance,
    build_power,
)

if TYPE_CHECKING:
    from .coordinator import GoveeBLECoordinator


async def apply_video_mode_from_state(
    coordinator: GoveeBLECoordinator,
    *,
    game_mode: bool,
    writer: Callable[[bytes], Awaitable[None]] | None = None,
) -> None:
    sound_effects = coordinator.video_sound_effects and coordinator.profile.supports_video_sound_effects
    send = coordinator.send_command if writer is None else writer
    await send(
        build_h6199_video(
            coordinator.video_full_screen,
            game_mode,
            coordinator.video_saturation,
            sound_effects,
            coordinator.video_sound_effects_softness,
        )
    )
    if not coordinator.profile.supports_video_sound_effects:
        coordinator.video_sound_effects = False


async def apply_active_video_mode(
    coordinator: GoveeBLECoordinator,
    *,
    writer: Callable[[bytes], Awaitable[None]] | None = None,
    verify: bool = True,
) -> bool:
    if coordinator.video_mode not in ("movie", "game"):
        return False
    send = coordinator.send_command if writer is None else writer
    for _ in range(2 if verify else 1):
        if not coordinator.is_on:
            await send(build_power(True, coordinator.model))
            coordinator.is_on = True
        await apply_video_mode_from_state(
            coordinator,
            game_mode=coordinator.video_mode == "game",
            writer=send,
        )
        if not verify:
            return True
        if await coordinator.refresh_state(
            expected_on=True,
            expected_video_mode=coordinator.video_mode,
            expected_video_full_screen=coordinator.video_full_screen,
            expected_video_saturation=coordinator.video_saturation,
            expected_video_sound_effects=coordinator.video_sound_effects,
            expected_video_sound_effects_softness=coordinator.video_sound_effects_softness,
        ):
            return True
    raise RuntimeError("Video-mode write was not confirmed by the device")


async def apply_white_balance(
    coordinator: GoveeBLECoordinator,
    *,
    writer: Callable[[bytes], Awaitable[None]] | None = None,
    verify: bool = True,
) -> bool:
    expected = coordinator.white_balance
    fields = {"white_balance_red": expected[0], "white_balance_blue": expected[1]}
    send = coordinator.send_command if writer is None else writer
    for _ in range(2 if verify else 1):
        if verify:
            coordinator._arm_expected_values(fields)
        await send(build_h6199_white_balance(*expected))
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
    values = tuple(getattr(coordinator, f"relative_brightness_{edge}") for edge in ("left", "top", "right", "bottom"))
    if any(value is None for value in values):
        raise ValueError("Relative-brightness edge state has not been read; set all edges first")
    left, top, right, bottom = values
    assert left is not None and top is not None and right is not None and bottom is not None
    expected = left, top, right, bottom
    aggregate = left if len(set(expected)) == 1 else None
    fields = {
        "relative_brightness": aggregate,
        "relative_brightness_left": left,
        "relative_brightness_top": top,
        "relative_brightness_right": right,
        "relative_brightness_bottom": bottom,
    }
    send = coordinator.send_command if writer is None else writer
    for _ in range(2 if verify else 1):
        if verify:
            coordinator._arm_expected_values(fields)
        await send(build_h6199_relative_brightness(*expected))
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
        await send(build_h6199_blank_screen(expected, detection, low_duration, same_duration))
        if not verify:
            return True
        if await coordinator.refresh_state(expected_blank_screen=expected):
            return True
    raise RuntimeError("Blank-screen write was not confirmed by the device")
