"""Synthetic exact profiles prove reuse, not compatibility with real products."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.core import ServiceCall
from homeassistant.exceptions import ServiceValidationError

from custom_components.ha_govee_led_ble.const import (
    DOMAIN,
    MODEL_PROFILES,
    ModelProfile,
    ReadDomain,
    device_profile,
    get_profile,
)
from custom_components.ha_govee_led_ble.dreamview import (
    DREAMVIEW_READ_SETTINGS,
    build_dreamview_command,
    build_dreamview_group,
    build_dreamview_query,
    parse_dreamview_status,
)
from custom_components.ha_govee_led_ble.dreamview_services import _async_dreamview_service
from custom_components.ha_govee_led_ble.generated_protocol_adapter import build_brightness, build_power
from custom_components.ha_govee_led_ble.protocol_core import _STATUS_ROOTS, H6199StatusReply
from custom_components.ha_govee_led_ble.transport import reassemble_a3
from tests.test_govee_encryption import client as ble_client
from tests.test_h6099_dreamview import coordinator, frame, member


@pytest.fixture
def profiles(monkeypatch):
    monkeypatch.setitem(_STATUS_ROOTS, "dreamview-test-status", ("dreamview-test-status", H6199StatusReply))
    for model, capacity in (("H9901", 2), ("H9902", 9)):
        monkeypatch.setitem(
            MODEL_PROFILES,
            model,
            ModelProfile(
                "Synthetic DreamView",
                command_grammar="H6199",
                command_operations=frozenset({"power"}),
                status_grammar="dreamview-test-status",
                read_domains=frozenset({ReadDomain.POWER}),
                dreamview_grammar="H6099",
                dreamview_operations=frozenset({"replace_group", "member_brightness", "member_connect"}),
                dreamview_reads=frozenset({"member_brightness", "member_connect", "video_settings"}),
                dreamview_max_sub_devices=capacity,
            ),
        )


@pytest.mark.parametrize("model", ["H9901", "H9902"])
async def test_capacity_service_and_restricted_physical_writer(hass, profiles, model):
    c = coordinator(hass, model)
    client = ble_client()
    c._client = client
    c._ensure_connected = AsyncMock(return_value=client)
    c._renew_foreground_lease = Mock()
    entity = SimpleNamespace(coordinator=c, _async_supersede_preview=AsyncMock())
    capacity = c.profile.dreamview_max_sub_devices
    members = [member(address=f"00:00:00:00:00:{i:02x}").as_dict() for i in range(capacity)]

    async def service(name, data):
        return await _async_dreamview_service(entity, ServiceCall(hass, DOMAIN, name, data), name=name)

    await service("replace_dreamview_group", {"members": members})
    packets = [call.args[1] for call in client.write_gatt_char.await_args_list]
    assert reassemble_a3(packets)[3] == capacity
    assert (await c._dreamview_store.async_load())["members"] == members
    await service("set_dreamview_member_brightness", {"index": capacity - 1, "level": 42})
    assert client.write_gatt_char.call_args.args[1] == frame(f"3360032a{capacity - 1:02x}")
    await service("set_dreamview_member_connect", {"index": capacity - 1, "connected": True})
    assert client.write_gatt_char.call_args.args[1] == frame(f"336005{capacity - 1:02x}01")
    await c._async_write_packet(client, build_power(True, model))
    with pytest.raises(ValueError):
        await c._async_write_packet(client, build_brightness(50, model))

    entity._async_supersede_preview.reset_mock()
    client.write_gatt_char.reset_mock()
    c._dreamview_store.async_save = AsyncMock()
    before = c._control_arbiter.preview_generation
    for name, data in (
        ("replace_dreamview_group", {"members": [*members, member().as_dict()]}),
        ("set_dreamview_member_brightness", {"index": capacity, "level": 42}),
        ("set_dreamview_member_connect", {"index": capacity, "connected": True}),
        ("set_dreamview_switch", {"enabled": True}),
        ("delete_dreamview_group", {}),
    ):
        with pytest.raises(ServiceValidationError):
            await service(name, data)
    entity._async_supersede_preview.assert_not_awaited()
    client.write_gatt_char.assert_not_awaited()
    c._dreamview_store.async_save.assert_not_awaited()
    assert c._control_arbiter.preview_generation == before


@pytest.mark.parametrize("basic_reads", [True, False])
async def test_partial_reads_connect_and_route_independently(hass, profiles, monkeypatch, basic_reads):
    profile = replace(
        get_profile("H9901"),
        dreamview_operations=frozenset(),
        dreamview_max_sub_devices=0,
        read_domains=frozenset({ReadDomain.POWER}) if basic_reads else frozenset(),
    )
    monkeypatch.setitem(MODEL_PROFILES, "H9901", profile)
    c = coordinator(hass, "H9901")
    client = ble_client()
    c._reset_disconnect_timer = Mock()
    c._start_keep_alive = Mock()
    with patch("custom_components.ha_govee_led_ble.coordinator.async_establish_ble_connection", return_value=client):
        await c._ensure_connected()
    client.start_notify.assert_awaited_once()
    receive = client.start_notify.call_args.args[1]

    async def transmit(_uuid, packet, **kwargs):
        if packet == build_dreamview_query("member_brightness", profile):
            receive(None, bytearray(frame("aa600301")))
        if packet == build_dreamview_query("member_connect", profile):
            receive(None, bytearray(frame("aa600501")))
        receive(None, bytearray(frame("aa600901")))  # Undeclared read must not become an observation.

    client.write_gatt_char.side_effect = transmit
    client.write_gatt_char.reset_mock()
    result = await c.async_read_dreamview_state(timeout=0)
    assert {call.args[1] for call in client.write_gatt_char.await_args_list} == {
        build_dreamview_query(setting, profile) for setting in profile.dreamview_reads
    }
    assert len(result["observed"]["member_brightness"]["brightness_bytes"]) == 16
    assert len(result["observed"]["member_connect"]["connection_bytes"]) == 10
    assert set(result["observed"]) == {"member_brightness", "member_connect"}
    assert result["missing_reads"] == ["sample", "video_settings"]
    assert result["unsupported_reads"] == sorted(set(DREAMVIEW_READ_SETTINGS) - profile.dreamview_reads)
    assert result["authored"] is None and not result["membership_confirmed"]
    assert result["slot_identities"] == "unknown"
    if basic_reads:
        receive(None, bytearray(frame("aa0101")))
        assert c.is_on


@pytest.mark.parametrize("operation", ["replace", "index", "write", "read"])
@pytest.mark.parametrize("change_at", ["connect", "transform"])
async def test_effective_profile_rechecked_before_physical_attempt(hass, profiles, operation, change_at):
    c = coordinator(hass, "H9902")
    client = ble_client()
    c._client = client
    c._renew_foreground_lease = Mock()
    c._ensure_connected = AsyncMock(return_value=client)
    original = c.profile
    reduced = (
        replace(original, dreamview_max_sub_devices=1)
        if operation in {"replace", "index"}
        else replace(original, dreamview_operations=frozenset(), dreamview_reads=frozenset())
    )

    async def connect():
        c.profile = reduced
        return client

    def transform(packet):
        c.profile = reduced
        return packet

    if change_at == "connect":
        c._ensure_connected.side_effect = connect
    else:
        c.profile = replace(original, outbound_transform=transform)
    with pytest.raises(ValueError):
        if operation == "replace":
            await c.async_replace_dreamview_group((member(), member(address=None, name="lamp")))
        elif operation in {"index", "write"}:
            await c.async_set_dreamview("member_brightness", {"index": 1, "level": 42})
        else:
            await c.async_read_dreamview_state(timeout=0)
    client.write_gatt_char.assert_not_awaited()

    if operation != "read":
        assert c._dreamview_last_write == "not_attempted"


async def test_empty_declarations_and_capacity_independent_settings(hass, profiles):
    c = coordinator(hass, "H9901")
    c.profile = replace(c.profile, dreamview_operations=frozenset(), dreamview_reads=frozenset())
    c.async_write_effect_sequence = AsyncMock()
    with pytest.raises(ValueError):
        build_dreamview_group((member(),), c.profile)
    with pytest.raises(ValueError):
        await c.async_read_dreamview_state(timeout=0)
    c.async_write_effect_sequence.assert_not_awaited()
    for setting, values in (
        ("switch_group", {"enabled": True}),
        ("same_brightness", {"enabled": True}),
        ("saturation", {"saturation": 50}),
        ("video_settings", {"apply_area": 1, "content_mode": 2}),
        ("sound", {"enabled": True, "softness": 50}),
        ("delete_group", {}),
    ):
        with pytest.raises(ValueError):
            build_dreamview_command(setting, values, c.profile)
        profile = replace(c.profile, dreamview_operations=frozenset({setting}), dreamview_max_sub_devices=0)
        assert build_dreamview_command(setting, values, profile) == build_dreamview_command(
            setting, values, get_profile("H6099")
        )


async def test_h6099_service_still_rejects_eighth_slot_before_preview(hass):
    c = coordinator(hass)
    entity = SimpleNamespace(coordinator=c, _async_supersede_preview=AsyncMock())
    with pytest.raises(ServiceValidationError):
        await _async_dreamview_service(
            entity,
            ServiceCall(hass, DOMAIN, "set_dreamview_member_brightness", {"index": 7, "level": 50}),
            name="set_dreamview_member_brightness",
        )
    entity._async_supersede_preview.assert_not_awaited()


async def test_h66a0_dreamview_profile_capacity_and_synthetic_group(hass):
    h66a0 = get_profile("H66A0")
    assert h66a0.dreamview_grammar == "H6099"
    assert h66a0.dreamview_max_sub_devices == 10
    ten = tuple(member(address=f"00:00:00:00:00:{i:02x}") for i in range(10))
    assert build_dreamview_group(ten, h66a0)
    with pytest.raises(ValueError):
        build_dreamview_group((*ten, member(address="00:00:00:00:00:0a")), h66a0)
    assert build_dreamview_command("member_brightness", {"index": 9, "level": 80}, h66a0) == frame("3360035009")
    assert build_dreamview_command("member_connect", {"index": 9, "connected": True}, h66a0) == frame("3360050901")
    with pytest.raises(ValueError):
        build_dreamview_command("member_brightness", {"index": 10, "level": 80}, h66a0)

    # Synthetic members exercise the two-member layout reported in issue #408.
    h1a42_member = member(
        address="AA:BB:CC:DD:EE:01",
        cmd_ver=1,
        is_rgbic=True,
        zones=(5, 4, 3, 2, 1),
    )
    h61f5_member = member(
        address="AA:BB:CC:DD:EE:02",
        cmd_ver=1,
        is_rgbic=True,
        zones=(6, 7, 8, 9, 10),
    )
    packets = build_dreamview_group((h1a42_member, h61f5_member), h66a0)
    assert len(packets) == 2
    assert packets[0][:6] == bytes.fromhex("a30001025002")
    assert packets[1][:2] == b"\xa3\xff"


@pytest.mark.parametrize(
    ("setting", "values", "write_hex", "query_hex"),
    [
        (
            "switch_group",
            {"enabled": True},
            "3354010000000000000000000000000000000066",
            "aa540000000000000000000000000000000000fe",
        ),
        (
            "member_brightness",
            {"level": 42, "index": 4},
            "33502a040000000000000000000000000000004d",
            "aa500000000000000000000000000000000000fa",
        ),
        (
            "same_brightness",
            {"enabled": False},
            "3360040000000000000000000000000000000057",
            "aa600400000000000000000000000000000000ce",
        ),
        (
            "member_connect",
            {"index": 4, "connected": True},
            "3343040100000000000000000000000000000075",
            "aa430000000000000000000000000000000000e9",
        ),
        (
            "saturation",
            {"saturation": 50},
            "3351320000000000000000000000000000000050",
            "aa510000000000000000000000000000000000fb",
        ),
        (
            "video_settings",
            {"apply_area": 1, "content_mode": 1},
            "3352010100000000000000000000000000000061",
            "aa520000000000000000000000000000000000f8",
        ),
        (
            "sound",
            {"enabled": True, "softness": 79},
            "3353014f0000000000000000000000000000002e",
            "aa530000000000000000000000000000000000f9",
        ),
        ("delete_group", {}, "3356000000000000000000000000000000000065", None),
    ],
)
def test_h6199_legacy_group_literal_frames(setting, values, write_hex, query_hex):
    profile = device_profile("H6199", 2, 1, firmware="1.09.00", hardware="3.02.01")
    assert build_dreamview_command(setting, values, profile) == bytes.fromhex(write_hex)
    if query_hex is not None:
        assert build_dreamview_query(setting, profile) == bytes.fromhex(query_hex)


@pytest.mark.parametrize(
    ("pact", "firmware", "hardware", "baseline", "same"),
    [
        ((1, 1), "1.07.02", "1.00.01", True, False),
        ((2, 1), "1.08.99", "3.02.01", True, False),
        ((2, 1), "1.09.00", "3.02.00", True, False),
        ((2, 1), "1.09.00", "3.02.01", True, True),
        ((3, 1), "1.10.04", "3.02.01", True, True),
        ((4, 1), "1.10.04", "3.02.01", True, True),
        ((1, 1), "1.10.04", "3.02.01", True, True),
        ((2, 1), None, "3.02.01", True, False),
        ((2, 1), "1.10.04", "invalid", True, False),
        ((None, None), "1.10.04", "3.02.01", False, False),
        ((2, None), "1.10.04", "3.02.01", False, False),
        ((2, 2), "1.10.04", "3.02.01", False, False),
    ],
)
def test_h6199_group_revision_admission(pact, firmware, hardware, baseline, same):
    profile = device_profile("H6199", *pact, firmware=firmware, hardware=hardware)
    assert ("video_settings" in profile.dreamview_operations) is baseline
    assert ("same_brightness" in profile.dreamview_operations) is same
    assert ("same_brightness" in profile.dreamview_reads) is same


def legacy_coordinator(hass, pact):
    c = coordinator(hass, "H6199")
    c.pact_type, c.pact_code = pact, 1
    c.fw_version, c.hw_version = "1.10.04", "3.02.01"
    c._resolve_device_profile()
    c._confirmed_identity_fields.update({"fw_version", "hw_version"})
    client = ble_client()
    c._client = client
    c._notification_token = object()
    c._ensure_connected = AsyncMock(return_value=client)
    c._renew_foreground_lease = Mock()
    return c, client


@pytest.mark.parametrize("pact", [1, 2, 3, 4])
@pytest.mark.parametrize("legacy_alias", [False, True])
async def test_h6199_video_service_reaches_real_writer(hass, pact, legacy_alias):
    c, client = legacy_coordinator(hass, pact)
    entity = SimpleNamespace(coordinator=c, _async_supersede_preview=AsyncMock())
    name = "set_dreamview_sample" if legacy_alias else "set_dreamview_video_settings"
    data = {"sample_first": 1, "sample_second": 1} if legacy_alias else {"apply_area": "part", "content_mode": "movie"}
    await _async_dreamview_service(entity, ServiceCall(hass, DOMAIN, name, data), name=name)
    assert client.write_gatt_char.call_args.args[1] == bytes.fromhex("3352010100000000000000000000000000000061")
    assert c.video_mode == "off"
    assert c._dreamview_authored is None


@pytest.mark.parametrize("pact", [1, 2, 3, 4])
async def test_h6199_cached_identity_does_not_block_baseline_reads(hass, pact):
    c, client = legacy_coordinator(hass, pact)
    c._confirmed_identity_fields.clear()

    async def reply(_uuid, packet, **kwargs):
        if packet == bytes.fromhex("aa520000000000000000000000000000000000f8"):
            c._notify_callback(None, bytearray(bytes.fromhex("aa5207fe12340000000000000000000000000027")))
        c._handle_dreamview_notification(frame("aa600401"))

    client.write_gatt_char.side_effect = reply
    result = await c.async_read_dreamview_state(timeout=0)
    assert result["observed"]["video_settings"] == {
        "apply_area": 7,
        "content_mode": 254,
        "unknown": [18, 52] + [0] * 13,
    }
    assert result["unavailable_reads"] == ["same_brightness"]
    assert "same_brightness" not in result["observed"]
    assert bytes.fromhex("aa600400000000000000000000000000000000ce") not in [
        call.args[1] for call in client.write_gatt_char.await_args_list
    ]
    with pytest.raises(ValueError):
        await c.async_set_dreamview("same_brightness", {"enabled": True})
    assert any(entry["parser"] == "h6199_dreamview_frame" for entry in c.packet_log)


@pytest.mark.parametrize("status", [0, 1, None])
async def test_h6199_group_completion_retains_intent_and_requires_acceptance(hass, status):
    c, client = legacy_coordinator(hass, 1)
    old = {"operation": "replace", "members": [member(name="old", address=None).as_dict()]}
    await c._dreamview_store.async_save(old)
    packets = build_dreamview_group((member(),), c.profile)

    async def complete(_uuid, packet, **kwargs):
        if packet == packets[-1] and status is not None:
            c._notify_callback(None, bytearray(frame(f"a350{status:02x}")))

    client.write_gatt_char.side_effect = complete
    if status == 0:
        await c.async_replace_dreamview_group((member(),))
        assert c._dreamview_last_write == "accepted"
    else:
        with pytest.raises(TimeoutError if status is None else RuntimeError):
            await c.async_replace_dreamview_group((member(),))
        assert c._dreamview_last_write == "sent_unconfirmed"
    stored = await c._dreamview_store.async_load()
    assert stored["previous"] == old
    assert stored["accepted"] is (status == 0)
    assert stored["members"] == [member().as_dict()]
    assert client.write_gatt_char.await_count == len(packets)
    assert c._dreamview_ack is None


async def test_h6199_partial_upload_never_replays(hass):
    c, client = legacy_coordinator(hass, 1)
    client.write_gatt_char.side_effect = [None, TimeoutError()]
    c._disconnect_locked = AsyncMock()
    with pytest.raises(TimeoutError):
        await c.async_replace_dreamview_group((member(),))
    assert client.write_gatt_char.await_count == 2
    assert c._dreamview_last_write == "attempted_unconfirmed"
    assert not (await c._dreamview_store.async_load())["accepted"]


async def test_h6199_generation_failure_quarantines_delayed_group_completion(hass):
    c, client = legacy_coordinator(hass, 2)
    await c._start_notify()
    old_receive = client.start_notify.call_args.args[1]
    packets = build_dreamview_group((member(),), c.profile)

    async def invalidate_final_write(_uuid, packet, **kwargs):
        if packet == packets[-1]:
            c._profile_generation += 1

    client.write_gatt_char.side_effect = invalidate_final_write
    with pytest.raises(ValueError):
        await c.async_replace_dreamview_group((member(),))
    assert c._client is None
    client.disconnect.assert_awaited_once()

    next_client = ble_client()
    c._client = next_client
    c._ensure_connected = AsyncMock(return_value=next_client)
    await c._start_notify()
    new_receive = next_client.start_notify.call_args.args[1]

    async def reject_new_write(_uuid, packet, **kwargs):
        if packet == packets[-1]:
            old_receive(None, bytearray(frame("a35000")))
            new_receive(None, bytearray(frame("a35001")))

    next_client.write_gatt_char.side_effect = reject_new_write
    with pytest.raises(RuntimeError, match="rejected DreamView"):
        await c.async_replace_dreamview_group((member(),))
    assert not (await c._dreamview_store.async_load())["accepted"]
    assert c._dreamview_last_write == "sent_unconfirmed"


@pytest.mark.parametrize("accepted", [True, False])
async def test_h6199_delete_releases_claims_only_after_acceptance(hass, accepted):
    c, client = legacy_coordinator(hass, 2)

    async def complete(_uuid, packet, **kwargs):
        c._notify_callback(None, bytearray(frame("335600" if accepted else "335601")))

    client.write_gatt_char.side_effect = complete
    with patch(
        "custom_components.ha_govee_led_ble.coordinator_dreamview.async_release_dreamview_claims_for_centre",
        new_callable=AsyncMock,
    ) as release:
        if accepted:
            await c.async_delete_dreamview_group()
            release.assert_awaited_once()
        else:
            with pytest.raises(RuntimeError):
                await c.async_delete_dreamview_group()
            release.assert_not_awaited()
    assert (await c._dreamview_store.async_load())["accepted"] is accepted


def test_h6199_group_status_does_not_accept_the_newer_family():
    profile = device_profile("H6199", 2, 1)
    five = tuple(member(address=f"00:00:00:00:00:{i:02x}") for i in range(5))
    assert build_dreamview_group(five, profile)
    with pytest.raises(ValueError):
        build_dreamview_group((*five, member()), profile)
    assert parse_dreamview_status(frame("aa600a0101"), profile) is None
    assert parse_dreamview_status(frame("aa520101"), get_profile("H6099")) is None
    brightness = parse_dreamview_status(frame("aa50"), profile)
    connections = parse_dreamview_status(frame("aa43"), profile)
    assert brightness is not None and len(brightness[1]["brightness_bytes"]) == 17
    assert connections is not None and len(connections[1]["connection_bytes"]) == 10
