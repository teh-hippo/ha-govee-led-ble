"""Coordinator notification and outgoing-expectation tests."""

import asyncio
import logging
import time
from dataclasses import replace
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, MUSIC_MODE_SLUGS
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_expectations import expectations_from_packet
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode
from custom_components.ha_govee_led_ble.effect_deployments import PriorControlState
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_blank_screen_query,
    build_brightness,
    build_brightness_query,
    build_h617a_scene,
    build_music_mode,
    build_power,
    build_relative_brightness_query,
    build_segment_query,
    build_video_mode,
    build_white_balance,
    build_white_balance_query,
    parse_command_ack_result,
)
from custom_components.ha_govee_led_ble.light_commands import (
    build_color_rgb,
    build_color_temp,
    build_white_brightness,
)
from custom_components.ha_govee_led_ble.protocol_core import H6199StatusReply, StatusReply
from custom_components.ha_govee_led_ble.scenes import MODEL_SCENES, SCENES
from custom_components.ha_govee_led_ble.transport import xor_checksum
from tests.coordinator_test_support import _CONFIGURATION_URL, _c, _packet

M = "custom_components.ha_govee_led_ble.coordinator"
_MUSIC_SLUG_BY_ID = {code: slug for slug, code in MUSIC_MODE_SLUGS.items()}
_SCENE_EFFECT_BY_ID = {scene.code: name for name, scene in SCENES.items()}


@pytest.fixture
def h6179(hass):
    return GoveeBLECoordinator(
        hass,
        "55:66:77:88:99:AA",
        "H6179",
        configuration_url=_CONFIGURATION_URL,
    )


def test_h6179_notifications_update_power_brightness_and_diy_mode(h6179):
    h6179._notify_callback(None, bytearray(_packet(0xAA, 0x01, [1])))
    h6179._notify_callback(None, bytearray(_packet(0xAA, 0x04, [0x88])))
    h6179._notify_callback(None, bytearray(_packet(0xAA, 0x05, [0x0A, 0x34, 0x12])))

    assert h6179.is_on
    assert h6179.brightness_pct == 50
    assert h6179.color_mode is ParsedMode.DIY
    assert h6179.diy_code == 0x1234


@pytest.mark.parametrize("mode_id", (0, 1))
def test_h6179_automatic_music_clears_fixed_colour_and_restores_automatic_selection(h6179, mode_id):
    h6179._notify_callback(None, bytearray(_packet(0xAA, 0x01, [1])))
    h6179._notify_callback(None, bytearray(_packet(0xAA, 0x05, [0x0E, mode_id, 99, 1, 255, 0, 0])))
    assert h6179.music_color == (255, 0, 0)
    revision = h6179._field_revisions["music_color"]

    h6179._notify_callback(None, bytearray(_packet(0xAA, 0x05, [0x0E, mode_id, 99, 0, 255, 0, 0])))

    assert h6179.color_mode is ParsedMode.MUSIC
    assert h6179.music_mode == f"mode_{mode_id}" and h6179.music_sensitivity == 99
    assert h6179.music_color is None and h6179._field_revisions["music_color"] > revision
    snapshot = PriorControlState.from_dict(h6179.capture_effect_control_state().to_dict())
    assert snapshot.music_color is None
    prepared = h6179._prepare_music_restore(snapshot)
    assert prepared is not None
    assert prepared[1][-1][0] == build_music_mode(mode_id, 99, None, False, "H6179")


