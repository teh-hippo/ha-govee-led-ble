import asyncio
import time
from dataclasses import replace
from unittest.mock import ANY, AsyncMock, MagicMock, call

import pytest
from homeassistant.components.light import ColorMode
from homeassistant.core import ServiceCall
from homeassistant.exceptions import HomeAssistantError

from custom_components.ha_govee_led_ble.const import DOMAIN, MODEL_PROFILES, LightSource, ReadDomain, device_profile
from custom_components.ha_govee_led_ble.control_arbiter import ControlIntent
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_refresh import RefreshRequest
from custom_components.ha_govee_led_ble.coordinator_sources import SourceTurnOnRequest
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_brightness,
    build_scene_activation,
    table_kelvin_rgb,
)
from custom_components.ha_govee_led_ble.light import GoveeBLELight, async_setup_entry
from custom_components.ha_govee_led_ble.light_commands import (
    build_color_rgb,
    build_color_temp,
    build_segment_brightness,
    build_segment_color,
    build_segment_color_temp,
    normalize_kelvin,
    parse_static_write,
)
from custom_components.ha_govee_led_ble.light_service_dispatch import _dispatch_device_lights
from custom_components.ha_govee_led_ble.light_source import GoveeBLESourceLight
from custom_components.ha_govee_led_ble.transport import xor_checksum
from tests.coordinator_test_support import frame

LEFT = LightSource("left_bar", "left_bar_enabled", (1, 2, 3, 4, 5))
RIGHT = LightSource("right_bar", "right_bar_enabled", (6, 7, 8, 9, 10))


@pytest.mark.parametrize(
    ("model", "pact", "available", "modes"),
    [
        ("H6046", (1, 1), True, {ColorMode.RGB, ColorMode.COLOR_TEMP}),
        ("H6046", (None, None), False, {ColorMode.ONOFF}),
        ("H607C", (1, 1), True, {ColorMode.RGB}),
        ("H607C", (None, None), False, {ColorMode.ONOFF}),
        ("H60B2", (1, 1), True, {ColorMode.RGB, ColorMode.COLOR_TEMP}),
        ("H60B2", (None, None), True, {ColorMode.RGB, ColorMode.COLOR_TEMP}),
        ("H60A6", (1, 2), True, {ColorMode.RGB}),
        ("H60A6", (1, 1), True, {ColorMode.BRIGHTNESS}),
        ("H60A6", (None, None), False, {ColorMode.ONOFF}),
    ],
)
def test_real_source_controls_follow_effective_revision(source_coordinator, model, pact, available, modes):
    source_coordinator.model = model
    source_coordinator.profile = device_profile(model, *pact)
    key = source_coordinator.profile.light_sources[0].key
    source = GoveeBLESourceLight(source_coordinator, key)
    assert source.available is available
    assert source.supported_color_modes == modes


def test_h60a1_does_not_invent_independent_power_controls():
    assert not MODEL_PROFILES["H60A1"].light_sources
    assert not device_profile("H60A1", 1, 1).supports_segment_color_temperature


@pytest.mark.parametrize(
    ("model", "key", "mask"),
    [
        ("H6046", "left_bar", 0x001F),
        ("H6046", "right_bar", 0x03E0),
        ("H607C", "pole", 0x00FF),
        ("H607C", "base", 0x1F00),
        ("H60B2", "bottom", 0x0001),
        ("H60B2", "middle", 0x0002),
        ("H60B2", "top", 0x0004),
    ],
)
def test_real_source_colour_and_brightness_packets_leave_sibling_masked(model, key, mask):
    profile = device_profile(model, 1, 1)
    segments = next(source.segments for source in profile.light_sources if source.key == key)
    packets = (
        build_segment_color(segments, 1, 2, 3, model, profile=profile),
        build_segment_brightness(segments, 50, model, profile=profile),
    )
    for packet in packets:
        parsed = parse_static_write(packet, model, profile=profile)
        assert parsed is not None and parsed.segment_mask == mask


@pytest.fixture
def source_coordinator(mock_coordinator):
    coordinator = mock_coordinator
    coordinator.model = "H6046"
    coordinator.profile = replace(MODEL_PROFILES["H6046"], light_sources=(LEFT, RIGHT))
    coordinator.is_on = True
    coordinator.boolean_control_state = {"left_bar_enabled": True, "right_bar_enabled": True}
    coordinator.segment_colors = [(1, 2, 3)] * 5 + [(4, 5, 6)] * 5
    coordinator.segment_brightness = [40] * 5 + [80] * 5
    coordinator.segment_state_source = "observed"
    coordinator.last_update_success = True
    coordinator.segment_kelvin = [None] * coordinator.profile.segment_count
    coordinator._async_supersede_effect_preview = AsyncMock()
    coordinator._notify_started_monotonic = 1.0
    coordinator._field_revisions["is_on"] = 1
    coordinator._observed_power_write_generation = coordinator._power_write_generation
    coordinator._observed_power_profile_generation = coordinator._profile_generation
    coordinator._field_received_at = {
        "is_on": 2.0,
        **{
            f"boolean_{control}": 2.0
            for control in (
                "left_bar_enabled",
                "right_bar_enabled",
                "pole_enabled",
                "base_enabled",
                "panel_enabled",
                "ring_enabled",
                "source_0_enabled",
                "source_1_enabled",
            )
        },
    }
    coordinator._source_power_observation_generation = {
        field: (coordinator._power_write_generation, coordinator._profile_generation)
        for field in coordinator._field_received_at
        if field.startswith("boolean_")
    }

    async def set_control(control, enabled):
        coordinator.boolean_control_state[control] = enabled
        coordinator._field_received_at[f"boolean_{control}"] = 2.0
        coordinator._source_power_observation_generation[f"boolean_{control}"] = (
            coordinator._power_write_generation,
            coordinator._profile_generation,
        )

    coordinator.async_set_boolean_control = AsyncMock(side_effect=set_control)
    coordinator.async_set_segment_kelvin = AsyncMock()
    return coordinator


