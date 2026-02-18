"""Light entity for Govee BLE Lights."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

import voluptuous as vol
from homeassistant.components.light import (
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

from .const import DOMAIN, ModelProfile
from .coordinator import GoveeBLECoordinator
from .h6199_effects import (
    MUSIC_MODE_IDS,
    apply_video_mode_from_state,
    music_mode_id_from_effect,
    video_game_mode_from_effect,
)
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

_LOGGER = logging.getLogger(__name__)

# Color temp range (Kelvin)
MIN_COLOR_TEMP_KELVIN = 2000
MAX_COLOR_TEMP_KELVIN = 9000

# Service names
SERVICE_SET_VIDEO_MODE = "set_video_mode"
SERVICE_SET_MUSIC_MODE = "set_music_mode"


def _build_effect_list(profile: ModelProfile) -> list[str]:
    """Build the effect list based on model capabilities."""
    effects: list[str] = []
    if profile.scene_source == "api":
        effects.extend(get_scene_names())
    effects.extend(profile.effects)
    return effects


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Govee BLE light from a config entry."""
    coordinator: GoveeBLECoordinator = config_entry.runtime_data
    async_add_entities([GoveeBLELight(coordinator, config_entry)])

    platform = entity_platform.async_get_current_platform()

    platform.async_register_entity_service(
        SERVICE_SET_VIDEO_MODE,
        {
            vol.Required("mode"): vol.In(["movie", "game"]),
            vol.Optional("saturation", default=100): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
            vol.Optional("brightness", default=100): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
            vol.Optional("capture_region"): vol.In(["full", "part"]),
            vol.Optional("full_screen", default=True): cv.boolean,
            vol.Optional("sound_effects", default=False): cv.boolean,
            vol.Optional("sound_effects_softness", default=0): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
        },
        "async_set_video_mode",
    )

    platform.async_register_entity_service(
        SERVICE_SET_MUSIC_MODE,
        {
            vol.Required("mode"): vol.In(["energic", "rhythm", "spectrum", "rolling"]),
            vol.Optional("sensitivity", default=100): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
            vol.Optional("color"): vol.All(vol.ExactSequence((cv.byte, cv.byte, cv.byte)), vol.Coerce(tuple)),
        },
        "async_set_music_mode",
    )


