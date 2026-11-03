"""What a connected-state refresh is expected to observe, and what it therefore needs to query."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .const import ModelProfile
from .coordinator_status import ParsedMode

BLANK_SCREEN_POLICY_FIELDS = (
    "blank_screen_detection",
    "blank_screen_low_brightness_duration_seconds",
    "blank_screen_same_tone_duration_seconds",
)


@dataclass(frozen=True, slots=True)
class RefreshExpectations:
    """The ``expected_*`` arguments of a refresh, with the rules that derive queries and field checks from them."""

    effect: str | None = None
    scene_code: int | None = None
    on: bool | None = None
    brightness: int | None = None
    rgb_color: tuple[int, int, int] | None = None
    color_temp_kelvin: int | None = None
    zero_kelvin: bool = False
    music_mode: str | None = None
    music_sensitivity: int | None = None
    music_calm: bool | None = None
    music_color: tuple[int, int, int] | None = None
    music_auto_color: bool = False
    video_mode: str | None = None
    video_parameters: Mapping[str, Any] | None = None
    video_full_screen: bool | None = None
    video_saturation: int | None = None
    video_sound_effects: bool | None = None
    video_sound_effects_softness: int | None = None
    white_brightness: int | None = None
    white_balance: tuple[int, ...] | None = None
    white_balance_flag: int | None = None
    blank_screen: bool | None = None
    blank_screen_policy: tuple[int, int, int] | None = None
    black_border: bool | None = None
    relative_brightness: tuple[int, ...] | None = None

    def unsupported_static_readback(self, profile: ModelProfile) -> bool:
        """Whether the profile cannot echo the static colour this refresh expects."""
        if self.rgb_color is not None and not profile.static_readback_echoes_color:
            return True
        if self.color_temp_kelvin is not None and not profile.static_readback_kelvin:
            return True
        return self.zero_kelvin and (
            not profile.static_readback_zero_kelvin_is_rgb or self.color_temp_kelvin is not None
        )

    @property
    def expects_color_readback(self) -> bool:
        """Whether any expectation can only be confirmed from a colour-mode reply."""
        color_expectations = (
            self.rgb_color,
            self.color_temp_kelvin,
            self.effect,
            self.scene_code,
            self.music_mode,
            self.music_sensitivity,
            self.music_calm,
            self.music_color,
            self.video_mode,
            self.video_parameters,
            self.video_full_screen,
            self.video_saturation,
            self.video_sound_effects,
            self.video_sound_effects_softness,
            self.white_brightness,
        )
        return self.zero_kelvin or self.music_auto_color or any(value is not None for value in color_expectations)

    @property
    def expects_white_balance(self) -> bool:
        return self.white_balance is not None or self.white_balance_flag is not None

    @property
    def expects_blank_screen(self) -> bool:
        return self.blank_screen is not None or self.blank_screen_policy is not None

    @property
    def expects_black_border(self) -> bool:
        return self.black_border is not None

    @property
    def expects_relative_brightness(self) -> bool:
        return self.relative_brightness is not None

    def field_expectations(self, profile: ModelProfile) -> dict[str, Any]:
        """Coordinator attribute values the refresh must observe, keyed by attribute name."""
        expectations: dict[str, Any] = {
            field: value
            for field, value in (
                ("effect", self.effect),
                ("scene_code", self.scene_code),
                ("is_on", self.on),
                ("brightness_pct", self.brightness),
                ("rgb_color", self.rgb_color),
                ("color_temp_kelvin", self.color_temp_kelvin),
                ("music_mode", self.music_mode),
                ("music_sensitivity", self.music_sensitivity),
                ("music_calm", self.music_calm),
                ("music_color", self.music_color),
                ("video_mode", self.video_mode),
                ("video_parameters", self.video_parameters),
                ("video_full_screen", self.video_full_screen),
                ("video_saturation", self.video_saturation),
                ("video_sound_effects", self.video_sound_effects),
                ("video_sound_effects_softness", self.video_sound_effects_softness),
                ("white_brightness", self.white_brightness),
            )
            if value is not None
        }
        if self.music_auto_color:
            expectations["music_color"] = None
        if self.zero_kelvin:
            expectations["color_temp_kelvin"] = None
        if self.rgb_color is not None or self.color_temp_kelvin is not None or self.zero_kelvin:
            expectations["color_mode"] = ParsedMode.COLOUR
        if self.white_balance is not None:
            fields = (
                ("white_balance_scalar",)
                if profile.video_white_balance_representation == "scalar"
                else ("white_balance_red", "white_balance_blue")
            )
            expectations.update(zip(fields, self.white_balance, strict=True))
        if self.white_balance_flag is not None:
            expectations["white_balance_flag"] = self.white_balance_flag
        if self.blank_screen is not None:
            expectations["blank_screen"] = self.blank_screen
        if self.blank_screen_policy is not None:
            expectations.update(zip(BLANK_SCREEN_POLICY_FIELDS, self.blank_screen_policy, strict=True))
        if self.black_border is not None:
            expectations["black_border"] = self.black_border
        if self.relative_brightness is not None:
            expectations["relative_brightness"] = (
                self.relative_brightness[0] if len(set(self.relative_brightness)) == 1 else None
            )
            expectations.update(
                (f"relative_brightness_{zone}", value)
                for zone, value in zip(profile.video_brightness_zones, self.relative_brightness, strict=True)
            )
        return expectations
