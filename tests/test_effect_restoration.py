"""Fresh physical-state recovery through the real coordinator and deployment path."""

import time
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ha_govee_led_ble.const import device_profile, get_profile
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
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
    build_diy_activation,
    build_power,
    build_scene_activation,
    require_profile_packet,
)
from custom_components.ha_govee_led_ble.light_commands import parse_static_write
from custom_components.ha_govee_led_ble.music_commands import edit_music_body
from custom_components.ha_govee_led_ble.music_semantics import music_variant
from custom_components.ha_govee_led_ble.transport import fragment_a3, xor_checksum
from tests.storage_test_double import InMemoryVersionedDocumentStore


def reply(domain, body):
    payload = bytes([0xAA, domain, *body]).ljust(19, b"\0")
    return bytearray(payload + bytes([xor_checksum(payload)]))


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
    state = {
        "on": True,
        "brightness": 37,
        "colours": [(10, 20, 30)] * 14 + [(90, 80, 70)],
        "relative": [30] * 14 + [70],
        "fault": None,
        "packets": [],
        "colour_modes": ["rgb"] * 15,
    }

    async def transmit(_uuid, packet, **_kwargs):
        state["packets"].append(packet)
        fault = state["fault"]
        if packet[0] == 0x33:
            if packet[1] == 1:
                state["on"] = bool(packet[2])
            elif packet[1] == 4 and fault != "brightness":
                state["brightness"] = packet[2]
            static = parse_static_write(packet, profile=coordinator.profile)
            if static is not None:
                for index in range(15):
                    if static.segment_mask & (1 << index):
                        if static.rgb is not None and fault != "colour":
                            state["colours"][index] = static.rgb
                            state["colour_modes"][index] = "rgb"
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
                    None, reply(5, [0x13, 0x04, 50, 0, 0, 0, 0, 0] if fault == "mode" else [0x15, 0])
                )
            elif domain == 0x0F and fault != "missing_count":
                coordinator._notify_callback(None, reply(0x0F, [1]))
            elif domain == 0x41:
                coordinator._notify_callback(None, reply(0x41, [1]))
            elif domain == 0xA5 and packet[2] == 5:
                pages = [5, 2, 4, 1, 3] if fault == "reordered" else range(1, 6)
                for page in pages:
                    if fault == "partial" and page == 3:
                        continue
                    body = [page]
                    for index in range((page - 1) * 3, page * 3):
                        body.extend([state["relative"][index], *state["colours"][index]])
                    coordinator._notify_callback(None, reply(0xA5, body))

    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=transmit), disconnect=AsyncMock())
    coordinator._client = client
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(coordinator, "_renew_foreground_lease", MagicMock())
    refresh = coordinator.refresh_state
    segments = coordinator.async_refresh_segments
    monkeypatch.setattr(coordinator, "refresh_state", lambda request: refresh(replace(request, timeout=0.02)))
    monkeypatch.setattr(coordinator, "async_refresh_segments", lambda: segments(timeout=0.02))
    return coordinator, state


@pytest.mark.parametrize("physical", ["H7020"], indirect=True)
async def test_ambiguous_bulb_readback_never_repaints_white_as_rgb_during_rollback(physical, virtual_clock):
    coordinator, state = physical
    state["colours"] = [(255, 213, 161)] + [(255, 0, 0)] * 14
    state["colour_modes"][0] = "white"
    assert await coordinator.refresh_state(RefreshRequest(refresh_all=True))
    prior = coordinator.capture_effect_control_state()
    assert prior.color_temp_kelvin is None and prior.segment_colors == tuple(state["colours"])
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
    coordinator.profile = replace(coordinator.profile, segment_count=0, whole_device_mask_override=0x7FFF)
    prior = PriorControlState("colour", True, 37, (1, 2, 3))

    async def send(packets, *, write_guard, **_kwargs):
        for packet in packets:
            write_guard()
            if parse_static_write(packet) is not None:
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
