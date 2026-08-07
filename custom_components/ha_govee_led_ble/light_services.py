"""Apply-helpers and entity-service mixin for the Govee BLE light."""

import logging
from collections.abc import Awaitable, Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import TYPE_CHECKING, Any

from homeassistant.components.light import ColorMode  # type: ignore[attr-defined]
from homeassistant.core import ServiceResponse
from homeassistant.exceptions import ServiceValidationError

from .const import DOMAIN, MUSIC_MODES
from .coordinator import GoveeBLECoordinator
from .coordinator_modes import MUSIC_STYLE_SLUGS
from .custom_effects import EffectValidationError, content_from_dict
from .protocol import (
    SegmentColorGroup,
    build_power,
    build_segment_brightness,
    build_video_mode,
    build_white_brightness,
)

# Deprecation warnings use the light entity's logger name.
_LOGGER = logging.getLogger("custom_components.ha_govee_led_ble.light")

MUSIC_MODE_IDS: dict[str, int] = MUSIC_MODES
MUSIC_MODE_ALIASES: dict[str, str] = {"energic": "energetic"}


@contextmanager
def _map_effect_errors(**placeholders: str) -> Iterator[None]:
    """Re-raise a coordinator ``EffectValidationError`` as a translated ``ServiceValidationError``."""
    try:
        yield
    except EffectValidationError as err:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key=err.key, translation_placeholders=placeholders or None
        ) from err
    except (TypeError, ValueError, OverflowError) as err:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_effect_content",
        ) from err


def _single_effect_ref(first: str | None, second: str | None, translation_key: str) -> str:
    """Return whichever identifier is set, or raise a translated error unless exactly one is given."""
    if first is not None and second is None:
        return first
    if first is None and second is not None:
        return second
    raise ServiceValidationError(translation_domain=DOMAIN, translation_key=translation_key)


# fmt: off
async def apply_video_mode_from_state(coord: GoveeBLECoordinator, *, game_mode: bool) -> None:
    sound_effects = coord.video_sound_effects and coord.profile.supports_video_sound_effects
    await coord.send_command(build_video_mode(full_screen=coord.video_full_screen, game_mode=game_mode,
        saturation=coord.video_saturation, sound_effects=sound_effects,
        sound_effects_softness=coord.video_sound_effects_softness))
    if not coord.profile.supports_video_sound_effects:
        coord.video_sound_effects = False
# fmt: on


async def apply_active_video_mode(coord: GoveeBLECoordinator) -> bool:
    if coord.video_mode not in ("movie", "game"):
        return False
    for _ in range(2):
        if not coord.is_on:
            await coord.send_command(build_power(True, coord.model))
            coord.is_on = True
        await apply_video_mode_from_state(coord, game_mode=coord.video_mode == "game")
        if await coord.refresh_state(
            expected_on=True,
            expected_video_mode=coord.video_mode,
            expected_video_full_screen=coord.video_full_screen,
            expected_video_saturation=coord.video_saturation,
            expected_video_sound_effects=coord.video_sound_effects,
            expected_video_sound_effects_softness=coord.video_sound_effects_softness,
        ):
            return True
    raise RuntimeError("Video-mode write was not confirmed by the device")


async def apply_active_music_mode(coord: GoveeBLECoordinator) -> bool:
    if not coord.is_on or coord.music_mode not in coord.profile.music_modes:
        return False
    for _ in range(2):
        await coord.async_select_music_slug(coord.music_mode)
        if await coord.refresh_state(
            expected_on=True,
            expected_music_mode=coord.music_mode,
            expected_music_sensitivity=coord.music_sensitivity,
            expected_music_calm=coord.music_calm if coord.music_mode == "rhythm" else None,
            expected_music_color=coord.music_color,
            expected_music_auto_color=coord.music_color is None,
        ):
            return True
    raise RuntimeError("Music-mode write was not confirmed by the device")


class _GoveeLightOwner:
    """Typed surface the service mixin relies on from ``GoveeBLELight``."""

    coordinator: GoveeBLECoordinator
    _attr_color_mode: ColorMode | None

    if TYPE_CHECKING:

        def _rollback(self) -> AbstractContextManager[None]: ...

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
        ) -> None: ...

        def _notify_state_changed(self) -> None: ...

        def _require_support(self, service: str, *, supported: bool) -> None: ...


