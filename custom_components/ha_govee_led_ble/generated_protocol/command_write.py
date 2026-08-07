# This is a generated file! Please edit source .ksy file and use kaitai-struct-compiler to rebuild
# type: ignore

import kaitaistruct
from kaitaistruct import ReadWriteKaitaiStruct, KaitaiStream, BytesIO
from custom_components.ha_govee_led_ble.generated_protocol import govee_shared
from custom_components.ha_govee_led_ble.generated_protocol import govee_common
from enum import IntEnum


if getattr(kaitaistruct, 'API_VERSION', (0, 9)) < (0, 11):
    raise Exception("Incompatible Kaitai Struct Python API: 0.11 or later is required, but you have %s" % (kaitaistruct.__version__))

class CommandWrite(ReadWriteKaitaiStruct):
    """H617A 20-byte command frame. The final byte is the XOR of bytes 0 through 18.
    """

    class CommandOp(IntEnum):
        power = 1
        brightness = 4
        multi = 5
        multi_effect = 163

    class MultiSub(IntEnum):
        scene = 4
        diy = 10
        music = 19
        static = 21
    def __init__(self, _io=None, _parent=None, _root=None):
        super(CommandWrite, self).__init__(_io)
        self._parent = _parent
        self._root = _root or self

    def _read(self):
        self.header = self._io.read_bytes(1)
        if not self.header == b"\x33":
            raise kaitaistruct.ValidationNotEqualError(b"\x33", self.header, self._io, u"/seq/0")
        self.opcode = KaitaiStream.resolve_enum(CommandWrite.CommandOp, self._io.read_u1())
        _on = self.opcode
        if _on == CommandWrite.CommandOp.brightness:
            pass
            self._raw_body = self._io.read_bytes(17)
            _io__raw_body = KaitaiStream(BytesIO(self._raw_body))
            self.body = CommandWrite.BrightnessCmd(_io__raw_body, self, self._root)
            self.body._read()
        elif _on == CommandWrite.CommandOp.multi:
            pass
            self._raw_body = self._io.read_bytes(17)
            _io__raw_body = KaitaiStream(BytesIO(self._raw_body))
            self.body = CommandWrite.MultiCmd(_io__raw_body, self, self._root)
            self.body._read()
        elif _on == CommandWrite.CommandOp.multi_effect:
            pass
            self._raw_body = self._io.read_bytes(17)
            _io__raw_body = KaitaiStream(BytesIO(self._raw_body))
            self.body = CommandWrite.MultiEffectCmd(_io__raw_body, self, self._root)
            self.body._read()
        elif _on == CommandWrite.CommandOp.power:
            pass
            self._raw_body = self._io.read_bytes(17)
            _io__raw_body = KaitaiStream(BytesIO(self._raw_body))
            self.body = CommandWrite.PowerCmd(_io__raw_body, self, self._root)
            self.body._read()
        else:
            pass
            self.body = self._io.read_bytes(17)
        self.checksum = self._io.read_u1()
        self._dirty = False


    def _fetch_instances(self):
        pass
        _on = self.opcode
        if _on == CommandWrite.CommandOp.brightness:
            pass
            self.body._fetch_instances()
        elif _on == CommandWrite.CommandOp.multi:
            pass
            self.body._fetch_instances()
        elif _on == CommandWrite.CommandOp.multi_effect:
            pass
            self.body._fetch_instances()
        elif _on == CommandWrite.CommandOp.power:
            pass
            self.body._fetch_instances()
        else:
            pass


    def _write__seq(self, io=None):
        super(CommandWrite, self)._write__seq(io)
        self._io.write_bytes(self.header)
        self._io.write_u1(int(self.opcode))
        _on = self.opcode
        if _on == CommandWrite.CommandOp.brightness:
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
        elif _on == CommandWrite.CommandOp.multi:
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
        elif _on == CommandWrite.CommandOp.multi_effect:
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
        elif _on == CommandWrite.CommandOp.power:
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
        if not self.header == b"\x33":
            raise kaitaistruct.ValidationNotEqualError(b"\x33", self.header, None, u"/seq/0")
        _on = self.opcode
        if _on == CommandWrite.CommandOp.brightness:
            pass
            if self.body._root != self._root:
                raise kaitaistruct.ConsistencyError(u"body", self._root, self.body._root)
            if self.body._parent != self:
                raise kaitaistruct.ConsistencyError(u"body", self, self.body._parent)
        elif _on == CommandWrite.CommandOp.multi:
            pass
            if self.body._root != self._root:
                raise kaitaistruct.ConsistencyError(u"body", self._root, self.body._root)
            if self.body._parent != self:
                raise kaitaistruct.ConsistencyError(u"body", self, self.body._parent)
        elif _on == CommandWrite.CommandOp.multi_effect:
            pass
            if self.body._root != self._root:
                raise kaitaistruct.ConsistencyError(u"body", self._root, self.body._root)
            if self.body._parent != self:
                raise kaitaistruct.ConsistencyError(u"body", self, self.body._parent)
        elif _on == CommandWrite.CommandOp.power:
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

    class BrightnessCmd(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(CommandWrite.BrightnessCmd, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.percent = self._io.read_u1()
            if not self.percent <= 100:
                raise kaitaistruct.ValidationGreaterThanError(100, self.percent, self._io, u"/types/brightness_cmd/seq/0")
            self._dirty = False


        def _fetch_instances(self):
            pass


        def _write__seq(self, io=None):
            super(CommandWrite.BrightnessCmd, self)._write__seq(io)
            self._io.write_u1(self.percent)


        def _check(self):
            if not self.percent <= 100:
                raise kaitaistruct.ValidationGreaterThanError(100, self.percent, None, u"/types/brightness_cmd/seq/0")
            self._dirty = False


    class MultiCmd(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(CommandWrite.MultiCmd, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.sub = KaitaiStream.resolve_enum(CommandWrite.MultiSub, self._io.read_u1())
            _on = self.sub
            if _on == CommandWrite.MultiSub.diy:
                pass
                self._raw_sub_body = self._io.read_bytes(16)
                _io__raw_sub_body = KaitaiStream(BytesIO(self._raw_sub_body))
                self.sub_body = govee_common.GoveeCommon.DiySelector(_io__raw_sub_body)
                self.sub_body._read()
            elif _on == CommandWrite.MultiSub.music:
                pass
                self._raw_sub_body = self._io.read_bytes(16)
                _io__raw_sub_body = KaitaiStream(BytesIO(self._raw_sub_body))
                self.sub_body = govee_common.GoveeCommon.MusicSelector(_io__raw_sub_body)
                self.sub_body._read()
            elif _on == CommandWrite.MultiSub.scene:
                pass
                self._raw_sub_body = self._io.read_bytes(16)
                _io__raw_sub_body = KaitaiStream(BytesIO(self._raw_sub_body))
                self.sub_body = CommandWrite.SceneActivate(_io__raw_sub_body, self, self._root)
                self.sub_body._read()
            elif _on == CommandWrite.MultiSub.static:
                pass
                self._raw_sub_body = self._io.read_bytes(16)
                _io__raw_sub_body = KaitaiStream(BytesIO(self._raw_sub_body))
                self.sub_body = CommandWrite.StaticCmd(_io__raw_sub_body, self, self._root)
                self.sub_body._read()
            else:
                pass
                self.sub_body = self._io.read_bytes(16)
            self._dirty = False


        def _fetch_instances(self):
            pass
            _on = self.sub
            if _on == CommandWrite.MultiSub.diy:
                pass
                self.sub_body._fetch_instances()
            elif _on == CommandWrite.MultiSub.music:
                pass
                self.sub_body._fetch_instances()
            elif _on == CommandWrite.MultiSub.scene:
                pass
                self.sub_body._fetch_instances()
            elif _on == CommandWrite.MultiSub.static:
                pass
                self.sub_body._fetch_instances()
            else:
                pass


        def _write__seq(self, io=None):
            super(CommandWrite.MultiCmd, self)._write__seq(io)
            self._io.write_u1(int(self.sub))
            _on = self.sub
            if _on == CommandWrite.MultiSub.diy:
                pass
                _io__raw_sub_body = KaitaiStream(BytesIO(bytearray(16)))
                self._io.add_child_stream(_io__raw_sub_body)
                _pos2 = self._io.pos()
                self._io.seek(self._io.pos() + (16))
                def handler(parent, _io__raw_sub_body=_io__raw_sub_body):
                    self._raw_sub_body = _io__raw_sub_body.to_byte_array()
                    if len(self._raw_sub_body) != 16:
                        raise kaitaistruct.ConsistencyError(u"raw(sub_body)", 16, len(self._raw_sub_body))
                    parent.write_bytes(self._raw_sub_body)
                _io__raw_sub_body.write_back_handler = KaitaiStream.WriteBackHandler(_pos2, handler)
                self.sub_body._write__seq(_io__raw_sub_body)
            elif _on == CommandWrite.MultiSub.music:
                pass
                _io__raw_sub_body = KaitaiStream(BytesIO(bytearray(16)))
                self._io.add_child_stream(_io__raw_sub_body)
                _pos2 = self._io.pos()
                self._io.seek(self._io.pos() + (16))
                def handler(parent, _io__raw_sub_body=_io__raw_sub_body):
                    self._raw_sub_body = _io__raw_sub_body.to_byte_array()
                    if len(self._raw_sub_body) != 16:
                        raise kaitaistruct.ConsistencyError(u"raw(sub_body)", 16, len(self._raw_sub_body))
                    parent.write_bytes(self._raw_sub_body)
                _io__raw_sub_body.write_back_handler = KaitaiStream.WriteBackHandler(_pos2, handler)
                self.sub_body._write__seq(_io__raw_sub_body)
            elif _on == CommandWrite.MultiSub.scene:
                pass
                _io__raw_sub_body = KaitaiStream(BytesIO(bytearray(16)))
                self._io.add_child_stream(_io__raw_sub_body)
                _pos2 = self._io.pos()
                self._io.seek(self._io.pos() + (16))
                def handler(parent, _io__raw_sub_body=_io__raw_sub_body):
                    self._raw_sub_body = _io__raw_sub_body.to_byte_array()
                    if len(self._raw_sub_body) != 16:
                        raise kaitaistruct.ConsistencyError(u"raw(sub_body)", 16, len(self._raw_sub_body))
                    parent.write_bytes(self._raw_sub_body)
                _io__raw_sub_body.write_back_handler = KaitaiStream.WriteBackHandler(_pos2, handler)
                self.sub_body._write__seq(_io__raw_sub_body)
            elif _on == CommandWrite.MultiSub.static:
                pass
                _io__raw_sub_body = KaitaiStream(BytesIO(bytearray(16)))
                self._io.add_child_stream(_io__raw_sub_body)
                _pos2 = self._io.pos()
                self._io.seek(self._io.pos() + (16))
                def handler(parent, _io__raw_sub_body=_io__raw_sub_body):
                    self._raw_sub_body = _io__raw_sub_body.to_byte_array()
                    if len(self._raw_sub_body) != 16:
                        raise kaitaistruct.ConsistencyError(u"raw(sub_body)", 16, len(self._raw_sub_body))
                    parent.write_bytes(self._raw_sub_body)
                _io__raw_sub_body.write_back_handler = KaitaiStream.WriteBackHandler(_pos2, handler)
                self.sub_body._write__seq(_io__raw_sub_body)
            else:
                pass
                self._io.write_bytes(self.sub_body)


        def _check(self):
            _on = self.sub
            if _on == CommandWrite.MultiSub.diy:
                pass
            elif _on == CommandWrite.MultiSub.music:
                pass
            elif _on == CommandWrite.MultiSub.scene:
                pass
                if self.sub_body._root != self._root:
                    raise kaitaistruct.ConsistencyError(u"sub_body", self._root, self.sub_body._root)
                if self.sub_body._parent != self:
                    raise kaitaistruct.ConsistencyError(u"sub_body", self, self.sub_body._parent)
            elif _on == CommandWrite.MultiSub.static:
                pass
                if self.sub_body._root != self._root:
                    raise kaitaistruct.ConsistencyError(u"sub_body", self._root, self.sub_body._root)
                if self.sub_body._parent != self:
                    raise kaitaistruct.ConsistencyError(u"sub_body", self, self.sub_body._parent)
            else:
                pass
                if len(self.sub_body) != 16:
                    raise kaitaistruct.ConsistencyError(u"sub_body", 16, len(self.sub_body))
            self._dirty = False


    class MultiEffectCmd(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(CommandWrite.MultiEffectCmd, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.flag = self._io.read_u1()
            self.padding = []
            i = 0
            while not self._io.is_eof():
                self.padding.append(self._io.read_u1())
                if not self.padding[i] == 0:
                    raise kaitaistruct.ValidationNotEqualError(0, self.padding[i], self._io, u"/types/multi_effect_cmd/seq/1")
                i += 1

            self._dirty = False


        def _fetch_instances(self):
            pass
            for i in range(len(self.padding)):
                pass



        def _write__seq(self, io=None):
            super(CommandWrite.MultiEffectCmd, self)._write__seq(io)
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
                    raise kaitaistruct.ValidationNotEqualError(0, self.padding[i], None, u"/types/multi_effect_cmd/seq/1")

            self._dirty = False


    class PowerCmd(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(CommandWrite.PowerCmd, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.is_on = self._io.read_u1()
            self._dirty = False


        def _fetch_instances(self):
            pass


        def _write__seq(self, io=None):
            super(CommandWrite.PowerCmd, self)._write__seq(io)
            self._io.write_u1(self.is_on)


        def _check(self):
            self._dirty = False


    class SceneActivate(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(CommandWrite.SceneActivate, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.code = self._io.read_u2le()
            self.scene_type = self._io.read_u1()
            self._dirty = False


        def _fetch_instances(self):
            pass


        def _write__seq(self, io=None):
            super(CommandWrite.SceneActivate, self)._write__seq(io)
            self._io.write_u2le(self.code)
            self._io.write_u1(self.scene_type)


        def _check(self):
            self._dirty = False


    class SegmentMask(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(CommandWrite.SegmentMask, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.bits = self._io.read_u2le()
            self._dirty = False


        def _fetch_instances(self):
            pass


        def _write__seq(self, io=None):
            super(CommandWrite.SegmentMask, self)._write__seq(io)
            self._io.write_u2le(self.bits)


        def _check(self):
            self._dirty = False


    class StaticBrightness(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(CommandWrite.StaticBrightness, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.percent = self._io.read_u1()
            if not self.percent <= 100:
                raise kaitaistruct.ValidationGreaterThanError(100, self.percent, self._io, u"/types/static_brightness/seq/0")
            self.mask = CommandWrite.SegmentMask(self._io, self, self._root)
            self.mask._read()
            self._dirty = False


        def _fetch_instances(self):
            pass
            self.mask._fetch_instances()


        def _write__seq(self, io=None):
            super(CommandWrite.StaticBrightness, self)._write__seq(io)
            self._io.write_u1(self.percent)
            self.mask._write__seq(self._io)


        def _check(self):
            if not self.percent <= 100:
                raise kaitaistruct.ValidationGreaterThanError(100, self.percent, None, u"/types/static_brightness/seq/0")
            if self.mask._root != self._root:
                raise kaitaistruct.ConsistencyError(u"mask", self._root, self.mask._root)
            if self.mask._parent != self:
                raise kaitaistruct.ConsistencyError(u"mask", self, self.mask._parent)
            self._dirty = False


    class StaticBrightnessAll(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(CommandWrite.StaticBrightnessAll, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.segment_percent = []
            i = 0
            while not self._io.is_eof():
                self.segment_percent.append(self._io.read_u1())
                if not self.segment_percent[i] <= 100:
                    raise kaitaistruct.ValidationGreaterThanError(100, self.segment_percent[i], self._io, u"/types/static_brightness_all/seq/0")
                i += 1

            self._dirty = False


        def _fetch_instances(self):
            pass
            for i in range(len(self.segment_percent)):
                pass



        def _write__seq(self, io=None):
            super(CommandWrite.StaticBrightnessAll, self)._write__seq(io)
            for i in range(len(self.segment_percent)):
                pass
                if self._io.is_eof():
                    raise kaitaistruct.ConsistencyError(u"segment_percent", 0, self._io.size() - self._io.pos())
                self._io.write_u1(self.segment_percent[i])

            if not self._io.is_eof():
                raise kaitaistruct.ConsistencyError(u"segment_percent", 0, self._io.size() - self._io.pos())


        def _check(self):
            for i in range(len(self.segment_percent)):
                pass
                if not self.segment_percent[i] <= 100:
                    raise kaitaistruct.ValidationGreaterThanError(100, self.segment_percent[i], None, u"/types/static_brightness_all/seq/0")

            self._dirty = False


    class StaticCmd(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(CommandWrite.StaticCmd, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.static_sub = self._io.read_u1()
            _on = self.static_sub
            if _on == 1:
                pass
                self._raw_static_body = self._io.read_bytes(15)
                _io__raw_static_body = KaitaiStream(BytesIO(self._raw_static_body))
                self.static_body = CommandWrite.StaticColor(_io__raw_static_body, self, self._root)
                self.static_body._read()
            elif _on == 2:
                pass
                self._raw_static_body = self._io.read_bytes(15)
                _io__raw_static_body = KaitaiStream(BytesIO(self._raw_static_body))
                self.static_body = CommandWrite.StaticBrightness(_io__raw_static_body, self, self._root)
                self.static_body._read()
            elif _on == 3:
                pass
                self._raw_static_body = self._io.read_bytes(15)
                _io__raw_static_body = KaitaiStream(BytesIO(self._raw_static_body))
                self.static_body = CommandWrite.StaticBrightnessAll(_io__raw_static_body, self, self._root)
                self.static_body._read()
            else:
                pass
                self.static_body = self._io.read_bytes(15)
            self._dirty = False


        def _fetch_instances(self):
            pass
            _on = self.static_sub
            if _on == 1:
                pass
                self.static_body._fetch_instances()
            elif _on == 2:
                pass
                self.static_body._fetch_instances()
            elif _on == 3:
                pass
                self.static_body._fetch_instances()
            else:
                pass


        def _write__seq(self, io=None):
            super(CommandWrite.StaticCmd, self)._write__seq(io)
            self._io.write_u1(self.static_sub)
            _on = self.static_sub
            if _on == 1:
                pass
                _io__raw_static_body = KaitaiStream(BytesIO(bytearray(15)))
                self._io.add_child_stream(_io__raw_static_body)
                _pos2 = self._io.pos()
                self._io.seek(self._io.pos() + (15))
                def handler(parent, _io__raw_static_body=_io__raw_static_body):
                    self._raw_static_body = _io__raw_static_body.to_byte_array()
                    if len(self._raw_static_body) != 15:
                        raise kaitaistruct.ConsistencyError(u"raw(static_body)", 15, len(self._raw_static_body))
                    parent.write_bytes(self._raw_static_body)
                _io__raw_static_body.write_back_handler = KaitaiStream.WriteBackHandler(_pos2, handler)
                self.static_body._write__seq(_io__raw_static_body)
            elif _on == 2:
                pass
                _io__raw_static_body = KaitaiStream(BytesIO(bytearray(15)))
                self._io.add_child_stream(_io__raw_static_body)
                _pos2 = self._io.pos()
                self._io.seek(self._io.pos() + (15))
                def handler(parent, _io__raw_static_body=_io__raw_static_body):
                    self._raw_static_body = _io__raw_static_body.to_byte_array()
                    if len(self._raw_static_body) != 15:
                        raise kaitaistruct.ConsistencyError(u"raw(static_body)", 15, len(self._raw_static_body))
                    parent.write_bytes(self._raw_static_body)
                _io__raw_static_body.write_back_handler = KaitaiStream.WriteBackHandler(_pos2, handler)
                self.static_body._write__seq(_io__raw_static_body)
            elif _on == 3:
                pass
                _io__raw_static_body = KaitaiStream(BytesIO(bytearray(15)))
                self._io.add_child_stream(_io__raw_static_body)
                _pos2 = self._io.pos()
                self._io.seek(self._io.pos() + (15))
                def handler(parent, _io__raw_static_body=_io__raw_static_body):
                    self._raw_static_body = _io__raw_static_body.to_byte_array()
                    if len(self._raw_static_body) != 15:
                        raise kaitaistruct.ConsistencyError(u"raw(static_body)", 15, len(self._raw_static_body))
                    parent.write_bytes(self._raw_static_body)
                _io__raw_static_body.write_back_handler = KaitaiStream.WriteBackHandler(_pos2, handler)
                self.static_body._write__seq(_io__raw_static_body)
            else:
                pass
                self._io.write_bytes(self.static_body)


        def _check(self):
            _on = self.static_sub
            if _on == 1:
                pass
                if self.static_body._root != self._root:
                    raise kaitaistruct.ConsistencyError(u"static_body", self._root, self.static_body._root)
                if self.static_body._parent != self:
                    raise kaitaistruct.ConsistencyError(u"static_body", self, self.static_body._parent)
            elif _on == 2:
                pass
                if self.static_body._root != self._root:
                    raise kaitaistruct.ConsistencyError(u"static_body", self._root, self.static_body._root)
                if self.static_body._parent != self:
                    raise kaitaistruct.ConsistencyError(u"static_body", self, self.static_body._parent)
            elif _on == 3:
                pass
                if self.static_body._root != self._root:
                    raise kaitaistruct.ConsistencyError(u"static_body", self._root, self.static_body._root)
                if self.static_body._parent != self:
                    raise kaitaistruct.ConsistencyError(u"static_body", self, self.static_body._parent)
            else:
                pass
                if len(self.static_body) != 15:
                    raise kaitaistruct.ConsistencyError(u"static_body", 15, len(self.static_body))
            self._dirty = False


    class StaticColor(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(CommandWrite.StaticColor, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.rgb_direct = govee_shared.GoveeShared.Rgb(self._io)
            self.rgb_direct._read()
            self.kelvin = self._io.read_u2be()
            self.rgb_preview = govee_shared.GoveeShared.Rgb(self._io)
            self.rgb_preview._read()
            self.mask = CommandWrite.SegmentMask(self._io, self, self._root)
            self.mask._read()
            self._dirty = False


        def _fetch_instances(self):
            pass
            self.rgb_direct._fetch_instances()
            self.rgb_preview._fetch_instances()
            self.mask._fetch_instances()


        def _write__seq(self, io=None):
            super(CommandWrite.StaticColor, self)._write__seq(io)
            self.rgb_direct._write__seq(self._io)
            self._io.write_u2be(self.kelvin)
            self.rgb_preview._write__seq(self._io)
            self.mask._write__seq(self._io)


        def _check(self):
            if self.mask._root != self._root:
                raise kaitaistruct.ConsistencyError(u"mask", self._root, self.mask._root)
            if self.mask._parent != self:
                raise kaitaistruct.ConsistencyError(u"mask", self, self.mask._parent)
            self._dirty = False



