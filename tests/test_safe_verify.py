import json
import struct
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from tools.ble import decode_govee as dg
from tools.ble.safe_verify import (
    ManifestError,
    RunError,
    _simulation_state,
    analyse_run,
    complete_recovery,
    evaluate_run,
    initialise_run,
    load_manifest_data,
    record_marker,
    record_ownership_snapshot,
    simulate_run,
)

TARGET_ADDRESS = "AA:BB:CC:DD:3A:5B"
OTHER_ADDRESS = "11:22:33:44:55:66"
POWER_OFF = bytes.fromhex("3301000000000000000000000000000000000032")
POWER_ON = bytes.fromhex("3301010000000000000000000000000000000033")
POWER_STATUS_OFF = bytes.fromhex("aa010000000000000000000000000000000000ab")
SUNRISE = bytes.fromhex("3305040000000000000000000000000000000032")
BRIGHTNESS_5 = bytes.fromhex("3304050000000000000000000000000000000032")
BRIGHTNESS_20 = bytes.fromhex("3304140000000000000000000000000000000023")


def _operator(before: str, after: str) -> dict[str, Any]:
    return {
        "navigation_path": ["Cupboard Skirt", "Control"],
        "control_label": "Control",
        "expected_before": before,
        "expected_after": after,
        "coordinates": [32000, 16000],
        "max_wait_seconds": 3,
    }


def _manifest() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "run_id": "20260715220000-h617a-test-power",
        "task_id": "h617a-verify-power",
        "provenance": {
            "integration_commit": "1" * 40,
            "app_build": "test-build",
            "device_firmware": "3.02.24",
            "catalogue_sha256": "2" * 64,
        },
        "ownership": {
            "start": "home_assistant",
            "end": "govee_home",
        },
        "target": {
            "address": TARGET_ADDRESS,
            "local_name": "Govee_H617A_3A5B",
            "config_entry_id": "entry-h617a",
            "entity_id": "light.cupboard_skirt",
        },
        "baseline": {
            "power": "on",
            "brightness_percent": 5,
            "mode": "scene",
            "effect": "Sunrise",
        },
        "limits": {
            "max_brightness_percent": 10,
            "max_run_seconds": 90,
            "max_action_seconds": 5,
            "max_marker_gap_seconds": 60,
            "min_settle_seconds": 2,
            "max_settle_seconds": 4,
        },
        "windows": [
            {
                "id": "power-off",
                "kind": "action",
                "operator": _operator("On", "Off"),
                "expected": [
                    {
                        "id": "power-off-tx",
                        "direction": "TX",
                        "hex": POWER_OFF.hex(),
                        "min_count": 1,
                        "max_count": 1,
                        "sequence": 1,
                    },
                    {
                        "id": "power-off-rx",
                        "direction": "RX",
                        "hex": POWER_STATUS_OFF.hex(),
                        "min_count": 0,
                        "max_count": 1,
                        "state_confirmation": True,
                    },
                ],
            },
            {
                "id": "restore-sunrise",
                "kind": "restoration",
                "operator": _operator("Off", "Sunrise"),
                "expected": [
                    {
                        "id": "restore-sunrise-tx",
                        "direction": "TX",
                        "hex": SUNRISE.hex(),
                        "min_count": 0,
                        "max_count": 1,
                    }
                ],
            },
            {
                "id": "restore-brightness",
                "kind": "restoration",
                "operator": _operator("Sunrise", "5%"),
                "expected": [
                    {
                        "id": "restore-brightness-tx",
                        "direction": "TX",
                        "hex": BRIGHTNESS_5.hex(),
                        "min_count": 0,
                        "max_count": 1,
                    }
                ],
            },
        ],
        "restoration": {
            "packet_hex": [
                SUNRISE.hex(),
                BRIGHTNESS_5.hex(),
            ]
        },
    }


def _snapshot() -> dict[str, Any]:
    return {
        "config_entry_id": "entry-h617a",
        "entity_id": "light.cupboard_skirt",
        "entry_state": "loaded",
        "disabled_by": None,
        "entity_available": True,
        "power": "on",
        "brightness_percent": 5,
        "mode": "scene",
        "effect": "Sunrise",
    }


