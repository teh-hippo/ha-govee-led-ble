# This is a generated file! Please edit source .ksy file and use kaitai-struct-compiler to rebuild
# type: ignore

import kaitaistruct
from kaitaistruct import ReadWriteKaitaiStruct, KaitaiStream, BytesIO
from custom_components.ha_govee_led_ble.generated_protocol import govee_common
from custom_components.ha_govee_led_ble.generated_protocol import govee_shared
from enum import IntEnum


if getattr(kaitaistruct, 'API_VERSION', (0, 9)) < (0, 11):
    raise Exception("Incompatible Kaitai Struct Python API: 0.11 or later is required, but you have %s" % (kaitaistruct.__version__))

class SceneBody(ReadWriteKaitaiStruct):

    class SceneType(IntEnum):
        scene_v0 = 0
        scene_v1 = 1
        scene_v2 = 2
    def __init__(self, _io=None, _parent=None, _root=None):
        super(SceneBody, self).__init__(_io)
        self._parent = _parent
        self._root = _root or self

    def _read(self):
        self.header = govee_common.GoveeCommon.A3Header(self._io)
        self.header._read()
        self.scene_type = KaitaiStream.resolve_enum(SceneBody.SceneType, self._io.read_u1())
        if not self.scene_type == SceneBody.SceneType.scene_v2:
            raise kaitaistruct.ValidationNotEqualError(SceneBody.SceneType.scene_v2, self.scene_type, self._io, u"/seq/1")
        self.num_records = self._io.read_u1()
        self.records = []
        for i in range(self.num_records):
            _t_records = SceneBody.Record(self._io, self, self._root)
            try:
                _t_records._read()
            finally:
                self.records.append(_t_records)

        self.padding = []
        i = 0
        while not self._io.is_eof():
            self.padding.append(self._io.read_u1())
            if not self.padding[i] == 0:
                raise kaitaistruct.ValidationNotEqualError(0, self.padding[i], self._io, u"/seq/4")
            i += 1

        self._dirty = False


    def _fetch_instances(self):
        pass
        self.header._fetch_instances()
        for i in range(len(self.records)):
            pass
            self.records[i]._fetch_instances()

        for i in range(len(self.padding)):
            pass



    def _write__seq(self, io=None):
        super(SceneBody, self)._write__seq(io)
        self.header._write__seq(self._io)
        self._io.write_u1(int(self.scene_type))
        self._io.write_u1(self.num_records)
        for i in range(len(self.records)):
            pass
            self.records[i]._write__seq(self._io)

        for i in range(len(self.padding)):
            pass
            if self._io.is_eof():
                raise kaitaistruct.ConsistencyError(u"padding", 0, self._io.size() - self._io.pos())
            self._io.write_u1(self.padding[i])

        if not self._io.is_eof():
            raise kaitaistruct.ConsistencyError(u"padding", 0, self._io.size() - self._io.pos())


    def _check(self):
        if not self.scene_type == SceneBody.SceneType.scene_v2:
            raise kaitaistruct.ValidationNotEqualError(SceneBody.SceneType.scene_v2, self.scene_type, None, u"/seq/1")
        if len(self.records) != self.num_records:
            raise kaitaistruct.ConsistencyError(u"records", self.num_records, len(self.records))
        for i in range(len(self.records)):
            pass
            if self.records[i]._root != self._root:
                raise kaitaistruct.ConsistencyError(u"records", self._root, self.records[i]._root)
            if self.records[i]._parent != self:
                raise kaitaistruct.ConsistencyError(u"records", self, self.records[i]._parent)

        for i in range(len(self.padding)):
            pass
            if not self.padding[i] == 0:
                raise kaitaistruct.ValidationNotEqualError(0, self.padding[i], None, u"/seq/4")

        self._dirty = False

    class Record(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(SceneBody.Record, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.len_body = self._io.read_u1()
            self._raw_body = self._io.read_bytes(self.len_body)
            _io__raw_body = KaitaiStream(BytesIO(self._raw_body))
            self.body = govee_shared.GoveeShared.EffectLayer(_io__raw_body)
            self.body._read()
            self._dirty = False


        def _fetch_instances(self):
            pass
            self.body._fetch_instances()


        def _write__seq(self, io=None):
            super(SceneBody.Record, self)._write__seq(io)
            self._io.write_u1(self.len_body)
            _io__raw_body = KaitaiStream(BytesIO(bytearray(self.len_body)))
            self._io.add_child_stream(_io__raw_body)
            _pos2 = self._io.pos()
            self._io.seek(self._io.pos() + (self.len_body))
            def handler(parent, _io__raw_body=_io__raw_body):
                self._raw_body = _io__raw_body.to_byte_array()
                if len(self._raw_body) != self.len_body:
                    raise kaitaistruct.ConsistencyError(u"raw(body)", self.len_body, len(self._raw_body))
                parent.write_bytes(self._raw_body)
            _io__raw_body.write_back_handler = KaitaiStream.WriteBackHandler(_pos2, handler)
            self.body._write__seq(_io__raw_body)


        def _check(self):
            self._dirty = False



