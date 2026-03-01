"""Config flow for HA Govee LED BLE."""

import re
from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import BluetoothServiceInfo
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .const import CONF_MODEL, DOMAIN, MODEL_PROFILES

MODEL_PATTERN = re.compile(r"(?:ihoment|Govee|GBK|GVH)_(H\w+)")


def _extract_model(name: str) -> str | None:
    if (m := MODEL_PATTERN.search(name)) and any(m.group(1).startswith(k) for k in MODEL_PROFILES):
        return next(k for k in MODEL_PROFILES if m.group(1).startswith(k))
    return None


def _normalize_address(address: str) -> str:
    return address.strip().upper()


class GoveeConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_bluetooth(self, discovery_info: BluetoothServiceInfo) -> ConfigFlowResult:
        model = _extract_model(discovery_info.name) or "H617A"
        await self.async_set_unique_id(_normalize_address(discovery_info.address))
        self._abort_if_unique_id_configured()
        self.context["title_placeholders"] = {"name": model}
        return self.async_create_entry(title=f"Govee {model}", data={CONF_MODEL: model})

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
                    vol.Required(CONF_MODEL, default=models[0]): vol.In(models),
                }
            ),
        )
