"""Unit tests for Govee H601C recessed downlight."""

from custom_components.ha_govee_led_ble.const import (
    BLE_DISCOVERABLE_MODELS,
    SupportQuality,
    get_profile,
    model_from_ble_name,
    protocol_model,
    resolve_model,
)
from custom_components.ha_govee_led_ble.coordinator_expectations import expectations_from_packet
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_brightness,
    build_power,
    build_segment_brightness,
)
from custom_components.ha_govee_led_ble.light_commands import (
    build_color_rgb,
    build_color_temp,
    parse_static_write,
)
from custom_components.ha_govee_led_ble.transport import xor_checksum


def test_h601c_profile():
    profile = get_profile("H601C")
    assert profile.name == "H601C Recessed Downlight"
    assert profile.support_quality is SupportQuality.EXPERIMENTAL
    assert profile.command_grammar == "H601C"
    assert profile.status_grammar is None
    assert profile.supports_rgb is True
    assert profile.supports_color_temperature is True
    assert (profile.min_color_temp_kelvin, profile.max_color_temp_kelvin) == (2700, 6500)
    assert not profile.supports_segments
    assert not profile.supports_scenes
    assert not profile.supports_music_mode
    assert not profile.supports_custom_effects
    assert profile.read_domains == frozenset()
    assert profile.setup_required_read_domains == frozenset()
    assert not profile.state_readable
    assert not profile.requires_notifications
    assert profile.whole_device_mask == 0x0001
    assert profile.connection_idle_timeout == 0.1
    assert resolve_model("H601C") == "H601C"
    assert protocol_model("H601C") == "H601C"


def test_h601c_ble_discovery():
    assert "H601C" in BLE_DISCOVERABLE_MODELS
    assert model_from_ble_name("ihoment_H601C_1234") == "H601C"
    assert model_from_ble_name("Govee_H601C_ABCD") == "H601C"
    assert model_from_ble_name("GVH_H601C_0011") == "H601C"
    assert model_from_ble_name("ihoment_H601C") == "H601C"


def test_h601c_power_commands():
    on_packet = build_power(True, "H601C")
    assert len(on_packet) == 20
    assert on_packet == bytes.fromhex("3301010000000000000000000000000000000033")
    assert xor_checksum(on_packet[:-1]) == on_packet[-1]
    assert expectations_from_packet(on_packet, "H601C") == {"is_on": True}

    off_packet = build_power(False, "H601C")
    assert len(off_packet) == 20
    assert off_packet == bytes.fromhex("3301000000000000000000000000000000000032")
    assert xor_checksum(off_packet[:-1]) == off_packet[-1]
    assert expectations_from_packet(off_packet, "H601C") == {"is_on": False}


def test_h601c_brightness_commands():
    for pct in (1, 20, 50, 100):
        packet = build_brightness(pct, "H601C")
        assert len(packet) == 20
        assert packet[0] == 0x33
        assert packet[1] == 0x04
        assert packet[2] == pct
        assert xor_checksum(packet[:-1]) == packet[-1]
        assert expectations_from_packet(packet, "H601C") == {"brightness_pct": pct}


def test_h601c_color_rgb_manual():
    # Dim purple (128, 0, 128)
    packet = build_color_rgb(128, 0, 128, "H601C")
    assert len(packet) == 20
    assert packet[:6] == bytes([0x33, 0x05, 0x0D, 128, 0, 128])
    assert packet[6:8] == bytes([0x00, 0x00])
    assert xor_checksum(packet[:-1]) == packet[-1]

    # Parse static write
    static = parse_static_write(packet, "H601C")
    assert static is not None
    assert static.rgb == (128, 0, 128)
    assert static.operation == 0x0D
    assert static.whole_strip

    # Expectations
    expectations = expectations_from_packet(packet, "H601C")
    assert expectations == {
        "color_mode": (ParsedMode.COLOUR, None),
        "rgb_color": (128, 0, 128),
    }


