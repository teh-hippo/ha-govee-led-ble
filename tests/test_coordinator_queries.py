"""Coordinator query selection, freshness and deadline tests."""

import asyncio
import time
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, ModelProfile, ReadDomain
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_blank_screen_query,
    build_brightness_query,
    build_colour_mode_query,
    build_firmware_query,
    build_hardware_query,
    build_power_query,
    build_relative_brightness_query,
    build_segment_query,
    build_subordinate_query,
    build_white_balance_query,
)
from custom_components.ha_govee_led_ble.scenes import MODEL_SCENES
from custom_components.ha_govee_led_ble.transport import ENCRYPTION_UUID, WRITE_UUID, xor_checksum
from custom_components.ha_govee_led_ble.video_applicability import video_identity_fields
from tests.coordinator_test_support import _CONFIGURATION_URL, _c, _packet

M = "custom_components.ha_govee_led_ble.coordinator"


@pytest.mark.parametrize("missing", ["zone", "power_on"])
@pytest.mark.parametrize("transport_error", [False, True])
async def test_h607c_optional_setting_timeout_preserves_required_setup(
    hass, monkeypatch, virtual_clock, missing, transport_error
):
    c = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H607C", configuration_url=None)
    c.pact_type, c.pact_code = 1, 1
    c._resolve_device_profile()
    c._present = True
    client = MagicMock(is_connected=True, disconnect=AsyncMock(), start_notify=AsyncMock())

    async def connect():
        c._client = client
        await c._start_notify()
        return client

    async def disconnect(_client):
        client.is_connected = False
        c._clear_client_state(client)

    async def write(_uuid, packet, **_kwargs):
        receive = client.start_notify.await_args.args[1]
        expected_query = b"\xaa\x07\x08" if missing == "zone" else b"\xaa\x41\x00"
        if transport_error and packet.startswith(expected_query):
            raise BleakError("optional query failed")
        if packet == build_power_query("H607C", profile=c.profile):
            receive(None, bytearray(_packet(0xAA, 1, [1])))
        elif packet == build_brightness_query("H607C", profile=c.profile):
            receive(None, bytearray(_packet(0xAA, 4, [37])))
        elif packet[:3] == b"\xaa\x07\x08" and missing != "zone":
            receive(None, bytearray(_packet(0xAA, 7, [8, 37, 7])))
        elif packet[:2] == b"\xaa\xa3":
            receive(None, bytearray(_packet(0xAA, 0xA3, [0])))

    client.write_gatt_char = AsyncMock(side_effect=write)
    monkeypatch.setattr(c, "_ensure_connected", AsyncMock(side_effect=connect))
    monkeypatch.setattr(c, "_disconnect_if_current_locked", AsyncMock(side_effect=disconnect))
    snapshot = await c._async_update_data()
    assert snapshot["is_on"] and snapshot["brightness_pct"] == 37
    assert c._state_read_available
    assert c._client is None and not client.is_connected
    assert c._notification_token is None
    expected_query = b"\xaa\x07\x08" if missing == "zone" else b"\xaa\x41\x00"
    assert client.write_gatt_char.await_args.args[1].startswith(expected_query)
    client.start_notify.await_args.args[1](None, bytearray(_packet(0xAA, 7, [8, 37, 0])))
    assert not c.boolean_control_state


async def test_h607c_marker_only_poll_preserves_brightness_after_optional_timeout(hass, monkeypatch, virtual_clock):
    c = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H607C", configuration_url=None)
    device = MagicMock(is_connected=True, mtu_size=100)
    device.services = [SimpleNamespace(characteristics=[SimpleNamespace(uuid=ENCRYPTION_UUID)])]
    device.read_gatt_char = AsyncMock(return_value=bytes.fromhex("020000000101"))
    device.start_notify = AsyncMock()

    async def write(_uuid, packet, **_kwargs):
        receive = device.start_notify.await_args.args[1]
        if packet == build_power_query("H607C", profile=c.profile):
            receive(None, bytearray(_packet(0xAA, 1, [1])))
        elif packet == build_brightness_query("H607C", profile=c.profile):
            receive(None, bytearray(_packet(0xAA, 4, [37])))

    async def disconnect():
        device.is_connected = False

    device.write_gatt_char = AsyncMock(side_effect=write)
    device.disconnect = AsyncMock(side_effect=disconnect)
    monkeypatch.setattr(f"{M}.async_establish_ble_connection", AsyncMock(return_value=device))
    monkeypatch.setattr(c, "_start_keep_alive", lambda: None)
    snapshot = await c._async_update_data()
    assert snapshot["is_on"] and snapshot["brightness_pct"] == 37
    assert c._state_read_available and c._client is None
    assert c.h607c_pact_readiness == "stale" and not c.profile.supports_rgb


