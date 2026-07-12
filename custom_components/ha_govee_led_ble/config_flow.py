"""Config flow for HA Govee LED BLE."""

import re
from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import BluetoothServiceInfo
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .const import CONF_MODEL, DOMAIN, MODEL_PROFILES, resolve_model

MODEL_PATTERN = re.compile(r"(?:ihoment|Govee|GBK|GVH)_(H\w+)")


def _extract_model(name: str) -> str | None:
    return resolve_model(m.group(1)) if (m := MODEL_PATTERN.search(name)) else None


def _normalize_address(address: str) -> str:
    return address.strip().upper()


class GoveeConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 3

    _discovered: dict[str, str]

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
            await self.async_set_unique_id(_normalize_address(user_input[CONF_ADDRESS]))
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"Govee {user_input[CONF_MODEL]}", data={CONF_MODEL: user_input[CONF_MODEL]}
            )
        models = list(MODEL_PROFILES.keys())
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): str,
                    vol.Required(CONF_MODEL): vol.In(models),
                }
            ),
        )
