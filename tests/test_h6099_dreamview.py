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
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from homeassistant.util.file import WriteError
from kaitaistruct import KaitaiStream
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_govee_led_ble.const import DOMAIN, device_profile, get_profile
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
_STORE_LOAD = Store._async_load


@pytest.fixture
def durable_storage(hass_storage):
    """Restore HA's real disk reads and writes inside the storage fixture."""
    with (
        patch.object(Store, "_async_write_data", _STORE_WRITE_DATA),
        patch.object(Store, "_async_load", _STORE_LOAD),
    ):
        yield


def frame(prefix: str) -> bytes:
    payload = bytes.fromhex(prefix).ljust(19, b"\x00")
    return payload + bytes((xor_checksum(payload),))


def member(**overrides) -> DreamviewMember:
    return DreamviewMember(
        **({"cmd_ver": 9, "is_rgbic": True, "zones": (0, 1, 10, 255), "address": "11:22:33:44:55:66"} | overrides)
    )


@pytest.mark.parametrize("model", ["H6097", "H6099"])
def test_exact_group_both_identities_and_capacity(model) -> None:
    profile = get_profile(model)
    members = (member(), member(address=None, name="lamp", cmd_ver=12, is_rgbic=False, zones=(2,)))
    packets = build_dreamview_group(members, profile)
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
    assert profile.dreamview_max_sub_devices == 7
    seven = tuple(member(address=f"00:00:00:00:00:{i:02x}") for i in range(7))
    assert build_dreamview_group(seven, profile)
    for invalid in ((), (*seven, member()), (member(), member(address="11:22:33:44:55:66"))):
        with pytest.raises(ValueError):
            build_dreamview_group(invalid, profile)
    for unsupported in (device_profile("H6199", None, None), replace(profile, dreamview_grammar="unknown")):
        with pytest.raises(ValueError):
            build_dreamview_group((member(),), unsupported)
    assert "11:22" not in repr(member())
    named = member(address=None, name="\u00e9", zones=(1,))
    envelope = reassemble_a3(build_dreamview_group((named,), profile))
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
        ("video_settings", {"apply_area": 0xAB, "content_mode": 0xCD}, "33600aabcd"),
        ("sound", {"enabled": True, "softness": 79}, "33600b014f"),
        ("delete_group", {}, "33600d"),
    ],
)
@pytest.mark.parametrize("model", ["H6097", "H6099"])
def test_apk_command_bytes(setting, values, prefix, model) -> None:
    assert build_dreamview_command(setting, values, get_profile(model)) == frame(prefix)


def test_individual_queries_and_truthful_raw_status() -> None:
    assert build_dreamview_query("switch_group", PROFILE) == frame("aa600101")
    for setting, prefix in (
        ("member_brightness", "aa6003"),
        ("same_brightness", "aa6004"),
        ("member_connect", "aa6005"),
        ("saturation", "aa6009"),
        ("video_settings", "aa600a"),
        ("sound", "aa600b"),
    ):
        assert build_dreamview_query(setting, PROFILE) == frame(prefix)
    video = parse_dreamview_status(frame("aa600aabcd"))
    switch = parse_dreamview_status(frame("aa600101"))
    sound = parse_dreamview_status(frame("aa600b014f"))
    connections = parse_dreamview_status(frame("aa600501000000000000007f00"))
    brightness = parse_dreamview_status(frame("aa6003"))
    assert video and switch and sound and connections and brightness
    assert video[1]["content_mode"] == 0xCD
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
        build_dreamview_query("video_settings", replace(PROFILE, dreamview_grammar="unknown"))


def coordinator(hass, model="H6099", *, entry_id="dreamview-entry") -> Any:
    entry = MockConfigEntry(domain=DOMAIN, data={}, entry_id=entry_id)
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
        c.profile = device_profile("H6199", None, None)
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
    assert status["missing_reads"] == sorted((*DREAMVIEW_READ_SETTINGS, "sample"))
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
        ("set_dreamview_video_settings", {"apply_area": "part"}),
        ("set_dreamview_video_settings", {"apply_area": 1, "content_mode": "movie"}),
        ("set_dreamview_video_settings", {"apply_area": "part", "content_mode": "unknown"}),
        ("set_dreamview_video_settings", {"apply_area": "part", "sample_second": 1}),
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
    assert ir.async_get(hass).async_get_issue(DOMAIN, "dreamview_sample_deprecated") is None


