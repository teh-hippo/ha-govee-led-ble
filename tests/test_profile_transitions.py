"""Profile changes invalidate batches and control completion, not accepted power."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.ha_govee_led_ble.const import (
    MODEL_PROFILES,
    ModelProfile,
    ReadDomain,
    device_profile,
)
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_refresh import RefreshRequest
from custom_components.ha_govee_led_ble.effect_deployments import PriorControlState
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_brightness,
    build_brightness_query,
    build_firmware_query,
    build_hardware_query,
    build_power,
    build_power_query,
    build_segment_query,
    build_subordinate_query,
    build_white_balance_query,
)
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from tests.coordinator_test_support import frame
from tests.test_h6199_capabilities import lifecycle as transition_lifecycle  # noqa: F401
from tests.test_h6199_capabilities import set_qualified_identity
from tests.test_h6199_pact1 import advertise

M = "custom_components.ha_govee_led_ble.coordinator"

PACT1_STATE_REPLIES = {
    frame("aa04"): frame("aa0488"),
    frame("aa0501"): frame("aa050b00"),
    **{frame(f"aaa2{group:02x}"): frame(f"aaa2{group:02x}" + "010203" * 4) for group in range(1, 5)},
}


@pytest.fixture
def brightness_profile_transition(hass, monkeypatch):
    model = "H9904"
    profile = ModelProfile(
        "Synthetic brightness profile",
        command_grammar="H617A",
        command_ack_grammar="H617A",
        status_grammar="H617A",
        command_operations=frozenset({"power", "brightness"}),
        profile_identity_fields=frozenset({"fw_version"}),
        read_domains=frozenset({ReadDomain.POWER, ReadDomain.BRIGHTNESS, ReadDomain.COLOUR_MODE}),
    )
    target = {"profile": profile}
    monkeypatch.setitem(MODEL_PROFILES, model, profile)
    monkeypatch.setattr(
        f"{M}.device_profile",
        lambda *_args, **_kwargs: target["profile"],
    )
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", model, configuration_url=None)
    coordinator._confirmed_identity_fields.add("fw_version")
    return coordinator, target, profile


@pytest.fixture
def brightness_client(brightness_profile_transition, monkeypatch):
    coordinator, target, profile = brightness_profile_transition
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(), disconnect=AsyncMock())
    coordinator._client = client
    coordinator._notification_token = object()
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(coordinator, "_renew_foreground_lease", lambda: None)
    return coordinator, client, target, profile


@pytest.mark.parametrize(
    ("source", "expected_source"),
    [
        ("initial", "initial"),
        ("restored", "restored"),
        ("delivered", "delivered"),
        ("observed", "retained"),
        ("retained", "retained"),
    ],
)
@pytest.mark.parametrize("preserve_state", [False, True])
def test_equivalent_profile_transition_retains_brightness_authority(
    brightness_profile_transition, source, expected_source, preserve_state
):
    coordinator, target, profile = brightness_profile_transition
    coordinator.brightness_pct = 42
    coordinator.brightness_pct_source = source
    coordinator._brightness_pct_known = source in {"observed", "delivered"}
    coordinator._field_revisions["brightness_pct"] = int(source in {"observed", "delivered"})
    target["profile"] = replace(profile, supports_rgb=True)
    coordinator.fw_version = "1.00.01"

    coordinator._resolve_device_profile(preserve_state=preserve_state)

    assert coordinator.brightness_pct == 42
    assert coordinator.brightness_pct_source == expected_source
    assert not coordinator._brightness_pct_known
    assert coordinator._field_revisions["brightness_pct"] == int(source in {"observed", "delivered"})


@pytest.mark.parametrize(
    "change",
    [
        {"command_grammar": "H6199"},
        {"command_ack_grammar": "H6199"},
        {"brightness_wire_range": (20, 254), "outbound_transform": lambda packet: packet},
        {"outbound_transform": lambda packet: packet},
        {"command_operations": frozenset({"power"})},
        {"read_domains": frozenset({ReadDomain.POWER})},
        {"status_grammar": "H6199"},
        {"bulk_status_grammar": "H60A"},
    ],
)
@pytest.mark.parametrize("preserve_state", [False, True])
def test_incompatible_profile_transition_resets_brightness(brightness_profile_transition, change, preserve_state):
    coordinator, target, profile = brightness_profile_transition
    coordinator.brightness_pct = 42
    coordinator.brightness_pct_source = "delivered"
    coordinator._brightness_pct_known = True
    target["profile"] = replace(profile, **change)
    coordinator.fw_version = "1.00.01"

    coordinator._resolve_device_profile(preserve_state=preserve_state)

    assert coordinator.brightness_pct == 100
    assert coordinator.brightness_pct_source == "initial"
    assert not coordinator._brightness_pct_known


@pytest.mark.parametrize(("value", "preserved"), [(0, False), (42, True)])
def test_zero_brightness_policy_only_invalidates_the_ambiguous_value(brightness_profile_transition, value, preserved):
    coordinator, target, profile = brightness_profile_transition
    coordinator.brightness_pct = value
    coordinator.brightness_pct_source = "restored"
    target["profile"] = replace(profile, brightness_zero_turns_off=True)
    coordinator.fw_version = "1.00.01"

    coordinator._resolve_device_profile()

    assert coordinator.brightness_pct == (value if preserved else 100)
    assert coordinator.brightness_pct_source == ("restored" if preserved else "initial")


@pytest.mark.parametrize("deadline", [-1, float("inf")])
def test_profile_transition_retires_brightness_expectations_without_losing_prior_authority(
    brightness_profile_transition, deadline
):
    coordinator, target, profile = brightness_profile_transition
    coordinator.brightness_pct = 42
    coordinator.brightness_pct_source = "delivered"
    coordinator._brightness_pct_known = True
    coordinator._expected_state["brightness_pct"] = (37, deadline)
    target["profile"] = replace(profile, supports_rgb=True)
    coordinator.fw_version = "1.00.01"

    coordinator._resolve_device_profile()

    assert coordinator.brightness_pct == 42
    assert coordinator.brightness_pct_source == "delivered"
    assert "brightness_pct" not in coordinator._expected_state
    assert not coordinator._brightness_pct_known


async def test_restored_write_only_brightness_survives_equivalent_profile(brightness_profile_transition, monkeypatch):
    coordinator, target, profile = brightness_profile_transition
    write_only = replace(profile, read_domains=frozenset({ReadDomain.POWER}))
    monkeypatch.setitem(MODEL_PROFILES, coordinator.model, write_only)
    coordinator.profile = target["profile"] = write_only
    light = GoveeBLELight(coordinator)
    monkeypatch.setattr(
        light,
        "async_get_last_state",
        AsyncMock(return_value=SimpleNamespace(attributes={"brightness": 128})),
    )

    await light._async_restore_brightness()
    assert coordinator.brightness_pct == 50
    assert coordinator.brightness_pct_source == "restored"
    assert coordinator._field_revisions == {}

    target["profile"] = replace(write_only, supports_rgb=True)
    coordinator.fw_version = "1.00.01"
    coordinator._resolve_device_profile()

    assert coordinator.brightness_pct == 50
    assert coordinator.brightness_pct_source == "restored"
    assert coordinator._field_revisions == {}


def test_observed_brightness_becomes_retained_across_equivalent_profile(brightness_profile_transition):
    coordinator, target, profile = brightness_profile_transition
    coordinator._notify_callback(None, bytearray(frame("aa0425")))
    assert coordinator.brightness_pct == 37
    assert coordinator.brightness_pct_source == "observed"
    target["profile"] = replace(profile, supports_rgb=True)
    coordinator.fw_version = "1.00.01"

    coordinator._resolve_device_profile()

    assert coordinator.brightness_pct == 37
    assert coordinator.brightness_pct_source == "retained"
    assert coordinator._field_revisions["brightness_pct"] == 1
    assert not coordinator._brightness_pct_known


async def test_brightness_pending_state_has_no_delivery_authority(brightness_client):
    coordinator, client, _, profile = brightness_client
    coordinator.brightness_pct = 20
    coordinator.brightness_pct_source = "restored"
    started, finish = asyncio.Event(), asyncio.Event()

    async def write(*_args, **_kwargs):
        started.set()
        await finish.wait()

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(coordinator.send_command(build_brightness(37, coordinator.model, profile=profile)))
    await started.wait()

    assert coordinator.brightness_pct == 37
    assert coordinator.brightness_pct_source == "pending"
    assert not coordinator._brightness_pct_known
    assert "brightness_pct" in coordinator._expected_state

    finish.set()
    await task
    assert coordinator.brightness_pct == 37
    assert coordinator.brightness_pct_source == "delivered"
    assert coordinator._brightness_pct_known
    assert coordinator._field_revisions.get("brightness_pct", 0) == 0


async def test_compatible_transition_during_brightness_write_keeps_pre_attempt_authority(brightness_client):
    coordinator, client, target, profile = brightness_client
    coordinator.brightness_pct = 20
    coordinator.brightness_pct_source = "restored"
    started, finish = asyncio.Event(), asyncio.Event()

    async def write(*_args, **_kwargs):
        started.set()
        await finish.wait()

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(coordinator.send_command(build_brightness(37, coordinator.model, profile=profile)))
    await started.wait()
    target["profile"] = replace(profile, supports_rgb=True)
    coordinator.fw_version = "1.00.01"
    coordinator._resolve_device_profile()
    finish.set()

    with pytest.raises(ValueError, match="profile changed during control write"):
        await task

    assert coordinator.brightness_pct == 20
    assert coordinator.brightness_pct_source == "restored"
    assert not coordinator._brightness_pct_known
    assert "brightness_pct" not in coordinator._expected_state
    assert coordinator._field_revisions.get("brightness_pct", 0) == 0


async def test_compatible_transition_during_retry_keeps_original_brightness_authority(brightness_client, monkeypatch):
    coordinator, client, target, profile = brightness_client
    coordinator.brightness_pct = 20
    coordinator.brightness_pct_source = "restored"
    started, finish = asyncio.Event(), asyncio.Event()
    attempts = 0

    async def write(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise BleakError("retryable first write")
        started.set()
        await finish.wait()

    client.write_gatt_char.side_effect = write
    monkeypatch.setattr(coordinator, "_disconnect_locked", AsyncMock())
    task = asyncio.create_task(coordinator.send_command(build_brightness(37, coordinator.model, profile=profile)))
    await started.wait()
    assert attempts == 2
    target["profile"] = replace(profile, supports_rgb=True)
    coordinator.fw_version = "1.00.01"
    coordinator._resolve_device_profile()
    finish.set()

    with pytest.raises(ValueError, match="profile changed during control write"):
        await task

    assert coordinator.brightness_pct == 20
    assert coordinator.brightness_pct_source == "restored"
    assert coordinator._pending_brightness_pct is None
    assert not coordinator._brightness_pct_known


async def test_mode_notification_during_failed_brightness_write_rolls_back_source(brightness_client):
    coordinator, client, _, profile = brightness_client
    coordinator.brightness_pct = 20
    coordinator.brightness_pct_source = "restored"

    async def write(*_args, **_kwargs):
        coordinator._notify_callback(
            None,
            bytearray.fromhex("aa0502ffffff0100000000000000000000000053"),
        )
        assert coordinator._field_revisions["color_mode"] == 1
        raise TimeoutError("ambiguous write")

    client.write_gatt_char.side_effect = write
    with pytest.raises(TimeoutError, match="ambiguous write"):
        with coordinator.control_state_checkpoint():
            await coordinator.send_command(build_brightness(37, coordinator.model, profile=profile))

    assert coordinator.brightness_pct == 20
    assert coordinator.brightness_pct_source == "restored"
    assert coordinator._pending_brightness_pct is None
    assert coordinator.capture_effect_control_state().brightness_pct_known is None


def test_incompatible_transition_invalidates_previous_authority_permanently(brightness_profile_transition):
    coordinator, target, profile = brightness_profile_transition
    coordinator.brightness_pct = 42
    coordinator.brightness_pct_source = "observed"
    coordinator._brightness_pct_known = True
    target["profile"] = replace(
        profile,
        brightness_wire_range=(20, 254),
        outbound_transform=lambda packet: packet,
    )
    coordinator.fw_version = "1.00.01"
    coordinator._resolve_device_profile()

    target["profile"] = profile
    coordinator.fw_version = "1.00.02"
    coordinator._resolve_device_profile()

    assert coordinator.brightness_pct == 100
    assert coordinator.brightness_pct_source == "initial"
    assert not coordinator._brightness_pct_known


@pytest.fixture
def device(hass, monkeypatch):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url=None)
    set_qualified_identity(c)
    c._present = True
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(), disconnect=AsyncMock())
    c._client = client
    monkeypatch.setattr(c, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(c, "_renew_foreground_lease", lambda: None)
    return c, client


async def test_colour_preparation_preserves_nontracked_protocol_identity(hass, monkeypatch):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6127", configuration_url=None)
    c.pact_type, c.pact_code = 10, 2
    c._resolve_device_profile()
    client = MagicMock(is_connected=True, disconnect=AsyncMock())
    monkeypatch.setattr(
        "custom_components.ha_govee_led_ble.coordinator.bluetooth.async_last_service_info",
        lambda *_args, **_kwargs: None,
    )

    async def connect():
        c._client = client
        c._notification_token = object()
        c._observe_identity_field("hw_version", "2.01.01")
        c._observe_identity_field("fw_version", "2.04.00")
        return client

    monkeypatch.setattr(c, "_ensure_connected", connect)
    try:
        guard = await c.async_prepare_identity_gated_control()
        guard()
        assert (c.pact_type, c.pact_code) == (10, 2)
        assert c.profile == device_profile("H6127", 10, 2, firmware="2.04.00", hardware="2.01.01")
    finally:
        await c.disconnect()


async def test_setup_rebuilds_after_narrowing_during_power_query(device):
    c, client = device
    power_query = build_power_query(c.model)

    async def write(_uuid, packet, **kwargs):
        if packet == power_query:
            advertise(c, 1)
            reply = frame("aa0101")
        else:
            reply = PACT1_STATE_REPLIES[packet]
        c._notify_callback(None, bytearray(reply))

    client.write_gatt_char.side_effect = write
    await c._async_update_data()
    assert c.profile == device_profile(c.model, 1, 1, firmware=c.fw_version, hardware=c.hw_version)
    assert c.is_on and c.available
    packets = [call.args[1] for call in client.write_gatt_char.await_args_list]
    assert packets.count(power_query) == 2
    assert set(packets) == {power_query, *PACT1_STATE_REPLIES}
    assert c._client is client and not c._lock.locked() and not c._control_arbiter.locked()


async def test_setup_transition_retry_is_bounded(device):
    c, client = device

    async def write(_uuid, packet, **kwargs):
        assert packet == build_power_query(c.model)
        advertise(c, 2 if c.pact_type == 1 else 1)
        c._notify_callback(None, bytearray(frame("aa0101")))

    client.write_gatt_char.side_effect = write
    with pytest.raises(UpdateFailed):
        await c._async_update_data()
    assert client.write_gatt_char.await_count == 2
    assert c._client is None and client.disconnect.await_count == 1


async def test_identity_batch_rebuilds_with_real_setup(transition_lifecycle):  # noqa: F811
    c, replies, clients, packets = transition_lifecycle
    replies.update(PACT1_STATE_REPLIES)
    original = c._async_write_packet
    changed = False

    async def write(client, packet, **kwargs):
        nonlocal changed
        await original(client, packet, **kwargs)
        if packet == build_hardware_query(c.model) and not changed:
            advertise(c, 1)
            changed = True

    c._async_write_packet = write
    await c._async_update_data()
    assert c.is_on and c.available
    assert c.profile == device_profile(c.model, 1, 1, firmware=c.fw_version, hardware=c.hw_version)
    assert set(packets) == {
        build_power_query(c.model),
        build_hardware_query(c.model),
        build_firmware_query(c.model),
        *PACT1_STATE_REPLIES,
    }
    assert len(clients) == 1 and c._client is None


@pytest.mark.parametrize("domain", [0x06, 0x07, 0x20, 0x21])
async def test_setup_retries_late_identity(transition_lifecycle, domain, virtual_clock):  # noqa: F811
    c, replies, clients, packets = transition_lifecycle
    query = (
        build_firmware_query(c.model)
        if domain == 0x06
        else build_hardware_query(c.model)
        if domain == 0x07
        else build_subordinate_query(domain, c.model)
    )
    delayed = replies.pop(query)
    original = c._async_write_packet

    async def write(client, packet, **kwargs):
        nonlocal delayed
        await original(client, packet, **kwargs)
        if packet == build_power_query(c.model) and delayed is not None:
            c._notify_callback(None, bytearray(delayed))
            delayed = None

    c._async_write_packet = write
    await c._async_update_data()

    assert c.is_on and c.available and c.brightness_pct == 50
    assert packets.count(build_power_query(c.model)) == 2
    assert len(clients) == 1 and c._client is None


@pytest.mark.parametrize("domain", [0x20, 0x21])
@pytest.mark.parametrize("during_collection", [False, True])
async def test_setup_retains_completed_segments_after_late_identity(
    transition_lifecycle,  # noqa: F811
    domain,
    during_collection,
    virtual_clock,
):
    c, replies, clients, packets = transition_lifecycle
    delayed = replies.pop(build_subordinate_query(domain, c.model))
    original = c._async_write_packet
    timers = []

    async def write(client, packet, **kwargs):
        await original(client, packet, **kwargs)
        if packet == build_segment_query(c.profile.segment_group_count, c.model):
            if during_collection:
                timers.append(
                    asyncio.get_running_loop().call_later(0.025, c._notify_callback, None, bytearray(delayed))
                )
            else:
                c._notify_callback(None, bytearray(delayed))

    c._async_write_packet = write
    try:
        await c._async_update_data()
        assert c.is_on and c.available and c.brightness_pct == 50
        assert packets.count(build_power_query(c.model)) == 2
        assert len(clients) == 1 and c._client is None
    finally:
        for timer in timers:
            timer.cancel()


async def test_setup_collects_dispatched_segments_before_abandoning_native_queries(transition_lifecycle, virtual_clock):  # noqa: F811
    c, _, clients, packets = transition_lifecycle
    original = c._async_write_packet
    changed = False

    async def write(client, packet, **kwargs):
        nonlocal changed
        await original(client, packet, **kwargs)
        if not changed and packet == build_segment_query(c.profile.segment_group_count, c.model):
            c._notify_callback(None, bytearray(frame("aa21" + b"1.00.34".hex())))
            changed = True

    c._async_write_packet = write
    await c._async_update_data()
    assert c.is_on and c.available
    assert packets.count(build_power_query(c.model)) == 2
    assert len(clients) == 1 and c._client is None
    assert not any(packet[:2] in {b"\xaa\x30", b"\xaa\x31", b"\xaa\xa3", b"\xaa\x32"} for packet in packets)


async def test_setup_identity_retry_is_bounded(transition_lifecycle, virtual_clock):  # noqa: F811
    c, _, clients, packets = transition_lifecycle
    original = c._async_write_packet
    revision = 0

    async def write(client, packet, **kwargs):
        nonlocal revision
        await original(client, packet, **kwargs)
        if packet == build_power_query(c.model):
            revision += 1
            c._notify_callback(None, bytearray(frame("aa20" + f"1.03.{revision:02}".encode().hex())))

    c._async_write_packet = write
    with pytest.raises(UpdateFailed):
        await c._async_update_data()

    assert packets.count(build_power_query(c.model)) == 2
    assert len(clients) == 1 and c._client is None


@pytest.mark.parametrize("roundtrip", [False, True])
@pytest.mark.parametrize("operation", ["scene", "brightness", "power"])
async def test_transition_during_awaited_control_does_not_reinstall_state(device, monkeypatch, roundtrip, operation):
    c, client = device
    c.is_on = True
    c.brightness_pct = 20
    if operation == "scene":
        monkeypatch.setattr(
            c,
            "async_prepare_static_baseline",
            AsyncMock(
                return_value=PriorControlState(
                    mode="colour",
                    is_on=True,
                    brightness_pct=20,
                    rgb_color=(12, 34, 56),
                    static_rgb_known=True,
                    segment_colors=((12, 34, 56),) * c.profile.segment_count,
                    segment_brightness=(100,) * c.profile.segment_count,
                    segment_kelvin=(0,) * c.profile.segment_count,
                )
            ),
        )
    light = GoveeBLELight(c)
    started, finish = asyncio.Event(), asyncio.Event()

    async def write(_uuid, packet, **kwargs):
        started.set()
        await finish.wait()

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(
        c.async_apply_native_scene("forest", verify=False)
        if operation == "scene"
        else light._async_turn_on(brightness=128)
        if operation == "brightness"
        else c.send_command(build_power(False, c.model))
    )
    await started.wait()
    advertise(c, 1)
    c._notify_callback(None, bytearray(frame("aa0100")))
    if roundtrip:
        advertise(c, 2)
    finish.set()
    with pytest.raises(
        HomeAssistantError if operation == "brightness" else ValueError,
        match=None if operation == "brightness" else "profile changed",
    ):
        await task
    assert not c.is_on  # Accepted power must survive the failed control transaction.
    assert c.brightness_pct == 100 and c.effect is None and c.scene_code is None
    assert c.color_mode is None
    assert client.write_gatt_char.await_count == 1
    assert not c._lock.locked() and not c._control_arbiter.locked()


@pytest.mark.parametrize("failure", ["optional", "brightness", "required", "disconnect", "value", "identity"])
async def test_keepalive_uses_basic_required_policy(device, monkeypatch, failure):
    c, client = device
    c._keep_alive_ticks = 2
    ticks = 0

    async def tick(_delay):
        nonlocal ticks
        ticks += 1
        if ticks > 1:
            raise asyncio.CancelledError

    async def write(_uuid, packet, **kwargs):
        bad = (
            build_power_query(c.model)
            if failure == "required"
            else build_brightness_query(c.model)
            if failure == "brightness"
            else build_white_balance_query(c.model)
        )
        if packet == bad:
            if failure == "identity":
                c._notify_callback(None, bytearray(frame("aa21" + b"1.00.34".hex())))
                return
            if failure == "disconnect":
                client.is_connected = False
            raise ValueError("unexpected failure") if failure == "value" else BleakError("query failed")
        if packet == build_power_query(c.model):
            c._notify_callback(None, bytearray(frame("aa0101")))

    monkeypatch.setattr("custom_components.ha_govee_led_ble.coordinator.asyncio.sleep", tick)
    client.write_gatt_char.side_effect = write
    try:
        if failure == "value":
            with pytest.raises(ValueError, match="unexpected"):
                await c._keep_alive_loop()
        else:
            await c._keep_alive_loop()
            assert (c._client is None) is (failure in {"required", "disconnect"})
    finally:
        monkeypatch.undo()
    if failure in {"optional", "brightness", "identity"}:
        assert c._client is client and c.is_on and ticks == 2
    assert not c._lock.locked() and not c._control_arbiter.locked()


async def test_identity_change_during_control_invalidates_completion_without_profile_change(device):
    c, client = device
    profile = c.profile

    async def write(_uuid, packet, **kwargs):
        c._notify_callback(None, bytearray(frame("aa21" + b"1.00.34".hex())))

    client.write_gatt_char.side_effect = write
    with pytest.raises(ValueError, match="identity changed during control"):
        await c.send_command(build_power(False, c.model))
    assert c.profile is profile and c.subordinate_21_version == "1.00.34"
    client.write_gatt_char.assert_awaited_once()


async def test_targeted_register_remains_strict(device):
    c, client = device
    client.write_gatt_char.side_effect = BleakError("white balance failed")
    assert not await c.refresh_state(RefreshRequest(display_settings=frozenset({"white_balance"})))
    assert client.write_gatt_char.await_count == 1 and c._client is None


@pytest.mark.parametrize("transition", ["profile", "identity"])
async def test_refresh_transition_never_confirms_old_expectation(device, transition):
    c, client = device

    async def write(_uuid, packet, **kwargs):
        assert packet == build_brightness_query(c.model)
        c._notify_callback(None, bytearray(frame("aa0432")))
        if transition == "profile":
            advertise(c, 1)
        else:
            c._notify_callback(None, bytearray(frame("aa21" + b"1.00.34".hex())))

    client.write_gatt_char.side_effect = write
    assert not await c.refresh_state(RefreshRequest(brightness=50))
    assert c.brightness_pct == (100 if transition == "profile" else 50) and c._client is client
