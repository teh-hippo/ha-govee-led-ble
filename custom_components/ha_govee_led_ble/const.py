"""Constants for HA Govee LED BLE."""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any

from .h6199_calibration import WHITE_BALANCE_POSITIONS
from .music_semantics import (
    H1A42_MUSIC_VARIANTS,
    H66A0_MUSIC_VARIANTS,
    H617A_MUSIC_VARIANTS,
    H617C_MUSIC_VARIANTS,
    H617E_MUSIC_VARIANTS,
    H6076_LEGACY_MUSIC_VARIANTS,
    H6076_MUSIC_VARIANTS,
    H6099_MUSIC_VARIANTS,
    H6102_MUSIC_VARIANTS,
    H6125_MUSIC_VARIANTS,
    H7020_MUSIC_VARIANTS,
    H7025_MUSIC_VARIANTS,
    MusicVariant,
)

DOMAIN = "ha_govee_led_ble"
CONF_MODEL = "model"
CONF_H6102_APP_FIRMWARE = "h6102_app_firmware"
CONF_H6102_APP_HARDWARE = "h6102_app_hardware"
CONF_H6102_PACT = "h6102_pact"
CONF_EFFECT_CATEGORIES = "effect_categories"
CONF_EFFECT_FAMILIES = "effect_families"
CONF_PREFIX_EFFECT_NAMES = "prefix_effect_names"
CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS = "always_include_custom_effects"
CONF_CONNECTION_MODE = "connection_mode"
CONNECTION_MODE_RELEASE = "release"
CONNECTION_MODE_HOLD = "hold"
EFFECT_FAMILY_SCENES = "scenes"
EFFECT_FAMILY_MUSIC = "music"
EFFECT_FAMILY_VIDEO = "video"
EFFECT_CATEGORY_SCENES = "scenes"
EFFECT_CATEGORY_VIDEO = "video"
EFFECT_CATEGORY_EFFECTS = "effects"
EFFECT_CATEGORY_MULTI_LAYERED = "multi_layered"
EFFECT_CATEGORY_REACTIVE = "reactive"
EFFECT_CATEGORY_ADVANCED = "advanced"
EFFECT_CATEGORIES = (
    EFFECT_CATEGORY_VIDEO,
    EFFECT_CATEGORY_SCENES,
    EFFECT_CATEGORY_EFFECTS,
    EFFECT_CATEGORY_MULTI_LAYERED,
    EFFECT_CATEGORY_REACTIVE,
    EFFECT_CATEGORY_ADVANCED,
)
EFFECT_CATEGORY_CONTENT_KINDS = {
    EFFECT_CATEGORY_SCENES: frozenset({"scene_builtin", "scene_palette", "scene_layered"}),
    EFFECT_CATEGORY_VIDEO: frozenset({"video_profile"}),
    EFFECT_CATEGORY_EFFECTS: frozenset({"h617a_painted", "h617a_single", "h6179_single_diy", "palette_diy"}),
    EFFECT_CATEGORY_MULTI_LAYERED: frozenset({"h617a_multi", "h6179_mixed_diy"}),
    EFFECT_CATEGORY_REACTIVE: frozenset({"music_profile"}),
    EFFECT_CATEGORY_ADVANCED: frozenset({"advanced", "workshop"}),
}
_BLE_MODEL_PATTERN = re.compile(
    r"(?:(?:ihoment|Govee|Minger|GBK|GVH)_(H[0-9A-Z]{4})(?:_|$)|^GVH?([0-9A-Z]{4})(?:_[0-9A-Z]+|[0-9A-Z]{4}|$)$|^(H[0-9A-Z]{4})_[0-9A-Z]+$)",
    re.IGNORECASE,
)


class SupportQuality(StrEnum):
    EXPERIMENTAL = "experimental"
    SUPPORTED = "supported"


class ReadDomain(StrEnum):
    POWER = "power"
    BRIGHTNESS = "brightness"
    COLOUR_MODE = "colour_mode"
    MODE = "mode"
    FIRMWARE = "firmware"
    HARDWARE = "hardware"
    SUBORDINATE_20 = "subordinate_20"
    SUBORDINATE_21 = "subordinate_21"
    DISPLAY_SETTING = "display_setting"
    RELATIVE_BRIGHTNESS = "relative_brightness"
    SEGMENTS = "segments"
    CONFIGURED_STRINGS = "configured_strings"
    PHYSICAL_IC_COUNT = "physical_ic_count"
    INSTALLATION_DIRECTION = "installation_direction"
    CAMERA_HEALTH = "camera_health"
    OTHER = "other"


_IDENTITY_READ_DOMAINS = frozenset(
    {
        ReadDomain.FIRMWARE,
        ReadDomain.HARDWARE,
        ReadDomain.SUBORDINATE_20,
        ReadDomain.SUBORDINATE_21,
        ReadDomain.PHYSICAL_IC_COUNT,
    }
)


@dataclass(frozen=True)
class VideoFirmwareCondition:
    control: str
    identity_field: str
    minimum: str

    def __post_init__(self) -> None:
        if self.control not in {
            "capture_region",
            "saturation",
            "sound_effects",
            "white_balance",
            "relative_brightness",
            "blank_screen",
            "black_border",
        }:
            raise ValueError("unknown video firmware control")
        if self.identity_field not in {"fw_version", "hw_version", "subordinate_20_version", "subordinate_21_version"}:
            raise ValueError("unknown firmware identity field")
        if re.fullmatch(r"[0-9]{1,3}\.[0-9]{2}\.[0-9]{2}", self.minimum) is None:
            raise ValueError("firmware minimum must use major.xx.xx notation")


