from dataclasses import replace
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_music_mode,
    build_power,
    parse_h6179_status,
)
from custom_components.ha_govee_led_ble.music_protocol import music_slug_for
from custom_components.ha_govee_led_ble.scenes import scene_key_for_code
from custom_components.ha_govee_led_ble.transport import xor_checksum

H6179_MUSIC_FRAMES = (
    ("mode_0", 0, None, "33050e0000000000000000000000000000000038"),
    ("mode_0", 0, (0x12, 0x34, 0x56), "33050e0000011234560000000000000000000049"),
    ("mode_0", 50, None, "33050e003200000000000000000000000000000a"),
    ("mode_0", 50, (0x12, 0x34, 0x56), "33050e003201123456000000000000000000007b"),
    ("mode_0", 99, None, "33050e006300000000000000000000000000005b"),
    ("mode_0", 99, (0x12, 0x34, 0x56), "33050e006301123456000000000000000000002a"),
    ("mode_1", 0, None, "33050e0100000000000000000000000000000039"),
    ("mode_1", 0, (0x12, 0x34, 0x56), "33050e0100011234560000000000000000000048"),
    ("mode_1", 50, None, "33050e013200000000000000000000000000000b"),
    ("mode_1", 50, (0x12, 0x34, 0x56), "33050e013201123456000000000000000000007a"),
    ("mode_1", 99, None, "33050e016300000000000000000000000000005a"),
    ("mode_1", 99, (0x12, 0x34, 0x56), "33050e016301123456000000000000000000002b"),
)


def _status(domain: int, body: bytes) -> bytes:
    packet = bytearray((0xAA, domain))
    packet.extend(body)
    packet.extend(bytes(19 - len(packet)))
    packet.append(xor_checksum(packet))
    return bytes(packet)


def _sent(send: AsyncMock) -> list[bytes]:
    return [call.args[0] for call in send.await_args_list]


@pytest.fixture
def h6179(hass) -> GoveeBLECoordinator:
    coordinator = GoveeBLECoordinator(
        hass,
        "AA:BB:CC:DD:EE:79",
        "H6179",
        configuration_url="homeassistant://ha-govee-led-ble/editor/test-entry",
    )
    coordinator.profile = replace(
        coordinator.profile,
        music_modes=("mode_0", "mode_1"),
        music_sensitivity_min=0,
        music_sensitivity_max=99,
        supports_music_color=True,
    )
    coordinator.is_on = True
    return coordinator


@pytest.mark.parametrize(("slug", "sensitivity", "colour", "frame"), H6179_MUSIC_FRAMES)
async def test_h6179_music_modes_emit_exact_primary_frame_without_inherited_writes(
    h6179: GoveeBLECoordinator,
    slug: str,
    sensitivity: int,
    colour: tuple[int, int, int] | None,
    frame: str,
) -> None:
    h6179.music_sensitivity = sensitivity
    h6179.music_color = colour
    h6179.music_calm = True

    with patch.object(h6179, "send_command", new_callable=AsyncMock) as send:
        await h6179.async_select_music_slug(slug)

    assert _sent(send) == [
        build_power(True, "H6179"),
        bytes.fromhex(frame),
    ]
    assert bytes.fromhex(frame) == build_music_mode(
        0 if slug == "mode_0" else 1,
        sensitivity,
        colour,
        False,
        "H6179",
    )


async def test_h6179_music_profile_ignores_h617a_parameters(h6179: GoveeBLECoordinator) -> None:
    original = (
        h6179.music_separation_point,
        h6179.music_separation_gradient,
        h6179.music_hopping_brightness,
        h6179.music_piano_key_count,
        h6179.music_fountain_direction,
        h6179.music_daynight_segments,
        h6179.music_daynight_speed,
        h6179.music_daynight_gradient,
    )
    h6179.install_music_profile_state(
        mode="mode_1",
        sensitivity=50,
        colour=(1, 2, 3),
        calm=True,
        parameters={
            "point": 5,
            "gradient": False,
            "relative_brightness": 1,
            "key_count": 8,
            "direction": "two_way",
            "segment_count": 7,
            "speed": 50,
        },
    )

    with patch.object(h6179, "send_command", new_callable=AsyncMock) as send:
        await h6179.async_apply_music_params(0x01)

    assert send.await_count == 0
    assert original == (
        h6179.music_separation_point,
        h6179.music_separation_gradient,
        h6179.music_hopping_brightness,
        h6179.music_piano_key_count,
        h6179.music_fountain_direction,
        h6179.music_daynight_segments,
        h6179.music_daynight_speed,
        h6179.music_daynight_gradient,
    )


def test_h6179_status_reverse_lookup_preserves_scene_ids_and_rejects_unknown_music_modes() -> None:
    known_scene = parse_h6179_status(_status(0x05, bytes.fromhex("040400")))
    unknown_scene = parse_h6179_status(_status(0x05, bytes.fromhex("043412")))
    known_music = parse_h6179_status(_status(0x05, bytes.fromhex("0e003200")))
    unknown_music = parse_h6179_status(_status(0x05, bytes.fromhex("0e7f3200")))

    assert known_scene is not None
    assert scene_key_for_code("H6179", int(known_scene.values["scene_code"])) == "movie"
    assert unknown_scene is not None
    assert unknown_scene.values["scene_code"] == 0x1234
    assert scene_key_for_code("H6179", int(unknown_scene.values["scene_code"])) is None
    assert known_music is not None
    assert known_music.values["music_mode_id"] == 0
    assert music_slug_for("H6179", int(known_music.values["music_mode_id"])) == "mode_0"
    assert unknown_music is None