@pytest.mark.parametrize(("poll", "reply_brightness"), [(False, True), (True, True), (False, False)])
async def test_power_required_profile_collects_optional_brightness_before_release(
    hass, monkeypatch, virtual_clock, poll, reply_brightness
):
    profile = ModelProfile(
        "Optional brightness fixture",
        command_grammar="H617A",
        status_grammar="H617A",
        read_domains=frozenset({ReadDomain.POWER, ReadDomain.BRIGHTNESS}),
        setup_required_read_domains=frozenset({ReadDomain.POWER}),
    )
    monkeypatch.setitem(MODEL_PROFILES, "H9904", profile)
    c = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H9904", configuration_url=None)
    client = MagicMock(is_connected=True, disconnect=AsyncMock())
    pending = []

    async def connect():
        c._client = client
        return client

    async def disconnect(_client):
        client.is_connected = False
        c._clear_client_state(client)

    async def brightness_reply():
        await asyncio.sleep(0.02)
        if client.is_connected:
            c._notify_callback(None, bytearray(_packet(0xAA, 4, [37])))

    async def write(_uuid, packet, **_kwargs):
        if packet == build_power_query():
            c._notify_callback(None, bytearray(_packet(0xAA, 1, [1])))
        elif packet == build_brightness_query() and reply_brightness:
            pending.append(asyncio.create_task(brightness_reply()))

    client.write_gatt_char = AsyncMock(side_effect=write)
    monkeypatch.setattr(c, "_ensure_connected", AsyncMock(side_effect=connect))
    monkeypatch.setattr(c, "_disconnect_if_current_locked", AsyncMock(side_effect=disconnect))
    try:
        if poll:
            snapshot = await c._async_update_data()
            assert not client.is_connected and snapshot["brightness_pct"] == 37
        else:
            assert await c.refresh_state(
                refresh_all=True, required_domains=profile.setup_required_read_domains, timeout=0.1
            )
        assert c.brightness_pct == (37 if reply_brightness else 100)
        assert c._field_revisions.get("brightness_pct", 0) == int(reply_brightness)
    finally:
        await asyncio.gather(*pending)
        await c.disconnect()


@pytest.fixture
def limited_readback_coord(hass):
    profile = replace(
        MODEL_PROFILES["H617A"],
        read_domains=MODEL_PROFILES["H617A"].read_domains - {ReadDomain.COLOUR_MODE, ReadDomain.SEGMENTS},
        setup_required_read_domains=frozenset({ReadDomain.POWER, ReadDomain.BRIGHTNESS}),
        segment_count=0,
        supports_segment_writes=False,
    )
    with patch(f"{M}.get_profile", return_value=profile):
        return GoveeBLECoordinator(
            hass,
            "22:33:44:55:66:77",
            "H617A",
            configuration_url=_CONFIGURATION_URL,
        )


async def test_send_state_queries_selective(coord):
    c = _c(write_gatt_char=AsyncMock())
    coord._client = c

    assert await coord._send_state_queries(query_power=False, query_brightness=True, query_color_mode=False) is True
    c.write_gatt_char.assert_awaited_once_with(WRITE_UUID, build_brightness_query(), response=False)

    c.write_gatt_char.reset_mock()
    assert await coord._send_state_queries(query_power=True, query_brightness=False, query_color_mode=True) is True
    calls = [args.args[1] for args in c.write_gatt_char.await_args_list]
    assert calls == [build_power_query(), build_colour_mode_query()]


