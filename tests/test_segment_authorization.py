"""Operation-specific segment authorization through preflight and physical writes."""

from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, ModelProfile, ReadDomain
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_brightness,
    build_colour_temperature,
    build_segment_colour,
    build_segment_query,
    require_profile_packet,
)
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_segment_brightness as build_brightness_mask,
)
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.light_commands import (
    build_color_rgb,
    build_color_temp,
    build_segment_brightness,
    build_segment_color,
    build_segment_color_temp,
    kelvin_to_rgb,
    parse_static_write,
)
from custom_components.ha_govee_led_ble.transport import xor_checksum


@pytest.fixture(params=["H617A", "H6099", "H6199"])
def profile(request, monkeypatch):
    profile = ModelProfile(
        "Synthetic segment capability profile",
        command_grammar=request.param,
        status_grammar=request.param,
        read_domains=frozenset({ReadDomain.SEGMENTS}),
        supports_rgb=True,
        supports_color_temperature=True,
        supports_segment_writes=True,
        supports_segment_brightness=True,
        supports_segment_color_temperature=True,
        segment_count=5,
        segment_group_size=3 if request.param == "H617A" else 4,
        whole_device_mask=31,
    )
    monkeypatch.setitem(MODEL_PROFILES, "H9901", profile)
    return profile


@pytest.mark.parametrize(
    "capability,builder,args,raw_builder",
    [
        ("supports_rgb", build_segment_color, ([1], 1, 2, 3), lambda p: build_segment_colour(1, 1, 2, 3, profile=p)),
        (
            "supports_segment_brightness",
            build_segment_brightness,
            ([1], 50),
            lambda p: build_brightness_mask(1, 50, profile=p),
        ),
        (
            "supports_segment_color_temperature",
            build_segment_color_temp,
            ([1], 3000),
            lambda p: build_colour_temperature(3000, kelvin_to_rgb(3000), 1, profile=p),
        ),
        (
            "supports_color_temperature",
            build_segment_color_temp,
            ([1], 3000),
            lambda p: build_colour_temperature(3000, kelvin_to_rgb(3000), 1, profile=p),
        ),
    ],
)
def test_per_operation_authorization(profile, capability, builder, args, raw_builder):
    packet = builder(*args, profile=profile)
    require_profile_packet(packet, profile)
    disabled = replace(profile, **{capability: False})
    with pytest.raises(ValueError, match="does not support"):
        builder(*args, profile=disabled)
    with pytest.raises(ValueError, match="does not support"):
        require_profile_packet(raw_builder(profile), disabled)
    # Parsing remains structural even when a write is unauthorized.
    assert parse_static_write(packet, profile=disabled) is not None
    require_profile_packet(build_brightness(50, profile=disabled), disabled)
    require_profile_packet(build_segment_query(1, profile=disabled), disabled)


def test_all_selected_segments_still_require_operation_flags(profile):
    disabled = replace(profile, supports_segment_brightness=False, supports_segment_color_temperature=False)
    for builder, args in (
        (build_segment_brightness, (range(1, 6), 50)),
        (build_segment_color_temp, (range(1, 6), 3000)),
    ):
        with pytest.raises(ValueError, match="does not support segment"):
            builder(*args, profile=disabled)
    with pytest.raises(ValueError, match="segment brightness"):
        require_profile_packet(build_brightness_mask(31, 50, profile=profile), disabled)


def test_whole_device_commands_do_not_require_segment_writes(profile):
    disabled = replace(
        profile,
        segment_count=0,
        supports_segment_writes=False,
        supports_segment_brightness=False,
        supports_segment_color_temperature=False,
        supports_white_brightness=True,
    )
    for packet in (
        build_color_rgb(1, 2, 3, profile=disabled),
        build_color_temp(3000, profile=disabled),
        build_brightness_mask(31, 50, profile=disabled),
    ):
        require_profile_packet(packet, disabled)
    for capability, packet in (
        ("supports_rgb", build_color_rgb(1, 2, 3, profile=disabled)),
        ("supports_color_temperature", build_color_temp(3000, profile=disabled)),
        ("supports_white_brightness", build_brightness_mask(31, 50, profile=disabled)),
    ):
        with pytest.raises(ValueError, match="does not support"):
            require_profile_packet(packet, replace(disabled, **{capability: False}))


@pytest.mark.parametrize("mask", [0, 32, 0x8000])
def test_raw_mask_geometry(profile, mask):
    for packet in (
        build_segment_colour(mask, 1, 2, 3, profile=profile),
        build_brightness_mask(mask, 50, profile=profile),
        build_colour_temperature(3000, kelvin_to_rgb(3000), mask, profile=profile),
    ):
        with pytest.raises(ValueError, match="no segments|geometry"):
            require_profile_packet(packet, profile)


