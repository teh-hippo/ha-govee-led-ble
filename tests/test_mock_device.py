"""Tests for the Govee BLE device simulator and its coordinator wiring."""

from unittest.mock import MagicMock

import pytest

from custom_components.ha_govee_led_ble import protocol as proto
from custom_components.ha_govee_led_ble.const import MUSIC_MODES
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.scenes import SCENES
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
def test_identity_replies_roundtrip(model):
    sim = GoveeDeviceSim(model)
    (firmware,) = sim.handle_write(proto.FW_QUERY)
    (hardware,) = sim.handle_write(proto.HW_QUERY)
    firmware_status = proto.decode_status_frame(firmware, model)
    hardware_status = proto.decode_status_frame(hardware, model)
    assert firmware_status is not None and firmware_status.generated.body.text == sim.firmware
    assert hardware_status is not None and hardware_status.generated.body.text == sim.hardware


@pytest.mark.parametrize("model", MODELS)
def test_rgb_command_fills_segments_and_roundtrips(model):
    sim = GoveeDeviceSim(model)
    sim.handle_write(proto.build_color_rgb(10, 20, 30))
    assert sim.color_mode == "rgb"
    assert sim.rgb_color == (10, 20, 30)
    assert all(seg == (10, 20, 30) for seg in sim.segments)
    expected = (10, 20, 30) if sim.profile.static_readback_echoes_color else None
    assert parse_color_reply(sim).rgb_color == expected


@pytest.mark.parametrize("model", MODELS)
def test_color_temp_default_readback_is_static_rgb(model):
    sim = GoveeDeviceSim(model)
    sim.handle_write(proto.build_color_temp(4000))
    assert sim.color_mode == "ct"
    assert sim.color_temp_kelvin == 4000
    parsed = parse_color_reply(sim)
    if not sim.profile.static_readback_echoes_color:
        # Nothing is echoed, so the coordinator's kelvin is never challenged in the first place.
        assert parsed.rgb_color is None
        return
    # A colour-temp state reads back as its white-point RGB (no kelvin field); the coordinator
    # recognises the white point and keeps CT (see test_ct_readback_keeps_coordinator_kelvin).
    assert parsed.rgb_color == sim.rgb_color == proto.kelvin_to_rgb(4000)
    assert parsed.white_brightness is None


async def test_ct_readback_keeps_coordinator_kelvin(mock_ble):
    """A static read-back carries no colour, so the coordinator keeps its optimistic CT."""
    sim, coord = mock_ble.sim, mock_ble.coordinator
    sim.handle_write(proto.build_color_temp(4000))
    coord.color_temp_kelvin, coord.rgb_color = 4000, proto.kelvin_to_rgb(4000)
    (frame,) = sim.handle_write(proto.COLOR_MODE_QUERY)
    coord._notify_callback(None, bytearray(frame))
    assert coord.color_temp_kelvin == 4000
    assert coord.rgb_color == proto.kelvin_to_rgb(4000)


@pytest.mark.parametrize("model", MODELS)
def test_white_brightness_command_roundtrips(model):
    sim = GoveeDeviceSim(model)
    sim.handle_write(proto.build_white_brightness(45))
    assert sim.color_mode == "white"
    assert sim.white_brightness == 45
    assert all(level == 45 for level in sim.segment_brightness)
    expected = 45 if sim.profile.static_readback_echoes_color else None
    assert parse_color_reply(sim).white_brightness == expected


@pytest.mark.parametrize("model", MODELS)
def test_static_readback_reports_the_multi_effect_register(model):
    """The byte after the static mode is the 33 a3 register, not a colour sub-selector."""
    sim = GoveeDeviceSim(model)
    sim.handle_write(proto.build_color_rgb(10, 20, 30))
    sim.handle_write(proto.build_packet(proto.COMMAND_HEADER, 0xA3, [0x01]))
    assert sim.multi_effect_flag == 1
    (reply,) = sim.handle_write(proto.build_packet(proto.STATUS_HEADER, 0xA3, []))
    assert proto.split_status_frame(reply)[1][0] == 1
    if sim.profile.static_readback_echoes_color:
        return
    parsed = parse_color_reply(sim)
    assert parsed.multi_effect_flag == (1 if model == "H617A" else None)
    # Decoding the zero payload as a colour here would report the strip as black.
    assert parsed.rgb_color is None