@pytest.mark.parametrize(
    ("offset", "value"),
    (
        pytest.param(3, 2, id="unknown-selector"),
        pytest.param(4, 100, id="invalid-sensitivity"),
        pytest.param(5, 2, id="invalid-colour-mode"),
        pytest.param(9, 1, id="nonzero-remaining-tail"),
        pytest.param(-1, 0, id="invalid-checksum"),
        pytest.param(20, 0, id="truncated"),
    ),
)
def test_h6179_rejected_music_does_not_change_observed_state(h6179, offset, value):
    h6179._notify_callback(None, bytearray(_packet(0xAA, 5, [0x0E, 1, 99, 1, 255, 0, 0])))
    state = h6179.capture_effect_control_state()
    revisions = dict(h6179._field_revisions)
    frame = bytearray(_packet(0xAA, 5, [0x0E, 0, 99, 0, 255, 0, 0]))
    if offset == 20:
        frame.pop()
    else:
        frame[offset] = value
        if offset != -1:
            frame[-1] = xor_checksum(frame[:-1])

    h6179._notify_callback(None, frame)

    assert h6179.capture_effect_control_state() == state
    assert h6179._field_revisions == revisions


def test_notify_callback(h6199):
    h6199.effect_families = frozenset({"scenes", "music", "video"})
    cb = h6199._notify_callback
    cb(None, bytearray(_packet(0xAA, 0x01, [0x01])))
    assert h6199.is_on is True
    cb(None, bytearray(_packet(0xAA, 0x01, [0x00])))
    assert h6199.is_on is False
    cb(None, bytearray(_packet(0xAA, 0x04, [0x4B])))
    assert h6199.brightness_pct == 75
    cb(None, bytearray(_packet(0xAA, 0x05, [0x00, 0x00, 0x01, 42])))
    assert (h6199.video_mode, h6199.video_full_screen, h6199.video_saturation) == ("game", False, 42)
    cb(None, bytearray(_packet(0xAA, 0x05, [0x13, 0x04, 66, 0x00, 0x01, 1, 2, 3])))
    assert (h6199.music_mode, h6199.music_sensitivity, h6199.music_calm, h6199.music_color) == (
        "spectrum",
        66,
        False,
        (1, 2, 3),
    )
    assert h6199.effect is None
    cb(None, bytearray(_packet(0xAA, 0xA9, [0x00, 0x06, 1, 16, 3, 1, 21, 5])))
    assert (h6199.white_balance_red, h6199.white_balance_blue) == (21, 5)
    cb(None, bytearray(_packet(0xAA, 0xA9, [0x0A, 0x06, 0, 2, 10, 0, 120, 0])))
    assert h6199.blank_screen is False
    assert h6199.blank_screen_detection == 2
    assert h6199.blank_screen_low_brightness_duration_seconds == 10
    assert h6199.blank_screen_same_tone_duration_seconds == 120
    cb(None, bytearray(_packet(0xAA, 0xAE, [1, 4, 51, 20, 31, 41])))
    assert (
        h6199.relative_brightness,
        h6199.relative_brightness_left,
        h6199.relative_brightness_top,
        h6199.relative_brightness_right,
        h6199.relative_brightness_bottom,
    ) == (None, 51, 20, 31, 41)
    cb(None, bytearray(_packet(0xAA, 0x05, [0x04, 0x09, 0x00])))
    assert h6199.effect == "candlelight"
    h6199.is_on = False
    cb(None, bytearray([0xAA]))
    cb(None, bytearray([0x33, 0x01, 0x01, 0x00]))
    assert h6199.is_on is False


def test_display_replies_reject_stale_composite_values_atomically(h6199):
    h6199.white_balance_red, h6199.white_balance_blue = 16, 3
    h6199._arm_expected_values({"white_balance_red": 21, "white_balance_blue": 5})
    h6199._notify_callback(None, bytearray(_packet(0xAA, 0xA9, [0x00, 0x06, 1, 16, 3, 1, 13, 3])))
    assert (h6199.white_balance_red, h6199.white_balance_blue) == (16, 3)

    h6199.blank_screen = True
    h6199._arm_expected_values({"blank_screen": True})
    h6199._notify_callback(None, bytearray(_packet(0xAA, 0xA9, [0x0A, 0x06, 0, 2, 10, 0, 120, 0])))
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
    h6199._notify_callback(None, bytearray(_packet(0xAA, 0xAE, [1, 4, 91, 91, 91, 91])))
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
    cb(None, bytearray(_packet(0xAA, 0x05, [0x04, 0x01, 0x00])))
    assert h6199.effect == "sunset"
    assert h6199.packet_log[-1]["outcome"] == "parsed"
    assert h6199.packet_log[-1]["reason"] == "status_parsed"
    assert h6199.packet_log[-1]["parser"] == "h6199_status_reply"
    assert h6199.packet_log[-1]["domain"] == "0x05"
    cb(None, bytearray(_packet(0xAA, 0x05, [0x04, 0x09])))
    assert h6199.effect == "candlelight"


