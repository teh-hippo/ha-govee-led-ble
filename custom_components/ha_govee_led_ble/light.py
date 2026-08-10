"""Light entity for HA Govee LED BLE."""

# fmt: off
import logging
from collections.abc import Awaitable, Callable, Generator
from contextlib import contextmanager
from functools import partial
from typing import Any

import voluptuous as vol
from homeassistant.components.light import (  # type: ignore[attr-defined]
    ATTR_BRIGHTNESS,
    ATTR_COLOR_MODE,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_EFFECT,
    ATTR_RGB_COLOR,
    EFFECT_OFF,
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
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DOMAIN,
    EFFECT_FAMILY_MUSIC,
    EFFECT_FAMILY_SCENES,
    EFFECT_FAMILY_VIDEO,
    MUSIC_MODES,
    ModelProfile,
)
from .coordinator import GoveeBLECoordinator
from .entity import GoveeBLEEntity
from .light_services import (
    _GoveeLightServicesMixin,
)
from .light_services import apply_active_video_mode as apply_active_video_mode
from .protocol import (
    ParsedMode,
    build_brightness,
    build_color_rgb,
    build_color_temp,
    build_h6199_scene_multi,
    build_power,
    build_scene_multi,
    kelvin_to_rgb,
)
from .scenes import MODEL_SCENE_LABELS, MODEL_SCENES, SceneEntry

# fmt: on

PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)

MIN_COLOR_TEMP_KELVIN = 2000
MAX_COLOR_TEMP_KELVIN = 9000

_EFFECT_QUOTE_CHARS = "\"'“”‘’"


def _normalize_effect_name(effect_name: str) -> str:
    stripped = effect_name.strip().strip(_EFFECT_QUOTE_CHARS).strip()
    return " ".join(stripped.split()).casefold()


# First-class mode effects on the light effect list: display label -> mode slug.
_VIDEO_EFFECTS: dict[str, str] = {"Video: Movie": "movie", "Video: Game": "game"}
_MUSIC_EFFECTS: dict[str, str] = {f"Music: {name.title()}": name.replace(" ", "_") for name in MUSIC_MODES}


_DEFAULT_SEGMENT_COLOR: tuple[int, int, int] = (255, 255, 255)


def _scene_packets(profile: ModelProfile, scene: SceneEntry, *, speed_index: int | None = None) -> list[bytes]:
    """Pick the activation the model's own app sends, which is not the same frame on both.

    The H6199 write carries a third byte saying whether the light already holds the scene, and
    the H617A write is two bytes with nothing there. Sharing one builder sent an H617A frame to
    an H6199, which differs from the captured one at exactly that byte.
    """
    if profile.uses_h6199_scene_protocol:
        return build_h6199_scene_multi(scene.param, scene.code, scene.scene_type, scene.music_code)
    return build_scene_multi(scene.param, scene.code, scene.scene_type, scene.speed, speed_index=speed_index)


def _coerce_rgb(raw: Any) -> tuple[int, int, int] | None:
    if not isinstance(raw, list | tuple) or len(raw) != 3:
        return None
    try:
        red, green, blue = (int(channel) for channel in raw)
    except TypeError, ValueError:
        return None
    return (
        max(0, min(255, red)),
        max(0, min(255, green)),
        max(0, min(255, blue)),
    )


def _coerce_segment_colors(raw: Any, count: int) -> list[tuple[int, int, int]] | None:
    """Validate a restored ``segment_colors`` attribute into RGB tuples, or None if malformed."""
    if not isinstance(raw, list) or len(raw) != count:
        return None
    colors: list[tuple[int, int, int]] = []
    for item in raw:
        if not isinstance(item, list | tuple) or len(item) != 3:
            return None
        try:
            r, g, b = int(item[0]), int(item[1]), int(item[2])
        except TypeError, ValueError:
            return None
        colors.append((max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))))
    return colors


