import asyncio
import logging
import time
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from bleak import BleakClient, BleakError
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_govee_led_ble.ble_device_resolver import (
    BLEDeviceResolution,
    BLEDeviceResolver,
)
from custom_components.ha_govee_led_ble.const import DOMAIN, MODEL_PROFILES, MUSIC_MODE_SLUGS
from custom_components.ha_govee_led_ble.control_arbiter import BLEControlArbiter, ControlIntent
from custom_components.ha_govee_led_ble.coordinator import (
    IDENTITY_RETRY_TICKS,
    RX_STALE_TIMEOUT,
    GoveeBLECoordinator,
)
from custom_components.ha_govee_led_ble.coordinator_expectations import expectations_from_packet
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode
from custom_components.ha_govee_led_ble.effect_commands import build_h617a_diy_activation
from custom_components.ha_govee_led_ble.effect_deployments import PriorControlState
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    H6199StatusReply,
    StatusReply,
    build_brightness,
    build_brightness_query,
    build_colour_mode_query,
    build_firmware_query,
    build_h617a_scene,
    build_h6199_blank_screen,
    build_h6199_blank_screen_query,
    build_h6199_relative_brightness_query,
    build_h6199_subordinate_query,
    build_h6199_video,
    build_h6199_white_balance,
    build_h6199_white_balance_query,
    build_hardware_query,
    build_music_mode,
    build_power,
    build_power_query,
    build_segment_query,
    parse_command,
    parse_status,
)
from custom_components.ha_govee_led_ble.h6199_calibration import WHITE_BALANCE_RESET
from custom_components.ha_govee_led_ble.light_commands import (
    build_color_rgb,
    build_color_temp,
    build_segment_brightness,
    build_segment_paint,
    build_white_brightness,
    kelvin_to_rgb,
)
from custom_components.ha_govee_led_ble.native_scenes import build_native_scene_packets
from custom_components.ha_govee_led_ble.scenes import MODEL_SCENES, SCENES
from custom_components.ha_govee_led_ble.transport import WRITE_UUID, xor_checksum

M = "custom_components.ha_govee_led_ble.coordinator"
_CONFIGURATION_URL = "homeassistant://ha-govee-led-ble/editor/test-entry"

_MUSIC_SLUG_BY_ID = {code: slug for slug, code in MUSIC_MODE_SLUGS.items()}
_SCENE_EFFECT_BY_ID = {scene.code: name for name, scene in SCENES.items()}


def _packet(header: int, action: int, params: list[int]) -> bytes:
    payload = bytearray([header, action, *params][:19])
    payload.extend(b"\x00" * (19 - len(payload)))
    payload.append(xor_checksum(payload))
    return bytes(payload)


proto = SimpleNamespace(
    COLOR_MODE_DIY=int(StatusReply.ColorMode.diy),
    COLOR_MODE_SCENE=int(StatusReply.ColorMode.scene),
    COLOR_MODE_STATIC=int(StatusReply.ColorMode.static),
    COLOR_MODE_VIDEO=int(H6199StatusReply.ModeSel.video),
    FIRMWARE_PACKET_TYPE=int(StatusReply.AaDomain.fw_version),
    HARDWARE_PACKET_TYPE=int(StatusReply.AaDomain.hw_version),
    MUSIC_SLUG_BY_ID=_MUSIC_SLUG_BY_ID,
    ParsedMode=ParsedMode,
    SCENE_EFFECT_BY_ID=_SCENE_EFFECT_BY_ID,
    STATUS_HEADER=0xAA,
    WHITE_BALANCE_RESET=WHITE_BALANCE_RESET,
    build_brightness=build_brightness,
    build_color_rgb=build_color_rgb,
    build_color_temp=build_color_temp,
    build_h617a_diy_activation=build_h617a_diy_activation,
    build_packet=_packet,
    build_power=build_power,
    build_scene=build_h617a_scene,
    build_segment_paint=build_segment_paint,
    build_white_brightness=build_white_brightness,
)


@pytest.fixture
def coord(hass):
    return GoveeBLECoordinator(
        hass,
        "AA:BB:CC:DD:EE:FF",
        "H617A",
        configuration_url=_CONFIGURATION_URL,
    )


@pytest.fixture
def h6199(hass):
    return GoveeBLECoordinator(
        hass,
        "11:22:33:44:55:66",
        "H6199",
        configuration_url=_CONFIGURATION_URL,
    )


def _c(**kw):
    return MagicMock(is_connected=True, **kw)


def _resolution(
    device=None,
    client_class=BleakClient,
):
    return BLEDeviceResolution(MagicMock() if device is None else device, client_class)


async def test_control_arbiter_prioritises_waiters_reenters_and_skips_background():
    arbiter = BLEControlArbiter()
    order: list[ControlIntent] = []

    async def contender(intent: ControlIntent) -> None:
        async with arbiter.hold(intent):
            order.append(intent)
            await asyncio.sleep(0)

    async with arbiter.hold(ControlIntent.BACKGROUND):
        async with arbiter.hold(ControlIntent.PREVIEW):
            assert arbiter.active_intent is ControlIntent.PREVIEW
        tasks = [
            asyncio.create_task(contender(ControlIntent.PREVIEW)),
            asyncio.create_task(contender(ControlIntent.APPLY)),
            asyncio.create_task(contender(ControlIntent.USER)),
        ]
        await asyncio.sleep(0)
        async with arbiter.hold(ControlIntent.BACKGROUND, wait=False) as acquired:
            assert acquired is True

        async def separate_background() -> bool:
            async with arbiter.hold(ControlIntent.BACKGROUND, wait=False) as background_acquired:
                return background_acquired

        assert await asyncio.create_task(separate_background()) is False

    await asyncio.gather(*tasks)
    assert order == [ControlIntent.USER, ControlIntent.APPLY, ControlIntent.PREVIEW]


async def test_control_arbiter_accepts_new_preview_during_foreground_intent():
    arbiter = BLEControlArbiter()

    async with arbiter.hold(ControlIntent.USER):
        admission = arbiter.admit_preview()

    assert admission.is_current is True


async def test_initial_state_and_update(coord, h6199):
    assert (coord.is_on, coord.brightness_pct, coord.rgb_color) == (False, 100, (255, 255, 255))
    assert coord.effect is None and coord.address == "AA:BB:CC:DD:EE:FF" and coord.model == "H617A"
    assert (coord.music_mode, coord.video_mode, coord.diy_code) == ("off", "off", None)
    assert coord.color_mode is None
    assert coord.profile == MODEL_PROFILES["H617A"] and coord.profile.state_readable
    assert coord.profile.supports_music_mode and not coord.profile.supports_video_mode
    assert h6199.profile == MODEL_PROFILES["H6199"] and h6199.profile.state_readable
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


def test_capture_effect_control_state(coord):
    coord.is_on = True
    coord.brightness_pct = 72
    coord.rgb_color = (1, 2, 3)
    coord.music_sensitivity = 50

    state = coord.capture_effect_control_state()

    assert state == PriorControlState(
        mode="colour",
        is_on=True,
        brightness_pct=72,
        rgb_color=(1, 2, 3),
        music_sensitivity=50,
    )


async def test_restore_effect_control_state_reapplies_static_state(coord):
    state = PriorControlState(
        mode="colour",
        is_on=True,
        brightness_pct=72,
        rgb_color=(1, 2, 3),
    )

    with (
        patch.object(coord, "send_command", new_callable=AsyncMock) as send,
        patch.object(coord, "refresh_state", new_callable=AsyncMock, return_value=True) as refresh,
    ):
        recovered = await coord.async_restore_effect_control_state(
            state,
            overwritten_diy_code=800,
        )

    assert recovered is True
    assert send.await_args_list == [
        call(proto.build_power(True)),
        call(proto.build_brightness(72)),
        call(proto.build_color_rgb(1, 2, 3)),
    ]
    refresh.assert_awaited_once_with()
    assert coord.active_mode == "colour"


async def test_restore_effect_control_state_cannot_recover_overwritten_diy_slot(coord):
    state = PriorControlState(
        mode="custom",
        is_on=True,
        brightness_pct=72,
        rgb_color=(1, 2, 3),
        diy_code=800,
    )

    with patch.object(coord, "send_command", new_callable=AsyncMock) as send:
        recovered = await coord.async_restore_effect_control_state(
            state,
            overwritten_diy_code=800,
        )

    assert recovered is False
    send.assert_not_awaited()