def test_h601c_colour_temperature():
    # Warm white 2700K
    packet = build_color_temp(2700, "H601C")
    assert len(packet) == 20
    assert packet[:8] == bytes([0x33, 0x05, 0x0D, 0xFF, 0xFF, 0xFF, 0x0A, 0x8C])
    assert xor_checksum(packet[:-1]) == packet[-1]

    # Parse static write
    static = parse_static_write(packet, "H601C")
    assert static is not None
    assert static.kelvin == 2700
    assert static.kelvin_companion_rgb is not None
    assert static.operation == 0x0D
    assert static.whole_strip

    # Expectations
    expectations = expectations_from_packet(packet, "H601C")
    assert expectations == {
        "color_mode": (ParsedMode.COLOUR, None),
        "color_temp_kelvin": 2700,
    }


def test_h601c_segment_brightness_fallback():
    pct = 40
    packet_brightness = build_brightness(pct, "H601C")
    packet_seg_brightness = build_segment_brightness(0x0001, pct, "H601C")
    assert packet_seg_brightness == packet_brightness


async def test_h601c_light_turn_on():
    from unittest.mock import AsyncMock, MagicMock

    from homeassistant.components.light import ColorMode

    from custom_components.ha_govee_led_ble.const import MODEL_PROFILES
    from custom_components.ha_govee_led_ble.light import GoveeBLELight
    from tests.conftest import _make_coord

    profile = MODEL_PROFILES["H601C"]
    coord = _make_coord(model="H601C", profile=profile, is_on=False)
    coord.send_command = AsyncMock()

    light = GoveeBLELight(coord)
    light.async_write_ha_state = MagicMock()

    assert light.supported_color_modes == {ColorMode.RGB, ColorMode.COLOR_TEMP}

    # Turn on with dim purple (128, 0, 128) at 20% brightness (51/255)
    await light.async_turn_on(rgb_color=(128, 0, 128), brightness=51)

    sent_packets = [call.args[0] for call in coord.send_command.await_args_list]
    assert len(sent_packets) == 3
    # 1. Power ON
    assert sent_packets[0] == build_power(True, "H601C")
    # 2. Brightness 20%
    assert sent_packets[1] == build_brightness(20, "H601C")
    # 3. Manual RGB purple
    assert sent_packets[2] == build_color_rgb(128, 0, 128, "H601C")


def test_h601c_speculative_kaitai_schema():
    import io
    import os
    import sys

    from kaitaistruct import KaitaiStream

    generated_dir = os.environ.get("KAITAI_GENERATED_DIR")
    if generated_dir and generated_dir not in sys.path:
        sys.path.insert(0, generated_dir)

    try:
        from importlib import import_module
        from typing import Any

        h601c_mod = import_module("h601c_command_write")
        schema_cls: Any = h601c_mod.H601cCommandWrite
    except ImportError, ModuleNotFoundError:
        return

    def _parse(data: bytes) -> Any:
        stream = KaitaiStream(io.BytesIO(data))
        parsed = schema_cls(stream)
        parsed._read()
        return parsed

    # Power ON packet
    pkt = build_power(True, "H601C")
    parsed = _parse(pkt)
    assert parsed.opcode == schema_cls.CommandOp.power
    assert parsed.body.is_on == 1

    # Brightness packet
    pkt = build_brightness(25, "H601C")
    parsed = _parse(pkt)
    assert parsed.opcode == schema_cls.CommandOp.brightness
    assert parsed.body.percent == 25

    # Manual RGB
    pkt = build_color_rgb(128, 0, 128, "H601C")
    parsed = _parse(pkt)
    assert parsed.opcode == schema_cls.CommandOp.colour
    assert parsed.body.mode == schema_cls.ColourMode.colour_or_cct
    assert (parsed.body.detail.rgb.red, parsed.body.detail.rgb.green, parsed.body.detail.rgb.blue) == (128, 0, 128)

    # Tunable white CCT
    pkt = build_color_temp(3000, "H601C")
    parsed = _parse(pkt)
    assert parsed.opcode == schema_cls.CommandOp.colour
    assert parsed.body.mode == schema_cls.ColourMode.colour_or_cct
    assert parsed.body.detail.kelvin == 3000
