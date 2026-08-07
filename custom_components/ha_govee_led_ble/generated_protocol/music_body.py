# This is a generated file! Please edit source .ksy file and use kaitai-struct-compiler to rebuild
# type: ignore

import kaitaistruct
from kaitaistruct import ReadWriteKaitaiStruct, KaitaiStream, BytesIO
from custom_components.ha_govee_led_ble.generated_protocol import govee_common
from custom_components.ha_govee_led_ble.generated_protocol import govee_shared
from enum import IntEnum


if getattr(kaitaistruct, 'API_VERSION', (0, 9)) < (0, 11):
    raise Exception("Incompatible Kaitai Struct Python API: 0.11 or later is required, but you have %s" % (kaitaistruct.__version__))

class MusicBody(ReadWriteKaitaiStruct):

    class ShinyStyle(IntEnum):
        dynamic = 1380
        calm = 5190
    def __init__(self, _io=None, _parent=None, _root=None):
        super(MusicBody, self).__init__(_io)
        self._parent = _parent
        self._root = _root or self

    def _read(self):
        self.header = govee_common.GoveeCommon.A3Header(self._io)
        self.header._read()
        self.command = self._io.read_bytes(1)
        if not self.command == b"\x41":
            raise kaitaistruct.ValidationNotEqualError(b"\x41", self.command, self._io, u"/seq/1")
        self.mode = KaitaiStream.resolve_enum(govee_common.GoveeCommon.MusicMode, self._io.read_u1())
        self.num_palette = self._io.read_u1()
        self.palette = []
        for i in range(self.num_palette):
            _t_palette = govee_shared.GoveeShared.Rgb(self._io)
            try:
                _t_palette._read()
            finally:
                self.palette.append(_t_palette)

        _on = self.mode
        if _on == govee_common.GoveeCommon.MusicMode.bloom:
            pass
            self._raw_tail = self._io.read_bytes(self.tail_len)
            _io__raw_tail = KaitaiStream(BytesIO(self._raw_tail))
            self.tail = MusicBody.BloomTail(_io__raw_tail, self, self._root)
            self.tail._read()
        elif _on == govee_common.GoveeCommon.MusicMode.day_and_night:
            pass
            self._raw_tail = self._io.read_bytes(self.tail_len)
            _io__raw_tail = KaitaiStream(BytesIO(self._raw_tail))
            self.tail = MusicBody.DayAndNightTail(_io__raw_tail, self, self._root)
            self.tail._read()
        elif _on == govee_common.GoveeCommon.MusicMode.fountain:
            pass
            self._raw_tail = self._io.read_bytes(self.tail_len)
            _io__raw_tail = KaitaiStream(BytesIO(self._raw_tail))
            self.tail = MusicBody.FountainTail(_io__raw_tail, self, self._root)
            self.tail._read()
        elif _on == govee_common.GoveeCommon.MusicMode.hopping:
            pass
            self._raw_tail = self._io.read_bytes(self.tail_len)
            _io__raw_tail = KaitaiStream(BytesIO(self._raw_tail))
            self.tail = MusicBody.HoppingTail(_io__raw_tail, self, self._root)
            self.tail._read()
        elif _on == govee_common.GoveeCommon.MusicMode.piano_keys:
            pass
            self._raw_tail = self._io.read_bytes(self.tail_len)
            _io__raw_tail = KaitaiStream(BytesIO(self._raw_tail))
            self.tail = MusicBody.PianoKeysTail(_io__raw_tail, self, self._root)
            self.tail._read()
        elif _on == govee_common.GoveeCommon.MusicMode.separation:
            pass
            self._raw_tail = self._io.read_bytes(self.tail_len)
            _io__raw_tail = KaitaiStream(BytesIO(self._raw_tail))
            self.tail = MusicBody.SeparationTail(_io__raw_tail, self, self._root)
            self.tail._read()
        elif _on == govee_common.GoveeCommon.MusicMode.shiny:
            pass
            self._raw_tail = self._io.read_bytes(self.tail_len)
            _io__raw_tail = KaitaiStream(BytesIO(self._raw_tail))
            self.tail = MusicBody.ShinyTail(_io__raw_tail, self, self._root)
            self.tail._read()
        else:
            pass
            self.tail = self._io.read_bytes(self.tail_len)
        self.padding = []
        i = 0
        while not self._io.is_eof():
            self.padding.append(self._io.read_u1())
            if not self.padding[i] == 0:
                raise kaitaistruct.ValidationNotEqualError(0, self.padding[i], self._io, u"/seq/6")
            i += 1

        self._dirty = False


    def _fetch_instances(self):
        pass
        self.header._fetch_instances()
        for i in range(len(self.palette)):
            pass
            self.palette[i]._fetch_instances()

        _on = self.mode
        if _on == govee_common.GoveeCommon.MusicMode.bloom:
            pass
            self.tail._fetch_instances()
        elif _on == govee_common.GoveeCommon.MusicMode.day_and_night:
            pass
            self.tail._fetch_instances()
        elif _on == govee_common.GoveeCommon.MusicMode.fountain:
            pass
            self.tail._fetch_instances()
        elif _on == govee_common.GoveeCommon.MusicMode.hopping:
            pass
            self.tail._fetch_instances()
        elif _on == govee_common.GoveeCommon.MusicMode.piano_keys:
            pass
            self.tail._fetch_instances()
        elif _on == govee_common.GoveeCommon.MusicMode.separation:
            pass
            self.tail._fetch_instances()
        elif _on == govee_common.GoveeCommon.MusicMode.shiny:
            pass
            self.tail._fetch_instances()
        else:
            pass
        for i in range(len(self.padding)):
            pass



    def _write__seq(self, io=None):
        super(MusicBody, self)._write__seq(io)
        self.header._write__seq(self._io)
        self._io.write_bytes(self.command)
        self._io.write_u1(int(self.mode))
        self._io.write_u1(self.num_palette)
        for i in range(len(self.palette)):
            pass
            self.palette[i]._write__seq(self._io)

        _on = self.mode
        if _on == govee_common.GoveeCommon.MusicMode.bloom:
            pass
            _io__raw_tail = KaitaiStream(BytesIO(bytearray(self.tail_len)))
            self._io.add_child_stream(_io__raw_tail)
            _pos2 = self._io.pos()
            self._io.seek(self._io.pos() + (self.tail_len))
            def handler(parent, _io__raw_tail=_io__raw_tail):
                self._raw_tail = _io__raw_tail.to_byte_array()
                if len(self._raw_tail) != self.tail_len:
                    raise kaitaistruct.ConsistencyError(u"raw(tail)", self.tail_len, len(self._raw_tail))
                parent.write_bytes(self._raw_tail)
            _io__raw_tail.write_back_handler = KaitaiStream.WriteBackHandler(_pos2, handler)
            self.tail._write__seq(_io__raw_tail)
        elif _on == govee_common.GoveeCommon.MusicMode.day_and_night:
            pass
            _io__raw_tail = KaitaiStream(BytesIO(bytearray(self.tail_len)))
            self._io.add_child_stream(_io__raw_tail)
            _pos2 = self._io.pos()
            self._io.seek(self._io.pos() + (self.tail_len))
            def handler(parent, _io__raw_tail=_io__raw_tail):
                self._raw_tail = _io__raw_tail.to_byte_array()
                if len(self._raw_tail) != self.tail_len:
                    raise kaitaistruct.ConsistencyError(u"raw(tail)", self.tail_len, len(self._raw_tail))
                parent.write_bytes(self._raw_tail)
            _io__raw_tail.write_back_handler = KaitaiStream.WriteBackHandler(_pos2, handler)
            self.tail._write__seq(_io__raw_tail)
        elif _on == govee_common.GoveeCommon.MusicMode.fountain:
            pass
            _io__raw_tail = KaitaiStream(BytesIO(bytearray(self.tail_len)))
            self._io.add_child_stream(_io__raw_tail)
            _pos2 = self._io.pos()
            self._io.seek(self._io.pos() + (self.tail_len))
            def handler(parent, _io__raw_tail=_io__raw_tail):
                self._raw_tail = _io__raw_tail.to_byte_array()
                if len(self._raw_tail) != self.tail_len:
                    raise kaitaistruct.ConsistencyError(u"raw(tail)", self.tail_len, len(self._raw_tail))
                parent.write_bytes(self._raw_tail)
            _io__raw_tail.write_back_handler = KaitaiStream.WriteBackHandler(_pos2, handler)
            self.tail._write__seq(_io__raw_tail)
        elif _on == govee_common.GoveeCommon.MusicMode.hopping:
            pass
            _io__raw_tail = KaitaiStream(BytesIO(bytearray(self.tail_len)))
            self._io.add_child_stream(_io__raw_tail)
            _pos2 = self._io.pos()
            self._io.seek(self._io.pos() + (self.tail_len))
            def handler(parent, _io__raw_tail=_io__raw_tail):
                self._raw_tail = _io__raw_tail.to_byte_array()
                if len(self._raw_tail) != self.tail_len:
                    raise kaitaistruct.ConsistencyError(u"raw(tail)", self.tail_len, len(self._raw_tail))
                parent.write_bytes(self._raw_tail)
            _io__raw_tail.write_back_handler = KaitaiStream.WriteBackHandler(_pos2, handler)
            self.tail._write__seq(_io__raw_tail)
        elif _on == govee_common.GoveeCommon.MusicMode.piano_keys:
            pass
            _io__raw_tail = KaitaiStream(BytesIO(bytearray(self.tail_len)))
            self._io.add_child_stream(_io__raw_tail)
            _pos2 = self._io.pos()
            self._io.seek(self._io.pos() + (self.tail_len))
            def handler(parent, _io__raw_tail=_io__raw_tail):
                self._raw_tail = _io__raw_tail.to_byte_array()
                if len(self._raw_tail) != self.tail_len:
                    raise kaitaistruct.ConsistencyError(u"raw(tail)", self.tail_len, len(self._raw_tail))
                parent.write_bytes(self._raw_tail)
            _io__raw_tail.write_back_handler = KaitaiStream.WriteBackHandler(_pos2, handler)
            self.tail._write__seq(_io__raw_tail)
        elif _on == govee_common.GoveeCommon.MusicMode.separation:
            pass
            _io__raw_tail = KaitaiStream(BytesIO(bytearray(self.tail_len)))
            self._io.add_child_stream(_io__raw_tail)
            _pos2 = self._io.pos()
            self._io.seek(self._io.pos() + (self.tail_len))
            def handler(parent, _io__raw_tail=_io__raw_tail):
                self._raw_tail = _io__raw_tail.to_byte_array()
                if len(self._raw_tail) != self.tail_len:
                    raise kaitaistruct.ConsistencyError(u"raw(tail)", self.tail_len, len(self._raw_tail))
                parent.write_bytes(self._raw_tail)
            _io__raw_tail.write_back_handler = KaitaiStream.WriteBackHandler(_pos2, handler)
            self.tail._write__seq(_io__raw_tail)
        elif _on == govee_common.GoveeCommon.MusicMode.shiny:
            pass
            _io__raw_tail = KaitaiStream(BytesIO(bytearray(self.tail_len)))
            self._io.add_child_stream(_io__raw_tail)
            _pos2 = self._io.pos()
            self._io.seek(self._io.pos() + (self.tail_len))
            def handler(parent, _io__raw_tail=_io__raw_tail):
                self._raw_tail = _io__raw_tail.to_byte_array()
                if len(self._raw_tail) != self.tail_len:
                    raise kaitaistruct.ConsistencyError(u"raw(tail)", self.tail_len, len(self._raw_tail))
                parent.write_bytes(self._raw_tail)
            _io__raw_tail.write_back_handler = KaitaiStream.WriteBackHandler(_pos2, handler)
            self.tail._write__seq(_io__raw_tail)
        else:
            pass
            self._io.write_bytes(self.tail)
        for i in range(len(self.padding)):
            pass
            if self._io.is_eof():
                raise kaitaistruct.ConsistencyError(u"padding", 0, self._io.size() - self._io.pos())
            self._io.write_u1(self.padding[i])

        if not self._io.is_eof():
            raise kaitaistruct.ConsistencyError(u"padding", 0, self._io.size() - self._io.pos())


    def _check(self):
        if len(self.command) != 1:
            raise kaitaistruct.ConsistencyError(u"command", 1, len(self.command))
        if not self.command == b"\x41":
            raise kaitaistruct.ValidationNotEqualError(b"\x41", self.command, None, u"/seq/1")
        if len(self.palette) != self.num_palette:
            raise kaitaistruct.ConsistencyError(u"palette", self.num_palette, len(self.palette))
        for i in range(len(self.palette)):
            pass

        _on = self.mode
        if _on == govee_common.GoveeCommon.MusicMode.bloom:
            pass
            if self.tail._root != self._root:
                raise kaitaistruct.ConsistencyError(u"tail", self._root, self.tail._root)
            if self.tail._parent != self:
                raise kaitaistruct.ConsistencyError(u"tail", self, self.tail._parent)
        elif _on == govee_common.GoveeCommon.MusicMode.day_and_night:
            pass
            if self.tail._root != self._root:
                raise kaitaistruct.ConsistencyError(u"tail", self._root, self.tail._root)
            if self.tail._parent != self:
                raise kaitaistruct.ConsistencyError(u"tail", self, self.tail._parent)
        elif _on == govee_common.GoveeCommon.MusicMode.fountain:
            pass
            if self.tail._root != self._root:
                raise kaitaistruct.ConsistencyError(u"tail", self._root, self.tail._root)
            if self.tail._parent != self:
                raise kaitaistruct.ConsistencyError(u"tail", self, self.tail._parent)
        elif _on == govee_common.GoveeCommon.MusicMode.hopping:
            pass
            if self.tail._root != self._root:
                raise kaitaistruct.ConsistencyError(u"tail", self._root, self.tail._root)
            if self.tail._parent != self:
                raise kaitaistruct.ConsistencyError(u"tail", self, self.tail._parent)
        elif _on == govee_common.GoveeCommon.MusicMode.piano_keys:
            pass
            if self.tail._root != self._root:
                raise kaitaistruct.ConsistencyError(u"tail", self._root, self.tail._root)
            if self.tail._parent != self:
                raise kaitaistruct.ConsistencyError(u"tail", self, self.tail._parent)
        elif _on == govee_common.GoveeCommon.MusicMode.separation:
            pass
            if self.tail._root != self._root:
                raise kaitaistruct.ConsistencyError(u"tail", self._root, self.tail._root)
            if self.tail._parent != self:
                raise kaitaistruct.ConsistencyError(u"tail", self, self.tail._parent)
        elif _on == govee_common.GoveeCommon.MusicMode.shiny:
            pass
            if self.tail._root != self._root:
                raise kaitaistruct.ConsistencyError(u"tail", self._root, self.tail._root)
            if self.tail._parent != self:
                raise kaitaistruct.ConsistencyError(u"tail", self, self.tail._parent)
        else:
            pass
            if len(self.tail) != self.tail_len:
                raise kaitaistruct.ConsistencyError(u"tail", self.tail_len, len(self.tail))
        for i in range(len(self.padding)):
            pass
            if not self.padding[i] == 0:
                raise kaitaistruct.ValidationNotEqualError(0, self.padding[i], None, u"/seq/6")

        self._dirty = False

    class BloomTail(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(MusicBody.BloomTail, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self._unnamed0 = self._io.read_bytes(1)
            if not self._unnamed0 == b"\x0A":
                raise kaitaistruct.ValidationNotEqualError(b"\x0A", self._unnamed0, self._io, u"/types/bloom_tail/seq/0")
            self.style_companion = self._io.read_u1()
            self._dirty = False


        def _fetch_instances(self):
            pass


        def _write__seq(self, io=None):
            super(MusicBody.BloomTail, self)._write__seq(io)
            self._io.write_bytes(self._unnamed0)
            self._io.write_u1(self.style_companion)


        def _check(self):
            if len(self._unnamed0) != 1:
                raise kaitaistruct.ConsistencyError(u"_unnamed0", 1, len(self._unnamed0))
            if not self._unnamed0 == b"\x0A":
                raise kaitaistruct.ValidationNotEqualError(b"\x0A", self._unnamed0, None, u"/types/bloom_tail/seq/0")
            self._dirty = False


    class DayAndNightTail(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(MusicBody.DayAndNightTail, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.segment_count = self._io.read_u1()
            self.speed = self._io.read_u1()
            self.gradient = self._io.read_u1()
            self._dirty = False


        def _fetch_instances(self):
            pass


        def _write__seq(self, io=None):
            super(MusicBody.DayAndNightTail, self)._write__seq(io)
            self._io.write_u1(self.segment_count)
            self._io.write_u1(self.speed)
            self._io.write_u1(self.gradient)


        def _check(self):
            self._dirty = False


    class FountainTail(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(MusicBody.FountainTail, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.start_point = self._io.read_u1()
            self.piece_len = self._io.read_u1()
            if not self.piece_len == 1:
                raise kaitaistruct.ValidationNotEqualError(1, self.piece_len, self._io, u"/types/fountain_tail/seq/1")
            self.piece_num = self._io.read_u1()
            self.speed = self._io.read_u1()
            self._dirty = False


        def _fetch_instances(self):
            pass


        def _write__seq(self, io=None):
            super(MusicBody.FountainTail, self)._write__seq(io)
            self._io.write_u1(self.start_point)
            self._io.write_u1(self.piece_len)
            self._io.write_u1(self.piece_num)
            self._io.write_u1(self.speed)


        def _check(self):
            if not self.piece_len == 1:
                raise kaitaistruct.ValidationNotEqualError(1, self.piece_len, None, u"/types/fountain_tail/seq/1")
            self._dirty = False


    class HoppingTail(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(MusicBody.HoppingTail, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.background = govee_shared.GoveeShared.Rgb(self._io)
            self.background._read()
            self.rel_brightness = self._io.read_u1()
            self._unnamed2 = self._io.read_bytes(5)
            if not self._unnamed2 == b"\x62\x01\x03\x02\x06":
                raise kaitaistruct.ValidationNotEqualError(b"\x62\x01\x03\x02\x06", self._unnamed2, self._io, u"/types/hopping_tail/seq/2")
            self._dirty = False


        def _fetch_instances(self):
            pass
            self.background._fetch_instances()


        def _write__seq(self, io=None):
            super(MusicBody.HoppingTail, self)._write__seq(io)
            self.background._write__seq(self._io)
            self._io.write_u1(self.rel_brightness)
            self._io.write_bytes(self._unnamed2)


        def _check(self):
            if len(self._unnamed2) != 5:
                raise kaitaistruct.ConsistencyError(u"_unnamed2", 5, len(self._unnamed2))
            if not self._unnamed2 == b"\x62\x01\x03\x02\x06":
                raise kaitaistruct.ValidationNotEqualError(b"\x62\x01\x03\x02\x06", self._unnamed2, None, u"/types/hopping_tail/seq/2")
            self._dirty = False


    class ModeSetFrame(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(MusicBody.ModeSetFrame, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.header = self._io.read_bytes(1)
            if not self.header == b"\x33":
                raise kaitaistruct.ValidationNotEqualError(b"\x33", self.header, self._io, u"/types/mode_set_frame/seq/0")
            self.domain = self._io.read_bytes(1)
            if not self.domain == b"\x05":
                raise kaitaistruct.ValidationNotEqualError(b"\x05", self.domain, self._io, u"/types/mode_set_frame/seq/1")
            self.sub = self._io.read_bytes(1)
            if not self.sub == b"\x13":
                raise kaitaistruct.ValidationNotEqualError(b"\x13", self.sub, self._io, u"/types/mode_set_frame/seq/2")
            self.mode = KaitaiStream.resolve_enum(govee_common.GoveeCommon.MusicMode, self._io.read_u1())
            self.sensitivity = self._io.read_u1()
            self.style = self._io.read_u1()
            self.num_colors = self._io.read_u1()
            if not self.num_colors <= 4:
                raise kaitaistruct.ValidationGreaterThanError(4, self.num_colors, self._io, u"/types/mode_set_frame/seq/6")
            self.colors = []
            for i in range(self.num_colors):
                _t_colors = govee_shared.GoveeShared.Rgb(self._io)
                try:
                    _t_colors._read()
                finally:
                    self.colors.append(_t_colors)

            self.padding = []
            for i in range(12 - self.num_colors * 3):
                self.padding.append(self._io.read_u1())
                if not self.padding[i] == 0:
                    raise kaitaistruct.ValidationNotEqualError(0, self.padding[i], self._io, u"/types/mode_set_frame/seq/8")

            self.checksum = self._io.read_u1()
            self._dirty = False


        def _fetch_instances(self):
            pass
            for i in range(len(self.colors)):
                pass
                self.colors[i]._fetch_instances()

            for i in range(len(self.padding)):
                pass



        def _write__seq(self, io=None):
            super(MusicBody.ModeSetFrame, self)._write__seq(io)
            self._io.write_bytes(self.header)
            self._io.write_bytes(self.domain)
            self._io.write_bytes(self.sub)
            self._io.write_u1(int(self.mode))
            self._io.write_u1(self.sensitivity)
            self._io.write_u1(self.style)
            self._io.write_u1(self.num_colors)
            for i in range(len(self.colors)):
                pass
                self.colors[i]._write__seq(self._io)

            for i in range(len(self.padding)):
                pass
                self._io.write_u1(self.padding[i])

            self._io.write_u1(self.checksum)


        def _check(self):
            if len(self.header) != 1:
                raise kaitaistruct.ConsistencyError(u"header", 1, len(self.header))
            if not self.header == b"\x33":
                raise kaitaistruct.ValidationNotEqualError(b"\x33", self.header, None, u"/types/mode_set_frame/seq/0")
            if len(self.domain) != 1:
                raise kaitaistruct.ConsistencyError(u"domain", 1, len(self.domain))
            if not self.domain == b"\x05":
                raise kaitaistruct.ValidationNotEqualError(b"\x05", self.domain, None, u"/types/mode_set_frame/seq/1")
            if len(self.sub) != 1:
                raise kaitaistruct.ConsistencyError(u"sub", 1, len(self.sub))
            if not self.sub == b"\x13":
                raise kaitaistruct.ValidationNotEqualError(b"\x13", self.sub, None, u"/types/mode_set_frame/seq/2")
            if not self.num_colors <= 4:
                raise kaitaistruct.ValidationGreaterThanError(4, self.num_colors, None, u"/types/mode_set_frame/seq/6")
            if len(self.colors) != self.num_colors:
                raise kaitaistruct.ConsistencyError(u"colors", self.num_colors, len(self.colors))
            for i in range(len(self.colors)):
                pass

            if len(self.padding) != 12 - self.num_colors * 3:
                raise kaitaistruct.ConsistencyError(u"padding", 12 - self.num_colors * 3, len(self.padding))
            for i in range(len(self.padding)):
                pass
                if not self.padding[i] == 0:
                    raise kaitaistruct.ValidationNotEqualError(0, self.padding[i], None, u"/types/mode_set_frame/seq/8")

            self._dirty = False


    class PianoKeysTail(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(MusicBody.PianoKeysTail, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.gradient = self._io.read_u1()
            self.key_count = self._io.read_u1()
            self._unnamed2 = self._io.read_bytes(2)
            if not self._unnamed2 == b"\x0A\x04":
                raise kaitaistruct.ValidationNotEqualError(b"\x0A\x04", self._unnamed2, self._io, u"/types/piano_keys_tail/seq/2")
            self.derived_half = self._io.read_u1()
            self._dirty = False


        def _fetch_instances(self):
            pass


        def _write__seq(self, io=None):
            super(MusicBody.PianoKeysTail, self)._write__seq(io)
            self._io.write_u1(self.gradient)
            self._io.write_u1(self.key_count)
            self._io.write_bytes(self._unnamed2)
            self._io.write_u1(self.derived_half)


        def _check(self):
            if len(self._unnamed2) != 2:
                raise kaitaistruct.ConsistencyError(u"_unnamed2", 2, len(self._unnamed2))
            if not self._unnamed2 == b"\x0A\x04":
                raise kaitaistruct.ValidationNotEqualError(b"\x0A\x04", self._unnamed2, None, u"/types/piano_keys_tail/seq/2")
            self._dirty = False


    class SeparationTail(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(MusicBody.SeparationTail, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.point = self._io.read_u1()
            self.gradient = self._io.read_u1()
            self.companion = self._io.read_u1()
            self._dirty = False


        def _fetch_instances(self):
            pass


        def _write__seq(self, io=None):
            super(MusicBody.SeparationTail, self)._write__seq(io)
            self._io.write_u1(self.point)
            self._io.write_u1(self.gradient)
            self._io.write_u1(self.companion)


        def _check(self):
            self._dirty = False


    class ShinyTail(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(MusicBody.ShinyTail, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.style_companion = KaitaiStream.resolve_enum(MusicBody.ShinyStyle, self._io.read_u2be())
            self._unnamed1 = self._io.read_bytes(1)
            if not self._unnamed1 == b"\x0A":
                raise kaitaistruct.ValidationNotEqualError(b"\x0A", self._unnamed1, self._io, u"/types/shiny_tail/seq/1")
            self._dirty = False


        def _fetch_instances(self):
            pass


        def _write__seq(self, io=None):
            super(MusicBody.ShinyTail, self)._write__seq(io)
            self._io.write_u2be(int(self.style_companion))
            self._io.write_bytes(self._unnamed1)


        def _check(self):
            if len(self._unnamed1) != 1:
                raise kaitaistruct.ConsistencyError(u"_unnamed1", 1, len(self._unnamed1))
            if not self._unnamed1 == b"\x0A":
                raise kaitaistruct.ValidationNotEqualError(b"\x0A", self._unnamed1, None, u"/types/shiny_tail/seq/1")
            self._dirty = False


    @property
    def tail_len(self):
        if hasattr(self, '_m_tail_len'):
            return self._m_tail_len

        self._m_tail_len = (9 if self.mode == govee_common.GoveeCommon.MusicMode.hopping else (5 if self.mode == govee_common.GoveeCommon.MusicMode.piano_keys else (4 if self.mode == govee_common.GoveeCommon.MusicMode.fountain else (3 if self.mode == govee_common.GoveeCommon.MusicMode.separation else (3 if self.mode == govee_common.GoveeCommon.MusicMode.shiny else (3 if self.mode == govee_common.GoveeCommon.MusicMode.day_and_night else 2))))))
        return getattr(self, '_m_tail_len', None)

    def _invalidate_tail_len(self):
        del self._m_tail_len

