"""Shared typed base for the coordinator and its write mixins."""

from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import ModelProfile
from .control_arbiter import BLEControlArbiter, ControlIntent
from .coordinator_status import ParsedMode

if TYPE_CHECKING:
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
    white_brightness: int
    music_mode: str
    video_mode: str
    music_sensitivity: int
    music_color: tuple[int, int, int] | None
    music_calm: bool
    diy_code: int | None
    color_mode: ParsedMode | None
    _control_lock: BLEControlArbiter
    _pre_mode_snapshot: PreModeSnapshot
    segment_colors: list[tuple[int, int, int]]

    if TYPE_CHECKING:

        async def send_command(self, packet: bytes) -> None: ...

        async def async_write_effect_sequence(
            self,
            packets: Sequence[bytes],
            *,
            intent: ControlIntent,
            before_write: Callable[[], Awaitable[None]] | None = None,
            attempt_started: Callable[[int], Awaitable[None]] | None = None,
            progress: Callable[[int], Awaitable[None]] | None = None,
        ) -> None: ...

        async def refresh_state(
            self,
            *,
            expected_effect: str | None = None,
            expected_on: bool | None = None,
        ) -> bool: ...

        @property
        def scene_name_set(self) -> frozenset[str]: ...
