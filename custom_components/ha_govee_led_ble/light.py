"""Light entity for HA Govee LED BLE."""

# fmt: off
from collections.abc import Awaitable, Callable, Generator
from contextlib import contextmanager
from functools import partial
from typing import Any

import voluptuous as vol
from homeassistant.components.light import (  # type: ignore[attr-defined]
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_EFFECT,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GoveeBLECoordinator
from .protocol import (
    build_brightness,
    build_color_rgb,
    build_color_temp,
    build_music_mode_with_color,
    build_power,
    build_scene,
    build_scene_multi,
    build_video_mode,
)
from .scenes import SCENES, get_scene_names

# fmt: on

PARALLEL_UPDATES = 0

MIN_COLOR_TEMP_KELVIN = 2000
MAX_COLOR_TEMP_KELVIN = 9000

VIDEO_EFFECT_GAME_MODE: dict[str, bool] = {"video: movie": False, "video: game": True}
MUSIC_MODE_IDS: dict[str, int] = {"energic": 0x05, "rhythm": 0x03, "spectrum": 0x04, "rolling": 0x06}
MUSIC_EFFECT_MODE_IDS: dict[str, int] = {f"music: {n}": i for n, i in MUSIC_MODE_IDS.items()}
RHYTHM_MODE_ID = MUSIC_MODE_IDS["rhythm"]


# fmt: off
async def apply_video_mode_from_state(coord: GoveeBLECoordinator, *, game_mode: bool) -> None:
    await coord.send_command(build_video_mode(full_screen=coord.video_full_screen, game_mode=game_mode,
        saturation=coord.video_saturation, sound_effects=coord.video_sound_effects,
        sound_effects_softness=coord.video_sound_effects_softness))
# fmt: on


async def apply_active_video_mode(coord: GoveeBLECoordinator) -> bool:
    gm = VIDEO_EFFECT_GAME_MODE.get(coord.effect) if coord.is_on and coord.effect else None
    if gm is None:
        return False
    await apply_video_mode_from_state(coord, game_mode=gm)
    return True


async def apply_active_music_mode(coord: GoveeBLECoordinator) -> bool:
    mid = MUSIC_EFFECT_MODE_IDS.get(coord.effect) if coord.is_on and coord.effect else None
    if mid is None:
        return False
    await coord.send_command(
        build_music_mode_with_color(
            mid,
            sensitivity=coord.music_sensitivity,
            color=coord.music_color,
            calm=coord.music_calm if mid == RHYTHM_MODE_ID else False,
        )
    )
    return True


_STATE_FIELDS = (
    "is_on brightness_pct rgb_color color_temp_kelvin effect video_saturation video_brightness "
    "video_full_screen video_sound_effects video_sound_effects_softness music_sensitivity "
    "music_calm music_color"
).split()


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Govee BLE light from a config entry."""
    async_add_entities([GoveeBLELight(config_entry.runtime_data)])
    p = entity_platform.async_get_current_platform()
    _pct = vol.All(vol.Coerce(int), vol.Range(min=0, max=100))
    # fmt: off
    p.async_register_entity_service("set_video_mode", {
        vol.Required("mode"): vol.In(["movie", "game"]),
        vol.Optional("saturation", default=100): _pct, vol.Optional("brightness", default=100): _pct,
        vol.Optional("capture_region"): vol.In(["full", "part"]),
        vol.Optional("full_screen", default=True): cv.boolean,
        vol.Optional("sound_effects", default=False): cv.boolean,
        vol.Optional("sound_effects_softness", default=0): _pct,
    }, "async_set_video_mode")
    p.async_register_entity_service("set_music_mode", {
        vol.Required("mode"): vol.In(["energic", "rhythm", "spectrum", "rolling"]),
        vol.Optional("sensitivity", default=100): _pct,
        vol.Optional("calm"): cv.boolean,
        vol.Optional("color"): vol.All(vol.ExactSequence((cv.byte, cv.byte, cv.byte)), vol.Coerce(tuple)),
    }, "async_set_music_mode")
    # fmt: on


class GoveeBLELight(CoordinatorEntity[GoveeBLECoordinator], LightEntity):
    """Representation of a Govee BLE light."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_color_modes = {ColorMode.RGB, ColorMode.COLOR_TEMP, ColorMode.ONOFF}
    _attr_supported_features = LightEntityFeature.EFFECT
    _attr_min_color_temp_kelvin = MIN_COLOR_TEMP_KELVIN
    _attr_max_color_temp_kelvin = MAX_COLOR_TEMP_KELVIN

    def __init__(self, coordinator: GoveeBLECoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = coordinator.address.replace(":", "").lower()
        self._attr_device_info = coordinator.device_info
        self._attr_color_mode = ColorMode.RGB
        self._attr_effect_list = (list(get_scene_names()) if coordinator.profile.scene_source == "api" else []) + list(
            coordinator.profile.effects
        )

    @contextmanager
    def _rollback(self) -> Generator[None, None, None]:
        snap = {f: getattr(self.coordinator, f) for f in _STATE_FIELDS}
        mode_snap = self._attr_color_mode
        try:
            yield
        except Exception:
            for f, v in snap.items():
                setattr(self.coordinator, f, v)
            self._attr_color_mode = mode_snap
            raise

    @property
    def is_on(self) -> bool:
        return self.coordinator.is_on

    @property
    def brightness(self) -> int | None:
        return round(self.coordinator.brightness_pct * 255 / 100)

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        return self.coordinator.rgb_color if self._attr_color_mode == ColorMode.RGB else None

    @property
    def color_temp_kelvin(self) -> int | None:
        return self.coordinator.color_temp_kelvin if self._attr_color_mode == ColorMode.COLOR_TEMP else None

    @property
    def effect(self) -> str | None:
        return self.coordinator.effect

    async def _refresh_with_retry(
        self,
        *,
        expected_effect: str | None = None,
        expected_on: bool | None = None,
        retry_command: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        if not self.coordinator.profile.state_readable:
            return
        if await self.coordinator.refresh_state(expected_effect=expected_effect, expected_on=expected_on):
            return
        if retry_command is not None:
            await retry_command()
        if not await self.coordinator.refresh_state(expected_effect=expected_effect, expected_on=expected_on):
            raise RuntimeError(f"Failed to confirm state for {self.coordinator.model}")

    def _notify_state_changed(self) -> None:
        self.async_write_ha_state()
        self.coordinator.async_set_updated_data(self.coordinator.data or {})

    def _require_h6199(self, service: str) -> None:
        model = self.coordinator.model
        if model != "H6199":
            raise ServiceValidationError(
                f"{service} is only supported on H6199, not {model}",
                translation_domain=DOMAIN,
                translation_key="unsupported_model",
                translation_placeholders={"service": service, "model": model},
            )

    async def _apply_effect(self, effect_name: str) -> bool:
        gm = VIDEO_EFFECT_GAME_MODE.get(effect_name)
        if gm is not None:

            async def send() -> None:
                await apply_video_mode_from_state(self.coordinator, game_mode=gm)
                await self.coordinator.send_command(build_brightness(self.coordinator.video_brightness))

            await send()
            self.coordinator.brightness_pct = self.coordinator.video_brightness
            await self._refresh_with_retry(expected_effect=effect_name, retry_command=send)
            return True
        mid = MUSIC_EFFECT_MODE_IDS.get(effect_name)
        if mid is not None:
            send = partial(
                self.coordinator.send_command,
                build_music_mode_with_color(
                    mid,
                    sensitivity=self.coordinator.music_sensitivity,
                    color=self.coordinator.music_color,
                    calm=self.coordinator.music_calm if mid == RHYTHM_MODE_ID else False,
                ),
            )
            await send()
            await self._refresh_with_retry(expected_effect=effect_name, retry_command=send)
            return True
        scene = SCENES.get(effect_name)
        if scene is not None:
            if scene.is_simple:
                await self.coordinator.send_command(build_scene(scene.code))
            else:
                for packet in build_scene_multi(scene.param, scene.code):
                    await self.coordinator.send_command(packet)
            return True
        return False

    async def async_turn_on(self, **kwargs: Any) -> None:
        power_on = partial(self.coordinator.send_command, build_power(True))
        with self._rollback():
            await power_on()
            self.coordinator.is_on, self.coordinator.effect = True, None
            await self._refresh_with_retry(expected_on=True, retry_command=power_on)
            if ATTR_BRIGHTNESS in kwargs:
                pct = max(1, min(100, round(kwargs[ATTR_BRIGHTNESS] * 100 / 255)))
                await self.coordinator.send_command(build_brightness(pct))
                self.coordinator.brightness_pct = pct
            if ATTR_RGB_COLOR in kwargs:
                r, g, b = kwargs[ATTR_RGB_COLOR]
                await self.coordinator.send_command(build_color_rgb(r, g, b))
                self.coordinator.rgb_color = (r, g, b)
                self._attr_color_mode, self.coordinator.color_temp_kelvin = ColorMode.RGB, None
                self.coordinator.effect = None
            if ATTR_COLOR_TEMP_KELVIN in kwargs:
                kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
                await self.coordinator.send_command(build_color_temp(kelvin))
                self.coordinator.color_temp_kelvin = kelvin
                self._attr_color_mode, self.coordinator.effect = ColorMode.COLOR_TEMP, None
            if ATTR_EFFECT in kwargs and await self._apply_effect(kwargs[ATTR_EFFECT]):
                self.coordinator.effect = kwargs[ATTR_EFFECT]
        self._notify_state_changed()

    async def async_turn_off(self, **kwargs: Any) -> None:
        power_off = partial(self.coordinator.send_command, build_power(False))
        with self._rollback():
            await power_off()
            self.coordinator.is_on = False
            await self._refresh_with_retry(expected_on=False, retry_command=power_off)
        self._notify_state_changed()

    # fmt: off
    async def async_set_video_mode(self, mode: str, saturation: int = 100, brightness: int = 100,
            capture_region: str | None = None, full_screen: bool = True,
            sound_effects: bool = False, sound_effects_softness: int = 0) -> None:
        # fmt: on
        self._require_h6199("set_video_mode")
        with self._rollback():
            resolved_fs = full_screen if capture_region is None else capture_region == "full"
            # fmt: off
            packet = build_video_mode(full_screen=resolved_fs, game_mode=mode == "game", saturation=saturation,
                sound_effects=sound_effects, sound_effects_softness=sound_effects_softness)
            # fmt: on
            async def send() -> None:
                await self.coordinator.send_command(packet)
                await self.coordinator.send_command(build_brightness(brightness))

            await self.coordinator.send_command(build_power(True))
            self.coordinator.is_on = True
            await send()
            await self._refresh_with_retry(expected_effect=f"video: {mode}", retry_command=send)
            c = self.coordinator
            c.effect, c.video_saturation, c.video_brightness = f"video: {mode}", saturation, brightness
            c.brightness_pct, c.video_full_screen = brightness, resolved_fs
            c.video_sound_effects, c.video_sound_effects_softness = sound_effects, sound_effects_softness
        self._notify_state_changed()

    async def async_set_music_mode(self, mode: str, sensitivity: int = 100,
            color: tuple[int, int, int] | None = None, calm: bool | None = None) -> None:
        self._require_h6199("set_music_mode")
        with self._rollback():
            mode_id = MUSIC_MODE_IDS[mode]
            resolved_calm = self.coordinator.music_calm if calm is None else calm
            packet = build_music_mode_with_color(
                mode_id,
                sensitivity=sensitivity,
                color=color,
                calm=resolved_calm if mode_id == RHYTHM_MODE_ID else False,
            )
            send = partial(self.coordinator.send_command, packet)
            await self.coordinator.send_command(build_power(True))
            self.coordinator.is_on = True
            await send()
            await self._refresh_with_retry(expected_effect=f"music: {mode}", retry_command=send)
            self.coordinator.effect = f"music: {mode}"
            self.coordinator.music_sensitivity, self.coordinator.music_color = sensitivity, color
            if mode_id == RHYTHM_MODE_ID:
                self.coordinator.music_calm = resolved_calm
        self._notify_state_changed()
