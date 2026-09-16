"""Complete-body retention and the parent-owned correlated-ACK sequence contract."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.ha_govee_led_ble.const import get_profile
from custom_components.ha_govee_led_ble.control_arbiter import ControlIntent
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.effect_compiler import compile_music_profile, validate_compiled_geometry
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem, MusicProfile
from custom_components.ha_govee_led_ble.music_commands import (
    edit_music_body,
    music_body_style,
    prepare_music_body_writes,
    prepare_music_profile_writes,
    validate_music_body,
)
from custom_components.ha_govee_led_ble.music_semantics import music_variant
from custom_components.ha_govee_led_ble.transport import fragment_a3
from tests.test_h617a_music import frame

BODY = bytes.fromhex("3302010203040506aabbcc196104050708")


@pytest.mark.parametrize("model", ["H617A", "H6099", "H617E"])
def test_original_body_replay_is_verbatim_not_an_authored_template(model):
    profile = get_profile(model)
    writes = prepare_music_body_writes(model, "hopping", 42, BODY, profile=profile)
    upload = writes[1:-1] if profile.music_upload_before_selector else writes[2:]
    assert [packet for packet, _ in upload] == fragment_a3(0x41, BODY)
    assert upload[0][1]["_music_body"] is None
    assert upload[-1][1]["_music_body"] == ("hopping", BODY)
    assert upload[-1][1]["music_hopping_brightness"] == 25
    if model != "H617E":
        assert upload[-1][1]["music_hopping_background"] == 0xAABBCC


@pytest.mark.parametrize("body", [b"", b"\x33", b"\x34\x00", b"\x33" * 5000, "3300", BODY[:-1]])
def test_invalid_restored_body_rejected(body):
    with pytest.raises(ValueError):
        prepare_music_body_writes("H617A", "hopping", 42, body)


def test_edit_known_body_preserves_every_unrequested_companion():
    profile = get_profile("H617A")
    changed = edit_music_body(BODY, "hopping", {"relative_brightness": 17}, profile=profile)
    assert changed == bytes.fromhex("3302010203040506aabbcc116104050708")
    assert edit_music_body(BODY, "hopping", {}, profile=profile) == BODY
    odd_style = bytes.fromhex("30010102030b51")
    assert edit_music_body(odd_style, "bloom", {}, profile=profile) == odd_style
    assert validate_music_body(changed, "hopping", profile=profile).tail.speed == 97


@pytest.mark.parametrize("model", ["H617A", "H617E", "H6099"])
@pytest.mark.parametrize("calm,tail", [(None, "0b51"), (False, "0a50"), (True, "0a14")])
def test_retained_bloom_explicit_style_sets_both_speeds(model, calm, tail):
    # APK RgbMusicZhanFang.java:17-24 sets both speeds for either explicit style.
    profile = get_profile(model)
    original = bytes.fromhex("30020102030405060b51")
    edited = edit_music_body(original, "bloom", {}, profile=profile, calm=calm)
    assert edited == bytes.fromhex("3002010203040506" + tail)
    assert music_body_style(edited, "bloom", profile=profile) is calm
    if calm is None:
        assert edited == original


@pytest.mark.parametrize(
    "mode,parameters,dependent",
    [
        ("piano_keys", {}, True),
        ("separation", {}, True),
        ("hopping", {}, False),
        ("bloom", {}, False),
    ],
)
def test_compiled_defaults_count_as_actual_geometry_parameters(mode, parameters, dependent):
    profile = replace(get_profile("H617A"), physical_ic_count=60)
    compiled = compile_music_profile(
        LibraryItem.new("Music", MusicProfile("H617A", mode, 42, parameters=parameters)), "H617A", profile=profile
    )
    if dependent:
        with pytest.raises(ValueError, match="Physical IC"):
            validate_compiled_geometry(compiled, replace(profile, physical_ic_count=None))
    else:
        validate_compiled_geometry(compiled, replace(profile, physical_ic_count=None))


def test_h617e_metadata_does_not_inherit_new_controls_or_geometry_policy():
    profile = get_profile("H617E")
    assert not profile.music_upload_before_selector and not profile.music_requires_upload_ack
    assert [variant.mode_code for variant in profile.music_variants] == [3, 48, 49, 50, 51, 52, 53, 55]
    for variant in profile.music_variants:
        assert variant.palette_bounds is None
        assert not any(spec.requires_physical_ic_count for spec in variant.parameters)
    piano = music_variant(replace(profile, physical_ic_count=60), 52)
    assert [(spec.profile_key, spec.min_value, spec.max_value) for spec in piano.parameters] == [("key_count", 8, 15)]
    assert [spec.profile_key for spec in music_variant(profile, 51).parameters] == ["relative_brightness"]


@pytest.mark.parametrize("preview", [False, True])
@pytest.mark.parametrize("failure", [None, 0, 1, 2, 3, "ack", "cancel", "notification"])
async def test_body_known_only_after_complete_sequence_and_positive_ack(hass, monkeypatch, preview, failure):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617A", configuration_url=None)
    coordinator.music_mode = "hopping"
    old = music_variant(coordinator.profile, 51).template
    coordinator._music_body = ("hopping", old)
    writes = prepare_music_body_writes("H617A", "hopping", 42, BODY)
    events = []
    preview_writer = AsyncMock() if preview else None

    async def sequence(
        packets, *, packet_state_values, packet_write_guard, require_upload_ack, upload_ack_index, writer=None, **kwargs
    ):
        assert require_upload_ack and upload_ack_index == len(writes) - 2
        assert writer is preview_writer
        for index, packet in enumerate(packets):
            if failure == 0 and index == 0:
                raise ValueError("before attempt")
            packet_write_guard(index)
            for key, value in packet_state_values[index].items():
                setattr(coordinator, key, value)
            events.append(packet)
            if index >= 1:
                assert coordinator.music_body is None
            if failure == index:
                raise ValueError("attempt failed")
            if index == upload_ack_index:
                if failure == "ack":
                    raise TimeoutError("positive ACK missing")
                if failure == "cancel":
                    raise asyncio.CancelledError
                events.append("positive ACK")
            if index == len(packets) - 1 and failure == "notification":
                coordinator._music_body = None

    monkeypatch.setattr(coordinator, "async_write_effect_sequence", sequence)
    if failure not in (None, "notification"):
        with pytest.raises((ValueError, TimeoutError, asyncio.CancelledError)):
            await coordinator.async_write_music_sequence(
                writes, mode_code=51, physical_ic_count=None, intent=ControlIntent.USER, writer=preview_writer
            )
        assert coordinator.music_body == (old if failure == 0 else None)
    else:
        await coordinator.async_write_music_sequence(
            writes, mode_code=51, physical_ic_count=None, intent=ControlIntent.USER, writer=preview_writer
        )
        assert coordinator.music_body == (BODY if failure is None else None)
        assert events[-2] == "positive ACK"
    assert "music_body" not in coordinator._field_revisions


async def test_lowlevel_edit_requires_body_and_retains_unknown_companions(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617A", configuration_url=None)
    coordinator.music_mode = "hopping"
    writer = AsyncMock()
    with pytest.raises(ValueError, match="unknown music body"):
        await coordinator.async_apply_music_params(51, parameters={"relative_brightness": 17}, writer=writer)
    writer.assert_not_awaited()
    coordinator._music_body = ("hopping", BODY)
    sequence = AsyncMock()
    monkeypatch.setattr(coordinator, "async_write_music_sequence", sequence)
    await coordinator.async_apply_music_params(51, parameters={"relative_brightness": 17}, writer=writer)
    writes = sequence.call_args.args[0]
    assert [packet for packet, _ in writes] == fragment_a3(0x41, bytes.fromhex("3302010203040506aabbcc116104050708"))
    assert writes[-1][1]["music_hopping_brightness"] == 17


async def test_per_parameter_guard_runs_before_physical_write(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617A", configuration_url=None)
    profile = replace(coordinator.profile, physical_ic_count=60)
    writes = prepare_music_profile_writes("H617A", "piano_keys", 42, None, False, {}, profile=profile)

    async def sequence(*args, packet_write_guard, **kwargs):
        packet_write_guard(0)
        pytest.fail("guard allowed stale geometry")

    monkeypatch.setattr(coordinator, "async_write_effect_sequence", sequence)
    with pytest.raises(ValueError, match="Physical IC"):
        await coordinator.async_write_music_sequence(
            writes, mode_code=52, physical_ic_count=60, intent=ControlIntent.USER
        )


async def test_edit_rejects_body_invalidated_while_waiting_for_control(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617A", configuration_url=None)
    coordinator.music_mode = "hopping"
    coordinator._music_body = ("hopping", BODY)

    async def sequence(*args, packet_write_guard, **kwargs):
        coordinator._music_body = None
        packet_write_guard(0)
        pytest.fail("edited stale body")

    monkeypatch.setattr(coordinator, "async_write_effect_sequence", sequence)
    with pytest.raises(ValueError, match="Retained music body changed"):
        await coordinator.async_apply_music_params(51, parameters={"relative_brightness": 17})


@pytest.mark.parametrize("model", ["H617A", "H6099"])
async def test_successful_native_sequence_retains_exact_body_after_await(hass, model):
    from tests.test_music_commands import _music_transport

    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", model, configuration_url=None)
    writes = prepare_music_body_writes(model, "hopping", 42, BODY)
    with _music_transport(coordinator) as physical:
        await coordinator.async_write_music_sequence(
            writes, mode_code=51, physical_ic_count=None, intent=ControlIntent.USER
        )
    assert [call.args[1] for call in physical.await_args_list] == [packet for packet, _ in writes]
    assert coordinator.music_body == BODY


@pytest.mark.parametrize(
    "mode,body,field,value",
    [
        ("bloom", bytes.fromhex("30010102030a14"), "music_calm", True),
        ("shiny", bytes.fromhex("310101020314460b"), "music_calm", True),
        ("hopping", BODY, "music_hopping_brightness", 25),
        ("piano_keys", bytes.fromhex("3401010203010c0b0306"), "music_piano_key_count", 12),
    ],
)
async def test_verbatim_restore_updates_retained_display_and_followup_edit_is_noop(hass, mode, body, field, value):
    from tests.test_music_commands import _music_transport

    c = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617A", configuration_url=None)
    prior = replace(
        c.capture_effect_control_state(),
        mode="music",
        music_mode=mode,
        is_on=True,
        music_model="H617A",
        music_body=body,
    )
    setattr(c, field, False if isinstance(value, bool) else 1)
    with _music_transport(c) as physical:
        assert not await c.async_restore_effect_control_state(prior, overwritten_diy_code=None)
        assert c.music_body == body
        assert getattr(c, field) == value
        assert field not in c._field_revisions
        physical.reset_mock()
        await c.async_apply_music_params(
            music_variant(
                c.profile,
                {
                    "bloom": 48,
                    "shiny": 49,
                    "hopping": 51,
                    "piano_keys": 52,
                }[mode],
            ).mode_code
        )
        assert [call.args[1] for call in physical.await_args_list] == fragment_a3(0x41, body)
        assert c.music_body == body


async def test_unknown_body_style_clears_stale_style_without_selector_authority(hass):
    from tests.test_music_commands import _music_transport

    c = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617A", configuration_url=None)
    c.music_calm = True
    body = bytes.fromhex("30010102030b51")
    writes = prepare_music_body_writes("H617A", "bloom", 42, body)
    assert writes[-2][1]["_music_calm"] is None
    assert "music_calm" not in writes[-1][1] and "_music_calm" not in writes[-1][1]
    with _music_transport(c):
        await c.async_write_music_sequence(writes, mode_code=48, physical_ic_count=None, intent=ControlIntent.USER)
    assert c._music_calm is None and c.music_body == body
    assert "music_calm" not in c._field_revisions


@pytest.mark.parametrize("prefix", ["aa05133032", "aa05133332", "aa05040900", "aa051501", "aa050a0100", "aa05ff"])
def test_fresh_mode_notifications_invalidate_body_and_palette_together(hass, prefix):
    c = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617A", configuration_url=None)
    c.music_mode = "bloom"
    c._music_body = ("bloom", bytes.fromhex("30010102030a14"))
    c._music_palette = ("bloom", ((1, 2, 3),))
    c._notify_callback(None, bytearray(frame(prefix)))
    if prefix == "aa05133032":
        assert c.music_body is not None and c.music_palette == ((1, 2, 3),)
    else:
        assert c._music_body is None and c._music_palette is None
        c.music_mode = "bloom"
        assert c.music_body is None


@pytest.mark.parametrize("event", ["lost", "disconnect", "reconnect", "stale_client"])
async def test_connection_authority_loss_invalidates_body_before_yield(hass, event):
    c = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617A", configuration_url=None)
    c.music_mode = "hopping"
    c._music_body = ("hopping", BODY)
    c._music_palette = ("hopping", ((1, 2, 3),))
    client = SimpleNamespace(is_connected=True, disconnect=AsyncMock())
    c._client = client
    if event == "stale_client":
        c._clear_client_state(object())
        assert c.music_body == BODY and c.music_palette is not None
        return
    if event == "lost":
        c._disconnected_callback(client)
    elif event == "disconnect":

        async def disconnect():
            assert c._music_body is None and c._music_palette is None

        client.disconnect.side_effect = disconnect
        await c.disconnect()
    else:
        c._client = None

        async def connect(*args, **kwargs):
            assert c._music_body is None and c._music_palette is None
            raise ValueError("stop at connection boundary")

        with patch(
            "custom_components.ha_govee_led_ble.coordinator.async_establish_ble_connection", side_effect=connect
        ):
            with pytest.raises(ValueError, match="connection boundary"):
                await c._ensure_connected()
    assert c._music_body is None and c._music_palette is None


@pytest.mark.parametrize("preview", [False, True])
async def test_notification_during_upload_cannot_resurrect_palette_or_body(hass, monkeypatch, preview):
    from tests.test_music_commands import _music_transport

    c = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617A", configuration_url=None)
    c.music_mode = "bloom"
    writes = prepare_music_body_writes("H617A", "hopping", 42, BODY)

    async def writer(packet, *, state_values=None, write_guard=None, **kwargs):
        await c.async_preview_write(packet, state_values=state_values, before_write=write_guard)

    async def transmit(_uuid, packet, **kwargs):
        if packet == writes[1][0]:
            c._expected_state.clear()
            c._notify_callback(None, bytearray(frame("aa05130432")))

    with _music_transport(c) as physical:
        physical.side_effect = transmit
        await c.async_write_music_sequence(
            writes,
            mode_code=51,
            physical_ic_count=None,
            intent=ControlIntent.PREVIEW if preview else ControlIntent.USER,
            writer=writer if preview else None,
        )
    assert c._music_body is None and c._music_palette is None


async def test_raw_replay_display_values_do_not_gate_on_reconnect_geometry(hass, monkeypatch):
    c = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6099", configuration_url=None)
    known = replace(c.profile, physical_ic_count=60)
    body = bytes.fromhex("34010102030112230109")
    writes = prepare_music_body_writes("H6099", "piano_keys", 42, body, profile=known)
    assert writes[-2][1]["music_piano_key_count"] == 18

    async def sequence(*args, packet_write_guard, **kwargs):
        packet_write_guard(0)

    monkeypatch.setattr(c, "async_write_effect_sequence", sequence)
    await c.async_write_music_sequence(writes, mode_code=52, physical_ic_count=60, intent=ControlIntent.USER)


def test_profile_change_clears_complete_body_with_palette(hass, monkeypatch):
    c = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6199", configuration_url=None)
    c._music_body = ("hopping", BODY)
    c._music_palette = ("hopping", ((1, 2, 3),))
    monkeypatch.setattr(
        "custom_components.ha_govee_led_ble.coordinator.parse_govee_advertisement",
        lambda _: SimpleNamespace(pact_type=10, pact_code=1, supports_encryption=False),
    )
    monkeypatch.setattr(
        "custom_components.ha_govee_led_ble.coordinator.device_profile",
        lambda *args: replace(c.profile, supports_music_color=not c.profile.supports_music_color),
    )
    c._note_advertisement(SimpleNamespace(manufacturer_data={}))
    assert c._music_body is None and c._music_palette is None


def test_rejected_stale_selector_does_not_invalidate_known_body(hass):
    import time

    c = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617A", configuration_url=None)
    c.music_mode = "hopping"
    c._music_body = ("hopping", BODY)
    c._music_palette = ("hopping", ((1, 2, 3),))
    c._expected_state["music_mode"] = ("hopping", time.monotonic() + 60)
    c._notify_callback(None, bytearray(frame("aa05133032")))
    assert c.music_body == BODY and c.music_palette == ((1, 2, 3),)