@pytest.mark.parametrize("model", ["H6099", "H66A0"])
@pytest.mark.parametrize(
    ("apply_area", "content_mode", "wire"),
    [("all", "game", "0000"), ("all", "movie", "0001"), ("part", "game", "0100"), ("part", "movie", "0101")],
)
async def test_named_video_settings_and_readback(hass, model, apply_area, content_mode, wire) -> None:
    c = coordinator(hass, model)
    c.async_write_effect_sequence = AsyncMock()
    entity = SimpleNamespace(coordinator=c, _async_supersede_preview=AsyncMock())
    await _async_dreamview_service(
        entity,
        ServiceCall(
            hass,
            DOMAIN,
            "set_dreamview_video_settings",
            {"apply_area": apply_area, "content_mode": content_mode},
        ),
        name="set_dreamview_video_settings",
    )
    assert c.async_write_effect_sequence.call_args.args[0] == (frame(f"33600a{wire}"),)
    assert ir.async_get(hass).async_get_issue(DOMAIN, "dreamview_sample_deprecated") is None
    assert c.video_mode == "off" and c._dreamview_authored is None

    c.profile = replace(c.profile, dreamview_reads=frozenset({"video_settings"}))

    async def observe(packets, **kwargs):
        assert packets == (frame("aa600a"),)
        c._handle_dreamview_notification(frame(f"aa600a{wire}"))

    c.async_write_effect_sequence = AsyncMock(side_effect=observe)
    result = await c.async_read_dreamview_state(timeout=0)
    assert result["missing_reads"] == []
    assert result["observed"]["video_settings"] == {
        "apply_area": apply_area,
        "content_mode": content_mode,
        "unknown": [0] * 14,
    }
    assert result["observed"]["sample"] == {
        "sample_first": int(wire[:2], 16),
        "sample_second": int(wire[2:], 16),
        "unknown": [0] * 14,
    }
    assert set(c._dreamview_observed) == {"video_settings"}

    c.profile = replace(c.profile, dreamview_reads=frozenset({"saturation"}))
    c.async_write_effect_sequence = AsyncMock()
    result = await c.async_read_dreamview_state(timeout=0)
    assert {"sample", "video_settings"} <= set(result["unsupported_reads"])
    assert result["observed"] == {}


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
    issue = ir.async_get(hass).async_get_issue(DOMAIN, "dreamview_sample_deprecated")
    assert issue is not None and issue.severity is ir.IssueSeverity.WARNING
    await _async_dreamview_service(
        entity,
        ServiceCall(hass, DOMAIN, "set_dreamview_sample", {"sample_first": 7, "sample_second": 254}),
        name="set_dreamview_sample",
    )
    assert ir.async_get(hass).async_get_issue(DOMAIN, "dreamview_sample_deprecated") is issue

    c.profile = replace(PROFILE, dreamview_reads=frozenset({"video_settings"}))

    async def observe(packets, **kwargs):
        c._handle_dreamview_notification(frame("aa600a07fe1234"))

    c.async_write_effect_sequence = AsyncMock(side_effect=observe)
    result = await c.async_read_dreamview_state(timeout=0)
    assert result["observed"]["video_settings"] == {
        "apply_area": 7,
        "content_mode": 254,
        "unknown": [18, 52, *([0] * 12)],
    }
    assert result["observed"]["sample"] == {
        "sample_first": 7,
        "sample_second": 254,
        "unknown": [18, 52, *([0] * 12)],
    }
    c.profile = device_profile("H6199", None, None)
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
    assert set(c._dreamview_observed) == {"video_settings"}
    assert c._dreamview_observed["video_settings"]["apply_area"] == 171
    assert c._dreamview_observed["video_settings"]["content_mode"] == 205
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
    assert c._dreamview_observed["video_settings"]["apply_area"] == 171
    c._encryption = None
    c._notify_callback(None, bytearray(frame("aa600901")))
    assert c._dreamview_observed["saturation"]["saturation"] == 1
    assert c.packet_log[-1]["raw"] == frame("aa600901").hex() and not c.packet_log[-1]["redacted"]


