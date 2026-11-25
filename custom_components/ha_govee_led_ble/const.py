"""Constants for HA Govee LED BLE."""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from math import ceil
from typing import Any

from .coordinator_identity import DeviceIdentitySource
from .firmware_version import FirmwareVersion
from .h6199_calibration import WHITE_BALANCE_POSITIONS
from .music_semantics import (
    H1A42_MUSIC_VARIANTS,
    H1AB2_MUSIC_VARIANTS,
    H60B0_MUSIC_VARIANTS,
    H60B2_MUSIC_VARIANTS,
    H61E5_MUSIC_VARIANTS,
    H61F5_MUSIC_VARIANTS,
    H66A0_MUSIC_VARIANTS,
    H617A_MUSIC_VARIANTS,
    H617C_MUSIC_VARIANTS,
    H617E_MUSIC_VARIANTS,
    H618A_MUSIC_VARIANTS,
    H619A_MUSIC_VARIANTS,
    H705A_MUSIC_VARIANTS,
    H1771_MUSIC_VARIANTS,
    H6022_MUSIC_VARIANTS,
    H6046_MUSIC_VARIANTS,
    H6053_MUSIC_VARIANTS,
    H6072_LEGACY_MUSIC_VARIANTS,
    H6072_MUSIC_VARIANTS,
    H6076_LEGACY_MUSIC_VARIANTS,
    H6076_MUSIC_VARIANTS,
    H6097_MUSIC_VARIANTS,
    H6099_MUSIC_VARIANTS,
    H6102_MUSIC_VARIANTS,
    H6117_MUSIC_VARIANTS,
    H6125_MUSIC_VARIANTS,
    H6127_MUSIC_VARIANTS,
    H6139_MUSIC_VARIANTS,
    H6159_MUSIC_VARIANTS,
    H6181_MUSIC_VARIANTS,
    H6182_MUSIC_VARIANTS,
    H7020_MUSIC_VARIANTS,
    H7025_MUSIC_VARIANTS,
    MusicVariant,
    h607c_music_variants,
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
CONF_REGISTER_EFFECT_STUDIO = "register_effect_studio"
CONF_SHOW_EXPERIMENTAL_FEEDBACK = "show_experimental_feedback"
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
    EFFECT_CATEGORY_EFFECTS: frozenset(
        {"static_rgb", "h617a_painted", "h617a_single", "h6179_single_diy", "palette_diy"}
    ),
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


class BrightnessEvidence(StrEnum):
    DEFAULT = "default"
    RESTORED = "restored"
    RETAINED = "retained"
    OBSERVED = "observed"
    DELIVERED = "delivered"
    PENDING = "pending"
    UNKNOWN = "unknown"

    @property
    def recovery_qualified(self) -> bool:
        return self in {BrightnessEvidence.OBSERVED, BrightnessEvidence.DELIVERED}

    @property
    def baseline_qualified(self) -> bool:
        return self in {
            BrightnessEvidence.DEFAULT,
            BrightnessEvidence.OBSERVED,
            BrightnessEvidence.DELIVERED,
        }


class ReadDomain(StrEnum):
    POWER = "power"
    BRIGHTNESS = "brightness"
    COLOUR_MODE = "colour_mode"
    MODE = "mode"
    FIRMWARE = "firmware"
    HARDWARE = "hardware"
    PACT = "pact"
    SUBORDINATE_20 = "subordinate_20"
    SUBORDINATE_21 = "subordinate_21"
    WIRELESS_FIRMWARE = "wireless_firmware"
    WIRELESS_HARDWARE = "wireless_hardware"
    DISPLAY_SETTING = "display_setting"
    RELATIVE_BRIGHTNESS = "relative_brightness"
    SEGMENTS = "segments"
    CONFIGURED_STRINGS = "configured_strings"
    PHYSICAL_IC_COUNT = "physical_ic_count"
    INSTALLATION_DIRECTION = "installation_direction"
    CAMERA_HEALTH = "camera_health"
    LOW_BLUE_LIGHT = "low_blue_light"
    OTHER = "other"


class LegacyEffectSelectorDomain(StrEnum):
    DIY = "diy"
    SCENE = "scene"


class VideoRevisionPolicy(StrEnum):
    QUALIFIED_CAMERA = "qualified_camera"


@dataclass(frozen=True, slots=True)
class ConfiguredIdentityOption:
    value: str
    label: str
    pact_type: int
    pact_code: int


@dataclass(frozen=True, slots=True)
class ConfiguredIdentityPolicy:
    step_id: str
    firmware_key: str
    hardware_key: str
    pact_key: str
    pact_options: tuple[ConfiguredIdentityOption, ...]

    @property
    def keys(self) -> frozenset[str]:
        return frozenset({self.firmware_key, self.hardware_key, self.pact_key})

    @property
    def pact_by_value(self) -> dict[str, tuple[int, int]]:
        return {option.value: (option.pact_type, option.pact_code) for option in self.pact_options}


@dataclass(frozen=True, slots=True)
class CameraControlPolicy:
    identity_fields: tuple[str, ...]
    qualified_versions: tuple[int, ...]
    qualified_pact: tuple[int, int]
    entity_suffixes: frozenset[str]


_IDENTITY_READ_DOMAINS = frozenset(
    {
        ReadDomain.FIRMWARE,
        ReadDomain.HARDWARE,
        ReadDomain.SUBORDINATE_20,
        ReadDomain.SUBORDINATE_21,
        ReadDomain.WIRELESS_FIRMWARE,
        ReadDomain.WIRELESS_HARDWARE,
        ReadDomain.PHYSICAL_IC_COUNT,
    }
)

# Seconds a connection stays open after the last command, for single bulbs and for everything else that opts in.
IDLE_TIMEOUT_BULB = 1.5
IDLE_TIMEOUT_STANDARD = 3.0

# Longest wait for a request's reply before the next outbound frame; replies normally arrive within 100 ms.
REPLY_PACING_TIMEOUT = 0.5

# Every colour temperature is a 100 K step of the shared companion-colour table.
KELVIN_STEP = 100
KELVIN_RANGE_2000_9000 = (2000, 9000)
KELVIN_RANGE_2200_6500 = (2200, 6500)
KELVIN_RANGE_2700_6500 = (2700, 6500)
KELVIN_RANGE_1000_10000 = (1000, 10000)

_GRAMMAR_TRAITS: Mapping[str, frozenset[str]] = {
    "H1771": frozenset(
        {
            "bulk_identity",
            "bulk_mode_reconciliation",
            "bulk_segments",
            "bulk_custom_query",
            "bulk_settings",
            "common_static",
            "custom_power_body",
            "display_music",
            "multi_native_music",
            "music_upload_ack",
            "native_music_status",
            "native_sources",
            "power_on_custom",
        }
    ),
    "H600A": frozenset({"whole_bulb_static", "whole_bulb_music"}),
    "H601C": frozenset({"whole_bulb_static", "whole_bulb_music"}),
    "H6022": frozenset({"opaque_scene_grammar"}),
    "H6046": frozenset(
        {
            "bar_sources",
            "display_static",
            "display_music",
            "h617a_workshop_selector",
            "mode_music",
            "music_selector_bar_parameters",
            "paired_bar_settings",
            "segment_query_tail",
            "setting_readback_separate",
        }
    ),
    "H6053-legacy": frozenset({"legacy_source_segments", "percent_brightness"}),
    "H605C": frozenset(
        {"music_status_settings", "percent_brightness", "source_only_static", "video_embedded_settings"}
    ),
    "H605C-video": frozenset(
        {"video_embedded_parameters", "video_inline_relative_brightness", "video_status_settings", "video_v3"}
    ),
    "H6072": frozenset(
        {
            "common_boolean_registers",
            "common_static",
            "legacy_music_selector",
            "low_blue_light",
            "mode_music",
            "revision_static",
            "workshop_scene_type",
        }
    ),
    "H6072-legacy": frozenset(
        {
            "common_boolean_registers",
            "common_static",
            "legacy_static",
            "revision_static",
            "segment_query_legacy",
            "workshop_scene_type",
        }
    ),
    "H607C": frozenset(
        {
            "common_static",
            "deferred_native_settings",
            "device_info_status",
            "diy_companion_required",
            "native_music_selector",
            "native_sources",
            "separate_native_setting_read",
            "workshop_scene_type",
        }
    ),
    "H6093": frozenset(
        {
            "projector",
            "projector_audio",
            "projector_status",
            "percent_brightness",
        }
    ),
    "H6099": frozenset(
        {
            "display_controls",
            "colour_mode_byte_selector",
            "display_music",
            "display_static",
            "display_video",
            "installation_direction",
            "music_status_settings",
            "mode_music",
            "video_status_settings",
            "video_sound_type",
            "default_diy_selector_254",
            "fixed_diy_slot",
        }
    ),
    "H60A": frozenset({"bulk_compact", "bulk_music_mode", "bulk_settings"}),
    "H60A6": frozenset({"bulk_settings", "native_sources", "power_on_bulk"}),
    "H60B0": frozenset(
        {
            "bulk_mode_reconciliation",
            "common_static",
            "custom_power_body",
            "display_music",
            "multi_native_music",
            "native_music_selector",
            "native_source_static",
            "native_sources",
            "separate_native_setting_read",
            "source_status",
            "special_static",
            "native_music_status",
        }
    ),
    "H60B2": frozenset(
        {
            "native_music_selector",
            "native_sources",
            "separate_native_setting_read",
            "source_status",
            "zone_notification_v2",
        }
    ),
    "H6076": frozenset({"legacy_music_selector"}),
    "H612A": frozenset({"extended_static", "strip_calibration", "strip_calibration_direct"}),
    "H6179": frozenset(
        {
            "common_boolean_registers",
            "custom_command",
            "custom_mode",
            "custom_status",
            "custom_status_query",
            "mode_music",
            "special_static",
        }
    ),
    "H617A": frozenset(
        {
            "common_boolean_registers",
            "common_music_selector",
            "common_static",
            "generic_native_diy",
            "h617a_workshop_selector",
            "legacy_effects",
            "mode_music",
            "workshop_scene_type",
        }
    ),
    "H6181": frozenset(
        {
            "common_boolean_registers",
            "native_music_selector",
            "dedicated_palette_music",
            "whole_bulb_music",
            "whole_bulb_static",
            "dedicated_a1_diy",
        }
    ),
    "H6199": frozenset(
        {
            "blank_screen_legacy_echo",
            "effect_diy_grammar_mismatch",
            "display_controls",
            "display_music",
            "always_fixed_music_state",
            "display_static",
            "display_video",
            "gradient_status",
            "music_status_settings",
            "mode_music",
            "display_scene_body",
            "exact_palette_diy_activation",
            "video_status_settings",
        }
    ),
    "H6199-Pact1": frozenset({"legacy_segments", "percent_brightness"}),
    "H66A0": frozenset(
        {
            "new_music_omits_colour",
            "new_music_selector",
            "music_status_settings",
            "scaled_music_sensitivity",
            "video_picture_preset",
        }
    ),
    "H66A0-video": frozenset({"video_picture_preset", "video_status_settings", "video_v3"}),
    "H7020": frozenset(
        {
            "common_boolean_registers",
            "common_static",
            "display_music",
            "music_selector_parameters",
            "rhythm_selector_parameter",
            "workshop_scene_type",
        }
    ),
    "H7025": frozenset({"new_music_selector"}),
    "H705A": frozenset({"common_boolean_registers", "common_static", "new_music_selector"}),
    "H8604": frozenset(
        {
            "display_settings",
            "device_info_status",
            "video_device_info_status",
            "native_music_selector",
            "music_status_settings",
            "native_sources",
            "separate_native_setting_read",
            "power_on_query_selector",
            "video_settings",
        }
    ),
    "H1A42": frozenset({"new_music_omits_colour", "new_music_selector", "scaled_music_sensitivity"}),
    "H1AB2": frozenset(
        {
            "new_music_omits_colour",
            "new_music_selector",
            "ordinary_settings",
            "strip_calibration",
            "strip_calibration_restore",
        }
    ),
    "H6097": frozenset(
        {
            "music_status_sensitivity",
            "new_music_omits_colour",
            "new_music_selector",
            "ordinary_settings",
            "power_on_query_selector",
        }
    ),
    "H61E5": frozenset({"new_music_selector"}),
    "H61F5": frozenset({"extended_static", "new_music_omits_colour", "new_music_selector", "scaled_music_sensitivity"}),
}


def grammar_traits(grammar: str | None) -> frozenset[str]:
    return frozenset() if grammar is None else _GRAMMAR_TRAITS.get(grammar, frozenset())


NATIVE_ZONE_CONTROLS = (
    "panel_enabled",
    "ring_enabled",
    "left_bar_enabled",
    "right_bar_enabled",
    "pole_enabled",
    "base_enabled",
    "source_0_enabled",
    "source_1_enabled",
    "top_enabled",
    "middle_enabled",
    "side_enabled",
    "bottom_enabled",
)
PROJECTOR_SOURCE_CONTROLS = (
    "aurora_enabled",
    "coarse_aurora_enabled",
    "fine_aurora_enabled",
    "stars_enabled",
)
H607C_NATIVE_ZONES = (("pole", 8, 144), ("base", 5, 30))


@dataclass(frozen=True)
class VideoFirmwareCondition:
    control: str
    identity_field: str
    minimum: str
    maximum: str | None = None

    def __post_init__(self) -> None:
        if self.control not in {
            "capture_region",
            "saturation",
            "sound_effects",
            "white_balance",
            "video_sensitivity",
            "hdmi_input",
            "color_calibration",
            "color_calibration_red",
            "relative_brightness",
            "whole_relative_brightness",
            "blank_screen",
            "black_border",
        }:
            raise ValueError("unknown video firmware control")
        if self.identity_field not in {"fw_version", "hw_version", "subordinate_20_version", "subordinate_21_version"}:
            raise ValueError("unknown firmware identity field")
        if re.fullmatch(r"[0-9]{1,3}\.[0-9]{2}\.[0-9]{2}", self.minimum) is None:
            raise ValueError("firmware minimum must use major.xx.xx notation")
        if self.maximum is not None and (
            re.fullmatch(r"[0-9]{1,3}\.[0-9]{2}\.[0-9]{2}", self.maximum) is None
            or int(self.maximum.replace(".", "")) < int(self.minimum.replace(".", ""))
        ):
            raise ValueError("firmware maximum must be a bounded major.xx.xx version")


@dataclass(frozen=True)
class LightSource:
    key: str
    control: str
    segments: tuple[int, ...]
    master_brightness: bool = False
    color_modes: frozenset[str] | None = None
    native_control: bool = False
    kelvin_hint_source: str | None = None
    palette_restore: bool = False


@dataclass(frozen=True, slots=True)
class ModelRevisionContext:
    model: str
    pact_type: int | None
    pact_code: int | None
    firmware: str | None = None
    firmware_source: DeviceIdentitySource | None = None
    hardware: str | None = None


@dataclass(frozen=True, slots=True)
class ModelRevisionPolicyRegistration:
    model: str
    policy_id: str


@dataclass(frozen=True)
class ModelProfile:
    name: str
    support_quality: SupportQuality = SupportQuality.EXPERIMENTAL
    confirmation_issue: int | None = None
    requires_legacy_encryption: bool = False
    allows_legacy_plaintext_marker: bool = False
    reconciles_marker_pact: bool = False
    command_grammar: str | None = None
    command_ack_grammar: str | None = None
    # None retains the grammar's shipped operations; a set restricts physical writes.
    command_operations: frozenset[str] | None = None
    status_grammar: str | None = None
    bulk_status_grammar: str | None = None
    setting_grammar: str | None = None
    outbound_transform: Callable[[bytes], bytes] | None = None
    status_query_transform: Callable[[bytes], bytes] | None = None
    static_outbound_transform: Callable[[bytes], bytes] | None = None
    # Device register range for the brightness byte; None means the wire carries percent.
    brightness_wire_range: tuple[int, int] | None = None
    # AA05 selector byte the device accepts for the active-mode query.
    colour_mode_query_selector: int = 0
    # Effect semantics require evidence independent of basic command compatibility.
    effect_grammar: str | None = None
    native_effect_codec: str | None = None
    native_effect_revision: int = 0
    projector_grammar: str | None = None
    projector_control_revision: int | None = None
    # None permits the exact-SKU workflow ceiling; a set narrows it for this device.
    effect_workflows: frozenset[str] | None = None
    video_grammar: str | None = None
    video_control_grammar: str | None = None
    dreamview_grammar: str | None = None
    dreamview_operations: frozenset[str] = frozenset()
    dreamview_reads: frozenset[str] = frozenset()
    dreamview_max_sub_devices: int = 0
    dreamview_requires_group_ack: bool = False
    video_firmware_conditions: tuple[VideoFirmwareCondition, ...] = ()
    video_control_exclusions: tuple[tuple[str, str], ...] = ()
    profile_identity_fields: frozenset[str] = frozenset()
    effect_identity_fields: frozenset[str] = frozenset()
    scene_identity_fields: frozenset[str] = frozenset()
    static_identity_fields: frozenset[str] = frozenset()
    # None retains whole-profile prerequisites for suspended static history.
    static_recovery_identity_fields: frozenset[str] | None = None
    resolve_profile_before_state_init: bool = False
    # Set when Pact alone changes capabilities, so the profile also resolves before hardware/firmware replies arrive.
    profile_pact_dependent: bool = False
    revision_policy: str | None = None
    configured_identity: ConfiguredIdentityPolicy | None = None
    protocol_identity: str | None = None
    # Colour and Kelvin controls are presented before identity resolves, but writes need fresh qualified Pact.
    requires_qualified_identity: bool = False
    requires_pact_confirmation: bool = False
    # Exact-product revision policy, independent of compatible wire grammars.
    video_revision_policy: VideoRevisionPolicy | None = None
    camera_control_policy: CameraControlPolicy | None = None
    diagnostic_light_count: bool = False
    read_domains: frozenset[ReadDomain] = frozenset()
    setup_required_read_domains: frozenset[ReadDomain] = frozenset()
    supports_rgb: bool = False
    main_colour_sources: tuple[str, ...] = ()
    minimum_enabled_sources: int = 0
    maximum_enabled_sources: int | None = None
    exclusive_source_groups: tuple[frozenset[str], ...] = ()
    supports_installation_direction: bool = False
    supports_color_temperature: bool = False
    supports_low_blue_light: bool = False
    color_temp_range: tuple[int, int] | None = None
    # Whole-lamp Kelvin is confirmed from a settled read that must also report colour mode, not just matching colours.
    kelvin_verification_reads_colour_mode: bool = False
    supports_custom_effects: bool = False
    supports_scenes: bool = False
    supports_video_mode: bool = False
    video_modes: tuple[str, ...] = ()
    default_video_parameters: tuple[tuple[str, int | str], ...] = ()
    supports_video_capture_region: bool = False
    supports_video_saturation: bool = False
    video_saturation_min: int = 0
    supports_video_sound_effects: bool = False
    video_softness_min: int = 1
    video_softness_max: int = 100
    supports_video_sensitivity: bool = False
    supports_hdmi_input: bool = False
    hdmi_input_count: int = 0
    supports_hdmi_box_light: bool = False
    hdmi_box_effect_max: int = 10
    video_sensitivity_min: int = 1
    video_sensitivity_max: int = 100
    supports_video_color_calibration: bool = False
    video_color_calibration_min: int = 1
    video_color_calibration_max: int = 100
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
    video_embeds_relative_brightness: bool = False
    supports_whole_relative_brightness: bool = False
    # HA brightness 0 means off on devices whose brightness register has no zero.
    brightness_zero_turns_off: bool = False
    supports_blank_screen: bool = False
    supports_black_border: bool = False
    # Selects the music codebook and selector writer when they differ from command_grammar.
    music_grammar: str | None = None
    music_modes: tuple[str, ...] = ()
    readback_music_modes: tuple[str, ...] = ()
    music_readback_ambiguous: bool = False
    music_variants: tuple[MusicVariant, ...] = ()
    music_upload_before_selector: bool = False
    music_requires_upload_ack: bool = False
    music_retry_after_upload: bool = True
    music_params_require_activation: bool = False
    # Physical IC count is independent of logical segment_count. None means unknown.
    # Declared product geometry: the installed count read from the device (ReadDomain.PHYSICAL_IC_COUNT) overrides it.
    physical_ic_count: int | None = None
    physical_ic_capacity: int | None = None
    segment_count_ic_divisor: int | None = None
    segment_count_ic_round_up: bool = True
    segment_count_capacity: int = 0
    extended_static_grammar: str | None = None
    music_sensitivity_min: int = 0
    music_sensitivity_max: int = 99
    supports_music_color: bool = False
    supports_white_brightness: bool = False
    static_readback_echoes_color: bool = False
    static_readback_kelvin: bool = False
    static_readback_kelvin_suppresses_rgb: bool = False
    static_readback_nonzero_kelvin: bool = False
    static_readback_zero_kelvin_is_rgb: bool = False
    static_readback_gradual: bool = False
    # Overrides the all-segments mask for devices whose addressable mask differs from their segment count.
    whole_device_mask_override: int = 0
    segment_count: int = 0
    native_zones: tuple[tuple[str, int, int], ...] = ()
    light_sources: tuple[LightSource, ...] = ()
    segment_group_size: int = 0
    segment_colour_mode_ambiguous: bool = False
    static_palette_recovery: bool = False
    configured_string_counts: tuple[int, ...] = ()
    bulbs_per_string: int = 0
    configured_string_ic_count: int = 0
    supports_ic_refresh: bool = False
    strip_length_metres: tuple[int, ...] = ()
    strip_ics_per_metre: int = 0
    supports_segment_writes: bool = False
    partition_segment_writes: bool = False
    supports_segment_brightness: bool = False
    supports_segment_color_temperature: bool = False
    # The lamp shows its own warm white rather than the companion colour, so any warm white confirms a Kelvin write.
    kelvin_renders_device_white: bool = False
    connection_idle_timeout: float | None = None
    scene_catalogue_sku: str | None = None
    legacy_scene_catalogue_sku: str | None = None
    selector_only_scene_bits: int | None = None
    # scene_codes limits selector eligibility per revision; local_scenes use scene_id 0, effect_id = selector.
    scene_codes: frozenset[int] | None = None
    scene_command_versions: frozenset[int] | None = None
    local_scenes: tuple[tuple[int, str], ...] = ()
    advanced_scene_carrier: tuple[int, int] | None = None
    workshop_scene_selector: int | None = None
    workshop_carriers: tuple[tuple[str, int, int], ...] = ()
    shared_scene_carriers: tuple[tuple[str, int, int], ...] = ()
    workshop_brightness_algorithm: int | None = None
    advanced_diy_selector: int | None = None
    authored_palette_scene_selector: int | None = None
    rgbic_scene_v0: bool | None = None
    # When set, Type04 custom effects upload as A1 command-02 frames led by this selector and activate with it.
    a1_diy_selector: int | None = None
    a1_diy_prefix: int | None = None
    diy_family_variants: tuple[tuple[int, tuple[int, ...]], ...] | None = None
    diy_palette_max: int | None = None
    diy_upload_transport: str | None = None
    native_diy_upload_subtype: int | None = None
    native_diy_selector: int | None = None
    diy_requires_upload_ack: bool = False
    effect_retry_after_upload: bool = True
    packet_write_delay: float = 0.0
    boolean_controls: frozenset[str] = frozenset()
    local_sound_options: tuple[str, ...] = ()
    local_volume_range: tuple[int, int] | None = None
    restarting_boolean_controls: frozenset[str] = frozenset()
    supports_power_on_behaviour: bool = False
    supports_ripple_speed: bool = False
    default_effect_families_override: frozenset[str] | None = None
    effect_readback: str = "none"
    legacy_effect_selector_domains: tuple[tuple[str, LegacyEffectSelectorDomain], ...] = ()
    legacy_custom_to_scene_signatures: tuple[tuple[str, int], ...] = ()

    @property
    def basic_controls_only(self) -> bool:
        return (
            self.command_operations is not None
            and bool(self.command_operations)
            and self.command_operations <= {"power", "brightness"}
        )

    def command_operation_supported(self, operation: str) -> bool:
        return self.command_operations is None or operation in self.command_operations

    def command_grammar_has(self, *traits: str) -> bool:
        return frozenset(traits) <= grammar_traits(self.command_grammar)

    def status_grammar_has(self, *traits: str) -> bool:
        return frozenset(traits) <= grammar_traits(self.status_grammar)

    def effect_grammar_has(self, *traits: str) -> bool:
        return frozenset(traits) <= grammar_traits(self.effect_grammar)

    def setting_grammar_has(self, *traits: str) -> bool:
        return frozenset(traits) <= grammar_traits(self.setting_grammar)

    def music_grammar_has(self, *traits: str) -> bool:
        return frozenset(traits) <= grammar_traits(self.music_grammar or self.command_grammar)

    def bulk_status_grammar_has(self, *traits: str) -> bool:
        return frozenset(traits) <= grammar_traits(self.bulk_status_grammar)

    def video_grammar_has(self, *traits: str) -> bool:
        return frozenset(traits) <= grammar_traits(self.video_grammar)

    def source_control_supported(self, source: LightSource | None) -> bool:
        return (
            source is not None
            and source in self.light_sources
            and (
                source.control in self.boolean_controls
                or self.projector_grammar is not None
                and "projector" in (self.command_operations or ())
                and source.control in PROJECTOR_SOURCE_CONTROLS
            )
        )

    @property
    def whole_device_mask(self) -> int:
        return self.whole_device_mask_override or (1 << self.segment_count) - 1

    @property
    def effect_activation_operations(self) -> frozenset[str]:
        operations = frozenset(
            operation
            for operation, grammars in _EFFECT_ACTIVATION_GRAMMARS.items()
            if self.command_grammar in grammars
            and not (
                operation == "diy"
                and self.command_grammar_has("effect_diy_grammar_mismatch")
                and self.effect_grammar != self.command_grammar
            )
        )
        return operations if self.command_operations is None else operations & self.command_operations

    def __post_init__(self) -> None:
        selector_routes = [route for route, _domain in self.legacy_effect_selector_domains]
        if len(set(selector_routes)) != len(selector_routes):
            raise ValueError("Legacy effect selector routes must be unique")
        if any(
            not isinstance(route, str) or not route or not isinstance(domain, LegacyEffectSelectorDomain)
            for route, domain in self.legacy_effect_selector_domains
        ):
            raise ValueError("Legacy effect selector routes require a route and selector domain")
        if any(
            not isinstance(route, str) or not route or type(selector) is not int or not 0 <= selector <= 65535
            for route, selector in self.legacy_custom_to_scene_signatures
        ):
            raise ValueError("Legacy signature migrations require a route and unsigned selector")
        if self.color_temp_range is not None:
            if (
                not isinstance(self.color_temp_range, tuple)
                or len(self.color_temp_range) != 2
                or any(type(value) is not int for value in self.color_temp_range)
            ):
                raise ValueError("Kelvin range must contain two integer bounds")
            low, high = self.color_temp_range
            if not 1000 <= low < high <= 10000 or low % KELVIN_STEP or high % KELVIN_STEP:
                raise ValueError("Kelvin range must lie on the supported companion-colour grid")
        if self.requires_pact_confirmation and not (self.requires_qualified_identity and self.profile_pact_dependent):
            raise ValueError("Pact confirmation requires identity-qualified, Pact-dependent controls")
        if (
            len({source.key for source in self.light_sources}) != len(self.light_sources)
            or len({source.control for source in self.light_sources}) != len(self.light_sources)
            or sum(bool(source.master_brightness) for source in self.light_sources) > 1
            or any(
                not source.key
                or source.control not in (*NATIVE_ZONE_CONTROLS, *PROJECTOR_SOURCE_CONTROLS)
                or type(source.master_brightness) is not bool
                or type(source.native_control) is not bool
                or type(source.palette_restore) is not bool
                or source.palette_restore
                and not source.segments
                or source.kelvin_hint_source is not None
                and (
                    not source.segments
                    or source.kelvin_hint_source == source.key
                    or source.kelvin_hint_source not in {item.key for item in self.light_sources}
                )
                or source.color_modes is not None
                and (not source.color_modes or not source.color_modes <= {"onoff", "brightness", "rgb", "color_temp"})
                or len(set(source.segments)) != len(source.segments)
                or any(type(segment) is not int or segment < 1 for segment in source.segments)
                for source in self.light_sources
            )
        ):
            raise ValueError("light sources require unique keys and controls and positive segment indices")
        if self.color_temp_range is None and (
            self.supports_color_temperature
            or self.supports_segment_color_temperature
            or any(
                source.control in self.boolean_controls and "color_temp" in (source.color_modes or ())
                for source in self.light_sources
            )
        ):
            raise ValueError("colour temperature support requires an explicit Kelvin range")
        if self.partition_segment_writes:
            segments = [segment for source in self.light_sources for segment in source.segments]
            if len(segments) != self.segment_count or set(segments) != set(range(1, self.segment_count + 1)):
                raise ValueError("partitioned sources must cover every segment exactly once")
        if len(set(self.main_colour_sources)) != len(self.main_colour_sources) or not set(self.main_colour_sources) <= {
            source.key for source in self.light_sources
        }:
            raise ValueError("main colour targets require distinct declared sources")
        source_controls = {source.control for source in self.light_sources}
        if (
            type(self.minimum_enabled_sources) is not int
            or not 0 <= self.minimum_enabled_sources <= len(source_controls)
            or self.maximum_enabled_sources is not None
            and (
                type(self.maximum_enabled_sources) is not int
                or not self.minimum_enabled_sources <= self.maximum_enabled_sources <= len(source_controls)
            )
            or any(len(group) < 2 or not group <= source_controls for group in self.exclusive_source_groups)
        ):
            raise ValueError("source power constraints require declared sources and valid limits")
        if self.diy_upload_transport not in {None, "a1_02", "a3", "single"}:
            raise ValueError("unknown DIY upload transport")
        if self.revision_policy is not None and (not isinstance(self.revision_policy, str) or not self.revision_policy):
            raise ValueError("model revision policy must be a non-empty identifier")
        if self.native_diy_upload_subtype is not None and (
            type(self.native_diy_upload_subtype) is not int or not 0 <= self.native_diy_upload_subtype <= 255
        ):
            raise ValueError("Native DIY upload subtype must be an unsigned byte")
        if self.native_diy_selector is not None and (
            type(self.native_diy_selector) is not int or not 0 <= self.native_diy_selector <= 65535
        ):
            raise ValueError("Native DIY selector must be an unsigned 16-bit value")
        if self.a1_diy_prefix is not None and (
            type(self.a1_diy_prefix) is not int
            or not 0 <= self.a1_diy_prefix <= 255
            or self.diy_upload_transport != "a1_02"
            or self.a1_diy_selector is not None
        ):
            raise ValueError("Independent A1 prefix requires a byte and an A1 upload without a fixed selector")
        if not self.restarting_boolean_controls <= self.boolean_controls:
            raise ValueError("restarting settings must be declared boolean controls")
        if self.local_sound_options and (
            len(self.local_sound_options) > 255
            or len(set(self.local_sound_options)) != len(self.local_sound_options)
            or any(not isinstance(option, str) or not option for option in self.local_sound_options)
        ):
            raise ValueError("Local sound options must be unique named byte selectors")
        if (
            self.local_volume_range is not None
            and not 0 <= self.local_volume_range[0] <= self.local_volume_range[1] <= 255
        ):
            raise ValueError("Local volume range must fit the native byte level")
        if not self.boolean_controls <= {
            "gradual",
            "limit",
            "power_off_memory",
            "pairing_prompt",
            "quiet_start",
            "local_sound_enabled",
            "dreamview_laser",
            *NATIVE_ZONE_CONTROLS,
        }:
            raise ValueError("unknown boolean device setting")
        if self.native_zones and (
            len({name for name, _, _ in self.native_zones}) != len(self.native_zones)
            or any(
                not name or type(logical) is not int or logical < 1 or type(physical) is not int or physical < 1
                for name, logical, physical in self.native_zones
            )
            or sum(logical for _, logical, _ in self.native_zones) != self.segment_count
        ):
            raise ValueError("native zones must partition logical segments with independent positive physical budgets")
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
        if self.workshop_scene_selector is not None and (
            type(self.workshop_scene_selector) is not int or not 0 <= self.workshop_scene_selector <= 65535
        ):
            raise ValueError("Workshop scene selector must be an unsigned 16-bit value")
        for carriers in (self.workshop_carriers, self.shared_scene_carriers):
            if len({carrier for carrier, _, _ in carriers}) != len(carriers) or any(
                carrier not in {"rgb", "rgbic_v1", "rgbic_v2"}
                or type(subtype) is not int
                or not 0 <= subtype <= 255
                or type(selector) is not int
                or not 0 <= selector <= 65535
                for carrier, subtype, selector in carriers
            ):
                raise ValueError("Retained scene carriers require distinct formats and unsigned upload/selector values")
        if self.workshop_brightness_algorithm is not None and (
            type(self.workshop_brightness_algorithm) is not int or not 0 <= self.workshop_brightness_algorithm <= 2
        ):
            raise ValueError("Unknown Workshop brightness algorithm")
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
        if self.video_revision_policy is VideoRevisionPolicy.QUALIFIED_CAMERA and self.camera_control_policy is None:
            raise ValueError("qualified video identity requires a camera-control policy")
        if self.video_revision_policy not in (None, VideoRevisionPolicy.QUALIFIED_CAMERA):
            raise ValueError("unknown video revision policy")
        if type(self.video_saturation_min) is not int or not 0 <= self.video_saturation_min <= 100:
            raise ValueError("video saturation minimum must be from 0 to 100")
        if self.supports_hdmi_input and self.hdmi_input_count < 1:
            raise ValueError("HDMI input support requires at least one input")
        if self.supports_hdmi_box_light and self.hdmi_box_effect_max < 0:
            raise ValueError("HDMI box light effect maximum must be non-negative")
        if not 0 <= self.video_softness_min <= self.video_softness_max <= 100:
            raise ValueError("invalid video softness range")
        if not self.setup_required_read_domains <= self.read_domains:
            raise ValueError("setup-required read domains must also be readable")
        if len({(condition.control, condition.identity_field) for condition in self.video_firmware_conditions}) != len(
            self.video_firmware_conditions
        ):
            raise ValueError("duplicate identity condition for a video control")
        controls = {
            "capture_region",
            "saturation",
            "sound_effects",
            "white_balance",
            "relative_brightness",
            "whole_relative_brightness",
            "blank_screen",
            "black_border",
        }
        if any(
            source not in controls or target not in controls or source == target
            for source, target in self.video_control_exclusions
        ):
            raise ValueError("invalid video control exclusion")
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
            or self.supports_video_sensitivity
            or self.supports_hdmi_input
            or self.supports_hdmi_box_light
            or self.supports_video_color_calibration
            or self.supports_white_balance
            or self.supports_relative_brightness
            or self.video_embeds_relative_brightness
            or self.supports_whole_relative_brightness
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
    def min_color_temp_kelvin(self) -> int:
        if self.color_temp_range is None:
            raise ValueError("device has no declared Kelvin range")
        return self.color_temp_range[0]

    @property
    def max_color_temp_kelvin(self) -> int:
        if self.color_temp_range is None:
            raise ValueError("device has no declared Kelvin range")
        return self.color_temp_range[1]

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
    color_temp_range=KELVIN_RANGE_2000_9000,
    revision_policy="h617a",
    protocol_identity="H617A",
    diagnostic_light_count=True,
    support_quality=SupportQuality.SUPPORTED,
    confirmation_issue=443,
    command_grammar="H617A",
    status_grammar="H617A",
    effect_grammar="H617A",
    scene_identity_fields=frozenset({"fw_version", "hw_version"}),
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
    music_variants=tuple(
        replace(
            variant,
            parameters=tuple(
                replace(parameter, max_value=100) if parameter.key == "music_daynight_speed" else parameter
                for parameter in variant.parameters
            ),
        )
        for variant in H617A_MUSIC_VARIANTS
    ),
    music_upload_before_selector=True,
    music_requires_upload_ack=True,
    music_params_require_activation=True,
    supports_music_color=True,
    supports_advanced_effects=True,
    supports_multi_layered_effects=True,
    # H617A and H617E expose fifteen segments through five explicit aa a5 query groups of three.
    # Segment writes ACK normally but do not publish updated groups without those queries.
    segment_count=15,
    segment_group_size=3,
    supports_segment_writes=True,
    # Preserve the existing qualified segment operations independently of RGB writes.
    supports_segment_brightness=True,
    supports_segment_color_temperature=True,
    physical_ic_count=15,
    rgbic_scene_v0=False,
    scene_command_versions=frozenset({0, 1}),
    diy_requires_upload_ack=True,
    effect_retry_after_upload=False,
    music_retry_after_upload=False,
    connection_idle_timeout=IDLE_TIMEOUT_STANDARD,
    scene_catalogue_sku="H617A",
    advanced_scene_carrier=(1013, 11836),
    effect_readback="diy_code_only",
    legacy_effect_selector_domains=(
        ("h617a_painted", LegacyEffectSelectorDomain.DIY),
        ("h617a_single", LegacyEffectSelectorDomain.DIY),
        ("h617a_multi", LegacyEffectSelectorDomain.DIY),
        ("workshop", LegacyEffectSelectorDomain.SCENE),
        ("shared_scene", LegacyEffectSelectorDomain.SCENE),
    ),
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
    revision_policy="h6076",
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
    color_temp_range=KELVIN_RANGE_2700_6500,
    # Static status can omit Kelvin. Segment rendering confirms plausible
    # white, not an exact Kelvin measurement or losslessly restorable native-white intent.
    kelvin_verification_reads_colour_mode=True,
    segment_colour_mode_ambiguous=True,
    kelvin_renders_device_white=True,
    static_readback_gradual=True,
    physical_ic_count=14,
    segment_count=7,
    segment_group_size=4,
    supports_segment_writes=True,
    supports_segment_brightness=True,
    supports_scenes=True,
    supports_custom_effects=True,
    supports_advanced_effects=True,
    supports_multi_layered_effects=True,
    effect_readback="diy_code_only",
    advanced_diy_selector=402,
    diy_requires_upload_ack=True,
    boolean_controls=frozenset({"gradual"}),
    connection_idle_timeout=IDLE_TIMEOUT_STANDARD,
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
    color_temp_range=KELVIN_RANGE_2200_6500,
    music_modes=_H6076_ALL_MUSIC_MODES,
    readback_music_modes=(),
    music_variants=H6076_MUSIC_VARIANTS,
    # The companion is uploaded before the selector and the lamp acknowledges it.
    music_upload_before_selector=True,
    music_requires_upload_ack=True,
    music_params_require_activation=True,
)

