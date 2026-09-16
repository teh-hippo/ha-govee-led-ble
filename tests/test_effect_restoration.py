"""Fresh physical-state recovery through the real coordinator and deployment path."""

from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode
from custom_components.ha_govee_led_ble.effect_deployments import (
    DeploymentPhase,
    EffectDeploymentRepository,
    PriorControlState,
)
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem, SingleEffect
from custom_components.ha_govee_led_ble.effect_runtime import EffectDeploymentEngine
from custom_components.ha_govee_led_ble.generated_protocol_adapter import build_power
from custom_components.ha_govee_led_ble.light_commands import parse_static_write
from custom_components.ha_govee_led_ble.music_commands import edit_music_body
from custom_components.ha_govee_led_ble.music_semantics import music_variant
from custom_components.ha_govee_led_ble.transport import fragment_a3, xor_checksum
from tests.storage_test_double import InMemoryVersionedDocumentStore


def reply(domain, body):
    payload = bytes([0xAA, domain, *body]).ljust(19, b"\0")
    return bytearray(payload + bytes([xor_checksum(payload)]))


@pytest.fixture
def physical(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617A", configuration_url="test")
    state = {
        "on": True,
        "brightness": 37,
        "colours": [(10, 20, 30)] * 14 + [(90, 80, 70)],
        "relative": [30] * 14 + [70],
        "fault": None,
        "packets": [],
    }

    async def transmit(_uuid, packet, **_kwargs):
        state["packets"].append(packet)
        fault = state["fault"]
        if packet[0] == 0x33:
            if packet[1] == 1:
                state["on"] = bool(packet[2])
            elif packet[1] == 4 and fault != "brightness":
                state["brightness"] = packet[2]
            static = parse_static_write(packet)
            if static is not None:
                for index in range(15):
                    if static.segment_mask & (1 << index):
                        if static.rgb is not None and fault != "colour":
                            state["colours"][index] = static.rgb
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
    monkeypatch.setattr(coordinator, "refresh_state", lambda **kwargs: refresh(timeout=0.02, **kwargs))
    monkeypatch.setattr(coordinator, "async_refresh_segments", lambda: segments(timeout=0.02))
    return coordinator, state


@pytest.mark.parametrize("on", [True, False])
@pytest.mark.parametrize("fault", [None, "brightness", "colour", "relative", "partial", "stale", "reordered", "mode"])
async def test_failed_deployment_restores_fresh_mixed_layout_and_persists_truth(physical, monkeypatch, on, fault):
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

    async def failed_upload(*_args, **_kwargs):
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
            kwargs["packet_write_guard"](index)
            for key, value in values.items():
                setattr(coordinator, key, value)

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
    coordinator.profile = replace(coordinator.profile, segment_count=0)
    prior = PriorControlState("colour", True, 37, (1, 2, 3))

    async def send(packet):
        if parse_static_write(packet) is not None:
            coordinator.rgb_color = (8, 9, 10)
            coordinator.brightness_pct = 12
            coordinator.is_on = False
            coordinator.color_mode = ParsedMode.UNKNOWN

    monkeypatch.setattr(coordinator, "send_command", send)
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
    send = coordinator.send_command

    async def fail_colour(packet, **kwargs):
        if parse_static_write(packet) is not None:
            raise RuntimeError("colour write failed")
        await send(packet, **kwargs)

    monkeypatch.setattr(coordinator, "send_command", fail_colour)
    with pytest.raises(RuntimeError, match="colour write failed"):
        await coordinator.async_restore_effect_control_state(prior, overwritten_diy_code=None)
    assert state["on"] is False
