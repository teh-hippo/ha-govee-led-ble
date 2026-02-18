"""DataUpdateCoordinator for Govee BLE Lights."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from typing import Any

from bleak import BleakClient, BleakError
from bleak_retry_connector import establish_connection
from homeassistant.components import bluetooth
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, ModelProfile, get_profile
from .protocol import (
    READ_UUID,
    WRITE_UUID,
    build_brightness_query,
    build_color_mode_query,
    build_keep_alive,
    parse_brightness_response,
    parse_color_mode_response,
    parse_power_response,
)

_LOGGER = logging.getLogger(__name__)

DISCONNECT_DELAY = 120  # seconds before auto-disconnect
KEEP_ALIVE_INTERVAL = 5  # seconds between keep-alive pings
STATE_QUERY_EVERY_N_KEEP_ALIVES = 3
SHUTDOWN_RETRY_BACKOFF_SECONDS = 4
DEVICE_DISCOVERY_RETRY_SECONDS = 2
DEVICE_DISCOVERY_ATTEMPTS = 4


class GoveeBLECoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Manages BLE connection lifecycle for a Govee device."""

    def __init__(
        self,
        hass: HomeAssistant,
        address: str,
        model: str,
    ) -> None:
        """Initialize the coordinator."""
        profile = get_profile(model)
        super().__init__(
            hass,
            _LOGGER,
            name=f"Govee {model} ({address})",
            update_interval=timedelta(seconds=30) if profile.state_readable else None,
        )
        self.address = address
        self.model = model
        self.profile: ModelProfile = profile
        self._client: BleakClient | None = None
        self._lock = asyncio.Lock()
        self._cancel_disconnect: CALLBACK_TYPE | None = None
        self._keep_alive_task: asyncio.Task | None = None
        self._trace_seq: int = 0
        self._keep_alive_ticks: int = 0
        # Optimistic state (updated by actual state for state_readable models)
        self.is_on: bool = False
        self.brightness_pct: int = 100
        self.rgb_color: tuple[int, int, int] = (255, 255, 255)
        self.color_temp_kelvin: int | None = None
        self.effect: str | None = None
        # Per-effect parameters (H6199)
        self.video_saturation: int = 100
        self.video_brightness: int = 100
        self.white_brightness: int = 100
        self.video_full_screen: bool = True
        self.video_sound_effects: bool = False
        self.video_sound_effects_softness: int = 0
        self.music_sensitivity: int = 100
        self.music_color: tuple[int, int, int] | None = None
        self._unsub_stop = hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP,
            self._handle_hass_stop,
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for this Govee device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.address)},
            name=f"Govee {self.model}",
            manufacturer="Govee",
            model=self.model,
        )

    @callback
    def _handle_hass_stop(self, _event: Event) -> None:
        """Ensure BLE tasks are cancelled before Home Assistant shutdown."""
        self._stop_keep_alive()
        if self._cancel_disconnect:
            self._cancel_disconnect()
            self._cancel_disconnect = None

    async def _async_update_data(self) -> dict[str, Any]:
        """Return current state dict."""
        if self.profile.state_readable:
            try:
                await self._ensure_connected()
                await self._send_state_queries()
            except BleakError:
                _LOGGER.debug("State refresh skipped for %s (device unavailable)", self.address)
        return {
            "is_on": self.is_on,
            "brightness_pct": self.brightness_pct,
            "rgb_color": self.rgb_color,
            "color_temp_kelvin": self.color_temp_kelvin,
            "effect": self.effect,
        }

    async def _ensure_connected(self) -> BleakClient:
        """Ensure BLE connection is established."""
        if self._client and self._client.is_connected:
            self._reset_disconnect_timer()
            return self._client

        ble_device = None
        for attempt in range(DEVICE_DISCOVERY_ATTEMPTS):
            ble_device = bluetooth.async_ble_device_from_address(self.hass, self.address, connectable=True)
            if ble_device is not None:
                break
            if attempt < DEVICE_DISCOVERY_ATTEMPTS - 1:
                await asyncio.sleep(DEVICE_DISCOVERY_RETRY_SECONDS)
        if not ble_device:
            raise BleakError(f"Device {self.address} not found")

        self._client = await establish_connection(BleakClient, ble_device, self.address)
        self._reset_disconnect_timer()

        if self.profile.state_readable:
            await self._start_notify()
            await self._send_state_queries()

        return self._client

    def _reset_disconnect_timer(self) -> None:
        """Reset the auto-disconnect timer."""
        if self._cancel_disconnect:
            self._cancel_disconnect()

        @callback
        def _on_disconnect_timeout(_now) -> None:
            self.hass.async_create_task(self.disconnect())

        self._cancel_disconnect = async_call_later(self.hass, DISCONNECT_DELAY, _on_disconnect_timeout)

    # --- Notify / state reading (for state_readable models) ---

    async def _start_notify(self) -> None:
        """Subscribe to BLE notifications for state reading."""
        if self._client and self._client.is_connected:
            try:
                await self._client.start_notify(READ_UUID, self._notify_callback)
                _LOGGER.debug("Started notify subscription for %s", self.address)
                self._start_keep_alive()
            except BleakError:
                _LOGGER.debug("Failed to start notify for %s", self.address)

    def _next_trace_id(self) -> int:
        """Return a per-device monotonically increasing trace id."""
        self._trace_seq += 1
        return self._trace_seq

    def _notify_callback(self, _sender: Any, data: bytearray) -> None:
        """Handle incoming BLE notifications with state data."""
        if len(data) < 3:
            return
        header = data[0]
        domain = data[1]
        payload = bytes(data[2:])
        trace_id = self._next_trace_id()
        _LOGGER.debug(
            "rx[%s] %s header=0x%02x domain=0x%02x payload=%s",
            trace_id,
            self.address,
            header,
            domain,
            payload.hex(),
        )
        if header != 0xAA:
            return
        try:
            if domain == 0x01:
                self.is_on = parse_power_response(payload)
            elif domain == 0x04:
                self.brightness_pct = parse_brightness_response(payload)
            elif domain == 0x05:
                parsed = parse_color_mode_response(payload)
                self.effect = parsed.effect
                if parsed.video_full_screen is not None:
                    self.video_full_screen = parsed.video_full_screen
                if parsed.video_saturation is not None:
                    self.video_saturation = parsed.video_saturation
                if parsed.video_sound_effects is not None:
                    self.video_sound_effects = parsed.video_sound_effects
                if parsed.video_sound_effects_softness is not None:
                    self.video_sound_effects_softness = parsed.video_sound_effects_softness
                if parsed.music_sensitivity is not None:
                    self.music_sensitivity = parsed.music_sensitivity
                if parsed.music_color is not None:
                    self.music_color = parsed.music_color
                if parsed.rgb_color is not None:
                    self.rgb_color = parsed.rgb_color
                    self.color_temp_kelvin = None
                if parsed.white_brightness is not None:
                    self.white_brightness = parsed.white_brightness
            self.async_set_updated_data(self.data or {})
        except (IndexError, ValueError):
            _LOGGER.debug("Failed to parse notify data from %s: %s", self.address, data.hex())

    async def _send_state_queries(self, *, include_keep_alive: bool = True) -> bool:
        """Send status query packets for state-readable models."""
        if not self._client or not self._client.is_connected:
            return False

        trace_id = self._next_trace_id()
        brightness_query = build_brightness_query()
        color_mode_query = build_color_mode_query()
        keep_alive = build_keep_alive()
        try:
            if include_keep_alive:
                _LOGGER.debug("tx[%s] %s keep_alive=%s", trace_id, self.address, keep_alive.hex())
                await self._client.write_gatt_char(WRITE_UUID, keep_alive, response=False)
            _LOGGER.debug(
                "tx[%s] %s state_query brightness=%s color_mode=%s",
                trace_id,
                self.address,
                brightness_query.hex(),
                color_mode_query.hex(),
            )
            await self._client.write_gatt_char(WRITE_UUID, brightness_query, response=False)
            await self._client.write_gatt_char(WRITE_UUID, color_mode_query, response=False)
            _LOGGER.debug("tx[%s] %s state_query_complete", trace_id, self.address)
            return True
        except BleakError:
            _LOGGER.debug("tx[%s] %s state_query_failed", trace_id, self.address)
            return False

    async def _send_keep_alive_only(self) -> bool:
        """Send only a keep-alive packet."""
        if not self._client or not self._client.is_connected:
            return False
        trace_id = self._next_trace_id()
        keep_alive = build_keep_alive()
        _LOGGER.debug("tx[%s] %s keep_alive=%s", trace_id, self.address, keep_alive.hex())
        try:
            await self._client.write_gatt_char(WRITE_UUID, keep_alive, response=False)
            return True
        except BleakError:
            _LOGGER.debug("tx[%s] %s keep_alive_failed", trace_id, self.address)
            return False

    async def refresh_state(
        self,
        *,
        expected_effect: str | None = None,
        expected_on: bool | None = None,
        timeout: float = 2.0,
    ) -> bool:
        """Refresh state for state-readable devices and optionally wait for an effect."""
        if not self.profile.state_readable:
            return False

        await self._ensure_connected()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not await self._send_state_queries(include_keep_alive=False):
                return False
            effect_ok = expected_effect is None or self.effect == expected_effect
            power_ok = expected_on is None or self.is_on == expected_on
            if effect_ok and power_ok:
                return True
            await asyncio.sleep(0.25)

        return expected_effect is None and expected_on is None

    def _start_keep_alive(self) -> None:
        """Start periodic keep-alive pings."""
        self._stop_keep_alive()
        self._keep_alive_task = self.hass.async_create_task(self._keep_alive_loop())

    def _stop_keep_alive(self) -> None:
        """Stop the keep-alive loop."""
        if self._keep_alive_task and not self._keep_alive_task.done():
            self._keep_alive_task.cancel()
            self._keep_alive_task = None

    async def _keep_alive_loop(self) -> None:
        """Periodically send keep-alive packets to maintain connection."""
        try:
            while True:
                await asyncio.sleep(KEEP_ALIVE_INTERVAL)
                if self._client and self._client.is_connected:
                    self._keep_alive_ticks += 1
                    if self._keep_alive_ticks % STATE_QUERY_EVERY_N_KEEP_ALIVES == 0:
                        ok = await self._send_state_queries(include_keep_alive=True)
                    else:
                        ok = await self._send_keep_alive_only()
                    if not ok:
                        break
                else:
                    break
        except asyncio.CancelledError:
            pass

    # --- Command sending ---

    async def send_command(self, packet: bytes) -> None:
        """Send a BLE command with retry logic."""
        async with self._lock:
            trace_id = self._next_trace_id()
            for attempt in range(3):
                try:
                    client = await self._ensure_connected()
                    _LOGGER.debug("tx[%s] %s command=%s attempt=%d", trace_id, self.address, packet.hex(), attempt + 1)
                    await client.write_gatt_char(WRITE_UUID, packet, response=False)
                    _LOGGER.debug("tx[%s] %s command_complete", trace_id, self.address)
                    return
                except BleakError as err:
                    self._client = None
                    _LOGGER.debug("tx[%s] %s command_failed attempt=%d", trace_id, self.address, attempt + 1)
                    if attempt == 2:
                        _LOGGER.error(
                            "Failed to send command to %s after 3 attempts",
                            self.address,
                        )
                        raise
                    if "already shutdown" in str(err).lower():
                        backoff = SHUTDOWN_RETRY_BACKOFF_SECONDS * (attempt + 1)
                        _LOGGER.debug(
                            "Bluetooth stack not ready for %s; retrying in %.1fs",
                            self.address,
                            backoff,
                        )
                        await asyncio.sleep(backoff)
                    elif "not found" in str(err).lower():
                        backoff = DEVICE_DISCOVERY_RETRY_SECONDS * (attempt + 1)
                        _LOGGER.debug(
                            "BLE device %s not discoverable yet; retrying in %.1fs",
                            self.address,
                            backoff,
                        )
                        await asyncio.sleep(backoff)
                    _LOGGER.debug(
                        "BLE command attempt %d failed for %s, retrying",
                        attempt + 1,
                        self.address,
                    )

    async def send_commands(self, packets: list[bytes]) -> None:
        """Send multiple BLE packets in sequence (for multi-packet scenes)."""
        for packet in packets:
            await self.send_command(packet)

    async def disconnect(self) -> None:
        """Disconnect from the BLE device."""
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
            finally:
                self._client = None
