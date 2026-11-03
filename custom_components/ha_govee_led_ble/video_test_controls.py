"""Temporary H6199 controls for comparing the two video settings banks in #532."""

from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.components.select import SelectEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.util import dt as dt_util

from . import GoveeBLEConfigEntry
from .const import DOMAIN, ModelProfile, ReadDomain
from .control_arbiter import ControlIntent, async_control_intent
from .coordinator import GoveeBLECoordinator
from .dreamview import DREAMVIEW_VIDEO_FIELDS, build_dreamview_command
from .effect_contracts import CapabilityState
from .effect_setup import get_effect_backend
from .entity import GoveeBLEEntity
from .generated_protocol_adapter import build_colour_mode_query, build_power_query
from .native_profile_controls import apply_active_video_mode
from .video_applicability import video_control_states, video_mode_controls

NUMBER_CONTROLS = ("effect_saturation", "effect_sound_effects_softness", "device_saturation", "device_softness")
SELECT_CONTROLS = ("effect_mode", "effect_full_screen", "device_apply_area", "device_content_mode")
SWITCH_CONTROLS = ("effect_sound_effects", "device_enabled")
_OPTIONS = {
    "effect_mode": ["movie", "game"],
    "effect_full_screen": ["part", "all"],
    "device_apply_area": ["part", "all"],
    "device_content_mode": ["movie", "game"],
}
_DEVICE_FIELDS = {
    "saturation": ("saturation", "saturation"),
    "apply_area": ("video_settings", "apply_area"),
    "content_mode": ("video_settings", "content_mode"),
    "enabled": ("sound", "enabled"),
    "softness": ("sound", "softness"),
}
_EFFECT_FIELDS = ("mode", "full_screen", "saturation", "sound_effects", "sound_effects_softness")


def video_test_snapshot_current(coordinator: GoveeBLECoordinator) -> bool:
    snapshot = coordinator.video_test_readback
    return (
        snapshot is not None
        and coordinator._client is snapshot["_client"]
        and coordinator._client is not None
        and coordinator._client.is_connected
        and coordinator._notification_token is snapshot["_token"]
        and coordinator._profile_generation == snapshot["_generation"]
    )


async def async_read_video_test_state(coordinator: GoveeBLECoordinator) -> None:
    """Record observations only, keeping missing replies separate from remembered values."""
    async with async_control_intent(coordinator, ControlIntent.USER):
        if coordinator.model != "H6199":
            raise ValueError("Video bank testing is only available for H6199")
        coordinator.video_test_readback = None
        coordinator.async_set_updated_data(coordinator.data or {})
        async with coordinator._lock:
            client = await coordinator._ensure_connected()
            profile = coordinator._authorization_profile()
            if not all(profile.can_read(domain) for domain in (ReadDomain.POWER, ReadDomain.COLOUR_MODE)):
                raise ValueError("Video test readback is unsupported for this device")
            token, generation = coordinator._notification_token, coordinator._profile_generation
            fields = ("is_on", "color_mode", *(f"video_{field}" for field in _EFFECT_FIELDS))
            baselines = {field: coordinator._field_revisions.get(field, 0) for field in fields}
            for packet in (build_power_query(coordinator.model), build_colour_mode_query(coordinator.model)):
                await coordinator._async_write_packet(client, packet)
                coordinator._renew_foreground_lease()
        deadline = asyncio.get_running_loop().time() + 2.0
        device = await coordinator.async_read_dreamview_state()
        await coordinator._wait_for_revisions(
            {field: baselines[field] for field in ("is_on", "color_mode")}, {}, deadline
        )
        fresh = {field for field in fields if coordinator._field_revisions.get(field, 0) > baselines[field]}
        effect = {
            field: getattr(coordinator, f"video_{field}") if f"video_{field}" in fresh else None
            for field in _EFFECT_FIELDS
        }
        if "color_mode" in fresh and coordinator.video_mode == "off":
            effect["mode"] = "off"
        current = (
            coordinator._client is client
            and client is not None
            and client.is_connected
            and coordinator._notification_token is token
            and coordinator._profile_generation == generation
        )
        if not current:
            raise ValueError("Video test connection changed during read; read both banks again")
        coordinator.video_test_readback = {
            "_client": client,
            "_token": token,
            "_generation": generation,
            "read_at": dt_util.utcnow().isoformat(),
            "power": coordinator.is_on if "is_on" in fresh else None,
            "effect": effect,
            "effect_missing_reads": sorted(field for field, value in effect.items() if value is None),
            "device": device,
        }
        coordinator.async_set_updated_data(coordinator.data or {})


