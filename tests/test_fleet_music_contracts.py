"""Exact-SKU music contract regressions; wire tests do not qualify playback."""

import pytest

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode, parse_color_mode
from custom_components.ha_govee_led_ble.generated_protocol_adapter import parse_status_result
from custom_components.ha_govee_led_ble.music_commands import prepare_music_profile_writes
from custom_components.ha_govee_led_ble.music_protocol import music_codebook
from custom_components.ha_govee_led_ble.music_semantics import music_variant
from custom_components.ha_govee_led_ble.transport import fragment_a3, xor_checksum
from tests.coordinator_test_support import frame

PALETTE = "07ff0000ff7f00ffff0000ff000000ff00ffff8b00ff"

H1A42_CONTRACT = (
    ("energetic", 0x05, None),
    ("rhythm", 0x03, None),
    ("spectrum", 0x04, None),
    ("rolling", 0x06, None),
    ("separation", 0x32, "3207" + "ff0000ff7f00ffff0000ff000000ff00ffff8b00ff" + "030061"),
    ("hopping", 0x33, "33" + PALETTE + "010101196201030205"),
    ("piano_keys", 0x07, "07" + PALETTE + "00090a0304"),
    ("fountain", 0x35, "35" + PALETTE + "01010350"),
    ("day_and_night", 0x37, "37" + PALETTE + "060a00"),
    ("bloom", 0x30, "30" + PALETTE + "0a50"),
    ("shiny", 0x31, "31" + PALETTE + "05640a"),
    ("splash", 0x84, "84" + PALETTE),
    ("orbit", 0xA3, "a3" + PALETTE),
    ("ripple", 0x92, "92" + PALETTE),
    ("spring", 0x85, "85" + PALETTE),
    ("meteor", 0x51, "51" + PALETTE),
)


@pytest.mark.parametrize(("mode", "code", "body"), H1A42_CONTRACT)
def test_h1a42_exact_music_roster_selector_and_body(mode: str, code: int, body: str | None) -> None:
    profile = MODEL_PROFILES["H1A42"]
    assert profile.music_modes == tuple(entry[0] for entry in H1A42_CONTRACT)
    assert music_codebook(profile)[mode] == code

    writes = prepare_music_profile_writes("H1A42", mode, 42, None, False, {}, profile=profile)
    expected_selector = bytes.fromhex(f"330513{code:02x}2a").ljust(19, b"\x00")
    assert writes.writes[-1][0] == expected_selector + bytes((xor_checksum(expected_selector),))

    uploads = tuple(packet for packet, _state in writes.writes if packet[0] == 0xA3)
    if body is None:
        assert writes.body is None and not uploads
    else:
        expected_body = bytes.fromhex(body)
        assert writes.body == (mode, expected_body)
        assert uploads == tuple(fragment_a3(0x41, expected_body))


@pytest.mark.parametrize(("mode", "code", "_body"), H1A42_CONTRACT)
def test_h1a42_exact_music_readback(mode: str, code: int, _body: str | None) -> None:
    result = parse_status_result(frame(f"aa0513{code:02x}2a"), "H1A42", profile=MODEL_PROFILES["H1A42"])
    parsed = parse_color_mode(result.parsed, "H1A42", profile=MODEL_PROFILES["H1A42"])

    assert result.rejection is None
    assert parsed.mode is ParsedMode.MUSIC
    assert parsed.music_mode == mode and parsed.music_sensitivity == 42


@pytest.mark.parametrize(
    ("model", "physical_ic_count", "expected"),
    [
        (
            "H617E",
            30,
            {
                0x32: "3205ff7f00ff0000ffff000000ff00ff00010162",
                0x33: "3307ff0000ff7f00ffff0000ff000000ff00ffff8b00ffff000032620103040c",
                0x34: "3407ff0000ff7f00ffff0000ff000000ff00ffff8b00ff000f230107",
                0x35: "3507ff0000ff7f00ffff0000ff000000ff00ffff8b00ff00030555",
                0x37: "3707ff0000ff7f00ffff0000ff000000ff00ffff8b00ff051400",
            },
        ),
        (
            "H617F",
            45,
            {
                0x32: "3205ff7f00ff0000ffff000000ff00ff00010162",
                0x33: "3307ff0000ff7f00ffff0000ff000000ff00ffff8b00ffff0000326201030612",
                0x34: "3407ff0000ff7f00ffff0000ff000000ff00ffff8b00ff000f230107",
                0x35: "3507ff0000ff7f00ffff0000ff000000ff00ffff8b00ff00030855",
                0x37: "3707ff0000ff7f00ffff0000ff000000ff00ffff8b00ff071400",
            },
        ),
    ],
)
def test_h617_music_geometry_owns_exact_ic_bodies(model: str, physical_ic_count: int, expected: dict[int, str]) -> None:
    profile = MODEL_PROFILES[model]
    assert profile.physical_ic_count == physical_ic_count

    for code, body_hex in expected.items():
        mode = next(slug for slug, candidate in music_codebook(profile).items() if candidate == code)
        variant = music_variant(profile, code)
        assert variant is not None and variant.requires_physical_ic_count
        writes = prepare_music_profile_writes(model, mode, 42, None, False, {}, profile=profile)
        uploads = tuple(packet for packet, _state in writes.writes if packet[0] == 0xA3)
        expected_body = bytes.fromhex(body_hex)
        assert writes.body == (mode, expected_body)
        assert uploads == tuple(fragment_a3(0x41, expected_body))
        selector_index = -1 if profile.music_upload_before_selector else 1
        assert writes.writes[selector_index][0][3] == code
