import asyncio
import time
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError
from homeassistant.components.light import ColorMode
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component

from custom_components.ha_govee_led_ble.const import ReadDomain, device_profile
from custom_components.ha_govee_led_ble.control_arbiter import ControlIntent
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_refresh import RefreshRequest
from custom_components.ha_govee_led_ble.coordinator_sources import SourceTurnOnRequest
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode
from custom_components.ha_govee_led_ble.effect_backend import EffectBackend
from custom_components.ha_govee_led_ble.effect_catalogue import MODEL_EFFECT_CATALOGUES
from custom_components.ha_govee_led_ble.effect_compiler import compile_effect, validate_compiled_geometry
from custom_components.ha_govee_led_ble.effect_deployments import PriorControlState
from custom_components.ha_govee_led_ble.effect_domain import BuiltinScene, CatalogueRef, LibraryItem
from custom_components.ha_govee_led_ble.effect_runtime import async_prepare_effect_control_state
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_boolean_control,
    build_boolean_control_query,
    build_brightness,
    build_colour_mode_query,
    build_hardware_query,
    build_pact_query,
    build_power,
    build_power_on_behaviour,
    build_segment_query,
    build_source_value,
    parse_a3_effect_envelope,
    parse_command_ack_result,
    require_profile_packet,
    table_kelvin_rgb,
    upload_ack_mode,
    upload_ack_subtype,
    upload_ack_success,
)
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.light_commands import (
    build_color_rgb,
    build_color_temp,
    build_segment_brightness,
    build_segment_brightness_packets,
    build_segment_color,
    build_segment_color_temp,
    build_segment_paint,
    parse_static_write,
)
from custom_components.ha_govee_led_ble.light_source import GoveeBLESourceLight
from custom_components.ha_govee_led_ble.music_commands import prepare_music_request
from custom_components.ha_govee_led_ble.protocol_core import serialize_native_body
from custom_components.ha_govee_led_ble.scenes import MODEL_SCENES
from custom_components.ha_govee_led_ble.transport import reassemble_a3, xor_checksum

PROFILE = device_profile("H60B0", 1, 2)


def frame(prefix: str) -> bytes:
    content = bytes.fromhex(prefix).ljust(19, b"\x00")
    return content + bytes((xor_checksum(content),))


@pytest.mark.parametrize("pact_code", [1, 2, 3])
@pytest.mark.parametrize("colour", [{"rgb_color": (1, 2, 3)}, {"color_temp_kelvin": 5000}])
async def test_main_colour_uses_area_controls_without_changing_selection(source_wire, pact_code, colour):
    coordinator, state = source_wire
    coordinator.profile = device_profile("H60B0", 1, pact_code)
    coordinator._authorization_profile.return_value = coordinator.profile
    state["apply"] = True
    state["flags"] = 0xB0
    assert await coordinator.refresh_state(RefreshRequest(refresh_all=True, query_segments=True))
    coordinator._client.write_gatt_char.reset_mock()
    light = GoveeBLELight(coordinator)
    light.async_write_ha_state = MagicMock()
    assert light.supported_color_modes == {ColorMode.RGB, ColorMode.COLOR_TEMP}
    for key in ("top", "side"):
        assert GoveeBLESourceLight(coordinator, key).supported_color_modes == {ColorMode.RGB, ColorMode.COLOR_TEMP}
    assert GoveeBLESourceLight(coordinator, "bottom").supported_color_modes == {ColorMode.COLOR_TEMP}
    await light.async_turn_on(**colour)
    physical_writes = [
        call.args[1] for call in coordinator._client.write_gatt_char.await_args_list if call.args[1][0] == 0x33
    ]
    if "rgb_color" in colour:
        assert physical_writes == [frame("33052c01010102030000"), frame("33052c02010102030000ff00")]
        assert state["colours"] == [(1, 2, 3)] * 9
        assert state["bottom"] == 4000
        assert light.color_mode is ColorMode.RGB
        assert light.rgb_color is None
    else:
        preview = bytes(table_kelvin_rgb(5000)).hex()
        assert physical_writes == [
            frame(f"33052c0101{preview}1388"),
            frame(f"33052c0201{preview}1388ff00"),
            frame("33052c03011388"),
        ]
        assert state["colours"] == [table_kelvin_rgb(5000)] * 9
        assert state["bottom"] == 5000
        assert light.color_temp_kelvin == 5000
        assert GoveeBLESourceLight(coordinator, "bottom").color_temp_kelvin == 5000
    assert state["flags"] == 0xB0
    assert state["levels"] == [40] * 8 + [60]
    assert state["bottom_brightness"] == 40
    assert light.brightness is not None


@pytest.mark.parametrize(
    ("flags", "colours", "mode", "rgb", "kelvin"),
    [
        (0xA0, [(0, 0, 255)] * 8 + [table_kelvin_rgb(2700)], ColorMode.RGB, (0, 0, 255), None),
        (0xE0, [(0, 0, 255)] * 8 + [table_kelvin_rgb(2700)], ColorMode.RGB, None, None),
        (0xB0, [(0, 0, 255)] * 9, ColorMode.RGB, None, None),
        (0x90, [(0, 0, 255)] * 9, ColorMode.COLOR_TEMP, None, 4000),
        (0x80, [(0, 0, 255)] * 9, ColorMode.UNKNOWN, None, None),
    ],
)
async def test_main_colour_after_reload_uses_only_known_enabled_areas(source_wire, flags, colours, mode, rgb, kelvin):
    coordinator, state = source_wire
    coordinator.segment_kelvin = [None] * 9
    state.update(flags=flags, colours=colours)
    assert await coordinator.refresh_state(RefreshRequest(refresh_all=True, query_segments=True))
    light = GoveeBLELight(coordinator)
    assert light.color_mode is mode
    assert light.rgb_color == rgb
    assert light.color_temp_kelvin == kelvin
    assert light.supported_color_modes == {ColorMode.RGB, ColorMode.COLOR_TEMP}
    coordinator.boolean_control_state.pop("top_enabled")
    assert light.color_mode is ColorMode.UNKNOWN
    assert light.rgb_color is None
    assert light.color_temp_kelvin is None


@pytest.mark.parametrize(
    "side_colours", [[table_kelvin_rgb(6500)] * 8, [(0, 0, 255)] * 8, [(1, 2, 3)] + [table_kelvin_rgb(6500)] * 7]
)
async def test_shared_kelvin_hint_after_reload_requires_matching_complete_source(source_wire, side_colours):
    coordinator, state = source_wire
    coordinator.segment_kelvin = [None] * 9
    state.update(flags=0xB0, top=6500, bottom=6500, colours=side_colours + [table_kelvin_rgb(6500)])
    assert await coordinator.refresh_state(RefreshRequest(refresh_all=True, query_segments=True))
    side = GoveeBLESourceLight(coordinator, "side")
    main = GoveeBLELight(coordinator)
    white = side_colours == [table_kelvin_rgb(6500)] * 8
    assert side.color_mode is (ColorMode.COLOR_TEMP if white else ColorMode.RGB)
    assert side.color_temp_kelvin == (6500 if white else None)
    assert main.color_mode is (ColorMode.COLOR_TEMP if white else ColorMode.RGB)
    assert main.color_temp_kelvin == (6500 if white else None)
    captured = coordinator.capture_effect_control_state()
    assert captured.segment_kelvin[:8] == (None,) * 8
    assert all(call.args[1][0] == 0xAA for call in coordinator._client.write_gatt_char.await_args_list)


@pytest.mark.parametrize("segments_first", [False, True])
async def test_shared_kelvin_hint_needs_current_mode_and_complete_segment_observation(source_wire, segments_first):
    coordinator, _state = source_wire
    coordinator.segment_kelvin = [None] * 9
    coordinator._field_received_at.clear()
    coordinator.segment_state_source = "initial"
    side = GoveeBLESourceLight(coordinator, "side")
    mode = frame("aa052c196432196464")
    pages = [
        frame("aaa501" + "64fff9fb" * 4),
        frame("aaa502" + "64fff9fb" * 4),
        frame("aaa50364fff9fb"),
    ]
    first, last = (pages, [mode]) if segments_first else ([mode] + pages[:2], pages[2:])
    for packet in first:
        coordinator._notify_callback(None, bytearray(packet))
        assert side.color_temp_kelvin is None
    for packet in last:
        coordinator._notify_callback(None, bytearray(packet))
    assert side.color_temp_kelvin == 6500
    coordinator._notify_started_monotonic = time.monotonic()
    coordinator._notify_callback(None, bytearray(mode))
    assert side.color_temp_kelvin is None


async def test_explicit_source_rgb_is_not_reclassified_by_shared_kelvin_hint(source_wire):
    coordinator, state = source_wire
    state.update(apply=True, flags=0xA0, top=6500, colours=[table_kelvin_rgb(6500)] * 9)
    coordinator.segment_kelvin = [None] * 9
    assert await coordinator.refresh_state(RefreshRequest(refresh_all=True, query_segments=True))
    side = GoveeBLESourceLight(coordinator, "side")
    await side.async_turn_on(rgb_color=table_kelvin_rgb(6500))
    assert side.color_mode is ColorMode.RGB
    assert side.color_temp_kelvin is None
    assert GoveeBLELight(coordinator).rgb_color == table_kelvin_rgb(6500)
    assert (await coordinator.async_prepare_static_baseline()).segment_kelvin[:8] == (0,) * 8


