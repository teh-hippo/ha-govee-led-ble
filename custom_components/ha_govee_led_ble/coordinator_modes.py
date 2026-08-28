"""Active-mode derivation and mode-switching for the Govee BLE coordinator."""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from .const import MUSIC_MODE_SLUGS
from .control_arbiter import ControlIntent, async_control_intent
from .coordinator_base import _CoordinatorBase
from .coordinator_status import ParsedMode
from .generated_protocol_adapter import build_music_mode, build_power
from .light_commands import (
    build_color_rgb,
    build_color_temp,
    build_white_brightness,
)
from .music_commands import build_music_params
from .native_scenes import build_native_scene_packets
from .scenes import MODEL_SCENES


@dataclass(frozen=True)
class PreModeSnapshot:
    """The typed static state to re-apply when leaving a music or video mode.

    ``kind`` selects which payload is meaningful; the others carry inert defaults so a fresh
    coordinator always has a defined state to restore.
    """

    kind: Literal["rgb", "color_temp", "white"] = "rgb"
    rgb: tuple[int, int, int] = (255, 255, 255)
    kelvin: int = 0
    level: int = 100


RHYTHM_MODE_ID = MUSIC_MODE_SLUGS["rhythm"]
BLOOM_MODE_ID = MUSIC_MODE_SLUGS["bloom"]
SHINY_MODE_ID = MUSIC_MODE_SLUGS["shiny"]
# Modes whose govee_common::music_selector style byte carries Dynamic/Calm.
MUSIC_STYLE_MODE_IDS = frozenset({RHYTHM_MODE_ID, BLOOM_MODE_ID, SHINY_MODE_ID})
# Slugs for the style-carrying modes, derived so the set never drifts from the id set above.
MUSIC_STYLE_SLUGS = frozenset(slug for slug, mode_id in MUSIC_MODE_SLUGS.items() if mode_id in MUSIC_STYLE_MODE_IDS)
# Bloom and Shiny also carry Dynamic/Calm in their a3 movement companion; Rhythm rides byte 5 alone.
# Absolute a3 offsets keyed by ``calm``; the Dynamic (False) values equal the capture-pinned templates.
_MUSIC_STYLE_COMPANION: dict[int, dict[bool, dict[int, int]]] = {
    BLOOM_MODE_ID: {False: {27: 0x50}, True: {27: 0x14}},
    SHINY_MODE_ID: {False: {20: 0x05, 21: 0x64}, True: {20: 0x14, 21: 0x46}},
}

FOUNTAIN_DIRECTION_BYTES: dict[str, tuple[int, int]] = {
    "clockwise": (0x00, 0x05),
    "counterclockwise": (0x02, 0x05),
    "two_way": (0x01, 0x03),
}


def _encode_byte(value: Any) -> int:
    return int(value)


def _encode_bool(value: Any) -> int:
    return int(bool(value))


def _encode_fountain_direction(value: Any) -> int:
    return FOUNTAIN_DIRECTION_BYTES[str(value)][1]


@dataclass(frozen=True)
class MusicParamSpec:
    key: str
    profile_key: str
    mode_code: int
    offset: int
    kind: Literal["number", "switch", "select"]
    encode: Callable[[Any], int]
    default: int | bool | str
    min_value: int = 0
    max_value: int = 0
    options: tuple[str, ...] = ()


