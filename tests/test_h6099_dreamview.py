"""APK-derived software checks only; no hardware or membership qualification."""

import asyncio
import io
import json
import logging
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
import voluptuous as vol
from bleak.exc import BleakError
from homeassistant.config_entries import current_entry
from homeassistant.core import CoreState, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.storage import Store
from homeassistant.util.file import WriteError
from kaitaistruct import KaitaiStream
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_govee_led_ble.const import DOMAIN, get_profile
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.diagnostics import async_get_config_entry_diagnostics
from custom_components.ha_govee_led_ble.dreamview import (
    DREAMVIEW_READ_SETTINGS,
    DreamviewMember,
    Group,
    build_dreamview_command,
    build_dreamview_group,
    build_dreamview_query,
    parse_dreamview_status,
)
from custom_components.ha_govee_led_ble.dreamview_services import (
    DREAMVIEW_SERVICES,
    _async_dreamview_service,
)
from custom_components.ha_govee_led_ble.govee_encryption import v1_transform
from custom_components.ha_govee_led_ble.light_services import async_register_light_services
from custom_components.ha_govee_led_ble.transport import reassemble_a3, xor_checksum
from tests.test_govee_encryption import KEY, negotiate

PROFILE = get_profile("H6099")
_STORE_WRITE_DATA = Store._async_write_data


@pytest.fixture
def durable_storage(hass_storage):
    """Restore HA's real writer inside the in-memory storage fixture's lifetime."""
    with patch.object(Store, "_async_write_data", _STORE_WRITE_DATA):
        yield


def frame(prefix: str) -> bytes:
    payload = bytes.fromhex(prefix).ljust(19, b"\x00")
    return payload + bytes((xor_checksum(payload),))


def member(**overrides) -> DreamviewMember:
    return DreamviewMember(
        **({"cmd_ver": 9, "is_rgbic": True, "zones": (0, 1, 10, 255), "address": "11:22:33:44:55:66"} | overrides)
    )


def test_exact_group_both_identities_and_capacity() -> None:
    members = (member(), member(address=None, name="lamp", cmd_ver=12, is_rgbic=False, zones=(2,)))
    packets = build_dreamview_group(members, PROFILE)
    envelope = reassemble_a3(packets)
    expected = bytes.fromhex("020100096655443322110400010aff00010c046c616d700102")
    assert envelope[2] == 0x50
    assert envelope[3 : 3 + len(expected)] == expected
    parsed = Group(KaitaiStream(io.BytesIO(envelope[3:])))
    parsed._read()
    assert parsed.num_members == 2
    assert parsed.members[0].reversed_mac == bytes.fromhex("665544332211")
    assert parsed.members[1].name_bytes == b"lamp"
    assert parsed.members[0].area_values == [0, 1, 10, 255]
    assert PROFILE.dreamview_max_sub_devices == 7
    seven = tuple(member(address=f"00:00:00:00:00:{i:02x}") for i in range(7))
    assert build_dreamview_group(seven, PROFILE)
    for invalid in ((), (*seven, member()), (member(), member(address="11:22:33:44:55:66"))):
        with pytest.raises(ValueError):
            build_dreamview_group(invalid, PROFILE)
    for profile in (get_profile("H6199"), replace(PROFILE, dreamview_grammar="unknown")):
        with pytest.raises(ValueError):
            build_dreamview_group((member(),), profile)
    assert "11:22" not in repr(member())
    named = member(address=None, name="\u00e9", zones=(1,))
    envelope = reassemble_a3(build_dreamview_group((named,), PROFILE))
    assert envelope[3:13] == bytes.fromhex("0101010902c3a9010100")


@pytest.mark.parametrize(
    "overrides",
    [
        {"cmd_ver": None},
        {"cmd_ver": True},
        {"cmd_ver": 256},
        {"cmd_ver": 9.5},
        {"is_rgbic": 1},
        {"address": "private-invalid"},
        {"address": None},
        {"name": "both"},
        {"zones": ()},
        {"zones": (11,)},
        {"zones": (None,)},
        {"zones": (True,)},
        {"zones": (255,)},
        {"address": None, "name": "x" * 256},
    ],
)
def test_member_validation(overrides) -> None:
    with pytest.raises((TypeError, ValueError)) as exc:
        member(**overrides)
    assert "private-invalid" not in str(exc.value)


