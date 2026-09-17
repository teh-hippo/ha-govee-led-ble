"""Active-mode derivation and mode-switching for the Govee BLE coordinator."""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from .const import MUSIC_MODE_SLUGS
from .control_arbiter import ControlIntent, async_control_intent
from .coordinator_base import _CoordinatorBase
from .coordinator_status import ParsedMode
from .generated_protocol_adapter import build_power
from .light_commands import (
    build_color_rgb,
    build_color_temp,
    build_white_brightness,
)
from .music_commands import (
    edit_music_body,
    music_body_parameters,
    music_body_style,
    prepare_music_body_writes,
    prepare_music_profile_writes,
)
from .music_semantics import music_parameters_depend_on_ic, music_params_for_mode, music_variant
from .native_profile_controls import ProfileWriter
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
    _music_palette: tuple[str, tuple[tuple[int, int, int], ...]] | None = None
    _retained_music_body: tuple[str, bytes] | None = None
    _music_body_revision: int = 0

    @property
    def _music_body(self) -> tuple[str, bytes] | None:
        return self._retained_music_body

    @_music_body.setter
    def _music_body(self, value: tuple[str, bytes] | None) -> None:
        self._retained_music_body = value
        self._music_body_revision += 1

    @property
    def music_body(self) -> bytes | None:
        """Known complete upload, scoped to its selector; never a BLE observation."""
        if self._music_body is not None and self._music_body[0] == self.music_mode:
            return self._music_body[1]
        return None

    @property
    def music_palette(self) -> tuple[tuple[int, int, int], ...] | None:
        """Retained upload for the active selector; unknown is never a default palette."""
        if self._music_palette is not None and self._music_palette[0] == self.music_mode:
            return self._music_palette[1]
        return None

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
        from .effect_compiler import require_native_scenes

        def qualified() -> None:
            require_native_scenes(self.model, self.profile)

        qualified()
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
                qualified()
                await writer(power)
                qualified()
            elif verify:
                await self.send_command(power, write_guard=qualified)
            else:
                packets.insert(0, power)
                power_in_sequence = True
            if not power_in_sequence:
                self.is_on = True
            if verify and self.profile.state_readable and not await self.refresh_state(expected_on=True):
                await self.send_command(power, write_guard=qualified)
                if not await self.refresh_state(expected_on=True):
                    raise RuntimeError(f"Failed to confirm power-on before selecting scene {scene_name!r}")

        async def apply() -> None:
            if writer is not None:
                for packet in packets:
                    qualified()
                    await writer(packet)
                    qualified()
                return
            await self.async_write_effect_sequence(
                packets,
                intent=intent,
                before_write=before_write,
                progress=progress,
                write_guard=qualified,
            )

        await apply()
        qualified()
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
        writer: ProfileWriter | None = None,
        palette: tuple[tuple[int, int, int], ...] | None = None,
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
        color = (
            self.music_color
            if self.profile.supports_music_color and (variant is None or variant.supports_fixed_colour)
            else None
        )
        # Native selection historically sends only style companions; authored profiles
        # and recovery explicitly request all parameter packets.
        writes = prepare_music_profile_writes(
            self.model,
            slug,
            self.music_sensitivity,
            color,
            calm,
            {},
            include_parameters=include_parameters
            and (
                palette is not None
                or self.profile.music_upload_before_selector
                or bool(variant and variant.supports_style)
            ),
            profile=self.profile,
            palette=palette,
        )
        await self.async_write_music_sequence(
            writes,
            mode_code=mode_id,
            physical_ic_count=self.profile.physical_ic_count,
            intent=ControlIntent.USER,
            writer=writer,
        )

    async def async_write_music_sequence(
        self,
        writes: Sequence[tuple[bytes, Mapping[str, Any]]],
        *,
        mode_code: int,
        physical_ic_count: int | None,
        intent: ControlIntent,
        writer: ProfileWriter | None = None,
        retained_body_revision: int | None = None,
    ) -> None:
        variant = music_variant(self.profile, mode_code)
        parameters = {
            spec.profile_key: state[spec.key]
            for spec in (() if variant is None else variant.parameters)
            for _, state in writes
            if spec.key in state
        }
        parameter_keys = next(
            (state["_music_parameter_keys"] for _, state in writes if "_music_parameter_keys" in state), None
        )
        if parameter_keys is not None:
            parameters = {key: value for key, value in parameters.items() if key in parameter_keys}
        dependent = parameter_keys != () and music_parameters_depend_on_ic(variant, parameters)
        candidate = next((state["_music_body"] for _, state in writes if state.get("_music_body") is not None), None)
        first_upload = next((index for index, (_, state) in enumerate(writes) if "_music_body" in state), None)
        last_upload = next(
            (index for index, (_, state) in enumerate(writes) if state.get("_music_body") is not None), None
        )
        states = tuple(
            {
                key: value
                for key, value in state.items()
                if key != "_music_parameter_keys" and (key != "_music_body" or value is None)
            }
            for _, state in writes
        )
        attempted_upload = False
        revision = self._music_body_revision

        def guard(index: int) -> None:
            nonlocal attempted_upload, revision
            if mode_code not in (MUSIC_MODE_SLUGS[slug] for slug in self.profile.music_modes):
                raise ValueError("Device profile no longer supports the requested music mode")
            if dependent and physical_ic_count != self.profile.physical_ic_count:
                raise ValueError("Physical IC count changed since preparation; refresh and retry")
            if music_variant(self.profile, mode_code) != variant:
                raise ValueError("Music variant changed since preparation; refresh and retry")
            if retained_body_revision is not None and self._music_body_revision != (
                revision if attempted_upload else retained_body_revision
            ):
                raise ValueError("Retained music body changed before edit; refresh and retry")
            if index == first_upload:
                attempted_upload = True
                # The shared writer installs the first-fragment None immediately after this guard.
                revision = self._music_body_revision + 1
            if "music_mode" in writes[index][1] and self.active_mode == "colour":
                self._pre_mode_snapshot = self._capture_static_state()

        async with async_control_intent(self, intent):
            try:
                ack_options: dict[str, Any] = {}
                if last_upload is not None and self.profile.music_requires_upload_ack:
                    ack_options = {"require_upload_ack": True, "upload_ack_index": last_upload}
                await self.async_write_effect_sequence(
                    tuple(packet for packet, _ in writes),
                    intent=intent,
                    packet_state_values=states,
                    packet_write_guard=guard,
                    writer=writer,
                    **ack_options,
                )
                if retained_body_revision is not None and self._music_body_revision != revision:
                    raise ValueError("Retained music body changed during edit; refresh and retry")
            except BaseException:
                if attempted_upload and (retained_body_revision is None or self._music_body_revision == revision):
                    self._music_body = None
                    self._music_palette = None
                raise
            if candidate is not None and attempted_upload and revision == self._music_body_revision:
                self._music_body = candidate
            elif candidate is not None and attempted_upload:
                self._music_palette = None

    async def async_apply_music_params(
        self,
        mode_code: int,
        *,
        writer: ProfileWriter | None = None,
        parameters: Mapping[str, Any] | None = None,
        calm: bool | None = None,
    ) -> None:
        if MUSIC_MODE_SLUGS.get(self.music_mode) != mode_code or self.music_body is None:
            raise ValueError("Cannot preserve unknown music body; select or apply a complete profile")
        retained_body_revision = self._music_body_revision
        previous = music_body_parameters(self.music_body, self.music_mode, profile=self.profile)
        parameters = (
            parameters
            if parameters is not None
            else {
                spec.profile_key: getattr(self, spec.key)
                for spec in music_params_for_mode(mode_code, self.profile)
                if hasattr(self, spec.key) and getattr(self, spec.key) != previous.get(spec.profile_key)
            }
        )
        previous_style = music_body_style(self.music_body, self.music_mode, profile=self.profile)
        if calm is None and previous_style is not None and self.music_calm != previous_style:
            calm = self.music_calm
        body = edit_music_body(self.music_body, self.music_mode, parameters, profile=self.profile, calm=calm)
        writes = prepare_music_body_writes(
            self.model, self.music_mode, self.music_sensitivity, body, profile=self.profile
        )
        upload = list(writes[1:-1] if self.profile.music_upload_before_selector else writes[2:])
        # Actual edited keys, rather than every control the mode could support, govern the guard.
        upload[-1][1].update(
            {
                spec.key: parameters[spec.profile_key]
                for spec in music_params_for_mode(mode_code, self.profile)
                if spec.profile_key in parameters
            }
        )
        upload[-1][1]["_music_parameter_keys"] = tuple(parameters)
        if calm is not None:
            upload[-1][1]["music_calm"] = calm
        await self.async_write_music_sequence(
            upload,
            mode_code=mode_code,
            physical_ic_count=self.profile.physical_ic_count,
            intent=ControlIntent.USER,
            writer=writer,
            retained_body_revision=retained_body_revision,
        )

    async def async_restore_pre_mode(self) -> None:
        snap = self._pre_mode_snapshot
        match snap.kind:
            case "color_temp":
                await self.send_command(build_color_temp(snap.kelvin, self.model, profile=self.profile))
            case "white":
                await self.send_command(build_white_brightness(snap.level, self.model))
            case _:
                await self.send_command(build_color_rgb(*snap.rgb, self.model, profile=self.profile))
        self._enter_static_mode()