_H6072_PROFILE = ModelProfile(
    "H6072 Floor Lamp",
    support_quality=SupportQuality.SUPPORTED,
    revision_policy="h6072",
    confirmation_issue=486,
    command_grammar="H6072",
    command_ack_grammar="H617A",
    status_grammar="H6072",
    setting_grammar="H6072",
    effect_grammar="H617A",
    effect_workflows=frozenset(
        {
            "native_scenes",
            "native_music",
            "single",
            "multi",
            "painted",
            "edited_palette_scenes",
            "layered_scenes",
            "advanced",
        }
    ),
    command_operations=frozenset({"power", "brightness", "static", "scene", "diy", "music", "effect_upload"}),
    read_domains=frozenset(
        {
            ReadDomain.POWER,
            ReadDomain.BRIGHTNESS,
            ReadDomain.COLOUR_MODE,
            ReadDomain.FIRMWARE,
            ReadDomain.HARDWARE,
            ReadDomain.SEGMENTS,
            ReadDomain.LOW_BLUE_LIGHT,
        }
    ),
    setup_required_read_domains=frozenset({ReadDomain.POWER, ReadDomain.BRIGHTNESS}),
    profile_identity_fields=frozenset({"fw_version", "hw_version"}),
    profile_pact_dependent=True,
    supports_rgb=True,
    supports_color_temperature=True,
    color_temp_range=KELVIN_RANGE_2000_9000,
    kelvin_verification_reads_colour_mode=True,
    static_readback_gradual=True,
    static_readback_nonzero_kelvin=True,
    segment_colour_mode_ambiguous=True,
    kelvin_renders_device_white=True,
    segment_count=8,
    segment_group_size=3,
    physical_ic_count=66,
    supports_segment_writes=True,
    supports_segment_brightness=True,
    supports_scenes=True,
    scene_catalogue_sku="H6072",
    supports_custom_effects=True,
    supports_multi_layered_effects=True,
    supports_advanced_effects=True,
    advanced_diy_selector=402,
    diy_requires_upload_ack=True,
    effect_readback="diy_code_only",
    music_grammar="H6072",
    music_modes=(
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
    ),
    readback_music_modes=(
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
    ),
    music_variants=H6072_MUSIC_VARIANTS,
    supports_music_color=True,
    music_upload_before_selector=True,
    music_requires_upload_ack=True,
    music_params_require_activation=True,
    supports_low_blue_light=True,
    boolean_controls=frozenset({"gradual"}),
    connection_idle_timeout=IDLE_TIMEOUT_STANDARD,
)


