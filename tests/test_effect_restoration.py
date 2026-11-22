"""Fresh physical-state recovery through the real coordinator and deployment path."""

import asyncio
import io
import time
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component
from kaitaistruct import KaitaiStream

from custom_components.ha_govee_led_ble import coordinator as coordinator_module
from custom_components.ha_govee_led_ble.const import device_profile, get_profile
from custom_components.ha_govee_led_ble.control_arbiter import ControlIntent, async_control_intent
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_modes import ModeTransitionSupersededError
from custom_components.ha_govee_led_ble.coordinator_refresh import RefreshRequest
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode
from custom_components.ha_govee_led_ble.coordinator_upload import UploadAckTimeoutError
from custom_components.ha_govee_led_ble.effect_backend import EffectBackend
from custom_components.ha_govee_led_ble.effect_catalogue import resolve_catalogue_template
from custom_components.ha_govee_led_ble.effect_deployments import (
    DeploymentPhase,
    EffectDeploymentRepository,
    PriorControlState,
)
from custom_components.ha_govee_led_ble.effect_domain import (
    BuiltinScene,
    LibraryItem,
    RelativeBrightness,
    SingleEffect,
    VideoProfile,
)
from custom_components.ha_govee_led_ble.effect_runtime import (
    EffectDeploymentEngine,
    EffectRestorationError,
    EffectStateReadError,
    async_prepare_effect_control_state,
)
from custom_components.ha_govee_led_ble.effect_template_defaults import CatalogueTemplateDefault
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_brightness,
    build_colour_mode_query,
    build_diy_activation,
    build_power,
    build_scene_activation,
    require_profile_packet,
)
from custom_components.ha_govee_led_ble.layered_scene import CatalogueRef
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.light_commands import parse_static_write
from custom_components.ha_govee_led_ble.light_source import GoveeBLESourceLight
from custom_components.ha_govee_led_ble.music_commands import edit_music_body
from custom_components.ha_govee_led_ble.music_semantics import music_variant
from custom_components.ha_govee_led_ble.projector import ProjectorAppearance, ProjectorControl, ProjectorStars
from custom_components.ha_govee_led_ble.projector_protocol import decode_appearance
from custom_components.ha_govee_led_ble.projector_runtime import (
    apply_appearance,
    initialise,
    qualified_profile,
    read_appearance,
    set_control,
    source_request,
)
from custom_components.ha_govee_led_ble.protocol_core import H6093Projector
from custom_components.ha_govee_led_ble.scenes import SCENE_ENTRIES
from custom_components.ha_govee_led_ble.transport import fragment_a3, reassemble_a3, xor_checksum
from tests.coordinator_test_support import _packet, frame
from tests.storage_test_double import InMemoryVersionedDocumentStore


def reply(domain, body):
    payload = bytes([0xAA, domain, *body]).ljust(19, b"\0")
    return bytearray(payload + bytes([xor_checksum(payload)]))


@pytest.fixture
def resident_video(hass, monkeypatch, request):
    model = getattr(request, "param", "H6199")
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", model, configuration_url=None)
    state = {
        "on": False,
        "brightness": 20,
        "mode": "game",
        "saturation": 42,
        "writes": [],
        "fault": None,
        "boundary": None,
    }

    def observe_mode():
        if state["fault"] in {"missing", "optimistic", "stale"}:
            return
        selector = 1 if state["mode"] == "game" else 0 if state["mode"] == "movie" else 255
        body = (
            [0, 1, 8 if selector == 1 else 0 if selector == 0 else 255, state["saturation"], 1, 2, 55]
            if model == "H6099"
            else [0, 0, selector, state["saturation"], 1, 55]
        )
        coordinator._notify_callback(None, reply(5, body))

    async def transmit(_characteristic, packet, **_kwargs):
        if packet[0] == 0x33:
            state["writes"].append(packet)
            if packet[1] == 1:
                state["on"] = bool(packet[2])
            elif packet[1] == 4:
                state["brightness"] = packet[2]
        elif packet[:2] == b"\xaa\x01":
            coordinator._notify_callback(None, reply(1, [int(state["on"])]))
        elif packet[:2] == b"\xaa\x04":
            coordinator._notify_callback(None, reply(4, [state["brightness"]]))
        elif packet[:2] == b"\xaa\x05":
            observe_mode()

    client = MagicMock(
        is_connected=True,
        write_gatt_char=AsyncMock(side_effect=transmit),
        disconnect=AsyncMock(),
    )
    client.disconnect.side_effect = lambda: setattr(client, "is_connected", False)
    coordinator._client = client
    coordinator._notification_token = object()
    coordinator._notify_started_monotonic = time.monotonic() - 1
    if model == "H6199":
        coordinator._observe_pact(2, 1)
        for field, value in (
            ("fw_version", "1.10.04"),
            ("hw_version", "3.02.01"),
            ("subordinate_20_version", "1.03.00"),
            ("subordinate_21_version", "1.00.33"),
        ):
            coordinator._observe_identity_field(field, value)

    async def connected():
        if state["boundary"] is not None:
            boundary, state["boundary"] = state["boundary"], None
            boundary()
        return client

    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(side_effect=connected))
    monkeypatch.setattr(coordinator, "_renew_foreground_lease", MagicMock())
    refresh = coordinator.refresh_state

    async def bounded_refresh(request=None):
        return await refresh(replace(request or RefreshRequest(), timeout=0.01))

    monkeypatch.setattr(coordinator, "refresh_state", bounded_refresh)
    return coordinator, state


@pytest.mark.parametrize("resident_video", ["H6199", "H6099"], indirect=True)
async def test_public_cold_resident_video_resume_reads_native_state_without_claiming_recovery(resident_video):
    coordinator, state = resident_video
    light = GoveeBLELight(coordinator)
    light.async_write_ha_state = MagicMock()
    await light.async_turn_on(effect="Video: Game", brightness=51)
    assert state["writes"] == [build_power(True, coordinator.model), build_brightness(20, coordinator.model)]
    assert state["on"] and state["brightness"] == 20
    assert coordinator.video_saturation == 42
    assert coordinator.video_mode == "game"
    assert coordinator._pre_mode_snapshot is None and coordinator._incomplete_static_exit is None
    state["writes"].clear()
    for effect in ("Video: Movie", "off"):
        with pytest.raises(HomeAssistantError):
            await light.async_turn_on(effect=effect, brightness=102)
        assert state["writes"] == []


@pytest.mark.parametrize("fault", ["missing", "optimistic", "stale", "unknown", "query_timeout"])
async def test_public_cold_video_resume_requires_independent_complete_current_readback(
    resident_video, monkeypatch, fault
):
    coordinator, state = resident_video
    client = coordinator._client
    if fault == "query_timeout":
        monkeypatch.setattr(coordinator, "_send_state_queries", AsyncMock(return_value=False))
    if fault in {"optimistic", "stale"}:
        coordinator._notify_callback(None, reply(5, [0, 0, 1, 42, 1, 55]))
    if fault == "optimistic":
        coordinator._mode_write_generation += 1
    if fault == "stale":
        coordinator._notify_started_monotonic = time.monotonic() + 1
    if fault == "unknown":
        state["mode"] = "unknown"
    state["fault"] = fault
    light = GoveeBLELight(coordinator)
    light.async_write_ha_state = MagicMock()
    with pytest.raises(HomeAssistantError):
        await light.async_turn_on(effect="Video: Game", brightness=51)
    assert state["writes"] == []
    assert coordinator._pre_mode_snapshot is None
    if fault == "query_timeout":
        client.disconnect.assert_awaited_once()


@pytest.mark.parametrize("change", ["none", "settings", "supplementary"])
async def test_public_cold_video_resume_respects_compiled_template_defaults(hass, resident_video, change):
    coordinator, state = resident_video
    backend = await EffectBackend.async_create(hass)
    content = VideoProfile(
        coordinator.model,
        "game",
        False,
        42 if change != "settings" else 43,
        True,
        55,
        None,
        RelativeBrightness(100, 100, 100, 100) if change == "supplementary" else None,
        None,
    )
    await backend.template_defaults.async_set(
        CatalogueTemplateDefault(
            config_entry_id="entry-a",
            model=coordinator.model,
            template_id="template:video:game",
            content=content,
            updated_at="2026-11-22T00:00:00Z",
        )
    )
    light = GoveeBLELight(coordinator, config_entry_id="entry-a", effect_backend=backend)
    light.async_write_ha_state = MagicMock()
    if change == "none":
        await light.async_turn_on(effect="Video: Game", brightness=51)
        assert state["writes"] == [build_power(True, coordinator.model), build_brightness(20, coordinator.model)]
    else:
        with pytest.raises(HomeAssistantError):
            await light.async_turn_on(effect="Video: Game", brightness=51)
        assert state["writes"] == []
    assert coordinator._pre_mode_snapshot is None