async def test_send_state_queries_include_h6199_display_state(h6199, virtual_clock):
    from tests.test_h6199_capabilities import set_qualified_identity

    set_qualified_identity(h6199)
    h6199.pact_type = None  # This test isolates video queries, not qualified native installation queries.
    c = _c(write_gatt_char=AsyncMock())
    h6199._client = c
    assert await h6199._send_state_queries() is True
    assert [call.args[1] for call in c.write_gatt_char.await_args_list] == [
        build_power_query("H6199"),
        build_brightness_query("H6199"),
        build_colour_mode_query("H6199"),
        build_white_balance_query("H6199"),
        build_blank_screen_query("H6199"),
        build_relative_brightness_query("H6199"),
        *(build_segment_query(group, "H6199") for group in range(1, 5)),
    ]


async def test_send_state_queries_include_h617a_core_state(coord, virtual_clock):
    c = _c(write_gatt_char=AsyncMock())
    coord._client = c
    assert await coord._send_state_queries() is True
    assert [call.args[1] for call in c.write_gatt_char.await_args_list] == [
        build_power_query(),
        build_brightness_query(),
        build_colour_mode_query(),
        *(build_segment_query(group) for group in range(1, 6)),
    ]


async def test_refresh_state_query_selection(coord):
    coord.is_on = True
    coord.effect = "candy"
    coord._client = client = _c()

    async def _reply(
        *,
        query_power: bool,
        query_brightness: bool,
        query_color_mode: bool,
        deadline: float,
    ) -> bool:
        if query_power:
            coord._notify_callback(None, bytearray(_packet(0xAA, 0x01, [1])))
        if query_brightness:
            coord._notify_callback(None, bytearray(_packet(0xAA, 0x04, [42])))
        if query_color_mode:
            coord._notify_callback(None, bytearray(_packet(0xAA, 0x05, [0x04, 0x9D, 0x08])))
        return True

    with (
        patch.object(coord, "_ensure_connected", new=AsyncMock(return_value=client)),
        patch.object(coord, "_send_state_queries", new=AsyncMock(side_effect=_reply)) as sq,
    ):
        assert await coord.refresh_state(expected_effect=None, expected_on=True) is True
        sq.assert_awaited_with(query_power=True, query_brightness=False, query_color_mode=False, deadline=ANY)
        sq.reset_mock()

        assert await coord.refresh_state(expected_effect="candy", expected_on=None) is True
        sq.assert_awaited_with(query_power=False, query_brightness=False, query_color_mode=True, deadline=ANY)
        sq.reset_mock()

        assert await coord.refresh_state(expected_brightness=42) is True
        sq.assert_awaited_with(query_power=False, query_brightness=True, query_color_mode=False, deadline=ANY)
        sq.reset_mock()

        assert await coord.refresh_state(expected_effect=None, expected_on=None) is True
        sq.assert_awaited_with(query_power=True, query_brightness=False, query_color_mode=True, deadline=ANY)


async def test_h617e_legacy_scene_verifies_by_raw_selector_code(hass, virtual_clock):
    coordinator = GoveeBLECoordinator(
        hass,
        "33:44:55:66:77:89",
        "H617E",
        configuration_url=_CONFIGURATION_URL,
    )
    coordinator._client = client = _c()
    exact_codes = {scene.code for scene in MODEL_SCENES["H617E"].values()}
    legacy = next(scene for scene in MODEL_SCENES["H617A"].values() if scene.code not in exact_codes)

    async def _reply(**_kwargs) -> bool:
        coordinator._notify_callback(
            None,
            bytearray(_packet(0xAA, 0x05, [0x04, legacy.code & 0xFF, legacy.code >> 8])),
        )
        return True

    with (
        patch.object(coordinator, "_ensure_connected", new=AsyncMock(return_value=client)),
        patch.object(coordinator, "_send_state_queries", new=AsyncMock(side_effect=_reply)),
    ):
        assert await coordinator.refresh_state(expected_scene_code=legacy.code, timeout=0.02)

    assert coordinator.scene_code == legacy.code
    assert coordinator.unknown_scene_code == legacy.code


