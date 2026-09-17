"""Control helpers for the Govee BLE light."""

from collections.abc import Awaitable, Callable, Mapping
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components.light import ColorMode  # type: ignore[attr-defined]
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import service
from homeassistant.helpers.typing import VolDictType

from .const import DOMAIN
from .control_arbiter import ControlIntent, async_control_intent
from .coordinator import GoveeBLECoordinator
from .dreamview_services import async_register_dreamview_services
from .h6099_controls import (
    async_read_installation_controls,
    async_set_installation_direction,
    installation_direction_value,
)
from .light_commands import (
    SegmentColorGroup,
    build_segment_brightness,
    build_segment_color_temp,
    build_segment_paint,
    kelvin_to_rgb,
    segments_to_mask,
)
from .native_profile_controls import apply_active_video_mode

__all__ = ("apply_active_video_mode", "async_register_light_services")


def _segment(value: int | str) -> int:
    """Keep integer-string service inputs without truncating fractional indices."""
    try:
        if isinstance(value, str):
            value = int(value)
        segments_to_mask((value,))
    except (TypeError, ValueError) as err:
        raise vol.Invalid(str(err)) from err
    return value


_PERCENTAGE = vol.All(vol.Coerce(int), vol.Range(min=0, max=100))
_SEGMENTS = vol.All([_segment], vol.Length(min=1))
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
_SET_SEGMENT_COLOR_TEMP_SCHEMA: VolDictType = {
    vol.Required("segments"): _SEGMENTS,
    vol.Required("color_temp_kelvin"): vol.All(vol.NotIn([True, False]), vol.Any(str, int), cv.positive_int),
}


def async_register_light_services(hass: HomeAssistant) -> None:
    """Register light entity services before config entries are loaded."""
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        "set_installation_direction",
        entity_domain=Platform.LIGHT,
        func=async_set_installation_direction,
        schema={vol.Required("value"): installation_direction_value},
    )
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        "read_installation_controls",
        entity_domain=Platform.LIGHT,
        func=async_read_installation_controls,
        schema={},
        supports_response=SupportsResponse.ONLY,
    )
    async_register_dreamview_services(hass)
    for name, schema, method in (
        ("paint_segments", _PAINT_SEGMENTS_SCHEMA, "async_paint_segments"),
        ("set_segment_color", _SET_SEGMENT_COLOR_SCHEMA, "async_set_segment_color"),
        ("set_segment_color_temp", _SET_SEGMENT_COLOR_TEMP_SCHEMA, "async_set_segment_color_temp"),
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
            sound_effects: bool = False, sound_effects_softness: int | None = None,
            *, values: Mapping[str, Any] | None = None) -> None:
        # fmt: on
        self._require_support("set_video_mode", supported=self.coordinator.profile.supports_video_mode)
        if sound_effects:
            self._require_support(
                "video sound effects",
                supported=self.coordinator.profile.supports_video_sound_effects,
            )
        with self._rollback():
            c = self.coordinator
            requested_fs = full_screen if capture_region is None else capture_region == "full"
            resolved_fs = requested_fs if c.profile.supports_video_capture_region else c.video_full_screen
            resolved_saturation = saturation if c.profile.supports_video_saturation else c.video_saturation
            c.profile.validate_video_saturation(resolved_saturation)
            supports_sound = c.profile.supports_video_sound_effects
            resolved_sound = sound_effects and supports_sound
            resolved_softness = (
                c.video_sound_effects_softness if sound_effects_softness is None else sound_effects_softness
            )
            requested = {
                field: value for field, value in (
                    ("full_screen", resolved_fs), ("saturation", resolved_saturation),
                    ("sound_effects", resolved_sound), ("sound_effects_softness", resolved_softness),
                ) if value != getattr(c, f"video_{field}")
            }
            await apply_active_video_mode(c, mode=mode, requested_values=requested, parameters=values)
        self._notify_state_changed()

    async def async_paint_segments(self, groups: list[dict[str, Any]]) -> None:
        self._require_support("paint_segments", supported=self.coordinator.profile.supports_segments)
        try:
            resolved: list[SegmentColorGroup] = [
                (list(group.get("segments", [])), group["rgb_color"]) for group in groups
            ]
            # Preflight serialization before disturbing an active preview or claiming user control.
            build_segment_paint(resolved, self.coordinator.model, profile=self.coordinator.profile)
            await self._async_supersede_preview()
            async with async_control_intent(self.coordinator, ControlIntent.USER):
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

    async def async_set_segment_color_temp(self, segments: list[int], color_temp_kelvin: int) -> None:
        """Verify rendered RGB and preserve freshly read sibling colours/brightness.

        At 3000 K the service computes (255,177,109). The older manual probe
        supplied (255,185,105); its device qualification is distinct.
        """
        c = self.coordinator
        self._require_support(
            "set_segment_color_temp",
            supported=c.profile.supports_segments and c.profile.supports_color_temperature,
        )
        try:
            segments = list(segments)
            packet = build_segment_color_temp(segments, color_temp_kelvin, c.model, profile=c.profile)
            expected = kelvin_to_rgb(color_temp_kelvin)
            await self._async_supersede_preview()
            async with async_control_intent(c, ControlIntent.USER):
                try:
                    if not await c.async_refresh_segments():
                        raise RuntimeError("Failed to read segments before colour temperature write")
                    expected_colors = list(c.segment_colors)
                    expected_brightness = list(c.segment_brightness)
                    for segment in segments:
                        expected_colors[segment - 1] = expected
                    # The shared writer installs masked RGB only at the physical-write boundary
                    # and reconciles attempted failures. Readback proves RGB, not per-segment Kelvin.
                    await c.send_command(packet)
                    if (
                        not await c.async_refresh_segments()
                        or c.segment_colors != expected_colors
                        or c.segment_brightness != expected_brightness
                    ):
                        raise RuntimeError("Failed to confirm segment colour temperature")
                finally:
                    self._notify_state_changed()
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

    async def async_set_segment_brightness(self, segments: list[int], brightness: int) -> None:
        self._require_support("set_segment_brightness", supported=self.coordinator.profile.supports_segments)
        try:
            segments = list(segments)
            build_segment_brightness(segments, brightness, self.coordinator.model, profile=self.coordinator.profile)
            await self._async_supersede_preview()
            async with async_control_intent(self.coordinator, ControlIntent.USER):
                await self.coordinator.async_set_segment_brightness(segments, brightness)
                self._notify_state_changed()
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