@pytest.mark.parametrize("boundary", ["subscription", "profile", "selector", "settings", "identity"])
@pytest.mark.parametrize("after_power", [False, True])
async def test_public_cold_video_resume_rechecks_every_physical_boundary(
    resident_video, monkeypatch, boundary, after_power
):
    coordinator, state = resident_video
    refresh = coordinator.refresh_state

    def change():
        if boundary == "subscription":
            coordinator._notification_token = object()
        elif boundary == "profile":
            coordinator._profile_generation += 1
        elif boundary == "identity":
            coordinator._confirmed_identity_fields.clear()
        elif boundary == "selector":
            coordinator._notify_callback(None, reply(5, [0, 0, 0, 42, 1, 55]))
        else:
            coordinator._notify_callback(None, reply(5, [0, 0, 1, 43, 1, 55]))

    async def arm(request=None):
        result = await refresh(request)
        if request is not None and (request.on is True if after_power else request.refresh_all):
            state["boundary"] = change
        return result

    monkeypatch.setattr(coordinator, "refresh_state", arm)
    light = GoveeBLELight(coordinator)
    light.async_write_ha_state = MagicMock()
    with pytest.raises((ValueError, HomeAssistantError)):
        await light.async_turn_on(effect="Video: Game", brightness=51)
    assert state["writes"] == ([build_power(True, coordinator.model)] if after_power else [])
    assert coordinator._pre_mode_snapshot is None


async def test_public_cold_video_resume_stops_for_newer_foreground_work(resident_video, monkeypatch):
    coordinator, state = resident_video
    requested = asyncio.Event()
    power_confirmed = asyncio.Event()
    refresh = coordinator.refresh_state

    async def newer_work():
        await power_confirmed.wait()
        requested.set()
        async with async_control_intent(coordinator, ControlIntent.USER):
            pass

    async def interleave(request=None):
        result = await refresh(request)
        if request is not None and request.on is True:
            power_confirmed.set()
            await requested.wait()
        return result

    monkeypatch.setattr(coordinator, "refresh_state", interleave)
    newer = asyncio.create_task(newer_work())
    light = GoveeBLELight(coordinator)
    light.async_write_ha_state = MagicMock()
    try:
        with pytest.raises(HomeAssistantError):
            await light.async_turn_on(effect="Video: Game", brightness=51)
    finally:
        newer.cancel()
        await asyncio.gather(newer, return_exceptions=True)
    assert state["writes"] == [build_power(True, coordinator.model)]
    assert state["on"] and coordinator._pre_mode_snapshot is None


async def test_public_cold_video_resume_validates_basic_inputs_before_reading(resident_video, monkeypatch):
    coordinator, state = resident_video
    read = AsyncMock(side_effect=AssertionError("Invalid inputs must not query the device"))
    monkeypatch.setattr(coordinator, "refresh_state", read)
    light = GoveeBLELight(coordinator)
    with pytest.raises(HomeAssistantError):
        await light.async_turn_on(effect="Video: Game", brightness="invalid")
    read.assert_not_awaited()
    assert state["writes"] == []


@pytest.mark.parametrize("history", ["original", "incomplete"])
async def test_public_cold_video_resume_never_downgrades_existing_recovery(resident_video, history):
    coordinator, state = resident_video
    target = PriorControlState(mode="colour", is_on=True, brightness_pct=50, rgb_color=(1, 2, 3))
    field = "_pre_mode_snapshot" if history == "original" else "_incomplete_static_exit"
    setattr(coordinator, field, target)
    coordinator._pre_mode_profile = coordinator.profile
    coordinator._notify_callback(None, reply(5, [0, 0, 1, 42, 1, 55]))
    light = GoveeBLELight(coordinator)
    light.async_write_ha_state = MagicMock()
    with pytest.raises(HomeAssistantError):
        await light.async_turn_on(effect="Video: Game", brightness=51)
    assert state["writes"] == []
    assert getattr(coordinator, field) is target


@pytest.mark.parametrize(
    ("initial_pact", "confirmed_pact"),
    [
        (None, (1, 1)),
        (None, (2, 1)),
        ((1, 1), (1, 1)),
        ((2, 1), (2, 1)),
        ((1, 1), (2, 1)),
        ((2, 1), (1, 1)),
    ],
)
async def test_h6053_native_scene_without_pact_uses_version_qualified_baseline(
    hass, monkeypatch, initial_pact, confirmed_pact
):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6053", configuration_url=None)
    if initial_pact is not None:
        coordinator.pact_type, coordinator.pact_code = initial_pact
    scene_selected = False

    async def transmit(_uuid, packet, **_kwargs):
        nonlocal scene_selected
        if packet[:3] == b"\x33\x05\x04":
            scene_selected = True
        elif packet[:3] in {b"\x33\x05\x0d", b"\x33\x05\x15"}:
            scene_selected = False
        elif packet[:2] == b"\xaa\x33":
            coordinator._notify_callback(None, bytearray(frame("aa3311")))

    client = MagicMock(
        is_connected=True,
        write_gatt_char=AsyncMock(side_effect=transmit),
        disconnect=AsyncMock(),
    )
    client.disconnect.side_effect = lambda: setattr(client, "is_connected", False)
    coordinator._client = client
    coordinator._notification_token = object()
    coordinator._notify_started_monotonic = time.monotonic() - 1
    coordinator._observe_identity_field("fw_version", "1.08.05")
    coordinator._observe_identity_field("hw_version", "1.00.00")

    def observe_static():
        coordinator._notify_callback(None, bytearray(frame("aa0101")))
        coordinator._notify_callback(None, bytearray(frame("aa3311")))
        coordinator._notify_callback(None, bytearray(frame("aa05150000000000")))
        for group in range(1, 4):
            coordinator._notify_callback(None, bytearray(frame(f"aaa5{group:02x}" + "32112233" * 4)))

    async def refresh(*_args, **_kwargs):
        coordinator._notify_callback(None, bytearray(frame("aa0101")))
        if coordinator.identity_fields_confirmed(frozenset({"pact"})):
            coordinator._notify_callback(None, bytearray(frame("aa0425")))
        coordinator._notify_callback(None, bytearray(frame("aa3311")))
        if scene_selected:
            coordinator._notify_callback(None, bytearray(frame("aa05041800")))
        else:
            coordinator._notify_callback(None, bytearray(frame("aa05150000000000")))
        await refresh_segments()
        return True

    async def refresh_segments(*_args, **_kwargs):
        for group in range(1, 4):
            coordinator._notify_callback(None, bytearray(frame(f"aaa5{group:02x}" + "32112233" * 4)))
        return True

    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(coordinator, "_renew_foreground_lease", MagicMock())
    monkeypatch.setattr(coordinator, "_refresh_h607c_advertisements", MagicMock())
    monkeypatch.setattr(coordinator, "refresh_state", AsyncMock(side_effect=refresh))
    monkeypatch.setattr(coordinator, "async_refresh_segments", AsyncMock(side_effect=refresh_segments))
    observe_static()

    light = GoveeBLELight(coordinator)
    light.hass = hass
    light.async_write_ha_state = MagicMock()
    await light.async_turn_on(effect="Aurora")

    client.write_gatt_char.assert_awaited_once()
    assert client.write_gatt_char.await_args.args[1] == build_scene_activation("H6053", 24, profile=coordinator.profile)
    assert not coordinator.identity_fields_confirmed(frozenset({"pact"}))
    assert not coordinator._brightness_pct_known
    baseline = coordinator._pre_mode_snapshot
    assert baseline is not None and baseline.brightness_pct_known is False

    client.write_gatt_char.reset_mock()
    with pytest.raises(HomeAssistantError):
        await light.async_turn_on(effect="off", brightness=128)
    assert client.write_gatt_char.await_count == 0

    if initial_pact is None:
        coordinator._observe_pact(*confirmed_pact)
        assert coordinator._pre_mode_snapshot is baseline
        await light.async_turn_on(effect="off")
        packets = [call.args[1] for call in client.write_gatt_char.await_args_list]
        assert packets and all(packet[:2] != b"\x33\x04" for packet in packets)
        return

    if initial_pact is not None:
        await coordinator._disconnect_locked(planned_release=True)
        assert coordinator._pre_mode_snapshot is baseline
        client.is_connected = True
        coordinator._client = client
        coordinator._notification_token = object()
        coordinator._notify_started_monotonic = time.monotonic() - 1
        coordinator._observe_pact(*confirmed_pact)
        coordinator._observe_identity_field("fw_version", "1.08.05")
        coordinator._observe_identity_field("hw_version", "1.00.00")
        await refresh()
        assert coordinator._pre_mode_snapshot is baseline
        await light.async_turn_on(effect="off")
        packets = [call.args[1] for call in client.write_gatt_char.await_args_list]
        assert packets and all(packet[:2] != b"\x33\x04" for packet in packets)

        await light.async_turn_on(effect="Aurora")
        baseline = coordinator._pre_mode_snapshot
        assert baseline is not None
        client.write_gatt_char.reset_mock()
    coordinator._observe_pact(*confirmed_pact)
    assert coordinator._pre_mode_snapshot is baseline
    await light.async_turn_on(effect="off", brightness=128)
    packets = [call.args[1] for call in client.write_gatt_char.await_args_list]
    brightness_packets = [packet for packet in packets if packet[:2] == b"\x33\x04"]
    assert len(brightness_packets) == 1
    expected_brightness = build_brightness(50, "H6053", profile=coordinator.profile)
    if coordinator.profile.outbound_transform is not None:
        expected_brightness = coordinator.profile.outbound_transform(expected_brightness)
    assert brightness_packets[0] == expected_brightness