async def test_dreamview_member_handover_replacement_rollback_and_delete(hass, monkeypatch) -> None:
    from homeassistant.config_entries import ConfigEntryDisabler

    from custom_components.ha_govee_led_ble.coordinator_dreamview import async_load_dreamview_claims

    monkeypatch.setattr(
        "custom_components.ha_govee_led_ble.bluetooth.async_last_service_info", lambda *_args, **_kwargs: None
    )
    centre = coordinator(hass, "H66A0")
    centre_client = SimpleNamespace(is_connected=True, write_gatt_char=AsyncMock(), disconnect=AsyncMock())
    centre._client = centre_client
    centre._ensure_connected = AsyncMock(return_value=centre_client)
    centre._renew_foreground_lease = Mock()

    # Member 1: enabled HA entry matched by MAC address, actively connected.
    m1_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="11:22:33:44:55:01",
        title="Strip 1",
        data={"model": "H1A42"},
        entry_id="member-1",
    )
    m1_entry.add_to_hass(hass)
    with current_entry.set(m1_entry):
        m1_coord: Any = GoveeBLECoordinator(hass, "11:22:33:44:55:01", "H1A42", configuration_url=None)
    m1_client = SimpleNamespace(is_connected=True, write_gatt_char=AsyncMock())

    async def disconnect_m1():
        m1_client.is_connected = False

    m1_client.disconnect = AsyncMock(side_effect=disconnect_m1)
    m1_coord._client = m1_client
    m1_entry.runtime_data = m1_coord

    # Member 2: enabled HA entry matched by BLE name.
    m2_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="11:22:33:44:55:02",
        title="Govee_H61F5_5502",
        data={"model": "H61F5"},
        entry_id="member-2",
    )
    m2_entry.add_to_hass(hass)
    with current_entry.set(m2_entry):
        m2_coord = GoveeBLECoordinator(hass, "11:22:33:44:55:02", "H61F5", configuration_url=None)
    m2_entry.runtime_data = m2_coord

    # Member 3: already user-disabled HA entry (must NOT be re-enabled on delete).
    m3_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="11:22:33:44:55:03",
        title="Pre-disabled Strip",
        data={"model": "H1A42"},
        entry_id="member-3",
        disabled_by=ConfigEntryDisabler.USER,
    )
    m3_entry.add_to_hass(hass)

    async def fake_set_disabled_by(entry_id: str, disabled_by: ConfigEntryDisabler | None) -> bool:
        target = hass.config_entries.async_get_entry(entry_id)
        assert target is not None
        target.disabled_by = disabled_by
        return True

    monkeypatch.setattr(hass.config_entries, "async_set_disabled_by", AsyncMock(side_effect=fake_set_disabled_by))

    events: list[str] = []

    async def record_write(_uuid, packet, **_kwargs):
        if not events:
            # Verify m1 is already disabled and physically disconnected before packet 0 is written.
            assert m1_entry.disabled_by == ConfigEntryDisabler.USER
            assert not m1_client.is_connected
            assert m1_coord._dreamview_claimed
        events.append("tx")

    centre_client.write_gatt_char.side_effect = record_write

    # Include m1 (by address), m2 (by name), m3 (pre-disabled), and an external non-HA member.
    await centre.async_replace_dreamview_group(
        (
            member(address="11:22:33:44:55:01", cmd_ver=1, zones=(1, 2, 3, 4, 5)),
            member(address=None, name="Govee_H61F5_5502", cmd_ver=1, zones=(6, 7, 8, 9, 10)),
            member(address="11:22:33:44:55:03", cmd_ver=1, zones=(1,)),
            member(address="99:88:77:66:55:44", cmd_ver=1, zones=(2,)),
        )
    )
    assert events
    claims = await async_load_dreamview_claims(hass)
    assert claims["member-1"]["disabled_by_dreamview"] is True
    assert claims["member-2"]["disabled_by_dreamview"] is True
    assert claims["member-3"]["disabled_by_dreamview"] is False
    assert claims["member-3"]["prior_disabled_by"] == str(ConfigEntryDisabler.USER)

    # Stale coordinator barrier: claimed member cannot reconnect or write packets.
    with pytest.raises(BleakError, match="DreamView"):
        await m1_coord._ensure_connected()
    with pytest.raises(BleakError, match="DreamView"):
        await m1_coord._async_write_packet(m1_client, frame("330101"))

    # Replace group dropping m2: m2 is released and re-enabled after new 0x50 upload succeeds.
    await centre.async_replace_dreamview_group(
        (
            member(address="11:22:33:44:55:01", cmd_ver=1, zones=(1, 2, 3, 4, 5)),
            member(address="11:22:33:44:55:03", cmd_ver=1, zones=(1,)),
        )
    )
    assert m2_entry.disabled_by is None
    assert not m2_coord._dreamview_claimed
    assert "member-2" not in await async_load_dreamview_claims(hass)
    assert m1_entry.disabled_by == ConfigEntryDisabler.USER

    # Failed delete_dreamview_group over BLE keeps claims intact and m1 disabled.
    centre_client.write_gatt_char.side_effect = BleakError("delete failed")
    with pytest.raises(BleakError):
        await centre.async_delete_dreamview_group()
    assert m1_entry.disabled_by == ConfigEntryDisabler.USER
    assert "member-1" in await async_load_dreamview_claims(hass)

    # Successful delete_dreamview_group re-enables m1, while keeping pre-disabled m3 disabled.
    centre_client.write_gatt_char.side_effect = None
    await centre.async_delete_dreamview_group()
    assert m1_entry.disabled_by is None
    assert not m1_coord._dreamview_claimed
    assert m3_entry.disabled_by == ConfigEntryDisabler.USER
    assert await async_load_dreamview_claims(hass) == {}

    # Pre-transmission failure (not_attempted) rolls back newly claimed member.
    centre._ensure_connected = AsyncMock(side_effect=BleakError("centre unreachable"))
    with pytest.raises(BleakError):
        await centre.async_replace_dreamview_group((member(address="11:22:33:44:55:02", cmd_ver=1, zones=(1,)),))
    assert centre._dreamview_last_write == "not_attempted"
    assert m2_entry.disabled_by is None
    assert not m2_coord._dreamview_claimed
    assert await async_load_dreamview_claims(hass) == {}