async def test_source_preflight_does_not_claim_foreign_preview_writes_as_partial(source_coordinator):
    failure = HomeAssistantError("Preview restoration failed")

    async def supersede():
        source_coordinator.control_write_attempts += 1
        raise failure

    source_coordinator._async_supersede_effect_preview = AsyncMock(side_effect=supersede)
    with pytest.raises(HomeAssistantError) as raised:
        await GoveeBLESourceLight(source_coordinator, "left_bar").async_turn_on()
    assert raised.value is failure
    source_coordinator.async_set_boolean_control.assert_not_awaited()


async def test_source_switch_without_values_does_not_require_segment_geometry(source_coordinator):
    source_coordinator.boolean_control_state["left_bar_enabled"] = False
    source_coordinator.async_mask_transaction = MagicMock(
        side_effect=AssertionError("Source power does not address segments")
    )
    await GoveeBLESourceLight(source_coordinator, "left_bar").async_turn_on()
    source_coordinator.async_set_boolean_control.assert_awaited_once_with("left_bar_enabled", True)


async def test_source_enable_rejects_removed_bar_operation_before_writes(source_coordinator):
    source_coordinator.profile = replace(
        source_coordinator.profile,
        command_operations=source_coordinator.profile.command_operations - {"bar_enable"},
    )

    with pytest.raises(HomeAssistantError) as raised:
        await GoveeBLESourceLight(source_coordinator, "left_bar")._set_source(False)

    assert raised.value.translation_key == "device_command_failed"
    source_coordinator.async_set_boolean_control.assert_not_awaited()
    source_coordinator.send_command.assert_not_awaited()
    source_coordinator._async_supersede_effect_preview.assert_not_awaited()


