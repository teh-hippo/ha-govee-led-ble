"""DataUpdateCoordinator for HA Govee LED BLE."""

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from datetime import time as dt_time
from typing import Any

from bleak import BleakClient, BleakError  # type: ignore[attr-defined]
from bleak_retry_connector import establish_connection
from homeassistant.components import bluetooth
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import DOMAIN, get_profile
from .coordinator_base import (
    POWEROFF_MEMORY_PACKET_TYPE,
    SCHEDULE_TIMER_PACKET_TYPE,
    SLEEP_TIMER_PACKET_TYPE,
    WAKEUP_TIMER_PACKET_TYPE,
)
from .coordinator_base import TIMER_SCHEDULE_SLOTS as TIMER_SCHEDULE_SLOTS
from .coordinator_effects import EffectStore, _CustomEffectMixin
from .coordinator_modes import PreModeSnapshot, _ActiveModeMixin
from .coordinator_timers import _TimerWriteMixin
from .custom_effects import CustomEffect, SegmentContent, uses_diy_slot
from .protocol import (
    AUTHORED_DIY_SLOT,
    BLANK_SCREEN_QUERY,
    BRIGHTNESS_PACKET_TYPE,
    BRIGHTNESS_QUERY,
    COLOR_MODE_DIY,
    COLOR_MODE_MUSIC,
    COLOR_MODE_QUERY,
    COLOR_MODE_SCENE,
    COLOR_MODE_STATIC,
    COLOR_MODE_VIDEO,
    COLOR_PACKET_TYPE,
    COMMAND_HEADER,
    DISPLAY_SETTING_PACKET_TYPE,
    FIRMWARE_PACKET_TYPE,
    FW_QUERY,
    HARDWARE_PACKET_TYPE,
    HW_QUERY,
    KEEP_ALIVE,
    MUSIC_SLUG_BY_ID,
    POWER_PACKET_TYPE,
    READ_UUID,
    RELATIVE_BRIGHTNESS_PACKET_TYPE,
    RELATIVE_BRIGHTNESS_QUERY,
    SCENE_EFFECT_BY_ID,
    SCHEDULE_TIMER_QUERY,
    SLEEP_TIMER_QUERY,
    WAKEUP_TIMER_QUERY,
    WHITE_BALANCE_QUERY,
    WHITE_BALANCE_RESET,
    WRITE_UUID,
    ParsedMode,
    ParsedTimerSchedule,
    SegmentColorGroup,
    build_segment_paint,
    decode_status_frame,
    kelvin_to_rgb,
    parse_color_mode_response,
    parse_display_setting_response,
    parse_fw_version,
    parse_hw_version,
    parse_poweroff_memory,
    parse_relative_brightness_response,
    parse_static_write,
    parse_timer_schedule_table,
    parse_timer_sleep,
    parse_timer_wakeup,
)

_LOGGER = logging.getLogger(__name__)

DISCONNECT_DELAY = 120
KEEP_ALIVE_INTERVAL = 5
STATE_QUERY_EVERY_N_KEEP_ALIVES = 3
RX_STALE_TIMEOUT = KEEP_ALIVE_INTERVAL * 4
IDENTITY_RETRY_TICKS = 6
RETRY_BACKOFF_SECONDS = 2
DEVICE_DISCOVERY_ATTEMPTS = 4
PACKET_LOG_LIMIT = 50
EXPECTED_STATE_TTL = 2.0

_CORE_STATE_FIELDS = (
    "is_on",
    "brightness_pct",
    "rgb_color",
    "color_temp_kelvin",
    "effect",
    "diy_slot",
)
_COLOR_MODE_FIELDS = (
    "video_full_screen",
    "video_saturation",
    "video_sound_effects",
    "video_sound_effects_softness",
    "music_sensitivity",
    "music_calm",
    "music_color",
    "white_brightness",
)
_COLOR_EXPECTATION_FIELDS = frozenset(
    ("color_mode", "effect", "rgb_color", "color_temp_kelvin", "music_mode", "video_mode", *_COLOR_MODE_FIELDS)
)


def _expectations_from_packet(packet: bytes, *, static_echoes_color: bool = False) -> dict[str, Any]:
    """Map an outgoing command to the optimistic fields its replies should confirm."""
    if len(packet) < 3 or packet[0] != COMMAND_HEADER:
        return {}
    if packet[1] == POWER_PACKET_TYPE:
        return {"is_on": bool(packet[2])}
    if packet[1] == BRIGHTNESS_PACKET_TYPE:
        return {"brightness_pct": packet[2]}
    if packet[1] != COLOR_PACKET_TYPE or len(packet) < 4:
        return {}
    expectations: dict[str, Any] = {}
    if color_mode := _expected_color_mode_from_packet(packet, static_echoes_color=static_echoes_color):
        expectations["color_mode"] = color_mode
    if packet[2] == COLOR_MODE_MUSIC:
        music_mode = MUSIC_SLUG_BY_ID.get(packet[3])
        expectations["music_mode"] = music_mode
        expectations["music_sensitivity"] = packet[4]
        if music_mode == "rhythm":
            expectations["music_calm"] = bool(packet[5])
        expectations["music_color"] = tuple(packet[7:10]) if packet[6] == 0x01 else None
        return expectations
    if packet[2] == COLOR_MODE_VIDEO and len(packet) >= 8:
        expectations.update(
            {
                "video_mode": "game" if packet[4] else "movie",
                "video_full_screen": bool(packet[3]),
                "video_saturation": packet[5],
                "video_sound_effects": bool(packet[6]),
                "video_sound_effects_softness": packet[7],
            }
        )
        return expectations
    if packet[2] == COLOR_MODE_SCENE and len(packet) >= 5:
        expectations["effect"] = SCENE_EFFECT_BY_ID.get(int.from_bytes(packet[3:5], "little"))
        return expectations
    if (static := parse_static_write(packet)) and static.whole_strip:
        if static.rgb is not None:
            expectations["rgb_color"] = static.rgb
        elif static.kelvin is not None:
            expectations["color_temp_kelvin"] = static.kelvin
        elif static.brightness_pct is not None:
            expectations["white_brightness"] = static.brightness_pct
    return expectations


