"""Operation-specific segment authorization through preflight and physical writes."""

from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, ModelProfile, ReadDomain, device_profile
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
    parse_static_write,
)
from custom_components.ha_govee_led_ble.transport import xor_checksum
from tests.coordinator_test_support import frame


@pytest.mark.parametrize("cached_modern", [False, True])
async def test_segment_read_authority_is_required_for_queries_and_subscription_observations(
    hass, monkeypatch, cached_modern
):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H618A", configuration_url=None)
    if cached_modern:
        coordinator.fw_version, coordinator.hw_version = "1.06.00", "1.00.02"
        coordinator._resolve_device_profile()
    client = MagicMock(is_connected=True, start_notify=AsyncMock(), write_gatt_char=AsyncMock())
    coordinator._client = client
    monkeypatch.setattr("custom_components.ha_govee_led_ble.coordinator.REPLY_PACING_TIMEOUT", 0)
    await coordinator._start_notify()
    receive = client.start_notify.await_args.args[1]
    width, domain = (3, 0xA5) if cached_modern else (4, 0xA2)
    pages = [
        frame(
            (
                bytes((0xAA, domain, group))
                + bytes((37, 1, 2, 3) if cached_modern else (1, 2, 3)) * min(width, 15 - (group - 1) * width)
            ).hex()
        )
        for group in range(1, 6 if cached_modern else 5)
    ]
    for page in pages:
        receive(None, bytearray(page))
    assert coordinator._field_revisions.get("segment_colors", 0) == 0
    assert coordinator._field_revisions.get("segment_brightness", 0) == 0
    assert not coordinator.segment_brightness_readable
    qualified = device_profile("H618A", 2, 1, firmware="1.06.00", hardware="1.00.02")
    query = build_segment_query(1, "H618A", profile=qualified)
    malformed = (frame("aaa500"), frame("aaa506"), bytes.fromhex("aaa5"), query[:-1], query + b"\x00")
    for candidate in (query, frame("aaa201"), *malformed):
        with pytest.raises((ValueError, HomeAssistantError)):
            await coordinator._async_write_packet(client, candidate)
    client.write_gatt_char.assert_not_awaited()

    receive(None, bytearray(frame("aa06" + ("1.06.00" if cached_modern else "1.05.99").encode().hex())))
    receive(None, bytearray(frame("aa0703" + b"1.00.02".hex())))
    for page in pages:
        receive(None, bytearray(page))
    assert coordinator.segment_colors == [(1, 2, 3)] * 15
    assert coordinator.segment_brightness_readable is cached_modern
    for candidate in (frame("aaa201"), *malformed):
        with pytest.raises(ValueError):
            await coordinator._async_write_packet(client, candidate)
    with pytest.raises((ValueError, HomeAssistantError)):
        await coordinator._async_write_packet(client, query, before_write=coordinator._confirmed_identity_fields.clear)
    client.write_gatt_char.assert_not_awaited()


async def test_h618a_pact3_reads_four_record_a5_pages(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H618A", configuration_url=None)
    coordinator.pact_type, coordinator.pact_code = 3, 1
    coordinator.fw_version, coordinator.hw_version = "1.00.11", "3.08.01"
    coordinator._resolve_device_profile()
    client = MagicMock(is_connected=True, start_notify=AsyncMock(), write_gatt_char=AsyncMock())
    coordinator._client = client
    monkeypatch.setattr("custom_components.ha_govee_led_ble.coordinator.REPLY_PACING_TIMEOUT", 0)
    await coordinator._start_notify()
    receive = client.start_notify.await_args.args[1]
    receive(None, bytearray(frame("aa06" + b"1.00.11".hex())))
    receive(None, bytearray(frame("aa0703" + b"3.08.01".hex())))
    receive(None, bytearray(frame("aaa50164ff866b64ff866b64ff866b64ff866b")))
    receive(None, bytearray(frame("aaa50264ff866b64ff866b64ff866b64ff866b")))
    receive(None, bytearray(frame("aaa50364ff866b00ff866b00ff866b00ff866b")))
    receive(None, bytearray(frame("aaa50400000000000000000000000000000000")))

    assert coordinator.profile.status_grammar == "H618A-pact3"
    assert coordinator.profile.segment_group_count == 4
    assert coordinator.segment_state_source == "observed"
    assert coordinator.segment_colors == [(255, 134, 107)] * 12 + [(0, 0, 0)] * 3
    assert coordinator.segment_brightness == [100] * 9 + [0] * 6
    query = build_segment_query(4, "H618A", profile=coordinator.profile)
    assert query[1:3] == b"\xa5\x04"


@pytest.fixture(params=["H617A", "H6099", "H6199"])
def profile(request, monkeypatch):
    profile = ModelProfile(
        "Synthetic segment capability profile",
        command_grammar=request.param,
        status_grammar=request.param,
        read_domains=frozenset({ReadDomain.SEGMENTS}),
        supports_rgb=True,
        supports_color_temperature=True,
        color_temp_range=(2000, 9000),
        supports_segment_writes=True,
        supports_segment_brightness=True,
        supports_segment_color_temperature=True,
        segment_count=5,
        segment_group_size=3 if request.param == "H617A" else 4,
        whole_device_mask_override=31,
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
            lambda p: build_colour_temperature(3000, 1, profile=p),
        ),
        (
            "supports_color_temperature",
            build_segment_color_temp,
            ([1], 3000),
            lambda p: build_colour_temperature(3000, 1, profile=p),
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
        build_colour_temperature(3000, mask, profile=profile),
    ):
        with pytest.raises(ValueError, match="no segments|geometry"):
            require_profile_packet(packet, profile)


@pytest.mark.parametrize(
    "change",
    [
        {"segment_count": 4},
        {"whole_device_mask_override": 15},
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
        assert MODEL_PROFILES[model].supports_segment_brightness
    assert MODEL_PROFILES["H6099"].supports_segment_color_temperature
    assert not ModelProfile("Unqualified").supports_segment_brightness
    assert not ModelProfile("Unqualified").supports_segment_color_temperature


def test_full_segment_brightness_array_cannot_bypass_capability_gate():
    payload = bytes.fromhex("33051503") + bytes([50]) * 15
    packet = payload + bytes([xor_checksum(payload)])
    profile = MODEL_PROFILES["H617A"]
    require_profile_packet(packet, profile)
    for change in (
        {"supports_segment_brightness": False},
        {"segment_count": 5},
        {"whole_device_mask_override": 0x001F},
    ):
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
        narrowed = replace(profile, whole_device_mask_override=0x001F)
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