async def test_cold_h6053_source_off_qualifies_before_bar_preflight(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6053", configuration_url=None)
    qualified = device_profile("H6053", 1, 1, firmware="1.00.12", hardware="1.00.00")
    initial_operations = coordinator.profile.command_operations
    qualified_operations = qualified.command_operations
    assert initial_operations is not None and "bar_enable" not in initial_operations
    assert qualified_operations is not None and "bar_enable" in qualified_operations

    async def prepare():
        coordinator.profile = qualified
        return None

    prepared = AsyncMock(side_effect=prepare)
    verified = AsyncMock()
    monkeypatch.setattr(coordinator, "async_prepare_identity_gated_control", prepared)
    monkeypatch.setattr(coordinator, "_async_set_verified_setting", verified)

    await GoveeBLESourceLight(coordinator, "left_bar")._set_source(False)

    prepared.assert_awaited_once_with()
    verified.assert_awaited_once_with("left_bar_enabled", False, write_guard=None)


async def test_source_turn_on_rejects_removed_bar_operation_before_lighting_writes(source_coordinator):
    source_coordinator.profile = replace(
        source_coordinator.profile,
        command_operations=source_coordinator.profile.command_operations - {"bar_enable"},
    )
    source_coordinator.is_on = False
    source_coordinator.boolean_control_state["left_bar_enabled"] = False

    with pytest.raises(HomeAssistantError) as raised:
        await GoveeBLESourceLight(source_coordinator, "left_bar").async_turn_on(brightness=50)

    assert raised.value.translation_key == "device_command_failed"
    source_coordinator.async_set_boolean_control.assert_not_awaited()
    source_coordinator.send_command.assert_not_awaited()
    source_coordinator.async_set_segment_brightness.assert_not_awaited()
    source_coordinator._async_supersede_effect_preview.assert_not_awaited()


async def test_h6053_source_colour_uses_version_identity_without_pact(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6053", configuration_url=None)
    coordinator._client = client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    coordinator._notification_token = object()
    coordinator._notify_started_monotonic = time.monotonic() - 1
    coordinator._observe_identity_field("fw_version", "1.08.05")
    coordinator._observe_identity_field("hw_version", "1.00.00")
    coordinator.is_on = True
    coordinator.boolean_control_state.update({"left_bar_enabled": True, "right_bar_enabled": True})
    coordinator._field_revisions["is_on"] = 1
    coordinator._observed_power_write_generation = coordinator._power_write_generation
    coordinator._observed_power_profile_generation = coordinator._profile_generation
    for field in ("is_on", "boolean_left_bar_enabled", "boolean_right_bar_enabled"):
        coordinator._field_received_at[field] = coordinator._notify_started_monotonic + 0.1
        if field.startswith("boolean_"):
            coordinator._source_power_observation_generation[field] = (
                coordinator._power_write_generation,
                coordinator._profile_generation,
            )
    monkeypatch.setattr(coordinator, "_refresh_pact_advertisements", MagicMock())
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(coordinator, "_renew_foreground_lease", MagicMock())
    monkeypatch.setattr(coordinator, "_async_supersede_effect_preview", AsyncMock())

    async def refresh_segments():
        coordinator.segment_colors = [(12, 34, 56)] * 6 + [(0, 0, 0)] * 6
        coordinator.segment_brightness = [100] * 12
        coordinator.segment_state_source = "observed"
        return True

    monkeypatch.setattr(coordinator, "async_refresh_segments", AsyncMock(side_effect=refresh_segments))

    await coordinator.async_turn_on_source("left_bar", SourceTurnOnRequest(rgb_color=(12, 34, 56)))

    assert coordinator.profile.supports_rgb
    assert "static" in coordinator.profile.command_operations
    assert "brightness" not in coordinator.profile.command_operations
    assert not coordinator.identity_fields_confirmed(frozenset({"pact"}))
    client.write_gatt_char.assert_awaited_once()
    parsed = parse_static_write(client.write_gatt_char.await_args.args[1], "H6053", profile=coordinator.profile)
    assert parsed is not None and parsed.segment_mask == 0x003F


async def test_setup_adds_sources_without_changing_main_light_identity(source_coordinator):
    entry = MagicMock(runtime_data=source_coordinator)
    added = []
    await async_setup_entry(MagicMock(), entry, lambda entities: added.extend(entities))
    assert isinstance(added[0], GoveeBLELight)
    assert added[0].unique_id == "aabbccddeeff"
    assert [entity.unique_id for entity in added[1:]] == ["aabbccddeeff_left_bar", "aabbccddeeff_right_bar"]
    source_coordinator.async_add_listener.call_args.args[0]()
    assert len(added) == 3


async def test_device_service_dispatches_once_to_main_for_device_and_source_targets(hass, source_coordinator):
    main = GoveeBLELight(source_coordinator)
    main.entity_id = "light.main"
    main.async_set_segment_color = AsyncMock()
    main.async_apply_custom_effect = AsyncMock(return_value={"phase": "confirmed"})

    async def request_call(operation):
        return await operation

    main.async_request_call = request_call
    source = GoveeBLESourceLight(source_coordinator, "left_bar", main)
    call = ServiceCall(hass, DOMAIN, "set_segment_color", {"segments": [1], "color": (1, 2, 3)})
    await _dispatch_device_lights([main, source], call, func="async_set_segment_color")
    main.async_set_segment_color.assert_awaited_once_with(segments=[1], color=(1, 2, 3))

    response_call = ServiceCall(hass, DOMAIN, "apply_custom_effect", {"effect": "test"}, return_response=True)
    result = await _dispatch_device_lights([source], response_call, func="async_apply_custom_effect")
    assert result == {"light.main": {"phase": "confirmed"}}
    main.async_apply_custom_effect.assert_awaited_once_with(effect="test")


async def test_device_service_works_when_main_entity_was_disabled(hass, source_coordinator):
    main = GoveeBLELight(source_coordinator)
    main.entity_id = "light.main"
    main.add_to_platform_abort()
    source = GoveeBLESourceLight(source_coordinator, "left_bar", main)
    call = ServiceCall(hass, DOMAIN, "set_segment_brightness", {"segments": [1], "brightness": 50})
    await _dispatch_device_lights([source], call, func="async_set_segment_brightness")
    source_coordinator.async_set_segment_brightness.assert_awaited_once_with([1], 50)
    source_coordinator.async_set_updated_data.assert_called_once()


def test_source_state_is_derived_from_its_own_segments_and_master_power(source_coordinator):
    source = GoveeBLESourceLight(source_coordinator, "left_bar")
    assert source.is_on is True
    assert source.rgb_color == (1, 2, 3)
    assert source.brightness == 102
    assert source.supported_color_modes == {ColorMode.RGB, ColorMode.COLOR_TEMP}

    source_coordinator.segment_colors[1] = (7, 8, 9)
    source_coordinator.segment_brightness[1] = 70
    assert source.rgb_color is None and source.brightness is None
    source_coordinator.is_on = False
    assert source.is_on is False
    source_coordinator.is_on = None
    assert source.is_on is None


def test_source_reports_valid_unknown_colour_mode_during_effects(source_coordinator):
    source_coordinator.color_mode = ParsedMode.SCENE
    source = GoveeBLESourceLight(source_coordinator, "left_bar")
    assert source.is_on is True and source.color_mode is ColorMode.UNKNOWN
    assert source.state_attributes is not None


def test_unconfirmed_colour_marks_only_colour_capable_sources_assumed(source_coordinator):
    coordinator = source_coordinator
    coordinator._unconfirmed_state_fields.add("color")
    assert GoveeBLESourceLight(coordinator, "left_bar").assumed_state
    coordinator.profile = MODEL_PROFILES["H1771"]
    coordinator.boolean_control_state = {"source_0_enabled": True}
    assert not GoveeBLESourceLight(coordinator, "source_0").assumed_state


def test_power_only_source_uses_its_own_observation_not_segment_state(source_coordinator):
    coordinator = source_coordinator
    coordinator.profile = MODEL_PROFILES["H1771"]
    coordinator.boolean_control_state = {"source_0_enabled": True}
    coordinator.segment_state_source = "initial"
    source = GoveeBLESourceLight(coordinator, "source_0")
    assert source.supported_color_modes == {ColorMode.ONOFF}
    assert source.is_on is True and not source.assumed_state
    coordinator.boolean_control_state.clear()
    assert source.is_on is None and source.assumed_state


def test_source_marks_retained_power_and_flags_as_assumed(source_coordinator):
    source = GoveeBLESourceLight(source_coordinator, "left_bar")
    source_coordinator._client = None
    assert source.is_on is True and source.assumed_state
    source_coordinator._field_revisions.clear()
    source_coordinator._expected_state = {}
    assert source.is_on is None


def test_missing_source_observation_is_not_fresh_at_clock_zero(source_coordinator):
    source_coordinator._notify_started_monotonic = 0.0
    source_coordinator._field_received_at.pop("boolean_left_bar_enabled")
    assert GoveeBLESourceLight(source_coordinator, "left_bar").assumed_state


async def test_source_controls_only_its_segments_and_does_not_change_sibling(source_coordinator):
    source = GoveeBLESourceLight(source_coordinator, "left_bar")
    await source.async_turn_on(brightness=128, rgb_color=(10, 20, 30))
    source_coordinator.async_set_segment_brightness.assert_awaited_once_with(list(LEFT.segments), 50, write_guard=ANY)
    writes = source_coordinator._async_write_segment_batch.await_args.args[0]
    assert writes == [build_segment_color(LEFT.segments, 10, 20, 30, "H6046", profile=source_coordinator.profile)]
    source_coordinator.async_set_boolean_control.assert_not_awaited()
    source_coordinator.send_command.assert_not_awaited()

    await source.async_turn_off()
    source_coordinator.async_set_boolean_control.assert_awaited_once_with("left_bar_enabled", False)
    source_coordinator.send_command.assert_not_awaited()
    guard = source_coordinator._async_write_segment_batch.await_args.kwargs["write_guard"]
    source_coordinator.profile = replace(source_coordinator.profile, segment_count=11)
    with pytest.raises(ValueError, match="profile changed"):
        guard()


async def test_h607c_base_writes_only_its_own_segment_mask(source_coordinator):
    coordinator = source_coordinator
    coordinator.model = "H607C"
    coordinator.profile = device_profile("H607C", 1, 1)
    coordinator.boolean_control_state = {"pole_enabled": True, "base_enabled": True}
    source = GoveeBLESourceLight(coordinator, "base")
    await source.async_turn_on(brightness=128, rgb_color=(10, 20, 30))
    coordinator.async_set_segment_brightness.assert_awaited_once_with([9, 10, 11, 12, 13], 50, write_guard=ANY)
    writes = coordinator._async_write_segment_batch.await_args.args[0]
    assert writes == [build_segment_color([9, 10, 11, 12, 13], 10, 20, 30, "H607C", profile=coordinator.profile)]
    coordinator.async_set_boolean_control.assert_not_awaited()


async def test_h60a6_panel_brightness_does_not_invent_ring_brightness(source_coordinator):
    coordinator = source_coordinator
    coordinator.model = "H60A6"
    coordinator.profile = device_profile("H60A6", 1, 2)
    coordinator.boolean_control_state = {"panel_enabled": True, "ring_enabled": True}
    coordinator.brightness_pct = 75
    panel = GoveeBLESourceLight(coordinator, "panel")
    ring = GoveeBLESourceLight(coordinator, "ring")
    assert panel.supported_color_modes == {ColorMode.RGB}
    assert panel.brightness == 191 and panel.assumed_state
    assert ring.supported_color_modes == {ColorMode.RGB}
    assert ring.brightness is None
    await panel.async_turn_on(brightness=128)
    packet = coordinator.send_command.await_args.args[0]
    assert packet[:3] == bytes.fromhex("330432")
    coordinator.async_set_segment_brightness.assert_not_awaited()
    coordinator.async_set_boolean_control.assert_not_awaited()
    with pytest.raises(HomeAssistantError):
        await ring.async_turn_on(brightness=128)


async def test_h60a6_failed_panel_brightness_is_unknown_until_a_new_write(hass):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H60A6", configuration_url=None)
    coordinator.pact_type, coordinator.pact_code = 1, 2
    coordinator.profile = device_profile("H60A6", 1, 2)
    coordinator.is_on = True
    coordinator.boolean_control_state = {"panel_enabled": True, "ring_enabled": True}
    coordinator._notify_started_monotonic = 1.0
    coordinator._field_received_at = {"is_on": 2.0, "boolean_panel_enabled": 2.0}
    coordinator._observed_power_write_generation = coordinator._power_write_generation
    coordinator._observed_power_profile_generation = coordinator._profile_generation
    coordinator._source_power_observation_generation["boolean_panel_enabled"] = (
        coordinator._power_write_generation,
        coordinator._profile_generation,
    )
    coordinator._client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=[TimeoutError(), None]))
    coordinator._ensure_connected = AsyncMock(return_value=coordinator._client)
    panel = GoveeBLESourceLight(coordinator, "panel")
    with pytest.raises(HomeAssistantError):
        await panel.async_turn_on(brightness=128)
    assert panel.brightness is None
    assert GoveeBLELight(coordinator).brightness is None
    await coordinator.send_command(build_brightness(78, "H60A6", profile=coordinator.profile))
    assert panel.brightness == 199 and panel.assumed_state
    assert GoveeBLELight(coordinator).brightness == 199


