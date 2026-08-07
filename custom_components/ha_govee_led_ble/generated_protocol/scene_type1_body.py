# This is a generated file! Please edit source .ksy file and use kaitai-struct-compiler to rebuild
# type: ignore

import kaitaistruct
from kaitaistruct import ReadWriteKaitaiStruct, KaitaiStream, BytesIO
from custom_components.ha_govee_led_ble.generated_protocol import govee_common
from custom_components.ha_govee_led_ble.generated_protocol import govee_shared


if getattr(kaitaistruct, 'API_VERSION', (0, 9)) < (0, 11):
    raise Exception("Incompatible Kaitai Struct Python API: 0.11 or later is required, but you have %s" % (kaitaistruct.__version__))

class SceneType1Body(ReadWriteKaitaiStruct):
    def __init__(self, _io=None, _parent=None, _root=None):
        super(SceneType1Body, self).__init__(_io)
        self._parent = _parent
        self._root = _root or self

    def _read(self):
        self.header = govee_common.GoveeCommon.A3Header(self._io)
        self.header._read()
        self.scene_type = self._io.read_u1()
        if not self.scene_type == 1:
            raise kaitaistruct.ValidationNotEqualError(1, self.scene_type, self._io, u"/seq/1")
        self.content = govee_shared.GoveeShared.SceneType1Content(self._io)
        self.content._read()
        self._dirty = False


    def _fetch_instances(self):
        pass
        self.header._fetch_instances()
        self.content._fetch_instances()


    def _write__seq(self, io=None):
        super(SceneType1Body, self)._write__seq(io)
        self.header._write__seq(self._io)
        self._io.write_u1(self.scene_type)
        self.content._write__seq(self._io)


    def _check(self):
        if not self.scene_type == 1:
            raise kaitaistruct.ValidationNotEqualError(1, self.scene_type, None, u"/seq/1")
        self._dirty = False

    @property
    def brightness_flag(self):
        if hasattr(self, '_m_brightness_flag'):
            return self._m_brightness_flag

        self._m_brightness_flag = self.content.brightness_flag
        return getattr(self, '_m_brightness_flag', None)

    def _invalidate_brightness_flag(self):
        del self._m_brightness_flag
    @property
    def colour_stride(self):
        if hasattr(self, '_m_colour_stride'):
            return self._m_colour_stride

        self._m_colour_stride = self.content.colour_stride
        return getattr(self, '_m_colour_stride', None)

    def _invalidate_colour_stride(self):
        del self._m_colour_stride
    @property
    def config(self):
        if hasattr(self, '_m_config'):
            return self._m_config

        self._m_config = self.content.config
        return getattr(self, '_m_config', None)

    def _invalidate_config(self):
        del self._m_config
    @property
    def layout(self):
        if hasattr(self, '_m_layout'):
            return self._m_layout

        self._m_layout = self.content.layout
        return getattr(self, '_m_layout', None)

    def _invalidate_layout(self):
        del self._m_layout
    @property
    def num_palette(self):
        if hasattr(self, '_m_num_palette'):
            return self._m_num_palette

        self._m_num_palette = self.content.num_palette
        return getattr(self, '_m_num_palette', None)

    def _invalidate_num_palette(self):
        del self._m_num_palette
    @property
    def num_steps(self):
        if hasattr(self, '_m_num_steps'):
            return self._m_num_steps

        self._m_num_steps = self.content.num_steps
        return getattr(self, '_m_num_steps', None)

    def _invalidate_num_steps(self):
        del self._m_num_steps
    @property
    def padding(self):
        if hasattr(self, '_m_padding'):
            return self._m_padding

        self._m_padding = self.content.padding
        return getattr(self, '_m_padding', None)

    def _invalidate_padding(self):
        del self._m_padding
    @property
    def palette(self):
        if hasattr(self, '_m_palette'):
            return self._m_palette

        self._m_palette = self.content.palette
        return getattr(self, '_m_palette', None)

    def _invalidate_palette(self):
        del self._m_palette
    @property
    def steps(self):
        if hasattr(self, '_m_steps'):
            return self._m_steps

        self._m_steps = self.content.steps
        return getattr(self, '_m_steps', None)

    def _invalidate_steps(self):
        del self._m_steps