def _h6181_wire(packet: bytes) -> bytes:
    from .protocol_transforms import h6181_outbound_transform

    return h6181_outbound_transform(packet)


def _h6181_legacy_colour_wire(packet: bytes) -> bytes:
    from .protocol_transforms import h6181_outbound_transform

    return h6181_outbound_transform(packet, colour_effect=True)


def _projection_power_wire(packet: bytes) -> bytes:
    from .projector_protocol import projection_power_wire

    return projection_power_wire(packet)


MODEL_PROFILES: dict[str, ModelProfile] = {
    "H6093": ModelProfile(
        "H6093 Star Light Projector (Aurora)",
        confirmation_issue=623,
        reconciles_marker_pact=True,
        profile_pact_dependent=True,
        projector_grammar="H6093",
        setting_grammar="H6093",
        local_volume_range=(0, 100),
        boolean_controls=frozenset({"pairing_prompt", "quiet_start", "local_sound_enabled", "dreamview_laser"}),
        local_sound_options=(
            "deep_water",
            "night_sky",
            "lullaby",
            "woodland_birds",
            "summer_insects",
            "light_rain",
            "running_water",
            "ocean_surf",
            "fire",
            "rain_drops",
            "bird_calls",
            "waterside_breeze",
            "wind",
            "calm",
            "upbeat",
            "night_music",
            "clock",
            "train",
        ),
        light_sources=(
            LightSource("aurora", "aurora_enabled", (), color_modes=frozenset({"rgb"}), native_control=True),
            LightSource(
                "coarse_aurora", "coarse_aurora_enabled", (), color_modes=frozenset({"onoff"}), native_control=True
            ),
            LightSource(
                "fine_aurora", "fine_aurora_enabled", (), color_modes=frozenset({"onoff"}), native_control=True
            ),
            LightSource("stars", "stars_enabled", (), color_modes=frozenset({"brightness"}), native_control=True),
        ),
        command_grammar="H600A",
        command_ack_grammar="H600A",
        status_grammar="H6093",
        outbound_transform=_projection_power_wire,
        effect_grammar="H6093",
        native_effect_codec="h6093-projector",
        command_operations=frozenset({"power", "brightness", "static", "scene", "diy", "effect_upload", "projector"}),
        colour_mode_query_selector=1,
        read_domains=frozenset(
            {
                ReadDomain.POWER,
                ReadDomain.BRIGHTNESS,
                ReadDomain.COLOUR_MODE,
                ReadDomain.FIRMWARE,
                ReadDomain.HARDWARE,
                ReadDomain.PACT,
            }
        ),
        setup_required_read_domains=frozenset({ReadDomain.POWER, ReadDomain.BRIGHTNESS}),
        supports_rgb=True,
        supports_color_temperature=True,
        color_temp_range=KELVIN_RANGE_2000_9000,
        static_readback_echoes_color=True,
        static_readback_kelvin=True,
        static_readback_kelvin_suppresses_rgb=True,
        static_readback_zero_kelvin_is_rgb=True,
        supports_custom_effects=True,
        supports_scenes=True,
        supports_advanced_effects=True,
        supports_multi_layered_effects=True,
        diy_requires_upload_ack=True,
        effect_readback="diy_code_only",
        whole_device_mask_override=1,
        connection_idle_timeout=IDLE_TIMEOUT_BULB,
        scene_catalogue_sku="H6093",
        music_modes=(),
        effect_retry_after_upload=False,
    ),
    "H600A": ModelProfile(
        "H600A Smart LED Bulb",
        support_quality=SupportQuality.SUPPORTED,
        confirmation_issue=494,
        command_grammar="H600A",
        command_ack_grammar="H600A",
        status_grammar="H600A",
        effect_grammar="H617A",
        command_operations=frozenset({"power", "brightness", "static", "scene", "diy", "effect_upload"}),
        colour_mode_query_selector=1,
        read_domains=frozenset(
            {ReadDomain.POWER, ReadDomain.BRIGHTNESS, ReadDomain.COLOUR_MODE, ReadDomain.FIRMWARE, ReadDomain.HARDWARE}
        ),
        supports_rgb=True,
        supports_color_temperature=True,
        color_temp_range=KELVIN_RANGE_2700_6500,
        static_readback_echoes_color=True,
        static_readback_kelvin=True,
        static_readback_kelvin_suppresses_rgb=True,
        static_readback_zero_kelvin_is_rgb=True,
        supports_custom_effects=True,
        supports_scenes=True,
        supports_multi_layered_effects=True,
        diy_requires_upload_ack=True,
        effect_readback="diy_code_only",
        whole_device_mask_override=1,
        connection_idle_timeout=IDLE_TIMEOUT_BULB,
        scene_catalogue_sku="H600A",
        music_modes=(),
        effect_retry_after_upload=False,
    ),
    "H6022": ModelProfile(
        "H6022 RGBICWW Table Lamp 2",
        protocol_identity="H617A",
        confirmation_issue=622,
        color_temp_range=KELVIN_RANGE_2700_6500,
        command_grammar="H617A",
        command_ack_grammar="H617A",
        status_grammar="H6022",
        effect_grammar="H6022",
        native_effect_codec="h6022-opaque-scenes",
        colour_mode_query_selector=1,
        static_readback_kelvin=True,
        static_readback_zero_kelvin_is_rgb=True,
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
        physical_ic_count=210,
        segment_count=15,
        segment_group_size=3,
        supports_segment_writes=True,
        supports_segment_brightness=True,
        connection_idle_timeout=IDLE_TIMEOUT_STANDARD,
        scene_catalogue_sku="H6022",
        scene_command_versions=frozenset({0}),
        diy_family_variants=(
            (0, (0,)),
            (5, (0,)),
            (9, (0,)),
            (14, (13, 14)),
            (15, (0,)),
            (82, (13, 14, 57, 58)),
            (83, (0,)),
        ),
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
        music_variants=H6022_MUSIC_VARIANTS,
        music_upload_before_selector=True,
        music_requires_upload_ack=True,
        supports_music_color=True,
        diy_requires_upload_ack=True,
        effect_readback="diy_code_only",
    ),
    "H1771": ModelProfile(
        "H1771 Wallwash Table Lamp",
        support_quality=SupportQuality.SUPPORTED,
        confirmation_issue=558,
        command_grammar="H1771",
        command_ack_grammar="H617A",
        status_grammar="H1771",
        setting_grammar="H1771",
        bulk_status_grammar="H1771",
        effect_grammar="H1771",
        native_effect_codec="h1771",
        music_grammar="H1771",
        effect_workflows=frozenset({"native_scenes", "layered_scenes", "native_music", "single", "multi", "advanced"}),
        command_operations=frozenset({"power", "brightness", "static", "scene", "diy", "music", "effect_upload"}),
        read_domains=frozenset(
            {
                ReadDomain.POWER,
                ReadDomain.BRIGHTNESS,
                ReadDomain.COLOUR_MODE,
                ReadDomain.FIRMWARE,
                ReadDomain.HARDWARE,
                ReadDomain.WIRELESS_FIRMWARE,
                ReadDomain.WIRELESS_HARDWARE,
                ReadDomain.SEGMENTS,
            }
        ),
        setup_required_read_domains=frozenset({ReadDomain.POWER, ReadDomain.BRIGHTNESS}),
        colour_mode_query_selector=1,
        supports_rgb=True,
        supports_color_temperature=True,
        color_temp_range=KELVIN_RANGE_1000_10000,
        static_readback_kelvin=True,
        segment_colour_mode_ambiguous=True,
        static_palette_recovery=True,
        segment_count=4,
        segment_group_size=4,
        physical_ic_count=4,
        supports_segment_writes=True,
        supports_segment_brightness=True,
        supports_segment_color_temperature=True,
        light_sources=(
            LightSource("source_0", "source_0_enabled", ()),
            LightSource("source_1", "source_1_enabled", ()),
        ),
        boolean_controls=frozenset({"source_0_enabled", "source_1_enabled", "gradual"}),
        supports_power_on_behaviour=True,
        supports_scenes=True,
        scene_catalogue_sku="H1771",
        supports_custom_effects=True,
        supports_multi_layered_effects=True,
        supports_advanced_effects=True,
        diy_upload_transport="a3",
        diy_requires_upload_ack=True,
        effect_readback="diy_code_only",
        music_modes=("rhythm", "expansion", "piano", "pulse", "flowing", "rolling"),
        music_variants=H1771_MUSIC_VARIANTS,
        music_upload_before_selector=True,
        music_requires_upload_ack=True,
    ),
    "H6046": ModelProfile(
        "H6046 TV Light Bars",
        color_temp_range=KELVIN_RANGE_2000_9000,
        support_quality=SupportQuality.SUPPORTED,
        confirmation_issue=481,
        command_grammar="H6046",
        command_ack_grammar="H6046",
        command_operations=frozenset(
            {"power", "brightness", "static", "scene", "diy", "music", "effect_upload", "bar_enable", "swap_bars"}
        ),
        status_grammar="H6046",
        setting_grammar="H6046",
        effect_grammar="H6046",
        music_grammar="H6046",
        profile_pact_dependent=True,
        read_domains=frozenset(
            {
                ReadDomain.POWER,
                ReadDomain.BRIGHTNESS,
                ReadDomain.COLOUR_MODE,
                ReadDomain.FIRMWARE,
                ReadDomain.HARDWARE,
                ReadDomain.SUBORDINATE_20,
                ReadDomain.SUBORDINATE_21,
                ReadDomain.SEGMENTS,
            }
        ),
        setup_required_read_domains=frozenset({ReadDomain.POWER, ReadDomain.BRIGHTNESS, ReadDomain.COLOUR_MODE}),
        supports_rgb=True,
        supports_color_temperature=True,
        kelvin_verification_reads_colour_mode=True,
        supports_segment_writes=True,
        supports_segment_brightness=True,
        supports_segment_color_temperature=True,
        segment_colour_mode_ambiguous=True,
        supports_scenes=True,
        supports_custom_effects=True,
        supports_multi_layered_effects=True,
        supports_advanced_effects=True,
        static_readback_kelvin=True,
        static_readback_zero_kelvin_is_rgb=True,
        segment_count=10,
        segment_group_size=4,
        physical_ic_count=10,
        scene_catalogue_sku="H6046",
        advanced_diy_selector=401,
        diy_requires_upload_ack=True,
        effect_retry_after_upload=False,
        effect_readback="diy_code_only",
        boolean_controls=frozenset({"left_bar_enabled", "right_bar_enabled"}),
        light_sources=(
            LightSource("left_bar", "left_bar_enabled", (1, 2, 3, 4, 5)),
            LightSource("right_bar", "right_bar_enabled", (6, 7, 8, 9, 10)),
        ),
        music_modes=("energetic", "rhythm", "impact", "spray", "beat", "torch", "rainbow_ring", "glitter"),
        music_variants=H6046_MUSIC_VARIANTS,
        music_sensitivity_min=0,
        music_sensitivity_max=99,
        supports_music_color=True,
        music_upload_before_selector=True,
        music_requires_upload_ack=True,
        music_retry_after_upload=False,
    ),
    "H6053": ModelProfile(
        "H6053 TV Light Bars",
        color_temp_range=KELVIN_RANGE_2200_6500,
        support_quality=SupportQuality.EXPERIMENTAL,
        confirmation_issue=662,
        command_grammar="H6046",
        command_ack_grammar="H6053",
        command_operations=frozenset(
            {"power", "brightness", "static", "scene", "diy", "music", "effect_upload", "bar_enable", "swap_bars"}
        ),
        status_grammar="H6053",
        setting_grammar="H6046",
        effect_grammar="H6053",
        effect_workflows=frozenset(
            {
                "native_scenes",
                "edited_palette_scenes",
                "layered_scenes",
                "single",
                "multi",
                "native_music",
                "advanced",
                "workshop",
            }
        ),
        music_grammar="H6046",
        profile_identity_fields=frozenset({"fw_version", "hw_version"}),
        static_identity_fields=frozenset({"fw_version", "hw_version"}),
        profile_pact_dependent=True,
        requires_qualified_identity=True,
        requires_pact_confirmation=True,
        colour_mode_query_selector=1,
        read_domains=frozenset(
            {
                ReadDomain.POWER,
                ReadDomain.BRIGHTNESS,
                ReadDomain.COLOUR_MODE,
                ReadDomain.FIRMWARE,
                ReadDomain.HARDWARE,
                ReadDomain.PACT,
                ReadDomain.SEGMENTS,
            }
        ),
        setup_required_read_domains=frozenset({ReadDomain.POWER, ReadDomain.BRIGHTNESS, ReadDomain.COLOUR_MODE}),
        supports_rgb=True,
        supports_color_temperature=True,
        kelvin_verification_reads_colour_mode=True,
        supports_segment_writes=True,
        supports_segment_brightness=True,
        supports_segment_color_temperature=True,
        segment_colour_mode_ambiguous=True,
        supports_scenes=True,
        supports_custom_effects=True,
        supports_multi_layered_effects=True,
        supports_advanced_effects=True,
        static_readback_kelvin=True,
        static_readback_zero_kelvin_is_rgb=True,
        segment_count=12,
        segment_group_size=4,
        scene_catalogue_sku="H6053",
        advanced_diy_selector=402,
        workshop_scene_selector=402,
        workshop_carriers=(("rgb", 1, 198), ("rgbic_v1", 2, 402), ("rgbic_v2", 10, 403)),
        shared_scene_carriers=(("rgb", 1, 199), ("rgbic_v1", 2, 401)),
        diy_upload_transport="a3",
        diy_requires_upload_ack=True,
        effect_retry_after_upload=False,
        effect_readback="diy_code_only",
        boolean_controls=frozenset({"left_bar_enabled", "right_bar_enabled"}),
        light_sources=(
            LightSource("left_bar", "left_bar_enabled", (1, 2, 3, 4, 5, 6)),
            LightSource("right_bar", "right_bar_enabled", (7, 8, 9, 10, 11, 12)),
        ),
        music_modes=("energetic", "rhythm", "impact", "spray", "beat", "torch", "rainbow_ring", "glitter"),
        music_variants=H6053_MUSIC_VARIANTS,
        music_sensitivity_min=0,
        music_sensitivity_max=99,
        supports_music_color=True,
        music_upload_before_selector=True,
        music_requires_upload_ack=True,
        music_retry_after_upload=False,
    ),
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
        color_temp_range=KELVIN_RANGE_2700_6500,
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
        native_effect_codec="h60a6",
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
        light_sources=(
            LightSource("panel", "panel_enabled", (13,), master_brightness=True),
            LightSource("ring", "ring_enabled", tuple(range(1, 13))),
        ),
        supports_power_on_behaviour=True,
        segment_colour_mode_ambiguous=True,
        profile_identity_fields=frozenset({"fw_version", "hw_version"}),
        setup_required_read_domains=frozenset({ReadDomain.POWER}),
        color_temp_range=KELVIN_RANGE_2700_6500,
        segment_count=13,
        segment_group_size=4,
        # Pact 1/1 uses whole-device colour; 1/2+ has thirteen logical segments.
    ),
    "H60B2": ModelProfile(
        "H60B2 Tree Floor Lamp",
        support_quality=SupportQuality.SUPPORTED,
        confirmation_issue=603,
        requires_legacy_encryption=True,
        command_grammar="H617A",
        command_ack_grammar="H617A",
        status_grammar="H60B2",
        setting_grammar="H60B2",
        effect_grammar="H60B2",
        native_effect_codec="h60b2-palette",
        music_grammar="H60B2",
        command_operations=frozenset({"power", "brightness", "static", "scene", "diy", "music", "effect_upload"}),
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
        setup_required_read_domains=frozenset({ReadDomain.POWER, ReadDomain.BRIGHTNESS}),
        colour_mode_query_selector=1,
        supports_rgb=True,
        supports_color_temperature=True,
        color_temp_range=KELVIN_RANGE_2700_6500,
        segment_count=3,
        physical_ic_count=3,
        segment_group_size=3,
        supports_segment_writes=True,
        supports_segment_brightness=True,
        supports_segment_color_temperature=True,
        segment_colour_mode_ambiguous=True,
        light_sources=(
            LightSource("bottom", "bottom_enabled", (1,)),
            LightSource("middle", "middle_enabled", (2,)),
            LightSource("top", "top_enabled", (3,)),
        ),
        boolean_controls=frozenset({"bottom_enabled", "middle_enabled", "top_enabled"}),
        supports_power_on_behaviour=True,
        supports_scenes=True,
        scene_catalogue_sku="H60B2",
        rgbic_scene_v0=False,
        supports_custom_effects=True,
        supports_advanced_effects=True,
        diy_upload_transport="a3",
        diy_requires_upload_ack=True,
        workshop_scene_selector=402,
        advanced_diy_selector=402,
        music_modes=("spectrum", "rhythm", "hopping", "energetic", "firefly", "rolling", "bloom"),
        music_variants=H60B2_MUSIC_VARIANTS,
        music_upload_before_selector=True,
        music_requires_upload_ack=True,
        effect_readback="diy_code_only",
    ),
    "H60B0": ModelProfile(
        "H60B0 Uplighter Floor Lamp",
        support_quality=SupportQuality.SUPPORTED,
        confirmation_issue=566,
        command_grammar="H60B0",
        command_ack_grammar="H60B0",
        status_grammar="H60B0",
        setting_grammar="H60B0",
        effect_grammar="H60B0",
        native_effect_codec="h60b0",
        music_grammar="H60B0",
        profile_pact_dependent=True,
        requires_qualified_identity=True,
        requires_pact_confirmation=True,
        command_operations=frozenset(
            {"power", "brightness", "static", "source_control", "scene", "diy", "music", "effect_upload"}
        ),
        read_domains=frozenset(
            {
                ReadDomain.POWER,
                ReadDomain.BRIGHTNESS,
                ReadDomain.COLOUR_MODE,
                ReadDomain.FIRMWARE,
                ReadDomain.HARDWARE,
                ReadDomain.PACT,
                ReadDomain.SEGMENTS,
            }
        ),
        setup_required_read_domains=frozenset({ReadDomain.POWER, ReadDomain.BRIGHTNESS}),
        supports_rgb=True,
        main_colour_sources=("top", "side", "bottom"),
        minimum_enabled_sources=1,
        maximum_enabled_sources=2,
        supports_color_temperature=True,
        color_temp_range=KELVIN_RANGE_2700_6500,
        supports_segment_writes=True,
        partition_segment_writes=True,
        supports_segment_brightness=True,
        supports_segment_color_temperature=True,
        segment_count=9,
        segment_group_size=4,
        physical_ic_count=9,
        segment_colour_mode_ambiguous=True,
        static_readback_echoes_color=True,
        static_readback_kelvin=True,
        static_readback_kelvin_suppresses_rgb=True,
        static_readback_zero_kelvin_is_rgb=True,
        light_sources=(
            LightSource("top", "top_enabled", (9,)),
            LightSource("side", "side_enabled", tuple(range(1, 9)), kelvin_hint_source="top", palette_restore=True),
            LightSource("bottom", "bottom_enabled", (), color_modes=frozenset({"color_temp"}), native_control=True),
        ),
        boolean_controls=frozenset({"top_enabled", "side_enabled", "bottom_enabled"}),
        supports_ripple_speed=True,
        supports_power_on_behaviour=True,
        supports_scenes=True,
        scene_catalogue_sku="H60B0",
        supports_custom_effects=True,
        supports_multi_layered_effects=True,
        supports_advanced_effects=True,
        diy_upload_transport="a3",
        diy_requires_upload_ack=True,
        effect_readback="diy_code_only",
        music_modes=("spectrum", "hopping", "flow", "firefly", "bloom", "rhythm", "shiny", "combined"),
        music_variants=H60B0_MUSIC_VARIANTS,
        music_upload_before_selector=True,
        music_requires_upload_ack=True,
        music_params_require_activation=True,
    ),
    "H601C": ModelProfile(
        "H601C Recessed Downlight",
        support_quality=SupportQuality.SUPPORTED,
        command_grammar="H601C",
        static_readback_kelvin_suppresses_rgb=True,
        effect_grammar="H617A",
        command_operations=frozenset({"power", "brightness", "static", "scene", "diy", "effect_upload"}),
        colour_mode_query_selector=1,
        supports_rgb=True,
        supports_color_temperature=True,
        color_temp_range=KELVIN_RANGE_2700_6500,
        supports_custom_effects=True,
        supports_scenes=True,
        supports_multi_layered_effects=True,
        whole_device_mask_override=1,
        connection_idle_timeout=IDLE_TIMEOUT_BULB,
        scene_catalogue_sku="H601C",
    ),
    "H6097": ModelProfile(
        "H6097 TV Backlight 3 Lite (40-50 inch)",
        color_temp_range=KELVIN_RANGE_2000_9000,
        support_quality=SupportQuality.SUPPORTED,
        confirmation_issue=445,
        command_grammar="H6099",
        command_ack_grammar="H617A",
        status_grammar="H6097",
        setting_grammar="H6097",
        music_grammar="H6097",
        profile_pact_dependent=True,
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
                "video_settings",
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
                "video_settings",
                "sound",
            }
        ),
        dreamview_max_sub_devices=7,
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
        supports_power_on_behaviour=True,
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
        physical_ic_count=24,
        music_variants=H6097_MUSIC_VARIANTS,
        music_upload_before_selector=True,
        music_requires_upload_ack=True,
        diy_requires_upload_ack=True,
        effect_retry_after_upload=False,
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
        segment_count=14,
        segment_group_size=4,
        segment_colour_mode_ambiguous=True,
        supports_segment_writes=True,
        supports_segment_brightness=True,
        supports_segment_color_temperature=True,
        scene_catalogue_sku="H6097",
        supports_custom_effects=True,
        supports_multi_layered_effects=True,
        default_effect_families_override=frozenset({EFFECT_FAMILY_VIDEO}),
        effect_readback="diy_code_only",
    ),
    "H605C": ModelProfile(
        "H605C Envisual TV Backlight T2",
        color_temp_range=KELVIN_RANGE_2000_9000,
        support_quality=SupportQuality.SUPPORTED,
        confirmation_issue=571,
        command_grammar="H6099",
        status_grammar="H605C",
        setting_grammar="H607C",
        effect_grammar="H617A",
        music_grammar="H6199",
        video_grammar="H605C-video",
        video_control_grammar="H6199",
        dreamview_grammar="H6199",
        dreamview_operations=frozenset(
            {
                "replace_group",
                "delete_group",
                "switch_group",
                "member_brightness",
                "same_brightness",
                "member_connect",
                "saturation",
                "video_settings",
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
                "video_settings",
                "sound",
            }
        ),
        dreamview_max_sub_devices=5,
        dreamview_requires_group_ack=True,
        profile_pact_dependent=True,
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
                ReadDomain.PHYSICAL_IC_COUNT,
                ReadDomain.SEGMENTS,
                ReadDomain.INSTALLATION_DIRECTION,
                ReadDomain.CAMERA_HEALTH,
            }
        ),
        setup_required_read_domains=frozenset({ReadDomain.POWER}),
        supports_rgb=True,
        supports_installation_direction=True,
        supports_color_temperature=True,
        supports_segment_writes=True,
        supports_segment_brightness=True,
        supports_segment_color_temperature=True,
        segment_count=14,
        segment_group_size=4,
        supports_custom_effects=True,
        supports_multi_layered_effects=True,
        supports_advanced_effects=True,
        supports_scenes=True,
        scene_catalogue_sku="H605C",
        advanced_scene_carrier=(29884, 41599),
        workshop_scene_selector=402,
        workshop_brightness_algorithm=1,
        diy_requires_upload_ack=True,
        effect_retry_after_upload=False,
        music_modes=("energetic", "rhythm", "spectrum", "rolling"),
        music_variants=(
            MusicVariant(0x05, "Energetic short selector", supports_fixed_colour=False),
            MusicVariant(0x03, "Rhythm selector with style and colour", supports_style=True),
            MusicVariant(0x04, "Spectrum selector with colour"),
            MusicVariant(0x06, "Rolling selector with colour"),
        ),
        music_sensitivity_max=99,
        supports_music_color=True,
        supports_video_mode=True,
        video_modes=("movie", "game"),
        supports_video_capture_region=True,
        supports_video_saturation=True,
        video_saturation_min=1,
        supports_video_sound_effects=True,
        video_softness_min=0,
        video_softness_max=99,
        supports_white_balance=True,
        supports_white_balance_readback=True,
        video_white_balance_default=13,
        video_white_balance_max=25,
        video_white_balance_calibration=(
            (5, 21),
            (5, 18),
            (6, 18),
            (6, 15),
            (7, 13),
            (7, 10),
            (8, 8),
            (9, 5),
            (10, 8),
            (10, 6),
            (11, 6),
            (12, 7),
            (12, 6),
            (13, 5),
            (13, 3),
            (14, 5),
            (14, 3),
            (15, 4),
            (15, 3),
            (16, 5),
            (16, 4),
            (16, 3),
            (18, 6),
            (18, 4),
            (21, 5),
        ),
        video_brightness_zones=("left", "top", "right", "bottom"),
        supports_relative_brightness=True,
        video_embeds_relative_brightness=True,
        supports_whole_relative_brightness=True,
        video_control_exclusions=(("whole_relative_brightness", "relative_brightness"),),
        video_firmware_conditions=(
            VideoFirmwareCondition("relative_brightness", "fw_version", "1.00.12"),
            VideoFirmwareCondition("relative_brightness", "subordinate_21_version", "1.00.08"),
            VideoFirmwareCondition("whole_relative_brightness", "fw_version", "1.00.09"),
            VideoFirmwareCondition("whole_relative_brightness", "subordinate_21_version", "1.00.04"),
            VideoFirmwareCondition("whole_relative_brightness", "subordinate_20_version", "1.03.30"),
            VideoFirmwareCondition("blank_screen", "subordinate_21_version", "1.00.08"),
        ),
        supports_blank_screen=True,
        boolean_controls=frozenset({"gradual"}),
        default_effect_families_override=frozenset({EFFECT_FAMILY_VIDEO}),
        effect_readback="diy_code_only",
    ),
    "H6099": ModelProfile(
        "H6099 TV Backlight 3 Lite",
        color_temp_range=KELVIN_RANGE_2000_9000,
        support_quality=SupportQuality.SUPPORTED,
        confirmation_issue=446,
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
                "video_settings",
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
                "video_settings",
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
        support_quality=SupportQuality.SUPPORTED,
        confirmation_issue=450,
        command_grammar="H6099",
        status_grammar="H66A0",
        effect_grammar="H6099",
        music_grammar="H66A0",
        video_grammar="H66A0-video",
        video_control_grammar="H6099",
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
                "video_settings",
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
                "video_settings",
                "sound",
            }
        ),
        dreamview_max_sub_devices=10,
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
        segment_count=14,
        segment_group_size=4,
        supports_segment_writes=True,
        supports_segment_brightness=True,
        supports_segment_color_temperature=True,
        kelvin_renders_device_white=True,
        color_temp_range=KELVIN_RANGE_2700_6500,
        kelvin_verification_reads_colour_mode=True,
        segment_colour_mode_ambiguous=True,
        scene_catalogue_sku="H66A0",
        supports_custom_effects=True,
        default_effect_families_override=frozenset({EFFECT_FAMILY_VIDEO}),
        effect_readback="diy_code_only",
    ),
    "H8604": ModelProfile(
        "H8604 Smart AI Sync Box",
        confirmation_issue=688,
        command_grammar="H6099",
        status_grammar="H8604",
        setting_grammar="H8604",
        effect_grammar="H6099",
        music_grammar="H8604",
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
                "video_settings",
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
                "video_settings",
                "sound",
            }
        ),
        dreamview_max_sub_devices=10,
        profile_pact_dependent=True,
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
            }
        ),
        setup_required_read_domains=frozenset({ReadDomain.POWER, ReadDomain.BRIGHTNESS, ReadDomain.COLOUR_MODE}),
        supports_installation_direction=True,
        supports_power_on_behaviour=True,
        supports_rgb=True,
        supports_color_temperature=True,
        color_temp_range=KELVIN_RANGE_2000_9000,
        static_readback_kelvin=True,
        static_readback_gradual=True,
        supports_scenes=True,
        supports_custom_effects=True,
        supports_multi_layered_effects=True,
        supports_advanced_effects=True,
        scene_catalogue_sku="H8604",
        scene_command_versions=frozenset({0, 1}),
        advanced_scene_carrier=(29884, 41599),
        workshop_scene_selector=402,
        workshop_brightness_algorithm=1,
        diy_requires_upload_ack=True,
        effect_retry_after_upload=False,
        music_modes=("energetic", "rhythm", "spectrum", "rolling"),
        music_variants=(
            MusicVariant(0x05, "Energetic short selector", supports_fixed_colour=False),
            MusicVariant(0x03, "Rhythm selector with style and colour", supports_style=True),
            MusicVariant(0x04, "Spectrum selector with colour"),
            MusicVariant(0x06, "Rolling selector with colour"),
        ),
        supports_music_color=True,
        supports_video_mode=True,
        video_modes=("movie",),
        supports_video_capture_region=True,
        supports_video_saturation=True,
        video_saturation_min=1,
        supports_video_sound_effects=True,
        supports_video_sensitivity=True,
        supports_hdmi_input=True,
        hdmi_input_count=4,
        supports_hdmi_box_light=True,
        supports_video_color_calibration=True,
        video_firmware_conditions=(
            VideoFirmwareCondition("color_calibration_red", "subordinate_20_version", "2.02.11"),
            VideoFirmwareCondition("color_calibration_red", "subordinate_21_version", "2.01.11", "2.01.11"),
        ),
        video_softness_min=0,
        video_softness_max=99,
        video_brightness_zones=("left", "top", "right", "bottom"),
        supports_relative_brightness=True,
        supports_blank_screen=True,
        supports_black_border=True,
        physical_ic_count=90,
        segment_count=14,
        segment_group_size=4,
        supports_segment_writes=True,
        supports_segment_brightness=True,
        supports_segment_color_temperature=True,
        boolean_controls=frozenset({"gradual", "left_bar_enabled", "middle_enabled", "right_bar_enabled"}),
        default_effect_families_override=frozenset({EFFECT_FAMILY_VIDEO}),
        effect_readback="diy_code_only",
    ),
    "H1A42": ModelProfile(
        "H1A42 LED Strip Light 2",
        support_quality=SupportQuality.SUPPORTED,
        confirmation_issue=444,
        command_grammar="H617A",
        status_grammar="H1A42",
        effect_grammar="H617A",
        music_grammar="H1A42",
        kelvin_verification_reads_colour_mode=True,
        segment_colour_mode_ambiguous=True,
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
        color_temp_range=KELVIN_RANGE_1000_10000,
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
        segment_count_ic_divisor=1,
        segment_count=5,
        segment_group_size=4,
        supports_segment_writes=True,
        supports_segment_brightness=True,
        supports_segment_color_temperature=True,
        scene_catalogue_sku="H1A42",
        effect_readback="diy_code_only",
        boolean_controls=frozenset({"gradual"}),
    ),
    "H1AB2": ModelProfile(
        "H1AB2 COB Strip Light 2",
        support_quality=SupportQuality.SUPPORTED,
        confirmation_issue=621,
        command_grammar="H617A",
        status_grammar="H1AB2",
        effect_grammar="H1AB2",
        native_effect_codec="h1ab2-accumulation",
        setting_grammar="H1AB2",
        music_grammar="H1AB2",
        kelvin_verification_reads_colour_mode=True,
        segment_colour_mode_ambiguous=True,
        static_palette_recovery=True,
        static_readback_nonzero_kelvin=True,
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
        setup_required_read_domains=frozenset({ReadDomain.POWER, ReadDomain.BRIGHTNESS, ReadDomain.COLOUR_MODE}),
        supports_rgb=True,
        supports_color_temperature=True,
        color_temp_range=KELVIN_RANGE_1000_10000,
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
            "splash",
            "orbit",
            "ripple",
            "spring",
            "meteor",
        ),
        music_variants=H1AB2_MUSIC_VARIANTS,
        music_upload_before_selector=True,
        music_requires_upload_ack=True,
        music_params_require_activation=True,
        supports_music_color=True,
        physical_ic_count=50,
        strip_length_metres=(1, 2, 3, 4, 5),
        strip_ics_per_metre=10,
        segment_count_ic_divisor=1,
        segment_count_capacity=10,
        segment_count=10,
        segment_group_size=4,
        supports_segment_writes=True,
        supports_segment_brightness=True,
        supports_segment_color_temperature=True,
        scene_catalogue_sku="H1AB2",
        rgbic_scene_v0=False,
        scene_command_versions=frozenset({0, 1}),
        advanced_diy_selector=2002,
        workshop_scene_selector=2002,
        diy_requires_upload_ack=True,
        effect_readback="diy_code_only",
        boolean_controls=frozenset({"gradual"}),
        supports_power_on_behaviour=True,
    ),
    "H61E5": ModelProfile(
        "H61E5 COB Strip Light Pro",
        confirmation_issue=731,
        command_grammar="H617A",
        status_grammar="H61F5",
        effect_grammar="H617A",
        music_grammar="H61F5",
        profile_pact_dependent=True,
        kelvin_verification_reads_colour_mode=True,
        segment_colour_mode_ambiguous=True,
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
        color_temp_range=KELVIN_RANGE_2700_6500,
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
        music_variants=H61E5_MUSIC_VARIANTS,
        music_upload_before_selector=True,
        supports_music_color=True,
        supports_advanced_effects=True,
        supports_multi_layered_effects=True,
        effect_workflows=frozenset({"native_scenes", "painted", "single", "multi", "native_music", "advanced"}),
        physical_ic_count=36,
        physical_ic_capacity=36,
        segment_count_ic_divisor=3,
        segment_count_capacity=12,
        segment_count=12,
        segment_group_size=4,
        supports_segment_writes=True,
        supports_segment_brightness=True,
        supports_segment_color_temperature=True,
        scene_catalogue_sku="H61E5",
        effect_readback="diy_code_only",
        boolean_controls=frozenset({"gradual"}),
    ),
    "H61F5": ModelProfile(
        "H61F5 Strip Light 2 Pro",
        support_quality=SupportQuality.SUPPORTED,
        confirmation_issue=449,
        command_grammar="H617A",
        status_grammar="H61F5",
        effect_grammar="H617A",
        music_grammar="H61F5",
        profile_pact_dependent=True,
        kelvin_verification_reads_colour_mode=True,
        segment_colour_mode_ambiguous=True,
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
        color_temp_range=KELVIN_RANGE_2700_6500,
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
            "splash",
            "spring",
            "meteor",
            "ripple",
            "orbit",
        ),
        music_variants=H61F5_MUSIC_VARIANTS,
        music_upload_before_selector=True,
        supports_music_color=True,
        physical_ic_count=50,
        segment_count_ic_divisor=5,
        segment_count_capacity=20,
        extended_static_grammar="H61F5",
        segment_count=10,
        segment_group_size=4,
        supports_segment_writes=True,
        supports_segment_brightness=True,
        supports_segment_color_temperature=True,
        scene_catalogue_sku="H61F5",
        effect_readback="diy_code_only",
        boolean_controls=frozenset({"gradual"}),
    ),
    "H617A": _H617A_PROFILE,
    "H617E": ModelProfile(
        "H617E LED Strip",
        color_temp_range=KELVIN_RANGE_2000_9000,
        support_quality=SupportQuality.SUPPORTED,
        protocol_identity="H617A",
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
        setup_required_read_domains=frozenset({ReadDomain.POWER, ReadDomain.BRIGHTNESS, ReadDomain.COLOUR_MODE}),
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
        music_variants=H617E_MUSIC_VARIANTS,
        music_upload_before_selector=False,
        music_requires_upload_ack=False,
        supports_music_color=True,
        supports_advanced_effects=True,
        supports_multi_layered_effects=True,
        segment_count=15,
        segment_group_size=3,
        supports_segment_writes=True,
        supports_segment_brightness=True,
        connection_idle_timeout=IDLE_TIMEOUT_STANDARD,
        scene_catalogue_sku="H617E",
        legacy_scene_catalogue_sku="H617A",
        advanced_scene_carrier=(29884, 41599),
        effect_readback="diy_code_only",
        legacy_effect_selector_domains=(
            ("h617a_painted", LegacyEffectSelectorDomain.DIY),
            ("h617a_single", LegacyEffectSelectorDomain.DIY),
            ("h617a_multi", LegacyEffectSelectorDomain.DIY),
            ("workshop", LegacyEffectSelectorDomain.SCENE),
            ("shared_scene", LegacyEffectSelectorDomain.SCENE),
        ),
    ),
    "H617C": ModelProfile(
        "H617C LED Strip",
        color_temp_range=KELVIN_RANGE_2000_9000,
        support_quality=SupportQuality.SUPPORTED,
        protocol_identity="H617A",
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
        segment_count=15,
        segment_group_size=3,
        supports_segment_writes=True,
        supports_segment_brightness=True,
        connection_idle_timeout=IDLE_TIMEOUT_STANDARD,
        scene_catalogue_sku="H617C",
        advanced_scene_carrier=(29884, 41599),
        advanced_diy_selector=402,
        diy_requires_upload_ack=True,
        boolean_controls=frozenset({"gradual"}),
        effect_readback="diy_code_only",
    ),
    "H617F": ModelProfile(
        "H617F LED Strip",
        color_temp_range=KELVIN_RANGE_2000_9000,
        support_quality=SupportQuality.SUPPORTED,
        protocol_identity="H617A",
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
        setup_required_read_domains=frozenset({ReadDomain.POWER, ReadDomain.BRIGHTNESS, ReadDomain.COLOUR_MODE}),
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
        segment_count=15,
        segment_group_size=3,
        supports_segment_writes=True,
        supports_segment_brightness=True,
        connection_idle_timeout=IDLE_TIMEOUT_STANDARD,
        scene_catalogue_sku="H617F",
        advanced_scene_carrier=(1013, 11836),
        effect_readback="diy_code_only",
    ),
    "H618A": ModelProfile(
        "H618A RGBIC Strip Lights",
        support_quality=SupportQuality.SUPPORTED,
        confirmation_issue=690,
        command_grammar="H617A",
        command_ack_grammar="H617A",
        status_grammar="H618A",
        effect_grammar="H617A",
        colour_mode_query_selector=1,
        profile_pact_dependent=True,
        profile_identity_fields=frozenset({"fw_version", "hw_version"}),
        scene_identity_fields=frozenset({"fw_version", "hw_version"}),
        static_readback_kelvin=True,
        static_readback_zero_kelvin_is_rgb=True,
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
        color_temp_range=KELVIN_RANGE_2000_9000,
        supports_segment_writes=True,
        supports_segment_brightness=True,
        supports_segment_color_temperature=True,
        physical_ic_count=15,
        segment_count=15,
        segment_group_size=3,
        supports_scenes=True,
        scene_catalogue_sku="H618A",
        rgbic_scene_v0=False,
        scene_command_versions=frozenset({0, 1}),
        supports_custom_effects=True,
        supports_advanced_effects=True,
        supports_multi_layered_effects=True,
        advanced_diy_selector=402,
        diy_requires_upload_ack=True,
        effect_readback="diy_code_only",
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
        music_variants=H618A_MUSIC_VARIANTS,
        music_upload_before_selector=True,
        music_requires_upload_ack=True,
        music_params_require_activation=True,
        supports_music_color=True,
        connection_idle_timeout=IDLE_TIMEOUT_STANDARD,
    ),
    "H6076": _H6076_MUSIC_PROFILE,
    "H6072": _H6072_PROFILE,
    "H607C": ModelProfile(
        "H607C Floor Lamp 2",
        support_quality=SupportQuality.SUPPORTED,
        confirmation_issue=511,
        command_grammar="H607C",
        command_ack_grammar="H607C",
        status_grammar="H607C",
        setting_grammar="H607C",
        effect_grammar="H607C",
        native_effect_codec="h607c-zoned",
        effect_workflows=frozenset({"native_scenes", "layered_scenes", "native_music", "single", "multi", "painted"}),
        command_operations=frozenset({"power", "brightness", "static", "scene", "diy", "music", "effect_upload"}),
        profile_pact_dependent=True,
        requires_qualified_identity=True,
        read_domains=frozenset(
            {ReadDomain.POWER, ReadDomain.BRIGHTNESS, ReadDomain.COLOUR_MODE, ReadDomain.FIRMWARE, ReadDomain.HARDWARE}
        ),
        setup_required_read_domains=frozenset({ReadDomain.POWER, ReadDomain.BRIGHTNESS}),
        brightness_zero_turns_off=True,
        supports_rgb=True,
        supports_color_temperature=True,
        color_temp_range=KELVIN_RANGE_2200_6500,
        kelvin_verification_reads_colour_mode=True,
        segment_count=13,
        native_zones=H607C_NATIVE_ZONES,
        physical_ic_count=H607C_NATIVE_ZONES[0][2],
        supports_segment_writes=True,
        supports_segment_brightness=True,
        segment_colour_mode_ambiguous=True,
        scene_catalogue_sku="H607C",
        supports_scenes=True,
        supports_custom_effects=True,
        supports_multi_layered_effects=True,
        diy_upload_transport="a3",
        diy_requires_upload_ack=True,
        effect_retry_after_upload=False,
        effect_readback="diy_code_only",
        music_grammar="H607C",
        music_modes=(
            "native_115",
            "rhythm",
            "hopping",
            "fusion",
            "shiny",
            "magic",
            "paired",
            "colour_dots",
            "splash",
            "spring",
        ),
        music_variants=h607c_music_variants(H607C_NATIVE_ZONES[0][2], H607C_NATIVE_ZONES[1][2]),
        music_upload_before_selector=True,
        music_requires_upload_ack=True,
        music_retry_after_upload=False,
        music_params_require_activation=True,
        boolean_controls=frozenset({"pole_enabled", "base_enabled", "gradual"}),
        light_sources=(
            LightSource("pole", "pole_enabled", tuple(range(1, 9))),
            LightSource("base", "base_enabled", tuple(range(9, 14))),
        ),
        supports_power_on_behaviour=True,
        dreamview_grammar="H607C",
        dreamview_operations=frozenset(
            {
                "replace_group",
                "switch_group",
                "member_brightness",
                "same_brightness",
                "member_connect",
                "delete_group",
            }
        ),
        dreamview_reads=frozenset({"switch_group", "member_brightness", "same_brightness", "member_connect"}),
        dreamview_max_sub_devices=10,
        dreamview_requires_group_ack=True,
        connection_idle_timeout=IDLE_TIMEOUT_STANDARD,
    ),
    "H6102": ModelProfile(
        "H6102 LED Strip",
        color_temp_range=KELVIN_RANGE_2000_9000,
        support_quality=SupportQuality.SUPPORTED,
        configured_identity=ConfiguredIdentityPolicy(
            step_id="h6102_firmware",
            firmware_key=CONF_H6102_APP_FIRMWARE,
            hardware_key=CONF_H6102_APP_HARDWARE,
            pact_key=CONF_H6102_PACT,
            pact_options=(
                ConfiguredIdentityOption("10/1", "RGBIC Pact 10/1", 10, 1),
                ConfiguredIdentityOption("10/2", "RGBIC Pact 10/2", 10, 2),
                ConfiguredIdentityOption("1/1", "Legacy Pact 1/1", 1, 1),
                ConfiguredIdentityOption("1/2", "Legacy Pact 1/2", 1, 2),
            ),
        ),
        resolve_profile_before_state_init=True,
        brightness_zero_turns_off=True,
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
        segment_count=15,
        segment_group_size=3,
        supports_segment_writes=True,
        supports_segment_brightness=True,
        effect_readback="diy_code_only",
        advanced_diy_selector=402,
        diy_requires_upload_ack=True,
        music_upload_before_selector=True,
        music_requires_upload_ack=True,
        boolean_controls=frozenset({"gradual", "limit"}),
        connection_idle_timeout=IDLE_TIMEOUT_STANDARD,
        scene_catalogue_sku="H6102",
    ),
    "H6117": ModelProfile(
        "H6117 LED Strip",
        color_temp_range=KELVIN_RANGE_2000_9000,
        support_quality=SupportQuality.EXPERIMENTAL,
        confirmation_issue=537,
        command_grammar="H617A",
        command_ack_grammar="H6125",
        status_grammar="H6117",
        profile_identity_fields=frozenset({"fw_version", "hw_version"}),
        profile_pact_dependent=True,
        brightness_zero_turns_off=True,
        colour_mode_query_selector=1,
        static_readback_kelvin=True,
        static_readback_zero_kelvin_is_rgb=True,
        static_readback_gradual=True,
        effect_grammar="H617A",
        read_domains=frozenset(
            {ReadDomain.POWER, ReadDomain.BRIGHTNESS, ReadDomain.COLOUR_MODE, ReadDomain.FIRMWARE, ReadDomain.HARDWARE}
        ),
        setup_required_read_domains=frozenset({ReadDomain.POWER}),
        supports_rgb=True,
        supports_color_temperature=True,
        supports_segment_color_temperature=True,
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
        music_variants=H6117_MUSIC_VARIANTS,
        supports_music_color=True,
        physical_ic_count=50,
        segment_count=15,
        segment_group_size=3,
        supports_segment_writes=True,
        supports_segment_brightness=True,
        effect_readback="diy_code_only",
        advanced_diy_selector=402,
        diy_requires_upload_ack=True,
        music_upload_before_selector=True,
        music_requires_upload_ack=True,
        boolean_controls=frozenset({"gradual"}),
        connection_idle_timeout=IDLE_TIMEOUT_STANDARD,
        scene_catalogue_sku="H6117",
    ),
    "H612A": ModelProfile(
        "H612A RGBIC+W Strip Light",
        support_quality=SupportQuality.EXPERIMENTAL,
        confirmation_issue=687,
        command_grammar="H617A",
        command_ack_grammar="H617A",
        extended_static_grammar="H612A",
        status_grammar="H612A",
        setting_grammar="H612A",
        effect_grammar="H617A",
        music_grammar="H617A",
        profile_pact_dependent=True,
        requires_qualified_identity=True,
        requires_pact_confirmation=True,
        colour_mode_query_selector=1,
        read_domains=frozenset(
            {
                ReadDomain.POWER,
                ReadDomain.BRIGHTNESS,
                ReadDomain.COLOUR_MODE,
                ReadDomain.FIRMWARE,
                ReadDomain.HARDWARE,
                ReadDomain.PACT,
                ReadDomain.PHYSICAL_IC_COUNT,
                ReadDomain.SEGMENTS,
            }
        ),
        setup_required_read_domains=frozenset({ReadDomain.POWER, ReadDomain.BRIGHTNESS, ReadDomain.COLOUR_MODE}),
        supports_rgb=True,
        supports_color_temperature=True,
        color_temp_range=KELVIN_RANGE_2700_6500,
        kelvin_verification_reads_colour_mode=True,
        static_readback_gradual=True,
        static_readback_kelvin=True,
        static_readback_zero_kelvin_is_rgb=True,
        segment_colour_mode_ambiguous=True,
        kelvin_renders_device_white=True,
        physical_ic_count=20,
        physical_ic_capacity=20,
        segment_count=10,
        segment_group_size=4,
        segment_count_capacity=10,
        segment_count_ic_divisor=2,
        segment_count_ic_round_up=True,
        supports_segment_writes=True,
        supports_segment_brightness=True,
        supports_scenes=True,
        supports_custom_effects=True,
        supports_advanced_effects=True,
        supports_multi_layered_effects=True,
        scene_catalogue_sku="H612A",
        scene_command_versions=frozenset({0, 1}),
        advanced_scene_carrier=(29884, 41599),
        advanced_diy_selector=402,
        rgbic_scene_v0=False,
        diy_requires_upload_ack=True,
        effect_retry_after_upload=False,
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
        music_retry_after_upload=False,
        music_params_require_activation=True,
        supports_music_color=True,
        supports_power_on_behaviour=True,
        boolean_controls=frozenset({"gradual"}),
        strip_length_metres=(5,),
        strip_ics_per_metre=4,
        connection_idle_timeout=IDLE_TIMEOUT_STANDARD,
        effect_readback="diy_code_only",
    ),
    "H6125": ModelProfile(
        "H6125 LED Strip",
        color_temp_range=KELVIN_RANGE_2000_9000,
        support_quality=SupportQuality.SUPPORTED,
        confirmation_issue=447,
        command_grammar="H617A",
        command_ack_grammar="H6125",
        status_grammar="H6125",
        profile_identity_fields=frozenset({"fw_version", "hw_version"}),
        effect_grammar="H617A",
        # Static replies carry the V2 Kelvin field, as on H6102.
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
        segment_count=15,
        segment_group_size=3,
        supports_segment_writes=True,
        supports_segment_brightness=True,
        connection_idle_timeout=IDLE_TIMEOUT_STANDARD,
        scene_catalogue_sku="H6125",
        local_scenes=((249, "Work"),),
        effect_readback="diy_code_only",
        # The latest Type04 upload is written through this slot on the pact-1 route.
        a1_diy_selector=0xFE,
        advanced_diy_selector=402,
        # The companion is uploaded before the selector and its acknowledgement is awaited.
        music_upload_before_selector=True,
        music_requires_upload_ack=True,
        diy_requires_upload_ack=True,
        boolean_controls=frozenset({"gradual"}),
    ),
    "H6127": ModelProfile(
        "H6127 DreamColor LED Strip",
        confirmation_issue=634,
        support_quality=SupportQuality.SUPPORTED,
        command_grammar="H617A",
        command_ack_grammar="H6125",
        status_grammar="H6125",
        effect_grammar="H617A",
        profile_identity_fields=frozenset({"fw_version", "hw_version"}),
        profile_pact_dependent=True,
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
        setup_required_read_domains=frozenset({ReadDomain.POWER}),
        supports_rgb=True,
        supports_color_temperature=True,
        color_temp_range=KELVIN_RANGE_2000_9000,
        static_readback_kelvin=True,
        static_readback_zero_kelvin_is_rgb=True,
        static_readback_gradual=True,
        physical_ic_count=50,
        segment_count=15,
        segment_group_size=3,
        supports_segment_writes=True,
        supports_segment_brightness=True,
        supports_segment_color_temperature=True,
        supports_scenes=True,
        scene_catalogue_sku="H6127",
        local_scenes=(
            (0, "Sunrise"),
            (1, "Sunset"),
            (4, "Film"),
            (5, "Date"),
            (7, "Romantic"),
            (8, "Blinking"),
            (9, "Candle"),
            (15, "Snow"),
        ),
        supports_custom_effects=True,
        supports_multi_layered_effects=True,
        supports_advanced_effects=True,
        advanced_diy_selector=402,
        a1_diy_selector=0xFE,
        diy_requires_upload_ack=True,
        effect_readback="diy_code_only",
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
        music_variants=H6127_MUSIC_VARIANTS,
        supports_music_color=True,
        music_upload_before_selector=True,
        music_requires_upload_ack=True,
        music_params_require_activation=True,
        boolean_controls=frozenset({"gradual"}),
        connection_idle_timeout=IDLE_TIMEOUT_STANDARD,
    ),
    "H6139": ModelProfile(
        "H6139 RGB LED Strip",
        confirmation_issue=705,
        reconciles_marker_pact=True,
        command_grammar="H6181",
        command_ack_grammar="H6181",
        command_operations=frozenset({"power", "brightness", "static", "scene", "diy", "music", "effect_upload"}),
        status_grammar="H6139",
        effect_grammar="H6181",
        effect_identity_fields=frozenset({"fw_version", "hw_version"}),
        static_recovery_identity_fields=frozenset({"pact"}),
        profile_pact_dependent=True,
        colour_mode_query_selector=1,
        read_domains=frozenset(
            {ReadDomain.POWER, ReadDomain.BRIGHTNESS, ReadDomain.COLOUR_MODE, ReadDomain.FIRMWARE, ReadDomain.HARDWARE}
        ),
        setup_required_read_domains=frozenset({ReadDomain.POWER}),
        supports_rgb=True,
        supports_color_temperature=True,
        color_temp_range=KELVIN_RANGE_2000_9000,
        static_readback_echoes_color=True,
        static_readback_kelvin=True,
        static_readback_kelvin_suppresses_rgb=True,
        static_readback_zero_kelvin_is_rgb=True,
        supports_scenes=True,
        scene_catalogue_sku="H6139",
        scene_command_versions=frozenset({0}),
        authored_palette_scene_selector=198,
        local_scenes=(
            (4, "Movie"),
            (5, "Date"),
            (7, "Romantic"),
            (8, "Blink"),
            (9, "Candle"),
            (16, "Colour cycle"),
            (10, "Breathe"),
        ),
        supports_custom_effects=True,
        supports_multi_layered_effects=True,
        effect_workflows=frozenset({"native_scenes", "edited_palette_scenes", "single", "multi", "native_music"}),
        diy_upload_transport="a3",
        diy_requires_upload_ack=True,
        effect_retry_after_upload=False,
        effect_readback="diy_code_only",
        music_modes=("dynamic", "soft", "bloom", "radiant"),
        music_variants=H6139_MUSIC_VARIANTS,
        music_upload_before_selector=True,
        music_requires_upload_ack=True,
        music_retry_after_upload=False,
        music_params_require_activation=True,
        music_sensitivity_max=99,
        supports_music_color=True,
        connection_idle_timeout=IDLE_TIMEOUT_STANDARD,
    ),
    "H6159": ModelProfile(
        "H6159 RGB LED Strip",
        support_quality=SupportQuality.SUPPORTED,
        confirmation_issue=636,
        reconciles_marker_pact=True,
        command_grammar="H6181",
        command_operations=frozenset({"power", "brightness", "static", "scene", "diy", "music", "effect_upload"}),
        status_grammar="H6159",
        effect_grammar="H6181",
        profile_identity_fields=frozenset({"fw_version", "hw_version"}),
        profile_pact_dependent=True,
        colour_mode_query_selector=1,
        read_domains=frozenset(
            {ReadDomain.POWER, ReadDomain.BRIGHTNESS, ReadDomain.COLOUR_MODE, ReadDomain.FIRMWARE, ReadDomain.HARDWARE}
        ),
        setup_required_read_domains=frozenset({ReadDomain.POWER}),
        supports_rgb=True,
        supports_color_temperature=True,
        color_temp_range=KELVIN_RANGE_2000_9000,
        static_readback_echoes_color=True,
        static_readback_kelvin=True,
        static_readback_kelvin_suppresses_rgb=True,
        static_readback_zero_kelvin_is_rgb=True,
        supports_scenes=True,
        scene_catalogue_sku="H6159",
        authored_palette_scene_selector=198,
        local_scenes=(
            (0, "Sunrise"),
            (1, "Sunset"),
            (4, "Movie"),
            (5, "Date"),
            (7, "Romantic"),
            (8, "Blink"),
            (9, "Candle"),
        ),
        supports_custom_effects=True,
        supports_multi_layered_effects=True,
        effect_workflows=frozenset({"native_scenes", "edited_palette_scenes", "single", "multi", "native_music"}),
        diy_upload_transport="a3",
        diy_requires_upload_ack=True,
        effect_retry_after_upload=False,
        effect_readback="diy_code_only",
        music_modes=("dynamic", "soft", "bloom", "radiant"),
        music_variants=H6159_MUSIC_VARIANTS,
        music_upload_before_selector=True,
        music_requires_upload_ack=True,
        music_retry_after_upload=False,
        music_params_require_activation=True,
        music_sensitivity_max=99,
        supports_music_color=True,
        connection_idle_timeout=IDLE_TIMEOUT_STANDARD,
    ),
    "H7020": ModelProfile(
        "H7020 Outdoor String Lights",
        support_quality=SupportQuality.SUPPORTED,
        resolve_profile_before_state_init=True,
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
        color_temp_range=KELVIN_RANGE_2000_9000,
        segment_count=30,
        segment_group_size=3,
        configured_string_counts=(1, 2),
        bulbs_per_string=15,
        segment_colour_mode_ambiguous=True,
        supports_segment_writes=True,
        supports_segment_brightness=True,
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
        connection_idle_timeout=IDLE_TIMEOUT_STANDARD,
    ),
    "H6181": ModelProfile(
        "H6181 RGB TV Backlight",
        color_temp_range=KELVIN_RANGE_2000_9000,
        support_quality=SupportQuality.SUPPORTED,
        confirmation_issue=580,
        allows_legacy_plaintext_marker=True,
        reconciles_marker_pact=True,
        command_grammar="H6181",
        status_grammar="H6181-modern",
        command_ack_grammar="H6181",
        command_operations=frozenset({"power", "brightness", "static", "scene", "diy", "music", "effect_upload"}),
        effect_grammar="H6181",
        effect_workflows=frozenset({"native_scenes", "edited_palette_scenes", "single", "multi", "native_music"}),
        colour_mode_query_selector=1,
        profile_identity_fields=frozenset({"fw_version", "hw_version"}),
        static_identity_fields=frozenset({"fw_version", "hw_version"}),
        profile_pact_dependent=True,
        read_domains=frozenset(
            {ReadDomain.POWER, ReadDomain.BRIGHTNESS, ReadDomain.COLOUR_MODE, ReadDomain.FIRMWARE, ReadDomain.HARDWARE}
        ),
        setup_required_read_domains=frozenset({ReadDomain.POWER}),
        supports_rgb=True,
        supports_color_temperature=True,
        supports_custom_effects=True,
        supports_multi_layered_effects=True,
        supports_scenes=True,
        static_readback_echoes_color=True,
        static_readback_kelvin=True,
        static_readback_kelvin_suppresses_rgb=True,
        static_readback_zero_kelvin_is_rgb=True,
        scene_catalogue_sku="H6181",
        local_scenes=(
            (0, "Sunrise"),
            (1, "Sunset"),
            (4, "Movie"),
            (5, "Date"),
            (7, "Romantic"),
            (8, "Blink"),
            (9, "Candle"),
        ),
        music_modes=("dynamic", "soft", "bloom", "radiant"),
        music_variants=H6181_MUSIC_VARIANTS,
        music_upload_before_selector=True,
        music_requires_upload_ack=True,
        music_retry_after_upload=False,
        music_readback_ambiguous=True,
        music_sensitivity_max=99,
        supports_music_color=True,
        effect_readback="diy_code_only",
        diy_upload_transport="a3",
        diy_requires_upload_ack=True,
        effect_retry_after_upload=False,
    ),
    "H6182": ModelProfile(
        "H6182 RGB TV Backlight",
        support_quality=SupportQuality.SUPPORTED,
        confirmation_issue=654,
        reconciles_marker_pact=True,
        command_grammar="H6181",
        command_operations=frozenset({"power", "brightness", "static", "scene", "diy", "music", "effect_upload"}),
        status_grammar="H6182-modern",
        effect_grammar="H6181",
        profile_identity_fields=frozenset({"fw_version", "hw_version"}),
        profile_pact_dependent=True,
        colour_mode_query_selector=1,
        read_domains=frozenset(
            {ReadDomain.POWER, ReadDomain.BRIGHTNESS, ReadDomain.COLOUR_MODE, ReadDomain.FIRMWARE, ReadDomain.HARDWARE}
        ),
        setup_required_read_domains=frozenset({ReadDomain.POWER}),
        supports_rgb=True,
        supports_color_temperature=True,
        color_temp_range=KELVIN_RANGE_2000_9000,
        static_readback_echoes_color=True,
        static_readback_kelvin=True,
        static_readback_kelvin_suppresses_rgb=True,
        static_readback_zero_kelvin_is_rgb=True,
        supports_scenes=True,
        scene_catalogue_sku="H6182",
        local_scenes=(
            (4, "Movie"),
            (5, "Date"),
            (9, "Candle"),
            (7, "Romantic"),
            (10, "Breathing"),
            (8, "Blink"),
            (16, "Energetic"),
        ),
        authored_palette_scene_selector=198,
        supports_custom_effects=True,
        supports_multi_layered_effects=True,
        effect_workflows=frozenset({"native_scenes", "edited_palette_scenes", "single", "multi", "native_music"}),
        diy_upload_transport="a3",
        diy_requires_upload_ack=True,
        effect_retry_after_upload=False,
        effect_readback="diy_code_only",
        music_modes=("dynamic", "soft", "bloom", "radiant"),
        music_variants=H6182_MUSIC_VARIANTS,
        music_readback_ambiguous=True,
        music_upload_before_selector=True,
        music_requires_upload_ack=True,
        music_retry_after_upload=False,
        music_params_require_activation=True,
        music_sensitivity_max=99,
        supports_music_color=True,
        connection_idle_timeout=IDLE_TIMEOUT_STANDARD,
    ),
    "H6179": ModelProfile(
        "H6179 RGB TV Backlight",
        color_temp_range=KELVIN_RANGE_2000_9000,
        support_quality=SupportQuality.EXPERIMENTAL,
        confirmation_issue=448,
        command_grammar="H6179",
        status_grammar="H6179",
        effect_grammar="H6179",
        profile_pact_dependent=True,
        diy_upload_transport="a1_02",
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
        static_readback_zero_kelvin_is_rgb=True,
        scene_catalogue_sku="H6179",
        selector_only_scene_bits=8,
        effect_readback="diy_code_only",
        boolean_controls=frozenset({"limit"}),
        restarting_boolean_controls=frozenset({"limit"}),
    ),
    "H619A": ModelProfile(
        "H619A RGBIC Pro Strip",
        color_temp_range=KELVIN_RANGE_2000_9000,
        confirmation_issue=567,
        command_grammar="H617A",
        command_ack_grammar="H617A",
        status_grammar="H619A",
        effect_grammar="H617A",
        colour_mode_query_selector=1,
        scene_identity_fields=frozenset({"fw_version", "hw_version"}),
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
        music_variants=H619A_MUSIC_VARIANTS,
        music_upload_before_selector=True,
        music_requires_upload_ack=True,
        supports_music_color=True,
        physical_ic_count=20,
        segment_count=10,
        segment_group_size=3,
        supports_segment_writes=True,
        supports_segment_brightness=True,
        supports_segment_color_temperature=True,
        connection_idle_timeout=IDLE_TIMEOUT_STANDARD,
        scene_catalogue_sku="H619A",
        rgbic_scene_v0=False,
        advanced_diy_selector=402,
        diy_requires_upload_ack=True,
        boolean_controls=frozenset({"gradual"}),
        effect_readback="diy_code_only",
    ),
    "H6199": ModelProfile(
        "H6199 DreamView T1",
        color_temp_range=KELVIN_RANGE_2000_9000,
        support_quality=SupportQuality.SUPPORTED,
        command_grammar="H6199",
        status_grammar="H6199",
        effect_grammar="H6199",
        video_grammar="H6199",
        video_revision_policy=VideoRevisionPolicy.QUALIFIED_CAMERA,
        camera_control_policy=CameraControlPolicy(
            identity_fields=("fw_version", "hw_version", "subordinate_20_version", "subordinate_21_version"),
            qualified_versions=(11004, 30201, 10300, 10033),
            qualified_pact=(2, 1),
            entity_suffixes=frozenset({"_strip_direction", "_camera_position", "_gradient", "_camera_status"}),
        ),
        profile_identity_fields=frozenset({"fw_version", "hw_version"}),
        profile_pact_dependent=True,
        dreamview_grammar="H6199",
        dreamview_operations=frozenset(
            {
                "replace_group",
                "delete_group",
                "switch_group",
                "member_brightness",
                "same_brightness",
                "member_connect",
                "saturation",
                "video_settings",
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
                "video_settings",
                "sound",
            }
        ),
        dreamview_max_sub_devices=5,
        dreamview_requires_group_ack=True,
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
        setup_required_read_domains=frozenset({ReadDomain.POWER}),
        supports_rgb=True,
        supports_color_temperature=True,
        supports_custom_effects=True,
        supports_scenes=True,
        supports_video_mode=True,
        video_modes=("movie", "game"),
        supports_video_capture_region=True,
        supports_video_saturation=True,
        supports_video_sound_effects=True,
        # These video registers have byte-exact builders.
        supports_white_balance=True,
        supports_white_balance_readback=True,
        video_white_balance_calibration=WHITE_BALANCE_POSITIONS,
        video_brightness_zones=("left", "top", "right", "bottom"),
        supports_relative_brightness=True,
        supports_blank_screen=True,
        music_modes=_H6199_MUSIC_MODES,
        music_variants=(
            MusicVariant(0x05, "H6199 Energetic selector; no fixed colour", supports_fixed_colour=False),
            MusicVariant(0x03, "H6199 Rhythm selector style", supports_style=True),
            MusicVariant(0x04, "H6199 owner-qualified Spectrum fixed-colour readback"),
            MusicVariant(0x06, "H6199 owner-qualified Rolling fixed-colour readback"),
        ),
        music_sensitivity_min=0,
        music_sensitivity_max=100,
        supports_music_color=True,
        supports_advanced_effects=True,
        # Static readback identifies the mode but exposes rendered colour only through segment
        # queries. Kelvin remains last-known while its RGB companion matches.
        # Fifteen segment bits are independently writable. The aa 40 value 38 is not a segment count.
        segment_count=15,
        segment_group_size=4,
        # Colour and brightness writes are observed through four explicit aa a5 query groups.
        supports_segment_writes=True,
        supports_segment_brightness=True,
        scene_catalogue_sku="H6199",
        advanced_scene_carrier=(29884, 41599),
        default_effect_families_override=frozenset({EFFECT_FAMILY_VIDEO}),
        effect_readback="diy_code_only",
        legacy_effect_selector_domains=(
            ("workshop", LegacyEffectSelectorDomain.SCENE),
            ("shared_scene", LegacyEffectSelectorDomain.SCENE),
            ("palette_diy", LegacyEffectSelectorDomain.SCENE),
        ),
        legacy_custom_to_scene_signatures=(("palette_diy", 401),),
    ),
    "H705A": ModelProfile(
        "H705A Permanent Outdoor Lights",
        confirmation_issue=596,
        command_grammar="H705A",
        command_ack_grammar="H705A",
        status_grammar="H705A",
        effect_grammar="H617A",
        music_grammar="H705A",
        colour_mode_query_selector=1,
        profile_pact_dependent=True,
        command_operations=frozenset(
            {
                "power",
                "brightness",
                "static",
                "scene",
                "diy",
                "music",
                "effect_upload",
                "configured_strings",
                "refresh_ic",
            }
        ),
        read_domains=frozenset(
            {
                ReadDomain.POWER,
                ReadDomain.BRIGHTNESS,
                ReadDomain.COLOUR_MODE,
                ReadDomain.FIRMWARE,
                ReadDomain.HARDWARE,
                ReadDomain.PHYSICAL_IC_COUNT,
                ReadDomain.SEGMENTS,
            }
        ),
        setup_required_read_domains=frozenset({ReadDomain.POWER, ReadDomain.PHYSICAL_IC_COUNT}),
        supports_rgb=True,
        supports_color_temperature=True,
        color_temp_range=KELVIN_RANGE_2000_9000,
        physical_ic_count=36,
        physical_ic_capacity=108,
        segment_count=9,
        segment_count_capacity=27,
        segment_count_ic_divisor=4,
        segment_count_ic_round_up=False,
        configured_string_counts=tuple(range(1, 10)),
        bulbs_per_string=3,
        configured_string_ic_count=12,
        supports_ic_refresh=True,
        segment_group_size=4,
        supports_segment_writes=True,
        supports_segment_brightness=True,
        supports_segment_color_temperature=True,
        segment_colour_mode_ambiguous=True,
        static_readback_kelvin=True,
        static_readback_zero_kelvin_is_rgb=True,
        static_readback_gradual=True,
        boolean_controls=frozenset({"gradual"}),
        supports_custom_effects=True,
        supports_multi_layered_effects=True,
        supports_scenes=True,
        supports_advanced_effects=True,
        scene_catalogue_sku="H705A",
        advanced_diy_selector=402,
        diy_requires_upload_ack=True,
        effect_retry_after_upload=False,
        effect_readback="diy_code_only",
        music_modes=("energetic", "shiny", "jumping", "hopping", "firefly", "rolling"),
        music_variants=H705A_MUSIC_VARIANTS,
        music_upload_before_selector=True,
        music_requires_upload_ack=True,
        music_retry_after_upload=False,
        music_params_require_activation=True,
        connection_idle_timeout=IDLE_TIMEOUT_STANDARD,
    ),
    "H7025": ModelProfile(
        "H7025 Outdoor String Lights",
        support_quality=SupportQuality.SUPPORTED,
        confirmation_issue=451,
        command_grammar="H617A",
        status_grammar="H7025",
        effect_grammar="H617A",
        native_effect_codec="h7025-a3-0x58",
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
        color_temp_range=KELVIN_RANGE_2700_6500,
        static_readback_kelvin=True,
        static_readback_zero_kelvin_is_rgb=True,
        segment_count=15,
        segment_group_size=4,
        segment_colour_mode_ambiguous=True,
        static_palette_recovery=True,
        supports_segment_writes=True,
        supports_segment_brightness=True,
        supports_segment_color_temperature=True,
        supports_custom_effects=True,
        supports_scenes=True,
        supports_multi_layered_effects=True,
        scene_catalogue_sku="H7025",
        diy_requires_upload_ack=True,
        native_diy_upload_subtype=0x58,
        native_diy_selector=254,
        effect_readback="diy_code_only",
        connection_idle_timeout=IDLE_TIMEOUT_STANDARD,
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

MODEL_REVISION_POLICY_REGISTRATIONS = (
    ModelRevisionPolicyRegistration("H612A", "h612a"),
    ModelRevisionPolicyRegistration("H6053", "h6053"),
    ModelRevisionPolicyRegistration("H6093", "h6093"),
    ModelRevisionPolicyRegistration("H6139", "h6139"),
    ModelRevisionPolicyRegistration("H6159", "h6159"),
    ModelRevisionPolicyRegistration("H6182", "h6182"),
    ModelRevisionPolicyRegistration("H6181", "h6181"),
    ModelRevisionPolicyRegistration("H60B0", "h60b0"),
    ModelRevisionPolicyRegistration("H705A", "h705a"),
    ModelRevisionPolicyRegistration("H605C", "h605c"),
    ModelRevisionPolicyRegistration("H8604", "h8604"),
    ModelRevisionPolicyRegistration("H6046", "standard_pacts"),
    ModelRevisionPolicyRegistration("H607C", "h607c"),
    ModelRevisionPolicyRegistration("H6097", "standard_pacts"),
    ModelRevisionPolicyRegistration("H61E5", "standard_pacts"),
    ModelRevisionPolicyRegistration("H7020", "standard_pacts"),
    ModelRevisionPolicyRegistration("H60A1", "h60a1"),
    ModelRevisionPolicyRegistration("H60A6", "h60a6"),
    ModelRevisionPolicyRegistration("H61F5", "h61f5"),
    ModelRevisionPolicyRegistration("H617A", "h617a"),
    ModelRevisionPolicyRegistration("H619A", "h619a"),
    ModelRevisionPolicyRegistration("H618A", "h618a"),
    ModelRevisionPolicyRegistration("H6199", "h6199"),
    ModelRevisionPolicyRegistration("H6072", "h6072"),
    ModelRevisionPolicyRegistration("H6076", "h6076"),
    ModelRevisionPolicyRegistration("H6179", "h6179"),
    ModelRevisionPolicyRegistration("H6117", "h6117"),
    ModelRevisionPolicyRegistration("H6125", "h6125"),
    ModelRevisionPolicyRegistration("H6127", "h6127"),
    ModelRevisionPolicyRegistration("H6102", "h6102"),
)
_REVISION_POLICY_BY_MODEL = {
    registration.model: registration.policy_id for registration in MODEL_REVISION_POLICY_REGISTRATIONS
}
MODEL_PROFILES = {
    model: replace(profile, revision_policy=_REVISION_POLICY_BY_MODEL[model])
    if model in _REVISION_POLICY_BY_MODEL
    else profile
    for model, profile in MODEL_PROFILES.items()
}

BLE_DISCOVERABLE_MODELS = frozenset(MODEL_PROFILES)

UNSUPPORTED_PROFILE = ModelProfile("Unsupported Govee device")

# Grammar families shared by several SKUs; shared code tests membership here, not literal sets.
VIDEO_GRAMMARS = frozenset({"H6099", "H6199"})
WHOLE_BULB_GRAMMARS = frozenset({"H600A", "H601C", "H6181"})
_DIY_ACTIVATION_GRAMMARS = WHOLE_BULB_GRAMMARS | {
    "H1771",
    "H60B0",
    "H6072",
    "H6072-legacy",
    "H607C",
    "H617A",
    "H7020",
    "H705A",
    "H6046",
    "H6099",
    "H6179",
    "H6199",
}
_EFFECT_ACTIVATION_GRAMMARS = {
    "diy": _DIY_ACTIVATION_GRAMMARS,
    "scene": _DIY_ACTIVATION_GRAMMARS | {"H6199"},
}
MODE_COMMAND_GRAMMARS = WHOLE_BULB_GRAMMARS | {"H6046", "H6099", "H6199"}
PERCENT_BRIGHTNESS_STATUS_GRAMMARS = frozenset(
    {
        "H1771",
        "H60B0",
        "H600A",
        "H6093",
        "H6046",
        "H6053",
        "H6053-legacy",
        "H6097",
        "H6099",
        "H8604",
        "H6139",
        "H6159",
        "H6181",
        "H6181-modern",
        "H6182",
        "H6182-modern",
        "H6199",
        "H6199-Pact1",
        "H66A0",
    }
)


def _h6199_pact1_wire(packet: bytes) -> bytes:
    from .protocol_transforms import h6199_pact1_outbound_transform

    return h6199_pact1_outbound_transform(packet)


H6199_PACT1_PROFILE = ModelProfile(
    "H6199 Pact 1",
    support_quality=SupportQuality.SUPPORTED,
    revision_policy="h6199",
    command_grammar="H6199",
    command_operations=frozenset({"power", "brightness", "static", "scene", "music"}),
    status_grammar="H6199-Pact1",
    effect_grammar="H6199",
    effect_workflows=frozenset({"native_scenes", "native_music"}),
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
    setup_required_read_domains=frozenset({ReadDomain.POWER}),
    colour_mode_query_selector=1,
    supports_rgb=True,
    supports_color_temperature=True,
    color_temp_range=KELVIN_RANGE_2000_9000,
    segment_count=15,
    segment_group_size=4,
    supports_segment_writes=True,
    segment_colour_mode_ambiguous=True,
    supports_scenes=True,
    scene_catalogue_sku="H6199",
    selector_only_scene_bits=16,
    scene_codes=frozenset({0, 1, 4, 5, 7, 8, 9, 10, 15, 16, 21, 22}),
    music_modes=("energetic", "rhythm", "spectrum", "rolling"),
    music_variants=(
        MusicVariant(0x05, "Energetic has no fixed colour", supports_fixed_colour=False),
        MusicVariant(0x03, "Rhythm supports style selection", supports_style=True),
        MusicVariant(0x04, "Spectrum supports fixed colour"),
        MusicVariant(0x06, "Rolling supports fixed colour"),
    ),
    music_sensitivity_min=0,
    music_sensitivity_max=99,
    supports_music_color=True,
    brightness_wire_range=(20, 254),
    outbound_transform=_h6199_pact1_wire,
    profile_identity_fields=frozenset({"fw_version", "hw_version"}),
    profile_pact_dependent=True,
    dreamview_grammar="H6199",
    dreamview_operations=frozenset(
        {
            "replace_group",
            "delete_group",
            "switch_group",
            "member_brightness",
            "member_connect",
            "saturation",
            "video_settings",
            "sound",
        }
    ),
    dreamview_reads=frozenset(
        {
            "switch_group",
            "member_brightness",
            "member_connect",
            "saturation",
            "video_settings",
            "sound",
        }
    ),
    dreamview_max_sub_devices=5,
    dreamview_requires_group_ack=True,
)


# Unresolved revisions authorise only the independently shared bootstrap operations.
H6125_POWER_ONLY_PROFILE = ModelProfile(
    "H6125 (power only)",
    support_quality=SupportQuality.SUPPORTED,
    revision_policy="h6125",
    confirmation_issue=MODEL_PROFILES["H6125"].confirmation_issue,
    command_grammar="H617A",
    command_operations=frozenset({"power"}),
    status_grammar="H6125",
    profile_identity_fields=frozenset({"fw_version", "hw_version"}),
    read_domains=frozenset({ReadDomain.POWER, ReadDomain.FIRMWARE, ReadDomain.HARDWARE}),
    setup_required_read_domains=frozenset({ReadDomain.POWER}),
)

H6117_POWER_ONLY_PROFILE = ModelProfile(
    "H6117 (awaiting controller identity)",
    revision_policy="h6117",
    confirmation_issue=537,
    command_grammar="H617A",
    command_operations=frozenset({"power"}),
    command_ack_grammar="H6125",
    status_grammar="H6117",
    profile_identity_fields=frozenset({"fw_version", "hw_version"}),
    profile_pact_dependent=True,
    read_domains=frozenset({ReadDomain.POWER, ReadDomain.FIRMWARE, ReadDomain.HARDWARE}),
    setup_required_read_domains=frozenset({ReadDomain.POWER}),
)


def _h6117_profile(
    pact_type: int | None, pact_code: int | None, firmware: str | None, hardware: str | None
) -> ModelProfile:
    """Resolve H6117 colour, brightness, music and uploads independently."""
    from .firmware_version import FirmwareVersion
    from .protocol_transforms import h6117_outbound_transform

    fw, hw = FirmwareVersion.parse(firmware), FirmwareVersion.parse(hardware)
    if fw is None or hw is None or pact_type is None or pact_code is None or pact_type < 1 or pact_code < 1:
        return H6117_POWER_ONLY_PROFILE
    family = hw.identity_number() // 10000
    if family != fw.identity_number() // 10000 or family not in {1, 2, 3}:
        return H6117_POWER_ONLY_PROFILE
    modern = pact_type >= 2
    if not modern and family != 1:
        return H6117_POWER_ONLY_PROFILE
    extended_rgb = hw >= FirmwareVersion((1, 0, 2)) and fw >= FirmwareVersion((1, 6))
    extended = modern or extended_rgb
    whole_device = hw < FirmwareVersion((1, 0, 2)) and fw < FirmwareVersion((1, 3, 18))
    expanded_music = (
        not modern
        and family == 1
        and fw >= FirmwareVersion((1, 7))
        or hardware is not None
        and hardware.startswith("2.01.")
        and fw >= FirmwareVersion((2, 4))
        or family == 3
        and hardware is not None
        and not hardware.startswith("3.04.")
        and fw >= FirmwareVersion((3, 1))
    )
    uploaded_scenes = hw >= FirmwareVersion((1, 0, 2)) and fw >= FirmwareVersion((1, 4))
    workflows = frozenset({"native_music", "native_scenes", "single", "multi"})
    if uploaded_scenes:
        workflows |= {"edited_palette_scenes", "layered_scenes", "advanced", "workshop"}
    if extended:
        workflows |= {"painted"}
    profile = MODEL_PROFILES["H6117"]
    wire_range = (6, 254) if family == 1 else None
    return replace(
        profile,
        status_grammar="H6117" if modern else "H6117-legacy",
        supports_color_temperature=extended,
        supports_segment_color_temperature=extended and not whole_device,
        static_readback_kelvin=extended,
        static_readback_zero_kelvin_is_rgb=extended,
        static_readback_gradual=extended,
        segment_count=1 if whole_device else 15,
        segment_group_size=3 if extended else 4,
        supports_segment_writes=not whole_device,
        supports_segment_brightness=extended and not whole_device,
        effect_workflows=workflows,
        music_modes=profile.music_modes if expanded_music else profile.music_modes[:4],
        supports_advanced_effects=uploaded_scenes,
        supports_multi_layered_effects=uploaded_scenes,
        advanced_diy_selector=profile.advanced_diy_selector if uploaded_scenes else None,
        a1_diy_selector=None if modern else 0xFE,
        selector_only_scene_bits=None if uploaded_scenes else 16,
        scene_codes=None if uploaded_scenes else frozenset({0, 1, 4, 5, 7, 8, 9, 10, 15, 16, 21, 22}),
        brightness_wire_range=wire_range,
        outbound_transform=h6117_outbound_transform(
            wire_range,
            legacy_colour=not extended_rgb and not whole_device,
            whole_device=whole_device,
            legacy_music=not modern,
        ),
    )


def _h6125_profile(
    pact_type: int | None, pact_code: int | None, firmware: str | None, hardware: str | None
) -> ModelProfile:
    """Resolve independently gated H6125 controls from the controller's full identity."""
    from .firmware_version import FirmwareVersion
    from .protocol_core import H6125IntermediateStatusReply, H6125LegacyStatusReply
    from .protocol_transforms import dreamcolor_outbound_transform

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
        outbound_transform=dreamcolor_outbound_transform(
            wire_range, legacy_colour=not extended_colour, legacy_music=original_music
        ),
    )


