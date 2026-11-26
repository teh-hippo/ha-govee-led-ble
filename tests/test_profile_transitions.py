"""Profile changes invalidate batches and control completion, not accepted power."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.ha_govee_led_ble.const import BrightnessEvidence, ModelProfile, ReadDomain, device_profile
from custom_components.ha_govee_led_ble.coordinator import (
    GoveeBLECoordinator,
    _brightness_value_survives_profile_transition,
    _equal_profile_requires_identity_reset,
)
from custom_components.ha_govee_led_ble.coordinator_refresh import RefreshRequest
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode
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

PACT1_STATE_REPLIES = {
    frame("aa04"): frame("aa0488"),
    frame("aa0501"): frame("aa050b00"),
    **{frame(f"aaa2{group:02x}"): frame(f"aaa2{group:02x}" + "010203" * 4) for group in range(1, 5)},
}


def _identity_transform(packet: bytes) -> bytes:
    return packet


def _changed_brightness_transform(packet: bytes) -> bytes:
    return b"\x00" + packet


def _brightness_profile(**changes):
    profile = ModelProfile(
        "Generic brightness profile",
        command_grammar="H617A",
        command_ack_grammar="H617A",
        command_operations=frozenset({"power", "brightness"}),
        status_grammar="generic-status",
        brightness_wire_range=(20, 254),
        outbound_transform=_identity_transform,
        read_domains=frozenset({ReadDomain.POWER, ReadDomain.BRIGHTNESS}),
        profile_pact_dependent=True,
    )
    return replace(profile, **changes)


@pytest.mark.parametrize(
    "evidence",
    [
        BrightnessEvidence.DEFAULT,
        BrightnessEvidence.RESTORED,
        BrightnessEvidence.RETAINED,
        BrightnessEvidence.OBSERVED,
        BrightnessEvidence.DELIVERED,
    ],
)
def test_brightness_presentation_survives_compatible_generic_transition(evidence):
    profile = _brightness_profile()
    assert _brightness_value_survives_profile_transition(profile, profile, evidence)


@pytest.mark.parametrize("evidence", [BrightnessEvidence.PENDING, BrightnessEvidence.UNKNOWN])
def test_unresolved_brightness_does_not_survive_generic_transition(evidence):
    profile = _brightness_profile()
    assert not _brightness_value_survives_profile_transition(profile, profile, evidence)


@pytest.mark.parametrize(
    "target",
    [
        _brightness_profile(command_grammar="changed-command"),
        _brightness_profile(brightness_wire_range=(1, 100)),
        _brightness_profile(command_operations=frozenset({"power"})),
        _brightness_profile(outbound_transform=_changed_brightness_transform),
    ],
)
@pytest.mark.parametrize("evidence", [BrightnessEvidence.RESTORED, BrightnessEvidence.DELIVERED])
def test_brightness_presentation_requires_compatible_write_semantics(target, evidence):
    assert not _brightness_value_survives_profile_transition(_brightness_profile(), target, evidence)


def test_brightness_compatibility_ignores_unrelated_transform_identity():
    previous = _brightness_profile()
    equivalent = replace(previous, outbound_transform=lambda packet: packet)

    assert _brightness_value_survives_profile_transition(previous, equivalent, BrightnessEvidence.DELIVERED)


def test_observed_brightness_requires_compatible_read_semantics():
    previous = _brightness_profile()
    changed_status = replace(previous, status_grammar="changed-status")
    write_only = replace(previous, read_domains=frozenset({ReadDomain.POWER}))

    assert not _brightness_value_survives_profile_transition(previous, changed_status, BrightnessEvidence.OBSERVED)
    assert not _brightness_value_survives_profile_transition(previous, write_only, BrightnessEvidence.OBSERVED)
    assert _brightness_value_survives_profile_transition(previous, changed_status, BrightnessEvidence.DELIVERED)
    assert _brightness_value_survives_profile_transition(previous, write_only, BrightnessEvidence.DELIVERED)


def test_equal_basic_profile_resets_only_for_real_stateful_identity_change():
    basic = _brightness_profile(command_operations=frozenset({"power", "brightness"}))
    full = replace(basic, command_operations=frozenset({"power", "brightness", "static"}))

    assert _equal_profile_requires_identity_reset(basic, identity_changed=True, preserve_state=False)
    assert not _equal_profile_requires_identity_reset(basic, identity_changed=False, preserve_state=False)
    assert not _equal_profile_requires_identity_reset(basic, identity_changed=True, preserve_state=True)
    assert not _equal_profile_requires_identity_reset(full, identity_changed=True, preserve_state=False)


@pytest.fixture
def device(hass, monkeypatch, virtual_clock):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url=None)
    set_qualified_identity(c)
    c._present = True
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(), disconnect=AsyncMock())
    c._client = client
    monkeypatch.setattr(c, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(c, "_renew_foreground_lease", lambda: None)
    return c, client


@pytest.mark.parametrize(
    ("evidence", "expected_value", "expected_evidence"),
    [
        (BrightnessEvidence.RESTORED, 44, BrightnessEvidence.RESTORED),
        (BrightnessEvidence.OBSERVED, 44, BrightnessEvidence.RETAINED),
        (BrightnessEvidence.DELIVERED, 44, BrightnessEvidence.RETAINED),
        (BrightnessEvidence.PENDING, 100, BrightnessEvidence.DEFAULT),
        (BrightnessEvidence.UNKNOWN, 100, BrightnessEvidence.DEFAULT),
    ],
)
def test_profile_transition_applies_generic_brightness_provenance(
    hass, monkeypatch, evidence, expected_value, expected_evidence
):
    previous = _brightness_profile()
    target = replace(previous, segment_count=2)
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H617A", configuration_url=None)
    coordinator.profile = previous
    coordinator.brightness_pct = 44
    coordinator._set_brightness_evidence(evidence)
    monkeypatch.setattr(
        "custom_components.ha_govee_led_ble.coordinator.get_profile",
        lambda _model: previous,
    )
    monkeypatch.setattr(
        "custom_components.ha_govee_led_ble.coordinator.device_profile",
        lambda *_args, **_kwargs: target,
    )

    coordinator._resolve_device_profile(identity_changed=True)

    assert coordinator.brightness_pct == expected_value
    assert coordinator._brightness_pct_evidence is expected_evidence
    assert not coordinator._brightness_pct_known


def test_equal_basic_profile_reinitializes_only_for_real_identity_transition(hass, monkeypatch):
    profile = _brightness_profile(command_operations=frozenset({"power", "brightness"}))
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H617A", configuration_url=None)
    coordinator.profile = profile
    coordinator.color_mode = ParsedMode.COLOUR
    monkeypatch.setattr(
        "custom_components.ha_govee_led_ble.coordinator.get_profile",
        lambda _model: profile,
    )
    monkeypatch.setattr(
        "custom_components.ha_govee_led_ble.coordinator.device_profile",
        lambda *_args, **_kwargs: profile,
    )

    generation = coordinator._profile_generation
    coordinator._resolve_device_profile(identity_changed=False)
    assert coordinator._profile_generation == generation and coordinator.color_mode is ParsedMode.COLOUR

    coordinator._resolve_device_profile(identity_changed=True)
    assert coordinator._profile_generation == generation + 1 and coordinator.color_mode is None


@pytest.mark.parametrize(
    ("model", "physical_ic_count", "v0_at_hardware_1_00_02"),
    [("H617C", 30, False), ("H617E", 30, True), ("H617F", 45, True)],
)
def test_goods_type_70_scene_transitions_preserve_ordinary_control_state(
    hass, model, physical_ic_count, v0_at_hardware_1_00_02
):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", model, configuration_url=None)
    coordinator._client = MagicMock(is_connected=True)
    coordinator.is_on = True
    coordinator.brightness_pct = 37
    coordinator.rgb_color = (1, 2, 3)
    coordinator.effect = "existing"

    coordinator._observe_identity_field("fw_version", "1.06.00")
    coordinator._observe_identity_field("hw_version", "1.00.02")
    assert coordinator.profile.scene_command_versions == {0, 1}
    assert coordinator.profile.rgbic_scene_v0 is v0_at_hardware_1_00_02

    coordinator._observe_identity_field("hw_version", "1.00.03")
    assert coordinator.profile.scene_command_versions == {0, 1}
    assert coordinator.profile.rgbic_scene_v0 is False
    assert coordinator.profile.physical_ic_count == physical_ic_count
    assert coordinator.is_on and coordinator.brightness_pct == 37
    assert coordinator.rgb_color == (1, 2, 3) and coordinator.effect == "existing"

    coordinator._observe_identity_field("fw_version", "1.05.99")
    assert coordinator.profile.scene_command_versions == {0}
    assert coordinator.profile.rgbic_scene_v0 is True
    assert coordinator.effect_authorization_profile.scene_command_versions == {0}
    assert coordinator.effect_authorization_profile.supports_rgb


@pytest.mark.parametrize("model", ["H617C", "H617E", "H617F"])
def test_goods_type_70_unconfirmed_scene_identity_revokes_only_scene_authority(hass, model):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", model, configuration_url=None)
    coordinator._client = MagicMock(is_connected=True)
    coordinator._observe_identity_field("fw_version", "1.06.00")
    coordinator._observe_identity_field("hw_version", "1.00.03")

    assert coordinator.effect_authorization_profile.scene_command_versions == {0, 1}
    assert coordinator.effect_authorization_profile.rgbic_scene_v0 is False

    coordinator._confirmed_identity_fields.remove("hw_version")

    assert coordinator.profile.scene_command_versions == {0, 1}
    assert coordinator.effect_authorization_profile.scene_command_versions == {0}
    assert coordinator.effect_authorization_profile.supports_rgb


async def test_duplicate_identity_resolution_does_not_interrupt_basic_brightness_write(hass, monkeypatch):
    profile = _brightness_profile(
        command_operations=frozenset({"power", "brightness"}),
        brightness_wire_range=None,
        outbound_transform=None,
    )
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H617A", configuration_url=None)
    coordinator.profile = profile
    monkeypatch.setattr(
        "custom_components.ha_govee_led_ble.coordinator.get_profile",
        lambda _model: profile,
    )
    monkeypatch.setattr(
        "custom_components.ha_govee_led_ble.coordinator.device_profile",
        lambda *_args, **_kwargs: profile,
    )
    started, finish = asyncio.Event(), asyncio.Event()

    async def pause_write(*_args, **_kwargs):
        started.set()
        await finish.wait()

    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=pause_write))
    task = asyncio.create_task(
        coordinator._async_write_packet(client, build_brightness(50, "H617A", profile=profile), arm_expected=True)
    )
    await started.wait()
    generation = coordinator._profile_generation
    expectation = coordinator._expected_state["brightness_pct"]

    coordinator._resolve_device_profile(identity_changed=False)

    assert coordinator._profile_generation == generation
    assert coordinator._expected_state["brightness_pct"] == expectation
    finish.set()
    await task
    assert coordinator._brightness_pct_evidence is BrightnessEvidence.DELIVERED


def test_advertisement_caller_distinguishes_real_and_duplicate_identity_change(hass, monkeypatch):
    profile = _brightness_profile(command_operations=frozenset({"power", "brightness"}))
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H617A", configuration_url=None)
    coordinator.profile = profile
    coordinator.pact_type, coordinator.pact_code = 3, 1
    coordinator.brightness_pct = 50
    coordinator._set_brightness_evidence(BrightnessEvidence.DELIVERED)
    coordinator._expected_state["brightness_pct"] = (50, 1)
    monkeypatch.setattr(
        "custom_components.ha_govee_led_ble.coordinator.get_profile",
        lambda _model: profile,
    )
    monkeypatch.setattr(
        "custom_components.ha_govee_led_ble.coordinator.device_profile",
        lambda *_args, **_kwargs: profile,
    )
    advertisement = SimpleNamespace(
        pacts={(3, 2)},
        invalid_version_seen=False,
        supports_encryption=False,
        supports_plaintext=False,
    )
    monkeypatch.setattr(
        "custom_components.ha_govee_led_ble.coordinator.parse_govee_advertisement",
        lambda _data: advertisement,
    )
    service_info = SimpleNamespace(name=None, manufacturer_data={1: b""})
    generation = coordinator._profile_generation

    coordinator._note_advertisement(service_info)

    assert coordinator._profile_generation == generation + 1
    assert coordinator.brightness_pct == 50
    assert coordinator._brightness_pct_evidence is BrightnessEvidence.RETAINED
    assert not coordinator._brightness_pct_known
    assert "brightness_pct" not in coordinator._expected_state

    coordinator._set_brightness_evidence(BrightnessEvidence.DELIVERED)
    coordinator._expected_state["brightness_pct"] = (50, 1)
    coordinator._note_advertisement(service_info)

    assert coordinator._profile_generation == generation + 1
    assert coordinator._brightness_pct_evidence is BrightnessEvidence.DELIVERED
    assert coordinator._expected_state["brightness_pct"] == (50, 1)


def test_restored_and_retained_brightness_are_not_recovery_authority(hass):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H617A", configuration_url=None)
    coordinator._install_restored_brightness(44)
    assert coordinator.capture_effect_control_state().brightness_pct_known is False

    coordinator._set_brightness_evidence(BrightnessEvidence.DELIVERED)
    assert coordinator.capture_effect_control_state().brightness_pct_known is None

    coordinator._retire_brightness_authority()
    assert coordinator._brightness_pct_evidence is BrightnessEvidence.RETAINED
    assert coordinator.capture_effect_control_state().brightness_pct_known is False


async def test_brightness_evidence_tracks_delivery_without_expiring_reorder_protection(hass):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H617A", configuration_url=None)
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())

    await coordinator._async_write_packet(client, build_brightness(50, "H617A"), arm_expected=True)

    assert coordinator.brightness_pct == 50
    assert coordinator._brightness_pct_evidence is BrightnessEvidence.DELIVERED
    assert coordinator._brightness_pct_known and "brightness_pct" in coordinator._expected_state

    coordinator._notify_callback(None, bytearray(frame("aa0432")))

    assert coordinator._brightness_pct_evidence is BrightnessEvidence.OBSERVED
    assert coordinator._brightness_pct_known and "brightness_pct" in coordinator._expected_state


@pytest.mark.parametrize("failure", [RuntimeError("write failed"), asyncio.CancelledError()])
async def test_brightness_physical_failure_invalidates_same_value_authority(hass, failure):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H617A", configuration_url=None)
    coordinator.brightness_pct = 50
    coordinator._set_brightness_evidence(BrightnessEvidence.OBSERVED)
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=failure))

    with pytest.raises(type(failure)):
        await coordinator._async_write_packet(client, build_brightness(50, "H617A"), arm_expected=True)

    assert coordinator.brightness_pct == 50
    assert coordinator._brightness_pct_evidence is BrightnessEvidence.UNKNOWN
    assert not coordinator._brightness_pct_known


async def test_brightness_late_delivery_cannot_outlive_profile_generation(hass):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H617A", configuration_url=None)

    async def advance_during_write(*_args, **_kwargs):
        coordinator._advance_profile_generation()

    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=advance_during_write))
    with pytest.raises(ValueError, match="profile changed during control write"):
        await coordinator._async_write_packet(client, build_brightness(50, "H617A"), arm_expected=True)

    assert coordinator._brightness_pct_evidence is BrightnessEvidence.UNKNOWN
    assert not coordinator._brightness_pct_known


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
    assert client.write_gatt_char.await_count == 4
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

    assert packets.count(build_power_query(c.model)) == 4
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