_STATE_FIELDS = (
    "is_on brightness_pct rgb_color color_temp_kelvin effect video_saturation "
    "segment_colors video_full_screen video_sound_effects video_sound_effects_softness "
    "white_brightness music_sensitivity "
    "music_calm music_color diy_code music_mode video_mode"
).split()


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([GoveeBLELight(config_entry.runtime_data)])
    p = entity_platform.async_get_current_platform()
    _pct = vol.All(vol.Coerce(int), vol.Range(min=0, max=100))
    _segment = vol.All(vol.Coerce(int), vol.Range(min=1, max=15))
    _segments = vol.All([_segment], vol.Length(min=1))
    _rgb = vol.All(vol.ExactSequence((cv.byte, cv.byte, cv.byte)), vol.Coerce(tuple))
    # fmt: off
    p.async_register_entity_service("paint_segments", {
        vol.Required("groups"): vol.All([{
            vol.Required("segments"): _segments,
            vol.Required("rgb_color"): _rgb,
        }], vol.Length(min=1)),
    }, "async_paint_segments")
    p.async_register_entity_service("set_segment_color", {
        vol.Required("segments"): _segments,
        vol.Required("color"): _rgb,
    }, "async_set_segment_color")
    p.async_register_entity_service("set_segment_brightness", {
        vol.Required("segments"): _segments,
        vol.Required("brightness"): _pct,
    }, "async_set_segment_brightness")
    # fmt: on


