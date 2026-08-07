# This is a generated file! Please edit source .ksy file and use kaitai-struct-compiler to rebuild
# type: ignore

import kaitaistruct
from kaitaistruct import ReadWriteKaitaiStruct, KaitaiStream, BytesIO
from custom_components.ha_govee_led_ble.generated_protocol import govee_shared
from custom_components.ha_govee_led_ble.generated_protocol import govee_common
from enum import IntEnum


if getattr(kaitaistruct, 'API_VERSION', (0, 9)) < (0, 11):
    raise Exception("Incompatible Kaitai Struct Python API: 0.11 or later is required, but you have %s" % (kaitaistruct.__version__))

class StatusReply(ReadWriteKaitaiStruct):
    """H617A 20-byte status reply. The final byte is the XOR of bytes 0 through 18.
    """

    class AaDomain(IntEnum):
        power = 1
        brightness = 4
        colormode = 5
        fw_version = 6
        hw_version = 7
        multi_effect = 163
        segments = 165

    class ColorMode(IntEnum):
        scene = 4
        diy = 10
        music = 19
        static = 21
    def __init__(self, _io=None, _parent=None, _root=None):
        super(StatusReply, self).__init__(_io)
        self._parent = _parent
        self._root = _root or self

    def _read(self):
        self.header = self._io.read_bytes(1)
        if not self.header == b"\xAA":
            raise kaitaistruct.ValidationNotEqualError(b"\xAA", self.header, self._io, u"/seq/0")
        self.domain = KaitaiStream.resolve_enum(StatusReply.AaDomain, self._io.read_u1())
        _on = self.domain
        if _on == StatusReply.AaDomain.brightness:
            pass
            self._raw_body = self._io.read_bytes(17)
            _io__raw_body = KaitaiStream(BytesIO(self._raw_body))
            self.body = StatusReply.BrightnessBody(_io__raw_body, self, self._root)
            self.body._read()
        elif _on == StatusReply.AaDomain.colormode:
            pass
            self._raw_body = self._io.read_bytes(17)
            _io__raw_body = KaitaiStream(BytesIO(self._raw_body))
            self.body = StatusReply.ColormodeBody(_io__raw_body, self, self._root)
            self.body._read()
        elif _on == StatusReply.AaDomain.fw_version:
            pass
            self._raw_body = self._io.read_bytes(17)
            _io__raw_body = KaitaiStream(BytesIO(self._raw_body))
            self.body = StatusReply.VersionBody(_io__raw_body, self, self._root)
            self.body._read()
        elif _on == StatusReply.AaDomain.hw_version:
            pass
            self._raw_body = self._io.read_bytes(17)
            _io__raw_body = KaitaiStream(BytesIO(self._raw_body))
            self.body = StatusReply.HwVersionBody(_io__raw_body, self, self._root)
            self.body._read()
        elif _on == StatusReply.AaDomain.multi_effect:
            pass
            self._raw_body = self._io.read_bytes(17)
            _io__raw_body = KaitaiStream(BytesIO(self._raw_body))
            self.body = StatusReply.MultiEffectBody(_io__raw_body, self, self._root)
            self.body._read()
        elif _on == StatusReply.AaDomain.power:
            pass
            self._raw_body = self._io.read_bytes(17)
            _io__raw_body = KaitaiStream(BytesIO(self._raw_body))
            self.body = StatusReply.PowerBody(_io__raw_body, self, self._root)
            self.body._read()
        elif _on == StatusReply.AaDomain.segments:
            pass
            self._raw_body = self._io.read_bytes(17)
            _io__raw_body = KaitaiStream(BytesIO(self._raw_body))
            self.body = StatusReply.SegmentsBody(_io__raw_body, self, self._root)
            self.body._read()
        else:
            pass
            self.body = self._io.read_bytes(17)
        self.checksum = self._io.read_u1()
        self._dirty = False


    def _fetch_instances(self):
        pass
        _on = self.domain
        if _on == StatusReply.AaDomain.brightness:
            pass
            self.body._fetch_instances()
        elif _on == StatusReply.AaDomain.colormode:
            pass
            self.body._fetch_instances()
        elif _on == StatusReply.AaDomain.fw_version:
            pass
            self.body._fetch_instances()
        elif _on == StatusReply.AaDomain.hw_version:
            pass
            self.body._fetch_instances()
        elif _on == StatusReply.AaDomain.multi_effect:
            pass
            self.body._fetch_instances()
        elif _on == StatusReply.AaDomain.power:
            pass
            self.body._fetch_instances()
        elif _on == StatusReply.AaDomain.segments:
            pass
            self.body._fetch_instances()
        else:
            pass


    def _write__seq(self, io=None):
        super(StatusReply, self)._write__seq(io)
        self._io.write_bytes(self.header)
        self._io.write_u1(int(self.domain))
        _on = self.domain
        if _on == StatusReply.AaDomain.brightness:
            pass
            _io__raw_body = KaitaiStream(BytesIO(bytearray(17)))
            self._io.add_child_stream(_io__raw_body)
            _pos2 = self._io.pos()
            self._io.seek(self._io.pos() + (17))
            def handler(parent, _io__raw_body=_io__raw_body):
                self._raw_body = _io__raw_body.to_byte_array()
                if len(self._raw_body) != 17:
                    raise kaitaistruct.ConsistencyError(u"raw(body)", 17, len(self._raw_body))
                parent.write_bytes(self._raw_body)
            _io__raw_body.write_back_handler = KaitaiStream.WriteBackHandler(_pos2, handler)
            self.body._write__seq(_io__raw_body)
        elif _on == StatusReply.AaDomain.colormode:
            pass
            _io__raw_body = KaitaiStream(BytesIO(bytearray(17)))
            self._io.add_child_stream(_io__raw_body)
            _pos2 = self._io.pos()
            self._io.seek(self._io.pos() + (17))
            def handler(parent, _io__raw_body=_io__raw_body):
                self._raw_body = _io__raw_body.to_byte_array()
                if len(self._raw_body) != 17:
                    raise kaitaistruct.ConsistencyError(u"raw(body)", 17, len(self._raw_body))
                parent.write_bytes(self._raw_body)
            _io__raw_body.write_back_handler = KaitaiStream.WriteBackHandler(_pos2, handler)
            self.body._write__seq(_io__raw_body)
        elif _on == StatusReply.AaDomain.fw_version:
            pass
            _io__raw_body = KaitaiStream(BytesIO(bytearray(17)))
            self._io.add_child_stream(_io__raw_body)
            _pos2 = self._io.pos()
            self._io.seek(self._io.pos() + (17))
            def handler(parent, _io__raw_body=_io__raw_body):
                self._raw_body = _io__raw_body.to_byte_array()
                if len(self._raw_body) != 17:
                    raise kaitaistruct.ConsistencyError(u"raw(body)", 17, len(self._raw_body))
                parent.write_bytes(self._raw_body)
            _io__raw_body.write_back_handler = KaitaiStream.WriteBackHandler(_pos2, handler)
            self.body._write__seq(_io__raw_body)
        elif _on == StatusReply.AaDomain.hw_version:
            pass
            _io__raw_body = KaitaiStream(BytesIO(bytearray(17)))
            self._io.add_child_stream(_io__raw_body)
            _pos2 = self._io.pos()
            self._io.seek(self._io.pos() + (17))
            def handler(parent, _io__raw_body=_io__raw_body):
                self._raw_body = _io__raw_body.to_byte_array()
                if len(self._raw_body) != 17:
                    raise kaitaistruct.ConsistencyError(u"raw(body)", 17, len(self._raw_body))
                parent.write_bytes(self._raw_body)
            _io__raw_body.write_back_handler = KaitaiStream.WriteBackHandler(_pos2, handler)
            self.body._write__seq(_io__raw_body)
        elif _on == StatusReply.AaDomain.multi_effect:
            pass
            _io__raw_body = KaitaiStream(BytesIO(bytearray(17)))
            self._io.add_child_stream(_io__raw_body)
            _pos2 = self._io.pos()
            self._io.seek(self._io.pos() + (17))
            def handler(parent, _io__raw_body=_io__raw_body):
                self._raw_body = _io__raw_body.to_byte_array()
                if len(self._raw_body) != 17:
                    raise kaitaistruct.ConsistencyError(u"raw(body)", 17, len(self._raw_body))
                parent.write_bytes(self._raw_body)
            _io__raw_body.write_back_handler = KaitaiStream.WriteBackHandler(_pos2, handler)
            self.body._write__seq(_io__raw_body)
        elif _on == StatusReply.AaDomain.power:
            pass
            _io__raw_body = KaitaiStream(BytesIO(bytearray(17)))
            self._io.add_child_stream(_io__raw_body)
            _pos2 = self._io.pos()
            self._io.seek(self._io.pos() + (17))
            def handler(parent, _io__raw_body=_io__raw_body):
                self._raw_body = _io__raw_body.to_byte_array()
                if len(self._raw_body) != 17:
                    raise kaitaistruct.ConsistencyError(u"raw(body)", 17, len(self._raw_body))
                parent.write_bytes(self._raw_body)
            _io__raw_body.write_back_handler = KaitaiStream.WriteBackHandler(_pos2, handler)
            self.body._write__seq(_io__raw_body)
        elif _on == StatusReply.AaDomain.segments:
            pass
            _io__raw_body = KaitaiStream(BytesIO(bytearray(17)))
            self._io.add_child_stream(_io__raw_body)
            _pos2 = self._io.pos()
            self._io.seek(self._io.pos() + (17))
            def handler(parent, _io__raw_body=_io__raw_body):
                self._raw_body = _io__raw_body.to_byte_array()
                if len(self._raw_body) != 17:
                    raise kaitaistruct.ConsistencyError(u"raw(body)", 17, len(self._raw_body))
                parent.write_bytes(self._raw_body)
            _io__raw_body.write_back_handler = KaitaiStream.WriteBackHandler(_pos2, handler)
            self.body._write__seq(_io__raw_body)
        else:
            pass
            self._io.write_bytes(self.body)
        self._io.write_u1(self.checksum)


    def _check(self):
        if len(self.header) != 1:
            raise kaitaistruct.ConsistencyError(u"header", 1, len(self.header))
        if not self.header == b"\xAA":
            raise kaitaistruct.ValidationNotEqualError(b"\xAA", self.header, None, u"/seq/0")
        _on = self.domain
        if _on == StatusReply.AaDomain.brightness:
            pass
            if self.body._root != self._root:
                raise kaitaistruct.ConsistencyError(u"body", self._root, self.body._root)
            if self.body._parent != self:
                raise kaitaistruct.ConsistencyError(u"body", self, self.body._parent)
        elif _on == StatusReply.AaDomain.colormode:
            pass
            if self.body._root != self._root:
                raise kaitaistruct.ConsistencyError(u"body", self._root, self.body._root)
            if self.body._parent != self:
                raise kaitaistruct.ConsistencyError(u"body", self, self.body._parent)
        elif _on == StatusReply.AaDomain.fw_version:
            pass
            if self.body._root != self._root:
                raise kaitaistruct.ConsistencyError(u"body", self._root, self.body._root)
            if self.body._parent != self:
                raise kaitaistruct.ConsistencyError(u"body", self, self.body._parent)
        elif _on == StatusReply.AaDomain.hw_version:
            pass
            if self.body._root != self._root:
                raise kaitaistruct.ConsistencyError(u"body", self._root, self.body._root)
            if self.body._parent != self:
                raise kaitaistruct.ConsistencyError(u"body", self, self.body._parent)
        elif _on == StatusReply.AaDomain.multi_effect:
            pass
            if self.body._root != self._root:
                raise kaitaistruct.ConsistencyError(u"body", self._root, self.body._root)
            if self.body._parent != self:
                raise kaitaistruct.ConsistencyError(u"body", self, self.body._parent)
        elif _on == StatusReply.AaDomain.power:
            pass
            if self.body._root != self._root:
                raise kaitaistruct.ConsistencyError(u"body", self._root, self.body._root)
            if self.body._parent != self:
                raise kaitaistruct.ConsistencyError(u"body", self, self.body._parent)
        elif _on == StatusReply.AaDomain.segments:
            pass
            if self.body._root != self._root:
                raise kaitaistruct.ConsistencyError(u"body", self._root, self.body._root)
            if self.body._parent != self:
                raise kaitaistruct.ConsistencyError(u"body", self, self.body._parent)
        else:
            pass
            if len(self.body) != 17:
                raise kaitaistruct.ConsistencyError(u"body", 17, len(self.body))
        self._dirty = False

    class BrightnessBody(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(StatusReply.BrightnessBody, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.brightness_pct = self._io.read_u1()
            self.padding = []
            i = 0
            while not self._io.is_eof():
                self.padding.append(self._io.read_u1())
                if not self.padding[i] == 0:
                    raise kaitaistruct.ValidationNotEqualError(0, self.padding[i], self._io, u"/types/brightness_body/seq/1")
                i += 1

            self._dirty = False


        def _fetch_instances(self):
            pass
            for i in range(len(self.padding)):
                pass



        def _write__seq(self, io=None):
            super(StatusReply.BrightnessBody, self)._write__seq(io)
            self._io.write_u1(self.brightness_pct)
            for i in range(len(self.padding)):
                pass
                if self._io.is_eof():
                    raise kaitaistruct.ConsistencyError(u"padding", 0, self._io.size() - self._io.pos())
                self._io.write_u1(self.padding[i])

            if not self._io.is_eof():
                raise kaitaistruct.ConsistencyError(u"padding", 0, self._io.size() - self._io.pos())


        def _check(self):
            for i in range(len(self.padding)):
                pass
                if not self.padding[i] == 0:
                    raise kaitaistruct.ValidationNotEqualError(0, self.padding[i], None, u"/types/brightness_body/seq/1")

            self._dirty = False


    class CmScene(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(StatusReply.CmScene, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.scene_id = self._io.read_u2le()
            self.padding = []
            i = 0
            while not self._io.is_eof():
                self.padding.append(self._io.read_u1())
                if not self.padding[i] == 0:
                    raise kaitaistruct.ValidationNotEqualError(0, self.padding[i], self._io, u"/types/cm_scene/seq/1")
                i += 1

            self._dirty = False


        def _fetch_instances(self):
            pass
            for i in range(len(self.padding)):
                pass



        def _write__seq(self, io=None):
            super(StatusReply.CmScene, self)._write__seq(io)
            self._io.write_u2le(self.scene_id)
            for i in range(len(self.padding)):
                pass
                if self._io.is_eof():
                    raise kaitaistruct.ConsistencyError(u"padding", 0, self._io.size() - self._io.pos())
                self._io.write_u1(self.padding[i])

            if not self._io.is_eof():
                raise kaitaistruct.ConsistencyError(u"padding", 0, self._io.size() - self._io.pos())


        def _check(self):
            for i in range(len(self.padding)):
                pass
                if not self.padding[i] == 0:
                    raise kaitaistruct.ValidationNotEqualError(0, self.padding[i], None, u"/types/cm_scene/seq/1")

            self._dirty = False


    class CmStatic(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(StatusReply.CmStatic, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.sub = self._io.read_u1()
            self.padding = []
            i = 0
            while not self._io.is_eof():
                self.padding.append(self._io.read_u1())
                if not self.padding[i] == 0:
                    raise kaitaistruct.ValidationNotEqualError(0, self.padding[i], self._io, u"/types/cm_static/seq/1")
                i += 1

            self._dirty = False


        def _fetch_instances(self):
            pass
            for i in range(len(self.padding)):
                pass



        def _write__seq(self, io=None):
            super(StatusReply.CmStatic, self)._write__seq(io)
            self._io.write_u1(self.sub)
            for i in range(len(self.padding)):
                pass
                if self._io.is_eof():
                    raise kaitaistruct.ConsistencyError(u"padding", 0, self._io.size() - self._io.pos())
                self._io.write_u1(self.padding[i])

            if not self._io.is_eof():
                raise kaitaistruct.ConsistencyError(u"padding", 0, self._io.size() - self._io.pos())


        def _check(self):
            for i in range(len(self.padding)):
                pass
                if not self.padding[i] == 0:
                    raise kaitaistruct.ValidationNotEqualError(0, self.padding[i], None, u"/types/cm_static/seq/1")

            self._dirty = False


    class ColormodeBody(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(StatusReply.ColormodeBody, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.mode = KaitaiStream.resolve_enum(StatusReply.ColorMode, self._io.read_u1())
            _on = self.mode
            if _on == StatusReply.ColorMode.diy:
                pass
                self._raw_mode_body = self._io.read_bytes(16)
                _io__raw_mode_body = KaitaiStream(BytesIO(self._raw_mode_body))
                self.mode_body = govee_common.GoveeCommon.DiySelector(_io__raw_mode_body)
                self.mode_body._read()
            elif _on == StatusReply.ColorMode.music:
                pass
                self._raw_mode_body = self._io.read_bytes(16)
                _io__raw_mode_body = KaitaiStream(BytesIO(self._raw_mode_body))
                self.mode_body = govee_common.GoveeCommon.MusicSelector(_io__raw_mode_body)
                self.mode_body._read()
            elif _on == StatusReply.ColorMode.scene:
                pass
                self._raw_mode_body = self._io.read_bytes(16)
                _io__raw_mode_body = KaitaiStream(BytesIO(self._raw_mode_body))
                self.mode_body = StatusReply.CmScene(_io__raw_mode_body, self, self._root)
                self.mode_body._read()
            elif _on == StatusReply.ColorMode.static:
                pass
                self._raw_mode_body = self._io.read_bytes(16)
                _io__raw_mode_body = KaitaiStream(BytesIO(self._raw_mode_body))
                self.mode_body = StatusReply.CmStatic(_io__raw_mode_body, self, self._root)
                self.mode_body._read()
            else:
                pass
                self.mode_body = self._io.read_bytes(16)
            self._dirty = False


        def _fetch_instances(self):
            pass
            _on = self.mode
            if _on == StatusReply.ColorMode.diy:
                pass
                self.mode_body._fetch_instances()
            elif _on == StatusReply.ColorMode.music:
                pass
                self.mode_body._fetch_instances()
            elif _on == StatusReply.ColorMode.scene:
                pass
                self.mode_body._fetch_instances()
            elif _on == StatusReply.ColorMode.static:
                pass
                self.mode_body._fetch_instances()
            else:
                pass


        def _write__seq(self, io=None):
            super(StatusReply.ColormodeBody, self)._write__seq(io)
            self._io.write_u1(int(self.mode))
            _on = self.mode
            if _on == StatusReply.ColorMode.diy:
                pass
                _io__raw_mode_body = KaitaiStream(BytesIO(bytearray(16)))
                self._io.add_child_stream(_io__raw_mode_body)
                _pos2 = self._io.pos()
                self._io.seek(self._io.pos() + (16))
                def handler(parent, _io__raw_mode_body=_io__raw_mode_body):
                    self._raw_mode_body = _io__raw_mode_body.to_byte_array()
                    if len(self._raw_mode_body) != 16:
                        raise kaitaistruct.ConsistencyError(u"raw(mode_body)", 16, len(self._raw_mode_body))
                    parent.write_bytes(self._raw_mode_body)
                _io__raw_mode_body.write_back_handler = KaitaiStream.WriteBackHandler(_pos2, handler)
                self.mode_body._write__seq(_io__raw_mode_body)
            elif _on == StatusReply.ColorMode.music:
                pass
                _io__raw_mode_body = KaitaiStream(BytesIO(bytearray(16)))
                self._io.add_child_stream(_io__raw_mode_body)
                _pos2 = self._io.pos()
                self._io.seek(self._io.pos() + (16))
                def handler(parent, _io__raw_mode_body=_io__raw_mode_body):
                    self._raw_mode_body = _io__raw_mode_body.to_byte_array()
                    if len(self._raw_mode_body) != 16:
                        raise kaitaistruct.ConsistencyError(u"raw(mode_body)", 16, len(self._raw_mode_body))
                    parent.write_bytes(self._raw_mode_body)
                _io__raw_mode_body.write_back_handler = KaitaiStream.WriteBackHandler(_pos2, handler)
                self.mode_body._write__seq(_io__raw_mode_body)
            elif _on == StatusReply.ColorMode.scene:
                pass
                _io__raw_mode_body = KaitaiStream(BytesIO(bytearray(16)))
                self._io.add_child_stream(_io__raw_mode_body)
                _pos2 = self._io.pos()
                self._io.seek(self._io.pos() + (16))
                def handler(parent, _io__raw_mode_body=_io__raw_mode_body):
                    self._raw_mode_body = _io__raw_mode_body.to_byte_array()
                    if len(self._raw_mode_body) != 16:
                        raise kaitaistruct.ConsistencyError(u"raw(mode_body)", 16, len(self._raw_mode_body))
                    parent.write_bytes(self._raw_mode_body)
                _io__raw_mode_body.write_back_handler = KaitaiStream.WriteBackHandler(_pos2, handler)
                self.mode_body._write__seq(_io__raw_mode_body)
            elif _on == StatusReply.ColorMode.static:
                pass
                _io__raw_mode_body = KaitaiStream(BytesIO(bytearray(16)))
                self._io.add_child_stream(_io__raw_mode_body)
                _pos2 = self._io.pos()
                self._io.seek(self._io.pos() + (16))
                def handler(parent, _io__raw_mode_body=_io__raw_mode_body):
                    self._raw_mode_body = _io__raw_mode_body.to_byte_array()
                    if len(self._raw_mode_body) != 16:
                        raise kaitaistruct.ConsistencyError(u"raw(mode_body)", 16, len(self._raw_mode_body))
                    parent.write_bytes(self._raw_mode_body)
                _io__raw_mode_body.write_back_handler = KaitaiStream.WriteBackHandler(_pos2, handler)
                self.mode_body._write__seq(_io__raw_mode_body)
            else:
                pass
                self._io.write_bytes(self.mode_body)


        def _check(self):
            _on = self.mode
            if _on == StatusReply.ColorMode.diy:
                pass
            elif _on == StatusReply.ColorMode.music:
                pass
            elif _on == StatusReply.ColorMode.scene:
                pass
                if self.mode_body._root != self._root:
                    raise kaitaistruct.ConsistencyError(u"mode_body", self._root, self.mode_body._root)
                if self.mode_body._parent != self:
                    raise kaitaistruct.ConsistencyError(u"mode_body", self, self.mode_body._parent)
            elif _on == StatusReply.ColorMode.static:
                pass
                if self.mode_body._root != self._root:
                    raise kaitaistruct.ConsistencyError(u"mode_body", self._root, self.mode_body._root)
                if self.mode_body._parent != self:
                    raise kaitaistruct.ConsistencyError(u"mode_body", self, self.mode_body._parent)
            else:
                pass
                if len(self.mode_body) != 16:
                    raise kaitaistruct.ConsistencyError(u"mode_body", 16, len(self.mode_body))
            self._dirty = False


    class HwVersionBody(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(StatusReply.HwVersionBody, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.prefix = self._io.read_bytes(1)
            if not self.prefix == b"\x03":
                raise kaitaistruct.ValidationNotEqualError(b"\x03", self.prefix, self._io, u"/types/hw_version_body/seq/0")
            self.text = (self._io.read_bytes_term(0, False, True, True)).decode(u"ASCII")
            self.padding = []
            i = 0
            while not self._io.is_eof():
                self.padding.append(self._io.read_u1())
                if not self.padding[i] == 0:
                    raise kaitaistruct.ValidationNotEqualError(0, self.padding[i], self._io, u"/types/hw_version_body/seq/2")
                i += 1

            self._dirty = False


        def _fetch_instances(self):
            pass
            for i in range(len(self.padding)):
                pass



        def _write__seq(self, io=None):
            super(StatusReply.HwVersionBody, self)._write__seq(io)
            self._io.write_bytes(self.prefix)
            self._io.write_bytes((self.text).encode(u"ASCII"))
            self._io.write_u1(0)
            for i in range(len(self.padding)):
                pass
                if self._io.is_eof():
                    raise kaitaistruct.ConsistencyError(u"padding", 0, self._io.size() - self._io.pos())
                self._io.write_u1(self.padding[i])

            if not self._io.is_eof():
                raise kaitaistruct.ConsistencyError(u"padding", 0, self._io.size() - self._io.pos())


        def _check(self):
            if len(self.prefix) != 1:
                raise kaitaistruct.ConsistencyError(u"prefix", 1, len(self.prefix))
            if not self.prefix == b"\x03":
                raise kaitaistruct.ValidationNotEqualError(b"\x03", self.prefix, None, u"/types/hw_version_body/seq/0")
            if KaitaiStream.byte_array_index_of((self.text).encode(u"ASCII"), 0) != -1:
                raise kaitaistruct.ConsistencyError(u"text", -1, KaitaiStream.byte_array_index_of((self.text).encode(u"ASCII"), 0))
            for i in range(len(self.padding)):
                pass
                if not self.padding[i] == 0:
                    raise kaitaistruct.ValidationNotEqualError(0, self.padding[i], None, u"/types/hw_version_body/seq/2")

            self._dirty = False


    class MultiEffectBody(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(StatusReply.MultiEffectBody, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.flag = self._io.read_u1()
            self.padding = []
            i = 0
            while not self._io.is_eof():
                self.padding.append(self._io.read_u1())
                if not self.padding[i] == 0:
                    raise kaitaistruct.ValidationNotEqualError(0, self.padding[i], self._io, u"/types/multi_effect_body/seq/1")
                i += 1

            self._dirty = False


        def _fetch_instances(self):
            pass
            for i in range(len(self.padding)):
                pass



        def _write__seq(self, io=None):
            super(StatusReply.MultiEffectBody, self)._write__seq(io)
            self._io.write_u1(self.flag)
            for i in range(len(self.padding)):
                pass
                if self._io.is_eof():
                    raise kaitaistruct.ConsistencyError(u"padding", 0, self._io.size() - self._io.pos())
                self._io.write_u1(self.padding[i])

            if not self._io.is_eof():
                raise kaitaistruct.ConsistencyError(u"padding", 0, self._io.size() - self._io.pos())


        def _check(self):
            for i in range(len(self.padding)):
                pass
                if not self.padding[i] == 0:
                    raise kaitaistruct.ValidationNotEqualError(0, self.padding[i], None, u"/types/multi_effect_body/seq/1")

            self._dirty = False


    class PowerBody(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(StatusReply.PowerBody, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.is_on = self._io.read_u1()
            self.padding = []
            i = 0
            while not self._io.is_eof():
                self.padding.append(self._io.read_u1())
                if not self.padding[i] == 0:
                    raise kaitaistruct.ValidationNotEqualError(0, self.padding[i], self._io, u"/types/power_body/seq/1")
                i += 1

            self._dirty = False


        def _fetch_instances(self):
            pass
            for i in range(len(self.padding)):
                pass



        def _write__seq(self, io=None):
            super(StatusReply.PowerBody, self)._write__seq(io)
            self._io.write_u1(self.is_on)
            for i in range(len(self.padding)):
                pass
                if self._io.is_eof():
                    raise kaitaistruct.ConsistencyError(u"padding", 0, self._io.size() - self._io.pos())
                self._io.write_u1(self.padding[i])

            if not self._io.is_eof():
                raise kaitaistruct.ConsistencyError(u"padding", 0, self._io.size() - self._io.pos())


        def _check(self):
            for i in range(len(self.padding)):
                pass
                if not self.padding[i] == 0:
                    raise kaitaistruct.ValidationNotEqualError(0, self.padding[i], None, u"/types/power_body/seq/1")

            self._dirty = False


    class Segment(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(StatusReply.Segment, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.brightness = self._io.read_u1()
            self.colour = govee_shared.GoveeShared.Rgb(self._io)
            self.colour._read()
            self._dirty = False


        def _fetch_instances(self):
            pass
            self.colour._fetch_instances()


        def _write__seq(self, io=None):
            super(StatusReply.Segment, self)._write__seq(io)
            self._io.write_u1(self.brightness)
            self.colour._write__seq(self._io)


        def _check(self):
            self._dirty = False


    class SegmentsBody(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(StatusReply.SegmentsBody, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.group = self._io.read_u1()
            if not self.group >= 1:
                raise kaitaistruct.ValidationLessThanError(1, self.group, self._io, u"/types/segments_body/seq/0")
            if not self.group <= 5:
                raise kaitaistruct.ValidationGreaterThanError(5, self.group, self._io, u"/types/segments_body/seq/0")
            if  ((self.group >= 1) and (self.group <= 5)) :
                pass
                self.segments = []
                for i in range(3):
                    _t_segments = StatusReply.Segment(self._io, self, self._root)
                    try:
                        _t_segments._read()
                    finally:
                        self.segments.append(_t_segments)


            self.padding = []
            i = 0
            while not self._io.is_eof():
                self.padding.append(self._io.read_u1())
                if not self.padding[i] == 0:
                    raise kaitaistruct.ValidationNotEqualError(0, self.padding[i], self._io, u"/types/segments_body/seq/2")
                i += 1

            self._dirty = False


        def _fetch_instances(self):
            pass
            if  ((self.group >= 1) and (self.group <= 5)) :
                pass
                for i in range(len(self.segments)):
                    pass
                    self.segments[i]._fetch_instances()


            for i in range(len(self.padding)):
                pass



        def _write__seq(self, io=None):
            super(StatusReply.SegmentsBody, self)._write__seq(io)
            self._io.write_u1(self.group)
            if  ((self.group >= 1) and (self.group <= 5)) :
                pass
                for i in range(len(self.segments)):
                    pass
                    self.segments[i]._write__seq(self._io)


            for i in range(len(self.padding)):
                pass
                if self._io.is_eof():
                    raise kaitaistruct.ConsistencyError(u"padding", 0, self._io.size() - self._io.pos())
                self._io.write_u1(self.padding[i])

            if not self._io.is_eof():
                raise kaitaistruct.ConsistencyError(u"padding", 0, self._io.size() - self._io.pos())


        def _check(self):
            if not self.group >= 1:
                raise kaitaistruct.ValidationLessThanError(1, self.group, None, u"/types/segments_body/seq/0")
            if not self.group <= 5:
                raise kaitaistruct.ValidationGreaterThanError(5, self.group, None, u"/types/segments_body/seq/0")
            if  ((self.group >= 1) and (self.group <= 5)) :
                pass
                if len(self.segments) != 3:
                    raise kaitaistruct.ConsistencyError(u"segments", 3, len(self.segments))
                for i in range(len(self.segments)):
                    pass
                    if self.segments[i]._root != self._root:
                        raise kaitaistruct.ConsistencyError(u"segments", self._root, self.segments[i]._root)
                    if self.segments[i]._parent != self:
                        raise kaitaistruct.ConsistencyError(u"segments", self, self.segments[i]._parent)


            for i in range(len(self.padding)):
                pass
                if not self.padding[i] == 0:
                    raise kaitaistruct.ValidationNotEqualError(0, self.padding[i], None, u"/types/segments_body/seq/2")

            self._dirty = False


    class VersionBody(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(StatusReply.VersionBody, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.text = (self._io.read_bytes_term(0, False, True, True)).decode(u"ASCII")
            self.padding = []
            i = 0
            while not self._io.is_eof():
                self.padding.append(self._io.read_u1())
                if not self.padding[i] == 0:
                    raise kaitaistruct.ValidationNotEqualError(0, self.padding[i], self._io, u"/types/version_body/seq/1")
                i += 1

            self._dirty = False


        def _fetch_instances(self):
            pass
            for i in range(len(self.padding)):
                pass



        def _write__seq(self, io=None):
            super(StatusReply.VersionBody, self)._write__seq(io)
            self._io.write_bytes((self.text).encode(u"ASCII"))
            self._io.write_u1(0)
            for i in range(len(self.padding)):
                pass
                if self._io.is_eof():
                    raise kaitaistruct.ConsistencyError(u"padding", 0, self._io.size() - self._io.pos())
                self._io.write_u1(self.padding[i])

            if not self._io.is_eof():
                raise kaitaistruct.ConsistencyError(u"padding", 0, self._io.size() - self._io.pos())


        def _check(self):
            if KaitaiStream.byte_array_index_of((self.text).encode(u"ASCII"), 0) != -1:
                raise kaitaistruct.ConsistencyError(u"text", -1, KaitaiStream.byte_array_index_of((self.text).encode(u"ASCII"), 0))
            for i in range(len(self.padding)):
                pass
                if not self.padding[i] == 0:
                    raise kaitaistruct.ValidationNotEqualError(0, self.padding[i], None, u"/types/version_body/seq/1")

            self._dirty = False



