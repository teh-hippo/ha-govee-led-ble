# This is a generated file! Please edit source .ksy file and use kaitai-struct-compiler to rebuild
# type: ignore

import kaitaistruct
from kaitaistruct import ReadWriteKaitaiStruct, KaitaiStream, BytesIO


if getattr(kaitaistruct, 'API_VERSION', (0, 9)) < (0, 11):
    raise Exception("Incompatible Kaitai Struct Python API: 0.11 or later is required, but you have %s" % (kaitaistruct.__version__))

class H6199WifiProvision(ReadWriteKaitaiStruct):
    """H6199 20-byte Wi-Fi fragment. The final byte is the XOR of bytes 0 through 18.
    """
    def __init__(self, _io=None, _parent=None, _root=None):
        super(H6199WifiProvision, self).__init__(_io)
        self._parent = _parent
        self._root = _root or self

    def _read(self):
        self.header = self._io.read_bytes(1)
        if not self.header == b"\xA1":
            raise kaitaistruct.ValidationNotEqualError(b"\xA1", self.header, self._io, u"/seq/0")
        self.sub_opcode = self._io.read_u1()
        if not self.sub_opcode == 17:
            raise kaitaistruct.ValidationNotEqualError(17, self.sub_opcode, self._io, u"/seq/1")
        self.index = self._io.read_u1()
        self.payload = self._io.read_bytes(16)
        self.checksum = self._io.read_u1()
        self._dirty = False


    def _fetch_instances(self):
        pass


    def _write__seq(self, io=None):
        super(H6199WifiProvision, self)._write__seq(io)
        self._io.write_bytes(self.header)
        self._io.write_u1(self.sub_opcode)
        self._io.write_u1(self.index)
        self._io.write_bytes(self.payload)
        self._io.write_u1(self.checksum)


    def _check(self):
        if len(self.header) != 1:
            raise kaitaistruct.ConsistencyError(u"header", 1, len(self.header))
        if not self.header == b"\xA1":
            raise kaitaistruct.ValidationNotEqualError(b"\xA1", self.header, None, u"/seq/0")
        if not self.sub_opcode == 17:
            raise kaitaistruct.ValidationNotEqualError(17, self.sub_opcode, None, u"/seq/1")
        if len(self.payload) != 16:
            raise kaitaistruct.ConsistencyError(u"payload", 16, len(self.payload))
        self._dirty = False

    @property
    def data_frame_count(self):
        if hasattr(self, '_m_data_frame_count'):
            return self._m_data_frame_count

        if self.index == 0:
            pass
            self._m_data_frame_count = KaitaiStream.byte_array_index(self.payload, 0)

        return getattr(self, '_m_data_frame_count', None)

    def _invalidate_data_frame_count(self):
        del self._m_data_frame_count
    @property
    def is_header(self):
        if hasattr(self, '_m_is_header'):
            return self._m_is_header

        self._m_is_header = self.index == 0
        return getattr(self, '_m_is_header', None)

    def _invalidate_is_header(self):
        del self._m_is_header
    @property
    def is_terminator(self):
        if hasattr(self, '_m_is_terminator'):
            return self._m_is_terminator

        self._m_is_terminator = self.index == 255
        return getattr(self, '_m_is_terminator', None)

    def _invalidate_is_terminator(self):
        del self._m_is_terminator