async def test_h6053_scene_recovery_preserves_unauthorized_master_brightness(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6053", configuration_url=None)
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    coordinator._client = client
    coordinator._notification_token = object()
    coordinator._notify_started_monotonic = time.monotonic() - 1
    coordinator._observe_identity_field("fw_version", "1.08.05")
    coordinator._observe_identity_field("hw_version", "1.00.00")
    coordinator._notify_callback(None, bytearray(frame("aa0101")))
    coordinator._notify_callback(None, bytearray(frame("aa3311")))
    coordinator._notify_callback(None, bytearray(frame("aa05041800")))

    prior = coordinator.capture_effect_control_state()
    assert prior.mode == "scene" and prior.scene_code == 24
    coordinator._notify_callback(None, bytearray(frame("aa05040f00")))
    client.write_gatt_char.reset_mock()
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(coordinator, "_renew_foreground_lease", MagicMock())
    monkeypatch.setattr(coordinator, "refresh_state", AsyncMock(return_value=True))
    monkeypatch.setattr(coordinator, "_async_read_bar_flags", AsyncMock(return_value=True))

    assert await coordinator.async_restore_effect_control_state(prior, overwritten_diy_code=None)

    packets = [call.args[1] for call in client.write_gatt_char.await_args_list]
    assert packets == [
        build_power(True, coordinator.model),
        build_scene_activation("H6053", 24, profile=coordinator.profile),
    ]
    assert not coordinator._brightness_pct_known


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
@pytest.mark.parametrize("model", ["H6139", "H6159"])
async def test_resident_palette_program_reselection_never_restores_an_overwritten_or_unsupported_body(
    hass, condition, model
):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", model, configuration_url=None)
    coordinator.profile = device_profile(model, 1, 1, firmware="1.07.02", hardware="1.00.01")
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
    target = getattr(request, "param", "H617A")
    model, pact = target if isinstance(target, tuple) else (target, None)
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", model, configuration_url="test")
    if model == "H7020":
        coordinator.pact_type = coordinator.pact_code = 1
        coordinator._resolve_device_profile()
        coordinator._apply_configured_strings(1)
    count = coordinator.profile.segment_count
    state = {
        "on": True,
        "brightness": 37,
        "colours": [(10, 20, 30)] * (count - 1) + [(90, 80, 70)],
        "relative": [30] * (count - 1) + [70],
        "fault": None,
        "packets": [],
        "colour_modes": ["rgb"] * count,
        "scene": None,
        "ic_count": coordinator.profile.physical_ic_count or 50,
    }
    if model == "H1771":
        state.update(
            colours=[(255, 255, 255), (255, 147, 44), (255, 0, 0), (204, 219, 255)],
            relative=[1, 50, 70, 1],
            sources=[True, False],
            gradual=True,
        )
    if model == "H1AB2":
        state.update(
            colours=[(0, 255, 0), *([(217, 225, 255)] * 3), (255, 174, 84), *([(217, 225, 255)] * 5)],
            relative=[100] * 9 + [20],
            gradual=False,
        )
    if model == "H6093":
        pact = pact or (2, 1)
        state.update(
            projector=ProjectorAppearance(
                ProjectorStars(True, 61, False, 25, True, 39),
                True,
                17,
                42,
                2,
                53,
                ((10, 20, 30), (40, 50, 60)),
                None if pact == (1, 1) else ((70, 80, 90),),
            ),
            native=True,
            upload=[],
            speaker=True,
            sound_enabled=False,
            sound_code=1,
            volume=50,
            settings={"pairing_prompt": False, "quiet_start": False, "dreamview_laser": False},
        )

    async def transmit(_uuid, packet, **_kwargs):
        state["packets"].append(packet)
        fault = state["fault"]
        if model == "H6093" and packet[0] == 0xA3:
            if packet[1] == 0:
                state["upload"] = []
            state["upload"].append(packet)
            if packet[1] == 255:
                envelope = reassemble_a3(state["upload"])
                if envelope[2] == 0x0C:
                    appearance = H6093Projector.Appearance(pact != (1, 1), KaitaiStream(io.BytesIO(envelope[3:])))
                    appearance._read()
                    state["projector"] = replace(decode_appearance(appearance), opaque=b"")
                pending = coordinator._upload_ack
                if pending is not None and fault != "missing_upload_ack":
                    coordinator._notify_callback(
                        None, frame(f"a3{pending.subtype:02x}{int(fault == 'upload_ack'):02x}")
                    )
            return
        if model == "H1AB2" and packet[0] == 0xA3:
            pending = coordinator._upload_ack
            if packet[1] == 255 and pending is not None:
                coordinator._notify_callback(
                    None,
                    bytearray(
                        _packet(pending.protocol, pending.subtype, [0] if pending.mode is None else [pending.mode, 0])
                    ),
                )
            return
        if packet[0] == 0x33:
            if packet[1] == 1:
                state["on"] = bool(packet[2])
                if model == "H6093":
                    state["speaker"] = False
            elif packet[1:3] == b"\x30\x01" and model == "H6093":
                state["on"] = bool(packet[3])
            elif packet[1] == 0x30 and model == "H6093":
                setting = {3: "pairing_prompt", 4: "quiet_start", 6: "sound_enabled", 7: "dreamview_laser"}[packet[2]]
                if fault != "setting":
                    if setting == "sound_enabled":
                        state[setting] = bool(packet[3])
                        state["speaker"] = bool(packet[3])
                    else:
                        state["settings"][setting] = bool(packet[3])
            elif packet[1] == 0x31 and model == "H6093":
                if fault != "setting":
                    state["speaker"] = bool(packet[2])
                    state["sound_code"] = 1 if fault == "sound_selection" else packet[3]
                    if fault == "pause_disables" and not packet[2]:
                        state["sound_enabled"] = False
            elif packet[1] == 0x32 and model == "H6093":
                if fault != "setting":
                    state["volume"] = packet[2]
            elif packet[1] == 4 and fault != "brightness":
                state["brightness"] = packet[2]
            elif packet[1:3] == b"\x05\x04":
                state["scene"] = list(packet[3:5])
                state["colours"] = [(255, 0, 0)] * count
                state["relative"] = [100] * count
                if model == "H6093":
                    state["projector"] = replace(
                        state["projector"],
                        coarse=((255, 0, 0),),
                        stars=replace(state["projector"].stars, brightness=100),
                    )
                if model == "H1771":
                    state["sources"] = [True, True]
                    state["gradual"] = False
            elif packet[1] == 0x36 and model == "H1771":
                state["sources"][packet[2]] = bool(packet[3])
            elif packet[1] == 0xA3:
                state["gradual"] = bool(packet[2])
            static = parse_static_write(packet, coordinator.model, profile=coordinator.profile)
            if static is not None:
                state["scene"] = None
                if model == "H6093":
                    state["native"] = static.kind == "projector"
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
            elif domain == 0x34 and model == "H6093" and fault != "missing_power":
                flags = (
                    (0x40 if state["on"] else 0)
                    | (4 if state["sound_enabled"] else 0)
                    | (8 if state["settings"]["pairing_prompt"] else 0)
                    | (32 if state["settings"]["quiet_start"] else 0)
                    | (2 if state["settings"]["dreamview_laser"] else 0)
                )
                coordinator._notify_callback(
                    None,
                    reply(
                        0x34,
                        [
                            flags,
                            state["brightness"],
                            128 if state["speaker"] else 0,
                            state["sound_code"],
                            state["volume"],
                        ],
                    ),
                )
            elif domain == 4 and fault != "missing_brightness":
                coordinator._notify_callback(None, reply(4, [state["brightness"]]))
            elif domain == 0xEF and model == "H6093" and fault != "missing_pact":
                coordinator._notify_callback(None, reply(0xEF, [*pact[0].to_bytes(2, "big"), pact[1]]))
            elif domain == 5 and fault != "missing_mode":
                coordinator._notify_callback(
                    None,
                    reply(
                        5,
                        [0x13, 0x04, 50, 0, 0, 0, 0, 0]
                        if fault == "mode"
                        else [0x04, *state["scene"]]
                        if state["scene"] is not None
                        else [0x0C]
                        if model == "H6093" and state["native"]
                        else [0x15, 0, *state.get("kelvin", 0).to_bytes(2, "big")],
                    ),
                )
            elif domain == 0x0F and fault != "missing_count":
                coordinator._notify_callback(None, reply(0x0F, [1]))
            elif domain == 0x40:
                coordinator._notify_callback(None, reply(0x40, list(state["ic_count"].to_bytes(2, "big"))))
            elif domain == 0xA3:
                coordinator._notify_callback(None, reply(0xA3, [int(state.get("gradual", False))]))
            elif domain == 0x41:
                coordinator._notify_callback(None, reply(0x41, [2, 0] if model == "H1AB2" else [1]))
            elif domain == 0xA5 and packet[2] == coordinator.profile.segment_group_count:
                pages = (
                    [5, 2, 4, 1, 3] if fault == "reordered" else range(1, coordinator.profile.segment_group_count + 1)
                )
                size = coordinator.profile.segment_group_size
                for page in pages:
                    if fault == "partial" and page == 3:
                        continue
                    body = [page]
                    for index in range((page - 1) * size, min(page * size, count)):
                        body.extend([state["relative"][index], *state["colours"][index]])
                    coordinator._notify_callback(None, reply(0xA5, body))
        elif packet[:4] == b"\xac\x03\x05\x0c" and model == "H6093":
            value = state["projector"]
            stars = value.stars
            raw = bytes(
                [
                    stars.enabled,
                    stars.brightness,
                    stars.flicker_enabled,
                    stars.flicker_speed,
                    stars.movement_enabled,
                    stars.movement_speed,
                    value.enabled,
                    value.movement_speed,
                    value.brightness,
                    value.pattern,
                    value.effect_speed,
                    len(value.coarse),
                    *(channel for colour in value.coarse for channel in colour),
                ]
            )
            chunks = [raw[:12], *(raw[index : index + 17] for index in range(12, len(raw), 17))]
            coordinator._notify_callback(
                None, frame(f"ac00{len(chunks).to_bytes(2, 'little').hex()}{len(chunks[-1]):02x}0305{chunks[0].hex()}")
            )
            for index, chunk in enumerate(chunks[1:], 1):
                if fault == "projector_read":
                    break
                coordinator._notify_callback(
                    None, frame(f"ac{255 if index == len(chunks) - 1 else index:02x}{chunk.hex()}")
                )
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

    client = MagicMock(
        is_connected=True,
        start_notify=AsyncMock(),
        write_gatt_char=AsyncMock(side_effect=transmit),
        disconnect=AsyncMock(),
    )
    client.disconnect.side_effect = lambda: setattr(client, "is_connected", False)
    coordinator._client = client
    coordinator._notification_token = object()
    coordinator._notify_started_monotonic = time.monotonic() - 1
    if model == "H6093":
        coordinator._observe_pact(*pact)

    async def reconnect():
        if coordinator._client is not client or not client.is_connected:
            client.is_connected = True
            coordinator._client = client
            await coordinator._start_notify()
            if model == "H6093":
                coordinator._observe_pact(*pact)
        return client

    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(side_effect=reconnect))
    monkeypatch.setattr(coordinator, "_renew_foreground_lease", MagicMock())
    refresh = coordinator.refresh_state
    segments = coordinator.async_refresh_segments
    monkeypatch.setattr(coordinator, "refresh_state", lambda request: refresh(replace(request, timeout=0.02)))
    monkeypatch.setattr(coordinator, "async_refresh_segments", lambda: segments(timeout=0.02))
    return coordinator, state


