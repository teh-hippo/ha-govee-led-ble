"""Coordinator command, preview and effect transaction tests."""

import asyncio
from dataclasses import replace
from unittest.mock import ANY, AsyncMock, MagicMock, call, patch

import pytest
from bleak import BleakError
from homeassistant.exceptions import HomeAssistantError

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, ReadDomain
from custom_components.ha_govee_led_ble.control_arbiter import ControlIntent
from custom_components.ha_govee_led_ble.coordinator_refresh import RefreshRequest
from custom_components.ha_govee_led_ble.effect_compiler import compile_effect
from custom_components.ha_govee_led_ble.effect_deployments import (
    DeploymentPhase,
    EffectDeploymentRepository,
    ObservationConfidence,
)
from custom_components.ha_govee_led_ble.effect_domain import BuiltinScene, CatalogueRef, LibraryItem, SingleEffect
from custom_components.ha_govee_led_ble.effect_runtime import EffectDeploymentEngine, _DeploymentTransaction
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_brightness,
    build_brightness_query,
    build_firmware_query,
    build_hardware_query,
    build_power,
    build_power_query,
    build_subordinate_query,
)
from custom_components.ha_govee_led_ble.govee_encryption import GoveeTransportError
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.native_scenes import build_native_scene_packets
from custom_components.ha_govee_led_ble.protocol_core import StatusReply
from custom_components.ha_govee_led_ble.reply_pacing import ReplyGate
from custom_components.ha_govee_led_ble.scenes import MODEL_SCENES, SCENES
from custom_components.ha_govee_led_ble.transport import WRITE_UUID, fragment_a3
from tests.coordinator_test_support import _c, _packet
from tests.storage_test_double import InMemoryVersionedDocumentStore
from tests.test_govee_encryption import client

M = "custom_components.ha_govee_led_ble.coordinator"


def _transform_packet(packet: bytes) -> bytes:
    return b"\xfe" + packet


@pytest.mark.parametrize("on", [False, True])
async def test_write_only_power_delivery_clears_previous_failure_without_observation(coord, monkeypatch, on):
    coord.profile = replace(coord.profile, read_domains=frozenset(), setup_required_read_domains=frozenset())
    device = _c(write_gatt_char=AsyncMock(side_effect=TimeoutError("ambiguous power write")))
    coord._client = device
    monkeypatch.setattr(coord, "_ensure_connected", AsyncMock(return_value=device))
    light = GoveeBLELight(coord)
    light.hass = coord.hass
    light.async_write_ha_state = MagicMock()
    revisions = dict(coord._field_revisions)

    with pytest.raises(HomeAssistantError):
        await light.async_turn_on()
    assert light.is_on is None

    device.write_gatt_char.side_effect = None
    await (light.async_turn_on() if on else light.async_turn_off())

    assert light.is_on is on
    assert not coord.control_state_uncertain("is_on")
    assert coord._field_revisions == revisions
    assert [entry.args[1] for entry in device.write_gatt_char.await_args_list] == [build_power(True), build_power(on)]


@pytest.mark.parametrize("retry", ["transport", "confirmation", "guard_rejected"])
async def test_interrupted_retry_uses_last_physical_attempt_revision(coord, monkeypatch, retry):
    device = _c(write_gatt_char=AsyncMock())
    coord.is_on = True
    coord._client = device
    coord._notification_token = object()

    async def connected():
        coord._client = device
        return device

    async def write(*_args, **_kwargs):
        if device.write_gatt_char.await_count == 1:
            coord._expected_state.clear()
            coord._notify_callback(None, bytearray(_packet(0xAA, 4, [75])))
            if retry == "transport":
                raise BleakError("retryable first write")
        else:
            raise TimeoutError("ambiguous retry")

    validate = coord._require_writable_packet
    validations = 0

    def qualified(*args, **kwargs):
        nonlocal validations
        validations += 1
        validate(*args, **kwargs)
        if retry == "guard_rejected" and validations == 4:
            raise ValueError("final guard rejected retry")

    device.write_gatt_char.side_effect = write
    monkeypatch.setattr(coord, "_ensure_connected", connected)
    monkeypatch.setattr(coord, "_require_writable_packet", qualified)
    monkeypatch.setattr(coord, "refresh_state", AsyncMock(return_value=False))
    monkeypatch.setattr(coord, "_async_read_setting_fields", AsyncMock(return_value=False))
    light = GoveeBLELight(coord)
    light.hass = coord.hass
    light.async_write_ha_state = MagicMock()

    with pytest.raises(HomeAssistantError) as error:
        await light.async_turn_on(brightness=128)

    assert error.value.translation_key == "partial_command"
    assert coord._field_revisions["brightness_pct"] == 1
    assert coord.control_write_attempts == device.write_gatt_char.await_count == (1 if retry == "guard_rejected" else 2)
    assert coord.control_state_uncertain("brightness_pct") is (retry != "guard_rejected")
    assert coord.brightness_pct == (75 if retry == "guard_rejected" else 50)
    if retry != "guard_rejected":
        assert "brightness_pct" not in coord._expected_state


