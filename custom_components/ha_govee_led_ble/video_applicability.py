"""Per-control firmware conditions narrow, never grant, model qualification."""

from collections.abc import Iterable
from typing import Any

from .const import ModelProfile, ReadDomain
from .effect_contracts import CapabilityState
from .effect_domain import VideoProfile
from .firmware_version import FirmwareVersion


def identity_version(value: object) -> int | None:
    version = FirmwareVersion.parse(value)
    return version.identity_number() if version is not None else None


def video_identity_fields(profile: ModelProfile) -> frozenset[str]:
    fields = frozenset(condition.identity_field for condition in profile.video_firmware_conditions)
    if profile.video_revision_policy == "H6199":
        fields |= {"fw_version", "hw_version", "subordinate_20_version", "subordinate_21_version"}
    return fields


def h6199_camera_controls_state(model: str, identity: object) -> CapabilityState:
    """Installation/status controls qualified only on the captured H6199 revision.

    Other revisions remain unqualified, not inferred compatible or incompatible.
    """
    if model != "H6199":
        return CapabilityState.UNSUPPORTED
    versions = tuple(
        identity_version(getattr(identity, field, None))
        for field in ("fw_version", "hw_version", "subordinate_20_version", "subordinate_21_version")
    )
    qualified = (11004, 30201, 10300, 10033)
    pact = (getattr(identity, "pact_type", None), getattr(identity, "pact_code", None))
    return CapabilityState.SUPPORTED if versions == qualified and pact == (2, 1) else CapabilityState.EVIDENCE_GAP


def _h6199_video_states(identity: object) -> dict[str, CapabilityState]:
    # Android 7.6.01 pact_tvlightv2/pact/Support.java:331-402. 0x20 is
    # Wi-Fi hardware, 0x21 Wi-Fi firmware; DeviceSkus.f119828e is 1.00.30.
    fw, hw, wifi_hw, wifi_fw = (
        identity_version(getattr(identity, field, None))
        for field in ("fw_version", "hw_version", "subordinate_20_version", "subordinate_21_version")
    )
    pact = (getattr(identity, "pact_type", None), getattr(identity, "pact_code", None))

    def state(*checks: bool | None) -> CapabilityState:
        if False in checks:
            return CapabilityState.UNSUPPORTED
        return CapabilityState.EVIDENCE_GAP if None in checks else CapabilityState.SUPPORTED

    white_balance = state(
        None if fw is None else fw >= 10811,
        None if hw is None else hw >= 30201,
        None if wifi_fw is None else wifi_fw >= 10023,
        None if wifi_hw is None else wifi_hw >= 10300,
    )
    relative = state(
        None if fw is None else fw >= 11002,
        None if hw is None else hw in (30201, 30210),
        None if wifi_fw is None else wifi_fw >= 10030,
        None if wifi_hw is None else wifi_hw == 10300,
    )
    if pact in ((3, 1), (4, 1)):
        sound = CapabilityState.SUPPORTED
    else:
        # OtaType: major 1 is Telink; major 3 except 3.04 is FRK V1.
        sound = state(
            None if hw is None else hw // 10000 in (1, 3) and hw // 100 != 304,
            None if fw is None or hw is None else fw >= (10601 if hw // 10000 == 1 else 10702),
        )
        if sound is CapabilityState.UNSUPPORTED and None in pact:
            sound = CapabilityState.EVIDENCE_GAP
    return {
        "white_balance": white_balance,
        "relative_brightness": relative,
        "blank_screen": relative,
        "sound_effects": sound,
    }


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
            ("black_border", profile.supports_black_border),
        )
    }
    return _apply_video_conditions(profile, identity, states)


def white_balance_readback_state(profile: ModelProfile, identity: object) -> CapabilityState:
    states = {
        "white_balance": CapabilityState.SUPPORTED
        if profile.supports_white_balance_readback and profile.can_read(ReadDomain.DISPLAY_SETTING)
        else CapabilityState.UNSUPPORTED
    }
    return _apply_video_conditions(profile, identity, states)["white_balance"]


def _apply_video_conditions(
    profile: ModelProfile, identity: object, states: dict[str, CapabilityState]
) -> dict[str, CapabilityState]:
    if profile.video_revision_policy == "H6199":
        for control, state in _h6199_video_states(identity).items():
            if states.get(control) is CapabilityState.SUPPORTED:
                states[control] = state
    for condition in profile.video_firmware_conditions:
        if states.get(condition.control) is not CapabilityState.SUPPORTED:
            continue
        version = identity_version(getattr(identity, condition.identity_field, None))
        if version is None:
            states[condition.control] = CapabilityState.EVIDENCE_GAP
        elif version < int(condition.minimum.replace(".", "")):
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
            ("black_border", content.black_border is not None),
        )
        if requested
    )


def require_video_controls(profile: ModelProfile, identity: object, controls: Iterable[str]) -> None:
    states = video_control_states(profile, identity)
    for control in controls:
        if states[control] is not CapabilityState.SUPPORTED:
            raise ValueError(f"video setting {control} is {states[control].value} for this device")


class CameraUnavailableError(ValueError):
    def __init__(self, state: str) -> None:
        self.state = state
        super().__init__(f"Camera is {state}; video mode is unavailable")


def require_video_mode(profile: ModelProfile, identity: object) -> None:
    state = "unknown"
    if profile.can_read(ReadDomain.CAMERA_HEALTH):
        state = getattr(identity, "camera_health", "unknown")
    elif h6199_camera_controls_state(getattr(identity, "model", ""), identity) is CapabilityState.SUPPORTED:
        state = getattr(identity, "camera_status", "unknown")
    if state in {"absent", "incompatible"}:
        raise CameraUnavailableError(state)


def validate_video_request(coordinator: Any, content: object) -> None:
    if isinstance(content, VideoProfile):
        require_video_mode(coordinator.profile, coordinator)
        if content.saturation is not None:
            coordinator.profile.validate_video_saturation(content.saturation)
        require_video_controls(coordinator.profile, coordinator, requested_video_controls(content))
