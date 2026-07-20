"""Tests for the Govee BLE device simulator and its coordinator wiring."""

from unittest.mock import MagicMock

import pytest

from custom_components.ha_govee_led_ble import protocol as proto
from custom_components.ha_govee_led_ble.const import MUSIC_MODES
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from tests.mock_ble import (
    MODELS,
    MockBle,
    mock_ble_fixture,  # noqa: F401
    mock_ble_h6199_fixture,  # noqa: F401
    parse_color_reply,
    segment_brightness_packet,
    segment_color_packet,
)
from tools.ble.mock_ble.mock_device import GoveeDeviceSim


@pytest.mark.parametrize("model", MODELS)
def test_power_and_brightness_commands_mutate(model):
    sim = GoveeDeviceSim(model)
    sim.handle_write(proto.build_power(True))
    assert sim.is_on is True
    sim.handle_write(proto.build_power(False))
    assert sim.is_on is False
    sim.handle_write(proto.build_brightness(37))
    assert sim.brightness_pct == 37


@pytest.mark.parametrize("model", MODELS)
def test_power_brightness_replies_roundtrip(model):
    sim = GoveeDeviceSim(model)
    sim.is_on = True
    sim.brightness_pct = 82
    (power,) = sim.handle_write(proto.STATE_QUERY)
    (bright,) = sim.handle_write(proto.BRIGHTNESS_QUERY)
    assert power[1] == proto.POWER_PACKET_TYPE and power[2] == 1
    assert bright[1] == proto.BRIGHTNESS_PACKET_TYPE and bright[2] == 82


@pytest.mark.parametrize("model", MODELS)
def test_rgb_command_fills_segments_and_roundtrips(model):
    sim = GoveeDeviceSim(model)
    sim.handle_write(proto.build_color_rgb(10, 20, 30))
    assert sim.color_mode == "rgb"
    assert sim.rgb_color == (10, 20, 30)
    assert all(seg == (10, 20, 30) for seg in sim.segments)
    assert parse_color_reply(sim).rgb_color == (10, 20, 30)


@pytest.mark.parametrize("model", MODELS)
def test_color_temp_default_readback_is_static_rgb(model):
    sim = GoveeDeviceSim(model)
    sim.handle_write(proto.build_color_temp(4000))
    assert sim.color_mode == "ct"
    assert sim.color_temp_kelvin == 4000
    parsed = parse_color_reply(sim)
    # A colour-temp state reads back as its white-point RGB (no kelvin field); the coordinator
    # recognises the white point and keeps CT (see test_ct_readback_keeps_coordinator_kelvin).
    assert parsed.rgb_color == sim.rgb_color == proto.kelvin_to_rgb(4000)
    assert parsed.white_brightness is None


async def test_ct_readback_keeps_coordinator_kelvin(mock_ble):
    """A colour-temp read-back echoes the white point; the coordinator keeps CT, not RGB."""
    sim, coord = mock_ble.sim, mock_ble.coordinator
    sim.handle_write(proto.build_color_temp(4000))
    coord.color_temp_kelvin, coord.rgb_color = 4000, proto.kelvin_to_rgb(4000)
    (frame,) = sim.handle_write(proto.COLOR_MODE_QUERY)
    coord._apply_color_mode_payload(frame[2:-1])
    assert coord.color_temp_kelvin == 4000
    # A genuinely different RGB read still drops CT and switches to RGB.
    coord._apply_color_mode_payload(bytes([proto.COLOR_MODE_STATIC, 0x01, 10, 20, 30]))
    assert coord.color_temp_kelvin is None and coord.rgb_color == (10, 20, 30)


@pytest.mark.parametrize("model", MODELS)
def test_white_brightness_command_roundtrips(model):
    sim = GoveeDeviceSim(model)
    sim.handle_write(proto.build_white_brightness(45))
    assert sim.color_mode == "white"
    assert sim.white_brightness == 45
    assert all(level == 45 for level in sim.segment_brightness)
    assert parse_color_reply(sim).white_brightness == 45


@pytest.mark.parametrize("model", MODELS)
def test_scene_command_roundtrips(model):
    sim = GoveeDeviceSim(model)
    sim.handle_write(proto.build_scene(2205))
    assert sim.scene_code == 2205
    assert sim.effect == "candy"
    assert parse_color_reply(sim).effect == "candy"


@pytest.mark.parametrize("model", MODELS)
def test_music_command_roundtrips(model):
    sim = GoveeDeviceSim(model)
    sim.handle_write(proto.build_music_mode_with_color(MUSIC_MODES["spectrum"], sensitivity=66, color=(1, 2, 3)))
    assert sim.effect == "music: spectrum"
    assert sim.music_sensitivity == 66
    assert sim.music_color == (1, 2, 3)
    parsed = parse_color_reply(sim)
    assert parsed.music_mode == "spectrum" and parsed.effect is None
    assert parsed.music_sensitivity == 66
    assert parsed.music_color == (1, 2, 3)