def test_notify_callback_records_command_echoes_without_applying_status(coord, h6199):
    for coordinator, model, parser in (
        (coord, "H617A", "h617a_command_ack"),
        (h6199, "H6199", "h6199_command_write"),
    ):
        initial_state = coordinator.is_on
        frame = build_power(not initial_state, model)

        coordinator._notify_callback(None, bytearray(frame))

        assert coordinator.is_on is initial_state
        assert coordinator.packet_log[-1]["outcome"] == "parsed"
        assert coordinator.packet_log[-1]["reason"] == (
            "command_ack_parsed" if model == "H617A" else "command_echo_parsed"
        )
        assert coordinator.packet_log[-1]["parser"] == parser
        assert coordinator.packet_log[-1]["raw"] == frame.hex()


@pytest.mark.parametrize(
    "frame",
    [
        bytes.fromhex("3301000000000000000000000000000000000032"),
        bytes.fromhex("3305000000000000000000000000000000000036"),
        bytes.fromhex("33a900000000000000000000000000000000009a"),
        bytes.fromhex("33ae00000000000000000000000000000000009d"),
    ],
)
def test_notify_callback_records_h6199_generic_acknowledgements(h6199, frame: bytes):
    h6199._notify_callback(None, bytearray(frame))

    assert h6199.packet_log[-1]["outcome"] == "parsed"
    assert h6199.packet_log[-1]["reason"] == "command_ack_parsed"
    assert h6199.packet_log[-1]["parser"] == "h6199_command_ack"
    assert h6199.packet_log[-1]["raw"] == frame.hex()


def test_h6199_subordinate_versions_are_retained_without_querying_identity(h6199):
    h6199._notify_callback(None, bytearray(_packet(0xAA, 0x20, list(b"1.03.00"))))
    h6199._notify_callback(None, bytearray(_packet(0xAA, 0x21, list(b"1.00.33"))))

    assert h6199.subordinate_20_version == "1.03.00"
    assert h6199.subordinate_21_version == "1.00.33"


def test_video_grammar_owns_writers_and_ack_independently_of_basic_grammars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = "H7000"
    monkeypatch.setitem(
        MODEL_PROFILES,
        model,
        replace(
            MODEL_PROFILES["H6199"],
            name="Synthetic video device",
            command_grammar="H617A",
            status_grammar=None,
            read_domains=frozenset(),
            setup_required_read_domains=frozenset(),
        ),
    )

    assert build_video_mode("game", False, 42, True, 55, model) == bytes.fromhex(
        "33050000012a013700000000000000000000002b"
    )
    # White-balance reads require their own capability and use the command query grammar.
    with pytest.raises(ValueError, match="readback"):
        build_white_balance_query(model)
    queries = (build_blank_screen_query, build_relative_brightness_query)
    expected_queries = [build("H6199") for build in queries]
    # Video grammar keys must not be resolved through the H6199 model profile.
    monkeypatch.setitem(
        MODEL_PROFILES,
        "H6199",
        replace(
            MODEL_PROFILES["H6199"],
            command_grammar=None,
            status_grammar="unknown",
            read_domains=frozenset(),
            setup_required_read_domains=frozenset(),
        ),
    )
    assert [build(model) for build in queries] == expected_queries
    ack = parse_command_ack_result(bytes.fromhex("33a900000000000000000000000000000000009a"), model)
    assert ack.parser == "h6199_command_ack" and ack.rejection is None
    assert ack.parsed is not None and ack.parsed.opcode.name == "display_setting"