def _expected_color_mode_from_packet(
    packet: bytes, *, static_echoes_color: bool = False
) -> tuple[ParsedMode, int | None] | None:
    if len(packet) < 4 or packet[0] != COMMAND_HEADER or packet[1] != COLOR_PACKET_TYPE:
        return None
    match packet[2]:
        case value if value == COLOR_MODE_DIY:
            return ParsedMode.DIY, packet[3]
        case value if value == COLOR_MODE_MUSIC:
            return ParsedMode.MUSIC, None
        case value if value == COLOR_MODE_VIDEO:
            return ParsedMode.VIDEO, None
        case value if value == COLOR_MODE_STATIC:
            # The write-side sub only survives into the reply on models that echo it; elsewhere
            # the same byte carries the 33 a3 register, so expecting it here never matches.
            return ParsedMode.COLOUR, (packet[3] if static_echoes_color else None)
        case value if value == COLOR_MODE_SCENE:
            return ParsedMode.SCENE, None
        case _:
            return None


class GoveeBLECoordinator(_TimerWriteMixin, _ActiveModeMixin, _CustomEffectMixin):
    """Manages BLE connection lifecycle for a Govee device."""

    def __init__(self, hass: HomeAssistant, address: str, model: str) -> None:
        profile = get_profile(model)
        super().__init__(
            hass,
            _LOGGER,
            name=f"Govee {model} ({address})",
            update_interval=timedelta(seconds=30) if profile.state_readable else None,
        )
        self.address, self.model, self.profile = address, model, profile
        self._client: BleakClient | None = None
        self._lock = asyncio.Lock()
        self._control_lock = asyncio.Lock()
        self._cancel_disconnect: CALLBACK_TYPE | None = None
        self._keep_alive_task: asyncio.Task[None] | None = None
        self._keep_alive_ticks = 0
        self._identity_retries = 0
        self.is_on = False
        self.brightness_pct = 100
        self.rgb_color: tuple[int, int, int] = (255, 255, 255)
        self.color_temp_kelvin: int | None = None
        self.effect: str | None = None
        # Device identity from the aa 06/aa 07 handshake replies; None until first read.
        self.fw_version: str | None = None
        self.hw_version: str | None = None
        self.music_mode = "off"
        self.video_mode = "off"
        self.active_custom_id: str | None = None
        self.diy_slot: int | None = None
        self.color_mode: ParsedMode | None = None
        self._scene_code: int | None = None
        self.scene_speed_scene_code: int | None = None
        self.scene_speed_index: int | None = None
        self._owned_diy_effect_id: str | None = None
        self._pre_mode_snapshot = PreModeSnapshot(kind="rgb", rgb=(255, 255, 255))
        self.custom_effects: dict[str, CustomEffect] = {}
        self._store_lock = asyncio.Lock()
        self._effect_store: EffectStore | None = None
        self.segment_colors: list[tuple[int, int, int]] = [self.rgb_color] * profile.segment_count
        self.video_saturation = self.white_brightness = 100
        self.music_sensitivity = 99
        self.music_calm = False
        self.video_full_screen, self.video_sound_effects = True, False
        self.video_sound_effects_softness = 100
        self.music_color: tuple[int, int, int] | None = None
        # H6199 display settings and edge brightness. None means the first read has not landed.
        self.white_balance_red: int | None = None
        self.white_balance_blue: int | None = None
        self.relative_brightness: int | None = None
        self.relative_brightness_left: int | None = None
        self.relative_brightness_top: int | None = None
        self.relative_brightness_right: int | None = None
        self.relative_brightness_bottom: int | None = None
        self.blank_screen: bool | None = None
        # Per-mode music movement defaults reproduce the captured music_body.ksy templates.
        self.music_separation_point = 1
        self.music_separation_gradient = True
        self.music_hopping_brightness = 50
        self.music_piano_key_count = 15
        self.music_fountain_direction = "clockwise"
        self.music_daynight_segments = 1
        self.music_daynight_speed = 10
        # Power-off memory (restore last state after power loss); None until a reply is seen.
        self.poweroff_memory: bool | None = None
        # Timer state is unknown until the device replies.
        self.sleep_timer_enabled: bool | None = None
        self.sleep_timer_start_brightness: int | None = None
        self.sleep_timer_minutes: int | None = None
        self.sleep_timer_current_minutes: int | None = None
        self.wakeup_timer_enabled: bool | None = None
        self.wakeup_timer_end_brightness: int | None = None
        self.wakeup_timer_time: dt_time | None = None
        self.wakeup_timer_repeat_days: frozenset[Any] | None = None
        self.wakeup_timer_duration_minutes: int | None = None
        self.schedule_timers: list[ParsedTimerSchedule | None] = [None] * TIMER_SCHEDULE_SLOTS
        self.packet_log: list[dict[str, Any]] = []
        self._expected_state: dict[str, tuple[Any, float]] = {}
        self._notify_started_monotonic: float | None = None
        self._last_rx_monotonic: float | None = None
        self._domain_revisions: dict[int, int] = {}
        self._field_revisions: dict[str, int] = {}
        # BLE presence (advertisement-driven) and first-refresh gate for ConfigEntryNotReady.
        self._present = False
        self._first_refresh_done = False
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._handle_hass_stop)

    @property
    def device_info(self) -> dr.DeviceInfo:
        # No `connections`: the BLE MAC is PII and must not surface in the device UI (OD1).
        return dr.DeviceInfo(
            identifiers={(DOMAIN, self.address)},
            name=f"Govee {self.model}",
            manufacturer="Govee",
            model=self.model,
            sw_version=self.fw_version,
            hw_version=self.hw_version,
        )

    @callback
    def _note_identity(self, *, fw_version: str | None = None, hw_version: str | None = None) -> None:
        # Entities snapshot device_info at construction, before the first identity reply lands,
        # so a newly learned version must be pushed to the registry or the device page stays blank (#97).
        changed = False
        if fw_version is not None and fw_version != self.fw_version:
            self.fw_version, changed = fw_version, True
        if hw_version is not None and hw_version != self.hw_version:
            self.hw_version, changed = hw_version, True
        if not changed:
            return
        registry = dr.async_get(self.hass)
        device = registry.async_get_device(identifiers={(DOMAIN, self.address)})
        if device is not None:
            registry.async_update_device(device.id, sw_version=self.fw_version, hw_version=self.hw_version)

    @property
    def white_balance(self) -> tuple[int, int]:
        """The gain pair to write, filling an unknown axis with the app's own neutral.

        Both bytes go out together. The H6199 read-back populates both during startup; neutral is
        retained only for the pre-read window and for models on firmware that does not answer it.
        """
        reset_red, reset_blue = WHITE_BALANCE_RESET
        return (
            reset_red if self.white_balance_red is None else self.white_balance_red,
            reset_blue if self.white_balance_blue is None else self.white_balance_blue,
        )

    @property
    def unknown_scene_code(self) -> int | None:
        """The raw scene id when the device is running a scene this build cannot name.

        ``effect`` stays None for these, because Home Assistant rejects a value outside
        ``effect_list`` and we could not re-activate the scene anyway. Reporting the id keeps
        the state honest about the light running something.
        """
        if self.color_mode is ParsedMode.SCENE and self.effect is None:
            return self._scene_code
        return None

    @property
    def available(self) -> bool:
        """Whether the device is reachable: a live BLE link or a recent advertisement."""
        if self._client is not None and self._client.is_connected:
            return True
        return self._present

    async def _async_setup(self) -> None:
        """Register BLE presence tracking once, before the first refresh (HA idiom)."""
        self._present = bluetooth.async_address_present(self.hass, self.address, connectable=True)
        unsubs = (
            bluetooth.async_register_callback(
                self.hass,
                self._async_on_advertisement,
                bluetooth.BluetoothCallbackMatcher(address=self.address, connectable=True),
                bluetooth.BluetoothScanningMode.PASSIVE,
            ),
            bluetooth.async_track_unavailable(self.hass, self._async_on_unavailable, self.address, connectable=True),
        )
        for unsub in unsubs:
            if self.config_entry is not None:
                self.config_entry.async_on_unload(unsub)

    @callback
    def _async_on_advertisement(
        self, _service_info: bluetooth.BluetoothServiceInfoBleak, _change: bluetooth.BluetoothChange
    ) -> None:
        self._set_present(True)

    @callback
    def _async_on_unavailable(self, _service_info: bluetooth.BluetoothServiceInfoBleak) -> None:
        self._set_present(False)

    @callback
    def _set_present(self, present: bool) -> None:
        if self._present != present:
            self._present = present
            self.async_update_listeners()

    @callback
    def _handle_hass_stop(self, _event: Event) -> None:
        self._stop_keep_alive()
        if self._cancel_disconnect:
            self._cancel_disconnect()
            self._cancel_disconnect = None

    async def _async_update_data(self) -> dict[str, Any]:
        first_refresh = not self._first_refresh_done
        self._first_refresh_done = True
        if self.hass.is_stopping:
            return self._state_snapshot()
        if self.profile.state_readable:
            try:
                async with self._lock:
                    await self._ensure_connected()
                    await self._send_state_queries()
            except BleakError as err:
                # ConfigEntryNotReady on first setup only; steady-state refreshes degrade silently
                # and presence-driven availability tracks the running state.
                if first_refresh:
                    raise UpdateFailed(f"{self.address} unreachable at setup") from err
                _LOGGER.debug("State refresh skipped for %s", self.address)
        elif first_refresh and not self._present:
            raise UpdateFailed(f"{self.address} not advertising at setup")
        return self._state_snapshot()

    def _state_snapshot(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in _CORE_STATE_FIELDS}

    async def _ensure_connected(self) -> BleakClient:
        if self._client and self._client.is_connected:
            if not self._receive_is_stale():
                self._reset_disconnect_timer()
                return self._client
            _LOGGER.debug("Reconnecting stale notification stream for %s", self.address)
            await self.disconnect()
        ble_device = None
        for attempt in range(DEVICE_DISCOVERY_ATTEMPTS):
            ble_device = bluetooth.async_ble_device_from_address(self.hass, self.address, connectable=True)
            if ble_device is not None:
                break
            if attempt < DEVICE_DISCOVERY_ATTEMPTS - 1:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS)
        if not ble_device:
            raise BleakError(f"Device {self.address} not found")
        self._client = await establish_connection(BleakClient, ble_device, self.address)
        self._reset_disconnect_timer()
        if self.profile.state_readable:
            try:
                await self._start_notify()
                await self._send_identity_queries()
                if not await self._send_state_queries():
                    raise BleakError(f"Initial state query failed for {self.address}")
            except BleakError:
                await self.disconnect()
                raise
        return self._client

    def _reset_disconnect_timer(self) -> None:
        if self._cancel_disconnect:
            self._cancel_disconnect()

        @callback
        def _on_timeout(_now: datetime) -> None:
            self.hass.async_create_task(self.disconnect())

        self._cancel_disconnect = async_call_later(self.hass, DISCONNECT_DELAY, _on_timeout)

    async def _start_notify(self) -> None:
        if not (self._client and self._client.is_connected):
            return
        await self._client.start_notify(READ_UUID, self._notify_callback)
        self._notify_started_monotonic = time.monotonic()
        self._last_rx_monotonic = None
        self._start_keep_alive()

    def _receive_is_stale(self) -> bool:
        baseline = self._last_rx_monotonic
        if baseline is None:
            baseline = self._notify_started_monotonic
        return baseline is not None and time.monotonic() - baseline >= RX_STALE_TIMEOUT

    def _mark_received(self, domain: int, *fields: str) -> None:
        self._domain_revisions[domain] = self._domain_revisions.get(domain, 0) + 1
        for field in fields:
            self._field_revisions[field] = self._field_revisions.get(field, 0) + 1

    def _arm_expected(self, packet: bytes) -> None:
        expectations = _expectations_from_packet(packet, static_echoes_color=self.profile.static_readback_echoes_color)
        if "color_mode" in expectations:
            for field in _COLOR_EXPECTATION_FIELDS:
                self._expected_state.pop(field, None)
        self._arm_expected_values(expectations)

    def _arm_expected_values(self, expectations: dict[str, Any]) -> None:
        """Protect optimistic fields from reordered replies until their verification window ends."""
        deadline = time.monotonic() + EXPECTED_STATE_TTL
        for field, value in expectations.items():
            self._expected_state[field] = (value, deadline)

    def _clear_expected_fields(self, *fields: str) -> None:
        for field in fields:
            self._expected_state.pop(field, None)

    def _accept_expected_values(self, values: dict[str, Any]) -> bool:
        """Accept a composite reply atomically; one stale sibling rejects the whole group."""
        return all(self._accept_expected(field, value) for field, value in values.items())

    def _accept_expected(self, field: str, value: Any) -> bool:
        """Consult the optimistic window for `field`.

        Returns True when the reply agrees or the deadline has passed; returns False to
        drop a stale reply that still disagrees in-window. Matching expectations remain
        authoritative until the deadline so a later reordered reply cannot overwrite them.
        """
        expectation = self._expected_state.get(field)
        if expectation is None:
            return True
        expected, deadline = expectation
        if time.monotonic() >= deadline:
            del self._expected_state[field]
            return True
        if value == expected:
            return True
        _LOGGER.debug("Ignoring stale %s for %s: %r (expecting %r)", field, self.address, value, expected)
        return False

    def _apply_color_mode_payload(self, payload: bytes) -> tuple[str, ...]:
        static_echoes_color = self.profile.static_readback_echoes_color
        parsed = parse_color_mode_response(
            payload, static_echoes_color=static_echoes_color, video_supported=self.profile.supports_video_mode
        )
        if parsed.mode is ParsedMode.DIY:
            mode_detail = parsed.diy_slot
        elif parsed.mode is ParsedMode.COLOUR and static_echoes_color:
            mode_detail = payload[1]
        else:
            mode_detail = None
        observed_color_mode = parsed.mode, mode_detail
        if not self._accept_expected("color_mode", observed_color_mode):
            return ()
        self.color_mode = parsed.mode
        # The parser names a scene code from one shared catalogue, which is an H617A numbering.
        # It agrees with H6199 wire for the three codes a capture confirmed and diverges after
        # that (Forest is 2163 there and 212 here), so a name is only trusted for a model that
        # owns it. Otherwise this would put a name outside effect_list into state, and assert a
        # scene the light is not running.
        scene_effect = parsed.effect if parsed.effect in self.scene_name_set else None
        # A scene we cannot name still leaves the light running something, and effect has to stay
        # None because HA rejects one outside effect_list. Keep the raw id so the state is honest
        # rather than silently claiming nothing is on. None for every other mode, so this one
        # assignment cannot leave a stale code behind.
        self._scene_code = parsed.scene_code if scene_effect is None else None
        observed: list[str] = []
        accept_parameters = True
        active_custom = self.custom_effects.get(self.active_custom_id) if self.active_custom_id is not None else None
        # Readback mirror of _enter_static_mode: committing one mode clears the others so exactly one
        # is ever truthful. Static segment effects and slot-backed DIY effects retain only matching metadata.
        if parsed.mode is ParsedMode.MUSIC:
            if parsed.music_mode is not None and self._accept_expected("music_mode", parsed.music_mode):
                self.music_mode = parsed.music_mode
                self.video_mode, self.effect, self.active_custom_id = "off", None, None
                self.diy_slot = None
                self._owned_diy_effect_id = None
                observed.append("music_mode")
            else:
                accept_parameters = False
        elif parsed.mode is ParsedMode.VIDEO:
            if parsed.video_mode is not None and self._accept_expected("video_mode", parsed.video_mode):
                self.video_mode = parsed.video_mode
                self.music_mode, self.effect, self.active_custom_id = "off", None, None
                self.diy_slot = None
                self._owned_diy_effect_id = None
                observed.append("video_mode")
            else:
                accept_parameters = False
        elif parsed.mode is ParsedMode.DIY:
            known_custom = (
                parsed.diy_slot == AUTHORED_DIY_SLOT
                and active_custom is not None
                and self._owned_diy_effect_id == active_custom.id
                and uses_diy_slot(active_custom.content)
            )
            readback_effect = self.effect if known_custom else None
            if self._accept_expected("effect", readback_effect):
                self.effect = readback_effect
                self.music_mode = self.video_mode = "off"
                self.diy_slot = parsed.diy_slot
                if not known_custom:
                    self.active_custom_id = None
                    self._owned_diy_effect_id = None
                observed.append("effect")
            else:
                accept_parameters = False
        elif parsed.mode is ParsedMode.SCENE:
            if self._accept_expected("effect", scene_effect):
                self.effect = scene_effect
                self.music_mode, self.video_mode, self.active_custom_id = "off", "off", None
                self.diy_slot = None
                self._owned_diy_effect_id = None
                self._sync_scene_speed(scene_effect)
                observed.append("effect")
        elif parsed.mode is ParsedMode.COLOUR:
            known_custom = active_custom is not None and isinstance(active_custom.content, SegmentContent)
            readback_effect = self.effect if known_custom else None
            if self._accept_expected("effect", readback_effect):
                self.effect, self.music_mode, self.video_mode = readback_effect, "off", "off"
                self.diy_slot = None
                if not known_custom:
                    self.active_custom_id = None
                self._owned_diy_effect_id = None
                observed.append("effect")
        else:
            self.effect = self.active_custom_id = None
            self.diy_slot = None
            self._owned_diy_effect_id = None
            self.music_mode = self.video_mode = "off"
            observed.append("effect")
        if accept_parameters:
            if parsed.mode is ParsedMode.MUSIC and len(payload) > 4 and payload[4] == 0:
                if self._accept_expected("music_color", None):
                    self.music_color = None
                    observed.append("music_color")
            for attr in _COLOR_MODE_FIELDS:
                if (value := getattr(parsed, attr)) is not None:
                    if self._accept_expected(attr, value):
                        setattr(self, attr, value)
                        observed.append(attr)
        if parsed.rgb_color is not None:
            # A colour-temp state reads back as its white-point RGB with no kelvin field; recognising it
            # keeps the light in CT mode instead of clobbering kelvin and dropping to a near-white RGB.
            if self.color_temp_kelvin is not None and parsed.rgb_color == kelvin_to_rgb(self.color_temp_kelvin):
                return tuple(observed)
            accept_rgb = self._accept_expected("rgb_color", parsed.rgb_color)
            accept_kelvin = self._accept_expected("color_temp_kelvin", None)
            if accept_rgb and accept_kelvin:
                self.rgb_color, self.color_temp_kelvin = parsed.rgb_color, None
        return tuple(observed)

    def _apply_sleep_timer_payload(self, payload: bytes) -> tuple[str, ...]:
        parsed = parse_timer_sleep(payload)
        self.sleep_timer_enabled = parsed.enabled
        self.sleep_timer_start_brightness = parsed.start_brightness
        self.sleep_timer_minutes = parsed.close_minutes
        self.sleep_timer_current_minutes = parsed.current_minutes
        return (
            "sleep_timer_enabled",
            "sleep_timer_start_brightness",
            "sleep_timer_minutes",
            "sleep_timer_current_minutes",
        )

    def _apply_wakeup_timer_payload(self, payload: bytes) -> tuple[str, ...]:
        parsed = parse_timer_wakeup(payload)
        self.wakeup_timer_enabled = parsed.enabled
        self.wakeup_timer_end_brightness = parsed.end_brightness
        self.wakeup_timer_time = dt_time(parsed.hour, parsed.minute)
        self.wakeup_timer_repeat_days = parsed.repeat_days
        self.wakeup_timer_duration_minutes = parsed.duration_minutes
        return (
            "wakeup_timer_enabled",
            "wakeup_timer_end_brightness",
            "wakeup_timer_time",
            "wakeup_timer_repeat_days",
            "wakeup_timer_duration_minutes",
        )

    def _apply_schedule_timer_payload(self, payload: bytes) -> tuple[str, ...]:
        # The aa 23 reply is the full table: 0xff prefix + four 4-byte slot records.
        if len(payload) != 17 or payload[:1] != b"\xff":
            raise ValueError("Schedule timer reply must contain the complete four-slot table")
        for slot, parsed in enumerate(parse_timer_schedule_table(payload)):
            if slot < TIMER_SCHEDULE_SLOTS:
                self.schedule_timers[slot] = parsed
        return ("schedule_timers",)

    def _notify_callback(self, _sender: Any, data: bytearray) -> None:
        frame = bytes(data)
        decoded = decode_status_frame(frame, self.model)
        if decoded is None:
            return
        domain, payload = decoded.domain, decoded.payload
        generated = decoded.generated
        self._record_packet("rx", frame)
        self._last_rx_monotonic = time.monotonic()
        _LOGGER.debug("rx %s domain=0x%02x payload=%s", self.address, domain, payload.hex())
        try:
            observed: tuple[str, ...] = ()
            if domain == POWER_PACKET_TYPE:
                value = bool(generated.body.is_on) if generated is not None else bool(payload[0])
                if self._accept_expected("is_on", value):
                    self.is_on = value
                    observed = ("is_on",)
            elif domain == BRIGHTNESS_PACKET_TYPE:
                brightness_value = (
                    int(generated.body.percent)
                    if generated is not None and self.model == "H6199"
                    else int(generated.body.brightness_pct)
                    if generated is not None
                    else payload[0]
                )
                if self._accept_expected("brightness_pct", brightness_value):
                    self.brightness_pct = brightness_value
                    observed = ("brightness_pct",)
            elif domain == COLOR_PACKET_TYPE:
                observed = self._apply_color_mode_payload(payload)
            elif domain == DISPLAY_SETTING_PACKET_TYPE:
                display_setting = parse_display_setting_response(payload)
                current_white_balance: tuple[int, int] | None
                if generated is not None and generated.body.setting == 0:
                    red = int(generated.body.payload.current_red)
                    blue = int(generated.body.payload.current_blue)
                    current_white_balance = (red, blue)
                else:
                    current_white_balance = display_setting.current_white_balance
                if current_white_balance is not None:
                    red, blue = current_white_balance
                    values = {"white_balance_red": red, "white_balance_blue": blue}
                    if self._accept_expected_values(values):
                        self.white_balance_red, self.white_balance_blue = red, blue
                        observed = tuple(values)
                else:
                    blank_screen = (
                        bool(generated.body.payload.is_enabled)
                        if generated is not None and generated.body.setting == 10
                        else display_setting.blank_screen
                    )
                    if blank_screen is not None and self._accept_expected(
                        "blank_screen",
                        blank_screen,
                    ):
                        self.blank_screen = blank_screen
                        observed = ("blank_screen",)
            elif domain == RELATIVE_BRIGHTNESS_PACKET_TYPE:
                if generated is not None:
                    edges = (
                        generated.body.left_percent,
                        generated.body.top_percent,
                        generated.body.right_percent,
                        generated.body.bottom_percent,
                    )
                else:
                    relative_brightness = parse_relative_brightness_response(payload)
                    edges = (
                        relative_brightness.left,
                        relative_brightness.top,
                        relative_brightness.right,
                        relative_brightness.bottom,
                    )
                aggregate = edges[0] if len(set(edges)) == 1 else None
                edge_values: dict[str, Any] = {
                    "relative_brightness": aggregate,
                    "relative_brightness_left": edges[0],
                    "relative_brightness_top": edges[1],
                    "relative_brightness_right": edges[2],
                    "relative_brightness_bottom": edges[3],
                }
                if self._accept_expected_values(edge_values):
                    self.relative_brightness = aggregate
                    (
                        self.relative_brightness_left,
                        self.relative_brightness_top,
                        self.relative_brightness_right,
                        self.relative_brightness_bottom,
                    ) = edges
                    observed = tuple(edge_values)
            elif domain == FIRMWARE_PACKET_TYPE:
                self._note_identity(
                    fw_version=(generated.body.text if generated is not None else parse_fw_version(payload))
                )
            elif domain == HARDWARE_PACKET_TYPE:
                self._note_identity(
                    hw_version=(generated.body.text if generated is not None else parse_hw_version(payload))
                )
            elif domain == POWEROFF_MEMORY_PACKET_TYPE:
                self.poweroff_memory = parse_poweroff_memory(payload).enabled
            elif domain == SLEEP_TIMER_PACKET_TYPE:
                observed = self._apply_sleep_timer_payload(payload)
            elif domain == WAKEUP_TIMER_PACKET_TYPE:
                observed = self._apply_wakeup_timer_payload(payload)
            elif domain == SCHEDULE_TIMER_PACKET_TYPE:
                observed = self._apply_schedule_timer_payload(payload)
            self._mark_received(domain, *observed)
            self.async_set_updated_data(self.data or {})
        except IndexError, ValueError:
            _LOGGER.debug("Failed to parse notify from %s: %s", self.address, data.hex())

    async def _send_state_queries(
        self,
        *,
        query_power: bool = True,
        query_brightness: bool = True,
        query_color_mode: bool = True,
        query_white_balance: bool | None = None,
        query_blank_screen: bool | None = None,
        query_relative_brightness: bool | None = None,
    ) -> bool:
        if not self._client or not self._client.is_connected:
            return False
        try:
            queries: list[bytes] = []
            if query_power:
                queries.append(KEEP_ALIVE)
            if query_brightness:
                queries.append(BRIGHTNESS_QUERY)
            if query_color_mode:
                queries.append(COLOR_MODE_QUERY)
            full_query = query_power and query_brightness and query_color_mode
            if self.profile.supports_white_balance and (
                query_white_balance if query_white_balance is not None else full_query
            ):
                queries.append(WHITE_BALANCE_QUERY)
            if self.profile.supports_blank_screen and (
                query_blank_screen if query_blank_screen is not None else full_query
            ):
                queries.append(BLANK_SCREEN_QUERY)
            if self.profile.supports_relative_brightness and (
                query_relative_brightness if query_relative_brightness is not None else full_query
            ):
                queries.append(RELATIVE_BRIGHTNESS_QUERY)
            if self.profile.supports_timers and full_query:
                queries.extend((SLEEP_TIMER_QUERY, WAKEUP_TIMER_QUERY, SCHEDULE_TIMER_QUERY))
            for query in queries:
                self._record_packet("tx", query)
                await self._client.write_gatt_char(WRITE_UUID, query, response=False)
            return True
        except BleakError:
            return False

    async def refresh_query_state(
        self,
        query: bytes,
        domain: int,
        accept: Callable[[], bool],
        timeout: float = 2.0,
    ) -> bool:
        """Query one register until a fresh reply satisfies ``accept``."""
        async with self._lock:
            client = await self._ensure_connected()
        baseline = self._domain_revisions.get(domain, 0)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                async with self._lock:
                    if self._client is not client:
                        return False
                    self._record_packet("tx", query)
                    await client.write_gatt_char(WRITE_UUID, query, response=False)
            except BleakError:
                await self._disconnect_if_current(client)
                return False
            if self._domain_revisions.get(domain, 0) > baseline and accept():
                return True
            if (remaining := deadline - time.monotonic()) > 0:
                await asyncio.sleep(min(0.25, remaining))
        if self._domain_revisions.get(domain, 0) <= baseline:
            await self._disconnect_if_current(client)
        return False

    async def _send_identity_queries(self) -> None:
        """Query firmware and hardware for DeviceInfo, sending only unknowns.

        Replies can be missed right after connect while notifications are starting, so the
        keep-alive loop retries unknown values up to ``IDENTITY_RETRY_TICKS``.
        """
        if not self._client or not self._client.is_connected:
            return
        candidates = [(HW_QUERY, self.hw_version), (FW_QUERY, self.fw_version)]
        queries = [q for q, value in candidates if value is None]
        try:
            for query in queries:
                self._record_packet("tx", query)
                await self._client.write_gatt_char(WRITE_UUID, query, response=False)
        except BleakError:
            _LOGGER.debug("Identity query failed for %s", self.address)

    async def refresh_state(
        self,
        *,
        expected_effect: str | None = None,
        expected_on: bool | None = None,
        expected_brightness: int | None = None,
        expected_music_mode: str | None = None,
        expected_music_sensitivity: int | None = None,
        expected_music_calm: bool | None = None,
        expected_music_color: tuple[int, int, int] | None = None,
        expected_music_auto_color: bool = False,
        expected_video_mode: str | None = None,
        expected_video_full_screen: bool | None = None,
        expected_video_saturation: int | None = None,
        expected_video_sound_effects: bool | None = None,
        expected_video_sound_effects_softness: int | None = None,
        expected_white_brightness: int | None = None,
        expected_white_balance: tuple[int, int] | None = None,
        expected_blank_screen: bool | None = None,
        expected_relative_brightness: tuple[int, int, int, int] | None = None,
        timeout: float = 2.0,
    ) -> bool:
        if not self.profile.state_readable:
            return False
        async with self._lock:
            client = await self._ensure_connected()
        expectations: dict[str, Any] = {
            field: value
            for field, value in (
                ("effect", expected_effect),
                ("is_on", expected_on),
                ("brightness_pct", expected_brightness),
                ("music_mode", expected_music_mode),
                ("music_sensitivity", expected_music_sensitivity),
                ("music_calm", expected_music_calm),
                ("music_color", expected_music_color),
                ("video_mode", expected_video_mode),
                ("video_full_screen", expected_video_full_screen),
                ("video_saturation", expected_video_saturation),
                ("video_sound_effects", expected_video_sound_effects),
                ("video_sound_effects_softness", expected_video_sound_effects_softness),
                ("white_brightness", expected_white_brightness),
            )
            if value is not None
        }
        if expected_music_auto_color:
            expectations["music_color"] = None
        if expected_white_balance is not None:
            expectations["white_balance_red"], expectations["white_balance_blue"] = expected_white_balance
        if expected_blank_screen is not None:
            expectations["blank_screen"] = expected_blank_screen
        if expected_relative_brightness is not None:
            left, top, right, bottom = expected_relative_brightness
            expectations.update(
                {
                    "relative_brightness": left if len(set(expected_relative_brightness)) == 1 else None,
                    "relative_brightness_left": left,
                    "relative_brightness_top": top,
                    "relative_brightness_right": right,
                    "relative_brightness_bottom": bottom,
                }
            )
        color_expectations = (
            expected_effect,
            expected_music_mode,
            expected_music_sensitivity,
            expected_music_calm,
            expected_music_color,
            expected_video_mode,
            expected_video_full_screen,
            expected_video_saturation,
            expected_video_sound_effects,
            expected_video_sound_effects_softness,
            expected_white_brightness,
        )
        field_baselines = {field: self._field_revisions.get(field, 0) for field in expectations}
        deadline = time.monotonic() + timeout
        query_power = expected_on is not None
        query_brightness = expected_brightness is not None
        query_color = expected_music_auto_color or any(value is not None for value in color_expectations)
        query_white_balance = expected_white_balance is not None
        query_blank_screen = expected_blank_screen is not None
        query_relative_brightness = expected_relative_brightness is not None
        if not any(
            (
                query_power,
                query_brightness,
                query_color,
                query_white_balance,
                query_blank_screen,
                query_relative_brightness,
            )
        ):
            query_power = query_color = True
        queried_domains = {
            domain
            for domain, enabled in (
                (POWER_PACKET_TYPE, query_power),
                (BRIGHTNESS_PACKET_TYPE, query_brightness),
                (COLOR_PACKET_TYPE, query_color),
                (DISPLAY_SETTING_PACKET_TYPE, query_white_balance or query_blank_screen),
                (RELATIVE_BRIGHTNESS_PACKET_TYPE, query_relative_brightness),
            )
            if enabled
        }
        domain_baselines = {domain: self._domain_revisions.get(domain, 0) for domain in queried_domains}
        while time.monotonic() < deadline:
            async with self._lock:
                if self._client is not client:
                    return False
                if query_white_balance or query_blank_screen or query_relative_brightness:
                    ok = await self._send_state_queries(
                        query_power=query_power,
                        query_brightness=query_brightness,
                        query_color_mode=query_color,
                        query_white_balance=query_white_balance,
                        query_blank_screen=query_blank_screen,
                        query_relative_brightness=query_relative_brightness,
                    )
                else:
                    ok = await self._send_state_queries(
                        query_power=query_power,
                        query_brightness=query_brightness,
                        query_color_mode=query_color,
                    )
            if not ok:
                await self._disconnect_if_current(client)
                return False
            if expectations and all(
                self._field_revisions.get(field, 0) > field_baselines[field] and getattr(self, field) == expected
                for field, expected in expectations.items()
            ):
                return True
            if not expectations and all(
                self._domain_revisions.get(domain, 0) > domain_baselines[domain] for domain in queried_domains
            ):
                return True
            if (remaining := deadline - time.monotonic()) > 0:
                await asyncio.sleep(min(0.25, remaining))
        if any(self._domain_revisions.get(domain, 0) <= baseline for domain, baseline in domain_baselines.items()):
            await self._disconnect_if_current(client)
        return False

    def _start_keep_alive(self) -> None:
        self._stop_keep_alive()
        self._identity_retries = 0
        self._keep_alive_task = self.hass.async_create_background_task(
            self._keep_alive_loop(), name=f"{DOMAIN} keep-alive {self.address}"
        )

    def _stop_keep_alive(self) -> None:
        if self._keep_alive_task and not self._keep_alive_task.done():
            self._keep_alive_task.cancel()
            self._keep_alive_task = None

    async def _keep_alive_loop(self) -> None:
        try:
            while self._client and self._client.is_connected:
                await asyncio.sleep(KEEP_ALIVE_INTERVAL)
                if not (self._client and self._client.is_connected):
                    break
                if self._receive_is_stale():
                    _LOGGER.debug("Disconnecting unresponsive notification stream for %s", self.address)
                    client = self._client
                    self.hass.async_create_task(self._disconnect_if_current(client))
                    break
                self._keep_alive_ticks += 1
                if (self.fw_version is None or self.hw_version is None) and (
                    self._identity_retries < IDENTITY_RETRY_TICKS
                ):
                    self._identity_retries += 1
                    async with self._lock:
                        await self._send_identity_queries()
                full = self._keep_alive_ticks % STATE_QUERY_EVERY_N_KEEP_ALIVES == 0
                async with self._lock:
                    ok = await self._send_state_queries(query_power=True, query_brightness=full, query_color_mode=full)
                if not ok:
                    break
        except asyncio.CancelledError:
            pass

    async def _disconnect_if_current(self, client: BleakClient) -> None:
        if self._client is client:
            await self.disconnect()

    async def send_command(self, packet: bytes) -> None:
        if self.hass.is_stopping:
            _LOGGER.debug("Ignoring command during shutdown for %s", self.address)
            return
        async with self._lock:
            for attempt in range(3):
                try:
                    client = await self._ensure_connected()
                    self._record_packet("tx", packet)
                    self._arm_expected(packet)
                    await client.write_gatt_char(WRITE_UUID, packet, response=False)
                    return
                except BleakError as err:
                    await self.disconnect()
                    if attempt == 2:
                        _LOGGER.error("Failed to send to %s after 3 attempts", self.address)
                        raise
                    s = str(err).lower()
                    if "already shutdown" in s or "not found" in s:
                        await asyncio.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))

    async def async_paint_segments(self, groups: list[SegmentColorGroup]) -> None:
        """Optimistically paint colour groups onto the segment slots.

        Each group pairs 1-based segment indices with an RGB colour; groups are encoded
        by ``build_segment_paint`` (one packet per colour) and written without readback, so
        the optimistic slots are restored if any write fails.
        """
        if not self.profile.supports_segments:
            raise ValueError(f"{self.model} does not support per-segment control")
        resolved: list[SegmentColorGroup] = [(list(segments), rgb) for segments, rgb in groups]
        if not resolved or any(not segments for segments, _rgb in resolved):
            raise ValueError("at least one non-empty segment group is required")
        snapshot = list(self.segment_colors)
        try:
            for segments, rgb in resolved:
                for segment in segments:
                    if not 1 <= segment <= self.profile.segment_count:
                        raise ValueError(f"segment {segment} out of range 1..{self.profile.segment_count}")
                    self.segment_colors[segment - 1] = rgb
            for packet in build_segment_paint(resolved, self.model):
                await self.send_command(packet)
        except Exception:
            self.segment_colors = snapshot
            raise
        self._enter_static_mode()
        self.async_set_updated_data(self.data or {})

    def _record_packet(self, direction: str, data: bytes) -> None:
        if not data:
            return
        header = data[0]
        action = data[1] if len(data) > 1 else None
        self.packet_log.append(
            {
                "ts": datetime.now().isoformat(),
                "dir": direction,
                "header": f"0x{header:02x}",
                "action": f"0x{action:02x}" if action is not None else None,
                "raw": data.hex(),
            }
        )
        if len(self.packet_log) > PACKET_LOG_LIMIT:
            del self.packet_log[:-PACKET_LOG_LIMIT]

    async def disconnect(self) -> None:
        client = self._client
        self._stop_keep_alive()
        if self._cancel_disconnect:
            self._cancel_disconnect()
            self._cancel_disconnect = None
        try:
            if client and client.is_connected:
                await client.disconnect()
        except BleakError, TimeoutError:
            _LOGGER.debug("Error disconnecting from %s", self.address)
        finally:
            if self._client is client:
                self._client = None
                self._notify_started_monotonic = None
                self._last_rx_monotonic = None
                self._expected_state.clear()
                if self.active_custom_id == self._owned_diy_effect_id:
                    self.active_custom_id = self.effect = None
                self._owned_diy_effect_id = None