async def test_h60a6_panel_colour_uses_only_the_panel_segment(source_coordinator):
    coordinator = source_coordinator
    coordinator.model = "H60A6"
    coordinator.profile = device_profile("H60A6", 1, 2)
    coordinator.boolean_control_state = {"panel_enabled": True, "ring_enabled": True}
    panel = GoveeBLESourceLight(coordinator, "panel")
    await panel.async_turn_on(rgb_color=(10, 20, 30))
    writes = coordinator._async_write_segment_batch.await_args.args[0]
    assert writes == [build_segment_color([13], 10, 20, 30, "H60A6", profile=coordinator.profile)]
    coordinator.async_set_boolean_control.assert_not_awaited()


@pytest.mark.parametrize(("key", "mask"), [("panel", 0x1000), ("ring", 0x0FFF)])
async def test_h60a6_source_kelvin_keeps_the_sibling_out_of_the_write_mask(source_coordinator, key, mask):
    coordinator = source_coordinator
    coordinator.model = "H60A6"
    coordinator.profile = device_profile("H60A6", 1, 3)
    coordinator.boolean_control_state = {"panel_enabled": True, "ring_enabled": True}
    source = GoveeBLESourceLight(coordinator, key)
    await source.async_turn_on(color_temp_kelvin=4000)
    packet = coordinator.async_set_segment_kelvin.await_args.args[0]
    parsed = parse_static_write(packet, "H60A6", profile=coordinator.profile)
    assert parsed is not None and parsed.segment_mask == mask and parsed.kelvin == 4000
    coordinator.async_set_boolean_control.assert_not_awaited()


async def test_source_enables_master_before_source_without_switching_sibling(source_coordinator):
    coordinator = source_coordinator
    coordinator.is_on = False
    coordinator.boolean_control_state["left_bar_enabled"] = False

    async def send(_packet, *, write_guard):
        write_guard()
        coordinator.is_on = True

    coordinator.send_command = AsyncMock(side_effect=send)
    source = GoveeBLESourceLight(coordinator, "left_bar")
    await source.async_turn_on()
    coordinator.send_command.assert_awaited_once()
    coordinator.refresh_state.assert_awaited_once_with(RefreshRequest(on=True))
    assert coordinator.async_set_boolean_control.await_args_list == [
        call("right_bar_enabled", False),
        call("left_bar_enabled", True),
    ]
    assert GoveeBLESourceLight(coordinator, "right_bar").is_on is False


