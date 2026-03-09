"""DataUpdateCoordinator for HA Govee LED BLE."""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any

from bleak import BleakClient, BleakError  # type: ignore[attr-defined]
from bleak_retry_connector import establish_connection
from homeassistant.components import bluetooth
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, get_profile
from .protocol import (
    BRIGHTNESS_PACKET_TYPE,
    BRIGHTNESS_QUERY,
    COLOR_MODE_QUERY,
    COLOR_PACKET_TYPE,
    KEEP_ALIVE,
    POWER_PACKET_TYPE,
    READ_UUID,
    STATUS_HEADER,
    WRITE_UUID,
    parse_color_mode_response,
    xor_checksum,
)

_LOGGER = logging.getLogger(__name__)

DISCONNECT_DELAY = 120
KEEP_ALIVE_INTERVAL = 5
STATE_QUERY_EVERY_N_KEEP_ALIVES = 3
RETRY_BACKOFF_SECONDS = 2
DEVICE_DISCOVERY_ATTEMPTS = 4
PACKET_LOG_LIMIT = 50
EXPECTED_BRIGHTNESS_TTL = 2.0

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


class GoveeBLECoordinator(DataUpdateCoordinator[dict[str, Any]]):
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
        # Optimistic state
        self.is_on = False
        self.brightness_pct = 100
        self.rgb_color: tuple[int, int, int] = (255, 255, 255)
        self.color_temp_kelvin: int | None = None
        self.effect: str | None = None
        # H6199 parameters
        self.video_saturation = self.white_brightness = self.music_sensitivity = 100
        self.video_white_balance: int | None = None
        self.music_calm = False
        self.video_full_screen, self.video_sound_effects = True, False
        self.video_sound_effects_softness = 0
        self.music_color: tuple[int, int, int] | None = None
        self.packet_log: list[dict[str, Any]] = []
        self._expected_brightness_pct: int | None = None
        self._expected_brightness_deadline = 0.0
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._handle_hass_stop)

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.address)},
            name=f"Govee {self.model}",
            manufacturer="Govee",
            model=self.model,
        )

    @callback
    def _handle_hass_stop(self, _event: Event) -> None:
        self._stop_keep_alive()
        if self._cancel_disconnect:
            self._cancel_disconnect()
            self._cancel_disconnect = None

    async def _async_update_data(self) -> dict[str, Any]:
        if self.hass.is_stopping:
            return {field: getattr(self, field) for field in _CORE_STATE_FIELDS}
        if self.profile.state_readable:
            try:
                async with self._lock:
                    await self._ensure_connected()
                    await self._send_state_queries()
            except BleakError:
                _LOGGER.debug("State refresh skipped for %s", self.address)
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

    def _apply_color_mode_payload(self, payload: bytes) -> None:
        parsed = parse_color_mode_response(payload)
        self.effect = parsed.effect
        for attr in _COLOR_MODE_FIELDS:
            if (value := getattr(parsed, attr)) is not None:
                setattr(self, attr, value)
        if parsed.rgb_color is not None:
            self.rgb_color, self.color_temp_kelvin = parsed.rgb_color, None

    def _notify_callback(self, _sender: Any, data: bytearray) -> None:
        frame = bytes(data)
        if len(frame) < 3 or frame[0] != STATUS_HEADER:
            return
        domain = frame[1]
        payload = bytes(frame[2:-1]) if len(frame) == 20 and xor_checksum(frame[:-1]) == frame[-1] else bytes(frame[2:])
        self._record_packet("rx", frame)
        _LOGGER.debug("rx %s domain=0x%02x payload=%s", self.address, domain, payload.hex())
        try:
            if domain == POWER_PACKET_TYPE:
                self.is_on = bool(payload[0])
            elif domain == BRIGHTNESS_PACKET_TYPE:
                pct = payload[0]
                if self._expected_brightness_pct is not None:
                    if time.monotonic() >= self._expected_brightness_deadline:
                        self._expected_brightness_pct = None
                    elif pct != self._expected_brightness_pct:
                        _LOGGER.debug(
                            "Ignoring stale brightness for %s: %s (expecting %s)",
                            self.address,
                            pct,
                            self._expected_brightness_pct,
                        )
                        return
                    else:
                        self._expected_brightness_pct = None
                self.brightness_pct = pct
            elif domain == COLOR_PACKET_TYPE:
                self._apply_color_mode_payload(payload)
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

    async def refresh_state(
        self, *, expected_effect: str | None = None, expected_on: bool | None = None, timeout: float = 2.0
    ) -> bool:
        if not self.profile.state_readable:
            return False
        async with self._lock:
            await self._ensure_connected()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            # Avoid querying brightness as part of verification to reduce stale/out-of-order
            # updates overriding optimistic writes.
            query_power = expected_on is not None
            query_color = expected_effect is not None
            if expected_on is None and expected_effect is None:
                query_power = query_color = True
            async with self._lock:
                ok = await self._send_state_queries(
                    query_power=query_power, query_brightness=False, query_color_mode=query_color
                )
            if not ok:
                return False
            if (expected_effect is None or self.effect == expected_effect) and (
                expected_on is None or self.is_on == expected_on
            ):
                return True
            await asyncio.sleep(0.25)
        return expected_effect is None and expected_on is None

    def _start_keep_alive(self) -> None:
        self._stop_keep_alive()
        self._keep_alive_task = self.hass.async_create_task(self._keep_alive_loop())

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
                    if len(packet) > 2 and packet[0] == 0x33 and packet[1] == 0x04:
                        self._expected_brightness_deadline = time.monotonic() + EXPECTED_BRIGHTNESS_TTL
                        self._expected_brightness_pct = packet[2]
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