@dataclass(frozen=True)
class ModelProfile:
    name: str
    support_quality: SupportQuality = SupportQuality.EXPERIMENTAL
    command_grammar: str | None = None
    command_ack_grammar: str | None = None
    # None retains the grammar's shipped operations; a set restricts physical writes.
    command_operations: frozenset[str] | None = None
    status_grammar: str | None = None
    bulk_status_grammar: str | None = None
    setting_grammar: str | None = None
    outbound_transform: Callable[[bytes], bytes] | None = None
    # Device register range for the brightness byte; None means the wire carries percent.
    brightness_wire_range: tuple[int, int] | None = None
    # AA05 selector byte the device accepts for the active-mode query.
    colour_mode_query_selector: int = 0
    # Effect semantics require evidence independent of basic command compatibility.
    effect_grammar: str | None = None
    # None permits the exact-SKU workflow ceiling; a set narrows it for this device.
    effect_workflows: frozenset[str] | None = None
    video_grammar: str | None = None
    dreamview_grammar: str | None = None
    dreamview_operations: frozenset[str] = frozenset()
    dreamview_reads: frozenset[str] = frozenset()
    dreamview_max_sub_devices: int = 0
    video_firmware_conditions: tuple[VideoFirmwareCondition, ...] = ()
    profile_identity_fields: frozenset[str] = frozenset()
    # Exact-product revision policy, independent of compatible wire grammars.
    video_revision_policy: str | None = None
    read_domains: frozenset[ReadDomain] = frozenset()
    setup_required_read_domains: frozenset[ReadDomain] = frozenset()
    supports_rgb: bool = False
    supports_installation_direction: bool = False
    supports_color_temperature: bool = False
    min_color_temp_kelvin: int = 2000
    max_color_temp_kelvin: int = 9000
    readback_min_color_temp_kelvin: int | None = None
    kelvin_direct_rgb: tuple[int, int, int] = (0, 0, 0)
    supports_custom_effects: bool = False
    supports_scenes: bool = False
    supports_video_mode: bool = False
    video_modes: tuple[str, ...] = ()
    default_video_parameters: tuple[tuple[str, int | str], ...] = ()
    supports_video_capture_region: bool = False
    supports_video_saturation: bool = False
    video_saturation_min: int = 0
    supports_video_sound_effects: bool = False
    supports_advanced_effects: bool = False
    supports_multi_layered_effects: bool = False
    supports_white_balance: bool = False
    supports_white_balance_readback: bool = False
    video_white_balance_default: int = 17
    video_white_balance_representation: str = "position"
    video_white_balance_min: int = 1
    video_white_balance_max: int = 20
    video_white_balance_calibration: tuple[tuple[int, ...], ...] = ()
    video_brightness_zones: tuple[str, ...] = ()
    supports_relative_brightness: bool = False
    supports_blank_screen: bool = False
    supports_black_border: bool = False
    # Selects the music codebook and selector writer when they differ from command_grammar.
    music_grammar: str | None = None
    music_modes: tuple[str, ...] = ()
    readback_music_modes: tuple[str, ...] = ()
    music_variants: tuple[MusicVariant, ...] = ()
    music_upload_before_selector: bool = False
    music_requires_upload_ack: bool = False
    music_retry_after_upload: bool = True
    music_params_require_activation: bool = False
    # Physical IC count is independent of logical segment_count. None means unknown.
    physical_ic_count: int | None = None
    music_sensitivity_min: int = 0
    music_sensitivity_max: int = 99
    supports_music_color: bool = False
    supports_white_brightness: bool = False
    static_readback_echoes_color: bool = False
    static_readback_kelvin: bool = False
    static_readback_zero_kelvin_is_rgb: bool = False
    static_readback_gradual: bool = False
    whole_device_mask: int = 0
    segment_count: int = 0
    segment_group_size: int = 0
    segment_colour_mode_ambiguous: bool = False
    configured_string_counts: tuple[int, ...] = ()
    bulbs_per_string: int = 0
    supports_segment_writes: bool = False
    supports_segment_brightness: bool = False
    supports_segment_color_temperature: bool = False
    segment_kelvin_renders_device_rgb: bool = False
    connection_idle_timeout: float | None = None
    scene_catalogue_sku: str | None = None
    legacy_scene_catalogue_sku: str | None = None
    selector_only_scene_bits: int | None = None
    scene_codes: frozenset[int] | None = None
    local_scenes: tuple[tuple[int, str], ...] = ()
    advanced_scene_carrier: tuple[int, int] | None = None
    advanced_diy_selector: int | None = None
    # When set, Type04 custom effects upload as A1 command-02 frames led by this selector and activate with it.
    a1_diy_selector: int | None = None
    diy_requires_upload_ack: bool = False
    packet_write_delay: float = 0.0
    boolean_controls: frozenset[str] = frozenset()
    supports_power_on_behaviour: bool = False
    default_effect_families_override: frozenset[str] | None = None
    effect_readback: str = "none"

    def __post_init__(self) -> None:
        if len(self.kelvin_direct_rgb) != 3 or any(
            type(channel) is not int or not 0 <= channel <= 255 for channel in self.kelvin_direct_rgb
        ):
            raise ValueError("Kelvin direct RGB must contain three byte values")
        if not self.boolean_controls <= {"gradual", "limit", "power_off_memory", "panel_enabled", "ring_enabled"}:
            raise ValueError("unknown boolean device setting")
        if self.configured_string_counts and (
            self.bulbs_per_string <= 0
            or any(type(count) is not int or count <= 0 for count in self.configured_string_counts)
            or self.command_grammar is None
            or self.status_grammar is None
        ):
            raise ValueError("configured strings require positive product counts and command/status grammars")
        if self.boolean_controls and (self.command_grammar is None or self.status_grammar is None):
            raise ValueError("boolean settings require command and status grammars")
        if self.advanced_diy_selector is not None and (
            type(self.advanced_diy_selector) is not int or not 0 <= self.advanced_diy_selector <= 65535
        ):
            raise ValueError("Advanced DIY selector must be an unsigned 16-bit value")
        if self.a1_diy_selector is not None and (
            type(self.a1_diy_selector) is not int or not 0 <= self.a1_diy_selector <= 255
        ):
            raise ValueError("A1 DIY selector must be an unsigned byte")
        if (
            isinstance(self.packet_write_delay, bool)
            or not isinstance(self.packet_write_delay, int | float)
            or self.packet_write_delay < 0
        ):
            raise ValueError("packet write delay must be non-negative")
        if type(self.dreamview_max_sub_devices) is not int or not 0 <= self.dreamview_max_sub_devices <= 255:
            raise ValueError("DreamView member capacity must be from 0 to 255")
        if self.physical_ic_count is not None and (
            type(self.physical_ic_count) is not int or self.physical_ic_count <= 0
        ):
            raise ValueError("physical IC count must be a positive integer or unknown")
        if self.video_revision_policy not in (None, "H6199"):
            raise ValueError("unknown video revision policy")
        if type(self.video_saturation_min) is not int or not 0 <= self.video_saturation_min <= 100:
            raise ValueError("video saturation minimum must be from 0 to 100")
        if not self.setup_required_read_domains <= self.read_domains:
            raise ValueError("setup-required read domains must also be readable")
        if len({condition.control for condition in self.video_firmware_conditions}) != len(
            self.video_firmware_conditions
        ):
            raise ValueError("only one firmware condition per video control is supported")
        if self.read_domains and self.status_grammar is None:
            raise ValueError("read domains require a status grammar")
        if (
            self.read_domains
            & {
                ReadDomain.POWER,
                ReadDomain.BRIGHTNESS,
                ReadDomain.COLOUR_MODE,
                ReadDomain.MODE,
                ReadDomain.FIRMWARE,
                ReadDomain.HARDWARE,
                ReadDomain.SEGMENTS,
                ReadDomain.CONFIGURED_STRINGS,
                ReadDomain.PHYSICAL_IC_COUNT,
                ReadDomain.INSTALLATION_DIRECTION,
                ReadDomain.CAMERA_HEALTH,
            }
            and self.command_grammar is None
        ):
            raise ValueError("basic read domains require a command grammar")
        if self.video_modes and self.video_grammar is None:
            raise ValueError("video modes require a grammar")
        if self.supports_video_mode and not self.video_modes:
            raise ValueError("video support requires explicit modes")
        if (
            self.supports_video_capture_region
            or self.supports_video_saturation
            or self.supports_video_sound_effects
            or self.supports_white_balance
            or self.supports_relative_brightness
            or self.supports_blank_screen
            or self.supports_black_border
        ) and not self.supports_video_mode:
            raise ValueError("video settings require video-mode support")
        if self.supports_white_balance or self.supports_white_balance_readback:
            if self.video_white_balance_representation not in {"position", "scalar"}:
                raise ValueError("unknown white-balance representation")
            if not self.video_white_balance_min <= self.video_white_balance_default <= self.video_white_balance_max:
                raise ValueError("white-balance default is outside its range")
        if self.supports_white_balance:
            if (
                len(self.video_white_balance_calibration)
                != self.video_white_balance_max - self.video_white_balance_min + 1
            ):
                raise ValueError("white-balance calibration must cover its range")
            width = 2 if self.video_white_balance_representation == "position" else 1
            if any(
                len(row) != width or any(type(value) is not int or not 0 <= value <= 255 for value in row)
                for row in self.video_white_balance_calibration
            ):
                raise ValueError("invalid white-balance calibration")
        if self.supports_relative_brightness and self.video_brightness_zones not in {
            ("left", "top", "right", "bottom"),
            ("left", "top", "right", "bottom", "strip_left", "strip_right"),
        }:
            raise ValueError("relative brightness requires an evidenced ordered topology")
        if self.selector_only_scene_bits is not None and not 1 <= self.selector_only_scene_bits <= 16:
            raise ValueError("selector-only scene width must be from 1 to 16 bits")
        if self.brightness_wire_range is not None:
            low, high = self.brightness_wire_range
            if not 1 <= low < high <= 255:
                raise ValueError("brightness register range must satisfy 1 <= minimum < maximum <= 255")
            if self.outbound_transform is None:
                raise ValueError("a brightness register range requires the outbound transform that encodes it")

    def can_read(self, domain: ReadDomain) -> bool:
        return domain in self.read_domains

    def validate_video_saturation(self, value: int) -> None:
        if type(value) is not int or not self.video_saturation_min <= value <= 100:
            raise ValueError(f"video saturation must be from {self.video_saturation_min} to 100")

    @property
    def requires_notifications(self) -> bool:
        return bool(self.read_domains or self.dreamview_reads or self.boolean_controls)

    @property
    def state_readable(self) -> bool:
        return bool(self.read_domains - _IDENTITY_READ_DOMAINS)

    @property
    def supports_color_mode_readback(self) -> bool:
        return self.can_read(ReadDomain.COLOUR_MODE) or self.can_read(ReadDomain.MODE)

    @property
    def supports_segments(self) -> bool:
        return self.segment_count > 0 and self.supports_segment_writes

    @property
    def segment_group_count(self) -> int:
        if not self.supports_segments or self.segment_group_size <= 0:
            return 0
        return (self.segment_count + self.segment_group_size - 1) // self.segment_group_size

    @property
    def supports_music_mode(self) -> bool:
        return bool(self.music_modes)