@pytest.mark.parametrize("previous_kelvin", [False, True])
async def test_external_source_colour_supersedes_contradicted_intent(source_wire, virtual_clock, previous_kelvin):
    coordinator, state = source_wire
    state.update(apply=True, flags=0xA0)
    side = GoveeBLESourceLight(coordinator, "side")
    await side.async_turn_on(**({"color_temp_kelvin": 5000} if previous_kelvin else {"rgb_color": (0, 0, 255)}))
    await asyncio.sleep(10)
    colour = (0, 0, 255) if previous_kelvin else table_kelvin_rgb(6500)
    state.update(top=6500, colours=[colour] * 9)
    assert await coordinator.refresh_state(RefreshRequest(refresh_all=True, query_segments=True))
    main = GoveeBLELight(coordinator)
    assert side.rgb_color == main.rgb_color
    assert side.color_temp_kelvin == main.color_temp_kelvin
    assert main.color_mode is (ColorMode.RGB if previous_kelvin else ColorMode.COLOR_TEMP)
    assert (main.rgb_color if previous_kelvin else main.color_temp_kelvin) == ((0, 0, 255) if previous_kelvin else 6500)


@pytest.mark.parametrize(("paint_segment", "powered_off"), [(False, False), (True, False), (True, True)])
async def test_complete_source_rgb_layout_survives_scene_after_reload(
    source_wire, virtual_clock, paint_segment, powered_off
):
    coordinator, state = source_wire
    state["apply"] = True
    coordinator.segment_kelvin = [None] * 9
    assert await coordinator.refresh_state(RefreshRequest(refresh_all=True, query_segments=True))
    if paint_segment:
        await GoveeBLESourceLight(coordinator, "side").async_turn_on(rgb_color=(0, 0, 255))
        await coordinator.async_paint_segments([([1], (0, 255, 0))])
    if powered_off:
        await coordinator.send_command(build_power(False, "H60B0"))
        assert await coordinator.refresh_state(RefreshRequest(refresh_all=True, query_segments=True))
    expected_colours, expected_levels = list(state["colours"]), list(state["levels"])
    await coordinator.async_apply_native_scene("rainbow", verify=False)
    before = coordinator._pre_mode_snapshot
    assert before.static_segment_kelvin(PROFILE) is not None
    assert PriorControlState.from_dict(before.to_dict()) == before
    state.update(top=0, colours=[(255, 0, 0)] * 9)
    coordinator.segment_kelvin = [None] * 9
    coordinator.color_mode = ParsedMode.SCENE
    await coordinator.async_restore_pre_mode()
    assert state["colours"] == expected_colours
    assert state["levels"] == expected_levels
    assert (state["flags"], state["bottom"], state["bottom_brightness"]) == (0x60 if powered_off else 0xE0, 4000, 40)


@pytest.mark.parametrize("pact_code", [1, 2, 3])
async def test_partial_kelvin_preserves_per_position_semantics_through_scene(source_wire, virtual_clock, pact_code):
    coordinator, state = source_wire
    coordinator.profile = device_profile("H60B0", 1, pact_code)
    coordinator._authorization_profile.return_value = coordinator.profile
    state["apply"] = True
    await GoveeBLESourceLight(coordinator, "side").async_turn_on(rgb_color=table_kelvin_rgb(4000))
    await coordinator.async_set_segment_kelvin(
        build_segment_color_temp([1, 3], 4000, "H60B0", profile=coordinator.profile), requested_kelvin=4000
    )
    assert await coordinator.refresh_state(RefreshRequest(refresh_all=True, query_segments=True))
    before = coordinator.capture_effect_control_state()
    assert before.segment_kelvin == (4000, 0, 4000, 0, 0, 0, 0, 0, 2700)
    assert PriorControlState.from_dict(before.to_dict()) == before
    await coordinator.send_command(frame("3305040100"))
    state.update(top=0, colours=[(255, 0, 0)] * 9)
    coordinator.color_mode = ParsedMode.SCENE
    await coordinator.async_restore_pre_mode()
    assert coordinator.capture_effect_control_state().segment_kelvin == before.segment_kelvin
    assert tuple(state["colours"]) == before.segment_colors
    assert tuple(state["levels"]) == before.segment_brightness
    assert (state["bottom"], state["bottom_brightness"], state["ripple"]) == (4000, 40, 50)


@pytest.mark.parametrize("prior_on", [False, True])
async def test_incomplete_colour_snapshot_cannot_mutate_native_sources(source_wire, prior_on):
    coordinator, state = source_wire
    assert await coordinator.refresh_state(RefreshRequest(refresh_all=True, query_segments=True))
    before = coordinator.capture_effect_control_state()
    invalid = replace(
        before,
        is_on=prior_on,
        segment_colors=None,
        segment_brightness=None,
        segment_kelvin=None,
        bottom_kelvin=6500,
        bottom_brightness=100,
    )
    coordinator._client.write_gatt_char.reset_mock()
    assert not await coordinator.async_restore_effect_control_state(invalid, overwritten_diy_code=None)
    writes = [call.args[1] for call in coordinator._client.write_gatt_char.await_args_list if call.args[1][0] == 0x33]
    assert writes == ([] if prior_on else [build_power(False, "H60B0")])
    assert (state["bottom"], state["bottom_brightness"]) == (4000, 40)


async def test_guarded_old_palette_cannot_authorise_fallback_recovery(source_wire):
    coordinator, state = source_wire
    state["apply"] = True
    await GoveeBLESourceLight(coordinator, "side").async_turn_on(rgb_color=(0, 255, 0))
    assert await coordinator.refresh_state(RefreshRequest(refresh_all=True, query_segments=True))
    await coordinator.send_command(build_segment_color(range(1, 9), 0, 255, 0, "H60B0", profile=PROFILE))
    coordinator._notify_callback(None, bytearray(frame("aa052c0a8c320fa028")))
    for group in range(1, 4):
        body = "28640000" * 4 if group < 3 else "3c" + bytes(table_kelvin_rgb(2700)).hex()
        coordinator._notify_callback(None, bytearray(frame(f"aaa5{group:02x}" + body)))
    assert coordinator.segment_state_source == "observed"
    prior = coordinator.capture_effect_control_state()
    assert prior.segment_colors is None
    assert prior.static_segment_kelvin(PROFILE) is None
    coordinator._client.write_gatt_char.reset_mock()
    assert await async_prepare_effect_control_state(coordinator, require_restorable_static=True)
    assert coordinator.capture_effect_control_state().segment_colors[:8] == ((0, 255, 0),) * 8
    assert all(call.args[1][0] == 0xAA for call in coordinator._client.write_gatt_char.await_args_list)


async def test_mixed_source_layout_keeps_brightness_in_ha_state(hass, source_wire):
    coordinator, physical = source_wire
    physical.update(apply=True, flags=0xE0)
    assert await coordinator.refresh_state(RefreshRequest(refresh_all=True, query_segments=True))
    light = GoveeBLELight(coordinator)
    light._attr_device_info = None
    light.async_added_to_hass = AsyncMock()
    assert await async_setup_component(hass, "light", {})
    await hass.data["light"].async_add_entities([light])
    state = hass.states.get(light.entity_id)
    assert state.attributes["brightness"] == 128
    assert state.attributes["rgb_color"] is None
    assert state.attributes["color_temp_kelvin"] is None


async def test_main_ha_service_delivers_colour_instead_of_filtering_it(hass, source_wire):
    coordinator, physical = source_wire
    physical["apply"] = True
    assert await coordinator.refresh_state(RefreshRequest(refresh_all=True, query_segments=True))
    light = GoveeBLELight(coordinator)
    light._attr_device_info = None
    light.async_added_to_hass = AsyncMock()
    assert await async_setup_component(hass, "light", {})
    await hass.data["light"].async_add_entities([light])
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": light.entity_id, "rgb_color": [1, 2, 3]}, blocking=True
    )
    state = hass.states.get(light.entity_id)
    assert set(state.attributes["supported_color_modes"]) == {"rgb", "color_temp"}
    assert tuple(state.attributes["rgb_color"]) == (1, 2, 3)
    assert physical["colours"] == [(1, 2, 3)] * 9


@pytest.mark.parametrize(
    "colour",
    [{"rgb_color": (256, 0, 0)}, {"rgb_color": (1, 2, 3), "color_temp_kelvin": 4000}],
)
async def test_invalid_main_colour_is_rejected_before_power_brightness_or_preview(source_wire, colour):
    coordinator, state = source_wire
    state["flags"] = 0x30
    coordinator.is_on = False
    light = GoveeBLELight(coordinator)
    light._async_supersede_preview = AsyncMock()
    with pytest.raises(HomeAssistantError):
        await light.async_turn_on(brightness=128, **colour)
    light._async_supersede_preview.assert_not_awaited()
    coordinator._client.write_gatt_char.assert_not_awaited()


async def test_partial_main_kelvin_preserves_confirmed_areas_and_reconciles_bottom(source_wire, virtual_clock):
    coordinator, state = source_wire
    state["flags"] = 0xB0
    state["apply"] = True
    state["ignore_bottom_kelvin"] = True
    light = GoveeBLELight(coordinator)
    with pytest.raises(HomeAssistantError) as error:
        await light.async_turn_on(color_temp_kelvin=5000)
    assert error.value.translation_key == "partial_command"
    assert state["top"] == 5000
    assert state["colours"] == [table_kelvin_rgb(5000)] * 9
    assert state["bottom"] == 4000
    assert GoveeBLESourceLight(coordinator, "top").color_temp_kelvin == 5000
    assert GoveeBLESourceLight(coordinator, "side").color_temp_kelvin == 5000
    assert GoveeBLESourceLight(coordinator, "bottom").color_temp_kelvin == 4000
    assert light.color_temp_kelvin is None
    assert light.rgb_color is None
    writes = [call.args[1] for call in coordinator._client.write_gatt_char.await_args_list if call.args[1][0] == 0x33]
    assert len(writes) == 3
    assert "bottom_kelvin" not in coordinator._expected_state