async def test_dreamview_member_validation_and_crash_consistency_guard(hass, monkeypatch) -> None:
    from homeassistant.config_entries import ConfigEntryDisabler
    from homeassistant.exceptions import ConfigEntryNotReady

    from custom_components.ha_govee_led_ble import async_remove_entry, async_setup_entry
    from custom_components.ha_govee_led_ble.coordinator_dreamview import (
        _async_save_dreamview_claims,
        async_load_dreamview_claims,
    )

    centre = coordinator(hass, "H66A0")
    object.__setattr__(centre.config_entry, "unique_id", "00:00:00:00:00:01")
    entity = SimpleNamespace(coordinator=centre, _async_supersede_preview=AsyncMock())
    monkeypatch.setattr(
        "custom_components.ha_govee_led_ble.bluetooth.async_last_service_info",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr("custom_components.ha_govee_led_ble._async_update_editor_panel", AsyncMock())

    m1_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="11:22:33:44:55:11",
        title="Shared Name",
        data={"model": "H1A42"},
        entry_id="member-a",
    )
    m1_entry.add_to_hass(hass)
    m2_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="11:22:33:44:55:12",
        title="Shared Name",
        data={"model": "H61F5"},
        entry_id="member-b",
    )
    m2_entry.add_to_hass(hass)
    other_centre = MockConfigEntry(
        domain=DOMAIN,
        unique_id="00:00:00:00:00:99",
        title="Other Centre",
        data={"model": "H6099"},
        entry_id="other-centre",
    )
    other_centre.add_to_hass(hass)
    await _async_save_dreamview_claims(
        hass,
        {"member-b": {"centre_entry_id": "other-centre", "disabled_by_dreamview": True, "prior_disabled_by": None}},
    )

    # Self-membership, ambiguous name, duplicate entry (address + name), and cross-centre conflict fail before preview.
    for invalid_members in (
        [member(address="00:00:00:00:00:01", cmd_ver=1, zones=(1,)).as_dict()],
        [member(address=None, name="Shared Name", cmd_ver=1, zones=(1,)).as_dict()],
        [member(address="11:22:33:44:55:12", cmd_ver=1, zones=(1,)).as_dict()],
    ):
        with pytest.raises(ServiceValidationError):
            await _async_dreamview_service(
                entity,
                ServiceCall(hass, DOMAIN, "replace_dreamview_group", {"members": invalid_members}),
                name="replace_dreamview_group",
            )
    entity._async_supersede_preview.assert_not_awaited()
    monkeypatch.setattr(
        "custom_components.ha_govee_led_ble.bluetooth.async_last_service_info",
        lambda _hass, address, **_kwargs: (
            SimpleNamespace(name="Shared Name") if address == m1_entry.unique_id else None
        ),
    )
    assert await centre.async_validate_dreamview_members((member(address=None, name="Shared Name"),)) == (m1_entry,)
    with pytest.raises(ValueError, match="Duplicate DreamView member config entry"):
        await centre.async_validate_dreamview_members(
            (member(address=m1_entry.unique_id), member(address=None, name="Shared Name"))
        )

    # Crash-consistency guard: member-b is claimed by other-centre with disabled_by_dreamview=True,
    # but m2_entry.disabled_by is still None on startup.
    set_disabled = AsyncMock()
    monkeypatch.setattr(hass.config_entries, "async_set_disabled_by", set_disabled)
    with pytest.raises(ConfigEntryNotReady):
        await async_setup_entry(hass, m2_entry)
    await hass.async_block_till_done()
    set_disabled.assert_awaited_once_with("member-b", ConfigEntryDisabler.USER)

    # Removing other-centre releases member-b's claim.
    await async_remove_entry(hass, other_centre)
    assert "member-b" not in await async_load_dreamview_claims(hass)


