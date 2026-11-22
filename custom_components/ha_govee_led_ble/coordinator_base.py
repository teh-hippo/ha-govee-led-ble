"""Shared typed base for the coordinator and its write mixins."""

import asyncio
from collections.abc import Awaitable, Callable, Generator, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, contextmanager
from typing import TYPE_CHECKING, Any, cast

from bleak import BleakClient
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, ModelProfile, ReadDomain
from .control_arbiter import BLEControlArbiter, ControlIntent, async_control_intent
from .coordinator_control import ControlStateCheckpoint
from .coordinator_status import ParsedMode, StatusDomain
from .coordinator_upload import PendingUploadAck
from .scenes import SceneEntry, resolve_scene_target, scene_command_identity_fields

if TYPE_CHECKING:
    from .coordinator import GoveeBLECoordinator
    from .coordinator_modes import ModeTransitionPurpose, _ModeTransition
    from .coordinator_recovery import PreparedStaticRecovery
    from .coordinator_refresh import RefreshRequest
    from .effect_deployments import PriorControlState
    from .effect_domain import EffectContent
    from .generated_protocol_adapter import BulkStatusCollector
    from .govee_encryption.session import GoveeEncryptionSession
    from .low_blue_light import LowBlueLightState
    from .music_commands import MusicWriteSequence
    from .native_profile_controls import ProfileWriter
    from .projector import ProjectorAppearance
    from .reply_pacing import ReplyGate


