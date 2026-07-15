"""Shared typed base for the coordinator and its write mixins."""

import asyncio
from datetime import time as dt_time
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import ModelProfile
from .custom_effects import CustomEffect
from .protocol import ParsedMode, ParsedTimerSchedule

if TYPE_CHECKING:
    from .coordinator_modes import PreModeSnapshot

# Domain byte of an `aa 41` power-off memory reply (mirrors protocol's 0x41 command).
POWEROFF_MEMORY_PACKET_TYPE = 0x41
# Domain bytes of experimental timer replies (mirror protocol's 0x11/0x12/0x23 commands).
SLEEP_TIMER_PACKET_TYPE = 0x11
WAKEUP_TIMER_PACKET_TYPE = 0x12
SCHEDULE_TIMER_PACKET_TYPE = 0x23
TIMER_SCHEDULE_SLOTS = 4
WAKEUP_END_BRIGHTNESS = 100


class _CoordinatorBase(DataUpdateCoordinator[dict[str, Any]]):
    """Optimistic-state attributes and behaviour the write mixins rely on.

    Declares the fields and methods that ``GoveeBLECoordinator`` populates so the timer
    mixin type-checks without importing the concrete coordinator. No ``__init__`` here.
    """

    brightness_pct: int
    profile: ModelProfile
    address: str
    model: str
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
    music_separation_point: int
    music_separation_gradient: bool
    music_hopping_brightness: int
    music_piano_key_count: int
    music_fountain_direction: str
    music_daynight_segments: int
    music_daynight_speed: int
    active_custom_id: str | None
    diy_slot: int | None
    color_mode: ParsedMode | None
    _owned_diy_effect_id: str | None
    _pre_mode_snapshot: PreModeSnapshot
    custom_effects: dict[str, CustomEffect]
    segment_colors: list[tuple[int, int, int]]
    _store_lock: asyncio.Lock
    _effect_store: Store[dict[str, Any]] | None
    sleep_timer_enabled: bool | None
    sleep_timer_minutes: int | None
    wakeup_timer_enabled: bool | None
    wakeup_timer_time: dt_time | None
    schedule_timers: list[ParsedTimerSchedule | None]

    if TYPE_CHECKING:

        async def send_command(self, packet: bytes) -> None: ...

        @property
        def scene_name_set(self) -> frozenset[str]: ...