async def test_main_kelvin_rejects_contradictory_final_native_observation(source_wire):
    coordinator, state = source_wire
    state["flags"] = 0xB0
    state["apply"] = True
    state["mode_bottom"] = 4000
    light = GoveeBLELight(coordinator)
    with pytest.raises(HomeAssistantError) as error:
        await light.async_turn_on(color_temp_kelvin=5000)
    assert error.value.translation_key == "partial_command"
    assert GoveeBLESourceLight(coordinator, "bottom").color_temp_kelvin == 4000
    assert light.color_temp_kelvin is None
    writes = [call.args[1] for call in coordinator._client.write_gatt_char.await_args_list if call.args[1][0] == 0x33]
    assert len(writes) == 3


async def test_hidden_observed_scene_does_not_expose_static_main_colour(source_wire):
    coordinator, state = source_wire
    state["colours"] = [(1, 2, 3)] * 9
    coordinator._notify_callback(None, bytearray(frame("aa05049999")))
    assert await coordinator.async_refresh_segments()
    light = GoveeBLELight(coordinator)
    assert coordinator.color_mode is ParsedMode.SCENE
    assert light.effect == "off"
    assert light.color_mode is ColorMode.BRIGHTNESS
    assert light.rgb_color is None
    assert light.color_temp_kelvin is None


@pytest.fixture
def native_sources(hass):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H60B0", configuration_url=None)
    coordinator.profile = PROFILE
    coordinator.pact_type, coordinator.pact_code = 1, 2
    coordinator._confirmed_identity_fields.add("pact")
    coordinator._refresh_h607c_advertisements = lambda: None
    client = MagicMock(is_connected=True, disconnect=AsyncMock())
    coordinator._client = client
    coordinator._notification_token = object()
    coordinator._notify_started_monotonic = time.monotonic() - 1
    coordinator._ensure_connected = AsyncMock(return_value=client)
    coordinator._async_supersede_effect_preview = AsyncMock()
    physical = {}

    def observe(flags=0xE0):
        physical.update(
            {
                control: bool(flags & mask)
                for control, mask in (("top_enabled", 0x40), ("side_enabled", 0x20), ("bottom_enabled", 0x10))
            }
        )
        coordinator._notify_callback(None, bytearray(frame(f"aa42{flags:02x}0a8c320a8c64")))

    async def write(_client, packet, **kwargs):
        if guard := kwargs.get("before_write"):
            guard()
        if packet[:2] == bytes.fromhex("aa42"):
            flags = 0x80 | sum(
                mask
                for control, mask in (("top_enabled", 0x40), ("side_enabled", 0x20), ("bottom_enabled", 0x10))
                if physical.get(control)
            )
            observe(flags)

    async def send(packet, **kwargs):
        if guard := kwargs.get("write_guard"):
            guard()
        coordinator.control_write_attempts += 1
        if on_write := kwargs.get("on_write"):
            on_write()
        control = {1: "top_enabled", 2: "side_enabled", 3: "bottom_enabled"}[packet[2]]
        enabled = bool(packet[3])
        physical[control] = enabled
        if enabled:
            for group in coordinator.profile.exclusive_source_groups:
                if control in group:
                    physical.update({name: False for name in group if name != control})
        await asyncio.sleep(0)

    coordinator._async_write_packet = AsyncMock(side_effect=write)
    coordinator.send_command = AsyncMock(side_effect=send)
    observe()
    return coordinator, observe


async def test_native_source_power_requires_current_pact_confirmation(native_sources):
    coordinator, observe = native_sources
    observe(0xA0)
    coordinator._confirmed_identity_fields.discard("pact")
    with pytest.raises(HomeAssistantError) as error:
        await coordinator.async_set_boolean_control("top_enabled", True)
    assert error.value.translation_key == "identity_not_ready"
    coordinator.send_command.assert_not_awaited()


@pytest.mark.parametrize(
    ("flags", "control", "enabled", "key"),
    [
        (0xE0, "bottom_enabled", True, "source_limit"),
        (0xA0, "side_enabled", False, "last_source"),
    ],
)
async def test_native_source_constraints_reject_before_write(native_sources, flags, control, enabled, key):
    coordinator, observe = native_sources
    observe(flags)
    before = dict(coordinator.boolean_control_state)
    with pytest.raises(HomeAssistantError) as error:
        await coordinator.async_set_source_enabled(control.removesuffix("_enabled"), enabled)
    assert error.value.translation_key == key
    coordinator.send_command.assert_not_awaited()
    assert coordinator.boolean_control_state == before


async def test_concurrent_source_enables_cannot_exceed_native_limit(native_sources):
    coordinator, observe = native_sources
    observe(0xA0)
    results = await asyncio.gather(
        coordinator.async_set_boolean_control("top_enabled", True),
        coordinator.async_set_boolean_control("bottom_enabled", True),
        return_exceptions=True,
    )
    assert sum(isinstance(result, HomeAssistantError) for result in results) == 1
    assert sum(coordinator.boolean_control_state.values()) == 2
    assert coordinator.send_command.await_count == 1


async def test_original_revision_swaps_top_and_bottom_without_disabling_side(native_sources):
    coordinator, observe = native_sources
    coordinator.profile = device_profile("H60B0", 1, 1)
    observe(0xB0)
    await coordinator.async_set_boolean_control("top_enabled", True)
    assert coordinator.boolean_control_state == {"top_enabled": True, "side_enabled": True, "bottom_enabled": False}
    assert [call.args[0] for call in coordinator.send_command.await_args_list] == [frame("33300101")]


async def test_source_selection_change_before_physical_write_is_rejected(native_sources):
    coordinator, observe = native_sources
    observe(0xA0)

    async def change_before_write(_packet, **kwargs):
        observe(0xB0)
        kwargs["write_guard"]()

    coordinator.send_command.side_effect = change_before_write
    with pytest.raises(ValueError, match="selection changed"):
        await coordinator.async_set_boolean_control("top_enabled", True)
    assert coordinator.control_write_attempts == 0
    assert coordinator.boolean_control_state == {"top_enabled": False, "side_enabled": True, "bottom_enabled": True}


@pytest.fixture
def source_wire(native_sources):
    coordinator, _observe = native_sources
    client = coordinator._client
    coordinator._async_write_packet = GoveeBLECoordinator._async_write_packet.__get__(coordinator)
    coordinator.send_command = GoveeBLECoordinator.send_command.__get__(coordinator)
    coordinator.async_prepare_identity_gated_control = AsyncMock(return_value=lambda: None)
    coordinator._authorization_profile = MagicMock(return_value=PROFILE)
    state = {
        "apply": False,
        "flags": 0xE0,
        "top": 2700,
        "colours": [(0, 0, 255)] * 8 + [table_kelvin_rgb(2700)],
        "levels": [40] * 8 + [60],
        "ripple": 50,
        "bottom_brightness": 40,
        "bottom": 4000,
        "drop_source_readback": False,
        "scene": None,
        "master": 50,
    }

    async def write(_uuid, packet, **_kwargs):
        command = packet[1]
        if packet[0] == 0x33 and state["apply"]:
            if command == 0x05 and packet[2] == 0x2C:
                state["scene"] = None
            if command == 0x01:
                state["flags"] = state["flags"] | 0x80 if packet[2] else state["flags"] & ~0x80
            elif command == 0x04:
                state["master"] = packet[2]
            elif command == 0x30:
                mask = {1: 0x40, 2: 0x20, 3: 0x10}[packet[2]]
                state["flags"] = state["flags"] | mask if packet[3] else state["flags"] & ~mask
            elif command == 0x05 and packet[2:5] == bytes.fromhex("2c0103"):
                state["ripple"] = packet[5]
            elif command == 0x05 and packet[2:5] == bytes.fromhex("2c0302"):
                state["bottom_brightness"] = packet[5]
            elif command == 0x05 and packet[2:5] in (bytes.fromhex("2c0301"), bytes.fromhex("2c0303")):
                if not state.get("ignore_bottom_kelvin"):
                    state["bottom"] = int.from_bytes(packet[5:7], "big")
            if command == 0x05 and packet[2] == 0x2C and packet[3] in (1, 2) and packet[4] in (1, 2):
                source, operation = packet[3:5]
                mask = (
                    0x100 if source == 1 else int.from_bytes(packet[10:12] if operation == 1 else packet[6:8], "little")
                )
                for index in range(9):
                    if mask & (1 << index):
                        if operation == 1:
                            state["colours"][index] = tuple(packet[5:8])
                        else:
                            state["levels"][index] = packet[5]
                if source == 1 and operation == 1:
                    state["top"] = int.from_bytes(packet[8:10], "big")
            elif command == 0x05 and packet[2] == 0x04:
                state["scene"] = packet[3:5].hex()
                state["colours"] = [(255, 0, 0)] * 9
        if packet[0] != 0xAA:
            return
        if command in (0x05, 0x42):
            if command == 0x42 and state["drop_source_readback"]:
                return
            if command == 0x05 and state["scene"] is not None:
                coordinator._notify_callback(None, bytearray(frame(f"aa0504{state['scene']}")))
                return
            prefix = "aa052c" if command == 0x05 else f"aa42{state['flags']:02x}"
            bottom = state.get("mode_bottom", state["bottom"]) if command == 0x05 else state["bottom"]
            response = frame(
                prefix + f"{state['top']:04x}{state['ripple']:02x}{bottom:04x}{state['bottom_brightness']:02x}"
            )
        elif command == 0xA5:
            group = packet[2]
            offset = (group - 1) * 4
            body = "".join(
                f"{state['levels'][index]:02x}" + bytes(state["colours"][index]).hex()
                for index in range(offset, min(offset + 4, 9))
            )
            response = frame(f"aaa5{group:02x}" + body)
        elif command == 0x01:
            response = frame(f"aa01{int(bool(state['flags'] & 0x80)):02x}")
        elif command == 0x04:
            response = frame(f"aa04{state['master']:02x}")
        else:
            return
        coordinator._notify_callback(None, bytearray(response))

    client.write_gatt_char = AsyncMock(side_effect=write)
    coordinator.color_mode = ParsedMode.COLOUR
    coordinator.segment_kelvin = [0] * 8 + [2700]
    coordinator.segment_colors = list(state["colours"])
    return coordinator, state