class _GoveeLightServicesMixin(_GoveeLightOwner):
    """Entity-service methods for the Govee BLE light."""

    # fmt: off
    async def async_set_video_mode(self, mode: str, saturation: int = 100,
            capture_region: str | None = None, full_screen: bool = True,
            sound_effects: bool = False, sound_effects_softness: int | None = None) -> None:
        async with self.coordinator._control_lock:
            await self._async_set_video_mode(
                mode, saturation, capture_region, full_screen, sound_effects, sound_effects_softness
            )

    async def _async_set_video_mode(self, mode: str, saturation: int = 100,
            capture_region: str | None = None, full_screen: bool = True,
            sound_effects: bool = False, sound_effects_softness: int | None = None) -> None:
        # fmt: on
        self._require_support("set_video_mode", supported=self.coordinator.profile.supports_video_mode)
        if sound_effects:
            self._require_support(
                "video sound effects",
                supported=self.coordinator.profile.supports_video_sound_effects,
            )
        with self._rollback():
            c = self.coordinator
            resolved_fs = full_screen if capture_region is None else capture_region == "full"
            supports_sound = c.profile.supports_video_sound_effects
            resolved_sound = sound_effects and supports_sound
            resolved_softness = (
                c.video_sound_effects_softness if sound_effects_softness is None else sound_effects_softness
            )
            # fmt: off
            packet = build_video_mode(full_screen=resolved_fs, game_mode=mode == "game", saturation=saturation,
                sound_effects=resolved_sound, sound_effects_softness=resolved_softness)
            # fmt: on
            async def apply() -> None:
                await self.coordinator.send_command(
                    build_power(True, self.coordinator.model)
                )
                self.coordinator.is_on = True
                await self.coordinator.send_command(packet)

            await apply()
            await self._refresh_with_retry(
                expected_on=True,
                expected_video_mode=mode,
                expected_video_full_screen=resolved_fs,
                expected_video_saturation=saturation,
                expected_video_sound_effects=resolved_sound if supports_sound else None,
                expected_video_sound_effects_softness=resolved_softness if resolved_sound else None,
                retry_command=apply,
            )
            c.video_mode, c.effect = mode, None
            c.active_custom_id, c.music_mode = None, "off"
            c.diy_slot = None
            c._owned_diy_effect_id = None
            c.video_saturation, c.video_full_screen = saturation, resolved_fs
            c.video_sound_effects = resolved_sound
            if supports_sound:
                c.video_sound_effects_softness = resolved_softness
        self._notify_state_changed()

    async def async_set_music_mode(self, mode: str, sensitivity: int = 99,
            color: tuple[int, int, int] | None = None, calm: bool | None = None) -> None:
        async with self.coordinator._control_lock:
            await self._async_set_music_mode(mode, sensitivity, color, calm)

    async def _async_set_music_mode(self, mode: str, sensitivity: int = 99,
            color: tuple[int, int, int] | None = None, calm: bool | None = None) -> None:
        if mode in MUSIC_MODE_ALIASES:
            canonical = MUSIC_MODE_ALIASES[mode]
            _LOGGER.warning("Music mode '%s' is deprecated; use '%s' instead", mode, canonical)
            mode = canonical
        slug = mode.replace(" ", "_")
        self._require_support("set_music_mode", supported=slug in self.coordinator.profile.music_modes)
        if color is not None:
            self._require_support(
                "set_music_mode",
                supported=self.coordinator.profile.supports_music_color,
            )
        if calm is not None:
            self._require_support(
                "set_music_mode",
                supported=self.coordinator.profile.supports_music_style and slug in MUSIC_STYLE_SLUGS,
            )
        with self._rollback():
            c = self.coordinator
            resolved_sensitivity = max(
                c.profile.music_sensitivity_min,
                min(sensitivity, c.profile.music_sensitivity_max),
            )
            if slug in MUSIC_STYLE_SLUGS and calm is not None:
                c.music_calm = calm
            style_calm = c.music_calm if slug in MUSIC_STYLE_SLUGS else None
            # Rhythm reflects STYLE in its status reply; Bloom/Shiny repurpose that byte, so their
            # calm is written optimistically but not verified on read-back.
            verify_calm = c.music_calm if slug == "rhythm" else None

            async def apply() -> None:
                c.music_sensitivity, c.music_color = resolved_sensitivity, color
                if style_calm is not None:
                    c.music_calm = style_calm
                await c.async_select_music_slug(slug)

            await apply()
            await self._refresh_with_retry(
                expected_on=True,
                expected_music_mode=slug,
                expected_music_sensitivity=resolved_sensitivity,
                expected_music_calm=verify_calm,
                expected_music_color=color,
                expected_music_auto_color=color is None,
                retry_command=apply,
            )
        self._notify_state_changed()

    async def async_set_white_brightness(self, brightness: int = 100) -> None:
        async with self.coordinator._control_lock:
            await self._async_set_white_brightness(brightness)

    async def _async_set_white_brightness(self, brightness: int = 100) -> None:
        self._require_support("set_white_brightness", supported=self.coordinator.profile.supports_white_brightness)
        with self._rollback():
            async def apply() -> None:
                await self.coordinator.send_command(
                    build_power(True, self.coordinator.model)
                )
                self.coordinator.is_on = True
                await self.coordinator.send_command(build_white_brightness(brightness))

            await apply()
            await self._refresh_with_retry(
                expected_on=True,
                expected_white_brightness=brightness,
                retry_command=apply,
            )
            self.coordinator._enter_static_mode()
            self.coordinator.white_brightness = brightness
            self._attr_color_mode = ColorMode.COLOR_TEMP
        self._notify_state_changed()

    async def async_paint_segments(self, groups: list[dict[str, Any]]) -> None:
        async with self.coordinator._control_lock:
            self._require_support("paint_segments", supported=self.coordinator.profile.supports_segments)
            if not groups or any(not group.get("segments") for group in groups):
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="invalid_segments",
                )
            resolved: list[SegmentColorGroup] = [(group["segments"], group["rgb_color"]) for group in groups]
            try:
                await self.coordinator.async_paint_segments(resolved)
            except (TypeError, ValueError) as err:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="invalid_segments",
                ) from err

    async def async_set_segment_color(self, segments: list[int], color: tuple[int, int, int]) -> None:
        group: dict[str, Any] = {"segments": segments, "rgb_color": color}
        await self.async_paint_segments([group])

    async def async_set_segment_brightness(self, segments: list[int], brightness: int) -> None:
        async with self.coordinator._control_lock:
            self._require_support("set_segment_brightness", supported=self.coordinator.profile.supports_segments)
            try:
                packet = build_segment_brightness(segments, brightness)
            except (TypeError, ValueError) as err:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="invalid_segments",
                ) from err
            await self.coordinator.send_command(packet)
            self.coordinator._enter_static_mode()
            self._notify_state_changed()

    async def async_save_effect(
        self, name: str, content: dict[str, Any] | None = None, capture_current: bool = False
    ) -> None:
        if capture_current == (content is not None):
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="content_xor_capture")
        with _map_effect_errors():
            if content is not None:
                await self.coordinator.async_save_effect(name, content=content_from_dict(content))
            else:
                await self.coordinator.async_save_effect(name, capture_current=True)

    async def async_delete_effect(self, id: str | None = None, name: str | None = None) -> None:
        identifier = _single_effect_ref(id, name, "delete_needs_id_or_name")
        with _map_effect_errors(effect=identifier):
            await self.coordinator.async_delete_effect(identifier)

    async def async_rename_effect(self, to: str, id: str | None = None, from_name: str | None = None) -> None:
        identifier = _single_effect_ref(id, from_name, "rename_needs_id_or_from")
        with _map_effect_errors(effect=identifier):
            await self.coordinator.async_rename_effect(identifier, to)

    async def async_update_effect(
        self, id: str, name: str | None = None, content: dict[str, Any] | None = None
    ) -> None:
        if name is None and content is None:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="update_needs_name_or_content")
        with _map_effect_errors(effect=id):
            await self.coordinator.async_update_effect(
                id,
                display_name=name,
                content=None if content is None else content_from_dict(content),
            )

    async def async_export_effect(self, id: str) -> ServiceResponse:
        with _map_effect_errors(effect=id):
            return await self.coordinator.async_export_effect(id)