async def test_refresh_all_can_require_only_the_setup_domains(coord, virtual_clock):
    coord._client = client = _c()

    async def _reply(**_kwargs) -> bool:
        coord._notify_callback(None, bytearray(_packet(0xAA, 0x01, [1])))
        return True

    with (
        patch.object(coord, "_ensure_connected", new=AsyncMock(return_value=client)),
        patch.object(coord, "_send_state_queries", new=AsyncMock(side_effect=_reply)),
    ):
        assert await coord.refresh_state(
            refresh_all=True,
            required_domains=frozenset({ReadDomain.POWER}),
            timeout=0.02,
        )


async def test_refresh_without_colour_readback_requires_power_and_brightness_only(
    limited_readback_coord, virtual_clock
):
    limited_readback_coord._client = client = _c()
    limited_readback_coord.rgb_color = (12, 34, 56)

    async def _reply(**kwargs) -> bool:
        assert kwargs == {
            "query_power": True,
            "query_brightness": True,
            "query_color_mode": False,
            "required_domains": frozenset({ReadDomain.POWER, ReadDomain.BRIGHTNESS}),
            "optional_baselines": {},
            "deadline": ANY,
        }
        limited_readback_coord._notify_callback(None, bytearray(_packet(0xAA, 0x01, [0])))
        limited_readback_coord._notify_callback(None, bytearray(_packet(0xAA, 0x04, [40])))
        limited_readback_coord._notify_callback(None, bytearray(_packet(0xAA, 0x05, [0x15, 0x01])))
        limited_readback_coord._notify_callback(
            None,
            bytearray(
                _packet(
                    0xAA,
                    0xA5,
                    [2, 100, 255, 146, 39, 100, 255, 146, 39, 100, 255, 146, 39],
                )
            ),
        )
        return True

    with (
        patch.object(limited_readback_coord, "_ensure_connected", new=AsyncMock(return_value=client)),
        patch.object(limited_readback_coord, "_send_state_queries", new=AsyncMock(side_effect=_reply)),
    ):
        assert await limited_readback_coord.refresh_state(refresh_all=True, timeout=0.02)

    assert limited_readback_coord.is_on is False
    assert limited_readback_coord.brightness_pct == 40
    assert limited_readback_coord.rgb_color == (12, 34, 56)
    assert limited_readback_coord.color_mode is None
    assert limited_readback_coord.segment_colors == []


async def test_profile_without_colour_readback_rejects_colour_expectations(limited_readback_coord):
    with patch.object(limited_readback_coord, "_ensure_connected", new_callable=AsyncMock) as ensure:
        assert await limited_readback_coord.refresh_state(expected_effect="candy") is False
    ensure.assert_not_awaited()


async def test_h6076_refresh_all_uses_colour_mode_and_segment_readback(hass, virtual_clock):
    coordinator = GoveeBLECoordinator(
        hass,
        "33:44:55:66:77:88",
        "H6076",
        configuration_url=_CONFIGURATION_URL,
    )
    coordinator._client = client = _c()

    async def _reply(**kwargs) -> bool:
        assert kwargs["query_color_mode"] is True
        coordinator._notify_callback(None, bytearray(_packet(0xAA, 0x01, [0])))
        coordinator._notify_callback(None, bytearray(_packet(0xAA, 0x04, [40])))
        # Firmware 1.04.05's static reply: gradual on, Kelvin never echoed.
        coordinator._notify_callback(None, bytearray(_packet(0xAA, 0x05, [0x15, 0x01, 0x00, 0x00])))
        return True

    with (
        patch.object(coordinator, "_ensure_connected", new=AsyncMock(return_value=client)),
        patch.object(coordinator, "_send_state_queries", new=AsyncMock(side_effect=_reply)),
    ):
        assert await coordinator.refresh_state(refresh_all=True, timeout=0.02)

    assert coordinator.scene_name_set == frozenset(MODEL_SCENES["H6076"])
    assert coordinator.color_mode is ParsedMode.COLOUR
    assert coordinator.color_temp_kelvin is None
    assert coordinator.static_gradual is True


