"""The 0xa9 display-setting registers behind the removable camera module.

Which registers exist and what their fields mean; the frames themselves are built in
generated_protocol_adapter from tools/ble/kaitai/command_write.ksy::display_setting_cmd.

Two policies live here rather than at the call sites, because they are the reason this surface
is safe to expose at all: calibration registers are never WRITTEN, and the sub-commands that
belong to the HDMI sync-box sibling are named and gated rather than deleted.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

# The registers this integration READS. Writes to a calibration register stay forbidden --
# that is the bright line, and it is about overwriting factory or user calibration with no
# clean undo. A read cannot do that, so reads are allowed only for observed getter forms.
VIDEO_SETTING_READS: tuple[int, ...] = (0x01, 0x04, 0x06, 0x09, 0x0A, 0x0B, 0x10, 0x11, 0x13)

# Calibration registers with an evidenced read form rather than a trigger.
# The bar is the one that settled 0x11: a builder and a parser agreeing on field order, or a
# constructor that distinguishes read from write.
#
#   0x06  Controller4WhiteBalance -- makeWriteController writes {6, 1, v} and parse() reads
#         bArr[2], the same position; the device answered `01 32`, which decodes through that
#         parser to 50, the exact value WhiteBalanceDialog's SKU list predicts for this model.
#   0x13  VideoCheckWbCaliController -- makeReadController() is `(false, {19})`: isWrite is
#         false, the payload is the bare sub-command with no argument, and parse() reads a
#         boolean from the reply. The strongest of the three, despite the alarming name.
#
# 0x12 is deliberately NOT here. VideoAutoWbController exposes only makeWriteController(v)
# -> (true, {18, 1, v}) and makeExitCaliController() -> (true, {20}); both set isWrite, and
# there is no read factory and no parser. Our device does answer `aa a9 12`, but the app
# never asks, so nothing establishes what a read of it means. Answering is not evidence of
# being a getter.
CALIBRATION_READ_ALLOWLIST: frozenset[int] = frozenset({0x06, 0x13})

# Calibration registers that must never be WRITTEN, under any evidence. Overwriting factory
# or user calibration has no clean undo.
CALIBRATION_WRITE_FORBIDDEN: frozenset[int] = frozenset({0x05, 0x06, 0x0D, 0x12, 0x13, 0x14})
# The one 0xa9 sub-command with an identified meaning AND a round-tripped write.
BLACK_BORDER_REMOVAL_SETTING = 0x0B
# Two bytes with matching write and read field order:
#
#     write   new byte[]{17, 2, bean.b(), (byte) bean.a()}   -> {sub, len, enabled, level}
#     parse   new HDREffectBean(bArr[2] == 1, bArr[3])       -> {enabled, level}
#
# Confirmed against the wire: an H66A0 answered `aa a9 11 02 01 02` -> enabled, level 2.
#
# The LEVEL'S RANGE is not established. HDRContrastViewInterface defaults an unset bean to
# `new HDREffectBean(false, 50)`, which hints at 0-100 like every other percentage on this
# surface -- **inferred**, from a default value, so no writer here relies on it. And
# AbsVideoNewDetailVm.supportHDRContrast() returns false with no override anywhere in the
# app, so no shipped Govee SKU writes this register at all. Read and decoded here; not
# written. See INTEGRATION_NOTES_hippo.md.
AI_FILTER_SETTING = 0x10
HDR_EFFECT_SETTING = 0x11
# The level is a GEAR INDEX, not a percentage. This was `HDR_EFFECT_LEVEL_DEFAULT = 50` --
# a 0-100 reading that nothing used and a test pinned, and it was wrong: the vendor control is
# a four-position picker (`VideoTextSpiltPointView` over a `SpiltPointViewV2`, with the layout
# `b2light_video_text_spilt_point` fixing `spiltPoint_nums="4"`), and its `onPositionChange(i)`
# writes the position straight through. The owner confirmed a four-dot picker in the app on
# 2026-08-25. An H66A0 answering `01 02` is enabled at gear 2, not "level 2 percent".
# Gears are numbered the way the app numbers them: 1..4. Verified on hardware 2026-08-27 --
# a device whose app read "4 of 4" answered `aa a9 11` with `02 01 04`, and one at step 2
# answered `02 01 02`. An earlier reading here said 0..3, inferred from the widget's
# `spiltPoint_nums="4"`; that would have refused gear 4, which the vendor uses.
HDR_EFFECT_GEAR_MIN = 1
HDR_EFFECT_GEAR_MAX = 4
HDR_EFFECT_GEARS = 4
HDR_EFFECT_GEAR_DEFAULT = 1


@dataclass(frozen=True, slots=True)
class HdrEffect:
    """The decoded 0xa9 sub-0x11 register."""

    enabled: bool
    level: int


def parse_hdr_effect(values: Sequence[int]) -> HdrEffect | None:
    """Decode the two values behind sub 0x11, or None if the register is not that shape."""
    if len(values) < 2:
        return None
    return HdrEffect(enabled=values[0] == 1, level=int(values[1]))


# Sub-commands the app builds that this hardware never answers. They are NOT dead code and
# they are NOT excluded: they belong to the HDMI sync-box sibling in the same product line,
# which the same app binary serves. Our H66A0 is the camera variant, which is why it stays
# silent -- with the camera module attached or detached, so "the accessory is missing" is
# not the explanation.
#
# These sub-commands belong to HDMI sync-box models, not the H66A0 camera variant.
# The required product discriminator is unavailable locally, so they remain named but gated.
VIDEO_SETTINGS_NOT_ON_CAMERA_VARIANT: tuple[int, ...] = (0x03, 0x0E)

BLANK_SCREEN_LOW_BRIGHTNESS = 0x01
BLANK_SCREEN_SAME_TONE = 0x02
# The app's own labels, so the dropdown reads the way the app does.
BLANK_SCREEN_DETECTIONS: dict[int, str] = {
    BLANK_SCREEN_LOW_BRIGHTNESS: "low_brightness",
    BLANK_SCREEN_SAME_TONE: "same_hue",
}
# Not a wire value: the register holds the enable separately, and the two are one control here.
BLANK_SCREEN_OFF = "off"


# The camera module presence probe and the video defaults the writer falls back to.
VIDEO_SETTING_QUERY_SUBS = VIDEO_SETTING_READS
VIDEO_DEFAULT_SATURATION = 50
VIDEO_DEFAULT_SOFTNESS = 100
VIDEO_DEFAULT_PRESET = "solid"
# Not identified. Reads 0x02 on the tested device and
# never moved in any capture. Preserve whatever the device reports rather than assuming 2.
VIDEO_RESERVED_DEFAULT = 0x02

# 0xa9 sub 0x0a: blank-screen detection. Named for the register, not the app's label.
BLACK_SCREEN_DETECTION_SETTING = 0x0A