class GoveeBLEVideoTestControl(GoveeBLEEntity):
    def __init__(self, entry: GoveeBLEConfigEntry, control: str) -> None:
        super().__init__(entry.runtime_data)
        self._entry = entry
        self._control = control
        self._bank, self._field = control.split("_", 1)
        self._attr_translation_key = f"video_test_{control}"
        self._attr_unique_id = f"{self.coordinator.address.replace(':', '').lower()}_video_test_{control}"
        self._attr_device_info = self.coordinator.device_info

    @property
    def available(self) -> bool:
        if self.coordinator.model != "H6199":
            return False
        profile = self.coordinator.profile
        if self._bank == "effect":
            states = video_control_states(profile, self.coordinator)
            supported = profile.supports_video_mode and all(
                states[control] is CapabilityState.SUPPORTED for control in video_mode_controls(profile)
            )
        else:
            setting, _field = _DEVICE_FIELDS[self._field]
            supported = setting in profile.dreamview_operations and setting in profile.dreamview_reads
        return supported and super().available

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        snapshot = self.coordinator.video_test_readback
        return {
            "settings_bank": self._bank,
            "read_at": snapshot["read_at"] if snapshot is not None else None,
            "current_subscription": video_test_snapshot_current(self.coordinator),
        }

    def _value(self) -> Any:
        snapshot = self.coordinator.video_test_readback
        if snapshot is None or not video_test_snapshot_current(self.coordinator):
            return None
        if self._bank == "effect":
            return snapshot["effect"].get(self._field)
        setting, field = _DEVICE_FIELDS[self._field]
        return snapshot["device"]["observed"].get(setting, {}).get(field)

    async def _set(self, value: Any) -> None:
        try:
            async with async_control_intent(self.coordinator, ControlIntent.USER):
                if not self.available:
                    raise ValueError("Video test control is unsupported for this device")
                await async_read_video_test_state(self.coordinator)
                if backend := get_effect_backend(self.hass):
                    await backend.preview.async_supersede_device(self._entry.entry_id, reason="home_assistant_control")
                if self._bank == "effect":
                    await self._write_effect(value)
                else:
                    await self._write_device(value)
                await async_read_video_test_state(self.coordinator)
        except ValueError as err:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="invalid_control_request") from err
        except Exception as err:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="device_command_failed") from err

    async def _write_effect(self, value: Any) -> None:
        snapshot = self.coordinator.video_test_readback
        assert snapshot is not None
        effect = snapshot["effect"]
        mode = value if self._field == "mode" else effect["mode"]
        requested = {} if self._field == "mode" else {self._field: value}
        if self._field == "mode" and effect["mode"] == "off":
            # Start an explicit baseline rather than silently inheriting a previous video effect.
            requested = {"full_screen": True, "saturation": 100, "sound_effects": False, "sound_effects_softness": 100}
        elif any(effect[field] is None for field in _EFFECT_FIELDS):
            raise ValueError("Read a complete active video effect before editing its settings")
        if not await apply_active_video_mode(self.coordinator, mode=mode, requested_values=requested):
            raise ValueError("Select Movie or Game before editing effect settings")

    async def _write_device(self, value: Any) -> None:
        coordinator = self.coordinator
        setting, field = _DEVICE_FIELDS[self._field]
        observed = dict(coordinator._dreamview_observed.get(setting, {}))
        fields = {
            "saturation": ("saturation",),
            "video_settings": ("apply_area", "content_mode"),
            "sound": ("enabled", "softness"),
        }
        if any(name not in observed for name in fields[setting]):
            raise ValueError("Read complete device settings before editing")
        values = {name: observed[name] for name in fields[setting]}
        if setting == "sound":
            if values["enabled"] not in (0, 1):
                raise ValueError("Unknown device sound flag")
            values["enabled"] = bool(values["enabled"])
        if setting == "video_settings":
            if any(values[name] not in choices for name, choices in DREAMVIEW_VIDEO_FIELDS.items()):
                raise ValueError("Unknown device video setting")
            values = {name: int(retained) for name, retained in values.items()}
            value = DREAMVIEW_VIDEO_FIELDS[field][value].value
        values[field] = value
        packet = build_dreamview_command(setting, values, coordinator.profile)
        client, token, generation = (
            coordinator._client,
            coordinator._notification_token,
            coordinator._profile_generation,
        )

        def validate(candidate: bytes, profile: ModelProfile) -> None:
            if (
                coordinator._client is not client
                or coordinator._notification_token is not token
                or coordinator._profile_generation != generation
                or coordinator._dreamview_observed.get(setting) != observed
                or candidate != build_dreamview_command(setting, values, profile)
            ):
                raise ValueError("Device settings changed before write; read both banks again")

        await coordinator._async_write_dreamview((packet,), validate)


class GoveeBLEVideoTestNumber(GoveeBLEVideoTestControl, NumberEntity):
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    @property
    def native_min_value(self) -> float:
        return 1 if self._bank == "effect" else 0

    @property
    def native_value(self) -> float | None:
        value = self._value()
        return value if type(value) is int else None

    async def async_set_native_value(self, value: float) -> None:
        if not self.native_min_value <= value <= self.native_max_value or int(value) != value:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="invalid_control_request")
        await self._set(int(value))


class GoveeBLEVideoTestSelect(GoveeBLEVideoTestControl, SelectEntity):
    @property
    def options(self) -> list[str]:
        return _OPTIONS[self._control]

    @property
    def current_option(self) -> str | None:
        value = self._value()
        if self._control == "effect_full_screen" and type(value) is bool:
            value = "all" if value else "part"
        return value if isinstance(value, str) and value in self.options else None

    async def async_select_option(self, option: str) -> None:
        if option not in self.options:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="invalid_control_request")
        await self._set(option == "all" if self._control == "effect_full_screen" else option)


class GoveeBLEVideoTestSwitch(GoveeBLEVideoTestControl, SwitchEntity):
    @property
    def is_on(self) -> bool | None:
        value = self._value()
        return bool(value) if value in (0, 1) else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)
