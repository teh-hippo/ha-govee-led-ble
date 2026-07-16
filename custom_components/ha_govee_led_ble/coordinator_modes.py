"""Active-mode derivation and mode-switching for the Govee BLE coordinator."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from .const import MUSIC_MODE_SLUGS
from .coordinator_base import _CoordinatorBase
from .protocol import (
    RHYTHM_MODE_ID,
    build_color_rgb,
    build_color_temp,
    build_music_mode_with_color,
    build_music_params_a3,
    build_power,
    build_white_brightness,
)
from .scenes import get_scene_names


@dataclass(frozen=True)
class PreModeSnapshot:
    """The typed static state to re-apply when leaving a music or video mode (spec §1.2, panel #9).

    ``kind`` selects which payload is meaningful; the others carry inert defaults so a fresh
    coordinator always has a defined state to restore.
    """

    kind: Literal["rgb", "color_temp", "white"] = "rgb"
    rgb: tuple[int, int, int] = (255, 255, 255)
    kelvin: int = 0
    level: int = 100


FOUNTAIN_DIRECTION_BYTES: dict[str, tuple[int, int]] = {
    "clockwise": (0x00, 0x05),
    "counterclockwise": (0x02, 0x05),
    "two_way": (0x01, 0x03),
}

BLOOM_MODE_ID = MUSIC_MODE_SLUGS["bloom"]
SHINY_MODE_ID = MUSIC_MODE_SLUGS["shiny"]
# Modes whose base-frame STYLE byte (byte 5) carries Dynamic/Calm (H617A §2.1, live 2026-07-16).
MUSIC_STYLE_MODE_IDS = frozenset({RHYTHM_MODE_ID, BLOOM_MODE_ID, SHINY_MODE_ID})
# Slugs for the style-carrying modes, derived so the set never drifts from the id set above.
MUSIC_STYLE_SLUGS = frozenset(slug for slug, mode_id in MUSIC_MODE_SLUGS.items() if mode_id in MUSIC_STYLE_MODE_IDS)
# Bloom and Shiny also carry Dynamic/Calm in their a3 movement companion; Rhythm rides byte 5 alone.
# Absolute a3 offsets keyed by ``calm``; the Dynamic (False) values equal the capture-pinned templates.
_MUSIC_STYLE_COMPANION: dict[int, dict[bool, dict[int, int]]] = {
    BLOOM_MODE_ID: {False: {27: 0x50}, True: {27: 0x14}},
    SHINY_MODE_ID: {False: {20: 0x05, 21: 0x64}, True: {20: 0x14, 21: 0x46}},
}


def _encode_byte(value: Any) -> int:
    return int(value)


def _encode_bool(value: Any) -> int:
    return int(bool(value))


def _encode_fountain_direction(value: Any) -> int:
    return FOUNTAIN_DIRECTION_BYTES[value][1]


@dataclass(frozen=True)
class MusicParamSpec:
    """One capture-pinned per-mode music movement param (§2.3): its coordinator field, a3 offset,
    encoder, and the entity shape/bounds it drives. ``mode_code`` ties it to the active music mode."""

    key: str
    mode_code: int
    offset: int
    kind: Literal["number", "switch", "select"]
    encode: Callable[[Any], int]
    min_value: int = 0
    max_value: int = 0
    options: tuple[str, ...] = ()


# Absolute a3 offsets per §2.3; volatile bytes stay out of this table so they are never written.
MUSIC_PARAM_SPECS: tuple[MusicParamSpec, ...] = (
    MusicParamSpec("music_separation_point", 0x32, 20, "number", _encode_byte, min_value=1, max_value=5),
    MusicParamSpec("music_separation_gradient", 0x32, 21, "switch", _encode_bool),
    MusicParamSpec("music_hopping_brightness", 0x33, 29, "number", _encode_byte, min_value=0, max_value=50),
    MusicParamSpec("music_piano_key_count", 0x34, 27, "number", _encode_byte, min_value=8, max_value=15),
    MusicParamSpec(
        "music_fountain_direction",
        0x35,
        28,
        "select",
        _encode_fountain_direction,
        options=("clockwise", "counterclockwise", "two_way"),
    ),
    MusicParamSpec("music_daynight_segments", 0x37, 26, "number", _encode_byte, min_value=1, max_value=7),
    MusicParamSpec("music_daynight_speed", 0x37, 27, "number", _encode_byte, min_value=1, max_value=50),
)


def music_params_for_mode(mode_code: int) -> tuple[MusicParamSpec, ...]:
    return tuple(spec for spec in MUSIC_PARAM_SPECS if spec.mode_code == mode_code)


class _ActiveModeMixin(_CoordinatorBase):
    """Derives the coarse operating mode and routes music-mode entry/exit."""

    @property
    def scene_name_set(self) -> frozenset[str]:
        if self.profile.scene_source == "api":
            return frozenset(get_scene_names())
        return frozenset()

    @property
    def active_mode(self) -> str:
        if not self.is_on:
            return "off"
        if self.active_custom_id is not None or self.diy_slot is not None:
            return "custom"
        if self.effect in self.scene_name_set:
            return "scene"
        if self.music_mode not in (None, "off"):
            return "music"
        if self.video_mode not in (None, "off"):
            return "video"
        return "colour"

    def _capture_static_state(self) -> PreModeSnapshot:
        if self.color_temp_kelvin is not None:
            return PreModeSnapshot(kind="color_temp", kelvin=self.color_temp_kelvin)
        return PreModeSnapshot(kind="rgb", rgb=self.rgb_color)

    def _enter_static_mode(self) -> None:
        """Clear every non-static mode so exactly one operating mode is ever active (spec §1.4)."""
        self.effect = self.active_custom_id = None
        self.diy_slot = None
        self._owned_diy_effect_id = None
        self.music_mode = self.video_mode = "off"

    @property
    def music_style(self) -> str:
        """Dynamic/Calm view of the Rhythm STYLE byte (§2.1), backed by the ``music_calm`` bool."""
        return "calm" if self.music_calm else "dynamic"

    @music_style.setter
    def music_style(self, value: str) -> None:
        self.music_calm = value == "calm"

    async def async_select_music_slug(self, slug: str) -> None:
        if slug == "off":
            await self.async_restore_pre_mode()
            return
        if slug not in self.profile.music_modes:
            raise ValueError(f"{self.model} does not support music mode {slug}")
        if self.active_mode == "colour":
            self._pre_mode_snapshot = self._capture_static_state()
        mode_id = MUSIC_MODE_SLUGS[slug]
        calm = self.music_calm if mode_id in MUSIC_STYLE_MODE_IDS else False
        color = self.music_color if self.profile.supports_music_color else None
        await self.send_command(build_power(True))
        self.is_on = True
        await self.send_command(
            build_music_mode_with_color(mode_id, sensitivity=self.music_sensitivity, color=color, calm=calm)
        )
        if mode_id in _MUSIC_STYLE_COMPANION:
            await self._send_music_params(mode_id)
        self.music_mode, self.video_mode = slug, "off"
        self.effect, self.active_custom_id = None, None
        self.diy_slot = None
        self._owned_diy_effect_id = None

    async def async_restore_pre_mode(self) -> None:
        snap = self._pre_mode_snapshot
        match snap.kind:
            case "color_temp":
                await self.send_command(build_color_temp(snap.kelvin))
            case "white":
                await self.send_command(build_white_brightness(snap.level))
            case _:
                await self.send_command(build_color_rgb(*snap.rgb))
        self._enter_static_mode()

    async def async_apply_music_params(self, mode_code: int) -> None:
        """Re-send the active mode's a3 movement frame, merging every stored param for that mode so
        multi-param modes (Separation, Day & Night) never clobber a sibling param (§2.3)."""
        await self._send_music_params(mode_code)

    async def _send_music_params(self, mode_code: int) -> None:
        overrides = {spec.offset: spec.encode(getattr(self, spec.key)) for spec in music_params_for_mode(mode_code)}
        if mode_code == 0x35:
            phase, selector = FOUNTAIN_DIRECTION_BYTES[self.music_fountain_direction]
            overrides.update({26: phase, 28: selector})
        companion = _MUSIC_STYLE_COMPANION.get(mode_code)
        if companion is not None:
            overrides.update(companion[self.music_calm])
        for packet in build_music_params_a3(mode_code, overrides):
            await self.send_command(packet)