MUSIC_MODE_SLUGS: dict[str, int] = {
    "energetic": 0x05,
    "rhythm": 0x03,
    "spectrum": 0x04,
    "rolling": 0x06,
    "separation": 0x32,
    "hopping": 0x33,
    "piano_keys": 0x34,
    "fountain": 0x35,
    "day_and_night": 0x37,
    "bloom": 0x30,
    "shiny": 0x31,
    "flowing_light": 0x53,
    "painting": 0x55,
    "windmill": 0x78,
    "splash": 0x84,
    "spring": 0x85,
    "beat": 0xA9,
}

_H6199_MUSIC_MODES = ("energetic", "rhythm", "spectrum", "rolling")


_H617A_PROFILE = ModelProfile(
    "H617A LED Strip",
    support_quality=SupportQuality.SUPPORTED,
    command_grammar="H617A",
    status_grammar="H617A",
    effect_grammar="H617A",
    read_domains=frozenset(
        {
            ReadDomain.POWER,
            ReadDomain.BRIGHTNESS,
            ReadDomain.COLOUR_MODE,
            ReadDomain.FIRMWARE,
            ReadDomain.HARDWARE,
            ReadDomain.SEGMENTS,
        }
    ),
    setup_required_read_domains=frozenset(
        {
            ReadDomain.POWER,
            ReadDomain.BRIGHTNESS,
            ReadDomain.COLOUR_MODE,
        }
    ),
    supports_rgb=True,
    supports_color_temperature=True,
    supports_custom_effects=True,
    supports_scenes=True,
    music_modes=(
        "energetic",
        "rhythm",
        "spectrum",
        "rolling",
        "separation",
        "hopping",
        "piano_keys",
        "fountain",
        "day_and_night",
        "bloom",
        "shiny",
    ),
    music_variants=H617A_MUSIC_VARIANTS,
    music_upload_before_selector=True,
    music_requires_upload_ack=True,
    supports_music_color=True,
    supports_advanced_effects=True,
    supports_multi_layered_effects=True,
    whole_device_mask=0x7FFF,
    # H617A and H617E expose fifteen segments through five explicit aa a5 query groups of three.
    # Segment writes ACK normally but do not publish updated groups without those queries.
    segment_count=15,
    segment_group_size=3,
    supports_segment_writes=True,
    # Preserve the existing qualified segment operations independently of RGB writes.
    supports_segment_brightness=True,
    supports_segment_color_temperature=True,
    connection_idle_timeout=3.0,
    scene_catalogue_sku="H617A",
    advanced_scene_carrier=(1013, 11836),
    effect_readback="diy_code_only",
    # supports_white_brightness stays false because static subcommand 0x02 is segment-relative
    # brightness, not the level of a white colour-temperature mode. It compounds with master
    # brightness and is exposed through set_segment_brightness, including all-segment writes;
    # the aa a5 groups provide its per-segment readback.
)


_H6076_ALL_MUSIC_MODES = (
    "energetic",
    "rhythm",
    "bounce",
    "hopping",
    "beat",
    "spray",
    "skittles",
    "torch",
    "candy_crush",
    "fusion",
    "shiny",
    "separation",
)

# Baseline H6076 controls.  Companion music modes need software 1.02.00+, added by _h6076_profile.
_H6076_PROFILE = ModelProfile(
    "H6076 Lyra Floor Lamp",
    support_quality=SupportQuality.SUPPORTED,
    command_grammar="H617A",
    status_grammar="H6076",
    effect_grammar="H617A",
    read_domains=frozenset(
        {
            ReadDomain.POWER,
            ReadDomain.BRIGHTNESS,
            ReadDomain.COLOUR_MODE,
            ReadDomain.FIRMWARE,
            ReadDomain.HARDWARE,
            ReadDomain.SEGMENTS,
        }
    ),
    profile_identity_fields=frozenset({"fw_version"}),
    setup_required_read_domains=frozenset({ReadDomain.POWER, ReadDomain.BRIGHTNESS}),
    supports_rgb=True,
    supports_color_temperature=True,
    min_color_temp_kelvin=2700,
    max_color_temp_kelvin=6500,
    readback_min_color_temp_kelvin=2200,
    static_readback_kelvin=True,
    static_readback_zero_kelvin_is_rgb=True,
    static_readback_gradual=True,
    physical_ic_count=14,
    whole_device_mask=0x007F,
    segment_count=7,
    segment_group_size=4,
    supports_segment_writes=True,
    supports_segment_brightness=True,
    supports_segment_color_temperature=False,
    supports_scenes=True,
    supports_custom_effects=True,
    supports_advanced_effects=True,
    supports_multi_layered_effects=True,
    effect_readback="diy_code_only",
    advanced_diy_selector=402,
    diy_requires_upload_ack=True,
    boolean_controls=frozenset({"gradual"}),
    connection_idle_timeout=3.0,
    scene_catalogue_sku="H6076",
    music_grammar="H6076",
    music_modes=(
        "energetic",
        "rhythm",
        "bounce",
        "hopping",
        "beat",
        "spray",
    ),
    readback_music_modes=_H6076_ALL_MUSIC_MODES,
    music_variants=H6076_LEGACY_MUSIC_VARIANTS,
    supports_music_color=True,
)

_H6076_MUSIC_PROFILE = replace(
    _H6076_PROFILE,
    min_color_temp_kelvin=2200,
    readback_min_color_temp_kelvin=None,
    music_modes=_H6076_ALL_MUSIC_MODES,
    readback_music_modes=(),
    music_variants=H6076_MUSIC_VARIANTS,
    # MultipleController4Music uploads the companion before the selector and the lamp acknowledges it.
    music_upload_before_selector=True,
    music_requires_upload_ack=True,
    music_params_require_activation=True,
)