class GoveeBLELight(_GoveeLightServicesMixin, GoveeBLEEntity, RestoreEntity, LightEntity):
    _attr_name = None
    _attr_supported_color_modes = {ColorMode.RGB, ColorMode.COLOR_TEMP}
    _attr_min_color_temp_kelvin = MIN_COLOR_TEMP_KELVIN
    _attr_max_color_temp_kelvin = MAX_COLOR_TEMP_KELVIN

    def __init__(self, coordinator: GoveeBLECoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = coordinator.address.replace(":", "").lower()
        self._attr_device_info = coordinator.device_info
        self._attr_color_mode = ColorMode.RGB

    @contextmanager
    def _rollback(self) -> Generator[None]:
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
        families = self.coordinator.effect_families
        if EFFECT_FAMILY_VIDEO in families:
            for label, mode in _VIDEO_EFFECTS.items():
                if mode == self.coordinator.video_mode:
                    return label
        if EFFECT_FAMILY_MUSIC in families:
            for label, slug in _MUSIC_EFFECTS.items():
                if slug == self.coordinator.music_mode:
                    return label
        if EFFECT_FAMILY_SCENES in families and self.coordinator.effect is not None:
            return MODEL_SCENE_LABELS[self.coordinator.model].get(self.coordinator.effect)
        return EFFECT_OFF if self.effect_list else None

    @property
    def supported_features(self) -> LightEntityFeature:
        return LightEntityFeature.EFFECT if self.effect_list else LightEntityFeature(0)

    @property
    def effect_list(self) -> list[str]:
        p = self.coordinator.profile
        families = self.coordinator.effect_families
        scenes = (
            sorted(MODEL_SCENE_LABELS[self.coordinator.model].values(), key=str.casefold)
            if EFFECT_FAMILY_SCENES in families
            else []
        )
        music = (
            [label for label, slug in _MUSIC_EFFECTS.items() if slug in p.music_modes]
            if EFFECT_FAMILY_MUSIC in families
            else []
        )
        video = list(_VIDEO_EFFECTS) if EFFECT_FAMILY_VIDEO in families else []
        return [*scenes, *music, *video]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {}
        if (scene_code := self.coordinator.unknown_scene_code) is not None:
            attrs["unknown_scene_code"] = scene_code
        if self.coordinator.profile.supports_segments:
            attrs["segment_colors"] = [list(color) for color in self.coordinator.segment_colors]
        return attrs

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        await self._async_restore_static_color()
        await self._async_restore_segments()

    async def _async_restore_static_color(self) -> None:
        coordinator = self.coordinator
        if coordinator.color_mode not in (None, ParsedMode.COLOUR):
            return
        if (
            coordinator.effect is not None
            or coordinator.diy_code is not None
            or coordinator.music_mode != "off"
            or coordinator.video_mode != "off"
        ):
            return
        if (last_state := await self.async_get_last_state()) is None:
            return
        if last_state.attributes.get(ATTR_EFFECT):
            return
        raw_mode = last_state.attributes.get(ATTR_COLOR_MODE)
        if isinstance(raw_mode, ColorMode):
            restored_mode = raw_mode
        elif isinstance(raw_mode, str):
            try:
                restored_mode = ColorMode(raw_mode)
            except ValueError:
                return
        else:
            return
        if restored_mode is ColorMode.RGB:
            if (rgb := _coerce_rgb(last_state.attributes.get(ATTR_RGB_COLOR))) is None:
                return
            coordinator.rgb_color = rgb
            coordinator.color_temp_kelvin = None
            if (
                _coerce_segment_colors(last_state.attributes.get("segment_colors"), len(coordinator.segment_colors))
                is None
            ):
                coordinator.segment_colors = [rgb] * len(coordinator.segment_colors)
        elif restored_mode is ColorMode.COLOR_TEMP:
            try:
                kelvin = int(last_state.attributes[ATTR_COLOR_TEMP_KELVIN])
            except KeyError, TypeError, ValueError:
                return
            if not MIN_COLOR_TEMP_KELVIN <= kelvin <= MAX_COLOR_TEMP_KELVIN:
                return
            coordinator.color_temp_kelvin = kelvin
            if (
                _coerce_segment_colors(last_state.attributes.get("segment_colors"), len(coordinator.segment_colors))
                is None
            ):
                coordinator.segment_colors = [kelvin_to_rgb(kelvin)] * len(coordinator.segment_colors)
        else:
            return
        self._attr_color_mode = restored_mode
        coordinator.async_set_updated_data(coordinator.data or {})

    async def _async_restore_segments(self) -> None:
        coordinator = self.coordinator
        count = coordinator.profile.segment_count
        if not count or coordinator.segment_colors != [_DEFAULT_SEGMENT_COLOR] * count:
            return
        if coordinator.color_mode not in (None, ParsedMode.COLOUR):
            return
        if coordinator.music_mode != "off" or coordinator.video_mode != "off" or coordinator.diy_code is not None:
            return
        if coordinator.effect is not None:
            return
        if (last_state := await self.async_get_last_state()) is None:
            return
        restored = _coerce_segment_colors(last_state.attributes.get("segment_colors"), count)
        if restored is None:
            return
        coordinator.segment_colors = restored
        coordinator.async_set_updated_data(coordinator.data or {})

    async def _refresh_with_retry(
        self,
        *,
        expected_effect: str | None = None,
        expected_on: bool | None = None,
        expected_brightness: int | None = None,
        expected_music_mode: str | None = None,
        expected_music_sensitivity: int | None = None,
        expected_music_calm: bool | None = None,
        expected_music_color: tuple[int, int, int] | None = None,
        expected_music_auto_color: bool = False,
        expected_video_mode: str | None = None,
        expected_video_full_screen: bool | None = None,
        expected_video_saturation: int | None = None,
        expected_video_sound_effects: bool | None = None,
        expected_video_sound_effects_softness: int | None = None,
        expected_white_brightness: int | None = None,
        retry_command: Callable[[], Awaitable[None]] | None = None,
        required: bool = True,
    ) -> None:
        if not self.coordinator.profile.state_readable:
            return
        confirm = partial(
            self.coordinator.refresh_state,
            expected_effect=expected_effect,
            expected_on=expected_on,
            expected_brightness=expected_brightness,
            expected_music_mode=expected_music_mode,
            expected_music_sensitivity=expected_music_sensitivity,
            expected_music_calm=expected_music_calm,
            expected_music_color=expected_music_color,
            expected_music_auto_color=expected_music_auto_color,
            expected_video_mode=expected_video_mode,
            expected_video_full_screen=expected_video_full_screen,
            expected_video_saturation=expected_video_saturation,
            expected_video_sound_effects=expected_video_sound_effects,
            expected_video_sound_effects_softness=expected_video_sound_effects_softness,
            expected_white_brightness=expected_white_brightness,
        )
        if await confirm():
            return
        if retry_command is not None:
            await retry_command()
        if not await confirm() and required:
            raise RuntimeError(f"Failed to confirm state for {self.coordinator.model}")

    def _notify_state_changed(self) -> None:
        self.async_write_ha_state()
        self.coordinator.async_set_updated_data(self.coordinator.data or {})

    def _require_support(self, service: str, *, supported: bool) -> None:
        if supported:
            return
        model = self.coordinator.model
        raise ServiceValidationError(
            f"{service} is not supported on {model}",
            translation_domain=DOMAIN,
            translation_key="unsupported_model",
            translation_placeholders={"service": service, "model": model},
        )

    async def _apply_effect(self, effect_name: str) -> None:
        key = _normalize_effect_name(effect_name)
        coordinator = self.coordinator
        scene = (
            MODEL_SCENES[coordinator.model].get(key) if EFFECT_FAMILY_SCENES in coordinator.effect_families else None
        )
        if scene is not None:
            speed_index = coordinator.scene_speed_index if coordinator.scene_speed_scene_code == scene.code else None
            for packet in _scene_packets(coordinator.profile, scene, speed_index=speed_index):
                await coordinator.send_command(packet)
            coordinator.effect = key
            coordinator.diy_code = None
            coordinator.music_mode = coordinator.video_mode = "off"
            coordinator._sync_scene_speed(key, speed_index=speed_index)
            return
        if EFFECT_FAMILY_VIDEO in coordinator.effect_families:
            mode = next((m for label, m in _VIDEO_EFFECTS.items() if _normalize_effect_name(label) == key), None)
            if mode is not None:
                await self._async_set_video_mode(
                    mode=mode,
                    saturation=coordinator.video_saturation,
                    full_screen=coordinator.video_full_screen,
                    sound_effects=(
                        coordinator.video_sound_effects and coordinator.profile.supports_video_sound_effects
                    ),
                    sound_effects_softness=coordinator.video_sound_effects_softness,
                )
                return
        if EFFECT_FAMILY_MUSIC in coordinator.effect_families:
            slug = next(
                (
                    candidate
                    for label, candidate in _MUSIC_EFFECTS.items()
                    if _normalize_effect_name(label) == key and candidate in coordinator.profile.music_modes
                ),
                None,
            )
            if slug is not None:
                await coordinator.async_select_music_slug(slug)
                return
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="unknown_effect",
            translation_placeholders={"effect": key},
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        async with self.coordinator._control_lock:
            await self._async_turn_on(**kwargs)

    async def _async_turn_on(self, **kwargs: Any) -> None:
        power_on = partial(
            self.coordinator.send_command,
            build_power(True, self.coordinator.model),
        )
        with self._rollback():
            if not self.coordinator.is_on:
                await power_on()
                self.coordinator.is_on = True
                await self._refresh_with_retry(expected_on=True, retry_command=power_on)
            if ATTR_BRIGHTNESS in kwargs:
                pct = max(1, min(100, round(kwargs[ATTR_BRIGHTNESS] * 100 / 255)))

                async def apply_brightness() -> None:
                    await self.coordinator.send_command(build_brightness(pct, self.coordinator.model))

                await apply_brightness()
                self.coordinator.brightness_pct = pct
                await self._refresh_with_retry(
                    expected_brightness=pct,
                    retry_command=apply_brightness,
                )
            if ATTR_RGB_COLOR in kwargs:
                r, g, b = kwargs[ATTR_RGB_COLOR]
                await self.coordinator.send_command(build_color_rgb(r, g, b, self.coordinator.model))
                self.coordinator.rgb_color = (r, g, b)
                self.coordinator.segment_colors = [(r, g, b)] * len(self.coordinator.segment_colors)
                self._attr_color_mode, self.coordinator.color_temp_kelvin = ColorMode.RGB, None
                self.coordinator._enter_static_mode()
            if ATTR_COLOR_TEMP_KELVIN in kwargs:
                kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
                await self.coordinator.send_command(build_color_temp(kelvin, self.coordinator.model))
                self.coordinator.color_temp_kelvin = kelvin
                self.coordinator.segment_colors = [kelvin_to_rgb(kelvin)] * len(self.coordinator.segment_colors)
                self._attr_color_mode = ColorMode.COLOR_TEMP
                self.coordinator._enter_static_mode()
            if ATTR_EFFECT in kwargs:
                await self._apply_effect(str(kwargs[ATTR_EFFECT]))
        self._notify_state_changed()

    async def async_turn_off(self, **kwargs: Any) -> None:
        async with self.coordinator._control_lock:
            await self._async_turn_off(**kwargs)

    async def _async_turn_off(self, **kwargs: Any) -> None:
        power_off = partial(
            self.coordinator.send_command,
            build_power(False, self.coordinator.model),
        )
        with self._rollback():
            await power_off()
            self.coordinator.is_on = False
            await self._refresh_with_retry(expected_on=False, retry_command=power_off)
        self._notify_state_changed()