def _h6127_profile(
    pact_type: int | None, pact_code: int | None, firmware: str | None, hardware: str | None
) -> ModelProfile:
    from .protocol_transforms import dreamcolor_outbound_transform

    profile = MODEL_PROFILES["H6127"]
    fw, hw = FirmwareVersion.parse(firmware), FirmwareVersion.parse(hardware)
    if fw is None or hw is None or fw.identity_number() // 10000 != hw.identity_number() // 10000:
        return replace(
            profile,
            command_operations=frozenset({"power"}),
            effect_workflows=frozenset(),
            read_domains=frozenset({ReadDomain.POWER, ReadDomain.FIRMWARE, ReadDomain.HARDWARE}),
            supports_rgb=False,
            supports_color_temperature=False,
            supports_segment_writes=False,
            supports_segment_brightness=False,
            supports_segment_color_temperature=False,
            supports_scenes=False,
            supports_custom_effects=False,
            supports_multi_layered_effects=False,
            supports_advanced_effects=False,
            music_modes=(),
            music_variants=(),
            boolean_controls=frozenset(),
        )
    modern = pact_type == 10 and pact_code in (1, 2, 3)
    telink = (
        hardware is not None
        and hardware.startswith("1.")
        and (
            pact_type == 1
            and pact_code in (1, 2)
            or pact_type is None
            and pact_code is None
            and fw < FirmwareVersion((1, 3, 1))
        )
    )
    if modern:
        bk = hardware is not None and hardware.startswith("2.01.")
        frk = hardware is not None and hardware.startswith("3.") and not hardware.startswith("3.04.")
        if bk or frk:
            return replace(
                profile,
                status_grammar="H6125-modern",
                music_modes=profile.music_modes
                if fw >= FirmwareVersion((2, 4) if bk else (3, 1))
                else profile.music_modes[:4],
                a1_diy_selector=None,
                rgbic_scene_v0=False,
                scene_command_versions=frozenset({0, 1}),
            )
    if not telink:
        return _h6127_profile(None, None, None, None)
    if fw < FirmwareVersion((1, 3, 1)):
        inline = fw < FirmwareVersion((1, 1, 20))
        diy = fw >= FirmwareVersion((1, 1, 16))
        legacy_workflows = {"native_music", "native_scenes"}
        if diy:
            legacy_workflows.add("single")
        if diy and not inline:
            legacy_workflows.add("multi")
        return replace(
            profile,
            status_grammar="H6127-legacy",
            effect_workflows=frozenset(legacy_workflows),
            read_domains=profile.read_domains - {ReadDomain.SEGMENTS},
            color_temp_range=KELVIN_RANGE_2700_6500,
            static_readback_kelvin=False,
            static_readback_zero_kelvin_is_rgb=False,
            static_readback_gradual=False,
            static_readback_echoes_color=True,
            supports_segment_writes=False,
            supports_segment_brightness=False,
            supports_segment_color_temperature=False,
            segment_count=1,
            segment_group_size=0,
            selector_only_scene_bits=8,
            scene_codes=frozenset({0, 1, 4, 5, 7, 8, 9, 15}),
            supports_custom_effects=diy,
            supports_multi_layered_effects=diy and not inline,
            supports_advanced_effects=False,
            advanced_diy_selector=None,
            diy_upload_transport="single" if inline else "a1_02",
            diy_family_variants=(
                (0, (0, 1, 2)),
                (1, (0, 2)),
                (2, (0, 1, 2)),
                (3, (3, 4, 5)),
                (4, (6, 7) if inline else (8, 6, 7)),
            ),
            diy_palette_max=4 if inline else 8,
            diy_requires_upload_ack=not inline,
            a1_diy_selector=None if inline else 0xFE,
            music_modes=profile.music_modes[:4],
            music_variants=tuple(
                replace(
                    variant,
                    supports_style=False,
                    supports_fixed_colour=variant.mode_code in (4, 6),
                    fixed_colour_default=(255, 0, 0) if variant.mode_code in (4, 6) else None,
                )
                for variant in profile.music_variants
                if variant.mode_code in (3, 4, 5, 6)
            ),
            music_readback_ambiguous=True,
            music_upload_before_selector=False,
            music_requires_upload_ack=False,
            boolean_controls=frozenset(),
            brightness_wire_range=(6, 254),
            outbound_transform=dreamcolor_outbound_transform(
                (6, 254), whole_device_colour=True, direct_music_colour=True
            ),
        )
    extended = hw >= FirmwareVersion((1, 0, 3)) and fw >= FirmwareVersion((1, 6))
    uploaded = pact_code == 2 or fw >= FirmwareVersion((1, 4))
    workflows = frozenset({"native_music", "native_scenes", "single", "multi"})
    if uploaded:
        workflows |= {"edited_palette_scenes", "layered_scenes", "advanced", "workshop"}
    if extended:
        workflows |= {"painted"}
    return replace(
        profile,
        status_grammar="H6127" if extended else "H6127-intermediate",
        effect_workflows=workflows,
        supports_color_temperature=extended,
        supports_segment_color_temperature=extended,
        static_readback_kelvin=extended,
        static_readback_zero_kelvin_is_rgb=extended,
        supports_segment_brightness=extended,
        segment_group_size=3 if extended else 4,
        supports_advanced_effects=uploaded,
        advanced_diy_selector=profile.advanced_diy_selector if uploaded else None,
        selector_only_scene_bits=None if uploaded else 8,
        scene_codes=None if uploaded else frozenset({0, 1, 4, 5, 7, 8, 9, 10, 15, 16, 21, 22}),
        music_modes=profile.music_modes if fw >= FirmwareVersion((1, 7)) else profile.music_modes[:4],
        brightness_wire_range=(6, 254),
        rgbic_scene_v0=not extended,
        scene_command_versions=frozenset({0, 1})
        if hw >= FirmwareVersion((1, 0, 2)) and fw >= FirmwareVersion((1, 6))
        else frozenset({0}),
        outbound_transform=dreamcolor_outbound_transform((6, 254), legacy_colour=not extended, legacy_gradual=True),
    )