MODEL_PROFILES: dict[str, ModelProfile] = {
    "H60A1": ModelProfile(
        "H60A1 Ceiling Light",
        support_quality=SupportQuality.SUPPORTED,
        command_grammar="H617A",
        command_ack_grammar="H617A",
        status_grammar="H60A1",
        bulk_status_grammar="H60A",
        effect_grammar="H617A",
        command_operations=frozenset({"power", "brightness", "static", "scene", "diy", "effect_upload"}),
        read_domains=frozenset({ReadDomain.POWER, ReadDomain.COLOUR_MODE, ReadDomain.FIRMWARE, ReadDomain.HARDWARE}),
        supports_scenes=True,
        supports_custom_effects=True,
        supports_multi_layered_effects=True,
        scene_catalogue_sku="H60A1",
        advanced_diy_selector=254,
        diy_requires_upload_ack=True,
        effect_readback="diy_code_only",
        segment_colour_mode_ambiguous=True,
        profile_identity_fields=frozenset({"fw_version", "hw_version"}),
        setup_required_read_domains=frozenset({ReadDomain.POWER}),
        min_color_temp_kelvin=2700,
        max_color_temp_kelvin=6500,
        whole_device_mask=0x3FFF,
        segment_count=14,
        segment_group_size=4,
        # RGB, whole-device Kelvin, and segment reads require revision evidence in
        # device_profile. Panel brightness is write-only; segment brightness ACKs
        # without rendering, and masked H60A1 Kelvin blanks the sibling zone.
    ),
    "H60A6": ModelProfile(
        "H60A6 Ceiling Light Pro",
        support_quality=SupportQuality.SUPPORTED,
        command_grammar="H617A",
        command_ack_grammar="H60A6",
        status_grammar="H60A6",
        bulk_status_grammar="H60A",
        setting_grammar="H60A6",
        effect_grammar="H60A6",
        command_operations=frozenset({"power", "brightness", "static", "scene", "diy", "effect_upload"}),
        read_domains=frozenset({ReadDomain.POWER, ReadDomain.COLOUR_MODE, ReadDomain.FIRMWARE, ReadDomain.HARDWARE}),
        supports_scenes=True,
        supports_custom_effects=True,
        supports_advanced_effects=True,
        supports_multi_layered_effects=True,
        scene_catalogue_sku="H60A6",
        advanced_diy_selector=254,
        diy_requires_upload_ack=True,
        effect_readback="diy_code_only",
        physical_ic_count=133,
        boolean_controls=frozenset({"panel_enabled", "ring_enabled"}),
        supports_power_on_behaviour=True,
        segment_colour_mode_ambiguous=True,
        profile_identity_fields=frozenset({"fw_version", "hw_version"}),
        setup_required_read_domains=frozenset({ReadDomain.POWER}),
        min_color_temp_kelvin=2700,
        max_color_temp_kelvin=6500,
        whole_device_mask=0x1FFF,
        segment_count=13,
        segment_group_size=4,
        # Pact 1/1 uses whole-device colour; 1/2+ has thirteen logical segments.
    ),
    "H601C": ModelProfile(
        "H601C Recessed Downlight",
        support_quality=SupportQuality.SUPPORTED,
        command_grammar="H601C",
        effect_grammar="H617A",
        command_operations=frozenset({"power", "brightness", "static", "scene", "diy", "effect_upload"}),
        colour_mode_query_selector=1,
        supports_rgb=True,
        supports_color_temperature=True,
        min_color_temp_kelvin=2700,
        max_color_temp_kelvin=6500,
        supports_custom_effects=True,
        supports_scenes=True,
        supports_multi_layered_effects=True,
        whole_device_mask=1,
        connection_idle_timeout=1.5,
        scene_catalogue_sku="H601C",
    ),
    "H6099": ModelProfile(
        "H6099 TV Backlight 3 Lite",
        support_quality=SupportQuality.EXPERIMENTAL,
        command_grammar="H6099",
        status_grammar="H6099",
        effect_grammar="H6099",
        video_grammar="H6099",
        dreamview_grammar="H6099",
        dreamview_operations=frozenset(
            {
                "replace_group",
                "delete_group",
                "switch_group",
                "member_brightness",
                "same_brightness",
                "member_connect",
                "saturation",
                "sample",
                "sound",
            }
        ),
        dreamview_reads=frozenset(
            {
                "switch_group",
                "member_brightness",
                "same_brightness",
                "member_connect",
                "saturation",
                "sample",
                "sound",
            }
        ),
        dreamview_max_sub_devices=7,
        video_firmware_conditions=(VideoFirmwareCondition("black_border", "subordinate_21_version", "1.00.11"),),
        read_domains=frozenset(
            {
                ReadDomain.POWER,
                ReadDomain.BRIGHTNESS,
                ReadDomain.COLOUR_MODE,
                ReadDomain.FIRMWARE,
                ReadDomain.HARDWARE,
                ReadDomain.DISPLAY_SETTING,
                ReadDomain.SUBORDINATE_20,
                ReadDomain.SUBORDINATE_21,
                ReadDomain.RELATIVE_BRIGHTNESS,
                ReadDomain.SEGMENTS,
                ReadDomain.PHYSICAL_IC_COUNT,
                ReadDomain.INSTALLATION_DIRECTION,
                ReadDomain.CAMERA_HEALTH,
            }
        ),
        setup_required_read_domains=frozenset({ReadDomain.POWER, ReadDomain.BRIGHTNESS, ReadDomain.COLOUR_MODE}),
        supports_installation_direction=True,
        supports_rgb=True,
        supports_color_temperature=True,
        static_readback_kelvin=True,
        supports_scenes=True,
        supports_video_mode=True,
        video_modes=("movie", "game"),
        supports_video_capture_region=True,
        supports_video_saturation=True,
        video_saturation_min=1,
        supports_video_sound_effects=True,
        supports_white_balance=True,
        supports_white_balance_readback=True,
        video_white_balance_representation="scalar",
        video_white_balance_default=50,
        video_white_balance_max=100,
        video_white_balance_calibration=tuple((value,) for value in range(1, 101)),
        video_brightness_zones=("left", "top", "right", "bottom"),
        supports_relative_brightness=True,
        supports_blank_screen=True,
        supports_black_border=True,
        music_variants=H6099_MUSIC_VARIANTS,
        music_upload_before_selector=True,
        supports_music_color=True,
        music_modes=(
            "energetic",
            "rhythm",
            "spectrum",
            "rolling",
            "separation",
            "hopping",
            "piano_keys",
            "fountain",
            "day_and_night",
            "bloom",
            "shiny",
        ),
        whole_device_mask=0x3FFF,
        segment_count=14,
        segment_group_size=4,
        supports_segment_writes=True,
        supports_segment_brightness=True,
        supports_segment_color_temperature=True,
        scene_catalogue_sku="H6099",
        supports_custom_effects=True,
        default_effect_families_override=frozenset({EFFECT_FAMILY_VIDEO}),
        # Ordinary DIY uses Sub4Diy, not an H6199 scene or Workshop carrier.
        effect_readback="diy_code_only",
    ),
    "H66A0": ModelProfile(
        "H66A0 TV Backlight 3 Pro",
        support_quality=SupportQuality.EXPERIMENTAL,
        command_grammar="H6099",
        status_grammar="H66A0",
        effect_grammar="H6099",
        music_grammar="H66A0",
        video_grammar="H66A0-video",
        read_domains=frozenset(
            {
                ReadDomain.POWER,
                ReadDomain.BRIGHTNESS,
                ReadDomain.COLOUR_MODE,
                ReadDomain.FIRMWARE,
                ReadDomain.HARDWARE,
                ReadDomain.DISPLAY_SETTING,
                ReadDomain.SUBORDINATE_20,
                ReadDomain.SUBORDINATE_21,
                ReadDomain.RELATIVE_BRIGHTNESS,
                ReadDomain.SEGMENTS,
                ReadDomain.PHYSICAL_IC_COUNT,
                ReadDomain.INSTALLATION_DIRECTION,
                ReadDomain.CAMERA_HEALTH,
            }
        ),
        setup_required_read_domains=frozenset({ReadDomain.POWER, ReadDomain.BRIGHTNESS, ReadDomain.COLOUR_MODE}),
        supports_installation_direction=True,
        supports_rgb=True,
        supports_color_temperature=True,
        static_readback_kelvin=True,
        static_readback_zero_kelvin_is_rgb=True,
        supports_scenes=True,
        supports_video_mode=True,
        video_modes=("movie", "game"),
        default_video_parameters=(("picture_preset", "vivid"), ("opaque", 2)),
        supports_video_saturation=True,
        video_saturation_min=1,
        supports_video_sound_effects=True,
        supports_white_balance=True,
        supports_white_balance_readback=True,
        video_white_balance_representation="scalar",
        video_white_balance_default=50,
        video_white_balance_max=100,
        video_white_balance_calibration=tuple((value,) for value in range(1, 101)),
        video_brightness_zones=("left", "top", "right", "bottom"),
        supports_relative_brightness=True,
        supports_blank_screen=True,
        supports_black_border=True,
        physical_ic_count=90,
        music_variants=H66A0_MUSIC_VARIANTS,
        music_upload_before_selector=True,
        supports_music_color=True,
        music_modes=(
            "energetic",
            "rhythm",
            "spectrum",
            "rolling",
            "separation",
            "hopping",
            "piano_keys",
            "fountain",
            "day_and_night",
            "bloom",
            "splash",
            "spring",
            "painting",
            "beat",
            "windmill",
            "flowing_light",
        ),
        whole_device_mask=0x3FFF,
        segment_count=14,
        segment_group_size=4,
        supports_segment_writes=True,
        supports_segment_brightness=True,
        supports_segment_color_temperature=True,
        segment_kelvin_renders_device_rgb=True,
        scene_catalogue_sku="H66A0",
        supports_custom_effects=True,
        default_effect_families_override=frozenset({EFFECT_FAMILY_VIDEO}),
        effect_readback="diy_code_only",
    ),
    "H1A42": ModelProfile(
        "H1A42 LED Strip Light 2",
        support_quality=SupportQuality.EXPERIMENTAL,
        command_grammar="H617A",
        status_grammar="H1A42",
        effect_grammar="H617A",
        music_grammar="H1A42",
        static_readback_kelvin=True,
        static_readback_zero_kelvin_is_rgb=True,
        static_readback_gradual=True,
        read_domains=frozenset(
            {
                ReadDomain.POWER,
                ReadDomain.BRIGHTNESS,
                ReadDomain.COLOUR_MODE,
                ReadDomain.FIRMWARE,
                ReadDomain.HARDWARE,
                ReadDomain.SUBORDINATE_20,
                ReadDomain.SUBORDINATE_21,
                ReadDomain.PHYSICAL_IC_COUNT,
                ReadDomain.SEGMENTS,
            }
        ),
        setup_required_read_domains=frozenset(
            {
                ReadDomain.POWER,
                ReadDomain.BRIGHTNESS,
                ReadDomain.COLOUR_MODE,
            }
        ),
        supports_rgb=True,
        supports_color_temperature=True,
        min_color_temp_kelvin=1000,
        max_color_temp_kelvin=10000,
        supports_custom_effects=True,
        supports_scenes=True,
        music_modes=(
            "rhythm",
            "spectrum",
            "energetic",
            "rolling",
            "splash",
            "spring",
            "ripple",
            "orbit",
        ),
        music_variants=H1A42_MUSIC_VARIANTS,
        music_upload_before_selector=True,
        supports_music_color=True,
        physical_ic_count=12,
        whole_device_mask=0x001F,
        segment_count=5,
        segment_group_size=4,
        supports_segment_writes=True,
        supports_segment_brightness=True,
        supports_segment_color_temperature=True,
        scene_catalogue_sku="H1A42",
        effect_readback="diy_code_only",
        boolean_controls=frozenset({"gradual"}),
    ),
    "H617A": _H617A_PROFILE,
    "H617E": replace(
        _H617A_PROFILE,
        name="H617E LED Strip",
        music_variants=H617E_MUSIC_VARIANTS,
        music_upload_before_selector=False,
        music_requires_upload_ack=False,
        support_quality=SupportQuality.SUPPORTED,
        effect_grammar="H617A",
        music_modes=(
            "energetic",
            "rhythm",
            "spectrum",
            "rolling",
            "separation",
            "hopping",
            "piano_keys",
            "fountain",
            "day_and_night",
            "bloom",
            "shiny",
        ),
        scene_catalogue_sku="H617E",
        legacy_scene_catalogue_sku="H617A",
        advanced_scene_carrier=(29884, 41599),
    ),
    "H617C": ModelProfile(
        "H617C LED Strip",
        support_quality=SupportQuality.SUPPORTED,
        command_grammar="H617A",
        status_grammar="H617C",
        effect_grammar="H617A",
        colour_mode_query_selector=1,
        static_readback_kelvin=True,
        static_readback_zero_kelvin_is_rgb=True,
        static_readback_gradual=True,
        read_domains=frozenset(
            {
                ReadDomain.POWER,
                ReadDomain.BRIGHTNESS,
                ReadDomain.COLOUR_MODE,
                ReadDomain.FIRMWARE,
                ReadDomain.HARDWARE,
                ReadDomain.SEGMENTS,
            }
        ),
        setup_required_read_domains=frozenset(
            {
                ReadDomain.POWER,
                ReadDomain.BRIGHTNESS,
                ReadDomain.COLOUR_MODE,
            }
        ),
        supports_rgb=True,
        supports_color_temperature=True,
        supports_custom_effects=True,
        supports_scenes=True,
        supports_advanced_effects=True,
        supports_multi_layered_effects=True,
        music_modes=(
            "energetic",
            "rhythm",
            "spectrum",
            "rolling",
            "separation",
            "hopping",
            "piano_keys",
            "fountain",
            "day_and_night",
            "bloom",
            "shiny",
        ),
        music_variants=H617C_MUSIC_VARIANTS,
        music_upload_before_selector=True,
        music_requires_upload_ack=True,
        supports_music_color=True,
        physical_ic_count=30,
        whole_device_mask=0x7FFF,
        segment_count=15,
        segment_group_size=3,
        supports_segment_writes=True,
        supports_segment_brightness=True,
        supports_segment_color_temperature=True,
        connection_idle_timeout=3.0,
        scene_catalogue_sku="H617C",
        advanced_scene_carrier=(29884, 41599),
        advanced_diy_selector=402,
        diy_requires_upload_ack=True,
        boolean_controls=frozenset({"gradual"}),
        effect_readback="diy_code_only",
    ),
    "H617F": replace(
        _H617A_PROFILE,
        name="H617F LED Strip",
        support_quality=SupportQuality.SUPPORTED,
        command_grammar="H617A",
        status_grammar="H617A",
        effect_grammar="H617A",
        scene_catalogue_sku="H617F",
    ),
    "H6076": _H6076_MUSIC_PROFILE,
    "H6102": ModelProfile(
        "H6102 LED Strip",
        support_quality=SupportQuality.SUPPORTED,
        command_grammar="H617A",
        status_grammar="H6102",
        profile_identity_fields=frozenset({"fw_version", "hw_version"}),
        colour_mode_query_selector=1,
        static_readback_kelvin=True,
        static_readback_zero_kelvin_is_rgb=True,
        static_readback_gradual=True,
        effect_grammar="H617A",
        read_domains=frozenset(
            {
                ReadDomain.POWER,
                ReadDomain.BRIGHTNESS,
                ReadDomain.COLOUR_MODE,
                ReadDomain.FIRMWARE,
                ReadDomain.HARDWARE,
                ReadDomain.SEGMENTS,
            }
        ),
        setup_required_read_domains=frozenset({ReadDomain.POWER, ReadDomain.BRIGHTNESS, ReadDomain.COLOUR_MODE}),
        supports_rgb=True,
        supports_color_temperature=True,
        supports_custom_effects=True,
        supports_scenes=True,
        supports_advanced_effects=True,
        supports_multi_layered_effects=True,
        music_modes=(
            "energetic",
            "rhythm",
            "spectrum",
            "rolling",
            "separation",
            "hopping",
            "piano_keys",
            "fountain",
            "day_and_night",
            "bloom",
            "shiny",
        ),
        music_variants=H6102_MUSIC_VARIANTS,
        physical_ic_count=60,
        supports_music_color=True,
        whole_device_mask=0x7FFF,
        segment_count=15,
        segment_group_size=3,
        supports_segment_writes=True,
        supports_segment_brightness=True,
        supports_segment_color_temperature=True,
        effect_readback="diy_code_only",
        advanced_diy_selector=402,
        diy_requires_upload_ack=True,
        music_upload_before_selector=True,
        music_requires_upload_ack=True,
        boolean_controls=frozenset({"gradual", "limit"}),
        connection_idle_timeout=3.0,
        scene_catalogue_sku="H6102",
    ),
    "H6125": ModelProfile(
        "H6125 LED Strip",
        support_quality=SupportQuality.EXPERIMENTAL,
        command_grammar="H617A",
        command_ack_grammar="H6125",
        status_grammar="H6125",
        profile_identity_fields=frozenset({"fw_version", "hw_version"}),
        effect_grammar="H617A",
        # Static replies carry the SubModeColorV2 Kelvin field, as on H6102.
        static_readback_kelvin=True,
        static_readback_zero_kelvin_is_rgb=True,
        static_readback_gradual=True,
        colour_mode_query_selector=1,
        read_domains=frozenset(
            {
                ReadDomain.POWER,
                ReadDomain.BRIGHTNESS,
                ReadDomain.COLOUR_MODE,
                ReadDomain.FIRMWARE,
                ReadDomain.HARDWARE,
                ReadDomain.SEGMENTS,
            }
        ),
        setup_required_read_domains=frozenset({ReadDomain.POWER, ReadDomain.BRIGHTNESS, ReadDomain.COLOUR_MODE}),
        supports_rgb=True,
        supports_color_temperature=True,
        supports_custom_effects=True,
        supports_scenes=True,
        supports_advanced_effects=True,
        supports_multi_layered_effects=True,
        music_modes=(
            "energetic",
            "rhythm",
            "spectrum",
            "rolling",
            "separation",
            "hopping",
            "piano_keys",
            "fountain",
            "day_and_night",
            "bloom",
            "shiny",
        ),
        music_variants=H6125_MUSIC_VARIANTS,
        supports_music_color=True,
        # Exact-SKU declared geometry, separate from connection-scoped measurements.
        physical_ic_count=50,
        whole_device_mask=0x7FFF,
        segment_count=15,
        segment_group_size=3,
        supports_segment_writes=True,
        supports_segment_brightness=True,
        supports_segment_color_temperature=True,
        connection_idle_timeout=3.0,
        scene_catalogue_sku="H6125",
        local_scenes=((249, "Work"),),
        effect_readback="diy_code_only",
        # The app writes the latest Type04 upload through this slot on the pact-1 route.
        a1_diy_selector=0xFE,
        advanced_diy_selector=402,
        # MultipleController4Music uploads the companion before the selector and waits for its acknowledgement.
        music_upload_before_selector=True,
        music_requires_upload_ack=True,
        diy_requires_upload_ack=True,
        boolean_controls=frozenset({"gradual"}),
    ),
    "H7020": ModelProfile(
        "H7020 Outdoor String Lights",
        support_quality=SupportQuality.SUPPORTED,
        command_grammar="H7020",
        status_grammar="H7020",
        colour_mode_query_selector=1,
        effect_grammar="H617A",
        music_grammar="H7020",
        command_operations=frozenset(
            {"power", "brightness", "static", "configured_strings", "scene", "diy", "music", "effect_upload"}
        ),
        read_domains=frozenset(
            {
                ReadDomain.POWER,
                ReadDomain.BRIGHTNESS,
                ReadDomain.COLOUR_MODE,
                ReadDomain.FIRMWARE,
                ReadDomain.HARDWARE,
                ReadDomain.CONFIGURED_STRINGS,
                ReadDomain.SEGMENTS,
            }
        ),
        setup_required_read_domains=frozenset({ReadDomain.POWER}),
        supports_rgb=True,
        supports_color_temperature=True,
        min_color_temp_kelvin=2000,
        max_color_temp_kelvin=9000,
        kelvin_direct_rgb=(255, 255, 255),
        whole_device_mask=0x3FFFFFFF,
        segment_count=30,
        segment_group_size=3,
        configured_string_counts=(1, 2),
        bulbs_per_string=15,
        segment_colour_mode_ambiguous=True,
        supports_segment_writes=True,
        supports_segment_brightness=True,
        supports_segment_color_temperature=True,
        static_readback_kelvin=True,
        static_readback_zero_kelvin_is_rgb=True,
        boolean_controls=frozenset({"power_off_memory"}),
        supports_custom_effects=True,
        supports_scenes=True,
        supports_multi_layered_effects=True,
        scene_catalogue_sku="H7020",
        diy_requires_upload_ack=True,
        effect_readback="diy_code_only",
        music_modes=("rhythm", "spectrum", "energetic", "rolling"),
        music_variants=H7020_MUSIC_VARIANTS,
        music_sensitivity_min=0,
        music_sensitivity_max=99,
        supports_music_color=True,
        connection_idle_timeout=3.0,
    ),
    "H6179": ModelProfile(
        "H6179 RGB TV Backlight",
        support_quality=SupportQuality.EXPERIMENTAL,
        command_grammar="H6179",
        status_grammar="H6179",
        effect_grammar="H6179",
        read_domains=frozenset(
            {
                ReadDomain.POWER,
                ReadDomain.BRIGHTNESS,
                ReadDomain.MODE,
                ReadDomain.FIRMWARE,
                ReadDomain.HARDWARE,
            }
        ),
        setup_required_read_domains=frozenset(
            {
                ReadDomain.POWER,
                ReadDomain.BRIGHTNESS,
                ReadDomain.MODE,
            }
        ),
        supports_rgb=True,
        supports_color_temperature=True,
        supports_custom_effects=True,
        supports_scenes=True,
        supports_multi_layered_effects=True,
        music_modes=("mode_0", "mode_1"),
        supports_music_color=True,
        static_readback_echoes_color=True,
        static_readback_kelvin=True,
        scene_catalogue_sku="H6179",
        selector_only_scene_bits=8,
        effect_readback="diy_code_only",
    ),
    "H6199": ModelProfile(
        "H6199 DreamView T1",
        support_quality=SupportQuality.SUPPORTED,
        command_grammar="H6199",
        status_grammar="H6199",
        effect_grammar="H6199",
        video_grammar="H6199",
        video_revision_policy="H6199",
        read_domains=frozenset(
            {
                ReadDomain.POWER,
                ReadDomain.BRIGHTNESS,
                ReadDomain.COLOUR_MODE,
                ReadDomain.FIRMWARE,
                ReadDomain.HARDWARE,
                ReadDomain.SUBORDINATE_20,
                ReadDomain.SUBORDINATE_21,
                ReadDomain.DISPLAY_SETTING,
                ReadDomain.RELATIVE_BRIGHTNESS,
                ReadDomain.SEGMENTS,
            }
        ),
        setup_required_read_domains=frozenset(
            {
                ReadDomain.POWER,
                ReadDomain.BRIGHTNESS,
                ReadDomain.COLOUR_MODE,
            }
        ),
        supports_rgb=True,
        supports_color_temperature=True,
        supports_custom_effects=True,
        supports_scenes=True,
        supports_video_mode=True,
        video_modes=("movie", "game"),
        supports_video_capture_region=True,
        supports_video_saturation=True,
        supports_video_sound_effects=True,
        # These independently captured video registers have byte-exact builders.
        supports_white_balance=True,
        supports_white_balance_readback=True,
        video_white_balance_calibration=WHITE_BALANCE_POSITIONS,
        video_brightness_zones=("left", "top", "right", "bottom"),
        supports_relative_brightness=True,
        supports_blank_screen=True,
        music_modes=_H6199_MUSIC_MODES,
        music_variants=(
            MusicVariant(0x05, "H6199 Energetic selector; no fixed colour", supports_fixed_colour=False),
            MusicVariant(0x03, "H6199 captured Rhythm selector style", supports_style=True),
            MusicVariant(0x04, "H6199 owner-qualified Spectrum fixed-colour readback"),
            MusicVariant(0x06, "H6199 owner-qualified Rolling fixed-colour readback"),
        ),
        music_sensitivity_min=0,
        music_sensitivity_max=100,
        supports_music_color=True,
        supports_advanced_effects=True,
        whole_device_mask=0x7FFF,
        # Static readback identifies the mode but exposes rendered colour only through segment
        # queries. Kelvin remains last-known while its RGB companion matches.
        # Fifteen segment bits are independently writable. The aa 40 value 38 is not a segment count.
        segment_count=15,
        segment_group_size=4,
        # Colour and brightness writes are observed through four explicit aa a5 query groups.
        supports_segment_writes=True,
        supports_segment_brightness=True,
        supports_segment_color_temperature=True,
        scene_catalogue_sku="H6199",
        advanced_scene_carrier=(29884, 41599),
        default_effect_families_override=frozenset({EFFECT_FAMILY_VIDEO}),
        effect_readback="scene_selector_for_user_effects",
    ),
    "H7025": ModelProfile(
        "H7025 Outdoor String Lights",
        support_quality=SupportQuality.EXPERIMENTAL,
        command_grammar="H617A",
        status_grammar="H7025",
        effect_grammar="H617A",
        music_grammar="H7025",
        colour_mode_query_selector=1,
        read_domains=frozenset(
            {
                ReadDomain.POWER,
                ReadDomain.BRIGHTNESS,
                ReadDomain.COLOUR_MODE,
                ReadDomain.FIRMWARE,
                ReadDomain.HARDWARE,
                ReadDomain.SEGMENTS,
            }
        ),
        setup_required_read_domains=frozenset({ReadDomain.POWER, ReadDomain.BRIGHTNESS, ReadDomain.COLOUR_MODE}),
        supports_rgb=True,
        supports_color_temperature=True,
        min_color_temp_kelvin=2700,
        max_color_temp_kelvin=6500,
        kelvin_direct_rgb=(255, 255, 255),
        static_readback_kelvin=True,
        static_readback_zero_kelvin_is_rgb=True,
        whole_device_mask=0x7FFF,
        segment_count=15,
        segment_group_size=4,
        segment_colour_mode_ambiguous=True,
        supports_segment_writes=True,
        supports_segment_brightness=True,
        supports_segment_color_temperature=True,
        supports_custom_effects=True,
        supports_scenes=True,
        supports_multi_layered_effects=True,
        scene_catalogue_sku="H7025",
        diy_requires_upload_ack=True,
        effect_readback="diy_code_only",
        connection_idle_timeout=3.0,
        music_modes=(
            "rhythm",
            "sway",
            "flow",
            "star",
            "twinkle",
            "hopping",
            "rolling",
            "day_and_night",
            "piano_keys",
            "separation",
        ),
        music_variants=H7025_MUSIC_VARIANTS,
        music_upload_before_selector=True,
        music_requires_upload_ack=True,
        music_retry_after_upload=False,
        music_params_require_activation=True,
        supports_music_color=True,
    ),
}