async def test_colour_readback_is_accepted_and_never_blacks_out(mock_ble: MockBle):
    """The static reply must satisfy the expectation it arms, and must not repaint the strip.

    Two failures ride on the same byte. Expecting the write-side sub back rejects every reply
    for the whole optimistic window, and reading a colour out of the zero payload sets the
    strip to (0, 0, 0) as soon as anything has written the 33 a3 register.
    """
    sim, coord = mock_ble.sim, mock_ble.coordinator
    coord.effect_families = frozenset({"scenes", "music", "video"})
    await coord._ensure_connected()
    # Let the stale effect arrive from the device rather than poking it in, so the state under
    # test is one the coordinator actually reaches.
    # Candlelight because both models name it: the H6199 only names the three scenes a
    # capture confirmed it can start, so an arbitrary catalogue code reads back unnamed there.
    sim.handle_write(proto.build_scene(SCENES["candlelight"].code))
    (reply,) = sim.handle_write(proto.COLOR_MODE_QUERY)
    coord._notify_callback(None, bytearray(reply))
    learned_effect = coord.effect
    assert learned_effect == "candlelight"

    # The register sits at 0 until something writes it, which is the state every colour write
    # lands in. The reply must still confirm the mode rather than be discarded as stale.
    await coord.send_command(proto.build_color_rgb(10, 20, 30))
    coord.rgb_color = (10, 20, 30)
    (reply,) = sim.handle_write(proto.COLOR_MODE_QUERY)
    coord._notify_callback(None, bytearray(reply))
    assert coord.color_mode is proto.ParsedMode.COLOUR
    assert coord.effect is None
    assert coord.rgb_color == (10, 20, 30)

    # Writing the register moves the same byte to 1, where a colour read invents black. Clear the
    # optimistic window first: it happens to mask this, so a later background poll is the real case.
    sim.handle_write(proto.build_packet(proto.COMMAND_HEADER, 0xA3, [0x01]))
    coord._expected_state.clear()
    (reply,) = sim.handle_write(proto.COLOR_MODE_QUERY)
    coord._notify_callback(None, bytearray(reply))
    assert coord.rgb_color == (10, 20, 30)


@pytest.mark.parametrize("model", MODELS)
def test_scene_command_roundtrips(model):
    sim = GoveeDeviceSim(model)
    sim.handle_write(proto.build_scene(9))
    assert sim.scene_code == 9
    assert sim.effect == "candlelight"
    assert parse_color_reply(sim).effect == "candlelight"


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


def test_video_frame_always_carries_sound_and_softness():
    sim = GoveeDeviceSim("H6199")
    sim.handle_write(proto.build_video_mode(sound_effects=True, sound_effects_softness=50))
    assert sim.video_sound_effects is True
    assert sim.video_sound_effects_softness == 50

    # The app always sends the full frame, so the mock applies sound and softness from every frame
    # rather than remembering a prior state; softness persists in the frame even with sound off.
    sim.handle_write(proto.build_video_mode(saturation=40, sound_effects=False, sound_effects_softness=50))
    assert sim.video_saturation == 40
    assert sim.video_sound_effects is False
    assert sim.video_sound_effects_softness == 50

    sim.handle_write(proto.build_video_mode(sound_effects=True, sound_effects_softness=80))
    assert sim.video_sound_effects is True
    assert sim.video_sound_effects_softness == 80


def test_video_white_balance_gated():
    h6199 = GoveeDeviceSim("H6199")
    h6199.handle_write(proto.build_video_white_balance(0x0F, 0x04))
    assert h6199.video_white_balance == (0x0F, 0x04)
    h617a = GoveeDeviceSim("H617A")
    h617a.handle_write(proto.build_video_white_balance(0x0F, 0x04))
    assert h617a.video_white_balance is None


