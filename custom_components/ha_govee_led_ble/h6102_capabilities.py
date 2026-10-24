"""Exact H6102 APK candidate capabilities, resolved per device."""

from dataclasses import dataclass, replace
from typing import Literal

from .const import MODEL_PROFILES, ModelProfile, ReadDomain
from .firmware_version import FirmwareVersion
from .h6102_protocol import H6102RgbVariant, classify_h6102_rgb
from .music_semantics import H6102_MUSIC_VARIANTS

type H6102FirmwareSource = Literal["ble", "configured"]
type H6102CapabilityResolutionReason = Literal["pact_unknown", "legacy_capture_required"]


@dataclass(frozen=True, slots=True)
class H6102CapabilityResolution:
    profile: ModelProfile
    rgb_variant: H6102RgbVariant | None
    firmware_source: H6102FirmwareSource | None
    capability_resolution_reason: H6102CapabilityResolutionReason | None


_UNSET = object()
_SCENES_V0_CODES = frozenset({0, 1, 4, 5, 7, 8, 9, 10, 15, 16, 21, 22})
_BASE_PROFILE = MODEL_PROFILES["H6102"]
_BOOTSTRAP_PROFILE = replace(
    _BASE_PROFILE,
    command_operations=frozenset({"power", "brightness"}),
    effect_grammar=None,
    read_domains=frozenset({ReadDomain.POWER, ReadDomain.BRIGHTNESS, ReadDomain.FIRMWARE, ReadDomain.HARDWARE}),
    setup_required_read_domains=frozenset({ReadDomain.POWER, ReadDomain.BRIGHTNESS}),
    supports_rgb=False,
    supports_color_temperature=False,
    static_readback_kelvin=False,
    static_readback_zero_kelvin_is_rgb=False,
    static_readback_gradual=False,
    supports_custom_effects=False,
    supports_scenes=False,
    supports_multi_layered_effects=False,
    supports_advanced_effects=False,
    music_modes=(),
    music_variants=(),
    supports_music_color=False,
    whole_device_mask=0,
    segment_count=0,
    segment_group_size=0,
    supports_segment_writes=False,
    supports_segment_brightness=False,
    supports_segment_color_temperature=False,
    effect_readback="none",
    advanced_diy_selector=None,
    diy_requires_upload_ack=False,
    music_upload_before_selector=False,
    music_requires_upload_ack=False,
    boolean_controls=frozenset(),
)


def resolve_h6102_capabilities(
    firmware: str | None = None,
    firmware_source: H6102FirmwareSource | None = None,
    *,
    hardware: str | None = None,
    pact_type: int | None = None,
    pact_code: int | None = None,
    physical_ic_count: int | None | object = _UNSET,
) -> H6102CapabilityResolution:
    """Pact selects the family; firmware alone never grants a product's features."""
    resolved_ic_count = (
        _BASE_PROFILE.physical_ic_count
        if physical_ic_count is _UNSET
        else physical_ic_count
        if isinstance(physical_ic_count, int) and not isinstance(physical_ic_count, bool)
        else None
    )
    version = FirmwareVersion.parse(firmware) if firmware_source is not None else None
    hw = FirmwareVersion.parse(hardware)
    variant = classify_h6102_rgb(
        version,
        hardware=hw,
        pact_type=pact_type,
        pact_code=pact_code,
    )
    if pact_type == 10 and pact_code in (1, 2):
        # Support.newProtocol4SupportMultiMusicMode: hardware family AND firmware.
        # Basic four selectors are unconditional in the modern route.
        music_modes = _BASE_PROFILE.music_modes[:4]
        if version is not None and hw is not None and hardware is not None and len(hardware) == 7:
            new_music = (
                hardware.startswith("2.01.")
                and version >= FirmwareVersion((2, 4))
                or hardware.startswith("3.")
                and not hardware.startswith("3.04.")
                and version >= FirmwareVersion((3, 1))
            )
            music_modes = _BASE_PROFILE.music_modes if new_music else _BASE_PROFILE.music_modes[:4]
        controls = {"gradual"}
        if hw is not None and hw >= FirmwareVersion((1, 0, 2)):
            controls.add("limit")
        profile = replace(
            _BASE_PROFILE,
            music_modes=music_modes,
            music_variants=H6102_MUSIC_VARIANTS,
            boolean_controls=frozenset(controls),
            physical_ic_count=resolved_ic_count,
        )
        return H6102CapabilityResolution(profile, variant, firmware_source, None)
    profile = replace(_BOOTSTRAP_PROFILE, physical_ic_count=resolved_ic_count)
    if pact_type == 1 and pact_code in (1, 2):
        from .generated_protocol_adapter import h6102_outbound_transform_for

        if variant is not None and version is not None and hw is not None and version >= FirmwareVersion((1, 3, 1)):
            extended_colour = variant is H6102RgbVariant.EXTENDED
            expanded_music = version >= FirmwareVersion((1, 7))
            uploaded_scenes = pact_code == 2 or version >= FirmwareVersion((1, 4))
            workflows = frozenset({"native_music", "native_scenes", "single", "multi"})
            if uploaded_scenes:
                workflows |= {"edited_palette_scenes", "layered_scenes", "advanced"}
            if extended_colour:
                workflows |= {"painted"}
            profile = replace(
                _BASE_PROFILE,
                command_operations=None,
                command_ack_grammar="H6125",
                read_domains=_BOOTSTRAP_PROFILE.read_domains,
                setup_required_read_domains=_BOOTSTRAP_PROFILE.setup_required_read_domains,
                effect_workflows=workflows,
                supports_rgb=True,
                supports_color_temperature=False,
                static_readback_kelvin=False,
                static_readback_zero_kelvin_is_rgb=False,
                static_readback_gradual=False,
                supports_custom_effects=True,
                supports_scenes=True,
                supports_advanced_effects=uploaded_scenes,
                supports_multi_layered_effects=uploaded_scenes,
                music_modes=_BASE_PROFILE.music_modes if expanded_music else _BASE_PROFILE.music_modes[:4],
                music_variants=H6102_MUSIC_VARIANTS,
                supports_music_color=True,
                whole_device_mask=0x7FFF,
                segment_count=0,
                segment_group_size=0,
                supports_segment_writes=False,
                supports_segment_brightness=False,
                supports_segment_color_temperature=False,
                selector_only_scene_bits=None if uploaded_scenes else 16,
                scene_codes=None if uploaded_scenes else _SCENES_V0_CODES,
                advanced_diy_selector=_BASE_PROFILE.advanced_diy_selector if uploaded_scenes else None,
                a1_diy_selector=0xFE,
                effect_readback="none",
                diy_requires_upload_ack=False,
                music_upload_before_selector=True,
                music_requires_upload_ack=False,
                packet_write_delay=0.1,
                boolean_controls=frozenset(),
                brightness_wire_range=(20, 254),
                outbound_transform=h6102_outbound_transform_for(legacy_colour=not extended_colour),
                physical_ic_count=resolved_ic_count,
            )
            return H6102CapabilityResolution(profile, variant, firmware_source, None)
        profile = replace(
            profile,
            command_ack_grammar="H6125",
            brightness_wire_range=(20, 254),
            outbound_transform=h6102_outbound_transform_for(),
            packet_write_delay=0.1,
        )
    return H6102CapabilityResolution(
        profile,
        variant,
        firmware_source,
        "legacy_capture_required" if pact_type is not None else "pact_unknown",
    )