@pytest.mark.parametrize("physical", [("H6093", (1, 1)), ("H6093", (1, 2)), ("H6093", (2, 1))], indirect=True)
async def test_projection_power_is_independent_of_speaker_and_initialisation_establishes_native_state(physical):
    coordinator, state = physical
    await initialise(coordinator)
    assert state["on"] and state["speaker"]
    assert state["projector"].coarse == ((0, 0, 255),)
    assert state["projector"].stars.brightness == 50
    assert not state["projector"].stars.flicker_enabled and not state["projector"].stars.movement_enabled
    light = GoveeBLELight(coordinator)
    light.async_write_ha_state = MagicMock()
    await light.async_turn_off()
    assert not state["on"] and state["speaker"]
    assert any(packet[:4] == b"\x33\x30\x01\x00" for packet in state["packets"])


@pytest.mark.parametrize("physical", [("H6093", (1, 1)), ("H6093", (1, 2)), ("H6093", (2, 1))], indirect=True)
async def test_public_native_scene_off_restores_complete_projector_optics(physical):
    coordinator, state = physical
    prior = state["projector"]
    await apply_appearance(coordinator, prior)
    light = GoveeBLELight(coordinator)
    light.async_write_ha_state = MagicMock()
    await light.async_turn_on(brightness=80)
    baseline_brightness = state["brightness"]
    assert baseline_brightness == 31
    await light.async_turn_on(effect="Forest", brightness=230)
    assert state["projector"] != prior
    assert state["brightness"] != baseline_brightness
    assert coordinator._pre_mode_snapshot is not None
    assert coordinator._pre_mode_snapshot.projector_appearance == prior
    await light.async_turn_on(effect="off")
    assert state["projector"] == prior
    assert state["brightness"] == baseline_brightness
    assert coordinator.projector_appearance == prior


@pytest.mark.parametrize("physical", [("H6093", (1, 1)), ("H6093", (1, 2)), ("H6093", (2, 1))], indirect=True)
@pytest.mark.parametrize("path", ["native", "saved_scene", "saved_diy"])
@pytest.mark.parametrize("power", [False, True])
async def test_missing_scene_verdict_preserves_projector_controls_without_initialisation(
    physical, monkeypatch, path, power
):
    coordinator, state = physical
    await initialise(coordinator)
    prior = state["projector"]
    token, client = coordinator._notification_token, coordinator._client
    light = GoveeBLELight(coordinator)
    light.async_write_ha_state = MagicMock()
    if not power:
        await light.async_turn_off()
    state["packets"].clear()
    state["fault"] = "missing_upload_ack"
    monkeypatch.setattr(coordinator_module, "UPLOAD_ACK_TIMEOUT", 0.02)

    if path == "native":
        with pytest.raises(HomeAssistantError) as caught:
            await light.async_turn_on(effect="Milky Way")
        cause = caught.value
        while isinstance(cause, HomeAssistantError):
            cause = cause.__cause__
        assert isinstance(cause, UploadAckTimeoutError)
    else:
        scene = next(scene for scene in SCENE_ENTRIES["H6093"] if "Milky" in scene.name)
        content = (
            BuiltinScene(CatalogueRef("H6093", scene.scene_id, scene.effect_id))
            if path == "saved_scene"
            else resolve_catalogue_template("H6093", "template:projector:1").content
        )
        repository = EffectDeploymentRepository(InMemoryVersionedDocumentStore())
        await repository.async_load()
        engine = EffectDeploymentEngine(repository)
        with pytest.raises(UploadAckTimeoutError):
            await engine.async_apply_saved(
                coordinator,
                LibraryItem.new("Saved", content),
                config_entry_id="entry",
                updated_at="2026-11-22T00:00:00Z",
            )

    client.disconnect.assert_awaited_once()
    assert coordinator._notification_token is not token
    assert coordinator.projector_appearance == state["projector"] == prior
    assert state["scene"] is None
    assert coordinator._upload_ack is None
    assert not any(packet[:3] == b"\x33\x05\x04" for packet in state["packets"])
    assert sum(packet[:2] == b"\xa3\x00" for packet in state["packets"]) == 1
    if path != "native":
        assert state["on"] is power

    state["fault"] = None
    await source_request(coordinator, "stars", False)
    assert not state["projector"].stars.enabled
    await light.async_turn_on(effect="Forest")
    assert state["scene"] is not None