@pytest.mark.parametrize("same_member", [False, True])
async def test_concurrent_dreamview_centres_preserve_claims_and_reject_conflicts(hass, monkeypatch, same_member):
    from homeassistant.config_entries import ConfigEntryDisabler

    from custom_components.ha_govee_led_ble.coordinator_dreamview import async_load_dreamview_claims

    centres = [coordinator(hass, "H66A0", entry_id=f"centre-{i}") for i in range(2)]
    entries = []
    for i in range(2):
        entry = MockConfigEntry(domain=DOMAIN, unique_id=f"11:22:33:44:55:{i:02x}", entry_id=f"member-{i}")
        entry.add_to_hass(hass)
        entries.append(entry)

    async def set_disabled(entry_id, disabled_by):
        hass.config_entries.async_get_known_entry(entry_id).disabled_by = disabled_by

    monkeypatch.setattr(hass.config_entries, "async_set_disabled_by", AsyncMock(side_effect=set_disabled))
    entered, proceed = asyncio.Event(), asyncio.Event()
    original_save = centres[0]._dreamview_store.async_save

    async def paused_save(data):
        entered.set()
        await proceed.wait()
        await original_save(data)

    centres[0]._dreamview_store.async_save = paused_save
    for centre in centres:
        centre.async_write_effect_sequence = AsyncMock()
    first = asyncio.create_task(centres[0].async_replace_dreamview_group((member(address=entries[0].unique_id),)))
    await entered.wait()
    second = asyncio.create_task(
        centres[1].async_replace_dreamview_group((member(address=entries[0 if same_member else 1].unique_id),))
    )
    await asyncio.sleep(0)
    proceed.set()
    results = await asyncio.gather(first, second, return_exceptions=True)
    claims = await async_load_dreamview_claims(hass)
    assert results[0] is None
    assert claims["member-0"]["centre_entry_id"] == "centre-0"
    if same_member:
        assert isinstance(results[1], ValueError)
        centres[1].async_write_effect_sequence.assert_not_awaited()
        assert len(claims) == 1
    else:
        assert results[1] is None
        assert claims["member-1"]["centre_entry_id"] == "centre-1"
    assert entries[0].disabled_by == ConfigEntryDisabler.USER
    for centre in centres:
        await centre.async_delete_dreamview_group()
    assert all(entry.disabled_by is None for entry in entries)
    assert await async_load_dreamview_claims(hass) == {}


@pytest.mark.parametrize("failure", ["disable", "disconnect"])
async def test_dreamview_failed_handover_never_uploads_and_restores_preview(hass, monkeypatch, failure):
    from homeassistant.config_entries import ConfigEntryDisabler

    from custom_components.ha_govee_led_ble.coordinator_dreamview import async_load_dreamview_claims

    centre = coordinator(hass, "H66A0")
    target = coordinator(hass, "H1A42", entry_id="member")
    entry = target.config_entry
    object.__setattr__(entry, "unique_id", "11:22:33:44:55:01")
    entry.runtime_data = target
    client = SimpleNamespace(is_connected=True, disconnect=AsyncMock(side_effect=BleakError("disconnect failed")))
    target._client = client
    preview = SimpleNamespace(async_unload_device=AsyncMock(), async_load_device=AsyncMock())
    monkeypatch.setattr(
        "custom_components.ha_govee_led_ble.effect_setup.get_effect_backend",
        lambda _hass: SimpleNamespace(preview=preview),
    )

    async def set_disabled(entry_id, disabled_by):
        if failure == "disable" and disabled_by == ConfigEntryDisabler.USER:
            raise RuntimeError("disable failed")
        entry.disabled_by = disabled_by
        if disabled_by is not None:
            await target.disconnect()

    monkeypatch.setattr(hass.config_entries, "async_set_disabled_by", AsyncMock(side_effect=set_disabled))
    centre.async_write_effect_sequence = AsyncMock()
    with pytest.raises((BleakError, RuntimeError), match="failed|released"):
        await centre.async_replace_dreamview_group((member(address=entry.unique_id),))
    centre.async_write_effect_sequence.assert_not_awaited()
    assert client.is_connected
    assert entry.disabled_by is None
    assert not target._dreamview_claimed
    assert centre._dreamview_authored is None
    assert await async_load_dreamview_claims(hass) == {}
    preview.async_load_device.assert_awaited_once_with(entry.entry_id)