class _CoordinatorBase(DataUpdateCoordinator[dict[str, Any]]):
    """Optimistic-state attributes and behaviour the write mixins rely on.

    Declares the fields and methods that ``GoveeBLECoordinator`` populates so the timer
    mixin type-checks without importing the concrete coordinator. No ``__init__`` here.
    """

    @property
    def _as_coordinator(self) -> GoveeBLECoordinator:
        return cast("GoveeBLECoordinator", self)

    brightness_pct: int
    bottom_brightness: int | None
    bottom_kelvin: int | None
    top_kelvin: int | None
    ripple_speed: int | None
    local_sound: int | None
    local_volume: int | None
    local_sound_playing: bool | None
    profile: ModelProfile
    _mode_transition: _ModeTransition | None
    address: str
    model: str
    effect_families: frozenset[str]
    effect_categories: frozenset[str]
    prefix_effect_names: bool
    always_include_custom_effects: bool
    is_on: bool
    effect: str | None
    fw_version: str | None
    wireless_firmware_version: str | None
    wireless_hardware_version: str | None
    hw_version: str | None
    _configured_firmware: str | None
    _configured_hardware: str | None
    rgb_color: tuple[int, int, int]
    color_temp_kelvin: int | None
    rgb_color_source: str
    color_temp_kelvin_source: str
    color_temp_unknown: bool
    _pending_kelvin: int | None
    _kelvin_observed_segment_revision: int
    _static_rgb_known: bool
    white_brightness: int
    music_mode: str
    video_mode: str
    music_sensitivity: int
    music_color: tuple[int, int, int] | None
    music_calm: bool
    music_separation_point: int
    music_separation_gradient: bool
    music_hopping_brightness: int
    music_piano_key_count: int
    music_fountain_direction: str
    music_daynight_segments: int
    music_daynight_speed: int
    music_daynight_gradient: bool
    video_parameters: dict[str, Any] | None
    video_full_screen: bool
    video_saturation: int
    video_sensitivity: int | None
    video_hdmi_input: int | None
    video_hdmi_inputs_connected: tuple[bool, bool, bool, bool] | None
    hdmi_box_light: bool | None
    hdmi_box_brightness: int | None
    hdmi_box_automatic: bool | None
    hdmi_box_effect: int | None
    video_color_calibration: tuple[int, ...] | None
    video_sound_effects: bool
    video_sound_effects_softness: int
    white_balance_red: int | None
    white_balance_blue: int | None
    white_balance_flag: int | None
    white_balance_default_flag: int | None
    white_balance_default_red: int | None
    white_balance_default_blue: int | None
    relative_brightness: int | None
    whole_relative_brightness: int | None
    relative_brightness_left: int | None
    relative_brightness_top: int | None
    relative_brightness_right: int | None
    relative_brightness_bottom: int | None
    relative_brightness_strip_left: int | None
    relative_brightness_strip_right: int | None
    blank_screen: bool | None
    blank_screen_detection: int | None
    blank_screen_low_brightness_duration_seconds: int | None
    blank_screen_same_tone_duration_seconds: int | None
    diy_code: int | None
    diy_companion: int | None
    power_on_open_flag: int | None
    color_mode: ParsedMode | None
    _observed_color_mode: ParsedMode | None
    _selector_revision: int
    _mode_write_generation: int
    _observed_mode_write_generation: int
    _observed_mode_profile_generation: int
    _power_write_generation: int
    _observed_power_write_generation: int
    _observed_power_profile_generation: int
    _source_power_observation_generation: dict[str, tuple[int, int]]
    _control_arbiter: BLEControlArbiter
    _lock: asyncio.Lock
    segment_state_source: str
    pact_type: int | None
    pact_code: int | None
    _confirmed_identity_fields: set[str]
    control_write_attempts: int
    _static_write_attempts: int
    segment_kelvin: list[int | None]
    segment_brightness_known: list[bool]
    _brightness_pct_known: bool
    _power_known: bool
    _static_colour_known: bool
    projector_appearance: ProjectorAppearance | None
    projector_appearance_observed: bool
    projector_mode_active: bool
    _projector_token: object | None
    _projector_generation: int
    _projector_profile: ModelProfile | None
    _projector_reply: asyncio.Future[ProjectorAppearance] | None
    _projector_collector: BulkStatusCollector | None

    _profile_generation: int
    _authorization_generation: int
    _pre_mode_snapshot: PriorControlState | None
    _incomplete_static_exit: PriorControlState | None
    _pre_mode_profile: ModelProfile | None
    _pre_mode_needs_qualification: bool
    segment_colors: list[tuple[int, int, int]]
    segment_brightness: list[int]
    segment_brightness_readable: bool
    boolean_control_state: dict[str, bool]
    low_blue_light: LowBlueLightState | None
    _music_palette: tuple[str, tuple[tuple[int, int, int], ...]] | None
    _music_body: tuple[str, bytes] | None
    static_gradual: bool | None
    left_bar_kelvin: int | None
    right_bar_kelvin: int | None
    bar_enable_mask: int | None
    white_balance_scalar: int | None
    black_border: bool | None
    segment_state_observed_at: str | None
    _client: BleakClient | None
    _encryption: GoveeEncryptionSession | None
    _notification_token: object | None
    _last_rx_monotonic: float | None
    _reply_gate: ReplyGate
    _notify_started_monotonic: float | None
    _expected_state: dict[str, tuple[Any, float]]
    _field_revisions: dict[str, int]
    _revision_event: asyncio.Event
    _field_received_at: dict[str, float]
    _observed_physical_ic_count: int | None
    _physical_ic_count_confirmed: bool
    _bulk_collector: BulkStatusCollector | None
    _bulk_query_deadline: float | None
    _bulk_mode_unqualified: bool
    _segment_query_generation: int | None
    _configured_strings_confirmed: bool
    _segment_query_incomplete: bool
    _segment_query_colors: list[tuple[int, int, int]] | None
    _segment_query_brightness: list[int] | None
    _segment_groups_observed: set[int]
    _initialized_music_parameters: set[str]
    _blank_screen_notification_revision: int
    _dreamview_private_write: bool
    _upload_ack: PendingUploadAck | None
    _domain_revisions: dict[StatusDomain, int]
    _h607c_uncertain_state_fields: set[str]
    _h607c_failed_color_write: bool
    _setting_ack: tuple[BleakClient, object | None, int, asyncio.Future[bool]] | None

    @contextmanager
    def control_state_checkpoint(self) -> Generator[ControlStateCheckpoint]:
        checkpoint = ControlStateCheckpoint(self)
        try:
            yield checkpoint
        except Exception:
            checkpoint.restore()
            raise

    def install_static_color(
        self, *, rgb: tuple[int, int, int] | None = None, kelvin: int | None = None, source: str = "optimistic"
    ) -> None:
        """Install local/restore values without advancing BLE observation revisions."""
        self.color_temp_unknown = False
        if rgb is not None:
            self.rgb_color = rgb
            self.rgb_color_source = source
        elif self.rgb_color_source == "observed":
            self.rgb_color_source = "retained"
        self.color_temp_kelvin = kelvin
        self.color_temp_kelvin_source = source if kelvin is not None else "initial"

    if TYPE_CHECKING:

        def capture_effect_control_state(self) -> PriorControlState: ...

        async def async_restore_effect_control_state(
            self, state: PriorControlState | PreparedStaticRecovery, *, overwritten_diy_code: int | None
        ) -> bool: ...

        def require_static_baseline(self) -> PriorControlState: ...
        def _discard_static_baseline(self, *, keep_incomplete_exit: bool = False) -> None: ...
        def _static_history_profile_current(self) -> bool: ...
        def async_prepare_static_recovery(
            self, off_guard: Callable[[], None] | None, *, brightness_pct: int | None = None
        ) -> AbstractAsyncContextManager[PreparedStaticRecovery | None]: ...

        def static_mode_confirmed(self) -> bool: ...

        async def async_preflight_static_off(self) -> Callable[[], None] | None: ...

        @property
        def effect_authorization_profile(self) -> ModelProfile: ...

        def _renew_foreground_lease(self) -> None: ...

        async def _disconnect_locked(self, *, clear_cache: bool = False, planned_release: bool = False) -> None: ...

        def _authorization_profile(self) -> ModelProfile: ...

        def _reconcile_authorization(self) -> None: ...

        def _advance_profile_generation(self, *, preserve_static_baseline: bool = False) -> None: ...

        def async_mode_transition(
            self, *, purpose: ModeTransitionPurpose | None = None
        ) -> AbstractAsyncContextManager[_ModeTransition]: ...

        async def async_prepare_static_baseline(self) -> PriorControlState: ...

        async def async_admit_effect_selection(self) -> None: ...

        def _revalidate_upload_ack(self) -> None: ...

        def identity_fields_confirmed(self, fields: frozenset[str] | None = None) -> bool: ...

        async def _async_require_identity(self, client: BleakClient, fields: frozenset[str]) -> None: ...

        def _record_packet(
            self,
            direction: str,
            data: bytes,
            *,
            outcome: str,
            reason: str,
            parser: str | None = None,
            domain: int | None = None,
        ) -> dict[str, Any]: ...

        def source_field_fresh(self, field: str) -> bool: ...
        def _mark_received(self, domain: StatusDomain, *fields: str) -> None: ...

        def _observe_identity_field(self, field: str, value: str | None) -> bool: ...

        def _observe_pact(self, pact_type: int, pact_code: int) -> bool: ...

        def _handle_dreamview_notification(self, frame: bytes) -> bool: ...

        def _apply_segment_group(self, generated: Any) -> tuple[str, ...]: ...

        def _apply_segment_palette(
            self, colours: list[tuple[int, int, int]], brightness: list[int] | None = None
        ) -> tuple[str, ...]: ...

        def _project_segment_palette(self) -> tuple[str, ...]: ...

        def _accept_expected_values(self, values: dict[str, Any]) -> bool: ...

        def _apply_configured_strings(self, count: int) -> None: ...

        async def _wait_for_revisions(
            self,
            field_baselines: Mapping[str, int],
            domain_baselines: Mapping[StatusDomain, int],
            deadline: float,
            *,
            expectations: Mapping[str, Any] | None = None,
            stop: Callable[[], bool] | None = None,
        ) -> bool: ...

        async def _async_write_packet(
            self,
            client: BleakClient,
            packet: bytes,
            *,
            arm_expected: bool = False,
            before_write: Callable[[], None] | None = None,
            state_values: Mapping[str, Any] | None = None,
            expected_values: Mapping[str, Any] | None = None,
            cleanup_deadline: float | None = None,
            packet_validator: Callable[[bytes, ModelProfile], None] = ...,
            on_write: Callable[[], None] | None = None,
        ) -> None: ...

        def async_mask_transaction(self) -> AbstractAsyncContextManager[None]: ...

        async def send_command(
            self,
            packet: bytes,
            *,
            write_guard: Callable[[], None] | None = None,
            state_values: Mapping[str, Any] | None = None,
            on_write: Callable[[], None] | None = None,
        ) -> None: ...

        async def async_observe_effect(
            self, expectations: Mapping[str, Any], *, timeout: float = 4.0
        ) -> bool | None: ...

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
        ) -> None: ...

        async def async_set_boolean_control(self, control: str, enabled: bool) -> None: ...

        def _fresh_source_power(self) -> dict[str, bool] | None: ...

        async def _async_set_verified_setting(
            self, control: str, value: bool | str | int, *, write_guard: Callable[[], None] | None = None
        ) -> None: ...

        async def _ensure_connected(self) -> BleakClient: ...

        async def _async_read_identity(self, required_fields: frozenset[str] | None = None) -> None: ...

        async def _async_read_bulk_status(
            self,
            client: BleakClient,
            *,
            deadline: float,
            domains: tuple[str, ...] | None = None,
            query: bytes | None = None,
            allow_complete_rejection: bool = False,
            qualify_mode: bool = False,
        ) -> bool: ...

        async def _async_read_setting_fields(
            self,
            client: BleakClient,
            query: bytes,
            fields: tuple[str, ...],
            *,
            deadline: float,
            write_guard: Callable[[], None] | None = None,
        ) -> bool: ...

        async def async_refresh_segments(self, *, timeout: float = 2.0) -> bool: ...

        async def _send_state_queries(
            self,
            *,
            query_power: bool = True,
            query_brightness: bool = True,
            query_color_mode: bool = True,
            query_white_balance: bool | None = None,
            query_blank_screen: bool | None = None,
            query_black_border: bool | None = None,
            query_relative_brightness: bool | None = None,
            query_whole_relative_brightness: bool | None = None,
            query_segments: bool | None = None,
            required_domains: frozenset[ReadDomain] | None = None,
            optional_baselines: dict[str, int] | None = None,
            deadline: float | None = None,
            query_native_settings: bool | frozenset[str] = True,
        ) -> bool: ...

        async def async_write_effect_sequence(
            self,
            packets: Sequence[bytes],
            *,
            intent: ControlIntent,
            before_write: Callable[[], Awaitable[None]] | None = None,
            write_guard: Callable[[], None] | None = None,
            state_values: Mapping[str, Any] | None = None,
            expected_values: Mapping[str, Any] | None = None,
            attempt_started: Callable[[int], Awaitable[None]] | None = None,
            retry_allowed: Callable[[], bool] | None = None,
            progress: Callable[[int], Awaitable[None]] | None = None,
            packet_state_values: Sequence[Mapping[str, Any]] | None = None,
            packet_write_guard: Callable[[int], None] | None = None,
            packet_on_write: Callable[[int], None] | None = None,
            require_upload_ack: bool = False,
            upload_ack_index: int | None = None,
            writer: ProfileWriter | None = None,
            packet_validator: Callable[[bytes, ModelProfile], None] = ...,
            final_packet: bytes | None = None,
            before_final: Callable[[], Awaitable[None]] | None = None,
        ) -> None: ...

        async def refresh_state(self, request: RefreshRequest = ...) -> bool | None: ...

        async def _refresh_connected_state(self, request: RefreshRequest = ...) -> bool | None: ...

        @property
        def active_mode(self) -> str: ...

        @property
        def scene_code(self) -> int | None: ...

        @property
        def music_palette(self) -> tuple[tuple[int, int, int], ...] | None: ...

        @property
        def music_body(self) -> bytes | None: ...

        @property
        def scene_name_set(self) -> frozenset[str]: ...


