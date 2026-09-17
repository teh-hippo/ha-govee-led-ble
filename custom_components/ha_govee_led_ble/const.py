"""Constants for HA Govee LED BLE."""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any

from .h6199_calibration import WHITE_BALANCE_POSITIONS
from .music_semantics import H617A_MUSIC_VARIANTS, H617E_MUSIC_VARIANTS, H6099_MUSIC_VARIANTS, MusicVariant

DOMAIN = "ha_govee_led_ble"
CONF_MODEL = "model"
CONF_EFFECT_CATEGORIES = "effect_categories"
CONF_EFFECT_FAMILIES = "effect_families"
CONF_PREFIX_EFFECT_NAMES = "prefix_effect_names"
CONF_ALWAYS_INCLUDE_CUSTOM_EFFECTS = "always_include_custom_effects"
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
    EFFECT_CATEGORY_EFFECTS: frozenset({"h617a_painted", "h617a_single", "palette_diy"}),
    EFFECT_CATEGORY_MULTI_LAYERED: frozenset({"h617a_multi"}),
    EFFECT_CATEGORY_REACTIVE: frozenset({"music_profile"}),
    EFFECT_CATEGORY_ADVANCED: frozenset({"advanced", "workshop"}),
}
_BLE_MODEL_PATTERN = re.compile(r"(?:ihoment|Govee|GBK|GVH)_(H[0-9A-Z]{4})(?:_|$)", re.IGNORECASE)


class SupportQuality(StrEnum):
    EXPERIMENTAL = "experimental"
    PARTIAL = "partial"
    COMPATIBLE = "compatible"
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
    INSTALLATION_DIRECTION = "installation_direction"
    CAMERA_HEALTH = "camera_health"
    OTHER = "other"


