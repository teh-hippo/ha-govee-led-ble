"""H6102 identity: configured and observed firmware, hardware and Pact resolve its profile."""

from __future__ import annotations

from typing import Any

from .const import ModelProfile
from .coordinator_base import _CoordinatorBase
from .h6102_capabilities import (
    H6102CapabilityResolution,
    H6102CapabilityResolutionReason,
    H6102FirmwareSource,
    resolve_h6102_capabilities,
)
from .h6102_protocol import H6102_PACTS, H6102RgbVariant


class _H6102Mixin(_CoordinatorBase):
    rgb_variant: H6102RgbVariant | None
    firmware_source: H6102FirmwareSource | None
    capability_resolution_reason: H6102CapabilityResolutionReason | None
    _configured_h6102_firmware: str | None
    _configured_h6102_hardware: str | None
    _h6102_context: tuple[Any, ...] | None = None

    def _init_h6102(
        self,
        resolution: H6102CapabilityResolution | None,
        *,
        firmware: str | None,
        firmware_source: H6102FirmwareSource | None,
        hardware: str | None,
        pact: str | None,
    ) -> None:
        self.rgb_variant = resolution.rgb_variant if resolution is not None else None
        self.firmware_source = resolution.firmware_source if resolution is not None else None
        self.capability_resolution_reason = resolution.capability_resolution_reason if resolution is not None else None
        self._configured_h6102_firmware = firmware if firmware_source == "configured" else None
        self._configured_h6102_hardware = hardware
        if pact is not None and pact not in H6102_PACTS:
            raise ValueError("Unknown H6102 Pact context")

    def _apply_h6102_context(
        self, *, firmware: str | None, firmware_source: H6102FirmwareSource | None, pact: str | None
    ) -> None:
        """Seed the observed identity from the config entry once the base attributes exist."""
        if self.model != "H6102":
            return
        if firmware_source == "ble":
            self.fw_version = firmware
        if pact is not None:
            self.pact_type, self.pact_code = H6102_PACTS[pact]

    def _forget_configured_identity(self, field: str) -> None:
        """A device reply supersedes the value the user typed into the config entry."""
        if self.model != "H6102":
            return
        if field == "fw_version":
            self._configured_h6102_firmware = None
        elif field == "hw_version":
            self._configured_h6102_hardware = None

    def _resolve_h6102_profile(self) -> tuple[ModelProfile, bool]:
        """Return the resolved profile and whether the identity context changed since the last call."""
        context = (self.pact_type, self.pact_code, self.fw_version, self.hw_version, self.profile.physical_ic_count)
        context_changed = self._h6102_context is not None and context != self._h6102_context
        self._h6102_context = context
        resolution = resolve_h6102_capabilities(
            self.fw_version or self._configured_h6102_firmware,
            "ble" if self.fw_version else "configured" if self._configured_h6102_firmware else None,
            hardware=self.hw_version or self._configured_h6102_hardware,
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
        firmware = (
            self.fw_version if confirmed_firmware else self._configured_h6102_firmware if self.pact_type == 1 else None
        )
        hardware = (
            self.hw_version
            if "hw_version" in self._confirmed_identity_fields
            else self._configured_h6102_hardware
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