def _handoff_snapshot() -> dict[str, str]:
    return {
        "config_entry_id": "entry-h617a",
        "entity_id": "light.cupboard_skirt",
        "entry_state": "not_loaded",
        "disabled_by": "user",
    }


def _retained_snapshot() -> dict[str, Any]:
    return {
        "config_entry_id": "entry-h617a",
        "entity_id": "light.cupboard_skirt",
        "entry_state": "not_loaded",
        "disabled_by": "user",
        "app_connected": True,
        "power": "on",
        "brightness_percent": 5,
        "mode": "scene",
        "effect": "Sunrise",
    }


def _pcap_packet(timestamp: datetime, packet: bytes) -> bytes:
    epoch = timestamp.timestamp()
    seconds = int(epoch)
    micros = round((epoch - seconds) * 1_000_000)
    return struct.pack("<IIII", seconds, micros, len(packet), len(packet)) + packet


def _connection_packet(
    handle: int,
    address: str,
    *,
    connected: bool = True,
    status: int = 0,
) -> bytes:
    pseudo_header = struct.pack(">I", 1)
    if connected:
        address_le = bytes.fromhex(address.replace(":", ""))[::-1]
        params = bytes([0x01, 0x00]) + struct.pack("<H", handle) + bytes([0x00, 0x00])
        params += address_le + b"\x00" * 7
        return pseudo_header + bytes([0x04, 0x3E, len(params)]) + params
    params = bytes([status]) + struct.pack("<H", handle) + bytes([0x13])
    return pseudo_header + bytes([0x04, 0x05, len(params)]) + params


def _att_packet(handle: int, direction: str, value: bytes) -> bytes:
    pseudo_header = struct.pack(">I", 0 if direction == "TX" else 1)
    opcode = 0x52 if direction == "TX" else 0x1B
    att = bytes([opcode]) + struct.pack("<H", 0x0025) + value
    l2cap = struct.pack("<HH", len(att), dg.ATT_CID) + att
    acl = struct.pack("<HH", handle | 0x2000, len(l2cap)) + l2cap
    return pseudo_header + b"\x02" + acl


def _write_pcap(path: Path, packets: list[tuple[datetime, bytes]]) -> None:
    header = struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 201)
    path.write_bytes(header + b"".join(_pcap_packet(timestamp, packet) for timestamp, packet in packets))


def _start_capture_sidecars(pcap: Path, prediction_sha256: str, started_at: datetime) -> None:
    pcap.with_suffix(".actions.tsv").write_text("")
    (pcap.parent / ".current").write_text(f"123 {pcap.stem} {started_at.isoformat()} {prediction_sha256}\n")


def _stop_capture_sidecars(pcap: Path, prediction_sha256: str, stopped_at: datetime) -> None:
    (pcap.parent / ".current").unlink()
    metadata = {
        "capture": pcap.stem,
        "started_at": (stopped_at - timedelta(seconds=120)).isoformat(),
        "stopped_at": stopped_at.isoformat(),
        "actions": pcap.with_suffix(".actions.tsv").name,
        "prediction_sha256": prediction_sha256,
    }
    pcap.with_suffix(".meta.json").write_text(json.dumps(metadata))


def _write_manifest(path: Path) -> None:
    path.write_text(json.dumps(_manifest()))


def _record_valid_markers(run_dir: Path, pcap: Path, base: datetime) -> None:
    record_marker(
        run_dir,
        "armed",
        at=base + timedelta(seconds=1),
        pcap_path=pcap,
        viewer_healthy=True,
        phone_unlocked=True,
        target_confirmed=True,
    )
    marker_values = [
        ("power-off", "On", "Off"),
        ("restore-sunrise", "Off", "Sunrise"),
        ("restore-brightness", "Sunrise", "5%"),
    ]
    cursor = base + timedelta(seconds=2)
    for window_id, before, after in marker_values:
        record_marker(
            run_dir,
            f"{window_id}:before-action",
            at=cursor,
            viewer_healthy=True,
            phone_unlocked=True,
            displayed=before,
        )
        record_marker(
            run_dir,
            f"{window_id}:after-action",
            at=cursor + timedelta(seconds=1),
            viewer_healthy=True,
            phone_unlocked=True,
            displayed=after,
            visual="confirmed",
        )
        record_marker(
            run_dir,
            f"{window_id}:settled",
            at=cursor + timedelta(seconds=3),
            viewer_healthy=True,
            phone_unlocked=True,
        )
        cursor += timedelta(seconds=4)


