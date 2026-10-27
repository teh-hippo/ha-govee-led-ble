"""Coordinator control-state capture and restoration tests."""

import asyncio
import time
from dataclasses import replace
from unittest.mock import AsyncMock, call, patch

import pytest

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, MUSIC_MODE_SLUGS, device_profile
from custom_components.ha_govee_led_ble.control_arbiter import ControlIntent
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode
from custom_components.ha_govee_led_ble.effect_commands import build_h617a_diy_activation
from custom_components.ha_govee_led_ble.effect_deployments import PriorControlState
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_blank_screen,
    build_brightness,
    build_power,
    build_scene_activation,
)
from custom_components.ha_govee_led_ble.light_commands import build_color_rgb, kelvin_companion_rgb
from custom_components.ha_govee_led_ble.scenes import MODEL_SCENES, scene_selector_code
from custom_components.ha_govee_led_ble.transport import WRITE_UUID
from custom_components.ha_govee_led_ble.video_applicability import video_identity_fields
from tests.coordinator_test_support import _CONFIGURATION_URL, _c, _packet

M = "custom_components.ha_govee_led_ble.coordinator"


@pytest.mark.parametrize(
    "outcome", ("match", "missing", "verification_missing", "cancelled", "sibling_changed", "subscription_changed")
)
async def test_h6046_bar_write_preserves_fresh_sibling_and_unknown_flags(hass, monkeypatch, virtual_clock, outcome):
    coord = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6046", configuration_url=_CONFIGURATION_URL)
    coord.pact_type, coord.pact_code = 2, 1
    coord._resolve_device_profile()
    coord._notify_started_monotonic = time.monotonic()
    coord._notification_token = object()
    coord.boolean_control_state = {"left_bar_enabled": False, "right_bar_enabled": False}
    client = _c(write_gatt_char=AsyncMock())
    coord._client = client
    monkeypatch.setattr(coord, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(coord, "_renew_foreground_lease", lambda: None)
    queried = 0

    async def respond(_uuid, packet, **kwargs):
        nonlocal queried
        if packet[:2] == b"\xaa\x33":
            queried += 1
            if outcome == "cancelled":
                raise asyncio.CancelledError
            if outcome == "missing" or (outcome == "verification_missing" and queried == 2):
                return
            flags = 0x90 if queried == 1 else 0x81 if outcome == "sibling_changed" else 0x91
            coord._notify_callback(None, bytearray(_packet(0xAA, 0x33, [flags])))
            if outcome == "subscription_changed":
                coord._notification_token = object()

    client.write_gatt_char.side_effect = respond
    if outcome == "match":
        await coord.async_set_boolean_control("left_bar_enabled", True)
        assert coord.boolean_control_state == {"left_bar_enabled": True, "right_bar_enabled": True}
    elif outcome == "cancelled":
        with pytest.raises(asyncio.CancelledError):
            await coord.async_set_boolean_control("left_bar_enabled", True)
    else:
        with pytest.raises(ValueError):
            await coord.async_set_boolean_control("left_bar_enabled", True)
    writes = [item.args[1] for item in client.write_gatt_char.await_args_list]
    if outcome in {"missing", "subscription_changed", "cancelled"}:
        assert writes == [_packet(0xAA, 0x33, [])]
    else:
        assert writes == [_packet(0xAA, 0x33, []), _packet(0x33, 0x33, [0x91]), _packet(0xAA, 0x33, [])]
    if outcome in {"missing", "verification_missing", "subscription_changed", "cancelled"}:
        client.disconnect.assert_awaited_once()
        assert coord._client is None
    coord._clear_client_state(client)


async def test_h6046_mixed_native_white_revokes_known_rgb_even_when_rendering_is_unchanged(hass):
    from custom_components.ha_govee_led_ble.effect_runtime import async_prepare_effect_control_state
    from custom_components.ha_govee_led_ble.light_commands import kelvin_companion_rgb

    coord = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6046", configuration_url=_CONFIGURATION_URL)
    coord.pact_type, coord.pact_code = 1, 1
    coord._resolve_device_profile()
    coord._notify_started_monotonic = time.monotonic()
    coord.color_mode = ParsedMode.COLOUR
    coord.segment_colors = [kelvin_companion_rgb(2700, coord.profile)] * 10
    coord.segment_state_source = "observed"
    coord._static_rgb_known = True
    coord._notify_callback(None, bytearray(_packet(0xAA, 0x33, [0x11])))
    baseline = coord._field_revisions.get("color_temp_kelvin", 0)
    coord._notify_callback(None, bytearray(_packet(0xAA, 0x05, [0x15, 0, 0x0A, 0x8C, 0, 0])))
    assert (coord.left_bar_kelvin, coord.right_bar_kelvin) == (2700, 0)
    assert not coord._static_rgb_known
    assert coord._field_revisions.get("color_temp_kelvin", 0) == baseline
    assert coord.color_temp_kelvin_source != "observed"
    with pytest.raises(RuntimeError, match="white intent"):
        await async_prepare_effect_control_state(coord, require_restorable_static=True)


def test_h6046_recovery_persists_both_white_points_and_native_power_flags():
    from custom_components.ha_govee_led_ble.light_commands import kelvin_companion_rgb

    profile = device_profile("H6046", 1, 1)
    colours = (kelvin_companion_rgb(2700, profile),) * 5 + (kelvin_companion_rgb(6500, profile),) * 5
    state = PriorControlState(
        mode="colour",
        is_on=False,
        brightness_pct=20,
        rgb_color=(1, 2, 3),
        left_bar_enabled=False,
        right_bar_enabled=True,
        left_bar_kelvin=2700,
        right_bar_kelvin=6500,
        segment_colors=colours,
        segment_brightness=(50,) * 10,
    )
    restored = PriorControlState.from_dict(state.to_dict())
    assert restored == state and restored.restorable_bar_white(profile)
    assert not replace(restored, left_bar_kelvin=0).restorable_bar_white(profile)
    assert not replace(restored, segment_colors=((1, 2, 3),) * 10).restorable_bar_white(profile)
    legacy = state.to_dict()
    for field in ("left_bar_enabled", "right_bar_enabled", "left_bar_kelvin", "right_bar_kelvin"):
        legacy.pop(field)
    prior = PriorControlState.from_dict(legacy)
    assert prior.left_bar_enabled is None and prior.right_bar_kelvin is None
    assert not prior.restorable_bar_white(profile)


async def test_h6046_swap_is_not_replayed_after_ambiguous_write(hass, monkeypatch):
    coord = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6046", configuration_url=_CONFIGURATION_URL)
    coord.pact_type, coord.pact_code = 1, 1
    coord._resolve_device_profile()
    client = _c(write_gatt_char=AsyncMock(side_effect=RuntimeError("ambiguous swap")))
    coord._client = client
    coord._static_rgb_known = True
    coord.left_bar_kelvin = 2700
    monkeypatch.setattr(coord, "_ensure_connected", AsyncMock(return_value=client))
    with pytest.raises(RuntimeError, match="ambiguous"):
        await coord.async_swap_bars()
    assert client.write_gatt_char.await_count == 1
    assert client.write_gatt_char.call_args.args[1] == _packet(0x33, 0x34, [])
    assert not coord._static_rgb_known and coord.left_bar_kelvin is None
    coord._clear_client_state(client)


def test_capture_effect_control_state(coord):
    coord.is_on = True
    coord.brightness_pct = 72
    coord.rgb_color = (1, 2, 3)
    coord.music_sensitivity = 50

    state = coord.capture_effect_control_state()

    assert state == PriorControlState(
        mode="colour",
        music_model="H617A",
        music_parameters={},
        is_on=True,
        brightness_pct=72,
        rgb_color=(1, 2, 3),
        music_sensitivity=50,
    )


async def test_restore_effect_control_state_legacy_static_never_flattens(coord):
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

    assert recovered is False
    send.assert_not_awaited()
    refresh.assert_not_awaited()


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
        expected = [
            build_power(True, coordinator.model),
            build_brightness(72, coordinator.model),
            build_scene_activation(coordinator.model, scene.code, scene.music_code),
        ]

        with (
            patch.object(coordinator, "send_command", new_callable=AsyncMock) as send,
            patch.object(coordinator, "refresh_state", new_callable=AsyncMock, return_value=True) as refresh,
        ):
            recovered = await coordinator.async_restore_effect_control_state(
                state,
                overwritten_diy_code=-1,
            )

        assert recovered is False  # original authored body/speed is unknown
        assert send.await_args_list == [call(packet) for packet in expected]
        refresh.assert_awaited_once_with(expected_on=True, expected_brightness=72, expected_scene_code=scene.code)


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

    assert recovered is False  # power alone cannot recover the missing hidden layout
    send.assert_awaited_once_with(build_power(False), state_values={"is_on": False})
    refresh.assert_awaited_once_with(expected_on=False)


@pytest.mark.parametrize("model", ["H617A", "H9999"])
async def test_restore_effect_control_state_reactivates_unmodified_diy_slot(coord, monkeypatch, model):
    monkeypatch.setitem(MODEL_PROFILES, model, coord.profile)
    coord.model = model
    state = PriorControlState(
        mode="custom",
        is_on=True,
        brightness_pct=72,
        rgb_color=(1, 2, 3),
        diy_code=700,
    )

    with (
        patch.object(coord, "send_command", wraps=coord.send_command) as send,
        patch.object(coord, "_ensure_connected", return_value=_c(write_gatt_char=AsyncMock())),
        patch.object(coord, "async_observe_effect", new_callable=AsyncMock, return_value=True) as refresh,
        patch.object(coord, "refresh_state", new=AsyncMock(return_value=True)),
    ):
        recovered = await coord.async_restore_effect_control_state(
            state,
            overwritten_diy_code=800,
        )

    assert recovered is True
    assert send.await_args_list == [
        call(build_power(True, model)),
        call(build_brightness(72, model)),
        call(build_h617a_diy_activation(700), state_values={"diy_code": 700}),
    ]
    refresh.assert_awaited_once_with({"is_on": True, "diy_code": 700})
    assert coord.diy_code == 700


async def test_restore_effect_control_state_reapplies_complete_music_profile(coord):
    from custom_components.ha_govee_led_ble.music_commands import prepare_music_body_writes
    from custom_components.ha_govee_led_ble.music_semantics import music_variant

    body = music_variant(coord.profile, MUSIC_MODE_SLUGS["separation"]).template
    state = PriorControlState(
        mode="music",
        is_on=True,
        brightness_pct=72,
        rgb_color=(1, 2, 3),
        music_mode="separation",
        music_model="H617A",
        music_body=body,
        music_sensitivity=50,
        music_color=(4, 5, 6),
        music_separation_point=4,
        music_separation_gradient=False,
    )
    with (
        patch.object(coord, "send_command", new=AsyncMock()) as send,
        patch.object(coord, "async_write_music_sequence", new=AsyncMock()) as sequence,
        patch.object(coord, "refresh_state", new_callable=AsyncMock, return_value=True) as refresh,
    ):
        recovered = await coord.async_restore_effect_control_state(
            state,
            overwritten_diy_code=None,
        )

    assert recovered is False  # accepted bytes are not full-settings readback
    sequence.assert_awaited_once_with(
        prepare_music_body_writes("H617A", "separation", 50, body, profile=coord.profile),
        mode_code=MUSIC_MODE_SLUGS["separation"],
        physical_ic_count=None,
        intent=ControlIntent.APPLY,
    )
    send.assert_awaited_once()
    assert send.await_args.args == (build_brightness(72, "H617A"),)
    send.await_args.kwargs["write_guard"]()
    refresh.assert_awaited_once_with(
        expected_on=True, expected_brightness=72, expected_music_mode="separation", expected_music_sensitivity=50
    )


async def test_restore_effect_control_state_reapplies_complete_video_profile(h6199):
    from tests.test_h6199_capabilities import set_qualified_identity

    set_qualified_identity(h6199)
    initial = h6199.capture_effect_control_state()
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
        white_balance_flag=1,
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
        patch(f"{M}_recovery.apply_white_balance", new_callable=AsyncMock, return_value=True) as white_balance,
        patch(
            f"{M}_recovery.apply_relative_brightness", new_callable=AsyncMock, return_value=True
        ) as relative_brightness,
        patch(f"{M}_recovery.apply_blank_screen", new_callable=AsyncMock, return_value=True) as blank_screen,
        patch(f"{M}_recovery.apply_active_video_mode", new_callable=AsyncMock, return_value=True) as video_mode,
        patch.object(h6199, "send_command", new=AsyncMock()),
        patch.object(h6199, "refresh_state", new=AsyncMock(return_value=True)),
    ):
        recovered = await h6199.async_restore_effect_control_state(
            state,
            overwritten_diy_code=None,
        )

    assert recovered is True
    white_balance.assert_awaited_once_with(h6199, (21, 5), flag=1)
    relative_brightness.assert_awaited_once_with(h6199, (20, 30, 40, 50))
    blank_screen.assert_awaited_once_with(h6199, True)
    video_mode.assert_awaited_once_with(
        h6199,
        parameters=None,
        mode="game",
        requested_values={"full_screen": False, "saturation": 63, "sound_effects": True, "sound_effects_softness": 27},
    )
    assert h6199.capture_effect_control_state() == initial


