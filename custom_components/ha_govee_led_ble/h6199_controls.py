"""Shared model control entities."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.components.select import SelectEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_ON, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import MUSIC_MODE_SLUGS, ModelProfile
from .coordinator import GoveeBLECoordinator
from .coordinator_modes import MUSIC_PARAM_SPECS, MusicParamSpec
from .entity import GoveeBLEEntity
from .light import (
    apply_active_music_mode,
    apply_active_video_mode,
)
from .protocol import (
    WHITE_BALANCE_POSITIONS,
    build_blank_screen,
    build_poweroff_memory,
    build_relative_brightness_edges,
    build_video_white_balance,
)

type _ReapplyCallback = Callable[[GoveeBLECoordinator], Awaitable[bool]]

_READ_BACKED_KEYS = frozenset(
    {
        "white_balance_red",
        "white_balance_blue",
        "relative_brightness",
        "relative_brightness_left",
        "relative_brightness_top",
        "relative_brightness_right",
        "relative_brightness_bottom",
        "blank_screen",
    }
)


async def _apply_poweroff_memory(coordinator: GoveeBLECoordinator) -> bool:
    if not coordinator.profile.supports_poweroff_memory:
        raise ValueError(f"{coordinator.model} does not support power-off memory")
    await coordinator.send_command(build_poweroff_memory(bool(coordinator.poweroff_memory)))
    return True


async def _apply_white_balance(coordinator: GoveeBLECoordinator) -> bool:
    expected = coordinator.white_balance
    fields = {"white_balance_red": expected[0], "white_balance_blue": expected[1]}
    for _ in range(2):
        coordinator._arm_expected_values(fields)
        await coordinator.send_command(build_video_white_balance(*expected))
        if await coordinator.refresh_state(expected_white_balance=expected):
            return True
    raise RuntimeError("White-balance write was not confirmed by the device")


async def _apply_relative_brightness(coordinator: GoveeBLECoordinator) -> bool:
    values = tuple(getattr(coordinator, f"relative_brightness_{edge}") for edge in ("left", "top", "right", "bottom"))
    if any(value is None for value in values):
        raise ValueError("Relative-brightness edge state has not been read; set all edges first")
    left, top, right, bottom = values
    assert left is not None and top is not None and right is not None and bottom is not None
    expected = left, top, right, bottom
    aggregate = left if len(set(expected)) == 1 else None
    fields = {
        "relative_brightness": aggregate,
        "relative_brightness_left": left,
        "relative_brightness_top": top,
        "relative_brightness_right": right,
        "relative_brightness_bottom": bottom,
    }
    for _ in range(2):
        coordinator._arm_expected_values(fields)
        await coordinator.send_command(build_relative_brightness_edges(*expected))
        if await coordinator.refresh_state(expected_relative_brightness=expected):
            return True
    raise RuntimeError("Relative-brightness write was not confirmed by the device")


async def _apply_blank_screen(coordinator: GoveeBLECoordinator) -> bool:
    expected = bool(coordinator.blank_screen)
    for _ in range(2):
        coordinator._arm_expected_values({"blank_screen": expected})
        await coordinator.send_command(build_blank_screen(expected))
        if await coordinator.refresh_state(expected_blank_screen=expected):
            return True
    raise RuntimeError("Blank-screen write was not confirmed by the device")


@dataclass(frozen=True)
class ControlSpec:
    """One optimistic control: the coordinator field it stores, what reapplies it, and its bounds.

    ``reapply`` decides how the stored value reaches the device. A setting with a register of its
    own writes that register; a setting that only exists as a field of a larger frame rewrites the
    whole frame, and does nothing at all while the mode owning that frame is not the live one.
    """

    supports: Callable[[ModelProfile], bool]
    reapply: _ReapplyCallback
    min_value: int = 0
    max_value: int = 100
    mode: NumberMode = NumberMode.SLIDER
    enabled_default: bool = True


# Numbers, in the order they are added. Music sensitivity and the two video percentages ride their
# mode's frame; relative brightness owns a register and white balance is added as a dedicated slider.
NUMBER_CONTROLS: dict[str, ControlSpec] = {
    "music_sensitivity": ControlSpec(lambda p: p.supports_music_mode, apply_active_music_mode),
    "video_saturation": ControlSpec(lambda p: p.supports_video_mode, apply_active_video_mode),
    "video_sound_effects_softness": ControlSpec(
        lambda p: p.supports_video_sound_effects, apply_active_video_mode, min_value=1
    ),
    "relative_brightness": ControlSpec(
        lambda p: p.supports_relative_brightness,
        _apply_relative_brightness,
        min_value=1,
        enabled_default=False,
    ),
    "relative_brightness_left": ControlSpec(
        lambda p: p.supports_relative_brightness,
        _apply_relative_brightness,
        min_value=1,
        enabled_default=False,
    ),
    "relative_brightness_top": ControlSpec(
        lambda p: p.supports_relative_brightness,
        _apply_relative_brightness,
        min_value=1,
        enabled_default=False,
    ),
    "relative_brightness_right": ControlSpec(
        lambda p: p.supports_relative_brightness,
        _apply_relative_brightness,
        min_value=1,
        enabled_default=False,
    ),
    "relative_brightness_bottom": ControlSpec(
        lambda p: p.supports_relative_brightness,
        _apply_relative_brightness,
        min_value=1,
        enabled_default=False,
    ),
}

SWITCH_CONTROLS: dict[str, ControlSpec] = {
    "video_sound_effects": ControlSpec(lambda p: p.supports_video_sound_effects, apply_active_video_mode),
    "blank_screen": ControlSpec(lambda p: p.supports_blank_screen, _apply_blank_screen),
}


def _supports_number_param(coordinator: GoveeBLECoordinator, key: str) -> bool:
    spec = NUMBER_CONTROLS.get(key)
    return spec is not None and spec.supports(coordinator.profile)


async def _set_with_rollback(
    coordinator: GoveeBLECoordinator, *, key: str, value: Any, reapply: _ReapplyCallback
) -> None:
    await _set_fields_with_rollback(coordinator, {key: value}, reapply=reapply)


async def _set_fields_with_rollback(
    coordinator: GoveeBLECoordinator, values: dict[str, Any], *, reapply: _ReapplyCallback
) -> None:
    """Store one or more coordinator fields optimistically, restoring all of them if the write fails.

    White balance is why this takes a mapping: both gains go out in one frame, so rolling back one
    of them without the other would leave a stored pair the device was never sent.
    """
    async with coordinator._control_lock:
        previous = {key: getattr(coordinator, key) for key in values}
        if previous == values:
            return
        for key, value in values.items():
            setattr(coordinator, key, value)
        try:
            await reapply(coordinator)
        except Exception:
            coordinator._clear_expected_fields(*values)
            for key, value in previous.items():
                setattr(coordinator, key, value)
            raise
        coordinator.async_set_updated_data(coordinator.data or {})


async def apply_active_music_param(coordinator: GoveeBLECoordinator, *, mode_code: int) -> bool:
    """Reapply a music_body parameter only while its owning mode is live."""
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


class _RestoreLastWritten(_H6199ControlEntity, RestoreEntity):
    """Restore last-written state only for controls the device cannot report.

    Restoring is display only: nothing is sent, because the device kept its own setting across
    our restart and re-asserting a remembered one would overwrite whatever else has changed it.

    Read-backed fields remain unknown until a device reply arrives. Restoring them during the
    asynchronous first-refresh window can seed stale siblings that a later partial write sends
    back over the device's real state.
    """

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        await self._async_restore_state()

    async def _async_restore_state(self) -> None:
        if self._key in _READ_BACKED_KEYS or getattr(self.coordinator, self._key) is not None:
            return
        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        restored = self._restored_value(last_state.state)
        if restored is None:
            return
        setattr(self.coordinator, self._key, restored)
        self.coordinator.async_set_updated_data(self.coordinator.data or {})

    def _restored_value(self, state: str) -> Any:
        raise NotImplementedError


class H6199ParameterNumber(_RestoreLastWritten, NumberEntity):
    _attr_native_step = 1

    def __init__(self, coordinator: GoveeBLECoordinator, *, key: str, **kwargs: object) -> None:
        super().__init__(coordinator, key=key, **kwargs)
        spec = NUMBER_CONTROLS[key]
        self._attr_mode = spec.mode
        self._attr_entity_registry_enabled_default = spec.enabled_default
        self._attr_native_min_value = (
            coordinator.profile.music_sensitivity_min if key == "music_sensitivity" else spec.min_value
        )
        self._attr_native_max_value = (
            coordinator.profile.music_sensitivity_max if key == "music_sensitivity" else spec.max_value
        )
        self._reapply = spec.reapply

    @property
    def native_value(self) -> float | None:
        value = getattr(self.coordinator, self._key)
        return float(value) if value is not None else None

    def _restored_value(self, state: str) -> int | None:
        try:
            value = int(round(float(state)))
        except ValueError:
            return None
        return value if self._attr_native_min_value <= value <= self._attr_native_max_value else None

    async def async_set_native_value(self, value: float) -> None:
        next_value = int(round(value))
        if self._key == "relative_brightness":
            await _set_fields_with_rollback(
                self.coordinator,
                {
                    "relative_brightness": next_value,
                    "relative_brightness_left": next_value,
                    "relative_brightness_top": next_value,
                    "relative_brightness_right": next_value,
                    "relative_brightness_bottom": next_value,
                },
                reapply=self._reapply,
            )
            return
        if self._key.startswith("relative_brightness_"):
            values = {
                f"relative_brightness_{edge}": (
                    next_value
                    if self._key == f"relative_brightness_{edge}"
                    else getattr(self.coordinator, f"relative_brightness_{edge}")
                )
                for edge in ("left", "top", "right", "bottom")
            }
            if any(edge_value is None for edge_value in values.values()):
                raise ValueError("Relative-brightness edge state has not been read; set all edges first")
            distinct = set(values.values())
            values["relative_brightness"] = next(iter(distinct)) if len(distinct) == 1 else None
            await _set_fields_with_rollback(self.coordinator, values, reapply=self._reapply)
            return
        await _set_with_rollback(self.coordinator, key=self._key, value=next_value, reapply=self._reapply)


class H6199WhiteBalanceNumber(_H6199ControlEntity, NumberEntity):
    """Vendor-equivalent position on the H6199's captured 20-step balance curve."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "white_balance"
    _attr_native_min_value = 1
    _attr_native_max_value = len(WHITE_BALANCE_POSITIONS)
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: GoveeBLECoordinator) -> None:
        super().__init__(coordinator, key="white_balance")

    @property
    def native_value(self) -> float | None:
        red, blue = self.coordinator.white_balance_red, self.coordinator.white_balance_blue
        if red is None or blue is None:
            return None
        try:
            return float(WHITE_BALANCE_POSITIONS.index((red, blue)) + 1)
        except ValueError:
            return None

    async def async_set_native_value(self, value: float) -> None:
        position = int(round(value))
        if not 1 <= position <= len(WHITE_BALANCE_POSITIONS):
            raise ValueError(f"white-balance position must be 1..{len(WHITE_BALANCE_POSITIONS)}")
        red, blue = WHITE_BALANCE_POSITIONS[position - 1]
        await _set_fields_with_rollback(
            self.coordinator,
            {"white_balance_red": red, "white_balance_blue": blue},
            reapply=_apply_white_balance,
        )


