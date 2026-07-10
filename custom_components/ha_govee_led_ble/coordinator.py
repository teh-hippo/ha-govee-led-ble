"""DataUpdateCoordinator for HA Govee LED BLE."""

import asyncio
import logging
import time
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
from .custom_effects import CustomEffect
from .protocol import (
    BRIGHTNESS_PACKET_TYPE,
    BRIGHTNESS_QUERY,
    COLOR_MODE_MUSIC,
    COLOR_MODE_QUERY,
    COLOR_MODE_STATIC,
    COLOR_PACKET_TYPE,
    COMMAND_HEADER,
    FIRMWARE_PACKET_TYPE,
    FW_QUERY,
    HARDWARE_PACKET_TYPE,
    HW_QUERY,
    KEEP_ALIVE,
    MUSIC_SLUG_BY_ID,
    POWER_PACKET_TYPE,
    READ_UUID,
    WRITE_UUID,
    ParsedMode,
    ParsedTimerSchedule,
    SegmentColorGroup,
    build_segment_paint,
    kelvin_to_rgb,
    parse_color_mode_response,
    parse_fw_version,
    parse_hw_version,
    parse_poweroff_memory,
    parse_timer_schedule_table,
    parse_timer_sleep,
    parse_timer_wakeup,
    split_status_frame,
)

_LOGGER = logging.getLogger(__name__)

DISCONNECT_DELAY = 120
KEEP_ALIVE_INTERVAL = 5
STATE_QUERY_EVERY_N_KEEP_ALIVES = 3
IDENTITY_RETRY_TICKS = 6
RETRY_BACKOFF_SECONDS = 2
DEVICE_DISCOVERY_ATTEMPTS = 4
PACKET_LOG_LIMIT = 50
EXPECTED_STATE_TTL = 2.0

_CORE_STATE_FIELDS = ("is_on", "brightness_pct", "rgb_color", "color_temp_kelvin", "effect")
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


