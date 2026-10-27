import asyncio
import logging
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from bleak import BleakClient, BleakError
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_govee_led_ble.ble_connection import mark_stale_gatt_recovery
from custom_components.ha_govee_led_ble.ble_device_resolver import (
    BLEDeviceResolution,
    BLEDeviceResolver,
)
from custom_components.ha_govee_led_ble.const import (
    DOMAIN,
    MODEL_PROFILES,
    ReadDomain,
    device_profile,
)
from custom_components.ha_govee_led_ble.control_arbiter import ControlIntent
from custom_components.ha_govee_led_ble.coordinator import (
    IDENTITY_RETRY_TICKS,
    RX_STALE_TIMEOUT,
    GoveeBLECoordinator,
)
from custom_components.ha_govee_led_ble.coordinator_expectations import expectations_from_packet
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode
from custom_components.ha_govee_led_ble.effect_compiler import compile_application
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem, SingleEffect
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_brightness,
    build_brightness_query,
    build_colour_mode_query,
    build_firmware_query,
    build_hardware_query,
    build_music_mode,
    build_power,
    build_power_query,
    build_segment_query,
)
from custom_components.ha_govee_led_ble.govee_encryption import GoveeCryptoError
from custom_components.ha_govee_led_ble.protocol_core import StatusReply
from custom_components.ha_govee_led_ble.transport import WRITE_UUID, xor_checksum
from tests.coordinator_test_support import _CONFIGURATION_URL, _c, _packet

M = "custom_components.ha_govee_led_ble.coordinator"


@pytest.fixture
def h6102(hass):
    return GoveeBLECoordinator(
        hass,
        "44:55:66:77:88:99",
        "H6102",
        configuration_url=_CONFIGURATION_URL,
    )


def test_h6102_unknown_context_bootstraps_identity_with_notifications(h6102):
    assert h6102.profile.command_operations == frozenset({"power", "brightness"})
    assert h6102.rgb_variant is None
    assert h6102.firmware_source is None
    assert h6102.capability_resolution_reason == "pact_unknown"
    assert h6102.configuration_url is None
    assert h6102.profile.requires_notifications
    assert h6102.update_interval == timedelta(seconds=30)


@pytest.mark.parametrize(
    ("pact", "register", "expected"),
    [(1, 235, 92), (1, 19, 1), (1, 0, None), (10, 235, None), (10, 50, 50)],
)
def test_h6102_register_readback_uses_pact_not_payload_value(h6102, pact, register, expected):
    from tests.test_h6199_pact1 import advertise

    advertise(h6102, pact)
    frame = bytearray.fromhex(f"aa04{register:02x}" + "00" * 16 + "00")
    frame[-1] = xor_checksum(frame[:-1])
    h6102._notify_callback(None, frame)
    if expected is None:
        assert "brightness_pct" not in h6102._field_revisions
        assert h6102.packet_log[-1]["reason"] == "semantic_rejected"
    else:
        assert h6102.brightness_pct == expected
        assert h6102._field_revisions["brightness_pct"] == 1


def test_h6102_configured_firmware_does_not_invent_pact(hass):
    coordinator = GoveeBLECoordinator(
        hass,
        "44:55:66:77:88:99",
        "H6102",
        configuration_url=_CONFIGURATION_URL,
        h6102_firmware="1.03.01",
        h6102_firmware_source="configured",
    )

    assert not coordinator.profile.supports_rgb
    assert coordinator.rgb_variant is None
    assert coordinator.firmware_source == "configured"
    assert coordinator.capability_resolution_reason == "pact_unknown"


def test_h617x_uses_short_idle_release_with_periodic_polling(coord):
    assert coord.update_interval == timedelta(seconds=30)
    with patch(f"{M}.async_call_later") as call_later:
        coord._reset_disconnect_timer()
    assert call_later.call_args.args[1] == 3.0


def test_h6199_retains_default_idle_release_and_polling(h6199):
    assert h6199.update_interval == timedelta(seconds=30)
    with patch(f"{M}.async_call_later") as call_later:
        h6199._reset_disconnect_timer()
    assert call_later.call_args.args[1] == 15


@pytest.fixture
def h6125(hass):
    return GoveeBLECoordinator(
        hass,
        "66:77:88:99:AA:BB",
        "H6125",
        configuration_url=_CONFIGURATION_URL,
    )


def _qualify_h6125(coordinator, *, hardware="1.00.04"):
    coordinator.pact_type, coordinator.pact_code = 1, 2
    coordinator.fw_version, coordinator.hw_version = "1.07.00", hardware
    coordinator._resolve_device_profile()


def test_h6125_notifications_decode_register_brightness_and_submode_0x11_music(h6125):
    _qualify_h6125(h6125)
    h6125._notify_callback(None, bytearray(_packet(0xAA, 0x04, [0xFE])))
    assert h6125.brightness_pct == 100
    h6125._notify_callback(None, bytearray(_packet(0xAA, 0x04, [0x14])))
    assert h6125.brightness_pct == 1
    h6125._notify_callback(None, bytearray(_packet(0xAA, 0x05, [0x11, 0x11, 0x32, 1, 1, 255, 0, 0])))
    assert h6125.color_mode is ParsedMode.MUSIC
    assert (h6125.music_mode, h6125.music_sensitivity, h6125.music_calm, h6125.music_color) == (
        "rhythm",
        50,
        True,
        (255, 0, 0),
    )
    h6125._notify_callback(None, bytearray(_packet(0xAA, 0x04, [0x05])))
    assert h6125.brightness_pct == 1


async def test_h6125_writes_the_register_while_expectations_stay_in_percent(h6125):
    _qualify_h6125(h6125, hardware="1.00.03")
    h6125._confirmed_identity_fields.update(h6125.profile.profile_identity_fields)
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    await h6125._async_write_packet(client, build_brightness(50, "H6125"), arm_expected=True)
    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == [
        bytes.fromhex("33048000000000000000000000000000000000b7")
    ]
    assert h6125.brightness_pct == 50
    assert h6125.packet_log[-1]["outcome"] == "sent"
    music = build_music_mode(0x03, 40, (1, 2, 3), True, "H6125")
    await h6125._async_write_packet(client, music, arm_expected=True)
    assert client.write_gatt_char.await_args.args[1] == bytes.fromhex("330511112801010102030000000000000000001e")
    expected = expectations_from_packet(music, "H6125", profile=h6125.profile)
    assert (expected["music_mode"], expected["music_calm"], expected["music_color"]) == ("rhythm", True, (1, 2, 3))
    assert {"music_mode", "music_sensitivity"} <= h6125._expected_state.keys()


async def test_h6179_advertised_pact_rejects_stale_diy_at_physical_write(hass):
    from custom_components.ha_govee_led_ble.effect_compiler import compile_effect, validate_compiled_geometry
    from custom_components.ha_govee_led_ble.effect_domain import H6179SingleDiyEffect, LibraryItem

    coordinator = GoveeBLECoordinator(hass, "55:66:77:88:99:AA", "H6179", configuration_url=_CONFIGURATION_URL)
    item = LibraryItem.new("Disposable DIY", H6179SingleDiyEffect("H6179", 0, 0, 50, ((255, 0, 0),)))
    coordinator._resolve_device_profile()
    with pytest.raises(ValueError):
        compile_effect(item, "H6179", diy_code=0x1234, profile=coordinator.profile)
    coordinator._note_advertisement(SimpleNamespace(manufacturer_data={34818: bytes((0xEC, 0, 1, 1, 0))}))
    compiled = compile_effect(item, "H6179", diy_code=0x1234, profile=coordinator.profile)
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    coordinator._client = client
    coordinator._note_advertisement(SimpleNamespace(manufacturer_data={34818: bytes((0xEC, 0, 10, 1, 0))}))
    with pytest.raises(ValueError, match="transport"):
        await coordinator._async_write_packet(
            client,
            compiled.upload_packets[0],
            before_write=lambda: validate_compiled_geometry(compiled, coordinator.profile),
        )
    client.write_gatt_char.assert_not_awaited()
    current = compile_effect(item, "H6179", diy_code=0x1234, profile=coordinator.profile)
    assert current.upload_transport == "a3"
    coordinator._clear_client_state(client)
    assert coordinator.profile == device_profile("H6179", 10, 1)


