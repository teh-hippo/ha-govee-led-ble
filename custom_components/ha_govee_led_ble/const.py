"""Constants for HA Govee LED BLE."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any

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
    EFFECT_CATEGORY_EFFECTS: frozenset({"h617a_painted", "h617a_single", "h6179_single_diy", "palette_diy"}),
    EFFECT_CATEGORY_MULTI_LAYERED: frozenset({"h617a_multi", "h6179_mixed_diy"}),
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
class ModelProfile:
    name: str
    support_quality: SupportQuality = SupportQuality.EXPERIMENTAL
    wire_model: str | None = None
    read_domains: frozenset[ReadDomain] = frozenset()
    setup_required_read_domains: frozenset[ReadDomain] = frozenset()
    supports_rgb: bool = False
    supports_color_temperature: bool = False
    min_color_temp_kelvin: int = 2000
    max_color_temp_kelvin: int = 9000
    supports_custom_effects: bool = False
    supports_scenes: bool = False
    supports_video_mode: bool = False
    supports_video_sound_effects: bool = False
    supports_advanced_effects: bool = False
    supports_multi_layered_effects: bool = False
    supports_white_balance: bool = False
    video_white_balance_default: int = 17
    supports_relative_brightness: bool = False
    supports_blank_screen: bool = False
    music_modes: tuple[str, ...] = ()
    music_sensitivity_min: int = 0
    music_sensitivity_max: int = 99
    supports_music_color: bool = False
    supports_white_brightness: bool = False
    static_readback_echoes_color: bool = False
    whole_device_mask: int = 0
    segment_count: int = 0
    segment_group_size: int = 0
    supports_segment_writes: bool = False
    connection_idle_timeout: float | None = None
    scene_catalogue_sku: str | None = None
    legacy_scene_catalogue_sku: str | None = None
    selector_only_scene_bits: int | None = None
    advanced_scene_carrier: tuple[int, int] | None = None
    default_effect_families_override: frozenset[str] | None = None
    effect_readback: str = "none"

    def __post_init__(self) -> None:
        if not self.setup_required_read_domains <= self.read_domains:
            raise ValueError("setup-required read domains must also be readable")
        if self.selector_only_scene_bits is not None and not 1 <= self.selector_only_scene_bits <= 16:
            raise ValueError("selector-only scene width must be from 1 to 16 bits")

    def can_read(self, domain: ReadDomain) -> bool:
        return domain in self.read_domains

    @property
    def requires_notifications(self) -> bool:
        return bool(self.read_domains)

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
    wire_model="H617A",
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
    music_modes=tuple(MUSIC_MODE_SLUGS),
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
    "H617A": _H617A_PROFILE,
    "H617E": replace(
        _H617A_PROFILE,
        name="H617E LED Strip",
        support_quality=SupportQuality.COMPATIBLE,
        scene_catalogue_sku="H617E",
        legacy_scene_catalogue_sku="H617A",
        advanced_scene_carrier=(29884, 41599),
    ),
    "H6076": ModelProfile(
        "H6076 Lyra Floor Lamp",
        support_quality=SupportQuality.PARTIAL,
        wire_model="H617A",
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
    "H6179": ModelProfile(
        "H6179 RGB TV Backlight",
        support_quality=SupportQuality.EXPERIMENTAL,
        wire_model="H6179",
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
        scene_catalogue_sku="H6179",
        selector_only_scene_bits=8,
        effect_readback="diy_code_only",
    ),
    "H6199": ModelProfile(
        "H6199 DreamView T1",
        support_quality=SupportQuality.SUPPORTED,
        wire_model="H6199",
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
                ReadDomain.DISPLAY_SETTING,
                ReadDomain.RELATIVE_BRIGHTNESS,
            }
        ),
        supports_rgb=True,
        supports_color_temperature=True,
        supports_custom_effects=True,
        supports_scenes=True,
        supports_video_mode=True,
        supports_video_sound_effects=True,
        # These independently captured video registers have byte-exact builders.
        supports_white_balance=True,
        supports_relative_brightness=True,
        supports_blank_screen=True,
        music_modes=_H6199_MUSIC_MODES,
        music_sensitivity_min=1,
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


def resolve_model(model: str) -> str | None:
    candidate = model.strip().upper()
    return candidate if candidate in MODEL_PROFILES else None


def model_from_ble_name(name: str) -> str | None:
    match = _BLE_MODEL_PATTERN.search(name)
    return resolve_model(match.group(1)) if match else None


def protocol_model(model: str) -> str | None:
    resolved = resolve_model(model)
    return "H617A" if resolved in {"H617A", "H617E"} else resolved


def wire_model(model: str) -> str | None:
    resolved = resolve_model(model)
    return MODEL_PROFILES[resolved].wire_model if resolved is not None else None


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


def supported_effect_categories(model: str) -> tuple[str, ...]:
    profile = get_profile(model)
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