@pytest.mark.parametrize(
    ("readable", "observed"),
    [
        (frozenset(), False),
        (frozenset({ReadDomain.POWER}), False),
        (MODEL_PROFILES["H617A"].read_domains, False),
        (MODEL_PROFILES["H617A"].read_domains, True),
    ],
)
async def test_interrupted_control_queries_only_attempted_readable_fields(coord, monkeypatch, readable, observed):
    coord.profile = replace(coord.profile, read_domains=readable, setup_required_read_domains=frozenset())
    coord.is_on = True
    coord.brightness_pct = 20
    device = _c(write_gatt_char=AsyncMock())
    coord._client = device
    coord._notification_token = object()
    monkeypatch.setattr(coord, "_ensure_connected", AsyncMock(return_value=device))

    async def write(_uuid, packet, **_kwargs):
        if packet == build_brightness(50):
            if observed:
                coord._expected_state.clear()
                coord._notify_callback(None, bytearray(_packet(0xAA, 4, [75])))
            raise TimeoutError("ambiguous brightness write")
        assert packet == build_brightness_query("H617A")
        coord._notify_callback(None, bytearray(_packet(0xAA, 4, [37])))

    device.write_gatt_char.side_effect = write
    light = GoveeBLELight(coord)
    light.hass = coord.hass
    light.async_write_ha_state = MagicMock()
    reconciled = not observed and ReadDomain.BRIGHTNESS in readable

    with pytest.raises(HomeAssistantError) as error:
        await light.async_turn_on(brightness=128)

    assert error.value.translation_key == "partial_command"
    assert coord.control_write_attempts == 1
    assert [entry.args[1] for entry in device.write_gatt_char.await_args_list] == [
        build_brightness(50),
        *([build_brightness_query("H617A")] if reconciled else []),
    ]
    assert coord.brightness_pct == (75 if observed else 37 if reconciled else 20)
    assert coord.control_state_uncertain("brightness_pct") is (not observed and not reconciled)


@pytest.mark.parametrize("model", ["H617A", "H6199"])
@pytest.mark.parametrize("workflow", ["state", "identity", "command", "preview", "sequence"])
async def test_outbound_workflows_share_profile_transform(coord, h6199, model, workflow):
    coordinator = coord if model == "H617A" else h6199
    transform = MagicMock(side_effect=_transform_packet)
    coordinator.profile = replace(coordinator.profile, outbound_transform=transform)
    coordinator._arm_expected_values({"is_on": False})
    previous_expectations = dict(coordinator._expected_state)
    control = workflow in {"command", "preview", "sequence"}
    packets = [build_power(True, model)]
    if workflow == "state":
        packets = [build_power_query(model)]
    elif workflow == "identity":
        coordinator.fw_version = coordinator.subordinate_20_version = coordinator.subordinate_21_version = "1.00.01"
        packets = (
            [
                build_hardware_query(model),
                build_firmware_query(model),
                build_subordinate_query(0x20, "H6199"),
                build_subordinate_query(0x21, "H6199"),
            ]
            if model == "H6199"
            else [build_hardware_query(model)]
        )
    elif workflow == "sequence":
        packets.extend(build_native_scene_packets(model, MODEL_SCENES[model]["glacier"]))

    async def write(_uuid, _packet, **_kwargs):
        assert coordinator._expected_state["is_on"][0] is control

    client = _c(write_gatt_char=AsyncMock(side_effect=write))
    coordinator._client = client
    with (
        patch.object(coordinator, "_ensure_connected", new=AsyncMock(return_value=client)),
        patch.object(coordinator, "_arm_expected", wraps=coordinator._arm_expected) as arm,
        patch.object(coordinator, "_reset_disconnect_timer") as renew,
    ):
        if workflow == "state":
            assert await coordinator._send_state_queries(query_brightness=False, query_color_mode=False)
        elif workflow == "identity":
            await coordinator._send_identity_queries()
        elif workflow == "command":
            await coordinator.send_command(packets[0])
        elif workflow == "preview":
            await coordinator.async_preview_write(packets[0])
        else:
            await coordinator.async_write_effect_sequence(packets, intent=ControlIntent.APPLY)

    assert transform.call_args_list == [call(packet) for packet in packets]
    assert client.write_gatt_char.await_args_list == [
        call(WRITE_UUID, _transform_packet(packet), response=False) for packet in packets
    ]
    assert [(entry["raw"], entry["outcome"], entry["reason"]) for entry in coordinator.packet_log] == [
        (_transform_packet(packet).hex(), "sent", "write_succeeded") for packet in packets
    ]
    assert arm.call_args_list == ([call(packet, expectations=ANY) for packet in packets] if control else [])
    assert renew.call_count == (len(packets) if control else 0)
    if not control:
        assert coordinator._expected_state == previous_expectations


@pytest.mark.parametrize("guarded", [False, True])
async def test_static_write_reuses_semantics_and_only_rechecks_permissions_around_hooks(coord, guarded):
    from custom_components.ha_govee_led_ble import coordinator as coordinator_module
    from custom_components.ha_govee_led_ble import coordinator_notifications
    from custom_components.ha_govee_led_ble.light_commands import build_color_rgb

    packet = build_color_rgb(10, 20, 30)
    client = _c(write_gatt_char=AsyncMock())
    with (
        patch.object(coord, "_require_writable_packet", wraps=coord._require_writable_packet) as validate,
        patch.object(coordinator_module, "parse_write_state", wraps=coordinator_module.parse_write_state) as parse,
        patch.object(
            coordinator_notifications,
            "expectations_from_packet",
            side_effect=AssertionError("write expectations must not be re-parsed"),
        ),
    ):
        await coord._async_write_packet(
            client, packet, arm_expected=True, before_write=(lambda: None) if guarded else None
        )
    assert validate.call_count == (2 if guarded else 1)
    parse.assert_called_once()
    assert coord.segment_colors == [(10, 20, 30)] * coord.profile.segment_count


