"""The 0xa9 registers behind the removable camera module, and the H66A0's segment layout.

The camera carries this hardware's WiFi radio and is removable, so "does this device have a
camera" is a runtime question rather than a model one. These pin how that determination is
made, and the calibration bright line that makes the surface safe to expose.
"""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_govee_led_ble.const import CONF_MODEL, DOMAIN, MODEL_PROFILES
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_black_border_removal,
    build_camera_install_query,
    build_power,
    build_video_setting_query,
)
from custom_components.ha_govee_led_ble.light_commands import ALL_SEGMENTS_MASK, build_color_rgb, build_segment_color
from custom_components.ha_govee_led_ble.video_settings import (
    CALIBRATION_READ_ALLOWLIST,
    CALIBRATION_WRITE_FORBIDDEN,
    VIDEO_SETTING_READS,
)
from tests.govee_device_double import FakeGoveeClient, GoveeDeviceDouble
from tests.test_govee_encryption import make_resolver, patch_connection

TEST_CONFIGURATION_URL = "homeassistant://ha-govee-led-ble/editor/test-entry"


def _coordinator(hass) -> GoveeBLECoordinator:
    coordinator = GoveeBLECoordinator(
        hass,
        "AA:BB:CC:DD:EE:FF",
        "H66A0",
        configuration_url=TEST_CONFIGURATION_URL,
        device_resolver=make_resolver(),
    )
    # Identity updates are scoped to a config entry, so a coordinator built outside one cannot
    # record a firmware version.  Attach an entry rather than avoid the path.
    entry = MockConfigEntry(domain=DOMAIN, unique_id=coordinator.address, data={CONF_MODEL: coordinator.model})
    entry.add_to_hass(hass)
    coordinator.config_entry = entry
    return coordinator


CAMERA_INSTALL_REPLY = bytes.fromhex("aa32010100000000000000000000000000000098")
BLACK_BORDER_REPLY = bytes.fromhex("aaa90b0101000000000000000000000000000008")
AI_FILTER_REPLY = bytes.fromhex("aaa9100f0000000000000000000000000000001c")


def test_the_camera_queries_are_the_frames_the_device_answered():
    assert build_camera_install_query().hex() == "aa32000000000000000000000000000000000098"
    assert build_video_setting_query(0x0B).hex() == "aaa90b0000000000000000000000000000000008"


def test_no_calibration_register_is_ever_written():
    """05, 06, 0d, 12, 13 and 14 overwrite factory or user calibration, with no clean undo.

    This is the bright line and it does not move. It was widened to cover READS as well until
    2026-08-24; that was broader than its own justification, because a read cannot overwrite
    anything. The narrowing is deliberate and is recorded in INTEGRATION_NOTES_hippo.md 2h --
    it is not erosion, and the write half below is exactly as strict as it ever was.

    build_black_border_removal is the only 0xa9 write this integration builds at all, and
    0x0b is not a calibration register.
    """
    for setting in CALIBRATION_WRITE_FORBIDDEN:
        assert build_black_border_removal(True)[2] != setting
    assert build_black_border_removal(True)[2] == 0x0B
    assert build_black_border_removal(False)[2] == 0x0B


def test_a_calibration_register_is_read_only_from_the_allowlist():
    """Reads are allowed only where the protocol has an evidenced getter.

    The bar is the one that settled 0x11: a builder and a parser agreeing on field order, or
    a constructor distinguishing read from write. 0x06 and 0x13 clear it; 0x12 does not, and
    its absence here is the point of the test rather than an omission.
    """
    read_calibration = set(VIDEO_SETTING_READS) & CALIBRATION_WRITE_FORBIDDEN
    assert read_calibration <= set(CALIBRATION_READ_ALLOWLIST)
    assert read_calibration == {0x06, 0x13}
    assert 0x12 not in VIDEO_SETTING_READS
    # 0x05, 0x0d and 0x14 have no evidenced getter.
    assert not set(VIDEO_SETTING_READS) & {0x05, 0x0D, 0x14}


def test_a_camera_install_reply_is_decoded_as_a_camera(hass):
    coordinator = _coordinator(hass)
    assert coordinator.camera_installed is None
    coordinator._notify_callback(None, bytearray(CAMERA_INSTALL_REPLY))
    assert coordinator.camera_installed is True