@pytest.mark.parametrize(
    ("setting", "values", "prefix"),
    [
        ("switch_group", {"enabled": True}, "3360010101"),
        ("switch_group", {"enabled": False}, "3360010001"),
        ("member_brightness", {"level": 42, "index": 6}, "3360032a06"),
        ("same_brightness", {"enabled": False}, "33600400"),
        ("member_connect", {"index": 6, "connected": True}, "3360050601"),
        ("saturation", {"saturation": 50}, "33600932"),
        ("sample", {"sample_first": 0xAB, "sample_second": 0xCD}, "33600aabcd"),
        ("sound", {"enabled": True, "softness": 79}, "33600b014f"),
        ("delete_group", {}, "33600d"),
    ],
)
def test_apk_command_bytes(setting, values, prefix) -> None:
    assert build_dreamview_command(setting, values, PROFILE) == frame(prefix)


def test_individual_queries_and_truthful_raw_status() -> None:
    assert build_dreamview_query("switch_group", PROFILE) == frame("aa600101")
    for setting, prefix in (
        ("member_brightness", "aa6003"),
        ("same_brightness", "aa6004"),
        ("member_connect", "aa6005"),
        ("saturation", "aa6009"),
        ("sample", "aa600a"),
        ("sound", "aa600b"),
    ):
        assert build_dreamview_query(setting, PROFILE) == frame(prefix)
    sample = parse_dreamview_status(frame("aa600aabcd"))
    switch = parse_dreamview_status(frame("aa600101"))
    sound = parse_dreamview_status(frame("aa600b014f"))
    connections = parse_dreamview_status(frame("aa600501000000000000007f00"))
    brightness = parse_dreamview_status(frame("aa6003"))
    assert sample and switch and sound and connections and brightness
    assert sample[1]["sample_second"] == 0xCD
    assert switch[1]["enabled"] == 1
    assert sound[1]["softness"] == 79
    slots = connections[1]
    assert slots["connection_bytes"] == [1, 0, 0, 0, 0, 0, 0, 0, 127, 0]
    assert len(brightness[1]["brightness_bytes"]) == 16
    for invalid in (
        frame("aa600c"),
        frame("3360010101"),
        frame("aa600d"),
        frame("aa6011"),
        frame("aa6009")[:-1],
        frame("aa6009")[:-1] + b"\xff",
        frame("aa6109"),
    ):
        assert parse_dreamview_status(invalid) is None
    for setting in ("digest", "delete_group", "camera"):
        with pytest.raises(ValueError):
            build_dreamview_query(setting, PROFILE)
    with pytest.raises(ValueError):
        build_dreamview_query("sample", replace(PROFILE, dreamview_grammar="unknown"))


def coordinator(hass, model="H6099") -> Any:
    entry = MockConfigEntry(domain=DOMAIN, data={}, entry_id="dreamview-entry")
    entry.add_to_hass(hass)
    with current_entry.set(entry):
        c = GoveeBLECoordinator(hass, "00:00:00:00:00:01", model, configuration_url="http://example.test")
    return c