async def test_dreamview_restoration_failure_retains_restart_recovery(hass, monkeypatch):
    from homeassistant.config_entries import ConfigEntryDisabler

    from custom_components.ha_govee_led_ble.coordinator_dreamview import (
        DREAMVIEW_CLAIMS_DATA_KEY,
        async_load_dreamview_claims,
        async_recover_dreamview_claims,
        async_release_dreamview_claims_for_centre,
        is_dreamview_claimed,
    )

    centre = coordinator(hass, "H66A0")
    centre.async_write_effect_sequence = AsyncMock()
    entry = MockConfigEntry(domain=DOMAIN, unique_id="11:22:33:44:55:01", entry_id="member")
    entry.add_to_hass(hass)

    async def set_disabled(entry_id, disabled_by):
        entry.disabled_by = disabled_by

    monkeypatch.setattr(hass.config_entries, "async_set_disabled_by", AsyncMock(side_effect=set_disabled))
    await centre.async_replace_dreamview_group((member(address=entry.unique_id),))
    monkeypatch.setattr(
        hass.config_entries, "async_set_disabled_by", AsyncMock(side_effect=RuntimeError("restore failed"))
    )
    with pytest.raises(RuntimeError, match="restore failed"):
        await async_release_dreamview_claims_for_centre(hass, centre.config_entry.entry_id)
    assert entry.disabled_by == ConfigEntryDisabler.USER
    assert (await async_load_dreamview_claims(hass))["member"]["releasing"]
    assert not is_dreamview_claimed(hass, "member")
    with pytest.raises(ValueError, match="restoration is pending"):
        await centre.async_validate_dreamview_members((member(address=entry.unique_id),))

    hass.data[DOMAIN].pop(DREAMVIEW_CLAIMS_DATA_KEY)
    monkeypatch.setattr(hass.config_entries, "async_set_disabled_by", AsyncMock(side_effect=set_disabled))
    await async_recover_dreamview_claims(hass)
    assert entry.disabled_by is None
    assert await async_load_dreamview_claims(hass) == {}


@pytest.mark.parametrize("fail_native_save", [False, True])
async def test_dreamview_restoration_journal_outlives_native_enable_persistence(
    hass, monkeypatch, tmp_path, durable_storage, fail_native_save
):
    from homeassistant.config_entries import ConfigEntryDisabler

    from custom_components.ha_govee_led_ble.coordinator_dreamview import (
        _async_save_dreamview_claims,
        async_load_dreamview_claims,
        async_recover_dreamview_claims,
        async_release_dreamview_claims_for_centre,
    )

    hass.config.config_dir = str(tmp_path)
    centre = coordinator(hass, "H66A0")
    entry = MockConfigEntry(domain=DOMAIN, entry_id="member", disabled_by=ConfigEntryDisabler.USER)
    entry.add_to_hass(hass)
    native_store = hass.config_entries._store
    await native_store.async_save(hass.config_entries._data_to_save())
    native_path = Path(native_store.path)
    await _async_save_dreamview_claims(
        hass, {"member": {"centre_entry_id": centre.config_entry.entry_id, "disabled_by_dreamview": True}}
    )
    hass.config.components.add(DOMAIN)
    monkeypatch.setattr(hass.config_entries, "async_setup", AsyncMock(return_value=True))
    if fail_native_save:
        with patch.object(native_store, "_async_write_data", side_effect=WriteError("native save failed")):
            with pytest.raises(OSError, match="restoration could not be persisted"):
                await async_release_dreamview_claims_for_centre(hass, centre.config_entry.entry_id)
        assert entry.disabled_by is None
        assert (await async_load_dreamview_claims(hass))["member"]["releasing"]
        stored = json.loads(await hass.async_add_executor_job(native_path.read_bytes))
        assert next(item for item in stored["data"]["entries"] if item["entry_id"] == "member")["disabled_by"] == "user"
        await async_recover_dreamview_claims(hass)
    else:
        await async_release_dreamview_claims_for_centre(hass, centre.config_entry.entry_id)
    assert await async_load_dreamview_claims(hass) == {}
    stored = json.loads(await hass.async_add_executor_job(native_path.read_bytes))
    assert next(item for item in stored["data"]["entries"] if item["entry_id"] == "member")["disabled_by"] is None


