"""Effect recovery: restoring the prior control state after previews and effect writes."""

import logging
import time
from contextlib import nullcontext
from dataclasses import replace
from typing import TYPE_CHECKING, Any, cast

from .const import NATIVE_ZONE_CONTROLS
from .control_arbiter import ControlIntent
from .coordinator_base import _CoordinatorBase
from .coordinator_status import (
    ParsedMode,
)
from .effect_contracts import CapabilityState
from .effect_deployments import PriorControlState
from .generated_protocol_adapter import (
    build_brightness,
    build_diy_activation,
    build_power,
    table_kelvin_rgb,
)
from .light_commands import (
    build_color_rgb,
    build_color_temp,
    build_segment_brightness,
    build_segment_color_temp,
    build_segment_paint,
    normalize_kelvin,
)
from .music_commands import prepare_music_profile_writes
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
)
from .scenes import (
    MODEL_SCENES,
    canonical_scene_key,
    resolve_scene_code,
    scene_selector_code,
)
from .video_applicability import (
    video_control_states,
)

if TYPE_CHECKING:
    from .coordinator import GoveeBLECoordinator

_LOGGER = logging.getLogger(__name__)


class _RecoveryMixin(_CoordinatorBase):
    @property
    def _as_coordinator(self) -> GoveeBLECoordinator:
        # The native-control helpers are typed on the concrete coordinator this mixin is part of.
        return cast("GoveeBLECoordinator", self)

    def capture_effect_control_state(self) -> PriorControlState:
        zone_flags = {
            name: value
            for name, value in self.boolean_control_state.items()
            if name in NATIVE_ZONE_CONTROLS
            and self._notify_started_monotonic is not None
            and self._field_received_at.get(f"boolean_{name}", -1) >= self._notify_started_monotonic
        }
        # active_mode hides the resident mode while powered off and maps unknown to colour.
        mode = (
            "unknown"
            if self.color_mode is ParsedMode.UNKNOWN
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
        return PriorControlState(
            mode=mode,
            is_on=self.is_on,
            brightness_pct=self.brightness_pct,
            rgb_color=self.rgb_color,
            color_temp_kelvin=self.color_temp_kelvin,
            static_rgb_known=self._static_rgb_known and self.segment_state_source == "observed",
            static_gradual=self.static_gradual if self.color_mode is ParsedMode.COLOUR else None,
            panel_enabled=zone_flags.get("panel_enabled"),
            ring_enabled=zone_flags.get("ring_enabled"),
            left_bar_enabled=zone_flags.get("left_bar_enabled"),
            right_bar_enabled=zone_flags.get("right_bar_enabled"),
            pole_enabled=zone_flags.get("pole_enabled"),
            base_enabled=zone_flags.get("base_enabled"),
            left_bar_kelvin=self.left_bar_kelvin
            if self._notify_started_monotonic is not None
            and self._field_received_at.get("left_bar_kelvin", -1) >= self._notify_started_monotonic
            else None,
            right_bar_kelvin=self.right_bar_kelvin
            if self._notify_started_monotonic is not None
            and self._field_received_at.get("right_bar_kelvin", -1) >= self._notify_started_monotonic
            else None,
            segment_colors=tuple(self.segment_colors) if self.segment_state_source == "observed" else None,
            segment_brightness=tuple(self.segment_brightness)
            if self.segment_state_source == "observed" and self.segment_brightness_readable
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
            music_sensitivity=self.music_sensitivity,
            music_calm=self.music_calm,
            music_color=self.music_color,
            music_separation_point=self.music_separation_point,
            music_separation_gradient=self.music_separation_gradient,
            music_hopping_brightness=self.music_hopping_brightness,
            music_piano_key_count=self.music_piano_key_count,
            music_fountain_direction=self.music_fountain_direction,
            music_daynight_segments=self.music_daynight_segments,
            music_daynight_speed=self.music_daynight_speed,
            music_daynight_gradient=self.music_daynight_gradient,
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
        state: PriorControlState,
        *,
        overwritten_diy_code: int | None,
    ) -> bool:
        restored = await self._async_restore_effect_appearance(state, overwritten_diy_code=overwritten_diy_code)
        native_zones = self.profile.boolean_controls.intersection(NATIVE_ZONE_CONTROLS)
        if not native_zones:
            return restored
        expected = {name: value for name in native_zones if (value := getattr(state, name)) is not None}
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
            elif self.profile.setting_grammar == "H607C":
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
        for name, value in expected.items():
            if self.boolean_control_state.get(name) != value:
                await self.async_set_boolean_control(name, value)
        return (
            restored
            and set(expected) == native_zones
            and all(self.boolean_control_state.get(name) == value for name, value in expected.items())
        )

    async def _async_restore_effect_appearance(
        self,
        state: PriorControlState,
        *,
        overwritten_diy_code: int | None,
    ) -> bool:
        if not state.is_on:
            return await self._async_restore_effect_control_state(state, overwritten_diy_code=overwritten_diy_code)
        if (
            state.mode == "colour"
            and self.profile.segment_colour_mode_ambiguous
            and not (state.static_rgb_known or state.restorable_bar_white(self.profile))
        ):
            return False
        async with self.async_mask_transaction() if state.mode == "colour" else nullcontext():
            if (
                self.profile.configured_string_counts
                and state.mode == "colour"
                and (state.segment_colors is None or len(state.segment_colors) != self.profile.segment_count)
            ):
                return False
            return await self._async_restore_effect_control_state(state, overwritten_diy_code=overwritten_diy_code)

    async def _async_restore_effect_control_state(
        self,
        state: PriorControlState,
        *,
        overwritten_diy_code: int | None,
    ) -> bool:
        if not state.is_on:
            return await self._restore_effect_while_off(state, overwritten_diy_code=overwritten_diy_code)
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
            return await self._restore_segmented_colour(state, complete)
        return await self._restore_static_colour(state, complete)

    async def _restore_effect_while_off(self, state: PriorControlState, *, overwritten_diy_code: int | None) -> bool:
        attempts = self.control_write_attempts
        try:
            appearance_restored = await self._async_restore_effect_appearance(
                replace(state, is_on=True), overwritten_diy_code=overwritten_diy_code
            )
        except BaseException:
            if self.is_on or self.control_write_attempts != attempts:
                try:
                    await self.send_command(build_power(False, self.model), state_values={"is_on": False})
                except Exception:
                    _LOGGER.debug("Power-off cleanup failed during effect recovery", exc_info=True)
            raise
        await self.send_command(build_power(False, self.model), state_values={"is_on": False})
        return await self.refresh_state(expected_on=False) and appearance_restored

    def _prepare_music_restore(
        self, state: PriorControlState
    ) -> tuple[Any, tuple[tuple[bytes, dict[str, Any]], ...]] | None:
        """Return (variant, writes) for a music snapshot, or None when it cannot be recovered."""
        from .music_commands import prepare_music_body_writes

        variant = None
        music_writes: tuple[tuple[bytes, dict[str, Any]], ...] = ()
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
            )
            if (state.video_restore_controls is None or control in state.video_restore_controls)
            and any(
                getattr(state, field) is not None and getattr(self, field) != getattr(state, field) for field in fields
            )
        }
        complete = not (needed - permitted)
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
        if (
            "relative_brightness" in permitted & needed
            and state.relative_brightness_left is not None
            and state.relative_brightness_top is not None
            and state.relative_brightness_right is not None
            and state.relative_brightness_bottom is not None
        ):
            await apply_relative_brightness(
                self._as_coordinator,
                tuple(getattr(state, f"relative_brightness_{zone}") for zone in self.profile.video_brightness_zones),
            )
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
            and await self.refresh_state(expected_on=True, expected_brightness=state.brightness_pct) is True
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
            if isinstance(template.content, LayeredEffect) and template.content.native_diy is not None
        }
        if (
            self.profile.supports_advanced_effects
            and state.scene_code is not None
            and (state.scene_code == self.profile.advanced_diy_selector or state.scene_code in native_selectors)
        ):
            if state.scene_code == overwritten_diy_code:
                return False
            await self.send_command(build_power(True, self.model))
            await self.send_command(build_brightness(state.brightness_pct, self.model))
            await self.send_command(build_scene_activation(self.model, state.scene_code, profile=self.profile))
            await self.refresh_state(
                expected_on=True, expected_brightness=state.brightness_pct, expected_scene_code=state.scene_code
            )
            # Selection is restored, but no supported read proves resident body equality.
            return False
        resolved = (
            resolve_scene_code(
                self.model,
                state.scene_code,
                preferred_key=state.effect,
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
            scene = candidate
        else:
            return False
        selector = scene_selector_code(self.model, scene, profile=self.profile)
        await self.send_command(build_power(True, self.model))
        await self.send_command(build_brightness(state.brightness_pct, self.model))
        # A catalogue body/default speed is not the original authored resident body.
        await self.send_command(build_scene_activation(self.model, selector, scene.music_code))
        return (
            await self.refresh_state(
                expected_on=True, expected_brightness=state.brightness_pct, expected_scene_code=selector
            )
            is True
            and not scene.param
            and complete
        )

    async def _restore_music(
        self,
        state: PriorControlState,
        variant: Any,
        music_writes: tuple[tuple[bytes, dict[str, Any]], ...],
        physical_ic_count: int | None,
        complete: bool,
    ) -> bool:
        music_expectations: dict[str, Any] = {}
        selector_expectations = {
            spec.key: (state.music_parameters or {})[spec.profile_key]
            for spec in (() if variant is None else variant.selector_parameters)
            if self.profile.music_grammar == "H6046" and spec.profile_key in (state.music_parameters or {})
        }
        selector_baselines = {field: self._field_revisions.get(field, 0) for field in selector_expectations}
        if (variant is None or variant.layout is None) and self.profile.music_grammar != "H6046":
            music_expectations = {
                "expected_music_color": state.music_color,
                "expected_music_auto_color": state.music_color is None,
            }
            if variant and variant.supports_style:
                music_expectations["expected_music_calm"] = state.music_calm
        if self.profile.music_grammar == "H6046" and variant and variant.supports_style:
            music_expectations["expected_music_calm"] = state.music_calm

        def guard_music_recovery() -> None:
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
                expected_on=True,
                expected_brightness=state.brightness_pct,
                expected_music_mode=state.music_mode,
                expected_music_sensitivity=state.music_sensitivity,
                **music_expectations,
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
        for field, control in (
            ("full_screen", "capture_region"),
            ("saturation", "saturation"),
            ("sound_effects", "sound_effects"),
            ("sound_effects_softness", "sound_effects"),
        ):
            if (
                state.video_restore_controls is None or control in state.video_restore_controls
            ) and control not in permitted:
                complete = complete and getattr(self, f"video_{field}") == getattr(state, f"video_{field}")
        restored = frozenset(
            field
            for field, control in (
                ("full_screen", "capture_region"),
                ("saturation", "saturation"),
                ("sound_effects", "sound_effects"),
                ("sound_effects_softness", "sound_effects"),
            )
            if control in permitted
        )
        return (
            await apply_active_video_mode(
                self._as_coordinator,
                mode=state.video_mode,
                requested_values={field: getattr(state, f"video_{field}") for field in restored},
                parameters=state.video_parameters,
            )
            and await self.refresh_state(expected_on=True, expected_brightness=state.brightness_pct) is True
            and complete
        )

    async def _restore_segmented_colour(self, state: PriorControlState, complete: bool) -> bool:
        if not self.profile.supports_color_mode_readback:
            # Incomplete state cannot safely reproduce the original emitter mode.
            return False
        if (
            state.segment_colors is None
            or len(state.segment_colors) != self.profile.segment_count
            or (state.segment_brightness is None) == self.profile.supports_segment_brightness
        ):
            return False
        colour_groups: dict[tuple[int, int, int], list[int]] = {}
        brightness_groups: dict[int, list[int]] = {}
        for index, rgb in enumerate(state.segment_colors, 1):
            colour_groups.setdefault(rgb, []).append(index)
        if state.segment_brightness is not None:
            for index, brightness in enumerate(state.segment_brightness, 1):
                brightness_groups.setdefault(brightness, []).append(index)
        kelvin_restore = state.color_temp_kelvin is not None and self.profile.static_readback_kelvin
        if (
            kelvin_restore
            and state.color_temp_kelvin is not None
            and (
                self.profile.segment_kelvin_renders_device_rgb
                or state.segment_colors != (table_kelvin_rgb(state.color_temp_kelvin),) * self.profile.segment_count
            )
        ):
            # Whole-device Kelvin cannot reproduce a simultaneously captured
            # different RGB layout. Preserve it instead of overwriting it.
            return False
        packets = (
            [build_color_temp(state.color_temp_kelvin, self.model, profile=self.profile)]
            if kelvin_restore and state.color_temp_kelvin is not None
            else build_segment_paint(
                [(segments, rgb) for rgb, segments in colour_groups.items()], self.model, profile=self.profile
            )
        ) + [
            build_segment_brightness(segments, brightness, self.model, profile=self.profile)
            for brightness, segments in brightness_groups.items()
        ]
        if self.profile.setting_grammar == "H6046" and state.restorable_bar_white(self.profile):
            half = self.profile.segment_count // 2
            packets = [
                build_segment_color_temp(range(start + 1, start + half + 1), kelvin, self.model, profile=self.profile)
                for start, kelvin in ((0, state.left_bar_kelvin), (half, state.right_bar_kelvin))
                if kelvin is not None
            ] + [
                build_segment_brightness(segments, brightness, self.model, profile=self.profile)
                for brightness, segments in brightness_groups.items()
            ]
        for packet in (build_power(True, self.model), build_brightness(state.brightness_pct, self.model), *packets):
            await self.send_command(packet)
        if state.static_gradual is not None:
            if "gradual" not in self.profile.boolean_controls:
                complete = False
            else:
                await self.async_set_boolean_control("gradual", state.static_gradual)
        mode_revision = self._field_revisions.get("color_mode", 0)
        basic_matches = await self.refresh_state(
            expected_on=True,
            expected_brightness=state.brightness_pct,
            refresh_all=True,
            expected_color_temp_kelvin=state.color_temp_kelvin if kelvin_restore else None,
            expected_zero_kelvin=(
                self.profile.static_readback_zero_kelvin_is_rgb
                and not kelvin_restore
                and not state.restorable_bar_white(self.profile)
            ),
        )
        segments_match = await self.async_refresh_segments()
        restored = (
            basic_matches is True
            and segments_match is True
            and self.is_on
            and self.brightness_pct == state.brightness_pct
            and self.active_mode == "colour"
            and self.color_mode is ParsedMode.COLOUR
            and self._field_revisions.get("color_mode", 0) > mode_revision
            and tuple(self.segment_colors) == state.segment_colors
            and (state.segment_brightness is None or tuple(self.segment_brightness) == state.segment_brightness)
            and (state.static_gradual is None or self.static_gradual == state.static_gradual)
            and (
                self.profile.setting_grammar != "H6046"
                or (self.left_bar_kelvin, self.right_bar_kelvin) == (state.left_bar_kelvin, state.right_bar_kelvin)
            )
            and complete
        )
        if restored:
            self._static_rgb_known = state.static_rgb_known
        return restored

    async def _restore_static_colour(self, state: PriorControlState, complete: bool) -> bool:
        await self.send_command(build_power(True, self.model))
        await self.send_command(build_brightness(state.brightness_pct, self.model))
        if state.color_temp_kelvin is not None:
            await self.send_command(build_color_temp(state.color_temp_kelvin, self.model, profile=self.profile))
        else:
            await self.send_command(build_color_rgb(*state.rgb_color, self.model, profile=self.profile))
        static_expectations: dict[str, Any] = {}
        if state.color_temp_kelvin is not None and self.profile.static_readback_kelvin:
            static_expectations["expected_color_temp_kelvin"] = normalize_kelvin(state.color_temp_kelvin, self.profile)
        elif state.color_temp_kelvin is None and self.profile.static_readback_echoes_color:
            static_expectations["expected_rgb_color"] = state.rgb_color
        if state.color_temp_kelvin is None and self.profile.static_readback_zero_kelvin_is_rgb:
            static_expectations["expected_zero_kelvin"] = True
        return (
            self.profile.state_readable
            and await self.refresh_state(
                expected_on=True, expected_brightness=state.brightness_pct, **static_expectations
            )
            and self.active_mode == "colour"
            and self.color_mode is ParsedMode.COLOUR
            and bool(static_expectations)
            and complete
        )