@pytest.mark.parametrize("physical", ["H6093"], indirect=True)
@pytest.mark.parametrize("fault", ["cancelled", "persistence", "new_owner"])
async def test_upload_power_cleanup_is_independent_of_failure_persistence(physical, monkeypatch, fault):
    coordinator, state = physical
    await initialise(coordinator)
    light = GoveeBLELight(coordinator)
    light.async_write_ha_state = MagicMock()
    await light.async_turn_off()
    state["fault"] = "missing_upload_ack"
    state["packets"].clear()
    scene = next(scene for scene in SCENE_ENTRIES["H6093"] if "Milky" in scene.name)
    item = LibraryItem.new("Scene", BuiltinScene(CatalogueRef("H6093", scene.scene_id, scene.effect_id)))
    repository = EffectDeploymentRepository(InMemoryVersionedDocumentStore())
    await repository.async_load()
    engine = EffectDeploymentEngine(repository)
    monkeypatch.setattr(coordinator_module, "UPLOAD_ACK_TIMEOUT", 1 if fault == "cancelled" else 0.02)
    if fault == "persistence":
        put = repository.async_put

        async def persist(record, **kwargs):
            if record.error_code == "upload_unconfirmed":
                raise OSError("Failure persistence is unavailable")
            await put(record, **kwargs)

        monkeypatch.setattr(repository, "async_put", persist)
    if fault == "new_owner":
        reconnect = coordinator._ensure_connected.side_effect
        token = coordinator._notification_token
        changed = False

        async def newer_request():
            coordinator._control_arbiter.invalidate_previews()

        async def connect():
            nonlocal changed
            result = await reconnect()
            if coordinator._notification_token is not token and not changed:
                changed = True
                await asyncio.create_task(newer_request())
            return result

        coordinator._ensure_connected.side_effect = connect
    uploaded = asyncio.Event()
    transmit = coordinator._client.write_gatt_char.side_effect

    async def write(uuid, packet, **kwargs):
        await transmit(uuid, packet, **kwargs)
        if packet[:2] == b"\xa3\xff":
            uploaded.set()

    coordinator._client.write_gatt_char.side_effect = write
    task = asyncio.create_task(
        engine.async_apply_saved(coordinator, item, config_entry_id="entry", updated_at="2026-11-22T00:00:00Z")
    )
    try:
        await asyncio.wait_for(uploaded.wait(), 1)
        if fault == "cancelled":
            task.cancel()
        with pytest.raises(asyncio.CancelledError if fault == "cancelled" else UploadAckTimeoutError):
            await task
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert state["on"] is (fault == "new_owner")
    assert sum(packet[:2] == b"\xa3\x00" for packet in state["packets"]) == 1
    assert not any(packet[:3] == b"\x33\x05\x04" for packet in state["packets"])


@pytest.mark.parametrize("physical", ["H6093"], indirect=True)
async def test_rejected_native_appearance_does_not_activate_or_retain_unconfirmed_state(physical):
    coordinator, state = physical
    await apply_appearance(coordinator, state["projector"])
    state["packets"].clear()
    state["fault"] = "upload_ack"
    with pytest.raises(RuntimeError, match="rejected"):
        await apply_appearance(coordinator, replace(state["projector"], brightness=18))
    assert not any(packet[:3] == b"\x33\x05\x0c" for packet in state["packets"])
    assert coordinator.projector_appearance is None


@pytest.mark.parametrize("physical", ["H6093"], indirect=True)
async def test_scalar_colour_observations_cannot_verify_native_projector_appearance(physical):
    coordinator, state = physical
    await apply_appearance(coordinator, state["projector"])
    coordinator._notify_callback(None, reply(5, [0x0C]))
    coordinator.rgb_color_source = "observed"
    coordinator._field_received_at["rgb_color"] = time.monotonic()
    prior = coordinator.capture_effect_control_state()
    assert prior.projector_appearance is not None
    assert not prior.static_colour_observed and not prior.static_rgb_known
    assert PriorControlState.from_dict(prior.to_dict()).projector_appearance == prior.projector_appearance


@pytest.mark.parametrize("physical", [("H6093", (1, 1))], indirect=True)
async def test_native_appearance_read_is_completed_when_its_profile_authority_changes(physical):
    coordinator, state = physical
    state["fault"] = "projector_read"
    transmit = coordinator._client.write_gatt_char.side_effect

    async def changing_profile(uuid, packet, **kwargs):
        await transmit(uuid, packet, **kwargs)
        if packet[:4] == b"\xac\x03\x05\x0c":
            coordinator._advance_profile_generation()

    coordinator._client.write_gatt_char.side_effect = changing_profile
    with pytest.raises(ValueError, match="authority changed"):
        await read_appearance(coordinator)
    assert coordinator._projector_reply is None and coordinator._projector_collector is None
    assert coordinator._bulk_query_incomplete


@pytest.mark.parametrize("physical", [("H6093", (1, 1)), ("H6093", (1, 2)), ("H6093", (2, 1))], indirect=True)
@pytest.mark.parametrize("mode", ["static", "scene"])
async def test_planned_release_requalifies_delivered_native_appearance_before_effect_selection(physical, mode):
    coordinator, state = physical
    coordinator._connection_pacts.clear()
    coordinator._h607c_marker_pact = coordinator.pact_type, coordinator.pact_code
    coordinator._resolve_h607c_pact(preserve_state=True)
    prior = state["projector"]
    await apply_appearance(coordinator, prior)
    light = GoveeBLELight(coordinator)
    light.async_write_ha_state = MagicMock()
    if mode == "scene":
        await light.async_turn_on(effect="Forest")
    client = coordinator._client
    client.disconnect.side_effect = lambda: setattr(client, "is_connected", False)
    await coordinator._disconnect_locked(planned_release=True)
    assert coordinator._projector_token is None
    if mode == "static":
        assert coordinator.projector_appearance == prior
    else:
        assert coordinator._pre_mode_snapshot is not None
        assert coordinator._pre_mode_snapshot.projector_appearance == prior
    client.is_connected = True
    coordinator._client = client
    client.start_notify = AsyncMock()
    await coordinator._start_notify()
    state["packets"].clear()
    await light.async_turn_on(effect="Forest" if mode == "static" else "off")
    assert any(packet[:2] == b"\xaa\xef" for packet in state["packets"])
    if mode == "static":
        assert coordinator._pre_mode_snapshot is not None
        assert coordinator._pre_mode_snapshot.projector_appearance == prior
    else:
        assert coordinator.projector_appearance == prior


@pytest.mark.parametrize("physical", ["H6093"], indirect=True)
@pytest.mark.parametrize("release", ["unexpected", "failed", "changed"])
async def test_native_appearance_does_not_survive_an_unqualified_release(physical, release):
    coordinator, state = physical
    await initialise(coordinator)
    client = coordinator._client

    async def disconnect():
        if release == "failed":
            raise BleakError("Disconnect failed")
        if release == "changed":
            coordinator._advance_profile_generation()
        client.is_connected = False

    client.disconnect.side_effect = disconnect
    await coordinator._disconnect_locked(planned_release=release != "unexpected")
    assert coordinator.projector_appearance is None
    assert coordinator._projector_profile is None


@pytest.mark.parametrize("physical", [("H6093", (1, 1)), ("H6093", (1, 2)), ("H6093", (2, 1))], indirect=True)
async def test_cold_projector_source_uses_independent_appearance_or_actionable_initialisation(physical, caplog):
    coordinator, state = physical
    if coordinator.profile.projector_control_revision == 0:
        await source_request(coordinator, "stars", False)
        assert not state["projector"].stars.enabled
    else:
        with pytest.raises(HomeAssistantError) as caught:
            await source_request(coordinator, "stars", False)
        assert caught.value.translation_key == "projector_recovery_not_ready"
        light = GoveeBLELight(coordinator)
        with pytest.raises(HomeAssistantError) as caught:
            await light.async_turn_on(effect="Forest")
        assert caught.value.translation_key == "projector_recovery_not_ready"
        assert not any(packet[0] in (0x33, 0xA3) for packet in state["packets"])
        assert not any(record.name.endswith(".entity") for record in caplog.records)


@pytest.mark.parametrize("physical", [("H6093", (1, 1)), ("H6093", (1, 2)), ("H6093", (2, 1))], indirect=True)
@pytest.mark.parametrize("mode", ["scene", "diy"])
async def test_cold_effect_selection_requires_projector_initialisation_not_scalar_rgb(physical, mode):
    coordinator, state = physical
    transmit = coordinator._client.write_gatt_char.side_effect

    async def active_effect(uuid, packet, **kwargs):
        if packet[:2] == b"\xaa\x05":
            state["packets"].append(packet)
            coordinator._notify_callback(None, reply(5, [4, 0xC7, 0x21] if mode == "scene" else [10, 254, 0]))
        else:
            await transmit(uuid, packet, **kwargs)

    coordinator._client.write_gatt_char.side_effect = active_effect
    with pytest.raises(HomeAssistantError) as caught:
        await GoveeBLELight(coordinator).async_turn_on(effect="Forest")
    assert caught.value.translation_key == "projector_recovery_not_ready"
    assert not any(packet[0] in (0x33, 0xA3) for packet in state["packets"])