@pytest.mark.parametrize(("mode_id", "fixed_colour", "confirmed"), ((0, 0, True), (1, 0, True), (1, 1, False)))
async def test_h6179_setup_reads_automatic_music_and_rejects_fixed_colour_mismatch(
    hass, virtual_clock, mode_id, fixed_colour, confirmed
):
    coordinator = GoveeBLECoordinator(hass, "55:66:77:88:99:AA", "H6179", configuration_url=_CONFIGURATION_URL)
    coordinator._client = client = _c()

    async def reply(**kwargs):
        assert kwargs["query_color_mode"]
        coordinator._notify_callback(None, bytearray(_packet(0xAA, 1, [1])))
        coordinator._notify_callback(None, bytearray(_packet(0xAA, 4, [254])))
        coordinator._notify_callback(None, bytearray(_packet(0xAA, 5, [0x0E, mode_id, 99, fixed_colour, 255, 0, 0])))
        return True

    with (
        patch.object(coordinator, "_ensure_connected", AsyncMock(return_value=client)),
        patch.object(coordinator, "_send_state_queries", AsyncMock(side_effect=reply)),
    ):
        assert (
            await coordinator.refresh_state(
                refresh_all=True,
                required_domains=coordinator.profile.setup_required_read_domains,
                expected_music_mode=f"mode_{mode_id}",
                expected_music_sensitivity=99,
                expected_music_auto_color=True,
                timeout=0.02,
            )
        ) is confirmed


async def test_refresh_reply_timeout_starts_after_connection(coord, virtual_clock):
    client = _c()

    async def connect():
        await asyncio.sleep(0.03)
        coord._client = client
        return client

    async def reply(**_kwargs) -> bool:
        coord._notify_callback(
            None,
            bytearray(_packet(0xAA, 0x01, [1])),
        )
        return True

    with (
        patch.object(
            coord,
            "_ensure_connected",
            new=AsyncMock(side_effect=connect),
        ),
        patch.object(
            coord,
            "_send_state_queries",
            new=AsyncMock(side_effect=reply),
        ),
    ):
        assert await coord.refresh_state(
            expected_on=True,
            timeout=0.02,
        )

    client.disconnect.assert_not_awaited()


async def test_refresh_state_queries_each_display_domain(h6199):
    from tests.test_h6199_capabilities import QUALIFIED

    vars(h6199).update(QUALIFIED)
    h6199._confirmed_identity_fields.update(video_identity_fields(h6199.profile))
    h6199._client = client = _c()

    async def _reply(**kwargs) -> bool:
        if kwargs.get("query_white_balance"):
            h6199._notify_callback(None, bytearray(_packet(0xAA, 0xA9, [0x00, 0x06, 1, 16, 3, 1, 21, 5])))
        if kwargs.get("query_blank_screen"):
            h6199._notify_callback(None, bytearray(_packet(0xAA, 0xA9, [0x0A, 0x06, 1, 2, 10, 0, 120, 0])))
        if kwargs.get("query_relative_brightness"):
            h6199._notify_callback(None, bytearray(_packet(0xAA, 0xAE, [1, 4, 51, 20, 31, 41])))
        return True

    with (
        patch.object(h6199, "_ensure_connected", new=AsyncMock(return_value=client)),
        patch.object(h6199, "_send_state_queries", new=AsyncMock(side_effect=_reply)) as queries,
    ):
        assert await h6199.refresh_state(expected_white_balance=(21, 5))
        assert queries.await_args.kwargs["query_white_balance"] is True
        queries.reset_mock()
        assert await h6199.refresh_state(expected_blank_screen=True)
        assert queries.await_args.kwargs["query_blank_screen"] is True
        queries.reset_mock()
        assert await h6199.refresh_state(expected_relative_brightness=(51, 20, 31, 41))
        assert queries.await_args.kwargs["query_relative_brightness"] is True
        queries.reset_mock()
        assert await h6199.refresh_state(
            refresh_all=True,
            required_domains=frozenset({ReadDomain.DISPLAY_SETTING, ReadDomain.RELATIVE_BRIGHTNESS}),
        )
        assert queries.await_args.kwargs["query_white_balance"] is True
        assert queries.await_args.kwargs["query_blank_screen"] is True
        assert queries.await_args.kwargs["query_relative_brightness"] is True


