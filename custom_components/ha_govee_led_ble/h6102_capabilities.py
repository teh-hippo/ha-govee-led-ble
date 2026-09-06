"""Pure H6102 firmware capability resolution."""

from dataclasses import dataclass, replace
from typing import Literal

from .const import MODEL_PROFILES, ModelProfile
from .firmware_version import FirmwareVersion
from .h6102_protocol import H6102RgbVariant, classify_h6102_rgb

type H6102FirmwareSource = Literal["ble", "configured"]
type H6102CapabilityResolutionReason = Literal["firmware_unknown", "legacy_capture_required"]


@dataclass(frozen=True, slots=True)
class H6102CapabilityResolution:
    profile: ModelProfile
    rgb_variant: H6102RgbVariant | None
    firmware_source: H6102FirmwareSource | None
    capability_resolution_reason: H6102CapabilityResolutionReason | None


_BASE_PROFILE = MODEL_PROFILES["H6102"]
_EXTENDED_RGB_PROFILE = replace(
    _BASE_PROFILE,
    supports_rgb=True,
    whole_device_mask=0x7FFF,
)


def resolve_h6102_capabilities(
    firmware: str | None = None,
    firmware_source: H6102FirmwareSource | None = None,
) -> H6102CapabilityResolution:
    """Resolve the safe H6102 profile for explicit firmware context."""
    variant = classify_h6102_rgb(FirmwareVersion.parse(firmware)) if firmware_source is not None else None
    if variant is H6102RgbVariant.EXTENDED:
        return H6102CapabilityResolution(_EXTENDED_RGB_PROFILE, variant, firmware_source, None)
    return H6102CapabilityResolution(
        _BASE_PROFILE,
        variant,
        firmware_source,
        "legacy_capture_required" if variant is H6102RgbVariant.LEGACY else "firmware_unknown",
    )