def test_h6125_advertised_pact_and_notified_identity_qualify_the_profile(h6125):
    h6125.config_entry = MagicMock(entry_id="test-entry")
    h6125._note_advertisement(SimpleNamespace(manufacturer_data={34818: bytes((0xEC, 0, 1, 2, 0))}))
    assert (h6125.pact_type, h6125.pact_code) == (1, 2)
    assert h6125.profile.command_operations == frozenset({"power"})
    h6125._notify_callback(None, bytearray(_packet(0xAA, 0x06, list(b"1.07.01\0"))))
    assert h6125.profile.command_operations == frozenset({"power"})
    h6125._notify_callback(None, bytearray(_packet(0xAA, 0x07, [3, *b"1.00.03\0"])))
    assert h6125.profile.brightness_wire_range == (6, 254) and h6125.profile.supports_segments
    h6125._notify_callback(None, bytearray(_packet(0xAA, 0x04, [128])))
    assert h6125.brightness_pct == 50
    generation = h6125._profile_generation
    h6125._notify_callback(None, bytearray(_packet(0xAA, 0x06, list(b"1.06.99\0"))))
    assert h6125.profile.supports_rgb and h6125.profile.supports_segments
    assert len(h6125.profile.music_modes) == 4 and h6125._profile_generation == generation + 1


async def test_h6125_type04_sequence_reaches_the_device_as_a1_frames_then_the_selector(h6125, monkeypatch):
    _qualify_h6125(h6125)
    h6125._confirmed_identity_fields.update(h6125.profile.profile_identity_fields)
    compiled = compile_application(
        LibraryItem.new("Fade", SingleEffect(family=0, variant=0, speed=40, palette=((255, 0, 0),))),
        "H6125",
        profile=h6125.profile,
    )
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    h6125._client = client
    monkeypatch.setattr(h6125, "_ensure_connected", AsyncMock(return_value=client))
    await h6125.async_write_effect_sequence(
        list(compiled.upload_packets), intent=ControlIntent.APPLY, final_packet=compiled.activation_packet
    )
    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == [
        *compiled.upload_packets,
        compiled.activation_packet,
    ]


async def test_h6125_reconnect_retains_profile_but_limits_writes_until_identity_returns(h6125, monkeypatch):
    _qualify_h6125(h6125)
    assert h6125.profile.outbound_transform is not None

    async def establish(*args, **kwargs):
        assert h6125.fw_version == "1.07.00" and h6125.hw_version == "1.00.04"
        assert h6125.profile.outbound_transform is not None
        assert h6125._authorization_profile().command_operations == frozenset({"power"})
        raise RuntimeError("stop before connecting")

    monkeypatch.setattr("custom_components.ha_govee_led_ble.coordinator.async_establish_ble_connection", establish)
    with pytest.raises(RuntimeError, match="stop before connecting"):
        await h6125._ensure_connected()


@pytest.fixture
def h6076(hass):
    return GoveeBLECoordinator(hass, "22:33:44:55:66:77", "H6076", configuration_url=None)


def test_h6076_music_follows_advertised_pact_and_notified_software(h6076):
    h6076.config_entry = MagicMock(entry_id="test-entry")
    assert len(h6076.profile.music_modes) == 6
    h6076._note_advertisement(SimpleNamespace(manufacturer_data={34818: bytes((0xEC, 0, 1, 1, 0))}))
    assert (h6076.pact_type, h6076.pact_code) == (1, 1) and len(h6076.profile.music_modes) == 6
    assert h6076.profile.min_color_temp_kelvin == 2200
    h6076._notify_callback(None, bytearray(_packet(0xAA, 0x06, list(b"1.01.99\0"))))
    assert len(h6076.profile.music_modes) == 6 and not h6076.profile.readback_music_modes
    generation = h6076._profile_generation
    h6076._notify_callback(None, bytearray(_packet(0xAA, 0x06, list(b"1.04.05\0"))))
    assert h6076.profile == MODEL_PROFILES["H6076"] and h6076._profile_generation == generation + 1
    h6076._notify_callback(None, bytearray(_packet(0xAA, 0x06, list(b"1.01.00\0"))))
    assert len(h6076.profile.music_modes) == 6 and h6076._profile_generation == generation + 2


def test_h6076_effect_studio_link_follows_the_effective_profile(hass):
    coordinator = GoveeBLECoordinator(hass, "22:33:44:55:66:77", "H6076", configuration_url=_CONFIGURATION_URL)
    assert coordinator.configuration_url == _CONFIGURATION_URL
    coordinator.pact_type, coordinator.pact_code = 1, 1
    coordinator.fw_version = "1.04.05"
    coordinator._resolve_device_profile()
    assert coordinator.configuration_url == _CONFIGURATION_URL


def test_h6076_registered_effect_studio_link_follows_late_identity(hass):
    coordinator = GoveeBLECoordinator(hass, "22:33:44:55:66:77", "H6076", configuration_url=_CONFIGURATION_URL)
    entry = MockConfigEntry(domain=DOMAIN, unique_id=coordinator.address)
    entry.add_to_hass(hass)
    coordinator.config_entry = entry
    registry = dr.async_get(hass)
    device = registry.async_get_or_create(config_entry_id=entry.entry_id, **coordinator.device_info)
    assert str(device.configuration_url) == _CONFIGURATION_URL
    coordinator.pact_type, coordinator.pact_code = 1, 1

    coordinator._notify_callback(None, bytearray(_packet(0xAA, 0x06, list(b"1.04.05\0"))))
    assert str(registry.async_get(device.id).configuration_url) == _CONFIGURATION_URL
    coordinator._notify_callback(None, bytearray(_packet(0xAA, 0x06, list(b"1.01.00\0"))))
    assert str(registry.async_get(device.id).configuration_url) == _CONFIGURATION_URL


async def test_h6076_reconnect_retains_music_profile_but_revokes_write_authority(h6076, monkeypatch):
    h6076.pact_type, h6076.pact_code = 2, 1
    h6076.fw_version, h6076.hw_version = "1.04.05", "3.05.00"
    h6076._resolve_device_profile()
    assert len(h6076.profile.music_modes) == 12

    async def establish(*args, **kwargs):
        assert h6076.fw_version == "1.04.05" and h6076.hw_version == "3.05.00"
        assert len(h6076.profile.music_modes) == 12
        assert len(h6076._authorization_profile().music_modes) == 6
        raise RuntimeError("stop before connecting")

    monkeypatch.setattr("custom_components.ha_govee_led_ble.coordinator.async_establish_ble_connection", establish)
    with pytest.raises(RuntimeError, match="stop before connecting"):
        await h6076._ensure_connected()


def _resolution(
    device=None,
    client_class=BleakClient,
):
    return BLEDeviceResolution(MagicMock() if device is None else device, client_class)


async def test_initial_state_and_update(coord, h6199):
    assert (coord.is_on, coord.brightness_pct, coord.rgb_color) == (False, 100, (255, 255, 255))
    assert coord.effect is None and coord.address == "AA:BB:CC:DD:EE:FF" and coord.model == "H617A"
    assert (coord.music_mode, coord.video_mode, coord.diy_code) == ("off", "off", None)
    assert coord.color_mode is None
    assert coord.profile == MODEL_PROFILES["H617A"] and coord.profile.state_readable
    assert coord.profile.supports_music_mode and not coord.profile.supports_video_mode
    assert h6199.profile == device_profile("H6199", None, None) and h6199.profile.state_readable
    assert h6199.profile.supports_video_mode and not h6199.profile.supports_white_brightness
    coord.is_on, coord.brightness_pct, coord.rgb_color = True, 75, (255, 0, 128)
    exp = {
        "is_on": True,
        "brightness_pct": 75,
        "rgb_color": (255, 0, 128),
        "color_temp_kelvin": None,
        "effect": None,
        "diy_code": None,
    }
    coord._client = _c()
    with (
        patch.object(coord, "refresh_state", new=AsyncMock(return_value=True)),
    ):
        assert await coord._async_update_data() == exp