async def test_refresh_state_rejects_optimistic_value_without_fresh_reply(coord, virtual_clock):
    coord.is_on = True
    coord._client = client = _c()
    with (
        patch.object(coord, "_ensure_connected", new=AsyncMock(return_value=client)),
        patch.object(coord, "_send_state_queries", new=AsyncMock(return_value=True)) as queries,
        patch.object(coord, "_disconnect_if_current_locked", new_callable=AsyncMock) as disconnect,
    ):
        assert await coord.refresh_state(expected_on=True, timeout=0.01) is False
    assert queries.await_count == 2
    disconnect.assert_awaited_once_with(client)


async def test_refresh_state_ignored_stale_reply_does_not_confirm(coord, virtual_clock):
    coord.music_mode = "rhythm"
    coord._client = client = _c()
    coord._expected_state["music_mode"] = ("rhythm", time.monotonic() + 60)

    async def _stale_reply(**kwargs) -> bool:
        coord._notify_callback(
            None,
            bytearray(_packet(0xAA, 0x05, [0x13, 0x04, 66, 0x00, 0x01, 1, 2, 3])),
        )
        return True

    with (
        patch.object(coord, "_ensure_connected", new=AsyncMock(return_value=client)),
        patch.object(coord, "_send_state_queries", new=AsyncMock(side_effect=_stale_reply)),
        patch.object(coord, "_disconnect_if_current_locked", new_callable=AsyncMock) as disconnect,
    ):
        assert await coord.refresh_state(expected_music_mode="rhythm", timeout=0.01) is False
    disconnect.assert_not_awaited()


async def test_refresh_state_requires_fresh_power_and_video_replies(coord, virtual_clock):
    coord.is_on = True
    coord.video_mode = "game"
    coord._client = client = _c()

    async def _video_only(**kwargs) -> bool:
        coord._notify_callback(None, bytearray(_packet(0xAA, 0x05, [0x00, 0x00, 0x01, 60])))
        return True

    with (
        patch.object(coord, "_ensure_connected", new=AsyncMock(return_value=client)),
        patch.object(coord, "_send_state_queries", new=AsyncMock(side_effect=_video_only)),
        patch.object(coord, "_disconnect_if_current_locked", new_callable=AsyncMock) as disconnect,
    ):
        assert await coord.refresh_state(expected_on=True, expected_video_mode="game", timeout=0.01) is False
    disconnect.assert_awaited_once_with(client)


async def test_refresh_state_rejects_wrong_video_parameters(coord, virtual_clock):
    coord._client = client = _c()

    async def _wrong_video(**kwargs) -> bool:
        coord._notify_callback(None, bytearray(_packet(0xAA, 0x01, [1])))
        coord._notify_callback(
            None,
            bytearray(_packet(0xAA, 0x05, [0x00, 0x01, 0x01, 100, 0, 0])),
        )
        return True

    with (
        patch.object(coord, "_ensure_connected", new=AsyncMock(return_value=client)),
        patch.object(coord, "_send_state_queries", new=AsyncMock(side_effect=_wrong_video)),
        patch.object(coord, "_disconnect_if_current", new_callable=AsyncMock) as disconnect,
    ):
        assert (
            await coord.refresh_state(
                expected_on=True,
                expected_video_mode="game",
                expected_video_full_screen=False,
                expected_video_saturation=60,
                expected_video_sound_effects=True,
                expected_video_sound_effects_softness=50,
                timeout=0.01,
            )
            is False
        )
    disconnect.assert_not_awaited()


async def test_refresh_state_does_not_disconnect_replacement_client(coord, virtual_clock):
    original = _c()
    replacement = _c()
    coord._client = original

    async def _replace(**kwargs) -> bool:
        coord._client = replacement
        return True

    with (
        patch.object(coord, "_ensure_connected", new=AsyncMock(return_value=original)),
        patch.object(coord, "_send_state_queries", new=AsyncMock(side_effect=_replace)),
    ):
        assert await coord.refresh_state(expected_on=True, timeout=0.01) is False

    assert coord._client is replacement
    original.disconnect.assert_not_awaited()
    replacement.disconnect.assert_not_awaited()


