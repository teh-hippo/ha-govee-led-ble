"""Software-only A3 ACK barrier faults; no radio or device-state proof."""

import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak import BleakError

from custom_components.ha_govee_led_ble import coordinator as coordinator_module
from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, ModelProfile, device_profile
from custom_components.ha_govee_led_ble.control_arbiter import ControlIntent
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.effect_catalogue import WORKSHOP_PROTOCOL_FIXTURES, resolve_catalogue_template
from custom_components.ha_govee_led_ble.effect_compiler import compile_application, compile_effect
from custom_components.ha_govee_led_ble.effect_deployments import DeploymentPhase, EffectDeploymentRepository
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem, MusicProfile, SingleEffect
from custom_components.ha_govee_led_ble.effect_preview import PreviewPhase
from custom_components.ha_govee_led_ble.effect_runtime import EffectDeploymentEngine
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_music_mode,
    build_power,
    build_scene_activation,
    parse_command_ack_result,
    upload_ack_mode,
    upload_ack_subtype,
    upload_ack_success,
)
from custom_components.ha_govee_led_ble.music_commands import prepare_music_request
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
async def connected(hass, monkeypatch, request):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", getattr(request, "param", "H617A"), configuration_url=None)
    client = MagicMock(is_connected=True, start_notify=AsyncMock(), write_gatt_char=AsyncMock())
    c._client = client
    await c._start_notify()
    monkeypatch.setattr(c, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(c, "_renew_foreground_lease", MagicMock())
    monkeypatch.setattr(coordinator_module, "UPLOAD_ACK_TIMEOUT", 0.02)
    if c.model != "H7025":
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


@pytest.mark.parametrize("connected", ["H7025"], indirect=True)
@pytest.mark.parametrize("accepted", [False, True])
async def test_h7025_music_waits_for_positive_upload_result(connected, accepted):
    c, client = connected
    c.music_sensitivity = 42
    expected = prepare_music_request("H7025", "hopping", 42, None, False, {})

    async def write(_uuid, packet, **_kwargs):
        if packet == expected[-2]:
            receive(client, frame("a34148" + ("00" if accepted else "01")))

    client.write_gatt_char.side_effect = write
    if accepted:
        await c.async_select_music_slug("hopping")
        assert c.music_body is not None
    else:
        with pytest.raises(RuntimeError, match="Device rejected A3 upload"):
            await c.async_select_music_slug("hopping")
        assert c.music_body is None
    sent = [call.args[1] for call in client.write_gatt_char.await_args_list]
    assert (expected[-1] in sent) is accepted


@pytest.mark.parametrize("connected", ["H7025"], indirect=True)
@pytest.mark.parametrize("fault", ["missing_ack", "write_timeout", "disconnect"])
async def test_h7025_uncertain_upload_is_not_automatically_replayed(connected, fault):
    c, client = connected
    expected = prepare_music_request("H7025", "hopping", 99, None, False, {})

    async def reconnect():
        c._client = client
        await c._start_notify()
        return client

    async def write(_uuid, packet, **_kwargs):
        if packet == expected[1]:
            if fault == "write_timeout":
                raise TimeoutError("upload write timed out")
            if fault == "disconnect":
                c._clear_client_state(client)
                raise BleakError("disconnected during upload")

    c._ensure_connected.side_effect = reconnect
    client.write_gatt_char.side_effect = write
    with pytest.raises((TimeoutError, BleakError)):
        await c.async_select_music_slug("hopping")
    sent = [call.args[1] for call in client.write_gatt_char.await_args_list]
    assert sent == (list(expected[:-1]) if fault == "missing_ack" else list(expected[:2]))
    assert c._ensure_connected.await_count == 1
    assert c.music_body is None and c._upload_ack is None


@pytest.mark.parametrize("connected", ["H7025"], indirect=True)
async def test_h7025_connection_failure_before_upload_can_retry(connected):
    c, client = connected
    expected = prepare_music_request("H7025", "hopping", 99, None, False, {})

    async def reconnect():
        if c._ensure_connected.await_count == 1:
            raise BleakError("connection failed before upload")
        c._client = client
        await c._start_notify()
        return client

    async def write(_uuid, packet, **_kwargs):
        if packet == expected[-2]:
            receive(client, frame("a3414800"))

    c._ensure_connected.side_effect = reconnect
    client.write_gatt_char.side_effect = write
    await c.async_select_music_slug("hopping")
    assert c._ensure_connected.await_count == 2
    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == list(expected)
    assert c.music_body is not None


@pytest.mark.parametrize("connected", ["H7025"], indirect=True)
@pytest.mark.parametrize(
    ("mode", "code", "body", "parameters", "edited"),
    [
        ("flow", 0x59, "5902010203040506000205", {"direction": "counterclockwise"}, "5902010203040506010205"),
        ("hopping", 0x48, "480201020304050601020319aabb", {"relative_brightness": 17}, "480201020304050601020311aabb"),
    ],
)
@pytest.mark.parametrize("accepted", [False, True])
@pytest.mark.parametrize("preview", [False, True])
async def test_h7025_retained_edit_uploads_acknowledges_then_activates(
    connected, mode, code, body, parameters, edited, accepted, preview
):
    c, client = connected
    c.music_mode, c.music_sensitivity = mode, 42
    c._music_body = (mode, bytes.fromhex(body))
    upload = fragment_a3(0x41, bytes.fromhex(edited))
    selector = build_music_mode(code, 42, None, False, "H7025")
    events = []

    async def write(_uuid, packet, **_kwargs):
        events.append(packet)
        if packet == upload[-1]:
            events.append("positive ACK" if accepted else "negative ACK")
            receive(client, frame(f"a341{code:02x}" + ("00" if accepted else "01")))

    client.write_gatt_char.side_effect = write
    options = {"writer": lambda *args, **kwargs: preview_writer(c, *args, **kwargs)} if preview else {}
    if accepted:
        await c.async_apply_music_params(code, parameters=parameters, **options)
        assert events == [*upload, "positive ACK", selector]
        assert c.music_body == bytes.fromhex(edited)
    else:
        with pytest.raises(RuntimeError, match="Device rejected A3 upload"):
            await c.async_apply_music_params(code, parameters=parameters, **options)
        assert events == [*upload, "negative ACK"]
        assert c.music_body is None


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


@pytest.mark.parametrize(
    ("prefix", "expected"),
    [("a3415000", True), ("a3415001", False), ("a3414d00", None), ("a3415100", None), ("a3425000", None)],
)
def test_h6076_ack_must_repeat_the_uploaded_mode(prefix, expected):
    # Issue #343: the lamp answers a Torch (0x50) companion with `a3 41 50 00`.
    profile = device_profile("H6076", 1, 1, firmware="1.04.05")
    *upload, selector = prepare_music_request("H6076", "torch", 99, None, False, {}, profile=profile)[1:]
    assert selector[:3] == b"\x33\x05\x0f"
    index = len(upload) - 1
    assert upload_ack_subtype(upload, index, "H6076", profile=profile) == 0x41
    assert upload_ack_mode(upload, index, "H6076", profile=profile) == 0x50
    result = parse_command_ack_result(frame(prefix), "H6076", profile=profile)
    assert result.parser == ("h6076_music_ack" if prefix.startswith("a341") else "h617a_command_ack")
    assert upload_ack_success(result.parsed, 0x41, 0x50) is expected
    assert upload_ack_success(result.parsed, 0x41) is None
    assert parse_command_ack_result(frame("330100"), "H6076", profile=profile).parser == "h617a_command_ack"
    for subtype in (0x02, 0x03, 0x04):
        effect_upload = fragment_a3(subtype, b"\x01\x02\x03")
        effect_index = len(effect_upload) - 1
        assert upload_ack_subtype(effect_upload, effect_index, "H6076", profile=profile) == subtype
        assert upload_ack_mode(effect_upload, effect_index, "H6076", profile=profile) is None
        ack = parse_command_ack_result(frame(f"a3{subtype:02x}00"), "H6076", profile=profile)
        assert ack.parser == "h617a_command_ack"
        assert upload_ack_success(ack.parsed, subtype) is True


def test_ack_uses_command_grammar_independently_of_video(monkeypatch):
    monkeypatch.setitem(MODEL_PROFILES, "H9908", ModelProfile("Synthetic ACK", command_grammar="H617A"))
    assert parse_command_ack_result(MUSIC_OK, "H9908").parsed.is_success
    monkeypatch.setitem(MODEL_PROFILES, "H9908", ModelProfile("Synthetic ACK", video_grammar="H6199"))
    assert parse_command_ack_result(MUSIC_OK, "H9908").parsed is None


@pytest.mark.parametrize("response", [None, "a10201", "a30200", "330200", "a10200"])
async def test_a1_upload_requires_its_own_positive_ack_before_activation(connected, response):
    c, client = connected
    c.model = "H6125"
    c.pact_type, c.pact_code = 1, 2
    c.fw_version, c.hw_version = "1.07.01", "1.00.04"
    c.profile = device_profile("H6125", 1, 2, firmware=c.fw_version, hardware=c.hw_version)
    c._confirmed_identity_fields.update(c.profile.profile_identity_fields)
    item = LibraryItem.new("Fade", SingleEffect(family=0, variant=0, speed=40, palette=((255, 0, 0),)))
    compiled = compile_application(item, c.model, profile=c.profile)
    packets = [build_power(True, c.model, profile=c.profile), *compiled.upload_packets]
    index = len(packets) - 1

    async def write(_uuid, packet, **kwargs):
        if packet == packets[index] and response is not None:
            receive(client, frame(response))

    client.write_gatt_char.side_effect = write
    if response == "a10200":
        await write_sequence(c, packets, index, final_packet=compiled.activation_packet)
        expected = [*packets, compiled.activation_packet]
    else:
        with pytest.raises((TimeoutError, RuntimeError)):
            await write_sequence(c, packets, index, final_packet=compiled.activation_packet)
        expected = packets
    assert [call.args[1] for call in client.write_gatt_char.call_args_list] == expected
    assert c._field_revisions == {}


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


@pytest.mark.parametrize("path", ["saved", "preview"])
@pytest.mark.parametrize("ack", ["accepted", "rejected", "missing"])
async def test_workshop_public_paths_require_upload_ack(connected, hass, monkeypatch, path, ack):
    c, client = connected
    c.model = "H6125"
    c.profile = device_profile("H6125", 10, 2, firmware="3.04.37", hardware="3.01.10")
    c._confirmed_identity_fields.update(c.profile.profile_identity_fields)
    c.is_on = True
    item = LibraryItem.new("Workshop", WORKSHOP_PROTOCOL_FIXTURES[0].content("H6125"))
    compiled = compile_effect(item, c.model, profile=c.profile)
    monkeypatch.setattr(c, "async_preview_preflight", AsyncMock())
    monkeypatch.setattr(c, "async_observe_effect", AsyncMock(return_value=True))

    async def write(_uuid, packet, **kwargs):
        if packet == compiled.upload_packets[-1] and ack != "missing":
            receive(client, DIY_OK if ack == "accepted" else DIY_NO)

    client.write_gatt_char.side_effect = write
    if path == "saved":
        repository = EffectDeploymentRepository(InMemoryVersionedDocumentStore())
        await repository.async_load()
        engine = EffectDeploymentEngine(repository)
        monkeypatch.setattr(engine, "_async_prepare_prior_state", AsyncMock(return_value=False))
        monkeypatch.setattr(c, "async_restore_effect_control_state", AsyncMock(return_value=False))
        monkeypatch.setattr(c, "refresh_state", AsyncMock(return_value=False))
        if ack == "accepted":
            result = await engine.async_apply_saved(
                c, item, config_entry_id="entry-a", updated_at="2026-09-16T00:00:00Z"
            )
            assert result.phase is DeploymentPhase.CONFIRMED
        else:
            with pytest.raises(TimeoutError if ack == "missing" else RuntimeError):
                await engine.async_apply_saved(c, item, config_entry_id="entry-a", updated_at="2026-09-16T00:00:00Z")
            assert repository.snapshot().records[-1].phase is DeploymentPhase.UNCERTAIN
    else:
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
                item=item,
            )
            await asyncio.wait_for(manager.async_wait_idle("entry-a"), 2)
            assert events[-1].phase in (
                {PreviewPhase.CONFIRMED, PreviewPhase.UNCONFIRMED} if ack == "accepted" else {PreviewPhase.FAILED}
            )
        finally:
            await manager.async_shutdown()
    sent = [call.args[1] for call in client.write_gatt_char.call_args_list]
    assert sent == list(compiled.packets if ack == "accepted" else compiled.upload_packets)
    if ack != "accepted":
        c.async_observe_effect.assert_not_awaited()
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
