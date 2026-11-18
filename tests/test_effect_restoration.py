"""Fresh physical-state recovery through the real coordinator and deployment path."""

import asyncio
import time
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component

from custom_components.ha_govee_led_ble.const import device_profile, get_profile
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_modes import ModeTransitionSupersededError
from custom_components.ha_govee_led_ble.coordinator_refresh import RefreshRequest
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode
from custom_components.ha_govee_led_ble.effect_deployments import (
    DeploymentPhase,
    EffectDeploymentRepository,
    PriorControlState,
)
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem, SingleEffect
from custom_components.ha_govee_led_ble.effect_runtime import (
    EffectDeploymentEngine,
    EffectRestorationError,
    EffectStateReadError,
    async_prepare_effect_control_state,
)
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_brightness,
    build_colour_mode_query,
    build_diy_activation,
    build_power,
    build_scene_activation,
    require_profile_packet,
)
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.light_commands import parse_static_write
from custom_components.ha_govee_led_ble.music_commands import edit_music_body
from custom_components.ha_govee_led_ble.music_semantics import music_variant
from custom_components.ha_govee_led_ble.transport import fragment_a3, xor_checksum
from tests.coordinator_test_support import frame
from tests.storage_test_double import InMemoryVersionedDocumentStore


def reply(domain, body):
    payload = bytes([0xAA, domain, *body]).ljust(19, b"\0")
    return bytearray(payload + bytes([xor_checksum(payload)]))


def report_scene(coordinator, virtual_clock, code):
    for field in ("color_mode", "effect", "scene_code", "unknown_scene_code"):
        if field in coordinator._expected_state:
            virtual_clock.vtime = max(virtual_clock.vtime, coordinator._expected_state[field][1])
    coordinator._notify_callback(None, reply(5, [4, *code.to_bytes(2, "little")]))
    assert coordinator.scene_code == code


@pytest.mark.parametrize("powered", [False, True])
async def test_inline_diy_selector_alone_cannot_authorise_preview_or_restoration(hass, powered):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6127", configuration_url=None)
    coordinator.profile = replace(
        device_profile("H6127", 1, 1, firmware="1.01.16", hardware="1.00.01"),
        profile_identity_fields=frozenset(),
    )
    coordinator._client = MagicMock(is_connected=True)
    coordinator._notify_started_monotonic = time.monotonic()
    coordinator._notify_callback(None, reply(1, [int(powered)]))
    coordinator._notify_callback(None, reply(4, [128]))
    coordinator._notify_callback(None, reply(5, [7, 25]))
    coordinator.send_command = AsyncMock()
    state = coordinator.capture_effect_control_state()
    assert not await coordinator.async_restore_effect_control_state(state, overwritten_diy_code=24)
    with pytest.raises(EffectRestorationError, match="inline DIY body"):
        await async_prepare_effect_control_state(coordinator, require_restorable_static=True)
    with pytest.raises(ValueError, match="complete body"):
        build_diy_activation(25, "H6127", profile=coordinator.profile)
    with pytest.raises(ValueError, match="resident selector"):
        require_profile_packet(build_diy_activation(25, "H617A"), coordinator.profile)
    coordinator.send_command.assert_not_awaited()


@pytest.mark.parametrize("retained_mode", [None, ParsedMode.COLOUR])
@pytest.mark.parametrize("observation", ["inline", "missing", "unknown", "static"])
async def test_preview_qualifies_mode_before_deciding_inline_restoration_is_available(hass, retained_mode, observation):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6127", configuration_url=None)
    coordinator.profile = replace(
        device_profile("H6127", 1, 1, firmware="1.01.16", hardware="1.00.01"),
        profile_identity_fields=frozenset(),
    )
    coordinator._client = MagicMock(is_connected=True)
    coordinator._notify_started_monotonic = time.monotonic()
    coordinator._field_received_at["color_mode"] = coordinator._notify_started_monotonic - 30
    coordinator.color_mode = retained_mode
    coordinator.send_command = AsyncMock()

    async def refresh(_request):
        if observation != "missing":
            coordinator._notify_callback(None, reply(1, [1]))
            coordinator._notify_callback(None, reply(4, [128]))
            body = [7, 25] if observation == "inline" else [2, 255, 0, 0, 0] if observation == "static" else [0x7F]
            coordinator._notify_callback(None, reply(5, body))
        return True

    coordinator.refresh_state = AsyncMock(side_effect=refresh)
    if observation == "static":
        assert await async_prepare_effect_control_state(coordinator, require_restorable_static=True)
    else:
        error = EffectStateReadError if observation == "missing" else EffectRestorationError
        with pytest.raises(error):
            await async_prepare_effect_control_state(coordinator, require_restorable_static=True)
    coordinator.refresh_state.assert_awaited_once()
    coordinator.send_command.assert_not_awaited()


async def test_fixed_only_music_cannot_promote_a_retained_colour_into_a_recovery_observation(hass):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6127", configuration_url=None)
    coordinator.profile = replace(
        device_profile("H6127", 1, 1, firmware="1.01.20", hardware="1.00.01"),
        profile_identity_fields=frozenset(),
    )
    coordinator._client = MagicMock(is_connected=True)
    coordinator._notify_started_monotonic = time.monotonic()
    coordinator.music_color = (255, 0, 0)
    coordinator.send_command = AsyncMock()
    coordinator._notify_callback(None, reply(1, [1]))
    coordinator._notify_callback(None, reply(5, [1, 1, 50, 0, 0, 255]))
    prior = coordinator.capture_effect_control_state()
    assert prior.mode == "music" and prior.music_mode == "spectrum" and prior.music_color is None
    with pytest.raises(EffectRestorationError, match="music colour"):
        await async_prepare_effect_control_state(coordinator, require_restorable_static=True)
    with pytest.raises(ValueError, match="fixed colour"):
        await coordinator.async_restore_effect_control_state(prior, overwritten_diy_code=None)
    coordinator.send_command.assert_not_awaited()


@pytest.mark.parametrize("condition", ["resident", "overwritten", "unsupported"])
async def test_resident_palette_program_reselection_never_restores_an_overwritten_or_unsupported_body(hass, condition):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6159", configuration_url=None)
    coordinator.profile = device_profile("H6159", 1, 1, firmware="1.07.02", hardware="1.00.02")
    if condition == "unsupported":
        coordinator.profile = replace(coordinator.profile, effect_workflows=frozenset())
    state = replace(
        coordinator.capture_effect_control_state(),
        is_on=True,
        mode="scene",
        scene_code=198,
        effect=None,
        brightness_pct=37,
    )
    coordinator.send_command = AsyncMock()
    coordinator.refresh_state = AsyncMock(return_value=True)
    assert not await coordinator.async_restore_effect_control_state(
        state, overwritten_diy_code=198 if condition == "overwritten" else None
    )
    sent = [call.args[0] for call in coordinator.send_command.await_args_list]
    if condition == "resident":
        assert sent == [
            build_power(True, coordinator.model),
            build_brightness(37, coordinator.model),
            build_scene_activation(coordinator.model, 198, profile=coordinator.profile),
        ]
        coordinator.refresh_state.assert_awaited_once()
    else:
        assert sent == []
        coordinator.refresh_state.assert_not_awaited()


