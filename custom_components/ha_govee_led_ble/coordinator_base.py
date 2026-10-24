"""Shared typed base for the coordinator and its write mixins."""

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING, Any

from bleak import BleakClient
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import ModelProfile
from .control_arbiter import BLEControlArbiter, ControlIntent
from .coordinator_status import ParsedMode, StatusDomain

if TYPE_CHECKING:
    from .coordinator_modes import PreModeSnapshot
    from .generated_protocol_adapter import BulkStatusCollector
    from .govee_encryption.session import GoveeEncryptionSession
    from .native_profile_controls import ProfileWriter


class _CoordinatorBase(DataUpdateCoordinator[dict[str, Any]]):
    """Optimistic-state attributes and behaviour the write mixins rely on.

    Declares the fields and methods that ``GoveeBLECoordinator`` populates so the timer
    mixin type-checks without importing the concrete coordinator. No ``__init__`` here.
    """

    brightness_pct: int
    profile: ModelProfile
    address: str
    model: str
    effect_families: frozenset[str]
    effect_categories: frozenset[str]
    prefix_effect_names: bool
    always_include_custom_effects: bool
    is_on: bool
    effect: str | None
    fw_version: str | None
    hw_version: str | None
    rgb_color: tuple[int, int, int]
    color_temp_kelvin: int | None
    rgb_color_source: str
    color_temp_kelvin_source: str
    white_brightness: int
    music_mode: str
    video_mode: str
    music_sensitivity: int
    music_color: tuple[int, int, int] | None
    music_calm: bool
    diy_code: int | None
    color_mode: ParsedMode | None
    _control_lock: BLEControlArbiter
    _lock: asyncio.Lock
    segment_state_source: str
    pact_type: int | None
    pact_code: int | None
    _confirmed_identity_fields: set[str]
    control_write_attempts: int
    _static_write_attempts: int
    _profile_generation: int
    _pre_mode_snapshot: PreModeSnapshot
    segment_colors: list[tuple[int, int, int]]
    segment_brightness: list[int]
    boolean_control_state: dict[str, bool]
    _music_palette: tuple[str, tuple[tuple[int, int, int], ...]] | None
    _music_body: tuple[str, bytes] | None
    static_gradual: bool | None
    white_balance_scalar: int | None
    black_border: bool | None
    segment_state_observed_at: str | None
    _client: BleakClient | None
    _encryption: GoveeEncryptionSession | None
    _notification_token: object | None
    _last_rx_monotonic: float | None
    _expected_state: dict[str, tuple[Any, float]]
    _field_revisions: dict[str, int]
    _observed_physical_ic_count: int | None
    _bulk_collector: BulkStatusCollector | None
    _bulk_query_deadline: float | None
    _segment_query_generation: int | None
    _segment_query_colors: list[tuple[int, int, int]] | None
    _segment_query_brightness: list[int] | None
    _segment_groups_observed: set[int]
    _initialized_music_parameters: set[str]
    _blank_screen_notification_revision: int
    _dreamview_private_write: bool
    _upload_ack: tuple[BleakClient, object | None, int, int, int | None, int, asyncio.Future[bool]] | None
    _setting_ack: tuple[BleakClient, object | None, int, asyncio.Future[bool]] | None

    def install_static_color(
        self, *, rgb: tuple[int, int, int] | None = None, kelvin: int | None = None, source: str = "optimistic"
    ) -> None:
        """Install local/restore values without advancing BLE observation revisions."""
        if rgb is not None:
            self.rgb_color = rgb
            self.rgb_color_source = source
        elif self.rgb_color_source == "observed":
            self.rgb_color_source = "retained"
        self.color_temp_kelvin = kelvin
        self.color_temp_kelvin_source = source if kelvin is not None else "initial"

    if TYPE_CHECKING:

        def _renew_foreground_lease(self) -> None: ...

        async def _disconnect_locked(self, *, clear_cache: bool = False) -> None: ...

        def _authorization_profile(self) -> ModelProfile: ...

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

        def _mark_received(self, domain: StatusDomain, *fields: str) -> None: ...

        def _observe_identity_field(self, field: str, value: str | None) -> bool: ...

        def _handle_dreamview_notification(self, frame: bytes) -> bool: ...

        def _apply_segment_group(self, generated: Any) -> tuple[str, ...]: ...

        def _apply_configured_strings(self, count: int) -> None: ...

        async def _wait_for_revisions(
            self,
            field_baselines: Mapping[str, int],
            domain_baselines: Mapping[StatusDomain, int],
            deadline: float,
            *,
            expectations: Mapping[str, Any] | None = None,
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
        ) -> None: ...

        def async_mask_transaction(self) -> AbstractAsyncContextManager[None]: ...

        async def send_command(
            self,
            packet: bytes,
            *,
            write_guard: Callable[[], None] | None = None,
            state_values: Mapping[str, Any] | None = None,
        ) -> None: ...

        async def async_observe_effect(
            self, expectations: Mapping[str, Any], *, timeout: float = 4.0
        ) -> bool | None: ...

        async def async_write_music_sequence(
            self,
            writes: Sequence[tuple[bytes, Mapping[str, Any]]],
            *,
            mode_code: int,
            physical_ic_count: int | None,
            intent: ControlIntent,
            writer: ProfileWriter | None = None,
            retained_body_revision: int | None = None,
        ) -> None: ...

        async def async_set_boolean_control(self, control: str, enabled: bool) -> None: ...

        async def _ensure_connected(self) -> BleakClient: ...

        async def _async_read_bulk_status(
            self, client: BleakClient, *, deadline: float, domains: tuple[str, ...] | None = None
        ) -> bool: ...

        async def async_refresh_segments(self, *, timeout: float = 2.0) -> bool: ...

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
            require_upload_ack: bool = False,
            upload_ack_index: int | None = None,
            writer: ProfileWriter | None = None,
            packet_validator: Callable[[bytes, ModelProfile], None] = ...,
        ) -> None: ...

        async def refresh_state(self, **kwargs: Any) -> bool: ...

        @property
        def active_mode(self) -> str: ...

        @property
        def scene_name_set(self) -> frozenset[str]: ...