@pytest.mark.parametrize(("command_grammar", "status_grammar"), [("H617A", "H6199"), ("H6199", "H617A")])
def test_mixed_grammars_route_command_expectations_and_status_semantics(
    hass, monkeypatch, command_grammar, status_grammar
):
    model = "H7000"
    monkeypatch.setitem(
        MODEL_PROFILES,
        model,
        replace(
            MODEL_PROFILES[status_grammar],
            name="Synthetic mixed-grammar device",
            command_grammar=command_grammar,
            status_grammar=status_grammar,
        ),
    )
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", model, configuration_url=_CONFIGURATION_URL)
    brightness = build_brightness(37, model)
    assert brightness == build_brightness(37, command_grammar)
    assert expectations_from_packet(brightness, model) == {"brightness_pct": 37}
    for build, args, field, expected in (
        (build_color_rgb, (10, 20, 30), "rgb_color", (10, 20, 30)),
        (build_color_temp, (4000,), "color_temp_kelvin", 4000),
        (build_white_brightness, (80,), "white_brightness", 80),
    ):
        packet = build(*args, model=model)
        assert packet == build(*args, model=command_grammar)
        expectations = expectations_from_packet(packet, model, static_echoes_color=True)
        assert expectations[field] == expected
        assert expectations["color_mode"] == (ParsedMode.COLOUR, 2 if field == "white_brightness" else 1)

    music = build_music_mode(MUSIC_MODE_SLUGS["rhythm"], 50, (10, 20, 30), True, model)
    assert music == build_music_mode(MUSIC_MODE_SLUGS["rhythm"], 50, (10, 20, 30), True, command_grammar)
    assert expectations_from_packet(music, model) == {
        "color_mode": (ParsedMode.MUSIC, None),
        "music_mode": "rhythm",
        "music_sensitivity": 50,
        "music_calm": True,
        "music_color": (10, 20, 30),
    }

    # Group 5 distinguishes outbound query grammars even with the opposite reply layout.
    assert build_brightness_query(model) == build_brightness_query(command_grammar)
    if command_grammar == "H617A":
        assert build_segment_query(5, model) == build_segment_query(5, "H617A")
    else:
        assert build_segment_query(4, model) == build_segment_query(4, "H6199")
        with pytest.raises(ValueError, match="selected grammar"):
            build_segment_query(5, model)

    coordinator._notify_callback(None, bytearray(_packet(0xAA, 0x04, [37])))
    assert coordinator.brightness_pct == 37
    assert coordinator._field_revisions["brightness_pct"] == 1
    music_reply = {
        "H617A": "aa051303580100000000000000000000000000e6",
        "H6199": "aa0513044d0001010203000000000000000000f4",
    }[status_grammar]
    coordinator._notify_callback(None, bytearray.fromhex(music_reply))
    assert coordinator.color_mode is ParsedMode.MUSIC
    assert coordinator.music_mode == ("rhythm" if status_grammar == "H617A" else "spectrum")
    assert coordinator.music_sensitivity == (88 if status_grammar == "H617A" else 77)
    assert coordinator.music_color == (None if status_grammar == "H617A" else (1, 2, 3))
    assert coordinator._field_revisions["color_mode"] == 1


async def test_send_command_sets_expected_brightness(coord):
    c = _c(write_gatt_char=AsyncMock())
    with patch.object(coord, "_ensure_connected", return_value=c):
        assert "brightness_pct" not in coord._expected_state
        await coord.send_command(build_brightness(42))
        assert coord._expected_state["brightness_pct"][0] == 42


