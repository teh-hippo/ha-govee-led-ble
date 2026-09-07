"""Diagnostics for the fields this branch adds.

Kept apart from tests/test_diagnostics.py so that file stays what it was.
"""

import pytest

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES
from custom_components.ha_govee_led_ble.govee_encryption import GoveeEncryptionSession

# Helpers that stayed with the upstream tests. Imported rather than copied so there is one
# definition of each, and so splitting these out added nothing to that file.
from tests.conftest import _make_coord
from tests.test_diagnostics import _entry, _prep, _run


@pytest.fixture
def h66a0_coordinator():
    return _make_coord(
        model="H66A0",
        profile=MODEL_PROFILES["H66A0"],
        camera_installed=True,
        video_settings={0x0B: [1], 0x11: [1, 2]},
        ic_count=90,
        reported_segment_count=14,
        _encryption=GoveeEncryptionSession("11:22:33:44:55:66"),
    )


async def test_encryption_state_survives_the_idle_disconnect(h66a0_coordinator):
    """The defect this block exists to fix.

    The session is scoped to one connection and reset on every disconnect, including the
    routine idle one. Reading only live state means a diagnostics download taken while idle
    reports "encryption off" for a device that encrypts every frame -- exactly backwards for
    the first artefact anybody asks a user to send.
    """
    session = h66a0_coordinator._encryption
    session.encryption_version = 2
    session.sku = "H66A0"
    session._record_negotiation(succeeded=True)
    session.reset()

    diag = await _run(_prep(h66a0_coordinator), _entry())
    encryption = diag["coordinator"]["encryption"]

    assert encryption["active"] is False, "no live session while disconnected"
    assert encryption["last_negotiation"]["succeeded"] is True
    assert encryption["last_negotiation"]["encryption_version"] == 2
    assert encryption["last_negotiation"]["sku"] == "H66A0"


async def test_a_failed_negotiation_records_why(h66a0_coordinator):
    session = h66a0_coordinator._encryption
    session.encryption_version = 2
    session._record_negotiation(succeeded=False, reason="no handshake response within 6s")
    session.reset()

    diag = await _run(_prep(h66a0_coordinator), _entry())
    last = diag["coordinator"]["encryption"]["last_negotiation"]

    assert last["succeeded"] is False
    assert last["reason"] == "no handshake response within 6s"


async def test_video_registers_and_camera_state_reach_the_download(h66a0_coordinator):
    diag = await _run(_prep(h66a0_coordinator), _entry())
    coord = diag["coordinator"]

    assert coord["camera_installed"] is True
    # Raw and keyed by sub-command: most of these registers are read but not identified, and
    # naming them here would invent fields for a reader to trust.
    assert coord["video_settings"]["0x11"] == [1, 2]
    assert coord["ic_count"] == 90
    assert coord["reported_segment_count"] == 14
