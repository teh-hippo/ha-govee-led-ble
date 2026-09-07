"""Display-setting and video-mode control for the Govee BLE coordinator.

The `0xa9` register family -- black bar elimination, blank screen, HDR, AI filter -- plus
entering video mode. Grouped because they share one awkward property: every `0xa9` write is
acknowledged with a generic `33 a9 00` that echoes neither the sub-command nor the value, so an
ack means "accepted" and never "applied". Each setter here writes, then reads back, and rolls
its optimistic state back if the read disagrees.

Split out the way :mod:`coordinator_modes` is -- a mixin over :class:`_CoordinatorBase` -- so
the concrete coordinator stays a composition of behaviours rather than one long class.
"""

from __future__ import annotations

import logging

from .coordinator_base import _CoordinatorBase
from .coordinator_status import ParsedMode
from .generated_protocol_adapter import (
    build_ai_filter,
    build_black_border_removal,
    build_black_screen_detection,
    build_hdr_effect,
    build_video_mode_h66a0,
    build_video_setting_query,
)
from .video_settings import (
    AI_FILTER_SETTING,
    BLACK_BORDER_REMOVAL_SETTING,
    BLACK_SCREEN_DETECTION_SETTING,
    BLANK_SCREEN_LOW_BRIGHTNESS,
    BLANK_SCREEN_SAME_TONE,
    HDR_EFFECT_SETTING,
    VIDEO_DEFAULT_PRESET,
    parse_hdr_effect,
)

_LOGGER = logging.getLogger(__name__)