def _h6072_profile(
    pact_type: int | None, pact_code: int | None, firmware: str | None, hardware: str | None
) -> ModelProfile:
    from .firmware_version import FirmwareVersion
    from .scenes import SCENE_ENTRIES

    profile = MODEL_PROFILES["H6072"]
    fw, hw = FirmwareVersion.parse(firmware), FirmwareVersion.parse(hardware)
    new_static = (
        fw is not None and hw is not None and fw >= FirmwareVersion((1, 0, 11)) and hw >= FirmwareVersion((1, 0, 1))
    )
    legacy_static = (fw is not None and fw < FirmwareVersion((1, 0, 11))) or (
        hw is not None and hw < FirmwareVersion((1, 0, 1))
    )
    new_scenes = fw is not None and fw >= FirmwareVersion((1, 1))
    new_music = fw is not None and (
        (pact_type, pact_code) == (1, 1)
        and fw >= FirmwareVersion((1, 3))
        or (pact_type, pact_code) == (2, 1)
        and fw >= FirmwareVersion((2, 2))
    )
    low_blue = fw is not None and fw >= FirmwareVersion((2, 4, 7))
    workflows = frozenset({"native_scenes", "native_music", "single", "multi", "edited_palette_scenes"})
    if new_static:
        workflows |= {"painted"}
    if new_scenes:
        workflows |= {"layered_scenes"}
    if new_static and new_scenes:
        workflows |= {"advanced"}
    return replace(
        profile,
        command_grammar="H6072-legacy" if legacy_static else "H6072",
        supports_rgb=new_static or legacy_static,
        supports_color_temperature=new_static or legacy_static,
        supports_segment_writes=new_static or legacy_static,
        supports_segment_brightness=new_static,
        read_domains=profile.read_domains
        - (set() if new_static or legacy_static else {ReadDomain.SEGMENTS})
        - (set() if low_blue else {ReadDomain.LOW_BLUE_LIGHT}),
        scene_codes=None
        if new_scenes
        else frozenset(scene.code for scene in SCENE_ENTRIES["H6072"] if scene.scene_type in {0, 1}),
        effect_workflows=workflows,
        supports_advanced_effects=new_static and new_scenes,
        advanced_diy_selector=402 if new_static and new_scenes else None,
        music_modes=profile.music_modes if new_music else profile.music_modes[:6],
        music_variants=H6072_MUSIC_VARIANTS if new_music else H6072_LEGACY_MUSIC_VARIANTS,
        music_requires_upload_ack=new_music,
        music_upload_before_selector=new_music,
        music_params_require_activation=new_music,
        supports_low_blue_light=low_blue,
    )