BLE_DISCOVERABLE_MODELS = frozenset(MODEL_PROFILES)

UNSUPPORTED_PROFILE = ModelProfile("Unsupported Govee device")


def _h6199_pact1_wire(packet: bytes) -> bytes:
    from .generated_protocol_adapter import h6199_pact1_outbound_transform

    return h6199_pact1_outbound_transform(packet)


H6199_PACT1_PROFILE = ModelProfile(
    "H6199 Pact 1 (legacy RGB)",
    support_quality=SupportQuality.SUPPORTED,
    command_grammar="H6199",
    command_operations=frozenset({"power", "brightness", "static"}),
    status_grammar="H6199",
    read_domains=frozenset({ReadDomain.POWER, ReadDomain.FIRMWARE, ReadDomain.HARDWARE}),
    setup_required_read_domains=frozenset({ReadDomain.POWER}),
    supports_rgb=True,
    whole_device_mask=0x7FFF,
    brightness_wire_range=(20, 254),
    outbound_transform=_h6199_pact1_wire,
)


# Unresolved revisions authorise only the independently shared bootstrap operations.
H6125_POWER_ONLY_PROFILE = ModelProfile(
    "H6125 (power only)",
    command_grammar="H617A",
    command_operations=frozenset({"power"}),
    status_grammar="H6125",
    profile_identity_fields=frozenset({"fw_version", "hw_version"}),
    read_domains=frozenset({ReadDomain.POWER, ReadDomain.FIRMWARE, ReadDomain.HARDWARE}),
    setup_required_read_domains=frozenset({ReadDomain.POWER}),
)