async def test_restore_effect_control_state_reapplies_model_scene(coord, h6199):
    for coordinator in (coord, h6199):
        effect, scene = next((name, entry) for name, entry in MODEL_SCENES[coordinator.model].items() if entry.param)
        state = PriorControlState(
            mode="scene",
            is_on=True,
            brightness_pct=72,
            rgb_color=(1, 2, 3),
            effect=effect,
        )
        expected = build_native_scene_packets(coordinator.model, scene)

        with (
            patch.object(coordinator, "send_command", new_callable=AsyncMock) as send,
            patch.object(coordinator, "refresh_state", new_callable=AsyncMock, return_value=True) as refresh,
        ):
            recovered = await coordinator.async_restore_effect_control_state(
                state,
                overwritten_diy_code=-1,
            )

        assert recovered is True
        assert send.await_args_list == [call(packet) for packet in expected]
        refresh.assert_awaited_once_with(expected_effect=effect)
        assert coordinator.active_mode == "scene"


async def test_restore_effect_control_state_reapplies_powered_off_state(coord):
    state = PriorControlState(
        mode="colour",
        is_on=False,
        brightness_pct=72,
        rgb_color=(1, 2, 3),
    )

    with (
        patch.object(coord, "send_command", new_callable=AsyncMock) as send,
        patch.object(coord, "refresh_state", new_callable=AsyncMock, return_value=True) as refresh,
    ):
        recovered = await coord.async_restore_effect_control_state(
            state,
            overwritten_diy_code=None,
        )

    assert recovered is True
    send.assert_awaited_once_with(proto.build_power(False))
    refresh.assert_awaited_once_with(expected_on=False)


async def test_restore_effect_control_state_reactivates_unmodified_diy_slot(coord):
    state = PriorControlState(
        mode="custom",
        is_on=True,
        brightness_pct=72,
        rgb_color=(1, 2, 3),
        diy_code=700,
    )

    with (
        patch.object(coord, "send_command", new_callable=AsyncMock) as send,
        patch.object(coord, "refresh_state", new_callable=AsyncMock, return_value=True) as refresh,
    ):
        recovered = await coord.async_restore_effect_control_state(
            state,
            overwritten_diy_code=800,
        )

    assert recovered is True
    send.assert_awaited_once_with(proto.build_h617a_diy_activation(700))
    refresh.assert_awaited_once_with()
    assert coord.diy_code == 700


async def test_restore_effect_control_state_reapplies_complete_music_profile(coord):
    state = PriorControlState(
        mode="music",
        is_on=True,
        brightness_pct=72,
        rgb_color=(1, 2, 3),
        music_mode="separation",
        music_sensitivity=50,
        music_color=(4, 5, 6),
        music_separation_point=4,
        music_separation_gradient=False,
    )

    with (
        patch.object(coord, "install_music_profile_state") as install,
        patch.object(coord, "async_select_music_slug", new_callable=AsyncMock) as select,
        patch.object(coord, "async_apply_music_params", new_callable=AsyncMock) as parameters,
        patch.object(coord, "refresh_state", new_callable=AsyncMock, return_value=True) as refresh,
    ):
        recovered = await coord.async_restore_effect_control_state(
            state,
            overwritten_diy_code=None,
        )

    assert recovered is True
    install.assert_called_once_with(
        mode="separation",
        sensitivity=50,
        colour=(4, 5, 6),
        calm=False,
        parameters={
            "point": 4,
            "gradient": False,
            "relative_brightness": 50,
            "key_count": 15,
            "direction": "clockwise",
            "segment_count": 1,
            "speed": 10,
        },
    )
    select.assert_awaited_once_with("separation")
    parameters.assert_awaited_once_with(0x32)
    refresh.assert_awaited_once_with(expected_music_mode="separation")


def test_install_music_profile_state_updates_only_the_selected_modes_parameters(coord):
    coord.music_separation_gradient = True
    coord.music_daynight_gradient = True

    coord.install_music_profile_state(
        mode="separation",
        sensitivity=50,
        colour=None,
        calm=False,
        parameters={"point": 4, "gradient": False},
    )
    recovery_snapshot = coord.capture_effect_control_state()

    assert coord.music_separation_point == 4
    assert coord.music_separation_gradient is False
    assert coord.music_daynight_gradient is True
    assert recovery_snapshot.music_daynight_gradient is True


async def test_restore_effect_control_state_reapplies_complete_video_profile(h6199):
    state = PriorControlState(
        mode="video",
        is_on=True,
        brightness_pct=72,
        rgb_color=(1, 2, 3),
        video_mode="game",
        video_full_screen=False,
        video_saturation=63,
        video_sound_effects=True,
        video_sound_effects_softness=27,
        white_balance_red=21,
        white_balance_blue=5,
        relative_brightness_left=20,
        relative_brightness_top=30,
        relative_brightness_right=40,
        relative_brightness_bottom=50,
        blank_screen=True,
        blank_screen_detection=2,
        blank_screen_low_brightness_duration_seconds=10,
        blank_screen_same_tone_duration_seconds=120,
    )

    with (
        patch(f"{M}.apply_white_balance", new_callable=AsyncMock, return_value=True) as white_balance,
        patch(f"{M}.apply_relative_brightness", new_callable=AsyncMock, return_value=True) as relative_brightness,
        patch(f"{M}.apply_blank_screen", new_callable=AsyncMock, return_value=True) as blank_screen,
        patch(f"{M}.apply_active_video_mode", new_callable=AsyncMock, return_value=True) as video_mode,
    ):
        recovered = await h6199.async_restore_effect_control_state(
            state,
            overwritten_diy_code=None,
        )

    assert recovered is True
    white_balance.assert_awaited_once_with(h6199)
    relative_brightness.assert_awaited_once_with(h6199)
    blank_screen.assert_awaited_once_with(h6199)
    video_mode.assert_awaited_once_with(h6199)
    assert (
        h6199.video_mode,
        h6199.video_full_screen,
        h6199.video_saturation,
        h6199.video_sound_effects,
        h6199.video_sound_effects_softness,
    ) == ("game", False, 63, True, 27)
    assert (h6199.white_balance_red, h6199.white_balance_blue) == (21, 5)
    assert (
        h6199.relative_brightness_left,
        h6199.relative_brightness_top,
        h6199.relative_brightness_right,
        h6199.relative_brightness_bottom,
    ) == (20, 30, 40, 50)
    assert h6199.blank_screen is True


async def test_restore_effect_control_state_reapplies_h6199_scene(h6199):
    state = PriorControlState(
        mode="scene",
        is_on=True,
        brightness_pct=72,
        rgb_color=(1, 2, 3),
        effect="forest",
    )
    scene = MODEL_SCENES["H6199"]["forest"]

    with (
        patch.object(h6199, "send_command", new_callable=AsyncMock) as send,
        patch.object(h6199, "refresh_state", new_callable=AsyncMock, return_value=True) as refresh,
    ):
        recovered = await h6199.async_restore_effect_control_state(
            state,
            overwritten_diy_code=None,
        )

    assert recovered is True
    assert send.await_args_list == [call(packet) for packet in build_native_scene_packets("H6199", scene)]
    refresh.assert_awaited_once_with(expected_effect="forest")
    assert h6199.effect == "forest"
    assert (h6199.diy_code, h6199.music_mode, h6199.video_mode) == (None, "off", "off")


async def test_send_command(coord):
    c = _c(write_gatt_char=AsyncMock(side_effect=[BleakError("f"), BleakError("f"), None]))
    with patch.object(coord, "_ensure_connected", return_value=c):
        await coord.send_command(proto.build_power(True))
    assert c.write_gatt_char.call_count == 3
    c2 = _c(write_gatt_char=AsyncMock(side_effect=BleakError("f")))
    with patch.object(coord, "_ensure_connected", return_value=c2), pytest.raises(BleakError):
        await coord.send_command(proto.build_power(True))
    assert c2.write_gatt_char.call_count == 3 and coord._client is None


