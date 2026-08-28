"""Config flow for HA Govee LED BLE."""

from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol
from bleak import BleakError  # type: ignore[attr-defined]
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothServiceInfo
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback

from .ble_connection import async_validate_ble_connection
from .const import (
    CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS,
    CONF_EFFECT_CATEGORIES,
    CONF_EFFECT_FAMILIES,
    CONF_MODEL,
    CONF_PREFIX_EFFECT_NAMES,
    DOMAIN,
    MODEL_PROFILES,
    default_effect_categories,
    resolve_model,
    supported_effect_categories,
)

_LOGGER = logging.getLogger(__name__)

MODEL_PATTERN = re.compile(r"(?:ihoment|Govee|GBK|GVH)_(H\w+)")
_MANUAL_ADDRESS_PATTERN = re.compile(r"^[0-9A-F]{12}$")


def _extract_model(name: str) -> str | None:
    return resolve_model(m.group(1)) if (m := MODEL_PATTERN.search(name)) else None


def _normalize_address(address: str) -> str:
    return address.strip().upper()


def _normalize_manual_address(address: str) -> str:
    compact = address.strip().upper().replace(":", "").replace("-", "")
    if not _MANUAL_ADDRESS_PATTERN.fullmatch(compact):
        raise ValueError("invalid BLE address")
    return ":".join(compact[index : index + 2] for index in range(0, 12, 2))


class GoveeConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 8

    _discovered: dict[str, str]

    @staticmethod
    @callback
    def async_get_options_flow(_config_entry: ConfigEntry) -> GoveeOptionsFlow:
        return GoveeOptionsFlow()

    async def async_step_bluetooth(self, discovery_info: BluetoothServiceInfo) -> ConfigFlowResult:
        model = _extract_model(discovery_info.name)
        if model is None:
            return self.async_abort(reason="not_supported")
        await self.async_set_unique_id(_normalize_address(discovery_info.address))
        self._abort_if_unique_id_configured()
        self._discovered = {CONF_MODEL: model}
        # Model only, never the BLE name/MAC (no PII).
        self.context["title_placeholders"] = {"name": model}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        model = self._discovered[CONF_MODEL]
        if user_input is None:
            self._set_confirm_only()
            return self.async_show_form(step_id="bluetooth_confirm", description_placeholders={"model": model})
        return self.async_create_entry(title=f"Govee {model}", data=self._discovered)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            try:
                address = _normalize_manual_address(user_input[CONF_ADDRESS])
            except ValueError:
                return self._show_user_form(errors={CONF_ADDRESS: "invalid_address"})
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            selected_model = user_input[CONF_MODEL]
            service_info = bluetooth.async_last_service_info(self.hass, address, connectable=True)
            advertised_model = _extract_model(service_info.name) if service_info is not None else None
            if advertised_model is not None and advertised_model != selected_model:
                return self._show_user_form(errors={"base": "model_mismatch"})
            try:
                await async_validate_ble_connection(self.hass, address)
            except BleakError:
                return self._show_user_form(errors={"base": "cannot_connect"})
            except Exception:  # noqa: BLE001 - config flows must surface unexpected validation failures.
                _LOGGER.exception("Unexpected error validating a Govee BLE device")
                return self._show_user_form(errors={"base": "unknown"})
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=f"Govee {selected_model}", data={CONF_MODEL: selected_model})
        return self._show_user_form()

    def _show_user_form(self, *, errors: dict[str, str] | None = None) -> ConfigFlowResult:
        models = list(MODEL_PROFILES.keys())
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): str,
                    vol.Required(CONF_MODEL): vol.In(models),
                }
            ),
            errors=errors,
        )


class GoveeOptionsFlow(OptionsFlowWithReload):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        raw_model = self.config_entry.data.get(CONF_MODEL)
        model = resolve_model(raw_model) if isinstance(raw_model, str) else None
        if model is None:
            return self.async_abort(reason="not_supported")
        supported = supported_effect_categories(model)
        if user_input is not None:
            ordered = [category for category in supported if user_input[category]]
            options = {key: value for key, value in self.config_entry.options.items() if key != CONF_EFFECT_FAMILIES}
            options[CONF_EFFECT_CATEGORIES] = ordered
            options[CONF_PREFIX_EFFECT_NAMES] = user_input[CONF_PREFIX_EFFECT_NAMES]
            options[CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS] = user_input[CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS]
            return self.async_create_entry(data=options)
        defaults = default_effect_categories(model)
        current = self.config_entry.options.get(
            CONF_EFFECT_CATEGORIES,
            list(defaults),
        )
        prefix_effect_names = self.config_entry.options.get(
            CONF_PREFIX_EFFECT_NAMES,
            False,
        )
        always_include_custom_effects = self.config_entry.options.get(
            CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS,
            False,
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    **{vol.Required(category, default=category in current): bool for category in supported},
                    vol.Required(CONF_PREFIX_EFFECT_NAMES, default=prefix_effect_names): bool,
                    vol.Required(CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS, default=always_include_custom_effects): bool,
                }
            ),
        )
