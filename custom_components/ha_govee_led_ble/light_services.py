"""Control helpers for the Govee BLE light."""

from collections.abc import Awaitable, Callable
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components.light import ColorMode  # type: ignore[attr-defined]
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import service
from homeassistant.helpers.typing import VolDictType

from .const import DOMAIN
from .control_arbiter import ControlIntent, async_control_intent
from .coordinator import GoveeBLECoordinator
from .generated_protocol_adapter import build_h6199_video, build_power
from .light_commands import SegmentColorGroup
from .native_profile_controls import apply_active_video_mode

__all__ = ("apply_active_video_mode", "async_register_light_services")

_PERCENTAGE = vol.All(vol.Coerce(int), vol.Range(min=0, max=100))
_SEGMENT = vol.All(vol.Coerce(int), vol.Range(min=1, max=15))
_SEGMENTS = vol.All([_SEGMENT], vol.Length(min=1))
_RGB = vol.All(vol.ExactSequence((cv.byte, cv.byte, cv.byte)), vol.Coerce(tuple))
_PAINT_SEGMENTS_SCHEMA: VolDictType = {
    vol.Required("groups"): vol.All(
        [
            {
                vol.Required("segments"): _SEGMENTS,
                vol.Required("rgb_color"): _RGB,
            }
        ],
        vol.Length(min=1),
    ),
}
_SET_SEGMENT_COLOR_SCHEMA: VolDictType = {
    vol.Required("segments"): _SEGMENTS,
    vol.Required("color"): _RGB,
}
_SET_SEGMENT_BRIGHTNESS_SCHEMA: VolDictType = {
    vol.Required("segments"): _SEGMENTS,
    vol.Required("brightness"): _PERCENTAGE,
}


def async_register_light_services(hass: HomeAssistant) -> None:
    """Register light entity services before config entries are loaded."""
    for name, schema, method in (
        ("paint_segments", _PAINT_SEGMENTS_SCHEMA, "async_paint_segments"),
        ("set_segment_color", _SET_SEGMENT_COLOR_SCHEMA, "async_set_segment_color"),
        (
            "set_segment_brightness",
            _SET_SEGMENT_BRIGHTNESS_SCHEMA,
            "async_set_segment_brightness",
        ),
    ):
        service.async_register_platform_entity_service(
            hass,
            DOMAIN,
            name,
            entity_domain=Platform.LIGHT,
            func=method,
            schema=schema,
        )


class _GoveeLightOwner:
    """Typed surface the service mixin relies on from ``GoveeBLELight``."""

    coordinator: GoveeBLECoordinator
    _attr_color_mode: ColorMode | None

    if TYPE_CHECKING:

        def _rollback(self) -> AbstractContextManager[None]: ...

        async def _refresh_with_retry(
            self,
            *,
            expected_on: bool | None = None,
            expected_brightness: int | None = None,
            expected_video_mode: str | None = None,
            expected_video_full_screen: bool | None = None,
            expected_video_saturation: int | None = None,
            expected_video_sound_effects: bool | None = None,
            expected_video_sound_effects_softness: int | None = None,
            retry_command: Callable[[], Awaitable[None]] | None = None,
        ) -> None: ...

        def _notify_state_changed(self) -> None: ...

        async def _async_supersede_preview(self) -> None: ...

        def _require_support(self, service: str, *, supported: bool) -> None: ...


class _GoveeLightServicesMixin(_GoveeLightOwner):
    """Entity-service methods for the Govee BLE light."""

    # fmt: off
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
            packet = build_h6199_video(resolved_fs, mode == "game", saturation, resolved_sound, resolved_softness)
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
            c.music_mode = "off"
            c.diy_code = None
            c.video_saturation, c.video_full_screen = saturation, resolved_fs
            c.video_sound_effects = resolved_sound
            if supports_sound:
                c.video_sound_effects_softness = resolved_softness
        self._notify_state_changed()

    async def async_paint_segments(self, groups: list[dict[str, Any]]) -> None:
        await self._async_supersede_preview()
        async with async_control_intent(
            self.coordinator,
            ControlIntent.USER,
        ):
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
            except HomeAssistantError:
                raise
            except Exception as err:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="device_command_failed",
                ) from err

    async def async_set_segment_color(self, segments: list[int], color: tuple[int, int, int]) -> None:
        group: dict[str, Any] = {"segments": segments, "rgb_color": color}
        await self.async_paint_segments([group])

    async def async_set_segment_brightness(self, segments: list[int], brightness: int) -> None:
        await self._async_supersede_preview()
        async with async_control_intent(
            self.coordinator,
            ControlIntent.USER,
        ):
            self._require_support("set_segment_brightness", supported=self.coordinator.profile.supports_segments)
            if not segments:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="invalid_segments",
                )
            try:
                await self.coordinator.async_set_segment_brightness(segments, brightness)
            except (TypeError, ValueError) as err:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="invalid_segments",
                ) from err
            except HomeAssistantError:
                raise
            except Exception as err:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="device_command_failed",
                ) from err
            self._notify_state_changed()