_STANDARD_PACTS = frozenset({(1, 1), (2, 1)})
_H612A_PACTS = frozenset({(1, 1), (1, 2), (2, 1)})
_H60A6_NATIVE_CONTROL_PACTS = frozenset({(1, 1), (1, 2), (1, 3)})
_H6199_DREAMVIEW_PACTS = frozenset({(1, 1), (2, 1), (3, 1), (4, 1)})
_H60A_SEGMENTED_HARDWARE = "1.04.03"
_H60A1_SEGMENTED_FIRMWARE = "1.02.20"
_H60A6_SEGMENTED_FIRMWARE = "1.00.41"


def _h6076_profile(pact_type: int | None, pact_code: int | None, firmware: str | None) -> ModelProfile:
    """Resolve H6076 music modes by software version and Kelvin floor by Pact type."""
    from .firmware_version import FirmwareVersion

    fw = FirmwareVersion.parse(firmware)
    known_pact = (pact_type, pact_code) in _STANDARD_PACTS
    base = (
        _H6076_MUSIC_PROFILE
        if known_pact and fw is not None and fw >= FirmwareVersion((1, 2))
        else replace(_H6076_PROFILE, readback_music_modes=())
        if known_pact and fw is not None
        else _H6076_PROFILE
    )
    return replace(
        base, color_temp_range=KELVIN_RANGE_2200_6500 if (pact_type, pact_code) == (1, 1) else KELVIN_RANGE_2700_6500
    )


