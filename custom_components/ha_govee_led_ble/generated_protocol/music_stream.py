# This is a generated file! Please edit source .ksy file and use kaitai-struct-compiler to rebuild
# type: ignore

import kaitaistruct
from kaitaistruct import ReadWriteKaitaiStruct, KaitaiStream, BytesIO
from custom_components.ha_govee_led_ble.generated_protocol import govee_shared


if getattr(kaitaistruct, 'API_VERSION', (0, 9)) < (0, 11):
    raise Exception("Incompatible Kaitai Struct Python API: 0.11 or later is required, but you have %s" % (kaitaistruct.__version__))

class MusicStream(ReadWriteKaitaiStruct):
    """H617A seven-byte microphone stream frame. The final byte is the low eight bits of the sum of bytes 0 through 5.
    """
    def __init__(self, _io=None, _parent=None, _root=None):
        super(MusicStream, self).__init__(_io)
        self._parent = _parent
        self._root = _root or self

    def _read(self):
        self.opcode = self._io.read_bytes(1)
        if not self.opcode == b"\xA5":
            raise kaitaistruct.ValidationNotEqualError(b"\xA5", self.opcode, self._io, u"/seq/0")
        self.stream_sub = self._io.read_bytes(1)
        if not self.stream_sub == b"\x02":
            raise kaitaistruct.ValidationNotEqualError(b"\x02", self.stream_sub, self._io, u"/seq/1")
        self.stream_mode = self._io.read_bytes(1)
        if not self.stream_mode == b"\x83":
            raise kaitaistruct.ValidationNotEqualError(b"\x83", self.stream_mode, self._io, u"/seq/2")
        self.colour = govee_shared.GoveeShared.Rgb(self._io)
        self.colour._read()
        self.checksum = self._io.read_u1()
        self._dirty = False


    def _fetch_instances(self):
        pass
        self.colour._fetch_instances()


    def _write__seq(self, io=None):
        super(MusicStream, self)._write__seq(io)
        self._io.write_bytes(self.opcode)
        self._io.write_bytes(self.stream_sub)
        self._io.write_bytes(self.stream_mode)
        self.colour._write__seq(self._io)
        self._io.write_u1(self.checksum)


    def _check(self):
        if len(self.opcode) != 1:
            raise kaitaistruct.ConsistencyError(u"opcode", 1, len(self.opcode))
        if not self.opcode == b"\xA5":
            raise kaitaistruct.ValidationNotEqualError(b"\xA5", self.opcode, None, u"/seq/0")
        if len(self.stream_sub) != 1:
            raise kaitaistruct.ConsistencyError(u"stream_sub", 1, len(self.stream_sub))
        if not self.stream_sub == b"\x02":
            raise kaitaistruct.ValidationNotEqualError(b"\x02", self.stream_sub, None, u"/seq/1")
        if len(self.stream_mode) != 1:
            raise kaitaistruct.ConsistencyError(u"stream_mode", 1, len(self.stream_mode))
        if not self.stream_mode == b"\x83":
            raise kaitaistruct.ValidationNotEqualError(b"\x83", self.stream_mode, None, u"/seq/2")
        self._dirty = False

    @property
    def checksum_expected(self):
        if hasattr(self, '_m_checksum_expected'):
            return self._m_checksum_expected

        self._m_checksum_expected = (((((165 + 2) + 131) + self.colour.r) + self.colour.g) + self.colour.b) % 256
        return getattr(self, '_m_checksum_expected', None)

    def _invalidate_checksum_expected(self):
        del self._m_checksum_expected

