"""Software-only A3 ACK barrier faults; no radio or device-state proof."""

import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak import BleakError

from custom_components.ha_govee_led_ble import coordinator as coordinator_module
from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, ModelProfile
from custom_components.ha_govee_led_ble.control_arbiter import ControlIntent
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.effect_catalogue import resolve_catalogue_template
from custom_components.ha_govee_led_ble.effect_compiler import compile_effect
from custom_components.ha_govee_led_ble.effect_deployments import EffectDeploymentRepository
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem, MusicProfile
from custom_components.ha_govee_led_ble.effect_preview import PreviewPhase
from custom_components.ha_govee_led_ble.effect_runtime import EffectDeploymentEngine
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_scene_activation,
    parse_command_ack_result,
    upload_ack_success,
)
from custom_components.ha_govee_led_ble.transport import fragment_a3, xor_checksum
from tests.storage_test_double import InMemoryVersionedDocumentStore
from tests.test_effect_preview import _manager, _open


def frame(prefix):
    body = bytes.fromhex(prefix).ljust(19, b"\0")
    return body + bytes((xor_checksum(body),))


MUSIC_OK = frame("a3413000")
MUSIC_NO = frame("a3413001")
DIY_OK = frame("a30200")
DIY_NO = frame("a30201")


@pytest.fixture
async def connected(hass, monkeypatch):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H617A", configuration_url=None)
    client = MagicMock(is_connected=True, start_notify=AsyncMock(), write_gatt_char=AsyncMock())
    c._client = client
    await c._start_notify()
    monkeypatch.setattr(c, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(c, "_renew_foreground_lease", MagicMock())
    monkeypatch.setattr(coordinator_module, "UPLOAD_ACK_TIMEOUT", 0.02)
    monkeypatch.setattr(coordinator_module, "EFFECT_SEQUENCE_ATTEMPTS", 1)
    monkeypatch.setattr(coordinator_module, "RETRY_BACKOFF_SECONDS", 0)

    async def disconnect():
        c._clear_client_state(c._client)

    monkeypatch.setattr(c, "_disconnect_locked", AsyncMock(side_effect=disconnect))
    yield c, client
    if c._cancel_disconnect:
        c._cancel_disconnect()


def receive(client, data):
    client.start_notify.call_args.args[1](None, bytearray(data))


def sequence(subtype=0x41):
    upload = fragment_a3(subtype, bytes(range(40)))
    return [*upload, build_scene_activation("H617A", 507)], len(upload) - 1


async def write_sequence(c, packets, index, **kwargs):
    await c.async_write_effect_sequence(
        packets,
        intent=ControlIntent.PREVIEW if "writer" in kwargs else ControlIntent.USER,
        require_upload_ack=True,
        upload_ack_index=index,
        **kwargs,
    )


async def preview_writer(c, packet, *, write_guard=None, state_values=None, expected_values=None):
    assert not c._lock.locked(), "caller must not deadlock the connection-bound writer"
    await c.async_preview_write(
        packet, before_write=write_guard, state_values=state_values, expected_values=expected_values
    )


@pytest.mark.parametrize(
    "prefix,subtype,expected",
    [
        ("a3413000", 0x41, True),
        ("a3410001", 0x41, False),
        ("a30200ff", 2, True),
        ("a3020100", 2, False),
        ("330100", 0x41, None),
        ("a30200", 0x41, None),
    ],
)
def test_generated_ack_offsets_and_subtype(prefix, subtype, expected):
    result = parse_command_ack_result(frame(prefix), "H617A")
    assert result.parsed is not None
    assert result.parser == "h617a_command_ack"
    assert type(result.parsed).__module__.endswith(".h617a_command_ack")
    assert upload_ack_success(result.parsed, subtype) is expected


def test_ack_uses_command_grammar_independently_of_video(monkeypatch):
    monkeypatch.setitem(MODEL_PROFILES, "H9908", ModelProfile("Synthetic ACK", command_grammar="H617A"))
    assert parse_command_ack_result(MUSIC_OK, "H9908").parsed.is_success
    monkeypatch.setitem(MODEL_PROFILES, "H9908", ModelProfile("Synthetic ACK", video_grammar="H6199"))
    assert parse_command_ack_result(MUSIC_OK, "H9908").parsed is None


async def test_ordinary_ack_is_diagnostic_not_power_readback(connected):
    c, client = connected
    c.is_on = True
    receive(client, frame("330100"))
    assert c.is_on
    assert c._field_revisions == {}
    assert c.packet_log[-1]["reason"] == "command_ack_parsed"


@pytest.mark.parametrize("response", [None, MUSIC_NO, DIY_OK, frame("330100"), MUSIC_OK[:-1] + b"\xff"])
@pytest.mark.parametrize("preview", [False, True])
async def test_no_negative_unrelated_or_corrupt_ack_never_activates(connected, response, preview):
    c, client = connected
    packets, index = sequence()

    async def write(_uuid, packet, **kwargs):
        if packet == packets[index] and response is not None:
            receive(client, response)

    client.write_gatt_char.side_effect = write
    options = {"writer": lambda *args, **kw: preview_writer(c, *args, **kw)} if preview else {}
    with pytest.raises((TimeoutError, RuntimeError)):
        await write_sequence(c, packets, index, **options)
    assert [call.args[1] for call in client.write_gatt_char.call_args_list] == packets[: index + 1]
    assert c._upload_ack is None
    if preview:
        c._ensure_connected.assert_not_awaited()
        c._disconnect_locked.assert_not_awaited()


@pytest.mark.parametrize("preview", [False, True])
async def test_final_write_callback_race_and_state_boundaries(connected, preview):
    c, client = connected
    packets, index = sequence()
    states = [{"music_sensitivity": n + 10} for n in range(len(packets))]
    guards, progress = [], []

    def guard(n):
        assert c._upload_ack is None
        guards.append(n)

    async def write(_uuid, packet, **kwargs):
        n = packets.index(packet)
        assert c.music_sensitivity == n + 10
        assert guards == list(range(n + 1))
        if n == index:
            receive(client, MUSIC_OK)  # Before write_gatt_char returns.
            c.music_sensitivity = 99  # Fresh notification must survive the await.
        if n == index + 1:
            assert c._upload_ack is None

    async def progressed(n):
        if n == index + 1:
            assert c.music_sensitivity == 99
        progress.append(n)

    client.write_gatt_char.side_effect = write
    options = {"writer": lambda *args, **kw: preview_writer(c, *args, **kw)} if preview else {}
    await asyncio.wait_for(
        write_sequence(
            c, packets, index, packet_state_values=states, packet_write_guard=guard, progress=progressed, **options
        ),
        1,
    )
    assert progress == list(range(1, len(packets) + 1))
    assert c._upload_ack is None


@pytest.mark.parametrize("fault", ["early", "stale_subscription", "profile", "disconnect", "cancel", "transform"])
async def test_stale_early_disconnected_and_cancelled_uploads(connected, fault):
    c, client = connected
    packets, index = sequence()
    old_callback = client.start_notify.call_args.args[1]
    if fault == "stale_subscription":
        await c._start_notify()
    if fault == "transform":

        def transform(packet):
            if packet == packets[index]:
                receive(client, MUSIC_OK)  # Transform occurs before physical arming.
            return packet

        c.profile = replace(c.profile, outbound_transform=transform)

    async def write(_uuid, packet, **kwargs):
        if fault == "early" and packet == packets[0]:
            receive(client, MUSIC_OK)
        if packet == packets[index]:
            if fault == "stale_subscription":
                old_callback(None, bytearray(MUSIC_OK))
            elif fault == "profile":
                c._profile_generation += 1
                receive(client, MUSIC_OK)
            elif fault == "disconnect":
                c._clear_client_state(client)
                old_callback(None, bytearray(MUSIC_OK))
            elif fault == "cancel":
                asyncio.current_task().cancel()
                await asyncio.sleep(0)

    client.write_gatt_char.side_effect = write
    with pytest.raises((TimeoutError, ValueError, BleakError, asyncio.CancelledError)):
        await write_sequence(c, packets, index)
    assert client.write_gatt_char.call_count == index + 1
    assert c._upload_ack is None


@pytest.mark.parametrize("ack_on_retry", [False, True])
async def test_failed_final_attempt_discards_ack_and_retries_entire_upload(connected, monkeypatch, ack_on_retry):
    c, first = connected
    packets, index = sequence()
    second = MagicMock(is_connected=True, start_notify=AsyncMock(), write_gatt_char=AsyncMock())
    connections = 0
    monkeypatch.setattr(coordinator_module, "EFFECT_SEQUENCE_ATTEMPTS", 2)

    async def connect():
        nonlocal connections
        connections += 1
        c._client = first if connections == 1 else second
        await c._start_notify()
        return c._client

    c._ensure_connected.side_effect = connect

    async def failed_write(_uuid, packet, **kwargs):
        if packet == packets[index]:
            receive(first, MUSIC_OK)
            raise BleakError("final physical attempt failed after callback")

    async def retry_write(_uuid, packet, **kwargs):
        receive(first, MUSIC_OK)  # Old-client callbacks must not unlock attempt two.
        if packet == packets[index] and ack_on_retry:
            receive(second, MUSIC_OK)

    first.write_gatt_char.side_effect = failed_write
    second.write_gatt_char.side_effect = retry_write
    if ack_on_retry:
        await write_sequence(c, packets, index)
    else:
        with pytest.raises(TimeoutError):
            await write_sequence(c, packets, index)
    assert [call.args[1] for call in first.write_gatt_char.call_args_list] == packets[: index + 1]
    assert [call.args[1] for call in second.write_gatt_char.call_args_list] == (
        packets if ack_on_retry else packets[: index + 1]
    )
    assert c._upload_ack is None


@pytest.mark.parametrize("index", [None, -1, 0, 3, True])
async def test_invalid_upload_boundary_fails_before_connection_or_writes(connected, index):
    c, client = connected
    packets, _ = sequence()
    with pytest.raises(ValueError):
        await write_sequence(c, packets, index)
    c._ensure_connected.assert_not_awaited()
    client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("kind", ["diy", "music"])
@pytest.mark.parametrize("positive", [False, True])
@pytest.mark.parametrize("power", [False, True])
async def test_real_preview_path_upload_ack_then_own_selector(connected, hass, monkeypatch, kind, positive, power):
    c, client = connected
    c.is_on = power
    c.async_preview_preflight = AsyncMock()
    c.async_observe_effect = AsyncMock(return_value=True)
    if kind == "diy":
        content = resolve_catalogue_template("H617A", "template:native-diy:507").content
        final = compile_effect(LibraryItem.new("Stack", content), "H617A").upload_packets[-1]
        response = DIY_OK if positive else DIY_NO
    else:
        content = MusicProfile("H617A", "bloom", 42)
        from custom_components.ha_govee_led_ble.music_commands import prepare_music_profile_writes

        writes = prepare_music_profile_writes("H617A", "bloom", 42, None, False, {}, profile=c.profile)
        final = next(packet for packet, state in writes if state.get("_music_body") is not None)
        response = MUSIC_OK if positive else MUSIC_NO
    written = []

    async def write(_uuid, packet, **kwargs):
        written.append(packet)
        if packet == final:
            receive(client, response)

    client.write_gatt_char.side_effect = write
    manager, _ = await _manager(hass, monkeypatch, c)
    events = []
    owner = object()
    session = _open(manager, owner, events)
    try:
        await manager.async_queue_snapshot(
            session_id=session,
            owner=owner,
            config_entry_id="entry-a",
            sequence=1,
            updated_at="2026-09-16T00:00:00Z",
            item=LibraryItem.new("Preview", content),
        )
        await asyncio.wait_for(manager.async_wait_idle("entry-a"), 2)
        assert final in written
        if positive:
            assert events[-1].phase in {PreviewPhase.CONFIRMED, PreviewPhase.UNCONFIRMED}
            assert written.index(final) < len(written) - 1
            if kind == "diy":
                assert written[-1] == build_scene_activation("H617A", 507)
        else:
            assert events[-1].phase == PreviewPhase.FAILED
            assert written[-1] == final
        assert c._upload_ack is None
        c._ensure_connected.assert_not_awaited()
    finally:
        await manager.async_shutdown()


@pytest.mark.parametrize("positive", [False, True])
async def test_saved_native_diy_apply_uses_ack_gate(connected, monkeypatch, positive):
    c, client = connected
    c.is_on = True
    item = LibraryItem.new("Stack", resolve_catalogue_template("H617A", "template:native-diy:507").content)
    compiled = compile_effect(item, "H617A")
    repository = EffectDeploymentRepository(InMemoryVersionedDocumentStore())
    await repository.async_load()
    engine = EffectDeploymentEngine(repository)
    monkeypatch.setattr(engine, "_async_prepare_prior_state", AsyncMock(return_value=False))
    monkeypatch.setattr(c, "async_restore_effect_control_state", AsyncMock(return_value=False))
    monkeypatch.setattr(c, "refresh_state", AsyncMock(return_value=True))
    monkeypatch.setattr(c, "async_observe_effect", AsyncMock(return_value=True))

    async def write(_uuid, packet, **kwargs):
        if packet == compiled.upload_packets[-1]:
            receive(client, DIY_OK if positive else DIY_NO)

    client.write_gatt_char.side_effect = write
    if positive:
        await engine.async_apply_saved(c, item, config_entry_id="entry-a", updated_at="2026-09-16T00:00:00Z")
    else:
        with pytest.raises(RuntimeError, match="rejected A3"):
            await engine.async_apply_saved(c, item, config_entry_id="entry-a", updated_at="2026-09-16T00:00:00Z")
    sent = [call.args[1] for call in client.write_gatt_char.call_args_list]
    assert sent == list(compiled.packets if positive else compiled.upload_packets)
    assert c._upload_ack is None


@pytest.mark.parametrize("fault", ["cancel_wait", "disconnect_wait", "write_error", "guard_error"])
async def test_preview_failure_cleans_pending_without_reconnect(connected, monkeypatch, fault):
    c, client = connected
    packets, index = sequence()
    final_written = asyncio.Event()
    monkeypatch.setattr(coordinator_module, "UPLOAD_ACK_TIMEOUT", 1)

    async def write(_uuid, packet, **kwargs):
        if packet == packets[index]:
            final_written.set()
            if fault == "write_error":
                receive(client, MUSIC_OK)
                raise BleakError("final write failed")

    def guard(n):
        if n == index and fault == "guard_error":
            receive(client, MUSIC_OK)
            raise ValueError("guard rejected final attempt")

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(
        write_sequence(
            c,
            packets,
            index,
            packet_write_guard=guard,
            writer=lambda *args, **kw: preview_writer(c, *args, **kw),
        )
    )
    if fault in {"cancel_wait", "disconnect_wait"}:
        await asyncio.wait_for(final_written.wait(), 1)
        pending = c._upload_ack[-1]
        if fault == "cancel_wait":
            task.cancel()
        else:
            c._clear_client_state(client)
        with pytest.raises(asyncio.CancelledError if fault == "cancel_wait" else BleakError):
            await asyncio.wait_for(task, 1)
        assert pending.cancelled()
    else:
        with pytest.raises(BleakError if fault == "write_error" else ValueError):
            await task
    assert client.write_gatt_char.call_count == index + (fault != "guard_error")
    assert c._upload_ack is None
    c._ensure_connected.assert_not_awaited()
    c._disconnect_locked.assert_not_awaited()
