"""Shared typed base for the coordinator and its write mixins."""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import ModelProfile
from .control_arbiter import BLEControlArbiter, ControlIntent
from .coordinator_status import ParsedMode

if TYPE_CHECKING:
    from bleak import BleakClient

    from .coordinator_modes import PreModeSnapshot


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
    # Video-surface state.  Declared here so the display mixin can see it, the same way
    # the mode state above is declared for the mode mixin.
    video_full_screen: bool
    video_saturation: int
    video_sound_effects: bool
    video_sound_effects_softness: int
    video_picture_preset: str | None
    video_reserved: int
    video_settings: dict[int, list[int]]
    camera_installed: bool | None
    _dreamview_frames: dict[int, bytes]

    # Supplied by the concrete coordinator.  Declared here so a write mixin can reach the
    # connection and the transmit path without importing the coordinator and creating a cycle.
    _client: BleakClient | None

    if TYPE_CHECKING:

        def _record_packet(
            self,
            direction: str,
            data: bytes,
            *,
            outcome: str,
            reason: str,
            parser: str | None = ...,
            domain: int | None = ...,
        ) -> dict[str, Any]: ...

        async def _async_write_packet(self, client: BleakClient, packet: bytes) -> None: ...

    _control_lock: BLEControlArbiter
    _pre_mode_snapshot: PreModeSnapshot
    segment_colors: list[tuple[int, int, int]]

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

        async def send_command(self, packet: bytes) -> None: ...

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
            progress: Callable[[int], Awaitable[None]] | None = None,
        ) -> None: ...

        async def refresh_state(
            self,
            *,
            expected_effect: str | None = None,
            expected_scene_code: int | None = None,
            expected_on: bool | None = None,
        ) -> bool: ...

        @property
        def scene_name_set(self) -> frozenset[str]: ...
