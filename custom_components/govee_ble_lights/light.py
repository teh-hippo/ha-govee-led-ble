"""Light entity for Govee BLE Lights."""

from __future__ import annotations

import logging
from typing import Any

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
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, ModelProfile
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

_LOGGER = logging.getLogger(__name__)

# Color temp range (Kelvin)
MIN_COLOR_TEMP_KELVIN = 2000
MAX_COLOR_TEMP_KELVIN = 9000

# H6199 music mode sub-IDs
_MUSIC_MODES: dict[str, int] = {
    "music: energic": 0x05,
    "music: rhythm": 0x03,
    "music: spectrum": 0x04,
    "music: rolling": 0x06,
}


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
    coordinator: GoveeBLECoordinator = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([GoveeBLELight(coordinator, config_entry)])


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
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            name=f"Govee {self._model}",
            manufacturer="Govee",
            model=self._model,
        )
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

    async def _apply_effect(self, effect_name: str) -> bool:
        """Apply an effect by name. Returns True if handled."""
        # Video modes (H6199)
        if effect_name == "video: movie":
            await self.coordinator.send_command(build_video_mode(full_screen=True, game_mode=False))
            return True
        if effect_name == "video: game":
            await self.coordinator.send_command(build_video_mode(full_screen=True, game_mode=True))
            return True

        # Music modes (H6199)
        music_id = _MUSIC_MODES.get(effect_name)
        if music_id is not None:
            await self.coordinator.send_command(build_music_mode_with_color(music_id))
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
            await self.coordinator.send_command(build_power(True))
            self.coordinator.is_on = True
            self.coordinator.effect = None

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

        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        prev_on = self.coordinator.is_on
        try:
            await self.coordinator.send_command(build_power(False))
            self.coordinator.is_on = False
        except Exception:
            self.coordinator.is_on = prev_on
            raise
        self.async_write_ha_state()
