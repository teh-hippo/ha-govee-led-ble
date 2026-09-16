"""Coordinator-native writers for music and video profile settings."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Mapping
from typing import TYPE_CHECKING, Any, Protocol

from .control_arbiter import ControlIntent, async_control_intent
from .generated_protocol_adapter import (
    build_black_border,
    build_blank_screen,
    build_power,
    build_relative_brightness,
    build_video_mode,
    build_white_balance,
)
from .video_applicability import require_video_controls, video_control_states

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


async def async_require_video_controls(
    coordinator: GoveeBLECoordinator,
    controls: Iterable[str],
    *,
    intent: ControlIntent = ControlIntent.USER,
) -> None:
    """Evaluate identity after an in-flight reconnect relinquishes control."""
    current_intent = coordinator._control_arbiter.current_task_intent
    async with async_control_intent(coordinator, intent if current_intent is None else current_intent):
        require_video_controls(coordinator.profile, coordinator, controls)


def prepare_video_mode(
    coordinator: GoveeBLECoordinator,
    *,
    mode: str,
    requested_values: Mapping[str, Any],
    parameters: Mapping[str, Any] | None = None,
) -> tuple[bytes, dict[str, Any], frozenset[str], Callable[[], None]]:
    """Compile the complete mode before any control side effect, then guard retention."""
    requested_values = dict(requested_values)
    parameters = dict(parameters) if parameters is not None else None
    if requested_values.keys() - {"full_screen", "saturation", "sound_effects", "sound_effects_softness"}:
        raise ValueError("unknown video setting")
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
    retained_parameters = dict(getattr(coordinator, "video_parameters", None) or {})
    resolved_parameters = retained_parameters | dict(parameters or {})
    profile = coordinator.profile
    client = getattr(coordinator, "_client", None)
    token = getattr(coordinator, "_notification_token", None)

    def check_retained() -> None:
        if coordinator.profile != profile:
            raise ValueError("Video profile changed before write; refresh and retry")
        coordinator.profile.validate_video_saturation(values["saturation"])
        if any(getattr(coordinator, f"video_{field}") != value for field, value in retained.items()):
            raise ValueError("Retained video settings changed before write; refresh and retry")
        current = getattr(coordinator, "video_parameters", None) or {}
        if any(
            current.get(field) != value
            for field, value in retained_parameters.items()
            if field not in (parameters or {})
        ):
            raise ValueError("Retained video values changed before write; refresh and retry")
        if retained_parameters.keys() - (parameters or {}).keys() and (
            getattr(coordinator, "_client", None) is not client
            or getattr(coordinator, "_notification_token", None) is not token
        ):
            raise ValueError("Video connection changed before write; refresh and retry")

    values = {
        field: requested_values.get(field, getattr(coordinator, f"video_{field}"))
        for field in ("full_screen", "saturation", "sound_effects", "sound_effects_softness")
    }
    values["sound_effects"] = values["sound_effects"] and coordinator.profile.supports_video_sound_effects
    coordinator.profile.validate_video_saturation(values["saturation"])
    packet = build_video_mode(
        mode,
        values["full_screen"],
        values["saturation"],
        values["sound_effects"],
        values["sound_effects_softness"],
        coordinator.model,
        values=resolved_parameters,
        profile=profile,
    )
    require_video_controls(profile, coordinator, controls)
    if resolved_parameters:
        values["parameters"] = resolved_parameters
    return packet, values, controls, check_retained


async def apply_active_video_mode(
    coordinator: GoveeBLECoordinator,
    *,
    mode: str,
    requested_values: Mapping[str, Any],
    parameters: Mapping[str, Any] | None = None,
    writer: ProfileWriter | None = None,
    verify: bool = True,
) -> bool:
    if mode not in ("movie", "game"):
        return False
    await async_require_video_controls(coordinator, ())
    packet, values, controls, check_retained = prepare_video_mode(
        coordinator, mode=mode, requested_values=requested_values, parameters=parameters
    )
    state_values = {f"video_{field}": value for field, value in values.items()}
    state_values.update(video_mode=mode, effect=None, music_mode="off", diy_code=None)
    observable = video_control_states(coordinator.profile, coordinator)
    expectations = {
        f"expected_video_{field}": values[field]
        for field, control in (
            ("full_screen", "capture_region"),
            ("saturation", "saturation"),
            ("sound_effects", "sound_effects"),
            ("sound_effects_softness", "sound_effects"),
        )
        if observable[control] == "supported"
    }
    if "parameters" in values:
        expectations["expected_video_parameters"] = values["parameters"]
    for _ in range(2 if verify else 1):
        await async_require_video_controls(coordinator, controls)
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

    await async_require_video_controls(coordinator, controls)
    if write_guard is not None:
        write_guard()

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
    expected: tuple[int, ...] | None,
    *,
    writer: ProfileWriter | None = None,
    verify: bool = True,
    flag: int = 1,
) -> bool:
    """Author manual gains, restore an explicit flag, or reset to freshly reported defaults with None."""
    scalar = coordinator.profile.video_white_balance_representation == "scalar"
    reset_fields = ("white_balance_default_flag", "white_balance_default_red", "white_balance_default_blue")
    reset = expected is None
    if reset:
        if scalar:
            raise ValueError("Scalar white balance requires an explicit value")
        await async_require_video_controls(coordinator, ("white_balance",))
        baselines = {field: coordinator._field_revisions.get(field, 0) for field in reset_fields}
        if not await coordinator.refresh_state(refresh_display_settings=frozenset({"white_balance"})) or any(
            coordinator._field_revisions.get(field, 0) <= revision for field, revision in baselines.items()
        ):
            raise ValueError("White-balance defaults have not been read freshly; refresh the device first")
        defaults = tuple(getattr(coordinator, field) for field in reset_fields)
        if any(value is None for value in defaults):
            raise ValueError("White-balance defaults are incomplete")
        flag, red, blue = defaults
        expected = (red, blue)
        client, token = coordinator._client, coordinator._notification_token

    def check_defaults() -> None:
        if reset and (
            tuple(getattr(coordinator, field) for field in reset_fields) != defaults
            or coordinator._client is not client
            or coordinator._notification_token is not token
        ):
            raise ValueError("White-balance defaults changed before reset; refresh and retry")

    assert expected is not None
    fields: dict[str, int] = dict(
        zip(("white_balance_scalar",) if scalar else ("white_balance_red", "white_balance_blue"), expected, strict=True)
    )
    if not scalar:
        fields["white_balance_flag"] = flag
    packet = build_white_balance(
        expected[0], expected[-1] if len(expected) == 2 else None, coordinator.model, flag=flag
    )
    for _ in range(2 if verify else 1):
        await _send_video_setting(
            coordinator,
            packet,
            frozenset({"white_balance"}),
            writer=writer,
            write_guard=check_defaults,
            state_values=fields,
            expected_values=fields if verify else None,
        )
        if not verify:
            return True
        confirmed = (
            await coordinator.refresh_state(expected_white_balance=expected)
            if scalar
            else await coordinator.refresh_state(expected_white_balance=expected, expected_white_balance_flag=flag)
        )
        if confirmed:
            check_defaults()
            return True
    raise RuntimeError("White-balance write was not confirmed by the device")


async def apply_relative_brightness(
    coordinator: GoveeBLECoordinator,
    values: tuple[int | None, ...],
    *,
    writer: ProfileWriter | None = None,
    verify: bool = True,
) -> bool:
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
    policy: tuple[int, int, int] | None = None,
    writer: ProfileWriter | None = None,
    verify: bool = True,
    write_guard: Callable[[], None] | None = None,
) -> bool:
    if policy is None:
        await async_require_video_controls(coordinator, ("blank_screen",))
        baselines = {
            field: coordinator._field_revisions.get(field, 0)
            for field in (
                "blank_screen_detection",
                "blank_screen_low_brightness_duration_seconds",
                "blank_screen_same_tone_duration_seconds",
            )
        }
        # Refresh owns its transport lock and inherits the caller's control intent.
        # Never refresh inside the synchronous physical-write guard.
        if not await coordinator.refresh_state(refresh_display_settings=frozenset({"blank_screen"})) or any(
            coordinator._field_revisions.get(field, 0) <= revision for field, revision in baselines.items()
        ):
            raise ValueError("Blank-screen policy state has not been read freshly; refresh the device first")
        policy_revision = coordinator._blank_screen_notification_revision
        client, token = coordinator._client, coordinator._notification_token
    detection, low_duration, same_duration = (
        policy
        if policy is not None
        else (
            coordinator.blank_screen_detection,
            coordinator.blank_screen_low_brightness_duration_seconds,
            coordinator.blank_screen_same_tone_duration_seconds,
        )
    )
    if detection is None or low_duration is None or same_duration is None:
        raise ValueError("Blank-screen policy state has not been read; refresh the device first")

    def check_policy() -> None:
        if write_guard is not None:
            write_guard()
        if policy is None and (
            coordinator._blank_screen_notification_revision != policy_revision
            or coordinator._client is not client
            or coordinator._notification_token is not token
            or (
                coordinator.blank_screen_detection,
                coordinator.blank_screen_low_brightness_duration_seconds,
                coordinator.blank_screen_same_tone_duration_seconds,
            )
            != (detection, low_duration, same_duration)
        ):
            raise ValueError("Blank-screen policy changed before write; refresh and retry")

    packet = build_blank_screen(expected, coordinator.model, detection, low_duration, same_duration)
    fields: dict[str, Any] = {"blank_screen": expected}
    if policy is not None:
        fields.update(
            blank_screen_detection=detection,
            blank_screen_low_brightness_duration_seconds=low_duration,
            blank_screen_same_tone_duration_seconds=same_duration,
        )
    for _ in range(2 if verify else 1):
        await _send_video_setting(
            coordinator,
            packet,
            frozenset({"blank_screen"}),
            writer=writer,
            write_guard=check_policy,
            state_values=fields,
            expected_values=fields if verify else None,
        )
        if not verify:
            return True
        confirmed = (
            await coordinator.refresh_state(expected_blank_screen=expected)
            if policy is None
            else await coordinator.refresh_state(expected_blank_screen=expected, expected_blank_screen_policy=policy)
        )
        if confirmed:
            return True
    raise RuntimeError("Blank-screen write was not confirmed by the device")


async def apply_black_border(
    coordinator: GoveeBLECoordinator,
    expected: bool,
    *,
    writer: ProfileWriter | None = None,
    verify: bool = True,
) -> bool:
    packet = build_black_border(expected, coordinator.model)
    fields = {"black_border": expected}
    for _ in range(2 if verify else 1):
        await _send_video_setting(
            coordinator,
            packet,
            frozenset({"black_border"}),
            writer=writer,
            state_values=fields,
            expected_values=fields if verify else None,
        )
        if not verify or await coordinator.refresh_state(expected_black_border=expected):
            return True
    raise RuntimeError("Black-border write was not confirmed by the device")
