"""Standalone installation direction and camera health, without camera calibration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.core import ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .const import DOMAIN, ModelProfile, ReadDomain
from .control_arbiter import ControlIntent, async_control_intent
from .coordinator_status import ParsedStatusEnvelope
from .generated_protocol_adapter import (
    INSTALLATION_DIRECTIONS,
    build_camera_health_query,
    build_installation_direction,
    build_installation_direction_query,
)

if TYPE_CHECKING:
    from .coordinator import GoveeBLECoordinator
    from .light import GoveeBLELight


def installation_direction_value(value: Any) -> int:
    """Accept selector strings or integers, never fractional values or booleans."""
    if isinstance(value, str) and value in {str(item) for item in INSTALLATION_DIRECTIONS}:
        return int(value)
    if type(value) is int and value in INSTALLATION_DIRECTIONS:
        return value
    raise vol.Invalid("Installation direction must be 2, 3, 4, or 5")


def h6099_control_queries(model: str, profile: ModelProfile) -> tuple[bytes, ...]:
    """Optional refresh queries; neither domain is required for setup."""
    return tuple(
        builder(model)
        for domain, builder in (
            (ReadDomain.INSTALLATION_DIRECTION, build_installation_direction_query),
            (ReadDomain.CAMERA_HEALTH, build_camera_health_query),
        )
        if profile.can_read(domain)
    )


def h6099_control_status(decoded: ParsedStatusEnvelope, profile: ModelProfile) -> dict[str, int | str | None]:
    """Interpret the generic status root; unknown values must clear old observations."""
    if not profile.can_read(decoded.domain):
        return {}
    if decoded.domain is ReadDomain.INSTALLATION_DIRECTION:
        value = int(decoded.generated.body.value)
        return {"installation_direction": value if value in INSTALLATION_DIRECTIONS else None}
    if decoded.domain is ReadDomain.CAMERA_HEALTH:
        return {"camera_health": getattr(decoded.generated.body.value, "name", "unknown")}
    return {}


async def async_read_h6099_controls(coordinator: GoveeBLECoordinator) -> dict[str, int | str | None]:
    domains = frozenset({ReadDomain.INSTALLATION_DIRECTION, ReadDomain.CAMERA_HEALTH})
    if not domains <= coordinator.profile.read_domains:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="unsupported_model",
            translation_placeholders={"service": "read_installation_controls", "model": coordinator.model},
        )
    async with async_control_intent(coordinator, ControlIntent.USER):
        baselines = {domain: coordinator._domain_revisions.get(domain, 0) for domain in domains}
        await coordinator.refresh_state(refresh_all=True, required_domains=domains)
        return {
            domain.value: getattr(coordinator, domain.value, missing)
            if coordinator._domain_revisions.get(domain, 0) > baselines[domain]
            else missing
            for domain, missing in (
                (ReadDomain.INSTALLATION_DIRECTION, None),
                (ReadDomain.CAMERA_HEALTH, "unknown"),
            )
        }


async def async_read_installation_controls(entity: GoveeBLELight, call: ServiceCall) -> dict[str, int | str | None]:
    """Return fresh observations, not cached health after a missed reply."""
    return await async_read_h6099_controls(entity.coordinator)


async def async_set_installation_direction(entity: GoveeBLELight, call: ServiceCall) -> None:
    coordinator = entity.coordinator
    try:
        value = installation_direction_value(call.data["value"])
        packet = build_installation_direction(value, coordinator.model)
        if not coordinator.profile.supports_installation_direction:
            raise ValueError("This light does not support installation direction")
        if not {ReadDomain.INSTALLATION_DIRECTION, ReadDomain.CAMERA_HEALTH} <= coordinator.profile.read_domains:
            raise ValueError("This light does not support installation-control readback")
    except ValueError, vol.Invalid:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="invalid_control_request") from None
    await entity._async_supersede_preview()
    async with async_control_intent(coordinator, ControlIntent.USER):
        await coordinator.async_write_effect_sequence((packet,), intent=ControlIntent.USER)
        observed = await async_read_h6099_controls(coordinator)
        if observed["installation_direction"] != value:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="device_command_failed")
