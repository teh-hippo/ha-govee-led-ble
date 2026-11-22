"""Effect recovery: restoring the prior control state after previews and effect writes."""

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable, Iterator, Mapping
from contextlib import asynccontextmanager, nullcontext
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, cast

from bleak.exc import BleakError
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN, NATIVE_ZONE_CONTROLS, ModelProfile, ReadDomain, get_profile, same_control_profile
from .control_arbiter import ControlIntent, async_control_intent
from .coordinator_base import _CoordinatorBase
from .coordinator_modes import ModeTransitionPurpose
from .coordinator_refresh import STATIC_RECOVERY_SETTINGS, RefreshRequest
from .coordinator_sources import (
    PreparedSourceValue,
    async_restore_source_flags,
    has_segmented_sources,
    native_source_fields,
    segment_colour_matches,
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
    apply_hdmi_box_light,
    apply_hdmi_input,
    apply_relative_brightness,
    apply_video_color_calibration,
    apply_video_sensitivity,
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
    pass

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
    off_guard: Callable[[], None] | None = None

    def check(self, coordinator: _CoordinatorBase) -> None:
        transition = coordinator._mode_transition
        if (
            not same_control_profile(coordinator.profile, self.profile)
            or coordinator._profile_generation != self.generation
            or self.subscription is not None
            and coordinator._notification_token is not self.subscription
            or self.off_guard is not None
            and (
                transition is None
                or transition.owner is not asyncio.current_task()
                or transition.purpose is not ModeTransitionPurpose.RECOVERY
                or transition.snapshot is None
            )
            or transition is not None
            and transition.owner is asyncio.current_task()
            and transition.purpose is ModeTransitionPurpose.RECOVERY
            and transition.snapshot is not None
            and coordinator._pre_mode_snapshot is not transition.snapshot
        ):
            raise ValueError("The colour restoration context changed")
        if self.off_guard is not None:
            self.off_guard()


class _RecoveryMixin(_CoordinatorBase):
    def _static_recovery_error(self) -> HomeAssistantError:
        return HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="projector_recovery_not_ready"
            if self.profile.projector_grammar is not None
            else "recovery_not_ready",
        )

    def require_static_baseline(self) -> PriorControlState:
        if self._pre_mode_snapshot is None:
            raise self._static_recovery_error()
        return self._pre_mode_snapshot

    def static_mode_confirmed(self) -> bool:
        return (
            self.color_mode is ParsedMode.COLOUR
            and self._observed_color_mode is ParsedMode.COLOUR
            and self.source_field_fresh("color_mode")
            and self.effect is None
            and self.scene_code is None
            and self.diy_code is None
            and self.music_mode in (None, "off")
            and self.video_mode in (None, "off")
        )

    async def async_preflight_static_off(self) -> Callable[[], None] | None:
        async with async_control_intent(self, ControlIntent.BACKGROUND):
            if not self.profile.supports_color_mode_readback:
                self.require_static_baseline()
                return None
            revision = self._field_revisions.get("color_mode", 0)
            try:
                refreshed = await self.refresh_state(
                    RefreshRequest(
                        query_segments=False,
                        query_native_settings=False,
                        required_domains=self.profile.read_domains & {ReadDomain.COLOUR_MODE, ReadDomain.MODE},
                    )
                )
            except BleakError as error:
                raise self._static_recovery_error() from error
            if (
                refreshed is not True
                or self._field_revisions.get("color_mode", 0) <= revision
                or not self.source_field_fresh("color_mode")
            ):
                raise self._static_recovery_error()
            static = self.static_mode_confirmed()
            snapshot = None if static else self.require_static_baseline()
            if not static and self._observed_color_mode in (None, ParsedMode.UNKNOWN, ParsedMode.COLOUR):
                raise self._static_recovery_error()
            selector_revision = self._selector_revision
            subscription = self._notification_token
            generation = self._profile_generation

            def check() -> None:
                if (
                    subscription is not self._notification_token
                    or generation != self._profile_generation
                    or not self.source_field_fresh("color_mode")
                    or (
                        not self.static_mode_confirmed()
                        if static
                        else self._selector_revision != selector_revision or self._pre_mode_snapshot is not snapshot
                    )
                ):
                    raise self._static_recovery_error()

            return check

    def _static_history_profile_current(self) -> bool:
        profile = self._pre_mode_profile
        if self._pre_mode_snapshot is None and self._incomplete_static_exit is None:
            return False
        if not self._pre_mode_needs_qualification:
            return True
        if profile is None:
            self._discard_static_baseline()
            return False
        if (
            profile.projector_grammar is not None
            and not self.identity_fields_confirmed(frozenset({"pact"}))
            or not self.identity_fields_confirmed(
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
        foreground = self._control_arbiter.foreground_generation
        subscription = self._notification_token
        observations = {field: self._field_revisions.get(field, 0) for field in ("color_mode", "segment_colors")}
        async with self._lock:
            client = await self._ensure_connected()
            profile = self._pre_mode_profile
            if self._pre_mode_needs_qualification and profile is not None and profile.projector_grammar is not None:
                await self._as_coordinator._async_require_identity(client, frozenset({"pact"}))
        if foreground != self._control_arbiter.foreground_generation:
            raise ValueError("Static restoration ownership changed; refresh and retry")
        if subscription is not None and subscription is not self._notification_token:
            raise ValueError("Static restoration subscription changed; refresh and retry")
        async with self.async_mask_transaction():
            if (
                self._incomplete_static_exit is None
                and self.color_mode is ParsedMode.COLOUR
                and any(self._field_revisions.get(field, 0) != revision for field, revision in observations.items())
            ):
                self._discard_static_baseline()
                raise ValueError("Static restoration observations changed; refresh and retry")
            if self._pre_mode_needs_qualification:
                if not self._static_history_profile_current():
                    raise self._static_recovery_error()
                self._pre_mode_needs_qualification = False
            yield

    @asynccontextmanager
    async def async_prepare_static_recovery(
        self, off_guard: Callable[[], None] | None, *, brightness_pct: int | None = None
    ) -> AsyncIterator[PreparedStaticRecovery | None]:
        transition = self._mode_transition
        if (
            transition is None
            or transition.owner is not asyncio.current_task()
            or transition.purpose is not ModeTransitionPurpose.RECOVERY
            or self._control_arbiter.current_task_intent is None
        ):
            raise RuntimeError("Static restoration requires an owned recovery transition")
        if off_guard is not None:
            off_guard()
            if self.static_mode_confirmed():
                incomplete = self._incomplete_static_exit
                if incomplete is not None:
                    current = await self.async_prepare_static_baseline()
                    off_guard()
                    if not self._same_static_appearance(incomplete, current):
                        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="partial_command")
                    attempts = self.control_write_attempts
                    subscription, generation = self._notification_token, self._profile_generation
                    transition.observations_match = lambda: (
                        self.control_write_attempts != attempts
                        or (
                            subscription is self._notification_token
                            and generation == self._profile_generation
                            and self._incomplete_static_exit is incomplete
                            and self.static_mode_confirmed()
                            and self._same_static_appearance(incomplete, self.capture_effect_control_state())
                        )
                    )
                yield None
                if incomplete is not None and not transition.current():
                    raise HomeAssistantError(translation_domain=DOMAIN, translation_key="partial_command")
                self._discard_static_baseline()
                return
        async with self._async_qualified_static_history():
            state = self.require_static_baseline()
            target = replace(state, brightness_pct=brightness_pct) if brightness_pct is not None else state
            prepared = self._prepare_static_colour(target)
            if prepared is None:
                raise self._static_recovery_error()
            attempts = self.control_write_attempts

            def check_before_first_write() -> None:
                # The recovery writes can change mode themselves once the restore has started.
                if off_guard is not None and self.control_write_attempts == attempts:
                    off_guard()

            transition.snapshot = state
            transition.profile = self.profile
            transition.profile_generation = self._profile_generation
            transition.subscription = self._notification_token
            transition.foreground_generation = self._control_arbiter.foreground_generation
            prepared = replace(prepared, off_guard=check_before_first_write)
            prepared.check(self)
            yield prepared

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
            raise self._static_recovery_error()
        if self.color_mode is ParsedMode.COLOUR and profile.projector_grammar is not None:
            from .projector_runtime import prepare_baseline

            await prepare_baseline(self._as_coordinator)
            projector_baseline = self.capture_effect_control_state()
            if projector_baseline.projector_appearance is None:
                raise self._static_recovery_error()
            return self._qualify_static_baseline(projector_baseline)
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
            if segment_fields and profile.supports_segment_brightness and self.segment_brightness_readable:
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
                        query_native_settings=STATIC_RECOVERY_SETTINGS,
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
                raise self._static_recovery_error()
            if "segment_colors" in segment_fields and profile.supports_segment_brightness:
                if self.segment_brightness_readable:
                    fields.add("segment_brightness")
                else:
                    fields.discard("segment_brightness")
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
        return self._qualify_static_baseline(baseline)

    def _qualify_static_baseline(self, baseline: PriorControlState | None) -> PriorControlState:
        profile, transition = self.profile, self._mode_transition
        if baseline is None or self._prepare_static_colour(baseline) is None:
            _LOGGER.debug(
                "Static effect admission rejected model=%s mode=%s baseline_mode=%s power_known=%s "
                "brightness_known=%s palette_source=%s captured_colours=%s captured_levels=%s missing_flags=%s",
                self.model,
                self.color_mode,
                baseline.mode if baseline is not None else None,
                self._power_known,
                self._brightness_pct_known,
                self.segment_state_source,
                baseline is not None and baseline.segment_colors is not None,
                baseline is not None and baseline.segment_brightness is not None,
                sorted(
                    name
                    for name in profile.boolean_controls.intersection(NATIVE_ZONE_CONTROLS)
                    if baseline is None or getattr(baseline, name) is None
                ),
            )
            raise self._static_recovery_error()
        if transition is not None and transition.purpose is not ModeTransitionPurpose.RECOVERY:
            selector_revision = self._selector_revision
            from_static = self.color_mode is ParsedMode.COLOUR
            transition.observations_match = lambda: (
                self._selector_revision == selector_revision
                and (
                    self._same_static_appearance(baseline, self.capture_effect_control_state())
                    if from_static
                    else self._pre_mode_snapshot is baseline
                )
            )
        return baseline

    def _same_static_appearance(self, target: PriorControlState, current: PriorControlState) -> bool:
        profile = self.profile
        if profile.projector_grammar is not None:
            return (
                current.mode == target.mode == "colour"
                and current.is_on == target.is_on
                and current.brightness_pct == target.brightness_pct
                and target.projector_appearance is not None
                and target.projector_appearance == current.projector_appearance
            )
        fields = (
            "is_on",
            "brightness_pct",
            *profile.boolean_controls.intersection(NATIVE_ZONE_CONTROLS),
            *native_source_fields(profile),
            *source_kelvin_hint_fields(profile),
            *(("left_bar_kelvin", "right_bar_kelvin") if profile.setting_grammar == "H6046" else ()),
        )
        target_intents = target.static_segment_kelvin(profile) if profile.supports_segments else None
        matching_palette = (
            current.segment_colors is not None
            and target.segment_colors is not None
            and target_intents is not None
            and len(current.segment_colors) == len(target.segment_colors) == len(target_intents)
            and all(
                not profile.static_palette_recovery and intent > 0 or actual == expected
                for actual, expected, intent in zip(
                    current.segment_colors, target.segment_colors, target_intents, strict=True
                )
            )
        )
        return (
            current.mode == target.mode == "colour"
            and all(getattr(current, field) == getattr(target, field) for field in fields)
            and (target.static_gradual is None or current.static_gradual == target.static_gradual)
            and (
                matching_palette
                and current.segment_brightness == target.segment_brightness
                and current.static_segment_kelvin(profile) == target_intents
                if profile.supports_segments
                else current.color_temp_kelvin == target.color_temp_kelvin
                and (
                    target.color_temp_kelvin is not None
                    or current.static_rgb_known
                    and current.rgb_color == target.rgb_color
                )
            )
        )

    def capture_effect_control_state(self) -> PriorControlState:
        transition = self._mode_transition
        gradual_observed = self.source_field_fresh("static_gradual") and (
            transition is None
            or transition.owner is not asyncio.current_task()
            or self._field_revisions.get("static_gradual", 0) > transition.field_baselines.get("static_gradual", 0)
        )
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
            not segment_colour_matches(self._as_coordinator, index, self.segment_colors[index], expected[0])
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
            projector_appearance=(
                self.projector_appearance
                if self.projector_mode_active
                and self._projector_token is self._notification_token
                and self._notification_token is not None
                and self._projector_generation == self._profile_generation
                else None
            ),
            color_temp_kelvin=self.color_temp_kelvin,
            static_rgb_known=self._static_rgb_known
            and (self.segment_state_source == "observed" or delivered_segments)
            or not self.profile.supports_segments
            and not self.projector_mode_active
            and self._static_colour_known
            and self.color_temp_kelvin is None,
            static_gradual=self.static_gradual if self.color_mode is ParsedMode.COLOUR and gradual_observed else None,
            static_colour_observed=self.color_mode is ParsedMode.COLOUR
            and (
                self.projector_appearance_observed
                and self.source_field_fresh("projector_appearance")
                or observed_segments
                and self.profile.can_read(ReadDomain.SEGMENTS)
                or not self.profile.supports_segments
                and not self.projector_mode_active
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
                or segment_colour_matches(self._as_coordinator, index, self.segment_colors[index], expected[0])
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
            video_sensitivity=self.video_sensitivity,
            video_hdmi_input=self.video_hdmi_input,
            hdmi_box_light=self.hdmi_box_light,
            hdmi_box_brightness=self.hdmi_box_brightness,
            hdmi_box_automatic=self.hdmi_box_automatic,
            hdmi_box_effect=self.hdmi_box_effect,
            video_color_calibration=self.video_color_calibration,
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
            transition = self._mode_transition
            if transition is not None and not transition.current():
                return False
            target = state.state if isinstance(state, PreparedStaticRecovery) else state
            if target.mode == "colour" and get_profile(self.model).static_identity_fields:
                await self._as_coordinator.async_prepare_identity_gated_control()
            prepared = state if isinstance(state, PreparedStaticRecovery) else self._prepare_static_colour(target)
            if prepared is not None:
                prepared.check(self)
            elif target.mode == "colour":
                if not target.is_on:
                    await self.send_command(build_power(False, self.model), state_values={"is_on": False})
                    await self.refresh_state(RefreshRequest(on=False))
                return False
            attempts = self.control_write_attempts
            snapshot = self._pre_mode_snapshot
            restored = False
            try:
                restored = await self._async_restore_prior_control_state(
                    target, overwritten_diy_code=overwritten_diy_code, prepared_colour=prepared
                ) and (transition is None or transition.current())
                return restored
            finally:
                if (
                    prepared is not None
                    and self.control_write_attempts != attempts
                    and self._pre_mode_snapshot is snapshot
                    and prepared.generation == self._profile_generation
                    and (prepared.subscription is None or prepared.subscription is self._notification_token)
                ):
                    self._incomplete_static_exit = None if restored else prepared.state

    async def _async_restore_prior_control_state(
        self,
        state: PriorControlState,
        *,
        overwritten_diy_code: int | None,
        prepared_colour: PreparedStaticRecovery | None = None,
    ) -> bool:
        if state.mode == "custom" and self.profile.diy_upload_transport == "single":
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
        source_values = () if prepared_colour is not None else tuple(self._native_recovery_values(state, native_writes))
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
        transition = self._mode_transition
        if not restored or transition is not None and not transition.current():
            return False
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
            elif self.profile.setting_grammar in {"H607C", "H60B0", "H60B2", "H8604"}:
                from .generated_protocol_adapter import build_boolean_control_query

                if not await self._as_coordinator._async_read_setting_fields(
                    client,
                    build_boolean_control_query(next(iter(native_zones)), self.model, profile=self.profile),
                    tuple(f"boolean_{name}" for name in sorted(native_zones)),
                    deadline=time.monotonic() + 4.0,
                ):
                    return False
            else:
                revisions = {
                    f"boolean_{name}": self._field_revisions.get(f"boolean_{name}", 0) for name in native_zones
                }
                if not await self._async_read_bulk_status(
                    client, deadline=time.monotonic() + 4.0, domains=("zone_enable",)
                ) or any(self._field_revisions.get(field, 0) <= revision for field, revision in revisions.items()):
                    return False
        if not await async_restore_source_flags(self._as_coordinator, expected):
            return False
        return (
            restored
            and set(expected) == native_zones
            and all(self.boolean_control_state.get(name) == value for name, value in expected.items())
            and all(getattr(self, field) == value for field, value in source_values)
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
        if self._mode_transition is not None:
            # Intermediate controls can use a different mode from the final resident effect.
            self._mode_transition.verifying_resident_effect = state.mode != "colour"
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
        transition = self._mode_transition

        def powering_off() -> None:
            if transition is not None:
                transition.powering_off = True

        try:
            appearance_restored = await self._async_restore_effect_appearance(
                replace(state, is_on=True), overwritten_diy_code=overwritten_diy_code, prepared_colour=prepared_colour
            )
        except BaseException:
            if self.is_on or self.control_write_attempts != attempts:
                try:
                    await self.send_command(
                        build_power(False, self.model), state_values={"is_on": False}, on_write=powering_off
                    )
                except Exception:
                    _LOGGER.debug("Power-off cleanup failed during effect recovery", exc_info=True)
            raise
        await self.send_command(build_power(False, self.model), state_values={"is_on": False}, on_write=powering_off)
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
                ("video_sensitivity", ("video_sensitivity",)),
                ("hdmi_input", ("video_hdmi_input",)),
                (
                    "hdmi_box_light",
                    ("hdmi_box_light", "hdmi_box_brightness", "hdmi_box_automatic", "hdmi_box_effect"),
                ),
                ("color_calibration", ("video_color_calibration",)),
                (
                    "color_calibration_red",
                    ("video_color_calibration",)
                    if state.video_color_calibration is not None and len(state.video_color_calibration) == 4
                    else (),
                ),
            )
            if (control != "inline_relative_brightness" or self.profile.video_embeds_relative_brightness)
            and fields
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
        if "video_sensitivity" in permitted & needed and state.video_sensitivity is not None:
            await apply_video_sensitivity(self._as_coordinator, state.video_sensitivity)
        if "hdmi_input" in permitted & needed and state.video_hdmi_input is not None:
            await apply_hdmi_input(self._as_coordinator, state.video_hdmi_input)
        if "hdmi_box_light" in permitted & needed:
            values = (
                state.hdmi_box_light,
                state.hdmi_box_brightness,
                state.hdmi_box_automatic,
                state.hdmi_box_effect,
            )
            if any(value is None for value in values):
                complete = False
                permitted.discard("hdmi_box_light")
            else:
                await apply_hdmi_box_light(self._as_coordinator, cast(tuple[bool, int, bool, int], values))
        if "color_calibration" in permitted & needed and state.video_color_calibration is not None:
            await apply_video_color_calibration(self._as_coordinator, state.video_color_calibration)
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

    def _native_recovery_values(
        self, state: PriorControlState, writes: tuple[PreparedSourceValue, ...]
    ) -> Iterator[tuple[str, int]]:
        for write in writes:
            field = "ripple_speed" if write.attribute == "ripple_speed" else f"{write.source}_{write.attribute}"
            yield field, write.value
        for field in source_kelvin_hint_fields(self.profile):
            if (value := getattr(state, field)) is not None:
                yield field, normalize_kelvin(value, self.profile) if value else 0

    def _prepare_static_colour(self, state: PriorControlState) -> PreparedStaticRecovery | None:
        if state.mode != "colour":
            return None
        if self.profile.projector_grammar is not None:
            if state.projector_appearance is None:
                return None
            from .projector_protocol import build_appearance

            packets = (
                build_power(True, self.model),
                build_brightness(state.brightness_pct, self.model),
                *build_appearance(state.projector_appearance, self.profile),
            )
            for packet in packets:
                require_profile_packet(packet, self.profile)
            return PreparedStaticRecovery(
                state, packets, False, self.profile, self._profile_generation, self._notification_token
            )
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
        native_values = dict(self._native_recovery_values(state, native_writes))
        if native_values:
            state = replace(
                state,
                top_kelvin=native_values.get("top_kelvin", state.top_kelvin),
                bottom_kelvin=native_values.get("bottom_kelvin", state.bottom_kelvin),
            )
        if self.profile.supports_segments:
            prepared = self._prepare_segmented_colour(state)
            return replace(prepared, native_writes=native_writes) if prepared is not None else None
        if not state.static_rgb_known and state.color_temp_kelvin is None:
            return None
        if state.color_temp_kelvin is not None:
            state = replace(state, color_temp_kelvin=normalize_kelvin(state.color_temp_kelvin, self.profile))
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
            and not self.profile.static_palette_recovery
            and bool(target_intents)
            and target_intents[0] > 0
            and len(set(target_intents)) == 1
            and self.profile.supports_color_temperature
        )
        target_colours = list(state.segment_colors)
        if not (self.profile.kelvin_renders_device_white or self.profile.static_palette_recovery):
            for index, kelvin in enumerate(target_intents):
                if kelvin:
                    target_colours[index] = table_kelvin_rgb(kelvin)
        left, right = state.left_bar_kelvin, state.right_bar_kelvin
        if source_restore or bar_restore:
            left = normalize_kelvin(left, self.profile) if left else left
            right = normalize_kelvin(right, self.profile) if right else right
        if bar_restore:
            assert left is not None and right is not None
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
                    packets.extend(
                        build_segment_kelvin_packets(
                            segments,
                            intent,
                            self.model,
                            profile=self.profile,
                            companion_rgb=rgb if self.profile.static_palette_recovery else None,
                        )
                    )
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
        subscription = await self._write_static_restore(prepared)
        mode_revision = self._field_revisions.get("color_mode", 0)
        request = RefreshRequest(
            on=True,
            brightness=state.brightness_pct if self.profile.can_read(ReadDomain.BRIGHTNESS) else None,
            refresh_all=True,
            query_native_settings=False,
            query_segments=False,
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
        )
        basic_matches = await self.refresh_state(request)
        segments_match = await self.async_refresh_segments() if self.profile.can_read(ReadDomain.SEGMENTS) else True

        expected_colours = state.segment_colors
        verify_gradual = False

        def matches_layout() -> bool:
            return (
                self.brightness_pct == state.brightness_pct
                and len(self.segment_colors) == len(expected_colours)
                and all(
                    segment_colour_matches(
                        self._as_coordinator,
                        index,
                        actual,
                        expected if self.profile.static_palette_recovery else intent or expected,
                    )
                    for index, (actual, expected, intent) in enumerate(
                        zip(self.segment_colors, expected_colours, target_intents, strict=True)
                    )
                )
                and (state.segment_brightness is None or tuple(self.segment_brightness) == state.segment_brightness)
                and (not verify_gradual or self.static_gradual == state.static_gradual)
                and (
                    self.profile.setting_grammar != "H6046"
                    or (self.left_bar_kelvin, self.right_bar_kelvin) == (state.left_bar_kelvin, state.right_bar_kelvin)
                )
                and (
                    (not source_restore or state.top_kelvin is None or self.top_kelvin == state.top_kelvin)
                    and self.capture_effect_control_state().static_segment_kelvin(self.profile) == target_intents
                )
            )

        restored = (
            complete
            and basic_matches is True
            and segments_match is True
            and (
                not self.profile.supports_color_mode_readback
                or self._field_revisions.get("color_mode", 0) > mode_revision
            )
            and self._confirm_static_appearance(prepared, subscription, request, matches_layout)
        )
        if not restored:
            return False
        if state.static_gradual is not None:
            if "gradual" not in self.profile.boolean_controls:
                return False
            await self.async_set_boolean_control("gradual", state.static_gradual)
            if self.profile.static_readback_gradual:
                # The register reply does not establish the static mode's Gradual flag.
                gradual_revision = self._field_revisions.get("static_gradual", 0)
                if (
                    await self.refresh_state(
                        RefreshRequest(
                            query_native_settings=False,
                            query_segments=False,
                            required_domains=self.profile.read_domains & {ReadDomain.COLOUR_MODE, ReadDomain.MODE},
                        )
                    )
                    is not True
                    or self._field_revisions.get("static_gradual", 0) <= gradual_revision
                ):
                    return False
            verify_gradual = True
            if not self._confirm_static_appearance(prepared, subscription, request, matches_layout):
                return False
        self._static_rgb_known = state.static_rgb_known
        return True

    async def _write_static_restore(self, prepared: PreparedStaticRecovery) -> object | None:
        generation = self._profile_generation
        foreground = self._control_arbiter.foreground_generation
        selector_revision = self._selector_revision
        segment_revision = self._field_revisions.get("segment_colors", 0)
        attempts = self.control_write_attempts
        static_attempts = self._static_write_attempts
        expected_segments = (tuple(self.segment_colors), tuple(self.segment_brightness))
        request = self._as_coordinator.control_write_request()
        transition = self._mode_transition
        token = self._notification_token
        bound = token is not None

        def guard() -> None:
            nonlocal token, bound
            prepared.check(self)
            if (
                generation != self._profile_generation
                or foreground != self._control_arbiter.foreground_generation
                or self._selector_revision != selector_revision
                and (self._static_write_attempts == static_attempts or self.color_mode is not ParsedMode.COLOUR)
                or self._field_revisions.get("segment_colors", 0) != segment_revision
                and (tuple(self.segment_colors), tuple(self.segment_brightness)) != expected_segments
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
            if transition is not None and self._static_write_attempts != static_attempts:
                transition.static_restore_started = True
            expected_segments = (tuple(self.segment_colors), tuple(self.segment_brightness))

        try:
            await self.async_write_effect_sequence(
                prepared.packets,
                intent=self._control_arbiter.current_task_intent or ControlIntent.USER,
                write_guard=guard,
                retry_allowed=lambda: self.control_write_attempts == attempts,
                packet_on_write=attempted,
                require_upload_ack=prepared.state.projector_appearance is not None,
                upload_ack_index=len(prepared.packets) - 2 if prepared.state.projector_appearance is not None else None,
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
        if prepared.state.projector_appearance is not None:
            from .projector_runtime import install_appearance

            install_appearance(self._as_coordinator, prepared.state.projector_appearance, observed=False)
        return token

    async def _restore_static_colour(
        self, state: PriorControlState, complete: bool, *, prepared: PreparedStaticRecovery | None = None
    ) -> bool:
        prepared = prepared or self._prepare_static_colour(state)
        if prepared is None:
            return False
        subscription = await self._write_static_restore(prepared)
        if state.projector_appearance is not None:
            from .projector_runtime import current_appearance, prepare_baseline

            await prepare_baseline(self._as_coordinator)
            return complete and self._retain_recovery_appearance(
                {
                    "is_on": True,
                    "brightness_pct": state.brightness_pct,
                    "color_mode": ParsedMode.COLOUR,
                    "projector_appearance": state.projector_appearance,
                },
                prepared.generation,
                subscription,
                lambda: current_appearance(self._as_coordinator) == state.projector_appearance,
            )
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
        verified = not self.profile.state_readable or await self.refresh_state(request) is True
        return complete and verified and self._confirm_static_appearance(prepared, subscription, request)

    def _confirm_static_appearance(
        self,
        prepared: PreparedStaticRecovery,
        subscription: object | None,
        request: RefreshRequest,
        matches_layout: Callable[[], bool] | None = None,
    ) -> bool:
        expected = request.field_expectations(self.profile)
        expected.update(is_on=True, color_mode=ParsedMode.COLOUR)
        expected.update(self._native_recovery_values(prepared.state, prepared.native_writes))
        return self._retain_recovery_appearance(expected, prepared.generation, subscription, matches_layout)

    def _retain_recovery_appearance(
        self,
        expected: Mapping[str, Any],
        generation: int,
        subscription: object | None,
        matches_layout: Callable[[], bool] | None = None,
    ) -> bool:
        transition = self._mode_transition
        selector_revision = self._selector_revision

        def matches() -> bool:
            powering_off = transition is not None and transition.powering_off
            return (
                generation == self._profile_generation
                and subscription is self._notification_token
                and (expected.get("color_mode") is ParsedMode.COLOUR or selector_revision == self._selector_revision)
                and all(
                    getattr(self, field) == (False if field == "is_on" and powering_off else value)
                    for field, value in expected.items()
                )
                and (
                    expected.get("color_mode") is not ParsedMode.COLOUR
                    or self.active_mode == ("off" if powering_off else "colour")
                )
                and (matches_layout is None or matches_layout())
            )

        if not matches() or transition is not None and transition.superseded:
            return False
        if transition is not None:
            transition.observations_match = matches
        return True

    def _retain_verified_selector(
        self, expectations: Mapping[str, Any], generation: int, subscription: object | None
    ) -> bool:
        transition = self._mode_transition
        if (
            transition is None
            or transition.owner is not asyncio.current_task()
            or not (
                transition.verifying_resident_effect
                or transition.purpose in (ModeTransitionPurpose.SELECTION, ModeTransitionPurpose.PREVIEW)
            )
            or not expectations.keys() & {"scene_code", "diy_code", "music_mode", "video_mode"}
        ):
            return True
        return self._retain_recovery_appearance(expectations, generation, subscription)