@pytest.mark.parametrize(
    ("enabled", "policy", "change_during_restore"),
    [
        pytest.param(False, (1, 30, 240), False, id="restore-enable-with-live-policy"),
        pytest.param(True, (1, 30, 240), False, id="policy-only-no-blank-write"),
        pytest.param(False, (None, 30, 240), False, id="unknown-detection"),
        pytest.param(False, (1, None, 240), False, id="unknown-low-duration"),
        pytest.param(False, (1, 30, None), False, id="unknown-same-duration"),
        pytest.param(False, (1, 30, 240), True, id="policy-changes-at-physical-boundary"),
    ],
)
async def test_blank_screen_recovery_preserves_live_policy(h6199, enabled, policy, change_during_restore):
    from tests.test_h6199_capabilities import QUALIFIED

    vars(h6199).update(QUALIFIED)
    h6199._confirmed_identity_fields.update(video_identity_fields(h6199.profile))
    h6199.is_on = True
    h6199.color_mode = ParsedMode.SCENE
    h6199.effect = "candlelight"
    h6199._scene_code = MODEL_SCENES["H6199"]["candlelight"].code
    h6199._notify_callback(None, bytearray(_packet(0xAA, 0xA9, [0x0A, 0x06, 1, 2, 10, 0, 120, 0])))
    state = h6199.capture_effect_control_state()
    h6199.blank_screen = enabled
    (
        h6199.blank_screen_detection,
        h6199.blank_screen_low_brightness_duration_seconds,
        h6199.blank_screen_same_tone_duration_seconds,
    ) = policy
    client = _c(write_gatt_char=AsyncMock())

    async def connect():
        if not client.write_gatt_char.await_count:
            assert h6199.blank_screen is enabled
            assert "blank_screen" not in h6199._expected_state
        if change_during_restore:
            h6199._notify_callback(None, bytearray(_packet(0xAA, 0xA9, [0x0A, 0x06, 0, 0, 60, 0, 44, 1])))
        return client

    async def refresh_policy(**kwargs):
        if kwargs.get("refresh_display_settings") and None not in policy:
            h6199._notify_callback(
                None, bytearray(_packet(0xAA, 0xA9, [0x0A, 0x06, int(enabled), policy[0], policy[1], 0, policy[2], 0]))
            )
        return True

    with (
        patch.object(h6199, "_ensure_connected", new=AsyncMock(side_effect=connect)),
        patch.object(h6199, "refresh_state", new=AsyncMock(side_effect=refresh_policy)) as refresh,
    ):
        if None in policy or change_during_restore:
            message = "policy changed before write" if change_during_restore else "policy state has not been read"
            with pytest.raises(ValueError, match=message):
                await h6199.async_restore_effect_control_state(state, overwritten_diy_code=None)
            client.write_gatt_char.assert_not_awaited()
            refresh.assert_awaited_once_with(refresh_display_settings=frozenset({"blank_screen"}))
            assert h6199.blank_screen is enabled
            assert "blank_screen" not in h6199._expected_state
        else:
            recovered = await h6199.async_restore_effect_control_state(state, overwritten_diy_code=None)
            scene = MODEL_SCENES["H6199"]["candlelight"]
            assert recovered is (not bool(scene.param))
            packets = ([] if enabled else [build_blank_screen(True, "H6199", *policy)]) + [
                build_power(True, "H6199"),
                build_brightness(state.brightness_pct, "H6199"),
                build_scene_activation("H6199", scene.code, scene.music_code),
            ]
            assert client.write_gatt_char.await_args_list == [
                call(WRITE_UUID, packet, response=False) for packet in packets
            ]
            assert refresh.await_args_list == (
                []
                if enabled
                else [call(refresh_display_settings=frozenset({"blank_screen"})), call(expected_blank_screen=True)]
            ) + [call(expected_on=True, expected_brightness=state.brightness_pct, expected_scene_code=scene.code)]
            assert h6199.blank_screen is True
    assert (
        h6199.blank_screen_detection,
        h6199.blank_screen_low_brightness_duration_seconds,
        h6199.blank_screen_same_tone_duration_seconds,
    ) == ((0, 60, 300) if change_during_restore else policy)


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

    assert recovered is (not bool(scene.param))
    assert send.await_args_list == [
        call(build_power(True, "H6199")),
        call(build_brightness(72, "H6199")),
        call(build_scene_activation("H6199", scene.code, scene.music_code)),
    ]
    refresh.assert_awaited_once_with(expected_on=True, expected_brightness=72, expected_scene_code=scene.code)


