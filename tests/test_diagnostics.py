from unittest.mock import MagicMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_govee_led_ble.const import CONF_MODEL, DOMAIN
from custom_components.ha_govee_led_ble.diagnostics import async_get_config_entry_diagnostics


def _prep(coord, *, packet_log=None, segment_colors=None):
    coord.packet_log = [] if packet_log is None else packet_log
    coord.segment_colors = [(1, 2, 3)] * coord.profile.segment_count if segment_colors is None else segment_colors
    coord._client = MagicMock(is_connected=True)
    coord._lock = MagicMock()
    coord._lock.locked.return_value = False
    coord._expected_state = {}
    return coord


def _entry(**kw):
    return MockConfigEntry(domain=DOMAIN, unique_id="AA:BB:CC:DD:EE:FF", data={CONF_MODEL: "H6199"}, **kw)


async def _run(coord, entry=None):
    entry = entry or _entry()
    entry.runtime_data = coord
    return await async_get_config_entry_diagnostics(MagicMock(), entry)


async def test_surfaces_segment_fields(mock_h6199_coordinator):
    colors = [(10, 20, 30)] * 15
    diag = await _run(_prep(mock_h6199_coordinator, segment_colors=colors))
    coord = diag["coordinator"]
    assert coord["supports_segments"] is False
    assert coord["segment_count"] == 15
    assert coord["segment_colors"] == colors


async def test_stale_experimental_option_ignored(mock_h6199_coordinator):
    """A leftover experimental option loads without error and drives no computed block."""
    entry = _entry(options={"experimental": {"timers": True, "diy": False}})
    diag = await _run(_prep(mock_h6199_coordinator), entry)
    assert "experimental" not in diag
    assert diag["entry"]["options"] == {"experimental": {"timers": True, "diy": False}}


async def test_redacts_unique_id(mock_h6199_coordinator):
    entry = _entry(options={"experimental": {"timers": True}})
    diag = await _run(_prep(mock_h6199_coordinator), entry)
    assert diag["entry"]["unique_id"] == "**REDACTED**"
    assert diag["entry"]["entry_id"] == entry.entry_id
    assert diag["entry"]["data"] == {CONF_MODEL: "H6199"}
    assert diag["entry"]["options"] == {"experimental": {"timers": True}}


async def test_last_rx_aa05_found(mock_h6199_coordinator):
    log = [
        {"dir": "tx", "raw": "aa0501"},
        {"dir": "rx", "raw": "ffff00"},
        {"dir": "rx"},
        {"dir": "rx", "raw": "aa05beef"},
    ]
    diag = await _run(_prep(mock_h6199_coordinator, packet_log=log))
    assert diag["coordinator"]["last_rx_aa05_raw"] == "aa05beef"
    assert diag["coordinator"]["packet_log"] is log


async def test_last_rx_aa05_picks_most_recent(mock_h6199_coordinator):
    log = [{"dir": "rx", "raw": "aa05aaaa"}, {"dir": "rx", "raw": "aa05bbbb"}]
    diag = await _run(_prep(mock_h6199_coordinator, packet_log=log))
    assert diag["coordinator"]["last_rx_aa05_raw"] == "aa05bbbb"


async def test_last_rx_aa05_none_when_unmatched(mock_h6199_coordinator):
    log = [{"dir": "tx", "raw": "aa05ff"}, {"dir": "rx", "raw": "3305ff"}, {"dir": "rx"}]
    diag = await _run(_prep(mock_h6199_coordinator, packet_log=log))
    assert diag["coordinator"]["last_rx_aa05_raw"] is None


async def test_last_rx_aa05_none_when_empty(mock_h6199_coordinator):
    diag = await _run(_prep(mock_h6199_coordinator))
    assert diag["coordinator"]["last_rx_aa05_raw"] is None


async def test_connected_true(mock_h6199_coordinator):
    coord = _prep(mock_h6199_coordinator)
    coord._client = MagicMock(is_connected=True)
    diag = await _run(coord)
    assert diag["coordinator"]["connected"] is True


async def test_connected_false_when_disconnected(mock_h6199_coordinator):
    coord = _prep(mock_h6199_coordinator)
    coord._client = MagicMock(is_connected=False)
    diag = await _run(coord)
    assert diag["coordinator"]["connected"] is False


async def test_connected_false_without_client(mock_h6199_coordinator):
    coord = _prep(mock_h6199_coordinator)
    coord._client = None
    diag = await _run(coord)
    assert diag["coordinator"]["connected"] is False


async def test_surfaces_firmware_hardware_and_availability(mock_h6199_coordinator):
    coord = _prep(mock_h6199_coordinator)
    coord.fw_version, coord.hw_version, coord.available = "3.02.24", "3.01.01", True
    diag = await _run(coord)
    assert diag["coordinator"]["fw_version"] == "3.02.24"
    assert diag["coordinator"]["hw_version"] == "3.01.01"
    assert diag["coordinator"]["available"] is True


async def test_lock_locked_surfaced(mock_h6199_coordinator):
    coord = _prep(mock_h6199_coordinator)
    coord._lock.locked.return_value = True
    diag = await _run(coord)
    assert diag["coordinator"]["lock_locked"] is True


async def test_surfaces_core_state(mock_h6199_coordinator):
    coord = _prep(mock_h6199_coordinator)
    coord._expected_state = {"brightness_pct": (55, 0.0)}
    diag = await _run(coord)
    coord = diag["coordinator"]
    assert coord["address"] == "11:22:33:44:55:66"
    assert coord["model"] == "H6199"
    assert coord["is_on"] is True
    assert coord["effect"] == "video: movie"
    assert coord["expected_brightness_pct"] == 55