@pytest.fixture
def physical(hass, monkeypatch, request):
    model = getattr(request, "param", "H617A")
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", model, configuration_url="test")
    if model == "H7020":
        coordinator.pact_type = coordinator.pact_code = 1
        coordinator._resolve_device_profile()
        coordinator._apply_configured_strings(1)
    count = coordinator.profile.segment_count
    state = {
        "on": True,
        "brightness": 37,
        "colours": [(10, 20, 30)] * 14 + [(90, 80, 70)],
        "relative": [30] * 14 + [70],
        "fault": None,
        "packets": [],
        "colour_modes": ["rgb"] * count,
        "scene": None,
    }
    if model == "H1771":
        state.update(
            colours=[(255, 255, 255), (255, 147, 44), (255, 0, 0), (204, 219, 255)],
            relative=[1, 50, 70, 1],
            sources=[True, False],
            gradual=True,
        )

    async def transmit(_uuid, packet, **_kwargs):
        state["packets"].append(packet)
        fault = state["fault"]
        if packet[0] == 0x33:
            if packet[1] == 1:
                state["on"] = bool(packet[2])
            elif packet[1] == 4 and fault != "brightness":
                state["brightness"] = packet[2]
            elif packet[1:3] == b"\x05\x04":
                state["scene"] = list(packet[3:5])
                state["colours"] = [(255, 0, 0)] * count
                state["relative"] = [100] * count
                if model == "H1771":
                    state["sources"] = [True, True]
                    state["gradual"] = False
            elif packet[1] == 0x36 and model == "H1771":
                state["sources"][packet[2]] = bool(packet[3])
            elif packet[1] == 0xA3 and model == "H1771":
                state["gradual"] = bool(packet[2])
            static = parse_static_write(packet, coordinator.model, profile=coordinator.profile)
            if static is not None:
                state["scene"] = None
                for index in range(count):
                    if static.segment_mask & (1 << index):
                        if static.rgb is not None and fault != "colour":
                            state["colours"][index] = static.rgb
                            state["colour_modes"][index] = "rgb"
                        elif static.kelvin is not None:
                            state["colours"][index] = static.kelvin_companion_rgb
                            state["colour_modes"][index] = "kelvin"
                        if static.brightness_pct is not None and fault != "relative":
                            state["relative"][index] = static.brightness_pct
        elif packet[0] == 0xAA:
            domain = packet[1]
            if fault == "stale":
                return
            if domain == 1 and fault != "missing_power":
                coordinator._notify_callback(None, reply(1, [int(state["on"])]))
            elif domain == 4 and fault != "missing_brightness":
                coordinator._notify_callback(None, reply(4, [state["brightness"]]))
            elif domain == 5 and fault != "missing_mode":
                coordinator._notify_callback(
                    None,
                    reply(
                        5,
                        [0x13, 0x04, 50, 0, 0, 0, 0, 0]
                        if fault == "mode"
                        else [0x04, *state["scene"]]
                        if state["scene"] is not None
                        else [0x15, 0, *state.get("kelvin", 0).to_bytes(2, "big")],
                    ),
                )
            elif domain == 0x0F and fault != "missing_count":
                coordinator._notify_callback(None, reply(0x0F, [1]))
            elif domain == 0x41:
                coordinator._notify_callback(None, reply(0x41, [1]))
            elif domain == 0xA5 and packet[2] == (1 if model == "H1771" else 5):
                pages = [5, 2, 4, 1, 3] if fault == "reordered" else range(1, 2 if model == "H1771" else 6)
                size = coordinator.profile.segment_group_size
                for page in pages:
                    if fault == "partial" and page == 3:
                        continue
                    body = [page]
                    for index in range((page - 1) * size, page * size):
                        body.extend([state["relative"][index], *state["colours"][index]])
                    coordinator._notify_callback(None, reply(0xA5, body))
        elif packet[:2] == b"\xac\x03" and model == "H1771":
            first, second = state["sources"]
            flags = int(state["on"]) | (int(first) << 1) | (int(second) << 2)
            records = {0x36: f"3601{flags:02x}", 0xA3: f"a301{int(state['gradual']):02x}", 0x41: "41020000"}
            if fault == "missing_gradual":
                records.pop(0xA3)
            if fault == "invalid_gradual":
                records[0xA3] = "a30102"
            if fault == "invalid_power_on":
                records[0x41] = "410200ff"
            body = "".join(records.get(domain, "") for domain in packet[3 : 3 + packet[2]])
            response = bytearray(frame(f"ac000100{len(body) // 2:02x}0300{body}"))
            if fault == "invalid_gradual" and 0xA3 in packet[3 : 3 + packet[2]]:
                asyncio.get_running_loop().call_soon(coordinator._notify_callback, None, response)
            else:
                coordinator._notify_callback(None, response)

    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=transmit), disconnect=AsyncMock())
    coordinator._client = client
    coordinator._notification_token = object()
    coordinator._notify_started_monotonic = time.monotonic() - 1
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(coordinator, "_renew_foreground_lease", MagicMock())
    refresh = coordinator.refresh_state
    segments = coordinator.async_refresh_segments
    monkeypatch.setattr(coordinator, "refresh_state", lambda request: refresh(replace(request, timeout=0.02)))
    monkeypatch.setattr(coordinator, "async_refresh_segments", lambda: segments(timeout=0.02))
    return coordinator, state


@pytest.mark.parametrize("physical", ["H617A", "H1771"], indirect=True)
async def test_public_effect_off_restores_non_source_segment_layout(hass, physical, virtual_clock):
    coordinator, state = physical
    light = GoveeBLELight(coordinator)
    light._attr_device_info = None
    light.async_added_to_hass = AsyncMock()
    assert await async_setup_component(hass, "light", {})
    await hass.data["light"].async_add_entities([light])
    if coordinator.model == "H1771":
        # A known RGB write takes precedence over an identical Kelvin companion.
        await light.async_set_segment_color([3], state["colours"][1])
    expected_colours, expected_levels = list(state["colours"]), list(state["relative"])
    effect = "Rainbow" if coordinator.model == "H1771" else "Sunrise"
    await hass.services.async_call("light", "turn_on", {"entity_id": light.entity_id, "effect": effect}, blocking=True)
    assert state["colours"] != expected_colours
    assert state["relative"] != expected_levels
    request = {"entity_id": light.entity_id, "effect": "off"}
    expected_brightness = 37
    if coordinator.model == "H1771":
        request["brightness"] = 128
        expected_brightness = 50
    state["packets"].clear()
    await hass.services.async_call("light", "turn_on", request, blocking=True)
    assert state["colours"] == expected_colours
    assert state["relative"] == expected_levels
    assert state["brightness"] == expected_brightness and state["on"]
    assert [packet[2] for packet in state["packets"] if packet[:2] == b"\x33\x04"] == [expected_brightness]
    if coordinator.model == "H1771":
        assert state["colour_modes"] == ["rgb", "kelvin", "rgb", "kelvin"]
        assert state["sources"] == [True, False] and state["gradual"]


@pytest.mark.parametrize("physical", ["H1771"], indirect=True)
@pytest.mark.parametrize("fault", ["missing_gradual", "invalid_gradual", "invalid_power_on"])
async def test_effect_recovery_uses_only_current_layout_settings(physical, virtual_clock, fault):
    coordinator, state = physical
    light = GoveeBLELight(coordinator)
    light.async_write_ha_state = MagicMock()
    assert await coordinator.refresh_state(RefreshRequest(refresh_all=True))
    if fault != "invalid_power_on":
        state["gradual"] = False
    state["fault"] = fault
    await light.async_turn_on(effect="Rainbow")
    assert state["scene"] is not None
    if fault != "invalid_power_on":
        state["fault"] = None
    await light.async_turn_on(effect="off")
    assert state["scene"] is None
    assert state["gradual"] is (fault == "invalid_power_on")