async def test_dreamview_restoration_preserves_a_subsequent_deliberate_disable(hass, monkeypatch):
    from homeassistant.config_entries import ConfigEntryDisabler

    from custom_components.ha_govee_led_ble.coordinator_dreamview import (
        _async_save_dreamview_claims,
        async_load_dreamview_claims,
        async_release_dreamview_claims_for_centre,
    )

    centre = coordinator(hass, "H66A0")
    entries = [
        MockConfigEntry(domain=DOMAIN, entry_id=f"member-{i}", disabled_by=ConfigEntryDisabler.USER) for i in range(2)
    ]
    for entry in entries:
        entry.add_to_hass(hass)
    await _async_save_dreamview_claims(
        hass,
        {
            entry.entry_id: {"centre_entry_id": centre.config_entry.entry_id, "disabled_by_dreamview": True}
            for entry in entries
        },
    )
    hass.config.components.add(DOMAIN)

    async def setup(entry_id, **_kwargs):
        if entry_id == "member-1":
            await hass.config_entries.async_set_disabled_by("member-0", ConfigEntryDisabler.USER)
        return True

    monkeypatch.setattr(hass.config_entries, "async_setup", AsyncMock(side_effect=setup))
    await async_release_dreamview_claims_for_centre(hass, centre.config_entry.entry_id)
    assert entries[0].disabled_by == ConfigEntryDisabler.USER
    assert entries[1].disabled_by is None
    assert await async_load_dreamview_claims(hass) == {}


async def test_cancelled_dreamview_native_flush_keeps_storage_serialised(hass, monkeypatch):
    from custom_components.ha_govee_led_ble.coordinator_dreamview import _async_persist_dreamview_restoration

    entry = MockConfigEntry(domain=DOMAIN, entry_id="member")
    entry.add_to_hass(hass)
    native_store = hass.config_entries._store
    entered, proceed = asyncio.Event(), asyncio.Event()
    persisted = {}

    async def write(data):
        if "revision" not in data["data"]:
            entered.set()
            await proceed.wait()
        persisted["revision"] = data["data"].get("revision", 0)

    monkeypatch.setattr(native_store, "_async_write_data", write)
    flush = asyncio.create_task(_async_persist_dreamview_restoration(hass, {"member"}))
    await entered.wait()
    flush.cancel()
    with pytest.raises(asyncio.CancelledError):
        await flush
    later = asyncio.create_task(native_store.async_save({"entries": [], "revision": 1}))
    try:
        await asyncio.sleep(0)
        assert not later.done()
    finally:
        proceed.set()
        await later
        await hass.async_block_till_done()
    assert persisted["revision"] == 1


async def test_dreamview_manual_enable_of_predisabled_member_preserves_intent_without_coordinator(hass, monkeypatch):
    from homeassistant.config_entries import ConfigEntryDisabler
    from homeassistant.exceptions import ConfigEntryNotReady

    from custom_components.ha_govee_led_ble import async_setup_entry
    from custom_components.ha_govee_led_ble.coordinator_dreamview import async_load_dreamview_claims

    centre = coordinator(hass, "H66A0")
    centre.async_write_effect_sequence = AsyncMock()
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="11:22:33:44:55:01", entry_id="member", disabled_by=ConfigEntryDisabler.USER
    )
    entry.add_to_hass(hass)
    await centre.async_replace_dreamview_group((member(address=entry.unique_id),))
    assert not (await async_load_dreamview_claims(hass))["member"]["disabled_by_dreamview"]
    entry.disabled_by = None

    async def set_disabled(entry_id, disabled_by):
        entry.disabled_by = disabled_by

    monkeypatch.setattr(hass.config_entries, "async_set_disabled_by", AsyncMock(side_effect=set_disabled))
    with patch("custom_components.ha_govee_led_ble.GoveeBLECoordinator") as constructor:
        with pytest.raises(ConfigEntryNotReady):
            await async_setup_entry(hass, entry)
        constructor.assert_not_called()
    await hass.async_block_till_done()
    assert entry.disabled_by == ConfigEntryDisabler.USER
    await centre.async_delete_dreamview_group()
    assert entry.disabled_by is None