def _expected_from_packet(packet: bytes) -> tuple[str, Any] | None:
    """Map an outgoing command to the optimistic (field, value) its reply should confirm."""
    if len(packet) < 3 or packet[0] != COMMAND_HEADER:
        return None
    if packet[1] == BRIGHTNESS_PACKET_TYPE:
        return "brightness_pct", packet[2]
    if packet[1] != COLOR_PACKET_TYPE or len(packet) < 4:
        return None
    if packet[2] == COLOR_MODE_MUSIC:
        return "music_mode", MUSIC_SLUG_BY_ID.get(packet[3])
    if packet[2] == COLOR_MODE_STATIC and packet[3] == 0x01 and len(packet) >= 9:
        if packet[4] or packet[5] or packet[6]:
            return "rgb_color", (packet[4], packet[5], packet[6])
        return "color_temp_kelvin", (packet[7] << 8) | packet[8]
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
        self._pre_mode_snapshot = PreModeSnapshot(kind="rgb", rgb=(255, 255, 255))
        self.custom_effects: dict[str, CustomEffect] = {}
        self._store_lock = asyncio.Lock()
        self._effect_store: EffectStore | None = None
        self.segment_colors: list[tuple[int, int, int]] = [self.rgb_color] * profile.segment_count
        # Backend-only preview flag (never a device command); the reduce-motion switch restores it.
        self.preview_reduce_motion = False
        self.video_saturation = self.white_brightness = 100
        self.music_sensitivity = 99
        self.video_white_balance: int | None = None
        self.music_calm = False
        self.video_full_screen, self.video_sound_effects = True, False
        self.video_sound_effects_softness = 0
        self.music_color: tuple[int, int, int] | None = None
        # Per-mode music movement params (§2.3, EXPERIMENTAL); defaults are the capture-pinned
        # template values so an untouched entity reapplies the exact captured body.
        self.music_separation_point = 1
        self.music_separation_gradient = True
        self.music_hopping_brightness = 50
        self.music_piano_key_count = 15
        self.music_fountain_direction = "clockwise"
        self.music_daynight_segments = 1
        self.music_daynight_speed = 10
        # Power-off memory (restore last state after power loss); None until a reply is seen.
        self.poweroff_memory: bool | None = None
        # Experimental timers; None until a write or reply populates them.
        self.sleep_timer_enabled: bool | None = None
        self.sleep_timer_minutes: int | None = None
        self.wakeup_timer_enabled: bool | None = None
        self.wakeup_timer_time: dt_time | None = None
        self.schedule_timers: list[ParsedTimerSchedule | None] = [None] * TIMER_SCHEDULE_SLOTS
        self.packet_log: list[dict[str, Any]] = []
        self._expected_state: dict[str, tuple[Any, float]] = {}
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
            self._reset_disconnect_timer()
            return self._client
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
            await self._start_notify()
            await self._send_identity_queries()
            await self._send_state_queries()
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
        try:
            await self._client.start_notify(READ_UUID, self._notify_callback)
            self._start_keep_alive()
        except BleakError:
            _LOGGER.debug("Failed to start notify for %s", self.address)

    def _arm_expected(self, packet: bytes) -> None:
        expectation = _expected_from_packet(packet)
        if expectation is not None:
            field, value = expectation
            self._expected_state[field] = (value, time.monotonic() + EXPECTED_STATE_TTL)

    def _accept_expected(self, field: str, value: Any) -> bool:
        """Consult the optimistic window for `field`.

        Returns True (and clears the expectation) when the reply agrees or the deadline
        has passed; returns False to drop a stale reply that still disagrees in-window.
        """
        expectation = self._expected_state.get(field)
        if expectation is None:
            return True
        expected, deadline = expectation
        if time.monotonic() >= deadline or value == expected:
            del self._expected_state[field]
            return True
        _LOGGER.debug("Ignoring stale %s for %s: %r (expecting %r)", field, self.address, value, expected)
        return False

    def _apply_color_mode_payload(self, payload: bytes) -> None:
        parsed = parse_color_mode_response(payload)
        # Readback mirror of _enter_static_mode: committing one mode clears the others so exactly one
        # is ever truthful. A bare COLOUR reply keeps active_custom_id (a custom effect reads back as static).
        if parsed.mode is ParsedMode.MUSIC:
            if parsed.music_mode is not None and self._accept_expected("music_mode", parsed.music_mode):
                self.music_mode = parsed.music_mode
                self.video_mode, self.effect, self.active_custom_id = "off", None, None
        elif parsed.mode is ParsedMode.VIDEO:
            if parsed.video_mode is not None:
                self.video_mode = parsed.video_mode
                self.music_mode, self.effect, self.active_custom_id = "off", None, None
        elif parsed.mode is ParsedMode.SCENE:
            if self._accept_expected("effect", parsed.effect):
                self.effect = parsed.effect
                self.music_mode, self.video_mode, self.active_custom_id = "off", "off", None
        elif parsed.mode is ParsedMode.COLOUR:
            if self._accept_expected("effect", parsed.effect):
                self.effect, self.music_mode, self.video_mode = None, "off", "off"
        for attr in _COLOR_MODE_FIELDS:
            if (value := getattr(parsed, attr)) is not None:
                setattr(self, attr, value)
        if parsed.rgb_color is not None:
            # A colour-temp state reads back as its white-point RGB with no kelvin field; recognising it
            # keeps the light in CT mode instead of clobbering kelvin and dropping to a near-white RGB.
            if self.color_temp_kelvin is not None and parsed.rgb_color == kelvin_to_rgb(self.color_temp_kelvin):
                return
            accept_rgb = self._accept_expected("rgb_color", parsed.rgb_color)
            accept_kelvin = self._accept_expected("color_temp_kelvin", None)
            if accept_rgb and accept_kelvin:
                self.rgb_color, self.color_temp_kelvin = parsed.rgb_color, None

    def _apply_sleep_timer_payload(self, payload: bytes) -> None:
        parsed = parse_timer_sleep(payload)
        self.sleep_timer_enabled = parsed.enabled
        self.sleep_timer_minutes = parsed.close_minutes

    def _apply_wakeup_timer_payload(self, payload: bytes) -> None:
        parsed = parse_timer_wakeup(payload)
        self.wakeup_timer_enabled = parsed.enabled
        self.wakeup_timer_time = dt_time(parsed.hour, parsed.minute)

    def _apply_schedule_timer_payload(self, payload: bytes) -> None:
        # The aa 23 reply is the full table: 0xff prefix + four 4-byte slot records.
        if payload[:1] != b"\xff":
            return
        for slot, parsed in enumerate(parse_timer_schedule_table(payload)):
            if slot < TIMER_SCHEDULE_SLOTS:
                self.schedule_timers[slot] = parsed

    def _notify_callback(self, _sender: Any, data: bytearray) -> None:
        frame = bytes(data)
        split = split_status_frame(frame)
        if split is None:
            return
        domain, payload = split
        self._record_packet("rx", frame)
        _LOGGER.debug("rx %s domain=0x%02x payload=%s", self.address, domain, payload.hex())
        try:
            if domain == POWER_PACKET_TYPE:
                self.is_on = bool(payload[0])
            elif domain == BRIGHTNESS_PACKET_TYPE:
                if not self._accept_expected("brightness_pct", payload[0]):
                    return
                self.brightness_pct = payload[0]
            elif domain == COLOR_PACKET_TYPE:
                self._apply_color_mode_payload(payload)
            elif domain == FIRMWARE_PACKET_TYPE:
                self._note_identity(fw_version=parse_fw_version(payload))
            elif domain == HARDWARE_PACKET_TYPE:
                self._note_identity(hw_version=parse_hw_version(payload))
            elif domain == POWEROFF_MEMORY_PACKET_TYPE:
                self.poweroff_memory = parse_poweroff_memory(payload).enabled
            elif domain == SLEEP_TIMER_PACKET_TYPE:
                self._apply_sleep_timer_payload(payload)
            elif domain == WAKEUP_TIMER_PACKET_TYPE:
                self._apply_wakeup_timer_payload(payload)
            elif domain == SCHEDULE_TIMER_PACKET_TYPE:
                self._apply_schedule_timer_payload(payload)
            self.async_set_updated_data(self.data or {})
        except IndexError, ValueError:
            _LOGGER.debug("Failed to parse notify from %s: %s", self.address, data.hex())

    async def _send_state_queries(
        self,
        *,
        query_power: bool = True,
        query_brightness: bool = True,
        query_color_mode: bool = True,
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
            for query in queries:
                self._record_packet("tx", query)
                await self._client.write_gatt_char(WRITE_UUID, query, response=False)
            return True
        except BleakError:
            return False

    async def _send_identity_queries(self, *, include_hw: bool = True) -> None:
        """Query firmware (and, at connect, hardware) for DeviceInfo, sending only unknowns.

        A firmware reply can be missed right after connect (notify not yet delivering), so the
        keep-alive loop re-sends the firmware query while it is unknown, bounded by
        ``IDENTITY_RETRY_TICKS``. Hardware is sent once per connect and not retried: some units
        never answer ``aa 07`` (see #97), so retrying it would only repeat a doomed write.
        """
        if not self._client or not self._client.is_connected:
            return
        candidates = [(FW_QUERY, self.fw_version)]
        if include_hw:
            candidates.append((HW_QUERY, self.hw_version))
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
        expected_music_mode: str | None = None,
        expected_video_mode: str | None = None,
        timeout: float = 2.0,
    ) -> bool:
        if not self.profile.state_readable:
            return False
        async with self._lock:
            await self._ensure_connected()
        expectations = (expected_effect, expected_on, expected_music_mode, expected_video_mode)
        color_expectations = (expected_effect, expected_music_mode, expected_video_mode)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            # Avoid querying brightness as part of verification to reduce stale/out-of-order
            # updates overriding optimistic writes.
            query_power = expected_on is not None
            query_color = any(value is not None for value in color_expectations)
            if not query_power and not query_color:
                query_power = query_color = True
            async with self._lock:
                ok = await self._send_state_queries(
                    query_power=query_power, query_brightness=False, query_color_mode=query_color
                )
            if not ok:
                return False
            if (
                (expected_effect is None or self.effect == expected_effect)
                and (expected_on is None or self.is_on == expected_on)
                and (expected_music_mode is None or self.music_mode == expected_music_mode)
                and (expected_video_mode is None or self.video_mode == expected_video_mode)
            ):
                return True
            await asyncio.sleep(0.25)
        return all(expectation is None for expectation in expectations)

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
                self._keep_alive_ticks += 1
                if self.fw_version is None and self._identity_retries < IDENTITY_RETRY_TICKS:
                    self._identity_retries += 1
                    async with self._lock:
                        await self._send_identity_queries(include_hw=False)
                full = self._keep_alive_ticks % STATE_QUERY_EVERY_N_KEEP_ALIVES == 0
                async with self._lock:
                    ok = await self._send_state_queries(query_power=True, query_brightness=full, query_color_mode=full)
                if not ok:
                    break
        except asyncio.CancelledError:
            pass

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
                    self._client = None
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
        if not self.profile.segment_count:
            raise ValueError(f"{self.model} does not support per-segment control")
        resolved: list[SegmentColorGroup] = [(list(segments), rgb) for segments, rgb in groups]
        snapshot = list(self.segment_colors)
        try:
            for segments, rgb in resolved:
                for segment in segments:
                    if not 1 <= segment <= self.profile.segment_count:
                        raise ValueError(f"segment {segment} out of range 1..{self.profile.segment_count}")
                    self.segment_colors[segment - 1] = rgb
            for packet in build_segment_paint(resolved):
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
        self._stop_keep_alive()
        if self._cancel_disconnect:
            self._cancel_disconnect()
            self._cancel_disconnect = None
        if self._client and self._client.is_connected:
            try:
                await self._client.disconnect()
            except BleakError:
                _LOGGER.debug("Error disconnecting from %s", self.address)
        self._client = None