async def test_h6046_source_turn_on_keeps_sibling_off_over_real_protocol(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6046", configuration_url=None)
    coordinator.pact_type, coordinator.pact_code = 1, 1
    coordinator._resolve_device_profile()
    coordinator._notify_started_monotonic = time.monotonic()
    coordinator._notification_token = object()
    client = MagicMock(is_connected=True)
    coordinator._client = client
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    state = {"power": False, "mask": 0x11}

    def notify(prefix):
        body = bytes.fromhex(prefix).ljust(19, b"\x00")
        coordinator._notify_callback(None, bytearray(body + bytes((xor_checksum(body),))))

    notify("aa0100")
    notify("aa3311")

    async def write(_uuid, packet, **_kwargs):
        if packet[:2] == b"\xaa\x33":
            notify(f"aa33{state['mask']:02x}")
        elif packet[:2] == b"\x33\x33":
            state["mask"] = packet[2]
        elif packet[:2] == b"\x33\x01":
            assert not state["mask"] & 0x10
            state["power"] = bool(packet[2])
        elif packet[:2] == b"\xaa\x01":
            notify(f"aa01{int(state['power']):02x}")
        else:
            raise AssertionError(f"unexpected packet {packet.hex()}")

    client.write_gatt_char = AsyncMock(side_effect=write)
    await GoveeBLESourceLight(coordinator, "left_bar").async_turn_on()
    assert state == {"power": True, "mask": 0x01}
    assert GoveeBLESourceLight(coordinator, "right_bar").is_on is False


@pytest.mark.parametrize("model", ["H6046", "H6053"])
@pytest.mark.parametrize("boundary", ["flags", "write"])
async def test_bar_setting_rejects_newer_foreground_before_physical_write(hass, monkeypatch, model, boundary):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", model, configuration_url=None)
    coordinator.pact_type, coordinator.pact_code = 1, 1
    if model == "H6053":
        coordinator.hw_version, coordinator.fw_version = "1.00.01", "1.08.01"
    coordinator._resolve_device_profile()
    coordinator._notification_token = object()
    coordinator._notify_started_monotonic = time.monotonic()
    coordinator._client = client = MagicMock(is_connected=True)
    coordinator._confirmed_identity_fields.update(coordinator.profile.profile_identity_fields)
    if coordinator.profile.requires_pact_confirmation:
        coordinator._observe_pact(coordinator.pact_type, coordinator.pact_code)
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    paused, admitted = asyncio.Event(), asyncio.Event()
    waits = 0

    async def wait():
        nonlocal waits
        waits += 1
        if boundary == "write" and waits == 2:
            paused.set()
            await admitted.wait()

    monkeypatch.setattr(coordinator._reply_gate, "wait", wait)

    async def write(_uuid, packet, **_kwargs):
        assert packet == frame("aa33")
        if boundary == "flags":
            paused.set()
            await admitted.wait()
        coordinator._notify_callback(None, bytearray(frame("aa3390")))

    client.write_gatt_char = AsyncMock(side_effect=write)

    async def old_setting():
        async with coordinator._control_arbiter.hold(ControlIntent.USER):
            generation = coordinator._control_arbiter.foreground_generation

            def guard():
                if coordinator._control_arbiter.foreground_generation != generation:
                    raise ValueError("Newer foreground request")

            await coordinator._async_set_verified_setting("left_bar_enabled", True, write_guard=guard)

    async def newer_foreground():
        await paused.wait()
        async with coordinator._control_arbiter.hold(ControlIntent.USER, wait=False) as acquired:
            assert not acquired
            admitted.set()

    old = asyncio.create_task(old_setting())
    newer = asyncio.create_task(newer_foreground())
    try:
        with pytest.raises(ValueError, match="Newer foreground request"):
            await old
        await newer
        assert coordinator.boolean_control_state == {"left_bar_enabled": False, "right_bar_enabled": True}
        assert coordinator.bar_enable_mask == 0x90
        assert coordinator.control_write_attempts == 0
    finally:
        for task in (old, newer):
            if not task.done():
                task.cancel()
        await asyncio.gather(old, newer, return_exceptions=True)


async def test_stale_master_state_is_refreshed_before_preserving_siblings(source_coordinator):
    coordinator = source_coordinator
    coordinator.is_on = False
    coordinator.boolean_control_state["left_bar_enabled"] = False
    coordinator._field_received_at.pop("is_on")

    async def refresh(_request):
        coordinator.is_on = True
        coordinator._field_received_at["is_on"] = 2.0
        coordinator._field_revisions["is_on"] += 1
        return True

    coordinator.refresh_state = AsyncMock(side_effect=refresh)
    source = GoveeBLESourceLight(coordinator, "left_bar")
    await source.async_turn_on()
    coordinator.send_command.assert_not_awaited()
    coordinator.async_set_boolean_control.assert_awaited_once_with("left_bar_enabled", True)
    assert GoveeBLESourceLight(coordinator, "right_bar").is_on is True


async def test_optimistic_master_write_does_not_make_an_older_power_reply_fresh(source_coordinator):
    coordinator = source_coordinator
    coordinator.is_on = True
    coordinator._power_write_generation += 1
    coordinator.boolean_control_state["left_bar_enabled"] = False

    async def refresh(request):
        coordinator.is_on = not request.refresh_all
        coordinator._field_revisions["is_on"] += 1
        coordinator._field_received_at["is_on"] = 2.0
        coordinator._observed_power_write_generation = coordinator._power_write_generation
        coordinator._observed_power_profile_generation = coordinator._profile_generation
        return True

    async def send(_packet, *, write_guard):
        write_guard()
        coordinator._power_write_generation += 1
        coordinator.is_on = True

    coordinator.refresh_state = AsyncMock(side_effect=refresh)
    coordinator.send_command = AsyncMock(side_effect=send)
    await GoveeBLESourceLight(coordinator, "left_bar").async_turn_on()
    assert coordinator.refresh_state.await_args_list[0].args[0].refresh_all is True
    assert coordinator.async_set_boolean_control.await_args_list == [
        call("right_bar_enabled", False),
        call("left_bar_enabled", True),
    ]


async def test_failed_master_confirmation_does_not_suppress_a_retry(source_coordinator):
    coordinator = source_coordinator
    coordinator.is_on = False

    async def send(_packet, *, write_guard):
        write_guard()
        coordinator.is_on = True
        coordinator.control_write_attempts += 1

    async def refresh(request):
        if request.refresh_all:
            coordinator.is_on = False
            coordinator._field_revisions["is_on"] += 1
            coordinator._unconfirmed_state_fields.discard("is_on")
            return True
        if coordinator.control_write_attempts == 1:
            return False
        coordinator._field_revisions["is_on"] += 1
        coordinator._unconfirmed_state_fields.discard("is_on")
        return True

    coordinator.send_command = AsyncMock(side_effect=send)
    coordinator.refresh_state = AsyncMock(side_effect=refresh)
    source = GoveeBLESourceLight(coordinator, "left_bar")
    with pytest.raises(HomeAssistantError):
        await source.async_turn_on()
    assert source.is_on is None and source.assumed_state
    await source.async_turn_on()
    assert coordinator.send_command.await_count == 2
    assert source.is_on is True


async def test_power_notification_before_write_does_not_confirm_a_failed_write(source_coordinator):
    coordinator = source_coordinator
    coordinator.is_on = False

    async def send(_packet, *, write_guard):
        coordinator._field_revisions["is_on"] = 1
        write_guard()
        coordinator.is_on = True
        coordinator.control_write_attempts += 1
        raise TimeoutError

    coordinator.send_command = AsyncMock(side_effect=send)
    source = GoveeBLESourceLight(coordinator, "left_bar")
    with pytest.raises(HomeAssistantError):
        await source.async_turn_on()
    assert source.is_on is None and source.assumed_state


async def test_source_colour_intent_follows_source_and_master_writes(source_coordinator):
    coordinator = source_coordinator
    source = GoveeBLESourceLight(coordinator, "left_bar")
    await coordinator.send_command(build_segment_color_temp(list(LEFT.segments), 3000, profile=coordinator.profile))
    assert source.color_temp_kelvin == 3000
    await coordinator.send_command(build_color_temp(4000, profile=coordinator.profile))
    assert source.color_temp_kelvin == 4000
    await coordinator.send_command(build_color_rgb(*table_kelvin_rgb(4000), profile=coordinator.profile))
    assert source.color_mode is ColorMode.RGB
    assert source.color_temp_kelvin is None


async def test_stale_kelvin_status_cannot_override_new_source_rgb(hass):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6046", configuration_url=None)
    coordinator.pact_type, coordinator.pact_code = 1, 1
    coordinator._resolve_device_profile()
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    coordinator._client = client
    colour = table_kelvin_rgb(4000)
    packet = build_segment_color(LEFT.segments, *colour, "H6046", profile=coordinator.profile)
    await coordinator._async_write_packet(client, packet, arm_expected=True)
    payload = bytes.fromhex("aa0515000fa00fa0").ljust(19, b"\x00")
    coordinator._notify_callback(None, bytearray(payload + bytes((xor_checksum(payload),))))
    assert coordinator.segment_kelvin[:5] == [0] * 5
    assert GoveeBLESourceLight(coordinator, "left_bar").color_mode is ColorMode.RGB
    coordinator._arm_expected(build_scene_activation("H6046", 1, profile=coordinator.profile))
    assert "source_kelvin_left_bar" not in coordinator._expected_state


@pytest.mark.parametrize("left_kelvin,right_kelvin", [(0, 0), (2199, 2199), (3123, 0), (3123, 4000)])
def test_inline_bar_readback_qualifies_complete_geometry_and_exact_mixed_intent(hass, left_kelvin, right_kelvin):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6053", configuration_url=None)
    coordinator.pact_type, coordinator.pact_code = 1, 1
    coordinator.fw_version, coordinator.hw_version = "1.00.11", "1.00.00"
    coordinator._resolve_device_profile()
    coordinator._notify_started_monotonic = time.monotonic() - 1
    coordinator._client = MagicMock(is_connected=True)
    payload = (
        bytes.fromhex("aa050d112233")
        + left_kelvin.to_bytes(2, "big")
        + bytes.fromhex("445566")
        + right_kelvin.to_bytes(2, "big")
    ).ljust(19, b"\0")
    coordinator._notify_callback(None, bytearray(payload + bytes((xor_checksum(payload),))))
    assert coordinator.segment_colors == [(17, 34, 51), (68, 85, 102)]
    assert coordinator.segment_kelvin == [left_kelvin, right_kelvin]
    assert coordinator.segment_state_source == "observed" and not coordinator.segment_brightness_readable
    assert coordinator._domain_revisions[ReadDomain.SEGMENTS] == 1
    assert coordinator.source_field_fresh("segment_colors")
    for key, kelvin in (("left_bar", left_kelvin), ("right_bar", right_kelvin)):
        source = GoveeBLESourceLight(coordinator, key)
        assert source.color_mode is (ColorMode.COLOR_TEMP if kelvin else ColorMode.RGB)
        assert source.color_temp_kelvin == (kelvin or None)
    observed = list(coordinator.segment_colors)
    rejected = bytes.fromhex("aa050dffffff00000102030001").ljust(19, b"\0")
    coordinator._notify_callback(None, bytearray(rejected + bytes((xor_checksum(rejected),))))
    assert coordinator.segment_colors == observed
    assert coordinator._domain_revisions[ReadDomain.SEGMENTS] == 1


async def test_failed_source_colour_write_releases_source_expectations(hass):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6046", configuration_url=None)
    coordinator.pact_type, coordinator.pact_code = 1, 1
    coordinator._resolve_device_profile()
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=RuntimeError))
    coordinator._client = client
    packet = build_segment_color(LEFT.segments, 1, 2, 3, "H6046", profile=coordinator.profile)
    with pytest.raises(RuntimeError):
        await coordinator._async_write_packet(client, packet, arm_expected=True)
    assert "source_kelvin_left_bar" not in coordinator._expected_state
    payload = bytes.fromhex("aa0515000fa00fa0").ljust(19, b"\x00")
    coordinator._notify_callback(None, bytearray(payload + bytes((xor_checksum(payload),))))
    assert coordinator.segment_kelvin[:5] == [4000] * 5