def _h6125_profile(
    pact_type: int | None, pact_code: int | None, firmware: str | None, hardware: str | None
) -> ModelProfile:
    """Resolve independently gated H6125 controls from the controller's full identity."""
    from .firmware_version import FirmwareVersion
    from .generated_protocol_adapter import (
        H6125IntermediateStatusReply,
        H6125LegacyStatusReply,
        h6125_outbound_transform,
    )

    fw, hw = FirmwareVersion.parse(firmware), FirmwareVersion.parse(hardware)
    if fw is None or hw is None:
        return H6125_POWER_ONLY_PROFILE
    hardware_family = hw.identity_number() // 10000
    firmware_family = fw.identity_number() // 10000
    if hardware_family != firmware_family:
        return H6125_POWER_ONLY_PROFILE
    profile = MODEL_PROFILES["H6125"]
    if pact_type == 10 and pact_code in (1, 2, 3):
        bk = hardware is not None and hardware.startswith("2.01.")
        frk = hardware_family == 3 and hardware is not None and not hardware.startswith("3.04.")
        if not (bk or frk):
            return H6125_POWER_ONLY_PROFILE
        expanded_music = fw >= FirmwareVersion((2, 4) if bk else (3, 1))
        return replace(
            profile,
            status_grammar="H6125-modern",
            music_modes=profile.music_modes if expanded_music else profile.music_modes[:4],
            a1_diy_selector=None,
            static_readback_gradual=True,
            supports_segment_color_temperature=True,
            boolean_controls=frozenset({"gradual"}),
        )
    if pact_type != 1 or pact_code not in (1, 2) or hardware_family != 1:
        return H6125_POWER_ONLY_PROFILE
    extended_colour = hw >= FirmwareVersion((1, 0, 3)) and fw >= FirmwareVersion((1, 6))
    original_music = fw < FirmwareVersion((1, 3, 1))
    expanded_music = fw >= FirmwareVersion((1, 7))
    uploaded_scenes = not original_music and (pact_code == 2 or fw >= FirmwareVersion((1, 4)))
    wire_range = (6, 254) if original_music or hw < FirmwareVersion((1, 0, 4)) else (20, 254)
    workflows = frozenset({"native_music", "native_scenes", "single", "multi"})
    if uploaded_scenes:
        workflows |= {"edited_palette_scenes", "layered_scenes", "advanced", "workshop"}
    if extended_colour:
        workflows |= {"native_scenes", "edited_palette_scenes", "layered_scenes", "painted", "advanced", "workshop"}
    return replace(
        profile,
        status_grammar="H6125" if extended_colour else "H6125-legacy" if original_music else "H6125-intermediate",
        effect_workflows=workflows,
        music_modes=profile.music_modes if expanded_music else profile.music_modes[:4],
        music_variants=tuple(
            replace(variant, supports_style=False) if original_music and variant.mode_code == 3 else variant
            for variant in profile.music_variants
        ),
        supports_color_temperature=extended_colour,
        static_readback_kelvin=extended_colour,
        static_readback_zero_kelvin_is_rgb=extended_colour,
        supports_segment_brightness=extended_colour,
        supports_segment_color_temperature=extended_colour,
        segment_group_size=3 if extended_colour else 4,
        supports_scenes=True,
        supports_advanced_effects=uploaded_scenes,
        advanced_diy_selector=profile.advanced_diy_selector if uploaded_scenes else None,
        selector_only_scene_bits=None if uploaded_scenes else 8,
        scene_codes=None
        if uploaded_scenes
        else frozenset(
            int(scene)
            for scene in (
                H6125LegacyStatusReply.SceneMode if original_music else H6125IntermediateStatusReply.SceneMode
            )
        ),
        static_readback_gradual=True,
        boolean_controls=frozenset({"gradual"}),
        brightness_wire_range=wire_range,
        outbound_transform=h6125_outbound_transform(
            wire_range, legacy_colour=not extended_colour, legacy_music=original_music
        ),
    )


