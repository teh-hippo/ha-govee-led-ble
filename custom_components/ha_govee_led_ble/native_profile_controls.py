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
from .video_settings import VIDEO_DEFAULT_PRESET

if TYPE_CHECKING:
    from .coordinator import GoveeBLECoordinator


class ProfileWriter(Protocol):
    """Run all guards before installing state and expectations at the physical boundary."""

    def __call__(
        self,
        packet: bytes,
        *,
        write_guard: Callable[[], None] | None = None,
        state_values: Mapping[str, Any] | None = None,
        expected_values: Mapping[str, Any] | None = None,
    ) -> Awaitable[None]: ...


async def apply_active_video_mode(
    coordinator: GoveeBLECoordinator,
    *,
    mode: str,
    requested_values: Mapping[str, Any],
    writer: ProfileWriter | None = None,
    verify: bool = True,
) -> bool:
    if mode not in ("movie", "game"):
        return False
    requested_values = dict(requested_values)
    controls = frozenset(
        "capture_region" if field == "full_screen" else "sound_effects" if field == "sound_effects_softness" else field
        for field in requested_values
    )
    retained = {
        field: getattr(coordinator, f"video_{field}")
        for field, supported in (
            ("full_screen", coordinator.profile.supports_video_capture_region),
            ("saturation", coordinator.profile.supports_video_saturation),
            ("sound_effects", coordinator.profile.supports_video_sound_effects),
            ("sound_effects_softness", coordinator.profile.supports_video_sound_effects),
        )
        if field not in requested_values and supported
    }
    if coordinator.profile.video_grammar == "H66A0":
        retained.update(
            picture_preset=coordinator.video_picture_preset,
            reserved=coordinator.video_reserved,
        )

    def check_retained() -> None:
        if any(getattr(coordinator, f"video_{field}") != value for field, value in retained.items()):
            raise ValueError("Retained video settings changed before write; refresh and retry")

    values = {
        field: requested_values.get(field, getattr(coordinator, f"video_{field}"))
        for field in ("full_screen", "saturation", "sound_effects", "sound_effects_softness")
    }
    values["sound_effects"] = values["sound_effects"] and coordinator.profile.supports_video_sound_effects
    if coordinator.profile.video_grammar == "H66A0":
        values["picture_preset"] = coordinator.video_picture_preset or VIDEO_DEFAULT_PRESET
        values["reserved"] = coordinator.video_reserved
    packet = build_video_mode(
        mode,
        values["full_screen"],
        values["saturation"],
        values["sound_effects"],
        values["sound_effects_softness"],
        coordinator.model,
        picture_preset=values.get("picture_preset"),
        reserved=values.get("reserved"),
    )
    state_values = {f"video_{field}": value for field, value in values.items()}
    state_values.update(video_mode=mode, effect=None, music_mode="off", diy_code=None)
    expectations = {f"expected_video_{field}": values[field] for field in requested_values}
    for _ in range(2 if verify else 1):
        require_video_controls(coordinator.profile, coordinator, controls)
        if not coordinator.is_on:
            await _send_video_setting(
                coordinator,
                build_power(True, coordinator.model),
                controls,
                writer=writer,
                write_guard=check_retained,
                state_values={"is_on": True},
            )
        await _send_video_setting(
            coordinator,
            packet,
            controls,
            writer=writer,
            write_guard=check_retained,
            state_values=state_values,
        )
        if not verify:
            return True
        if await coordinator.refresh_state(
            expected_on=True,
            expected_video_mode=mode,
            **expectations,
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
    state_values: Mapping[str, Any] | None = None,
    expected_values: Mapping[str, Any] | None = None,
) -> None:
    def check() -> None:
        require_video_controls(coordinator.profile, coordinator, controls)
        if write_guard is not None:
            write_guard()

    check()

    if writer is None:
        # The sequence callback runs under the transport lock after every reconnect.
        await coordinator.async_write_effect_sequence(
            (packet,),
            intent=coordinator._control_arbiter.current_task_intent or ControlIntent.USER,
            write_guard=check,
            state_values=state_values,
            expected_values=expected_values,
        )
    else:
        await writer(packet, write_guard=check, state_values=state_values, expected_values=expected_values)


async def apply_white_balance(
    coordinator: GoveeBLECoordinator,
    expected: tuple[int, ...],
    *,
    writer: ProfileWriter | None = None,
    verify: bool = True,
) -> bool:
    require_video_controls(coordinator.profile, coordinator, ("white_balance",))
    scalar = coordinator.profile.video_white_balance_representation == "scalar"
    fields: dict[str, int] = dict(
        zip(("white_balance_scalar",) if scalar else ("white_balance_red", "white_balance_blue"), expected, strict=True)
    )
    packet = build_white_balance(expected[0], expected[-1] if len(expected) == 2 else None, coordinator.model)
    for _ in range(2 if verify else 1):
        await _send_video_setting(
            coordinator,
            packet,
            frozenset({"white_balance"}),
            writer=writer,
            state_values=fields,
            expected_values=fields if verify else None,
        )
        if not verify:
            return True
        if await coordinator.refresh_state(expected_white_balance=expected):
            return True
    raise RuntimeError("White-balance write was not confirmed by the device")


async def apply_relative_brightness(
    coordinator: GoveeBLECoordinator,
    values: tuple[int | None, ...],
    *,
    writer: ProfileWriter | None = None,
    verify: bool = True,
) -> bool:
    require_video_controls(coordinator.profile, coordinator, ("relative_brightness",))
    zones = coordinator.profile.video_brightness_zones
    if any(value is None for value in values):
        raise ValueError("Relative-brightness edge state has not been read; set all edges first")
    expected = tuple(value for value in values if value is not None)
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
            state_values=fields,
            expected_values=fields if verify else None,
        )
        if not verify:
            return True
        if await coordinator.refresh_state(expected_relative_brightness=expected):
            return True
    raise RuntimeError("Relative-brightness write was not confirmed by the device")


async def apply_blank_screen(
    coordinator: GoveeBLECoordinator,
    expected: bool,
    *,
    writer: ProfileWriter | None = None,
    verify: bool = True,
) -> bool:
    require_video_controls(coordinator.profile, coordinator, ("blank_screen",))
    detection = coordinator.blank_screen_detection
    low_duration = coordinator.blank_screen_low_brightness_duration_seconds
    same_duration = coordinator.blank_screen_same_tone_duration_seconds
    if detection is None or low_duration is None or same_duration is None:
        raise ValueError("Blank-screen policy state has not been read; refresh the device first")

    def check_policy() -> None:
        if (
            coordinator.blank_screen_detection,
            coordinator.blank_screen_low_brightness_duration_seconds,
            coordinator.blank_screen_same_tone_duration_seconds,
        ) != (detection, low_duration, same_duration):
            raise ValueError("Blank-screen policy changed before write; refresh and retry")

    packet = build_blank_screen(expected, coordinator.model, detection, low_duration, same_duration)
    for _ in range(2 if verify else 1):
        await _send_video_setting(
            coordinator,
            packet,
            frozenset({"blank_screen"}),
            writer=writer,
            write_guard=check_policy,
            state_values={"blank_screen": expected},
            expected_values={"blank_screen": expected} if verify else None,
        )
        if not verify:
            return True
        if await coordinator.refresh_state(expected_blank_screen=expected):
            return True
    raise RuntimeError("Blank-screen write was not confirmed by the device")
