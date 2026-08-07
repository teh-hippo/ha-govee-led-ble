# This is a generated file! Please edit source .ksy file and use kaitai-struct-compiler to rebuild
# type: ignore

import kaitaistruct
from kaitaistruct import ReadWriteKaitaiStruct, KaitaiStream, BytesIO
from enum import IntEnum


if getattr(kaitaistruct, 'API_VERSION', (0, 9)) < (0, 11):
    raise Exception("Incompatible Kaitai Struct Python API: 0.11 or later is required, but you have %s" % (kaitaistruct.__version__))

class H6199WifiResult(ReadWriteKaitaiStruct):
    """H6199 20-byte Wi-Fi association result. The final byte is the XOR of bytes 0 through 18.
    """

    class Outcome(IntEnum):
        associated = 0
        not_connected = 1
    def __init__(self, _io=None, _parent=None, _root=None):
        super(H6199WifiResult, self).__init__(_io)
        self._parent = _parent
        self._root = _root or self

    def _read(self):
        self.header = self._io.read_bytes(1)
        if not self.header == b"\xEE":
            raise kaitaistruct.ValidationNotEqualError(b"\xEE", self.header, self._io, u"/seq/0")
        self.sub_opcode = self._io.read_u1()
        if not self.sub_opcode == 17:
            raise kaitaistruct.ValidationNotEqualError(17, self.sub_opcode, self._io, u"/seq/1")
        self.status = KaitaiStream.resolve_enum(H6199WifiResult.Outcome, self._io.read_u1())
        self._unnamed3 = self._io.read_bytes(16)
        self.checksum = self._io.read_u1()
        self._dirty = False


    def _fetch_instances(self):
        pass


    def _write__seq(self, io=None):
        super(H6199WifiResult, self)._write__seq(io)
        self._io.write_bytes(self.header)
        self._io.write_u1(self.sub_opcode)
        self._io.write_u1(int(self.status))
        self._io.write_bytes(self._unnamed3)
        self._io.write_u1(self.checksum)


    def _check(self):
        if len(self.header) != 1:
            raise kaitaistruct.ConsistencyError(u"header", 1, len(self.header))
        if not self.header == b"\xEE":
            raise kaitaistruct.ValidationNotEqualError(b"\xEE", self.header, None, u"/seq/0")
        if not self.sub_opcode == 17:
            raise kaitaistruct.ValidationNotEqualError(17, self.sub_opcode, None, u"/seq/1")
        if len(self._unnamed3) != 16:
            raise kaitaistruct.ConsistencyError(u"_unnamed3", 16, len(self._unnamed3))
        self._dirty = False


