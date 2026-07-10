"""Apply-helpers and entity-service mixin for the Govee BLE light."""

import logging
from collections.abc import Awaitable, Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from functools import partial
from typing import TYPE_CHECKING, Any

from homeassistant.components.light import ColorMode  # type: ignore[attr-defined]
from homeassistant.exceptions import ServiceValidationError

from .const import DOMAIN, MUSIC_MODE_SLUGS, MUSIC_MODES
from .coordinator import GoveeBLECoordinator
from .custom_effects import EffectValidationError, content_from_dict
from .protocol import (
    SegmentColorGroup,
    build_power,
    build_segment_brightness,
    build_video_mode,
    build_video_white_balance,
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


def _single_effect_ref(first: str | None, second: str | None, translation_key: str) -> str:
    """Return whichever identifier is set, or raise a translated error unless exactly one is given."""
    if first is not None and second is None:
        return first
    if first is None and second is not None:
        return second
    raise ServiceValidationError(translation_domain=DOMAIN, translation_key=translation_key)


# fmt: off
async def apply_video_mode_from_state(coord: GoveeBLECoordinator, *, game_mode: bool) -> None:
    await coord.send_command(build_video_mode(full_screen=coord.video_full_screen, game_mode=game_mode,
        saturation=coord.video_saturation, sound_effects=coord.video_sound_effects,
        sound_effects_softness=coord.video_sound_effects_softness))
# fmt: on


async def apply_active_video_mode(coord: GoveeBLECoordinator) -> bool:
    if coord.video_mode not in ("movie", "game"):
        return False
    if not coord.is_on:
        await coord.send_command(build_power(True))
        coord.is_on = True
    await apply_video_mode_from_state(coord, game_mode=coord.video_mode == "game")
    return True


async def apply_active_video_white_balance(coord: GoveeBLECoordinator) -> bool:
    if coord.video_white_balance is None:
        return False
    if not coord.is_on:
        await coord.send_command(build_power(True))
        coord.is_on = True
    await coord.send_command(build_video_white_balance(coord.video_white_balance))
    return True


async def apply_active_music_mode(coord: GoveeBLECoordinator) -> bool:
    if not coord.is_on or coord.music_mode not in MUSIC_MODE_SLUGS:
        return False
    await coord.async_select_music_slug(coord.music_mode)
    return True


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
            expected_music_mode: str | None = None,
            expected_video_mode: str | None = None,
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
            sound_effects: bool = False, sound_effects_softness: int = 0) -> None:
        # fmt: on
        self._require_support("set_video_mode", supported=self.coordinator.profile.supports_video_mode)
        with self._rollback():
            resolved_fs = full_screen if capture_region is None else capture_region == "full"
            # fmt: off
            packet = build_video_mode(full_screen=resolved_fs, game_mode=mode == "game", saturation=saturation,
                sound_effects=sound_effects, sound_effects_softness=sound_effects_softness)
            # fmt: on
            async def send() -> None:
                await self.coordinator.send_command(packet)

            await self.coordinator.send_command(build_power(True))
            self.coordinator.is_on = True
            await send()
            await self._refresh_with_retry(expected_video_mode=mode, retry_command=send, required=False)
            c = self.coordinator
            c.video_mode, c.effect = mode, None
            c.active_custom_id, c.music_mode = None, "off"
            c.video_saturation, c.video_full_screen = saturation, resolved_fs
            c.video_sound_effects, c.video_sound_effects_softness = sound_effects, sound_effects_softness
        self._notify_state_changed()

    async def async_set_music_mode(self, mode: str, sensitivity: int = 99,
            color: tuple[int, int, int] | None = None, calm: bool | None = None) -> None:
        self._require_support("set_music_mode", supported=self.coordinator.profile.supports_music_mode)
        if mode in MUSIC_MODE_ALIASES:
            canonical = MUSIC_MODE_ALIASES[mode]
            _LOGGER.warning("Music mode '%s' is deprecated; use '%s' instead", mode, canonical)
            mode = canonical
        slug = mode.replace(" ", "_")
        with self._rollback():
            c = self.coordinator
            c.music_sensitivity, c.music_color = sensitivity, color
            if slug == "rhythm" and calm is not None:
                c.music_calm = calm
            apply = partial(c.async_select_music_slug, slug)
            await apply()
            await self._refresh_with_retry(expected_music_mode=slug, retry_command=apply)
        self._notify_state_changed()

    async def async_set_white_brightness(self, brightness: int = 100) -> None:
        self._require_support("set_white_brightness", supported=self.coordinator.profile.supports_white_brightness)
        with self._rollback():
            send = partial(self.coordinator.send_command, build_white_brightness(brightness))
            await self.coordinator.send_command(build_power(True))
            self.coordinator.is_on = True
            await send()
            await self._refresh_with_retry(expected_on=True, retry_command=send)
            self.coordinator._enter_static_mode()
            self.coordinator.white_brightness = brightness
            self._attr_color_mode = ColorMode.COLOR_TEMP
        self._notify_state_changed()

    async def async_paint_segments(self, groups: list[dict[str, Any]]) -> None:
        self._require_support("paint_segments", supported=self.coordinator.profile.supports_segments)
        resolved: list[SegmentColorGroup] = [(group["segments"], group["rgb_color"]) for group in groups]
        await self.coordinator.async_paint_segments(resolved)

    async def async_set_segment_color(self, segments: list[int], color: tuple[int, int, int]) -> None:
        group: dict[str, Any] = {"segments": segments, "rgb_color": color}
        await self.async_paint_segments([group])

    async def async_set_segment_brightness(self, segments: list[int], brightness: int) -> None:
        self._require_support("set_segment_brightness", supported=self.coordinator.profile.supports_segments)
        await self.coordinator.send_command(build_segment_brightness(segments, brightness))
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
