"""In-memory, protocol-accurate Govee BLE device simulator.

The inverse of :mod:`custom_components.ha_govee_led_ble.protocol`: decode the
``0x33`` command frames the integration writes (mutating internal state) and
answer the ``aa 01/04/05`` query frames with status frames that
the generated status decoder reconstructs into the coordinator's optimistic
fields. Experimental timer writes (``0x33 11/12/23``) update timer state and the
matching ``aa 11/12/23`` queries echo it back. Paired with
:class:`FakeGoveeClient`, the real coordinator and entities run end-to-end with
no hardware, and removing the transport patch restores real hardware behaviour
unchanged.
"""

from collections.abc import Callable
from typing import Literal

from custom_components.ha_govee_led_ble.const import MUSIC_MODES, get_profile
from custom_components.ha_govee_led_ble.protocol import (
    ALL_SEGMENTS_MASK,
    BRIGHTNESS_PACKET_TYPE,
    COLOR_MODE_MUSIC,
    COLOR_MODE_SCENE,
    COLOR_MODE_STATIC,
    COLOR_MODE_VIDEO,
    COLOR_PACKET_TYPE,
    COMMAND_HEADER,
    DISPLAY_SETTING_BLANK_SCREEN,
    DISPLAY_SETTING_PACKET_TYPE,
    DISPLAY_SETTING_WHITE_BALANCE,
    FIRMWARE_PACKET_TYPE,
    HARDWARE_PACKET_TYPE,
    POWER_PACKET_TYPE,
    RELATIVE_BRIGHTNESS_PACKET_TYPE,
    SCENE_EFFECT_BY_ID,
    STATIC_SUB_BRIGHTNESS,
    STATIC_SUB_COLOR,
    STATUS_HEADER,
    build_packet,
    parse_static_write,
)

RGB = tuple[int, int, int]
NotifyCallback = Callable[[object, bytearray], None]
ColorMode = Literal["rgb", "ct", "white", "scene", "video", "music"]

_COLOR_FLAG = 0x01
# Human-readable label for the sim's current music mode (inspection only; the integration
# tracks music as a slug in ``music_mode``, not as an effect string).
_MUSIC_LABEL_BY_ID = {code: f"music: {name}" for name, code in MUSIC_MODES.items()}
# op 0xa3 on a write is the multi-effect register (command_write::multi_effect_cmd); the same
# byte as a query domain reads it back. Distinct from protocol.MULTI_PACKET_PREFIX, which is the
# 0xa3 *fragment* header and arrives as frame[0] rather than as a command action.
MULTI_EFFECT_ACTION = 0xA3
# Experimental timer command/reply actions (mirror protocol's 0x11/0x12/0x23).
SLEEP_TIMER_ACTION = 0x11
WAKEUP_TIMER_ACTION = 0x12
SCHEDULE_TIMER_ACTION = 0x23
SCHEDULE_ENABLE_BIT = 0x80
SCHEDULE_SLOTS = 4