@pytest.mark.parametrize("clear_result", [True, False, BleakError("clear failed"), "cancel"])
async def test_stale_write_revokes_authority_before_awaited_native_clear(coord, clear_result):
    clearing = asyncio.Event()
    release = asyncio.Event()

    async def clear_cache():
        clearing.set()
        await release.wait()
        if isinstance(clear_result, Exception):
            raise clear_result
        return clear_result

    client = _c(
        start_notify=AsyncMock(),
        write_gatt_char=AsyncMock(),
        clear_cache=AsyncMock(side_effect=clear_cache),
    )
    with (
        patch(f"{M}.BLEDeviceResolver.async_resolve", return_value=_resolution()),
        patch(f"{M}.establish_connection", return_value=client),
    ):
        assert await coord._ensure_connected() is client
    receive = client.start_notify.await_args.args[1]
    client.write_gatt_char.reset_mock(side_effect=True)
    client.write_gatt_char.side_effect = BleakError("GATT characteristic not found")
    coord._arm_expected_values({"brightness_pct": 42})
    task = asyncio.create_task(coord.async_preview_write(build_power(True)))
    try:
        await asyncio.wait_for(clearing.wait(), 1)
        assert coord.fresh_services_required
        assert coord._client is None
        assert coord._notification_token is None
        assert coord._expected_state == {}
        assert coord._cancel_disconnect is None
        assert coord._keep_alive_task is None
        assert not coord._encryption.ready
        client.disconnect.assert_not_awaited()
        before = (coord.brightness_pct, dict(coord._domain_revisions), list(coord.packet_log))
        receive(None, bytearray(_packet(0xAA, 0x04, [42])))
        assert (coord.brightness_pct, coord._domain_revisions, coord.packet_log) == before
        with pytest.raises(GoveeCryptoError, match="stale_connection"):
            await coord._async_write_packet(client, build_power(False))
        client.write_gatt_char.assert_awaited_once()
        if clear_result == "cancel":
            task.cancel()
        else:
            release.set()
        error = asyncio.CancelledError if clear_result == "cancel" else BleakError
        with pytest.raises(error):
            await task
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    client.clear_cache.assert_awaited_once_with()
    client.disconnect.assert_awaited_once_with()
    assert coord.fresh_services_required
    assert coord._client is None


@pytest.mark.parametrize("outcome", ["cancel", "stale-bleak", "stale-crypto"])
@pytest.mark.parametrize("disconnect_failure", ["bleak", "runtime", "stall"])
async def test_gatt_cleanup_disconnect_failure_preserves_original_outcome(coord, outcome, disconnect_failure):
    clearing = asyncio.Event()
    release = asyncio.Event()
    disconnect_finished = asyncio.Event()
    original = (GoveeCryptoError if outcome == "stale-crypto" else BleakError)("GATT characteristic not found")

    async def clear_cache():
        clearing.set()
        await release.wait()
        return True

    async def disconnect():
        try:
            if disconnect_failure == "stall":
                await asyncio.Future()
            raise (BleakError if disconnect_failure == "bleak" else RuntimeError)("disconnect failed")
        finally:
            disconnect_finished.set()

    client = _c(
        start_notify=AsyncMock(),
        write_gatt_char=AsyncMock(),
        clear_cache=AsyncMock(side_effect=clear_cache),
        disconnect=AsyncMock(side_effect=disconnect),
    )
    with (
        patch(f"{M}.BLEDeviceResolver.async_resolve", return_value=_resolution()),
        patch(f"{M}.establish_connection", return_value=client),
    ):
        assert await coord._ensure_connected() is client
    client.write_gatt_char.reset_mock()
    client.write_gatt_char.side_effect = original

    with patch(f"{M}.VALIDATION_DISCONNECT_TIMEOUT", 0.01):
        task = asyncio.create_task(coord.async_preview_write(build_power(True)))
        try:
            await asyncio.wait_for(clearing.wait(), 1)
            assert coord.fresh_services_required
            assert coord._client is None
            client.disconnect.assert_not_awaited()
            if outcome == "cancel":
                task.cancel("cancel native cache clear")
            else:
                release.set()
            # Observe completion without a watchdog cancellation hiding an unbounded disconnect.
            done, _ = await asyncio.wait({task}, timeout=1)
            assert task in done, "GATT recovery disconnect did not respect its timeout"
            with pytest.raises(asyncio.CancelledError if outcome == "cancel" else type(original)) as raised:
                await task
            if outcome == "cancel":
                assert raised.value.args == ("cancel native cache clear",)
                assert task.cancelled()
            else:
                assert raised.value is original
        finally:
            release.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    assert disconnect_finished.is_set()
    client.clear_cache.assert_awaited_once_with()
    client.disconnect.assert_awaited_once_with()
    client.write_gatt_char.assert_awaited_once_with(WRITE_UUID, build_power(True), response=False)
    assert coord.fresh_services_required
    assert coord._client is None
    assert coord._intentional_disconnect_client is None
    assert coord._notification_token is None
    assert coord._cancel_disconnect is None
    assert coord._keep_alive_task is None
    assert not coord._encryption.ready


async def test_background_connection_use_does_not_renew_foreground_lease(coord):
    coord._client = _c()
    with patch.object(coord, "_reset_disconnect_timer") as reset:
        async with coord._control_arbiter.hold(ControlIntent.BACKGROUND):
            await coord._ensure_connected()
        reset.assert_not_called()

        async with coord._control_arbiter.hold(ControlIntent.USER):
            await coord._ensure_connected()
        reset.assert_called_once_with()


async def test_successful_command_renews_foreground_lease(coord):
    client = _c(write_gatt_char=AsyncMock())
    with (
        patch.object(coord, "_ensure_connected", new=AsyncMock(return_value=client)),
        patch.object(coord, "_reset_disconnect_timer") as reset,
    ):
        await coord.send_command(build_power(True))

    reset.assert_called_once_with()


async def test_superseded_disconnect_callback_does_not_disconnect(coord):
    with patch(f"{M}.async_call_later", return_value=MagicMock()):
        coord._reset_disconnect_timer()
        generation = coord._disconnect_generation
        coord._reset_disconnect_timer()
        with patch.object(coord, "_disconnect_locked", new_callable=AsyncMock) as disconnect:
            await coord._async_disconnect_on_timeout(generation)

    disconnect.assert_not_awaited()


async def test_background_refresh_keeps_background_intent_and_preview_admission(
    coord,
):
    coord._client = _c()

    async def reply(**_kwargs) -> bool:
        assert coord._control_arbiter.current_task_intent is ControlIntent.BACKGROUND
        assert coord.admit_preview().is_current
        coord._notify_callback(
            None,
            bytearray(_packet(0xAA, 0x01, [1])),
        )
        coord._notify_callback(
            None,
            bytearray(_packet(0xAA, 0x04, [42])),
        )
        coord._notify_callback(
            None,
            bytearray(
                _packet(
                    0xAA,
                    0x05,
                    [0x04, 0x9D, 0x08],
                )
            ),
        )
        return True

    with (
        patch.object(
            coord,
            "_send_state_queries",
            new=AsyncMock(side_effect=reply),
        ),
        patch.object(coord, "_reset_disconnect_timer") as reset,
    ):
        await coord._async_update_data()

    reset.assert_not_called()


@pytest.mark.parametrize("advertised", [False, True])
async def test_background_refresh_disconnects_poll_only_connection_after_query(coord, advertised):
    coord._present = advertised
    client = _c()

    async def refresh(**_kwargs) -> bool:
        coord._client = client
        client.disconnect.assert_not_awaited()
        return True

    with patch.object(
        coord,
        "refresh_state",
        new=AsyncMock(side_effect=refresh),
    ):
        await coord._async_update_data()

    client.disconnect.assert_awaited_once_with()
    assert coord._client is None
    assert coord.available


@pytest.mark.parametrize("advertised", [False, True])
@pytest.mark.parametrize("failure", [BleakError("No state reply"), ValueError("Unexpected read failure")])
async def test_failed_poll_revokes_read_availability_without_erasing_advertisement_presence(coord, advertised, failure):
    coord._present = advertised
    client = _c()

    async def refresh(**_kwargs) -> bool:
        coord._client = client
        return True

    with patch.object(coord, "refresh_state", new=AsyncMock(side_effect=refresh)):
        await coord._async_update_data()
    assert coord.available

    with patch.object(coord, "refresh_state", new=AsyncMock(side_effect=failure)):
        if isinstance(failure, BleakError):
            await coord._async_update_data()
        else:
            with pytest.raises(ValueError, match="Unexpected read failure"):
                await coord._async_update_data()
    assert coord.available is advertised


def test_disconnect_callback_clears_only_current_unintentional_client(coord):
    client = _c()
    coord._client = client
    coord._notify_started_monotonic = 1
    coord._last_rx_monotonic = 2
    coord._expected_state["is_on"] = (True, 3)

    with patch.object(coord, "async_update_listeners") as listeners:
        coord._disconnected_callback(client)

    assert coord._client is None
    assert coord._notify_started_monotonic is None
    assert coord._last_rx_monotonic is None
    assert coord._expected_state == {}
    listeners.assert_called_once_with()

    replacement = _c()
    coord._client = replacement
    coord._disconnected_callback(client)
    assert coord._client is replacement