def test_display_settings_are_told_apart_by_their_selector():
    """Both settings share the 33 a9 register, so a mock reading every frame the same way lies.

    Taking the gain pair off a blank-screen frame records a white balance nothing asked for, and
    it reads as a device that answered rather than as an error.
    """
    sim = GoveeDeviceSim("H6199")
    sim.handle_write(proto.build_blank_screen(True))
    assert sim.blank_screen is True
    assert sim.video_white_balance is None

    sim.handle_write(proto.build_video_white_balance(21, 5))
    assert sim.video_white_balance == (21, 5)
    assert sim.blank_screen is True

    sim.handle_write(proto.build_blank_screen(False))
    assert sim.blank_screen is False
    assert sim.video_white_balance == (21, 5)


def test_relative_brightness_records_every_edge():
    sim = GoveeDeviceSim("H6199")
    sim.handle_write(proto.build_relative_brightness(36))
    assert sim.relative_brightness == [36, 36, 36, 36]
    h617a = GoveeDeviceSim("H617A")
    h617a.handle_write(proto.build_relative_brightness(36))
    assert h617a.relative_brightness is None


def test_segment_writes_address_individual_slots():
    sim = GoveeDeviceSim("H617A")
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
    coord.rgb_color = (1, 2, 3)
    await coord._ensure_connected()
    assert coord.is_on is True
    assert coord.brightness_pct == 42
    # Colour is write-only unless the model echoes it, so a connect cannot discover an
    # externally set colour; it stays at whatever the integration last wrote.
    expected_rgb = (10, 20, 30) if coord.profile.static_readback_echoes_color else (1, 2, 3)
    assert coord.rgb_color == expected_rgb
    assert coord.color_temp_kelvin is None
    assert coord.effect is None


async def test_refresh_state_converges_effect(mock_ble: MockBle):
    sim, coord = mock_ble.sim, mock_ble.coordinator
    coord.effect_families = frozenset({"scenes"})
    sim.handle_write(proto.build_scene(SCENES["candlelight"].code))
    coord.effect = None
    assert await coord.refresh_state(expected_effect="candlelight") is True
    assert coord.effect == "candlelight"


async def test_refresh_state_converges_music_mode(mock_ble: MockBle):
    sim, coord = mock_ble.sim, mock_ble.coordinator
    sim.handle_write(proto.build_music_mode_with_color(MUSIC_MODES["rhythm"], sensitivity=50))
    coord.music_mode = "off"
    assert await coord.refresh_state() is True
    assert coord.music_mode == "rhythm"
    assert coord.effect is None


async def test_music_effect_confirms_via_music_mode(mock_ble: MockBle, monkeypatch):
    """End to end (un-mocked): the readback lands in music_mode, so the confirm converges."""
    coord = mock_ble.coordinator
    coord.effect_families = frozenset({"music"})
    light = GoveeBLELight(coord)
    notified = MagicMock()
    monkeypatch.setattr(light, "async_write_ha_state", notified)
    await light.async_turn_on(effect="Music: Spectrum")
    assert coord.music_mode == "spectrum"
    assert coord.is_on is True
    assert coord.effect is None
    assert coord.music_sensitivity == 99
    notified.assert_called_once()


async def test_video_effect_confirms_via_video_mode(mock_ble_h6199: MockBle, monkeypatch):
    """End to end (un-mocked): the H6199 readback lands in video_mode and the confirm converges."""
    coord = mock_ble_h6199.coordinator
    light = GoveeBLELight(coord)
    notified = MagicMock()
    monkeypatch.setattr(light, "async_write_ha_state", notified)
    coord.video_saturation = 60
    await light.async_turn_on(effect="Video: Game")
    assert coord.video_mode == "game"
    assert coord.is_on is True
    assert coord.effect is None
    assert coord.video_saturation == 60
    assert notified.call_count >= 1


async def test_update_data_queries_reach_sim(mock_ble: MockBle):
    sim, coord = mock_ble.sim, mock_ble.coordinator
    sim.is_on = True
    sim.brightness_pct = 77
    await coord._async_update_data()
    assert coord.is_on is True
    assert coord.brightness_pct == 77