@pytest.mark.parametrize("layout", ["mixed", "white", "external"])
async def test_public_scene_stop_preserves_complete_pre_effect_layout(hass, source_wire, virtual_clock, layout):
    coordinator, physical = source_wire
    physical.update(
        apply=True,
        top=0,
        bottom=6500 if layout == "white" else 4000,
        flags=0xB0 if layout == "white" else 0xE0,
        colours=([(255, 249, 251)] * 8 if layout == "white" else [(0, 0, 255)] * 8) + [(255, 120, 0)],
    )
    coordinator.segment_kelvin = [None] * 9
    assert await coordinator.refresh_state(RefreshRequest(refresh_all=True, query_segments=True))
    main = GoveeBLELight(coordinator)
    side = GoveeBLESourceLight(coordinator, "side")
    for light in (main, side):
        light._attr_device_info = None
        light.async_added_to_hass = AsyncMock()
    assert await async_setup_component(hass, "light", {})
    await hass.data["light"].async_add_entities([main, side])

    async def control(light, **kwargs):
        await hass.services.async_call("light", "turn_on", {"entity_id": light.entity_id, **kwargs}, blocking=True)

    await control(side, **({"color_temp_kelvin": 6500} if layout == "white" else {"rgb_color": [0, 255, 0]}))
    if layout == "mixed":
        await coordinator.async_paint_segments(
            [([1, 2], (255, 0, 0)), ([3, 4], (0, 255, 0)), ([5, 6], (0, 0, 255)), ([7, 8], (128, 0, 128))]
        )
    if layout == "external":
        from custom_components.ha_govee_led_ble.coordinator_notifications import EXPECTED_STATE_TTL

        assert await coordinator.refresh_state(RefreshRequest(refresh_all=True, query_segments=True))
        virtual_clock.vtime += EXPECTED_STATE_TTL + 1
        physical["colours"][:8] = [(36, 72, 108)] * 8
    expected_colours, expected_levels = list(physical["colours"]), list(physical["levels"])
    native_keys = ("flags", "top", "bottom", "bottom_brightness", "ripple", "master")
    expected_native = tuple(physical[key] for key in native_keys)
    await control(main, effect="Rainbow")
    assert physical["scene"] is not None
    assert physical["colours"] != expected_colours
    for _ in range(2):
        await control(main, effect="off")
        assert physical["scene"] is None
        assert physical["colours"] == expected_colours
        assert physical["levels"] == expected_levels
        assert tuple(physical[key] for key in native_keys) == expected_native


async def test_effect_readiness_precedes_combined_power_and_brightness(hass, source_wire, virtual_clock):
    coordinator, physical = source_wire
    physical.update(apply=True, flags=0x60, drop_source_readback=True)
    coordinator.is_on = False
    light = GoveeBLELight(coordinator)
    light.async_write_ha_state = MagicMock()
    with pytest.raises(HomeAssistantError):
        await light.async_turn_on(effect="Rainbow", brightness=200)
    assert not any(call.args[1][0] == 0x33 for call in coordinator._client.write_gatt_char.await_args_list)
    assert physical["flags"] == 0x60


async def test_effect_off_cannot_replay_baseline_invalidated_while_waiting(
    hass, source_wire, monkeypatch, virtual_clock
):
    coordinator, physical = source_wire
    physical["apply"] = True
    main = GoveeBLELight(coordinator)
    side = GoveeBLESourceLight(coordinator, "side")
    for light in (main, side):
        light._attr_device_info = None
        light.async_added_to_hass = AsyncMock()
    assert await async_setup_component(hass, "light", {})
    await hass.data["light"].async_add_entities([main, side])

    async def control(light, **kwargs):
        await hass.services.async_call("light", "turn_on", {"entity_id": light.entity_id, **kwargs}, blocking=True)

    await control(main, effect="Rainbow")
    source_entered, release_source, off_ready = asyncio.Event(), asyncio.Event(), asyncio.Event()
    resolve_effect = main._prepare_effect

    async def source_control():
        async with coordinator._control_arbiter.hold(ControlIntent.USER):
            source_entered.set()
            await release_source.wait()
            await coordinator.async_turn_on_source("side", SourceTurnOnRequest(rgb_color=(36, 72, 108)))

    async def note_off_ready(*args, **kwargs):
        effect = await resolve_effect(*args, **kwargs)
        off_ready.set()
        return effect

    monkeypatch.setattr(main, "_prepare_effect", note_off_ready)
    source = hass.async_create_task(source_control())
    off = None
    try:
        await asyncio.wait_for(source_entered.wait(), 2)
        off = hass.async_create_task(control(main, effect="off", brightness=200))
        await asyncio.wait_for(off_ready.wait(), 2)
        release_source.set()
        await source
        with pytest.raises(HomeAssistantError) as error:
            await off
        assert error.value.translation_key == "recovery_not_ready"
        assert physical["colours"][:8] == [(36, 72, 108)] * 8
        assert physical["master"] == 50
    finally:
        release_source.set()
        await asyncio.gather(source, *([off] if off is not None else []), return_exceptions=True)


async def test_lost_effect_baseline_requires_complete_static_controls(source_wire, virtual_clock):
    coordinator, physical = source_wire
    physical["apply"] = True
    light = GoveeBLELight(coordinator)
    light.async_write_ha_state = MagicMock()
    await light.async_turn_on(effect="Rainbow")
    coordinator._pre_mode_snapshot = None
    coordinator._client.write_gatt_char.reset_mock()
    with pytest.raises(HomeAssistantError) as error:
        await light.async_turn_on(effect="Rainbow", brightness=200)
    assert error.value.translation_key == "recovery_not_ready"
    assert not any(call.args[1][0] == 0x33 for call in coordinator._client.write_gatt_char.await_args_list)
    assert physical["scene"] is not None
    await light.async_turn_on(rgb_color=(36, 72, 108), brightness=120)
    expected = list(physical["colours"])
    expected_master = physical["master"]
    await light.async_turn_on(effect="Rainbow")
    await light.async_turn_on(effect="off")
    assert physical["colours"] == expected
    assert physical["master"] == expected_master


@pytest.mark.parametrize("ripple_supported", [False, True])
async def test_native_source_recovery_uses_fresh_values_without_ripple_dependency(
    source_wire, virtual_clock, ripple_supported
):
    coordinator, physical = source_wire
    coordinator.profile = replace(PROFILE, supports_ripple_speed=ripple_supported)
    coordinator._authorization_profile.return_value = coordinator.profile
    physical["apply"] = True
    light = GoveeBLELight(coordinator)
    light.async_write_ha_state = MagicMock()
    expected = physical["bottom"], physical["bottom_brightness"]
    await light.async_turn_on(effect="Rainbow")
    physical.update(bottom=6500, bottom_brightness=5)
    await light.async_turn_on(effect="off")
    assert (physical["bottom"], physical["bottom_brightness"]) == expected


async def test_live_reuses_observed_original_layout_without_cancel_undo(hass, monkeypatch, source_wire, virtual_clock):
    from custom_components.ha_govee_led_ble.effect_preview import PreviewPhase
    from tests.test_effect_preview import _manager, _open

    coordinator, physical = source_wire
    physical.update(
        apply=True,
        colours=[(255, 0, 0), (0, 255, 0), (0, 0, 255), (128, 0, 128)] * 2 + [table_kelvin_rgb(2700)],
    )
    coordinator.segment_kelvin = [None] * 9
    expected_colours, expected_levels = list(physical["colours"]), list(physical["levels"])
    expected_native = tuple(
        physical[key] for key in ("flags", "top", "bottom", "bottom_brightness", "ripple", "master")
    )
    manager, _cache = await _manager(hass, monkeypatch, coordinator, verify_timeout=2)
    owner, events = object(), []
    session = _open(manager, owner, events)

    async def apply(sequence, key):
        scene = MODEL_SCENES["H60B0"][key]
        await manager.async_queue_scene(
            session_id=session,
            owner=owner,
            config_entry_id="entry-a",
            sequence=sequence,
            updated_at="2026-11-16T00:00:00Z",
            scene_id=scene.scene_id,
            effect_id=scene.effect_id,
            speed_index=None,
        )
        await manager.async_wait_idle("entry-a")
        assert events[-1].phase is PreviewPhase.CONFIRMED

    try:
        await apply(1, "rainbow")
        baseline = coordinator._pre_mode_snapshot
        assert baseline is not None and baseline.static_colour_observed
        assert physical["colours"] != expected_colours
        coordinator._client.write_gatt_char.reset_mock()
        await apply(2, "moonlight")
        assert coordinator._pre_mode_snapshot is baseline
        assert not any(call.args[1][:2] == b"\xaa\xa5" for call in coordinator._client.write_gatt_char.await_args_list)
        coordinator._client.write_gatt_char.reset_mock()
        await manager.async_cancel(session_id=session, owner=owner, config_entry_id="entry-a")
        await manager.async_close_session(session, owner)
        coordinator._client.write_gatt_char.assert_not_awaited()
        assert coordinator._pre_mode_snapshot is baseline
        session = _open(manager, owner, events)
        await apply(1, "rainbow")
        assert coordinator._pre_mode_snapshot is baseline
        await manager.async_close_session(session, owner)
        light = GoveeBLELight(coordinator)
        light.async_write_ha_state = MagicMock()
        await light.async_turn_on(effect="off")
        assert physical["colours"] == expected_colours
        assert physical["levels"] == expected_levels
        assert (
            tuple(physical[key] for key in ("flags", "top", "bottom", "bottom_brightness", "ripple", "master"))
            == expected_native
        )
    finally:
        await manager.async_shutdown()