def test_notify_callback_brightness_expectation(h6199):
    cb = h6199._notify_callback
    h6199.brightness_pct = 99
    h6199._expected_state["brightness_pct"] = (10, time.monotonic() + 60)
    cb(None, bytearray(_packet(0xAA, 0x04, [0x4B])))
    assert h6199.brightness_pct == 99  # ignored

    h6199._expected_state["brightness_pct"] = (75, time.monotonic() + 60)
    cb(None, bytearray(_packet(0xAA, 0x04, [0x4B])))
    assert h6199.brightness_pct == 75 and "brightness_pct" in h6199._expected_state

    with patch(f"{M}.time.monotonic", return_value=1000):
        h6199._expected_state["brightness_pct"] = (10, 0)
        cb(None, bytearray(_packet(0xAA, 0x04, [0x01])))
        assert h6199.brightness_pct == 1 and "brightness_pct" not in h6199._expected_state


def test_notify_callback_power_expectation(h6199):
    cb = h6199._notify_callback
    h6199.is_on = True
    h6199._expected_state["is_on"] = (True, time.monotonic() + 60)
    field_revision = h6199._field_revisions.get("is_on", 0)

    cb(None, bytearray(_packet(0xAA, 0x01, [0x00])))
    assert h6199.is_on is True
    assert h6199._field_revisions.get("is_on", 0) == field_revision
    assert "is_on" in h6199._expected_state

    cb(None, bytearray(_packet(0xAA, 0x01, [0x01])))
    assert h6199.is_on is True
    assert h6199._field_revisions["is_on"] == field_revision + 1
    assert "is_on" in h6199._expected_state


def test_notify_callback_static_readback_keeps_color_temp(h6199):
    """A static reply carries no colour, so it cannot replace an optimistic colour temperature."""
    cb = h6199._notify_callback
    reply = bytearray(_packet(0xAA, 0x05, [0x15, 0x01, 10, 20, 30]))

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
    cb(None, bytearray(_packet(0xAA, 0x05, [0x15, 0x01, 10, 20, 30])))
    assert h6199.effect == "candy"
    assert "effect" in h6199._expected_state


def test_notify_callback_music_auto_color_clears_manual_color(h6199):
    h6199.music_color = (1, 2, 3)
    revision = h6199._field_revisions.get("music_color", 0)

    h6199._notify_callback(
        None,
        bytearray(_packet(0xAA, 0x05, [0x13, 0x04, 66, 0x00, 0x00])),
    )

    assert h6199.music_color is None
    assert h6199._field_revisions["music_color"] == revision + 1


def test_readback_mode_mutual_exclusion(h6199):
    """Each parsed readback mode leaves exactly one mode truthful, clearing any stale others."""
    h6199.effect_families = frozenset({"scenes", "music", "video"})
    cb = h6199._notify_callback
    music = bytearray(_packet(0xAA, 0x05, [0x13, 0x04, 66, 0x00, 0x01, 1, 2, 3]))
    video = bytearray(_packet(0xAA, 0x05, [0x00, 0x00, 0x01, 42]))
    scene = bytearray(_packet(0xAA, 0x05, [0x04, 0x09, 0x00]))

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
        bytearray(_packet(0xAA, 0x05, [int(StatusReply.ColorMode.diy), 0x84, 0x03])),
    )

    assert coord.color_mode is ParsedMode.DIY
    assert coord.active_mode == "custom"
    assert coord.diy_code == 900
    assert all(coord._field_revisions[field] > baseline for field, baseline in baselines.items())


async def test_diy_command_expectation_rejects_truncated_readback(coord):
    command = _packet(0x33, 0x05, [int(StatusReply.ColorMode.diy), 0x20, 0x03])
    client = _c(write_gatt_char=AsyncMock())
    with patch.object(coord, "_ensure_connected", return_value=client):
        await coord.send_command(command)

    assert coord._expected_state["color_mode"][0] == (ParsedMode.DIY, 800)

    coord._notify_callback(
        None,
        bytearray(_packet(0xAA, 0x05, [int(StatusReply.ColorMode.diy), 0x20, 0x00])),
    )
    assert coord.color_mode is None
    assert coord.diy_code is None

    coord._notify_callback(
        None,
        bytearray(_packet(0xAA, 0x05, [int(StatusReply.ColorMode.diy), 0x20, 0x03])),
    )
    assert coord.color_mode is ParsedMode.DIY
    assert coord.diy_code == 800


