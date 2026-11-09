"""Dispatch device-wide light actions once per physical device."""

import asyncio
from collections.abc import Awaitable, Callable
from functools import partial
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import service
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import VolDictType


async def _dispatch_device_lights(
    entities: list[Entity],
    call: ServiceCall,
    *,
    func: str | Callable[..., Awaitable[Any]],
) -> dict[str, Any] | None:
    owners: dict[int, Entity] = {}
    for entity in entities:
        owner = getattr(entity, "device_service_owner", None) or entity
        owners[id(owner)] = owner

    async def invoke(owner: Entity) -> Any:
        owner.async_set_context(call.context)
        operation = getattr(owner, func)(**call.data) if isinstance(func, str) else func(owner, call)

        async def run() -> Any:
            return await operation

        return await owner.async_request_call(run())

    results = await asyncio.gather(*(invoke(owner) for owner in owners.values()))
    if not call.return_response:
        return None
    return {owner.entity_id: result for owner, result in zip(owners.values(), results, strict=True)}


def register_device_light_service(
    hass: HomeAssistant,
    service_domain: str,
    service_name: str,
    *,
    entity_domain: str,
    func: str | Callable[..., Awaitable[Any]],
    schema: VolDictType,
    supports_response: SupportsResponse = SupportsResponse.NONE,
) -> None:
    service.async_register_batched_platform_entity_service(
        hass,
        service_domain,
        service_name,
        entity_domain=entity_domain,
        func=partial(_dispatch_device_lights, func=func),
        schema=schema,
        supports_response=supports_response,
    )
