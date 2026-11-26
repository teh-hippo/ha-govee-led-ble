"""Exact H6102 candidate capabilities, resolved per device."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, Literal

from .const import MODEL_PROFILES, ConfiguredIdentityPolicy, ModelProfile, ReadDomain
from .coordinator_identity import InitialDeviceIdentity
from .firmware_version import FirmwareVersion
from .h6102_protocol import H6102_PACTS, H6102RgbVariant, classify_h6102_rgb
from .music_semantics import H6102_MUSIC_VARIANTS

type H6102FirmwareSource = Literal["ble", "configured"]
type H6102CapabilityResolutionReason = Literal["pact_unknown", "legacy_capture_required"]


@dataclass(frozen=True, slots=True)
class H6102CapabilityResolution:
    profile: ModelProfile
    rgb_variant: H6102RgbVariant | None
    firmware_source: H6102FirmwareSource | None
    capability_resolution_reason: H6102CapabilityResolutionReason | None


@dataclass(frozen=True, slots=True)
class H6102InitialIdentity(InitialDeviceIdentity):
    pact: str | None = None

    @property
    def bootstrap_hardware(self) -> None:
        return None

    @property
    def bootstrap_pact_type(self) -> None:
        return None

    @property
    def bootstrap_pact_code(self) -> None:
        return None

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.pact is not None and self.pact not in H6102_PACTS:
            raise ValueError("Unknown H6102 Pact context")
        if self.pact is not None:
            pact_type, pact_code = H6102_PACTS[self.pact]
            object.__setattr__(self, "pact_type", pact_type)
            object.__setattr__(self, "pact_code", pact_code)
        if self.hardware is not None and self.hardware_source is None:
            object.__setattr__(self, "hardware_source", "configured")


def initial_identity_from_entry(
    data: Mapping[str, Any],
    policy: ConfiguredIdentityPolicy,
) -> H6102InitialIdentity:
    firmware = data.get(policy.firmware_key)
    hardware = data.get(policy.hardware_key)
    pact = data.get(policy.pact_key)
    return H6102InitialIdentity(
        firmware=firmware if isinstance(firmware, str) else None,
        firmware_source="configured" if isinstance(firmware, str) else None,
        hardware=hardware if isinstance(hardware, str) else None,
        hardware_source="configured" if isinstance(hardware, str) else None,
        pact=pact if isinstance(pact, str) else None,
    )


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
    segment_count=0,
    segment_group_size=0,
    supports_segment_writes=False,
    supports_segment_brightness=False,
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
        # The extra music modes need both the hardware family and the firmware.
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
        from .protocol_transforms import h6102_outbound_transform_for

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
                supports_color_temperature=extended_colour,
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
                whole_device_mask_override=0x7FFF,
                segment_count=0,
                segment_group_size=0,
                supports_segment_writes=False,
                supports_segment_brightness=False,
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


resolve_configured_identity = resolve_h6102_capabilities


def configured_identity_diagnostics(entry: Any, coordinator: Any) -> dict[str, Any]:
    profile = coordinator.profile
    policy = profile.configured_identity
    resolution = coordinator.configured_identity_resolution
    assert policy is not None and resolution is not None
    data: dict[str, Any] = {
        "configured_app_firmware": entry.data.get(policy.firmware_key),
        "configured_app_hardware": entry.data.get(policy.hardware_key),
        "configured_pact": entry.data.get(policy.pact_key),
        "pact_type": coordinator.pact_type,
        "pact_code": coordinator.pact_code,
        "music_modes": list(profile.music_modes),
        "music_context": "resolved" if profile.music_modes else "evidence_gap",
        "boolean_controls": dict(coordinator.boolean_control_state),
        "resolved_profile": profile.name,
        "firmware_source": resolution.firmware_source,
        "classified_rgb_variant": (resolution.rgb_variant.value if resolution.rgb_variant is not None else None),
        "rgb_enabled": profile.supports_rgb,
        "capability_resolution_reason": resolution.capability_resolution_reason,
        "read_domains": sorted(domain.value for domain in profile.read_domains),
        "surface_capabilities": {
            "color_temperature": profile.supports_color_temperature,
            "regions": profile.supports_segments,
            "music": profile.supports_music_mode,
            "scenes": profile.supports_scenes,
            "diy": profile.supports_custom_effects,
            "studio": bool(coordinator.configuration_url and coordinator.effect_categories),
        },
    }
    if coordinator.fw_version is not None:
        data["observed_firmware"] = coordinator.fw_version
    if coordinator.hw_version is not None:
        data["observed_hardware"] = coordinator.hw_version
    return data