class _DisplaySettingsMixin(_CoordinatorBase):
    """The `0xa9` display registers and video-mode entry, each write read back."""

    @property
    def black_border_removal(self) -> bool | None:
        """0xa9 sub 0x0b, one byte, 0 or 1. None until the register answers."""
        values = self.video_settings.get(BLACK_BORDER_REMOVAL_SETTING)
        return bool(values[0]) if values else None

    async def async_enter_video_mode(
        self,
        *,
        game_mode: bool | None = None,
        picture_preset: str | None = None,
        saturation: int | None = None,
        sound_effects: bool | None = None,
        sound_effects_softness: int | None = None,
    ) -> None:
        """Put the device into video mode, mimicking what the vendor app sends.

        The app writes a full body every time rather than resuming a stored one, so this does
        too. Anything not given falls back to what the device last reported through `aa 05`
        while it was in video mode, and to the vendor defaults otherwise.

        Video mode is NOT DreamView: a device in a DreamView group is not in video mode, and
        DreamView's settings live in the 0x60 family, which this integration does not drive.
        """
        if not self.profile.supports_video_mode:
            raise ValueError(f"{self.model} does not support video mode")
        resolved_game = self.video_mode == "game" if game_mode is None else game_mode
        resolved_preset = picture_preset or self.video_picture_preset or VIDEO_DEFAULT_PRESET
        resolved_saturation = self.video_saturation if saturation is None else saturation
        resolved_sfx = self.video_sound_effects if sound_effects is None else sound_effects
        resolved_soft = self.video_sound_effects_softness if sound_effects_softness is None else sound_effects_softness
        async with self._control_lock:
            await self.send_command(
                build_video_mode_h66a0(
                    game_mode=bool(resolved_game),
                    picture_preset=resolved_preset,
                    saturation=int(resolved_saturation),
                    sound_effects=bool(resolved_sfx),
                    sound_effects_softness=int(resolved_soft),
                    reserved=int(self.video_reserved),
                )
            )
            self.color_mode = ParsedMode.VIDEO
            self.video_mode = "game" if resolved_game else "movie"
            self.video_picture_preset = resolved_preset
            self.video_sound_effects_softness = int(resolved_soft)
            self.async_set_updated_data(self.data or {})

    @property
    def video_blank_screen(self) -> bool | None:
        """0xa9 sub 0x0a byte 0, on the H66A0 family.

        Distinct from ``blank_screen_detection``, which is the H6199's own integer register --
        same feature name in the app, different models and different frames. Colliding the two
        replaced an instance attribute with a read-only property and broke every H6199 test
        that assigned to it.
        """
        values = self.video_settings.get(BLACK_SCREEN_DETECTION_SETTING)
        return bool(values[0]) if values else None

    @property
    def video_blank_screen_config(self) -> tuple[int, int, int] | None:
        """`(detection, low_brightness_seconds, same_tone_seconds)`, or None until read.

        The five bytes after the enable were once recorded here as unidentified. They are the
        same layout the H6199 uses -- h6199_command_write::blank_screen_payload -- which this
        family shares byte-for-byte: `detection` then two little-endian u16 durations in
        seconds. Confirmed against the capture, where the owner had set 22 minutes and the
        register read `02 17 00 28 05`: detection 2 (same tone), 23 s, and 0x0528 = 1320 s = 22
        minutes exactly.
        """
        values = self.video_settings.get(BLACK_SCREEN_DETECTION_SETTING)
        if not values or len(values) < 6:
            return None
        return (
            int(values[1]),
            int(values[2]) | (int(values[3]) << 8),
            int(values[4]) | (int(values[5]) << 8),
        )

    async def async_set_video_blank_screen_config(
        self,
        *,
        enabled: bool | None = None,
        detection: int | None = None,
        low_brightness_seconds: int | None = None,
        same_tone_seconds: int | None = None,
    ) -> None:
        """Change the blank-screen policy, optionally flipping the enable in the same write.

        Anything omitted keeps what the device reported, so setting one field cannot silently
        rewrite the others. `enabled` is here so choosing a detection mode while the feature is
        off can be one register write rather than two -- the device only has one register, and
        writing it twice would briefly enable the mode that was being replaced.
        """
        current = self.video_blank_screen_config
        if current is None:
            raise ValueError(
                "blank-screen register has not been read from this device yet, so its configuration cannot be changed"
            )
        mode, low, same = current
        mode = mode if detection is None else detection
        low = low if low_brightness_seconds is None else low_brightness_seconds
        same = same if same_tone_seconds is None else same_tone_seconds
        if mode not in (BLANK_SCREEN_LOW_BRIGHTNESS, BLANK_SCREEN_SAME_TONE):
            raise ValueError(f"detection must be 1 (low brightness) or 2 (same tone), got {mode}")
        for name, seconds in (("low_brightness", low), ("same_tone", same)):
            if not 0 <= seconds <= 0xFFFF:
                raise ValueError(f"{name} duration must fit a u16 of seconds, got {seconds}")
        tail = [mode, low & 0xFF, low >> 8, same & 0xFF, same >> 8]
        on = bool(self.video_blank_screen) if enabled is None else enabled
        await self._write_blank_screen(on, tail)

    async def async_set_video_blank_screen(self, enabled: bool) -> None:
        """Toggle blank-screen detection, preserving its configuration.

        The five bytes after the enable hold the policy the user set in the app. They are read
        back and written through unchanged, so this only ever flips the enable. Refuses when the
        register has not been read, rather than inventing them.
        """
        values = self.video_settings.get(BLACK_SCREEN_DETECTION_SETTING)
        if not values or len(values) < 6:
            raise ValueError(
                "blank-screen register has not been read from this device yet, so its configuration cannot be preserved"
            )
        await self._write_blank_screen(enabled, list(values[1:6]))

    async def _write_blank_screen(self, enabled: bool, tail: list[int]) -> None:
        """Write the whole `0xa9 0x0a` register: enable plus its five policy bytes.

        Shared so the enable switch and the policy controls cannot drift into writing the
        register two different ways. Restores the cached value if the write fails, so a refused
        write never leaves Home Assistant showing a setting the device does not have.
        """
        previous = self.video_settings.get(BLACK_SCREEN_DETECTION_SETTING)
        async with self._control_lock:
            self.video_settings[BLACK_SCREEN_DETECTION_SETTING] = [1 if enabled else 0, *tail]
            try:
                await self.send_command(build_black_screen_detection(enabled, tail))
                client = self._client
                if client and client.is_connected:
                    await self._async_write_packet(
                        client,
                        build_video_setting_query(BLACK_SCREEN_DETECTION_SETTING, self.model),
                    )
            except Exception:
                if previous is not None:
                    self.video_settings[BLACK_SCREEN_DETECTION_SETTING] = previous
                raise
            self.async_set_updated_data(self.data or {})

    @property
    def hdr_effect(self) -> tuple[bool, int] | None:
        """0xa9 sub 0x11 as ``(enabled, gear)``. None until the register answers.

        The second byte is a GEAR INDEX in 0..3, not a percentage -- the vendor control is a
        four-position picker. See protocol.build_hdr_effect.
        """
        decoded = parse_hdr_effect(self.video_settings.get(HDR_EFFECT_SETTING, []))
        return None if decoded is None else (decoded.enabled, decoded.level)

    async def async_set_hdr_effect(self, enabled: bool, gear: int) -> None:
        """Write sub 0x11 and confirm it by reading the register back.

        Confirmed rather than assumed, for the same reason the black-border write is: every
        0xa9 write acknowledges with a generic `33 a9 00` that echoes neither the sub-command
        nor the value, so an acknowledgement says only that the frame was accepted. Three
        writes were watched being acked and appearing not to apply on 2026-08-25; they had all
        applied, and only a read-back on a fresh connection showed it.
        """
        async with self._control_lock:
            previous = self.video_settings.get(HDR_EFFECT_SETTING)
            self.video_settings[HDR_EFFECT_SETTING] = [1 if enabled else 0, gear]
            try:
                await self.send_command(build_hdr_effect(enabled, gear))
                client = self._client
                if client and client.is_connected:
                    await self._async_write_packet(
                        client,
                        build_video_setting_query(HDR_EFFECT_SETTING, self.model),
                    )
            except Exception:
                if previous is None:
                    self.video_settings.pop(HDR_EFFECT_SETTING, None)
                else:
                    self.video_settings[HDR_EFFECT_SETTING] = previous
                raise
            self.async_set_updated_data(self.data or {})

    @property
    def ai_filter(self) -> bool | None:
        """0xa9 sub 0x10 byte 0, or None until the register answers.

        A BLE register, despite the feature looking cloud-shaped: both the read and the app's
        writes are on the wire.
        """
        values = self.video_settings.get(AI_FILTER_SETTING)
        return bool(values[0]) if values else None

    async def async_set_ai_filter(self, enabled: bool) -> None:
        """Write sub 0x10 and confirm it by reading the register back.

        Confirmed rather than assumed, for the same reason as the sibling 0xa9 writes: the ack
        is a generic `33 a9 00` echoing neither sub-command nor value.
        """
        previous = self.video_settings.get(AI_FILTER_SETTING)
        if previous is None or len(previous) < 9:
            raise ValueError(
                "AI-filter register has not been read from this device yet, so the selected filter cannot be preserved"
            )
        # Bytes 1..8 are the selected filter, which the app builds from a CLOUD definition. We
        # cannot reconstruct one, so the only safe write hands back exactly what was read.
        params = bytes(previous[1:9])
        async with self._control_lock:
            self.video_settings[AI_FILTER_SETTING] = [1 if enabled else 0, *previous[1:]]
            try:
                await self.send_command(build_ai_filter(enabled, params))
                client = self._client
                if client and client.is_connected:
                    await self._async_write_packet(
                        client,
                        build_video_setting_query(AI_FILTER_SETTING, self.model),
                    )
            except Exception:
                self.video_settings[AI_FILTER_SETTING] = previous
                raise
            self.async_set_updated_data(self.data or {})

    async def async_set_black_border_removal(self, enabled: bool) -> None:
        """Write sub 0x0b and confirm it by reading the register back.

        Confirmed rather than assumed because this is the one 0xa9 write here, and a device
        that accepts a write without applying it is a shape we have already met on this
        surface (sub 0x01 does exactly that).
        """
        async with self._control_lock:
            previous = self.video_settings.get(BLACK_BORDER_REMOVAL_SETTING)
            self.video_settings[BLACK_BORDER_REMOVAL_SETTING] = [int(enabled)]
            try:
                await self.send_command(build_black_border_removal(enabled))
                client = self._client
                if client and client.is_connected:
                    await self._async_write_packet(
                        client,
                        build_video_setting_query(BLACK_BORDER_REMOVAL_SETTING, self.model),
                    )
            except Exception:
                if previous is None:
                    self.video_settings.pop(BLACK_BORDER_REMOVAL_SETTING, None)
                else:
                    self.video_settings[BLACK_BORDER_REMOVAL_SETTING] = previous
                raise
            self.async_set_updated_data(self.data or {})
