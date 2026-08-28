"""Fail-open process setup for the optional advanced-effect backend."""

from __future__ import annotations

import logging
from typing import Final, cast

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import UnsupportedStorageVersionError

from .const import DOMAIN
from .effect_backend import EffectBackend
from .effect_services import async_register_effect_services
from .effect_storage import EffectStorageError
from .effect_websocket import async_register_effect_websocket

_LOGGER = logging.getLogger(__name__)

EFFECT_BACKEND_DATA_KEY: Final = "effect_backend"


async def async_setup_effects(hass: HomeAssistant) -> EffectBackend | None:
    try:
        backend = await EffectBackend.async_create(hass)
        await backend.async_complete_storage_migration()
    except EffectStorageError, OSError, UnsupportedStorageVersionError:
        _LOGGER.exception("Advanced effect storage is unavailable; normal Govee entities remain active")
        return None
    async_register_effect_websocket(hass, backend)
    async_register_effect_services(hass)
    hass.data.setdefault(DOMAIN, {})[EFFECT_BACKEND_DATA_KEY] = backend
    return backend


def get_effect_backend(hass: HomeAssistant) -> EffectBackend | None:
    value = hass.data.get(DOMAIN, {}).get(EFFECT_BACKEND_DATA_KEY)
    return cast(EffectBackend | None, value)