async def test_effect_sequence_reconnect_restarts_from_frame_zero(coord):
    packets = [b"first", b"second", b"activation"]
    attempted: list[bytes] = []

    async def first_write(_uuid, packet, **_kwargs):
        attempted.append(packet)
        if packet == b"second":
            raise BleakError("connection dropped")

    async def replacement_write(_uuid, packet, **_kwargs):
        attempted.append(packet)

    first = _c(write_gatt_char=AsyncMock(side_effect=first_write))
    replacement = _c(write_gatt_char=AsyncMock(side_effect=replacement_write))
    attempts: list[int] = []
    progress: list[int] = []

    async def note_attempt(attempt: int) -> None:
        attempts.append(attempt)

    async def note_progress(index: int) -> None:
        progress.append(index)

    with patch.object(
        coord,
        "_ensure_connected",
        new=AsyncMock(side_effect=[first, replacement]),
    ):
        await coord.async_write_effect_sequence(
            packets,
            intent=ControlIntent.PREVIEW,
            attempt_started=note_attempt,
            progress=note_progress,
        )

    assert attempted == [
        b"first",
        b"second",
        b"first",
        b"second",
        b"activation",
    ]
    assert attempts == [1, 2]
    assert progress == [1, 1, 2, 3]


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


async def test_foreground_command_waits_for_atomic_preview_packets(coord):
    writes: list[bytes] = []
    client = _c(write_gatt_char=AsyncMock(side_effect=lambda _uuid, packet, **_kwargs: writes.append(packet)))
    coord._client = client
    first, second, user = b"first", b"second", proto.build_power(True)

    async with coord._control_arbiter.hold(ControlIntent.PREVIEW):
        await coord.async_preview_write(first)
        command = asyncio.create_task(coord.send_command(user))
        await asyncio.sleep(0)
        await coord.async_preview_write(second)
        assert writes == [first, second]

    await command
    assert writes == [first, second, user]


async def test_preview_write_arms_expected_state(coord):
    packet = proto.build_power(True)
    coord._client = _c(write_gatt_char=AsyncMock())

    await coord.async_preview_write(packet)

    assert coord._expected_state["is_on"][0] is True


async def test_background_connection_use_does_not_renew_foreground_lease(coord):
    coord._client = _c()
    with patch.object(coord, "_reset_disconnect_timer") as reset:
        async with coord._control_arbiter.hold(ControlIntent.BACKGROUND):
            await coord._ensure_connected()
        reset.assert_not_called()

        async with coord._control_arbiter.hold(ControlIntent.USER):
            await coord._ensure_connected()
        reset.assert_called_once_with()


async def test_background_refresh_keeps_background_intent_and_preview_admission(
    coord,
):
    coord._client = _c()

    async def reply(**_kwargs) -> bool:
        assert coord._control_arbiter.current_task_intent is ControlIntent.BACKGROUND
        assert coord.admit_preview().is_current
        coord._notify_callback(
            None,
            bytearray(proto.build_packet(0xAA, 0x01, [1])),
        )
        coord._notify_callback(
            None,
            bytearray(proto.build_packet(0xAA, 0x04, [42])),
        )
        coord._notify_callback(
            None,
            bytearray(
                proto.build_packet(
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


async def test_background_refresh_disconnects_poll_only_connection_after_query(coord):
    client = _c(disconnect=AsyncMock())

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
    c = _c(disconnect=AsyncMock())
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
    h6199._keep_alive_task, h6199._client = task, _c(disconnect=AsyncMock())
    await h6199.disconnect()
    task.cancel.assert_called_once()


async def test_disconnect_does_not_clear_replacement_client(coord):
    replacement = _c(disconnect=AsyncMock())

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


def test_notify_callback(h6199):
    h6199.effect_families = frozenset({"scenes", "music", "video"})
    cb = h6199._notify_callback
    cb(None, bytearray(proto.build_packet(0xAA, 0x01, [0x01])))
    assert h6199.is_on is True
    cb(None, bytearray(proto.build_packet(0xAA, 0x01, [0x00])))
    assert h6199.is_on is False
    cb(None, bytearray(proto.build_packet(0xAA, 0x04, [0x4B])))
    assert h6199.brightness_pct == 75
    cb(None, bytearray(proto.build_packet(0xAA, 0x05, [0x00, 0x00, 0x01, 42])))
    assert (h6199.video_mode, h6199.video_full_screen, h6199.video_saturation) == ("game", False, 42)
    cb(None, bytearray(proto.build_packet(0xAA, 0x05, [0x13, 0x04, 66, 0x00, 0x01, 1, 2, 3])))
    assert (h6199.music_mode, h6199.music_sensitivity, h6199.music_calm, h6199.music_color) == (
        "spectrum",
        66,
        False,
        (1, 2, 3),
    )
    assert h6199.effect is None
    cb(None, bytearray(proto.build_packet(0xAA, 0xA9, [0x00, 0x06, 1, 16, 3, 1, 21, 5])))
    assert (h6199.white_balance_red, h6199.white_balance_blue) == (21, 5)
    cb(None, bytearray(proto.build_packet(0xAA, 0xA9, [0x0A, 0x06, 0, 2, 10, 0, 120, 0])))
    assert h6199.blank_screen is False
    assert h6199.blank_screen_detection == 2
    assert h6199.blank_screen_low_brightness_duration_seconds == 10
    assert h6199.blank_screen_same_tone_duration_seconds == 120
    cb(None, bytearray(proto.build_packet(0xAA, 0xAE, [1, 4, 51, 20, 31, 41])))
    assert (
        h6199.relative_brightness,
        h6199.relative_brightness_left,
        h6199.relative_brightness_top,
        h6199.relative_brightness_right,
        h6199.relative_brightness_bottom,
    ) == (None, 51, 20, 31, 41)
    cb(None, bytearray(proto.build_packet(0xAA, 0x05, [0x04, 0x09, 0x00])))
    assert h6199.effect == "candlelight"
    h6199.is_on = False
    cb(None, bytearray([0xAA]))
    cb(None, bytearray([0x33, 0x01, 0x01, 0x00]))
    assert h6199.is_on is False


def test_display_replies_reject_stale_composite_values_atomically(h6199):
    h6199.white_balance_red, h6199.white_balance_blue = 16, 3
    h6199._arm_expected_values({"white_balance_red": 21, "white_balance_blue": 5})
    h6199._notify_callback(None, bytearray(proto.build_packet(0xAA, 0xA9, [0x00, 0x06, 1, 16, 3, 1, 13, 3])))
    assert (h6199.white_balance_red, h6199.white_balance_blue) == (16, 3)

    h6199.blank_screen = True
    h6199._arm_expected_values({"blank_screen": True})
    h6199._notify_callback(None, bytearray(proto.build_packet(0xAA, 0xA9, [0x0A, 0x06, 0, 2, 10, 0, 120, 0])))
    assert h6199.blank_screen is True

    expected = (51, 20, 31, 41)
    h6199.relative_brightness = None
    (
        h6199.relative_brightness_left,
        h6199.relative_brightness_top,
        h6199.relative_brightness_right,
        h6199.relative_brightness_bottom,
    ) = expected
    h6199._arm_expected_values(
        {
            "relative_brightness": None,
            "relative_brightness_left": 51,
            "relative_brightness_top": 20,
            "relative_brightness_right": 31,
            "relative_brightness_bottom": 41,
        }
    )
    h6199._notify_callback(None, bytearray(proto.build_packet(0xAA, 0xAE, [1, 4, 91, 91, 91, 91])))
    assert (
        h6199.relative_brightness_left,
        h6199.relative_brightness_top,
        h6199.relative_brightness_right,
        h6199.relative_brightness_bottom,
    ) == expected


def test_notify_callback_parses_full_frame_with_checksum(h6199):
    """Scene readback remains available when scenes are hidden from the HA effect list."""
    h6199.effect_families = frozenset()
    cb = h6199._notify_callback
    cb(None, bytearray(proto.build_packet(0xAA, 0x05, [0x04, 0x01, 0x00])))
    assert h6199.effect == "sunset"
    cb(None, bytearray(proto.build_packet(0xAA, 0x05, [0x04, 0x09])))
    assert h6199.effect == "candlelight"


def test_h6199_subordinate_versions_are_retained_without_querying_identity(h6199):
    h6199._notify_callback(None, bytearray(proto.build_packet(0xAA, 0x20, list(b"1.03.00"))))
    h6199._notify_callback(None, bytearray(proto.build_packet(0xAA, 0x21, list(b"1.00.33"))))

    assert h6199.subordinate_20_version == "1.03.00"
    assert h6199.subordinate_21_version == "1.00.33"


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
    )


async def test_resolution_reuses_selected_client_after_disconnect(coord):
    device = MagicMock()
    original_client_class = type("OriginalClient", (), {})
    resolution = _resolution(device, original_client_class)
    resolver = MagicMock(spec=BLEDeviceResolver)
    resolver.async_resolve = AsyncMock(return_value=resolution)
    coord._device_resolver = resolver
    first = _c(disconnect=AsyncMock())
    second = _c(disconnect=AsyncMock())

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
        ),
        call(
            original_client_class,
            device,
            coord.address,
            disconnected_callback=coord._disconnected_callback,
        ),
    ]
    first.disconnect.assert_awaited_once()
    await coord.disconnect()


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