def require_scene_command_identity(coordinator: _CoordinatorBase, scene: SceneEntry) -> None:
    fields = scene_command_identity_fields(coordinator.model, scene)
    if fields and not coordinator.identity_fields_confirmed(fields):
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="identity_not_ready")


async def async_prepare_effect_profile(
    coordinator: _CoordinatorBase, *, intent: ControlIntent, content: EffectContent | None = None
) -> ModelProfile:
    from .effect_domain import (
        BuiltinScene,
        LayeredEffect,
        LayeredScene,
        PaletteScene,
        RetainedSceneEffect,
        StaticRgbComposition,
    )

    scene = None
    scene_required = content is None or isinstance(content, LayeredEffect | RetainedSceneEffect)
    if isinstance(content, BuiltinScene | LayeredScene | PaletteScene):
        if resolved := resolve_scene_target(coordinator.model, content.template):
            _, scene = resolved
        scene_required = scene is not None and (
            scene.command_version != 0 or (scene.scene_type == 2 and coordinator.profile.rgbic_scene_v0 is not None)
        )

    if (
        content is not None
        and coordinator.profile.supports_rgb
        and not coordinator._authorization_profile().basic_controls_only
        and not scene_required
        and not isinstance(content, StaticRgbComposition)
    ):
        return coordinator.effect_authorization_profile
    fields = coordinator.profile.profile_identity_fields
    if scene_required:
        fields |= coordinator.profile.scene_identity_fields
    if fields and coordinator.identity_fields_confirmed(fields):
        return coordinator.effect_authorization_profile
    if (
        not (scene_required and coordinator.profile.scene_identity_fields)
        and coordinator.profile.rgbic_scene_v0 is None
        and (
            not coordinator.profile.profile_identity_fields
            or not coordinator._authorization_profile().basic_controls_only
        )
    ):
        return coordinator.effect_authorization_profile
    async with async_control_intent(coordinator, intent):
        async with coordinator._lock:
            client = await coordinator._ensure_connected()
            if coordinator._authorization_profile().basic_controls_only:
                await coordinator._async_require_identity(client, coordinator.profile.profile_identity_fields)
            if (
                scene_required
                and coordinator.profile.scene_identity_fields
                and not coordinator.identity_fields_confirmed(fields)
            ):
                token = coordinator._notification_token
                await coordinator._async_read_identity(fields)
                if (
                    coordinator._client is not client
                    or not client.is_connected
                    or coordinator._notification_token is not token
                ):
                    raise HomeAssistantError(translation_domain=DOMAIN, translation_key="identity_not_ready")
        coordinator._reconcile_authorization()
        if not coordinator.profile.supports_rgb and not coordinator.identity_fields_confirmed(
            coordinator.profile.profile_identity_fields
        ):
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="identity_not_ready")
        if scene is not None and scene_required:
            require_scene_command_identity(coordinator, scene)
        return coordinator.effect_authorization_profile
