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
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, MUSIC_MODES
from .coordinator import GoveeBLECoordinator
from .entity import GoveeBLEEntity
from .light_services import (
    MUSIC_MODE_ALIASES,
    _GoveeLightServicesMixin,
)
from .light_services import MUSIC_MODE_IDS as MUSIC_MODE_IDS
from .light_services import apply_active_music_mode as apply_active_music_mode
from .light_services import apply_active_video_mode as apply_active_video_mode
from .protocol import (
    build_brightness,
    build_color_rgb,
    build_color_temp,
    build_power,
    build_scene_multi,
    kelvin_to_rgb,
)
from .scenes import SCENES, get_scene_names

# fmt: on

PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)

MIN_COLOR_TEMP_KELVIN = 2000
MAX_COLOR_TEMP_KELVIN = 9000

_EFFECT_QUOTE_CHARS = "\"'“”‘’"


def _normalize_effect_name(effect_name: str) -> str:
    return effect_name.strip().strip(_EFFECT_QUOTE_CHARS).strip().lower()


# First-class mode effects on the light effect list: display label -> mode slug. The light's effect
# list is the single mode selector (scene/custom/music/video); there is no parallel mode Select.
_VIDEO_EFFECTS: dict[str, str] = {"Video: Movie": "movie", "Video: Game": "game"}
_MUSIC_EFFECTS: dict[str, str] = {f"Music: {name.title()}": name.replace(" ", "_") for name in MUSIC_MODES}


_DEFAULT_SEGMENT_COLOR: tuple[int, int, int] = (255, 255, 255)


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
    "is_on brightness_pct rgb_color color_temp_kelvin effect video_saturation segment_colors "
    "video_full_screen video_sound_effects video_sound_effects_softness white_brightness music_sensitivity "
    "music_calm music_color active_custom_id music_mode video_mode"
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
    _rgb = vol.All(vol.ExactSequence((cv.byte, cv.byte, cv.byte)), vol.Coerce(tuple))
    # fmt: off
    p.async_register_entity_service("set_video_mode", {
        vol.Required("mode"): vol.In(["movie", "game"]),
        vol.Optional("saturation", default=100): _pct,
        vol.Optional("capture_region"): vol.In(["full", "part"]),
        vol.Optional("full_screen", default=True): cv.boolean,
        vol.Optional("sound_effects", default=False): cv.boolean,
        vol.Optional("sound_effects_softness", default=0): _pct,
    }, "async_set_video_mode")
    p.async_register_entity_service("set_music_mode", {
        vol.Required("mode"): vol.In([*MUSIC_MODE_IDS, *MUSIC_MODE_ALIASES]),
        vol.Optional("sensitivity", default=99): _pct,
        vol.Optional("calm"): cv.boolean,
        vol.Optional("color"): vol.All(vol.ExactSequence((cv.byte, cv.byte, cv.byte)), vol.Coerce(tuple)),
    }, "async_set_music_mode")
    p.async_register_entity_service("set_white_brightness", {
        vol.Optional("brightness", default=100): _pct,
    }, "async_set_white_brightness")
    p.async_register_entity_service("paint_segments", {
        vol.Required("groups"): [{
            vol.Required("segments"): [_segment],
            vol.Required("rgb_color"): _rgb,
        }],
    }, "async_paint_segments")
    p.async_register_entity_service("set_segment_color", {
        vol.Required("segments"): [_segment],
        vol.Required("color"): _rgb,
    }, "async_set_segment_color")
    p.async_register_entity_service("set_segment_brightness", {
        vol.Required("segments"): [_segment],
        vol.Required("brightness"): _pct,
    }, "async_set_segment_brightness")
    p.async_register_entity_service("save_effect", {
        vol.Required("name"): cv.string,
        vol.Optional("content"): dict,
        vol.Optional("capture_current", default=False): cv.boolean,
    }, "async_save_effect")
    p.async_register_entity_service("delete_effect", {
        vol.Optional("id"): cv.string,
        vol.Optional("name"): cv.string,
    }, "async_delete_effect")
    p.async_register_entity_service("rename_effect", {
        vol.Optional("id"): cv.string,
        vol.Optional("from_name"): cv.string,
        vol.Required("to"): cv.string,
    }, "async_rename_effect")
    # fmt: on