def _h6076_profile(pact_type: int | None, pact_code: int | None, firmware: str | None) -> ModelProfile:
    """Resolve H6076 music modes by software version and Kelvin floor by Pact type."""
    from .firmware_version import FirmwareVersion

    fw = FirmwareVersion.parse(firmware)
    known_pact = (pact_type, pact_code) in {(1, 1), (2, 1)}
    base = (
        _H6076_MUSIC_PROFILE
        if known_pact and fw is not None and fw >= FirmwareVersion((1, 2))
        else replace(_H6076_PROFILE, readback_music_modes=())
        if known_pact and fw is not None
        else _H6076_PROFILE
    )
    if (pact_type, pact_code) == (1, 1):
        return replace(base, min_color_temp_kelvin=2200, readback_min_color_temp_kelvin=None)
    if (pact_type, pact_code) == (2, 1):
        return replace(base, min_color_temp_kelvin=2700, readback_min_color_temp_kelvin=None)
    return replace(base, min_color_temp_kelvin=2700, readback_min_color_temp_kelvin=2200)


def device_profile(
    model: str,
    pact_type: int | None,
    pact_code: int | None,
    *,
    firmware: str | None = None,
    hardware: str | None = None,
) -> ModelProfile:
    """Resolve exact-product capabilities from evidenced revision context."""
    if model == "H7020":
        profile = get_profile(model)
        if (pact_type, pact_code) in {(1, 1), (2, 1)}:
            return profile
        return replace(
            profile,
            command_operations=frozenset({"power", "brightness"}),
            read_domains=frozenset({ReadDomain.POWER, ReadDomain.BRIGHTNESS, ReadDomain.FIRMWARE, ReadDomain.HARDWARE}),
            supports_rgb=False,
            supports_color_temperature=False,
            supports_segment_writes=False,
            supports_segment_brightness=False,
            supports_segment_color_temperature=False,
            supports_custom_effects=False,
            supports_scenes=False,
            supports_multi_layered_effects=False,
            music_modes=(),
            music_variants=(),
            boolean_controls=frozenset(),
            configured_string_counts=(),
        )
    if model in {"H60A1", "H60A6"}:
        from .firmware_version import FirmwareVersion

        profile = get_profile(model)
        if model == "H60A6" and not (
            (pact_type, pact_code) in {(1, 1), (1, 2), (1, 3)}
            or (pact_type, pact_code, hardware, firmware) == (None, None, "1.04.03", "1.00.41")
        ):
            profile = replace(profile, boolean_controls=frozenset(), supports_power_on_behaviour=False)
        if model == "H60A6" and (pact_type, pact_code) == (1, 1):
            from .generated_protocol_adapter import h60a6_legacy_outbound_transform

            return replace(
                profile,
                segment_count=1,
                whole_device_mask=1,
                supports_rgb=True,
                supports_color_temperature=True,
                kelvin_direct_rgb=(255, 255, 255),
                outbound_transform=h60a6_legacy_outbound_transform,
            )
        hw = FirmwareVersion.parse(hardware)
        # Android KelvinConfig.S2: HW >=1.04.03 uses the 2700 K table;
        # older hardware uses 2200 K. Unknown retains conservative bounds.
        if model == "H60A1" and hw is not None and hw.identity_number() < 10403:
            profile = replace(profile, min_color_temp_kelvin=2200)
        # The owner tuple qualifies absent Pact metadata, never a contradictory topology.
        segmented = (
            ((pact_type, pact_code) in {(1, 1), (2, 1)})
            if model == "H60A1"
            else (pact_type == 1 and type(pact_code) is int and pact_code >= 2)
        )
        captured_firmware = "1.02.20" if model == "H60A1" else "1.00.41"
        if (pact_type, pact_code) == (None, None):
            segmented = (hardware, firmware) == ("1.04.03", captured_firmware)
        if segmented:
            segmented_kelvin = model == "H60A6" and (
                (pact_type == 1 and type(pact_code) is int and pact_code >= 3)
                or (hardware, firmware) == ("1.04.03", "1.00.41")
            )
            return replace(
                profile,
                supports_rgb=True,
                supports_color_temperature=True,
                supports_segment_writes=True,
                supports_segment_color_temperature=segmented_kelvin,
                read_domains=profile.read_domains | {ReadDomain.SEGMENTS},
            )
        return profile
    if model == "H6199" and (pact_type, pact_code) == (1, 1):
        return H6199_PACT1_PROFILE
    if model == "H6076":
        return _h6076_profile(pact_type, pact_code, firmware)
    if model == "H6125":
        return _h6125_profile(pact_type, pact_code, firmware, hardware)
    if model == "H6102":
        from .h6102_capabilities import resolve_h6102_capabilities

        return resolve_h6102_capabilities(
            firmware,
            "ble" if firmware is not None else None,
            hardware=hardware,
            pact_type=pact_type,
            pact_code=pact_code,
        ).profile
    return get_profile(model)