@pytest.mark.parametrize("modern", [False, True])
@pytest.mark.parametrize("kelvin", [2199, 3123, 4000])
async def test_native_kelvin_survives_non_table_palette_and_recovery_projection(hass, monkeypatch, modern, kelvin):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6053", configuration_url=None)
    coordinator.pact_type, coordinator.pact_code = 2 if modern else 1, 1
    coordinator.fw_version, coordinator.hw_version = "1.08.05" if modern else "1.00.11", "1.00.00"
    coordinator._resolve_device_profile()
    coordinator._notification_token = object()
    coordinator._notify_started_monotonic = time.monotonic() - 1
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    coordinator._client = client
    coordinator._observe_pact(2 if modern else 1, 1)
    coordinator._observe_identity_field("fw_version", coordinator.fw_version)
    coordinator._observe_identity_field("hw_version", coordinator.hw_version)
    monkeypatch.setattr(coordinator, "_refresh_pact_advertisements", MagicMock())
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(coordinator, "_renew_foreground_lease", MagicMock())

    def observe(value):
        for data in ("aa0101", "aa0432" if modern else "aa0488", "aa3311"):
            coordinator._notify_callback(None, bytearray(frame(data)))
        status = f"aa051500{value:04x}{value:04x}" if modern else f"aa050dffffff{value:04x}ffffff{value:04x}"
        coordinator._notify_callback(None, bytearray(frame(status)))
        if modern:
            for group in range(1, 4):
                coordinator._notify_callback(None, bytearray(frame(f"aaa5{group:02x}" + "32ffffff" * 4)))

    observe(kelvin)
    assert coordinator.segment_colors == [(255, 255, 255)] * coordinator.profile.segment_count
    assert coordinator.segment_kelvin == [kelvin] * coordinator.profile.segment_count
    state = coordinator.capture_effect_control_state()
    assert state.left_bar_kelvin == state.right_bar_kelvin == kelvin
    prepared = coordinator._prepare_static_colour(state)
    assert prepared is not None
    expected = (normalize_kelvin(kelvin, coordinator.profile),) * coordinator.profile.segment_count
    assert prepared.state.segment_kelvin == expected
    assert prepared.state.static_segment_kelvin(coordinator.profile) == expected
    assert coordinator.segment_kelvin == [kelvin] * coordinator.profile.segment_count

    async def refresh(_request):
        observe(expected[0])
        return True

    async def write(_uuid, packet, **_kwargs):
        if packet[:2] == bytes.fromhex("aa33"):
            coordinator._notify_callback(None, bytearray(frame("aa3311")))

    client.write_gatt_char.side_effect = write
    monkeypatch.setattr(coordinator, "refresh_state", AsyncMock(side_effect=refresh))
    monkeypatch.setattr(coordinator, "async_refresh_segments", AsyncMock(return_value=True))
    assert await coordinator.async_restore_effect_control_state(prepared, overwritten_diy_code=None)
    assert coordinator._same_static_appearance(prepared.state, coordinator.capture_effect_control_state())


