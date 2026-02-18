"""DataUpdateCoordinator for Govee BLE Lights."""

from __future__ import annotations

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

# fmt: off
from .const import DOMAIN, get_profile
from .protocol import (
    BRIGHTNESS_QUERY,
    COLOR_MODE_QUERY,
    KEEP_ALIVE,
    READ_UUID,
    WRITE_UUID,
    parse_brightness_response,
    parse_color_mode_response,
    parse_power_response,
)

# fmt: on

_LOGGER = logging.getLogger(__name__)

DISCONNECT_DELAY = 120
KEEP_ALIVE_INTERVAL = 5
STATE_QUERY_EVERY_N_KEEP_ALIVES = 3
RETRY_BACKOFF_SECONDS = 2
DEVICE_DISCOVERY_ATTEMPTS = 4


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
        self.video_saturation = self.video_brightness = self.white_brightness = self.music_sensitivity = 100
        self.video_full_screen, self.video_sound_effects = True, False
        self.video_sound_effects_softness = 0
        self.music_color: tuple[int, int, int] | None = None
        self._unsub_stop: CALLBACK_TYPE | None = hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP, self._handle_hass_stop
        )

    @property
    def device_info(self) -> DeviceInfo:
        # fmt: off
        return DeviceInfo(identifiers={(DOMAIN, self.address)}, name=f"Govee {self.model}",
                          manufacturer="Govee", model=self.model)
        # fmt: on

    @callback
    def _handle_hass_stop(self, _event: Event) -> None:
        self._stop_keep_alive()
        if self._cancel_disconnect:
            self._cancel_disconnect()
            self._cancel_disconnect = None

    async def _async_update_data(self) -> dict[str, Any]:
        if self.profile.state_readable:
            try:
                await self._ensure_connected()
                await self._send_state_queries()
            except BleakError:
                _LOGGER.debug("State refresh skipped for %s", self.address)
        # fmt: off
        return {"is_on": self.is_on, "brightness_pct": self.brightness_pct, "rgb_color": self.rgb_color,
                "color_temp_kelvin": self.color_temp_kelvin, "effect": self.effect}
        # fmt: on

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
        if self._client and self._client.is_connected:
            try:
                await self._client.start_notify(READ_UUID, self._notify_callback)
                self._start_keep_alive()
            except BleakError:
                _LOGGER.debug("Failed to start notify for %s", self.address)

    def _notify_callback(self, _sender: Any, data: bytearray) -> None:
        if len(data) < 3 or data[0] != 0xAA:
            return
        domain, payload = data[1], bytes(data[2:])
        _LOGGER.debug("rx %s domain=0x%02x payload=%s", self.address, domain, payload.hex())
        try:
            if domain == 0x01:
                self.is_on = parse_power_response(payload)
            elif domain == 0x04:
                self.brightness_pct = parse_brightness_response(payload)
            elif domain == 0x05:
                p = parse_color_mode_response(payload)
                self.effect = p.effect
                for attr in (
                    "video_full_screen",
                    "video_saturation",
                    "video_sound_effects",
                    "video_sound_effects_softness",
                    "music_sensitivity",
                    "music_color",
                    "white_brightness",
                ):
                    if (val := getattr(p, attr)) is not None:
                        setattr(self, attr, val)
                if p.rgb_color is not None:
                    self.rgb_color, self.color_temp_kelvin = p.rgb_color, None
            self.async_set_updated_data(self.data or {})
        except (IndexError, ValueError):
            _LOGGER.debug("Failed to parse notify from %s: %s", self.address, data.hex())

    async def _send_state_queries(self, *, include_keep_alive: bool = True, full_query: bool = True) -> bool:
        if not self._client or not self._client.is_connected:
            return False
        try:
            w = self._client.write_gatt_char
            if include_keep_alive:
                await w(WRITE_UUID, KEEP_ALIVE, response=False)
            if full_query:
                await w(WRITE_UUID, BRIGHTNESS_QUERY, response=False)
                await w(WRITE_UUID, COLOR_MODE_QUERY, response=False)
            return True
        except BleakError:
            return False

    async def refresh_state(
        self, *, expected_effect: str | None = None, expected_on: bool | None = None, timeout: float = 2.0
    ) -> bool:
        if not self.profile.state_readable:
            return False
        await self._ensure_connected()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not await self._send_state_queries(include_keep_alive=False):
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
                if not await self._send_state_queries(include_keep_alive=True, full_query=full):
                    break
        except asyncio.CancelledError:
            pass

    async def send_command(self, packet: bytes) -> None:
        async with self._lock:
            for attempt in range(3):
                try:
                    client = await self._ensure_connected()
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

    async def send_commands(self, packets: list[bytes]) -> None:
        for packet in packets:
            await self.send_command(packet)

    async def disconnect(self) -> None:
        self._stop_keep_alive()
        self._unsub_stop = None
        if self._cancel_disconnect:
            self._cancel_disconnect()
            self._cancel_disconnect = None
        if self._client and self._client.is_connected:
            try:
                await self._client.disconnect()
            except BleakError:
                _LOGGER.debug("Error disconnecting from %s", self.address)
        self._client = None