@pytest.mark.parametrize("physical", [("H6093", (1, 1)), ("H6093", (1, 2)), ("H6093", (2, 1))], indirect=True)
@pytest.mark.parametrize("control", ["source", "scalar"])
@pytest.mark.parametrize("starting_mode", ["native", "scene"])
@pytest.mark.parametrize("external_change", ["none", "released", "prepared", "attempted", "activated"])
async def test_native_attribute_edits_qualify_and_guard_historical_appearance(
    physical, control, starting_mode, external_change, virtual_clock
):
    coordinator, state = physical
    await initialise(coordinator)
    if control == "source":
        await source_request(coordinator, "stars", False)
    light = GoveeBLELight(coordinator)
    light.async_write_ha_state = MagicMock()
    if starting_mode == "scene":
        await light.async_turn_on(effect="Forest")
    client = coordinator._client
    client.disconnect.side_effect = lambda: setattr(client, "is_connected", False)
    await coordinator._disconnect_locked(planned_release=True)
    client.is_connected = True
    coordinator._client = client
    client.start_notify = AsyncMock()
    await coordinator._start_notify()
    transmit = client.write_gatt_char.side_effect
    write = coordinator._async_write_packet
    interrupted = False

    async def external_static(uuid, packet, **kwargs):
        nonlocal interrupted
        if packet[:2] == b"\xaa\x05" and external_change == "released":
            state["packets"].append(packet)
            coordinator._notify_callback(None, reply(5, [0x0D, 255, 0, 0]))
        else:
            await transmit(uuid, packet, **kwargs)
            if packet[0] in (0x33, 0xA3) and external_change == "attempted" and not interrupted:
                interrupted = True
                coordinator._notify_callback(None, reply(5, [0x0D, 255, 0, 0]))
            if packet[:3] == b"\x33\x05\x0c" and external_change == "activated":
                virtual_clock.vtime = max(
                    virtual_clock.vtime, *(deadline for _, deadline in coordinator._expected_state.values())
                )
                state["native"] = False
                state["scene"] = None
                coordinator._notify_callback(None, reply(5, [0x0D, 255, 0, 0]))

    async def change_before_upload(client, packet, **kwargs):
        if packet[0] in (0x33, 0xA3) and external_change == "prepared":
            coordinator._notify_callback(None, reply(5, [0x0D, 255, 0, 0]))
        await write(client, packet, **kwargs)

    client.write_gatt_char.side_effect = external_static
    coordinator._async_write_packet = change_before_upload
    state["packets"].clear()
    operation = (
        source_request(coordinator, "stars", True)
        if control == "source"
        else set_control(coordinator, ProjectorControl.STAR_MOVEMENT_SPEED, 73)
    )
    if external_change == "none":
        await operation
        assert (
            state["projector"].stars.enabled if control == "source" else state["projector"].stars.movement_speed == 73
        )
    else:
        with pytest.raises(HomeAssistantError if external_change == "released" else ModeTransitionSupersededError):
            await operation
        if external_change in {"attempted", "activated"}:
            if external_change == "attempted":
                assert sum(packet[0] in (0x33, 0xA3) for packet in state["packets"]) == 1
                assert not any(packet[:3] == b"\x33\x05\x0c" for packet in state["packets"])
            else:
                assert sum(packet[:3] == b"\x33\x05\x0c" for packet in state["packets"]) == 1
                assert not state["native"] and coordinator.rgb_color == (255, 0, 0)
            assert not coordinator.projector_mode_active and coordinator.projector_appearance is None
        else:
            assert not any(packet[0] in (0x33, 0xA3) for packet in state["packets"])
    assert any(packet[:2] == b"\xaa\x05" for packet in state["packets"])


@pytest.mark.parametrize("physical", ["H6093"], indirect=True)
async def test_cached_pact_does_not_authorise_native_writes_but_keeps_bootstrap_power_available(physical):
    coordinator, state = physical
    coordinator._connection_pacts.clear()
    coordinator._confirmed_identity_fields.clear()
    coordinator._h607c_marker_pact = None
    coordinator._subscription_advertised_pact = None
    coordinator._h607c_advertisement_observations = {"cached": (coordinator._notify_started_monotonic - 1, {(2, 1)})}
    coordinator._h607c_advertised_pacts = {(2, 1)}
    with pytest.raises(HomeAssistantError) as caught:
        qualified_profile(coordinator)
    assert caught.value.translation_key == "identity_not_ready"
    assert coordinator.profile.projector_control_revision == 1
    await coordinator.send_command(build_power(True, "H6093"))
    assert state["on"] and state["speaker"]
    assert not coordinator.identity_fields_confirmed(frozenset({"pact"}))


@pytest.mark.parametrize("physical", ["H6093"], indirect=True)
async def test_individual_projector_pattern_enable_keeps_its_effectively_off_sibling_off(physical):
    coordinator, state = physical
    await initialise(coordinator)
    await source_request(coordinator, "aurora", False)
    await source_request(coordinator, "coarse_aurora", True)
    value = state["projector"]
    assert value.enabled and value.coarse_enabled
    assert not value.fine_enabled and value.fine is not None


@pytest.mark.parametrize("physical", [("H6093", (1, 2)), ("H6093", (2, 1))], indirect=True)
@pytest.mark.parametrize("unified", [False, True])
async def test_projector_source_power_composes_effective_child_output(physical, unified):
    coordinator, state = physical
    await initialise(coordinator)
    if unified:
        await apply_appearance(coordinator, replace(state["projector"], fine=None))
    aurora = GoveeBLESourceLight(coordinator, "aurora")
    coarse = GoveeBLESourceLight(coordinator, "coarse_aurora")
    fine = GoveeBLESourceLight(coordinator, "fine_aurora")
    await fine.async_turn_off()
    assert state["projector"].fine is not None and not state["projector"].fine_enabled
    assert coarse.is_on and not fine.is_on and aurora.is_on
    await coarse.async_turn_off()
    assert not aurora.is_on
    await aurora.async_turn_on()
    assert aurora.is_on and coarse.is_on and fine.is_on
    assert state["projector"].coarse_enabled and state["projector"].fine_enabled
    await fine.async_turn_off()
    await aurora.async_turn_off()
    await aurora.async_turn_on()
    assert coarse.is_on and not fine.is_on


@pytest.mark.parametrize("physical", ["H6093"], indirect=True)
async def test_planned_projector_release_retains_all_appearance_presentation_not_authority(physical):
    from custom_components.ha_govee_led_ble.projector import ProjectorControl
    from custom_components.ha_govee_led_ble.projector_runtime import control_value

    coordinator, state = physical
    await apply_appearance(coordinator, state["projector"])
    before = {control: control_value(coordinator, control) for control in ProjectorControl}
    coordinator._present = True
    coordinator._clear_client_state(coordinator._client, preserve_static_baseline=True)
    assert coordinator.available
    assert {control: control_value(coordinator, control) for control in ProjectorControl} == before
    assert not coordinator.projector_appearance_observed
    with pytest.raises(HomeAssistantError):
        qualified_profile(coordinator)
    coordinator._advance_profile_generation()
    assert all(control_value(coordinator, control) is None for control in ProjectorControl)


@pytest.mark.parametrize("physical", [("H6093", (1, 1)), ("H6093", (1, 2)), ("H6093", (2, 1))], indirect=True)
async def test_local_audio_and_settings_use_verified_controls_without_appearance(physical):
    from custom_components.ha_govee_led_ble.number import GoveeBLELocalVolume
    from custom_components.ha_govee_led_ble.select import GoveeBLELocalSoundSelect
    from custom_components.ha_govee_led_ble.switch import GoveeBLEControlSwitch
    from custom_components.ha_govee_led_ble.switch import async_setup_entry as setup_switches

    coordinator, state = physical
    entry = MagicMock(runtime_data=coordinator)
    sound = GoveeBLELocalSoundSelect(entry)
    volume = GoveeBLELocalVolume(entry)
    add = MagicMock()
    await setup_switches(coordinator.hass, entry, add)
    switches = {entity.translation_key: entity for call in add.call_args_list for entity in call.args[0]}
    entry.async_on_unload.call_args.args[0]()
    playback, mode = switches["local_sound_playback"], switches["local_sound_enabled"]
    assert playback.unique_id == "aabbccddeeff_local_sound_enabled"
    assert mode.unique_id != playback.unique_id
    light_before = state["projector"]
    await sound.async_select_option("train")
    assert sound.current_option == "train" and state["sound_code"] == 18 and playback.is_on
    assert frame("33300601") in state["packets"]
    assert frame("33310112") in state["packets"]
    await volume.async_set_native_value(0)
    assert volume.native_value == 0 and state["volume"] == 0
    assert frame("333200") in state["packets"]
    await playback.async_turn_off()
    assert not playback.is_on and not state["speaker"]
    assert mode.is_on
    assert state["sound_enabled"] and state["sound_code"] == 18
    assert frame("33310012") in state["packets"]
    await playback.async_turn_on()
    assert playback.is_on and state["speaker"] and state["sound_code"] == 18
    await mode.async_turn_off()
    assert not mode.is_on and not playback.is_on
    await playback.async_turn_on()
    assert mode.is_on and playback.is_on and state["sound_code"] == 18
    for setting in ("quiet_start", "pairing_prompt"):
        entity = GoveeBLEControlSwitch(entry, setting)
        await entity.async_turn_on()
        assert entity.is_on and state["settings"][setting]
        await entity.async_turn_off()
        assert not entity.is_on and not state["settings"][setting]
    assert state["projector"] == light_before and state["on"]
    assert coordinator.projector_appearance is None
    assert not any(packet[0] == 0xA3 for packet in state["packets"])
    state["fault"] = "setting"
    with pytest.raises(HomeAssistantError):
        await volume.async_set_native_value(100)


