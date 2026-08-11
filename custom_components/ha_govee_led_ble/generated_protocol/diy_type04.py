# This is a generated file! Please edit source .ksy file and use kaitai-struct-compiler to rebuild
# type: ignore

import kaitaistruct
from kaitaistruct import ReadWriteKaitaiStruct, KaitaiStream, BytesIO
from custom_components.ha_govee_led_ble.generated_protocol import govee_common
from custom_components.ha_govee_led_ble.generated_protocol import govee_shared


if getattr(kaitaistruct, 'API_VERSION', (0, 9)) < (0, 11):
    raise Exception("Incompatible Kaitai Struct Python API: 0.11 or later is required, but you have %s" % (kaitaistruct.__version__))

class DiyType04(ReadWriteKaitaiStruct):
    def __init__(self, _io=None, _parent=None, _root=None):
        super(DiyType04, self).__init__(_io)
        self._parent = _parent
        self._root = _root or self

    def _read(self):
        self.header = govee_common.GoveeCommon.A3Header(self._io)
        self.header._read()
        self.a3_type = self._io.read_bytes(1)
        if not self.a3_type == b"\x04":
            raise kaitaistruct.ValidationNotEqualError(b"\x04", self.a3_type, self._io, u"/seq/1")
        self.family = self._io.read_u1()
        _on = self.family
        if _on == 255:
            pass
            self.body = DiyType04.ComboBody(self._io, self, self._root)
            self.body._read()
        else:
            pass
            self.body = DiyType04.FlatBody(self._io, self, self._root)
            self.body._read()
        self._dirty = False


    def _fetch_instances(self):
        pass
        self.header._fetch_instances()
        _on = self.family
        if _on == 255:
            pass
            self.body._fetch_instances()
        else:
            pass
            self.body._fetch_instances()


    def _write__seq(self, io=None):
        super(DiyType04, self)._write__seq(io)
        self.header._write__seq(self._io)
        self._io.write_bytes(self.a3_type)
        self._io.write_u1(self.family)
        _on = self.family
        if _on == 255:
            pass
            self.body._write__seq(self._io)
        else:
            pass
            self.body._write__seq(self._io)


    def _check(self):
        if len(self.a3_type) != 1:
            raise kaitaistruct.ConsistencyError(u"a3_type", 1, len(self.a3_type))
        if not self.a3_type == b"\x04":
            raise kaitaistruct.ValidationNotEqualError(b"\x04", self.a3_type, None, u"/seq/1")
        _on = self.family
        if _on == 255:
            pass
            if self.body._root != self._root:
                raise kaitaistruct.ConsistencyError(u"body", self._root, self.body._root)
            if self.body._parent != self:
                raise kaitaistruct.ConsistencyError(u"body", self, self.body._parent)
        else:
            pass
            if self.body._root != self._root:
                raise kaitaistruct.ConsistencyError(u"body", self._root, self.body._root)
            if self.body._parent != self:
                raise kaitaistruct.ConsistencyError(u"body", self, self.body._parent)
        self._dirty = False

    class ComboBody(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(DiyType04.ComboBody, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.variant = self._io.read_u1()
            self.speed = self._io.read_u1()
            self.len_palette = self._io.read_u1()
            _ = self.len_palette
            if not _ % 3 == 0:
                raise kaitaistruct.ValidationExprError(self.len_palette, self._io, u"/types/combo_body/seq/2")
            self._raw_palette = self._io.read_bytes(self.len_palette)
            _io__raw_palette = KaitaiStream(BytesIO(self._raw_palette))
            self.palette = DiyType04.Palette(_io__raw_palette, self, self._root)
            self.palette._read()
            self.seqlen = self._io.read_u1()
            _ = self.seqlen
            if not _ % 2 == 0:
                raise kaitaistruct.ValidationExprError(self.seqlen, self._io, u"/types/combo_body/seq/4")
            self.pairs = []
            for i in range(self.seqlen // 2):
                _t_pairs = DiyType04.FamilyVariant(self._io, self, self._root)
                try:
                    _t_pairs._read()
                finally:
                    self.pairs.append(_t_pairs)

            self.padding = []
            i = 0
            while not self._io.is_eof():
                self.padding.append(self._io.read_u1())
                if not self.padding[i] == 0:
                    raise kaitaistruct.ValidationNotEqualError(0, self.padding[i], self._io, u"/types/combo_body/seq/6")
                i += 1

            self._dirty = False


        def _fetch_instances(self):
            pass
            self.palette._fetch_instances()
            for i in range(len(self.pairs)):
                pass
                self.pairs[i]._fetch_instances()

            for i in range(len(self.padding)):
                pass



        def _write__seq(self, io=None):
            super(DiyType04.ComboBody, self)._write__seq(io)
            self._io.write_u1(self.variant)
            self._io.write_u1(self.speed)
            self._io.write_u1(self.len_palette)
            _io__raw_palette = KaitaiStream(BytesIO(bytearray(self.len_palette)))
            self._io.add_child_stream(_io__raw_palette)
            _pos2 = self._io.pos()
            self._io.seek(self._io.pos() + (self.len_palette))
            def handler(parent, _io__raw_palette=_io__raw_palette):
                self._raw_palette = _io__raw_palette.to_byte_array()
                if len(self._raw_palette) != self.len_palette:
                    raise kaitaistruct.ConsistencyError(u"raw(palette)", self.len_palette, len(self._raw_palette))
                parent.write_bytes(self._raw_palette)
            _io__raw_palette.write_back_handler = KaitaiStream.WriteBackHandler(_pos2, handler)
            self.palette._write__seq(_io__raw_palette)
            self._io.write_u1(self.seqlen)
            for i in range(len(self.pairs)):
                pass
                self.pairs[i]._write__seq(self._io)

            for i in range(len(self.padding)):
                pass
                if self._io.is_eof():
                    raise kaitaistruct.ConsistencyError(u"padding", 0, self._io.size() - self._io.pos())
                self._io.write_u1(self.padding[i])

            if not self._io.is_eof():
                raise kaitaistruct.ConsistencyError(u"padding", 0, self._io.size() - self._io.pos())


        def _check(self):
            _ = self.len_palette
            if not _ % 3 == 0:
                raise kaitaistruct.ValidationExprError(self.len_palette, None, u"/types/combo_body/seq/2")
            if self.palette._root != self._root:
                raise kaitaistruct.ConsistencyError(u"palette", self._root, self.palette._root)
            if self.palette._parent != self:
                raise kaitaistruct.ConsistencyError(u"palette", self, self.palette._parent)
            _ = self.seqlen
            if not _ % 2 == 0:
                raise kaitaistruct.ValidationExprError(self.seqlen, None, u"/types/combo_body/seq/4")
            if len(self.pairs) != self.seqlen // 2:
                raise kaitaistruct.ConsistencyError(u"pairs", self.seqlen // 2, len(self.pairs))
            for i in range(len(self.pairs)):
                pass
                if self.pairs[i]._root != self._root:
                    raise kaitaistruct.ConsistencyError(u"pairs", self._root, self.pairs[i]._root)
                if self.pairs[i]._parent != self:
                    raise kaitaistruct.ConsistencyError(u"pairs", self, self.pairs[i]._parent)

            for i in range(len(self.padding)):
                pass
                if not self.padding[i] == 0:
                    raise kaitaistruct.ValidationNotEqualError(0, self.padding[i], None, u"/types/combo_body/seq/6")

            self._dirty = False


    class FamilyVariant(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(DiyType04.FamilyVariant, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.family = self._io.read_u1()
            self.variant = self._io.read_u1()
            self._dirty = False


        def _fetch_instances(self):
            pass


        def _write__seq(self, io=None):
            super(DiyType04.FamilyVariant, self)._write__seq(io)
            self._io.write_u1(self.family)
            self._io.write_u1(self.variant)


        def _check(self):
            self._dirty = False


    class FlatBody(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(DiyType04.FlatBody, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.variant = self._io.read_u1()
            self.speed = self._io.read_u1()
            self.len_palette = self._io.read_u1()
            _ = self.len_palette
            if not _ % 3 == 0:
                raise kaitaistruct.ValidationExprError(self.len_palette, self._io, u"/types/flat_body/seq/2")
            self._raw_palette = self._io.read_bytes(self.len_palette)
            _io__raw_palette = KaitaiStream(BytesIO(self._raw_palette))
            self.palette = DiyType04.Palette(_io__raw_palette, self, self._root)
            self.palette._read()
            self.padding = []
            i = 0
            while not self._io.is_eof():
                self.padding.append(self._io.read_u1())
                if not self.padding[i] == 0:
                    raise kaitaistruct.ValidationNotEqualError(0, self.padding[i], self._io, u"/types/flat_body/seq/4")
                i += 1

            self._dirty = False


        def _fetch_instances(self):
            pass
            self.palette._fetch_instances()
            for i in range(len(self.padding)):
                pass



        def _write__seq(self, io=None):
            super(DiyType04.FlatBody, self)._write__seq(io)
            self._io.write_u1(self.variant)
            self._io.write_u1(self.speed)
            self._io.write_u1(self.len_palette)
            _io__raw_palette = KaitaiStream(BytesIO(bytearray(self.len_palette)))
            self._io.add_child_stream(_io__raw_palette)
            _pos2 = self._io.pos()
            self._io.seek(self._io.pos() + (self.len_palette))
            def handler(parent, _io__raw_palette=_io__raw_palette):
                self._raw_palette = _io__raw_palette.to_byte_array()
                if len(self._raw_palette) != self.len_palette:
                    raise kaitaistruct.ConsistencyError(u"raw(palette)", self.len_palette, len(self._raw_palette))
                parent.write_bytes(self._raw_palette)
            _io__raw_palette.write_back_handler = KaitaiStream.WriteBackHandler(_pos2, handler)
            self.palette._write__seq(_io__raw_palette)
            for i in range(len(self.padding)):
                pass
                if self._io.is_eof():
                    raise kaitaistruct.ConsistencyError(u"padding", 0, self._io.size() - self._io.pos())
                self._io.write_u1(self.padding[i])

            if not self._io.is_eof():
                raise kaitaistruct.ConsistencyError(u"padding", 0, self._io.size() - self._io.pos())


        def _check(self):
            _ = self.len_palette
            if not _ % 3 == 0:
                raise kaitaistruct.ValidationExprError(self.len_palette, None, u"/types/flat_body/seq/2")
            if self.palette._root != self._root:
                raise kaitaistruct.ConsistencyError(u"palette", self._root, self.palette._root)
            if self.palette._parent != self:
                raise kaitaistruct.ConsistencyError(u"palette", self, self.palette._parent)
            for i in range(len(self.padding)):
                pass
                if not self.padding[i] == 0:
                    raise kaitaistruct.ValidationNotEqualError(0, self.padding[i], None, u"/types/flat_body/seq/4")

            self._dirty = False


    class Palette(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(DiyType04.Palette, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.colours = []
            i = 0
            while not self._io.is_eof():
                _t_colours = govee_shared.GoveeShared.Rgb(self._io)
                try:
                    _t_colours._read()
                finally:
                    self.colours.append(_t_colours)
                i += 1

            self._dirty = False


        def _fetch_instances(self):
            pass
            for i in range(len(self.colours)):
                pass
                self.colours[i]._fetch_instances()



        def _write__seq(self, io=None):
            super(DiyType04.Palette, self)._write__seq(io)
            for i in range(len(self.colours)):
                pass
                if self._io.is_eof():
                    raise kaitaistruct.ConsistencyError(u"colours", 0, self._io.size() - self._io.pos())
                self.colours[i]._write__seq(self._io)

            if not self._io.is_eof():
                raise kaitaistruct.ConsistencyError(u"colours", 0, self._io.size() - self._io.pos())


        def _check(self):
            for i in range(len(self.colours)):
                pass

            self._dirty = False