async def test_restore_h6179_scene_converts_legacy_catalogue_code_to_wire_selector(hass):
    coordinator = GoveeBLECoordinator(
        hass,
        "22:33:44:55:66:78",
        "H6179",
        configuration_url=_CONFIGURATION_URL,
    )
    scene = MODEL_SCENES["H6179"]["karst cave"]
    selector = scene_selector_code("H6179", scene)
    state = PriorControlState(
        mode="scene",
        is_on=True,
        brightness_pct=72,
        rgb_color=(1, 2, 3),
        effect="karst cave",
        scene_code=scene.code,
    )

    with (
        patch.object(coordinator, "send_command", new_callable=AsyncMock) as send,
        patch.object(coordinator, "refresh_state", new_callable=AsyncMock, return_value=True) as refresh,
    ):
        recovered = await coordinator.async_restore_effect_control_state(state, overwritten_diy_code=None)

    assert recovered is False
    assert send.await_args_list == [
        call(build_power(True, "H6179")),
        call(build_brightness(72, "H6179")),
        call(build_scene_activation("H6179", selector, scene.music_code)),
    ]
    refresh.assert_awaited_once_with(expected_on=True, expected_brightness=72, expected_scene_code=selector)


async def test_h6179_zero_kelvin_rgb_observation_replaces_retained_white_and_restores_rgb(hass):
    coordinator = GoveeBLECoordinator(hass, "55:66:77:88:99:AA", "H6179", configuration_url=_CONFIGURATION_URL)
    coordinator._notify_callback(None, bytearray(_packet(0xAA, 1, [1])))
    coordinator._notify_callback(None, bytearray(_packet(0xAA, 5, [0x0D, 255, 255, 255, 0x0E, 0x10, 255, 203, 141])))
    assert coordinator.color_temp_kelvin == 3600
    rgb = kelvin_companion_rgb(3600, coordinator.profile)
    coordinator._notify_callback(None, bytearray(_packet(0xAA, 5, [0x0D, *rgb, 0, 0, 0, 0, 0])))
    state = PriorControlState.from_dict(coordinator.capture_effect_control_state().to_dict())
    assert state.color_temp_kelvin is None and state.rgb_color == rgb

    with (
        patch.object(coordinator, "send_command", new_callable=AsyncMock) as send,
        patch.object(coordinator, "refresh_state", new_callable=AsyncMock, return_value=True) as refresh,
    ):
        assert await coordinator.async_restore_effect_control_state(state, overwritten_diy_code=None)

    assert send.await_args_list == [
        call(build_power(True, "H6179")),
        call(build_brightness(100, "H6179")),
        call(build_color_rgb(*rgb, "H6179")),
    ]
    refresh.assert_awaited_once_with(
        expected_on=True, expected_brightness=100, expected_rgb_color=rgb, expected_zero_kelvin=True
    )


