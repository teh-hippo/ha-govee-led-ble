"""A protocol-accurate stand-in for a Govee strip, driven by real wire frames.

The inverse of :mod:`custom_components.ha_govee_led_ble.generated_protocol_adapter`:
decode the ``0x33`` command frames the integration writes, mutate state, and answer
``0xaa`` queries with status frames the generated decoder reconstructs.

It exists because the encryption tests need a peer that performs the *device* half of
the handshake -- deriving its own key, running its own frame counter -- which a
``MagicMock`` cannot do. Everything outside that need is deliberately thin: power,
brightness and colour are enough to prove a command survived the sealed path.
"""

from __future__ import annotations

from collections.abc import Callable

from custom_components.ha_govee_led_ble.generated_protocol.status_reply import StatusReply
from custom_components.ha_govee_led_ble.generated_protocol_adapter import parse_command
from custom_components.ha_govee_led_ble.transport import xor_checksum

RGB = tuple[int, int, int]
NotifyCallback = Callable[[object, bytearray], None]

COMMAND_HEADER = 0x33
STATUS_HEADER = 0xAA


def status_packet(domain: int, params: list[int]) -> bytes:
    """One 20-byte ``0xaa`` status frame, zero-padded and XOR-checksummed."""
    payload = bytearray([STATUS_HEADER, domain, *params][:19])
    payload.extend(b"\x00" * (19 - len(payload)))
    payload.append(xor_checksum(payload))
    return bytes(payload)


class GoveeDeviceDouble:
    """Minimal strip state machine driven by the frames the integration really sends."""

    def __init__(self, model: str = "H617A") -> None:
        self.model = model
        self.is_on = False
        self.brightness_pct = 100
        self.rgb_color: RGB = (255, 255, 255)
        self.firmware = "3.02.24"
        self.hardware = "3.01.01"
        self.commands: list[bytes] = []

    def handle_write(self, data: bytes) -> list[bytes]:
        """Apply a command or answer a query; return the frames to notify back."""
        frame = bytes(data)
        if len(frame) < 2:
            return []
        if frame[0] == STATUS_HEADER:
            return self._reply(frame[1])
        if frame[0] == COMMAND_HEADER:
            self.commands.append(frame)
            self._apply(frame)
        return []

    def _apply(self, frame: bytes) -> None:
        parsed = parse_command(frame, self.model)
        if parsed is None:
            return
        opcode = getattr(parsed.opcode, "name", None)
        body = parsed.body
        if opcode == "power":
            self.is_on = bool(body.is_on)
        elif opcode == "brightness":
            self.brightness_pct = int(body.percent)

    def _reply(self, domain: int) -> list[bytes]:
        if domain == int(StatusReply.AaDomain.power):
            return [status_packet(domain, [int(self.is_on)])]
        if domain == int(StatusReply.AaDomain.brightness):
            return [status_packet(domain, [self.brightness_pct])]
        if domain == int(StatusReply.AaDomain.fw_version):
            return [status_packet(domain, list(self.firmware.encode("ascii")))]
        if domain == int(StatusReply.AaDomain.hw_version):
            return [status_packet(domain, [0x03, *self.hardware.encode("ascii")])]
        return []


class FakeGoveeClient:
    """A bleak-shaped client wired straight to a :class:`GoveeDeviceDouble`.

    Plaintext only. The encryption tests wrap their own client around the double instead,
    because there the point is the sealed path.
    """

    def __init__(self, strip: GoveeDeviceDouble) -> None:
        self.strip = strip
        self.is_connected = True
        self.mtu_size = 512
        self.frames: list[bytes] = []
        self._notify: NotifyCallback | None = None

    @property
    def services(self) -> object:
        class _NoMarker:
            def get_characteristic(self, _uuid: str) -> None:
                return None

        return _NoMarker()

    async def start_notify(self, _uuid: str, callback: NotifyCallback) -> None:
        self._notify = callback

    async def disconnect(self) -> None:
        self.is_connected = False

    async def write_gatt_char(self, _uuid: str, data: bytes, response: bool = False) -> None:
        frame = bytes(data)
        self.frames.append(frame)
        for reply in self.strip.handle_write(frame):
            if self._notify is not None:
                self._notify(None, bytearray(reply))
