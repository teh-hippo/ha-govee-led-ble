from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_govee_led_ble.const import CONF_MODEL, DOMAIN
from custom_components.ha_govee_led_ble.coordinator import (
    PACKET_LOG_LIMIT,
    PACKET_LOG_RAW_BYTES_LIMIT,
)
from custom_components.ha_govee_led_ble.diagnostics import async_get_config_entry_diagnostics
from custom_components.ha_govee_led_ble.effect_diagnostics import (
    DiagnosticOutcome,
    DiagnosticStage,
    EffectDiagnosticHistory,
)
from custom_components.ha_govee_led_ble.effect_setup import EFFECT_BACKEND_DATA_KEY

REDACTED = "**REDACTED**"


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


async def _run(coord, entry=None, hass=None):
    entry = entry or _entry()
    entry.runtime_data = coord
    return await async_get_config_entry_diagnostics(hass or MagicMock(), entry)


async def test_surfaces_segment_fields(mock_h6199_coordinator):
    colors = [(10, 20, 30)] * 15
    diag = await _run(_prep(mock_h6199_coordinator, segment_colors=colors))
    coord = diag["coordinator"]
    assert coord["supports_segments"] is True
    assert coord["segment_count"] == 15
    assert coord["segment_colors"] == colors
    assert coord["segment_brightness"] == [100] * 15
    assert coord["segment_state_source"] == "initial"
    assert coord["segment_state_observed_at"] is None
    assert coord["subordinate_20_version"] is None
    assert coord["subordinate_21_version"] is None
    assert coord["diy_code"] is None
    assert coord["color_mode"] is None
    assert coord["effect_categories"] == ["advanced", "effects", "reactive", "scenes", "video"]
    assert coord["prefix_effect_names"] is False
    assert coord["always_include_custom_effects"] is False


async def test_surfaces_release_capability_evidence_without_hiding_planned_workflows(
    mock_h6199_coordinator,
) -> None:
    diag = await _run(_prep(mock_h6199_coordinator))
    contract = diag["coordinator"]["release_capabilities"]
    capabilities = {capability["workflow"]: capability for capability in contract["capabilities"]}

    assert contract["schema_version"] == 1
    assert contract["model"] == "H6199"
    assert capabilities["palette_diy"] == {
        "workflow": "palette_diy",
        "frontend_visibility": "visible",
        "persistent_content_kind": "palette_diy",
        "application_route": "home_assistant_control",
        "compiler_deployer_strategy": "h6199_custom_engine",
        "verification_confidence": "selection_only",
        "physical_validation_state": "capture_validated",
        "evidence_classification": "structural",
    }
    assert capabilities["workshop"]["verification_confidence"] == "selection_only"


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
    assert diag["coordinator"]["address"] == "**REDACTED**"


@pytest.mark.parametrize(
    ("packet_log", "expected_last_rx"),
    [
        pytest.param(
            [
                {"dir": "tx", "raw": "aa0501"},
                {"dir": "rx", "raw": "ffff00"},
                {"dir": "rx"},
                {"dir": "rx", "raw": "aa05beef"},
            ],
            "aa05beef",
            id="latest-matching-packet",
        ),
        pytest.param(
            [{"dir": "rx", "raw": "aa05aaaa"}, {"dir": "rx", "raw": "aa05bbbb"}],
            "aa05bbbb",
            id="most-recent-match",
        ),
        pytest.param(
            [{"dir": "tx", "raw": "aa05ff"}, {"dir": "rx", "raw": "3305ff"}, {"dir": "rx"}],
            None,
            id="unmatched-packets",
        ),
        pytest.param([], None, id="empty-log"),
    ],
)
async def test_last_rx_aa05_from_packet_log(mock_h6199_coordinator, packet_log, expected_last_rx):
    diag = await _run(_prep(mock_h6199_coordinator, packet_log=packet_log))
    assert diag["coordinator"]["last_rx_aa05_raw"] == expected_last_rx
    assert diag["coordinator"]["packet_log"] == packet_log