def _prepare_replay(
    tmp_path: Path,
    extra_packets: list[tuple[datetime, bytes]] | None = None,
) -> tuple[Path, Path, datetime]:
    manifest_path = tmp_path / "manifest.json"
    run_dir = tmp_path / "run"
    pcap = tmp_path / "capture.pcap"
    _write_manifest(manifest_path)
    state = initialise_run(manifest_path, run_dir)
    record_ownership_snapshot(run_dir, "before", _snapshot())
    record_ownership_snapshot(run_dir, "handoff", _handoff_snapshot())
    base = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    packets = [
        (base, _connection_packet(0x0040, TARGET_ADDRESS)),
        (base + timedelta(seconds=2.2), _att_packet(0x0040, "TX", POWER_OFF)),
        (base + timedelta(seconds=2.4), _att_packet(0x0040, "RX", POWER_STATUS_OFF)),
        (base + timedelta(seconds=6.2), _att_packet(0x0040, "TX", SUNRISE)),
        (base + timedelta(seconds=10.2), _att_packet(0x0040, "TX", BRIGHTNESS_5)),
    ]
    packets.extend(extra_packets or [])
    packets.sort(key=lambda item: item[0])
    _write_pcap(pcap, packets)
    _start_capture_sidecars(pcap, state["prediction_sha256"], base)
    _record_valid_markers(run_dir, pcap, base)
    _stop_capture_sidecars(pcap, state["prediction_sha256"], base + timedelta(seconds=20))
    record_ownership_snapshot(run_dir, "retained-after", _retained_snapshot())
    return run_dir, pcap, base


def test_parse_capture_attributes_att_to_connection(tmp_path: Path):
    base = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    pcap = tmp_path / "attributed.pcap"
    _write_pcap(
        pcap,
        [
            (base, _connection_packet(0x0040, TARGET_ADDRESS)),
            (base + timedelta(seconds=1), _att_packet(0x0040, "TX", POWER_OFF)),
            (
                base + timedelta(seconds=1.5),
                _connection_packet(0x0040, TARGET_ADDRESS, connected=False, status=1),
            ),
            (base + timedelta(seconds=2), _att_packet(0x0040, "RX", POWER_STATUS_OFF)),
            (base + timedelta(seconds=3), _connection_packet(0x0040, TARGET_ADDRESS, connected=False)),
        ],
    )

    trace = dg.parse_capture(pcap.read_bytes())

    assert [(record.direction, record.connection_handle, record.address) for record in trace.att] == [
        ("TX", 0x0040, TARGET_ADDRESS),
        ("RX", 0x0040, TARGET_ADDRESS),
    ]
    assert dg.active_connections_at(trace, base + timedelta(seconds=2)) == {0x0040: TARGET_ADDRESS}
    assert dg.active_connections_at(trace, base + timedelta(seconds=4)) == {}


def test_parse_capture_rejects_truncated_record(tmp_path: Path):
    base = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    pcap = tmp_path / "truncated.pcap"
    _write_pcap(pcap, [(base, _connection_packet(0x0040, TARGET_ADDRESS))])
    pcap.write_bytes(pcap.read_bytes() + struct.pack("<IIII", int(base.timestamp()), 0, 100, 100) + b"\x00")

    with pytest.raises(ValueError, match="payload is truncated"):
        dg.parse_capture(pcap.read_bytes())

    assert dg.active_connections_at(
        dg.parse_capture(pcap.read_bytes(), allow_truncated=True),
        base,
    ) == {0x0040: TARGET_ADDRESS}


def test_simulation_uses_frozen_predictions_and_writes_evidence(tmp_path: Path):
    manifest = tmp_path / "manifest.json"
    run_dir = tmp_path / "simulation"
    _write_manifest(manifest)

    report = simulate_run(manifest, run_dir)

    assert report["verdict"] == "wire-pass"
    assert report["restoration_source"] == "wire"
    assert len(report["prediction_sha256"]) == 64
    assert report["provenance"]["device_firmware"] == "3.02.24"
    assert (run_dir / "evidence.json").exists()
    assert (run_dir / "evidence.md").exists()