def test_video_command_applies_only_on_h6199():
    h6199 = GoveeDeviceSim("H6199")
    h6199.handle_write(proto.build_video_mode(full_screen=False, game_mode=True, saturation=70))
    assert h6199.color_mode == "video"
    assert h6199.effect == "video: game"
    parsed = parse_color_reply(h6199)
    assert parsed.video_mode == "game" and parsed.effect is None
    assert parsed.video_full_screen is False
    assert parsed.video_saturation == 70
    # H617A has no video capability, so the frame is ignored.
    h617a = GoveeDeviceSim("H617A")
    h617a.handle_write(proto.build_video_mode(game_mode=True))
    assert h617a.color_mode == "rgb"
    assert h617a.effect is None


def test_video_white_balance_gated():
    h6199 = GoveeDeviceSim("H6199")
    h6199.handle_write(proto.build_video_white_balance(0x0F, 0x04))
    assert h6199.video_white_balance == (0x0F, 0x04)
    h617a = GoveeDeviceSim("H617A")
    h617a.handle_write(proto.build_video_white_balance(0x0F, 0x04))
    assert h617a.video_white_balance is None


@pytest.mark.parametrize("model", MODELS)
def test_segment_writes_address_individual_slots(model):
    sim = GoveeDeviceSim(model)
    sim.handle_write(segment_color_packet((255, 0, 0), mask=0b101))
    assert sim.segments[0] == (255, 0, 0)
    assert sim.segments[2] == (255, 0, 0)
    assert sim.segments[1] != (255, 0, 0)
    # Partial writes are write-only and don't change the reported whole-strip mode.
    assert sim.color_mode == "rgb"
    sim.handle_write(segment_brightness_packet(20, mask=0b10))
    assert sim.segment_brightness[1] == 20
    assert sim.segment_brightness[0] != 20


async def test_ensure_connected_converges_core_state(mock_ble: MockBle):
    sim, coord = mock_ble.sim, mock_ble.coordinator
    sim.is_on = True
    sim.brightness_pct = 42
    sim.handle_write(proto.build_color_rgb(10, 20, 30))
    await coord._ensure_connected()
    assert coord.is_on is True
    assert coord.brightness_pct == 42
    assert coord.rgb_color == (10, 20, 30)
    assert coord.color_temp_kelvin is None
    assert coord.effect is None


async def test_refresh_state_converges_effect(mock_ble: MockBle):
    sim, coord = mock_ble.sim, mock_ble.coordinator
    sim.handle_write(proto.build_scene(2205))
    coord.effect = None
    assert await coord.refresh_state(expected_effect="candy") is True
    assert coord.effect == "candy"


async def test_refresh_state_converges_music_mode(mock_ble: MockBle):
    sim, coord = mock_ble.sim, mock_ble.coordinator
    sim.handle_write(proto.build_music_mode_with_color(MUSIC_MODES["rhythm"], sensitivity=50))
    coord.music_mode = "off"
    assert await coord.refresh_state() is True
    assert coord.music_mode == "rhythm"
    assert coord.effect is None


async def test_set_music_mode_confirms_via_music_mode(mock_ble: MockBle, monkeypatch):
    """End to end (un-mocked): the readback lands in music_mode, so the confirm converges."""
    coord = mock_ble.coordinator
    light = GoveeBLELight(coord)
    notified = MagicMock()
    monkeypatch.setattr(light, "async_write_ha_state", notified)
    await light.async_set_music_mode(mode="spectrum", sensitivity=70)
    assert coord.music_mode == "spectrum"
    assert coord.is_on is True
    assert coord.effect is None
    assert coord.music_sensitivity == 70
    notified.assert_called_once()


async def test_set_video_mode_confirms_via_video_mode(mock_ble_h6199: MockBle, monkeypatch):
    """End to end (un-mocked): the H6199 readback lands in video_mode and the confirm converges."""
    coord = mock_ble_h6199.coordinator
    light = GoveeBLELight(coord)
    notified = MagicMock()
    monkeypatch.setattr(light, "async_write_ha_state", notified)
    await light.async_set_video_mode(mode="game", saturation=60)
    assert coord.video_mode == "game"
    assert coord.is_on is True
    assert coord.effect is None
    assert coord.video_saturation == 60
    notified.assert_called_once()


async def test_update_data_queries_reach_sim(mock_ble: MockBle):
    sim, coord = mock_ble.sim, mock_ble.coordinator
    sim.is_on = True
    sim.brightness_pct = 77
    await coord._async_update_data()
    assert coord.is_on is True
    assert coord.brightness_pct == 77