async def test_disconnect(coord, h6199):
    c = _c()
    coord._client, coord._cancel_disconnect = c, (cancel := MagicMock())
    await coord.disconnect()
    c.disconnect.assert_called_once()
    cancel.assert_called_once()
    assert coord._client is None and coord._cancel_disconnect is None
    coord._client = _c(disconnect=AsyncMock(side_effect=BleakError("e")))
    await coord.disconnect()
    assert coord._client is None
    coord._client = _c(disconnect=AsyncMock(side_effect=TimeoutError))
    await coord.disconnect()
    assert coord._client is None
    coord._client = None
    await coord.disconnect()
    task = MagicMock(done=MagicMock(return_value=False), cancel=MagicMock())
    h6199._keep_alive_task, h6199._client = task, _c()
    await h6199.disconnect()
    task.cancel.assert_called_once()


async def test_disconnect_does_not_clear_replacement_client(coord):
    replacement = _c()

    async def _replace() -> None:
        coord._client = replacement
        coord._notify_started_monotonic = 10
        coord._last_rx_monotonic = 11
        coord._expected_state["is_on"] = (True, 12)

    original = _c(disconnect=AsyncMock(side_effect=_replace))
    coord._client = original

    await coord.disconnect()

    assert coord._client is replacement
    assert coord._notify_started_monotonic == 10
    assert coord._last_rx_monotonic == 11
    assert coord._expected_state["is_on"] == (True, 12)


async def test_ensure_connected(coord):
    coord._client = (c := _c())
    assert await coord._ensure_connected() is c
    coord._client = None
    with (
        patch(f"{M}.BLEDeviceResolver.async_resolve", new_callable=AsyncMock, return_value=None) as resolve,
        patch(f"{M}.asyncio.sleep", new_callable=AsyncMock),
        pytest.raises(BleakError, match="not found"),
    ):
        await coord._ensure_connected()
    assert resolve.await_count == 4


async def test_ensure_connected_retries_cache_resolution_with_wrapped_client(coord):
    device = MagicMock()
    resolver = MagicMock(spec=BLEDeviceResolver)
    resolver.async_resolve = AsyncMock(side_effect=[None, _resolution(device)])
    coord._device_resolver = resolver
    client = _c(start_notify=AsyncMock(), write_gatt_char=AsyncMock(), disconnect=AsyncMock())

    with (
        patch(f"{M}.asyncio.sleep", new_callable=AsyncMock) as sleep,
        patch(f"{M}.establish_connection", return_value=client) as connect,
        patch.object(coord, "_start_notify", new_callable=AsyncMock),
        patch.object(coord, "_send_identity_queries", new_callable=AsyncMock),
        patch.object(coord, "_send_state_queries", new_callable=AsyncMock, return_value=True),
    ):
        assert await coord._ensure_connected() is client

    assert resolver.async_resolve.await_count == 2
    sleep.assert_awaited_once()
    connect.assert_awaited_once_with(
        BleakClient,
        device,
        coord.address,
        disconnected_callback=coord._disconnected_callback,
        use_services_cache=True,
    )


async def test_resolution_reuses_selected_client_after_disconnect(coord):
    device = MagicMock()
    original_client_class = type("OriginalClient", (), {})
    resolution = _resolution(device, original_client_class)
    resolver = MagicMock(spec=BLEDeviceResolver)
    resolver.async_resolve = AsyncMock(return_value=resolution)
    coord._device_resolver = resolver
    first = _c()
    second = _c()

    with (
        patch(f"{M}.establish_connection", side_effect=[first, second]) as connect,
        patch.object(coord, "_start_notify", new_callable=AsyncMock),
        patch.object(coord, "_send_identity_queries", new_callable=AsyncMock),
        patch.object(coord, "_send_state_queries", new_callable=AsyncMock, return_value=True),
    ):
        assert await coord._ensure_connected() is first
        await coord.disconnect()
        assert await coord._ensure_connected() is second

    assert resolver.async_resolve.await_count == 2
    assert connect.await_args_list == [
        call(
            original_client_class,
            device,
            coord.address,
            disconnected_callback=coord._disconnected_callback,
            use_services_cache=True,
        ),
        call(
            original_client_class,
            device,
            coord.address,
            disconnected_callback=coord._disconnected_callback,
            use_services_cache=True,
        ),
    ]
    first.disconnect.assert_awaited_once()
    await coord.disconnect()


async def test_gatt_failure_reconnects_new_client_with_fresh_services(coord):
    device = MagicMock()
    resolver = MagicMock(spec=BLEDeviceResolver)
    resolver.async_resolve = AsyncMock(return_value=_resolution(device))
    coord._device_resolver = resolver
    first = _c(
        write_gatt_char=AsyncMock(side_effect=BleakError("GATT characteristic not found")),
        clear_cache=AsyncMock(return_value=True),
        disconnect=AsyncMock(),
    )
    bootstrap = _c(clear_cache=AsyncMock(return_value=True))
    fresh = _c(write_gatt_char=AsyncMock(), disconnect=AsyncMock())
    normal = _c(write_gatt_char=AsyncMock(), disconnect=AsyncMock())

    with (
        patch(f"{M}.establish_connection", side_effect=[first, bootstrap, fresh, normal]) as connect,
        patch(f"{M}.asyncio.sleep", new_callable=AsyncMock),
        patch.object(coord, "_start_notify", new_callable=AsyncMock),
        patch.object(coord, "_send_identity_queries", new_callable=AsyncMock),
    ):
        await coord.send_command(build_power(True))
        assert coord.fresh_services_required is False
        assert coord.fresh_service_discovery_forced is True
        assert coord.last_failure_type == "BleakError"

        await coord.disconnect()
        assert await coord._ensure_connected() is normal

    assert [item.kwargs["use_services_cache"] for item in connect.await_args_list] == [True, False, False, True]
    assert "disconnected_callback" not in connect.await_args_list[1].kwargs
    assert connect.await_args_list[2].kwargs["disconnected_callback"] == coord._disconnected_callback
    first.clear_cache.assert_awaited_once_with()
    bootstrap.clear_cache.assert_awaited_once_with()
    bootstrap.disconnect.assert_awaited_once_with()
    first.disconnect.assert_awaited_once()
    fresh.disconnect.assert_awaited_once()
    assert coord.fresh_service_discovery_forced is False
    await coord.disconnect()


async def test_stale_gatt_connection_failure_forces_next_connection_fresh(coord):
    device = MagicMock()
    resolver = MagicMock(spec=BLEDeviceResolver)
    resolver.async_resolve = AsyncMock(return_value=_resolution(device))
    coord._device_resolver = resolver
    client = _c()
    bootstrap = _c(clear_cache=AsyncMock(return_value=True))

    with (
        patch(f"{M}.establish_connection", side_effect=BleakError("GATT service not found")) as connect,
        patch.object(coord, "_start_notify", new_callable=AsyncMock),
        patch.object(coord, "_send_identity_queries", new_callable=AsyncMock),
        pytest.raises(BleakError, match="GATT service not found"),
    ):
        await coord._ensure_connected()

    assert coord.fresh_services_required is True
    assert connect.await_args.kwargs["use_services_cache"] is True

    with (
        patch(f"{M}.establish_connection", side_effect=[bootstrap, client]) as fresh_connect,
        patch.object(coord, "_start_notify", new_callable=AsyncMock),
        patch.object(coord, "_send_identity_queries", new_callable=AsyncMock),
    ):
        assert await coord._ensure_connected() is client

    assert fresh_connect.await_args_list == [
        call(BleakClient, device, coord.address, use_services_cache=False),
        call(
            BleakClient,
            device,
            coord.address,
            disconnected_callback=coord._disconnected_callback,
            use_services_cache=False,
        ),
    ]
    bootstrap.clear_cache.assert_awaited_once_with()
    bootstrap.disconnect.assert_awaited_once_with()
    assert coord.fresh_services_required is False
    assert coord.fresh_service_discovery_forced is True
    await coord.disconnect()


async def test_failed_fresh_notification_setup_retains_fresh_requirement(coord):
    device = MagicMock()
    resolver = MagicMock(spec=BLEDeviceResolver)
    resolver.async_resolve = AsyncMock(return_value=_resolution(device))
    coord._device_resolver = resolver
    mark_stale_gatt_recovery(coord.hass, coord.address)
    bootstrap = _c(clear_cache=AsyncMock(return_value=True))
    retry_bootstrap = _c(clear_cache=AsyncMock(return_value=True))
    failed = _c(
        start_notify=AsyncMock(side_effect=BleakError("notify failed")),
        disconnect=AsyncMock(),
    )
    recovered = _c(start_notify=AsyncMock(), write_gatt_char=AsyncMock(), disconnect=AsyncMock())

    with patch(f"{M}.establish_connection", side_effect=[bootstrap, failed, retry_bootstrap, recovered]) as connect:
        with pytest.raises(BleakError, match="notify failed"):
            await coord._ensure_connected()
        assert coord.fresh_services_required is True
        assert coord.fresh_service_discovery_forced is False

        assert await coord._ensure_connected() is recovered

    assert [item.kwargs["use_services_cache"] for item in connect.await_args_list] == [False] * 4
    for index, native in ((0, bootstrap), (2, retry_bootstrap)):
        assert "disconnected_callback" not in connect.await_args_list[index].kwargs
        native.clear_cache.assert_awaited_once_with()
        native.disconnect.assert_awaited_once_with()
    assert coord.fresh_services_required is False
    assert coord.fresh_service_discovery_forced is True
    failed.disconnect.assert_awaited_once()
    await coord.disconnect()