@pytest.mark.parametrize("failure", [TimeoutError, asyncio.CancelledError])
async def test_failed_masked_colour_write_preserves_untouched_source_intent(hass, failure):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H60A6", configuration_url=None)
    coordinator.pact_type, coordinator.pact_code = 1, 3
    coordinator.profile = device_profile("H60A6", 1, 3)
    colour = table_kelvin_rgb(4000)
    coordinator.segment_colors = [colour] * 13
    coordinator.segment_state_source = "observed"
    coordinator.color_mode = ParsedMode.COLOUR
    coordinator._observed_color_mode = ParsedMode.COLOUR
    coordinator._observed_mode_write_generation = coordinator._mode_write_generation
    coordinator._observed_mode_profile_generation = coordinator._profile_generation
    coordinator._notify_started_monotonic = 1.0
    coordinator._field_received_at["color_mode"] = 2.0
    coordinator.segment_kelvin = [0] * 12 + [4000]
    coordinator._arm_expected_values({"source_kelvin_panel": 4000, "source_kelvin_ring": 0})
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=failure))
    coordinator._client = client
    packet = build_segment_color((1,), 1, 2, 3, "H60A6", profile=coordinator.profile)
    with pytest.raises(failure):
        await coordinator._async_write_packet(client, packet, arm_expected=True)
    assert coordinator.segment_kelvin == [None] + [0] * 11 + [4000]
    assert "source_kelvin_panel" in coordinator._expected_state
    assert "source_kelvin_ring" not in coordinator._expected_state
    assert GoveeBLESourceLight(coordinator, "panel").color_temp_kelvin == 4000


@pytest.mark.parametrize("profile_changed", [False, True])
@pytest.mark.parametrize("kelvin", [4000, 3123])
async def test_expired_mode_guard_does_not_hide_confirmed_sibling_kelvin(hass, profile_changed, kelvin):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6046", configuration_url=None)
    coordinator.pact_type, coordinator.pact_code = 1, 1
    coordinator._resolve_device_profile()
    coordinator._notify_started_monotonic = time.monotonic() - 1
    coordinator.segment_colors = [table_kelvin_rgb(4000)] * 10
    coordinator.segment_state_source = "observed"
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=TimeoutError))
    coordinator._client = client
    payload = bytes.fromhex(f"aa051500{kelvin:04x}{kelvin:04x}").ljust(19, b"\x00")
    coordinator._notify_callback(None, bytearray(payload + bytes((xor_checksum(payload),))))
    coordinator._expected_state["color_mode"] = ((ParsedMode.COLOUR, None), 0.0)
    if profile_changed:
        coordinator._profile_generation += 1
    packet = build_segment_color(LEFT.segments, 1, 2, 3, "H6046", profile=coordinator.profile)
    with pytest.raises(TimeoutError):
        await coordinator._async_write_packet(client, packet, arm_expected=True)
    if profile_changed:
        assert coordinator.color_mode is None
    else:
        assert coordinator.color_mode is ParsedMode.COLOUR
        assert GoveeBLESourceLight(coordinator, "right_bar").color_temp_kelvin == kelvin


async def test_expired_mode_guard_does_not_confirm_optimistic_static_mode(hass):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6046", configuration_url=None)
    coordinator.pact_type, coordinator.pact_code = 1, 1
    coordinator._resolve_device_profile()
    coordinator._notify_started_monotonic = time.monotonic() - 1
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=[None, TimeoutError()]))
    coordinator._client = client
    payload = bytes.fromhex("aa05040100").ljust(19, b"\x00")
    coordinator._notify_callback(None, bytearray(payload + bytes((xor_checksum(payload),))))
    first = build_segment_color(LEFT.segments, 1, 2, 3, "H6046", profile=coordinator.profile)
    second = build_segment_color(RIGHT.segments, 4, 5, 6, "H6046", profile=coordinator.profile)
    await coordinator._async_write_packet(client, first, arm_expected=True)
    coordinator._expected_state["color_mode"] = ((ParsedMode.COLOUR, None), 0.0)
    with pytest.raises(TimeoutError):
        await coordinator._async_write_packet(client, second, arm_expected=True)
    assert coordinator.color_mode is None
    assert "color_mode" in coordinator._unconfirmed_state_fields