def test_subsequent_run_starts_from_retained_govee_ownership(tmp_path: Path):
    manifest_data = _manifest()
    manifest_data["ownership"]["start"] = "govee_home"
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(manifest_data))
    run_dir = tmp_path / "run"
    pcap = tmp_path / "capture.pcap"
    state = initialise_run(manifest, run_dir)
    record_ownership_snapshot(run_dir, "retained-before", _retained_snapshot())
    base = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    _write_pcap(pcap, [(base, _connection_packet(0x0040, TARGET_ADDRESS))])
    _start_capture_sidecars(pcap, state["prediction_sha256"], base)

    armed = record_marker(
        run_dir,
        "armed",
        at=base + timedelta(seconds=1),
        pcap_path=pcap,
        viewer_healthy=True,
        phone_unlocked=True,
        target_confirmed=True,
    )

    assert armed["status"] == "active"
    assert set(armed["ownership_checks"]) == {"retained-before"}


def test_simulation_supports_explicit_home_assistant_handback(tmp_path: Path):
    manifest_data = _manifest()
    manifest_data["ownership"]["end"] = "home_assistant"
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(manifest_data))
    run_dir = tmp_path / "simulation"

    report = simulate_run(manifest, run_dir)

    assert report["ownership"]["boundary"]["end"] == "home_assistant"
    assert "after" in report["ownership"]["checks"]
    assert "retained-after" not in report["ownership"]["checks"]


def test_replay_passes_with_target_rx_and_exact_restoration(tmp_path: Path):
    run_dir, pcap, _ = _prepare_replay(tmp_path)

    report = analyse_run(run_dir, pcap)

    assert report["verdict"] == "wire-pass"
    assert report["restoration_source"] == "wire"
    assert report["errors"] == []
    assert report["artifacts"]["pcap"]["sha256"]


@pytest.mark.parametrize(
    ("extra_factory", "error_text"),
    [
        (
            lambda base: [
                (base + timedelta(seconds=0.1), _connection_packet(0x0041, OTHER_ADDRESS)),
                (base + timedelta(seconds=2.5), _att_packet(0x0041, "TX", POWER_ON)),
            ],
            "unattributed Govee frame",
        ),
        (
            lambda base: [(base + timedelta(seconds=2.5), _att_packet(0x0040, "TX", BRIGHTNESS_20))],
            "brightness 20% exceeds 10%",
        ),
        (
            lambda base: [(base + timedelta(seconds=2.5), _att_packet(0x0040, "TX", POWER_OFF))],
            "observed 2, expected 1..1",
        ),
    ],
)
def test_live_window_fails_before_the_next_action(
    tmp_path: Path,
    extra_factory,
    error_text: str,
):
    manifest_path = tmp_path / "manifest.json"
    run_dir = tmp_path / "run"
    pcap = tmp_path / "capture.pcap"
    _write_manifest(manifest_path)
    state = initialise_run(manifest_path, run_dir)
    record_ownership_snapshot(run_dir, "before", _snapshot())
    record_ownership_snapshot(run_dir, "handoff", _handoff_snapshot())
    base = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    packets = [
        (base, _connection_packet(0x0040, TARGET_ADDRESS)),
        (base + timedelta(seconds=2.2), _att_packet(0x0040, "TX", POWER_OFF)),
        (base + timedelta(seconds=2.4), _att_packet(0x0040, "RX", POWER_STATUS_OFF)),
        *extra_factory(base),
    ]
    packets.sort(key=lambda item: item[0])
    _write_pcap(pcap, packets)
    _start_capture_sidecars(pcap, state["prediction_sha256"], base)
    record_marker(
        run_dir,
        "armed",
        at=base + timedelta(seconds=1),
        pcap_path=pcap,
        viewer_healthy=True,
        phone_unlocked=True,
        target_confirmed=True,
    )
    record_marker(
        run_dir,
        "power-off:before-action",
        at=base + timedelta(seconds=2),
        viewer_healthy=True,
        phone_unlocked=True,
        displayed="On",
    )
    record_marker(
        run_dir,
        "power-off:after-action",
        at=base + timedelta(seconds=3),
        viewer_healthy=True,
        phone_unlocked=True,
        displayed="Off",
        visual="confirmed",
    )

    with pytest.raises(RunError, match=error_text):
        record_marker(
            run_dir,
            "power-off:settled",
            at=base + timedelta(seconds=5),
            viewer_healthy=True,
            phone_unlocked=True,
        )

    assert json.loads((run_dir / "state.json").read_text())["status"] == "needs_recovery"
    _stop_capture_sidecars(pcap, state["prediction_sha256"], base + timedelta(seconds=6))
    complete_recovery(run_dir, _retained_snapshot())
    assert json.loads((run_dir / "evidence.json").read_text())["verdict"] == "invalid"


