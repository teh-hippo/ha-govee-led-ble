# This is a generated file! Please edit source .ksy file and use kaitai-struct-compiler to rebuild
# type: ignore

import kaitaistruct
from kaitaistruct import ReadWriteKaitaiStruct, KaitaiStream, BytesIO
from custom_components.ha_govee_led_ble.generated_protocol import govee_shared
from enum import IntEnum


if getattr(kaitaistruct, 'API_VERSION', (0, 9)) < (0, 11):
    raise Exception("Incompatible Kaitai Struct Python API: 0.11 or later is required, but you have %s" % (kaitaistruct.__version__))

class GoveeCommon(ReadWriteKaitaiStruct):

    class MusicMode(IntEnum):
        rhythm = 3
        spectrum = 4
        energetic = 5
        rolling = 6
        bloom = 48
        shiny = 49
        separation = 50
        hopping = 51
        piano_keys = 52
        fountain = 53
        day_and_night = 55
    def __init__(self, _io=None, _parent=None, _root=None):
        super(GoveeCommon, self).__init__(_io)
        self._parent = _parent
        self._root = _root or self

    def _read(self):
        pass
        self._dirty = False


    def _fetch_instances(self):
        pass


    def _write__seq(self, io=None):
        super(GoveeCommon, self)._write__seq(io)


    def _check(self):
        self._dirty = False

    class A3Header(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(GoveeCommon.A3Header, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.marker = self._io.read_bytes(1)
            if not self.marker == b"\x01":
                raise kaitaistruct.ValidationNotEqualError(b"\x01", self.marker, self._io, u"/types/a3_header/seq/0")
            self.linecount = self._io.read_u1()
            if not self.linecount >= 2:
                raise kaitaistruct.ValidationLessThanError(2, self.linecount, self._io, u"/types/a3_header/seq/1")
            self._dirty = False


        def _fetch_instances(self):
            pass


        def _write__seq(self, io=None):
            super(GoveeCommon.A3Header, self)._write__seq(io)
            self._io.write_bytes(self.marker)
            self._io.write_u1(self.linecount)


        def _check(self):
            if len(self.marker) != 1:
                raise kaitaistruct.ConsistencyError(u"marker", 1, len(self.marker))
            if not self.marker == b"\x01":
                raise kaitaistruct.ValidationNotEqualError(b"\x01", self.marker, None, u"/types/a3_header/seq/0")
            if not self.linecount >= 2:
                raise kaitaistruct.ValidationLessThanError(2, self.linecount, None, u"/types/a3_header/seq/1")
            self._dirty = False


    class DiySelector(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(GoveeCommon.DiySelector, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.code = self._io.read_u2le()
            self._dirty = False


        def _fetch_instances(self):
            pass


        def _write__seq(self, io=None):
            super(GoveeCommon.DiySelector, self)._write__seq(io)
            self._io.write_u2le(self.code)


        def _check(self):
            self._dirty = False


    class MusicSelector(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(GoveeCommon.MusicSelector, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.mode_id = KaitaiStream.resolve_enum(GoveeCommon.MusicMode, self._io.read_u1())
            self.sensitivity = self._io.read_u1()
            self.style = self._io.read_u1()
            self.manual_color_count = self._io.read_u1()
            if self.manual_color_count >= 1:
                pass
                self.rgb = govee_shared.GoveeShared.Rgb(self._io)
                self.rgb._read()

            self._dirty = False


        def _fetch_instances(self):
            pass
            if self.manual_color_count >= 1:
                pass
                self.rgb._fetch_instances()



        def _write__seq(self, io=None):
            super(GoveeCommon.MusicSelector, self)._write__seq(io)
            self._io.write_u1(int(self.mode_id))
            self._io.write_u1(self.sensitivity)
            self._io.write_u1(self.style)
            self._io.write_u1(self.manual_color_count)
            if self.manual_color_count >= 1:
                pass
                self.rgb._write__seq(self._io)



        def _check(self):
            if self.manual_color_count >= 1:
                pass

            self._dirty = False



