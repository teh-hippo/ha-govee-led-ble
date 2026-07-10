"""Shared model control entities."""

from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.components.select import SelectEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_ON, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import MUSIC_MODE_SLUGS
from .coordinator import GoveeBLECoordinator
from .coordinator_modes import MUSIC_PARAM_SPECS, MusicParamSpec
from .entity import GoveeBLEEntity
from .light import (
    apply_active_music_mode,
    apply_active_video_mode,
    apply_active_video_white_balance,
)
from .protocol import build_poweroff_memory

type _ReapplyCallback = Callable[[GoveeBLECoordinator], Awaitable[bool]]
_NUMBER_PARAMS = [
    "video_white_balance",
    "music_sensitivity",
]


def _supports_number_param(coordinator: GoveeBLECoordinator, key: str) -> bool:
    profile = coordinator.profile
    if key == "video_white_balance":
        return profile.supports_video_mode
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


async def _apply_poweroff_memory(coordinator: GoveeBLECoordinator) -> bool:
    await coordinator.send_command(build_poweroff_memory(bool(coordinator.poweroff_memory)))
    return True


async def apply_active_music_param(coordinator: GoveeBLECoordinator, *, mode_code: int) -> bool:
    """Reapply a music param only while its mode is the live music mode; otherwise just store it (§2.3)."""
    if not coordinator.is_on or MUSIC_MODE_SLUGS.get(coordinator.music_mode) != mode_code:
        return False
    await coordinator.async_apply_music_params(mode_code)
    return True


class _H6199ControlEntity(GoveeBLEEntity):
    _attr_entity_category: EntityCategory | None = EntityCategory.CONFIG

    def __init__(self, coordinator: GoveeBLECoordinator, *, key: str, **_: object) -> None:
        super().__init__(coordinator)
        self._key = key
        base = coordinator.address.replace(":", "").lower()
        self._attr_unique_id = f"{base}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = coordinator.device_info


class H6199ParameterNumber(_H6199ControlEntity, RestoreEntity, NumberEntity):
    _attr_mode = NumberMode.SLIDER
    _attr_native_step = 1
    _attr_native_min_value = 0
    _attr_native_max_value = 100

    def __init__(self, coordinator: GoveeBLECoordinator, *, key: str, **kwargs: object) -> None:
        super().__init__(coordinator, key=key, **kwargs)
        if key == "music_sensitivity":
            self._attr_native_max_value = 99
        elif key == "video_white_balance":
            # EXPERIMENTAL / capture-pending: the 33 a9 value mapping is unproven (§2.2, B3).
            self._attr_entity_registry_enabled_default = False

    @property
    def native_value(self) -> float | None:
        value = getattr(self.coordinator, self._key)
        return float(value) if value is not None else None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        await self._async_restore_value()

    async def _async_restore_value(self) -> None:
        if self._key != "video_white_balance" or getattr(self.coordinator, self._key) is not None:
            return
        default_balance = int(self._attr_native_max_value)
        restored = default_balance
        if (last_state := await self.async_get_last_state()) is not None:
            try:
                restored = int(round(float(last_state.state)))
            except TypeError, ValueError:
                restored = default_balance
        restored = min(max(restored, int(self._attr_native_min_value)), int(self._attr_native_max_value))
        setattr(self.coordinator, self._key, restored)
        self.coordinator.async_set_updated_data(self.coordinator.data or {})

    async def async_set_native_value(self, value: float) -> None:
        next_value = int(round(value))
        reapply = apply_active_video_white_balance if self._key == "video_white_balance" else apply_active_music_mode
        await _set_with_rollback(self.coordinator, key=self._key, value=next_value, reapply=reapply)


class PowerOffMemorySwitch(_H6199ControlEntity, RestoreEntity, SwitchEntity):
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: GoveeBLECoordinator) -> None:
        super().__init__(coordinator, key="poweroff_memory")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.poweroff_memory

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        await self._async_restore_state()

    async def _async_restore_state(self) -> None:
        if self.coordinator.poweroff_memory is not None:
            return
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state in (STATE_ON, STATE_OFF):
            self.coordinator.poweroff_memory = last_state.state == STATE_ON
            self.coordinator.async_set_updated_data(self.coordinator.data or {})

    async def async_turn_on(self, **kwargs: object) -> None:
        await self._set_state(True)

    async def async_turn_off(self, **kwargs: object) -> None:
        await self._set_state(False)

    async def _set_state(self, value: bool) -> None:
        await _set_with_rollback(self.coordinator, key="poweroff_memory", value=value, reapply=_apply_poweroff_memory)