async def test_send_command_arms_expected_state(coord, h6199):
    c = _c(write_gatt_char=AsyncMock())
    with patch.object(coord, "_ensure_connected", return_value=c):
        await coord.send_command(build_power(True))
        assert coord._expected_state["is_on"][0] is True

        await coord.send_command(build_color_temp(4000))
        assert coord._expected_state["color_temp_kelvin"][0] == 4000

        await coord.send_command(build_color_rgb(10, 20, 30))
        assert coord._expected_state["rgb_color"][0] == (10, 20, 30)
        assert "color_temp_kelvin" not in coord._expected_state

        mode_id = next(iter(_MUSIC_SLUG_BY_ID))
        await coord.send_command(build_music_mode(mode_id, 99, None, False))
        assert coord._expected_state["music_mode"][0] == _MUSIC_SLUG_BY_ID[mode_id]
        assert "rgb_color" not in coord._expected_state

    with patch.object(h6199, "_ensure_connected", return_value=c):
        await h6199.send_command(build_video_mode("game", False, 60, False, 100, "H6199"))
        assert h6199._expected_state["video_mode"][0] == "game"
        assert h6199._expected_state["video_full_screen"][0] is False
        assert h6199._expected_state["video_saturation"][0] == 60
        # The frame is always full, so sound and softness are armed even when sound is off.
        assert h6199._expected_state["video_sound_effects"][0] is False
        assert h6199._expected_state["video_sound_effects_softness"][0] == 100

    with patch.object(coord, "_ensure_connected", return_value=c):
        await coord.send_command(build_color_rgb(10, 20, 30))
        assert coord._expected_state["color_mode"][0] == (ParsedMode.COLOUR, None)
        assert coord._expected_state["rgb_color"][0] == (10, 20, 30)

        await coord.send_command(build_h617a_scene(9))
        assert coord._expected_state["color_mode"][0] == (ParsedMode.SCENE, None)
        assert coord._expected_state["effect"][0] == _SCENE_EFFECT_BY_ID[9]


def test_music_expectation_rejects_delayed_same_mode_reply(h6199):
    h6199._expected_state["color_mode"] = ((ParsedMode.MUSIC, None), time.monotonic() + 60)
    h6199._expected_state["music_mode"] = ("rhythm", time.monotonic() + 60)
    cb = h6199._notify_callback

    cb(None, bytearray(_packet(0xAA, 0x05, [0x13, 0x03, 66, 0x00, 0x01, 1, 2, 3])))
    cb(None, bytearray(_packet(0xAA, 0x05, [0x13, 0x04, 66, 0x00, 0x01, 1, 2, 3])))

    assert h6199.music_mode == "rhythm"
    assert h6199.color_mode is ParsedMode.MUSIC


def test_scene_expectation_rejects_delayed_same_mode_reply(h6199):
    h6199.effect_families = frozenset({"scenes"})
    sunrise_code = next(code for code, effect in _SCENE_EFFECT_BY_ID.items() if effect == "sunrise")
    candlelight_code = next(code for code, effect in _SCENE_EFFECT_BY_ID.items() if effect == "candlelight")
    h6199._expected_state["color_mode"] = ((ParsedMode.SCENE, None), time.monotonic() + 60)
    h6199._expected_state["effect"] = ("sunrise", time.monotonic() + 60)
    cb = h6199._notify_callback

    cb(None, bytearray(_packet(0xAA, 0x05, [0x04, *sunrise_code.to_bytes(2, "little")])))
    cb(None, bytearray(_packet(0xAA, 0x05, [0x04, *candlelight_code.to_bytes(2, "little")])))

    assert h6199.effect == "sunrise"
    assert h6199.color_mode is ParsedMode.SCENE