async def test_ensure_connected_cleans_up_notify_failure(coord):
    client = _c(start_notify=AsyncMock(side_effect=BleakError("notify failed")), disconnect=AsyncMock())
    with (
        patch(f"{M}.BLEDeviceResolver.async_resolve", new_callable=AsyncMock, return_value=_resolution()),
        patch(f"{M}.establish_connection", return_value=client),
        pytest.raises(BleakError, match="notify failed"),
    ):
        await coord._ensure_connected()
    client.disconnect.assert_awaited_once()
    assert coord._client is None


async def test_background_refresh_disconnects_replacement_connection(coord):
    original = _c()
    replacement = _c(disconnect=AsyncMock())
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
    old = _c(disconnect=AsyncMock())
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
    old = _c(disconnect=AsyncMock())
    new = _c(disconnect=AsyncMock())
    coord._client = new

    await coord._disconnect_if_current(old)
    assert coord._client is new
    old.disconnect.assert_not_awaited()
    new.disconnect.assert_not_awaited()

    await coord._disconnect_if_current(new)
    new.disconnect.assert_awaited_once()
    assert coord._client is None


async def test_send_state_queries_selective(coord):
    c = _c(write_gatt_char=AsyncMock())
    coord._client = c

    assert await coord._send_state_queries(query_power=False, query_brightness=True, query_color_mode=False) is True
    c.write_gatt_char.assert_awaited_once_with(WRITE_UUID, build_brightness_query(), response=False)

    c.write_gatt_char.reset_mock()
    assert await coord._send_state_queries(query_power=True, query_brightness=False, query_color_mode=True) is True
    calls = [args.args[1] for args in c.write_gatt_char.await_args_list]
    assert calls == [build_power_query(), build_colour_mode_query()]


async def test_send_state_queries_include_h6199_display_state(h6199):
    c = _c(write_gatt_char=AsyncMock())
    h6199._client = c
    assert await h6199._send_state_queries() is True
    assert [call.args[1] for call in c.write_gatt_char.await_args_list] == [
        build_power_query("H6199"),
        build_brightness_query("H6199"),
        build_colour_mode_query("H6199"),
        build_h6199_white_balance_query(),
        build_h6199_blank_screen_query(),
        build_h6199_relative_brightness_query(),
        *(build_segment_query(group, "H6199") for group in range(1, 5)),
    ]


async def test_send_state_queries_include_h617a_core_state(coord):
    c = _c(write_gatt_char=AsyncMock())
    coord._client = c
    assert await coord._send_state_queries() is True
    assert [call.args[1] for call in c.write_gatt_char.await_args_list] == [
        build_power_query(),
        build_brightness_query(),
        build_colour_mode_query(),
        *(build_segment_query(group) for group in range(1, 6)),
    ]


async def test_send_command_sets_expected_brightness(coord):
    c = _c(write_gatt_char=AsyncMock())
    with patch.object(coord, "_ensure_connected", return_value=c):
        assert "brightness_pct" not in coord._expected_state
        await coord.send_command(proto.build_brightness(42))
        assert coord._expected_state["brightness_pct"][0] == 42


def test_notify_callback_brightness_expectation(h6199):
    cb = h6199._notify_callback
    h6199.brightness_pct = 99
    h6199._expected_state["brightness_pct"] = (10, time.monotonic() + 60)
    cb(None, bytearray(proto.build_packet(0xAA, 0x04, [0x4B])))
    assert h6199.brightness_pct == 99  # ignored

    h6199._expected_state["brightness_pct"] = (75, time.monotonic() + 60)
    cb(None, bytearray(proto.build_packet(0xAA, 0x04, [0x4B])))
    assert h6199.brightness_pct == 75 and "brightness_pct" in h6199._expected_state

    with patch(f"{M}.time.monotonic", return_value=1000):
        h6199._expected_state["brightness_pct"] = (10, 0)
        cb(None, bytearray(proto.build_packet(0xAA, 0x04, [0x01])))
        assert h6199.brightness_pct == 1 and "brightness_pct" not in h6199._expected_state


def test_notify_callback_power_expectation(h6199):
    cb = h6199._notify_callback
    h6199.is_on = True
    h6199._expected_state["is_on"] = (True, time.monotonic() + 60)
    field_revision = h6199._field_revisions.get("is_on", 0)

    cb(None, bytearray(proto.build_packet(0xAA, 0x01, [0x00])))
    assert h6199.is_on is True
    assert h6199._field_revisions.get("is_on", 0) == field_revision
    assert "is_on" in h6199._expected_state

    cb(None, bytearray(proto.build_packet(0xAA, 0x01, [0x01])))
    assert h6199.is_on is True
    assert h6199._field_revisions["is_on"] == field_revision + 1
    assert "is_on" in h6199._expected_state


def test_notify_callback_static_readback_keeps_color_temp(h6199):
    """A static reply carries no colour, so it cannot replace an optimistic colour temperature."""
    cb = h6199._notify_callback
    reply = bytearray(proto.build_packet(0xAA, 0x05, [0x15, 0x01, 10, 20, 30]))

    h6199.color_temp_kelvin = 4000
    h6199.rgb_color = (1, 2, 3)
    cb(None, reply)
    assert h6199.color_temp_kelvin == 4000
    assert h6199.rgb_color == (1, 2, 3)


def test_notify_callback_effect_window(h6199):
    """A stale aa05 reply must not clobber a just-set effect within the window."""
    cb = h6199._notify_callback
    h6199.effect = "candy"
    h6199._expected_state["effect"] = ("candy", time.monotonic() + 60)
    cb(None, bytearray(proto.build_packet(0xAA, 0x05, [0x15, 0x01, 10, 20, 30])))
    assert h6199.effect == "candy"
    assert "effect" in h6199._expected_state


def test_notify_callback_music_auto_color_clears_manual_color(h6199):
    h6199.music_color = (1, 2, 3)
    revision = h6199._field_revisions.get("music_color", 0)

    h6199._notify_callback(
        None,
        bytearray(proto.build_packet(0xAA, 0x05, [0x13, 0x04, 66, 0x00, 0x00])),
    )

    assert h6199.music_color is None
    assert h6199._field_revisions["music_color"] == revision + 1


def test_readback_mode_mutual_exclusion(h6199):
    """Each parsed readback mode leaves exactly one mode truthful, clearing any stale others."""
    h6199.effect_families = frozenset({"scenes", "music", "video"})
    cb = h6199._notify_callback
    music = bytearray(proto.build_packet(0xAA, 0x05, [0x13, 0x04, 66, 0x00, 0x01, 1, 2, 3]))
    video = bytearray(proto.build_packet(0xAA, 0x05, [0x00, 0x00, 0x01, 42]))
    scene = bytearray(proto.build_packet(0xAA, 0x05, [0x04, 0x09, 0x00]))

    h6199.video_mode, h6199.effect = "game", "candlelight"
    cb(None, music)
    assert (h6199.music_mode, h6199.video_mode, h6199.effect) == (
        "spectrum",
        "off",
        None,
    )

    h6199.music_mode, h6199.effect = "rhythm", "candlelight"
    cb(None, video)
    assert (h6199.video_mode, h6199.music_mode, h6199.effect) == (
        "game",
        "off",
        None,
    )

    h6199.music_mode, h6199.video_mode = "rhythm", "movie"
    cb(None, scene)
    assert (h6199.effect, h6199.music_mode, h6199.video_mode) == (
        "candlelight",
        "off",
        "off",
    )