@pytest.mark.parametrize("changed", [True, False])
@pytest.mark.parametrize("physical", ["H1771", "H617A"], indirect=True)
async def test_selection_rechecks_layout_at_first_physical_write(physical, monkeypatch, virtual_clock, changed):
    coord, state = physical
    light = GoveeBLELight(coord)
    light.async_write_ha_state = MagicMock()
    send = coord._async_write_packet
    injected = False

    async def accept_palette(client, packet, **kwargs):
        nonlocal injected
        if kwargs.get("arm_expected") and not injected:
            assert coord.control_write_attempts == 0
            injected = True
            if changed:
                state["relative"] = [24] * coord.profile.segment_count
            size = coord.profile.segment_group_size
            for start in range(0, coord.profile.segment_count, size):
                body = [1 + start // size]
                for position in range(start, min(start + size, coord.profile.segment_count)):
                    body.extend([state["relative"][position], *state["colours"][position]])
                coord._notify_callback(None, reply(0xA5, body))
            assert coord.segment_brightness == state["relative"]
        await send(client, packet, **kwargs)

    monkeypatch.setattr(coord, "_async_write_packet", accept_palette)
    select = light.async_turn_on(effect="Rainbow" if coord.model == "H1771" else "Sunrise")
    if changed:
        with pytest.raises(HomeAssistantError) as error:
            await select
        assert isinstance(error.value.__cause__, ValueError) and "observed device state" in str(error.value.__cause__)
        assert coord.control_write_attempts == 0 and state["scene"] is None
    else:
        await select
        assert state["scene"] is not None
    assert injected


@pytest.mark.parametrize("physical", ["H1771"], indirect=True)
@pytest.mark.parametrize("changed", [True, False])
async def test_off_tracks_selector_changes_not_reply_count(physical, monkeypatch, virtual_clock, changed):
    coord, state = physical
    light = GoveeBLELight(coord)
    light.async_write_ha_state = MagicMock()
    await light.async_turn_on(effect="Rainbow")
    attempts = coord.control_write_attempts
    preflight = coord.async_preflight_static_off

    async def preflight_with_report():
        guard = await preflight()
        if changed:
            report_scene(coord, virtual_clock, 91)
        coord._notify_callback(None, reply(5, [4, *state["scene"]]))
        assert coord.scene_code == 22
        return guard

    monkeypatch.setattr(coord, "async_preflight_static_off", preflight_with_report)
    if changed:
        with pytest.raises(HomeAssistantError):
            await coord.async_select_music_slug("off")
        assert coord.control_write_attempts == attempts
    else:
        state["packets"].clear()
        await coord.async_select_music_slug("off")
        assert state["scene"] is None and state["packets"].count(frame("aaa501")) == 1


@pytest.mark.parametrize("physical", ["H1771"], indirect=True)
@pytest.mark.parametrize("exit_path", ["light", "rollback", "rollback_after_release"])
async def test_partial_exit_requires_evidence_not_another_repaint(physical, monkeypatch, virtual_clock, exit_path):
    coord, state = physical
    light = GoveeBLELight(coord)
    light.async_write_ha_state = MagicMock()
    levels, sources = list(state["relative"]), list(state["sources"])
    if exit_path == "light":
        await light.async_turn_on(effect="Rainbow")
    else:
        assert await coord.refresh_state(RefreshRequest(refresh_all=True))
        target = coord.capture_effect_control_state()
        state.update(scene=[22, 0], relative=[100] * 4, sources=[True, True], gradual=False)
        coord._notify_callback(None, reply(5, [4, 22, 0]))
    state["fault"] = "relative"
    if exit_path == "light":
        with pytest.raises(HomeAssistantError) as error:
            await light.async_turn_on(effect="off", brightness=128)
        assert error.value.translation_key == "partial_command"
    else:
        assert not await coord.async_restore_effect_control_state(target, overwritten_diy_code=None)
    assert state["scene"] is None and state["relative"] != levels
    if exit_path == "rollback_after_release":
        if expected_mode := coord._expected_state.get("color_mode"):
            virtual_clock.vtime = max(virtual_clock.vtime, expected_mode[1])
        state["scene"] = [91, 0]
        coord._notify_callback(None, reply(5, [4, 91, 0]))
        assert coord.scene_code == 91
        client = coord._client
        client.disconnect.side_effect = lambda: setattr(client, "is_connected", False)
        await coord._async_disconnect_on_timeout(coord._disconnect_generation)
        assert coord._client is None
        state["scene"] = None

        async def connect(*_args, **_kwargs):
            client.is_connected = True
            return client

        client.services = []
        client.start_notify = AsyncMock()
        coord._ensure_connected = GoveeBLECoordinator._ensure_connected.__get__(coord)
        monkeypatch.setattr("custom_components.ha_govee_led_ble.coordinator.async_establish_ble_connection", connect)
    attempts = coord.control_write_attempts
    state["fault"] = None
    with pytest.raises(HomeAssistantError) as error:
        await coord.async_select_music_slug("off")
    assert error.value.translation_key == "partial_command" and coord.control_write_attempts == attempts
    state.update(relative=levels, sources=sources, gradual=True)
    await coord.async_select_music_slug("off")
    assert coord.control_write_attempts == attempts and coord._pre_mode_snapshot is None
    assert state["brightness"] == (50 if exit_path == "light" else 37)


@pytest.mark.parametrize("physical", ["H1771"], indirect=True)
@pytest.mark.parametrize("changed", [False, True])
async def test_repeat_off_rechecks_verified_layout_at_completion(physical, monkeypatch, virtual_clock, changed):
    coord, state = physical
    light = GoveeBLELight(coord)
    light.async_write_ha_state = MagicMock()
    levels, sources = list(state["relative"]), list(state["sources"])
    await light.async_turn_on(effect="Rainbow")
    state["fault"] = "relative"
    with pytest.raises(HomeAssistantError) as error:
        await light.async_turn_on(effect="off")
    assert error.value.translation_key == "partial_command"
    target = coord._incomplete_static_exit
    assert target is not None
    state.update(relative=levels, sources=sources, gradual=True, fault=None)

    async def report_palette():
        if changed:
            state.update(colours=[(0, 0, 255)] * 4, relative=[20] * 4)
        body = [1]
        for rgb, level in zip(state["colours"], state["relative"], strict=True):
            body.extend([level, *rgb])
        revision = coord._field_revisions["segment_colors"]
        coord._notify_callback(None, reply(0xA5, body))
        assert coord._field_revisions["segment_colors"] > revision

    monkeypatch.setattr(light, "_async_supersede_preview", report_palette)
    attempts = coord.control_write_attempts
    if changed:
        with pytest.raises(HomeAssistantError) as error:
            await light.async_turn_on(effect="off")
        assert error.value.translation_key == "partial_command"
        assert coord._incomplete_static_exit is target
    else:
        await light.async_turn_on(effect="off")
        assert coord._incomplete_static_exit is None
    assert coord.control_write_attempts == attempts and coord.static_mode_confirmed()


@pytest.mark.parametrize("physical", ["H1771"], indirect=True)
async def test_complete_bulk_reply_without_requested_source_flags_cannot_confirm_off(physical, virtual_clock):
    coord, state = physical
    light = GoveeBLELight(coord)
    light.async_write_ha_state = MagicMock()
    await light.async_turn_on(effect="Rainbow")
    send = coord._client.write_gatt_char.side_effect

    async def omit_flags(uuid, packet, **kwargs):
        if packet[:4] == b"\xac\x03\x01\x36":
            coord._notify_callback(None, bytearray(frame("ac000100030300a30101")))
        else:
            await send(uuid, packet, **kwargs)

    coord._client.write_gatt_char.side_effect = omit_flags
    with pytest.raises(HomeAssistantError) as error:
        await light.async_turn_on(effect="off")
    assert error.value.translation_key == "partial_command" and state["sources"] == [True, True]
    assert not coord._bulk_query_incomplete


@pytest.mark.parametrize("physical", ["H1771"], indirect=True)
@pytest.mark.parametrize(
    ("prior_scene", "update"),
    [
        (True, "matching"),
        (True, "source_readback"),
        (True, "recovering_record"),
        (False, "recovering_record"),
        (True, "recovering_source"),
        (True, "matching_recovering_source"),
        (True, "before_rejected_ack"),
        (False, "before_rejected_ack"),
        (True, "own_activation"),
    ],
)
async def test_saved_failure_preserves_new_scene_across_recovery(
    physical, monkeypatch, virtual_clock, prior_scene, update
):
    from custom_components.ha_govee_led_ble.effect_catalogue import MODEL_EFFECT_CATALOGUES
    from custom_components.ha_govee_led_ble.native_effect import NativeEffect

    coord, state = physical
    light = GoveeBLELight(coord)
    light.async_write_ha_state = MagicMock()
    if prior_scene:
        await light.async_turn_on(effect="Rainbow")
        await coord.async_set_boolean_control("source_1_enabled", False)
    send = coord._client.write_gatt_char.side_effect
    failed = observed = False

    def set_scene(code):
        nonlocal observed
        state["scene"] = [code, 0]
        report_scene(coord, virtual_clock, code)
        observed = True

    async def interrupt(uuid, packet, **kwargs):
        nonlocal failed
        if not failed and packet[0] == 0xA3 and coord._upload_ack is not None:
            failed = True
            await send(uuid, packet, **kwargs)
            if update == "before_rejected_ack":
                set_scene(91)
                state["packets"].clear()
            coord._notify_callback(None, bytearray(frame("a358ff00" if update == "own_activation" else "a358ff01")))
            return
        if update == "own_activation" and packet[:3] == b"\x33\x05\x0a":
            await send(uuid, packet, **kwargs)
            code = int.from_bytes(packet[3:5], "little")
            coord._notify_callback(None, reply(5, [0x0A, *packet[3:5]]))
            assert coord.diy_code == code
            return
        if (
            failed
            and not observed
            and update in {"matching", "source_readback", "own_activation"}
            and packet[:4] == b"\xac\x03\x01\x36"
        ):
            assert state["scene"] == [22, 0]
            set_scene(91 if update == "source_readback" else 22)
        await send(uuid, packet, **kwargs)

    coord._client.write_gatt_char.side_effect = interrupt
    store = InMemoryVersionedDocumentStore()
    repository = EffectDeploymentRepository(store)
    await repository.async_load()
    if update in {"recovering_record", "own_activation"}:
        put = repository.async_put

        async def persist(record, **kwargs):
            if update == "own_activation" and record.phase is DeploymentPhase.VERIFYING:
                raise RuntimeError("interrupted after own activation")
            await put(record, **kwargs)
            if update == "recovering_record" and record.phase is DeploymentPhase.RECOVERING:
                set_scene(91)
                state["packets"].clear()

        monkeypatch.setattr(repository, "async_put", persist)
    if update in {"recovering_source", "matching_recovering_source"}:
        save = store.async_save

        async def persist_source(data):
            nonlocal observed
            if any(row["phase"] == "recovering" for row in data["records"].values()):
                changed = update == "recovering_source"
                state["sources"] = [True, changed]
                revision = coord._field_revisions["boolean_source_1_enabled"]
                coord._notify_callback(None, bytearray(frame("ee300107" if changed else "ee300103")))
                assert coord._field_revisions["boolean_source_1_enabled"] > revision
                assert coord.boolean_control_state["source_1_enabled"] is changed
                assert coord.scene_code == 22
                state["packets"].clear()
                observed = True
            await save(data)

        monkeypatch.setattr(store, "async_save", persist_source)
    item = next(t.content for t in MODEL_EFFECT_CATALOGUES["H1771"].templates if isinstance(t.content, NativeEffect))
    match = "interrupted after own activation" if update == "own_activation" else "Device rejected A3 upload"
    with pytest.raises(RuntimeError, match=match):
        await EffectDeploymentEngine(repository).async_apply_saved(
            coord, LibraryItem.new("Test", item), config_entry_id="entry", updated_at="2026-11-18T00:00:00Z"
        )
    loaded = EffectDeploymentRepository(store)
    await loaded.async_load()
    (record,) = loaded.snapshot().records
    assert observed and record.prior_state.scene_code == (22 if prior_scene else None)
    assert record.error_code == "deployment_failed"
    recovered = update in {"matching", "matching_recovering_source", "own_activation"}
    assert record.phase is (DeploymentPhase.FAILED if recovered else DeploymentPhase.UNCERTAIN)
    assert state["scene"] == [22 if recovered or update == "recovering_source" else 91, 0]
    assert state["sources"] == [True, update in {"source_readback", "recovering_source"}]
    if update in {"recovering_record", "recovering_source", "before_rejected_ack"}:
        assert not any(packet[0] == 0x33 for packet in state["packets"])


@pytest.mark.parametrize("physical", ["H1771"], indirect=True)
@pytest.mark.parametrize(
    "handoff", ["matching", "retry_prior", "upload_ack", "verification_retry", "confirmation_save"]
)
async def test_saved_effect_observation_authority(physical, monkeypatch, virtual_clock, handoff):
    from custom_components.ha_govee_led_ble.effect_catalogue import MODEL_EFFECT_CATALOGUES
    from custom_components.ha_govee_led_ble.effect_identity import EffectDeviceCache
    from custom_components.ha_govee_led_ble.native_effect import NativeEffect

    coord, state = physical
    light = GoveeBLELight(coord)
    light.async_write_ha_state = MagicMock()
    await light.async_turn_on(effect="Rainbow")
    store = InMemoryVersionedDocumentStore()
    repo = EffectDeploymentRepository(store)
    await repo.async_load()
    cache = EffectDeviceCache(InMemoryVersionedDocumentStore())
    await cache.async_load()
    send, save = coord._client.write_gatt_char.side_effect, store.async_save
    selector = [4, 22, 0]
    activations = 0

    def set_scene(code):
        nonlocal selector
        selector = [4, code, 0]
        revision = coord._selector_revision
        report_scene(coord, virtual_clock, code)
        assert (coord._selector_revision > revision) is (code != 22)

    async def transmit(uuid, packet, **kwargs):
        nonlocal selector, activations
        if packet[0] == 0xA3 and coord._upload_ack is not None:
            await send(uuid, packet, **kwargs)
            if handoff == "upload_ack":
                set_scene(91)
            else:
                coord._notify_callback(None, reply(5, selector))
            coord._notify_callback(None, bytearray(frame("a358ff00")))
        elif packet[:3] == b"\x33\x05\x0a":
            activations += 1
            if handoff != "retry_prior" or activations > 1:
                selector = [0x0A, *packet[3:5]]
                coord._notify_callback(None, reply(5, selector))
        elif packet[:2] == b"\xaa\x05":
            if handoff == "verification_retry" and activations:
                set_scene(91)
            elif handoff == "retry_prior" and activations == 1:
                set_scene(22)
            else:
                coord._notify_callback(None, reply(5, selector))
        else:
            await send(uuid, packet, **kwargs)

    async def persist(data):
        if handoff == "confirmation_save" and any(row["phase"] == "confirmed" for row in data["records"].values()):
            set_scene(91)
        await save(data)

    monkeypatch.setattr(store, "async_save", persist)
    coord._client.write_gatt_char.side_effect = transmit
    content = next(t.content for t in MODEL_EFFECT_CATALOGUES["H1771"].templates if isinstance(t.content, NativeEffect))
    engine = EffectDeploymentEngine(repo, device_cache=cache)
    item = LibraryItem.new("Test", content)
    if handoff == "upload_ack":
        with pytest.raises(ModeTransitionSupersededError, match="observed device state changed"):
            await engine.async_apply_saved(coord, item, config_entry_id="entry", updated_at="2026-11-18T00:00:00Z")
    else:
        await engine.async_apply_saved(coord, item, config_entry_id="entry", updated_at="2026-11-18T00:00:00Z")
    loaded = EffectDeploymentRepository(store)
    await loaded.async_load()
    (record,) = loaded.snapshot().records
    assert activations == (0 if handoff == "upload_ack" else 2 if handoff == "retry_prior" else 1)
    assert record.phase is (
        DeploymentPhase.UNCERTAIN if handoff in {"upload_ack", "verification_retry"} else DeploymentPhase.CONFIRMED
    )
    observed = cache.get("entry")
    assert observed is not None
    if handoff in {"matching", "retry_prior"}:
        assert observed.mode == "custom" and observed.matched_operation_id == record.operation_id
    else:
        assert selector == [4, 91, 0]
        assert observed.mode == "scene" and observed.matched_operation_id is None


@pytest.mark.parametrize("physical", ["H1771"], indirect=True)
@pytest.mark.parametrize("changed", [False, True])
async def test_live_music_upload_preserves_accepted_selector(physical, hass, monkeypatch, virtual_clock, changed):
    from custom_components.ha_govee_led_ble.effect_domain import MusicProfile
    from custom_components.ha_govee_led_ble.effect_preview import PreviewPhase
    from tests.test_effect_preview import _manager, _open

    coord, state = physical
    send = coord._client.write_gatt_char.side_effect
    music = None

    async def transmit(uuid, packet, **kwargs):
        nonlocal music
        if packet[0] == 0xA3 and coord._upload_ack is not None:
            await send(uuid, packet, **kwargs)
            if changed:
                state["scene"] = [91, 0]
            revision = coord._selector_revision
            coord._notify_callback(None, reply(5, [4, 91, 0] if changed else [0x15, 1, 0, 0]))
            assert (coord._selector_revision > revision) is changed
            coord._notify_callback(None, bytearray(frame("a341ff00")))
        elif packet[:3] == b"\x33\x05\x13":
            music = [0x13, *packet[3:5]]
            state["scene"] = None
            await send(uuid, packet, **kwargs)
        elif packet[:2] == b"\xaa\x05" and music is not None:
            coord._notify_callback(None, reply(5, music))
        else:
            await send(uuid, packet, **kwargs)

    coord._client.write_gatt_char.side_effect = transmit
    manager, _ = await _manager(hass, monkeypatch, coord)
    owner, events = object(), []
    session = _open(manager, owner, events)
    try:
        await manager.async_queue_snapshot(
            session_id=session,
            owner=owner,
            config_entry_id="entry-a",
            sequence=1,
            updated_at="2026-11-18T00:00:00Z",
            item=LibraryItem.new("Flowing", MusicProfile("H1771", "flowing", 50)),
        )
        await manager.async_wait_idle("entry-a")
        if changed:
            assert music is None and state["scene"] == [91, 0] and coord.scene_code == 91
            assert events[-1].phase not in {PreviewPhase.WRITTEN, PreviewPhase.CONFIRMED}
        else:
            assert music == [0x13, 81, 50] and events[-1].phase is PreviewPhase.CONFIRMED
    finally:
        await manager.async_shutdown()


@pytest.mark.parametrize("physical", ["H1771"], indirect=True)
@pytest.mark.parametrize("palette_first", [False, True])
async def test_fresh_palette_revokes_kelvin_without_assuming_zero_means_rgb(physical, virtual_clock, palette_first):
    coordinator, state = physical
    light = GoveeBLELight(coordinator)
    state.update(kelvin=2200, colours=[(255, 152, 41)] * 4)
    assert await coordinator.refresh_state(RefreshRequest(refresh_all=True))
    assert light.color_temp_kelvin == 2200
    state["kelvin"] = 0
    assert await coordinator.refresh_state(RefreshRequest(refresh_all=True))
    assert light.color_temp_kelvin == 2200
    coordinator._notify_callback(None, reply(5, [0x15, 0, 0x08, 0x98]))
    zero = reply(5, [0x15, 1, 0, 0])
    blue = reply(0xA5, [1] + [30, 0, 0, 255] * 4)
    for packet in (blue, zero) if palette_first else (zero, blue):
        coordinator._notify_callback(None, packet)
    assert light.color_temp_kelvin is None and light.rgb_color == (0, 0, 255)


@pytest.mark.parametrize("entry", ["light", "music"])
async def test_effect_off_rechecks_cached_static_mode(physical, virtual_clock, entry):
    coordinator, state = physical
    light = GoveeBLELight(coordinator)
    light.async_write_ha_state = MagicMock()
    assert await coordinator.refresh_state(RefreshRequest(refresh_all=True))

    async def off(**kwargs):
        if entry == "light":
            await light.async_turn_on(effect="off", **kwargs)
        else:
            await coordinator.async_select_music_slug("off")

    state["packets"].clear()
    await off()
    assert build_colour_mode_query(coordinator.model, profile=coordinator.profile) in state["packets"]
    assert coordinator.control_write_attempts == 0
    state["scene"] = [22, 0]
    with pytest.raises(HomeAssistantError) as error:
        await off(brightness=100)
    assert error.value.translation_key == "recovery_not_ready"
    assert coordinator.control_write_attempts == 0 and state["brightness"] == 37


@pytest.mark.parametrize("physical", ["H1771"], indirect=True)
@pytest.mark.parametrize(("entry", "during_setting_readback"), [("light", False), ("music", False), ("light", True)])
async def test_off_does_not_finish_over_a_new_scene(physical, virtual_clock, entry, during_setting_readback):
    coordinator, state = physical
    light = GoveeBLELight(coordinator)
    light.async_write_ha_state = MagicMock()
    await light.async_turn_on(effect="Rainbow")
    client = coordinator._client
    transmit = client.write_gatt_char.side_effect
    state["packets"].clear()
    observed = False
    zone_reads = 0

    async def report_new_scene(uuid, packet, **kwargs):
        nonlocal zone_reads, observed
        if packet[:4] == b"\xac\x03\x01\x36":
            zone_reads += 1
            if zone_reads == (2 if during_setting_readback else 1):
                assert state["scene"] is None
                for field in ("color_mode", "effect"):
                    if field in coordinator._expected_state:
                        virtual_clock.vtime = max(virtual_clock.vtime, coordinator._expected_state[field][1])
                state["scene"] = [22, 0]
                coordinator._notify_callback(None, reply(5, [0x04, *state["scene"]]))
                assert coordinator.color_mode is ParsedMode.SCENE
                observed = True
        await transmit(uuid, packet, **kwargs)

    client.write_gatt_char.side_effect = report_new_scene
    off = light.async_turn_on(effect="off") if entry == "light" else coordinator.async_select_music_slug("off")
    with pytest.raises(HomeAssistantError if entry == "light" else ValueError) as error:
        await off
    if isinstance(error.value, HomeAssistantError):
        assert error.value.translation_key == "partial_command"
    assert observed and state["scene"] == [22, 0] and coordinator.active_mode == "scene"
    assert state["sources"] == [True, not during_setting_readback]
    assert sum(packet[:2] == b"\x33\x36" for packet in state["packets"]) == int(during_setting_readback)


@pytest.mark.parametrize("physical", ["H1771"], indirect=True)
@pytest.mark.parametrize(
    ("entry", "update"),
    [
        ("light", "unverified"),
        ("rollback", "unverified"),
        ("light", "before_gradual"),
        ("music", "new_palette"),
        ("light", "new_levels"),
        ("light", "matching"),
        ("rollback", "matching"),
    ],
)
async def test_source_recovery_requires_current_static_appearance(physical, virtual_clock, entry, update):
    coordinator, state = physical
    light = GoveeBLELight(coordinator)
    light.async_write_ha_state = MagicMock()
    state["on"] = entry != "rollback"
    await light.async_turn_on(effect="Rainbow")
    client = coordinator._client
    transmit = client.write_gatt_char.side_effect
    state["packets"].clear()
    state["fault"] = "relative" if update == "unverified" else None
    zone_reads = 0
    observed = False

    def report_palette(colours, levels):
        body = [1]
        for rgb, level in zip(colours, levels, strict=True):
            body.extend([level, *rgb])
        coordinator._notify_callback(None, reply(0xA5, body))
        assert coordinator.color_mode is ParsedMode.COLOUR
        assert coordinator.segment_colors == colours and coordinator.segment_brightness == levels

    async def report_update(uuid, packet, **kwargs):
        nonlocal zone_reads, observed
        if update == "before_gradual":
            await transmit(uuid, packet, **kwargs)
            static = parse_static_write(packet, coordinator.model, profile=coordinator.profile)
            if static is not None and static.brightness_pct == 70:
                for field, (_, deadline) in coordinator._expected_state.items():
                    if field.startswith("segment_"):
                        virtual_clock.vtime = max(virtual_clock.vtime, deadline)
                state.update(colours=[(0, 0, 255)] * 4, relative=[20] * 4)
                report_palette(state["colours"], state["relative"])
                observed = True
            return
        if packet[:4] == b"\xac\x03\x01\x36":
            zone_reads += 1
            if update != "unverified" and zone_reads == (2 if update == "new_levels" else 1):
                assert state["scene"] is None
                colours, levels = list(state["colours"]), list(state["relative"])
                if update == "new_palette":
                    report_palette([(0, 0, 255)] * 4, levels)
                    # A second accepted reply must not regain authority for this operation.
                    report_palette(colours, levels)
                elif update == "new_levels":
                    state["relative"] = [20] * 4
                    report_palette(colours, state["relative"])
                else:
                    report_palette(colours, levels)
                observed = True
        await transmit(uuid, packet, **kwargs)

    client.write_gatt_char.side_effect = report_update
    if entry == "rollback":
        prior = coordinator.require_static_baseline()
        assert await coordinator.async_restore_effect_control_state(prior, overwritten_diy_code=None) is (
            update == "matching"
        )
        assert not state["on"]
        assert frame("330100") in state["packets"]
    else:
        off = light.async_turn_on(effect="off") if entry == "light" else coordinator.async_select_music_slug("off")
        if update == "matching":
            await off
        else:
            with pytest.raises(HomeAssistantError if entry == "light" else ValueError) as error:
                await off
            if isinstance(error.value, HomeAssistantError):
                assert error.value.translation_key == "partial_command"
    writes = 1 if update in {"matching", "new_levels"} else 0
    assert observed is (update != "unverified")
    assert state["sources"] == [True, not writes]
    assert sum(packet[:2] == b"\x33\x36" for packet in state["packets"]) == writes
    if update in {"before_gradual", "unverified"}:
        assert not state["gradual"] and frame("33a301") not in state["packets"]


@pytest.mark.parametrize("physical", ["H1771"], indirect=True)
@pytest.mark.parametrize("entry", ["light", "music"])
@pytest.mark.parametrize("active_elsewhere", [False, True])
async def test_effect_off_qualifies_cold_mode_without_snapshot(
    physical, monkeypatch, virtual_clock, entry, active_elsewhere
):
    coordinator, state = physical
    light = GoveeBLELight(coordinator)
    light.async_write_ha_state = MagicMock()
    coordinator._present = True
    client = coordinator._client
    client.disconnect.side_effect = lambda: setattr(client, "is_connected", False)

    async def connected():
        client.is_connected = True
        coordinator._client = client
        if coordinator._notification_token is None:
            coordinator._notification_token = object()
            coordinator._notify_started_monotonic = virtual_clock.virtual_time()
        return client

    monkeypatch.setattr(coordinator, "_ensure_connected", connected)
    assert await coordinator.refresh_state(RefreshRequest(refresh_all=True))
    assert coordinator.static_mode_confirmed()
    await coordinator._async_disconnect_on_timeout(coordinator._disconnect_generation)
    assert coordinator._client is None
    if active_elsewhere:
        state["scene"] = [22, 0]
    state["packets"].clear()
    off = light.async_turn_on(effect="off") if entry == "light" else coordinator.async_select_music_slug("off")
    if active_elsewhere:
        with pytest.raises(HomeAssistantError) as error:
            await off
        assert error.value.translation_key == "recovery_not_ready"
    else:
        await off
    assert frame("aa0501") in state["packets"]
    assert coordinator.control_write_attempts == 0


@pytest.mark.parametrize("physical", ["H1771"], indirect=True)
@pytest.mark.parametrize(("entry", "already_static"), [("light", True), ("music", True), ("light", False)])
async def test_effect_off_rechecks_mode_before_replaying_suspended_history(
    physical, monkeypatch, virtual_clock, entry, already_static
):
    coordinator, state = physical
    light = GoveeBLELight(coordinator)
    light.async_write_ha_state = MagicMock()
    original = list(state["colours"]), list(state["relative"])
    await light.async_turn_on(effect="Rainbow")
    client = coordinator._client
    client.disconnect.side_effect = lambda: setattr(client, "is_connected", False)
    await coordinator._async_disconnect_on_timeout(coordinator._disconnect_generation)
    assert coordinator._client is None and coordinator._pre_mode_needs_qualification
    if already_static:
        state.update(scene=None, colours=[(0, 0, 255)] * 4, relative=[20] * 4)
    expected = (list(state["colours"]), list(state["relative"])) if already_static else original
    state["packets"].clear()

    async def connect(*_args, **_kwargs):
        client.is_connected = True
        return client

    client.services = []
    client.start_notify = AsyncMock()
    coordinator._ensure_connected = GoveeBLECoordinator._ensure_connected.__get__(coordinator)
    monkeypatch.setattr("custom_components.ha_govee_led_ble.coordinator.async_establish_ble_connection", connect)
    if entry == "light":
        await light.async_turn_on(effect="off")
    else:
        await coordinator.async_select_music_slug("off")

    assert (state["colours"], state["relative"]) == expected
    assert state["scene"] is None
    mode_read = state["packets"].index(frame("aa0501"))
    writes = [index for index, packet in enumerate(state["packets"]) if packet[0] == 0x33]
    if already_static:
        assert not writes and coordinator._pre_mode_snapshot is None
    else:
        assert mode_read < writes[0]


@pytest.mark.parametrize(
    ("initially_on", "release"),
    [
        (False, "idle"),
        (True, "idle"),
        (True, "poll"),
        (True, "poll_failed"),
        (True, "unexpected"),
        (True, "manual"),
        (True, "failed"),
        (True, "cancelled"),
        (True, "profile_changed"),
        (True, "resubscribed"),
    ],
)
async def test_public_effect_recovery_after_release(hass, physical, monkeypatch, virtual_clock, initially_on, release):
    coordinator, state = physical
    state["on"] = initially_on
    coordinator._present = True
    expected_colours, expected_levels = list(state["colours"]), list(state["relative"])
    client = coordinator._client
    client.disconnect.side_effect = lambda: setattr(client, "is_connected", False)

    async def connected():
        client.is_connected = True
        coordinator._client = client
        if coordinator._notification_token is None:
            coordinator._notification_token = object()
            coordinator._notify_started_monotonic = virtual_clock.virtual_time()
        return client

    monkeypatch.setattr(coordinator, "_ensure_connected", connected)
    light = GoveeBLELight(coordinator)
    light._attr_device_info = None
    light.async_added_to_hass = AsyncMock()
    assert await async_setup_component(hass, "light", {})
    await hass.data["light"].async_add_entities([light])

    async def control(effect):
        await hass.services.async_call(
            "light", "turn_on", {"entity_id": light.entity_id, "effect": effect}, blocking=True
        )

    async def lose_subscription():
        if release in {"idle", "poll", "poll_failed", "failed", "cancelled", "profile_changed"}:
            if release in {"failed", "cancelled", "profile_changed"}:

                async def interrupted_disconnect():
                    if release == "failed":
                        raise BleakError("Failed release")
                    if release == "cancelled":
                        raise asyncio.CancelledError
                    coordinator._advance_profile_generation()
                    client.is_connected = False

                client.disconnect.side_effect = interrupted_disconnect
            if release == "cancelled":
                with pytest.raises(asyncio.CancelledError):
                    await coordinator._async_disconnect_on_timeout(coordinator._disconnect_generation)
                return
            await coordinator._async_disconnect_on_timeout(coordinator._disconnect_generation)
            if release in {"poll", "poll_failed"}:
                coordinator._first_refresh_done = True
                if release == "poll_failed":
                    state["fault"] = "missing_mode"
                await coordinator._async_update_data()
                state["fault"] = None
                assert coordinator._client is None
        elif release == "manual":
            await coordinator.disconnect()
        elif release == "resubscribed":
            client.start_notify = AsyncMock()
            await coordinator._start_notify()
            return
        else:
            coordinator._disconnected_callback(client)
        assert coordinator._notification_token is None

    await control("Sunrise")
    await lose_subscription()
    if release not in {"idle", "poll"}:
        with pytest.raises(HomeAssistantError) as error:
            await control("off")
        assert error.value.translation_key == "recovery_not_ready"
        return
    await control("Rainbow")
    await lose_subscription()
    await control("off")
    assert state["on"] is initially_on
    assert state["brightness"] == 37
    assert state["colours"] == expected_colours
    assert state["relative"] == expected_levels


@pytest.mark.parametrize("physical", ["H7020"], indirect=True)
async def test_ambiguous_bulb_readback_never_repaints_white_as_rgb_during_rollback(physical, virtual_clock):
    coordinator, state = physical
    state["colours"] = [(255, 213, 161)] + [(255, 0, 0)] * 14
    state["colour_modes"][0] = "white"
    assert await coordinator.refresh_state(RefreshRequest(refresh_all=True))
    prior = coordinator.capture_effect_control_state()
    assert prior.color_temp_kelvin is None and prior.segment_colors == tuple(state["colours"])
    state["packets"].clear()
    with pytest.raises(EffectRestorationError, match="original static"):
        await async_prepare_effect_control_state(coordinator, require_restorable_static=True)
    assert not any(packet[0] == 0x33 for packet in state["packets"])
    state["packets"].clear()

    assert not await coordinator.async_restore_effect_control_state(prior, overwritten_diy_code=321)
    assert state["colour_modes"][0] == "white"
    assert not state["packets"]


@pytest.mark.parametrize("physical", ["H7020"], indirect=True)
@pytest.mark.parametrize("failure", ["ambiguous", "missing_geometry", "missing_count"])
async def test_prior_off_cleanup_does_not_require_static_recovery(physical, monkeypatch, failure):
    coordinator, state = physical
    coordinator.is_on = state["on"] = True
    prior = PriorControlState(
        mode="colour",
        is_on=False,
        brightness_pct=37,
        rgb_color=state["colours"][0],
        segment_colors=None if failure == "missing_geometry" else tuple(state["colours"]),
        segment_brightness=None if failure == "missing_geometry" else tuple(state["relative"]),
    )
    if failure != "ambiguous":
        coordinator.profile = replace(coordinator.profile, segment_colour_mode_ambiguous=False)
    if failure == "missing_count":
        state["fault"] = failure
        wait = coordinator._wait_for_revisions

        async def wait_for_reply(fields, domains, deadline, **kwargs):
            return False if "configured_strings" in fields else await wait(fields, domains, deadline, **kwargs)

        monkeypatch.setattr(coordinator, "_wait_for_revisions", wait_for_reply)
        with pytest.raises(ValueError, match="Cannot confirm configured"):
            await coordinator.async_restore_effect_control_state(prior, overwritten_diy_code=321)
    else:
        assert not await coordinator.async_restore_effect_control_state(prior, overwritten_diy_code=321)
    assert not state["on"]
    assert build_power(False, "H7020") in state["packets"]
    assert all(parse_static_write(packet, profile=get_profile("H7020")) is None for packet in state["packets"])


@pytest.mark.parametrize("on", [True, False])
@pytest.mark.parametrize("fault", [None, "brightness", "colour", "relative", "partial", "stale", "reordered", "mode"])
async def test_failed_deployment_restores_fresh_mixed_layout_and_persists_truth(
    physical, monkeypatch, virtual_clock, on, fault
):
    coordinator, physical_state = physical
    physical_state["on"] = on
    original = {key: value.copy() if isinstance(value, list) else value for key, value in physical_state.items()}
    # Cache intentionally differs from physical state in power, brightness and layout.
    coordinator.is_on = not on
    coordinator.brightness_pct = 99
    coordinator.segment_colors = [(255, 255, 255)] * 15
    coordinator.segment_brightness = [100] * 15
    coordinator.segment_state_source = "observed"
    store = InMemoryVersionedDocumentStore()
    repository = EffectDeploymentRepository(store)
    await repository.async_load()

    sequence = coordinator.async_write_effect_sequence

    async def failed_upload(packets, **kwargs):
        if not any(packet[0] == 0xA3 for packet in packets):
            return await sequence(packets, **kwargs)
        await coordinator.send_command(build_power(True))
        physical_state.update(brightness=99, colours=[(2, 3, 4)] * 15, relative=[100] * 15, fault=fault)
        raise RuntimeError("simulated effect failure after writes")

    monkeypatch.setattr(coordinator, "async_write_effect_sequence", AsyncMock(side_effect=failed_upload))
    with pytest.raises(RuntimeError, match="simulated effect failure"):
        await EffectDeploymentEngine(repository).async_apply_saved(
            coordinator,
            LibraryItem.new("Test", SingleEffect(0, 0, 50, ((255, 0, 0),))),
            config_entry_id="entry-a",
            updated_at="2026-09-17T00:00:00Z",
        )
    (record,) = repository.snapshot().records
    prior = record.prior_state
    assert prior.mode == "colour" and prior.is_on is on
    assert prior.brightness_pct == 37
    assert prior.segment_colors == tuple(original["colours"])
    assert prior.segment_brightness == tuple(original["relative"])
    assert record.phase is (DeploymentPhase.FAILED if fault in (None, "reordered") else DeploymentPhase.UNCERTAIN)
    assert physical_state["on"] is on
    if fault in (None, "reordered"):
        assert physical_state["colours"] == original["colours"]
        assert physical_state["relative"] == original["relative"]
        assert physical_state["brightness"] == 37
    loaded = EffectDeploymentRepository(store)
    await loaded.async_load()
    assert loaded.snapshot().records == repository.snapshot().records


@pytest.mark.parametrize("fault", ["missing_mode", "missing_power", "missing_brightness", "partial", "stale"])
async def test_failed_fresh_preflight_never_captures_defaults_or_writes(physical, fault):
    coordinator, state = physical
    state["fault"] = fault
    repository = EffectDeploymentRepository(InMemoryVersionedDocumentStore())
    await repository.async_load()
    with pytest.raises(RuntimeError, match="Could not read"):
        await EffectDeploymentEngine(repository).async_apply_saved(
            coordinator,
            LibraryItem.new("Test", SingleEffect(0, 0, 50, ((255, 0, 0),))),
            config_entry_id="entry-a",
            updated_at="2026-09-17T00:00:00Z",
        )
    (record,) = repository.snapshot().records
    assert record.phase is DeploymentPhase.FAILED
    assert record.prior_state is None
    assert coordinator.control_write_attempts == 0
    assert all(packet[0] == 0xAA for packet in state["packets"])


@pytest.mark.parametrize("mode", ["bloom", "shiny", "separation", "hopping", "piano_keys", "fountain", "day_and_night"])
async def test_known_music_body_replayed_exactly_but_ack_never_proves_settings(physical, monkeypatch, mode):
    from custom_components.ha_govee_led_ble.const import MUSIC_MODE_SLUGS

    coordinator, state = physical
    variant = music_variant(coordinator.profile, MUSIC_MODE_SLUGS[mode])
    body = variant.template
    if mode == "hopping":
        body = edit_music_body(
            body, mode, {"background": 0x010101, "relative_brightness": 17}, profile=coordinator.profile
        )
    coordinator.music_mode = mode
    coordinator._music_body = (mode, body)
    coordinator.music_sensitivity = 50
    coordinator.is_on = False
    prior = PriorControlState.from_dict(coordinator.capture_effect_control_state().to_dict())
    assert prior.mode == "music" and prior.music_body == body
    revisions = dict(coordinator._field_revisions)
    monkeypatch.setattr(coordinator, "refresh_state", AsyncMock(return_value=True))

    async def accepted_sequence(packets, **kwargs):
        # ACK boundary is separately tested by the parent; capture the exact upload here.
        assert kwargs["require_upload_ack"] is True
        assert [packet for packet in packets if packet[0] == 0xA3] == fragment_a3(0x41, body)
        for index, values in enumerate(kwargs["packet_state_values"]):
            kwargs["write_guard"]()
            for key, value in values.items():
                setattr(coordinator, key, value)
            kwargs["packet_on_write"](index)

    monkeypatch.setattr(coordinator, "async_write_effect_sequence", AsyncMock(side_effect=accepted_sequence))
    assert await coordinator.async_restore_effect_control_state(prior, overwritten_diy_code=None) is False
    assert coordinator.music_body == body
    assert coordinator._field_revisions == revisions
    assert state["on"] is False


@pytest.mark.parametrize("mode", ["unknown", "music", "colour"])
async def test_unknown_and_legacy_prior_state_never_substitutes_defaults(physical, mode):
    coordinator, state = physical
    prior = PriorControlState(mode=mode, is_on=True, brightness_pct=37, rgb_color=(1, 2, 3), music_mode="hopping")
    assert await coordinator.async_restore_effect_control_state(prior, overwritten_diy_code=None) is False
    assert state["packets"] == []


async def test_unknown_observed_mode_stays_unknown_in_capture(physical):
    coordinator, _ = physical
    coordinator.color_mode = ParsedMode.UNKNOWN
    assert coordinator.capture_effect_control_state().mode == "unknown"


async def test_nonsegment_restore_never_overwrites_notification_after_await(physical, monkeypatch):
    coordinator, _ = physical
    coordinator.model, coordinator.profile = "H600A", get_profile("H600A")
    prior = PriorControlState("colour", True, 37, (1, 2, 3), static_rgb_known=True)

    async def send(packets, *, write_guard, **_kwargs):
        for packet in packets:
            write_guard()
            if parse_static_write(packet, coordinator.model, profile=coordinator.profile) is not None:
                coordinator.rgb_color = (8, 9, 10)
                coordinator.brightness_pct = 12
                coordinator.is_on = False
                coordinator.color_mode = ParsedMode.UNKNOWN

    monkeypatch.setattr(coordinator, "async_write_effect_sequence", send)
    monkeypatch.setattr(coordinator, "refresh_state", AsyncMock(return_value=False))
    assert not await coordinator.async_restore_effect_control_state(prior, overwritten_diy_code=None)
    assert coordinator.rgb_color == (8, 9, 10)
    assert coordinator.brightness_pct == 12 and not coordinator.is_on
    assert coordinator.color_mode is ParsedMode.UNKNOWN


async def test_power_off_is_attempted_even_when_hidden_restoration_raises(physical, monkeypatch):
    coordinator, state = physical
    prior = PriorControlState(
        "colour", False, 37, (1, 2, 3), segment_colors=((1, 2, 3),) * 15, segment_brightness=(30,) * 15
    )
    send = coordinator._client.write_gatt_char.side_effect

    async def fail_colour(uuid, packet, **kwargs):
        if parse_static_write(packet) is not None:
            raise RuntimeError("colour write failed")
        await send(uuid, packet, **kwargs)

    coordinator._client.write_gatt_char.side_effect = fail_colour
    with pytest.raises(RuntimeError, match="colour write failed"):
        await coordinator.async_restore_effect_control_state(prior, overwritten_diy_code=None)
    assert state["on"] is False