MUSIC_PARAM_SPECS: tuple[MusicParamSpec, ...] = (
    MusicParamSpec("music_separation_point", "point", 0x32, 20, "number", _encode_byte, 1, min_value=1, max_value=5),
    MusicParamSpec("music_separation_gradient", "gradient", 0x32, 21, "switch", _encode_bool, True),
    MusicParamSpec(
        "music_hopping_brightness",
        "relative_brightness",
        0x33,
        29,
        "number",
        _encode_byte,
        50,
        min_value=0,
        max_value=50,
    ),
    MusicParamSpec(
        "music_piano_key_count", "key_count", 0x34, 27, "number", _encode_byte, 15, min_value=8, max_value=15
    ),
    MusicParamSpec(
        "music_fountain_direction",
        "direction",
        0x35,
        28,
        "select",
        _encode_fountain_direction,
        "clockwise",
        options=("clockwise", "counterclockwise", "two_way"),
    ),
    MusicParamSpec(
        "music_daynight_segments",
        "segment_count",
        0x37,
        26,
        "number",
        _encode_byte,
        1,
        min_value=1,
        max_value=7,
    ),
    MusicParamSpec("music_daynight_speed", "speed", 0x37, 27, "number", _encode_byte, 10, min_value=1, max_value=50),
    MusicParamSpec("music_daynight_gradient", "gradient", 0x37, 28, "switch", _encode_bool, False),
)


def music_params_for_mode(mode_code: int) -> tuple[MusicParamSpec, ...]:
    return tuple(spec for spec in MUSIC_PARAM_SPECS if spec.mode_code == mode_code)


def music_mode_has_parameter_write(mode_code: int) -> bool:
    return bool(music_params_for_mode(mode_code) or mode_code in _MUSIC_STYLE_COMPANION)