async def test_h6179_off_grid_persisted_kelvin_restores_against_normalised_readback(hass, monkeypatch, virtual_clock):
    coord = GoveeBLECoordinator(hass, "55:66:77:88:99:AA", "H6179", configuration_url=_CONFIGURATION_URL)
    client = _c(write_gatt_char=AsyncMock())
    coord._client = client
    monkeypatch.setattr(coord, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(coord, "_renew_foreground_lease", lambda: None)

    async def respond(_uuid, packet, **kwargs):
        replies = {
            b"\xaa\x01": _packet(0xAA, 1, [1]),
            b"\xaa\x04": _packet(0xAA, 4, [254]),
            b"\xaa\x05": _packet(0xAA, 5, [0x0D, 255, 255, 255, 7, 0xD0, 255, 141, 11]),
        }
        if reply := replies.get(packet[:2]):
            coord._notify_callback(None, bytearray(reply))

    client.write_gatt_char.side_effect = respond
    state = PriorControlState.from_dict(
        PriorControlState(
            mode="colour", is_on=True, brightness_pct=100, rgb_color=(255, 141, 11), color_temp_kelvin=2001
        ).to_dict()
    )
    assert await coord.async_restore_effect_control_state(state, overwritten_diy_code=None)
    assert coord.color_temp_kelvin == 2000


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize(
    "outcome",
    ["match", "mismatch", "missing", "write_failure", "reconnect_failure", "profile_changed", "subscription_changed"],
)
async def test_h6179_current_adaptation_reconnects_without_replay_and_requires_fresh_readback(
    hass, monkeypatch, virtual_clock, enabled, outcome
):
    from bleak.exc import BleakError

    coord = GoveeBLECoordinator(hass, "55:66:77:88:99:AA", "H6179", configuration_url=_CONFIGURATION_URL)
    coord.pact_type, coord.pact_code = 1, 1
    coord._resolve_device_profile()
    coord.boolean_control_state["limit"] = enabled
    old = _c(write_gatt_char=AsyncMock())
    new = _c(write_gatt_char=AsyncMock())
    coord._client = old
    connections = 0

    async def connect():
        nonlocal connections
        connections += 1
        if connections > 2 and outcome == "reconnect_failure":
            raise BleakError("Restarted controller is unavailable")
        coord._client = old if connections <= 2 else new
        if connections > 2 and outcome == "profile_changed":
            coord.pact_type, coord.pact_code = 10, 1
            coord._resolve_device_profile()
        return coord._client

    async def respond(_uuid, packet, **kwargs):
        if packet[:2] == b"\xaa\x0e" and outcome in {"match", "mismatch", "subscription_changed"}:
            coord._notify_callback(
                None, bytearray(_packet(0xAA, 0x0E, [int(not enabled if outcome == "mismatch" else enabled)]))
            )
            if outcome == "subscription_changed":
                coord._notification_token = object()

    new.write_gatt_char.side_effect = respond

    async def write_setting(_uuid, packet, **kwargs):
        if outcome == "write_failure":
            raise BleakError("Controller disconnected during setting write")
        coord._notify_callback(None, bytearray(_packet(0xAA, 0x0E, [int(enabled)])))

    old.write_gatt_char.side_effect = write_setting
    monkeypatch.setattr(coord, "_ensure_connected", connect)
    monkeypatch.setattr(coord, "_renew_foreground_lease", lambda: None)
    if outcome == "match":
        await coord.async_set_boolean_control("limit", enabled)
        assert coord.boolean_control_state["limit"] is enabled
    else:
        with pytest.raises((ValueError, BleakError)):
            await coord.async_set_boolean_control("limit", enabled)
    old.disconnect.assert_awaited_once()
    assert [item.args[1] for item in old.write_gatt_char.await_args_list] == [_packet(0x33, 0x0E, [int(enabled)])]
    assert all(item.args[1][:1] == b"\xaa" for item in new.write_gatt_char.await_args_list)
    coord._clear_client_state(coord._client)


async def test_restore_effect_control_state_maps_h617e_legacy_scene_name(hass):
    coordinator = GoveeBLECoordinator(
        hass,
        "22:33:44:55:66:78",
        "H617E",
        configuration_url=_CONFIGURATION_URL,
    )
    state = PriorControlState(
        mode="scene",
        is_on=True,
        brightness_pct=72,
        rgb_color=(1, 2, 3),
        effect="aurora",
    )
    scene = MODEL_SCENES["H617E"]["aurora-a"]

    with (
        patch.object(coordinator, "send_command", new_callable=AsyncMock) as send,
        patch.object(coordinator, "refresh_state", new_callable=AsyncMock, return_value=True) as refresh,
    ):
        assert await coordinator.async_restore_effect_control_state(state, overwritten_diy_code=None) is (
            not bool(scene.param)
        )

    assert send.await_args_list == [
        call(build_power(True, "H617E")),
        call(build_brightness(72, "H617E")),
        call(build_scene_activation("H617E", scene.code, scene.music_code)),
    ]
    refresh.assert_awaited_once_with(expected_on=True, expected_brightness=72, expected_scene_code=scene.code)


async def test_restore_effect_control_state_preserves_h617e_raw_legacy_scene(hass):
    coordinator = GoveeBLECoordinator(
        hass,
        "22:33:44:55:66:79",
        "H617E",
        configuration_url=_CONFIGURATION_URL,
    )
    exact_codes = {scene.code for scene in MODEL_SCENES["H617E"].values()}
    legacy_name, legacy = next(
        (name, scene) for name, scene in MODEL_SCENES["H617A"].items() if scene.code not in exact_codes
    )
    coordinator.is_on = True
    coordinator.color_mode = ParsedMode.SCENE
    coordinator._scene_code = legacy.code
    coordinator.effect = None
    state = coordinator.capture_effect_control_state()

    assert state.mode == "scene"
    assert state.scene_code == legacy.code
    with (
        patch.object(coordinator, "send_command", new_callable=AsyncMock) as send,
        patch.object(coordinator, "refresh_state", new_callable=AsyncMock, return_value=True) as refresh,
    ):
        assert await coordinator.async_restore_effect_control_state(state, overwritten_diy_code=None) is (
            not bool(legacy.param)
        )

    assert send.await_args_list == [
        call(build_power(True, "H617E")),
        call(build_brightness(state.brightness_pct, "H617E")),
        call(build_scene_activation("H617E", legacy.code, legacy.music_code)),
    ]
    refresh.assert_awaited_once_with(
        expected_on=True, expected_brightness=state.brightness_pct, expected_scene_code=legacy.code
    )


async def test_restore_effect_control_state_uses_legacy_identity_to_disambiguate_scene_code(hass):
    coordinator = GoveeBLECoordinator(
        hass,
        "22:33:44:55:66:80",
        "H617E",
        configuration_url=_CONFIGURATION_URL,
    )
    legacy = MODEL_SCENES["H617A"]["aurora"]
    state = PriorControlState(
        mode="scene",
        is_on=True,
        brightness_pct=72,
        rgb_color=(1, 2, 3),
        effect="aurora",
        scene_code=legacy.code,
    )

    with (
        patch.object(coordinator, "send_command", new_callable=AsyncMock) as send,
        patch.object(coordinator, "refresh_state", new_callable=AsyncMock, return_value=True),
    ):
        assert await coordinator.async_restore_effect_control_state(state, overwritten_diy_code=None) is (
            not bool(legacy.param)
        )

    assert send.await_args_list == [
        call(build_power(True, "H617E")),
        call(build_brightness(72, "H617E")),
        call(build_scene_activation("H617E", legacy.code, legacy.music_code)),
    ]