async def test_physical_writer_retry_guards_and_private_authorship(hass) -> None:
    c = coordinator(hass)
    client = SimpleNamespace(
        is_connected=True, write_gatt_char=AsyncMock(side_effect=[BleakError("retry"), None, None])
    )
    c._client = client
    c.profile = replace(PROFILE, outbound_transform=lambda packet: b"wrapped" + packet)
    c._ensure_connected = AsyncMock(return_value=client)
    c._disconnect_locked = AsyncMock()
    c._renew_foreground_lease = Mock()
    await c.async_replace_dreamview_group((member(),))
    packets = build_dreamview_group((member(),), PROFILE)
    writes = [call.args[1] for call in client.write_gatt_char.await_args_list]
    assert writes == [b"wrapped" + packets[0], *(b"wrapped" + packet for packet in packets)]
    assert c._dreamview_last_write == "sent_unconfirmed"
    assert not c._dreamview_private_write
    assert c.packet_log and all(entry["raw"] == "" and entry["redacted"] for entry in c.packet_log)
    assert c._dreamview_store.key == f"{DOMAIN}.dreamview.dreamview-entry"
    stored = await c._dreamview_store.async_load()
    assert stored == {"operation": "replace", "members": [member().as_dict()]}

    async def change_profile():
        c.profile = get_profile("H6199")
        return client

    c._ensure_connected = AsyncMock(side_effect=change_profile)
    client.write_gatt_char.reset_mock()
    with pytest.raises(ValueError):
        await c.async_set_dreamview("switch_group", {"enabled": True})
    client.write_gatt_char.assert_not_awaited()
    assert c._dreamview_last_write == "not_attempted"


async def test_observations_never_identify_authored_members_and_delete_retains_recovery(hass) -> None:
    c = coordinator(hass)
    c.async_write_effect_sequence = AsyncMock()
    await c.async_replace_dreamview_group((member(),))
    assert c._handle_dreamview_notification(frame("aa600501"))
    assert not c._handle_dreamview_notification(frame("3360050001"))
    c._dreamview_loaded = False
    c._dreamview_authored = None
    status = await c.async_read_dreamview_state(timeout=0)
    assert status["authored"]["members"] == [member().as_dict()]
    assert status["observed"] == {}
    assert status["missing_reads"] == sorted(DREAMVIEW_READ_SETTINGS)
    assert not status["membership_confirmed"] and status["slot_identities"] == "unknown"

    async def observe(packets, **kwargs):
        c._handle_dreamview_notification(frame("aa600500000000000000000000"))
        c._handle_dreamview_notification(frame("aa6003010000"))

    c.async_write_effect_sequence = AsyncMock(side_effect=observe)
    status = await c.async_read_dreamview_state(timeout=0)
    assert status["observed"]["member_connect"]["connection_bytes"] == [0] * 10
    assert "member_count" not in status and "has_group" not in status
    assert not status["membership_confirmed"]
    await c.async_delete_dreamview_group()
    stored = await c._dreamview_store.async_load()
    assert stored["operation"] == "delete" and stored["members"] == [member().as_dict()]
    assert c._dreamview_last_write == "sent_unconfirmed"


async def test_failed_and_cancelled_upload_keeps_local_request_not_confirmation(hass) -> None:
    c = coordinator(hass)
    for error in (BleakError("failure"), asyncio.CancelledError()):

        async def fail(packets, error=error, **kwargs):
            assert c._dreamview_private_write
            kwargs["write_guard"]()
            raise error

        c.async_write_effect_sequence = AsyncMock(side_effect=fail)
        with pytest.raises(type(error)):
            await c.async_replace_dreamview_group((member(),))
        assert c._dreamview_last_write == "attempted_unconfirmed"
        assert not c._dreamview_private_write
        assert (await c._dreamview_store.async_load())["members"] == [member().as_dict()]