@pytest.mark.parametrize("failure", [TimeoutError, asyncio.CancelledError])
@pytest.mark.parametrize("operation", ["rgb", "brightness"])
@pytest.mark.parametrize("previous_mode", [ParsedMode.SCENE, ParsedMode.COLOUR])
async def test_failed_scene_to_static_write_stays_unknown_until_mode_reply(hass, failure, operation, previous_mode):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6046", configuration_url=None)
    coordinator.pact_type, coordinator.pact_code = 1, 1
    coordinator._resolve_device_profile()
    coordinator.color_mode = previous_mode
    coordinator._field_revisions["color_mode"] = 1
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=failure))
    coordinator._client = client
    packet = (
        build_segment_color(LEFT.segments, 1, 2, 3, "H6046", profile=coordinator.profile)
        if operation == "rgb"
        else build_segment_brightness(LEFT.segments, 50, "H6046", profile=coordinator.profile)
    )
    with pytest.raises(failure):
        await coordinator._async_write_packet(client, packet, arm_expected=True)
    assert coordinator.color_mode is None
    assert GoveeBLESourceLight(coordinator, "left_bar").color_mode is ColorMode.UNKNOWN
    main = GoveeBLELight(coordinator)
    assert main.color_mode is ColorMode.UNKNOWN and main.extra_restore_state_data is None
    assert not main._can_restore_static_color
    assert "color_mode" not in coordinator._expected_state
    payload = bytes.fromhex("aa05040100").ljust(19, b"\x00")
    coordinator._notify_callback(None, bytearray(payload + bytes((xor_checksum(payload),))))
    assert coordinator.color_mode is ParsedMode.SCENE
    assert "color_mode" not in coordinator._unconfirmed_state_fields


async def test_failed_segment_brightness_keeps_source_colour_intents(hass):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6046", configuration_url=None)
    coordinator.pact_type, coordinator.pact_code = 1, 1
    coordinator._resolve_device_profile()
    coordinator.color_mode = ParsedMode.COLOUR
    coordinator.segment_kelvin = [4000] * 5 + [2700] * 5
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=TimeoutError))
    coordinator._client = client
    packet = build_segment_brightness(LEFT.segments, 50, "H6046", profile=coordinator.profile)
    with pytest.raises(TimeoutError):
        await coordinator._async_write_packet(client, packet, arm_expected=True)
    assert coordinator.segment_kelvin == [4000] * 5 + [2700] * 5


async def test_successful_retry_after_failed_source_write_is_optimistic(hass):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6046", configuration_url=None)
    coordinator.pact_type, coordinator.pact_code = 1, 1
    coordinator._resolve_device_profile()
    coordinator.color_mode = ParsedMode.SCENE
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=[TimeoutError(), None]))
    coordinator._client = client
    packet = build_segment_color(LEFT.segments, 1, 2, 3, "H6046", profile=coordinator.profile)
    with pytest.raises(TimeoutError):
        await coordinator._async_write_packet(client, packet, arm_expected=True)
    await coordinator._async_write_packet(client, packet, arm_expected=True)
    assert coordinator.color_mode is ParsedMode.COLOUR
    assert "color_mode" not in coordinator._unconfirmed_state_fields
    assert "color" in coordinator._unconfirmed_state_fields
    assert GoveeBLELight(coordinator).assumed_state


async def test_native_rgb_readback_invalidates_matching_source_kelvin(hass):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6046", configuration_url=None)
    coordinator.pact_type, coordinator.pact_code = 1, 1
    coordinator._resolve_device_profile()
    coordinator.profile = replace(coordinator.profile, light_sources=(LEFT, RIGHT))
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    coordinator._client = client
    source = GoveeBLESourceLight(coordinator, "left_bar")
    await coordinator._async_write_packet(
        client,
        build_segment_color_temp(list(LEFT.segments), 3000, "H6046", profile=coordinator.profile),
        arm_expected=True,
    )
    assert source.color_temp_kelvin == 3000
    coordinator._expected_state.clear()
    payload = bytes.fromhex("aa05150000000000").ljust(19, b"\x00")
    coordinator._notify_callback(None, bytearray(payload + bytes((xor_checksum(payload),))))
    assert source.color_mode is ColorMode.RGB
    assert source.color_temp_kelvin is None


async def test_source_rejects_unsupported_controls_before_writing(source_coordinator):
    coordinator = source_coordinator
    coordinator.profile = replace(coordinator.profile, supports_segment_brightness=False)
    source = GoveeBLESourceLight(coordinator, "left_bar")
    assert source.supported_color_modes == {ColorMode.RGB, ColorMode.COLOR_TEMP}
    assert source.brightness is None
    with pytest.raises(HomeAssistantError):
        await source.async_turn_on(brightness=128)
    coordinator.send_command.assert_not_awaited()
    coordinator.async_set_boolean_control.assert_not_awaited()
    coordinator.async_set_segment_brightness.assert_not_awaited()


@pytest.mark.parametrize(
    ("failure", "raised"), [(TimeoutError, HomeAssistantError), (asyncio.CancelledError, asyncio.CancelledError)]
)
async def test_rejected_source_off_preserves_observations_before_turn_on(source_coordinator, failure, raised):
    coordinator = source_coordinator

    async def fail_write(*_args):
        coordinator.control_write_attempts += 1
        raise failure

    coordinator.async_set_boolean_control = AsyncMock(side_effect=fail_write)
    source = GoveeBLESourceLight(coordinator, "left_bar")
    with pytest.raises(raised):
        await source.async_turn_off()
    assert source.is_on is True
    assert coordinator._field_received_at["boolean_left_bar_enabled"] == 2.0
    coordinator.async_set_boolean_control = AsyncMock()
    await source.async_turn_on()
    coordinator.async_set_boolean_control.assert_not_awaited()


def test_source_availability_tracks_effective_profile(source_coordinator):
    source = GoveeBLESourceLight(source_coordinator, "left_bar")
    assert source.available
    source_coordinator.profile = replace(
        source_coordinator.profile,
        boolean_controls=source_coordinator.profile.boolean_controls - {"left_bar_enabled"},
    )
    assert not source.available
