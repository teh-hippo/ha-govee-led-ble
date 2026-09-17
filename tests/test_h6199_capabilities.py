"""H6199 software revision routing and captured music semantics, not hardware qualification."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, ReadDomain
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.effect_catalogue import MODEL_EFFECT_CATALOGUES
from custom_components.ha_govee_led_ble.effect_contracts import CapabilityState
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_blank_screen_query,
    build_brightness_query,
    build_colour_mode_query,
    build_firmware_query,
    build_h6199_control,
    build_h6199_control_query,
    build_hardware_query,
    build_power_query,
    build_relative_brightness_query,
    build_subordinate_query,
    build_video_mode,
    build_white_balance,
    build_white_balance_query,
)
from custom_components.ha_govee_led_ble.music_commands import resolve_music_profile
from custom_components.ha_govee_led_ble.transport import xor_checksum
from custom_components.ha_govee_led_ble.video_applicability import (
    h6199_camera_controls_state,
    video_control_states,
    video_identity_fields,
)

QUALIFIED = dict(
    fw_version="1.10.04",
    hw_version="3.02.01",
    subordinate_20_version="1.03.00",
    subordinate_21_version="1.00.33",
    pact_type=2,
    pact_code=1,
)


@pytest.mark.parametrize("mode,colour", [("energetic", False), ("rhythm", True), ("spectrum", True), ("rolling", True)])
@pytest.mark.parametrize("sensitivity", [0, 100])
def test_catalogue_matches_music_backend(mode, colour, sensitivity):
    metadata = MODEL_EFFECT_CATALOGUES["H6199"].to_dict()["music_settings"][mode]
    assert metadata["colour"] is colour
    assert metadata["style"] is (mode == "rhythm")
    assert metadata["available"]
    resolve_music_profile("H6199", mode, sensitivity, None, None, {})
    if colour:
        _, _, packets = resolve_music_profile("H6199", mode, sensitivity, (32, 96, 160), None, {})
        assert packets[-1][4:10] == bytes((sensitivity, 0, 1, 32, 96, 160))
    else:
        with pytest.raises(ValueError, match="fixed music colour"):
            resolve_music_profile("H6199", mode, sensitivity, (32, 96, 160), None, {})


@pytest.mark.parametrize("sensitivity", [-1, 101, True])
def test_music_rejects_out_of_bounds(sensitivity):
    with pytest.raises(ValueError, match="sensitivity"):
        resolve_music_profile("H6199", "spectrum", sensitivity, None, None, {})


@pytest.mark.parametrize(
    "changes,control,expected",
    [
        ({}, "relative_brightness", "supported"),
        ({"hw_version": "3.02.10"}, "blank_screen", "supported"),
        ({"hw_version": "3.02.11"}, "relative_brightness", "unsupported"),
        ({"subordinate_20_version": "1.03.01"}, "blank_screen", "unsupported"),
        ({"fw_version": "1.10.01"}, "relative_brightness", "unsupported"),
        ({"subordinate_21_version": "1.00.29"}, "relative_brightness", "unsupported"),
        ({"fw_version": "1.10.02", "subordinate_21_version": "1.00.30"}, "relative_brightness", "supported"),
        ({"fw_version": "1.08.10"}, "white_balance", "unsupported"),
        ({"fw_version": "1.08.11", "subordinate_21_version": "1.00.23"}, "white_balance", "supported"),
        ({"subordinate_20_version": "1.00.01"}, "white_balance", "unsupported"),
        ({"hw_version": None}, "white_balance", "evidence_gap"),
        ({"hw_version": None, "fw_version": "1.00.01"}, "white_balance", "unsupported"),
        ({"hw_version": "malformed"}, "relative_brightness", "evidence_gap"),
        ({"hw_version": "1.00.01", "fw_version": "1.06.01"}, "sound_effects", "supported"),
        ({"hw_version": "1.00.01", "fw_version": "1.06.00"}, "sound_effects", "unsupported"),
        ({"fw_version": "1.07.02"}, "sound_effects", "supported"),
        ({"fw_version": "1.07.01"}, "sound_effects", "unsupported"),
        ({"pact_type": 3, "fw_version": None, "hw_version": None}, "sound_effects", "supported"),
        ({"pact_type": None, "fw_version": "1.00.01"}, "sound_effects", "evidence_gap"),
    ],
)
def test_apk_revision_gates(changes, control, expected):
    identity = SimpleNamespace(**(QUALIFIED | changes))
    states = video_control_states(MODEL_PROFILES["H6199"], identity)
    assert states[control] == expected
    assert states["capture_region"] is CapabilityState.SUPPORTED
    assert states["black_border"] is CapabilityState.UNSUPPORTED
    narrowed = replace(MODEL_PROFILES["H6199"], supports_white_balance=False)
    assert video_control_states(narrowed, identity)["white_balance"] is CapabilityState.UNSUPPORTED


def test_unknown_and_exact_camera_qualification():
    profile = MODEL_PROFILES["H6199"]
    assert video_control_states(profile, SimpleNamespace())["blank_screen"] is CapabilityState.EVIDENCE_GAP
    assert h6199_camera_controls_state("H6199", SimpleNamespace(**QUALIFIED)) is CapabilityState.SUPPORTED
    assert h6199_camera_controls_state("H6199", SimpleNamespace()) is CapabilityState.EVIDENCE_GAP
    assert h6199_camera_controls_state("H6099", SimpleNamespace(**QUALIFIED)) is CapabilityState.UNSUPPORTED
    assert (
        h6199_camera_controls_state("H6199", SimpleNamespace(**(QUALIFIED | {"fw_version": "1.11.00"})))
        is CapabilityState.EVIDENCE_GAP
    )
    assert (
        h6199_camera_controls_state("H6199", SimpleNamespace(**(QUALIFIED | {"fw_version": "1.00.01"})))
        is CapabilityState.EVIDENCE_GAP
    )
    assert set(QUALIFIED) - {"pact_type", "pact_code"} == video_identity_fields(profile)
    assert profile.dreamview_max_sub_devices == 0


@pytest.mark.parametrize("revision", ["old", "qualified", "unknown"])
async def test_basic_setup_survives_optional_silence(hass, monkeypatch, revision):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url="test")
    coordinator._note_advertisement(SimpleNamespace(manufacturer_data={34818: bytes.fromhex("ec00020100")}))
    assert (coordinator.pact_type, coordinator.pact_code) == (2, 1)
    assert not coordinator._advertised_encryption
    if revision != "unknown":
        # Identity values are synthetic routing input, not an older-hardware test.
        for field, value in QUALIFIED.items():
            setattr(coordinator, field, value)
        if revision == "old":
            coordinator.fw_version = "1.00.01"
    replies = {
        build_power_query("H6199"): "aa0100",
        build_brightness_query("H6199"): "aa0432",
        build_colour_mode_query("H6199"): "aa051500",
    }
    packets = []

    async def transmit(_uuid, packet, **kwargs):
        packets.append(packet)
        if packet in replies:
            frame = bytes.fromhex(replies[packet]).ljust(19, b"\x00")
            coordinator._notify_callback(None, frame + bytes((xor_checksum(frame),)))

    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=transmit))
    coordinator._client = client
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    await coordinator._async_update_data()
    assert coordinator.available
    assert coordinator._first_refresh_done
    assert coordinator.profile.setup_required_read_domains == {
        ReadDomain.POWER,
        ReadDomain.BRIGHTNESS,
        ReadDomain.COLOUR_MODE,
    }
    optional = {
        build_white_balance_query("H6199"),
        build_blank_screen_query("H6199"),
        build_relative_brightness_query("H6199"),
    }
    assert bool(optional & set(packets)) is (revision == "qualified")
    if revision == "old":
        prior = replace(
            coordinator.capture_effect_control_state(), blank_screen=True, video_restore_controls=("blank_screen",)
        )
        monkeypatch.setattr(coordinator, "send_command", AsyncMock())
        monkeypatch.setattr(coordinator, "refresh_state", AsyncMock(return_value=True))
        assert not await coordinator.async_restore_effect_control_state(prior, overwritten_diy_code=None)
        assert coordinator.send_command.await_count == 1  # Power only, no newer register recovery.


async def test_missing_basic_reply_still_fails_setup(hass, monkeypatch):
    from homeassistant.helpers.update_coordinator import UpdateFailed

    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url="test")
    client = MagicMock(is_connected=True)
    coordinator._client = client
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(coordinator, "_send_state_queries", AsyncMock(return_value=True))
    monkeypatch.setattr(coordinator, "_wait_for_revisions", AsyncMock(return_value=False))
    disconnect = AsyncMock()
    monkeypatch.setattr(coordinator, "_disconnect_if_current_locked", disconnect)
    with pytest.raises(UpdateFailed, match="unreachable at setup"):
        await coordinator._async_update_data()
    disconnect.assert_awaited()


async def test_reconnect_invalidates_all_h6199_revision_authorization(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url="test")
    vars(coordinator).update(QUALIFIED)
    client = MagicMock(is_connected=True, start_notify=AsyncMock(), write_gatt_char=AsyncMock(), disconnect=AsyncMock())

    async def connect(*args, **kwargs):
        assert all(getattr(coordinator, field) is None for field in video_identity_fields(coordinator.profile))
        assert h6199_camera_controls_state(coordinator.model, coordinator) is CapabilityState.EVIDENCE_GAP
        return client

    monkeypatch.setattr("custom_components.ha_govee_led_ble.coordinator.async_establish_ble_connection", connect)
    monkeypatch.setattr(coordinator, "_start_keep_alive", MagicMock())
    try:
        await coordinator._ensure_connected()
        assert client.write_gatt_char.await_count == 4
        assert coordinator._identity_incomplete()
        assert (coordinator.pact_type, coordinator.pact_code) == (2, 1)
    finally:
        await coordinator.disconnect()


@pytest.fixture
async def lifecycle(hass, monkeypatch):
    """Only the radio is fake: connection, subscriptions, parsing, guards and polling are real."""
    from homeassistant.config_entries import current_entry
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.ha_govee_led_ble.const import DOMAIN
    from tests.test_h6199_native_controls import frame

    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    with current_entry.set(entry):
        c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url="test")
    c._present = True
    c._note_advertisement(SimpleNamespace(manufacturer_data={34818: bytes.fromhex("ec00020100")}))
    replies = {
        build_hardware_query("H6199"): frame("aa0703" + b"3.02.01".hex()),
        build_firmware_query("H6199"): frame("aa06" + b"1.10.04".hex()),
        build_subordinate_query(0x20, "H6199"): frame("aa20" + b"1.03.00".hex()),
        build_subordinate_query(0x21, "H6199"): frame("aa21" + b"1.00.33".hex()),
        build_power_query("H6199"): frame("aa0101"),
        build_brightness_query("H6199"): frame("aa0432"),
        build_colour_mode_query("H6199"): frame("aa051500"),
        build_white_balance_query("H6199"): frame("aaa90006011003011003"),
        build_h6199_control_query("strip_direction"): frame("aa3001"),
        build_h6199_control_query("camera_position"): frame("aa3101"),
        build_h6199_control_query("gradient"): frame("aaa301"),
        build_h6199_control_query("camera_status"): frame("aa3201"),
    }
    clients, packets, timers = [], [], []

    async def connect(*args, **kwargs):
        client = MagicMock(is_connected=True)
        clients.append(client)
        assert c.strip_direction is c.camera_position is c.gradient is None
        assert c.camera_status == "unknown"
        receive = None

        async def subscribe(_uuid, callback):
            nonlocal receive
            receive = callback

        async def transmit(_uuid, packet, **kwargs):
            packets.append(packet)
            if packet in replies:
                # A GATT write completes before the separate BLE notification arrives.
                timers.append(asyncio.get_running_loop().call_later(0.02, receive, None, bytearray(replies[packet])))

        async def disconnect():
            client.is_connected = False
            kwargs["disconnected_callback"](client)

        client.start_notify = AsyncMock(side_effect=subscribe)
        client.write_gatt_char = AsyncMock(side_effect=transmit)
        client.disconnect = AsyncMock(side_effect=disconnect)
        return client

    monkeypatch.setattr("custom_components.ha_govee_led_ble.coordinator.async_establish_ble_connection", connect)
    monkeypatch.setattr("custom_components.ha_govee_led_ble.coordinator.IDENTITY_QUERY_TIMEOUT", 0.08)
    monkeypatch.setattr(c, "_start_keep_alive", MagicMock())
    try:
        yield c, replies, clients, packets
    finally:
        await c.disconnect()
        for timer in timers:
            timer.cancel()


@pytest.mark.parametrize("route", ["select", "white_balance", "video"])
@pytest.mark.parametrize("identity", ["qualified", "missing", "mismatched"])
async def test_real_reconnect_waits_for_identity_before_guard(lifecycle, hass, monkeypatch, route, identity):
    from custom_components.ha_govee_led_ble.native_profile_controls import apply_active_video_mode, apply_white_balance
    from custom_components.ha_govee_led_ble.select import GoveeBLEControlSelect
    from tests.test_h6199_native_controls import frame

    c, replies, clients, packets = lifecycle
    await c._async_update_data()
    assert c._client is None and clients[-1].disconnect.await_count == 1
    assert h6199_camera_controls_state(c.model, c) is CapabilityState.SUPPORTED
    if identity == "missing":
        del replies[build_firmware_query("H6199")]
    elif identity == "mismatched":
        replies[build_firmware_query("H6199")] = frame("aa06" + b"1.00.01".hex())
    packets.clear()

    async def apply():
        if route == "select":
            entity = GoveeBLEControlSelect(SimpleNamespace(runtime_data=c, entry_id="test"), "camera_position")
            entity.hass = hass
            monkeypatch.setattr("custom_components.ha_govee_led_ble.select.get_effect_backend", lambda _: None)
            await entity.async_select_option("bottom")
        elif route == "white_balance":
            assert await apply_white_balance(c, (21, 5))
        else:
            assert await apply_active_video_mode(c, mode="movie", requested_values={"sound_effects": True})

    replies[build_white_balance_query("H6199")] = frame("aaa90006011003011505")
    replies[build_colour_mode_query("H6199")] = frame("aa05000100640164")
    if identity == "qualified":
        await apply()
        expected = {
            "select": build_h6199_control("camera_position", 1),
            "white_balance": build_white_balance(21, 5, "H6199"),
            "video": build_video_mode("movie", True, 100, True, 100, "H6199"),
        }[route]
        assert expected in packets
    else:
        from homeassistant.exceptions import HomeAssistantError

        with pytest.raises((ValueError, HomeAssistantError)):
            await apply()
        assert not any(packet[0] == 0x33 for packet in packets)
    assert len(clients) == 2


async def test_poll_preserves_delayed_native_replies_until_next_query(lifecycle):
    from custom_components.ha_govee_led_ble.light import GoveeBLELight
    from custom_components.ha_govee_led_ble.select import GoveeBLEControlSelect
    from custom_components.ha_govee_led_ble.sensor import GoveeBLECameraStatus

    c, replies, clients, _ = lifecycle
    entry = SimpleNamespace(runtime_data=c, entry_id="test")
    selects = [GoveeBLEControlSelect(entry, field) for field in ("strip_direction", "camera_position", "gradient")]
    sensor = GoveeBLECameraStatus(c)
    light = GoveeBLELight(c)
    await c._async_update_data()
    assert c._client is None and not clients[-1].is_connected
    assert [entity.current_option for entity in selects] == ["anticlockwise", "bottom", "on"]
    assert sensor.native_value == "healthy" and light.available
    for control in ("strip_direction", "camera_position", "gradient", "camera_status"):
        del replies[build_h6199_control_query(control)]
    # Avoid the static-mode gradient companion answering the independent missing query.
    from tests.test_h6199_native_controls import frame

    replies[build_colour_mode_query("H6199")] = frame("aa05000100640064")
    await c._async_update_data()
    assert len(clients) == 2 and c._client is None
    assert all(entity.current_option is None for entity in selects)
    assert sensor.native_value == "unknown" and light.available
    assert c.is_on and c._first_refresh_done


async def test_basic_setup_with_missing_identity_uses_real_lifecycle(lifecycle):
    c, replies, clients, _ = lifecycle
    del replies[build_firmware_query("H6199")]
    await c._async_update_data()
    assert c.is_on and c.available and c.camera_status == "unknown"
    assert c._client is None and clients[-1].disconnect.await_count == 1
    assert h6199_camera_controls_state(c.model, c) is CapabilityState.EVIDENCE_GAP


@pytest.mark.parametrize("missing_domain", [None, "power", "brightness", "colour_mode"])
async def test_issue_293_setup_requires_only_basic_readback(lifecycle, missing_domain):
    from homeassistant.helpers.update_coordinator import UpdateFailed

    from tests.test_h6199_native_controls import frame

    c, replies, clients, packets = lifecycle
    # Reported main versions; Wi-Fi identity and Pact were not supplied.
    c.pact_type = c.pact_code = None
    replies[build_hardware_query("H6199")] = frame("aa0703" + b"1.00.01".hex())
    replies[build_firmware_query("H6199")] = frame("aa06" + b"1.07.02".hex())
    basic = {
        "power": build_power_query("H6199"),
        "brightness": build_brightness_query("H6199"),
        "colour_mode": build_colour_mode_query("H6199"),
    }
    allowed = {build_hardware_query("H6199"), build_firmware_query("H6199"), *basic.values()}
    for query in list(replies):
        if query not in allowed or query == basic.get(missing_domain):
            del replies[query]

    if missing_domain is None:
        await c._async_update_data()
        assert c.available and c.is_on and c.brightness_pct == 50
    else:
        with pytest.raises(UpdateFailed, match="unreachable at setup"):
            await c._async_update_data()

    assert c.hw_version == "1.00.01" and c.fw_version == "1.07.02"
    assert c.subordinate_20_version is c.subordinate_21_version is None
    states = video_control_states(c.profile, c)
    assert all(
        states[control] is CapabilityState.UNSUPPORTED
        for control in ("white_balance", "relative_brightness", "blank_screen")
    )
    assert not any(packet[0] == 0x33 or packet[1] in (0xA9, 0xAE, 0x30, 0x31, 0x32, 0xA3) for packet in packets)
    assert c._client is None and clients[-1].disconnect.await_count == 1
