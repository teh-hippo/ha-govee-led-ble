"""Effect recovery: restoring the prior control state after previews and effect writes."""

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, nullcontext
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, cast

from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN, NATIVE_ZONE_CONTROLS, ModelProfile, ReadDomain, get_profile, same_control_profile
from .control_arbiter import ControlIntent, async_control_intent
from .coordinator_base import _CoordinatorBase
from .coordinator_modes import ModeTransitionPurpose
from .coordinator_refresh import RefreshRequest
from .coordinator_sources import (
    PreparedSourceValue,
    has_segmented_sources,
    native_source_fields,
    source_kelvin_hint_fields,
)
from .coordinator_status import (
    ParsedMode,
)
from .effect_contracts import CapabilityState, CapabilityWorkflow, profile_supports_workflow
from .effect_deployments import PriorControlState
from .generated_protocol_adapter import (
    build_brightness,
    build_diy_activation,
    build_power,
    require_profile_packet,
    table_kelvin_rgb,
)
from .light_commands import (
    build_color_rgb,
    build_color_temp,
    build_segment_brightness_packets,
    build_segment_color_temp,
    build_segment_kelvin_packets,
    build_segment_paint,
    normalize_kelvin,
    static_colour_matches,
)
from .music_commands import MusicWriteSequence, prepare_music_profile_writes
from .music_protocol import music_code_for
from .music_semantics import (
    COMPANION_MUSIC_LAYOUTS,
    capture_music_parameters,
    music_variant,
)
from .native_profile_controls import (
    apply_active_video_mode,
    apply_black_border,
    apply_blank_screen,
    apply_relative_brightness,
    apply_white_balance,
    apply_whole_relative_brightness,
)
from .scenes import (
    MODEL_SCENES,
    canonical_scene_key,
    resolve_scene_code,
    scene_selector_code,
    scene_supported,
)
from .video_applicability import (
    video_control_states,
    video_identity_fields,
)

if TYPE_CHECKING:
    from .coordinator import GoveeBLECoordinator

_LOGGER = logging.getLogger(__name__)

# (name passed to apply_active_video_mode, coordinator/state attribute, restore control)
_VIDEO_VALUE_FIELDS = (
    ("full_screen", "video_full_screen", "capture_region"),
    ("saturation", "video_saturation", "saturation"),
    ("sound_effects", "video_sound_effects", "sound_effects"),
    ("sound_effects_softness", "video_sound_effects_softness", "sound_effects"),
)


@dataclass(frozen=True)
class PreparedStaticRecovery:
    state: PriorControlState
    packets: tuple[bytes, ...]
    whole_kelvin: bool
    profile: ModelProfile
    generation: int
    subscription: object | None
    native_writes: tuple[PreparedSourceValue, ...] = ()

    def check(self, coordinator: _CoordinatorBase) -> None:
        transition = coordinator._mode_transition
        if (
            not same_control_profile(coordinator.profile, self.profile)
            or coordinator._profile_generation != self.generation
            or self.subscription is not None
            and coordinator._notification_token is not self.subscription
            or transition is not None
            and transition.owner is asyncio.current_task()
            and transition.purpose is ModeTransitionPurpose.RECOVERY
            and transition.snapshot is not None
            and coordinator._pre_mode_snapshot is not transition.snapshot
        ):
            raise ValueError("The colour restoration context changed")