async def test_stale_gatt_identity_failure_discards_client_and_requires_fresh_services(coord):
    device = MagicMock()
    resolver = MagicMock(spec=BLEDeviceResolver)
    resolver.async_resolve = AsyncMock(return_value=_resolution(device))
    coord._device_resolver = resolver
    client = _c(
        start_notify=AsyncMock(),
        write_gatt_char=AsyncMock(side_effect=BleakError("GATT characteristic not found")),
        clear_cache=AsyncMock(return_value=True),
        disconnect=AsyncMock(),
    )

    with (
        patch(f"{M}.establish_connection", return_value=client) as connect,
        pytest.raises(BleakError, match="GATT characteristic not found"),
    ):
        await coord._ensure_connected()

    assert connect.await_args.kwargs["use_services_cache"] is True
    assert coord.fresh_services_required is True
    assert coord._client is None
    client.clear_cache.assert_awaited_once_with()
    client.disconnect.assert_awaited_once()


@pytest.mark.parametrize("stale", [False, True], ids=["ordinary-optional", "stale-gatt"])
async def test_recovery_identity_failure_only_rejects_discarded_client(coord, stale):
    mark_stale_gatt_recovery(coord.hass, coord.address.lower())
    bootstrap = _c(clear_cache=AsyncMock(return_value=True))
    error = BleakError("GATT characteristic not found" if stale else "identity query failed")
    client = _c(
        start_notify=AsyncMock(),
        write_gatt_char=AsyncMock(side_effect=error),
        clear_cache=AsyncMock(return_value=True),
    )
    with (
        patch(f"{M}.BLEDeviceResolver.async_resolve", return_value=_resolution()),
        patch(f"{M}.establish_connection", side_effect=[bootstrap, client]) as connect,
    ):
        if stale:
            with pytest.raises(BleakError, match="GATT characteristic not found"):
                await coord._ensure_connected()
            assert coord._client is None
            client.clear_cache.assert_awaited_once_with()
            client.disconnect.assert_awaited_once_with()
        else:
            assert await coord._ensure_connected() is client
            assert coord._encryption.ready
            assert coord.hw_version is None
            client.clear_cache.assert_not_awaited()
            client.disconnect.assert_not_awaited()
        assert coord.fresh_services_required is stale
        assert coord.fresh_service_discovery_forced is not stale
        assert [item.kwargs["use_services_cache"] for item in connect.await_args_list] == [False, False]
        assert "disconnected_callback" not in connect.await_args_list[0].kwargs
    bootstrap.clear_cache.assert_awaited_once_with()
    bootstrap.disconnect.assert_awaited_once_with()
    client.write_gatt_char.assert_awaited_once_with(WRITE_UUID, build_hardware_query(), response=False)
    await coord.disconnect()


@pytest.mark.parametrize("stale", [False, True], ids=["ordinary-optional", "stale-gatt"])
async def test_optional_state_query_failure_only_tolerated_on_current_client(coord, stale):
    optional = build_colour_mode_query()

    async def write(_uuid, packet, **_kwargs):
        if packet == optional:
            raise BleakError("GATT characteristic not found" if stale else "query failed")

    client = _c(
        start_notify=AsyncMock(),
        write_gatt_char=AsyncMock(side_effect=write),
        clear_cache=AsyncMock(return_value=True),
    )
    with (
        patch(f"{M}.BLEDeviceResolver.async_resolve", return_value=_resolution()),
        patch(f"{M}.establish_connection", return_value=client),
    ):
        await coord._ensure_connected()
    client.write_gatt_char.reset_mock()
    assert (
        await coord._send_state_queries(
            required_domains=frozenset({ReadDomain.POWER, ReadDomain.BRIGHTNESS}),
        )
        is not stale
    )
    packets = [item.args[1] for item in client.write_gatt_char.await_args_list]
    assert packets[:3] == [build_power_query(), build_brightness_query(), optional]
    assert coord.fresh_services_required is stale
    if stale:
        assert len(packets) == 3
        assert coord._client is None
        client.clear_cache.assert_awaited_once_with()
        client.disconnect.assert_awaited_once_with()
    else:
        assert build_segment_query(1) in packets
        assert coord._client is client
        client.clear_cache.assert_not_awaited()
        client.disconnect.assert_not_awaited()
    await coord.disconnect()


@pytest.mark.parametrize("failure", ["false", "error", "timeout", "cancel", "disconnect"])
async def test_recovery_bootstrap_failure_retains_pending_and_skips_qualification(coord, failure):
    mark_stale_gatt_recovery(coord.hass, coord.address)
    clearing = asyncio.Event()

    async def clear_cache():
        clearing.set()
        if failure in {"cancel", "timeout"}:
            await asyncio.Future()
        if failure == "error":
            raise BleakError("native clear failed")
        return failure != "false"

    bootstrap = _c(
        clear_cache=AsyncMock(side_effect=clear_cache),
        disconnect=AsyncMock(side_effect=BleakError("disconnect failed") if failure == "disconnect" else None),
    )
    with (
        patch(f"{M}.BLEDeviceResolver.async_resolve", return_value=_resolution()),
        patch(f"{M}.establish_connection", return_value=bootstrap) as connect,
        patch(
            "custom_components.ha_govee_led_ble.ble_connection.GATT_CACHE_CLEAR_TIMEOUT",
            0 if failure == "timeout" else 10,
        ),
    ):
        task = asyncio.create_task(coord._ensure_connected())
        try:
            await asyncio.wait_for(clearing.wait(), 1)
            if failure == "cancel":
                task.cancel()
            with pytest.raises(asyncio.CancelledError if failure == "cancel" else BleakError):
                await task
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    connect.assert_awaited_once()
    assert connect.await_args.kwargs == {"use_services_cache": False}
    bootstrap.clear_cache.assert_awaited_once_with()
    bootstrap.disconnect.assert_awaited_once_with()
    bootstrap.start_notify.assert_not_called()
    bootstrap.write_gatt_char.assert_not_called()
    assert coord.fresh_services_required
    assert not coord.fresh_service_discovery_forced
    assert coord._client is None
    assert not coord._connection_initializing


async def test_recovery_proxy_switch_failure_requires_another_native_bootstrap(coord):
    mark_stale_gatt_recovery(coord.hass, coord.address)
    local = _resolution(client_class=type("LocalClient", (), {}))
    proxy = _resolution(client_class=type("ProxyClient", (), {}))
    bootstrap = _c(clear_cache=AsyncMock(return_value=True))
    proxy_bootstrap = _c(clear_cache=AsyncMock(return_value=True))
    qualified = _c(start_notify=AsyncMock(), write_gatt_char=AsyncMock())
    with (
        patch(f"{M}.BLEDeviceResolver.async_resolve", side_effect=[local, proxy, proxy, proxy]),
        patch(
            f"{M}.establish_connection",
            side_effect=[
                bootstrap,
                BleakError("proxy connection failed"),
                proxy_bootstrap,
                qualified,
            ],
        ) as connect,
    ):
        with pytest.raises(BleakError, match="Failed to recover the GATT cache"):
            await coord._ensure_connected()
        assert coord.fresh_services_required
        assert coord._client is None
        assert await coord._ensure_connected() is qualified
    assert [item.args[0] for item in connect.await_args_list] == [
        local.client_class,
        proxy.client_class,
        proxy.client_class,
        proxy.client_class,
    ]
    assert [item.kwargs["use_services_cache"] for item in connect.await_args_list] == [False] * 4
    for index, client in ((0, bootstrap), (2, proxy_bootstrap)):
        assert "disconnected_callback" not in connect.await_args_list[index].kwargs
        client.clear_cache.assert_awaited_once_with()
        client.disconnect.assert_awaited_once_with()
        client.start_notify.assert_not_called()
    assert not coord.fresh_services_required
    await coord.disconnect()


