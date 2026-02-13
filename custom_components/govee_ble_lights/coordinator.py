"""DataUpdateCoordinator for Govee BLE Lights."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from bleak import BleakClient, BleakError
from bleak_retry_connector import establish_connection
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import ModelProfile, get_profile
from .protocol import (
    READ_UUID,
    WRITE_UUID,
    build_keep_alive,
    parse_brightness_response,
    parse_power_response,
)

_LOGGER = logging.getLogger(__name__)

DISCONNECT_DELAY = 120  # seconds before auto-disconnect
KEEP_ALIVE_INTERVAL = 5  # seconds between keep-alive pings


class GoveeBLECoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Manages BLE connection lifecycle for a Govee device."""

    def __init__(
        self,
        hass: HomeAssistant,
        address: str,
        model: str,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"Govee {model} ({address})",
        )
        self.address = address
        self.model = model
        self.profile: ModelProfile = get_profile(model)
        self._client: BleakClient | None = None
        self._lock = asyncio.Lock()
        self._disconnect_timer: asyncio.TimerHandle | None = None
        self._keep_alive_task: asyncio.Task | None = None
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

    async def _async_update_data(self) -> dict[str, Any]:
        """Return current state dict."""
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

        ble_device = bluetooth.async_ble_device_from_address(self.hass, self.address, connectable=True)
        if not ble_device:
            raise BleakError(f"Device {self.address} not found")

        self._client = await establish_connection(BleakClient, ble_device, self.address)
        self._reset_disconnect_timer()

        if self.profile.state_readable:
            await self._start_notify()

        return self._client

    def _reset_disconnect_timer(self) -> None:
        """Reset the auto-disconnect timer."""
        if self._disconnect_timer:
            self._disconnect_timer.cancel()
        self._disconnect_timer = self.hass.loop.call_later(
            DISCONNECT_DELAY, lambda: self.hass.async_create_task(self.disconnect())
        )

    # --- Notify / state reading (for state_readable models) ---

    async def _start_notify(self) -> None:
        """Subscribe to BLE notifications for state reading."""
        if self._client and self._client.is_connected:
            try:
                await self._client.start_notify(READ_UUID, self._notify_callback)
                self._start_keep_alive()
            except BleakError:
                _LOGGER.debug("Failed to start notify for %s", self.address)

    def _notify_callback(self, _sender: Any, data: bytearray) -> None:
        """Handle incoming BLE notifications with state data."""
        if len(data) < 3:
            return
        header = data[0]
        domain = data[1]
        payload = bytes(data[2:])
        if header != 0xAA:
            return
        try:
            if domain == 0x01:
                self.is_on = parse_power_response(payload)
            elif domain == 0x04:
                self.brightness_pct = parse_brightness_response(payload)
            self.async_set_updated_data(self.data or {})
        except (IndexError, ValueError):
            _LOGGER.debug("Failed to parse notify data from %s: %s", self.address, data.hex())

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
                    try:
                        await self._client.write_gatt_char(WRITE_UUID, build_keep_alive(), response=False)
                    except BleakError:
                        _LOGGER.debug("Keep-alive failed for %s", self.address)
                        break
                else:
                    break
        except asyncio.CancelledError:
            pass

    # --- Command sending ---

    async def send_command(self, packet: bytes) -> None:
        """Send a BLE command with retry logic."""
        async with self._lock:
            for attempt in range(3):
                try:
                    client = await self._ensure_connected()
                    await client.write_gatt_char(WRITE_UUID, packet, response=False)
                    return
                except BleakError:
                    self._client = None
                    if attempt == 2:
                        _LOGGER.error(
                            "Failed to send command to %s after 3 attempts",
                            self.address,
                        )
                        raise
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
        if self._disconnect_timer:
            self._disconnect_timer.cancel()
            self._disconnect_timer = None
        if self._client and self._client.is_connected:
            try:
                await self._client.disconnect()
            except BleakError:
                _LOGGER.debug("Error disconnecting from %s", self.address)
            finally:
                self._client = None
