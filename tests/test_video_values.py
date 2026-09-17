"""Issue #297: a different generated grammar survives every native video entry."""

from dataclasses import replace
from importlib import import_module
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, ModelProfile, ReadDomain
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_expectations import expectations_from_packet
from custom_components.ha_govee_led_ble.effect_compiler import compile_video_profile
from custom_components.ha_govee_led_ble.effect_deployments import PriorControlState
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem, VideoProfile
from custom_components.ha_govee_led_ble.effect_runtime import async_apply_compiled_profile
from custom_components.ha_govee_led_ble.generated_protocol_adapter import _STATUS_ROOTS, build_video_mode
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.native_profile_controls import apply_active_video_mode, prepare_video_mode
from tests.test_h6099 import frame


@pytest.fixture
def device(hass, monkeypatch):
    profile = ModelProfile(
        "Video values software fixture",
        command_grammar="H617A",
        status_grammar="test-video-values",
        video_grammar="H66A0-video",
        supports_video_mode=True,
        video_modes=("movie", "game"),
        supports_video_saturation=True,
        supports_video_sound_effects=True,
        read_domains=frozenset({ReadDomain.POWER, ReadDomain.BRIGHTNESS, ReadDomain.COLOUR_MODE}),
    )
    monkeypatch.setitem(MODEL_PROFILES, "H7002", profile)
    root = import_module("custom_components.ha_govee_led_ble.generated_protocol.h66a0_video_status").H66a0VideoStatus
    monkeypatch.setitem(_STATUS_ROOTS, "test-video-values", ("h66a0_video_status", root))
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H7002", configuration_url="test")
    coordinator._notify_callback(None, bytearray(frame("aa0500000b3e01a537")))
    coordinator._client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    monkeypatch.setattr(coordinator, "refresh_state", AsyncMock(return_value=True))
    return coordinator


@pytest.mark.parametrize("mode,source", [("movie", "00"), ("game", "01")])
async def test_selector_compiled_and_recovery_preserve_values(device, monkeypatch, mode, source):
    assert "H66A0" not in MODEL_PROFILES
    assert device.video_parameters == {"picture_preset": "delicate", "opaque": 0xA5}
    assert device._field_revisions["video_parameters"] == 1

    device.is_on = True
    snapshot = device.capture_effect_control_state()
    assert PriorControlState.from_dict(snapshot.to_dict()) == snapshot
    legacy = snapshot.to_dict()
    del legacy["video_parameters"]
    assert PriorControlState.from_dict(legacy).video_parameters is None
    light = GoveeBLELight(device)
    monkeypatch.setattr(light, "_notify_state_changed", lambda: None)
    await light.async_turn_on(effect=f"Video: {mode.title()}")
    expected = frame(f"330500{source}0b3e01a537")
    assert device._client.write_gatt_char.await_args.args[1] == expected
    assert device.video_parameters == snapshot.video_parameters
    assert device._field_revisions["video_parameters"] == 1  # optimistic != observed
    assert device.refresh_state.await_args.kwargs["expected_video_parameters"] == snapshot.video_parameters
    assert expectations_from_packet(expected, "H7002")["video_parameters"] == snapshot.video_parameters

    content = VideoProfile("H7002", mode, None, 62, True, 55, None, None, None)
    compiled = compile_video_profile(LibraryItem.new("Fixture default", content), "H7002")
    monkeypatch.setattr(light, "_compile_template_default", lambda _: compiled)
    await light.async_turn_on(effect=f"Video: {mode.title()}")
    assert device._client.write_gatt_char.await_args.args[1] == expected
    await async_apply_compiled_profile(device, compiled)
    assert device._client.write_gatt_char.await_args.args[1] == expected

    device.video_parameters = {"picture_preset": "vivid", "opaque": 0x12}
    assert await device.async_restore_effect_control_state(snapshot, overwritten_diy_code=None)
    assert device._client.write_gatt_char.await_args.args[1] == frame("330500000b3e01a537")
    assert device.video_parameters == snapshot.video_parameters
    assert device._field_revisions["video_parameters"] == 1

    await device.async_restore_effect_control_state(replace(snapshot, is_on=False), overwritten_diy_code=None)
    writes = device._client.write_gatt_char.await_args_list
    assert writes[-2].args[1] == frame("330500000b3e01a537")
    assert writes[-1].args[1] == frame("330100")
    assert not device.is_on
    device._client.write_gatt_char.reset_mock()
    with pytest.raises(ValueError, match="requires picture_preset"):
        await device.async_restore_effect_control_state(
            replace(snapshot, video_parameters=None), overwritten_diy_code=None
        )
    device._client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize(
    "values",
    [
        None,
        {},
        {"picture_preset": "delicate"},
        {"picture_preset": "wrong", "opaque": 2},
        {"picture_preset": "solid", "opaque": True},
    ],
)
async def test_invalid_values_precede_all_selector_side_effects(device, monkeypatch, values):
    device.video_parameters = values
    device.is_on = False
    light = GoveeBLELight(device)
    cancel = AsyncMock()
    monkeypatch.setattr(light, "_async_supersede_preview", cancel)
    with pytest.raises(ValueError):
        await light.async_turn_on(effect="Video: Movie", brightness=50)
    cancel.assert_not_awaited()
    device._client.write_gatt_char.assert_not_awaited()
    assert not device.is_on and not device._expected_state