async def test_keep_alive_stale_identity_failure_stops_before_state_queries(coord):
    client = _c(
        write_gatt_char=AsyncMock(side_effect=BleakError("GATT characteristic not found")),
        clear_cache=AsyncMock(return_value=True),
    )
    coord._client = client
    with (
        patch(f"{M}.asyncio.sleep", new_callable=AsyncMock),
        patch.object(coord, "_send_state_queries", new_callable=AsyncMock) as state_queries,
    ):
        await coord._keep_alive_loop()
    state_queries.assert_not_awaited()
    client.write_gatt_char.assert_awaited_once_with(WRITE_UUID, build_hardware_query(), response=False)
    client.clear_cache.assert_awaited_once_with()
    client.disconnect.assert_awaited_once_with()
    assert coord._client is None
    assert coord.fresh_services_required


async def test_start_notify(coord, h6199):
    c = _c(start_notify=AsyncMock(), write_gatt_char=AsyncMock(), disconnect=AsyncMock())
    with (
        patch(f"{M}.BLEDeviceResolver.async_resolve", new_callable=AsyncMock, return_value=_resolution()),
        patch(f"{M}.establish_connection", return_value=c),
    ):
        assert await h6199._ensure_connected() is c
    c.start_notify.assert_called_once()
    for query in (build_hardware_query("H6199"), build_firmware_query("H6199")):
        c.write_gatt_char.assert_any_await(WRITE_UUID, query, response=False)
    state_queries = (build_power_query("H6199"), build_brightness_query("H6199"), build_colour_mode_query("H6199"))
    assert not any(item.args[1] in state_queries for item in c.write_gatt_char.await_args_list)
    await h6199.disconnect()
    c2 = _c(start_notify=AsyncMock(), write_gatt_char=AsyncMock(), disconnect=AsyncMock())
    with (
        patch(f"{M}.BLEDeviceResolver.async_resolve", new_callable=AsyncMock, return_value=_resolution()),
        patch(f"{M}.establish_connection", return_value=c2),
    ):
        await coord._ensure_connected()
    c2.start_notify.assert_called_once()
    for query in (build_hardware_query("H617A"), build_firmware_query("H617A")):
        c2.write_gatt_char.assert_any_await(WRITE_UUID, query, response=False)
    state_queries = (build_power_query(), build_brightness_query(), build_colour_mode_query())
    assert not any(item.args[1] in state_queries for item in c2.write_gatt_char.await_args_list)
    await coord.disconnect()
    h6199._client = _c(start_notify=AsyncMock(side_effect=BleakError("fail")))
    with pytest.raises(BleakError, match="fail"):
        await h6199._start_notify()
    assert h6199._notify_started_monotonic is None


@pytest.mark.parametrize("failure", ["notify", "identity_transform"])
async def test_ensure_connected_cleans_up_setup_failure(coord, failure):
    error = BleakError("notify failed") if failure == "notify" else ValueError("Cannot transform identity query")
    client = _c(
        start_notify=AsyncMock(side_effect=error if failure == "notify" else None),
        write_gatt_char=AsyncMock(),
        disconnect=AsyncMock(),
    )
    if failure == "identity_transform":
        coord.profile = replace(coord.profile, outbound_transform=MagicMock(side_effect=error))
    with (
        patch(f"{M}.BLEDeviceResolver.async_resolve", new_callable=AsyncMock, return_value=_resolution()),
        patch(f"{M}.establish_connection", return_value=client) as connect,
        pytest.raises(type(error), match=str(error)),
    ):
        if failure == "identity_transform":
            await coord.send_command(build_power(True))
        else:
            await coord._ensure_connected()
    connect.assert_awaited_once()
    client.disconnect.assert_awaited_once()
    client.write_gatt_char.assert_not_awaited()
    assert coord.packet_log == []
    assert coord._client is None
    assert coord._keep_alive_task is None
    assert coord._cancel_disconnect is None


async def test_background_refresh_disconnects_replacement_connection(coord):
    original = _c()
    replacement = _c()
    coord._client = original

    async def refresh(**_kwargs) -> bool:
        coord._client = replacement
        return True

    with patch.object(
        coord,
        "refresh_state",
        new=AsyncMock(side_effect=refresh),
    ):
        await coord._async_update_data()

    replacement.disconnect.assert_awaited_once()
    assert coord._client is None


async def test_ensure_connected_replaces_receive_stale_client(coord):
    old = _c()
    new = _c(start_notify=AsyncMock(), write_gatt_char=AsyncMock(), disconnect=AsyncMock())
    coord._client = old
    coord._notify_started_monotonic = 1.0
    with (
        patch(f"{M}.time.monotonic", return_value=RX_STALE_TIMEOUT + 2),
        patch(f"{M}.BLEDeviceResolver.async_resolve", new_callable=AsyncMock, return_value=_resolution()),
        patch(f"{M}.establish_connection", return_value=new),
    ):
        assert await coord._ensure_connected() is new
    old.disconnect.assert_awaited_once()
    new.start_notify.assert_awaited_once()
    await coord.disconnect()


async def test_keep_alive_retires_receive_stale_client(coord):
    coord._client = _c()
    scheduled = []

    def _schedule(coro, *args, **kwargs):
        scheduled.append(coro)
        coro.close()
        return MagicMock()

    with (
        patch(f"{M}.asyncio.sleep", new_callable=AsyncMock),
        patch.object(coord, "_receive_is_stale", return_value=True),
        patch.object(coord.hass, "async_create_task", side_effect=_schedule),
    ):
        await coord._keep_alive_loop()
    assert len(scheduled) == 1


async def test_disconnect_if_current_ignores_replaced_client(coord):
    old = _c()
    new = _c()
    coord._client = new

    await coord._disconnect_if_current(old)
    assert coord._client is new
    old.disconnect.assert_not_awaited()
    new.disconnect.assert_not_awaited()

    await coord._disconnect_if_current(new)
    new.disconnect.assert_awaited_once()
    assert coord._client is None


async def test_send_command_noop_during_shutdown(coord):
    """Commands must be silently dropped once HA is shutting down."""
    c = _c(write_gatt_char=AsyncMock())
    coord.hass.is_stopping = True
    with patch.object(coord, "_ensure_connected", return_value=c):
        await coord.send_command(build_power(True))
    c.write_gatt_char.assert_not_awaited()


async def test_update_data_noop_during_shutdown(coord):
    """_async_update_data must return cached state without BLE activity during shutdown."""
    coord.is_on, coord.brightness_pct = True, 50
    coord.hass.is_stopping = True
    ensure = AsyncMock()
    with patch.object(coord, "_ensure_connected", ensure):
        result = await coord._async_update_data()
    ensure.assert_not_awaited()
    assert result["is_on"] is True and result["brightness_pct"] == 50


def test_available_reflects_link_or_presence(coord):
    coord._client, coord._present = None, False
    assert coord.available is False
    coord._present = True
    assert coord.available is True
    coord._present, coord._client = False, MagicMock(is_connected=True)
    assert coord.available is True
    coord._client = MagicMock(is_connected=False)
    assert coord.available is False


def test_availability_transitions_log_once_without_address(coord, caplog):
    coord._client, coord._present = None, True

    with caplog.at_level(logging.INFO, logger="custom_components.ha_govee_led_ble.coordinator"):
        coord._set_present(False)
        coord._set_present(False)
        coord._set_present(True)
        coord._set_present(True)

    messages = [record.getMessage() for record in caplog.records]
    assert messages == ["Govee H617A is unavailable", "Govee H617A is back online"]
    assert coord.address not in caplog.text


def test_availability_log_deduplicates_across_setup_retries(hass, coord, caplog):
    coord._client, coord._present = None, False
    retry = GoveeBLECoordinator(
        hass,
        coord.address,
        coord.model,
        configuration_url=_CONFIGURATION_URL,
    )

    with caplog.at_level(logging.INFO, logger="custom_components.ha_govee_led_ble.coordinator"):
        coord._log_availability_transition()
        retry._log_availability_transition()
        retry._set_present(True)

    messages = [record.getMessage() for record in caplog.records]
    assert messages == ["Govee H617A is unavailable", "Govee H617A is back online"]


async def test_intentional_disconnect_does_not_log_unavailability(coord, caplog):
    coord._present = False
    coord._client = _c()

    with caplog.at_level(logging.INFO, logger="custom_components.ha_govee_led_ble.coordinator"):
        await coord.disconnect()

    assert caplog.records == []


def test_device_info_carries_versions_and_omits_connections(coord):
    coord.fw_version, coord.hw_version = "3.02.24", "3.01.01"
    info = coord.device_info
    assert info["sw_version"] == "3.02.24" and info["hw_version"] == "3.01.01"
    assert info["identifiers"] == {(DOMAIN, coord.address)}
    assert info["configuration_url"] == _CONFIGURATION_URL
    assert coord.address not in info["configuration_url"]
    assert "connections" not in info