def test_post_settled_tail_traffic_invalidates_final_analysis(tmp_path: Path):
    base = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    run_dir, pcap, _ = _prepare_replay(
        tmp_path,
        [(base + timedelta(seconds=14), _att_packet(0x0040, "TX", BRIGHTNESS_20))],
    )

    report = analyse_run(run_dir, pcap)

    assert report["verdict"] == "invalid"
    assert any("post-settled target TX" in error for error in report["errors"])
    assert any("brightness 20% exceeds 10%" in error for error in report["errors"])


def test_before_action_rejects_idle_gap_traffic(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    run_dir = tmp_path / "run"
    pcap = tmp_path / "capture.pcap"
    _write_manifest(manifest_path)
    state = initialise_run(manifest_path, run_dir)
    record_ownership_snapshot(run_dir, "before", _snapshot())
    record_ownership_snapshot(run_dir, "handoff", _handoff_snapshot())
    base = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    _write_pcap(
        pcap,
        [
            (base, _connection_packet(0x0040, TARGET_ADDRESS)),
            (base + timedelta(seconds=2.2), _att_packet(0x0040, "TX", POWER_OFF)),
            (base + timedelta(seconds=2.4), _att_packet(0x0040, "RX", POWER_STATUS_OFF)),
            (base + timedelta(seconds=5.5), _att_packet(0x0040, "TX", POWER_ON)),
        ],
    )
    _start_capture_sidecars(pcap, state["prediction_sha256"], base)
    record_marker(
        run_dir,
        "armed",
        at=base + timedelta(seconds=1),
        pcap_path=pcap,
        viewer_healthy=True,
        phone_unlocked=True,
        target_confirmed=True,
    )
    record_marker(
        run_dir,
        "power-off:before-action",
        at=base + timedelta(seconds=2),
        viewer_healthy=True,
        phone_unlocked=True,
        displayed="On",
    )
    record_marker(
        run_dir,
        "power-off:after-action",
        at=base + timedelta(seconds=3),
        viewer_healthy=True,
        phone_unlocked=True,
        displayed="Off",
        visual="confirmed",
    )
    record_marker(
        run_dir,
        "power-off:settled",
        at=base + timedelta(seconds=5),
        viewer_healthy=True,
        phone_unlocked=True,
    )

    with pytest.raises(RunError, match="unwindowed target TX before action"):
        record_marker(
            run_dir,
            "restore-sunrise:before-action",
            at=base + timedelta(seconds=6),
            viewer_healthy=True,
            phone_unlocked=True,
            displayed="Off",
        )


def test_total_run_limit_is_checked_before_each_action(tmp_path: Path):
    manifest_data = _manifest()
    manifest_data["limits"]["max_run_seconds"] = 5
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest_data))
    run_dir = tmp_path / "run"
    pcap = tmp_path / "capture.pcap"
    state = initialise_run(manifest_path, run_dir)
    record_ownership_snapshot(run_dir, "before", _snapshot())
    record_ownership_snapshot(run_dir, "handoff", _handoff_snapshot())
    base = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    _write_pcap(
        pcap,
        [
            (base, _connection_packet(0x0040, TARGET_ADDRESS)),
            (base + timedelta(seconds=2.2), _att_packet(0x0040, "TX", POWER_OFF)),
            (base + timedelta(seconds=2.4), _att_packet(0x0040, "RX", POWER_STATUS_OFF)),
        ],
    )
    _start_capture_sidecars(pcap, state["prediction_sha256"], base)
    record_marker(
        run_dir,
        "armed",
        at=base + timedelta(seconds=1),
        pcap_path=pcap,
        viewer_healthy=True,
        phone_unlocked=True,
        target_confirmed=True,
    )
    record_marker(
        run_dir,
        "power-off:before-action",
        at=base + timedelta(seconds=2),
        viewer_healthy=True,
        phone_unlocked=True,
        displayed="On",
    )
    record_marker(
        run_dir,
        "power-off:after-action",
        at=base + timedelta(seconds=3),
        viewer_healthy=True,
        phone_unlocked=True,
        displayed="Off",
        visual="confirmed",
    )
    record_marker(
        run_dir,
        "power-off:settled",
        at=base + timedelta(seconds=5),
        viewer_healthy=True,
        phone_unlocked=True,
    )

    with pytest.raises(RunError, match="maximum duration"):
        record_marker(
            run_dir,
            "restore-sunrise:before-action",
            at=base + timedelta(seconds=7),
            viewer_healthy=True,
            phone_unlocked=True,
            displayed="Off",
        )


