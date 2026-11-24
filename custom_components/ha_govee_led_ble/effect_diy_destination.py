"""Operation-scoped consent for destructive DIY destinations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .const import ModelProfile, same_control_profile
from .effect_catalogue import (
    diy_destination_range,
    diy_destination_route,
    requires_diy_destination_consent,
)

if TYPE_CHECKING:
    from .coordinator import GoveeBLECoordinator
    from .effect_compiler import CompiledApplication


def diy_destination_authority(coordinator: GoveeBLECoordinator) -> str:
    return ":".join(
        (
            getattr(coordinator, "_physical_authority_id", "unbound"),
            str(getattr(coordinator, "_profile_generation", 0)),
            str(getattr(coordinator, "_authorization_generation", 0)),
        )
    )


def requested_diy_destination(raw: Mapping[str, Any] | None, fallback: int | None = None) -> int | None:
    if raw is None:
        return fallback
    destination = raw.get("destination")
    if not isinstance(destination, int) or isinstance(destination, bool) or not 0 <= destination <= 0xFFFF:
        raise ValueError("DIY destination consent requires an unsigned 16-bit destination")
    if fallback is not None and destination != fallback:
        raise ValueError("DIY destination consent conflicts with the requested selector")
    return destination


@dataclass(frozen=True, slots=True)
class DiyDestinationConsent:
    config_entry_id: str
    model: str
    destination: int
    minimum: int
    maximum: int
    route: str
    authority: str
    overwrite_confirmed: bool
    client: object
    subscription: object | None
    profile: ModelProfile
    profile_generation: int
    authorization_generation: int

    @classmethod
    def bind(
        cls,
        coordinator: GoveeBLECoordinator,
        config_entry_id: str,
        raw: Mapping[str, Any],
    ) -> DiyDestinationConsent:
        required_strings = ("config_entry_id", "model", "route", "authority")
        if any(type(raw.get(key)) is not str or not raw.get(key) for key in required_strings):
            raise ValueError("DIY destination consent identity is malformed")
        destination = requested_diy_destination(raw)
        minimum_raw, maximum_raw = raw.get("minimum"), raw.get("maximum")
        if (
            not isinstance(minimum_raw, int)
            or isinstance(minimum_raw, bool)
            or not isinstance(maximum_raw, int)
            or isinstance(maximum_raw, bool)
        ):
            raise ValueError("DIY destination consent range is malformed")
        if destination is None or raw.get("overwrite_confirmed") is not True:
            raise ValueError("DIY destination consent requires explicit overwrite confirmation")
        if raw["config_entry_id"] != config_entry_id or raw["model"] != coordinator.model:
            raise ValueError("DIY destination consent belongs to another device")
        route = diy_destination_route(coordinator.model, coordinator.effect_authorization_profile)
        authority = diy_destination_authority(coordinator)
        if raw["route"] != route:
            raise ValueError("DIY destination consent route is stale")
        if raw["authority"] != authority:
            raise ValueError("DIY destination consent authority is stale")
        minimum, maximum = diy_destination_range(coordinator.model)
        if (minimum_raw, maximum_raw) != (minimum, maximum):
            raise ValueError("DIY destination consent range is stale")
        if not minimum <= destination <= maximum:
            raise ValueError(f"{coordinator.model} DIY destination must be from {minimum} to {maximum}")
        return cls(
            config_entry_id=config_entry_id,
            model=coordinator.model,
            destination=destination,
            minimum=minimum,
            maximum=maximum,
            route=route,
            authority=authority,
            overwrite_confirmed=True,
            client=getattr(coordinator, "_client", None),
            subscription=getattr(coordinator, "_notification_token", None),
            profile=coordinator.effect_authorization_profile,
            profile_generation=getattr(coordinator, "_profile_generation", 0),
            authorization_generation=getattr(coordinator, "_authorization_generation", 0),
        )

    def require_current(self, coordinator: GoveeBLECoordinator) -> None:
        if (
            self.model != coordinator.model
            or self.client is not getattr(coordinator, "_client", None)
            or self.subscription is not getattr(coordinator, "_notification_token", None)
            or self.profile_generation != getattr(coordinator, "_profile_generation", 0)
            or self.authorization_generation != getattr(coordinator, "_authorization_generation", 0)
            or not same_control_profile(self.profile, coordinator.effect_authorization_profile)
            or self.route != diy_destination_route(coordinator.model, coordinator.effect_authorization_profile)
            or self.authority != diy_destination_authority(coordinator)
        ):
            raise ValueError("DIY destination consent authority changed; approve the destination again")


async def async_prepare_diy_destination_consent(
    coordinator: GoveeBLECoordinator,
    config_entry_id: str,
    raw: Mapping[str, Any],
) -> DiyDestinationConsent:
    raw_authority = raw.get("authority")
    disconnected_authority = diy_destination_authority(coordinator)
    ensure_connected = getattr(coordinator, "_ensure_connected", None)
    lock = getattr(coordinator, "_lock", None)
    if getattr(coordinator, "_notification_token", None) is None and ensure_connected is not None and lock is not None:
        async with lock:
            await ensure_connected()
        raw = {
            **raw,
            "authority": (
                diy_destination_authority(coordinator) if raw_authority == disconnected_authority else raw_authority
            ),
        }
    return DiyDestinationConsent.bind(coordinator, config_entry_id, raw)


def compiled_requires_diy_destination_consent(
    compiled: CompiledApplication,
    profile: ModelProfile,
) -> bool:
    from .effect_compiler import CompiledEffect

    return (
        isinstance(compiled, CompiledEffect)
        and compiled.selector_kind == "diy"
        and requires_diy_destination_consent(compiled.model)
        and not (
            compiled.content_kind == "native_effect"
            and profile.native_diy_selector is not None
            and compiled.diy_code == profile.native_diy_selector
        )
    )


def validate_diy_destination_consent(
    coordinator: GoveeBLECoordinator,
    compiled: CompiledApplication,
    consent: DiyDestinationConsent | None,
    *,
    config_entry_id: str | None = None,
) -> None:
    required = compiled_requires_diy_destination_consent(compiled, coordinator.effect_authorization_profile)
    if not required:
        if consent is not None:
            raise ValueError("DIY destination consent is not valid for this fixed destination route")
        return
    if consent is None:
        raise ValueError("DIY destination and explicit overwrite confirmation are required")
    if config_entry_id is not None and consent.config_entry_id != config_entry_id:
        raise ValueError("DIY destination consent belongs to another config entry")
    consent.require_current(coordinator)
    minimum, maximum = diy_destination_range(coordinator.model)
    if (consent.minimum, consent.maximum) != (minimum, maximum):
        raise ValueError("DIY destination consent range changed; approve the destination again")
    if consent.destination != compiled.diy_code:
        raise ValueError("DIY destination consent does not match the compiled destination")