@pytest.mark.parametrize(
    ("model", "display_model"),
    [("H6179", "H6179 (Experimental)"), ("H6099", "H6099"), ("H617A", "H617A")],
)
def test_device_info_shows_support_maturity_without_changing_sku_or_studio_link(hass, model, display_model):
    coordinator = GoveeBLECoordinator(
        hass,
        "AA:BB:CC:DD:EE:FF",
        model,
        configuration_url=_CONFIGURATION_URL,
    )
    info = coordinator.device_info
    assert info["model"] == display_model
    assert info["model_id"] == model
    assert info["configuration_url"] == _CONFIGURATION_URL


def test_device_info_clears_stale_configuration_url(hass):
    coordinator = GoveeBLECoordinator(
        hass,
        "33:44:55:66:77:88",
        "H6076",
        configuration_url=None,
    )
    entry = MockConfigEntry(domain=DOMAIN, unique_id=coordinator.address)
    entry.add_to_hass(hass)
    registry = dr.async_get(hass)
    registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, coordinator.address)},
        configuration_url="homeassistant://ha-govee-led-ble/editor/stale",
    )

    device = registry.async_get_or_create(config_entry_id=entry.entry_id, **coordinator.device_info)

    assert device.configuration_url is None


def test_device_info_replaces_a_stale_configuration_url(hass, coord):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=coord.address)
    entry.add_to_hass(hass)
    registry = dr.async_get(hass)
    registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, coord.address)},
        configuration_url="homeassistant://retired-editor/test-entry",
    )

    device = registry.async_get_or_create(config_entry_id=entry.entry_id, **coord.device_info)

    assert device.configuration_url == _CONFIGURATION_URL


def test_notify_callback_pushes_identity_to_own_registry_device(hass, coord):
    registry = dr.async_get(hass)
    other_entry = MockConfigEntry(domain=DOMAIN)
    other_entry.add_to_hass(hass)
    foreign_device = registry.async_get_or_create(
        config_entry_id=other_entry.entry_id,
        identifiers={(DOMAIN, coord.address)},
        sw_version="other-firmware",
        hw_version="other-hardware",
    )
    unrelated_device = registry.async_get_or_create(
        config_entry_id=coord.config_entry.entry_id,
        identifiers={(DOMAIN, "11:22:33:44:55:66")},
    )
    device = registry.async_get_or_create(config_entry_id=coord.config_entry.entry_id, **coord.device_info)
    fw = _packet(0xAA, int(StatusReply.AaDomain.fw_version), list(b"3.02.24"))
    hw = _packet(0xAA, int(StatusReply.AaDomain.hw_version), [0x03, *b"3.01.01"])
    with (
        patch.object(registry, "async_get_device", side_effect=AssertionError("Deprecated device lookup")),
        patch.object(registry, "async_update_device", wraps=registry.async_update_device) as update,
    ):
        coord._notify_callback(None, bytearray(fw))
        coord._notify_callback(None, bytearray(hw))
        assert update.call_args_list == [
            call(device.id, sw_version="3.02.24", hw_version=None),
            call(device.id, sw_version="3.02.24", hw_version="3.01.01"),
        ]
        update.reset_mock()
        coord._notify_callback(None, bytearray(fw))
        coord._notify_callback(None, bytearray(hw))
        update.assert_not_called()

    updated_device = registry.async_get(device.id)
    assert (updated_device.sw_version, updated_device.hw_version) == (coord.fw_version, coord.hw_version)
    assert registry.async_get(foreign_device.id) == foreign_device
    assert registry.async_get(unrelated_device.id) == unrelated_device


def test_note_identity_retains_versions_until_own_device_is_registered(hass, coord):
    registry = dr.async_get(hass)
    other_entry = MockConfigEntry(domain=DOMAIN)
    other_entry.add_to_hass(hass)
    foreign_device = registry.async_get_or_create(
        config_entry_id=other_entry.entry_id,
        identifiers={(DOMAIN, coord.address)},
    )
    fw = _packet(0xAA, int(StatusReply.AaDomain.fw_version), list(b"3.02.24"))
    hw = _packet(0xAA, int(StatusReply.AaDomain.hw_version), [0x03, *b"3.01.01"])
    with (
        patch.object(registry, "async_get_device", side_effect=AssertionError("Deprecated device lookup")),
        patch.object(registry, "async_update_device", wraps=registry.async_update_device) as update,
    ):
        coord._notify_callback(None, bytearray(fw))
        coord._notify_callback(None, bytearray(hw))
        update.assert_not_called()

    assert dr.async_entries_for_config_entry(registry, coord.config_entry.entry_id) == []
    assert registry.async_get(foreign_device.id) == foreign_device
    device = registry.async_get_or_create(config_entry_id=coord.config_entry.entry_id, **coord.device_info)
    assert (device.sw_version, device.hw_version) == ("3.02.24", "3.01.01")


def test_keep_alive_started_as_background_task(coord):
    """#86 guard: the lifetime keep-alive loop must be a background task (never a tracked
    setup task), or HA bootstrap waits on it and logs a "blocking start up" warning."""
    created = {}

    def _capture(hass, coro, name):
        coro.close()
        assert hass is coord.hass
        created["name"] = name
        return MagicMock()

    with patch.object(coord.config_entry, "async_create_background_task", side_effect=_capture) as spy:
        coord._start_keep_alive()
    spy.assert_called_once()
    assert "keep-alive" in created["name"]


async def test_entry_shutdown_releases_ble_resources_and_cannot_reconnect(coord):
    client = _c()
    coord._client = client
    coord._start_keep_alive()
    keep_alive = coord._keep_alive_task
    coord._reset_disconnect_timer()
    listeners = coord.hass.bus.async_listeners()[EVENT_HOMEASSISTANT_STOP]

    await coord.config_entry._async_process_on_unload(coord.hass)
    await coord.async_shutdown()

    assert keep_alive.done()
    assert coord._client is None
    assert coord._keep_alive_task is None
    assert coord._cancel_disconnect is None
    assert coord.hass.bus.async_listeners().get(EVENT_HOMEASSISTANT_STOP, 0) == listeners - 1
    client.disconnect.assert_awaited_once_with()
    with (
        patch(f"{M}.async_establish_ble_connection", new_callable=AsyncMock) as connect,
        pytest.raises(BleakError, match="shut down"),
    ):
        await coord._ensure_connected()
    connect.assert_not_awaited()


async def test_entry_shutdown_rejects_inflight_connection_completion(coord, virtual_clock):
    client = _c(services=[], start_notify=AsyncMock(), write_gatt_char=AsyncMock())
    connecting = asyncio.Event()

    async def establish(*_args, **_kwargs):
        connecting.set()
        await asyncio.sleep(19)
        return client

    with patch(f"{M}.async_establish_ble_connection", side_effect=establish) as connect:
        command = coord.hass.async_create_task(coord.send_command(build_power(True)))
        await connecting.wait()
        await coord.config_entry._async_process_on_unload(coord.hass)
        with pytest.raises(BleakError, match="shut down"):
            await command

    connect.assert_awaited_once()
    client.disconnect.assert_awaited_once_with()
    client.start_notify.assert_not_awaited()
    client.write_gatt_char.assert_not_awaited()
    assert coord._client is None and coord._keep_alive_task is None
    assert not coord.config_entry._background_tasks


async def test_packet_write_cannot_use_a_client_after_shutdown(coord):
    client = _c(write_gatt_char=AsyncMock(), disconnect=AsyncMock(side_effect=BleakError("disconnect failed")))
    coord._client = client
    await coord.async_shutdown()

    async with coord._lock:
        with pytest.raises(BleakError, match="shut down"):
            await coord._async_write_packet(client, build_power(True), arm_expected=True)

    client.write_gatt_char.assert_not_awaited()
    assert not coord._expected_state and not coord.control_write_attempts


async def test_entry_shutdown_closes_an_admitted_write_that_finishes_late(coord, virtual_clock):
    writing = asyncio.Event()
    coord.connection_mode = "hold"

    async def write(*_args, **_kwargs):
        writing.set()
        await asyncio.sleep(19)

    client = _c(write_gatt_char=AsyncMock(side_effect=write))
    coord._client = client
    coord._start_keep_alive()
    command = coord.hass.async_create_task(coord.send_command(build_power(True)))
    await writing.wait()

    await coord.config_entry._async_process_on_unload(coord.hass)
    with pytest.raises(BleakError, match="shut down"):
        await command

    client.disconnect.assert_awaited_once_with()
    assert coord._client is None and coord._keep_alive_task is None
    assert coord._cancel_disconnect is None
    assert not coord.config_entry._background_tasks