class _RecoveryMixin(_CoordinatorBase):
    @property
    def _as_coordinator(self) -> GoveeBLECoordinator:
        # The native-control helpers are typed on the concrete coordinator this mixin is part of.
        return cast("GoveeBLECoordinator", self)

    def require_static_baseline(self) -> PriorControlState:
        if self._pre_mode_snapshot is None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="recovery_not_ready")
        return self._pre_mode_snapshot

    def _static_history_profile_current(self) -> bool:
        profile = self._pre_mode_profile
        if self._pre_mode_snapshot is None:
            return False
        if not self._pre_mode_needs_qualification:
            return True
        if profile is None:
            self._discard_static_baseline()
            return False
        if (
            not self.identity_fields_confirmed(
                profile.profile_identity_fields | frozenset(video_identity_fields(profile))
            )
            or profile.segment_count_ic_divisor is not None
            and not self._physical_ic_count_confirmed
            or profile.configured_string_counts
            and not self._configured_strings_confirmed
        ):
            return False
        if not same_control_profile(profile, self._as_coordinator._authorization_profile()):
            self._discard_static_baseline()
            return False
        return True

    @asynccontextmanager
    async def _async_qualified_static_history(self) -> AsyncIterator[None]:
        self.require_static_baseline()
        foreground = self._control_arbiter.foreground_generation
        subscription = self._notification_token
        observations = {field: self._field_revisions.get(field, 0) for field in ("color_mode", "segment_colors")}
        async with self._lock:
            await self._ensure_connected()
        if foreground != self._control_arbiter.foreground_generation:
            raise ValueError("Static restoration ownership changed; refresh and retry")
        if subscription is not None and subscription is not self._notification_token:
            raise ValueError("Static restoration subscription changed; refresh and retry")
        async with self.async_mask_transaction():
            if self.color_mode is ParsedMode.COLOUR and any(
                self._field_revisions.get(field, 0) != revision for field, revision in observations.items()
            ):
                self._discard_static_baseline()
                raise ValueError("Static restoration observations changed; refresh and retry")
            if self._pre_mode_needs_qualification:
                if not self._static_history_profile_current():
                    raise HomeAssistantError(translation_domain=DOMAIN, translation_key="recovery_not_ready")
                self._pre_mode_needs_qualification = False
            self.require_static_baseline()
            yield

    @asynccontextmanager
    async def async_prepare_static_recovery(
        self, prepared: PreparedStaticRecovery | None = None
    ) -> AsyncIterator[PreparedStaticRecovery]:
        transition = self._mode_transition
        if (
            transition is None
            or transition.owner is not asyncio.current_task()
            or transition.purpose is not ModeTransitionPurpose.RECOVERY
            or self._control_arbiter.current_task_intent is None
        ):
            raise RuntimeError("Static restoration requires an owned recovery transition")
        if prepared is not None:
            yield self.prepare_static_recovery(prepared)
        else:
            async with self._async_qualified_static_history():
                yield self.prepare_static_recovery()

    def prepare_static_recovery(self, prepared: PreparedStaticRecovery | None = None) -> PreparedStaticRecovery:
        transition = self._mode_transition
        if (
            transition is None
            or transition.owner is not asyncio.current_task()
            or transition.purpose is not ModeTransitionPurpose.RECOVERY
            or self._control_arbiter.current_task_intent is None
        ):
            raise RuntimeError("Static restoration requires an owned recovery transition")
        state = self.require_static_baseline()
        if prepared is not None and transition.snapshot is not state:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="recovery_not_ready")
        prepared = prepared or self._prepare_static_colour(state)
        if prepared is None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="recovery_not_ready")
        prepared.check(self)
        if transition.snapshot is None:
            transition.snapshot = state
            transition.profile = self.profile
            transition.profile_generation = self._profile_generation
            transition.subscription = self._notification_token
            transition.foreground_generation = self._control_arbiter.foreground_generation
        return prepared

    async def async_prepare_static_baseline(self) -> PriorControlState:
        if self._pre_mode_needs_qualification:
            async with self._async_qualified_static_history():
                pass
        profile = self.profile
        transition = self._mode_transition
        baselines = transition.field_baselines if transition is not None else dict(self._field_revisions)

        def fresh(field: str) -> bool:
            return self._field_revisions.get(field, 0) > baselines.get(field, 0) and self.source_field_fresh(field)

        if (
            self.color_mode is not ParsedMode.COLOUR
            and profile.supports_color_mode_readback
            and not fresh("color_mode")
        ):
            if (
                await self.refresh_state(
                    RefreshRequest(
                        query_segments=False,
                        query_native_settings=False,
                        required_domains=profile.read_domains
                        & {ReadDomain.POWER, ReadDomain.COLOUR_MODE, ReadDomain.MODE},
                    )
                )
                is not True
            ):
                raise HomeAssistantError(translation_domain=DOMAIN, translation_key="recovery_read_failed")
        if not same_control_profile(profile, self.profile):
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="recovery_not_ready")
        if self.color_mode is not ParsedMode.COLOUR:
            baseline = self._pre_mode_snapshot
        else:
            fields = {
                *(("is_on",) if profile.can_read(ReadDomain.POWER) else ()),
                *(("brightness_pct",) if profile.can_read(ReadDomain.BRIGHTNESS) else ()),
                *(("color_mode",) if profile.supports_color_mode_readback else ()),
                *(f"boolean_{name}" for name in profile.boolean_controls.intersection(NATIVE_ZONE_CONTROLS)),
                *native_source_fields(profile),
                *source_kelvin_hint_fields(profile),
            }
            segment_fields = (
                {"segment_colors"} if profile.can_read(ReadDomain.SEGMENTS) and profile.supports_segments else set()
            )
            if segment_fields and profile.supports_segment_brightness:
                segment_fields.add("segment_brightness")
            fields |= segment_fields
            missing = {field for field in fields if not fresh(field)}
            refreshed: bool | None
            if missing and missing <= segment_fields:
                refreshed = await self.async_refresh_segments()
            elif missing:
                refreshed = await self.refresh_state(
                    RefreshRequest(
                        refresh_all=True,
                        query_segments=profile.can_read(ReadDomain.SEGMENTS),
                        required_domains=profile.read_domains
                        & {
                            ReadDomain.POWER,
                            ReadDomain.BRIGHTNESS,
                            ReadDomain.COLOUR_MODE,
                            ReadDomain.MODE,
                            ReadDomain.SEGMENTS,
                        },
                    )
                )
            else:
                refreshed = True
            if not same_control_profile(profile, self.profile):
                raise HomeAssistantError(translation_domain=DOMAIN, translation_key="recovery_not_ready")
            if refreshed is not True or any(not fresh(field) for field in fields):
                raise HomeAssistantError(translation_domain=DOMAIN, translation_key="recovery_read_failed")
            baseline = self._pre_mode_snapshot
            if self.color_mode is ParsedMode.COLOUR:
                baseline = self.capture_effect_control_state()
                scalar_field = (
                    "color_temp_kelvin"
                    if self.color_temp_kelvin is not None
                    and (profile.static_readback_kelvin or profile.static_readback_nonzero_kelvin)
                    else "rgb_color"
                    if profile.static_readback_echoes_color
                    else None
                )
                if (
                    not self._power_known
                    or not self._brightness_pct_known
                    or not profile.supports_segments
                    and (not self._static_colour_known or scalar_field is not None and not fresh(scalar_field))
                ):
                    baseline = None
        if baseline is None or self._prepare_static_colour(baseline) is None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="recovery_not_ready")
        return baseline

    def capture_effect_control_state(self) -> PriorControlState:
        current_source_layout = (
            self._client is not None
            and self._client.is_connected
            and self._notify_started_monotonic is not None
            and self._field_received_at.get("segment_colors", -1) >= self._notify_started_monotonic
            and self._field_received_at.get("color_mode", -1) >= self._notify_started_monotonic
            and self._observed_mode_write_generation == self._mode_write_generation
            and self._observed_mode_profile_generation == self._profile_generation
        )
        guarded_colours = any(
            not static_colour_matches(self.segment_colors[index], expected[0], self.profile)
            for index in range(len(self.segment_colors))
            if (expected := self._expected_state.get(f"segment_colour_{index}")) is not None
        )
        observed_segments = (
            not guarded_colours
            and self.segment_state_source == "observed"
            and (not self.profile.supports_segments or current_source_layout)
            and self._brightness_pct_known
        )
        delivered_segments = (
            self.profile.supports_segments
            and not guarded_colours
            and not self.profile.can_read(ReadDomain.SEGMENTS)
            and self.color_mode is ParsedMode.COLOUR
            and len(self.segment_kelvin) == self.profile.segment_count
            and all(value is not None for value in self.segment_kelvin)
            and self._brightness_pct_known
        )
        known_segments = observed_segments or delivered_segments
        zone_flags = {
            name: value
            for name, value in self.boolean_control_state.items()
            if name in NATIVE_ZONE_CONTROLS
            and self._notify_started_monotonic is not None
            and self._field_received_at.get(f"boolean_{name}", -1) >= self._notify_started_monotonic
        }
        if self.profile.minimum_enabled_sources:
            zone_flags = self._as_coordinator._fresh_source_power() or {}
        # active_mode hides the resident mode while powered off and maps unknown to colour.
        mode = (
            "unknown"
            if self.color_mode is ParsedMode.UNKNOWN or self.color_mode is ParsedMode.COLOUR and self.color_temp_unknown
            else "custom"
            if self.diy_code is not None
            else "scene"
            if self.effect is not None or self.scene_code is not None
            else "music"
            if self.color_mode is ParsedMode.MUSIC or self.music_mode not in (None, "off")
            else "video"
            if self.video_mode not in (None, "off")
            else "colour"
        )
        observed_controls: dict[str, int | None] = {
            name: getattr(self, name)
            if self._notify_started_monotonic is not None
            and self._field_received_at.get(name, -1) >= self._notify_started_monotonic
            else None
            for name in ("top_kelvin", "bottom_kelvin", "bottom_brightness", "ripple_speed")
        }
        music_colour = self.music_color
        if mode == "music" and self.music_mode in self.profile.music_modes:
            variant = music_variant(self.profile, music_code_for(self.model, self.music_mode, profile=self.profile))
            if (
                variant
                and variant.fixed_colour_default is not None
                and not self._as_coordinator.source_field_fresh("music_color")
            ):
                music_colour = None
        return PriorControlState(
            mode=mode,
            is_on=self.is_on,
            brightness_pct=self.brightness_pct,
            rgb_color=self.rgb_color,
            color_temp_kelvin=self.color_temp_kelvin,
            static_rgb_known=self._static_rgb_known
            and (self.segment_state_source == "observed" or delivered_segments)
            or not self.profile.supports_segments
            and self._static_colour_known
            and self.color_temp_kelvin is None,
            static_gradual=self.static_gradual if self.color_mode is ParsedMode.COLOUR else None,
            static_colour_observed=self.color_mode is ParsedMode.COLOUR
            and (
                observed_segments
                and self.profile.can_read(ReadDomain.SEGMENTS)
                or not self.profile.supports_segments
                and self._static_colour_known
                and self.source_field_fresh("color_mode")
                and self.source_field_fresh("color_temp_kelvin" if self.color_temp_kelvin is not None else "rgb_color")
                and (
                    self.color_temp_kelvin_source == "observed"
                    if self.color_temp_kelvin is not None
                    else self.rgb_color_source == "observed"
                )
            ),
            panel_enabled=zone_flags.get("panel_enabled"),
            ring_enabled=zone_flags.get("ring_enabled"),
            left_bar_enabled=zone_flags.get("left_bar_enabled"),
            right_bar_enabled=zone_flags.get("right_bar_enabled"),
            pole_enabled=zone_flags.get("pole_enabled"),
            base_enabled=zone_flags.get("base_enabled"),
            source_0_enabled=zone_flags.get("source_0_enabled"),
            source_1_enabled=zone_flags.get("source_1_enabled"),
            top_enabled=zone_flags.get("top_enabled"),
            middle_enabled=zone_flags.get("middle_enabled"),
            side_enabled=zone_flags.get("side_enabled"),
            bottom_enabled=zone_flags.get("bottom_enabled"),
            segment_kelvin=tuple(
                value
                if (expected := self._expected_state.get(f"segment_colour_{index}")) is None
                or static_colour_matches(self.segment_colors[index], expected[0], self.profile)
                else None
                for index, value in enumerate(self.segment_kelvin)
            )
            if known_segments
            and self.color_mode is ParsedMode.COLOUR
            and len(self.segment_kelvin) == self.profile.segment_count
            else None,
            top_kelvin=observed_controls["top_kelvin"],
            bottom_kelvin=observed_controls["bottom_kelvin"],
            bottom_brightness=observed_controls["bottom_brightness"],
            ripple_speed=observed_controls["ripple_speed"],
            left_bar_kelvin=self.left_bar_kelvin
            if self._notify_started_monotonic is not None
            and self._field_received_at.get("left_bar_kelvin", -1) >= self._notify_started_monotonic
            else None,
            right_bar_kelvin=self.right_bar_kelvin
            if self._notify_started_monotonic is not None
            and self._field_received_at.get("right_bar_kelvin", -1) >= self._notify_started_monotonic
            else None,
            segment_colors=tuple(self.segment_colors) if known_segments else None,
            segment_brightness=tuple(self.segment_brightness)
            if known_segments and (self.segment_brightness_readable or all(self.segment_brightness_known))
            else None,
            effect=self.effect,
            scene_code=self.scene_code,
            diy_code=self.diy_code,
            diy_companion=self.diy_companion
            if self.color_mode is ParsedMode.DIY
            and self._notify_started_monotonic is not None
            and self._field_received_at.get("diy_companion", -1) >= self._notify_started_monotonic
            else None,
            music_mode=self.music_mode,
            music_model=self.model,
            music_parameters=capture_music_parameters(self, self.profile, self.music_mode),
            music_palette=self.music_palette,
            music_body=self.music_body,
            video_mode=self.video_mode,
            video_parameters=dict(self.video_parameters) if self.video_parameters is not None else None,
            whole_relative_brightness=self.whole_relative_brightness,
            music_sensitivity=self.music_sensitivity,
            music_calm=self.music_calm,
            music_color=music_colour,
            video_full_screen=self.video_full_screen,
            video_saturation=self.video_saturation,
            video_sound_effects=self.video_sound_effects,
            video_sound_effects_softness=self.video_sound_effects_softness,
            white_balance_red=self.white_balance_red,
            white_balance_blue=self.white_balance_blue,
            white_balance_flag=self.white_balance_flag,
            white_balance_default_flag=self.white_balance_default_flag,
            white_balance_default_red=self.white_balance_default_red,
            white_balance_default_blue=self.white_balance_default_blue,
            white_balance_scalar=self.white_balance_scalar,
            relative_brightness=self.relative_brightness,
            relative_brightness_left=self.relative_brightness_left,
            relative_brightness_top=self.relative_brightness_top,
            relative_brightness_right=self.relative_brightness_right,
            relative_brightness_bottom=self.relative_brightness_bottom,
            relative_brightness_strip_left=self.relative_brightness_strip_left,
            relative_brightness_strip_right=self.relative_brightness_strip_right,
            blank_screen=self.blank_screen,
            black_border=self.black_border,
            blank_screen_detection=self.blank_screen_detection,
            blank_screen_low_brightness_duration_seconds=self.blank_screen_low_brightness_duration_seconds,
            blank_screen_same_tone_duration_seconds=self.blank_screen_same_tone_duration_seconds,
        )

    async def async_restore_effect_control_state(
        self,
        state: PriorControlState | PreparedStaticRecovery,
        *,
        overwritten_diy_code: int | None,
    ) -> bool:
        intent = self._control_arbiter.current_task_intent or ControlIntent.USER
        async with (
            async_control_intent(self, intent),
            self.async_mode_transition(purpose=ModeTransitionPurpose.RECOVERY),
        ):
            if (state.state if isinstance(state, PreparedStaticRecovery) else state).mode == "colour" and get_profile(
                self.model
            ).static_identity_fields:
                await self._as_coordinator.async_prepare_identity_gated_control()
            prepared = state if isinstance(state, PreparedStaticRecovery) else None
            if prepared is not None:
                prepared.check(self)
            return await self._async_restore_prior_control_state(
                prepared.state if prepared is not None else cast(PriorControlState, state),
                overwritten_diy_code=overwritten_diy_code,
                prepared_colour=prepared,
            )

    async def _async_restore_prior_control_state(
        self,
        state: PriorControlState,
        *,
        overwritten_diy_code: int | None,
        prepared_colour: PreparedStaticRecovery | None = None,
    ) -> bool:
        if state.mode == "custom" and self.profile.diy_upload_transport == "single":
            return False
        if state.mode == "colour":
            prepared_colour = prepared_colour or self._prepare_static_colour(state)
            if prepared_colour is None:
                if not state.is_on:
                    await self.send_command(build_power(False, self.model), state_values={"is_on": False})
                    await self.refresh_state(RefreshRequest(on=False))
                return False
        native_zones = self.profile.boolean_controls.intersection(NATIVE_ZONE_CONTROLS)
        expected = {name: value for name in native_zones if (value := getattr(state, name)) is not None}
        if self.profile.minimum_enabled_sources and (
            set(expected) != native_zones
            or not (
                self.profile.minimum_enabled_sources
                <= sum(expected.values())
                <= (self.profile.maximum_enabled_sources or len(native_zones))
            )
            or any(
                sum(expected.get(name, False) for name in group) > 1 for group in self.profile.exclusive_source_groups
            )
        ):
            return False
        native_writes = (
            prepared_colour.native_writes if prepared_colour is not None else self._prepare_native_sources(state)
        )
        if native_writes is None:
            return False
        source_values = {
            "ripple_speed" if write.attribute == "ripple_speed" else f"{write.source}_{write.attribute}": write.value
            for write in native_writes
        }
        source_values.update(
            (field, normalize_kelvin(value, self.profile) if value else 0)
            for field in source_kelvin_hint_fields(self.profile)
            if (value := getattr(state, field)) is not None
        )
        for write in native_writes:
            field = "ripple_speed" if write.attribute == "ripple_speed" else f"{write.source}_{write.attribute}"
            transition = self._mode_transition
            if (
                transition is not None
                and self._field_revisions.get(field, 0) > transition.field_baselines.get(field, 0)
                and self.source_field_fresh(field)
                and getattr(self, field) == write.value
            ):
                continue
            await self._as_coordinator.async_apply_source_value(
                write, write_guard=(lambda: prepared_colour.check(self)) if prepared_colour is not None else None
            )
        restored = await self._async_restore_effect_appearance(
            state, overwritten_diy_code=overwritten_diy_code, prepared_colour=prepared_colour
        )
        if prepared_colour is not None:
            prepared_colour.check(self)
        if not native_zones:
            return restored
        if not expected:
            return False
        async with self._lock:
            client = await self._ensure_connected()
            if self.profile.setting_grammar == "H6046":
                from .generated_protocol_adapter import build_boolean_control_query

                if not await self._as_coordinator._async_read_bar_flags(
                    client,
                    build_boolean_control_query(next(iter(native_zones)), self.model, profile=self.profile),
                    deadline=time.monotonic() + 4.0,
                ):
                    return False
            elif self.profile.setting_grammar in {"H607C", "H60B0", "H60B2"}:
                from .generated_protocol_adapter import build_boolean_control_query

                if not await self._as_coordinator._async_read_setting_fields(
                    client,
                    build_boolean_control_query(next(iter(native_zones)), self.model, profile=self.profile),
                    tuple(f"boolean_{name}" for name in sorted(native_zones)),
                    deadline=time.monotonic() + 4.0,
                ):
                    return False
            elif not await self._async_read_bulk_status(
                client, deadline=time.monotonic() + 4.0, domains=("zone_enable",)
            ):
                return False
        if self.profile.minimum_enabled_sources:
            for _ in range(len(expected) * 2):
                remove = [
                    name for name, value in expected.items() if not value and self.boolean_control_state.get(name)
                ]
                add = [name for name, value in expected.items() if value and not self.boolean_control_state.get(name)]
                if not remove and not add:
                    break
                if (
                    remove
                    and sum(self.boolean_control_state.get(name, False) for name in expected)
                    > self.profile.minimum_enabled_sources
                ):
                    await self.async_set_boolean_control(remove[0], False)
                elif add:
                    await self.async_set_boolean_control(add[0], True)
                else:
                    return False
        else:
            for name, value in expected.items():
                if self.boolean_control_state.get(name) != value:
                    await self.async_set_boolean_control(name, value)
        return (
            restored
            and set(expected) == native_zones
            and all(self.boolean_control_state.get(name) == value for name, value in expected.items())
            and all(getattr(self, field) == value for field, value in source_values.items())
        )

    async def _async_restore_effect_appearance(
        self,
        state: PriorControlState,
        *,
        overwritten_diy_code: int | None,
        prepared_colour: PreparedStaticRecovery | None = None,
    ) -> bool:
        if not state.is_on:
            return await self._async_restore_effect_control_state(
                state, overwritten_diy_code=overwritten_diy_code, prepared_colour=prepared_colour
            )
        async with self.async_mask_transaction() if state.mode == "colour" else nullcontext():
            return await self._async_restore_effect_control_state(
                state, overwritten_diy_code=overwritten_diy_code, prepared_colour=prepared_colour
            )

    async def _async_restore_effect_control_state(
        self,
        state: PriorControlState,
        *,
        overwritten_diy_code: int | None,
        prepared_colour: PreparedStaticRecovery | None = None,
    ) -> bool:
        if not state.is_on:
            return await self._restore_effect_while_off(
                state, overwritten_diy_code=overwritten_diy_code, prepared_colour=prepared_colour
            )
        if state.mode == "video" and self.profile.supports_video_mode:
            # A legacy snapshot cannot reconstruct values overwritten since it was captured.
            from .generated_protocol_adapter import validate_video_parameters

            validate_video_parameters(self.profile.video_grammar, state.video_parameters or {})
        physical_ic_count = self.profile.physical_ic_count
        prepared = self._prepare_music_restore(state)
        if prepared is None:
            return False
        variant, music_writes = prepared
        permitted, complete = await self._restore_video_controls(state)
        if state.mode == "custom":
            return await self._restore_custom(state, overwritten_diy_code, complete)
        if state.mode == "scene" and (state.effect is not None or state.scene_code is not None):
            return await self._restore_scene(state, overwritten_diy_code, complete)
        if state.mode == "music" and state.music_mode in self.profile.music_modes:
            return await self._restore_music(state, variant, music_writes, physical_ic_count, complete)
        if state.mode == "video" and state.video_mode in {"movie", "game"} and self.profile.supports_video_mode:
            return await self._restore_video_mode(state, permitted, complete)
        if state.mode != "colour":
            return False
        if self.profile.supports_segments:
            return await self._restore_segmented_colour(state, complete, prepared=prepared_colour)
        return await self._restore_static_colour(state, complete, prepared=prepared_colour)

    async def _restore_effect_while_off(
        self,
        state: PriorControlState,
        *,
        overwritten_diy_code: int | None,
        prepared_colour: PreparedStaticRecovery | None = None,
    ) -> bool:
        attempts = self.control_write_attempts
        try:
            appearance_restored = await self._async_restore_effect_appearance(
                replace(state, is_on=True), overwritten_diy_code=overwritten_diy_code, prepared_colour=prepared_colour
            )
        except BaseException:
            if self.is_on or self.control_write_attempts != attempts:
                try:
                    await self.send_command(build_power(False, self.model), state_values={"is_on": False})
                except Exception:
                    _LOGGER.debug("Power-off cleanup failed during effect recovery", exc_info=True)
            raise
        await self.send_command(build_power(False, self.model), state_values={"is_on": False})
        powered_off = (
            await self.refresh_state(RefreshRequest(on=False)) is True
            if self.profile.can_read(ReadDomain.POWER)
            else not self.is_on
        )
        return powered_off and appearance_restored

    def _prepare_music_restore(self, state: PriorControlState) -> tuple[Any, MusicWriteSequence] | None:
        """Return (variant, writes) for a music snapshot, or None when it cannot be recovered."""
        from .music_commands import prepare_music_body_writes

        variant = None
        music_writes = MusicWriteSequence()
        if state.mode == "music" and state.is_on:
            if state.music_model is not None and state.music_model != self.model:
                raise ValueError("music recovery model does not match device")
            if state.music_mode not in self.profile.music_modes:
                return None
            variant = music_variant(
                self.profile,
                music_code_for(self.model, state.music_mode, profile=self.profile),
            )
            if variant and any(
                not spec.optional and spec.profile_key not in (state.music_parameters or {})
                for spec in variant.selector_parameters
            ):
                return None
            if self.profile.music_grammar == "H6046" and variant and variant.supports_fixed_colour:
                parameters = state.music_parameters or {}
                if "fixed_colour" not in parameters or (
                    parameters["fixed_colour"] and not {"left_colour", "right_colour"} <= parameters.keys()
                ):
                    return None
            # Legacy snapshots retain style across modes even when the active selector
            # has no style byte semantics. Do not reinterpret that retained value.
            music_calm = state.music_calm if variant and variant.supports_style else False
            if variant and variant.layout in COMPANION_MUSIC_LAYOUTS:
                if state.music_body is None:
                    # The selector cannot recover resident companions; presets are not a backup.
                    return None
                music_writes = prepare_music_body_writes(
                    self.model, state.music_mode, state.music_sensitivity, state.music_body, profile=self.profile
                )
            else:
                music_writes = prepare_music_profile_writes(
                    self.model,
                    state.music_mode,
                    state.music_sensitivity,
                    state.music_color
                    if self.profile.supports_music_color and (variant is None or variant.supports_fixed_colour)
                    else None,
                    music_calm,
                    {
                        spec.profile_key: (state.music_parameters or {})[spec.profile_key]
                        for spec in (() if variant is None else variant.selector_parameters)
                        if spec.profile_key in (state.music_parameters or {})
                    },
                    profile=self.profile,
                    include_parameters=False,
                )
        return variant, music_writes

    async def _restore_video_controls(self, state: PriorControlState) -> tuple[set[str], bool]:
        """Re-apply captured video controls; return the permitted controls and whether recovery is complete."""
        states = video_control_states(self.profile, self)
        restore_policy = (
            state.video_restore_controls is not None and "blank_screen_policy" in state.video_restore_controls
        )
        policy_revision = self._blank_screen_notification_revision

        def check_policy() -> None:
            if self._blank_screen_notification_revision != policy_revision:
                raise ValueError("Blank-screen policy changed before recovery write; refresh and retry")

        permitted = {
            control
            for control, status in states.items()
            if status is CapabilityState.SUPPORTED
            and (state.video_restore_controls is None or control in state.video_restore_controls)
        }
        needed = {
            control
            for control, fields in (
                (
                    "white_balance",
                    ("white_balance_scalar",)
                    if self.profile.video_white_balance_representation == "scalar"
                    else ("white_balance_flag", "white_balance_red", "white_balance_blue"),
                ),
                (
                    "relative_brightness",
                    tuple(f"relative_brightness_{zone}" for zone in self.profile.video_brightness_zones),
                ),
                ("inline_relative_brightness", ("video_parameters",)),
                (
                    "blank_screen",
                    (
                        "blank_screen",
                        "blank_screen_detection",
                        "blank_screen_low_brightness_duration_seconds",
                        "blank_screen_same_tone_duration_seconds",
                    )
                    if restore_policy
                    else ("blank_screen",),
                ),
                ("black_border", ("black_border",)),
                ("whole_relative_brightness", ("whole_relative_brightness",)),
            )
            if (control != "inline_relative_brightness" or self.profile.video_embeds_relative_brightness)
            and (state.video_restore_controls is None or control in state.video_restore_controls)
            and any(
                getattr(state, field) is not None and getattr(self, field) != getattr(state, field) for field in fields
            )
        }
        complete = not (needed - permitted)
        if self.profile.video_embeds_relative_brightness and (
            state.video_restore_controls is None or "inline_relative_brightness" in state.video_restore_controls
        ):
            if state.video_parameters is None:
                complete = False
            elif "inline_relative_brightness" in needed and state.mode != "video":
                if self.video_mode not in self.profile.video_modes:
                    complete = False
                else:
                    await apply_active_video_mode(
                        self._as_coordinator,
                        mode=self.video_mode,
                        requested_values={},
                        parameters=state.video_parameters,
                    )
        restore_white_balance = self.profile.supports_white_balance and (
            state.video_restore_controls is None or "white_balance" in state.video_restore_controls
        )
        if restore_white_balance and self.profile.video_white_balance_representation == "position":
            # A fresh read cannot recover a legacy snapshot's missing pre-write mode.
            if (
                state.white_balance_flag not in (0, 1)
                or state.white_balance_red is None
                or state.white_balance_blue is None
            ):
                if (
                    "white_balance" in needed
                    or state.video_restore_controls is not None
                    or any(
                        value is not None
                        for value in (state.white_balance_flag, state.white_balance_red, state.white_balance_blue)
                    )
                ):
                    complete = False
                permitted.discard("white_balance")
            else:
                # Even equal retained values are not fresh recovery proof.
                needed.add("white_balance")
                complete = complete and "white_balance" in permitted
        if (
            restore_policy
            and state.blank_screen is not None
            and (state.video_restore_controls is None or "blank_screen" in state.video_restore_controls)
            and any(
                value is None
                for value in (
                    state.blank_screen_detection,
                    state.blank_screen_low_brightness_duration_seconds,
                    state.blank_screen_same_tone_duration_seconds,
                )
            )
        ):
            complete = False
        if (
            "white_balance" in permitted & needed
            and state.white_balance_scalar is not None
            and self.profile.video_white_balance_representation == "scalar"
        ):
            await apply_white_balance(self._as_coordinator, (state.white_balance_scalar,))
        if (
            "white_balance" in permitted & needed
            and self.profile.video_white_balance_representation == "position"
            and state.white_balance_red is not None
            and state.white_balance_blue is not None
        ):
            assert state.white_balance_flag is not None
            await apply_white_balance(
                self._as_coordinator, (state.white_balance_red, state.white_balance_blue), flag=state.white_balance_flag
            )
            # Defaults are device-owned, not writable. Never install persisted defaults as observations.
            complete = complete and all(
                getattr(state, field) is None or getattr(self, field) == getattr(state, field)
                for field in ("white_balance_default_flag", "white_balance_default_red", "white_balance_default_blue")
            )
        if "relative_brightness" in permitted & needed:
            values = tuple(
                getattr(state, f"relative_brightness_{zone}") for zone in self.profile.video_brightness_zones
            )
            if any(value is None for value in values):
                complete = False
                permitted.discard("relative_brightness")
            else:
                await apply_relative_brightness(self._as_coordinator, values)
        if "whole_relative_brightness" in permitted & needed and state.whole_relative_brightness is not None:
            await apply_whole_relative_brightness(self._as_coordinator, state.whole_relative_brightness)
        if "blank_screen" in permitted & needed and state.blank_screen is not None:
            if not restore_policy:
                await apply_blank_screen(self._as_coordinator, state.blank_screen)
            elif (
                state.blank_screen_detection is None
                or state.blank_screen_low_brightness_duration_seconds is None
                or state.blank_screen_same_tone_duration_seconds is None
            ):
                complete = False
            else:
                await apply_blank_screen(
                    self._as_coordinator,
                    state.blank_screen,
                    policy=(
                        state.blank_screen_detection,
                        state.blank_screen_low_brightness_duration_seconds,
                        state.blank_screen_same_tone_duration_seconds,
                    ),
                    write_guard=check_policy,
                )
        if "black_border" in permitted & needed and state.black_border is not None:
            await apply_black_border(self._as_coordinator, state.black_border)
        return permitted, complete

    async def _restore_custom(self, state: PriorControlState, overwritten_diy_code: int | None, complete: bool) -> bool:
        if (
            state.diy_code is None
            or (overwritten_diy_code is not None and state.diy_code == overwritten_diy_code)
            or not self.profile.supports_custom_effects
        ):
            return False
        if self.profile.command_grammar == "H607C" and state.diy_companion is None:
            return False
        activation = build_diy_activation(
            state.diy_code,
            self.model,
            profile=self.profile,
            companion=state.diy_companion if self.profile.command_grammar == "H607C" else None,
        )
        await self.send_command(build_power(True, self.model))
        await self.send_command(build_brightness(state.brightness_pct, self.model))
        expected: dict[str, Any] = {"is_on": True, "diy_code": state.diy_code}
        if self.profile.command_grammar == "H607C":
            expected["diy_companion"] = state.diy_companion
        await self.send_command(activation, state_values={"diy_code": state.diy_code})
        return (
            await self.async_observe_effect(expected) is True
            and await self.refresh_state(RefreshRequest(on=True, brightness=state.brightness_pct)) is True
            and complete
        )

    async def _restore_scene(self, state: PriorControlState, overwritten_diy_code: int | None, complete: bool) -> bool:
        from .effect_catalogue import MODEL_EFFECT_CATALOGUES
        from .effect_domain import LayeredEffect
        from .generated_protocol_adapter import build_scene_activation

        catalogue = MODEL_EFFECT_CATALOGUES.get(self.model)
        native_selectors = {
            template.content.native_diy
            for template in (() if catalogue is None else catalogue.templates)
            if self.profile.supports_advanced_effects
            and isinstance(template.content, LayeredEffect)
            and template.content.native_diy is not None
        }
        if self.profile.supports_advanced_effects and self.profile.advanced_diy_selector is not None:
            native_selectors.add(self.profile.advanced_diy_selector)
        if self.profile.authored_palette_scene_selector is not None and profile_supports_workflow(
            self.profile, CapabilityWorkflow.EDITED_PALETTE_SCENES
        ):
            native_selectors.add(self.profile.authored_palette_scene_selector)
        if state.scene_code is not None and state.scene_code in native_selectors:
            if state.scene_code == overwritten_diy_code:
                return False
            await self.send_command(build_power(True, self.model))
            await self.send_command(build_brightness(state.brightness_pct, self.model))
            await self.send_command(build_scene_activation(self.model, state.scene_code, profile=self.profile))
            await self.refresh_state(
                RefreshRequest(on=True, brightness=state.brightness_pct, scene_code=state.scene_code)
            )
            # Selection is restored, but no supported read proves resident body equality.
            return False
        resolved = (
            resolve_scene_code(
                self.model,
                state.scene_code,
                preferred_key=state.effect,
                profile=self.profile,
            )
            if state.scene_code is not None
            else None
        )
        if resolved is not None:
            scene_name, scene = resolved
        elif state.effect is not None:
            scene_name = canonical_scene_key(self.model, state.effect)
            candidate = MODEL_SCENES.get(self.model, {}).get(scene_name)
            if candidate is None:
                return False
            if not scene_supported(candidate, self.profile):
                return False
            scene = candidate
        else:
            return False
        selector = scene_selector_code(self.model, scene, profile=self.profile)
        await self.send_command(build_power(True, self.model))
        await self.send_command(build_brightness(state.brightness_pct, self.model))
        # A catalogue body/default speed is not the original authored resident body.
        await self.send_command(build_scene_activation(self.model, selector, scene.music_code))
        return (
            await self.refresh_state(RefreshRequest(on=True, brightness=state.brightness_pct, scene_code=selector))
            is True
            and not scene.param
            and complete
        )

    async def _restore_music(
        self,
        state: PriorControlState,
        variant: Any,
        music_writes: MusicWriteSequence,
        physical_ic_count: int | None,
        complete: bool,
    ) -> bool:
        observes_color = (variant is None or variant.layout is None) and self.profile.music_grammar != "H6046"
        observes_style = bool(variant and variant.supports_style) and (
            observes_color or self.profile.music_grammar == "H6046"
        )
        selector_expectations = {
            spec.key: (state.music_parameters or {})[spec.profile_key]
            for spec in (() if variant is None else variant.selector_parameters)
            if self.profile.music_grammar == "H6046" and spec.profile_key in (state.music_parameters or {})
        }
        selector_baselines = {field: self._field_revisions.get(field, 0) for field in selector_expectations}

        def guard_music_recovery() -> None:
            self._reconcile_authorization()
            profile = self._authorization_profile()
            if (
                state.music_mode not in profile.music_modes
                or music_variant(
                    profile,
                    music_code_for(self.model, state.music_mode, profile=profile),
                )
                != variant
            ):
                raise ValueError("Music variant changed before recovery; refresh and retry")

        await self.send_command(build_brightness(state.brightness_pct, self.model), write_guard=guard_music_recovery)
        await self.async_write_music_sequence(
            music_writes,
            mode_code=music_code_for(self.model, state.music_mode, profile=self.profile),
            physical_ic_count=physical_ic_count,
            intent=ControlIntent.APPLY,
        )
        restored = (
            self.profile.state_readable
            and await self.refresh_state(
                RefreshRequest(
                    on=True,
                    brightness=state.brightness_pct,
                    music_mode=state.music_mode,
                    music_sensitivity=state.music_sensitivity,
                    music_color=state.music_color if observes_color else None,
                    music_auto_color=observes_color and state.music_color is None,
                    music_calm=state.music_calm if observes_style else None,
                ),
            )
            is True
            and complete
            # Successful upload/ACK retains bytes; no supported query verifies the body.
            and state.music_body is None
        )
        return restored and all(
            getattr(self, field, None) == value and self._field_revisions.get(field, 0) > selector_baselines[field]
            for field, value in selector_expectations.items()
        )

    async def _restore_video_mode(self, state: PriorControlState, permitted: set[str], complete: bool) -> bool:
        await self.send_command(build_power(True, self.model))
        await self.send_command(build_brightness(state.brightness_pct, self.model))
        for _name, attr, control in _VIDEO_VALUE_FIELDS:
            if (
                state.video_restore_controls is None or control in state.video_restore_controls
            ) and control not in permitted:
                complete = complete and getattr(self, attr) == getattr(state, attr)
        restored = [(name, attr) for name, attr, control in _VIDEO_VALUE_FIELDS if control in permitted]
        return (
            await apply_active_video_mode(
                self._as_coordinator,
                mode=state.video_mode,
                requested_values={name: getattr(state, attr) for name, attr in restored},
                parameters=state.video_parameters,
            )
            and await self.refresh_state(RefreshRequest(on=True, brightness=state.brightness_pct)) is True
            and complete
        )

    def _prepare_native_sources(self, state: PriorControlState) -> tuple[PreparedSourceValue, ...] | None:
        if any(getattr(state, field) is None for field in source_kelvin_hint_fields(self.profile)):
            return None
        writes = []
        for field, (source, attribute) in native_source_fields(self.profile).items():
            value = getattr(state, field)
            if value is None or attribute == "kelvin" and value <= 0:
                return None
            writes.append(
                PreparedSourceValue.prepare(
                    source,
                    attribute,
                    normalize_kelvin(value, self.profile) if attribute == "kelvin" else value,
                    self.profile,
                )
            )
        return tuple(writes)

    def _prepare_static_colour(self, state: PriorControlState) -> PreparedStaticRecovery | None:
        if state.mode != "colour":
            return None
        zones = self.profile.boolean_controls.intersection(NATIVE_ZONE_CONTROLS)
        flags = {name: getattr(state, name) for name in zones}
        if any(value is None for value in flags.values()):
            return None
        if self.profile.minimum_enabled_sources and (
            not self.profile.minimum_enabled_sources
            <= sum(bool(value) for value in flags.values())
            <= (self.profile.maximum_enabled_sources or len(zones))
            or any(sum(bool(flags.get(name)) for name in group) > 1 for group in self.profile.exclusive_source_groups)
        ):
            return None
        native_writes = self._prepare_native_sources(state)
        if native_writes is None:
            return None
        if self.profile.supports_segments:
            prepared = self._prepare_segmented_colour(state)
            return replace(prepared, native_writes=native_writes) if prepared is not None else None
        if not state.static_rgb_known and state.color_temp_kelvin is None:
            return None
        packet = (
            build_color_temp(state.color_temp_kelvin, self.model, profile=self.profile)
            if state.color_temp_kelvin is not None
            else build_color_rgb(*state.rgb_color, self.model, profile=self.profile)
        )
        packets = (build_power(True, self.model), build_brightness(state.brightness_pct, self.model), packet)
        for packet in packets:
            require_profile_packet(packet, self.profile)
        return PreparedStaticRecovery(
            state,
            packets,
            state.color_temp_kelvin is not None,
            self.profile,
            self._profile_generation,
            self._notification_token,
            native_writes,
        )

    def _prepare_segmented_colour(self, state: PriorControlState) -> PreparedStaticRecovery | None:
        if (
            state.segment_colors is None
            or len(state.segment_colors) != self.profile.segment_count
            or state.segment_brightness is None
            and self.profile.supports_segment_brightness
        ):
            return None
        source_restore = has_segmented_sources(self.profile)
        target_intents = state.static_segment_kelvin(self.profile)
        if target_intents is None:
            return None
        bar_restore = state.restorable_bar_white(self.profile)
        kelvin_restore = (
            not source_restore
            and not bar_restore
            and bool(target_intents)
            and target_intents[0] > 0
            and len(set(target_intents)) == 1
            and self.profile.supports_color_temperature
        )
        target_colours = list(state.segment_colors)
        if not self.profile.kelvin_renders_device_white:
            for index, kelvin in enumerate(target_intents):
                if kelvin:
                    target_colours[index] = table_kelvin_rgb(kelvin)
        left, right = state.left_bar_kelvin, state.right_bar_kelvin
        if bar_restore:
            assert left is not None and right is not None
            left, right = normalize_kelvin(left, self.profile), normalize_kelvin(right, self.profile)
            half = self.profile.segment_count // 2
            target_colours = [table_kelvin_rgb(left)] * half + [table_kelvin_rgb(right)] * half
        whole = target_intents[0] if kelvin_restore else state.color_temp_kelvin
        if kelvin_restore and whole is not None:
            whole = normalize_kelvin(whole, self.profile)
        state = replace(
            state,
            color_temp_kelvin=whole,
            left_bar_kelvin=left,
            right_bar_kelvin=right,
            top_kelvin=normalize_kelvin(state.top_kelvin, self.profile)
            if source_restore and state.top_kelvin
            else state.top_kelvin,
            source_static_intents=None,
            segment_kelvin=target_intents,
            segment_colors=tuple(target_colours),
        )
        assert state.segment_colors is not None
        brightness_groups: dict[int, list[int]] = {}
        if state.segment_brightness is not None and self.profile.supports_segment_brightness:
            for index, brightness in enumerate(state.segment_brightness, 1):
                brightness_groups.setdefault(brightness, []).append(index)
        if bar_restore:
            half = self.profile.segment_count // 2
            packets = [
                build_segment_color_temp(range(start + 1, start + half + 1), kelvin, self.model, profile=self.profile)
                for start, kelvin in ((0, state.left_bar_kelvin), (half, state.right_bar_kelvin))
                if kelvin is not None
            ]
        elif kelvin_restore and state.color_temp_kelvin is not None:
            packets = [build_color_temp(state.color_temp_kelvin, self.model, profile=self.profile)]
        else:
            packets = []
            semantic_groups: dict[tuple[int, tuple[int, int, int]], list[int]] = {}
            for index, (intent, rgb) in enumerate(zip(target_intents, state.segment_colors, strict=True), 1):
                semantic_groups.setdefault((intent, rgb), []).append(index)
            for (intent, rgb), segments in semantic_groups.items():
                if intent:
                    packets.extend(build_segment_kelvin_packets(segments, intent, self.model, profile=self.profile))
                else:
                    packets.extend(build_segment_paint([(segments, rgb)], self.model, profile=self.profile))
        packets.extend(
            packet
            for brightness, segments in brightness_groups.items()
            for packet in build_segment_brightness_packets(segments, brightness, self.model, profile=self.profile)
        )
        prepared_packets = (build_power(True, self.model), build_brightness(state.brightness_pct, self.model), *packets)
        for packet in prepared_packets:
            require_profile_packet(packet, self.profile)
        return PreparedStaticRecovery(
            state, prepared_packets, kelvin_restore, self.profile, self._profile_generation, self._notification_token
        )

    async def _restore_segmented_colour(
        self, state: PriorControlState, complete: bool, *, prepared: PreparedStaticRecovery | None = None
    ) -> bool:
        prepared = prepared or self._prepare_segmented_colour(state)
        if prepared is None:
            return False
        state = prepared.state
        source_restore = has_segmented_sources(self.profile)
        target_intents = state.static_segment_kelvin(self.profile)
        assert target_intents is not None and state.segment_colors is not None
        kelvin_restore = prepared.whole_kelvin
        bar_restore = state.restorable_bar_white(self.profile)
        prepared.check(self)
        await self._write_static_restore(prepared)
        if state.static_gradual is not None:
            if "gradual" not in self.profile.boolean_controls:
                complete = False
            else:
                await self.async_set_boolean_control("gradual", state.static_gradual)
        mode_revision = self._field_revisions.get("color_mode", 0)
        basic_matches = await self.refresh_state(
            RefreshRequest(
                on=True,
                brightness=state.brightness_pct if self.profile.can_read(ReadDomain.BRIGHTNESS) else None,
                refresh_all=True,
                color_temp_kelvin=(
                    normalize_kelvin(state.color_temp_kelvin, self.profile)
                    if kelvin_restore and state.color_temp_kelvin is not None and self.profile.static_readback_kelvin
                    else None
                ),
                zero_kelvin=(
                    self.profile.static_readback_zero_kelvin_is_rgb
                    and not source_restore
                    and not kelvin_restore
                    and not bar_restore
                ),
            ),
        )
        segments_match = await self.async_refresh_segments() if self.profile.can_read(ReadDomain.SEGMENTS) else True
        restored = (
            basic_matches is True
            and segments_match is True
            and self.is_on
            and self.brightness_pct == state.brightness_pct
            and self.active_mode == "colour"
            and self.color_mode is ParsedMode.COLOUR
            and (
                not self.profile.supports_color_mode_readback
                or self._field_revisions.get("color_mode", 0) > mode_revision
            )
            and len(self.segment_colors) == len(state.segment_colors)
            and all(
                static_colour_matches(actual, intent or expected, self.profile)
                for actual, expected, intent in zip(
                    self.segment_colors, state.segment_colors, target_intents, strict=True
                )
            )
            and (state.segment_brightness is None or tuple(self.segment_brightness) == state.segment_brightness)
            and (state.static_gradual is None or self.static_gradual == state.static_gradual)
            and (
                self.profile.setting_grammar != "H6046"
                or (self.left_bar_kelvin, self.right_bar_kelvin) == (state.left_bar_kelvin, state.right_bar_kelvin)
            )
            and complete
            and (
                (not source_restore or state.top_kelvin is None or self.top_kelvin == state.top_kelvin)
                and self.capture_effect_control_state().static_segment_kelvin(self.profile) == target_intents
            )
        )
        if restored:
            self._static_rgb_known = state.static_rgb_known
        return restored

    async def _write_static_restore(self, prepared: PreparedStaticRecovery) -> None:
        generation = self._profile_generation
        foreground = self._control_arbiter.foreground_generation
        mode_revision = self._field_revisions.get("color_mode", 0)
        segment_revision = self._field_revisions.get("segment_colors", 0)
        attempts = self.control_write_attempts
        static_attempts = self._static_write_attempts
        expected_segments = (tuple(self.segment_colors), tuple(self.segment_brightness))
        request = self._as_coordinator.control_write_request()
        token = self._notification_token
        bound = token is not None

        def guard() -> None:
            nonlocal token, bound
            prepared.check(self)
            if (
                generation != self._profile_generation
                or foreground != self._control_arbiter.foreground_generation
                or self._field_revisions.get("color_mode", 0) != mode_revision
                and (self._static_write_attempts == static_attempts or self.color_mode is not ParsedMode.COLOUR)
                or self._field_revisions.get("segment_colors", 0) != segment_revision
                and (
                    self._static_write_attempts == static_attempts
                    or (tuple(self.segment_colors), tuple(self.segment_brightness)) != expected_segments
                )
            ):
                raise ValueError("Static restoration context changed; refresh and retry")
            if not bound:
                token, bound = self._notification_token, True
            elif token is not self._notification_token:
                raise ValueError("Static restoration subscription changed; refresh and retry")

        def attempted(index: int) -> None:
            nonlocal expected_segments
            with request.track("is_on" if index == 0 else "brightness_pct" if index == 1 else "rgb_color"):
                request.on_write()
            expected_segments = (tuple(self.segment_colors), tuple(self.segment_brightness))

        try:
            await self.async_write_effect_sequence(
                prepared.packets,
                intent=self._control_arbiter.current_task_intent or ControlIntent.USER,
                write_guard=guard,
                retry_allowed=lambda: self.control_write_attempts == attempts,
                packet_on_write=attempted,
            )
        except asyncio.CancelledError:
            request.mark_interrupted()
            self.async_set_updated_data(self.data or {})
            raise
        except Exception:
            request.mark_interrupted()
            self.async_set_updated_data(self.data or {})
            try:
                await request.reconcile()
            except Exception:
                _LOGGER.debug("Static restoration reconciliation failed", exc_info=True)
            raise
        request.complete(colour_requested=True)

    async def _restore_static_colour(
        self, state: PriorControlState, complete: bool, *, prepared: PreparedStaticRecovery | None = None
    ) -> bool:
        prepared = prepared or self._prepare_static_colour(state)
        if prepared is None:
            return False
        await self._write_static_restore(prepared)
        request = RefreshRequest(
            on=True if self.profile.can_read(ReadDomain.POWER) else None,
            brightness=state.brightness_pct if self.profile.can_read(ReadDomain.BRIGHTNESS) else None,
            color_temp_kelvin=normalize_kelvin(state.color_temp_kelvin, self.profile)
            if state.color_temp_kelvin is not None and self.profile.static_readback_kelvin
            else None,
            rgb_color=state.rgb_color
            if state.color_temp_kelvin is None and self.profile.static_readback_echoes_color
            else None,
            zero_kelvin=state.color_temp_kelvin is None and self.profile.static_readback_zero_kelvin_is_rgb,
        )
        return (
            (not self.profile.state_readable or await self.refresh_state(request) is True)
            and self.active_mode == "colour"
            and self.color_mode is ParsedMode.COLOUR
            and complete
        )