def same_profile_except_segment_readback(first: ModelProfile, second: ModelProfile) -> bool:
    from .protocol_transforms import rgb_only_segment_query_transform

    formats = {
        "H619A": ("H619A", 3, None),
        "H619A-legacy": ("H619A", 4, rgb_only_segment_query_transform),
        "H618A": ("H618A", 3, None),
        "H618A-legacy": ("H618A", 4, rgb_only_segment_query_transform),
        "H618A-pact3": ("H618A", 4, None),
    }
    first_format = formats.get(first.status_grammar or "")
    second_format = formats.get(second.status_grammar or "")
    if (
        first_format is None
        or second_format is None
        or first.segment_group_size != first_format[1]
        or first.status_query_transform is not first_format[2]
        or second.segment_group_size != second_format[1]
        or second.status_query_transform is not second_format[2]
        or first_format[0] != second_format[0]
    ):
        return False
    return (
        replace(
            first,
            status_grammar=second.status_grammar,
            status_query_transform=second.status_query_transform,
            read_domains=(first.read_domains - {ReadDomain.SEGMENTS}) | (second.read_domains & {ReadDomain.SEGMENTS}),
            segment_group_size=second.segment_group_size,
        )
        == second
    )


def same_control_profile(first: ModelProfile, second: ModelProfile) -> bool:
    if first == second or same_profile_except_segment_readback(first, second):
        return True
    if first.scene_identity_fields:
        scene_normalized = replace(
            first,
            rgbic_scene_v0=second.rgbic_scene_v0,
            scene_command_versions=second.scene_command_versions,
        )
        if scene_normalized == second or same_profile_except_segment_readback(scene_normalized, second):
            return True
    if (
        not first.effect_identity_fields
        or first.static_outbound_transform is None
        or first.static_outbound_transform != second.static_outbound_transform
    ):
        return False
    return replace(
        first,
        command_operations=first.command_operations - {"music"} if first.command_operations is not None else None,
        outbound_transform=second.outbound_transform,
        effect_workflows=second.effect_workflows,
        music_modes=second.music_modes,
        music_variants=second.music_variants,
        selector_only_scene_bits=second.selector_only_scene_bits,
        authored_palette_scene_selector=second.authored_palette_scene_selector,
        scene_codes=second.scene_codes,
    ) == replace(
        second,
        command_operations=second.command_operations - {"music"} if second.command_operations is not None else None,
    )


def profile_with_physical_ic_count(profile: ModelProfile, count: int, *, segment_count_ceiling: int) -> ModelProfile:
    """Apply installed geometry using the qualified product capacity."""
    if (
        type(count) is not int
        or count <= 0
        or (profile.physical_ic_capacity is not None and count > profile.physical_ic_capacity)
    ):
        raise ValueError("Physical IC count is outside product capacity")
    segments = profile.segment_count
    if profile.segment_count_ic_divisor is not None:
        quotient = count / profile.segment_count_ic_divisor
        segments = min(
            segment_count_ceiling, max(1, ceil(quotient) if profile.segment_count_ic_round_up else int(quotient))
        )
    return replace(profile, physical_ic_count=count, segment_count=segments)


def _basic_revision_profile(profile: ModelProfile) -> ModelProfile:
    """Grant only independently qualified basic controls, never inherit capability flags."""
    domains = frozenset(
        {ReadDomain.POWER, ReadDomain.BRIGHTNESS, ReadDomain.FIRMWARE, ReadDomain.HARDWARE, ReadDomain.PACT}
    )
    return ModelProfile(
        profile.name,
        support_quality=profile.support_quality,
        confirmation_issue=profile.confirmation_issue,
        allows_legacy_plaintext_marker=profile.allows_legacy_plaintext_marker,
        reconciles_marker_pact=profile.reconciles_marker_pact,
        command_grammar=profile.command_grammar,
        command_ack_grammar=profile.command_ack_grammar,
        command_operations=frozenset({"power", "brightness"}),
        status_grammar=profile.status_grammar,
        setting_grammar=profile.setting_grammar,
        outbound_transform=profile.outbound_transform,
        static_outbound_transform=profile.static_outbound_transform,
        brightness_wire_range=profile.brightness_wire_range,
        profile_identity_fields=profile.profile_identity_fields,
        effect_identity_fields=profile.effect_identity_fields,
        static_recovery_identity_fields=profile.static_recovery_identity_fields,
        scene_identity_fields=profile.scene_identity_fields,
        resolve_profile_before_state_init=profile.resolve_profile_before_state_init,
        profile_pact_dependent=profile.profile_pact_dependent,
        requires_qualified_identity=profile.requires_qualified_identity,
        requires_pact_confirmation=profile.requires_pact_confirmation,
        revision_policy=profile.revision_policy,
        read_domains=domains & profile.read_domains,
        setup_required_read_domains=domains & profile.setup_required_read_domains,
        segment_count=profile.segment_count,
        native_zones=profile.native_zones,
        light_sources=profile.light_sources,
        physical_ic_count=profile.physical_ic_count,
        physical_ic_capacity=profile.physical_ic_capacity,
        segment_count_capacity=profile.segment_count_capacity,
        segment_count_ic_divisor=profile.segment_count_ic_divisor,
        segment_count_ic_round_up=profile.segment_count_ic_round_up,
        connection_idle_timeout=profile.connection_idle_timeout,
        effect_workflows=frozenset(),
    )


def _h612a_revision_policy(context: ModelRevisionContext) -> ModelProfile:
    profile = get_profile(context.model)
    return profile if (context.pact_type, context.pact_code) in _H612A_PACTS else _basic_revision_profile(profile)


def _h6053_revision_policy(context: ModelRevisionContext) -> ModelProfile:
    from .protocol_transforms import h6053_outbound_transform

    pact_type, pact_code = context.pact_type, context.pact_code
    profile = get_profile(context.model)
    known_pact = (pact_type, pact_code) in _STANDARD_PACTS
    legacy_pact = (pact_type, pact_code) == (1, 1)
    wire_range = (20, 254) if legacy_pact else None
    fw, hw = FirmwareVersion.parse(context.firmware), FirmwareVersion.parse(context.hardware)
    modern_static = (
        fw is not None and hw is not None and fw >= FirmwareVersion((1, 0, 12)) and hw >= FirmwareVersion((1,))
    )
    profile = replace(
        profile,
        brightness_wire_range=wire_range,
        outbound_transform=h6053_outbound_transform(
            wire_range, legacy_colour=not modern_static, legacy_music=legacy_pact
        ),
    )
    if fw is None or hw is None:
        basic = _basic_revision_profile(profile)
        return (
            replace(
                basic,
                command_operations=frozenset({"power"}),
                read_domains=basic.read_domains - {ReadDomain.BRIGHTNESS},
                setup_required_read_domains=basic.setup_required_read_domains - {ReadDomain.BRIGHTNESS},
            )
            if not known_pact
            else basic
        )
    uploaded_scenes = fw >= FirmwareVersion((1, 1))
    expanded_music = fw >= FirmwareVersion((1, 8))
    workshop = uploaded_scenes and hw.identity_number() > 0
    assert profile.effect_workflows is not None
    profile = replace(
        profile,
        status_grammar="H6053" if modern_static else "H6053-legacy",
        supports_segment_brightness=modern_static,
        segment_count=12 if modern_static else 2,
        segment_group_size=4 if modern_static else 2,
        light_sources=profile.light_sources
        if modern_static
        else (
            LightSource("left_bar", "left_bar_enabled", (1,)),
            LightSource("right_bar", "right_bar_enabled", (2,)),
        ),
        effect_workflows=profile.effect_workflows
        - (set() if uploaded_scenes else {"layered_scenes"})
        - (set() if workshop else {"advanced", "workshop"}),
        scene_command_versions=None if uploaded_scenes else frozenset(),
        shared_scene_carriers=profile.shared_scene_carriers
        if uploaded_scenes
        else tuple(route for route in profile.shared_scene_carriers if route[0] == "rgb"),
        diy_upload_transport="a1_02" if legacy_pact else "a3",
        a1_diy_prefix=254 if legacy_pact else None,
        music_modes=profile.music_modes if expanded_music else profile.music_modes[:4],
        music_variants=profile.music_variants if expanded_music else profile.music_variants[:4],
    )
    if known_pact:
        return profile
    assert profile.command_operations is not None
    return replace(
        profile,
        command_operations=profile.command_operations & {"power", "static", "scene", "bar_enable", "swap_bars"},
        effect_workflows=frozenset({"native_scenes"}),
        music_modes=(),
        music_variants=(),
        supports_music_color=False,
        music_upload_before_selector=False,
        music_requires_upload_ack=False,
        supports_custom_effects=False,
        supports_multi_layered_effects=False,
        supports_advanced_effects=False,
        advanced_diy_selector=None,
        workshop_scene_selector=None,
        workshop_carriers=(),
        shared_scene_carriers=(),
        diy_upload_transport=None,
        a1_diy_prefix=None,
        read_domains=profile.read_domains - {ReadDomain.BRIGHTNESS},
        setup_required_read_domains=profile.setup_required_read_domains - {ReadDomain.BRIGHTNESS},
    )


def _h6093_revision_policy(context: ModelRevisionContext) -> ModelProfile:
    pact = (context.pact_type, context.pact_code)
    revision = 0 if pact == (1, 1) else 1 if pact in {(1, 2), (2, 1)} else None
    profile = get_profile(context.model)
    sources = tuple(source for source in profile.light_sources if revision != 0 or source.key in {"aurora", "stars"})
    controls = profile.boolean_controls if pact == (2, 1) else profile.boolean_controls - {"dreamview_laser"}
    return replace(profile, projector_control_revision=revision, light_sources=sources, boolean_controls=controls)


def _h6139_revision_policy(context: ModelRevisionContext) -> ModelProfile:
    from .protocol_transforms import whole_rgb_outbound_transform

    profile = get_profile(context.model)
    fw, hw = FirmwareVersion.parse(context.firmware), FirmwareVersion.parse(context.hardware)
    later = (
        context.pact_type is not None
        and context.pact_code is not None
        and context.pact_type >= 10
        and context.pact_code >= 1
    )
    later_music = (context.pact_type, context.pact_code) in {(10, 1), (10, 2)}
    wire_range = None if later else (6, 254)
    hardware_number = hw.identity_number() if hw is not None else 0
    palette_hardware = 20100 <= hardware_number < 20200 or (
        30000 <= hardware_number < 40000 and not 30400 <= hardware_number < 30500
    )
    palette_music = fw is not None and (
        later_music and palette_hardware and fw >= FirmwareVersion((2, 4)) if later else fw >= FirmwareVersion((1, 7))
    )
    music_version = 2 if palette_music else 1 if fw is not None and fw >= FirmwareVersion((1, 3)) else 0
    modes = (
        profile.music_modes
        if palette_music
        else ("dynamic", "soft")
        if later_music or not later and music_version
        else ("dynamic",)
        if not later and fw is not None
        else ()
    )
    authored_programmes = fw is not None and fw >= FirmwareVersion((1, 3))
    uploaded_scenes = later or authored_programmes
    assert profile.effect_workflows is not None
    assert profile.command_operations is not None
    return replace(
        profile,
        effect_identity_fields=frozenset({"fw_version", "hw_version"}) if later else frozenset({"fw_version"}),
        brightness_wire_range=wire_range,
        outbound_transform=whole_rgb_outbound_transform(
            wire_range, legacy_colour=not later, music_version=None if later else music_version
        ),
        static_outbound_transform=whole_rgb_outbound_transform(wire_range, legacy_colour=not later, music_version=None),
        diy_upload_transport="a3" if later or context.pact_type == 10 else "a1_02",
        command_operations=profile.command_operations - (set() if modes else {"music"}),
        effect_workflows=profile.effect_workflows
        - (set() if authored_programmes else {"edited_palette_scenes"})
        - (set() if modes else {"native_music"}),
        selector_only_scene_bits=None if uploaded_scenes else 16,
        authored_palette_scene_selector=198 if authored_programmes else None,
        scene_codes=None if uploaded_scenes else frozenset({4, 5, 7, 8, 9, 16, 10}),
        music_modes=modes,
        music_variants=tuple(
            variant for variant in profile.music_variants if palette_music or variant.mode_code < len(modes)
        ),
    )