async def test_entry_shutdown_during_stale_disconnect_does_not_start_a_connection(coord, virtual_clock):
    disconnecting = asyncio.Event()

    async def disconnect():
        disconnecting.set()
        await asyncio.sleep(5)

    client = _c(disconnect=AsyncMock(side_effect=disconnect))
    coord._client = client
    with (
        patch.object(coord, "_receive_is_stale", return_value=True),
        patch(f"{M}.async_establish_ble_connection", new_callable=AsyncMock) as establish,
    ):
        command = coord.hass.async_create_task(coord.send_command(build_power(True)))
        await disconnecting.wait()
        await coord.config_entry._async_process_on_unload(coord.hass)
        with pytest.raises(BleakError, match="shut down"):
            await command

    establish.assert_not_awaited()
    client.disconnect.assert_awaited_once_with()
    assert coord._client is None and coord._keep_alive_task is None
    assert coord._cancel_disconnect is None


async def test_keep_alive_retries_identity_until_bounded(coord):
    """Connect-time identity replies can be missed, so retries remain bounded."""
    coord._client = client = _c(write_gatt_char=AsyncMock(), disconnect=AsyncMock())
    coord.fw_version = coord.hw_version = None
    calls = {"n": 0}

    async def _state(**_kw):
        calls["n"] += 1
        return calls["n"] < IDENTITY_RETRY_TICKS + 2  # break two ticks past the cap

    with (
        patch.object(coord, "_send_identity_queries", new_callable=AsyncMock) as ident,
        patch.object(coord, "_send_state_queries", side_effect=_state),
        patch(f"{M}.asyncio.sleep", new_callable=AsyncMock),
    ):
        await coord._keep_alive_loop()
    assert ident.await_count == IDENTITY_RETRY_TICKS
    client.disconnect.assert_awaited_once()
    assert coord._client is None


async def test_keep_alive_retries_missing_hw_when_fw_known(coord):
    coord._client = client = _c(write_gatt_char=AsyncMock(), disconnect=AsyncMock())
    coord.fw_version, coord.hw_version = "3.02.24", None
    with (
        patch.object(coord, "_send_identity_queries", new_callable=AsyncMock) as ident,
        patch.object(coord, "_send_state_queries", new_callable=AsyncMock, return_value=False),
        patch(f"{M}.asyncio.sleep", new_callable=AsyncMock),
    ):
        await coord._keep_alive_loop()
    ident.assert_awaited_once_with()
    client.disconnect.assert_awaited_once()
    assert coord._client is None


async def test_keep_alive_skips_identity_when_versions_known(coord):
    coord._client = client = _c(write_gatt_char=AsyncMock(), disconnect=AsyncMock())
    coord.fw_version, coord.hw_version = "3.02.24", "3.01.01"
    with (
        patch.object(coord, "_send_identity_queries", new_callable=AsyncMock) as ident,
        patch.object(coord, "_send_state_queries", new_callable=AsyncMock, return_value=False),
        patch(f"{M}.asyncio.sleep", new_callable=AsyncMock),
    ):
        await coord._keep_alive_loop()
    ident.assert_not_awaited()
    client.disconnect.assert_awaited_once()
    assert coord._client is None


async def test_async_setup_registers_presence_and_callbacks_flip(coord):
    with patch(f"{M}.bluetooth") as bt:
        bt.async_address_present.return_value = False
        await coord._async_setup()
        bt.async_address_present.assert_called_once()
        bt.async_register_callback.assert_called_once()
        bt.async_track_unavailable.assert_called_once()
    assert coord._present is False
    with patch.object(coord, "async_update_listeners") as notify:
        coord._async_on_advertisement(MagicMock(), MagicMock())
        assert coord._present is True
        notify.assert_called_once()
        notify.reset_mock()
        coord._async_on_advertisement(MagicMock(), MagicMock())
        notify.assert_not_called()
        coord._async_on_unavailable(MagicMock())
        assert coord._present is False
        notify.assert_called_once()


async def test_first_refresh_reports_update_failed_then_degrades_silently(coord):
    with patch.object(coord, "_ensure_connected", new_callable=AsyncMock, side_effect=BleakError("down")):
        with pytest.raises(UpdateFailed):
            await coord._async_update_data()
        assert await coord._async_update_data() == coord._state_snapshot()


async def test_first_refresh_non_readable_requires_presence(hass):
    flat = replace(
        MODEL_PROFILES["H617A"],
        read_domains=frozenset(),
        setup_required_read_domains=frozenset(),
    )
    with patch(f"{M}.get_profile", return_value=flat):
        c = GoveeBLECoordinator(
            hass,
            "AA:BB:CC:DD:EE:22",
            "H617A",
            configuration_url=_CONFIGURATION_URL,
        )
    c._present = False
    with pytest.raises(UpdateFailed):
        await c._async_update_data()
    assert await c._async_update_data() == c._state_snapshot()


async def test_config_entry_first_refresh_raises_config_entry_not_ready(coord):
    coord.config_entry = MagicMock(state=ConfigEntryState.SETUP_IN_PROGRESS)
    with (
        patch(f"{M}.bluetooth") as bt,
        patch.object(coord, "_ensure_connected", new_callable=AsyncMock, side_effect=BleakError("down")),
    ):
        bt.async_address_present.return_value = False
        with pytest.raises(ConfigEntryNotReady):
            await coord.async_config_entry_first_refresh()


async def test_hold_keeps_connection_and_refreshes_basic_state_without_segments(hass, monkeypatch):
    from custom_components.ha_govee_led_ble.const import CONNECTION_MODE_HOLD, ReadDomain

    coord = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:99", "H617A", configuration_url=None)
    coord.connection_mode = CONNECTION_MODE_HOLD
    client = MagicMock(is_connected=True, disconnect=AsyncMock())
    coord._client = client
    coord._first_refresh_done = True
    send_queries = AsyncMock(return_value=True)
    refresh_connected = AsyncMock(return_value=True)
    send_identity_queries = AsyncMock()
    monkeypatch.setattr(coord, "_send_state_queries", send_queries)
    monkeypatch.setattr(coord, "_refresh_connected_state", refresh_connected)
    monkeypatch.setattr(coord, "_send_identity_queries", send_identity_queries)
    monkeypatch.setattr(coord, "_receive_is_stale", lambda: False)
    sleeps = 0

    async def sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps == 4:
            client.is_connected = False

    monkeypatch.setattr(f"{M}.asyncio.sleep", sleep)
    assert await coord._async_update_data() == coord._state_snapshot()
    await coord._keep_alive_loop()
    assert send_identity_queries.await_count == 3
    assert send_queries.await_count == 2
    assert send_queries.await_args.kwargs == {
        "query_power": True,
        "query_brightness": False,
        "query_color_mode": False,
        "required_domains": frozenset({ReadDomain.POWER}),
    }
    refresh_connected.assert_awaited_once_with(
        refresh_all=True,
        query_segments=False,
        required_domains=coord.profile.setup_required_read_domains,
    )
    client.disconnect.assert_not_awaited()


async def test_h66a0_setup_survives_identity_replies_inside_the_refresh(hass, monkeypatch, virtual_clock):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H66A0", configuration_url="test")

    def status(domain: int, payload: str) -> bytes:
        frame = bytes((0xAA, domain)) + bytes.fromhex(payload).ljust(17, b"\0")
        return frame + bytes((xor_checksum(frame),))

    replies = {0x01: "01", 0x04: "64", 0x05: "1500100400"}
    late = ((0x07, "03332e30372e3031"), (0x06, "312e30302e3234"), (0x20, "362e30312e3030"), (0x21, "312e30312e3138"))
    pages = (
        "0146ffc68246ffc68246ffc68264ffc682",
        "0264ffc68264ffc68264ffc68264ffc682",
        "0364ffc68264ffc68264ffc68264ffc682",
        "0464ffc68264ffc6820000000000000000",
    )

    async def transmit(_uuid, packet, **_kwargs):
        if packet[1] == 0x01:
            for domain, payload in late:
                coordinator._notify_callback(None, status(domain, payload))
        if packet[1] == 0xA5:
            for page in pages:
                coordinator._notify_callback(None, status(0xA5, page))
        elif packet[1] in replies:
            coordinator._notify_callback(None, status(packet[1], replies[packet[1]]))

    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=transmit), disconnect=AsyncMock())
    coordinator._client = client
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    await coordinator._async_update_data()
    assert coordinator.available
    assert (coordinator.fw_version, coordinator.hw_version) == ("1.00.24", "3.07.01")
    assert (coordinator.subordinate_20_version, coordinator.subordinate_21_version) == ("6.01.00", "1.01.18")
    assert coordinator.segment_state_source == "observed"
