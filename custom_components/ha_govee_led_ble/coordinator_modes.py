"""Active-mode derivation and mode-switching for the Govee BLE coordinator."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from .const import MUSIC_MODE_SLUGS
from .control_arbiter import ControlIntent, async_control_intent
from .coordinator_base import _CoordinatorBase
from .coordinator_status import ParsedMode
from .effect_contracts import CapabilityWorkflow, require_effect_route
from .generated_protocol_adapter import build_power
from .light_commands import (
    build_color_rgb,
    build_color_temp,
    build_white_brightness,
)
from .music_commands import build_music_params, prepare_music_request
from .music_semantics import music_params_for_mode, music_variant
from .native_scenes import build_native_scene_packets
from .scenes import MODEL_SCENES, SceneEntry, canonical_scene_key


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
    _music_calm: bool | None = None

    @property
    def music_calm(self) -> bool:
        if self._music_calm is not None:
            return self._music_calm
        variant = music_variant(self.profile, MUSIC_MODE_SLUGS.get(self.music_mode, -1))
        return variant.calm_default if variant and variant.supports_style else False

    @music_calm.setter
    def music_calm(self, value: bool) -> None:
        self._music_calm = value

    @property
    def scene_name_set(self) -> frozenset[str]:
        return frozenset(MODEL_SCENES.get(self.model, ())) if self.profile.supports_scenes else frozenset()

    @property
    def active_mode(self) -> str:
        if not self.is_on:
            return "off"
        if self.diy_code is not None:
            return "custom"
        if self.effect is not None or (self.color_mode is ParsedMode.SCENE and self._scene_code is not None):
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
        scene_entry: SceneEntry | None = None,
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
                scene_entry=scene_entry,
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
        scene_entry: SceneEntry | None = None,
        speed_index: int | None = None,
        canonical_body: bytes | None = None,
        writer: Callable[[bytes], Awaitable[None]] | None = None,
        before_write: Callable[[], Awaitable[None]] | None = None,
        progress: Callable[[int], Awaitable[None]] | None = None,
        verify: bool,
        intent: ControlIntent,
    ) -> None:
        if not self.profile.supports_scenes:
            raise ValueError(f"{self.model} does not support native scenes")
        require_effect_route(self.model, CapabilityWorkflow.NATIVE_SCENES)
        if scene_entry is None:
            scene_name = canonical_scene_key(self.model, scene_name)
            scene = MODEL_SCENES[self.model].get(scene_name)
        else:
            scene = scene_entry
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
        if verify and self.profile.state_readable and not await self.refresh_state(expected_scene_code=scene.code):
            await apply()
            if not await self.refresh_state(expected_scene_code=scene.code):
                raise RuntimeError(f"Failed to confirm scene {scene_name!r}")
        self.color_mode = ParsedMode.SCENE
        self.effect = scene_name
        self._scene_code = scene.code
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
        mode_id = MUSIC_MODE_SLUGS[slug]
        variant = music_variant(self.profile, mode_id)
        calm = (
            (self._music_calm if self._music_calm is not None else variant.calm_default)
            if variant is not None and variant.supports_style
            else False
        )
        color = self.music_color if self.profile.supports_music_color else None
        # Native selection historically sends only style companions; authored profiles
        # and recovery explicitly request all parameter packets.
        packets = prepare_music_request(
            self.model,
            slug,
            self.music_sensitivity,
            color,
            calm,
            {},
            include_parameters=include_parameters and variant is not None and variant.supports_style,
        )
        if self.active_mode == "colour":
            self._pre_mode_snapshot = self._capture_static_state()
        send = self.send_command if writer is None else writer
        for packet in packets:
            await send(packet)
        self.is_on = True
        self.music_mode, self.video_mode = slug, "off"
        self.effect = None
        self.diy_code = None

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
        parameters = {
            spec.profile_key: getattr(self, spec.key) for spec in music_params_for_mode(mode_code, self.profile)
        }
        packets = build_music_params(mode_code, parameters, profile=self.profile, calm=self.music_calm)
        send = self.send_command if writer is None else writer
        for packet in packets:
            await send(packet)

    async def async_restore_pre_mode(self) -> None:
        snap = self._pre_mode_snapshot
        match snap.kind:
            case "color_temp":
                self.install_static_color(kelvin=snap.kelvin)
                await self.send_command(build_color_temp(snap.kelvin, self.model))
            case "white":
                await self.send_command(build_white_brightness(snap.level, self.model))
            case _:
                self.install_static_color(rgb=snap.rgb)
                await self.send_command(build_color_rgb(*snap.rgb, self.model))
        self._enter_static_mode()