@pytest.mark.parametrize("arrival", [3.9, 4.0, 4.1])
async def test_revision_wait_respects_receipt_deadline(coord, virtual_clock, arrival):
    loop = asyncio.get_running_loop()
    baseline = {"is_on": coord._field_revisions.get("is_on", 0)}
    deadline = loop.time() + 4
    reply = bytearray(_packet(0xAA, 0x01, [1]))
    await asyncio.sleep(arrival)
    coord._notify_callback(None, reply)
    # Even a callback processed before the waiter is resumed must respect its receipt deadline.
    assert await coord._wait_for_revisions(baseline, {}, deadline) is (arrival <= 4)


async def test_revision_wait_cancellation_does_not_consume_later_reply(coord, virtual_clock):
    loop = asyncio.get_running_loop()
    baseline = {"is_on": coord._field_revisions.get("is_on", 0)}
    deadline = loop.time() + 4
    waiting = asyncio.create_task(coord._wait_for_revisions(baseline, {}, deadline))
    await asyncio.sleep(0)
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    assert coord._field_revisions.get("is_on", 0) == baseline["is_on"]
    reply = bytearray(_packet(0xAA, 0x01, [1]))
    loop.call_later(1, coord._notify_callback, None, reply)
    assert await coord._wait_for_revisions(baseline, {}, deadline)


async def test_send_identity_queries_only_unknown(coord):
    c = _c(write_gatt_char=AsyncMock())
    coord._client = c
    await coord._send_identity_queries()
    assert [call.args[1] for call in c.write_gatt_char.await_args_list] == [
        build_hardware_query(),
        build_firmware_query(),
    ]
    # Only the still-unknown value is re-queried.
    coord.fw_version, coord.hw_version = "3.02.24", None
    c.write_gatt_char.reset_mock()
    await coord._send_identity_queries()
    c.write_gatt_char.assert_awaited_once_with(WRITE_UUID, build_hardware_query(), response=False)
    # Both known -> nothing sent.
    coord.hw_version = "3.01.01"
    c.write_gatt_char.reset_mock()
    await coord._send_identity_queries()
    c.write_gatt_char.assert_not_awaited()


async def test_h6199_identity_queries_reconfirm_all_revision_fields_on_a_new_connection(h6199):
    c = _c(write_gatt_char=AsyncMock())
    h6199._client = c

    await h6199._send_identity_queries()

    assert [item.args[1] for item in c.write_gatt_char.await_args_list] == [
        build_hardware_query("H6199"),
        build_firmware_query("H6199"),
        build_subordinate_query(0x20, "H6199"),
        build_subordinate_query(0x21, "H6199"),
    ]
    assert all(packet[1] != 0x14 for packet in (item.args[1] for item in c.write_gatt_char.await_args_list))

    h6199.fw_version = "1.10.04"
    h6199.hw_version = "3.02.01"
    h6199.subordinate_20_version = "1.03.00"
    h6199.subordinate_21_version = "1.00.33"
    h6199._confirmed_identity_fields.update(video_identity_fields(h6199.profile) - {"subordinate_21_version"})
    c.write_gatt_char.reset_mock()

    await h6199._send_identity_queries()

    c.write_gatt_char.assert_awaited_once_with(
        WRITE_UUID,
        build_subordinate_query(0x21, "H6199"),
        response=False,
    )


@pytest.mark.parametrize("model", ["H66A0", "H1A42", "H61F5"])
@pytest.mark.parametrize(
    ("reply", "expected"),
    [("15000bb8", {"expected_color_temp_kelvin": 3000}), ("15000000", {"expected_zero_kelvin": True})],
)
async def test_static_readback_confirms_measured_kelvin_and_rgb(
    hass, monkeypatch, model, reply, expected, virtual_clock
):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", model, configuration_url="test")

    async def transmit(_uuid, packet, **_kwargs):
        if packet[1] == 0x05:
            frame = bytes.fromhex("aa05" + reply).ljust(19, b"\0")
            coordinator._notify_callback(None, frame + bytes((xor_checksum(frame),)))

    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=transmit), disconnect=AsyncMock())
    coordinator._client = client
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    if model == "H61F5":
        assert not await coordinator.refresh_state(**expected)
        client.write_gatt_char.assert_not_awaited()
    else:
        assert await coordinator.refresh_state(**expected)