async def test_dreamview_disconnect_failure_does_not_poison_native_entry_unload(hass, monkeypatch):
    from homeassistant.config_entries import ConfigEntryState

    from custom_components import ha_govee_led_ble as integration
    from custom_components.ha_govee_led_ble.coordinator_dreamview import async_load_dreamview_claims

    centre = coordinator(hass, "H66A0")
    centre.async_write_effect_sequence = AsyncMock()
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="11:22:33:44:55:01", entry_id="member", state=ConfigEntryState.LOADED
    )
    entry.add_to_hass(hass)
    with current_entry.set(entry):
        target: Any = GoveeBLECoordinator(hass, entry.unique_id, "H1A42", configuration_url=None)
    entry.runtime_data = target
    client = SimpleNamespace(is_connected=True, disconnect=AsyncMock(side_effect=BleakError("release failed")))
    target._client = client
    entry._integration_for_domain = SimpleNamespace(
        domain=DOMAIN, async_get_component=AsyncMock(return_value=integration)
    )
    hass.config.components.add(DOMAIN)
    monkeypatch.setattr(hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True))
    monkeypatch.setattr(hass.config_entries, "async_setup", AsyncMock(return_value=True))
    monkeypatch.setattr(integration, "_async_update_editor_panel", AsyncMock())
    with pytest.raises(BleakError, match="could not be released"):
        await centre.async_replace_dreamview_group((member(address=entry.unique_id),))
    assert entry.state == ConfigEntryState.NOT_LOADED
    assert entry.disabled_by is None
    assert target._client is client
    assert await async_load_dreamview_claims(hass) == {}
    centre.async_write_effect_sequence.assert_not_awaited()


async def test_dreamview_startup_disable_does_not_hold_claims_lock_while_waiting_for_setup(hass):
    from custom_components.ha_govee_led_ble.coordinator_dreamview import (
        _async_save_dreamview_claims,
        _claims_lock,
        async_guard_dreamview_entry,
    )

    centre = coordinator(hass, "H66A0")
    entry = MockConfigEntry(domain=DOMAIN, unique_id="11:22:33:44:55:01", entry_id="member")
    entry.add_to_hass(hass)
    hass.config.components.add(DOMAIN)
    await _async_save_dreamview_claims(
        hass,
        {"member": {"centre_entry_id": centre.config_entry.entry_id, "disabled_by_dreamview": True}},
    )
    async with entry.setup_lock:
        assert await async_guard_dreamview_entry(hass, entry)
        await asyncio.sleep(0)
        async with asyncio.timeout(0.2):
            async with _claims_lock(hass):
                pass
    await hass.async_block_till_done()
    assert entry.disabled_by is not None


async def test_dreamview_claim_blocks_queued_commands_callbacks_and_physical_write(hass):
    from custom_components.ha_govee_led_ble.control_arbiter import ControlIntent

    target = coordinator(hass)
    client = SimpleNamespace(is_connected=True, write_gatt_char=AsyncMock(), disconnect=AsyncMock())
    target._client = client
    target._ensure_connected = AsyncMock(return_value=client)
    packet = frame("330101")
    await target._lock.acquire()
    queued = asyncio.create_task(target.send_command(packet))
    await asyncio.sleep(0)
    target._dreamview_claimed = True
    target._lock.release()
    with pytest.raises(BleakError, match="DreamView"):
        await queued
    target._ensure_connected.assert_not_awaited()
    before, started, writer = AsyncMock(), AsyncMock(), AsyncMock()
    with pytest.raises(BleakError, match="DreamView"):
        await target.async_write_effect_sequence(
            (packet,), intent=ControlIntent.APPLY, before_write=before, attempt_started=started, writer=writer
        )
    before.assert_not_awaited()
    started.assert_not_awaited()
    writer.assert_not_awaited()
    target._dreamview_claimed = False

    def claim():
        target._dreamview_claimed = True

    with pytest.raises(BleakError, match="DreamView"):
        await target._async_write_packet(client, packet, arm_expected=True, before_write=claim)
    assert target.control_write_attempts == 0
    client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("during_encryption", [False, True])
async def test_dreamview_mid_connection_claim_aborts_without_retry_or_crypto_mask(hass, monkeypatch, during_encryption):
    from custom_components.ha_govee_led_ble.govee_encryption.session import GoveeEncryptionSession

    target = coordinator(hass)
    client = SimpleNamespace(is_connected=True, disconnect=AsyncMock(), write_gatt_char=AsyncMock())

    async def disconnect():
        client.is_connected = False

    client.disconnect.side_effect = disconnect

    async def establish(*_args, **_kwargs):
        if not during_encryption:
            target._dreamview_claimed = True
        return client

    async def select(session, *_args, **_kwargs):
        session.version = 1
        target._dreamview_claimed = True

    connect = AsyncMock(side_effect=establish)
    monkeypatch.setattr("custom_components.ha_govee_led_ble.coordinator.async_establish_ble_connection", connect)
    monkeypatch.setattr(GoveeEncryptionSession, "async_select", select)
    with pytest.raises(BleakError, match="DreamView"):
        await target.send_command(frame("330101"))
    connect.assert_awaited_once()
    assert not client.is_connected
    client.write_gatt_char.assert_not_awaited()