def _h6159_revision_policy(context: ModelRevisionContext) -> ModelProfile:
    from .protocol_transforms import whole_rgb_outbound_transform

    profile = get_profile(context.model)
    fw, hw = FirmwareVersion.parse(context.firmware), FirmwareVersion.parse(context.hardware)
    later = (
        context.pact_type is not None
        and context.pact_code is not None
        and context.pact_type >= 2
        and context.pact_code >= 1
    )
    wire_range = None if later else (6, 254)
    if fw is None or hw is None:
        return _basic_revision_profile(
            replace(
                profile,
                brightness_wire_range=wire_range,
                outbound_transform=whole_rgb_outbound_transform(
                    wire_range, legacy_colour=not later, music_version=None if later else 0
                ),
                static_outbound_transform=whole_rgb_outbound_transform(
                    wire_range, legacy_colour=not later, music_version=None
                ),
            )
        )
    hardware_number = hw.identity_number()
    telink = 10000 <= hardware_number < 20000
    palette_hardware = 20100 <= hardware_number < 20200 or (
        30000 <= hardware_number < 40000 and not 30400 <= hardware_number < 30500
    )
    palette_music = palette_hardware and fw >= FirmwareVersion((2, 4)) if later else fw >= FirmwareVersion((1, 7))
    music_version = 2 if palette_music else 1 if fw >= FirmwareVersion((1, 3)) else 0
    modes = profile.music_modes if palette_music else ("dynamic", "soft") if music_version else ("dynamic",)
    uploaded_scenes = fw >= FirmwareVersion((1, 3))
    mixed = fw >= FirmwareVersion((1, 2, 3))
    assert profile.effect_workflows is not None
    return replace(
        profile,
        brightness_wire_range=wire_range,
        outbound_transform=whole_rgb_outbound_transform(
            wire_range, legacy_colour=not later, music_version=None if later else music_version
        ),
        static_outbound_transform=whole_rgb_outbound_transform(wire_range, legacy_colour=not later, music_version=None),
        diy_upload_transport="a3" if later or not telink else "a1_02",
        supports_multi_layered_effects=mixed,
        effect_workflows=profile.effect_workflows
        - (set() if mixed else {"multi"})
        - (set() if uploaded_scenes else {"edited_palette_scenes"}),
        selector_only_scene_bits=None if uploaded_scenes else 16,
        authored_palette_scene_selector=198 if uploaded_scenes else None,
        scene_codes=None if uploaded_scenes else frozenset({0, 1, 4, 5, 7, 8, 9}),
        music_modes=modes,
        music_variants=tuple(
            variant for variant in profile.music_variants if palette_music or variant.mode_code < len(modes)
        ),
    )


def _h6182_revision_policy(context: ModelRevisionContext) -> ModelProfile:
    from .protocol_transforms import whole_rgb_outbound_transform

    profile = get_profile(context.model)
    fw, hw = FirmwareVersion.parse(context.firmware), FirmwareVersion.parse(context.hardware)
    later = (
        context.pact_type is not None
        and context.pact_code is not None
        and context.pact_type >= 2
        and context.pact_code >= 1
    )
    telink = hw is None or 10000 <= hw.identity_number() < 20000
    wire_range = (20, 254) if telink else None
    profile = replace(
        profile,
        status_grammar="H6182-modern" if later else "H6182",
        profile_identity_fields=profile.profile_identity_fields if later else frozenset({"hw_version"}),
        brightness_wire_range=wire_range,
        outbound_transform=whole_rgb_outbound_transform(
            wire_range, legacy_colour=not later, music_version=None if later else 0
        ),
        static_outbound_transform=whole_rgb_outbound_transform(wire_range, legacy_colour=not later, music_version=None),
    )
    if hw is None or later and fw is None:
        basic = _basic_revision_profile(profile)
        return (
            replace(
                basic,
                command_operations=frozenset({"power"}),
                read_domains=basic.read_domains - {ReadDomain.BRIGHTNESS},
            )
            if hw is None
            else basic
        )
    hardware_number = hw.identity_number()
    palette_hardware = 20100 <= hardware_number < 20200 or (
        30000 <= hardware_number < 40000 and not 30400 <= hardware_number < 30500
    )
    palette_music = later and palette_hardware and fw is not None and fw >= FirmwareVersion((2, 4))
    modes = profile.music_modes if palette_music else ("dynamic", "soft") if later else ("dynamic",)
    uploaded_scenes = not telink and (
        not later or context.pact_code != 1 or fw is not None and fw >= FirmwareVersion((1, 3))
    )
    local_scenes = (
        profile.local_scenes
        if telink
        else (
            (0, "Sunrise"),
            (1, "Sunset"),
            (4, "Movie"),
            (5, "Date"),
            (7, "Romantic"),
            (8, "Blink"),
            (9, "Candle"),
        )
    )
    assert profile.effect_workflows is not None
    return replace(
        profile,
        diy_upload_transport="a3" if later else "a1_02",
        effect_workflows=profile.effect_workflows - (set() if uploaded_scenes else {"edited_palette_scenes"}),
        selector_only_scene_bits=None if uploaded_scenes else 8 if telink else 16,
        authored_palette_scene_selector=198 if uploaded_scenes else None,
        local_scenes=local_scenes,
        scene_codes=None if uploaded_scenes else frozenset(code for code, _name in local_scenes),
        music_modes=modes,
        music_variants=tuple(
            variant for variant in profile.music_variants if palette_music or variant.mode_code < len(modes)
        ),
        music_readback_ambiguous=later,
    )


def _h6181_revision_policy(context: ModelRevisionContext) -> ModelProfile:
    profile = get_profile(context.model)
    later = (
        context.pact_type is not None
        and context.pact_code is not None
        and context.pact_type >= 10
        and context.pact_code >= 1
    )
    if not later:
        legacy_colour = context.firmware == "1.03.00" and context.hardware == "1.00.03"
        return replace(
            profile,
            status_grammar="H6181",
            brightness_wire_range=(20, 254),
            outbound_transform=_h6181_legacy_colour_wire if legacy_colour else _h6181_wire,
            diy_upload_transport="a1_02",
            music_modes=(),
            music_variants=(),
            scene_codes=frozenset({0, 1, 4, 5, 7, 8, 9}),
            selector_only_scene_bits=8,
        )
    fw = FirmwareVersion.parse(context.firmware)
    hw = FirmwareVersion.parse(context.hardware)
    percentage = (context.pact_type, context.pact_code) in {(10, 1), (10, 2)}
    uploaded_scenes = context.pact_code != 1 or fw is not None and fw >= FirmwareVersion((1, 3))
    hardware_number = hw.identity_number() if hw is not None else 0
    palette_hardware = 20100 <= hardware_number < 20200 or (
        30000 <= hardware_number < 40000 and not 30400 <= hardware_number < 30500
    )
    palette_music = palette_hardware and fw is not None and fw >= FirmwareVersion((2, 4))
    modes = profile.music_modes if palette_music else ("dynamic", "soft")
    return replace(
        profile,
        static_identity_fields=frozenset(),
        brightness_wire_range=None if percentage else (20, 254),
        outbound_transform=None if percentage else _h6181_wire,
        music_modes=modes if percentage else (),
        music_variants=tuple(
            variant
            for variant in profile.music_variants
            if percentage and (palette_music or variant.mode_code in (0, 1))
        ),
        selector_only_scene_bits=None if uploaded_scenes else 16,
        scene_codes=None if uploaded_scenes else frozenset({0, 1, 4, 5, 7, 8, 9, 10, 16}),
    )


def _h60b0_revision_policy(context: ModelRevisionContext) -> ModelProfile:
    profile = get_profile(context.model)
    if context.pact_type == 1 and context.pact_code in {1, 2, 3}:
        return replace(
            profile,
            native_effect_revision=context.pact_code,
            exclusive_source_groups=(frozenset({"top_enabled", "bottom_enabled"}),) if context.pact_code == 1 else (),
        )
    return _basic_revision_profile(profile)


def _h705a_revision_policy(context: ModelRevisionContext) -> ModelProfile:
    profile = get_profile(context.model)
    assert profile.command_operations is not None
    installation = (
        {"refresh_ic"}
        if (context.pact_type, context.pact_code) == (1, 1)
        else {"configured_strings"}
        if (context.pact_type, context.pact_code) == (1, 2)
        else set()
    )
    return replace(
        profile,
        command_operations=(profile.command_operations - {"configured_strings", "refresh_ic"}) | installation,
        supports_ic_refresh="refresh_ic" in installation,
        configured_string_counts=profile.configured_string_counts if "configured_strings" in installation else (),
    )


def _h605c_revision_policy(context: ModelRevisionContext) -> ModelProfile:
    profile = get_profile(context.model)
    if (context.pact_type, context.pact_code) == (1, 2):
        return replace(
            profile,
            dreamview_grammar="H6099",
            dreamview_operations=profile.dreamview_operations | {"same_brightness"},
            dreamview_reads=profile.dreamview_reads | {"same_brightness"},
            dreamview_max_sub_devices=7,
            dreamview_requires_group_ack=False,
        )
    if (context.pact_type, context.pact_code) != (1, 1):
        return replace(profile, dreamview_operations=frozenset(), dreamview_reads=frozenset())
    return profile


def _standard_pacts_revision_policy(context: ModelRevisionContext) -> ModelProfile:
    profile = get_profile(context.model)
    return profile if (context.pact_type, context.pact_code) in _STANDARD_PACTS else _basic_revision_profile(profile)


def _h607c_revision_policy(context: ModelRevisionContext) -> ModelProfile:
    profile = get_profile(context.model)
    known = (context.pact_type, context.pact_code) in _STANDARD_PACTS or (
        context.pact_type,
        context.pact_code,
    ) == (2, 2)
    return profile if known else _basic_revision_profile(profile)


def _h8604_revision_policy(context: ModelRevisionContext) -> ModelProfile:
    profile = get_profile(context.model)
    return (
        profile
        if (context.pact_type, context.pact_code) in {(1, 1), (2, 1), (3, 1)}
        else _basic_revision_profile(profile)
    )


def _h60a_revision_profile(
    context: ModelRevisionContext,
    *,
    segmented_firmware: str,
    supports_segment_color_temperature: bool,
    native_controls: bool,
) -> ModelProfile:
    profile = get_profile(context.model)
    pact = (context.pact_type, context.pact_code)
    if native_controls and not (
        pact in _H60A6_NATIVE_CONTROL_PACTS
        or (*pact, context.hardware, context.firmware)
        == (None, None, _H60A_SEGMENTED_HARDWARE, _H60A6_SEGMENTED_FIRMWARE)
    ):
        profile = replace(profile, boolean_controls=frozenset(), supports_power_on_behaviour=False)
    hw = FirmwareVersion.parse(context.hardware)
    if not native_controls and hw is not None and hw.identity_number() < 10403:
        profile = replace(profile, color_temp_range=KELVIN_RANGE_2200_6500)
    segmented = (
        pact in _STANDARD_PACTS
        if not native_controls
        else context.pact_type == 1 and type(context.pact_code) is int and context.pact_code >= 2
    )
    if pact == (None, None):
        segmented = (context.hardware, context.firmware) == (_H60A_SEGMENTED_HARDWARE, segmented_firmware)
    if segmented:
        return replace(
            profile,
            supports_rgb=True,
            supports_color_temperature=True,
            supports_segment_writes=True,
            supports_segment_color_temperature=supports_segment_color_temperature,
            read_domains=profile.read_domains | {ReadDomain.SEGMENTS},
        )
    return profile


def _h60a1_revision_policy(context: ModelRevisionContext) -> ModelProfile:
    return _h60a_revision_profile(
        context,
        segmented_firmware=_H60A1_SEGMENTED_FIRMWARE,
        supports_segment_color_temperature=False,
        native_controls=False,
    )


def _h60a6_revision_policy(context: ModelRevisionContext) -> ModelProfile:
    profile = _h60a_revision_profile(
        context,
        segmented_firmware=_H60A6_SEGMENTED_FIRMWARE,
        supports_segment_color_temperature=True,
        native_controls=True,
    )
    if (context.pact_type, context.pact_code) == (1, 1):
        from .protocol_transforms import h60a6_legacy_outbound_transform

        return replace(
            profile,
            segment_count=1,
            supports_rgb=True,
            supports_color_temperature=True,
            outbound_transform=h60a6_legacy_outbound_transform,
        )
    return profile


def _h61f5_revision_policy(context: ModelRevisionContext) -> ModelProfile:
    profile = get_profile(context.model)
    return (
        replace(profile, color_temp_range=KELVIN_RANGE_1000_10000)
        if (context.pact_type, context.pact_code) == (4, 1)
        else profile
    )


def _h617a_revision_policy(context: ModelRevisionContext) -> ModelProfile:
    fw, hw = FirmwareVersion.parse(context.firmware), FirmwareVersion.parse(context.hardware)
    modern_firmware = fw is not None and fw >= FirmwareVersion((1, 6))
    return replace(
        get_profile(context.model),
        rgbic_scene_v0=not modern_firmware or hw is None or hw < FirmwareVersion((1, 0, 3)),
        scene_command_versions=frozenset({0, 1})
        if modern_firmware and hw is not None and hw >= FirmwareVersion((1, 0, 2))
        else frozenset({0}),
    )


def _h619a_revision_policy(context: ModelRevisionContext) -> ModelProfile:
    from .protocol_transforms import rgb_only_segment_query_transform

    fw, hw = FirmwareVersion.parse(context.firmware), FirmwareVersion.parse(context.hardware)
    modern = fw is not None and hw is not None and fw >= FirmwareVersion((1, 6)) and hw >= FirmwareVersion((1, 0, 2))
    profile = get_profile(context.model)
    return replace(
        profile,
        status_grammar="H619A" if modern else "H619A-legacy",
        segment_group_size=3 if modern else 4,
        status_query_transform=None if modern else rgb_only_segment_query_transform,
        rgbic_scene_v0=not modern,
        read_domains=profile.read_domains
        if fw is not None and hw is not None
        else profile.read_domains - {ReadDomain.SEGMENTS},
    )


def _h618a_revision_policy(context: ModelRevisionContext) -> ModelProfile:
    from .protocol_transforms import rgb_only_segment_query_transform

    fw, hw = FirmwareVersion.parse(context.firmware), FirmwareVersion.parse(context.hardware)
    modern = fw is not None and hw is not None and fw >= FirmwareVersion((1, 6)) and hw >= FirmwareVersion((1, 0, 2))
    modern_readback = modern or (
        (context.pact_type, context.pact_code) == (3, 1) and hw is not None and hw >= FirmwareVersion((3,))
    )
    pact3_readback = modern_readback and not modern and (context.pact_type, context.pact_code) == (3, 1)
    profile = get_profile(context.model)
    return replace(
        profile,
        status_grammar="H618A-pact3" if pact3_readback else "H618A" if modern else "H618A-legacy",
        segment_group_size=4 if pact3_readback or not modern_readback else 3,
        status_query_transform=None if modern_readback else rgb_only_segment_query_transform,
        rgbic_scene_v0=not modern,
        scene_command_versions=frozenset({0, 1}) if modern else frozenset({0}),
        read_domains=profile.read_domains
        if fw is not None and hw is not None
        else profile.read_domains - {ReadDomain.SEGMENTS},
    )


def _h6199_revision_policy(context: ModelRevisionContext) -> ModelProfile:
    pact = (context.pact_type, context.pact_code)
    profile = H6199_PACT1_PROFILE if pact == (1, 1) else get_profile(context.model)
    if pact not in _H6199_DREAMVIEW_PACTS:
        return replace(profile, dreamview_operations=frozenset(), dreamview_reads=frozenset())
    fw, hw = FirmwareVersion.parse(context.firmware), FirmwareVersion.parse(context.hardware)
    if fw is None or hw is None or fw < FirmwareVersion((1, 9)) or hw < FirmwareVersion((3, 2, 1)):
        if "same_brightness" not in profile.dreamview_operations:
            return profile
        return replace(
            profile,
            dreamview_operations=profile.dreamview_operations - {"same_brightness"},
            dreamview_reads=profile.dreamview_reads - {"same_brightness"},
        )
    if "same_brightness" not in profile.dreamview_operations:
        return replace(
            profile,
            dreamview_operations=profile.dreamview_operations | {"same_brightness"},
            dreamview_reads=profile.dreamview_reads | {"same_brightness"},
        )
    return profile


def _h6072_revision_policy(context: ModelRevisionContext) -> ModelProfile:
    return _h6072_profile(context.pact_type, context.pact_code, context.firmware, context.hardware)


def _h6076_revision_policy(context: ModelRevisionContext) -> ModelProfile:
    return _h6076_profile(context.pact_type, context.pact_code, context.firmware)


def _h6179_revision_policy(context: ModelRevisionContext) -> ModelProfile:
    profile = get_profile(context.model)
    if context.pact_type is None or context.pact_code is None:
        return replace(
            profile,
            diy_upload_transport=None,
            supports_custom_effects=False,
            supports_multi_layered_effects=False,
            boolean_controls=frozenset(),
            restarting_boolean_controls=frozenset(),
        )
    if context.pact_type >= 10 and context.pact_code >= 1:
        return replace(
            profile,
            diy_upload_transport="a3",
            boolean_controls=frozenset(),
            restarting_boolean_controls=frozenset(),
        )
    return profile


def _h6117_revision_policy(context: ModelRevisionContext) -> ModelProfile:
    return _h6117_profile(context.pact_type, context.pact_code, context.firmware, context.hardware)


def _h6125_revision_policy(context: ModelRevisionContext) -> ModelProfile:
    return _h6125_profile(context.pact_type, context.pact_code, context.firmware, context.hardware)


def _h6127_revision_policy(context: ModelRevisionContext) -> ModelProfile:
    return _h6127_profile(context.pact_type, context.pact_code, context.firmware, context.hardware)


def _h6102_revision_policy(context: ModelRevisionContext) -> ModelProfile:
    from .h6102_capabilities import resolve_h6102_capabilities

    return resolve_h6102_capabilities(
        context.firmware,
        context.firmware_source
        if context.firmware_source is not None
        else "ble"
        if context.firmware is not None
        else None,
        hardware=context.hardware,
        pact_type=context.pact_type,
        pact_code=context.pact_code,
    ).profile


_MODEL_REVISION_POLICIES: Mapping[str, Callable[[ModelRevisionContext], ModelProfile]] = {
    "h612a": _h612a_revision_policy,
    "h6053": _h6053_revision_policy,
    "h6093": _h6093_revision_policy,
    "h6139": _h6139_revision_policy,
    "h6159": _h6159_revision_policy,
    "h6182": _h6182_revision_policy,
    "h6181": _h6181_revision_policy,
    "h60b0": _h60b0_revision_policy,
    "h705a": _h705a_revision_policy,
    "h605c": _h605c_revision_policy,
    "h8604": _h8604_revision_policy,
    "standard_pacts": _standard_pacts_revision_policy,
    "h607c": _h607c_revision_policy,
    "h60a1": _h60a1_revision_policy,
    "h60a6": _h60a6_revision_policy,
    "h61f5": _h61f5_revision_policy,
    "h617a": _h617a_revision_policy,
    "h619a": _h619a_revision_policy,
    "h618a": _h618a_revision_policy,
    "h6199": _h6199_revision_policy,
    "h6072": _h6072_revision_policy,
    "h6076": _h6076_revision_policy,
    "h6179": _h6179_revision_policy,
    "h6117": _h6117_revision_policy,
    "h6125": _h6125_revision_policy,
    "h6127": _h6127_revision_policy,
    "h6102": _h6102_revision_policy,
}


def device_profile(
    model: str,
    pact_type: int | None,
    pact_code: int | None,
    *,
    firmware: str | None = None,
    firmware_source: DeviceIdentitySource | None = None,
    hardware: str | None = None,
) -> ModelProfile:
    """Resolve exact-product capabilities from its declared revision policy."""
    profile = get_profile(model)
    if model not in MODEL_PROFILES or profile.revision_policy is None:
        return profile
    policy = _MODEL_REVISION_POLICIES.get(profile.revision_policy)
    if policy is None:
        raise ValueError("unknown model revision policy")
    return policy(
        ModelRevisionContext(
            model=model,
            pact_type=pact_type,
            pact_code=pact_code,
            firmware=firmware,
            firmware_source=firmware_source,
            hardware=hardware,
        )
    )


def light_unique_id(address: str, source: str | None = None) -> str:
    base = address.replace(":", "").lower()
    return f"{base}_{source}" if source is not None else base


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
    if resolved is None:
        return None
    return MODEL_PROFILES[resolved].protocol_identity or resolved


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
    if profile.supports_custom_effects or profile.supports_segments and profile.supports_rgb:
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