@pytest.mark.parametrize("reconnect_flags", [None, 0xB0])
async def test_source_retry_rejects_missing_or_changed_selection(source_wire, native_sources, reconnect_flags):
    coordinator, state = source_wire
    _, observe = native_sources
    client = coordinator._client
    state["flags"] = 0xA0
    observe(0xA0)

    async def connect():
        if coordinator._client is None:
            coordinator._client = client
            coordinator._notification_token = object()
            coordinator._notify_started_monotonic = time.monotonic()
            if reconnect_flags is not None:
                observe(reconnect_flags)
        return client

    coordinator._ensure_connected = AsyncMock(side_effect=connect)
    client.write_gatt_char.side_effect = BleakError("Physical write failed")
    with pytest.raises(ValueError, match="selection changed"):
        await coordinator.async_set_boolean_control("top_enabled", True)
    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == [frame("33300101")]
    assert coordinator.boolean_control_state == (
        {} if reconnect_flags is None else {"top_enabled": False, "side_enabled": True, "bottom_enabled": True}
    )


@pytest.mark.parametrize("operation", ["kelvin", "rgb"])
async def test_unconfirmed_source_write_reconciles_real_area_state(source_wire, virtual_clock, operation):
    coordinator, _state = source_wire
    if operation == "kelvin":
        request = coordinator.async_set_segment_kelvin(
            build_segment_color_temp([9], 5000, "H60B0", profile=PROFILE), requested_kelvin=5000
        )
    else:
        request = coordinator.async_paint_segments([(list(range(1, 9)), (255, 0, 0))])
    with pytest.raises((TimeoutError, RuntimeError)):
        await request
    top, side = GoveeBLESourceLight(coordinator, "top"), GoveeBLESourceLight(coordinator, "side")
    assert top.color_temp_kelvin == 2700
    assert side.color_mode is ColorMode.RGB
    assert side.rgb_color == (0, 0, 255)
    assert "source_kelvin_top" not in coordinator._expected_state
    assert "source_kelvin_side" not in coordinator._expected_state
    assert coordinator.segment_state_source == "observed"
    assert GoveeBLELight(coordinator).rgb_color is None
    assert GoveeBLELight(coordinator).brightness is not None


async def test_cancelled_source_kelvin_write_does_not_query_recovery(source_wire):
    coordinator, _state = source_wire
    client = coordinator._client
    write = client.write_gatt_char.side_effect
    packet = build_segment_color_temp([9], 5000, "H60B0", profile=PROFILE)

    async def cancel_kelvin(uuid, command, **kwargs):
        if command == packet:
            raise asyncio.CancelledError
        await write(uuid, command, **kwargs)

    client.write_gatt_char.side_effect = cancel_kelvin
    with pytest.raises(asyncio.CancelledError):
        await coordinator.async_set_segment_kelvin(packet, requested_kelvin=5000)
    assert client.write_gatt_char.await_args_list[-1].args[1] == packet
    assert not coordinator._control_arbiter.locked()
    assert not coordinator._lock.locked()


@pytest.mark.parametrize(
    ("native_setting", "white"),
    [(None, False), (("top", "ripple_speed", 60), False), (("bottom", "brightness", 50), False), (None, True)],
)
async def test_effect_stop_restores_mixed_source_capture_without_aggregate_colour(
    source_wire, virtual_clock, native_setting, white
):
    coordinator, state = source_wire
    state["apply"] = True
    if white:
        state.update(flags=0xB0, top=6500, bottom=6500, colours=[table_kelvin_rgb(6500)] * 9)
        coordinator.segment_kelvin = [None] * 9
    assert await coordinator.refresh_state(RefreshRequest(refresh_all=True, query_segments=True))
    if native_setting is not None:
        await coordinator.async_set_source_value(*native_setting)
        assert coordinator.segment_state_source == "observed"
    before = coordinator.capture_effect_control_state()
    assert before.top_kelvin == (6500 if white else 2700)
    assert before.segment_kelvin == ((None,) * 8 + (6500,) if white else (0,) * 8 + (2700,))
    assert before.static_segment_kelvin(PROFILE) is not None
    assert PriorControlState.from_dict(before.to_dict()) == before
    await coordinator.send_command(frame("3305040100"))
    assert coordinator._pre_mode_snapshot == before
    state["apply"] = True
    state["top"] = 0
    state["colours"] = [(255, 0, 0)] * 9
    coordinator.segment_kelvin = [None] * 9
    coordinator.color_mode = ParsedMode.SCENE
    await coordinator.async_restore_pre_mode()
    assert state["colours"] == ([table_kelvin_rgb(6500)] * 9 if white else [(0, 0, 255)] * 8 + [table_kelvin_rgb(2700)])
    assert coordinator.capture_effect_control_state().source_segment_kelvin(PROFILE) == before.source_segment_kelvin(
        PROFILE
    )
    assert coordinator._client.write_gatt_char.await_count > 0


async def test_music_captures_sources_at_its_physical_mode_transition(source_wire, virtual_clock):
    coordinator, state = source_wire
    state["apply"] = True
    assert await coordinator.refresh_state(RefreshRequest(refresh_all=True, query_segments=True))
    before = coordinator.capture_effect_control_state()

    write = coordinator._client.write_gatt_char.side_effect

    async def with_music_ack(*args, **kwargs):
        await write(*args, **kwargs)
        pending = coordinator._upload_ack
        if pending is not None and not pending.future.done():
            assert pending.mode is not None
            coordinator._notify_callback(
                None, bytearray(frame(f"{pending.protocol:02x}{pending.subtype:02x}{pending.mode:02x}00"))
            )

    coordinator._client.write_gatt_char.side_effect = with_music_ack
    await coordinator.async_select_music_slug("spectrum")
    assert coordinator._pre_mode_snapshot == before
    assert coordinator.color_mode is ParsedMode.MUSIC
    state["top"], state["colours"] = 0, [(255, 0, 0)] * 9
    await coordinator.async_restore_pre_mode()
    assert state["colours"] == [(0, 0, 255)] * 8 + [table_kelvin_rgb(2700)]


@pytest.mark.parametrize("route", ["native", "saved"])
@pytest.mark.parametrize("power_failure", [False, True])
async def test_entity_effect_owns_source_restoration_before_leading_power(
    hass, source_wire, virtual_clock, route, power_failure
):
    coordinator, state = source_wire
    state.update(apply=True, flags=0x60)
    assert await coordinator.refresh_state(RefreshRequest(refresh_all=True, query_segments=True))
    assert not coordinator.is_on
    before = coordinator.capture_effect_control_state()
    before_flags = state["flags"]
    original_snapshot = coordinator._pre_mode_snapshot
    backend = await EffectBackend.async_create(hass)
    light = GoveeBLELight(coordinator, config_entry_id="source-device", effect_backend=backend)
    light.async_write_ha_state = MagicMock()
    scene = MODEL_SCENES["H60B0"]["rainbow"]
    item = LibraryItem.new("Saved rainbow", BuiltinScene(CatalogueRef("H60B0", scene.scene_id, scene.effect_id)))
    await backend.library.async_create(item)
    light._library_snapshot = backend.application.library_snapshot()
    coordinator.async_observe_effect = AsyncMock(return_value=True)
    write = coordinator._client.write_gatt_char.side_effect

    async def transmit(uuid, packet, **kwargs):
        if power_failure and packet[:3] == bytes.fromhex("330101"):
            raise RuntimeError("power failed")
        await write(uuid, packet, **kwargs)

    coordinator._client.write_gatt_char.side_effect = transmit
    try:
        if power_failure:
            with pytest.raises(HomeAssistantError):
                await light.async_turn_on(effect="Rainbow" if route == "native" else item.name)
            assert coordinator._pre_mode_snapshot is original_snapshot
        else:
            await light.async_turn_on(effect="Rainbow" if route == "native" else item.name)
            assert coordinator._pre_mode_snapshot == before
            state["top"], state["colours"] = 0, [(255, 0, 0)] * 9
            coordinator.color_mode = ParsedMode.SCENE
            await coordinator.async_restore_pre_mode()
            assert state["colours"] == [(0, 0, 255)] * 8 + [table_kelvin_rgb(2700)]
            assert state["flags"] & 0x70 == before_flags & 0x70
        assert coordinator._mode_transition is None
    finally:
        await backend.preview.async_shutdown()


async def test_missing_switch_readback_requires_fresh_flags_before_next_enable(source_wire, virtual_clock):
    coordinator, state = source_wire
    client = coordinator._client
    state["apply"], state["flags"], state["drop_source_readback"] = True, 0xA0, True
    coordinator._notify_callback(None, bytearray(frame("aa42a00a8c320fa028")))
    with pytest.raises(ValueError, match="fresh setting readback"):
        await coordinator.async_set_boolean_control("top_enabled", True)
    assert coordinator._fresh_source_power() is None
    with pytest.raises(ValueError, match="complete source power"):
        await coordinator.async_set_boolean_control("bottom_enabled", True)
    source_writes = [call.args[1] for call in client.write_gatt_char.await_args_list if call.args[1][:2] == b"\x33\x30"]
    assert source_writes == [frame("33300101")]
    assert state["flags"] == 0xE0