_IDENTITY_READ_DOMAINS = frozenset(
    {
        ReadDomain.FIRMWARE,
        ReadDomain.HARDWARE,
        ReadDomain.SUBORDINATE_20,
        ReadDomain.SUBORDINATE_21,
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
    # None retains the grammar's shipped operations; a set restricts physical writes.
    command_operations: frozenset[str] | None = None
    status_grammar: str | None = None
    outbound_transform: Callable[[bytes], bytes] | None = None
    # Effect semantics require evidence independent of basic command compatibility.
    effect_grammar: str | None = None
    video_grammar: str | None = None
    dreamview_grammar: str | None = None
    dreamview_operations: frozenset[str] = frozenset()
    dreamview_reads: frozenset[str] = frozenset()
    dreamview_max_sub_devices: int = 0
    video_firmware_conditions: tuple[VideoFirmwareCondition, ...] = ()
    # Exact-product revision policy, independent of compatible wire grammars.
    video_revision_policy: str | None = None
    read_domains: frozenset[ReadDomain] = frozenset()
    setup_required_read_domains: frozenset[ReadDomain] = frozenset()
    supports_rgb: bool = False
    supports_installation_direction: bool = False
    supports_color_temperature: bool = False
    min_color_temp_kelvin: int = 2000
    max_color_temp_kelvin: int = 9000
    supports_custom_effects: bool = False
    supports_scenes: bool = False
    supports_video_mode: bool = False
    video_modes: tuple[str, ...] = ()
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
    music_modes: tuple[str, ...] = ()
    music_variants: tuple[MusicVariant, ...] = ()
    music_upload_before_selector: bool = False
    music_requires_upload_ack: bool = False
    # Physical IC count is independent of logical segment_count. None means unknown.
    physical_ic_count: int | None = None
    music_sensitivity_min: int = 0
    music_sensitivity_max: int = 99
    supports_music_color: bool = False
    supports_white_brightness: bool = False
    static_readback_echoes_color: bool = False
    static_readback_kelvin: bool = False
    whole_device_mask: int = 0
    segment_count: int = 0
    segment_group_size: int = 0
    supports_segment_writes: bool = False
    connection_idle_timeout: float | None = None
    scene_catalogue_sku: str | None = None
    legacy_scene_catalogue_sku: str | None = None
    advanced_scene_carrier: tuple[int, int] | None = None
    default_effect_families_override: frozenset[str] | None = None
    effect_readback: str = "none"

    def __post_init__(self) -> None:
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

    def can_read(self, domain: ReadDomain) -> bool:
        return domain in self.read_domains

    def validate_video_saturation(self, value: int) -> None:
        if type(value) is not int or not self.video_saturation_min <= value <= 100:
            raise ValueError(f"video saturation must be from {self.video_saturation_min} to 100")

    @property
    def requires_notifications(self) -> bool:
        return bool(self.read_domains or self.dreamview_reads)

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
    connection_idle_timeout=3.0,
    scene_catalogue_sku="H617A",
    advanced_scene_carrier=(1013, 11836),
    effect_readback="diy_code_only",
    # supports_white_brightness stays false because static subcommand 0x02 is segment-relative
    # brightness, not the level of a white colour-temperature mode. It compounds with master
    # brightness and is exposed through set_segment_brightness, including all-segment writes;
    # the aa a5 groups provide its per-segment readback.
)


MODEL_PROFILES: dict[str, ModelProfile] = {
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
        scene_catalogue_sku="H6099",
        supports_custom_effects=True,
        default_effect_families_override=frozenset({EFFECT_FAMILY_VIDEO}),
        # Ordinary DIY uses Sub4Diy, not an H6199 scene or Workshop carrier.
        effect_readback="diy_code_only",
    ),
    "H617A": _H617A_PROFILE,
    "H617E": replace(
        _H617A_PROFILE,
        name="H617E LED Strip",
        music_variants=H617E_MUSIC_VARIANTS,
        music_upload_before_selector=False,
        music_requires_upload_ack=False,
        support_quality=SupportQuality.COMPATIBLE,
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
    "H6076": ModelProfile(
        "H6076 Lyra Floor Lamp",
        support_quality=SupportQuality.PARTIAL,
        command_grammar="H617A",
        status_grammar="H617A",
        read_domains=frozenset(
            {
                ReadDomain.POWER,
                ReadDomain.BRIGHTNESS,
                ReadDomain.FIRMWARE,
                ReadDomain.HARDWARE,
            }
        ),
        setup_required_read_domains=frozenset({ReadDomain.POWER, ReadDomain.BRIGHTNESS}),
        supports_rgb=True,
        supports_color_temperature=True,
        min_color_temp_kelvin=2700,
        max_color_temp_kelvin=6500,
        whole_device_mask=0x007F,
        scene_catalogue_sku="H6076",
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
        scene_catalogue_sku="H6199",
        advanced_scene_carrier=(29884, 41599),
        default_effect_families_override=frozenset({EFFECT_FAMILY_VIDEO}),
        effect_readback="scene_selector_for_user_effects",
    ),
}

UNSUPPORTED_PROFILE = ModelProfile("Unsupported Govee device")

H6199_PACT1_PROFILE = ModelProfile(
    "H6199 Pact 1 (power only)",
    support_quality=SupportQuality.PARTIAL,
    command_grammar="H6199",
    command_operations=frozenset({"power"}),
    status_grammar="H6199",
    read_domains=frozenset({ReadDomain.POWER, ReadDomain.FIRMWARE, ReadDomain.HARDWARE}),
    setup_required_read_domains=frozenset({ReadDomain.POWER}),
)


def device_profile(model: str, pact_type: int | None, pact_code: int | None) -> ModelProfile:
    """Restrict positively identified Pact 1 only; unknown is not proof of Pact 2."""
    if model == "H6199" and (pact_type, pact_code) == (1, 1):
        return H6199_PACT1_PROFILE
    return get_profile(model)


def resolve_model(model: str) -> str | None:
    candidate = model.strip().upper()
    return candidate if candidate in MODEL_PROFILES else None


def model_from_ble_name(name: str) -> str | None:
    match = _BLE_MODEL_PATTERN.search(name)
    return resolve_model(match.group(1)) if match else None


def protocol_model(model: str) -> str | None:
    """Resolve legacy runtime policy identity, not effect-grammar compatibility."""
    resolved = resolve_model(model)
    return "H617A" if resolved in {"H617A", "H617E"} else resolved


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