class GoveeBLELight(_GoveeLightServicesMixin, GoveeBLEEntity, RestoreEntity, LightEntity):
    _attr_name = None
    _attr_supported_color_modes = {ColorMode.RGB, ColorMode.COLOR_TEMP}
    _attr_supported_features = LightEntityFeature.EFFECT
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
        for label, mode in _VIDEO_EFFECTS.items():
            if mode == self.coordinator.video_mode:
                return label
        for label, slug in _MUSIC_EFFECTS.items():
            if slug == self.coordinator.music_mode:
                return label
        return self.coordinator.effect

    @property
    def effect_list(self) -> list[str]:
        p = self.coordinator.profile
        scenes = get_scene_names() if p.scene_source == "api" else []
        music = list(_MUSIC_EFFECTS) if p.supports_music_mode else []
        video = list(_VIDEO_EFFECTS) if p.supports_video_mode else []
        return [*scenes, *self.coordinator.custom_effect_display_names(), *music, *video]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {"custom_effects": self.coordinator.custom_effect_index()}
        if self.coordinator.profile.supports_segments:
            attrs["segment_colors"] = [list(color) for color in self.coordinator.segment_colors]
        return attrs

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        await self._async_restore_effect()
        await self._async_restore_segments()

    async def _async_restore_effect(self) -> None:
        coordinator = self.coordinator
        if (
            coordinator.effect is not None
            or coordinator.active_custom_id is not None
            or coordinator.music_mode != "off"
            or coordinator.video_mode != "off"
        ):
            return
        if (last_state := await self.async_get_last_state()) is None:
            return
        if not (restored := last_state.attributes.get(ATTR_EFFECT)):
            return
        key = _normalize_effect_name(str(restored))
        if (effect := coordinator.resolve_custom(key)) is not None:
            coordinator.active_custom_id, coordinator.effect = effect.id, effect.display_name
        elif key in SCENES:
            coordinator.effect = key

    async def _async_restore_segments(self) -> None:
        coordinator = self.coordinator
        count = coordinator.profile.segment_count
        if not count or coordinator.segment_colors != [_DEFAULT_SEGMENT_COLOR] * count:
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
        if (effect := coordinator.resolve_custom(key)) is not None:
            await coordinator.async_apply_custom_effect(effect.id)
            return
        scene = SCENES.get(key)
        if scene is not None:
            for packet in build_scene_multi(scene.param, scene.code, scene.scene_type):
                await coordinator.send_command(packet)
            coordinator.effect, coordinator.active_custom_id = key, None
            coordinator.music_mode = coordinator.video_mode = "off"
            return
        if coordinator.profile.supports_video_mode:
            mode = next((m for label, m in _VIDEO_EFFECTS.items() if _normalize_effect_name(label) == key), None)
            if mode is not None:
                await self.async_set_video_mode(mode=mode)
                return
        if coordinator.profile.supports_music_mode:
            slug = next((s for label, s in _MUSIC_EFFECTS.items() if _normalize_effect_name(label) == key), None)
            if slug is not None:
                await coordinator.async_select_music_slug(slug)
                return
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="unknown_effect",
            translation_placeholders={"effect": key},
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        power_on = partial(self.coordinator.send_command, build_power(True))
        with self._rollback():
            if not self.coordinator.is_on:
                await power_on()
                self.coordinator.is_on = True
                await self._refresh_with_retry(expected_on=True, retry_command=power_on)
            if ATTR_BRIGHTNESS in kwargs:
                pct = max(1, min(100, round(kwargs[ATTR_BRIGHTNESS] * 100 / 255)))
                await self.coordinator.send_command(build_brightness(pct))
                self.coordinator.brightness_pct = pct
            if ATTR_RGB_COLOR in kwargs:
                r, g, b = kwargs[ATTR_RGB_COLOR]
                await self.coordinator.send_command(build_color_rgb(r, g, b))
                self.coordinator.rgb_color = (r, g, b)
                self.coordinator.segment_colors = [(r, g, b)] * len(self.coordinator.segment_colors)
                self._attr_color_mode, self.coordinator.color_temp_kelvin = ColorMode.RGB, None
                self.coordinator._enter_static_mode()
            if ATTR_COLOR_TEMP_KELVIN in kwargs:
                kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
                await self.coordinator.send_command(build_color_temp(kelvin))
                self.coordinator.color_temp_kelvin = kelvin
                self.coordinator.segment_colors = [kelvin_to_rgb(kelvin)] * len(self.coordinator.segment_colors)
                self._attr_color_mode = ColorMode.COLOR_TEMP
                self.coordinator._enter_static_mode()
            if ATTR_EFFECT in kwargs:
                await self._apply_effect(str(kwargs[ATTR_EFFECT]))
        self._notify_state_changed()

    async def async_turn_off(self, **kwargs: Any) -> None:
        power_off = partial(self.coordinator.send_command, build_power(False))
        with self._rollback():
            await power_off()
            self.coordinator.is_on = False
            await self._refresh_with_retry(expected_on=False, retry_command=power_off)
        self._notify_state_changed()
