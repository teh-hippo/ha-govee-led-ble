"""Configured identity adaptation selected by the device profile."""

from collections.abc import Mapping
from importlib import import_module
from typing import Any, cast

from .const import ConfiguredIdentityPolicy, ModelProfile, get_profile
from .coordinator_base import _CoordinatorBase
from .coordinator_identity import DeviceIdentitySource, InitialDeviceIdentity


def _configured_identity_adapter(policy: ConfiguredIdentityPolicy) -> Any:
    return import_module(f".{policy.adapter}", __package__)


def initial_identity_from_entry(
    data: Mapping[str, Any],
    policy: ConfiguredIdentityPolicy,
) -> InitialDeviceIdentity:
    return cast(
        InitialDeviceIdentity,
        _configured_identity_adapter(policy).initial_identity_from_entry(data, policy),
    )


def resolve_configured_identity(
    policy: ConfiguredIdentityPolicy,
    firmware: str | None,
    firmware_source: DeviceIdentitySource | None,
    **kwargs: Any,
) -> Any:
    return _configured_identity_adapter(policy).resolve_configured_identity(
        firmware,
        firmware_source,
        **kwargs,
    )


def configured_identity_diagnostics(entry: Any, coordinator: Any) -> dict[str, Any]:
    policy = coordinator.profile.configured_identity
    assert policy is not None
    return cast(
        dict[str, Any],
        _configured_identity_adapter(policy).configured_identity_diagnostics(entry, coordinator),
    )


class _ConfiguredIdentityMixin(_CoordinatorBase):
    configured_identity_resolution: Any | None = None
    _configured_identity_context: tuple[Any, ...] | None = None

    def _resolve_configured_identity_profile(self) -> tuple[ModelProfile, bool]:
        policy = get_profile(self.model).configured_identity
        assert policy is not None
        firmware = self.fw_version or self._configured_firmware
        firmware_source: DeviceIdentitySource | None = "ble" if self.fw_version else "configured" if firmware else None
        hardware = self.hw_version or self._configured_hardware
        context = (
            self.pact_type,
            self.pact_code,
            firmware,
            hardware,
            self.profile.physical_ic_count,
        )
        context_changed = self._configured_identity_context is not None and context != self._configured_identity_context
        self._configured_identity_context = context
        resolution = resolve_configured_identity(
            policy,
            firmware,
            firmware_source,
            hardware=hardware,
            pact_type=self.pact_type,
            pact_code=self.pact_code,
            physical_ic_count=self.profile.physical_ic_count,
        )
        self.configured_identity_resolution = resolution
        return cast(ModelProfile, resolution.profile), context_changed

    def _configured_identity_authorization_profile(self) -> ModelProfile:
        policy = get_profile(self.model).configured_identity
        assert policy is not None
        confirmed_firmware = "fw_version" in self._confirmed_identity_fields
        configured_authorized = (
            self.pact_type,
            self.pact_code,
        ) in policy.configured_authorization_pacts
        firmware = (
            self.fw_version if confirmed_firmware else self._configured_firmware if configured_authorized else None
        )
        hardware = (
            self.hw_version
            if "hw_version" in self._confirmed_identity_fields
            else self._configured_hardware
            if configured_authorized
            else None
        )
        resolution = resolve_configured_identity(
            policy,
            firmware,
            "ble" if confirmed_firmware else "configured" if firmware else None,
            hardware=hardware,
            pact_type=self.pact_type,
            pact_code=self.pact_code,
            physical_ic_count=self.profile.physical_ic_count,
        )
        return cast(ModelProfile, resolution.profile)