def test_video_setting_replies_are_stored_raw_and_keyed_by_sub_command(hass):
    coordinator = _coordinator(hass)
    coordinator._notify_callback(None, bytearray(BLACK_BORDER_REPLY))
    coordinator._notify_callback(None, bytearray(AI_FILTER_REPLY))
    assert coordinator.video_settings[0x0B] == [1]
    # len 15, the longest observed: pins that the length byte is honoured rather than assumed.
    assert coordinator.video_settings[0x10] == [0] * 15
    assert coordinator.camera_installed is True


def test_the_h66a0_profile_claims_fourteen_writable_segments():
    profile = MODEL_PROFILES["H66A0"]
    assert (profile.segment_count, profile.supports_segment_writes) == (14, True)
    assert profile.supports_segments


@pytest.mark.parametrize(
    ("segments", "mask"),
    [
        ([1, 2, 3], 0x0007),
        ([11, 12, 13, 14], 0x3C00),
        ([5, 9], 0x0110),
        (list(range(1, 15)), 0x3FFF),
    ],
)
def test_segment_masks_address_the_segments_driven_on_hardware(segments, mask):
    """The masks in these frames were written to the device and read back with aa a5.

    Each landed on exactly the addressed segments and left the others alone, so this pins
    the encoding rather than restating build_segment_color's implementation.
    """
    frame = build_segment_color(segments, 0xFF, 0x00, 0x00, "H66A0")
    assert int.from_bytes(frame[12:14], "little") == mask


def test_a_whole_strip_write_still_uses_the_shared_fifteen_bit_mask():
    """0x7FFF on a 14-segment device: the surplus bits are ignored, verified on hardware.

    Worth pinning because the obvious "fix" -- narrowing the constant to the profile's
    segment count -- would change the frames every other model sends, to solve a problem
    the device does not have.
    """
    assert int.from_bytes(build_color_rgb(0, 0, 255, "H66A0")[12:14], "little") == ALL_SEGMENTS_MASK
    assert ALL_SEGMENTS_MASK == 0x7FFF


def test_painting_beyond_the_fourteenth_segment_is_refused(hass):
    coordinator = _coordinator(hass)
    assert len(coordinator.segment_colors) == 14


async def test_capability_queries_stay_out_of_the_state_and_keep_alive_paths(hass):
    """A detached camera must not be able to degrade light control.

    The camera carries this device's WiFi radio and is removable, so its registers going
    silent is a normal condition, not a fault. If those queries rode the state path, an
    unplugged accessory would look like an unresponsive light.
    """
    coordinator = _coordinator(hass)
    device = GoveeDeviceDouble("H66A0")
    client = FakeGoveeClient(device)
    with patch_connection(client):
        await coordinator._ensure_connected()
        client.frames.clear()
        await coordinator._send_state_queries()

    sent = {(frame[0], frame[1]) for frame in client.frames}
    assert (0xAA, 0x32) not in sent, "camera probe rode the state-query path"
    assert (0xAA, 0xA9) not in sent, "video-setting reads rode the state-query path"


async def test_a_device_that_never_answers_the_camera_probe_still_controls_the_light(hass):
    """The sim answers no 0xa9 register, which is exactly the detached-camera case."""
    coordinator = _coordinator(hass)
    device = GoveeDeviceDouble("H66A0")
    client = FakeGoveeClient(device)
    with patch_connection(client):
        await coordinator.send_command(build_power(True))

    assert coordinator.camera_installed is None
    assert coordinator.video_settings == {}
    assert device.is_on, "light control did not survive a silent camera"


def test_the_ic_probe_records_both_of_its_fields(hass):
    """`aa 40` answers `00 5a 0e`: 90 ICs and 14 segments.

    Both are surfaced in diagnostics, and only the second was being stored -- so a bug report
    from a live H66A0 carried `ic_count: null` beside a populated segment count. Found by
    reading a real diagnostics download, not by a test.
    """
    coordinator = _coordinator(hass)
    coordinator._notify_callback(None, bytearray(bytes.fromhex("aa40005a0e0000000000000000000000000000be")))

    assert coordinator.ic_count == 90
    assert coordinator.reported_segment_count == 14
    assert coordinator.segment_count == 14