async def test_reconnected_native_fields_cannot_qualify_cached_segment_layout(source_wire, virtual_clock):
    coordinator, state = source_wire
    assert await coordinator.refresh_state(RefreshRequest(refresh_all=True, query_segments=True))
    assert coordinator.capture_effect_control_state().static_segment_kelvin(PROFILE) is not None
    client = coordinator._client
    coordinator._clear_client_state(client)
    await asyncio.sleep(0.1)
    coordinator._client, coordinator._notification_token = client, object()
    coordinator._notify_started_monotonic = asyncio.get_running_loop().time()
    coordinator._notify_callback(None, bytearray(frame("aa052c0a8c320fa028")))
    coordinator._notify_callback(None, bytearray(frame("aa42e00a8c320fa028")))
    state["colours"] = [(255, 0, 0)] * 8 + [table_kelvin_rgb(2700)]
    captured = coordinator.capture_effect_control_state()
    assert captured.segment_colors is None
    assert captured.segment_kelvin is None
    assert await async_prepare_effect_control_state(coordinator, require_restorable_static=True)
    assert coordinator.capture_effect_control_state().segment_colors == tuple(state["colours"])
    assert coordinator.segment_colors[0] == (255, 0, 0)


async def test_source_on_from_master_off_preserves_remembered_siblings(source_wire, virtual_clock):
    coordinator, state = source_wire
    state["apply"], state["flags"] = True, 0x60
    coordinator._notify_callback(None, bytearray(frame("aa42600a8c320fa028")))
    await GoveeBLESourceLight(coordinator, "top").async_turn_on()
    assert coordinator.is_on
    assert coordinator.boolean_control_state == {"top_enabled": True, "side_enabled": True, "bottom_enabled": False}
    assert not any(
        call.args[1][:2] == bytes.fromhex("3330") and not call.args[1][3]
        for call in coordinator._client.write_gatt_char.await_args_list
    )


async def test_partial_source_paint_preserves_success_and_untouched_bottom(source_wire, virtual_clock):
    coordinator, state = source_wire
    state["apply"] = True
    write = coordinator._client.write_gatt_char.side_effect
    attempted_masks = []

    async def fail_side(uuid, packet, **kwargs):
        static = parse_static_write(packet, "H60B0", profile=PROFILE) if packet[0] == 0x33 else None
        if static is not None:
            attempted_masks.append(static.segment_mask)
            if static.segment_mask == 0xFF:
                raise RuntimeError("side write failed")
        await write(uuid, packet, **kwargs)

    coordinator._client.write_gatt_char.side_effect = fail_side
    with pytest.raises(RuntimeError, match="side write failed"):
        await coordinator.async_paint_segments([(list(range(1, 10)), (255, 0, 0))])
    assert attempted_masks == [0x100, 0xFF]
    assert GoveeBLESourceLight(coordinator, "top").rgb_color == (255, 0, 0)
    assert GoveeBLESourceLight(coordinator, "side").rgb_color == (0, 0, 255)
    assert coordinator.bottom_kelvin == 4000
    assert coordinator.boolean_control_state["bottom_enabled"] is False


@pytest.mark.parametrize(
    ("packet", "prefix"),
    [
        (build_brightness(50, profile=PROFILE), "330432"),
        (build_color_rgb(1, 2, 3, profile=PROFILE), "33050d0102030000000000"),
        (build_color_temp(4000, profile=PROFILE), "33050dffffff0fa0ffd5a1"),
        (build_segment_color([9], 1, 2, 3, profile=PROFILE), "33052c01010102030000"),
        (build_segment_color([1, 8], 1, 2, 3, profile=PROFILE), "33052c020101020300008100"),
        (build_segment_color_temp([9], 4000, profile=PROFILE), "33052c0101ffd5a10fa0"),
        (build_segment_brightness([9], 40, profile=PROFILE), "33052c010228"),
        (build_segment_brightness([1, 8], 40, profile=PROFILE), "33052c0202288100"),
        (build_source_value("bottom", "brightness", 40, PROFILE), "33052c030228"),
        (build_source_value("bottom", "kelvin", 4000, PROFILE), "33052c03010fa0"),
        (build_source_value("top", "ripple_speed", 30, PROFILE), "33052c01031e"),
        (build_boolean_control("side_enabled", True, "H60B0", profile=PROFILE), "33300201"),
        (build_power_on_behaviour("off", PROFILE), "33410202"),
        (build_boolean_control_query("top_enabled", "H60B0", profile=PROFILE), "aa42"),
        (build_colour_mode_query(profile=PROFILE), "aa05"),
        (build_hardware_query(profile=PROFILE), "aa0703"),
        (build_pact_query(PROFILE), "aaef"),
        (build_segment_query(3, profile=PROFILE), "aaa503"),
    ],
)
def test_source_and_ordinary_commands_match_exact_model_contract(packet, prefix):
    assert packet == frame(prefix)
    require_profile_packet(packet, PROFILE)


def test_mixed_source_writes_partition_without_touching_bottom_or_other_segments():
    colour = build_segment_paint([([1, 9], (1, 2, 3))], "H60B0", profile=PROFILE)
    brightness = build_segment_brightness_packets([1, 9], 40, "H60B0", profile=PROFILE)
    assert colour == [frame("33052c01010102030000"), frame("33052c020101020300000100")]
    assert brightness == [frame("33052c010228"), frame("33052c0202280100")]
    for packets in (colour, brightness):
        assert [parse_static_write(packet, profile=PROFILE).segment_mask for packet in packets] == [256, 1]
        for packet in packets:
            require_profile_packet(packet, PROFILE)


def test_combined_music_ack_tracks_the_outer_mode_and_preserves_envelope_fill():
    packets = prepare_music_request("H60B0", "combined", 50, None, False, {}, profile=PROFILE)
    index = len(packets) - 2
    assert upload_ack_subtype(packets, index, "H60B0", profile=PROFILE) == 0x41
    assert upload_ack_mode(packets, index, "H60B0", profile=PROFILE) == 130
    envelope = reassemble_a3(tuple(packet for packet in packets if packet[0] == 0xA3))
    assert serialize_native_body(parse_a3_effect_envelope(envelope, "H60B0", profile=PROFILE)) == envelope
    for prefix, expected in (("a3418200", True), ("a3418201", False), ("a3413000", None)):
        parsed = parse_command_ack_result(frame(prefix), "H60B0", profile=PROFILE).parsed
        assert parsed is not None
        assert upload_ack_success(parsed, 0x41, 130, protocol=0xA3) is expected


@pytest.mark.parametrize("pact", [(1, 1), (1, 2), (1, 3)])
def test_revision_qualification_does_not_infer_firmware_thresholds(pact):
    profile = device_profile("H60B0", *pact, firmware="1.00.12", hardware="3.05.01")
    assert profile.native_effect_revision == pact[1]
    assert profile.supports_rgb and profile.supports_scenes and profile.supports_ripple_speed
    unknown = device_profile("H60B0", None, None, firmware="1.00.12", hardware="3.05.01")
    with pytest.raises(ValueError):
        require_profile_packet(build_source_value("bottom", "kelvin", 4000, profile), unknown)
    with pytest.raises(ValueError):
        require_profile_packet(build_segment_color([9], 1, 2, 3, profile=profile), unknown)


@pytest.mark.parametrize(
    "prefix",
    [
        "33300401",
        "33300102",
        "33052c0202010001",
        "33052c010365",
        "33052c030265",
        "33052c03010fa1",
        "33052c050101020300000100",
    ],
)
def test_unqualified_sources_masks_and_levels_are_rejected(prefix):
    with pytest.raises(ValueError):
        require_profile_packet(frame(prefix), PROFILE)


@pytest.mark.parametrize(("top_kelvin", "bottom_kelvin"), [(3000, 4000), (3123, 1999)])
async def test_source_readback_is_independent_and_invalid_state_cannot_update_flags(
    hass, monkeypatch, top_kelvin, bottom_kelvin
):
    from custom_components.ha_govee_led_ble import coordinator_notifications, h60b0_controls

    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H60B0", configuration_url=None)
    coordinator.profile = PROFILE
    decode = MagicMock(wraps=h60b0_controls.source_readback)
    monkeypatch.setattr(h60b0_controls, "source_readback", decode)
    monkeypatch.setattr(coordinator_notifications, "source_readback", decode)
    coordinator._notify_callback(None, bytearray(frame(f"aa42d0{top_kelvin:04x}1e{bottom_kelvin:04x}28")))
    decode.assert_called_once()
    assert coordinator.boolean_control_state == {"top_enabled": True, "side_enabled": False, "bottom_enabled": True}
    assert (coordinator.top_kelvin, coordinator.bottom_kelvin) == (top_kelvin, bottom_kelvin)
    assert (coordinator.bottom_brightness, coordinator.ripple_speed) == (40, 30)
    coordinator._notify_callback(None, bytearray(frame("aa42200bb81e0fa065")))
    assert coordinator.boolean_control_state["top_enabled"] is True
    assert coordinator.bottom_brightness == 40
    bottom = GoveeBLESourceLight(coordinator, "bottom")
    assert bottom.supported_color_modes == {ColorMode.COLOR_TEMP}
    assert bottom.color_temp_kelvin == bottom_kelvin and bottom.brightness == 102
    assert bottom.rgb_color is None


@pytest.mark.parametrize("pact_code", [1, 2, 3])
@pytest.mark.parametrize("prefix", ["aa42b0", "aa052c"])
async def test_reported_source_state_keeps_bottom_values_separate_from_ripple(hass, pact_code, prefix):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H60B0", configuration_url=None)
    coordinator.profile = device_profile("H60B0", 1, pact_code)
    coordinator._notify_callback(None, bytearray(frame(prefix + "000032196464")))
    assert (coordinator.top_kelvin, coordinator.ripple_speed) == (0, 50)
    assert (coordinator.bottom_kelvin, coordinator.bottom_brightness) == (6500, 100)
    bottom = GoveeBLESourceLight(coordinator, "bottom")
    assert bottom.color_temp_kelvin == 6500
    assert bottom.brightness == 255


