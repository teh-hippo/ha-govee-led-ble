"""Home Assistant entity action for saved Effect Studio content."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import service
from homeassistant.helpers.typing import VolDictType

from .const import DOMAIN

SERVICE_APPLY_CUSTOM_EFFECT = "apply_custom_effect"
ATTR_EFFECT = "effect"
ATTR_EFFECT_ID = "effect_id"

APPLY_CUSTOM_EFFECT_SCHEMA: VolDictType = {
    vol.Exclusive(ATTR_EFFECT, "effect_reference"): cv.string,
    vol.Exclusive(ATTR_EFFECT_ID, "effect_reference"): cv.string,
}


def async_register_effect_services(hass: HomeAssistant) -> None:
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_APPLY_CUSTOM_EFFECT,
        entity_domain=Platform.LIGHT,
        func="async_apply_custom_effect",
        schema=APPLY_CUSTOM_EFFECT_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