def resolve_model(model: str) -> str | None:
    candidate = model.strip().upper()
    return candidate if candidate in MODEL_PROFILES else None


def model_from_ble_name(name: str) -> str | None:
    match = _BLE_MODEL_PATTERN.search(name)
    if match is None:
        return None
    raw = next(group for group in match.groups() if group is not None)
    model = resolve_model(raw if len(raw) == 5 else f"H{raw}")
    return model if model in BLE_DISCOVERABLE_MODELS else None


def protocol_model(model: str) -> str | None:
    """Resolve legacy runtime policy identity, not effect-grammar compatibility."""
    resolved = resolve_model(model)
    return "H617A" if resolved in {"H617A", "H617C", "H617E", "H617F"} else resolved


def get_profile(model: str) -> ModelProfile:
    resolved = resolve_model(model)
    return MODEL_PROFILES[resolved] if resolved is not None else UNSUPPORTED_PROFILE


def supported_effect_families(model: str) -> frozenset[str]:
    profile = get_profile(model)
    families: set[str] = set()
    if profile.supports_scenes:
        families.add(EFFECT_FAMILY_SCENES)
    if profile.supports_music_mode:
        families.add(EFFECT_FAMILY_MUSIC)
    if profile.supports_video_mode:
        families.add(EFFECT_FAMILY_VIDEO)
    return frozenset(families)


def supported_effect_categories(model: str, *, profile: ModelProfile | None = None) -> tuple[str, ...]:
    profile = get_profile(model) if profile is None else profile
    categories: set[str] = set()
    if profile.supports_custom_effects:
        categories.add(EFFECT_CATEGORY_EFFECTS)
    if profile.supports_scenes:
        categories.add(EFFECT_CATEGORY_SCENES)
    if profile.supports_video_mode:
        categories.add(EFFECT_CATEGORY_VIDEO)
    if profile.supports_music_mode:
        categories.add(EFFECT_CATEGORY_REACTIVE)
    if profile.supports_multi_layered_effects:
        categories.add(EFFECT_CATEGORY_MULTI_LAYERED)
    if profile.supports_advanced_effects:
        categories.add(EFFECT_CATEGORY_ADVANCED)
    return tuple(category for category in EFFECT_CATEGORIES if category in categories)


def default_effect_categories(model: str) -> tuple[str, ...]:
    return supported_effect_categories(model)


def effect_categories_from_options(model: str, options: Mapping[str, Any]) -> frozenset[str]:
    selected = options.get(CONF_EFFECT_CATEGORIES)
    if not isinstance(selected, list | tuple | set | frozenset):
        return frozenset(default_effect_categories(model))
    return frozenset(str(value) for value in selected) & frozenset(supported_effect_categories(model))


def prefix_effect_names_from_options(options: Mapping[str, Any]) -> bool:
    return options.get(CONF_PREFIX_EFFECT_NAMES) is True


def always_include_custom_effects_from_options(options: Mapping[str, Any]) -> bool:
    return options.get(CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS) is True


def effect_families_from_categories(categories: frozenset[str]) -> frozenset[str]:
    families: set[str] = set()
    if EFFECT_CATEGORY_SCENES in categories:
        families.add(EFFECT_FAMILY_SCENES)
    if EFFECT_CATEGORY_REACTIVE in categories:
        families.add(EFFECT_FAMILY_MUSIC)
    if EFFECT_CATEGORY_VIDEO in categories:
        families.add(EFFECT_FAMILY_VIDEO)
    return frozenset(families)


def effect_category_for_content_kind(content_kind: str) -> str | None:
    return next(
        (category for category, kinds in EFFECT_CATEGORY_CONTENT_KINDS.items() if content_kind in kinds),
        None,
    )


def default_effect_families(model: str) -> frozenset[str]:
    profile = get_profile(model)
    supported = supported_effect_families(model)
    requested = profile.default_effect_families_override
    return supported if requested is None else requested & supported


def effect_families_from_options(model: str, options: Mapping[str, Any]) -> frozenset[str]:
    if CONF_EFFECT_CATEGORIES in options:
        return effect_families_from_categories(effect_categories_from_options(model, options))
    selected = options.get(CONF_EFFECT_FAMILIES)
    if not isinstance(selected, list | tuple | set | frozenset):
        return default_effect_families(model)
    return frozenset(str(value) for value in selected) & supported_effect_families(model)
