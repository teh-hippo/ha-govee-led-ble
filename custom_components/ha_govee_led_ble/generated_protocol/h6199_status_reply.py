# This is a generated file! Please edit source .ksy file and use kaitai-struct-compiler to rebuild
# type: ignore

import kaitaistruct
from kaitaistruct import ReadWriteKaitaiStruct, KaitaiStream, BytesIO
from custom_components.ha_govee_led_ble.generated_protocol import govee_shared
from enum import IntEnum


if getattr(kaitaistruct, 'API_VERSION', (0, 9)) < (0, 11):
    raise Exception("Incompatible Kaitai Struct Python API: 0.11 or later is required, but you have %s" % (kaitaistruct.__version__))

class H6199StatusReply(ReadWriteKaitaiStruct):
    """H6199 20-byte status reply. The final byte is the XOR of bytes 0 through 18.
    """

    class BlankScreenDetection(IntEnum):
        low_brightness = 1
        same_tone = 2

    class DisplaySetting(IntEnum):
        white_balance = 0
        blank_screen = 10

    class ModeSel(IntEnum):
        video = 0
        scene = 4
        music = 19
        static_colour = 21

    class StatusDomain(IntEnum):
        power = 1
        brightness = 4
        colour_mode = 5
        firmware = 6
        hardware = 7
        subordinate_20 = 32
        subordinate_21 = 33
        segments = 165
        display_setting = 169
        relative_brightness = 174

    class VideoRegion(IntEnum):
        part = 0
        all = 1

    class VideoSource(IntEnum):
        movie = 0
        game = 1
    def __init__(self, _io=None, _parent=None, _root=None):
        super(H6199StatusReply, self).__init__(_io)
        self._parent = _parent
        self._root = _root or self

    def _read(self):
        self.header = self._io.read_bytes(1)
        if not self.header == b"\xAA":
            raise kaitaistruct.ValidationNotEqualError(b"\xAA", self.header, self._io, u"/seq/0")
        self.domain = KaitaiStream.resolve_enum(H6199StatusReply.StatusDomain, self._io.read_u1())
        _on = self.domain
        if _on == H6199StatusReply.StatusDomain.brightness:
            pass
            self._raw_body = self._io.read_bytes(17)
            _io__raw_body = KaitaiStream(BytesIO(self._raw_body))
            self.body = H6199StatusReply.BrightnessBody(_io__raw_body, self, self._root)
            self.body._read()
        elif _on == H6199StatusReply.StatusDomain.colour_mode:
            pass
            self._raw_body = self._io.read_bytes(17)
            _io__raw_body = KaitaiStream(BytesIO(self._raw_body))
            self.body = H6199StatusReply.ColourModeBody(_io__raw_body, self, self._root)
            self.body._read()
        elif _on == H6199StatusReply.StatusDomain.display_setting:
            pass
            self._raw_body = self._io.read_bytes(17)
            _io__raw_body = KaitaiStream(BytesIO(self._raw_body))
            self.body = H6199StatusReply.DisplaySettingBody(_io__raw_body, self, self._root)
            self.body._read()
        elif _on == H6199StatusReply.StatusDomain.firmware:
            pass
            self._raw_body = self._io.read_bytes(17)
            _io__raw_body = KaitaiStream(BytesIO(self._raw_body))
            self.body = H6199StatusReply.VersionBody(_io__raw_body, self, self._root)
            self.body._read()
        elif _on == H6199StatusReply.StatusDomain.hardware:
            pass
            self._raw_body = self._io.read_bytes(17)
            _io__raw_body = KaitaiStream(BytesIO(self._raw_body))
            self.body = H6199StatusReply.HardwareVersionBody(_io__raw_body, self, self._root)
            self.body._read()
        elif _on == H6199StatusReply.StatusDomain.power:
            pass
            self._raw_body = self._io.read_bytes(17)
            _io__raw_body = KaitaiStream(BytesIO(self._raw_body))
            self.body = H6199StatusReply.PowerBody(_io__raw_body, self, self._root)
            self.body._read()
        elif _on == H6199StatusReply.StatusDomain.relative_brightness:
            pass
            self._raw_body = self._io.read_bytes(17)
            _io__raw_body = KaitaiStream(BytesIO(self._raw_body))
            self.body = H6199StatusReply.RelativeBrightnessBody(_io__raw_body, self, self._root)
            self.body._read()
        elif _on == H6199StatusReply.StatusDomain.segments:
            pass
            self._raw_body = self._io.read_bytes(17)
            _io__raw_body = KaitaiStream(BytesIO(self._raw_body))
            self.body = H6199StatusReply.SegmentGroupBody(_io__raw_body, self, self._root)
            self.body._read()
        elif _on == H6199StatusReply.StatusDomain.subordinate_20:
            pass
            self._raw_body = self._io.read_bytes(17)
            _io__raw_body = KaitaiStream(BytesIO(self._raw_body))
            self.body = H6199StatusReply.VersionBody(_io__raw_body, self, self._root)
            self.body._read()
        elif _on == H6199StatusReply.StatusDomain.subordinate_21:
            pass
            self._raw_body = self._io.read_bytes(17)
            _io__raw_body = KaitaiStream(BytesIO(self._raw_body))
            self.body = H6199StatusReply.VersionBody(_io__raw_body, self, self._root)
            self.body._read()
        else:
            pass
            self.body = self._io.read_bytes(17)
        self.checksum = self._io.read_u1()
        self._dirty = False


    def _fetch_instances(self):
        pass
        _on = self.domain
        if _on == H6199StatusReply.StatusDomain.brightness:
            pass
            self.body._fetch_instances()
        elif _on == H6199StatusReply.StatusDomain.colour_mode:
            pass
            self.body._fetch_instances()
        elif _on == H6199StatusReply.StatusDomain.display_setting:
            pass
            self.body._fetch_instances()
        elif _on == H6199StatusReply.StatusDomain.firmware:
            pass
            self.body._fetch_instances()
        elif _on == H6199StatusReply.StatusDomain.hardware:
            pass
            self.body._fetch_instances()
        elif _on == H6199StatusReply.StatusDomain.power:
            pass
            self.body._fetch_instances()
        elif _on == H6199StatusReply.StatusDomain.relative_brightness:
            pass
            self.body._fetch_instances()
        elif _on == H6199StatusReply.StatusDomain.segments:
            pass
            self.body._fetch_instances()
        elif _on == H6199StatusReply.StatusDomain.subordinate_20:
            pass
            self.body._fetch_instances()
        elif _on == H6199StatusReply.StatusDomain.subordinate_21:
            pass
            self.body._fetch_instances()
        else:
            pass


    def _write__seq(self, io=None):
        super(H6199StatusReply, self)._write__seq(io)
        self._io.write_bytes(self.header)
        self._io.write_u1(int(self.domain))
        _on = self.domain
        if _on == H6199StatusReply.StatusDomain.brightness:
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
        elif _on == H6199StatusReply.StatusDomain.colour_mode:
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
        elif _on == H6199StatusReply.StatusDomain.display_setting:
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
        elif _on == H6199StatusReply.StatusDomain.firmware:
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
        elif _on == H6199StatusReply.StatusDomain.hardware:
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
        elif _on == H6199StatusReply.StatusDomain.power:
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
        elif _on == H6199StatusReply.StatusDomain.relative_brightness:
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
        elif _on == H6199StatusReply.StatusDomain.segments:
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
        elif _on == H6199StatusReply.StatusDomain.subordinate_20:
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
        elif _on == H6199StatusReply.StatusDomain.subordinate_21:
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
        if _on == H6199StatusReply.StatusDomain.brightness:
            pass
            if self.body._root != self._root:
                raise kaitaistruct.ConsistencyError(u"body", self._root, self.body._root)
            if self.body._parent != self:
                raise kaitaistruct.ConsistencyError(u"body", self, self.body._parent)
        elif _on == H6199StatusReply.StatusDomain.colour_mode:
            pass
            if self.body._root != self._root:
                raise kaitaistruct.ConsistencyError(u"body", self._root, self.body._root)
            if self.body._parent != self:
                raise kaitaistruct.ConsistencyError(u"body", self, self.body._parent)
        elif _on == H6199StatusReply.StatusDomain.display_setting:
            pass
            if self.body._root != self._root:
                raise kaitaistruct.ConsistencyError(u"body", self._root, self.body._root)
            if self.body._parent != self:
                raise kaitaistruct.ConsistencyError(u"body", self, self.body._parent)
        elif _on == H6199StatusReply.StatusDomain.firmware:
            pass
            if self.body._root != self._root:
                raise kaitaistruct.ConsistencyError(u"body", self._root, self.body._root)
            if self.body._parent != self:
                raise kaitaistruct.ConsistencyError(u"body", self, self.body._parent)
        elif _on == H6199StatusReply.StatusDomain.hardware:
            pass
            if self.body._root != self._root:
                raise kaitaistruct.ConsistencyError(u"body", self._root, self.body._root)
            if self.body._parent != self:
                raise kaitaistruct.ConsistencyError(u"body", self, self.body._parent)
        elif _on == H6199StatusReply.StatusDomain.power:
            pass
            if self.body._root != self._root:
                raise kaitaistruct.ConsistencyError(u"body", self._root, self.body._root)
            if self.body._parent != self:
                raise kaitaistruct.ConsistencyError(u"body", self, self.body._parent)
        elif _on == H6199StatusReply.StatusDomain.relative_brightness:
            pass
            if self.body._root != self._root:
                raise kaitaistruct.ConsistencyError(u"body", self._root, self.body._root)
            if self.body._parent != self:
                raise kaitaistruct.ConsistencyError(u"body", self, self.body._parent)
        elif _on == H6199StatusReply.StatusDomain.segments:
            pass
            if self.body._root != self._root:
                raise kaitaistruct.ConsistencyError(u"body", self._root, self.body._root)
            if self.body._parent != self:
                raise kaitaistruct.ConsistencyError(u"body", self, self.body._parent)
        elif _on == H6199StatusReply.StatusDomain.subordinate_20:
            pass
            if self.body._root != self._root:
                raise kaitaistruct.ConsistencyError(u"body", self._root, self.body._root)
            if self.body._parent != self:
                raise kaitaistruct.ConsistencyError(u"body", self, self.body._parent)
        elif _on == H6199StatusReply.StatusDomain.subordinate_21:
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

    class BlankScreenState(ReadWriteKaitaiStruct):
        """Blank-screen detection policy. The app parser reads the same two modes and second-based
        durations written by h6199_command_write::blank_screen_payload.
        """
        def __init__(self, _io=None, _parent=None, _root=None):
            super(H6199StatusReply.BlankScreenState, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.is_enabled = self._io.read_u1()
            self.detection = KaitaiStream.resolve_enum(H6199StatusReply.BlankScreenDetection, self._io.read_u1())
            self.low_brightness_duration_seconds = self._io.read_u2le()
            self.same_tone_duration_seconds = self._io.read_u2le()
            self._dirty = False


        def _fetch_instances(self):
            pass


        def _write__seq(self, io=None):
            super(H6199StatusReply.BlankScreenState, self)._write__seq(io)
            self._io.write_u1(self.is_enabled)
            self._io.write_u1(int(self.detection))
            self._io.write_u2le(self.low_brightness_duration_seconds)
            self._io.write_u2le(self.same_tone_duration_seconds)


        def _check(self):
            self._dirty = False


    class BrightnessBody(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(H6199StatusReply.BrightnessBody, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.percent = self._io.read_u1()
            self._dirty = False


        def _fetch_instances(self):
            pass


        def _write__seq(self, io=None):
            super(H6199StatusReply.BrightnessBody, self)._write__seq(io)
            self._io.write_u1(self.percent)


        def _check(self):
            self._dirty = False


    class ColourModeBody(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(H6199StatusReply.ColourModeBody, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.mode = KaitaiStream.resolve_enum(H6199StatusReply.ModeSel, self._io.read_u1())
            _on = self.mode
            if _on == H6199StatusReply.ModeSel.music:
                pass
                self._raw_detail = self._io.read_bytes(16)
                _io__raw_detail = KaitaiStream(BytesIO(self._raw_detail))
                self.detail = H6199StatusReply.MusicState(_io__raw_detail, self, self._root)
                self.detail._read()
            elif _on == H6199StatusReply.ModeSel.scene:
                pass
                self._raw_detail = self._io.read_bytes(16)
                _io__raw_detail = KaitaiStream(BytesIO(self._raw_detail))
                self.detail = H6199StatusReply.SceneState(_io__raw_detail, self, self._root)
                self.detail._read()
            elif _on == H6199StatusReply.ModeSel.video:
                pass
                self._raw_detail = self._io.read_bytes(16)
                _io__raw_detail = KaitaiStream(BytesIO(self._raw_detail))
                self.detail = H6199StatusReply.VideoState(_io__raw_detail, self, self._root)
                self.detail._read()
            else:
                pass
                self.detail = self._io.read_bytes(16)
            self._dirty = False


        def _fetch_instances(self):
            pass
            _on = self.mode
            if _on == H6199StatusReply.ModeSel.music:
                pass
                self.detail._fetch_instances()
            elif _on == H6199StatusReply.ModeSel.scene:
                pass
                self.detail._fetch_instances()
            elif _on == H6199StatusReply.ModeSel.video:
                pass
                self.detail._fetch_instances()
            else:
                pass


        def _write__seq(self, io=None):
            super(H6199StatusReply.ColourModeBody, self)._write__seq(io)
            self._io.write_u1(int(self.mode))
            _on = self.mode
            if _on == H6199StatusReply.ModeSel.music:
                pass
                _io__raw_detail = KaitaiStream(BytesIO(bytearray(16)))
                self._io.add_child_stream(_io__raw_detail)
                _pos2 = self._io.pos()
                self._io.seek(self._io.pos() + (16))
                def handler(parent, _io__raw_detail=_io__raw_detail):
                    self._raw_detail = _io__raw_detail.to_byte_array()
                    if len(self._raw_detail) != 16:
                        raise kaitaistruct.ConsistencyError(u"raw(detail)", 16, len(self._raw_detail))
                    parent.write_bytes(self._raw_detail)
                _io__raw_detail.write_back_handler = KaitaiStream.WriteBackHandler(_pos2, handler)
                self.detail._write__seq(_io__raw_detail)
            elif _on == H6199StatusReply.ModeSel.scene:
                pass
                _io__raw_detail = KaitaiStream(BytesIO(bytearray(16)))
                self._io.add_child_stream(_io__raw_detail)
                _pos2 = self._io.pos()
                self._io.seek(self._io.pos() + (16))
                def handler(parent, _io__raw_detail=_io__raw_detail):
                    self._raw_detail = _io__raw_detail.to_byte_array()
                    if len(self._raw_detail) != 16:
                        raise kaitaistruct.ConsistencyError(u"raw(detail)", 16, len(self._raw_detail))
                    parent.write_bytes(self._raw_detail)
                _io__raw_detail.write_back_handler = KaitaiStream.WriteBackHandler(_pos2, handler)
                self.detail._write__seq(_io__raw_detail)
            elif _on == H6199StatusReply.ModeSel.video:
                pass
                _io__raw_detail = KaitaiStream(BytesIO(bytearray(16)))
                self._io.add_child_stream(_io__raw_detail)
                _pos2 = self._io.pos()
                self._io.seek(self._io.pos() + (16))
                def handler(parent, _io__raw_detail=_io__raw_detail):
                    self._raw_detail = _io__raw_detail.to_byte_array()
                    if len(self._raw_detail) != 16:
                        raise kaitaistruct.ConsistencyError(u"raw(detail)", 16, len(self._raw_detail))
                    parent.write_bytes(self._raw_detail)
                _io__raw_detail.write_back_handler = KaitaiStream.WriteBackHandler(_pos2, handler)
                self.detail._write__seq(_io__raw_detail)
            else:
                pass
                self._io.write_bytes(self.detail)


        def _check(self):
            _on = self.mode
            if _on == H6199StatusReply.ModeSel.music:
                pass
                if self.detail._root != self._root:
                    raise kaitaistruct.ConsistencyError(u"detail", self._root, self.detail._root)
                if self.detail._parent != self:
                    raise kaitaistruct.ConsistencyError(u"detail", self, self.detail._parent)
            elif _on == H6199StatusReply.ModeSel.scene:
                pass
                if self.detail._root != self._root:
                    raise kaitaistruct.ConsistencyError(u"detail", self._root, self.detail._root)
                if self.detail._parent != self:
                    raise kaitaistruct.ConsistencyError(u"detail", self, self.detail._parent)
            elif _on == H6199StatusReply.ModeSel.video:
                pass
                if self.detail._root != self._root:
                    raise kaitaistruct.ConsistencyError(u"detail", self._root, self.detail._root)
                if self.detail._parent != self:
                    raise kaitaistruct.ConsistencyError(u"detail", self, self.detail._parent)
            else:
                pass
                if len(self.detail) != 16:
                    raise kaitaistruct.ConsistencyError(u"detail", 16, len(self.detail))
            self._dirty = False


    class DisplaySettingBody(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(H6199StatusReply.DisplaySettingBody, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.setting = KaitaiStream.resolve_enum(H6199StatusReply.DisplaySetting, self._io.read_u1())
            self.len = self._io.read_u1()
            _on = self.setting
            if _on == H6199StatusReply.DisplaySetting.blank_screen:
                pass
                self._raw_payload = self._io.read_bytes(self.len)
                _io__raw_payload = KaitaiStream(BytesIO(self._raw_payload))
                self.payload = H6199StatusReply.BlankScreenState(_io__raw_payload, self, self._root)
                self.payload._read()
            elif _on == H6199StatusReply.DisplaySetting.white_balance:
                pass
                self._raw_payload = self._io.read_bytes(self.len)
                _io__raw_payload = KaitaiStream(BytesIO(self._raw_payload))
                self.payload = H6199StatusReply.WhiteBalanceState(_io__raw_payload, self, self._root)
                self.payload._read()
            else:
                pass
                self.payload = self._io.read_bytes(self.len)
            self.padding = []
            i = 0
            while not self._io.is_eof():
                self.padding.append(self._io.read_u1())
                if not self.padding[i] == 0:
                    raise kaitaistruct.ValidationNotEqualError(0, self.padding[i], self._io, u"/types/display_setting_body/seq/3")
                i += 1

            self._dirty = False


        def _fetch_instances(self):
            pass
            _on = self.setting
            if _on == H6199StatusReply.DisplaySetting.blank_screen:
                pass
                self.payload._fetch_instances()
            elif _on == H6199StatusReply.DisplaySetting.white_balance:
                pass
                self.payload._fetch_instances()
            else:
                pass
            for i in range(len(self.padding)):
                pass



        def _write__seq(self, io=None):
            super(H6199StatusReply.DisplaySettingBody, self)._write__seq(io)
            self._io.write_u1(int(self.setting))
            self._io.write_u1(self.len)
            _on = self.setting
            if _on == H6199StatusReply.DisplaySetting.blank_screen:
                pass
                _io__raw_payload = KaitaiStream(BytesIO(bytearray(self.len)))
                self._io.add_child_stream(_io__raw_payload)
                _pos2 = self._io.pos()
                self._io.seek(self._io.pos() + (self.len))
                def handler(parent, _io__raw_payload=_io__raw_payload):
                    self._raw_payload = _io__raw_payload.to_byte_array()
                    if len(self._raw_payload) != self.len:
                        raise kaitaistruct.ConsistencyError(u"raw(payload)", self.len, len(self._raw_payload))
                    parent.write_bytes(self._raw_payload)
                _io__raw_payload.write_back_handler = KaitaiStream.WriteBackHandler(_pos2, handler)
                self.payload._write__seq(_io__raw_payload)
            elif _on == H6199StatusReply.DisplaySetting.white_balance:
                pass
                _io__raw_payload = KaitaiStream(BytesIO(bytearray(self.len)))
                self._io.add_child_stream(_io__raw_payload)
                _pos2 = self._io.pos()
                self._io.seek(self._io.pos() + (self.len))
                def handler(parent, _io__raw_payload=_io__raw_payload):
                    self._raw_payload = _io__raw_payload.to_byte_array()
                    if len(self._raw_payload) != self.len:
                        raise kaitaistruct.ConsistencyError(u"raw(payload)", self.len, len(self._raw_payload))
                    parent.write_bytes(self._raw_payload)
                _io__raw_payload.write_back_handler = KaitaiStream.WriteBackHandler(_pos2, handler)
                self.payload._write__seq(_io__raw_payload)
            else:
                pass
                self._io.write_bytes(self.payload)
            for i in range(len(self.padding)):
                pass
                if self._io.is_eof():
                    raise kaitaistruct.ConsistencyError(u"padding", 0, self._io.size() - self._io.pos())
                self._io.write_u1(self.padding[i])

            if not self._io.is_eof():
                raise kaitaistruct.ConsistencyError(u"padding", 0, self._io.size() - self._io.pos())


        def _check(self):
            _on = self.setting
            if _on == H6199StatusReply.DisplaySetting.blank_screen:
                pass
                if self.payload._root != self._root:
                    raise kaitaistruct.ConsistencyError(u"payload", self._root, self.payload._root)
                if self.payload._parent != self:
                    raise kaitaistruct.ConsistencyError(u"payload", self, self.payload._parent)
            elif _on == H6199StatusReply.DisplaySetting.white_balance:
                pass
                if self.payload._root != self._root:
                    raise kaitaistruct.ConsistencyError(u"payload", self._root, self.payload._root)
                if self.payload._parent != self:
                    raise kaitaistruct.ConsistencyError(u"payload", self, self.payload._parent)
            else:
                pass
                if len(self.payload) != self.len:
                    raise kaitaistruct.ConsistencyError(u"payload", self.len, len(self.payload))
            for i in range(len(self.padding)):
                pass
                if not self.padding[i] == 0:
                    raise kaitaistruct.ValidationNotEqualError(0, self.padding[i], None, u"/types/display_setting_body/seq/3")

            self._dirty = False


    class HardwareVersionBody(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(H6199StatusReply.HardwareVersionBody, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.prefix = self._io.read_bytes(1)
            if not self.prefix == b"\x03":
                raise kaitaistruct.ValidationNotEqualError(b"\x03", self.prefix, self._io, u"/types/hardware_version_body/seq/0")
            self.text = (self._io.read_bytes_term(0, False, True, True)).decode(u"ASCII")
            self._dirty = False


        def _fetch_instances(self):
            pass


        def _write__seq(self, io=None):
            super(H6199StatusReply.HardwareVersionBody, self)._write__seq(io)
            self._io.write_bytes(self.prefix)
            self._io.write_bytes((self.text).encode(u"ASCII"))
            self._io.write_u1(0)


        def _check(self):
            if len(self.prefix) != 1:
                raise kaitaistruct.ConsistencyError(u"prefix", 1, len(self.prefix))
            if not self.prefix == b"\x03":
                raise kaitaistruct.ValidationNotEqualError(b"\x03", self.prefix, None, u"/types/hardware_version_body/seq/0")
            if KaitaiStream.byte_array_index_of((self.text).encode(u"ASCII"), 0) != -1:
                raise kaitaistruct.ConsistencyError(u"text", -1, KaitaiStream.byte_array_index_of((self.text).encode(u"ASCII"), 0))
            self._dirty = False


    class MusicState(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(H6199StatusReply.MusicState, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.mode = self._io.read_u1()
            self.sensitivity = self._io.read_u1()
            self.is_calm = self._io.read_u1()
            self.has_fixed_colour = self._io.read_u1()
            self.fixed_colour = govee_shared.GoveeShared.Rgb(self._io)
            self.fixed_colour._read()
            self._dirty = False


        def _fetch_instances(self):
            pass
            self.fixed_colour._fetch_instances()


        def _write__seq(self, io=None):
            super(H6199StatusReply.MusicState, self)._write__seq(io)
            self._io.write_u1(self.mode)
            self._io.write_u1(self.sensitivity)
            self._io.write_u1(self.is_calm)
            self._io.write_u1(self.has_fixed_colour)
            self.fixed_colour._write__seq(self._io)


        def _check(self):
            self._dirty = False


    class PowerBody(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(H6199StatusReply.PowerBody, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.is_on = self._io.read_u1()
            self._dirty = False


        def _fetch_instances(self):
            pass


        def _write__seq(self, io=None):
            super(H6199StatusReply.PowerBody, self)._write__seq(io)
            self._io.write_u1(self.is_on)


        def _check(self):
            self._dirty = False


    class RelativeBrightnessBody(ReadWriteKaitaiStruct):
        """The shared app parser always reads six value slots. H6199 reports edge_count 4; the final
        strip-left and strip-right slots belong to six-segment hardware and are retained without
        constraining reads so an unexpected firmware value remains observable.
        """
        def __init__(self, _io=None, _parent=None, _root=None):
            super(H6199StatusReply.RelativeBrightnessBody, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.selector = self._io.read_bytes(1)
            if not self.selector == b"\x01":
                raise kaitaistruct.ValidationNotEqualError(b"\x01", self.selector, self._io, u"/types/relative_brightness_body/seq/0")
            self.edge_count = self._io.read_u1()
            if not self.edge_count == 4:
                raise kaitaistruct.ValidationNotEqualError(4, self.edge_count, self._io, u"/types/relative_brightness_body/seq/1")
            self.left_percent = self._io.read_u1()
            self.top_percent = self._io.read_u1()
            self.right_percent = self._io.read_u1()
            self.bottom_percent = self._io.read_u1()
            self.strip_left_percent = self._io.read_u1()
            self.strip_right_percent = self._io.read_u1()
            self._dirty = False


        def _fetch_instances(self):
            pass


        def _write__seq(self, io=None):
            super(H6199StatusReply.RelativeBrightnessBody, self)._write__seq(io)
            self._io.write_bytes(self.selector)
            self._io.write_u1(self.edge_count)
            self._io.write_u1(self.left_percent)
            self._io.write_u1(self.top_percent)
            self._io.write_u1(self.right_percent)
            self._io.write_u1(self.bottom_percent)
            self._io.write_u1(self.strip_left_percent)
            self._io.write_u1(self.strip_right_percent)


        def _check(self):
            if len(self.selector) != 1:
                raise kaitaistruct.ConsistencyError(u"selector", 1, len(self.selector))
            if not self.selector == b"\x01":
                raise kaitaistruct.ValidationNotEqualError(b"\x01", self.selector, None, u"/types/relative_brightness_body/seq/0")
            if not self.edge_count == 4:
                raise kaitaistruct.ValidationNotEqualError(4, self.edge_count, None, u"/types/relative_brightness_body/seq/1")
            self._dirty = False


    class SceneState(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(H6199StatusReply.SceneState, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.scene_id = self._io.read_u2le()
            self._dirty = False


        def _fetch_instances(self):
            pass


        def _write__seq(self, io=None):
            super(H6199StatusReply.SceneState, self)._write__seq(io)
            self._io.write_u2le(self.scene_id)


        def _check(self):
            self._dirty = False


    class SegmentGroupBody(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(H6199StatusReply.SegmentGroupBody, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.group = self._io.read_u1()
            self.segments = []
            for i in range((3 if self.group == 4 else 4)):
                _t_segments = H6199StatusReply.SegmentRecord(self._io, self, self._root)
                try:
                    _t_segments._read()
                finally:
                    self.segments.append(_t_segments)

            if self.group == 4:
                pass
                self._unnamed2 = self._io.read_bytes(4)

            self._dirty = False


        def _fetch_instances(self):
            pass
            for i in range(len(self.segments)):
                pass
                self.segments[i]._fetch_instances()

            if self.group == 4:
                pass



        def _write__seq(self, io=None):
            super(H6199StatusReply.SegmentGroupBody, self)._write__seq(io)
            self._io.write_u1(self.group)
            for i in range(len(self.segments)):
                pass
                self.segments[i]._write__seq(self._io)

            if self.group == 4:
                pass
                self._io.write_bytes(self._unnamed2)



        def _check(self):
            if len(self.segments) != (3 if self.group == 4 else 4):
                raise kaitaistruct.ConsistencyError(u"segments", (3 if self.group == 4 else 4), len(self.segments))
            for i in range(len(self.segments)):
                pass
                if self.segments[i]._root != self._root:
                    raise kaitaistruct.ConsistencyError(u"segments", self._root, self.segments[i]._root)
                if self.segments[i]._parent != self:
                    raise kaitaistruct.ConsistencyError(u"segments", self, self.segments[i]._parent)

            if self.group == 4:
                pass
                if len(self._unnamed2) != 4:
                    raise kaitaistruct.ConsistencyError(u"_unnamed2", 4, len(self._unnamed2))

            self._dirty = False


    class SegmentRecord(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(H6199StatusReply.SegmentRecord, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.brightness_percent = self._io.read_u1()
            self.colour = govee_shared.GoveeShared.Rgb(self._io)
            self.colour._read()
            self._dirty = False


        def _fetch_instances(self):
            pass
            self.colour._fetch_instances()


        def _write__seq(self, io=None):
            super(H6199StatusReply.SegmentRecord, self)._write__seq(io)
            self._io.write_u1(self.brightness_percent)
            self.colour._write__seq(self._io)


        def _check(self):
            self._dirty = False


    class VersionBody(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(H6199StatusReply.VersionBody, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.text = (self._io.read_bytes_term(0, False, True, True)).decode(u"ASCII")
            self._dirty = False


        def _fetch_instances(self):
            pass


        def _write__seq(self, io=None):
            super(H6199StatusReply.VersionBody, self)._write__seq(io)
            self._io.write_bytes((self.text).encode(u"ASCII"))
            self._io.write_u1(0)


        def _check(self):
            if KaitaiStream.byte_array_index_of((self.text).encode(u"ASCII"), 0) != -1:
                raise kaitaistruct.ConsistencyError(u"text", -1, KaitaiStream.byte_array_index_of((self.text).encode(u"ASCII"), 0))
            self._dirty = False


    class VideoState(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(H6199StatusReply.VideoState, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.region = KaitaiStream.resolve_enum(H6199StatusReply.VideoRegion, self._io.read_u1())
            self.source = KaitaiStream.resolve_enum(H6199StatusReply.VideoSource, self._io.read_u1())
            self.saturation = self._io.read_u1()
            self.sound_effects = self._io.read_u1()
            self.softness = self._io.read_u1()
            self._dirty = False


        def _fetch_instances(self):
            pass


        def _write__seq(self, io=None):
            super(H6199StatusReply.VideoState, self)._write__seq(io)
            self._io.write_u1(int(self.region))
            self._io.write_u1(int(self.source))
            self._io.write_u1(self.saturation)
            self._io.write_u1(self.sound_effects)
            self._io.write_u1(self.softness)


        def _check(self):
            self._dirty = False


    class WhiteBalanceState(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(H6199StatusReply.WhiteBalanceState, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.reset_flag = self._io.read_u1()
            self.reset_red = self._io.read_u1()
            self.reset_blue = self._io.read_u1()
            self.current_flag = self._io.read_u1()
            self.current_red = self._io.read_u1()
            self.current_blue = self._io.read_u1()
            self._dirty = False


        def _fetch_instances(self):
            pass


        def _write__seq(self, io=None):
            super(H6199StatusReply.WhiteBalanceState, self)._write__seq(io)
            self._io.write_u1(self.reset_flag)
            self._io.write_u1(self.reset_red)
            self._io.write_u1(self.reset_blue)
            self._io.write_u1(self.current_flag)
            self._io.write_u1(self.current_red)
            self._io.write_u1(self.current_blue)


        def _check(self):
            self._dirty = False