async def test_bottom_source_uses_native_attributes_without_segment_writes(mock_coordinator):
    coordinator = mock_coordinator
    coordinator.model, coordinator.profile = "H60B0", PROFILE
    coordinator.is_on = True
    coordinator.boolean_control_state = {"top_enabled": True, "side_enabled": False, "bottom_enabled": True}
    coordinator._async_supersede_effect_preview = AsyncMock()
    coordinator.async_prepare_identity_gated_control = AsyncMock(return_value=lambda: None)
    coordinator.refresh_state = AsyncMock(return_value=True)
    coordinator.async_set_boolean_control = AsyncMock()
    coordinator.async_set_source_value = AsyncMock()
    coordinator.async_set_segment_brightness = AsyncMock()
    coordinator.async_set_segment_kelvin = AsyncMock()
    coordinator._notify_started_monotonic = 1.0
    coordinator._field_revisions["is_on"] = 1
    coordinator._field_received_at.update({"is_on": 2.0, "boolean_bottom_enabled": 2.0})
    coordinator._observed_power_write_generation = coordinator._power_write_generation
    coordinator._observed_power_profile_generation = coordinator._profile_generation
    coordinator._source_power_observation_generation["boolean_bottom_enabled"] = (
        coordinator._power_write_generation,
        coordinator._profile_generation,
    )
    coordinator.async_mask_transaction = MagicMock(
        side_effect=AssertionError("Native source controls do not address segments")
    )
    source = GoveeBLESourceLight(coordinator, "bottom")
    await source.async_turn_on(brightness=102, color_temp_kelvin=4000)
    assert coordinator.async_set_source_value.await_args_list[0].args == ("bottom", "brightness", 40)
    assert coordinator.async_apply_source_value.await_args.args[0].packet == frame("33052c03010fa0")
    coordinator.async_set_segment_brightness.assert_not_awaited()
    coordinator.async_set_segment_kelvin.assert_not_awaited()
    coordinator.async_set_boolean_control.assert_not_awaited()


@pytest.mark.parametrize(
    ("source", "attribute", "value", "prefix", "matching_body", "mismatched_body"),
    [
        ("bottom", "brightness", 100, "33052c030264", "000032196464", "000032196432"),
        ("bottom", "kelvin", 6500, "33052c03011964", "000032196464", "0000320fa064"),
        ("top", "ripple_speed", 30, "33052c01031e", "00001e196464", "000032196464"),
    ],
)
@pytest.mark.parametrize("matching", [True, False])
async def test_native_source_setting_requires_fresh_matching_readback(
    hass, source, attribute, value, prefix, matching_body, mismatched_body, matching
):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H60B0", configuration_url=None)
    coordinator.profile = PROFILE
    coordinator.pact_type, coordinator.pact_code = 1, 2
    client = MagicMock(is_connected=True)
    coordinator._client = client
    coordinator._notification_token = object()
    coordinator._ensure_connected = AsyncMock(return_value=client)
    coordinator._async_supersede_effect_preview = AsyncMock()
    body = matching_body if matching else mismatched_body

    async def write(_client, packet, **kwargs):
        if guard := kwargs.get("before_write"):
            guard()
        if callback := kwargs.get("on_write"):
            callback()
        if packet == frame("aa42"):
            coordinator._notify_callback(None, bytearray(frame("aa42f0" + body)))
        if packet == frame("aa05"):
            coordinator._notify_callback(None, bytearray(frame("aa052c" + body)))

    coordinator._async_write_packet = AsyncMock(side_effect=write)
    if matching:
        await coordinator.async_set_source_value(source, attribute, value)
        field = "ripple_speed" if attribute == "ripple_speed" else f"{source}_{attribute}"
        assert getattr(coordinator, field) == value
    else:
        with pytest.raises(ValueError, match="did not confirm"):
            await coordinator.async_set_source_value(source, attribute, value)
    assert [call.args[1] for call in coordinator._async_write_packet.await_args_list] == [
        frame(prefix),
        frame("aa42"),
        *([frame("aa05")] if matching else []),
    ]


async def test_preview_requires_complete_source_values_and_preserves_them_in_storage(source_wire, virtual_clock):
    coordinator, physical = source_wire
    physical["bottom"] = 0
    with pytest.raises(RuntimeError, match="original static"):
        await async_prepare_effect_control_state(coordinator, require_restorable_static=True)
    assert not any(call.args[1][0] == 0x33 for call in coordinator._client.write_gatt_char.await_args_list)
    physical.update(bottom=4000, ripple=30)
    assert await async_prepare_effect_control_state(coordinator, require_restorable_static=True)
    complete = coordinator.capture_effect_control_state()
    assert (complete.top_kelvin, complete.bottom_kelvin, complete.bottom_brightness, complete.ripple_speed) == (
        2700,
        4000,
        40,
        30,
    )
    assert complete.static_colour_observed
    assert PriorControlState.from_dict(complete.to_dict()) == complete


@pytest.mark.parametrize(
    ("cold", "drop_readback", "error"),
    [(False, False, None), (True, False, None), (False, True, "state_unavailable")],
)
async def test_live_acquires_source_state_without_guessing_missing_intent(
    hass, monkeypatch, source_wire, virtual_clock, cold, drop_readback, error
):
    from custom_components.ha_govee_led_ble.effect_preview import PreviewPhase, PreviewWriteDisposition
    from tests.test_effect_preview import _manager, _open

    coordinator, state = source_wire
    state["drop_source_readback"] = drop_readback
    if cold:
        coordinator.segment_kelvin = [None] * 9
    coordinator._field_received_at.clear()
    manager, _cache = await _manager(hass, monkeypatch, coordinator)

    async def begin_transmission(_request, _coordinator, _compiled, writer):
        await writer.begin()

    transmit = AsyncMock(side_effect=begin_transmission)
    monkeypatch.setattr(manager, "_async_transmit_request", transmit)
    template = next(
        template
        for template in MODEL_EFFECT_CATALOGUES["H60B0"].templates
        if template.id == "template:h60b0:1:single:1"
    )
    events = []
    owner = object()
    session = _open(manager, owner, events)
    try:
        await manager.async_queue_snapshot(
            session_id=session,
            owner=owner,
            config_entry_id="entry-a",
            sequence=1,
            updated_at="2026-11-14T00:00:00Z",
            item=LibraryItem.new("Source preview", template.content),
        )
        await manager.async_wait_idle("entry-a")
        if error is None:
            transmit.assert_awaited_once()
            assert events[-1].write_disposition is PreviewWriteDisposition.COMPLETED
            assert coordinator.capture_effect_control_state().static_segment_kelvin(PROFILE) is not None
        else:
            transmit.assert_not_awaited()
            assert events[-1].phase is PreviewPhase.FAILED
            assert events[-1].error_code == error
            assert events[-1].write_disposition is PreviewWriteDisposition.NOT_STARTED
            assert "could not be reached" not in events[-1].error_message
        assert not any(call.args[1][0] == 0x33 for call in coordinator._client.write_gatt_char.await_args_list)
    finally:
        await manager.async_shutdown()