@pytest.mark.parametrize("operation", ["replace", "delete"])
@pytest.mark.parametrize("failure", ["write_error", "atomic_sync"])
async def test_storage_failure_prevents_transmission(hass, tmp_path, durable_storage, operation, failure) -> None:
    hass.config.config_dir = str(tmp_path)
    c = coordinator(hass)
    c.async_write_effect_sequence = AsyncMock()
    prior = {"operation": "replace", "members": [member().as_dict()]}
    await c._dreamview_store.async_save(prior)
    c._dreamview_authored, c._dreamview_loaded = prior, True
    path = Path(c._dreamview_store.path)
    before = await hass.async_add_executor_job(path.read_bytes)
    assert json.loads(before)["data"] == prior
    assert c._dreamview_store._atomic_writes
    target = (
        "homeassistant.helpers.storage.write_utf8_file_atomic"
        if failure == "write_error"
        else "atomicwrites.AtomicWriter.sync"
    )
    error = WriteError("write failed") if failure == "write_error" else OSError("fsync failed")
    with patch(target, side_effect=error) as write:
        with pytest.raises(OSError):
            if operation == "replace":
                await c.async_replace_dreamview_group((member(cmd_ver=12),))
            else:
                await c.async_delete_dreamview_group()
        write.assert_called_once()
    c.async_write_effect_sequence.assert_not_awaited()
    assert c._dreamview_authored == prior
    assert await hass.async_add_executor_job(path.read_bytes) == before
    assert c._dreamview_store._data is None
    assert not c._dreamview_private_write
    # Retrying must not be mistaken for a prior successful save or a cached write.
    await c.async_delete_dreamview_group()
    assert json.loads(await hass.async_add_executor_job(path.read_bytes))["data"] == {**prior, "operation": "delete"}
    c.async_write_effect_sequence.assert_awaited_once()


async def test_shutdown_cannot_defer_membership_persistence(hass) -> None:
    c = coordinator(hass)
    c.async_write_effect_sequence = AsyncMock()
    c._dreamview_loaded = True
    hass.set_state(CoreState.stopping)
    try:
        with pytest.raises(OSError):
            await c.async_replace_dreamview_group((member(),))
    finally:
        hass.set_state(CoreState.not_running)
    c.async_write_effect_sequence.assert_not_awaited()
    assert c._dreamview_store._data is None
    assert c._dreamview_authored is None


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("replace_dreamview_group", {"members": [{"address": "private", "zones": [1], "is_rgbic": True}]}),
        ("replace_dreamview_group", {"members": [member().as_dict()] * 2}),
        ("set_dreamview_member_brightness", {"index": 256, "level": 50}),
        ("set_dreamview_member_brightness", {"index": 1.5, "level": 50}),
        ("set_dreamview_member_connect", {"index": True, "connected": True}),
        ("set_dreamview_sound_effects", {"enabled": True}),
        ("set_dreamview_sample", {"sample_first": 1}),
        ("set_dreamview_switch", {"enabled": "false"}),
        ("delete_dreamview_group", {"extra": "private"}),
    ],
)
async def test_schema_preflight_has_no_control_side_effects(hass, name, data) -> None:
    c = coordinator(hass)
    entity = SimpleNamespace(coordinator=c, _async_supersede_preview=AsyncMock())
    c.async_write_effect_sequence = AsyncMock()
    before = c._control_arbiter.preview_generation
    with pytest.raises(vol.Invalid):
        vol.Schema(DREAMVIEW_SERVICES[name][1])(data)
    with pytest.raises(ServiceValidationError) as exc:
        await _async_dreamview_service(entity, ServiceCall(hass, DOMAIN, name, data), name=name)
    assert "private" not in str(exc.value)
    assert exc.value.translation_domain == DOMAIN
    assert exc.value.translation_key == "invalid_control_request"
    entity._async_supersede_preview.assert_not_awaited()
    c.async_write_effect_sequence.assert_not_awaited()
    assert c._control_arbiter.preview_generation == before