async def test_guard_runs_after_transform_and_retains_fresh_reply(device):
    device.is_on = True

    def transform(packet):
        device.video_parameters = {"picture_preset": "solid", "opaque": 0x12}
        return packet

    device.profile = replace(device.profile, outbound_transform=transform)
    with pytest.raises(ValueError, match="Retained video values"):
        await apply_active_video_mode(device, mode="game", requested_values={})
    device._client.write_gatt_char.assert_not_awaited()

    device.profile = replace(device.profile, outbound_transform=None)

    async def reply(*args, **kwargs):
        device._expected_state.clear()
        device._notify_callback(None, bytearray(frame("aa0500010a3e016637")))

    device._client.write_gatt_char.side_effect = reply
    await apply_active_video_mode(device, mode="game", requested_values={}, verify=False)
    assert device.video_parameters == {"picture_preset": "smooth", "opaque": 0x66}
    assert device._field_revisions["video_parameters"] == 2


def test_effective_profile_and_reconnect_guard(device):
    profile = replace(device.profile, video_saturation_min=70)
    with pytest.raises(ValueError, match="saturation"):
        build_video_mode("movie", True, 62, True, 55, device.model, values=device.video_parameters, profile=profile)
    _, _, _, guard = prepare_video_mode(device, mode="movie", requested_values={})
    device._notification_token = object()
    with pytest.raises(ValueError, match="connection changed"):
        guard()


async def test_extra_values_require_fresh_matching_readback(device, monkeypatch):
    # Exercise the real refresh implementation; stale optimistic state is insufficient.
    monkeypatch.setattr(device, "refresh_state", GoveeBLECoordinator.refresh_state.__get__(device))

    async def mismatch(*args, **kwargs):
        device._expected_state.clear()
        device._notify_callback(None, bytearray(frame("aa0500000b3e01a437")))
        return True

    monkeypatch.setattr(device, "_send_state_queries", mismatch)
    assert not await device.refresh_state(
        expected_video_parameters={"picture_preset": "delicate", "opaque": 0xA5}, timeout=0.001
    )

    async def match(*args, **kwargs):
        device._notify_callback(None, bytearray(frame("aa0500000b3e01a537")))
        return True

    monkeypatch.setattr(device, "_send_state_queries", match)
    assert await device.refresh_state(
        expected_video_parameters={"picture_preset": "delicate", "opaque": 0xA5}, timeout=0.001
    )