@pytest.mark.parametrize("result", [ValueError("Cannot transform packet"), b"", None, bytearray(b"wire")])
async def test_outbound_transform_rejection_does_not_write_or_arm_state(coord, result):
    transform = MagicMock(side_effect=[result])
    coord.profile = replace(coord.profile, outbound_transform=transform)
    coord._arm_expected_values({"is_on": False})
    previous_expectations = dict(coord._expected_state)
    client = _c(write_gatt_char=AsyncMock())
    packet = build_power(True)

    with pytest.raises(ValueError):
        await coord._async_write_packet(client, packet, arm_expected=True)

    transform.assert_called_once_with(packet)
    client.write_gatt_char.assert_not_awaited()
    assert coord.packet_log == []
    assert coord._expected_state == previous_expectations


@pytest.mark.parametrize("transform", [None, _transform_packet])
async def test_send_command(coord, transform):
    transform_mock = MagicMock(side_effect=transform) if transform is not None else None
    coord.profile = replace(coord.profile, outbound_transform=transform_mock)
    packet = build_power(True)
    wire_packet = packet if transform is None else transform(packet)
    c = _c(write_gatt_char=AsyncMock(side_effect=[BleakError("f"), BleakError("f"), None]))
    with patch.object(coord, "_ensure_connected", return_value=c):
        await coord.send_command(packet)
    assert c.write_gatt_char.await_args_list == [call(WRITE_UUID, wire_packet, response=False)] * 3
    assert coord.packet_log[-1]["outcome"] == "sent"
    assert coord.packet_log[-1]["reason"] == "write_succeeded"
    assert coord.packet_log[-1]["raw"] == wire_packet.hex()
    c2 = _c(write_gatt_char=AsyncMock(side_effect=BleakError("f")))
    with patch.object(coord, "_ensure_connected", return_value=c2), pytest.raises(BleakError):
        await coord.send_command(packet)
    assert c2.write_gatt_char.await_args_list == [call(WRITE_UUID, wire_packet, response=False)] * 3
    assert coord._client is None
    assert len(coord.packet_log) == 1
    if transform_mock is not None:
        assert transform_mock.call_args_list == [call(packet)] * 6


async def test_writes_wait_for_previous_reply_and_learn_silent_commands(coord, virtual_clock):
    coord._reply_gate = ReplyGate(0.5)
    client = _c(write_gatt_char=AsyncMock())
    loop = asyncio.get_running_loop()
    power, query = build_power(True), build_power_query("H617A")

    async def elapsed(packet: bytes) -> float:
        start = loop.time()
        await coord._async_write_packet(client, packet)
        return loop.time() - start

    await coord._async_write_packet(client, power)
    loop.call_later(0.1, coord._notify_callback, None, bytearray(_packet(0x33, 0x01, [])))
    assert await elapsed(query) == pytest.approx(0.1)
    # The unanswered query is learned as silent; the answered power command stays paced.
    assert await elapsed(power) == pytest.approx(0.5)
    assert await elapsed(query) == pytest.approx(0.5)
    assert await elapsed(power) == pytest.approx(0)
    coord._reply_gate.reset()
    await coord._async_write_packet(client, query)
    assert await elapsed(power) == pytest.approx(0.5)


@pytest.mark.parametrize("header", [0x33, 0xAA])
async def test_reply_during_physical_write_keeps_later_writes_paced(coord, virtual_clock, header):
    coord._reply_gate = ReplyGate(0.5)
    packet = build_power(True) if header == 0x33 else build_power_query("H617A")
    writes = 0

    async def transmit(_uuid, _packet, **_kwargs):
        nonlocal writes
        writes += 1
        if writes == 1:
            coord._notify_callback(None, bytearray(reply))
            await asyncio.sleep(0)

    reply = _packet(header, 0x01, [0])
    client = _c(write_gatt_char=AsyncMock(side_effect=transmit))
    await coord._async_write_packet(client, packet)
    loop = asyncio.get_running_loop()
    start = loop.time()
    await coord._async_write_packet(client, packet)
    assert loop.time() - start == pytest.approx(0)
    start = loop.time()
    await coord._async_write_packet(client, packet)
    assert loop.time() - start == pytest.approx(0.5)


async def test_late_reply_reinstates_pacing_for_a_command_learned_as_silent(coord, virtual_clock):
    coord._reply_gate = ReplyGate(0.5)
    client = _c(write_gatt_char=AsyncMock())
    packet = build_power(True)
    await coord._async_write_packet(client, packet)
    await coord._async_write_packet(client, packet)
    coord._notify_callback(None, bytearray(_packet(0x33, 0x01, [0])))
    await coord._async_write_packet(client, packet)
    loop = asyncio.get_running_loop()
    start = loop.time()
    await coord._async_write_packet(client, packet)
    assert loop.time() - start == pytest.approx(0.5)


async def test_reply_timeout_starts_after_slow_physical_write_completes(coord, virtual_clock):
    coord._reply_gate = ReplyGate(0.5)
    loop = asyncio.get_running_loop()

    async def transmit(_uuid, _packet, **_kwargs):
        await asyncio.sleep(1)

    client = _c(write_gatt_char=AsyncMock(side_effect=transmit))
    await coord._async_write_packet(client, build_power(True))
    timer = loop.call_later(0.1, coord._notify_callback, None, bytearray(_packet(0x33, 0x01, [0])))
    client.write_gatt_char.side_effect = None
    start = loop.time()
    try:
        await coord._async_write_packet(client, build_power_query("H617A"))
        assert loop.time() - start == pytest.approx(0.1)
    finally:
        timer.cancel()


