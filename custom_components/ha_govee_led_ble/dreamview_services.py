"""Validated entity services for explicitly declared DreamView operations."""

from __future__ import annotations

import logging
from collections.abc import Callable
from functools import partial
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers import service

from .const import DOMAIN
from .dreamview import (
    DREAMVIEW_VIDEO_FIELDS,
    DreamviewMember,
    build_dreamview_command,
    build_dreamview_group,
    integer,
)
from .schema_compat import vol

_LOGGER = logging.getLogger(__name__)


def _integer(maximum: int) -> Callable[[Any], int]:
    def validate(value: Any) -> int:
        try:
            return integer(value, maximum)
        except ValueError as err:
            raise vol.Invalid(str(err)) from None

    return validate


def _boolean(value: Any) -> bool:
    if type(value) is not bool:
        raise vol.Invalid("Expected an explicit boolean")
    return value


def _members(value: Any) -> list[dict[str, Any]]:
    schema = vol.Schema(
        vol.All(
            [
                {
                    vol.Required("cmd_ver"): _integer(255),
                    vol.Required("is_rgbic"): _boolean,
                    vol.Required("zones"): vol.All([_integer(255)], vol.Length(min=1, max=255)),
                    vol.Optional("address"): str,
                    vol.Optional("name"): str,
                }
            ],
            vol.Length(min=1, max=255),
        )
    )
    try:
        members = [DreamviewMember(**{**item, "zones": tuple(item["zones"])}) for item in schema(value)]
        if len({(member.address, member.name) for member in members}) != len(members):
            raise ValueError("Duplicate DreamView identity")
        return [member.as_dict() for member in members]
    except TypeError, ValueError, vol.Invalid:
        # No identity values in exception messages or chained service logs.
        raise vol.Invalid("Invalid DreamView members; supply known cmd_ver, identity and wire areas") from None


DREAMVIEW_SERVICES: dict[str, tuple[str, dict[Any, Any]]] = {
    "replace_dreamview_group": ("replace", {vol.Required("members"): _members}),
    "delete_dreamview_group": ("delete", {}),
    "read_dreamview_group": ("read", {}),
    "set_dreamview_switch": ("switch_group", {vol.Required("enabled"): _boolean}),
    "set_dreamview_member_brightness": (
        "member_brightness",
        {vol.Required("level"): _integer(100), vol.Required("index"): _integer(255)},
    ),
    "set_dreamview_same_brightness": ("same_brightness", {vol.Required("enabled"): _boolean}),
    "set_dreamview_member_connect": (
        "member_connect",
        {vol.Required("index"): _integer(255), vol.Required("connected"): _boolean},
    ),
    "set_dreamview_saturation": ("saturation", {vol.Required("saturation"): _integer(100)}),
    "set_dreamview_video_settings": (
        "video_settings",
        {vol.Required(name): vol.In(choices.__members__) for name, choices in DREAMVIEW_VIDEO_FIELDS.items()},
    ),
    "set_dreamview_sample": (
        "video_settings",
        {vol.Required("sample_first"): _integer(255), vol.Required("sample_second"): _integer(255)},
    ),
    "set_dreamview_sound_effects": (
        "sound",
        {vol.Required("enabled"): _boolean, vol.Required("softness"): _integer(100)},
    ),
}


async def _async_dreamview_service(entity: Any, call: ServiceCall, *, name: str) -> dict[str, Any] | None:
    """Revalidate direct invocations and compile before preview/control side effects."""
    c = entity.coordinator
    setting, schema = DREAMVIEW_SERVICES[name]
    try:
        values = vol.Schema(schema)(service.remove_entity_service_fields(call))
        if name == "set_dreamview_sample":
            values = {"apply_area": values["sample_first"], "content_mode": values["sample_second"]}
        elif setting == "video_settings":
            values = {field: choices[values[field]].value for field, choices in DREAMVIEW_VIDEO_FIELDS.items()}
        members: tuple[DreamviewMember, ...] = ()
        if setting == "replace":
            members = tuple(DreamviewMember(**{**item, "zones": tuple(item["zones"])}) for item in values["members"])
            build_dreamview_group(members, c.profile)
            await c.async_validate_dreamview_members(members)
        elif setting != "read":
            build_dreamview_command("delete_group" if setting == "delete" else setting, values, c.profile)
        if setting == "read":
            return await c.async_read_dreamview_state()  # type: ignore[no-any-return]
        if name == "set_dreamview_sample":
            ir.async_create_issue(
                c.hass,
                DOMAIN,
                "dreamview_sample_deprecated",
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="dreamview_sample_deprecated",
                learn_more_url="https://github.com/teh-hippo/ha-govee-led-ble#dreamview",
            )
        await entity._async_supersede_preview()
        if setting == "replace":
            await c.async_replace_dreamview_group(members)
        elif setting == "delete":
            await c.async_delete_dreamview_group()
        else:
            await c.async_set_dreamview(setting, values)
    except ServiceValidationError:
        raise
    except TypeError, ValueError, vol.Invalid:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="invalid_control_request") from None
    except Exception as err:
        _LOGGER.exception("DreamView service call failed")
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="device_command_failed") from err
    return None


def async_register_dreamview_services(hass: HomeAssistant) -> None:
    for name, (setting, schema) in DREAMVIEW_SERVICES.items():
        service.async_register_platform_entity_service(
            hass,
            DOMAIN,
            name,
            entity_domain="light",
            func=partial(_async_dreamview_service, name=name),
            schema=schema,
            supports_response=SupportsResponse.ONLY if setting == "read" else SupportsResponse.NONE,
        )