class _ActiveModeMixin(_CoordinatorBase):
    """Derives the coarse operating mode and routes music-mode entry/exit."""

    music_separation_point: int
    music_separation_gradient: bool
    music_hopping_brightness: int
    music_piano_key_count: int
    music_fountain_direction: str
    music_daynight_segments: int
    music_daynight_speed: int
    music_daynight_gradient: bool
    _scene_code: int | None

    @property
    def scene_name_set(self) -> frozenset[str]:
        return frozenset(MODEL_SCENES[self.model])

    @property
    def active_mode(self) -> str:
        if not self.is_on:
            return "off"
        if self.diy_code is not None:
            return "custom"
        if self.effect is not None:
            return "scene"
        if self.music_mode not in (None, "off"):
            return "music"
        if self.video_mode not in (None, "off"):
            return "video"
        return "colour"

    async def async_apply_native_scene(
        self,
        scene_name: str,
        *,
        speed_index: int | None = None,
        canonical_body: bytes | None = None,
        writer: Callable[[bytes], Awaitable[None]] | None = None,
        before_write: Callable[[], Awaitable[None]] | None = None,
        progress: Callable[[int], Awaitable[None]] | None = None,
        verify: bool = True,
        intent: ControlIntent = ControlIntent.USER,
    ) -> None:
        async with async_control_intent(self, intent):
            await self._async_apply_native_scene_locked(
                scene_name,
                speed_index=speed_index,
                canonical_body=canonical_body,
                writer=writer,
                before_write=before_write,
                progress=progress,
                verify=verify,
                intent=intent,
            )

    async def _async_apply_native_scene_locked(
        self,
        scene_name: str,
        *,
        speed_index: int | None = None,
        canonical_body: bytes | None = None,
        writer: Callable[[bytes], Awaitable[None]] | None = None,
        before_write: Callable[[], Awaitable[None]] | None = None,
        progress: Callable[[int], Awaitable[None]] | None = None,
        verify: bool,
        intent: ControlIntent,
    ) -> None:
        scene = MODEL_SCENES[self.model].get(scene_name)
        if scene is None:
            raise ValueError(f"unknown native scene {scene_name!r}")
        packets = build_native_scene_packets(
            self.model,
            scene,
            speed_index=speed_index,
            canonical_body=canonical_body,
        )

        power_in_sequence = False
        if not self.is_on:
            power = build_power(True, self.model)
            if writer is not None:
                await writer(power)
            elif verify:
                await self.send_command(power)
            else:
                packets.insert(0, power)
                power_in_sequence = True
            if not power_in_sequence:
                self.is_on = True
            if verify and self.profile.state_readable and not await self.refresh_state(expected_on=True):
                await self.send_command(power)
                if not await self.refresh_state(expected_on=True):
                    raise RuntimeError(f"Failed to confirm power-on before selecting scene {scene_name!r}")

        async def apply() -> None:
            if writer is not None:
                for packet in packets:
                    await writer(packet)
                return
            await self.async_write_effect_sequence(
                packets,
                intent=intent,
                before_write=before_write,
                progress=progress,
            )

        await apply()
        if power_in_sequence:
            self.is_on = True
        if verify and self.profile.state_readable and not await self.refresh_state(expected_effect=scene_name):
            await apply()
            if not await self.refresh_state(expected_effect=scene_name):
                raise RuntimeError(f"Failed to confirm scene {scene_name!r}")
        self.effect = scene_name
        self.diy_code = None
        self.music_mode = self.video_mode = "off"
        self.async_set_updated_data(self.data or {})

    def _capture_static_state(self) -> PreModeSnapshot:
        if self.color_temp_kelvin is not None:
            return PreModeSnapshot(kind="color_temp", kelvin=self.color_temp_kelvin)
        return PreModeSnapshot(kind="rgb", rgb=self.rgb_color)

    def _enter_static_mode(self) -> None:
        """Clear every non-static mode so exactly one operating mode is active."""
        self.color_mode = ParsedMode.COLOUR
        self._scene_code = None
        self.effect = None
        self.diy_code = None
        self.music_mode = self.video_mode = "off"

    async def async_select_music_slug(
        self,
        slug: str,
        *,
        include_parameters: bool = True,
        writer: Callable[[bytes], Awaitable[None]] | None = None,
    ) -> None:
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
        send = self.send_command if writer is None else writer
        await send(build_power(True, self.model))
        self.is_on = True
        await send(
            build_music_mode(
                mode_id,
                self.music_sensitivity,
                color,
                calm,
                self.model,
            )
        )
        if include_parameters and mode_id in _MUSIC_STYLE_COMPANION:
            await self._send_music_params(mode_id, writer=send)
        self.music_mode, self.video_mode = slug, "off"
        self.effect = None
        self.diy_code = None

    def install_music_profile_state(
        self,
        *,
        mode: str,
        sensitivity: int,
        colour: tuple[int, int, int] | None,
        calm: bool,
        parameters: Mapping[str, int | bool | str],
    ) -> None:
        self.music_sensitivity = sensitivity
        self.music_color = colour
        self.music_calm = calm
        for spec in music_params_for_mode(MUSIC_MODE_SLUGS[mode]):
            if spec.profile_key in parameters:
                setattr(self, spec.key, parameters[spec.profile_key])

    async def async_apply_music_params(
        self,
        mode_code: int,
        *,
        writer: Callable[[bytes], Awaitable[None]] | None = None,
    ) -> None:
        await self._send_music_params(mode_code, writer=writer)

    async def _send_music_params(
        self,
        mode_code: int,
        *,
        writer: Callable[[bytes], Awaitable[None]] | None = None,
    ) -> None:
        overrides = {spec.offset: spec.encode(getattr(self, spec.key)) for spec in music_params_for_mode(mode_code)}
        if mode_code == 0x35:
            start_point, piece_num = FOUNTAIN_DIRECTION_BYTES[self.music_fountain_direction]
            overrides.update({26: start_point, 28: piece_num})
        if mode_code == 0x32:
            overrides[22] = 0x5E if self.music_separation_gradient else 0x61
        if mode_code == 0x34:
            overrides[30] = self.music_piano_key_count // 2
        companion = _MUSIC_STYLE_COMPANION.get(mode_code)
        if companion is not None:
            overrides.update(companion[self.music_calm])
        send = self.send_command if writer is None else writer
        for packet in build_music_params(mode_code, overrides):
            await send(packet)

    async def async_restore_pre_mode(self) -> None:
        snap = self._pre_mode_snapshot
        match snap.kind:
            case "color_temp":
                await self.send_command(build_color_temp(snap.kelvin, self.model))
            case "white":
                await self.send_command(build_white_brightness(snap.level, self.model))
            case _:
                await self.send_command(build_color_rgb(*snap.rgb, self.model))
        self._enter_static_mode()
