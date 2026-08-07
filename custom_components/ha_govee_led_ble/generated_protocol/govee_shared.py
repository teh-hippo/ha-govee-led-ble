# This is a generated file! Please edit source .ksy file and use kaitai-struct-compiler to rebuild
# type: ignore

import kaitaistruct
from kaitaistruct import ReadWriteKaitaiStruct, KaitaiStream, BytesIO
from enum import IntEnum


if getattr(kaitaistruct, 'API_VERSION', (0, 9)) < (0, 11):
    raise Exception("Incompatible Kaitai Struct Python API: 0.11 or later is required, but you have %s" % (kaitaistruct.__version__))

class GoveeShared(ReadWriteKaitaiStruct):

    class BrightnessOrder(IntEnum):
        brightest_darkest = 0
        brightest_darkest_brightest = 1
        darkest_brightest = 2
        darkest_brightest_darkest = 3

    class SelectType(IntEnum):
        segment = 0
        select_ic_continuously = 1
        select_ic_randomly = 2
        customize_segment = 3
    def __init__(self, _io=None, _parent=None, _root=None):
        super(GoveeShared, self).__init__(_io)
        self._parent = _parent
        self._root = _root or self

    def _read(self):
        pass
        self._dirty = False


    def _fetch_instances(self):
        pass


    def _write__seq(self, io=None):
        super(GoveeShared, self)._write__seq(io)


    def _check(self):
        self._dirty = False

    class BrightnessBlock(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(GoveeShared.BrightnessBlock, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.brightness_scope_start = self._io.read_u1()
            self.brightness_scope_end = self._io.read_u1()
            self.brightness_order = KaitaiStream.resolve_enum(GoveeShared.BrightnessOrder, self._io.read_u1())
            self.brightness_speed = self._io.read_u1()
            self.brightest_retention = self._io.read_u1()
            self.darkest_retention = self._io.read_u1()
            self._dirty = False


        def _fetch_instances(self):
            pass


        def _write__seq(self, io=None):
            super(GoveeShared.BrightnessBlock, self)._write__seq(io)
            self._io.write_u1(self.brightness_scope_start)
            self._io.write_u1(self.brightness_scope_end)
            self._io.write_u1(int(self.brightness_order))
            self._io.write_u1(self.brightness_speed)
            self._io.write_u1(self.brightest_retention)
            self._io.write_u1(self.darkest_retention)


        def _check(self):
            self._dirty = False

        @property
        def change_speed(self):
            if hasattr(self, '_m_change_speed'):
                return self._m_change_speed

            self._m_change_speed = self.brightness_speed
            return getattr(self, '_m_change_speed', None)

        def _invalidate_change_speed(self):
            del self._m_change_speed
        @property
        def order(self):
            if hasattr(self, '_m_order'):
                return self._m_order

            self._m_order = self.brightness_order
            return getattr(self, '_m_order', None)

        def _invalidate_order(self):
            del self._m_order
        @property
        def retention_brightest(self):
            if hasattr(self, '_m_retention_brightest'):
                return self._m_retention_brightest

            self._m_retention_brightest = self.brightest_retention
            return getattr(self, '_m_retention_brightest', None)

        def _invalidate_retention_brightest(self):
            del self._m_retention_brightest
        @property
        def retention_darkest(self):
            if hasattr(self, '_m_retention_darkest'):
                return self._m_retention_darkest

            self._m_retention_darkest = self.darkest_retention
            return getattr(self, '_m_retention_darkest', None)

        def _invalidate_retention_darkest(self):
            del self._m_retention_darkest
        @property
        def scope_high(self):
            if hasattr(self, '_m_scope_high'):
                return self._m_scope_high

            self._m_scope_high = self.brightness_scope_start
            return getattr(self, '_m_scope_high', None)

        def _invalidate_scope_high(self):
            del self._m_scope_high
        @property
        def scope_low(self):
            if hasattr(self, '_m_scope_low'):
                return self._m_scope_low

            self._m_scope_low = self.brightness_scope_end
            return getattr(self, '_m_scope_low', None)

        def _invalidate_scope_low(self):
            del self._m_scope_low

    class EffectLayer(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(GoveeShared.EffectLayer, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.applied_area = self._io.read_u1()
            self.select_type = KaitaiStream.resolve_enum(GoveeShared.SelectType, self._io.read_u1())
            self.select_param_1 = self._io.read_u1()
            self.select_param_2 = self._io.read_u1()
            self.layer_flags = self._io.read_u1()
            self.num_brightness_blocks = self._io.read_u1()
            self.brightness_blocks = []
            for i in range(self.num_brightness_blocks):
                _t_brightness_blocks = GoveeShared.BrightnessBlock(self._io, self, self._root)
                try:
                    _t_brightness_blocks._read()
                finally:
                    self.brightness_blocks.append(_t_brightness_blocks)

            self.direction_distribution = self._io.read_u1()
            self.colour_speed = self._io.read_u1()
            self.colour_retention = self._io.read_u1()
            self.num_palette = self._io.read_u1()
            self.palette = []
            for i in range(self.num_palette):
                _t_palette = GoveeShared.Rgb(self._io, self, self._root)
                try:
                    _t_palette._read()
                finally:
                    self.palette.append(_t_palette)

            self.selected_area_movement = GoveeShared.Movement(self._io, self, self._root)
            self.selected_area_movement._read()
            self.overall_movement = GoveeShared.Movement(self._io, self, self._root)
            self.overall_movement._read()
            self.priority = self._io.read_u1()
            self.excess = self._io.read_bytes_full()
            self._dirty = False


        def _fetch_instances(self):
            pass
            for i in range(len(self.brightness_blocks)):
                pass
                self.brightness_blocks[i]._fetch_instances()

            for i in range(len(self.palette)):
                pass
                self.palette[i]._fetch_instances()

            self.selected_area_movement._fetch_instances()
            self.overall_movement._fetch_instances()


        def _write__seq(self, io=None):
            super(GoveeShared.EffectLayer, self)._write__seq(io)
            self._io.write_u1(self.applied_area)
            self._io.write_u1(int(self.select_type))
            self._io.write_u1(self.select_param_1)
            self._io.write_u1(self.select_param_2)
            self._io.write_u1(self.layer_flags)
            self._io.write_u1(self.num_brightness_blocks)
            for i in range(len(self.brightness_blocks)):
                pass
                self.brightness_blocks[i]._write__seq(self._io)

            self._io.write_u1(self.direction_distribution)
            self._io.write_u1(self.colour_speed)
            self._io.write_u1(self.colour_retention)
            self._io.write_u1(self.num_palette)
            for i in range(len(self.palette)):
                pass
                self.palette[i]._write__seq(self._io)

            self.selected_area_movement._write__seq(self._io)
            self.overall_movement._write__seq(self._io)
            self._io.write_u1(self.priority)
            self._io.write_bytes(self.excess)
            if not self._io.is_eof():
                raise kaitaistruct.ConsistencyError(u"excess", 0, self._io.size() - self._io.pos())


        def _check(self):
            if len(self.brightness_blocks) != self.num_brightness_blocks:
                raise kaitaistruct.ConsistencyError(u"brightness_blocks", self.num_brightness_blocks, len(self.brightness_blocks))
            for i in range(len(self.brightness_blocks)):
                pass
                if self.brightness_blocks[i]._root != self._root:
                    raise kaitaistruct.ConsistencyError(u"brightness_blocks", self._root, self.brightness_blocks[i]._root)
                if self.brightness_blocks[i]._parent != self:
                    raise kaitaistruct.ConsistencyError(u"brightness_blocks", self, self.brightness_blocks[i]._parent)

            if len(self.palette) != self.num_palette:
                raise kaitaistruct.ConsistencyError(u"palette", self.num_palette, len(self.palette))
            for i in range(len(self.palette)):
                pass
                if self.palette[i]._root != self._root:
                    raise kaitaistruct.ConsistencyError(u"palette", self._root, self.palette[i]._root)
                if self.palette[i]._parent != self:
                    raise kaitaistruct.ConsistencyError(u"palette", self, self.palette[i]._parent)

            if self.selected_area_movement._root != self._root:
                raise kaitaistruct.ConsistencyError(u"selected_area_movement", self._root, self.selected_area_movement._root)
            if self.selected_area_movement._parent != self:
                raise kaitaistruct.ConsistencyError(u"selected_area_movement", self, self.selected_area_movement._parent)
            if self.overall_movement._root != self._root:
                raise kaitaistruct.ConsistencyError(u"overall_movement", self._root, self.overall_movement._root)
            if self.overall_movement._parent != self:
                raise kaitaistruct.ConsistencyError(u"overall_movement", self, self.overall_movement._parent)
            self._dirty = False

        @property
        def applied_area_start_tenths(self):
            if hasattr(self, '_m_applied_area_start_tenths'):
                return self._m_applied_area_start_tenths

            self._m_applied_area_start_tenths = self.applied_area & 15
            return getattr(self, '_m_applied_area_start_tenths', None)

        def _invalidate_applied_area_start_tenths(self):
            del self._m_applied_area_start_tenths
        @property
        def applied_area_width_tenths(self):
            if hasattr(self, '_m_applied_area_width_tenths'):
                return self._m_applied_area_width_tenths

            self._m_applied_area_width_tenths = (self.applied_area & 240) >> 4
            return getattr(self, '_m_applied_area_width_tenths', None)

        def _invalidate_applied_area_width_tenths(self):
            del self._m_applied_area_width_tenths
        @property
        def brightness_is_gradient(self):
            if hasattr(self, '_m_brightness_is_gradient'):
                return self._m_brightness_is_gradient

            self._m_brightness_is_gradient = self.layer_flags & 2 != 0
            return getattr(self, '_m_brightness_is_gradient', None)

        def _invalidate_brightness_is_gradient(self):
            del self._m_brightness_is_gradient
        @property
        def direction_is_backward(self):
            if hasattr(self, '_m_direction_is_backward'):
                return self._m_direction_is_backward

            self._m_direction_is_backward = self.direction_distribution & 128 != 0
            return getattr(self, '_m_direction_is_backward', None)

        def _invalidate_direction_is_backward(self):
            del self._m_direction_is_backward

    class Movement(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(GoveeShared.Movement, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.packed = self._io.read_u1()
            self.interval = self._io.read_u1()
            self.speed = self._io.read_u1()
            self._dirty = False


        def _fetch_instances(self):
            pass


        def _write__seq(self, io=None):
            super(GoveeShared.Movement, self)._write__seq(io)
            self._io.write_u1(self.packed)
            self._io.write_u1(self.interval)
            self._io.write_u1(self.speed)


        def _check(self):
            self._dirty = False

        @property
        def direction(self):
            if hasattr(self, '_m_direction'):
                return self._m_direction

            self._m_direction = self.packed & 3
            return getattr(self, '_m_direction', None)

        def _invalidate_direction(self):
            del self._m_direction
        @property
        def enabled(self):
            if hasattr(self, '_m_enabled'):
                return self._m_enabled

            self._m_enabled = self.packed & 16 != 0
            return getattr(self, '_m_enabled', None)

        def _invalidate_enabled(self):
            del self._m_enabled
        @property
        def enter_exit_effect(self):
            if hasattr(self, '_m_enter_exit_effect'):
                return self._m_enter_exit_effect

            self._m_enter_exit_effect = self.packed & 4 != 0
            return getattr(self, '_m_enter_exit_effect', None)

        def _invalidate_enter_exit_effect(self):
            del self._m_enter_exit_effect

    class Rgb(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(GoveeShared.Rgb, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.red = self._io.read_u1()
            self.green = self._io.read_u1()
            self.blue = self._io.read_u1()
            self._dirty = False


        def _fetch_instances(self):
            pass


        def _write__seq(self, io=None):
            super(GoveeShared.Rgb, self)._write__seq(io)
            self._io.write_u1(self.red)
            self._io.write_u1(self.green)
            self._io.write_u1(self.blue)


        def _check(self):
            self._dirty = False

        @property
        def b(self):
            if hasattr(self, '_m_b'):
                return self._m_b

            self._m_b = self.blue
            return getattr(self, '_m_b', None)

        def _invalidate_b(self):
            del self._m_b
        @property
        def g(self):
            if hasattr(self, '_m_g'):
                return self._m_g

            self._m_g = self.green
            return getattr(self, '_m_g', None)

        def _invalidate_g(self):
            del self._m_g
        @property
        def r(self):
            if hasattr(self, '_m_r'):
                return self._m_r

            self._m_r = self.red
            return getattr(self, '_m_r', None)

        def _invalidate_r(self):
            del self._m_r

    class SceneType1Content(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(GoveeShared.SceneType1Content, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.config = self._io.read_u1()
            _ = self.config
            if not  ((self.layout <= 1) and (self.colour_stride == 3)) :
                raise kaitaistruct.ValidationExprError(self.config, self._io, u"/types/scene_type1_content/seq/0")
            self.num_steps = self._io.read_u1()
            self.steps = []
            for i in range(self.num_steps):
                _on = self.layout
                if _on == 0:
                    pass
                    _t_steps = GoveeShared.SceneType1Step(self._io, self, self._root)
                    try:
                        _t_steps._read()
                    finally:
                        self.steps.append(_t_steps)
                elif _on == 1:
                    pass
                    _t_steps = GoveeShared.SceneType1StepInlineColour(self._io, self, self._root)
                    try:
                        _t_steps._read()
                    finally:
                        self.steps.append(_t_steps)

            if self.layout == 0:
                pass
                self.num_palette = self._io.read_u1()

            if self.layout == 0:
                pass
                self.palette = []
                for i in range(self.num_palette):
                    _t_palette = GoveeShared.Rgb(self._io, self, self._root)
                    try:
                        _t_palette._read()
                    finally:
                        self.palette.append(_t_palette)


            self.padding = []
            i = 0
            while not self._io.is_eof():
                self.padding.append(self._io.read_u1())
                if not self.padding[i] == 0:
                    raise kaitaistruct.ValidationNotEqualError(0, self.padding[i], self._io, u"/types/scene_type1_content/seq/5")
                i += 1

            self._dirty = False


        def _fetch_instances(self):
            pass
            for i in range(len(self.steps)):
                pass
                _on = self.layout
                if _on == 0:
                    pass
                    self.steps[i]._fetch_instances()
                elif _on == 1:
                    pass
                    self.steps[i]._fetch_instances()

            if self.layout == 0:
                pass

            if self.layout == 0:
                pass
                for i in range(len(self.palette)):
                    pass
                    self.palette[i]._fetch_instances()


            for i in range(len(self.padding)):
                pass



        def _write__seq(self, io=None):
            super(GoveeShared.SceneType1Content, self)._write__seq(io)
            self._io.write_u1(self.config)
            self._io.write_u1(self.num_steps)
            for i in range(len(self.steps)):
                pass
                _on = self.layout
                if _on == 0:
                    pass
                    self.steps[i]._write__seq(self._io)
                elif _on == 1:
                    pass
                    self.steps[i]._write__seq(self._io)

            if self.layout == 0:
                pass
                self._io.write_u1(self.num_palette)

            if self.layout == 0:
                pass
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
            _ = self.config
            if not  ((self.layout <= 1) and (self.colour_stride == 3)) :
                raise kaitaistruct.ValidationExprError(self.config, None, u"/types/scene_type1_content/seq/0")
            if len(self.steps) != self.num_steps:
                raise kaitaistruct.ConsistencyError(u"steps", self.num_steps, len(self.steps))
            for i in range(len(self.steps)):
                pass
                _on = self.layout
                if _on == 0:
                    pass
                    if self.steps[i]._root != self._root:
                        raise kaitaistruct.ConsistencyError(u"steps", self._root, self.steps[i]._root)
                    if self.steps[i]._parent != self:
                        raise kaitaistruct.ConsistencyError(u"steps", self, self.steps[i]._parent)
                elif _on == 1:
                    pass
                    if self.steps[i]._root != self._root:
                        raise kaitaistruct.ConsistencyError(u"steps", self._root, self.steps[i]._root)
                    if self.steps[i]._parent != self:
                        raise kaitaistruct.ConsistencyError(u"steps", self, self.steps[i]._parent)

            if self.layout == 0:
                pass

            if self.layout == 0:
                pass
                if len(self.palette) != self.num_palette:
                    raise kaitaistruct.ConsistencyError(u"palette", self.num_palette, len(self.palette))
                for i in range(len(self.palette)):
                    pass
                    if self.palette[i]._root != self._root:
                        raise kaitaistruct.ConsistencyError(u"palette", self._root, self.palette[i]._root)
                    if self.palette[i]._parent != self:
                        raise kaitaistruct.ConsistencyError(u"palette", self, self.palette[i]._parent)


            for i in range(len(self.padding)):
                pass
                if not self.padding[i] == 0:
                    raise kaitaistruct.ValidationNotEqualError(0, self.padding[i], None, u"/types/scene_type1_content/seq/5")

            self._dirty = False

        @property
        def brightness_flag(self):
            if hasattr(self, '_m_brightness_flag'):
                return self._m_brightness_flag

            self._m_brightness_flag = self.config & 128 != 0
            return getattr(self, '_m_brightness_flag', None)

        def _invalidate_brightness_flag(self):
            del self._m_brightness_flag
        @property
        def colour_stride(self):
            if hasattr(self, '_m_colour_stride'):
                return self._m_colour_stride

            self._m_colour_stride = self.config & 7
            return getattr(self, '_m_colour_stride', None)

        def _invalidate_colour_stride(self):
            del self._m_colour_stride
        @property
        def layout(self):
            if hasattr(self, '_m_layout'):
                return self._m_layout

            self._m_layout = self.config >> 4 & 7
            return getattr(self, '_m_layout', None)

        def _invalidate_layout(self):
            del self._m_layout

    class SceneType1Step(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(GoveeShared.SceneType1Step, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.colour = GoveeShared.Rgb(self._io, self, self._root)
            self.colour._read()
            self.value = self._io.read_u2le()
            self._dirty = False


        def _fetch_instances(self):
            pass
            self.colour._fetch_instances()


        def _write__seq(self, io=None):
            super(GoveeShared.SceneType1Step, self)._write__seq(io)
            self.colour._write__seq(self._io)
            self._io.write_u2le(self.value)


        def _check(self):
            if self.colour._root != self._root:
                raise kaitaistruct.ConsistencyError(u"colour", self._root, self.colour._root)
            if self.colour._parent != self:
                raise kaitaistruct.ConsistencyError(u"colour", self, self.colour._parent)
            self._dirty = False


    class SceneType1StepInlineColour(ReadWriteKaitaiStruct):
        def __init__(self, _io=None, _parent=None, _root=None):
            super(GoveeShared.SceneType1StepInlineColour, self).__init__(_io)
            self._parent = _parent
            self._root = _root

        def _read(self):
            self.param = GoveeShared.SceneType1Step(self._io, self, self._root)
            self.param._read()
            self.colour = GoveeShared.Rgb(self._io, self, self._root)
            self.colour._read()
            self._dirty = False


        def _fetch_instances(self):
            pass
            self.param._fetch_instances()
            self.colour._fetch_instances()


        def _write__seq(self, io=None):
            super(GoveeShared.SceneType1StepInlineColour, self)._write__seq(io)
            self.param._write__seq(self._io)
            self.colour._write__seq(self._io)


        def _check(self):
            if self.param._root != self._root:
                raise kaitaistruct.ConsistencyError(u"param", self._root, self.param._root)
            if self.param._parent != self:
                raise kaitaistruct.ConsistencyError(u"param", self, self.param._parent)
            if self.colour._root != self._root:
                raise kaitaistruct.ConsistencyError(u"colour", self._root, self.colour._root)
            if self.colour._parent != self:
                raise kaitaistruct.ConsistencyError(u"colour", self, self.colour._parent)
            self._dirty = False