@pytest.mark.parametrize(
    ("outbound", "invalid", "valid"),
    [
        (build_power(True), b"\x33\x01", _packet(0x33, 0x01, [0])),
        (build_power(True), _packet(0x33, 0x01, [0])[:-1] + b"\xff", _packet(0x33, 0x01, [0])),
        (build_brightness_query("H617A"), _packet(0xAA, 0x04, [101]), _packet(0xAA, 0x04, [50])),
    ],
)
async def test_malformed_reply_does_not_release_a_queued_write(coord, virtual_clock, outbound, invalid, valid):
    coord._reply_gate = ReplyGate(0.5)
    coord._arm_expected_values({"brightness_pct": 60})
    client = _c(write_gatt_char=AsyncMock())
    await coord._async_write_packet(client, outbound)
    loop = asyncio.get_running_loop()
    invalid_timer = loop.call_later(0.1, coord._notify_callback, None, bytearray(invalid))
    valid_timer = loop.call_later(0.2, coord._notify_callback, None, bytearray(valid))
    start = loop.time()
    try:
        await coord._async_write_packet(client, build_power_query("H617A"))
        assert loop.time() - start == pytest.approx(0.2)
        assert coord.packet_log[1]["outcome"] == "rejected"
    finally:
        invalid_timer.cancel()
        valid_timer.cancel()


@pytest.mark.parametrize("error", [BleakError("write failed"), asyncio.CancelledError()])
async def test_failed_physical_write_does_not_leave_a_pending_reply(coord, virtual_clock, error):
    coord._reply_gate = ReplyGate(0.5)
    client = _c(write_gatt_char=AsyncMock(side_effect=[error, None]))
    packet = build_power(True)
    with pytest.raises(type(error)):
        await coord._async_write_packet(client, packet)
    loop = asyncio.get_running_loop()
    start = loop.time()
    await coord._async_write_packet(client, packet)
    assert loop.time() - start == pytest.approx(0)
    start = loop.time()
    await coord._reply_gate.wait()
    assert loop.time() - start == pytest.approx(0.5)


@pytest.mark.parametrize("model", ["H617A", "H6199"])
async def test_mid_poll_disconnect_handles_stale_write_and_cancels_real_keep_alive(
    coord, h6199, monkeypatch, virtual_clock, caplog, model
):
    coordinator = coord if model == "H617A" else h6199
    coordinator._first_refresh_done = coordinator._present = coordinator._state_read_available = True
    coordinator._reply_gate = ReplyGate(0.5)
    device = client(b"\x01\x00")
    keep_alive = []
    failures = []
    refresh = coordinator.refresh_state

    async def record_refresh(request):
        try:
            return await refresh(request)
        except GoveeTransportError as error:
            failures.append(str(error))
            raise

    def disconnect():
        device.is_connected = False
        coordinator._disconnected_callback(device)

    async def write(_uuid, packet, **_kwargs):
        if packet == build_power_query(model):
            keep_alive.append(coordinator._keep_alive_task)
            asyncio.get_running_loop().call_later(0.1, disconnect)
            return
        payload = {0x06: list(b"3.02.24"), 0x07: [3, *b"3.02.01"]}.get(packet[1])
        if payload is not None:
            device.start_notify.await_args.args[1](None, bytearray(_packet(0xAA, packet[1], payload)))

    device.write_gatt_char.side_effect = write
    device.disconnect.side_effect = disconnect
    establish = AsyncMock(return_value=device)
    monkeypatch.setattr(f"{M}.async_establish_ble_connection", establish)
    monkeypatch.setattr(coordinator, "refresh_state", record_refresh)
    await coordinator.async_refresh()
    await coordinator.hass.async_block_till_done(wait_background_tasks=True)
    assert coordinator.last_update_success and coordinator.available
    assert not coordinator._state_read_available
    assert coordinator._client is None and not coordinator._encryption.ready
    assert len(keep_alive) == 1 and keep_alive[0].done() and keep_alive[0].exception() is None
    assert coordinator._keep_alive_task is None
    assert failures == ["stale_connection"]
    assert not any("Unexpected error fetching" in record.getMessage() for record in caplog.records)
    establish.assert_awaited_once()
    assert device.write_gatt_char.await_args.args[1] == build_power_query(model)


@pytest.mark.parametrize("private", [False, True])
async def test_successful_tx_debug_uses_redacted_packet_log(coord, caplog, private):
    packet = build_power(True)
    coord._dreamview_private_write = private
    caplog.set_level("DEBUG", logger=M)
    await coord._async_write_packet(_c(write_gatt_char=AsyncMock()), packet)
    messages = [record.message for record in caplog.records if record.message.startswith("tx ")]
    assert messages == [f"tx H617A raw={'' if private else packet.hex()}"]
    assert coord.address not in messages[0]


@pytest.mark.parametrize("problem", ["truncated", "reordered", "orphaned"])
async def test_invalid_upload_sequence_is_rejected_before_power_or_connection(coord, monkeypatch, problem):
    frames = fragment_a3(4, bytes(range(60)))
    if problem == "truncated":
        frames = frames[:-1]
    elif problem == "reordered":
        frames[1], frames[2] = frames[2], frames[1]
    else:
        frames = frames[1:]
    connect = AsyncMock()
    monkeypatch.setattr(coord, "_ensure_connected", connect)
    with pytest.raises(ValueError, match="A3"):
        await coord.async_write_effect_sequence((build_power(True), *frames), intent=ControlIntent.APPLY)
    connect.assert_not_awaited()


