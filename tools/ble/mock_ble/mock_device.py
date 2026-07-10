"""In-memory, protocol-accurate Govee BLE device simulator.

The inverse of :mod:`custom_components.ha_govee_led_ble.protocol`: decode the
``0x33`` command frames the integration writes (mutating internal state) and
answer the ``aa 01/04/05`` query frames with status frames that
``parse_color_mode_response`` reconstructs into the coordinator's optimistic
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
    BRIGHTNESS_PACKET_TYPE,
    COLOR_MODE_MUSIC,
    COLOR_MODE_SCENE,
    COLOR_MODE_STATIC,
    COLOR_MODE_VIDEO,
    COLOR_PACKET_TYPE,
    COMMAND_HEADER,
    FIRMWARE_PACKET_TYPE,
    HARDWARE_PACKET_TYPE,
    POWER_PACKET_TYPE,
    SCENE_EFFECT_BY_ID,
    STATUS_HEADER,
    build_packet,
)

RGB = tuple[int, int, int]
NotifyCallback = Callable[[object, bytearray], None]
ColorMode = Literal["rgb", "ct", "white", "scene", "video", "music"]
CtReadback = Literal["rgb", "sticky"]

ALL_SEGMENTS_MASK = 0x7FFF
STATIC_SUB = 0x01
WHITE_SUB = 0x02
_COLOR_FLAG = 0x01
# Human-readable label for the sim's current music mode (inspection only; the integration
# tracks music as a slug in ``music_mode``, not as an effect string).
_MUSIC_LABEL_BY_ID = {code: f"music: {name}" for name, code in MUSIC_MODES.items()}
_WHITE_BALANCE_ACTION = 0xA9
# Mirror the red endpoints of protocol.build_video_white_balance so the
# write-only calibration decodes back to a 0-100 percentage.
_WB_RED_MIN, _WB_RED_MAX = 0x07, 0x15
# Experimental timer command/reply actions (mirror protocol's 0x11/0x12/0x23).
SLEEP_TIMER_ACTION = 0x11
WAKEUP_TIMER_ACTION = 0x12
SCHEDULE_TIMER_ACTION = 0x23
SCHEDULE_ENABLE_BIT = 0x80
SCHEDULE_SLOTS = 4


class GoveeDeviceSim:
    """Model-parametrised Govee strip state machine driven by wire frames."""

    def __init__(self, model: str = "H617A", *, ct_readback: CtReadback = "rgb") -> None:
        self.model = model
        self.profile = get_profile(model)
        self.ct_readback = ct_readback
        self.is_on = False
        self.brightness_pct = 100
        # Identity replies for the aa 06/aa 07 handshake (H617A live values; VAL).
        self.firmware = "3.02.24"
        self.hardware = "3.01.01"
        self.color_mode: ColorMode = "rgb"
        self.rgb_color: RGB = (255, 255, 255)
        self.color_temp_kelvin: int | None = None
        self.scene_code: int | None = None
        self.effect: str | None = None
        self.video_full_screen = True
        self.video_game = False
        self.video_saturation = 100
        self.video_sound_effects = False
        self.video_sound_effects_softness = 0
        self.video_white_balance: int | None = None
        self.music_mode_id: int | None = None
        self.music_sensitivity = 100
        self.music_calm = False
        self.music_color: RGB | None = None
        self.white_brightness = 100
        count = self.profile.segment_count
        self.segments: list[RGB] = [self.rgb_color] * count
        self.segment_brightness: list[int] = [100] * count
        self.sleep_timer: tuple[int, int, int, int] | None = None
        self.wakeup_timer: tuple[int, int, int, int, int, int] | None = None
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
            return [build_packet(STATUS_HEADER, HARDWARE_PACKET_TYPE, list(self.hardware.encode("ascii")))]
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
        if self.color_mode == "white":
            return [COLOR_MODE_STATIC, WHITE_SUB, self.white_brightness]
        if self.color_mode == "ct" and self.ct_readback == "sticky":
            # OPEN: pending live capture. The real aa 05 reply for a colour-temp
            # state is unconfirmed; "sticky" emits an unhandled static sub-mode so
            # parse_color_mode_response returns empty and the coordinator keeps its
            # optimistic kelvin rather than the sim inventing a frame.
            return [COLOR_MODE_STATIC, 0x00]
        # rgb, and ct with the default "rgb" read-back: OPEN — colour-temp kelvin
        # is not reconstructable today, so fall back to the last whole-strip colour.
        return [COLOR_MODE_STATIC, STATIC_SUB, *self.rgb_color]

    def _apply_command(self, frame: bytes) -> None:
        action = frame[1]
        if action == POWER_PACKET_TYPE:
            self.is_on = bool(frame[2])
        elif action == BRIGHTNESS_PACKET_TYPE:
            self.brightness_pct = frame[2]
        elif action == COLOR_PACKET_TYPE:
            self._apply_color_command(frame)
        elif action == _WHITE_BALANCE_ACTION and self.profile.supports_video_mode:
            self.video_white_balance = round((frame[5] - _WB_RED_MIN) / (_WB_RED_MAX - _WB_RED_MIN) * 100)
        elif action == SLEEP_TIMER_ACTION:
            self.sleep_timer = (frame[2], frame[3], frame[4], frame[5])
        elif action == WAKEUP_TIMER_ACTION:
            self.wakeup_timer = (frame[2], frame[3], frame[4], frame[5], frame[6], frame[7])
        elif action == SCHEDULE_TIMER_ACTION:
            self._apply_schedule_command(frame)

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
        if frame[3] == WHITE_SUB:
            self._apply_white(frame[4], frame[5] | (frame[6] << 8))
            return
        rgb = (frame[4], frame[5], frame[6])
        kelvin = (frame[7] << 8) | frame[8]
        mask = frame[12] | (frame[13] << 8)
        if rgb == (0, 0, 0) and kelvin:
            self._set_color_temp(kelvin, (frame[9], frame[10], frame[11]))
        elif mask != ALL_SEGMENTS_MASK:
            self._fill_segments(rgb, mask)
        else:
            self._set_rgb(rgb)

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
        if self.video_sound_effects:
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
