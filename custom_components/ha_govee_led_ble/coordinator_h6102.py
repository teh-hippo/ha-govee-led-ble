"""H6102 identity: configured and observed firmware, hardware and Pact resolve its profile."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .const import CONF_H6102_APP_FIRMWARE, CONF_H6102_APP_HARDWARE, CONF_H6102_PACT, CONF_MODEL, ModelProfile
from .coordinator_base import _CoordinatorBase
from .coordinator_identity import InitialDeviceIdentity
from .h6102_capabilities import (
    H6102CapabilityResolutionReason,
    H6102FirmwareSource,
    resolve_h6102_capabilities,
)
from .h6102_protocol import H6102_PACTS, H6102RgbVariant


@dataclass(frozen=True, slots=True)
class H6102InitialIdentity(InitialDeviceIdentity):
    # Only firmware participates in the pre-state bootstrap.
    # Pact and hardware qualify the final runtime profile.
    pact: str | None = None

    @property
    def bootstrap_hardware(self) -> None:
        return None

    @property
    def bootstrap_pact_type(self) -> None:
        return None

    @property
    def bootstrap_pact_code(self) -> None:
        return None

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.pact is not None and self.pact not in H6102_PACTS:
            raise ValueError("Unknown H6102 Pact context")
        if self.pact is not None:
            pact_type, pact_code = H6102_PACTS[self.pact]
            object.__setattr__(self, "pact_type", pact_type)
            object.__setattr__(self, "pact_code", pact_code)
        if self.hardware is not None and self.hardware_source is None:
            object.__setattr__(self, "hardware_source", "configured")


def initial_identity_from_entry(data: Mapping[str, Any]) -> H6102InitialIdentity | None:
    """Adapt persisted H6102 config without leaking its product keys into the coordinator."""
    if data.get(CONF_MODEL) != "H6102":
        return None
    firmware = data.get(CONF_H6102_APP_FIRMWARE)
    hardware = data.get(CONF_H6102_APP_HARDWARE)
    pact = data.get(CONF_H6102_PACT)
    return H6102InitialIdentity(
        firmware=firmware if isinstance(firmware, str) else None,
        firmware_source="configured" if isinstance(firmware, str) else None,
        hardware=hardware if isinstance(hardware, str) else None,
        hardware_source="configured" if isinstance(hardware, str) else None,
        pact=pact if isinstance(pact, str) else None,
    )


class _H6102Mixin(_CoordinatorBase):
    rgb_variant: H6102RgbVariant | None = None
    firmware_source: H6102FirmwareSource | None = None
    capability_resolution_reason: H6102CapabilityResolutionReason | None = None
    _h6102_context: tuple[Any, ...] | None = None

    def _resolve_h6102_profile(self) -> tuple[ModelProfile, bool]:
        """Return the resolved profile and whether the identity context changed since the last call."""
        context = (self.pact_type, self.pact_code, self.fw_version, self.hw_version, self.profile.physical_ic_count)
        context_changed = self._h6102_context is not None and context != self._h6102_context
        self._h6102_context = context
        resolution = resolve_h6102_capabilities(
            self.fw_version or self._configured_firmware,
            "ble" if self.fw_version else "configured" if self._configured_firmware else None,
            hardware=self.hw_version or self._configured_hardware,
            pact_type=self.pact_type,
            pact_code=self.pact_code,
            physical_ic_count=self.profile.physical_ic_count,
        )
        self.rgb_variant = resolution.rgb_variant
        self.firmware_source = resolution.firmware_source
        self.capability_resolution_reason = resolution.capability_resolution_reason
        return resolution.profile, context_changed

    def _h6102_authorization_profile(self) -> ModelProfile:
        """Profile admitted by identity confirmed on this connection; configured values count only for Pact 1."""
        confirmed_firmware = "fw_version" in self._confirmed_identity_fields
        firmware = self.fw_version if confirmed_firmware else self._configured_firmware if self.pact_type == 1 else None
        hardware = (
            self.hw_version
            if "hw_version" in self._confirmed_identity_fields
            else self._configured_hardware
            if self.pact_type == 1
            else None
        )
        return resolve_h6102_capabilities(
            firmware,
            "ble" if confirmed_firmware else "configured" if firmware else None,
            hardware=hardware,
            pact_type=self.pact_type,
            pact_code=self.pact_code,
            physical_ic_count=self.profile.physical_ic_count,
        ).profile