class GoveeDeviceSim:
    """Model-parametrised Govee strip state machine driven by wire frames."""

    def __init__(self, model: str = "H617A") -> None:
        self.model = model
        self.profile = get_profile(model)
        self.is_on = False
        self.brightness_pct = 100
        self.firmware = "1.10.04" if model == "H6199" else "3.02.24"
        self.hardware = "3.02.01" if model == "H6199" else "3.01.01"
        self.color_mode: ColorMode = "rgb"
        self.rgb_color: RGB = (255, 255, 255)
        self.color_temp_kelvin: int | None = None
        self.scene_code: int | None = None
        self.effect: str | None = None
        self.video_full_screen = True
        self.video_game = False
        self.video_saturation = 100
        self.video_sound_effects = False
        self.video_sound_effects_softness = 100
        self.video_white_balance: tuple[int, int] | None = None
        self.relative_brightness: list[int] | None = None
        self.blank_screen: bool | None = None
        self.music_mode_id: int | None = None
        self.music_sensitivity = 100
        self.music_calm = False
        self.music_color: RGB | None = None
        self.white_brightness = 100
        self.multi_effect_flag = 0
        count = self.profile.segment_count
        self.segments: list[RGB] = [self.rgb_color] * count
        self.segment_brightness: list[int] = [100] * count
        self.sleep_timer: tuple[int, int, int, int] | None = (0, 50, 16, 16) if self.profile.supports_timers else None
        self.wakeup_timer: tuple[int, int, int, int, int, int] | None = (
            (0, 100, 17, 1, 0, 29) if self.profile.supports_timers else None
        )
        self.schedule_timers: list[tuple[int, int, int, int] | None] = [None] * SCHEDULE_SLOTS

    def handle_write(self, data: bytes) -> list[bytes]:
        """Apply a command or answer a query; return status frames to notify."""
        frame = bytes(data)
        if len(frame) < 2:
            return []
        if frame[0] == STATUS_HEADER:
            return self._reply(frame[1])
        if frame[0] == COMMAND_HEADER:
            self._apply_command(frame)
        # 0xA3 multi-frame scene bodies are inert here: the trailing 33 05 04
        # command activates the scene.
        return []

    def _reply(self, domain: int) -> list[bytes]:
        if domain == POWER_PACKET_TYPE:
            return [build_packet(STATUS_HEADER, POWER_PACKET_TYPE, [int(self.is_on)])]
        if domain == BRIGHTNESS_PACKET_TYPE:
            return [build_packet(STATUS_HEADER, BRIGHTNESS_PACKET_TYPE, [self.brightness_pct])]
        if domain == COLOR_PACKET_TYPE:
            return [build_packet(STATUS_HEADER, COLOR_PACKET_TYPE, self._color_mode_payload())]
        if domain == FIRMWARE_PACKET_TYPE:
            return [build_packet(STATUS_HEADER, FIRMWARE_PACKET_TYPE, list(self.firmware.encode("ascii")))]
        if domain == HARDWARE_PACKET_TYPE:
            return [build_packet(STATUS_HEADER, HARDWARE_PACKET_TYPE, [0x03, *self.hardware.encode("ascii")])]
        if domain == MULTI_EFFECT_ACTION:
            return [build_packet(STATUS_HEADER, MULTI_EFFECT_ACTION, [self.multi_effect_flag])]
        if domain == SLEEP_TIMER_ACTION and self.sleep_timer is not None:
            return [build_packet(STATUS_HEADER, SLEEP_TIMER_ACTION, list(self.sleep_timer))]
        if domain == WAKEUP_TIMER_ACTION and self.wakeup_timer is not None:
            return [build_packet(STATUS_HEADER, WAKEUP_TIMER_ACTION, list(self.wakeup_timer))]
        if domain == SCHEDULE_TIMER_ACTION:
            # The real aa 23 reply is the whole table: 0xff prefix + four 4-byte slot records.
            table = [0xFF]
            for record in self.schedule_timers:
                table.extend(record if record is not None else (0, 0, 0, 0))
            return [build_packet(STATUS_HEADER, SCHEDULE_TIMER_ACTION, table)]
        return []

    def _color_mode_payload(self) -> list[int]:
        if self.color_mode == "scene":
            code = self.scene_code or 0
            width = max(1, (code.bit_length() + 7) // 8)
            return [COLOR_MODE_SCENE, *code.to_bytes(width, "little")]
        if self.color_mode == "video":
            return [
                COLOR_MODE_VIDEO,
                int(self.video_full_screen),
                int(self.video_game),
                self.video_saturation,
                int(self.video_sound_effects),
                self.video_sound_effects_softness,
            ]
        if self.color_mode == "music":
            payload = [COLOR_MODE_MUSIC, self.music_mode_id or 0, self.music_sensitivity, int(self.music_calm)]
            if self.music_color is not None:
                payload += [_COLOR_FLAG, *self.music_color]
            return payload
        if not self.profile.static_readback_echoes_color:
            # status_reply::cm_static. The device echoes only the mode and the 33 a3 register;
            # colour, kelvin and brightness are write-only and are never read back.
            return [COLOR_MODE_STATIC, self.multi_effect_flag]
        if self.color_mode == "white":
            return [COLOR_MODE_STATIC, STATIC_SUB_BRIGHTNESS, self.white_brightness]
        # A colour-temp state reads back as its white-point RGB with no kelvin field (live-confirmed
        # 2026-07-10); the coordinator recognises that and keeps CT. rgb and ct both report the rgb.
        return [COLOR_MODE_STATIC, STATIC_SUB_COLOR, *self.rgb_color]

    def _apply_command(self, frame: bytes) -> None:
        action = frame[1]
        if action == POWER_PACKET_TYPE:
            self.is_on = bool(frame[2])
        elif action == BRIGHTNESS_PACKET_TYPE:
            self.brightness_pct = frame[2]
        elif action == COLOR_PACKET_TYPE:
            self._apply_color_command(frame)
        elif action == DISPLAY_SETTING_PACKET_TYPE:
            self._apply_display_setting(frame)
        elif action == RELATIVE_BRIGHTNESS_PACKET_TYPE and self.profile.supports_relative_brightness:
            # h6199_command_write::relative_brightness_body: the count sits after the head byte,
            # and reading the head as the count truncates the payload to one edge.
            self.relative_brightness = list(frame[4 : 4 + frame[3]])
        elif action == MULTI_EFFECT_ACTION:
            self.multi_effect_flag = frame[2]
        elif action == SLEEP_TIMER_ACTION:
            self.sleep_timer = (frame[2], frame[3], frame[4], frame[5])
        elif action == WAKEUP_TIMER_ACTION:
            self.wakeup_timer = (frame[2], frame[3], frame[4], frame[5], frame[6], frame[7])
        elif action == SCHEDULE_TIMER_ACTION:
            self._apply_schedule_command(frame)

    def _apply_display_setting(self, frame: bytes) -> None:
        """Route a 33 a9 write on its selector (h6199_command_write::display_setting_body).

        The selector is what tells the two settings apart. Reading every frame on this register as
        white balance records a blank-screen write as a gain pair, which is a state nothing set.
        """
        setting, length = frame[2], frame[3]
        payload = frame[4 : 4 + length]
        if setting == DISPLAY_SETTING_WHITE_BALANCE and self.profile.supports_white_balance:
            self.video_white_balance = (payload[1], payload[2])
        elif setting == DISPLAY_SETTING_BLANK_SCREEN and self.profile.supports_blank_screen:
            self.blank_screen = bool(payload[0])

    def _apply_schedule_command(self, frame: bytes) -> None:
        index = frame[2]
        if not 0 <= index < SCHEDULE_SLOTS:
            return
        # A cleared slot (enable bit low) drops the record so queries stop reporting it.
        if frame[3] & SCHEDULE_ENABLE_BIT:
            self.schedule_timers[index] = (frame[3], frame[4], frame[5], frame[6])
        else:
            self.schedule_timers[index] = None

    def _apply_color_command(self, frame: bytes) -> None:
        sub = frame[2]
        if sub == COLOR_MODE_SCENE:
            self._apply_scene(frame)
        elif sub == COLOR_MODE_VIDEO and self.profile.supports_video_mode:
            self._apply_video(frame)
        elif sub == COLOR_MODE_MUSIC:
            self._apply_music(frame)
        elif sub == COLOR_MODE_STATIC:
            self._apply_static(frame)

    def _apply_static(self, frame: bytes) -> None:
        static = parse_static_write(frame)
        if static is None:
            return
        if static.brightness_pct is not None:
            self._apply_white(static.brightness_pct, static.segment_mask)
        elif static.kelvin is not None:
            self._set_color_temp(static.kelvin, static.kelvin_companion_rgb or (0, 0, 0))
        elif static.rgb is not None and not static.whole_strip:
            self._fill_segments(static.rgb, static.segment_mask)
        elif static.rgb is not None:
            self._set_rgb(static.rgb)

    def _set_rgb(self, rgb: RGB) -> None:
        self.color_mode = "rgb"
        self.rgb_color = rgb
        self.color_temp_kelvin = None
        self.effect = None
        self._fill_segments(rgb, ALL_SEGMENTS_MASK)

    def _set_color_temp(self, kelvin: int, preview: RGB) -> None:
        self.color_mode = "ct"
        self.color_temp_kelvin = kelvin
        self.rgb_color = preview
        self.effect = None

    def _apply_white(self, brightness: int, mask: int) -> None:
        self.effect = None
        self._fill_segment_brightness(brightness, mask)
        if mask == ALL_SEGMENTS_MASK:
            self.color_mode = "white"
            self.white_brightness = brightness

    def _apply_scene(self, frame: bytes) -> None:
        code_bytes = frame[3:19].rstrip(b"\x00") or b"\x00"
        self.scene_code = int.from_bytes(code_bytes, "little")
        self.color_mode = "scene"
        self.color_temp_kelvin = None
        self.effect = SCENE_EFFECT_BY_ID.get(self.scene_code)

    def _apply_video(self, frame: bytes) -> None:
        self.color_mode = "video"
        self.color_temp_kelvin = None
        self.video_full_screen = bool(frame[3])
        self.video_game = bool(frame[4])
        self.video_saturation = frame[5]
        self.video_sound_effects = bool(frame[6])
        self.video_sound_effects_softness = frame[7]
        self.effect = "video: game" if self.video_game else "video: movie"

    def _apply_music(self, frame: bytes) -> None:
        self.color_mode = "music"
        self.color_temp_kelvin = None
        self.music_mode_id = frame[3]
        self.music_sensitivity = frame[4]
        self.music_calm = bool(frame[5])
        self.music_color = (frame[7], frame[8], frame[9]) if frame[6] == _COLOR_FLAG else None
        self.effect = _MUSIC_LABEL_BY_ID.get(self.music_mode_id)

    def _fill_segments(self, rgb: RGB, mask: int) -> None:
        for index in range(len(self.segments)):
            if mask & (1 << index):
                self.segments[index] = rgb

    def _fill_segment_brightness(self, brightness: int, mask: int) -> None:
        for index in range(len(self.segment_brightness)):
            if mask & (1 << index):
                self.segment_brightness[index] = brightness


class FakeGoveeClient:
    """Minimal bleak-facing adapter that drives a GoveeDeviceSim."""

    def __init__(self, sim: GoveeDeviceSim) -> None:
        self.sim = sim
        self._connected = True
        self._notify: NotifyCallback | None = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def start_notify(self, uuid: str, callback: NotifyCallback) -> None:
        self._notify = callback

    async def write_gatt_char(self, uuid: str, data: bytes, response: bool = False) -> None:
        replies = self.sim.handle_write(bytes(data))
        if self._notify is None:
            return
        for reply in replies:
            self._notify(None, bytearray(reply))

    async def disconnect(self) -> None:
        self._connected = False