@pytest.mark.parametrize("physical", [("H6093", (1, 1)), ("H6093", (1, 2)), ("H6093", (2, 1))], indirect=True)
async def test_power_notification_cannot_confirm_a_suppressed_setting_write(physical, virtual_clock):
    coordinator, state = physical
    transmit = coordinator._client.write_gatt_char.side_effect
    state["fault"] = "setting"

    async def partial_only(uuid, packet, **kwargs):
        if packet[:2] == b"\xaa\x34":
            coordinator._notify_callback(None, frame("ee30030101"))
        else:
            await transmit(uuid, packet, **kwargs)

    coordinator._client.write_gatt_char.side_effect = partial_only
    with pytest.raises(ValueError, match="fresh setting readback"):
        await coordinator.async_set_boolean_control("pairing_prompt", True)
    assert not state["settings"]["pairing_prompt"]
    assert coordinator.boolean_control_state.get("pairing_prompt") is not True


@pytest.mark.parametrize("physical", ["H6093"], indirect=True)
async def test_local_sound_sequence_rejects_invalid_input_and_replacement_subscription(physical):
    coordinator, state = physical
    for control, value in (("local_sound", 0), ("local_sound", 19), ("local_volume", 101), ("local_volume", True)):
        with pytest.raises(ValueError):
            await coordinator.async_set_local_audio(control, value)
    with pytest.raises(ValueError, match="boolean"):
        await coordinator.async_set_local_playback(1)
    assert state["packets"] == []
    transmit = coordinator._client.write_gatt_char.side_effect

    async def replace_subscription(uuid, packet, **kwargs):
        await transmit(uuid, packet, **kwargs)
        if packet[:4] == b"\x33\x30\x06\x01":
            coordinator._notification_token = object()

    coordinator._client.write_gatt_char.side_effect = replace_subscription
    with pytest.raises(ValueError, match="sequence authority changed"):
        await coordinator.async_set_local_audio("local_sound", 18)
    assert not any(packet[:2] == b"\x33\x31" for packet in state["packets"])
    assert coordinator.local_sound is None
    assert coordinator.boolean_control_state.get("local_sound_enabled") is None


@pytest.mark.parametrize("physical", ["H6093"], indirect=True)
async def test_playback_start_rejects_a_different_reported_track_without_replay(physical):
    coordinator, state = physical
    await coordinator.async_set_local_audio("local_sound", 18)
    state["fault"] = "sound_selection"
    state["packets"].clear()
    with pytest.raises(ValueError, match="selected local sound"):
        await coordinator.async_set_local_playback(True)
    assert state["speaker"] and state["sound_code"] == 1
    assert state["packets"].count(frame("33310112")) == 1


@pytest.mark.parametrize("physical", ["H6093"], indirect=True)
@pytest.mark.parametrize("change", ["subscription", "track", "disabled"])
async def test_pause_revalidates_qualified_track_before_mutation(physical, monkeypatch, change):
    coordinator, state = physical
    await coordinator.async_set_local_audio("local_sound", 18)
    state["packets"].clear()
    transmit = coordinator._client.write_gatt_char.side_effect
    changed = asyncio.Event()
    queried = False

    def update():
        if change == "subscription":
            coordinator._notification_token = object()
        else:
            state["sound_code"] = 1 if change == "track" else 18
            if change == "disabled":
                state["sound_enabled"] = state["speaker"] = False
            coordinator._notify_callback(
                None,
                reply(
                    0x34,
                    [
                        0x40 | (4 if state["sound_enabled"] else 0),
                        state["brightness"],
                        128 if state["speaker"] else 0,
                        state["sound_code"],
                        state["volume"],
                    ],
                ),
            )
        changed.set()

    async def write(uuid, packet, **kwargs):
        nonlocal queried
        await transmit(uuid, packet, **kwargs)
        if packet[:2] == b"\xaa\x34" and not queried:
            queried = True
            asyncio.get_running_loop().call_soon(update)

    async def wait():
        if queried:
            await changed.wait()

    coordinator._client.write_gatt_char.side_effect = write
    monkeypatch.setattr(coordinator._reply_gate, "wait", wait)
    with pytest.raises(ValueError, match="changed"):
        await coordinator.async_set_local_playback(False)
    assert not any(packet[0] == 0x33 for packet in state["packets"])
    assert state["sound_code"] == (1 if change == "track" else 18)


@pytest.mark.parametrize("physical", ["H6093"], indirect=True)
async def test_pause_rejects_global_disablement_without_replay(physical):
    coordinator, state = physical
    await coordinator.async_set_local_audio("local_sound", 18)
    state["fault"] = "pause_disables"
    state["packets"].clear()
    with pytest.raises(ValueError, match="confirm local sound pause"):
        await coordinator.async_set_local_playback(False)
    assert not state["speaker"] and not state["sound_enabled"]
    assert state["packets"].count(frame("33310012")) == 1


@pytest.mark.parametrize("physical", ["H6093"], indirect=True)
async def test_pause_does_not_invent_an_unknown_playing_track(physical, monkeypatch):
    coordinator, state = physical
    state.update(sound_enabled=True, speaker=True, sound_code=0)
    supersede = AsyncMock()
    monkeypatch.setattr(coordinator, "_async_supersede_effect_preview", supersede)
    foreground = coordinator._control_arbiter.foreground_generation
    with pytest.raises(ValueError, match="unknown local sound"):
        await coordinator.async_set_local_playback(False)
    assert not any(packet[0] == 0x33 for packet in state["packets"])
    supersede.assert_not_awaited()
    assert coordinator._control_arbiter.foreground_generation == foreground


@pytest.mark.parametrize("physical", [("H6093", (1, 1)), ("H6093", (1, 2)), ("H6093", (2, 1))], indirect=True)
async def test_dreamview_laser_setting_requires_fresh_exact_revision(physical):
    coordinator, state = physical
    permitted = (coordinator.pact_type, coordinator.pact_code) == (2, 1)
    packet = frame("33300701")
    coordinator._connection_pacts.clear()
    coordinator._confirmed_identity_fields.clear()
    with pytest.raises(HomeAssistantError):
        coordinator._validate_authorized_packet(packet)
    state["packets"].clear()
    if permitted:
        await coordinator.async_set_boolean_control("dreamview_laser", True)
        assert state["settings"]["dreamview_laser"]
        assert any(value[:2] == b"\xaa\xef" for value in state["packets"])
    else:
        with pytest.raises(ValueError):
            await coordinator.async_set_boolean_control("dreamview_laser", True)
        assert not any(value[0] == 0x33 for value in state["packets"])


@pytest.mark.parametrize("physical", ["H617A", "H1771", "H1AB2"], indirect=True)
async def test_public_effect_off_restores_non_source_segment_layout(hass, physical, virtual_clock):
    coordinator, state = physical
    light = GoveeBLELight(coordinator)
    light._attr_device_info = None
    light.async_added_to_hass = AsyncMock()
    assert await async_setup_component(hass, "light", {})
    await hass.data["light"].async_add_entities([light])
    if coordinator.model in {"H1771", "H1AB2"}:
        # A known RGB write takes precedence over an identical Kelvin companion.
        await light.async_set_segment_color([3], state["colours"][1])
    expected_colours, expected_levels = list(state["colours"]), list(state["relative"])
    effect = "Aurora" if coordinator.model == "H1AB2" else "Rainbow" if coordinator.model == "H1771" else "Sunrise"
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
    if coordinator.model == "H1AB2":
        assert state["colour_modes"] == ["rgb", "kelvin", "rgb", *(["kelvin"] * 7)]


