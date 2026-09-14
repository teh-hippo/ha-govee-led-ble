"""Per-control firmware conditions narrow, never grant, model qualification."""

import re
from collections.abc import Iterable
from typing import Any

from .const import ModelProfile
from .effect_contracts import CapabilityState
from .effect_domain import VideoProfile


def video_control_states(profile: ModelProfile, identity: object) -> dict[str, CapabilityState]:
    states = {
        control: CapabilityState.SUPPORTED if profile.supports_video_mode and supported else CapabilityState.UNSUPPORTED
        for control, supported in (
            ("capture_region", profile.supports_video_capture_region),
            ("saturation", profile.supports_video_saturation),
            ("sound_effects", profile.supports_video_sound_effects),
            ("white_balance", profile.supports_white_balance),
            ("relative_brightness", profile.supports_relative_brightness),
            ("blank_screen", profile.supports_blank_screen),
        )
    }
    for condition in profile.video_firmware_conditions:
        if states[condition.control] is not CapabilityState.SUPPORTED:
            continue
        version = getattr(identity, condition.identity_field, None)
        if not isinstance(version, str) or re.fullmatch(r"[0-9]{1,3}\.[0-9]{2}\.[0-9]{2}", version) is None:
            states[condition.control] = CapabilityState.EVIDENCE_GAP
        elif int(version.replace(".", "")) < int(condition.minimum.replace(".", "")):
            states[condition.control] = CapabilityState.UNSUPPORTED
    return states


def requested_video_controls(content: Any) -> frozenset[str]:
    return frozenset(
        control
        for control, requested in (
            ("capture_region", content.full_screen is not None),
            ("saturation", content.saturation is not None),
            ("sound_effects", content.sound_effects is not None or content.sound_effects_softness is not None),
            (
                "white_balance",
                (content.white_balance_position is not None or content.white_balance_value is not None)
                if isinstance(content, VideoProfile)
                else content.white_balance_wire is not None,
            ),
            ("relative_brightness", content.relative_brightness is not None),
            ("blank_screen", content.blank_screen is not None),
        )
        if requested
    )


def require_video_controls(profile: ModelProfile, identity: object, controls: Iterable[str]) -> None:
    states = video_control_states(profile, identity)
    for control in controls:
        if states[control] is not CapabilityState.SUPPORTED:
            raise ValueError(f"video setting {control} is {states[control].value} for this device")


def validate_video_request(coordinator: Any, content: object) -> None:
    if isinstance(content, VideoProfile):
        require_video_controls(coordinator.profile, coordinator, requested_video_controls(content))