async def test_registration_and_valid_service_dispatch(hass) -> None:
    with patch("homeassistant.helpers.service.async_register_platform_entity_service") as register:
        async_register_light_services(hass)
    calls = {call.args[2]: call.kwargs for call in register.call_args_list}
    assert set(DREAMVIEW_SERVICES) <= calls.keys()
    assert calls["read_dreamview_group"]["supports_response"] is SupportsResponse.ONLY
    c = coordinator(hass)
    c.async_write_effect_sequence = AsyncMock()
    entity = SimpleNamespace(coordinator=c, _async_supersede_preview=AsyncMock())
    await _async_dreamview_service(
        entity,
        ServiceCall(hass, DOMAIN, "set_dreamview_sample", {"sample_first": 7, "sample_second": 254}),
        name="set_dreamview_sample",
    )
    entity._async_supersede_preview.assert_awaited_once()
    assert c.async_write_effect_sequence.call_args.args[0] == (frame("33600a07fe"),)
    c.profile = get_profile("H6199")
    entity._async_supersede_preview.reset_mock()
    with pytest.raises(ServiceValidationError):
        await _async_dreamview_service(
            entity, ServiceCall(hass, DOMAIN, "set_dreamview_switch", {"enabled": True}), name="set_dreamview_switch"
        )
    entity._async_supersede_preview.assert_not_awaited()
    c.profile = PROFILE
    c.async_write_effect_sequence.side_effect = BleakError("private-address")
    with pytest.raises(HomeAssistantError) as exc:
        await _async_dreamview_service(
            entity, ServiceCall(hass, DOMAIN, "set_dreamview_switch", {"enabled": True}), name="set_dreamview_switch"
        )
    assert "private-address" not in str(exc.value)
    assert exc.value.translation_domain == DOMAIN
    assert exc.value.translation_key == "device_command_failed"


async def test_concrete_encrypted_notifications_and_private_logs(hass, caplog):
    c = coordinator(hass)
    session, client = await negotiate()
    c._encryption, c._client = session, client
    c._ensure_connected = AsyncMock(return_value=client)
    c._renew_foreground_lease = Mock()
    await c._start_notify()
    receive = client.start_notify.call_args.args[1]
    caplog.set_level(logging.DEBUG, logger="custom_components.ha_govee_led_ble.coordinator")
    private_frames = (
        frame("aa600aabcd"),  # DreamView individual reply.
        frame("33600aabcd"),  # Command echo, not readback.
        frame("aa600c112233445566"),  # Unhandled digest.
        frame("aa0515010001"),  # Semantic rejection.
        frame("aa3004"),  # Generic status payload.
        frame("aa30112233445566")[:-1] + b"\xff",  # Schema rejection.
    )
    transmitted = []

    async def transmit(_uuid, packet, **kwargs):
        assert c._dreamview_private_write
        transmitted.append(packet)
        for reply in private_frames:
            receive(None, bytearray(v1_transform(reply, KEY, encrypt=True)))

    client.write_gatt_char.side_effect = transmit
    await c.async_replace_dreamview_group((member(address=None, name="private-lamp", zones=(1,)),))
    assert set(c._dreamview_observed) == {"sample"}
    assert c._dreamview_observed["sample"]["sample_first"] == 171
    assert c._dreamview_observed["sample"]["sample_second"] == 205
    assert not c.is_on and c.video_mode == "off" and c.color_mode is None
    assert c.installation_direction == 4
    assert c.packet_log and all(entry["redacted"] and entry["raw"] == "" for entry in c.packet_log)
    logs = "\n".join(record.getMessage() for record in caplog.records if record.name.startswith("custom_components."))
    for reply in private_frames:
        assert reply.hex() not in logs and reply[2:-1].hex() not in logs
    assert "private-lamp" not in logs
    c.config_entry.runtime_data = c
    diagnostics = await async_get_config_entry_diagnostics(hass, c.config_entry)
    serialized = json.dumps(diagnostics)
    assert "private-lamp" not in serialized and "members" not in diagnostics["coordinator"]
    assert all(packet.hex() not in serialized for packet in transmitted)
    assert diagnostics["coordinator"]["installation_direction"] == 4
    assert diagnostics["coordinator"]["camera_health"] == "unknown"
    assert diagnostics["coordinator"]["dreamview_last_write"] == "sent_unconfirmed"
    c._notification_token = object()
    receive(None, bytearray(v1_transform(frame("aa600a0102"), KEY, encrypt=True)))
    assert c._dreamview_observed["sample"]["sample_first"] == 171
    c._encryption = None
    c._notify_callback(None, bytearray(frame("aa600901")))
    assert c._dreamview_observed["saturation"]["saturation"] == 1
    assert c.packet_log[-1]["raw"] == frame("aa600901").hex() and not c.packet_log[-1]["redacted"]