class GoveeMusicModeSelect(_H6199ControlEntity, SelectEntity):
    _attr_entity_category = None
    _attr_translation_key = "music_mode"
    _attr_options = [
        "off",
        "energetic",
        "rhythm",
        "spectrum",
        "rolling",
        "separation",
        "hopping",
        "piano_keys",
        "fountain",
        "day_and_night",
        "bloom",
        "shiny",
    ]

    def __init__(self, coordinator: GoveeBLECoordinator) -> None:
        super().__init__(coordinator, key="music_mode")

    @property
    def current_option(self) -> str:
        return self.coordinator.music_mode

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_select_music_slug(option)


class GoveeMusicStyleSelect(_H6199ControlEntity, SelectEntity):
    """Dynamic/Calm music style for Rhythm (§2.1); H617A only, replaces the old ``music_calm`` switch."""

    _attr_options = ["dynamic", "calm"]

    def __init__(self, coordinator: GoveeBLECoordinator) -> None:
        super().__init__(coordinator, key="music_style")

    @property
    def current_option(self) -> str:
        return self.coordinator.music_style

    async def async_select_option(self, option: str) -> None:
        await _set_with_rollback(self.coordinator, key="music_style", value=option, reapply=apply_active_music_mode)


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


class _MusicParamEntity(_H6199ControlEntity):
    """Base for the EXPERIMENTAL, disabled-by-default per-mode music movement entities (§2.3)."""

    _attr_entity_registry_enabled_default = False
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: GoveeBLECoordinator, spec: MusicParamSpec) -> None:
        super().__init__(coordinator, key=spec.key)
        self._spec = spec

    async def _reapply(self, coordinator: GoveeBLECoordinator) -> bool:
        return await apply_active_music_param(coordinator, mode_code=self._spec.mode_code)

    async def _store(self, value: Any) -> None:
        await _set_with_rollback(self.coordinator, key=self._spec.key, value=value, reapply=self._reapply)


class MusicParamNumber(_MusicParamEntity, NumberEntity):
    _attr_mode = NumberMode.SLIDER
    _attr_native_step = 1

    def __init__(self, coordinator: GoveeBLECoordinator, spec: MusicParamSpec) -> None:
        super().__init__(coordinator, spec)
        self._attr_native_min_value = spec.min_value
        self._attr_native_max_value = spec.max_value

    @property
    def native_value(self) -> float:
        return float(getattr(self.coordinator, self._spec.key))

    async def async_set_native_value(self, value: float) -> None:
        await self._store(int(round(value)))


class MusicParamSwitch(_MusicParamEntity, SwitchEntity):
    @property
    def is_on(self) -> bool:
        return bool(getattr(self.coordinator, self._spec.key))

    async def async_turn_on(self, **kwargs: object) -> None:
        await self._store(True)

    async def async_turn_off(self, **kwargs: object) -> None:
        await self._store(False)


class MusicParamSelect(_MusicParamEntity, SelectEntity):
    def __init__(self, coordinator: GoveeBLECoordinator, spec: MusicParamSpec) -> None:
        super().__init__(coordinator, spec)
        self._attr_options = list(spec.options)

    @property
    def current_option(self) -> str:
        return str(getattr(self.coordinator, self._spec.key))

    async def async_select_option(self, option: str) -> None:
        await self._store(option)


async def async_setup_number_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = config_entry.runtime_data
    entities: list[NumberEntity] = [
        H6199ParameterNumber(coordinator, key=key) for key in _NUMBER_PARAMS if _supports_number_param(coordinator, key)
    ]
    if coordinator.profile.supports_music_params:
        entities.extend(MusicParamNumber(coordinator, spec) for spec in MUSIC_PARAM_SPECS if spec.kind == "number")
    if entities:
        async_add_entities(entities)


async def async_setup_select_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = config_entry.runtime_data
    entities: list[SelectEntity] = []
    if coordinator.profile.supports_music_mode:
        entities.append(GoveeMusicModeSelect(coordinator))
    if coordinator.profile.supports_music_style:
        entities.append(GoveeMusicStyleSelect(coordinator))
    if coordinator.profile.supports_music_params:
        entities.extend(MusicParamSelect(coordinator, spec) for spec in MUSIC_PARAM_SPECS if spec.kind == "select")
    if coordinator.profile.supports_video_mode:
        entities.append(H6199VideoCaptureSelect(coordinator))
    if entities:
        async_add_entities(entities)


async def async_setup_switch_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = config_entry.runtime_data
    entities: list[SwitchEntity] = []
    if coordinator.profile.supports_music_params:
        entities.extend(MusicParamSwitch(coordinator, spec) for spec in MUSIC_PARAM_SPECS if spec.kind == "switch")
    if coordinator.profile.supports_poweroff_memory:
        entities.append(PowerOffMemorySwitch(coordinator))
    if entities:
        async_add_entities(entities)