@pytest.mark.parametrize("physical", ["H1771"], indirect=True)
@pytest.mark.parametrize(
    ("bulk_selector", "result"),
    [
        (0x15, "static"),
        (0x15, "mixed"),
        (0x15, "unknown"),
        (0x15, "missing_mode"),
        (0x15, "missing_layout"),
        (0x15, "saved_missing_layout"),
        (0x15, "saved_layout"),
        (0x15, "scene"),
        (0x04, "static"),
    ],
)
async def test_scoped_settings_do_not_authorise_effects_without_a_qualified_layout(
    physical, virtual_clock, bulk_selector, result
):
    from tests.test_h60a_protocol import bulk_frames

    coord, state = physical
    light = GoveeBLELight(coord)
    light.async_write_ha_state = MagicMock()
    if result == "mixed":
        await light.async_set_segment_color([3], state["colours"][1])
        virtual_clock.vtime = max(virtual_clock.vtime, coord._expected_state["color_mode"][1])
    else:
        state.update(colours=[(255, 255, 255)] * 4, relative=[1, 15, 20, 1], brightness=100)
        if result == "saved_layout":
            state["colours"] = [(127, 0, 0)] * 4
    colours, levels = tuple(state["colours"]), tuple(state["relative"])
    sources, gradual = list(state["sources"]), state["gradual"]
    send = coord._client.write_gatt_char.side_effect
    settings_read = False
    mode_reads_after_settings = 0
    requested_pages = 0

    async def transmit(uuid, packet, **kwargs):
        nonlocal settings_read, mode_reads_after_settings, requested_pages
        if packet[:4] == b"\xac\x03\x01\x36":
            if settings_read and "color_mode" in coord._expected_state:
                # The restored selector's optimistic guard may expire before source verification.
                virtual_clock.vtime = max(virtual_clock.vtime, coord._expected_state["color_mode"][1])
            settings_read = True
            mode = "050415010000" if bulk_selector == 0x15 else "0503045b00"
            first, second = state["sources"]
            flags = int(state["on"]) | (int(first) << 1) | (int(second) << 2)
            body = bytes((0x36, 1, flags)) + bytes.fromhex(mode)
            if result in {"missing_layout", "saved_missing_layout", "saved_layout"}:
                body += bytes((0xA5, 17, 1, 1, 255, 255, 255, 15, 255, 255, 255, 20, 255, 255, 255, 1, 255, 255, 255))
            for response in bulk_frames(body):
                coord._notify_callback(None, bytearray(response))
        elif packet[:2] == b"\xaa\x05" and settings_read and not state["scene"]:
            mode_reads_after_settings += 1
            if result.startswith("saved_"):
                coord._notify_callback(None, reply(0xA5, [1, *([15, 255, 255, 255] * 4)]))
            if result != "missing_mode":
                report = {"unknown": [0x7F], "scene": [4, 91, 0]}.get(result, [0x15, 1, 0, 0])
                coord._notify_callback(None, reply(5, report))
        else:
            if packet[:2] == b"\xaa\xa5":
                requested_pages += 1
            if result not in {"missing_layout", "saved_missing_layout"} or packet[:2] != b"\xaa\xa5":
                await send(uuid, packet, **kwargs)

    coord._client.write_gatt_char.side_effect = transmit
    if result.startswith("saved_"):
        async with coord.async_mode_transition() as transition:
            assert await async_prepare_effect_control_state(coord, require_restorable_static=False)
            if result == "saved_missing_layout":
                with pytest.raises(HomeAssistantError):
                    await coord.async_admit_effect_selection()
            else:
                await coord.async_admit_effect_selection()
                assert transition.snapshot is not None and transition.snapshot.segment_colors == colours
        assert requested_pages == 1 and coord.control_write_attempts == 0
        return
    if bulk_selector == 0x15 and result in {"static", "mixed"}:
        await light.async_turn_on(effect="Rainbow")
        target = coord._pre_mode_snapshot
        assert target is not None
        assert target.segment_colors == colours
        assert target.segment_brightness == levels
        assert state["scene"] is not None
        assert mode_reads_after_settings == requested_pages == 1
        await light.async_turn_on(effect="off")
        assert state["scene"] is None
        assert tuple(state["colours"]) == colours
        assert tuple(state["relative"]) == levels
        assert state["sources"] == sources and state["gradual"] == gradual
        if result == "mixed":
            assert state["colour_modes"] == ["rgb", "kelvin", "rgb", "kelvin"]
    else:
        with pytest.raises(HomeAssistantError):
            await light.async_turn_on(effect="Rainbow")
        assert coord.control_write_attempts == 0 and state["scene"] is None
        assert mode_reads_after_settings == (1 if bulk_selector == 0x15 else 0)
    if bulk_selector == 0x04 or result == "scene":
        assert coord.scene_code == 91


@pytest.mark.parametrize("physical", ["H1771"], indirect=True)
async def test_settings_hint_does_not_invalidate_later_ordinary_mode(physical, virtual_clock):
    coord, state = physical
    send = coord._client.write_gatt_char.side_effect

    async def transmit(uuid, packet, **kwargs):
        if packet[:4] == b"\xac\x03\x01\xa3":
            coord._notify_callback(None, bytearray(frame(f"ac000100090300a301{int(state['gradual']):02x}050415010000")))
            coord._notify_callback(None, reply(5, [4, 91, 0]))
        else:
            await send(uuid, packet, **kwargs)

    coord._client.write_gatt_char.side_effect = transmit
    await coord.async_set_boolean_control("gradual", False)
    assert not state["gradual"] and coord.scene_code == 91
    assert coord.source_field_fresh("color_mode")


@pytest.mark.parametrize("physical", ["H1771"], indirect=True)
@pytest.mark.parametrize("mode_reply", [[0x15, 1, 0, 0], [0x7F], None])
async def test_standalone_settings_hint_qualifies_the_next_segment_write(physical, virtual_clock, mode_reply):
    coord, state = physical
    light = GoveeBLELight(coord)
    light.async_write_ha_state = MagicMock()
    send = coord._client.write_gatt_char.side_effect
    reads = []

    async def transmit(uuid, packet, **kwargs):
        if packet[:4] == b"\xac\x03\x01\xa3":
            coord._notify_callback(None, bytearray(frame(f"ac000100090300a301{int(state['gradual']):02x}050415010000")))
        elif packet[:2] == b"\xaa\x05":
            reads.append("mode")
            if mode_reply is not None:
                coord._notify_callback(None, reply(5, mode_reply))
        else:
            if packet[:2] == b"\xaa\xa5":
                reads.append("layout")
            await send(uuid, packet, **kwargs)

    coord._client.write_gatt_char.side_effect = transmit
    await coord.async_set_boolean_control("gradual", False)
    assert not state["gradual"] and not reads
    attempts = coord.control_write_attempts
    if mode_reply == [0x15, 1, 0, 0]:
        await light.async_set_segment_color_temp([1], 3000)
        assert reads[:2] == ["mode", "layout"]
        assert state["colour_modes"] == ["kelvin", "rgb", "rgb", "rgb"]
    else:
        with pytest.raises(HomeAssistantError):
            await light.async_set_segment_color_temp([1], 3000)
        assert reads == ["mode"] and coord.control_write_attempts == attempts


async def test_saved_effect_preparation_reads_each_segment_page_once(physical, virtual_clock):
    coord, state = physical
    async with coord.async_mode_transition():
        assert await async_prepare_effect_control_state(coord, require_restorable_static=False)
        await coord.async_admit_effect_selection()

    assert [packet[2] for packet in state["packets"] if packet[:2] == b"\xaa\xa5"] == [1, 2, 3, 4, 5]


@pytest.mark.parametrize("physical", ["H1771"], indirect=True)
async def test_optional_bulk_timeout_does_not_prevent_independent_page(physical, virtual_clock):
    coord, _ = physical
    transmit = coord._client.write_gatt_char.side_effect

    async def withhold_optional_settings(uuid, packet, **kwargs):
        if packet[:2] != b"\xac\x03":
            await transmit(uuid, packet, **kwargs)

    coord._client.write_gatt_char.side_effect = withhold_optional_settings
    assert await coord.refresh_state(
        RefreshRequest(refresh_all=True, required_domains=coord.profile.setup_required_read_domains)
    )
    assert coord.source_field_fresh("segment_colors")


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
    ("physical", "initially_on", "release"),
    [
        ("H617A", False, "idle"),
        ("H617A", True, "idle"),
        ("H617A", True, "poll"),
        ("H617A", True, "poll_failed"),
        ("H617A", True, "unexpected"),
        ("H617A", True, "manual"),
        ("H617A", True, "failed"),
        ("H617A", True, "cancelled"),
        ("H617A", True, "profile_changed"),
        ("H617A", True, "resubscribed"),
        ("H1AB2", False, "idle"),
        ("H1AB2", True, "poll"),
    ],
    indirect=["physical"],
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
            if coordinator.profile.segment_count_ic_divisor is not None:
                await coordinator._async_write_packet(client, frame("aa40"))
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


@pytest.mark.parametrize("physical", ["H617A", "H1AB2"], indirect=True)
@pytest.mark.parametrize("fault", ["missing_mode", "missing_power", "missing_brightness", "partial", "stale"])
async def test_failed_fresh_preflight_never_captures_defaults_or_writes(physical, fault):
    coordinator, state = physical
    state["fault"] = fault
    repository = EffectDeploymentRepository(InMemoryVersionedDocumentStore())
    await repository.async_load()
    with pytest.raises((RuntimeError, HomeAssistantError)):
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
