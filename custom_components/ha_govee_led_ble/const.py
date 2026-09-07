"""Constants for HA Govee LED BLE."""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any

from .h6199_calibration import WHITE_BALANCE_POSITIONS
from .music_semantics import H617A_MUSIC_VARIANTS, MusicVariant

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
    IC_SEGMENT_COUNT = "ic_segment_count"
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
    status_grammar: str | None = None
    outbound_transform: Callable[[bytes], bytes] | None = None
    # Effect semantics require evidence independent of basic command compatibility.
    effect_grammar: str | None = None
    video_grammar: str | None = None
    video_firmware_conditions: tuple[VideoFirmwareCondition, ...] = ()
    read_domains: frozenset[ReadDomain] = frozenset()
    setup_required_read_domains: frozenset[ReadDomain] = frozenset()
    supports_rgb: bool = False
    supports_color_temperature: bool = False
    min_color_temp_kelvin: int = 2000
    max_color_temp_kelvin: int = 9000
    supports_custom_effects: bool = False
    supports_scenes: bool = False
    supports_video_mode: bool = False
    video_modes: tuple[str, ...] = ()
    supports_video_capture_region: bool = False
    supports_video_saturation: bool = False
    supports_video_sound_effects: bool = False
    supports_advanced_effects: bool = False
    supports_multi_layered_effects: bool = False
    supports_white_balance: bool = False
    video_white_balance_default: int = 17
    video_white_balance_representation: str = "position"
    video_white_balance_min: int = 1
    video_white_balance_max: int = 20
    video_white_balance_calibration: tuple[tuple[int, ...], ...] = ()
    video_brightness_zones: tuple[str, ...] = ()
    supports_relative_brightness: bool = False
    supports_blank_screen: bool = False
    music_modes: tuple[str, ...] = ()
    music_variants: tuple[MusicVariant, ...] = ()
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
    # Prefer the segment count the device reports over the one declared above.  A strip
    # that has been cut to length reports its own, and the declared value then describes
    # the product rather than the installation.
    segment_count_from_ic_probe: bool = False
    supports_segment_writes: bool = False
    connection_idle_timeout: float | None = None
    scene_catalogue_sku: str | None = None
    legacy_scene_catalogue_sku: str | None = None
    advanced_scene_carrier: tuple[int, int] | None = None
    default_effect_families_override: frozenset[str] | None = None
    effect_readback: str = "none"

    def __post_init__(self) -> None:
        if self.physical_ic_count is not None and (
            type(self.physical_ic_count) is not int or self.physical_ic_count <= 0
        ):
            raise ValueError("physical IC count must be a positive integer or unknown")
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
        ) and not self.supports_video_mode:
            raise ValueError("video settings require video-mode support")
        if self.supports_white_balance:
            if self.video_white_balance_representation not in {"position", "scalar"}:
                raise ValueError("unknown white-balance representation")
            if not self.video_white_balance_min <= self.video_white_balance_default <= self.video_white_balance_max:
                raise ValueError("white-balance default is outside its range")
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


