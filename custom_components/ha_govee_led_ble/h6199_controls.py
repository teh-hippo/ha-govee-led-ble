"""Shared model control entities."""

from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.components.select import SelectEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import GoveeBLECoordinator
from .light import (
    apply_active_music_mode,
    apply_active_video_mode,
    apply_active_video_white_balance,
    apply_active_white_mode,
)

type _ReapplyCallback = Callable[[GoveeBLECoordinator], Awaitable[bool]]
_NUMBER_PARAMS = [
    "video_saturation",
    "video_white_balance",
    "video_sound_effects_softness",
    "music_sensitivity",
    "white_brightness",
]


def _supports_number_param(coordinator: GoveeBLECoordinator, key: str) -> bool:
    profile = coordinator.profile
    if key in {"video_saturation", "video_white_balance", "video_sound_effects_softness"}:
        return profile.supports_video_mode
    if key == "white_brightness":
        return profile.supports_white_brightness
    if key == "music_sensitivity":
        return profile.supports_music_mode
    return False


async def _set_with_rollback(
    coordinator: GoveeBLECoordinator, *, key: str, value: Any, reapply: _ReapplyCallback
) -> None:
    previous = getattr(coordinator, key)
    if previous == value:
        return
    setattr(coordinator, key, value)
    try:
        await reapply(coordinator)
    except Exception:
        setattr(coordinator, key, previous)
        raise
    coordinator.async_set_updated_data(coordinator.data or {})


class _H6199ControlEntity(CoordinatorEntity[GoveeBLECoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: GoveeBLECoordinator, *, key: str, **_: object) -> None:
        super().__init__(coordinator)
        self._key = key
        base = coordinator.address.replace(":", "").lower()
        self._attr_unique_id = f"{base}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = coordinator.device_info


class H6199ParameterNumber(_H6199ControlEntity, NumberEntity):
    _attr_mode = NumberMode.SLIDER
    _attr_native_step = 1
    _attr_native_min_value = 0
    _attr_native_max_value = 100

    @property
    def native_value(self) -> float | None:
        value = getattr(self.coordinator, self._key)
        return float(value) if value is not None else None

    async def async_set_native_value(self, value: float) -> None:
        next_value = int(round(value))
        if self._key in {"video_saturation", "video_sound_effects_softness"}:
            reapply = apply_active_video_mode
        elif self._key == "video_white_balance":
            reapply = apply_active_video_white_balance
        elif self._key == "white_brightness":
            reapply = apply_active_white_mode
        else:
            reapply = apply_active_music_mode
        await _set_with_rollback(self.coordinator, key=self._key, value=next_value, reapply=reapply)


class H6199ParameterSwitch(_H6199ControlEntity, SwitchEntity):
    @property
    def is_on(self) -> bool:
        return bool(getattr(self.coordinator, self._key))

    async def async_turn_on(self, **kwargs: object) -> None:
        await self._set_state(True)

    async def async_turn_off(self, **kwargs: object) -> None:
        await self._set_state(False)

    async def _set_state(self, value: bool) -> None:
        reapply = apply_active_video_mode if self._key == "video_sound_effects" else apply_active_music_mode
        await _set_with_rollback(self.coordinator, key=self._key, value=value, reapply=reapply)


class H6199VideoCaptureSelect(_H6199ControlEntity, SelectEntity):
    _attr_translation_key = "video_capture_region"
    _attr_options = ["full", "part"]

    def __init__(self, coordinator: GoveeBLECoordinator) -> None:
        super().__init__(coordinator, key="video_capture_region")

    @property
    def current_option(self) -> str:
        return "full" if self.coordinator.video_full_screen else "part"

    async def async_select_option(self, option: str) -> None:
        await _set_with_rollback(
            self.coordinator,
            key="video_full_screen",
            value=(option == "full"),
            reapply=apply_active_video_mode,
        )


async def async_setup_number_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = config_entry.runtime_data
    entities = [
        H6199ParameterNumber(coordinator, key=key) for key in _NUMBER_PARAMS if _supports_number_param(coordinator, key)
    ]
    if entities:
        async_add_entities(entities)


async def async_setup_select_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    if (coordinator := config_entry.runtime_data).profile.supports_video_mode:
        async_add_entities([H6199VideoCaptureSelect(coordinator)])


async def async_setup_switch_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = config_entry.runtime_data
    entities: list[H6199ParameterSwitch] = []
    if coordinator.profile.supports_video_mode:
        entities.append(H6199ParameterSwitch(coordinator, key="video_sound_effects"))
    if coordinator.profile.supports_music_calm:
        entities.append(H6199ParameterSwitch(coordinator, key="music_calm"))
    if entities:
        async_add_entities(entities)