def test_state_confirmation_must_follow_the_required_tx(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    run_dir = tmp_path / "run"
    pcap = tmp_path / "capture.pcap"
    _write_manifest(manifest_path)
    state = initialise_run(manifest_path, run_dir)
    record_ownership_snapshot(run_dir, "before", _snapshot())
    record_ownership_snapshot(run_dir, "handoff", _handoff_snapshot())
    base = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    _write_pcap(
        pcap,
        [
            (base, _connection_packet(0x0040, TARGET_ADDRESS)),
            (base + timedelta(seconds=2.2), _att_packet(0x0040, "RX", POWER_STATUS_OFF)),
            (base + timedelta(seconds=2.4), _att_packet(0x0040, "TX", POWER_OFF)),
        ],
    )
    _start_capture_sidecars(pcap, state["prediction_sha256"], base)
    record_marker(
        run_dir,
        "armed",
        at=base + timedelta(seconds=1),
        pcap_path=pcap,
        viewer_healthy=True,
        phone_unlocked=True,
        target_confirmed=True,
    )
    record_marker(
        run_dir,
        "power-off:before-action",
        at=base + timedelta(seconds=2),
        viewer_healthy=True,
        phone_unlocked=True,
        displayed="On",
    )
    record_marker(
        run_dir,
        "power-off:after-action",
        at=base + timedelta(seconds=3),
        viewer_healthy=True,
        phone_unlocked=True,
        displayed="Off",
        visual="confirmed",
    )

    with pytest.raises(RunError, match="state confirmation preceded required TX"):
        record_marker(
            run_dir,
            "power-off:settled",
            at=base + timedelta(seconds=5),
            viewer_healthy=True,
            phone_unlocked=True,
        )


def test_missing_required_rx_is_not_classified_as_no_write():
    manifest_data = _manifest()
    manifest_data["windows"][0]["expected"][1]["min_count"] = 1
    manifest = load_manifest_data(manifest_data)
    state, records = _simulation_state(
        manifest,
        {
            "prediction_sha256": "prediction",
            "manifest_sha256": "manifest",
            "target_handle": None,
            "markers": [],
            "ownership_checks": {},
        },
    )
    without_rx = tuple(record for record in records if record.direction != "RX")

    report = evaluate_run(manifest, state, without_rx, simulation=True)

    assert report["verdict"] == "mismatch"
    assert any(frame["hex"] == POWER_OFF.hex() for frame in report["frames"])


def test_manifest_tampering_is_rejected(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    run_dir = tmp_path / "run"
    _write_manifest(manifest_path)
    initialise_run(manifest_path, run_dir)
    frozen = json.loads((run_dir / "manifest.json").read_text())
    frozen["windows"][0]["expected"][0]["hex"] = POWER_ON.hex()
    (run_dir / "manifest.json").write_text(json.dumps(frozen))

    with pytest.raises(RunError, match="frozen manifest hash mismatch"):
        record_ownership_snapshot(run_dir, "before", _snapshot())


def test_manifest_rejects_predicted_brightness_above_the_limit():
    manifest = _manifest()
    manifest["windows"][0]["expected"][0]["hex"] = BRIGHTNESS_20.hex()

    with pytest.raises(ManifestError, match="brightness 20% above the safety limit"):
        load_manifest_data(manifest)


def test_early_arming_failure_preserves_capture_for_recovery(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    run_dir = tmp_path / "run"
    pcap = tmp_path / "capture.pcap"
    _write_manifest(manifest_path)
    state = initialise_run(manifest_path, run_dir)
    record_ownership_snapshot(run_dir, "before", _snapshot())
    record_ownership_snapshot(run_dir, "handoff", _handoff_snapshot())
    base = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    _write_pcap(pcap, [(base, _connection_packet(0x0040, TARGET_ADDRESS))])
    _start_capture_sidecars(pcap, state["prediction_sha256"], base)

    with pytest.raises(RunError, match="viewer unhealthy"):
        record_marker(
            run_dir,
            "armed",
            at=base + timedelta(seconds=1),
            pcap_path=pcap,
            viewer_healthy=False,
            phone_unlocked=True,
            target_confirmed=True,
        )

    failed_state = json.loads((run_dir / "state.json").read_text())
    assert failed_state["status"] == "needs_recovery"
    assert failed_state["pcap_path"] == str(pcap.resolve())
    with pytest.raises(RunError, match="capture is still active"):
        complete_recovery(run_dir, _retained_snapshot())

    _stop_capture_sidecars(pcap, state["prediction_sha256"], base + timedelta(seconds=2))
    recovered = complete_recovery(run_dir, _retained_snapshot())
    assert recovered["status"] == "invalid_recovered"
    assert "pcap" in json.loads((run_dir / "evidence.json").read_text())["artifacts"]


def test_ambiguous_visual_result_requires_terminal_recovery(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    run_dir = tmp_path / "run"
    pcap = tmp_path / "capture.pcap"
    _write_manifest(manifest_path)
    state = initialise_run(manifest_path, run_dir)
    record_ownership_snapshot(run_dir, "before", _snapshot())
    record_ownership_snapshot(run_dir, "handoff", _handoff_snapshot())
    base = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    _write_pcap(pcap, [(base, _connection_packet(0x0040, TARGET_ADDRESS))])
    _start_capture_sidecars(pcap, state["prediction_sha256"], base)
    record_marker(
        run_dir,
        "armed",
        at=base + timedelta(seconds=1),
        pcap_path=pcap,
        viewer_healthy=True,
        phone_unlocked=True,
        target_confirmed=True,
    )
    record_marker(
        run_dir,
        "power-off:before-action",
        at=base + timedelta(seconds=2),
        viewer_healthy=True,
        phone_unlocked=True,
        displayed="On",
    )

    with pytest.raises(RunError, match="visual result"):
        record_marker(
            run_dir,
            "power-off:after-action",
            at=base + timedelta(seconds=3),
            viewer_healthy=True,
            phone_unlocked=True,
            displayed="Off",
            visual="ambiguous",
        )

    _stop_capture_sidecars(pcap, state["prediction_sha256"], base + timedelta(seconds=4))
    state = complete_recovery(run_dir, _retained_snapshot())
    assert state["status"] == "invalid_recovered"
    assert json.loads((run_dir / "evidence.json").read_text())["verdict"] == "invalid"


def test_phone_activity_gap_requires_recovery(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    run_dir = tmp_path / "run"
    pcap = tmp_path / "capture.pcap"
    _write_manifest(manifest_path)
    state = initialise_run(manifest_path, run_dir)
    record_ownership_snapshot(run_dir, "before", _snapshot())
    record_ownership_snapshot(run_dir, "handoff", _handoff_snapshot())
    base = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    _write_pcap(pcap, [(base, _connection_packet(0x0040, TARGET_ADDRESS))])
    _start_capture_sidecars(pcap, state["prediction_sha256"], base)
    record_marker(
        run_dir,
        "armed",
        at=base + timedelta(seconds=1),
        pcap_path=pcap,
        viewer_healthy=True,
        phone_unlocked=True,
        target_confirmed=True,
    )

    with pytest.raises(RunError, match="phone activity gap"):
        record_marker(
            run_dir,
            "power-off:before-action",
            at=base + timedelta(seconds=62),
            viewer_healthy=True,
            phone_unlocked=True,
            displayed="On",
        )

    _stop_capture_sidecars(pcap, state["prediction_sha256"], base + timedelta(seconds=63))
    state = complete_recovery(run_dir, _retained_snapshot())
    assert state["status"] == "invalid_recovered"