# The vendor registry.  Ids are the vendor's own, not an index.  A model exposes only the
# subset its device accepts, so every profile lists its modes rather than deriving them.
MUSIC_MODE_SLUGS: dict[str, int] = {
    "energetic": 0x05,
    "rhythm": 0x03,
    "spectrum": 0x04,
    "rolling": 0x06,
    "separation": 0x32,  # fenli
    "hopping": 0x33,  # yuedong
    "piano_keys": 0x34,  # gangqinjian
    "fountain": 0x35,  # duiji
    "day_and_night": 0x37,  # zhouye
    "bloom": 0x30,  # zhanfang
    "shiny": 0x31,  # cuican
    # NOT ALL EQUALLY EVIDENCED, and the difference matters when a profile decides what to
    # claim.  0x84, 0x85, 0x92 and 0xA3 were written by the vendor app itself and are captured.
    # 0x53, 0x55, 0x65 and 0x78 come from the app's own registry and from sweeping a device,
    # and the single device swept REFUSED all four -- see MUSIC_MODE_IDS_REFUSED_BY_H61F5.
    # They are named here because the registry names them; naming an id is not evidence that
    # any particular device accepts it, which is the profile's question, not the registry's.
    #
    # They sit far outside the 0x30-0x3b block that an earlier pass assumed was the whole
    # space -- the registry actually runs 0x16-0xab.
    #
    # Appended rather than merged into the run above, because this dict's insertion order is
    # MUSIC_MODES' display order and reordering it would shuffle an existing user's effect list.
    "flowing_light": 0x53,  # liuguang -> new_scenes_liuguang
    "color_painting": 0x55,  # caihui -> b2light_music_caihui
    "meteor": 0x65,  # meteor_shower
    "windmill": 0x78,  # windmill_606a
    "splash": 0x84,  # water_flower -> b2light_music_water_flower
    "spring": 0x85,  # spring -> b2light_music_spring
    # Swept from an H1A42 strip on 2026-08-27. Neither id has an entry in
    # IMusicEffectStatic.parseSubStr4New, which is why an earlier read of that file alone would
    # have called them unnamed. SubMusicModeConfig carries the labels instead, bound to the id
    # through each maker's default argument: makeLianYi$default defaults to
    # RhyRule.op_type_trigger_finish_clean (146 = 0x92) and its maker passes
    # R.string.b2light_scenes_ripple; makeYouDong$default defaults to -93 (0xa3) and passes
    # R.string.app_move_about. strings.xml renders those "Ripple" and "Orbit" -- transcribed.
    "ripple": 0x92,  # h70CX_multi_value_sub_lianyi -> b2light_scenes_ripple
    "orbit": 0xA3,  # multi_value_sub_youdong -> app_move_about
}

MUSIC_MODE_IDS_ACCEPTED_BY_H61F5: tuple[int, ...] = (
    0x03, 0x04, 0x05, 0x06, 0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x37, 0x84, 0x85, 0x92, 0xA3,
)  # fmt: skip
MUSIC_MODE_IDS_REFUSED_BY_H61F5: tuple[int, ...] = (0x53, 0x55, 0x65, 0x78)

_H66A0_MUSIC_MODES = (
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
    "flowing_light",
    "color_painting",
    "meteor",
    "windmill",
    "splash",
    "spring",
)

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
        music_variants=tuple(
            replace(variant, evidence="H617E owner-qualified shared music semantics")
            for variant in H617A_MUSIC_VARIANTS
        ),
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
    "H66A0": ModelProfile(
        "Govee TV Backlight 3 Pro (H66A0)",
        support_quality=SupportQuality.COMPATIBLE,
        command_grammar="H617A",
        status_grammar="H66A0",
        effect_grammar="H617A",
        video_grammar="H66A0",
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
                ReadDomain.IC_SEGMENT_COUNT,
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
        supports_multi_layered_effects=True,
        supports_scenes=True,
        supports_video_mode=True,
        video_modes=("movie", "game"),
        supports_video_sound_effects=True,
        supports_relative_brightness=True,
        video_brightness_zones=("left", "top", "right", "bottom", "strip_left", "strip_right"),
        music_modes=_H66A0_MUSIC_MODES,
        music_variants=H617A_MUSIC_VARIANTS,
        supports_music_color=True,
        whole_device_mask=0x7FFF,
        # The device reports 14 segments and 90 lamp beads through its aa 40 probe.  The
        # count is read from the device rather than fixed here, because a strip that has
        # been cut reports its own length.
        segment_count=14,
        segment_group_size=4,
        segment_count_from_ic_probe=True,
        supports_segment_writes=True,
        scene_catalogue_sku="H66A0",
    ),
    "H6199": ModelProfile(
        "H6199 DreamView T1",
        support_quality=SupportQuality.SUPPORTED,
        command_grammar="H6199",
        status_grammar="H6199",
        effect_grammar="H6199",
        video_grammar="H6199",
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
        video_modes=("movie", "game"),
        supports_video_capture_region=True,
        supports_video_saturation=True,
        supports_video_sound_effects=True,
        # These independently captured video registers have byte-exact builders.
        supports_white_balance=True,
        video_white_balance_calibration=WHITE_BALANCE_POSITIONS,
        video_brightness_zones=("left", "top", "right", "bottom"),
        supports_relative_brightness=True,
        supports_blank_screen=True,
        music_modes=_H6199_MUSIC_MODES,
        music_variants=(MusicVariant(0x03, "H6199 captured Rhythm selector style", supports_style=True),),
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
