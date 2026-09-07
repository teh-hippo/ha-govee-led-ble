"""Registration for the services this branch adds.

Kept out of :mod:`light_services` so that file stays what it was. The entity services follow
the pattern already there -- ``async_register_platform_entity_service`` against the light
platform -- and one domain service is registered separately, for the reason its docstring gives.
"""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import service
from homeassistant.helpers.typing import VolDictType

from .const import DOMAIN
from .generated_protocol_adapter import PICTURE_PRESET_DISPLAY_ORDER

_LOGGER = logging.getLogger(__name__)

_PERCENTAGE = vol.All(vol.Coerce(int), vol.Range(min=0, max=100))
_SECONDS = vol.All(vol.Coerce(float), vol.Range(min=0, max=86400))

_SET_VIDEO_SETTINGS_SCHEMA: VolDictType = {
    vol.Optional("game_mode"): cv.boolean,
    vol.Optional("picture_preset"): vol.In(PICTURE_PRESET_DISPLAY_ORDER),
    vol.Optional("saturation"): _PERCENTAGE,
    vol.Optional("sound_effects"): cv.boolean,
    vol.Optional("sound_effects_softness"): _PERCENTAGE,
}
_ENABLED_SCHEMA: VolDictType = {vol.Required("enabled"): cv.boolean}
# softness is Optional on purpose: both fields share one wire frame, so the coordinator reads
# the group's current softness back when it is omitted rather than sending a zero.
_DREAMVIEW_SOUND_SCHEMA: VolDictType = {
    vol.Required("enabled"): cv.boolean,
    vol.Optional("softness"): _PERCENTAGE,
}
_MEMBER_BRIGHTNESS_SCHEMA: VolDictType = {
    vol.Required("index"): vol.All(vol.Coerce(int), vol.Range(min=0, max=9)),
    vol.Required("brightness"): _PERCENTAGE,
}
_IDENTIFY_SCHEMA: VolDictType = {vol.Optional("settle", default=30.0): vol.All(vol.Coerce(float), vol.Range(min=1))}
_RELEASE_SCHEMA: VolDictType = {vol.Optional("seconds", default=120.0): _SECONDS}
# `enabled` and `is_rgbic` are part of the contract, not extras: async_set_dreamview_group
# reads both. `enabled: false` leaves a device OUT of the upload, which is what the vendor
# app's per-member toggle does -- so a caller can keep one list of every device it knows
# about and flip members in and out of the group without rewriting it. Omitting them from
# this schema made voluptuous reject that list outright.
#
# `zones` is accepted here and REQUIRED by the handler, which raises with the reason. Letting
# voluptuous refuse it would give "required key not provided"; the handler explains that a
# DreamView zone count is not an LED segment count and cannot be read over BLE at all.
_SET_GROUP_SCHEMA: VolDictType = {
    vol.Required("members"): vol.All(
        [
            {
                vol.Required("address"): cv.string,
                vol.Optional("enabled", default=True): cv.boolean,
                vol.Optional("is_rgbic", default=True): cv.boolean,
                vol.Optional("zones"): [vol.Any(None, vol.All(vol.Coerce(int), vol.Range(min=0, max=10)))],
            }
        ],
        vol.Length(min=1),
    ),
}

_ENTITY_SERVICES: tuple[tuple[str, VolDictType, str, bool], ...] = (
    ("set_video_settings", _SET_VIDEO_SETTINGS_SCHEMA, "async_set_video_settings", False),
    ("set_video_blank_screen", _ENABLED_SCHEMA, "async_set_video_blank_screen", False),
    ("get_dreamview_candidates", {}, "async_get_dreamview_candidates", True),
    ("read_dreamview_group", {}, "async_read_dreamview_group", True),
    ("identify_dreamview_members", _IDENTIFY_SCHEMA, "async_identify_dreamview_members", True),
    ("set_dreamview_group", _SET_GROUP_SCHEMA, "async_set_dreamview_group", False),
    ("set_dreamview_switch", _ENABLED_SCHEMA, "async_set_dreamview_switch", False),
    ("set_dreamview_member_brightness", _MEMBER_BRIGHTNESS_SCHEMA, "async_set_dreamview_member_brightness", False),
    ("set_dreamview_same_brightness", _ENABLED_SCHEMA, "async_set_dreamview_same_brightness", False),
    ("set_dreamview_sound_effects", _DREAMVIEW_SOUND_SCHEMA, "async_set_dreamview_sound_effects", False),
    ("delete_dreamview_group", {}, "async_delete_dreamview_group", False),
    ("release_ble", _RELEASE_SCHEMA, "async_release_ble", False),
)


def async_register_extra_services(hass: HomeAssistant) -> None:
    """Register the video-settings and DreamView services."""
    for name, schema, method, returns_response in _ENTITY_SERVICES:
        service.async_register_platform_entity_service(
            hass,
            DOMAIN,
            name,
            entity_domain=Platform.LIGHT,
            func=method,
            schema=schema,
            supports_response=SupportsResponse.ONLY if returns_response else SupportsResponse.NONE,
        )
    _async_register_release_all(hass)


def _async_register_release_all(hass: HomeAssistant) -> None:
    """Register `release_all_ble`, which must work while a device is UNAVAILABLE.

    `release_ble` is also an entity service, and that is a trap for this particular job: Home
    Assistant filters unavailable entities out of an entity-service call before the handler ever
    runs, so `release_ble` is silently skipped exactly when it is most wanted.

    That is circular, because the reason to release a device is usually that something else --
    the Govee phone app, or a DreamView sync centre -- has taken it, and a device something else
    holds stops advertising and therefore reads `unavailable` here.

    Nothing about the hold needs the radio: it is a deadline stored on the coordinator and
    checked in `_async_update_data`, so the device does not have to be reachable, present, or
    even powered on for it to be set. The same capability is therefore offered as a DOMAIN
    service, which is not entity-filtered, and it applies to every configured Govee device.
    """
    if hass.services.has_service(DOMAIN, "release_all_ble"):
        return

    async def _async_release_all(call: ServiceCall) -> None:
        seconds = float(call.data["seconds"])
        released: list[str] = []
        for entry in hass.config_entries.async_entries(DOMAIN):
            coordinator = getattr(entry, "runtime_data", None)
            # An entry still in setup_retry has no coordinator, so there is no link to release
            # and nothing to hold off.
            if coordinator is None:
                continue
            await coordinator.async_release_ble(seconds)
            released.append(coordinator.address)
        _LOGGER.info(
            "release_all_ble: %s %d device(s): %s",
            "released" if seconds else "restored",
            len(released),
            ", ".join(released) or "none",
        )

    hass.services.async_register(DOMAIN, "release_all_ble", _async_release_all, schema=vol.Schema(_RELEASE_SCHEMA))