class GoveeBLELight(CoordinatorEntity[GoveeBLECoordinator], LightEntity):
    """Representation of a Govee BLE light."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_color_modes = {ColorMode.RGB, ColorMode.COLOR_TEMP, ColorMode.ONOFF}
    _attr_supported_features = LightEntityFeature.EFFECT
    _attr_min_color_temp_kelvin = MIN_COLOR_TEMP_KELVIN
    _attr_max_color_temp_kelvin = MAX_COLOR_TEMP_KELVIN

    def __init__(
        self,
        coordinator: GoveeBLECoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the light."""
        super().__init__(coordinator)
        self._address = coordinator.address
        self._model = coordinator.model
        self._profile = coordinator.profile
        self._attr_unique_id = coordinator.address.replace(":", "").lower()
        self._attr_device_info = coordinator.device_info
        self._attr_color_mode = ColorMode.RGB
        self._effect_list = _build_effect_list(self._profile)

    @property
    def is_on(self) -> bool:
        """Return true if light is on."""
        return self.coordinator.is_on

    @property
    def brightness(self) -> int | None:
        """Return the brightness (0-255)."""
        return round(self.coordinator.brightness_pct * 255 / 100)

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        """Return the RGB color."""
        if self._attr_color_mode == ColorMode.RGB:
            return self.coordinator.rgb_color
        return None

    @property
    def color_temp_kelvin(self) -> int | None:
        """Return the color temperature in Kelvin."""
        if self._attr_color_mode == ColorMode.COLOR_TEMP:
            return self.coordinator.color_temp_kelvin
        return None

    @property
    def effect(self) -> str | None:
        """Return the current effect."""
        return self.coordinator.effect

    @property
    def effect_list(self) -> list[str]:
        """Return the list of supported effects."""
        return self._effect_list

    async def _refresh_state_with_retry(
        self,
        *,
        expected_effect: str | None = None,
        expected_on: bool | None = None,
        retry_command: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        """Refresh state for state-readable devices and retry once if needed."""
        if not self._profile.state_readable:
            return
        if await self.coordinator.refresh_state(expected_effect=expected_effect, expected_on=expected_on):
            return
        if retry_command is not None:
            await retry_command()
        if await self.coordinator.refresh_state(expected_effect=expected_effect, expected_on=expected_on):
            return
        raise RuntimeError(f"Failed to confirm state for {self._model}: effect={expected_effect} power={expected_on}")

    def _notify_state_changed(self) -> None:
        """Sync HA state after an optimistic update."""
        self.async_write_ha_state()
        self.coordinator.async_set_updated_data(self.coordinator.data or {})

    async def _apply_effect(self, effect_name: str) -> bool:
        """Apply an effect by name. Returns True if handled."""
        game_mode = video_game_mode_from_effect(effect_name)
        if game_mode is not None:

            async def _send_video_mode() -> None:
                await apply_video_mode_from_state(self.coordinator, game_mode=game_mode)
                await self.coordinator.send_command(build_brightness(self.coordinator.video_brightness))

            await _send_video_mode()
            self.coordinator.brightness_pct = self.coordinator.video_brightness
            await self._refresh_state_with_retry(
                expected_effect=effect_name,
                retry_command=_send_video_mode,
            )
            return True

        # Music modes (H6199)
        music_id = music_mode_id_from_effect(effect_name)
        if music_id is not None:

            async def _send_music_mode() -> None:
                await self.coordinator.send_command(
                    build_music_mode_with_color(
                        music_id,
                        sensitivity=self.coordinator.music_sensitivity,
                        color=self.coordinator.music_color,
                    )
                )

            await _send_music_mode()
            await self._refresh_state_with_retry(
                expected_effect=effect_name,
                retry_command=_send_music_mode,
            )
            return True

        # Scenes (H617A)
        scene = SCENES.get(effect_name)
        if scene is not None:
            if scene.is_simple:
                await self.coordinator.send_command(build_scene(scene.code))
            else:
                packets = build_scene_multi(scene.param, scene.code)
                await self.coordinator.send_commands(packets)
            return True

        return False

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        prev_on = self.coordinator.is_on
        prev_brightness = self.coordinator.brightness_pct
        prev_rgb = self.coordinator.rgb_color
        prev_temp = self.coordinator.color_temp_kelvin
        prev_effect = self.coordinator.effect
        prev_mode = self._attr_color_mode

        try:

            async def _send_power_on() -> None:
                await self.coordinator.send_command(build_power(True))

            await _send_power_on()
            self.coordinator.is_on = True
            self.coordinator.effect = None
            await self._refresh_state_with_retry(expected_on=True, retry_command=_send_power_on)

            if ATTR_BRIGHTNESS in kwargs:
                brightness_255 = kwargs[ATTR_BRIGHTNESS]
                brightness_pct = max(1, min(100, round(brightness_255 * 100 / 255)))
                await self.coordinator.send_command(build_brightness(brightness_pct))
                self.coordinator.brightness_pct = brightness_pct

            if ATTR_RGB_COLOR in kwargs:
                r, g, b = kwargs[ATTR_RGB_COLOR]
                await self.coordinator.send_command(build_color_rgb(r, g, b))
                self.coordinator.rgb_color = (r, g, b)
                self._attr_color_mode = ColorMode.RGB
                self.coordinator.color_temp_kelvin = None
                self.coordinator.effect = None

            if ATTR_COLOR_TEMP_KELVIN in kwargs:
                kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
                await self.coordinator.send_command(build_color_temp(kelvin))
                self.coordinator.color_temp_kelvin = kelvin
                self._attr_color_mode = ColorMode.COLOR_TEMP
                self.coordinator.effect = None

            if ATTR_EFFECT in kwargs:
                effect_name = kwargs[ATTR_EFFECT]
                if await self._apply_effect(effect_name):
                    self.coordinator.effect = effect_name
        except Exception:
            self.coordinator.is_on = prev_on
            self.coordinator.brightness_pct = prev_brightness
            self.coordinator.rgb_color = prev_rgb
            self.coordinator.color_temp_kelvin = prev_temp
            self.coordinator.effect = prev_effect
            self._attr_color_mode = prev_mode
            raise

        self._notify_state_changed()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        prev_on = self.coordinator.is_on
        try:

            async def _send_power_off() -> None:
                await self.coordinator.send_command(build_power(False))

            await _send_power_off()
            self.coordinator.is_on = False
            await self._refresh_state_with_retry(expected_on=False, retry_command=_send_power_off)
        except Exception:
            self.coordinator.is_on = prev_on
            raise
        self._notify_state_changed()

    async def async_set_video_mode(
        self,
        mode: str,
        saturation: int = 100,
        brightness: int = 100,
        capture_region: str | None = None,
        full_screen: bool = True,
        sound_effects: bool = False,
        sound_effects_softness: int = 0,
    ) -> None:
        """Handle set_video_mode service call."""
        if self._model != "H6199":
            raise ServiceValidationError(
                f"set_video_mode is only supported on H6199, not {self._model}",
                translation_domain=DOMAIN,
                translation_key="unsupported_model",
            )
        prev_on = self.coordinator.is_on
        prev_effect = self.coordinator.effect
        prev_brightness = self.coordinator.brightness_pct
        prev_video_sat = self.coordinator.video_saturation
        prev_video_brightness = self.coordinator.video_brightness
        prev_video_fs = self.coordinator.video_full_screen
        prev_video_se = self.coordinator.video_sound_effects
        prev_video_ses = self.coordinator.video_sound_effects_softness
        try:
            resolved_full_screen = full_screen if capture_region is None else capture_region == "full"
            game_mode = mode == "game"
            packet = build_video_mode(
                full_screen=resolved_full_screen,
                game_mode=game_mode,
                saturation=saturation,
                sound_effects=sound_effects,
                sound_effects_softness=sound_effects_softness,
            )

            async def _send_video_mode() -> None:
                await self.coordinator.send_command(packet)
                await self.coordinator.send_command(build_brightness(brightness))

            await self.coordinator.send_command(build_power(True))
            self.coordinator.is_on = True
            await _send_video_mode()
            await self._refresh_state_with_retry(
                expected_effect=f"video: {mode}",
                retry_command=_send_video_mode,
            )
            self.coordinator.effect = f"video: {mode}"
            self.coordinator.video_saturation = saturation
            self.coordinator.video_brightness = brightness
            self.coordinator.brightness_pct = brightness
            self.coordinator.video_full_screen = resolved_full_screen
            self.coordinator.video_sound_effects = sound_effects
            self.coordinator.video_sound_effects_softness = sound_effects_softness
        except Exception:
            self.coordinator.is_on = prev_on
            self.coordinator.effect = prev_effect
            self.coordinator.brightness_pct = prev_brightness
            self.coordinator.video_saturation = prev_video_sat
            self.coordinator.video_brightness = prev_video_brightness
            self.coordinator.video_full_screen = prev_video_fs
            self.coordinator.video_sound_effects = prev_video_se
            self.coordinator.video_sound_effects_softness = prev_video_ses
            raise
        self._notify_state_changed()

    async def async_set_music_mode(
        self,
        mode: str,
        sensitivity: int = 100,
        color: tuple[int, int, int] | None = None,
    ) -> None:
        """Handle set_music_mode service call."""
        if self._model != "H6199":
            raise ServiceValidationError(
                f"set_music_mode is only supported on H6199, not {self._model}",
                translation_domain=DOMAIN,
                translation_key="unsupported_model",
            )
        prev_on = self.coordinator.is_on
        prev_effect = self.coordinator.effect
        prev_sensitivity = self.coordinator.music_sensitivity
        prev_color = self.coordinator.music_color
        try:
            mode_id = MUSIC_MODE_IDS[mode]
            packet = build_music_mode_with_color(mode_id, sensitivity=sensitivity, color=color)

            async def _send_music_mode() -> None:
                await self.coordinator.send_command(packet)

            await self.coordinator.send_command(build_power(True))
            self.coordinator.is_on = True
            await _send_music_mode()
            await self._refresh_state_with_retry(
                expected_effect=f"music: {mode}",
                retry_command=_send_music_mode,
            )
            self.coordinator.effect = f"music: {mode}"
            self.coordinator.music_sensitivity = sensitivity
            self.coordinator.music_color = color
        except Exception:
            self.coordinator.is_on = prev_on
            self.coordinator.effect = prev_effect
            self.coordinator.music_sensitivity = prev_sensitivity
            self.coordinator.music_color = prev_color
            raise
        self._notify_state_changed()
