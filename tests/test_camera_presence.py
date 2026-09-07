"""The camera module is plug-and-play, so its presence is a runtime determination.

The trap this is designed around: `aa 32`, the install check, is itself camera-gated. It
goes silent alongside everything it would report on, so it cannot be asked whether the
camera is there. The signal is not a reply -- it is the pattern, measured on hardware
2026-08-24 across five query shapes: every camera register silent while non-camera
registers answer on the same connection, 6/16 every time.
"""

import pytest

from custom_components.ha_govee_led_ble.coordinator import (
    CAMERA_ABSENT_STRIKES,
    GoveeBLECoordinator,
)
from custom_components.ha_govee_led_ble.coordinator_status import StatusDomain

_URL = "homeassistant://ha-govee-led-ble/editor/test-entry"

CAMERA_REPLY = bytes.fromhex("aa32010100000000000000000000000000000098")
REGISTER_REPLY = bytes.fromhex("aaa90b0101000000000000000000000000000008")
NON_CAMERA_REPLY = bytes.fromhex("aa40005a0e0000000000000000000000000000be")


@pytest.fixture
def coord(hass):
    return GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H66A0", configuration_url=_URL)


def _probe_round(c, *replies):
    """One probe window: tallies reset, some replies land, the verdict is drawn."""
    c._probe_camera_replies = 0
    c._probe_other_replies = 0
    c._camera_before_probe = c.camera_installed
    for frame in replies:
        c._notify_callback(None, bytearray(frame))
    c._settle_camera_probe()


def test_a_camera_reply_means_present(coord):
    _probe_round(coord, CAMERA_REPLY, NON_CAMERA_REPLY)
    assert coord.camera_installed is True


def test_silence_with_the_link_alive_means_absent(coord):
    # The determination this whole module exists for: no camera register answered, but the
    # device answered something else on the same connection, so the module is not there.
    for _ in range(CAMERA_ABSENT_STRIKES):
        _probe_round(coord, NON_CAMERA_REPLY)
    assert coord.camera_installed is False


def test_total_silence_concludes_nothing(coord):
    # Unreachable is a different state from absent, and must not be reported as absent.
    for _ in range(CAMERA_ABSENT_STRIKES * 3):
        _probe_round(coord)
    assert coord.camera_installed is None


def test_one_silent_probe_is_not_enough(coord):
    _probe_round(coord, NON_CAMERA_REPLY)
    assert coord.camera_installed is None, "a single dropped frame must not flip the state"


def test_unplugging_is_noticed_and_stale_registers_are_dropped(coord):
    _probe_round(coord, CAMERA_REPLY, REGISTER_REPLY)
    assert coord.camera_installed is True
    assert coord.video_settings, "the register value should have been stored"
    for _ in range(CAMERA_ABSENT_STRIKES):
        _probe_round(coord, NON_CAMERA_REPLY)
    assert coord.camera_installed is False
    # Stale values would keep the entities looking populated after the module went away.
    assert coord.video_settings == {}


def test_plugging_back_in_is_noticed_and_asks_for_the_full_block(coord):
    for _ in range(CAMERA_ABSENT_STRIKES):
        _probe_round(coord, NON_CAMERA_REPLY)
    assert coord.camera_installed is False
    _probe_round(coord, CAMERA_REPLY)
    assert coord.camera_installed is True
    # The cheap probe only asked aa 32, so the registers the entities need are still missing.
    assert coord._camera_needs_full_read is True


def test_strikes_reset_so_a_present_camera_does_not_drift_to_absent(coord):
    _probe_round(coord, NON_CAMERA_REPLY)
    _probe_round(coord, CAMERA_REPLY)
    _probe_round(coord, NON_CAMERA_REPLY)
    assert coord.camera_installed is True


def test_an_h6199_never_treats_0xa9_as_camera_evidence(hass):
    # On an H6199 the same opcode is the video sheet's own register and answers with no
    # camera anywhere, so it must not count either way.
    c = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6199", configuration_url=_URL)
    assert c._is_camera_domain(StatusDomain.DISPLAY_SETTING) is False
    assert c._is_camera_domain(StatusDomain.CAMERA_INSTALL) is True


def test_an_h66a0_counts_0xa9_as_camera_evidence(coord):
    assert coord._is_camera_domain(StatusDomain.DISPLAY_SETTING) is True