def test_unknown_mode_clears_restored_metadata(h6199):
    h6199.effect = "Flame"
    h6199.diy_code = 0xF0
    h6199.music_mode, h6199.video_mode = "rhythm", "movie"

    h6199._notify_callback(None, bytearray(_packet(0xAA, 0x05, [0x99, 0x01])))

    assert h6199.color_mode is ParsedMode.UNKNOWN
    assert h6199.effect is None
    assert h6199.diy_code is None
    assert (h6199.music_mode, h6199.video_mode) == ("off", "off")


@pytest.mark.parametrize("elapsed", [1.9, 2.0, 2.1])
async def test_expectation_expiry_uses_notification_clock(coord, virtual_clock, elapsed):
    coord.brightness_pct = 42
    coord._arm_expected_values({"brightness_pct": 42})
    baseline = coord._field_revisions.get("brightness_pct", 0)
    await asyncio.sleep(elapsed)
    coord._notify_callback(None, bytearray(_packet(0xAA, 0x04, [75])))
    assert coord.brightness_pct == (42 if elapsed < 2 else 75)
    assert (coord._field_revisions.get("brightness_pct", 0) > baseline) is (elapsed >= 2)


def test_notify_callback_rejected_frame_is_retained_without_address(h6199, caplog):
    revision = h6199._domain_revisions.get(0x99, 0)
    frame = bytearray([0xAA, 0x99, 0x01, 0x00])
    with caplog.at_level(logging.DEBUG, logger="custom_components.ha_govee_led_ble.coordinator"):
        h6199._notify_callback(None, frame)

    assert h6199._domain_revisions.get(0x99, 0) == revision
    assert h6199.packet_log[-1]["outcome"] == "rejected"
    assert h6199.packet_log[-1]["reason"] == "invalid_length"
    assert h6199.packet_log[-1]["domain"] == "0x99"
    assert h6199.packet_log[-1]["raw"] == bytes(frame).hex()
    assert "H6199" in caplog.text
    assert "invalid_length" in caplog.text
    assert h6199.address not in caplog.text


def test_expectations_from_packet_covers_every_command_family():
    rhythm_id = next(mid for mid, slug in _MUSIC_SLUG_BY_ID.items() if slug == "rhythm")
    spectrum_id = next(mid for mid, slug in _MUSIC_SLUG_BY_ID.items() if slug == "spectrum")
    scene_code = next(iter(_SCENE_EFFECT_BY_ID))

    assert expectations_from_packet(build_power(True)) == {"is_on": True}
    assert expectations_from_packet(build_power(False)) == {"is_on": False}
    assert expectations_from_packet(build_brightness(37)) == {"brightness_pct": 37}

    rgb = expectations_from_packet(build_color_rgb(255, 0, 0))
    assert rgb["rgb_color"] == (255, 0, 0)
    # The write-side sub is not echoed back, so expecting it would reject every reply. Models
    # that do echo it keep the discriminator.
    assert rgb["color_mode"] == (ParsedMode.COLOUR, None)
    echoed = expectations_from_packet(build_color_rgb(255, 0, 0), static_echoes_color=True)
    assert echoed["color_mode"] == (ParsedMode.COLOUR, 0x01)

    # Colour-temperature writes zero the direct RGB field, so they map to a Kelvin
    # expectation rather than an rgb_color one.
    ct = expectations_from_packet(build_color_temp(4000))
    assert ct["color_temp_kelvin"] == 4000
    assert "rgb_color" not in ct

    # A deliberate black paint is also all-zero, but it is a colour, not a 0 K temperature.
    # Splitting the two on "any RGB byte set" put this frame in the kelvin branch.
    black = expectations_from_packet(build_color_rgb(0, 0, 0))
    assert black["rgb_color"] == (0, 0, 0)
    assert "color_temp_kelvin" not in black

    assert expectations_from_packet(build_white_brightness(80))["white_brightness"] == 80

    assert expectations_from_packet(build_h617a_scene(scene_code))["effect"] == _SCENE_EFFECT_BY_ID[scene_code]

    diy = expectations_from_packet(_packet(0x33, 0x05, [int(StatusReply.ColorMode.diy), 0x20, 0x03]))
    assert diy["color_mode"] == (ParsedMode.DIY, 800)

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
        build_video_mode("game", False, 42, True, 55, "H6199"),
        "H6199",
    )
    assert video["video_mode"] == "game"
    assert video["video_full_screen"] is False
    assert video["video_saturation"] == 42
    assert video["video_sound_effects"] is True
    assert video["video_sound_effects_softness"] == 55

    assert expectations_from_packet(b"\x00\x01") == {}
    assert expectations_from_packet(_packet(0x33, 0x05, [0xEE])) == {}