def test_diy_readback_retains_complete_code(coord):
    coord.is_on = True
    baselines = {field: coord._field_revisions.get(field, 0) for field in ("color_mode", "diy_code")}
    coord._notify_callback(
        None,
        bytearray(proto.build_packet(0xAA, 0x05, [proto.COLOR_MODE_DIY, 0x84, 0x03])),
    )

    assert coord.color_mode is proto.ParsedMode.DIY
    assert coord.active_mode == "custom"
    assert coord.diy_code == 900
    assert all(coord._field_revisions[field] > baseline for field, baseline in baselines.items())


async def test_diy_command_expectation_rejects_truncated_readback(coord):
    command = proto.build_packet(0x33, 0x05, [proto.COLOR_MODE_DIY, 0x20, 0x03])
    client = _c(write_gatt_char=AsyncMock())
    with patch.object(coord, "_ensure_connected", return_value=client):
        await coord.send_command(command)

    assert coord._expected_state["color_mode"][0] == (proto.ParsedMode.DIY, 800)

    coord._notify_callback(
        None,
        bytearray(proto.build_packet(0xAA, 0x05, [proto.COLOR_MODE_DIY, 0x20, 0x00])),
    )
    assert coord.color_mode is None
    assert coord.diy_code is None

    coord._notify_callback(
        None,
        bytearray(proto.build_packet(0xAA, 0x05, [proto.COLOR_MODE_DIY, 0x20, 0x03])),
    )
    assert coord.color_mode is proto.ParsedMode.DIY
    assert coord.diy_code == 800


async def test_send_command_arms_expected_state(coord, h6199):
    c = _c(write_gatt_char=AsyncMock())
    with patch.object(coord, "_ensure_connected", return_value=c):
        await coord.send_command(proto.build_power(True))
        assert coord._expected_state["is_on"][0] is True

        await coord.send_command(proto.build_color_temp(4000))
        assert coord._expected_state["color_temp_kelvin"][0] == 4000

        await coord.send_command(proto.build_color_rgb(10, 20, 30))
        assert coord._expected_state["rgb_color"][0] == (10, 20, 30)
        assert "color_temp_kelvin" not in coord._expected_state

        mode_id = next(iter(_MUSIC_SLUG_BY_ID))
        await coord.send_command(build_music_mode(mode_id, 99, None, False))
        assert coord._expected_state["music_mode"][0] == _MUSIC_SLUG_BY_ID[mode_id]
        assert "rgb_color" not in coord._expected_state

    with patch.object(h6199, "_ensure_connected", return_value=c):
        await h6199.send_command(build_h6199_video(False, True, 60, False, 100))
        assert h6199._expected_state["video_mode"][0] == "game"
        assert h6199._expected_state["video_full_screen"][0] is False
        assert h6199._expected_state["video_saturation"][0] == 60
        # The frame is always full, so sound and softness are armed even when sound is off.
        assert h6199._expected_state["video_sound_effects"][0] is False
        assert h6199._expected_state["video_sound_effects_softness"][0] == 100

    with patch.object(coord, "_ensure_connected", return_value=c):
        await coord.send_command(proto.build_color_rgb(10, 20, 30))
        assert coord._expected_state["color_mode"][0] == (proto.ParsedMode.COLOUR, None)
        assert coord._expected_state["rgb_color"][0] == (10, 20, 30)

        await coord.send_command(proto.build_scene(9))
        assert coord._expected_state["color_mode"][0] == (proto.ParsedMode.SCENE, None)
        assert coord._expected_state["effect"][0] == proto.SCENE_EFFECT_BY_ID[9]


def test_music_expectation_rejects_delayed_same_mode_reply(h6199):
    h6199._expected_state["color_mode"] = ((proto.ParsedMode.MUSIC, None), time.monotonic() + 60)
    h6199._expected_state["music_mode"] = ("rhythm", time.monotonic() + 60)
    cb = h6199._notify_callback

    cb(None, bytearray(proto.build_packet(0xAA, 0x05, [0x13, 0x03, 66, 0x00, 0x01, 1, 2, 3])))
    cb(None, bytearray(proto.build_packet(0xAA, 0x05, [0x13, 0x04, 66, 0x00, 0x01, 1, 2, 3])))

    assert h6199.music_mode == "rhythm"
    assert h6199.color_mode is proto.ParsedMode.MUSIC


def test_scene_expectation_rejects_delayed_same_mode_reply(h6199):
    h6199.effect_families = frozenset({"scenes"})
    sunrise_code = next(code for code, effect in proto.SCENE_EFFECT_BY_ID.items() if effect == "sunrise")
    candlelight_code = next(code for code, effect in proto.SCENE_EFFECT_BY_ID.items() if effect == "candlelight")
    h6199._expected_state["color_mode"] = ((proto.ParsedMode.SCENE, None), time.monotonic() + 60)
    h6199._expected_state["effect"] = ("sunrise", time.monotonic() + 60)
    cb = h6199._notify_callback

    cb(None, bytearray(proto.build_packet(0xAA, 0x05, [0x04, *sunrise_code.to_bytes(2, "little")])))
    cb(None, bytearray(proto.build_packet(0xAA, 0x05, [0x04, *candlelight_code.to_bytes(2, "little")])))

    assert h6199.effect == "sunrise"
    assert h6199.color_mode is proto.ParsedMode.SCENE


def test_unknown_mode_clears_restored_metadata(h6199):
    h6199.effect = "Flame"
    h6199.diy_code = 0xF0
    h6199.music_mode, h6199.video_mode = "rhythm", "movie"

    h6199._notify_callback(None, bytearray(proto.build_packet(0xAA, 0x05, [0x99, 0x01])))

    assert h6199.color_mode is proto.ParsedMode.UNKNOWN
    assert h6199.effect is None
    assert h6199.diy_code is None
    assert (h6199.music_mode, h6199.video_mode) == ("off", "off")


async def test_refresh_state_query_selection(coord):
    coord.is_on = True
    coord.effect = "candy"
    coord._client = client = _c()

    async def _reply(
        *,
        query_power: bool,
        query_brightness: bool,
        query_color_mode: bool,
    ) -> bool:
        if query_power:
            coord._notify_callback(None, bytearray(proto.build_packet(0xAA, 0x01, [1])))
        if query_brightness:
            coord._notify_callback(None, bytearray(proto.build_packet(0xAA, 0x04, [42])))
        if query_color_mode:
            coord._notify_callback(None, bytearray(proto.build_packet(0xAA, 0x05, [0x04, 0x9D, 0x08])))
        return True

    with (
        patch.object(coord, "_ensure_connected", new=AsyncMock(return_value=client)),
        patch.object(coord, "_send_state_queries", new=AsyncMock(side_effect=_reply)) as sq,
    ):
        assert await coord.refresh_state(expected_effect=None, expected_on=True) is True
        sq.assert_awaited_with(query_power=True, query_brightness=False, query_color_mode=False)
        sq.reset_mock()

        assert await coord.refresh_state(expected_effect="candy", expected_on=None) is True
        sq.assert_awaited_with(query_power=False, query_brightness=False, query_color_mode=True)
        sq.reset_mock()

        assert await coord.refresh_state(expected_brightness=42) is True
        sq.assert_awaited_with(query_power=False, query_brightness=True, query_color_mode=False)
        sq.reset_mock()

        assert await coord.refresh_state(expected_effect=None, expected_on=None) is True
        sq.assert_awaited_with(query_power=True, query_brightness=False, query_color_mode=True)