@pytest.mark.parametrize("index", [0, 1])
async def test_upload_chunks_cannot_bypass_the_sequence_writer(coord, monkeypatch, index):
    client = _c(write_gatt_char=AsyncMock())
    coord._client = client
    monkeypatch.setattr(coord, "_ensure_connected", AsyncMock(return_value=client))
    with pytest.raises(ValueError, match="complete ordered"):
        await coord.send_command(fragment_a3(4, bytes(range(60)))[index])
    client.write_gatt_char.assert_not_awaited()


async def test_music_only_profile_authorises_all_bound_companion_chunks(coord, monkeypatch, virtual_clock):
    coord.profile = replace(coord.profile, effect_grammar=None, command_operations=frozenset({"music"}))
    packets = fragment_a3(0x41, bytes(range(60)))
    client = _c(write_gatt_char=AsyncMock())
    coord._client = client
    monkeypatch.setattr(coord, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(coord, "_renew_foreground_lease", lambda: None)
    await coord.async_write_effect_sequence(packets, intent=ControlIntent.APPLY)
    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == packets
    assert coord._a3_sequence is None


@pytest.mark.parametrize("transform", [None, _transform_packet])
async def test_effect_sequence_reconnect_restarts_from_frame_zero(coord, transform):
    transform_mock = MagicMock(side_effect=transform) if transform is not None else None
    coord.profile = replace(coord.profile, outbound_transform=transform_mock)
    packets = [b"first", b"second", b"activation"]
    wire_packets = packets if transform is None else [transform(packet) for packet in packets]
    attempted: list[bytes] = []

    async def first_write(_uuid, packet, **_kwargs):
        attempted.append(packet)
        if packet == wire_packets[1]:
            raise BleakError("connection dropped")

    async def replacement_write(_uuid, packet, **_kwargs):
        attempted.append(packet)

    first = _c(write_gatt_char=AsyncMock(side_effect=first_write), disconnect=AsyncMock())
    replacement = _c(write_gatt_char=AsyncMock(side_effect=replacement_write), disconnect=AsyncMock())
    attempts: list[int] = []
    validations: list[int] = []
    progress: list[int] = []

    async def note_attempt(attempt: int) -> None:
        attempts.append(attempt)

    async def validate_attempt() -> None:
        validations.append(len(attempts))

    async def note_progress(index: int) -> None:
        progress.append(index)

    clients = iter((first, replacement))

    async def connect():
        client = next(clients)
        coord._client = client
        return client

    with patch.object(
        coord,
        "_ensure_connected",
        new=AsyncMock(side_effect=connect),
    ):
        await coord.async_write_effect_sequence(
            packets,
            intent=ControlIntent.PREVIEW,
            before_write=validate_attempt,
            attempt_started=note_attempt,
            progress=note_progress,
        )

    assert attempted == [*wire_packets[:2], *wire_packets]
    assert [entry["raw"] for entry in coord.packet_log] == [packet.hex() for packet in (wire_packets[0], *wire_packets)]
    assert attempts == [1, 2]
    assert validations == [1, 2]
    assert progress == [1, 1, 2, 3]
    if transform_mock is not None:
        assert transform_mock.call_args_list == [call(packet) for packet in (*packets[:2], *packets)]


async def test_effect_sequence_does_not_reconnect_during_shutdown(coord):
    async def fail_during_shutdown(_uuid, _packet, **_kwargs):
        coord.hass.is_stopping = True
        raise BleakError("connection dropped")

    client = _c(write_gatt_char=AsyncMock(side_effect=fail_during_shutdown))
    with (
        patch.object(coord, "_ensure_connected", new=AsyncMock(return_value=client)) as ensure_connected,
        patch.object(coord, "_disconnect_locked", new_callable=AsyncMock) as disconnect,
        pytest.raises(RuntimeError, match="Home Assistant is stopping"),
    ):
        await coord.async_write_effect_sequence(
            [b"first", b"activation"],
            intent=ControlIntent.PREVIEW,
        )

    assert ensure_connected.await_count == 1
    disconnect.assert_awaited_once_with()


async def test_effect_sequence_does_not_retry_optional_final_packet(coord):
    attempted: list[bytes] = []

    async def write(_uuid, packet, **_kwargs):
        attempted.append(packet)
        if packet == b"selector":
            raise BleakError("selector failed")

    client = _c(write_gatt_char=AsyncMock(side_effect=write))
    coord._client = client
    with (
        patch.object(coord, "_ensure_connected", new=AsyncMock(return_value=client)) as ensure_connected,
        pytest.raises(BleakError, match="selector failed"),
    ):
        await coord.async_write_effect_sequence(
            [b"start", b"data", b"finish"],
            intent=ControlIntent.PREVIEW,
            final_packet=b"selector",
        )

    assert attempted == [b"start", b"data", b"finish", b"selector"]
    ensure_connected.assert_awaited_once_with()


async def test_foreground_command_waits_for_atomic_preview_packets(coord):
    writes: list[bytes] = []
    client = _c(write_gatt_char=AsyncMock(side_effect=lambda _uuid, packet, **_kwargs: writes.append(packet)))
    coord._client = client
    first, second, user = b"first", b"second", build_power(True)

    async with coord._control_arbiter.hold(ControlIntent.PREVIEW):
        await coord.async_preview_write(first)
        command = asyncio.create_task(coord.send_command(user))
        await asyncio.sleep(0)
        await coord.async_preview_write(second)
        assert writes == [first, second]

    await command
    assert writes == [first, second, user]


async def test_preview_write_arms_expected_state(coord):
    packet = build_power(True)
    coord._client = _c(write_gatt_char=AsyncMock())

    await coord.async_preview_write(packet)

    assert coord._expected_state["is_on"][0] is True


async def test_preview_stale_gatt_failure_discards_client_and_requires_fresh_services(coord):
    client = _c(
        write_gatt_char=AsyncMock(side_effect=BleakError("GATT characteristic not found")),
        clear_cache=AsyncMock(return_value=True),
        disconnect=AsyncMock(),
    )
    coord._client = client

    with pytest.raises(BleakError, match="GATT characteristic not found"):
        await coord.async_preview_write(build_power(True))

    assert coord.fresh_services_required is True
    assert coord._client is None
    client.clear_cache.assert_awaited_once_with()
    client.disconnect.assert_awaited_once()


async def test_native_scene_holds_control_ownership_for_complete_delivery(coord):
    lock = coord._control_arbiter
    coord.is_on = False
    packets = []

    async def transmit(_uuid, packet: bytes, **kwargs: object) -> None:
        assert lock.locked()
        packets.append(packet)

    coord.effect_families = frozenset()
    client = _c(write_gatt_char=AsyncMock(side_effect=transmit))
    with (
        patch.object(coord, "_ensure_connected", AsyncMock(return_value=client)),
        patch.object(coord, "_reset_disconnect_timer"),
    ):
        await coord.async_apply_native_scene("glacier", speed_index=0, verify=False)

    assert packets[0] == build_power(True, "H617A")
    assert packets[1:] == build_native_scene_packets("H617A", SCENES["glacier"], speed_index=0)


async def test_native_scene_power_state_waits_for_atomic_sequence(coord):
    coord.is_on = False
    coord.effect_families = frozenset()
    with (
        patch.object(
            coord,
            "async_write_effect_sequence",
            new_callable=AsyncMock,
            side_effect=BleakError("connection dropped"),
        ) as write_sequence,
        pytest.raises(BleakError, match="connection dropped"),
    ):
        await coord.async_apply_native_scene(
            "glacier",
            speed_index=0,
            verify=False,
        )

    assert write_sequence.await_args.args[0][0] == build_power(True, "H617A")
    assert coord.is_on is False


@pytest.mark.parametrize("expectations", [{"effect": "glacier"}, {"scene_code": SCENES["glacier"].code}])
async def test_preview_observation_stays_read_only_when_device_is_silent(coord, virtual_clock, expectations):
    coord._client = MagicMock(is_connected=True)
    with (
        patch.object(coord, "_send_state_queries", new=AsyncMock(return_value=True)) as query,
        patch.object(coord, "_disconnect_if_current", new_callable=AsyncMock) as disconnect,
        patch.object(coord, "send_command", new_callable=AsyncMock) as send,
    ):
        result = await coord.async_observe_effect(
            expectations,
            timeout=0.05,
        )

    assert result is None
    assert query.await_count == 1
    query.assert_awaited_with(
        query_power=False,
        query_brightness=False,
        query_color_mode=True,
        query_white_balance=False,
        query_blank_screen=False,
        query_black_border=False,
        query_relative_brightness=False,
        query_whole_relative_brightness=False,
        deadline=ANY,
    )
    disconnect.assert_not_awaited()
    send.assert_not_awaited()
    assert not coord._control_arbiter.locked()


@pytest.mark.parametrize("reply", [True, False, None], ids=["match", "contradiction", "silence"])
@pytest.mark.parametrize("missing_companion", [False, True])
async def test_connected_refresh_distinguishes_fresh_observations_from_silence(
    coord, virtual_clock, reply, missing_companion
):
    client = coord._client = _c(write_gatt_char=AsyncMock())
    coord.is_on = True

    async def query(**kwargs):
        if reply is not None:
            coord._notify_callback(None, bytearray(_packet(0xAA, 0x01, [int(reply)])))
        return True

    with (
        patch.object(coord, "_ensure_connected", AsyncMock(return_value=client)),
        patch.object(coord, "_send_state_queries", AsyncMock(side_effect=query)),
        patch.object(coord, "_disconnect_if_current_locked", AsyncMock()) as disconnect,
    ):
        result = await coord.refresh_state(
            RefreshRequest(on=True, brightness=50 if missing_companion else None, timeout=0.05)
        )

    assert result is (None if missing_companion and reply is True else reply)
    disconnect.assert_not_awaited()
    client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("connected", [False, True])
async def test_preview_preflight_retries_one_failed_connection_path(coord, virtual_clock, connected):
    partial = _c()
    partial.is_connected = connected
    replacement = _c()
    attempts = 0

    async def connect():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            coord._client = partial
            raise TimeoutError
        coord._client = replacement
        return replacement

    with patch.object(coord, "_ensure_connected", new=AsyncMock(side_effect=connect)) as ensure_connected:
        await coord.async_preview_preflight(timeout=0.2)

    assert ensure_connected.await_count == 2
    partial.disconnect.assert_awaited_once_with()
    assert coord._client is replacement
    assert not coord._control_arbiter.locked()


async def test_preview_preflight_bounds_partial_client_cleanup(coord, virtual_clock):
    never_disconnected = asyncio.Event()
    partial = _c(disconnect=AsyncMock(side_effect=never_disconnected.wait))

    async def connect():
        coord._client = partial
        await asyncio.Event().wait()

    with (
        patch.object(coord, "_ensure_connected", new=AsyncMock(side_effect=connect)),
        pytest.raises(TimeoutError),
    ):
        async with asyncio.timeout(0.2):
            await coord.async_preview_preflight(timeout=0.02)

    partial.disconnect.assert_awaited_once_with()
    assert coord._client is None
    assert not coord._control_arbiter.locked()


async def test_preview_preflight_cancellation_finishes_detached_cleanup(coord):
    connect_started = asyncio.Event()
    disconnect_started = asyncio.Event()
    release_disconnect = asyncio.Event()
    disconnect_finished = asyncio.Event()

    async def disconnect():
        disconnect_started.set()
        await release_disconnect.wait()
        disconnect_finished.set()

    partial = _c(disconnect=AsyncMock(side_effect=disconnect))

    async def connect():
        coord._client = partial
        connect_started.set()
        await asyncio.Event().wait()

    with patch.object(coord, "_ensure_connected", new=AsyncMock(side_effect=connect)):
        preflight = asyncio.create_task(coord.async_preview_preflight(timeout=1))
        await connect_started.wait()
        preflight.cancel()
        with pytest.raises(asyncio.CancelledError):
            await preflight

    await disconnect_started.wait()
    assert coord._client is None
    assert not coord._control_arbiter.locked()
    release_disconnect.set()
    await disconnect_finished.wait()


async def test_preview_preflight_timeout_includes_foreground_wait(coord, virtual_clock):
    foreground_started = asyncio.Event()
    release_foreground = asyncio.Event()

    async def hold_foreground() -> None:
        async with coord._control_arbiter.hold(ControlIntent.USER):
            foreground_started.set()
            await release_foreground.wait()

    foreground = asyncio.create_task(hold_foreground())
    await foreground_started.wait()
    with (
        patch.object(coord, "_ensure_connected", new_callable=AsyncMock) as ensure_connected,
        pytest.raises(TimeoutError),
    ):
        await coord.async_preview_preflight(timeout=0.02)

    ensure_connected.assert_not_awaited()
    release_foreground.set()
    await foreground


@pytest.mark.parametrize("selector", ["diy_code", "scene_code"])
@pytest.mark.parametrize(
    ("replies", "expected"),
    [
        ("none", None),
        ("power", None),
        ("selector", None),
        ("both", True),
        ("mismatch", False),
        ("selector_mismatch", False),
        ("power_mismatch", False),
        ("wrong_mode", False),
        ("suppressed_mode", None),
        ("stale_mode", None),
    ],
)
@pytest.mark.parametrize("intent", [ControlIntent.PREVIEW, ControlIntent.APPLY])
async def test_effect_observation_requires_fresh_selector_and_power(
    coord, virtual_clock, selector, replies, expected, intent
):
    coord._client = MagicMock(is_connected=True)
    mode = int(StatusReply.ColorMode.diy) if selector == "diy_code" else int(StatusReply.ColorMode.scene)
    coord._notify_callback(None, bytearray(_packet(0xAA, 0x01, [1])))
    coord._notify_callback(None, bytearray(_packet(0xAA, 0x05, [mode, 24, 0])))
    wrong_mode = bytearray(_packet(0xAA, 0x05, [int(StatusReply.ColorMode.static), 0]))
    if replies == "stale_mode":
        coord._notify_callback(None, wrong_mode)
    elif replies == "suppressed_mode":
        coord._arm_expected_values({"color_mode": (coord.color_mode, coord.diy_code)})

    async def query(**_kwargs) -> bool:
        assert coord._control_arbiter.current_task_intent == intent
        loop = asyncio.get_running_loop()
        if replies in {"power", "both", "mismatch", "power_mismatch", "suppressed_mode", "stale_mode"}:
            power = 0 if replies == "power_mismatch" else 1
            loop.call_soon(coord._notify_callback, None, bytearray(_packet(0xAA, 0x01, [power])))
        if replies in {"selector", "both", "mismatch", "selector_mismatch"}:
            code = 25 if replies in {"mismatch", "selector_mismatch"} else 24
            loop.call_soon(coord._notify_callback, None, bytearray(_packet(0xAA, 0x05, [mode, code, 0])))
        if replies in {"wrong_mode", "suppressed_mode"}:
            loop.call_soon(coord._notify_callback, None, wrong_mode)
        return True

    with patch.object(
        coord,
        "_send_state_queries",
        new=AsyncMock(side_effect=query),
    ) as sent:
        async with coord._control_arbiter.hold(intent):
            result = await coord.async_observe_effect({"is_on": True, selector: 24}, timeout=0.01)

    assert result is expected
    sent.assert_awaited_once()
    assert not coord._control_arbiter.locked()


@pytest.mark.parametrize(
    ("selector", "actual", "final_desired"),
    [
        ("diy_code", [int(StatusReply.ColorMode.scene), 0x74, 0x08], True),
        ("scene_code", [int(StatusReply.ColorMode.diy), 24, 0], True),
        ("scene_code", [int(StatusReply.ColorMode.static), 0], True),
        ("diy_code", [int(StatusReply.ColorMode.scene), 0x74, 0x08], False),
        ("diy_code", None, False),
    ],
    ids=["diy-to-scene", "scene-to-diy", "scene-to-static", "persistent-wrong", "silence"],
)
async def test_deployment_retries_activation_after_fresh_wrong_mode(
    coord, selector, actual, final_desired, virtual_clock
):
    scene = MODEL_SCENES[coord.model]["aurora"]
    item = LibraryItem.new(
        "Retry",
        SingleEffect(0, 0, 50, ((255, 0, 0),))
        if selector == "diy_code"
        else BuiltinScene(CatalogueRef(coord.model, scene.scene_id, scene.effect_id)),
    )
    compiled = compile_effect(item, coord.model, diy_code=24 if selector == "diy_code" else None)
    assert compiled.upload_packets
    assert compiled.diy_code is not None
    repository = EffectDeploymentRepository(InMemoryVersionedDocumentStore())
    await repository.async_load()
    engine = EffectDeploymentEngine(repository)
    record = replace(
        engine._new_record(
            compiled,
            config_entry_id="entry-a",
            updated_at="2026-08-26T00:00:00Z",
            operation_id=None,
            source_item=item,
            source_kind="saved_effect",
        ),
        phase=DeploymentPhase.VERIFYING,
        progress_current=compiled.progress_total,
    )
    await repository.async_put(record, expected_version=None)
    client = _c(write_gatt_char=AsyncMock())
    coord._client = client
    desired_mode = int(StatusReply.ColorMode.diy) if selector == "diy_code" else int(StatusReply.ColorMode.scene)
    desired = [desired_mode, compiled.diy_code & 0xFF, compiled.diy_code >> 8]
    accepted_revisions = []

    async def query(**_kwargs) -> bool:
        assert coord._control_arbiter.current_task_intent is ControlIntent.APPLY
        assert sent.await_count <= (2 if actual is None else 4)
        assert client.write_gatt_char.await_args_list == [
            call(WRITE_UUID, packet, response=False)
            for packet in (*compiled.packets, *((compiled.activation_packet,) if sent.await_count > 2 else ()))
        ]
        if actual is None:
            return True
        payload = desired if final_desired and sent.await_count > 2 else actual
        baseline = coord._field_revisions.get("color_mode", 0)
        coord._notify_callback(None, bytearray(_packet(0xAA, 0x01, [1])))
        coord._notify_callback(None, bytearray(_packet(0xAA, 0x05, payload)))
        accepted_revisions.append(coord._field_revisions.get("color_mode", 0) > baseline)
        return True

    with (
        patch.object(coord, "_send_state_queries", new=AsyncMock(side_effect=query)) as sent,
        patch.object(coord, "async_observe_effect", wraps=coord.async_observe_effect) as observe,
        patch.object(coord, "_reset_disconnect_timer"),
    ):
        async with coord._control_arbiter.hold(ControlIntent.APPLY):
            await coord.async_write_effect_sequence(compiled.packets, intent=ControlIntent.APPLY)
            assert "color_mode" in coord._expected_state
            transaction = _DeploymentTransaction(repository, record, len(compiled.upload_packets), persisted=True)
            confirmed, confidence = await engine._async_verify(coord, compiled, transaction)
            current = transaction.current

    expected_revisions = (
        [] if actual is None else ([False, True, True] if final_desired else [False, True, False, True])
    )
    assert accepted_revisions == expected_revisions
    assert confirmed is (None if actual is None else final_desired)
    assert confidence is (ObservationConfidence.ACTIVATION_MATCH if final_desired else ObservationConfidence.UNKNOWN)
    assert sent.await_count == observe.await_count == (2 if actual is None else len(expected_revisions))
    assert all(observation.kwargs == {"timeout": 4.0} for observation in observe.await_args_list)
    assert client.write_gatt_char.await_args_list == [
        call(WRITE_UUID, packet, response=False)
        for packet in (*compiled.packets, *((compiled.activation_packet,) if actual is not None else ()))
    ]
    assert repository.get(record.operation_id) == current
    assert current.phase is DeploymentPhase.VERIFYING


@pytest.mark.parametrize("effect", ["aurora-a", "racing game-a"])
@pytest.mark.parametrize("power", [True, False])
async def test_effect_observation_cannot_disambiguate_h617e_scene_aliases(coord, effect, power):
    coord.model = "H617E"
    coord.profile = MODEL_PROFILES[coord.model]
    coord._client = _c()
    scene_received = asyncio.Event()

    async def query(**_kwargs) -> bool:
        coord._notify_callback(None, bytearray(_packet(0xAA, 0x05, [int(StatusReply.ColorMode.scene), 0x74, 0x08])))
        scene_received.set()
        return True

    with patch.object(coord, "_send_state_queries", new=AsyncMock(side_effect=query)) as sent:
        observation = asyncio.create_task(
            coord.async_observe_effect({"is_on": True, "scene_code": 2164, "effect": effect}, timeout=1.0)
        )
        try:
            await asyncio.wait_for(scene_received.wait(), timeout=1.0)
            assert coord.scene_code == 2164
            assert coord.effect == "racing game-a"
            assert not observation.done()
            coord._notify_callback(None, bytearray(_packet(0xAA, 0x01, [int(power)])))
            result = await observation
        finally:
            observation.cancel()
            await asyncio.gather(observation, return_exceptions=True)

    assert result is (None if power else False)
    sent.assert_awaited_once()
