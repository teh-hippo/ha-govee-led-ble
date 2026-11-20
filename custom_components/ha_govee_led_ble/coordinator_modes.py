"""Active-mode derivation and mode-switching for the Govee BLE coordinator."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN, NATIVE_ZONE_CONTROLS, ModelProfile, ReadDomain, same_control_profile
from .control_arbiter import ControlIntent, async_control_intent
from .coordinator_base import _CoordinatorBase, async_prepare_effect_profile
from .coordinator_refresh import RefreshRequest
from .coordinator_sources import has_segmented_sources, native_source_fields, source_kelvin_hint_fields
from .coordinator_status import ParsedMode
from .generated_protocol_adapter import build_power
from .music_commands import (
    MusicWriteSequence,
    edit_music_body,
    music_body_parameters,
    music_body_style,
    prepare_music_body_writes,
    prepare_music_profile_writes,
)
from .music_protocol import music_code_for, music_mode_supports_style
from .music_semantics import (
    music_body_params_for_mode,
    music_parameters_depend_on_ic,
    music_params_for_mode,
    music_variant,
    retained_music_selector_parameters,
)
from .native_profile_controls import ProfileWriter
from .native_scenes import build_native_scene_packets
from .scenes import (
    MODEL_SCENES,
    SceneEntry,
    canonical_scene_key,
    scene_for_profile,
    scene_selector_code,
    scene_supported,
)

if TYPE_CHECKING:
    from .coordinator_recovery import PreparedStaticRecovery
    from .effect_deployments import PriorControlState


class ModeTransitionPurpose(StrEnum):
    SELECTION = "selection"
    PREVIEW = "preview"
    RECOVERY = "recovery"


class ModeTransitionSupersededError(ValueError):
    """A newer device observation invalidated an in-progress mode transition."""


@dataclass
class _ModeTransition:
    owner: asyncio.Task[Any] | None
    captured: bool = False
    installed: bool = False
    snapshot: PriorControlState | None = None
    profile: ModelProfile | None = None
    foreground_generation: int = 0
    purpose: ModeTransitionPurpose | None = None
    profile_generation: int = 0
    subscription: object | None = None
    field_baselines: dict[str, int] = field(default_factory=dict)
    write_baseline: int = 0
    static_restore_started: bool = False
    verifying_resident_effect: bool = False
    last_selector: tuple[object, ...] | None = None
    written_selector: dict[str, Any] | None = None
    superseded: bool = False
    observations_match: Callable[[], bool] | None = None
    powering_off: bool = False

    def current(self) -> bool:
        return not self.superseded and (self.observations_match is None or self.observations_match())

    def require_current(self) -> None:
        if not self.current():
            raise ModeTransitionSupersededError("The observed device state changed during the mode transition")


class _ActiveModeMixin(_CoordinatorBase):
    """Derives the coarse operating mode and routes music-mode entry/exit."""

    _scene_code: int | None
    _music_calm: bool | None = None
    _music_palette: tuple[str, tuple[tuple[int, int, int], ...]] | None = None
    _retained_music_body: tuple[str, bytes] | None = None
    _music_body_revision: int = 0

    def _init_mode_state(self) -> None:
        self.effect: str | None = None
        self.music_mode = "off"
        self.diy_code: int | None = None
        self.diy_companion: int | None = None
        self.color_mode: ParsedMode | None = None
        self._observed_color_mode: ParsedMode | None = None
        self._observed_selector: tuple[object, ...] = ()
        self._selector_revision = 0
        self._mode_write_generation = 0
        self._observed_mode_write_generation = -1
        self._observed_mode_profile_generation = -1
        self._power_write_generation = 0
        self._observed_power_write_generation = -1
        self._observed_power_profile_generation = -1
        self._source_power_observation_generation: dict[str, tuple[int, int]] = {}
        self._scene_code = None
        self._pre_mode_snapshot: PriorControlState | None = None
        self._incomplete_static_exit: PriorControlState | None = None
        self._pre_mode_profile: ModelProfile | None = None
        self._pre_mode_needs_qualification = False
        self._mode_transition: _ModeTransition | None = None
        self.music_sensitivity = 99
        self.music_color: tuple[int, int, int] | None = None
        self.music_fixed_colour: bool | None = None
        self.music_left_colour: int | None = None
        self.music_right_colour: int | None = None
        self.music_separation_point = 1
        self.music_separation_gradient = True
        self.music_hopping_brightness = 50
        self.music_piano_key_count = 15
        self.music_fountain_direction = "clockwise"
        self.music_daynight_segments = 1
        self.music_daynight_speed = 10
        self.music_daynight_gradient = False
        self._initialized_music_parameters: set[str] = set()
        for variant in self.profile.music_variants:
            for spec in music_body_params_for_mode(variant.mode_code, self.profile):
                setattr(self, spec.key, spec.default)
                if not self.profile.can_read(ReadDomain.PHYSICAL_IC_COUNT) or not (
                    variant.requires_physical_ic_count or spec.requires_physical_ic_count
                ):
                    self._initialized_music_parameters.add(spec.key)
            for spec in variant.selector_parameters:
                setattr(self, spec.key, None)

    def _discard_static_baseline(self, *, keep_incomplete_exit: bool = False) -> None:
        self._pre_mode_snapshot = None
        if keep_incomplete_exit and self._incomplete_static_exit is not None:
            return
        self._incomplete_static_exit = None
        self._pre_mode_profile = None
        self._pre_mode_needs_qualification = False

    def _init_video_state(self) -> None:
        self.video_mode = "off"
        self.video_saturation = self.white_brightness = 100
        self.video_full_screen, self.video_sound_effects = True, False
        self.video_sound_effects_softness = 100
        self.video_parameters: dict[str, Any] | None = None
        self.installation_direction: int | None = None
        self.camera_health = "unknown"
        self.strip_direction: int | None = None
        self.camera_position: int | None = None
        self.gradient: int | None = None
        self.camera_status = "unknown"
        self.white_balance_red: int | None = None
        self.white_balance_blue: int | None = None
        self.white_balance_flag: int | None = None
        self.white_balance_default_flag: int | None = None
        self.white_balance_default_red: int | None = None
        self.white_balance_default_blue: int | None = None
        self.white_balance_scalar: int | None = None
        self.relative_brightness: int | None = None
        self.whole_relative_brightness: int | None = None
        self.relative_brightness_left: int | None = None
        self.relative_brightness_top: int | None = None
        self.relative_brightness_right: int | None = None
        self.relative_brightness_bottom: int | None = None
        self.relative_brightness_strip_left: int | None = None
        self.relative_brightness_strip_right: int | None = None
        self.blank_screen: bool | None = None
        self.black_border: bool | None = None
        self.blank_screen_detection: int | None = None
        self.blank_screen_low_brightness_duration_seconds: int | None = None
        self.blank_screen_same_tone_duration_seconds: int | None = None
        self._blank_screen_notification_revision = 0

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
        mode_code = (
            music_code_for(self.model, self.music_mode, profile=self.profile)
            if self.music_mode in self.profile.music_modes
            else -1
        )
        variant = music_variant(self.profile, mode_code)
        return variant.calm_default if variant and variant.supports_style else False

    @music_calm.setter
    def music_calm(self, value: bool) -> None:
        self._music_calm = value

    @property
    def scene_name_set(self) -> frozenset[str]:
        catalogue = self.profile.scene_catalogue_sku or self.model
        return frozenset(
            key for key, scene in MODEL_SCENES.get(catalogue, {}).items() if scene_supported(scene, self.profile)
        )

    @property
    def active_mode(self) -> str:
        if not self.is_on:
            return "off"
        if self.diy_code is not None:
            return "custom"
        if self.effect is not None or (self.color_mode is ParsedMode.SCENE and self._scene_code is not None):
            return "scene"
        if self.color_mode is ParsedMode.MUSIC or self.music_mode not in (None, "off"):
            return "music"
        if self.video_mode not in (None, "off"):
            return "video"
        return "colour"

    @asynccontextmanager
    async def async_mode_transition(
        self, *, purpose: ModeTransitionPurpose | None = None
    ) -> AsyncIterator[_ModeTransition]:
        previous = self._mode_transition
        owner = asyncio.current_task()
        if (
            previous is not None
            and previous.owner is owner
            and not (purpose is ModeTransitionPurpose.RECOVERY and previous.purpose is not purpose)
        ):
            if purpose is ModeTransitionPurpose.PREVIEW and previous.purpose is None:
                previous.purpose = purpose
            if purpose is ModeTransitionPurpose.SELECTION:
                await self.async_admit_effect_selection()
            yield previous
            return
        transition = _ModeTransition(
            owner,
            purpose=purpose,
            captured=purpose is ModeTransitionPurpose.RECOVERY,
            installed=purpose is ModeTransitionPurpose.RECOVERY,
            field_baselines=dict(self._field_revisions),
        )
        self._mode_transition = transition
        try:
            if (
                purpose is ModeTransitionPurpose.RECOVERY
                and previous is not None
                and previous.owner is owner
                and previous.purpose in (ModeTransitionPurpose.SELECTION, ModeTransitionPurpose.PREVIEW)
            ):
                transition.superseded = previous.superseded
                zones = self.profile.boolean_controls.intersection(NATIVE_ZONE_CONTROLS)
                source_fields = (*native_source_fields(self.profile), *source_kelvin_hint_fields(self.profile))

                def appearance() -> tuple[object, ...]:
                    basic = (
                        self._selector_revision,
                        self.is_on,
                        self.brightness_pct,
                        *((self.projector_appearance,) if self.profile.projector_grammar is not None else ()),
                        *(self.boolean_control_state.get(zone) for zone in zones),
                        *(getattr(self, name) for name in source_fields),
                    )
                    if self.color_mode is not ParsedMode.COLOUR:
                        return basic
                    return (
                        *basic,
                        self.rgb_color,
                        self.color_temp_kelvin,
                        self.static_gradual,
                        tuple(self.segment_colors),
                        tuple(self.segment_brightness),
                    )

                # Deployment rollback must retain its starting context across persistence.
                starting_appearance = appearance()
                generation, subscription = self._profile_generation, self._notification_token
                foreground = self._control_arbiter.foreground_generation
                attempts = self.control_write_attempts
                transition.observations_match = lambda: (
                    self.control_write_attempts != attempts
                    or (
                        generation == self._profile_generation
                        and subscription is self._notification_token
                        and foreground == self._control_arbiter.foreground_generation
                        and appearance() == starting_appearance
                    )
                )
            if purpose is ModeTransitionPurpose.SELECTION:
                await self.async_admit_effect_selection()
            yield transition
        finally:
            if self._mode_transition is transition:
                self._mode_transition = previous

    async def async_admit_effect_selection(self) -> None:
        transition = self._mode_transition
        if transition is None or transition.owner is not asyncio.current_task():
            raise RuntimeError("Effect selection requires an owned mode transition")
        if transition.purpose is ModeTransitionPurpose.RECOVERY or (
            transition.purpose in (ModeTransitionPurpose.SELECTION, ModeTransitionPurpose.PREVIEW)
            and transition.captured
        ):
            return
        if transition.captured:
            raise RuntimeError("Effect selection must be admitted before control writes")
        preview = transition.purpose is ModeTransitionPurpose.PREVIEW
        snapshot = await self.async_prepare_static_baseline()
        if (
            preview
            and (
                has_segmented_sources(self.profile)
                or self.profile.configured_string_counts
                or self.profile.projector_grammar
            )
            and not snapshot.static_colour_observed
        ):
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="live_recovery_not_observed")
        transition.snapshot = snapshot
        transition.profile = self.profile
        transition.profile_generation = self._profile_generation
        transition.subscription = self._notification_token
        transition.foreground_generation = self._control_arbiter.foreground_generation
        transition.write_baseline = self.control_write_attempts
        transition.captured = True
        transition.purpose = ModeTransitionPurpose.PREVIEW if preview else ModeTransitionPurpose.SELECTION

    def _rebind_selection_retry(self) -> None:
        transition = self._mode_transition
        if (
            transition is not None
            and transition.owner is asyncio.current_task()
            and transition.purpose in (ModeTransitionPurpose.SELECTION, ModeTransitionPurpose.PREVIEW)
            and transition.profile is not None
            and transition.captured
            and self.control_write_attempts > transition.write_baseline
            and transition.foreground_generation == self._control_arbiter.foreground_generation
            and same_control_profile(transition.profile, self.profile)
        ):
            # A permitted transport retry retains the pre-attempt intent, not the partially changed current state.
            transition.profile = self.profile
            transition.profile_generation = self._profile_generation
            transition.subscription = self._notification_token
            transition.installed = False

    async def async_apply_native_scene(
        self,
        scene_name: str,
        *,
        scene_entry: SceneEntry | None = None,
        speed_index: int | None = None,
        canonical_body: bytes | None = None,
        before_write: Callable[[], Awaitable[None]] | None = None,
        progress: Callable[[int], Awaitable[None]] | None = None,
        verify: bool = True,
        intent: ControlIntent = ControlIntent.USER,
    ) -> None:
        async with (
            async_control_intent(self, intent),
            self.async_mode_transition(
                purpose=ModeTransitionPurpose.PREVIEW if intent is ControlIntent.PREVIEW else None
            ),
        ):
            await self._async_apply_native_scene_locked(
                scene_name,
                scene_entry=scene_entry,
                speed_index=speed_index,
                canonical_body=canonical_body,
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
        before_write: Callable[[], Awaitable[None]] | None = None,
        progress: Callable[[int], Awaitable[None]] | None = None,
        verify: bool,
        intent: ControlIntent,
    ) -> None:
        from .effect_compiler import require_native_scenes
        from .effect_domain import BuiltinScene
        from .layered_scene import CatalogueRef

        if scene_entry is None:
            scene_name = canonical_scene_key(self.model, scene_name)
            scene = MODEL_SCENES[self.model].get(scene_name)
        else:
            scene = scene_entry
        if scene is None:
            raise ValueError(f"unknown native scene {scene_name!r}")
        content = BuiltinScene(CatalogueRef(self.model, scene.scene_id, scene.effect_id))
        profile = await async_prepare_effect_profile(self, intent=intent, content=content)
        route = (profile.command_grammar, profile.effect_grammar, profile.selector_only_scene_bits)
        prepared_body = scene.scene_type == 2 and profile.rgbic_scene_v0 is not None

        def qualified() -> None:
            self._reconcile_authorization()
            current = self.effect_authorization_profile
            require_native_scenes(self.model, current)
            scene_for_profile(scene, current)
            if route != (current.command_grammar, current.effect_grammar, current.selector_only_scene_bits):
                raise ValueError("Device scene route changed during scene preparation")
            if prepared_body and profile.rgbic_scene_v0 != current.rgbic_scene_v0:
                raise ValueError("RGBIC scene format changed during scene preparation")
            if prepared_body and profile.physical_ic_count != current.physical_ic_count:
                raise ValueError("RGBIC scene geometry changed during scene preparation")

        qualified()
        selector = scene_selector_code(self.model, scene, profile=profile)
        packets = build_native_scene_packets(
            self.model,
            scene,
            speed_index=speed_index,
            canonical_body=canonical_body,
            profile=profile,
        )
        upload_count = len(packets) - 1
        async with self.async_mode_transition(purpose=ModeTransitionPurpose.SELECTION) as transition:
            power_in_sequence = False
            if not self.is_on:
                power = build_power(True, self.model)
                if verify:
                    await self.send_command(power, write_guard=qualified)
                else:
                    packets.insert(0, power)
                    power_in_sequence = True
                if not power_in_sequence:
                    self.is_on = True
                if (
                    verify
                    and self.profile.state_readable
                    and await self.refresh_state(RefreshRequest(on=True)) is False
                ):
                    await self.send_command(power, write_guard=qualified)
                    if await self.refresh_state(RefreshRequest(on=True)) is False:
                        raise RuntimeError(f"Failed to confirm power-on before selecting scene {scene_name!r}")
            require_ack = bool(upload_count and self.profile.diy_requires_upload_ack)
            await self.async_write_effect_sequence(
                packets,
                intent=intent,
                before_write=before_write,
                progress=progress,
                write_guard=qualified,
                require_upload_ack=require_ack,
                upload_ack_index=upload_count - 1 + int(power_in_sequence) if require_ack else None,
            )
            qualified()
            if power_in_sequence:
                self.is_on = True
            if verify and self.profile.supports_color_mode_readback:
                observed = await self.async_observe_effect({"scene_code": selector})
                if observed is False:
                    await self.send_command(packets[-1], write_guard=qualified)
                    observed = await self.async_observe_effect({"scene_code": selector})
                if observed is False:
                    raise RuntimeError(f"Failed to confirm scene {scene_name!r}")
            transition.require_current()
            self.color_mode = ParsedMode.SCENE
            self.effect = scene_name
            self._scene_code = selector
            self.diy_code = None
            self.music_mode = self.video_mode = "off"
            self.async_set_updated_data(self.data or {})

    def _capture_static_state(self) -> PriorControlState:
        return self.capture_effect_control_state()

    def _enter_static_mode(self) -> None:
        """Clear every non-static mode so exactly one operating mode is active."""
        transition = self._mode_transition
        if transition is None or transition.purpose not in (
            ModeTransitionPurpose.SELECTION,
            ModeTransitionPurpose.RECOVERY,
            ModeTransitionPurpose.PREVIEW,
        ):
            self._discard_static_baseline()
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
        on_write: Callable[[], None] | None = None,
    ) -> None:
        if slug == "off":
            await self.async_restore_pre_mode()
            return
        if slug not in self.profile.music_modes:
            raise ValueError(f"{self.model} does not support music mode {slug}")
        mode_id = music_code_for(self.model, slug, profile=self.profile)
        variant = music_variant(self.profile, mode_id)
        supports_style = (variant is not None and variant.supports_style) or music_mode_supports_style(
            self.model, mode_id, profile=self.profile
        )
        calm_default = variant.calm_default if variant is not None else False
        calm = (self._music_calm if self._music_calm is not None else calm_default) if supports_style else False
        color = (
            self.music_color
            if self.profile.supports_music_color and (variant is None or variant.supports_fixed_colour)
            else None
        )
        if color is None and variant is not None:
            color = variant.fixed_colour_default
        # Native selection historically sends only style companions; authored profiles
        # and recovery explicitly request all parameter packets.
        writes = prepare_music_profile_writes(
            self.model,
            slug,
            self.music_sensitivity,
            color,
            calm,
            retained_music_selector_parameters(self, mode_id, self.profile),
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
            on_write=on_write,
        )

    async def async_write_music_sequence(
        self,
        writes: MusicWriteSequence,
        *,
        mode_code: int,
        physical_ic_count: int | None,
        intent: ControlIntent,
        writer: ProfileWriter | None = None,
        retained_body_revision: int | None = None,
        on_write: Callable[[], None] | None = None,
    ) -> None:
        variant = music_variant(self.profile, mode_code)
        parameters = {
            spec.profile_key: state[spec.key]
            for spec in (() if variant is None else variant.parameters)
            for _, state in writes
            if spec.key in state
        }
        parameter_keys = writes.parameter_keys
        if parameter_keys is not None:
            parameters = {key: value for key, value in parameters.items() if key in parameter_keys}
        dependent = parameter_keys != () and music_parameters_depend_on_ic(variant, parameters)
        candidate = writes.body
        first_upload, last_upload = writes.first_upload, writes.last_upload
        states = tuple(state for _, state in writes)
        attempted_upload = False
        revision = self._music_body_revision

        def guard() -> None:
            self._reconcile_authorization()
            profile = self._authorization_profile()
            if mode_code not in (music_code_for(self.model, slug, profile=profile) for slug in profile.music_modes):
                raise ValueError("Device profile no longer supports the requested music mode")
            if dependent and physical_ic_count != profile.physical_ic_count:
                raise ValueError("Physical IC count changed since preparation; refresh and retry")
            if music_variant(profile, mode_code) != variant:
                raise ValueError("Music variant changed since preparation; refresh and retry")
            if retained_body_revision is not None and self._music_body_revision != (
                revision if attempted_upload else retained_body_revision
            ):
                raise ValueError("Retained music body changed before edit; refresh and retry")

        async with (
            async_control_intent(self, intent),
            self.async_mode_transition(purpose=ModeTransitionPurpose.SELECTION),
        ):
            try:

                def commit(index: int) -> None:
                    nonlocal attempted_upload, revision
                    if index == first_upload:
                        self._music_body = None
                        self._music_palette = None
                        attempted_upload = True
                        revision = self._music_body_revision
                    if index == last_upload:
                        if writes.palette is not None:
                            self._music_palette = writes.palette
                        if writes.unknown_style:
                            self._music_calm = None
                    if "music_mode" in writes[index][1]:
                        self._scene_code = None
                        self.color_mode = ParsedMode.MUSIC
                    if on_write is not None and (
                        "music_mode" in writes[index][1] or index in (first_upload, last_upload)
                    ):
                        on_write()

                sequence_options: dict[str, Any] = {}
                if last_upload is not None and self.profile.music_requires_upload_ack:
                    sequence_options = {"require_upload_ack": True, "upload_ack_index": last_upload}
                if not self.profile.music_retry_after_upload:
                    sequence_options["retry_allowed"] = lambda: not attempted_upload
                await self.async_write_effect_sequence(
                    tuple(packet for packet, _ in writes),
                    intent=intent,
                    packet_state_values=states,
                    write_guard=guard,
                    writer=writer,
                    **sequence_options,
                    packet_on_write=commit,
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
        if (
            self.music_mode not in self.profile.music_modes
            or music_code_for(self.model, self.music_mode, profile=self.profile) != mode_code
        ):
            raise ValueError("Cannot preserve unknown music body; select or apply a complete profile")
        if self.music_body is None:
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
        packet, final_state = upload[-1]
        final_state = {
            **final_state,
            **{
                spec.key: parameters[spec.profile_key]
                for spec in music_params_for_mode(mode_code, self.profile)
                if spec.profile_key in parameters
            },
        }
        if calm is not None:
            final_state["music_calm"] = calm
        upload[-1] = (packet, final_state)
        last_upload = len(upload) - 1
        if self.profile.music_params_require_activation:
            upload.append(writes[-1] if self.profile.music_upload_before_selector else writes[1])
        await self.async_write_music_sequence(
            replace(
                writes,
                writes=tuple(upload),
                first_upload=0,
                last_upload=last_upload,
                parameter_keys=tuple(parameters),
                unknown_style=writes.unknown_style and calm is None,
            ),
            mode_code=mode_code,
            physical_ic_count=self.profile.physical_ic_count,
            intent=ControlIntent.USER,
            writer=writer,
            retained_body_revision=retained_body_revision,
        )

    async def async_restore_pre_mode(self, prepared: PreparedStaticRecovery | None = None) -> None:
        if prepared is None:
            guard = await self.async_preflight_static_off()
            intent = self._control_arbiter.current_task_intent or ControlIntent.USER
            async with (
                async_control_intent(self, intent),
                self.async_mode_transition(purpose=ModeTransitionPurpose.RECOVERY),
                self.async_prepare_static_recovery(guard) as prepared,
            ):
                if prepared is not None:
                    await self.async_restore_pre_mode(prepared)
        elif not await self.async_restore_effect_control_state(prepared, overwritten_diy_code=None):
            raise ValueError("No complete static state is available to restore")
        elif self.profile.supports_color_mode_readback:
            self._discard_static_baseline()
        else:
            self._pre_mode_snapshot = prepared.state