async def test_refresh_reply_timeout_starts_after_connection(coord):
    client = _c(disconnect=AsyncMock())

    async def connect():
        await asyncio.sleep(0.03)
        coord._client = client
        return client

    async def reply(**_kwargs) -> bool:
        coord._notify_callback(
            None,
            bytearray(proto.build_packet(0xAA, 0x01, [1])),
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
    h6199._client = client = _c()

    async def _reply(**kwargs) -> bool:
        if kwargs.get("query_white_balance"):
            h6199._notify_callback(None, bytearray(proto.build_packet(0xAA, 0xA9, [0x00, 0x06, 1, 16, 3, 1, 21, 5])))
        if kwargs.get("query_blank_screen"):
            h6199._notify_callback(None, bytearray(proto.build_packet(0xAA, 0xA9, [0x0A, 0x06, 1, 2, 10, 0, 120, 0])))
        if kwargs.get("query_relative_brightness"):
            h6199._notify_callback(None, bytearray(proto.build_packet(0xAA, 0xAE, [1, 4, 51, 20, 31, 41])))
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


async def test_refresh_state_rejects_optimistic_value_without_fresh_reply(coord):
    coord.is_on = True
    coord._client = client = _c(disconnect=AsyncMock())
    with (
        patch.object(coord, "_ensure_connected", new=AsyncMock(return_value=client)),
        patch.object(coord, "_send_state_queries", new=AsyncMock(return_value=True)) as queries,
        patch.object(coord, "_disconnect_if_current_locked", new_callable=AsyncMock) as disconnect,
    ):
        assert await coord.refresh_state(expected_on=True, timeout=0.01) is False
    assert queries.await_count == 2
    disconnect.assert_awaited_once_with(client)


async def test_refresh_state_ignored_stale_reply_does_not_confirm(coord):
    coord.music_mode = "rhythm"
    coord._client = client = _c()
    coord._expected_state["music_mode"] = ("rhythm", time.monotonic() + 60)

    async def _stale_reply(**kwargs) -> bool:
        coord._notify_callback(
            None,
            bytearray(proto.build_packet(0xAA, 0x05, [0x13, 0x04, 66, 0x00, 0x01, 1, 2, 3])),
        )
        return True

    with (
        patch.object(coord, "_ensure_connected", new=AsyncMock(return_value=client)),
        patch.object(coord, "_send_state_queries", new=AsyncMock(side_effect=_stale_reply)),
        patch.object(coord, "_disconnect_if_current_locked", new_callable=AsyncMock) as disconnect,
    ):
        assert await coord.refresh_state(expected_music_mode="rhythm", timeout=0.01) is False
    disconnect.assert_not_awaited()


async def test_refresh_state_requires_fresh_power_and_video_replies(coord):
    coord.is_on = True
    coord.video_mode = "game"
    coord._client = client = _c(disconnect=AsyncMock())

    async def _video_only(**kwargs) -> bool:
        coord._notify_callback(None, bytearray(proto.build_packet(0xAA, 0x05, [0x00, 0x00, 0x01, 60])))
        return True

    with (
        patch.object(coord, "_ensure_connected", new=AsyncMock(return_value=client)),
        patch.object(coord, "_send_state_queries", new=AsyncMock(side_effect=_video_only)),
        patch.object(coord, "_disconnect_if_current_locked", new_callable=AsyncMock) as disconnect,
    ):
        assert await coord.refresh_state(expected_on=True, expected_video_mode="game", timeout=0.01) is False
    disconnect.assert_awaited_once_with(client)


async def test_refresh_state_rejects_wrong_video_parameters(coord):
    coord._client = client = _c()

    async def _wrong_video(**kwargs) -> bool:
        coord._notify_callback(None, bytearray(proto.build_packet(0xAA, 0x01, [1])))
        coord._notify_callback(
            None,
            bytearray(proto.build_packet(0xAA, 0x05, [0x00, 0x01, 0x01, 100, 0, 0])),
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


async def test_refresh_state_does_not_disconnect_replacement_client(coord):
    original = _c(disconnect=AsyncMock())
    replacement = _c(disconnect=AsyncMock())
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


async def test_send_command_noop_during_shutdown(coord):
    """Commands must be silently dropped once HA is shutting down."""
    c = _c(write_gatt_char=AsyncMock())
    coord.hass.is_stopping = True
    with patch.object(coord, "_ensure_connected", return_value=c):
        await coord.send_command(proto.build_power(True))
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


def test_segment_colors_initial_state(coord, h6199):
    assert coord.segment_colors == [(255, 255, 255)] * 15
    assert h6199.segment_colors == [(255, 255, 255)] * 15
    assert coord.segment_brightness == [100] * 15
    assert h6199.segment_brightness == [100] * 15
    assert coord.segment_state_source == h6199.segment_state_source == "initial"
    assert len(coord.segment_colors) == coord.profile.segment_count


def test_segment_colors_empty_for_unsupported(hass):
    flat = replace(MODEL_PROFILES["H617A"], segment_count=0)
    with patch(f"{M}.get_profile", return_value=flat):
        c = GoveeBLECoordinator(
            hass,
            "AA:BB:CC:DD:EE:00",
            "H617A",
            configuration_url=_CONFIGURATION_URL,
        )
    assert c.segment_colors == [] and c.profile.segment_count == 0


def test_h6199_static_reply_reports_mode_only(h6199):
    h6199.segment_colors = [(1, 2, 3)] * 15
    h6199._notify_callback(None, bytearray(proto.build_packet(0xAA, 0x05, [0x15, 0x01, 10, 20, 30])))
    assert h6199.color_mode is proto.ParsedMode.COLOUR
    assert h6199.rgb_color == (255, 255, 255)
    assert h6199.segment_colors == [(1, 2, 3)] * 15


def _send_uniform_segment_replies(coordinator, rgb: tuple[int, int, int]) -> None:
    group_size = 4 if coordinator.model == "H6199" else 3
    group_count = 4 if coordinator.model == "H6199" else 5
    for group in range(1, group_count + 1):
        count = min(group_size, 15 - (group - 1) * group_size)
        payload = [group, *([100, *rgb] * count)]
        coordinator._notify_callback(None, bytearray(proto.build_packet(0xAA, 0xA5, payload)))


def test_h6199_static_segment_readback_updates_uniform_rgb(h6199):
    h6199.color_mode = ParsedMode.COLOUR
    h6199.rgb_color = (1, 2, 3)
    h6199.color_temp_kelvin = 4000

    _send_uniform_segment_replies(h6199, (10, 20, 30))

    assert h6199.rgb_color == (10, 20, 30)
    assert h6199.color_temp_kelvin is None


def test_h6199_static_segment_readback_preserves_matching_kelvin_companion(h6199):
    h6199.color_mode = ParsedMode.COLOUR
    h6199.color_temp_kelvin = 2000
    companion = kelvin_to_rgb(2000)

    _send_uniform_segment_replies(h6199, companion)

    assert h6199.color_temp_kelvin == 2000
    assert h6199.segment_colors == [companion] * 15


def test_partial_segment_refresh_does_not_publish_mixed_snapshot(coord):
    original_colors = [(1, 2, 3)] * 15
    original_brightness = [10] * 15
    coord.segment_colors = original_colors
    coord.segment_brightness = original_brightness
    coord.segment_state_source = "observed"
    coord.segment_state_observed_at = "2026-08-17T00:00:00+00:00"

    coord._notify_callback(
        None,
        bytearray(proto.build_packet(0xAA, 0xA5, [1, *([90, 9, 8, 7] * 3)])),
    )

    assert coord.segment_colors == original_colors
    assert coord.segment_brightness == original_brightness
    assert coord.segment_state_source == "observed"
    assert coord.segment_state_observed_at == "2026-08-17T00:00:00+00:00"


@pytest.mark.parametrize(("model_fixture", "group_size", "group_count"), [("coord", 3, 5), ("h6199", 4, 4)])
def test_segment_query_replies_replace_restored_state(
    request: pytest.FixtureRequest,
    model_fixture: str,
    group_size: int,
    group_count: int,
) -> None:
    coordinator = request.getfixturevalue(model_fixture)
    coordinator.segment_colors = [(1, 2, 3)] * 15
    coordinator.segment_brightness = [1] * 15

    for group in range(1, group_count + 1):
        count = min(group_size, 15 - (group - 1) * group_size)
        payload = [group]
        for index in range(count):
            value = (group - 1) * group_size + index
            payload.extend((20 + value, value, value + 1, value + 2))
        coordinator._notify_callback(None, bytearray(proto.build_packet(0xAA, 0xA5, payload)))

    assert coordinator.segment_state_source == "observed"
    assert coordinator.segment_state_observed_at is not None
    assert coordinator.segment_brightness == list(range(20, 35))
    assert coordinator.segment_colors == [(value, value + 1, value + 2) for value in range(15)]


async def test_async_paint_segments_updates_slots_and_sends(coord):
    groups = [([1, 2], (255, 0, 0)), ([3], (0, 0, 255))]
    with (
        patch.object(coord, "send_command", new_callable=AsyncMock) as sc,
        patch.object(coord, "async_refresh_segments", new_callable=AsyncMock, return_value=True) as refresh,
        patch.object(coord, "async_set_updated_data") as pushed,
    ):
        await coord.async_paint_segments(groups)
    assert [call.args[0] for call in sc.await_args_list] == proto.build_segment_paint(groups)
    assert sc.await_count == 2
    assert coord.segment_colors[:4] == [(255, 0, 0), (255, 0, 0), (0, 0, 255), (255, 255, 255)]
    assert coord.segment_state_source == "optimistic"
    refresh.assert_awaited_once_with()
    pushed.assert_called_once()


async def test_async_paint_segments_rolls_back_on_failure(coord):
    before = list(coord.segment_colors)
    with (
        patch.object(coord, "send_command", new=AsyncMock(side_effect=BleakError("boom"))),
        pytest.raises(BleakError),
    ):
        await coord.async_paint_segments([([1, 2], (255, 0, 0))])
    assert coord.segment_colors == before
    assert coord.segment_state_source == "initial"


async def test_async_set_segment_brightness_verifies_complete_state(coord):
    with (
        patch.object(coord, "send_command", new_callable=AsyncMock) as send,
        patch.object(coord, "async_refresh_segments", new_callable=AsyncMock, return_value=True) as refresh,
    ):
        await coord.async_set_segment_brightness([2, 4], 60)

    send.assert_awaited_once_with(build_segment_brightness([2, 4], 60))
    assert coord.segment_brightness[:5] == [100, 60, 100, 60, 100]
    assert coord.segment_state_source == "optimistic"
    refresh.assert_awaited_once_with()


async def test_async_paint_segments_rejects_unsupported(coord):
    coord.profile = replace(coord.profile, supports_segment_writes=False)
    with (
        patch.object(coord, "send_command", new_callable=AsyncMock) as sc,
        pytest.raises(ValueError),
    ):
        await coord.async_paint_segments([([1], (1, 2, 3))])
    sc.assert_not_awaited()


@pytest.mark.parametrize("bad", [[0], [16], []])
async def test_async_paint_segments_rejects_invalid_segments(coord, bad):
    before = list(coord.segment_colors)
    with (
        patch.object(coord, "send_command", new_callable=AsyncMock) as sc,
        pytest.raises(ValueError),
    ):
        await coord.async_paint_segments([(bad, (1, 2, 3))])
    sc.assert_not_awaited()
    assert coord.segment_colors == before


async def test_native_scene_primitive_acquires_control_lock_exactly_once(coord):
    class CountingLock:
        def __init__(self) -> None:
            self.acquisitions = 0
            self._locked = False

        async def __aenter__(self):
            await self.acquire()

        async def __aexit__(self, *_args):
            self.release()

        async def acquire(self):
            assert not self._locked
            self._locked = True
            self.acquisitions += 1

        def release(self):
            self._locked = False

        def locked(self) -> bool:
            return self._locked

    lock = CountingLock()
    coord._control_arbiter = None
    coord._control_lock = lock
    coord.is_on = False
    packets = []

    async def writer(packet: bytes) -> None:
        assert lock.locked()
        packets.append(packet)

    coord.effect_families = frozenset()
    await coord.async_apply_native_scene(
        "glacier",
        speed_index=0,
        writer=writer,
        verify=False,
    )

    assert lock.acquisitions == 1
    assert packets[0] == proto.build_power(True, "H617A")
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

    assert write_sequence.await_args.args[0][0] == proto.build_power(True, "H617A")
    assert coord.is_on is False


async def test_preview_observation_stays_read_only_when_device_is_silent(coord):
    coord._client = MagicMock(is_connected=True)
    with (
        patch.object(coord, "_send_state_queries", new=AsyncMock(return_value=True)) as query,
        patch.object(coord, "_disconnect_if_current", new_callable=AsyncMock) as disconnect,
        patch.object(coord, "send_command", new_callable=AsyncMock) as send,
    ):
        result = await coord.async_preview_observe(
            {"effect": "glacier"},
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
        query_relative_brightness=False,
    )
    disconnect.assert_not_awaited()
    send.assert_not_awaited()


async def test_preview_preflight_retries_one_failed_connection_path(coord):
    partial = _c(disconnect=AsyncMock())
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


async def test_preview_preflight_bounds_partial_client_cleanup(coord):
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


async def test_preview_preflight_timeout_includes_foreground_wait(coord):
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


async def test_preview_observation_confirms_diy_code_readback(coord):
    coord._client = MagicMock(is_connected=True)

    async def query(**_kwargs) -> bool:
        coord._notify_callback(
            None,
            bytearray(
                proto.build_packet(
                    0xAA,
                    0x05,
                    [proto.COLOR_MODE_DIY, 0x18, 0x00],
                )
            ),
        )
        return True

    with patch.object(
        coord,
        "_send_state_queries",
        new=AsyncMock(side_effect=query),
    ) as sent:
        result = await coord.async_preview_observe(
            {"diy_code": 24},
            timeout=0.2,
        )

    assert result is True
    sent.assert_awaited_once()


async def test_preview_observation_does_not_repeat_silent_query(coord):
    coord._client = MagicMock(is_connected=True)
    coord.effect = None

    async def query_state(**_kwargs) -> bool:
        return True

    with patch.object(
        coord,
        "_send_state_queries",
        new=AsyncMock(side_effect=query_state),
    ) as query:
        result = await coord.async_preview_observe(
            {"effect": "glacier"},
            timeout=0.05,
        )

    assert result is None
    assert query.await_count == 1
    assert not coord._control_lock.locked()


def test_notify_callback_unknown_domain_ignored(h6199):
    revision = h6199._domain_revisions.get(0x99, 0)
    h6199._notify_callback(None, bytearray([0xAA, 0x99, 0x01, 0x00]))
    assert h6199._domain_revisions.get(0x99, 0) == revision


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
    coord._client = _c(disconnect=AsyncMock())

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


def test_notify_callback_sets_fw_hw_versions(coord):
    fw = proto.build_packet(proto.STATUS_HEADER, proto.FIRMWARE_PACKET_TYPE, list(b"3.02.24"))
    hw = proto.build_packet(proto.STATUS_HEADER, proto.HARDWARE_PACKET_TYPE, [0x03, *b"3.01.01"])
    coord._notify_callback(None, bytearray(fw))
    coord._notify_callback(None, bytearray(hw))
    assert coord.fw_version == "3.02.24" and coord.hw_version == "3.01.01"


def test_notify_callback_pushes_identity_to_registry(coord):
    """#97: fw/hw arrive after entities snapshot device_info, so the coordinator must push the
    version into the device registry itself or the device page stays blank."""
    fw = proto.build_packet(proto.STATUS_HEADER, proto.FIRMWARE_PACKET_TYPE, list(b"3.02.24"))
    registry = MagicMock()
    registry.async_get_device.return_value = MagicMock(id="dev-1")
    with patch(f"{M}.dr.async_get", return_value=registry):
        coord._notify_callback(None, bytearray(fw))
        registry.async_update_device.assert_called_once_with("dev-1", sw_version="3.02.24", hw_version=None)
        # A repeat reply carrying the same value must not re-write the registry.
        registry.async_update_device.reset_mock()
        coord._notify_callback(None, bytearray(fw))
        registry.async_update_device.assert_not_called()


def test_note_identity_skips_registry_when_device_absent(coord):
    """No device yet (identity read races entity setup): store the value, never crash."""
    registry = MagicMock()
    registry.async_get_device.return_value = None
    with patch(f"{M}.dr.async_get", return_value=registry):
        coord._note_identity(fw_version="3.02.24")
    assert coord.fw_version == "3.02.24"
    registry.async_update_device.assert_not_called()


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


async def test_h6199_identity_queries_include_only_non_sensitive_subordinate_versions(h6199):
    c = _c(write_gatt_char=AsyncMock())
    h6199._client = c

    await h6199._send_identity_queries()

    assert [item.args[1] for item in c.write_gatt_char.await_args_list] == [
        build_hardware_query("H6199"),
        build_firmware_query("H6199"),
        build_h6199_subordinate_query(0x20),
        build_h6199_subordinate_query(0x21),
    ]
    assert all(packet[1] != 0x14 for packet in (item.args[1] for item in c.write_gatt_char.await_args_list))

    h6199.fw_version = "1.10.04"
    h6199.hw_version = "3.02.01"
    h6199.subordinate_20_version = "1.03.00"
    c.write_gatt_char.reset_mock()

    await h6199._send_identity_queries()

    c.write_gatt_char.assert_awaited_once_with(
        WRITE_UUID,
        build_h6199_subordinate_query(0x21),
        response=False,
    )


def test_keep_alive_started_as_background_task(coord):
    """#86 guard: the lifetime keep-alive loop must be a background task (never a tracked
    setup task), or HA bootstrap waits on it and logs a "blocking start up" warning."""
    created = {}

    def _capture(coro, name):
        coro.close()
        created["name"] = name
        return MagicMock()

    with patch.object(coord.hass, "async_create_background_task", side_effect=_capture) as spy:
        coord._start_keep_alive()
    spy.assert_called_once()
    assert "keep-alive" in created["name"]


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
    flat = replace(MODEL_PROFILES["H617A"], state_readable=False)
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


def test_expectations_from_packet_covers_every_command_family():
    rhythm_id = next(mid for mid, slug in proto.MUSIC_SLUG_BY_ID.items() if slug == "rhythm")
    spectrum_id = next(mid for mid, slug in proto.MUSIC_SLUG_BY_ID.items() if slug == "spectrum")
    scene_code = next(iter(proto.SCENE_EFFECT_BY_ID))

    assert expectations_from_packet(proto.build_power(True)) == {"is_on": True}
    assert expectations_from_packet(proto.build_power(False)) == {"is_on": False}
    assert expectations_from_packet(proto.build_brightness(37)) == {"brightness_pct": 37}

    rgb = expectations_from_packet(proto.build_color_rgb(255, 0, 0))
    assert rgb["rgb_color"] == (255, 0, 0)
    # The write-side sub is not echoed back, so expecting it would reject every reply. Models
    # that do echo it keep the discriminator.
    assert rgb["color_mode"] == (proto.ParsedMode.COLOUR, None)
    echoed = expectations_from_packet(proto.build_color_rgb(255, 0, 0), static_echoes_color=True)
    assert echoed["color_mode"] == (proto.ParsedMode.COLOUR, 0x01)

    # Colour-temperature writes zero the direct RGB field, so they map to a Kelvin
    # expectation rather than an rgb_color one.
    ct = expectations_from_packet(proto.build_color_temp(4000))
    assert ct["color_temp_kelvin"] == 4000
    assert "rgb_color" not in ct

    # A deliberate black paint is also all-zero, but it is a colour, not a 0 K temperature.
    # Splitting the two on "any RGB byte set" put this frame in the kelvin branch.
    black = expectations_from_packet(proto.build_color_rgb(0, 0, 0))
    assert black["rgb_color"] == (0, 0, 0)
    assert "color_temp_kelvin" not in black

    assert expectations_from_packet(proto.build_white_brightness(80))["white_brightness"] == 80

    assert expectations_from_packet(proto.build_scene(scene_code))["effect"] == proto.SCENE_EFFECT_BY_ID[scene_code]

    diy = expectations_from_packet(proto.build_packet(0x33, 0x05, [proto.COLOR_MODE_DIY, 0x20, 0x03]))
    assert diy["color_mode"] == (proto.ParsedMode.DIY, 800)

    rhythm = expectations_from_packet(build_music_mode(rhythm_id, 50, (10, 20, 30), True))
    assert rhythm["music_mode"] == "rhythm"
    assert rhythm["music_sensitivity"] == 50
    assert rhythm["music_calm"] is True
    assert rhythm["music_color"] == (10, 20, 30)

    auto = expectations_from_packet(build_music_mode(spectrum_id, 40, None, False))
    assert auto["music_mode"] == "spectrum"
    assert auto["music_color"] is None
    assert "music_calm" not in auto

    video = expectations_from_packet(
        build_h6199_video(False, True, 42, True, 55),
        "H6199",
    )
    assert video["video_mode"] == "game"
    assert video["video_full_screen"] is False
    assert video["video_saturation"] == 42
    assert video["video_sound_effects"] is True
    assert video["video_sound_effects_softness"] == 55

    assert expectations_from_packet(b"\x00\x01") == {}
    assert expectations_from_packet(proto.build_packet(0x33, 0x05, [0xEE])) == {}


def test_an_unnameable_scene_is_reported_rather_than_hidden(coord):
    """A scene we cannot name still means the light is running something.

    effect has to stay None, because Home Assistant rejects a value outside effect_list and
    we could not re-activate the scene anyway, so the raw id is the only honest signal left.
    """
    unknown = 401
    assert unknown not in proto.SCENE_EFFECT_BY_ID
    coord._notify_callback(
        None,
        bytearray(proto.build_packet(0xAA, 0x05, [proto.COLOR_MODE_SCENE, *unknown.to_bytes(2, "little")])),
    )
    assert coord.effect is None
    assert coord.unknown_scene_code == unknown

    # A scene we can name is reported by name, and leaves no stale code behind.
    known = next(iter(proto.SCENE_EFFECT_BY_ID))
    coord._notify_callback(
        None,
        bytearray(proto.build_packet(0xAA, 0x05, [proto.COLOR_MODE_SCENE, *known.to_bytes(2, "little")])),
    )
    assert coord.effect == proto.SCENE_EFFECT_BY_ID[known]
    assert coord.unknown_scene_code is None

    # Leaving scene mode drops it too, so it can never describe a light that is not in a scene.
    coord._notify_callback(
        None,
        bytearray(proto.build_packet(0xAA, 0x05, [proto.COLOR_MODE_SCENE, *unknown.to_bytes(2, "little")])),
    )
    assert coord.unknown_scene_code == unknown
    coord._notify_callback(None, bytearray(proto.build_packet(0xAA, 0x05, [proto.COLOR_MODE_STATIC, 0x00])))
    assert coord.unknown_scene_code is None


def test_h6199_scene_codes_are_named_when_hidden_from_the_ha_effect_list(h6199):
    scene = MODEL_SCENES["H6199"]["forest"]
    h6199._notify_callback(
        None,
        bytearray(proto.build_packet(0xAA, 0x05, [proto.COLOR_MODE_SCENE, *scene.code.to_bytes(2, "little")])),
    )
    assert h6199.effect == "forest"
    assert h6199.unknown_scene_code is None


def test_video_readback_is_gated_on_the_model(coord, h6199):
    """The same mode byte is video only in the H6199 status grammar."""
    payload = [proto.COLOR_MODE_VIDEO, 0x00, 0x01, 42, 0x01, 55]

    coord._notify_callback(None, bytearray(proto.build_packet(0xAA, 0x05, payload)))
    assert coord.color_mode is proto.ParsedMode.UNKNOWN
    assert coord.video_mode == "off"

    h6199._notify_callback(None, bytearray(proto.build_packet(0xAA, 0x05, payload)))
    assert h6199.color_mode is proto.ParsedMode.VIDEO
    assert h6199.video_mode == "game"
    assert h6199.video_saturation == 42


def test_white_balance_fills_the_untouched_axis_with_the_apps_own_neutral(coord):
    """The register takes both gains at once and never reads back, so one axis alone is a guess.

    Filling from the pair the app's Reset button writes is the only defensible starting point:
    zero is a real gain the app never sends, and reusing the other axis would tint the picture.
    """
    assert coord.white_balance == proto.WHITE_BALANCE_RESET
    coord.white_balance_red = 21
    assert coord.white_balance == (21, proto.WHITE_BALANCE_RESET[1])
    coord.white_balance_blue = 5
    assert coord.white_balance == (21, 5)
    assert build_h6199_white_balance(*coord.white_balance) == build_h6199_white_balance(21, 5)


def test_h6199_blank_screen_builder_clamps_durations() -> None:
    assert build_h6199_blank_screen(
        True,
        detection=2,
        low_brightness_duration_seconds=-1,
        same_tone_duration_seconds=0x10000,
    ) == bytes.fromhex("33a90a0601020000ffff00000000000000000095")


def test_generated_adapter_rejects_structurally_invalid_frames() -> None:
    assert parse_command(_packet(0x33, 0x04, [101])) is None
    assert parse_status(bytes.fromhex("aaa506731f646408646464fe6464640000000093")) is None


@pytest.mark.parametrize(("model", "maximum"), [("H617A", 5), ("H6199", 4)])
def test_segment_query_groups_are_model_bounded(model: str, maximum: int) -> None:
    assert build_segment_query(maximum, model)[2] == maximum
    with pytest.raises(ValueError, match=f"1 to {maximum}"):
        build_segment_query(maximum + 1, model)


def test_h6199_subordinate_queries_exclude_identity_domain() -> None:
    with pytest.raises(ValueError, match="0x20 or 0x21"):
        build_h6199_subordinate_query(0x14)