@pytest.mark.parametrize(
    ("client_connected", "expected_connected"),
    [
        pytest.param(True, True, id="connected-client"),
        pytest.param(False, False, id="disconnected-client"),
        pytest.param(None, False, id="missing-client"),
    ],
)
async def test_connected_state(mock_h6199_coordinator, client_connected, expected_connected):
    coord = _prep(mock_h6199_coordinator)
    coord._client = None if client_connected is None else MagicMock(is_connected=client_connected)
    diag = await _run(coord)
    assert diag["coordinator"]["connected"] is expected_connected


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
    assert coord["address"] == "**REDACTED**"
    assert coord["model"] == "H6199"
    assert coord["is_on"] is True
    assert coord["effect"] == "video: movie"
    assert coord["expected_brightness_pct"] == 55
    assert coord["blank_screen_policy"] == {
        "detection": 2,
        "low_brightness_duration_seconds": 10,
        "same_tone_duration_seconds": 120,
    }


async def test_full_diagnostics_contains_no_ble_address(mock_h6199_coordinator):
    coord = _prep(mock_h6199_coordinator)
    diag = await _run(coord)
    blob = str(diag)
    assert "11:22:33:44:55:66" not in blob
    assert "AA:BB:CC:DD:EE:FF" not in blob


async def test_diagnostics_defensively_bound_and_redact_packet_history(
    mock_h6199_coordinator,
) -> None:
    log = [
        {
            "dir": "rx",
            "raw": f"aa05{index:04x}",
            "address": "11:22:33:44:55:66",
        }
        for index in range(PACKET_LOG_LIMIT + 10)
    ]

    diag = await _run(_prep(mock_h6199_coordinator, packet_log=log))
    packet_log = diag["coordinator"]["packet_log"]

    assert len(packet_log) == PACKET_LOG_LIMIT
    assert packet_log[0]["raw"] == "aa05000a"
    assert all(packet["address"] == "**REDACTED**" for packet in packet_log)


async def test_diagnostics_truncate_oversized_raw_packet_data(
    mock_h6199_coordinator,
) -> None:
    raw = "aa" * (PACKET_LOG_RAW_BYTES_LIMIT + 1)

    diag = await _run(
        _prep(
            mock_h6199_coordinator,
            packet_log=[{"dir": "rx", "raw": raw}],
        )
    )
    packet = diag["coordinator"]["packet_log"][0]

    assert len(packet["raw"]) == PACKET_LOG_RAW_BYTES_LIMIT * 2
    assert packet["truncated"] is True


async def test_surfaces_only_bounded_deployment_diagnostics_for_this_entry(
    mock_h6199_coordinator,
) -> None:
    entry = _entry()
    history = EffectDiagnosticHistory(maximum_events=2)
    history.record(
        DiagnosticStage.API_SERVICE,
        DiagnosticOutcome.STARTED,
        "apply_request_received",
        config_entry_id=entry.entry_id,
        details={"password": "never-visible"},
    )
    history.record_evidence_gap(
        "unsupported_capability",
        config_entry_id="other-entry",
        details={"capability": "workshop"},
    )
    hass = SimpleNamespace(
        data={
            DOMAIN: {
                EFFECT_BACKEND_DATA_KEY: SimpleNamespace(
                    diagnostics=history,
                )
            }
        }
    )

    diag = await _run(_prep(mock_h6199_coordinator), entry, hass)
    deployment = diag["effect_deployment_diagnostics"]

    assert deployment["schema_version"] == 1
    assert deployment["limits"]["event_count"] == 2
    assert len(deployment["events"]) == 1
    assert deployment["events"][0]["details"]["password"] == REDACTED
    assert "never-visible" not in str(diag)


async def test_unknown_white_balance_is_not_reported_as_neutral(mock_h6199_coordinator):
    coord = _prep(mock_h6199_coordinator)
    coord.white_balance_red = coord.white_balance_blue = None
    diag = await _run(coord)
    assert diag["coordinator"]["white_balance"] is None
    assert diag["coordinator"]["white_balance_position"] is None


async def test_white_balance_position_is_exact_not_nearest(mock_h6199_coordinator):
    coord = _prep(mock_h6199_coordinator)
    coord.white_balance_red, coord.white_balance_blue = 16, 3
    diag = await _run(coord)
    assert diag["coordinator"]["white_balance_position"] == 17

    coord.white_balance_red, coord.white_balance_blue = 17, 4
    diag = await _run(coord)
    assert diag["coordinator"]["white_balance_position"] is None
