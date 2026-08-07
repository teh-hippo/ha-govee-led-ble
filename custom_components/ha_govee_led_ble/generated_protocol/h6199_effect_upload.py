# This is a generated file! Please edit source .ksy file and use kaitai-struct-compiler to rebuild
# type: ignore

import kaitaistruct
from kaitaistruct import ReadWriteKaitaiStruct, KaitaiStream, BytesIO
from custom_components.ha_govee_led_ble.generated_protocol import govee_shared
from enum import IntEnum


if getattr(kaitaistruct, 'API_VERSION', (0, 9)) < (0, 11):
    raise Exception("Incompatible Kaitai Struct Python API: 0.11 or later is required, but you have %s" % (kaitaistruct.__version__))

class H6199EffectUpload(ReadWriteKaitaiStruct):

    class BodyKind(IntEnum):
        builtin_parameters = 1
        scene = 2
        diy = 4

    class EffectFamily(IntEnum):
        fade = 0
        jumping = 1
        twinkle = 2
        marquee = 3
        music = 4
        chasing = 8
        rainbow = 9
        crossing = 10
    def __init__(self, _io=None, _parent=None, _root=None):
        super(H6199EffectUpload, self).__init__(_io)
        self._parent = _parent
        self._root = _root or self

    def _read(self):
        self.header = self._io.read_bytes(1)
        if not self.header == b"\x01":
            raise kaitaistruct.ValidationNotEqualError(b"\x01", self.header, self._io, u"/seq/0")
        self.chunk_count = self._io.read_u1()
        self.kind = KaitaiStream.resolve_enum(H6199EffectUpload.BodyKind, self._io.read_u1())
        _on = self.kind
        if _on == H6199EffectUpload.BodyKind.builtin_parameters:
            pass
            self.content = govee_shared.GoveeShared.SceneType1Content(self._io)
            self.content._read()
        elif _on == H6199EffectUpload.BodyKind.diy:
            pass
            self.content = H6199EffectUpload.DiyContent(self._io, self, self._root)
            self.content._read()
        elif _on == H6199EffectUpload.BodyKind.scene:
            pass
            self.content = H6199EffectUpload.SceneContent(self._io, self, self._root)
            self.content._read()
        self._dirty = False


    def _fetch_instances(self):
        pass
        _on = self.kind
        if _on == H6199EffectUpload.BodyKind.builtin_parameters:
            pass
            self.content._fetch_instances()
        elif _on == H6199EffectUpload.BodyKind.diy:
            pass
            self.content._fetch_instances()
        elif _on == H6199EffectUpload.BodyKind.scene:
            pass
            self.content._fetch_instances()


    def _write__seq(self, io=None):
        super(H6199EffectUpload, self)._write__seq(io)
        self._io.write_bytes(self.header)
        self._io.write_u1(self.chunk_count)
        self._io.write_u1(int(self.kind))
        _on = self.kind
        if _on == H6199EffectUpload.BodyKind.builtin_parameters:
            pass
            self.content._write__seq(self._io)
        elif _on == H6199EffectUpload.BodyKind.diy:
            pass
            self.content._write__seq(self._io)
        elif _on == H6199EffectUpload.BodyKind.scene:
            pass
            self.content._write__seq(self._io)


    def _check(self):
        if len(self.header) != 1:
            raise kaitaistruct.ConsistencyError(u"header", 1, len(self.header))
        if not self.header == b"\x01":
            raise kaitaistruct.ValidationNotEqualError(b"\x01", self.header, None, u"/seq/0")
        _on = self.kind
        if _on == H6199EffectUpload.BodyKind.builtin_parameters:
            pass
        elif _on == H6199EffectUpload.BodyKind.diy:
            pass
            if self.content._root != self._root:
                raise kaitaistruct.ConsistencyError(u"content", self._root, self.content._root)
            if self.content._parent != self:
                raise kaitaistruct.ConsistencyError(u"content", self, self.content._parent)
        elif _on == H6199EffectUpload.BodyKind.scene:
            pass
            if self.content._root != self._root:
                raise kaitaistruct.ConsistencyError(u"content", self._root, self.content._root)
            if self.content._parent != self:
                raise kaitaistruct.ConsistencyError(u"content", self, self.content._parent)
        self._dirty = False

    class Block(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(H6199EffectUpload.Block, self).__init__(_io)
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
            super(H6199EffectUpload.Block, self)._write__seq(io)
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

        @property
        def applied_area(self):
            if hasattr(self, '_m_applied_area'):
                return self._m_applied_area

            self._m_applied_area = self.body.applied_area
            return getattr(self, '_m_applied_area', None)

        def _invalidate_applied_area(self):
            del self._m_applied_area
        @property
        def applied_area_start_tenths(self):
            if hasattr(self, '_m_applied_area_start_tenths'):
                return self._m_applied_area_start_tenths

            self._m_applied_area_start_tenths = self.body.applied_area_start_tenths
            return getattr(self, '_m_applied_area_start_tenths', None)

        def _invalidate_applied_area_start_tenths(self):
            del self._m_applied_area_start_tenths
        @property
        def applied_area_width_tenths(self):
            if hasattr(self, '_m_applied_area_width_tenths'):
                return self._m_applied_area_width_tenths

            self._m_applied_area_width_tenths = self.body.applied_area_width_tenths
            return getattr(self, '_m_applied_area_width_tenths', None)

        def _invalidate_applied_area_width_tenths(self):
            del self._m_applied_area_width_tenths
        @property
        def brightness_blocks(self):
            if hasattr(self, '_m_brightness_blocks'):
                return self._m_brightness_blocks

            self._m_brightness_blocks = self.body.brightness_blocks
            return getattr(self, '_m_brightness_blocks', None)

        def _invalidate_brightness_blocks(self):
            del self._m_brightness_blocks
        @property
        def brightness_change_speed(self):
            if hasattr(self, '_m_brightness_change_speed'):
                return self._m_brightness_change_speed

            self._m_brightness_change_speed = self.body.brightness_blocks[0].brightness_speed
            return getattr(self, '_m_brightness_change_speed', None)

        def _invalidate_brightness_change_speed(self):
            del self._m_brightness_change_speed
        @property
        def brightness_is_gradient(self):
            if hasattr(self, '_m_brightness_is_gradient'):
                return self._m_brightness_is_gradient

            self._m_brightness_is_gradient = self.body.brightness_is_gradient
            return getattr(self, '_m_brightness_is_gradient', None)

        def _invalidate_brightness_is_gradient(self):
            del self._m_brightness_is_gradient
        @property
        def brightness_scope_low(self):
            if hasattr(self, '_m_brightness_scope_low'):
                return self._m_brightness_scope_low

            self._m_brightness_scope_low = self.body.brightness_blocks[0].brightness_scope_end
            return getattr(self, '_m_brightness_scope_low', None)

        def _invalidate_brightness_scope_low(self):
            del self._m_brightness_scope_low
        @property
        def colour_change_speed(self):
            if hasattr(self, '_m_colour_change_speed'):
                return self._m_colour_change_speed

            self._m_colour_change_speed = self.body.colour_speed
            return getattr(self, '_m_colour_change_speed', None)

        def _invalidate_colour_change_speed(self):
            del self._m_colour_change_speed
        @property
        def direction_is_backward(self):
            if hasattr(self, '_m_direction_is_backward'):
                return self._m_direction_is_backward

            self._m_direction_is_backward = self.body.direction_is_backward
            return getattr(self, '_m_direction_is_backward', None)

        def _invalidate_direction_is_backward(self):
            del self._m_direction_is_backward
        @property
        def distribution_direction(self):
            if hasattr(self, '_m_distribution_direction'):
                return self._m_distribution_direction

            self._m_distribution_direction = self.body.direction_distribution
            return getattr(self, '_m_distribution_direction', None)

        def _invalidate_distribution_direction(self):
            del self._m_distribution_direction
        @property
        def distribution_method(self):
            if hasattr(self, '_m_distribution_method'):
                return self._m_distribution_method

            self._m_distribution_method = self.body.direction_distribution & 127
            return getattr(self, '_m_distribution_method', None)

        def _invalidate_distribution_method(self):
            del self._m_distribution_method
        @property
        def excess(self):
            if hasattr(self, '_m_excess'):
                return self._m_excess

            self._m_excess = self.body.excess
            return getattr(self, '_m_excess', None)

        def _invalidate_excess(self):
            del self._m_excess
        @property
        def layer_flags(self):
            if hasattr(self, '_m_layer_flags'):
                return self._m_layer_flags

            self._m_layer_flags = self.body.layer_flags
            return getattr(self, '_m_layer_flags', None)

        def _invalidate_layer_flags(self):
            del self._m_layer_flags
        @property
        def layer_priority(self):
            if hasattr(self, '_m_layer_priority'):
                return self._m_layer_priority

            self._m_layer_priority = self.body.priority
            return getattr(self, '_m_layer_priority', None)

        def _invalidate_layer_priority(self):
            del self._m_layer_priority
        @property
        def num_brightness_blocks(self):
            if hasattr(self, '_m_num_brightness_blocks'):
                return self._m_num_brightness_blocks

            self._m_num_brightness_blocks = self.body.num_brightness_blocks
            return getattr(self, '_m_num_brightness_blocks', None)

        def _invalidate_num_brightness_blocks(self):
            del self._m_num_brightness_blocks
        @property
        def num_palette(self):
            if hasattr(self, '_m_num_palette'):
                return self._m_num_palette

            self._m_num_palette = self.body.num_palette
            return getattr(self, '_m_num_palette', None)

        def _invalidate_num_palette(self):
            del self._m_num_palette
        @property
        def overall_movement(self):
            if hasattr(self, '_m_overall_movement'):
                return self._m_overall_movement

            self._m_overall_movement = self.body.overall_movement.packed
            return getattr(self, '_m_overall_movement', None)

        def _invalidate_overall_movement(self):
            del self._m_overall_movement
        @property
        def overall_movement_interval(self):
            if hasattr(self, '_m_overall_movement_interval'):
                return self._m_overall_movement_interval

            self._m_overall_movement_interval = self.body.overall_movement.interval
            return getattr(self, '_m_overall_movement_interval', None)

        def _invalidate_overall_movement_interval(self):
            del self._m_overall_movement_interval
        @property
        def overall_movement_speed(self):
            if hasattr(self, '_m_overall_movement_speed'):
                return self._m_overall_movement_speed

            self._m_overall_movement_speed = self.body.overall_movement.speed
            return getattr(self, '_m_overall_movement_speed', None)

        def _invalidate_overall_movement_speed(self):
            del self._m_overall_movement_speed
        @property
        def palette(self):
            if hasattr(self, '_m_palette'):
                return self._m_palette

            self._m_palette = self.body.palette
            return getattr(self, '_m_palette', None)

        def _invalidate_palette(self):
            del self._m_palette
        @property
        def retention_time(self):
            if hasattr(self, '_m_retention_time'):
                return self._m_retention_time

            self._m_retention_time = self.body.colour_retention
            return getattr(self, '_m_retention_time', None)

        def _invalidate_retention_time(self):
            del self._m_retention_time
        @property
        def retention_time_brightest(self):
            if hasattr(self, '_m_retention_time_brightest'):
                return self._m_retention_time_brightest

            self._m_retention_time_brightest = self.body.brightness_blocks[0].brightest_retention
            return getattr(self, '_m_retention_time_brightest', None)

        def _invalidate_retention_time_brightest(self):
            del self._m_retention_time_brightest
        @property
        def retention_time_darkest(self):
            if hasattr(self, '_m_retention_time_darkest'):
                return self._m_retention_time_darkest

            self._m_retention_time_darkest = self.body.brightness_blocks[0].darkest_retention
            return getattr(self, '_m_retention_time_darkest', None)

        def _invalidate_retention_time_darkest(self):
            del self._m_retention_time_darkest
        @property
        def select_param_1(self):
            if hasattr(self, '_m_select_param_1'):
                return self._m_select_param_1

            self._m_select_param_1 = self.body.select_param_1
            return getattr(self, '_m_select_param_1', None)

        def _invalidate_select_param_1(self):
            del self._m_select_param_1
        @property
        def select_param_2(self):
            if hasattr(self, '_m_select_param_2'):
                return self._m_select_param_2

            self._m_select_param_2 = self.body.select_param_2
            return getattr(self, '_m_select_param_2', None)

        def _invalidate_select_param_2(self):
            del self._m_select_param_2
        @property
        def select_type(self):
            if hasattr(self, '_m_select_type'):
                return self._m_select_type

            self._m_select_type = self.body.select_type
            return getattr(self, '_m_select_type', None)

        def _invalidate_select_type(self):
            del self._m_select_type
        @property
        def selected_direction(self):
            if hasattr(self, '_m_selected_direction'):
                return self._m_selected_direction

            self._m_selected_direction = self.body.selected_area_movement.direction
            return getattr(self, '_m_selected_direction', None)

        def _invalidate_selected_direction(self):
            del self._m_selected_direction
        @property
        def selected_enter_exit_enabled(self):
            if hasattr(self, '_m_selected_enter_exit_enabled'):
                return self._m_selected_enter_exit_enabled

            self._m_selected_enter_exit_enabled = self.body.selected_area_movement.enter_exit_effect
            return getattr(self, '_m_selected_enter_exit_enabled', None)

        def _invalidate_selected_enter_exit_enabled(self):
            del self._m_selected_enter_exit_enabled
        @property
        def selected_movement(self):
            if hasattr(self, '_m_selected_movement'):
                return self._m_selected_movement

            self._m_selected_movement = self.body.selected_area_movement.packed
            return getattr(self, '_m_selected_movement', None)

        def _invalidate_selected_movement(self):
            del self._m_selected_movement
        @property
        def selected_movement_enabled(self):
            if hasattr(self, '_m_selected_movement_enabled'):
                return self._m_selected_movement_enabled

            self._m_selected_movement_enabled = self.body.selected_area_movement.enabled
            return getattr(self, '_m_selected_movement_enabled', None)

        def _invalidate_selected_movement_enabled(self):
            del self._m_selected_movement_enabled
        @property
        def selected_movement_interval(self):
            if hasattr(self, '_m_selected_movement_interval'):
                return self._m_selected_movement_interval

            self._m_selected_movement_interval = self.body.selected_area_movement.interval
            return getattr(self, '_m_selected_movement_interval', None)

        def _invalidate_selected_movement_interval(self):
            del self._m_selected_movement_interval
        @property
        def selected_movement_speed(self):
            if hasattr(self, '_m_selected_movement_speed'):
                return self._m_selected_movement_speed

            self._m_selected_movement_speed = self.body.selected_area_movement.speed
            return getattr(self, '_m_selected_movement_speed', None)

        def _invalidate_selected_movement_speed(self):
            del self._m_selected_movement_speed

    class DiyContent(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(H6199EffectUpload.DiyContent, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.family = KaitaiStream.resolve_enum(H6199EffectUpload.EffectFamily, self._io.read_u1())
            self.variant = self._io.read_u1()
            self.speed = self._io.read_u1()
            self.palette_len = self._io.read_u1()
            _ = self.palette_len
            if not _ % 3 == 0:
                raise kaitaistruct.ValidationExprError(self.palette_len, self._io, u"/types/diy_content/seq/3")
            self.palette = []
            for i in range(self.palette_len // 3):
                _t_palette = govee_shared.GoveeShared.Rgb(self._io)
                try:
                    _t_palette._read()
                finally:
                    self.palette.append(_t_palette)

            self.padding = []
            i = 0
            while not self._io.is_eof():
                self.padding.append(self._io.read_u1())
                if not self.padding[i] == 0:
                    raise kaitaistruct.ValidationNotEqualError(0, self.padding[i], self._io, u"/types/diy_content/seq/5")
                i += 1

            self._dirty = False


        def _fetch_instances(self):
            pass
            for i in range(len(self.palette)):
                pass
                self.palette[i]._fetch_instances()

            for i in range(len(self.padding)):
                pass



        def _write__seq(self, io=None):
            super(H6199EffectUpload.DiyContent, self)._write__seq(io)
            self._io.write_u1(int(self.family))
            self._io.write_u1(self.variant)
            self._io.write_u1(self.speed)
            self._io.write_u1(self.palette_len)
            for i in range(len(self.palette)):
                pass
                self.palette[i]._write__seq(self._io)

            for i in range(len(self.padding)):
                pass
                if self._io.is_eof():
                    raise kaitaistruct.ConsistencyError(u"padding", 0, self._io.size() - self._io.pos())
                self._io.write_u1(self.padding[i])

            if not self._io.is_eof():
                raise kaitaistruct.ConsistencyError(u"padding", 0, self._io.size() - self._io.pos())


        def _check(self):
            _ = self.palette_len
            if not _ % 3 == 0:
                raise kaitaistruct.ValidationExprError(self.palette_len, None, u"/types/diy_content/seq/3")
            if len(self.palette) != self.palette_len // 3:
                raise kaitaistruct.ConsistencyError(u"palette", self.palette_len // 3, len(self.palette))
            for i in range(len(self.palette)):
                pass

            for i in range(len(self.padding)):
                pass
                if not self.padding[i] == 0:
                    raise kaitaistruct.ValidationNotEqualError(0, self.padding[i], None, u"/types/diy_content/seq/5")

            self._dirty = False


    class SceneContent(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(H6199EffectUpload.SceneContent, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.num_blocks = self._io.read_u1()
            self.blocks = []
            for i in range(self.num_blocks):
                _t_blocks = H6199EffectUpload.Block(self._io, self, self._root)
                try:
                    _t_blocks._read()
                finally:
                    self.blocks.append(_t_blocks)

            self.padding = []
            i = 0
            while not self._io.is_eof():
                self.padding.append(self._io.read_u1())
                if not self.padding[i] == 0:
                    raise kaitaistruct.ValidationNotEqualError(0, self.padding[i], self._io, u"/types/scene_content/seq/2")
                i += 1

            self._dirty = False


        def _fetch_instances(self):
            pass
            for i in range(len(self.blocks)):
                pass
                self.blocks[i]._fetch_instances()

            for i in range(len(self.padding)):
                pass



        def _write__seq(self, io=None):
            super(H6199EffectUpload.SceneContent, self)._write__seq(io)
            self._io.write_u1(self.num_blocks)
            for i in range(len(self.blocks)):
                pass
                self.blocks[i]._write__seq(self._io)

            for i in range(len(self.padding)):
                pass
                if self._io.is_eof():
                    raise kaitaistruct.ConsistencyError(u"padding", 0, self._io.size() - self._io.pos())
                self._io.write_u1(self.padding[i])

            if not self._io.is_eof():
                raise kaitaistruct.ConsistencyError(u"padding", 0, self._io.size() - self._io.pos())


        def _check(self):
            if len(self.blocks) != self.num_blocks:
                raise kaitaistruct.ConsistencyError(u"blocks", self.num_blocks, len(self.blocks))
            for i in range(len(self.blocks)):
                pass
                if self.blocks[i]._root != self._root:
                    raise kaitaistruct.ConsistencyError(u"blocks", self._root, self.blocks[i]._root)
                if self.blocks[i]._parent != self:
                    raise kaitaistruct.ConsistencyError(u"blocks", self, self.blocks[i]._parent)

            for i in range(len(self.padding)):
                pass
                if not self.padding[i] == 0:
                    raise kaitaistruct.ValidationNotEqualError(0, self.padding[i], None, u"/types/scene_content/seq/2")

            self._dirty = False



