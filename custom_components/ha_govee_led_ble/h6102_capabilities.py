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


_BASE_PROFILE = MODEL_PROFILES["H6102"]
_BOOTSTRAP_PROFILE = replace(
    _BASE_PROFILE,
    command_operations=frozenset({"power", "brightness"}),
    effect_grammar=None,
    read_domains=frozenset({ReadDomain.POWER, ReadDomain.BRIGHTNESS, ReadDomain.FIRMWARE, ReadDomain.HARDWARE}),
    setup_required_read_domains=frozenset({ReadDomain.POWER, ReadDomain.BRIGHTNESS}),
    supports_rgb=False,
    supports_color_temperature=False,
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
    effect_readback="none",
    advanced_diy_selector=None,
    diy_requires_upload_ack=False,
    boolean_controls=frozenset(),
)


def resolve_h6102_capabilities(
    firmware: str | None = None,
    firmware_source: H6102FirmwareSource | None = None,
    *,
    hardware: str | None = None,
    pact_type: int | None = None,
    pact_code: int | None = None,
    physical_ic_count: int | None = None,
) -> H6102CapabilityResolution:
    """Pact selects the family; firmware alone never grants a product's features."""
    version = FirmwareVersion.parse(firmware) if firmware_source is not None else None
    variant = classify_h6102_rgb(
        version,
        hardware=FirmwareVersion.parse(hardware),
        pact_type=pact_type,
        pact_code=pact_code,
    )
    if pact_type == 10 and pact_code in (1, 2):
        # Support.newProtocol4SupportMultiMusicMode: hardware family AND firmware.
        # Basic four selectors are unconditional in the modern route.
        hw = FirmwareVersion.parse(hardware)
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
            physical_ic_count=physical_ic_count,
        )
        return H6102CapabilityResolution(profile, variant, firmware_source, None)
    # Pact 1 DIY uses A1, not the modern A3 route. Its separate RGB opcode
    # qualification does not grant static subcommands or other effect families.
    profile = _BOOTSTRAP_PROFILE
    if variant is H6102RgbVariant.EXTENDED:
        profile = replace(
            profile,
            command_operations=frozenset({"power", "brightness", "static"}),
            supports_rgb=True,
            supports_color_temperature=True,
            whole_device_mask=0x7FFF,
            segment_count=15,
            segment_group_size=3,
            supports_segment_writes=True,
            read_domains=_BASE_PROFILE.read_domains,
            setup_required_read_domains=_BASE_PROFILE.setup_required_read_domains,
        )
    return H6102CapabilityResolution(
        profile,
        variant,
        firmware_source,
        "legacy_capture_required" if pact_type is not None else "pact_unknown",
    )