class H6199ControlSwitch(_RestoreLastWritten, SwitchEntity):
    def __init__(self, coordinator: GoveeBLECoordinator, *, key: str) -> None:
        super().__init__(coordinator, key=key)
        self._reapply = SWITCH_CONTROLS[key].reapply

    @property
    def is_on(self) -> bool | None:
        value = getattr(self.coordinator, self._key)
        return None if value is None else bool(value)

    def _restored_value(self, state: str) -> bool | None:
        return state == STATE_ON if state in (STATE_ON, STATE_OFF) else None

    async def async_turn_on(self, **kwargs: object) -> None:
        await _set_with_rollback(self.coordinator, key=self._key, value=True, reapply=self._reapply)

    async def async_turn_off(self, **kwargs: object) -> None:
        await _set_with_rollback(self.coordinator, key=self._key, value=False, reapply=self._reapply)


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


class GoveeMusicStyleSelect(_H6199ControlEntity, SelectEntity):
    """Dynamic/Calm music style for the capture-backed H617A modes."""

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
    """Base for disabled-by-default, capture-backed music_body controls."""

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
        H6199ParameterNumber(coordinator, key=key)
        for key in NUMBER_CONTROLS
        if _supports_number_param(coordinator, key)
    ]
    if coordinator.profile.supports_white_balance:
        entities.append(H6199WhiteBalanceNumber(coordinator))
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
    entities: list[SwitchEntity] = [
        H6199ControlSwitch(coordinator, key=key)
        for key, spec in SWITCH_CONTROLS.items()
        if spec.supports(coordinator.profile)
    ]
    if coordinator.profile.supports_music_params:
        entities.extend(MusicParamSwitch(coordinator, spec) for spec in MUSIC_PARAM_SPECS if spec.kind == "switch")
    if coordinator.profile.supports_poweroff_memory:
        entities.append(PowerOffMemorySwitch(coordinator))
    if entities:
        async_add_entities(entities)