@pytest.mark.parametrize(
    "change",
    [
        {"segment_count": 4},
        {"whole_device_mask": 15},
        {"supports_segment_brightness": False},
        {"supports_segment_writes": False},
    ],
)
@pytest.mark.parametrize("timing", ["prepared", "before_write"])
async def test_physical_boundary_revalidates_current_profile(hass, profile, change, timing):
    c = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H9901", configuration_url=None)
    packet = build_segment_brightness([5], 50, profile=profile)
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    before = c.capture_effect_control_state()

    def narrow():
        c.profile = replace(profile, **change)

    if timing == "prepared":
        narrow()
    with pytest.raises(ValueError):
        await c._async_write_packet(
            client,
            packet,
            arm_expected=True,
            before_write=narrow if timing == "before_write" else None,
            state_values={"brightness_pct": 50},
        )
    client.write_gatt_char.assert_not_awaited()
    assert c.capture_effect_control_state() == before
    assert c.control_write_attempts == 0 and not c._expected_state


@pytest.mark.parametrize(
    "capability,method,args",
    [
        ("supports_rgb", "async_set_segment_color", ([1], (1, 2, 3))),
        ("supports_segment_brightness", "async_set_segment_brightness", ([1], 50)),
        ("supports_segment_color_temperature", "async_set_segment_color_temp", ([1], 3000)),
    ],
)
async def test_public_services_reject_before_side_effects(hass, profile, monkeypatch, capability, method, args):
    c = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H9901", configuration_url=None)
    c.profile = replace(profile, **{capability: False})
    light = GoveeBLELight(c)
    preview = AsyncMock()
    monkeypatch.setattr(light, "_async_supersede_preview", preview)
    monkeypatch.setattr(c, "send_command", AsyncMock())
    monkeypatch.setattr(c, "async_refresh_segments", AsyncMock())
    with pytest.raises(ServiceValidationError):
        await getattr(light, method)(*args)
    preview.assert_not_awaited()
    c.send_command.assert_not_awaited()
    c.async_refresh_segments.assert_not_awaited()
    assert c.control_write_attempts == 0


def test_existing_profiles_deliberately_preserve_segment_operations():
    for model in ("H617A", "H617E", "H6099", "H6102", "H6199"):
        profile = MODEL_PROFILES[model]
        assert profile.supports_segment_brightness and profile.supports_segment_color_temperature
    assert not ModelProfile("Unqualified").supports_segment_brightness
    assert not ModelProfile("Unqualified").supports_segment_color_temperature


def test_full_segment_brightness_array_cannot_bypass_capability_gate():
    payload = bytes.fromhex("33051503") + bytes([50]) * 15
    packet = payload + bytes([xor_checksum(payload)])
    profile = MODEL_PROFILES["H617A"]
    require_profile_packet(packet, profile)
    for change in ({"supports_segment_brightness": False}, {"segment_count": 5}, {"whole_device_mask": 0x001F}):
        with pytest.raises(ValueError, match="segment brightness"):
            require_profile_packet(packet, replace(profile, **change))


@pytest.mark.parametrize("array", [False, True])
@pytest.mark.parametrize("timing", ["prepared", "before_write"])
async def test_all_segment_brightness_rejects_stale_geometry_before_physical_attempt(hass, array, timing):
    c = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617A", configuration_url=None)
    profile = c.profile
    if array:
        payload = bytes.fromhex("33051503") + bytes([50]) * 15
        packet = payload + bytes([xor_checksum(payload)])
        narrowed = replace(profile, whole_device_mask=0x001F)
    else:
        packet = build_brightness_mask(0x7FFF, 50, profile=profile)
        narrowed = replace(profile, segment_count=4)
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    before = c.capture_effect_control_state()
    revisions = dict(c._field_revisions)

    def narrow():
        c.profile = narrowed

    if timing == "prepared":
        narrow()
    with pytest.raises(ValueError, match="geometry"):
        await c._async_write_packet(
            client,
            packet,
            arm_expected=True,
            before_write=narrow if timing == "before_write" else None,
            state_values={"brightness_pct": 50},
        )
    client.write_gatt_char.assert_not_awaited()
    assert c.capture_effect_control_state() == before
    assert c._field_revisions == revisions
    assert c.control_write_attempts == 0 and not c._expected_state


async def test_physical_boundary_preserves_explicit_whole_device_operations(hass, profile):
    c = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H9901", configuration_url=None)
    c.profile = replace(
        profile,
        segment_count=0,
        supports_segment_writes=False,
        supports_segment_brightness=False,
        supports_segment_color_temperature=False,
        supports_white_brightness=True,
    )
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    packets = (
        build_brightness_mask(profile.whole_device_mask, 50, profile=profile),
        build_color_rgb(1, 2, 3, profile=profile),
        build_color_temp(3000, profile=profile),
    )
    for packet in packets:
        await c._async_write_packet(client, packet, arm_expected=True)
    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == list(packets)
    assert c.control_write_attempts == 3