async def test_reconnect_revokes_cached_pact_and_qualifies_the_current_marker(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H60B0", configuration_url=None)
    coordinator.pact_type, coordinator.pact_code = 1, 2
    coordinator.profile = PROFILE
    old_client = MagicMock(is_connected=True)
    coordinator._client = old_client
    coordinator._confirmed_identity_fields.add("pact")
    coordinator._h607c_marker_pact = (1, 2)
    coordinator._h607c_advertisement_observations = {"cached": (time.monotonic() - 10, frozenset({(1, 2)}))}
    template = next(
        template
        for template in MODEL_EFFECT_CATALOGUES["H60B0"].templates
        if template.id == "template:h60b0:1:single:1"
    )
    compiled = compile_effect(LibraryItem.new("Older native effect", template.content), "H60B0", profile=PROFILE)
    source_packet = build_source_value("bottom", "brightness", 40, PROFILE)
    coordinator._clear_client_state(old_client)
    assert coordinator.profile.native_effect_revision == 2
    assert not coordinator.identity_fields_confirmed()
    assert coordinator.h607c_pact_readiness == "stale"
    with pytest.raises(HomeAssistantError) as error:
        coordinator._validate_authorized_packet(source_packet)
    assert error.value.translation_key == "identity_not_ready"
    with pytest.raises(HomeAssistantError) as error:
        coordinator._validate_authorized_packet(compiled.upload_packets[0])
    assert error.value.translation_key == "identity_not_ready"

    client = MagicMock(is_connected=True, start_notify=AsyncMock(), write_gatt_char=AsyncMock(), disconnect=AsyncMock())
    coordinator._encryption = MagicMock(
        ready=True, version=0, marker_pact=(1, 3), async_select=AsyncMock(), async_negotiate=AsyncMock()
    )
    monkeypatch.setattr(
        "custom_components.ha_govee_led_ble.coordinator.async_establish_ble_connection", AsyncMock(return_value=client)
    )
    monkeypatch.setattr(coordinator, "_send_identity_queries", AsyncMock())
    monkeypatch.setattr(coordinator, "_start_keep_alive", MagicMock())
    try:
        await coordinator._ensure_connected()
        assert coordinator.profile.native_effect_revision == 3
        assert coordinator.identity_fields_confirmed()
        assert coordinator.h607c_pact_readiness == "ready"
        coordinator._validate_authorized_packet(source_packet)
        with pytest.raises(ValueError, match="revision"):
            validate_compiled_geometry(compiled, coordinator.profile)
        coordinator._clear_client_state(client)
        assert not coordinator.identity_fields_confirmed()
        with pytest.raises(HomeAssistantError) as error:
            coordinator._validate_authorized_packet(source_packet)
        assert error.value.translation_key == "identity_not_ready"
        assert coordinator.profile.native_effect_revision == 3
    finally:
        await coordinator.disconnect()


async def test_only_current_subscription_advertisements_can_confirm_pact(hass):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H60B0", configuration_url=None)
    coordinator._client = MagicMock(is_connected=True)
    coordinator._notify_started_monotonic = time.monotonic()
    coordinator._h607c_advertisement_observations = {
        "proxy": (coordinator._notify_started_monotonic - 1, frozenset({(1, 2)}))
    }
    coordinator._resolve_h607c_pact()
    assert not coordinator.identity_fields_confirmed()
    coordinator._h607c_advertisement_observations["proxy"] = (
        coordinator._notify_started_monotonic + 1,
        frozenset({(1, 2)}),
    )
    coordinator._resolve_h607c_pact()
    assert coordinator.identity_fields_confirmed()
    coordinator._h607c_marker_pact = (1, 3)
    coordinator._resolve_h607c_pact()
    assert not coordinator.identity_fields_confirmed()
    assert not coordinator._authorization_profile().supports_custom_effects


async def test_pact_is_rechecked_after_reply_pacing_before_the_physical_write(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H60B0", configuration_url=None)
    coordinator.profile = PROFILE
    coordinator.pact_type, coordinator.pact_code = 1, 2
    coordinator._client = client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    coordinator._confirmed_identity_fields.add("pact")
    packet = build_source_value("bottom", "brightness", 40, PROFILE)

    async def lose_confirmation():
        coordinator._confirmed_identity_fields.discard("pact")

    monkeypatch.setattr(coordinator._reply_gate, "wait", lose_confirmation)
    with pytest.raises(HomeAssistantError) as error:
        await coordinator._async_write_packet(client, packet, arm_expected=True)
    assert error.value.translation_key == "identity_not_ready"
    client.write_gatt_char.assert_not_awaited()


@pytest.fixture
def pact_connection(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H60B0", configuration_url=None)
    coordinator.pact_type, coordinator.pact_code = 1, 2
    coordinator.profile = PROFILE
    coordinator._h607c_advertisement_observations = {"cached": (time.monotonic() - 10, frozenset({(1, 2)}))}
    client = MagicMock(is_connected=True, start_notify=AsyncMock(), write_gatt_char=AsyncMock(), disconnect=AsyncMock())
    coordinator._encryption = MagicMock(
        ready=True,
        version=0,
        marker_pact=None,
        async_select=AsyncMock(),
        async_negotiate=AsyncMock(),
        encode=lambda packet: packet,
        decode=lambda packet: packet,
    )
    monkeypatch.setattr(
        "custom_components.ha_govee_led_ble.coordinator.async_establish_ble_connection", AsyncMock(return_value=client)
    )
    monkeypatch.setattr(coordinator, "_send_identity_queries", AsyncMock())
    monkeypatch.setattr(coordinator, "_start_keep_alive", MagicMock())
    return coordinator, client


@pytest.mark.parametrize(("revision", "cached"), [(1, True), (2, True), (3, True), (9, True), (2, False)])
async def test_live_pact_read_qualifies_without_marker_or_connected_advertisements(pact_connection, revision, cached):
    coordinator, client = pact_connection
    if not cached:
        coordinator.pact_type = coordinator.pact_code = None
        coordinator.profile = device_profile("H60B0", None, None)
        coordinator._h607c_advertisement_observations.clear()
    initial_profile = coordinator.profile
    source = GoveeBLESourceLight(coordinator, "top")
    packet = build_source_value("bottom", "brightness", 40, PROFILE)

    async def write(_uuid, query, **kwargs):
        assert query == frame("aaef")
        assert source.available
        assert source.is_on is None
        assert coordinator.profile == initial_profile
        assert not coordinator.identity_fields_confirmed()
        with pytest.raises(HomeAssistantError if cached else ValueError):
            coordinator._require_writable_packet(
                packet,
                require_profile_packet,
                arm_expected=True,
                static=parse_static_write(packet, coordinator.model, profile=coordinator.profile),
            )
        receive = client.start_notify.await_args.args[1]
        receive(None, bytearray(frame(f"aaef0001{revision:02x}" + "55" * 14)))

    client.write_gatt_char.side_effect = write
    try:
        assert await coordinator._ensure_connected() is client
        client.write_gatt_char.assert_awaited_once()
        assert coordinator.identity_fields_confirmed()
        assert coordinator._authorization_profile().supports_rgb is (revision != 9)
        if revision != 9:
            assert source.available
            assert coordinator.profile.native_effect_revision == revision
            coordinator._validate_authorized_packet(packet)
        else:
            assert not source.available
            assert coordinator._pact_query_result == "unsupported"
            with pytest.raises(ValueError):
                await coordinator._async_write_packet(client, packet, arm_expected=True)
            client.write_gatt_char.assert_awaited_once()
    finally:
        await coordinator.disconnect()


async def test_pact_timeout_preserves_presentation_but_not_write_authority(pact_connection, virtual_clock):
    coordinator, client = pact_connection
    source = GoveeBLESourceLight(coordinator, "top")
    packet = build_source_value("bottom", "brightness", 40, PROFILE)
    try:
        assert await coordinator._ensure_connected() is client
        assert coordinator._pact_query_result == "timeout"
        assert coordinator.profile == PROFILE and source.available
        assert not coordinator.identity_fields_confirmed()
        assert not coordinator._authorization_profile().supports_rgb
        coordinator._validate_authorized_packet(build_brightness(50, profile=PROFILE))
        with pytest.raises(HomeAssistantError) as error:
            coordinator._validate_authorized_packet(packet)
        assert error.value.translation_key == "identity_not_ready"
        receive = client.start_notify.await_args.args[1]
        malformed = bytearray(frame("aaef000102"))
        malformed[-1] ^= 1
        receive(None, malformed)
        assert not coordinator.identity_fields_confirmed()
        receive(None, bytearray(frame("aaef000102")))
        assert coordinator.identity_fields_confirmed()
        coordinator._clear_client_state(client)
        assert not coordinator.identity_fields_confirmed()
        receive(None, bytearray(frame("aaef000103")))
        assert not coordinator._connection_pacts
        client.write_gatt_char.side_effect = lambda *args, **kwargs: receive(None, bytearray(frame("aaef000103")))
        assert await coordinator._ensure_connected() is client
        assert not coordinator.identity_fields_confirmed()
        assert coordinator._pact_query_result == "timeout"
        assert coordinator.profile == PROFILE
    finally:
        await coordinator.disconnect()


@pytest.mark.parametrize("conflict", ["query", "marker", "advertisement"])
async def test_live_pact_conflicts_revoke_write_authority(pact_connection, conflict):
    coordinator, client = pact_connection
    client.write_gatt_char.side_effect = lambda *args, **kwargs: client.start_notify.await_args.args[1](
        None, bytearray(frame("aaef000102"))
    )
    try:
        await coordinator._ensure_connected()
        assert coordinator.identity_fields_confirmed()
        if conflict == "query":
            client.start_notify.await_args.args[1](None, bytearray(frame("aaef000103")))
        elif conflict == "marker":
            coordinator._h607c_marker_pact = (1, 3)
            coordinator._resolve_h607c_pact()
        else:
            coordinator._h607c_advertisement_observations["current"] = (time.monotonic(), frozenset({(1, 3)}))
            coordinator._resolve_h607c_pact()
        assert coordinator.h607c_pact_readiness == "conflicting"
        assert not coordinator.identity_fields_confirmed()
        assert not coordinator._authorization_profile().supports_rgb
        with pytest.raises(ValueError):
            await coordinator._async_write_packet(
                client, build_source_value("bottom", "brightness", 40, PROFILE), arm_expected=True
            )
        client.write_gatt_char.assert_awaited_once()
    finally:
        await coordinator.disconnect()


@pytest.mark.parametrize(
    ("flags", "expected"),
    [(0x30, (False, False, True, True)), (0xB0, (True, False, True, True)), (0xA0, (True, False, True, False))],
)
async def test_reported_source_notifications_update_only_power_fields(hass, flags, expected):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H60B0", configuration_url=None)
    coordinator.profile = PROFILE
    coordinator._notify_callback(None, bytearray(frame("aa42d00bb81e0fa028")))
    native_revisions = {field: coordinator._field_revisions[field] for field in ("bottom_kelvin", "ripple_speed")}
    notification = frame(f"ee3001{flags:02x}" + "ab" * 15)
    coordinator._notify_callback(None, bytearray(notification))
    controls = ("top_enabled", "side_enabled", "bottom_enabled")
    assert (coordinator.is_on, *(coordinator.boolean_control_state[name] for name in controls)) == expected
    assert (coordinator.bottom_kelvin, coordinator.bottom_brightness, coordinator.ripple_speed) == (4000, 40, 30)
    assert {field: coordinator._field_revisions[field] for field in native_revisions} == native_revisions
    assert not coordinator.identity_fields_confirmed()
    assert ReadDomain.PACT not in coordinator._domain_revisions
    broken = bytearray(notification)
    broken[3] ^= 0xF0
    coordinator._notify_callback(None, broken)
    assert (coordinator.is_on, *(coordinator.boolean_control_state[name] for name in controls)) == expected
    coordinator._expected_state["boolean_top_enabled"] = (True, time.monotonic() + 10)
    coordinator.boolean_control_state["top_enabled"] = True
    previous = coordinator._field_revisions["boolean_top_enabled"]
    coordinator._notify_callback(None, bytearray(notification))
    assert coordinator.boolean_control_state["top_enabled"] is True
    assert coordinator._field_revisions["boolean_top_enabled"] == previous