def test_an_unnameable_scene_is_reported_rather_than_hidden(coord):
    """A scene we cannot name still means the light is running something.

    effect has to stay None, because Home Assistant rejects a value outside effect_list and
    we could not re-activate the scene anyway, so the raw id is the only honest signal left.
    """
    unknown = 401
    assert unknown not in _SCENE_EFFECT_BY_ID
    coord._notify_callback(
        None,
        bytearray(_packet(0xAA, 0x05, [int(StatusReply.ColorMode.scene), *unknown.to_bytes(2, "little")])),
    )
    assert coord.effect is None
    assert coord.unknown_scene_code == unknown

    # A scene we can name is reported by name, and leaves no stale code behind.
    known = next(iter(_SCENE_EFFECT_BY_ID))
    coord._notify_callback(
        None,
        bytearray(_packet(0xAA, 0x05, [int(StatusReply.ColorMode.scene), *known.to_bytes(2, "little")])),
    )
    assert coord.effect == _SCENE_EFFECT_BY_ID[known]
    assert coord.unknown_scene_code is None

    # Leaving scene mode drops it too, so it can never describe a light that is not in a scene.
    coord._notify_callback(
        None,
        bytearray(_packet(0xAA, 0x05, [int(StatusReply.ColorMode.scene), *unknown.to_bytes(2, "little")])),
    )
    assert coord.unknown_scene_code == unknown
    coord._notify_callback(None, bytearray(_packet(0xAA, 0x05, [int(StatusReply.ColorMode.static), 0x00])))
    assert coord.unknown_scene_code is None


def test_h6199_scene_codes_are_named_when_hidden_from_the_ha_effect_list(h6199):
    scene = MODEL_SCENES["H6199"]["forest"]
    h6199._notify_callback(
        None,
        bytearray(_packet(0xAA, 0x05, [int(StatusReply.ColorMode.scene), *scene.code.to_bytes(2, "little")])),
    )
    assert h6199.effect == "forest"
    assert h6199.unknown_scene_code is None


def test_video_readback_is_gated_on_the_model(coord, h6199):
    """The same mode byte is video only in the H6199 status grammar."""
    payload = [int(H6199StatusReply.ModeSel.video), 0x00, 0x01, 42, 0x01, 55]

    coord._notify_callback(None, bytearray(_packet(0xAA, 0x05, payload)))
    assert coord.color_mode is ParsedMode.UNKNOWN
    assert coord.video_mode == "off"

    h6199._notify_callback(None, bytearray(_packet(0xAA, 0x05, payload)))
    assert h6199.color_mode is ParsedMode.VIDEO
    assert h6199.video_mode == "game"
    assert h6199.video_saturation == 42


def test_white_balance_never_fabricates_an_unknown_gain(coord):
    assert coord.white_balance is None
    coord.white_balance_red = 21
    assert coord.white_balance is None
    coord.white_balance_blue = 5
    assert coord.white_balance == (21, 5)
    assert build_white_balance(*coord.white_balance, "H6199") == build_white_balance(21, 5, "H6199")
