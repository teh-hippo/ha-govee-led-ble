#!/usr/bin/env python3
"""Fail-closed runner for one approved iPhone-driven Govee BLE verification."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.ble import decode_govee as dg

SCHEMA_VERSION = 1
STATE_FILE = "state.json"
MANIFEST_FILE = "manifest.json"
PREDICTION_FILE = "prediction.json"
EVIDENCE_JSON = "evidence.json"
EVIDENCE_MARKDOWN = "evidence.md"


class ManifestError(ValueError):
    pass


class RunError(RuntimeError):
    pass


@dataclass(frozen=True)
class FrameExpectation:
    id: str
    direction: str
    value: bytes
    min_count: int
    max_count: int
    state_confirmation: bool
    sequence: int | None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "direction": self.direction,
            "hex": self.value.hex(),
            "min_count": self.min_count,
            "max_count": self.max_count,
        }
        if self.state_confirmation:
            result["state_confirmation"] = True
        if self.sequence is not None:
            result["sequence"] = self.sequence
        return result


@dataclass(frozen=True)
class OperatorAction:
    navigation_path: tuple[str, ...]
    control_label: str
    expected_before: str
    expected_after: str
    coordinates: tuple[int, int]
    max_wait_seconds: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "navigation_path": list(self.navigation_path),
            "control_label": self.control_label,
            "expected_before": self.expected_before,
            "expected_after": self.expected_after,
            "coordinates": list(self.coordinates),
            "max_wait_seconds": self.max_wait_seconds,
        }


@dataclass(frozen=True)
class VerificationWindow:
    id: str
    kind: str
    operator: OperatorAction
    expected: tuple[FrameExpectation, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "operator": self.operator.to_dict(),
            "expected": [item.to_dict() for item in self.expected],
        }


@dataclass(frozen=True)
class RunManifest:
    run_id: str
    task_id: str
    provenance: dict[str, str]
    ownership: dict[str, str]
    target: dict[str, str]
    baseline: dict[str, Any]
    limits: dict[str, int]
    windows: tuple[VerificationWindow, ...]
    restoration_packets: tuple[bytes, ...]

    @property
    def target_address(self) -> str:
        return self.target["address"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "provenance": dict(self.provenance),
            "ownership": dict(self.ownership),
            "target": dict(self.target),
            "baseline": dict(self.baseline),
            "limits": dict(self.limits),
            "windows": [window.to_dict() for window in self.windows],
            "restoration": {"packet_hex": [packet.hex() for packet in self.restoration_packets]},
        }

    def prediction_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "windows": [
                {
                    "id": window.id,
                    "expected": [item.to_dict() for item in window.expected],
                }
                for window in self.windows
            ],
            "restoration_packet_hex": [packet.hex() for packet in self.restoration_packets],
        }

    def marker_sequence(self) -> tuple[str, ...]:
        markers = ["armed"]
        for window in self.windows:
            markers.extend(
                (
                    f"{window.id}:before-action",
                    f"{window.id}:after-action",
                    f"{window.id}:settled",
                )
            )
        return tuple(markers)


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ManifestError(f"{label} must be an object")
    return value


def _exact_keys(value: dict[str, Any], required: set[str], optional: set[str], label: str) -> None:
    missing = required - value.keys()
    unknown = value.keys() - required - optional
    if missing:
        raise ManifestError(f"{label} is missing: {', '.join(sorted(missing))}")
    if unknown:
        raise ManifestError(f"{label} has unknown keys: {', '.join(sorted(unknown))}")


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{label} must be a non-empty string")
    return value.strip()


def _integer(value: Any, label: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ManifestError(f"{label} must be an integer from {minimum} to {maximum}")
    return value


def _identifier(value: Any, label: str) -> str:
    result = _text(value, label)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,127}", result):
        raise ManifestError(f"{label} contains unsupported characters")
    return result


def normalise_address(value: Any) -> str:
    address = _text(value, "target.address")
    compact = address.replace(":", "").replace("-", "")
    if not re.fullmatch(r"[0-9A-Fa-f]{12}", compact):
        raise ManifestError("target.address must be a six-byte Bluetooth address")
    return ":".join(compact[index : index + 2].upper() for index in range(0, 12, 2))


def _frame(value: Any, label: str) -> bytes:
    text = _text(value, label)
    try:
        frame = bytes.fromhex(text)
    except ValueError as exc:
        raise ManifestError(f"{label} must be hexadecimal") from exc
    if not dg._is_govee(frame):
        raise ManifestError(f"{label} must be one checksummed 20-byte Govee frame")
    return frame


def _load_operator(value: Any, label: str, max_action_seconds: int) -> OperatorAction:
    raw = _mapping(value, label)
    required = {
        "navigation_path",
        "control_label",
        "expected_before",
        "expected_after",
        "coordinates",
        "max_wait_seconds",
    }
    _exact_keys(raw, required, set(), label)
    path = raw["navigation_path"]
    if not isinstance(path, list) or not path:
        raise ManifestError(f"{label}.navigation_path must be a non-empty array")
    navigation_path = tuple(_text(item, f"{label}.navigation_path") for item in path)
    coordinates = raw["coordinates"]
    if not isinstance(coordinates, list) or len(coordinates) != 2:
        raise ManifestError(f"{label}.coordinates must contain x and y")
    return OperatorAction(
        navigation_path=navigation_path,
        control_label=_text(raw["control_label"], f"{label}.control_label"),
        expected_before=_text(raw["expected_before"], f"{label}.expected_before"),
        expected_after=_text(raw["expected_after"], f"{label}.expected_after"),
        coordinates=(
            _integer(coordinates[0], f"{label}.coordinates[0]", 0, 65535),
            _integer(coordinates[1], f"{label}.coordinates[1]", 0, 65535),
        ),
        max_wait_seconds=_integer(
            raw["max_wait_seconds"],
            f"{label}.max_wait_seconds",
            1,
            max_action_seconds,
        ),
    )


def _load_expectation(value: Any, label: str) -> FrameExpectation:
    raw = _mapping(value, label)
    required = {"id", "direction", "hex", "min_count", "max_count"}
    optional = {"state_confirmation", "sequence"}
    _exact_keys(raw, required, optional, label)
    direction = _text(raw["direction"], f"{label}.direction").upper()
    if direction not in {"TX", "RX"}:
        raise ManifestError(f"{label}.direction must be TX or RX")
    minimum = _integer(raw["min_count"], f"{label}.min_count", 0, 20)
    maximum = _integer(raw["max_count"], f"{label}.max_count", minimum, 20)
    state_confirmation = raw.get("state_confirmation", False)
    if not isinstance(state_confirmation, bool):
        raise ManifestError(f"{label}.state_confirmation must be boolean")
    if state_confirmation and direction != "RX":
        raise ManifestError(f"{label}.state_confirmation is valid only for RX frames")
    if state_confirmation and maximum == 0:
        raise ManifestError(f"{label}.state_confirmation must allow at least one frame")
    sequence = raw.get("sequence")
    if sequence is not None:
        sequence = _integer(sequence, f"{label}.sequence", 1, 100)
        if minimum != 1 or maximum != 1:
            raise ManifestError(f"{label} sequenced frames must occur exactly once")
    return FrameExpectation(
        id=_identifier(raw["id"], f"{label}.id"),
        direction=direction,
        value=_frame(raw["hex"], f"{label}.hex"),
        min_count=minimum,
        max_count=maximum,
        state_confirmation=state_confirmation,
        sequence=sequence,
    )


def load_manifest_data(value: Any) -> RunManifest:
    raw = _mapping(value, "manifest")
    required = {
        "schema_version",
        "run_id",
        "task_id",
        "provenance",
        "ownership",
        "target",
        "baseline",
        "limits",
        "windows",
        "restoration",
    }
    _exact_keys(raw, required, set(), "manifest")
    if raw["schema_version"] != SCHEMA_VERSION:
        raise ManifestError(f"schema_version must be {SCHEMA_VERSION}")

    provenance = _mapping(raw["provenance"], "provenance")
    provenance_keys = {
        "integration_commit",
        "app_build",
        "device_firmware",
        "catalogue_sha256",
    }
    _exact_keys(provenance, provenance_keys, set(), "provenance")
    integration_commit = _text(provenance["integration_commit"], "provenance.integration_commit").lower()
    catalogue_sha256 = _text(provenance["catalogue_sha256"], "provenance.catalogue_sha256").lower()
    if not re.fullmatch(r"[0-9a-f]{40}", integration_commit):
        raise ManifestError("provenance.integration_commit must be a full Git commit")
    if not re.fullmatch(r"[0-9a-f]{64}", catalogue_sha256):
        raise ManifestError("provenance.catalogue_sha256 must be SHA-256")
    normalised_provenance = {
        "integration_commit": integration_commit,
        "app_build": _text(provenance["app_build"], "provenance.app_build"),
        "device_firmware": _text(provenance["device_firmware"], "provenance.device_firmware"),
        "catalogue_sha256": catalogue_sha256,
    }

    ownership = _mapping(raw["ownership"], "ownership")
    _exact_keys(ownership, {"start", "end"}, set(), "ownership")
    normalised_ownership = {
        "start": _text(ownership["start"], "ownership.start"),
        "end": _text(ownership["end"], "ownership.end"),
    }
    for boundary, owner in normalised_ownership.items():
        if owner not in {"home_assistant", "govee_home"}:
            raise ManifestError(f"ownership.{boundary} must be home_assistant or govee_home")

    target = _mapping(raw["target"], "target")
    _exact_keys(target, {"address", "local_name", "config_entry_id", "entity_id"}, set(), "target")
    normalised_target = {
        "address": normalise_address(target["address"]),
        "local_name": _text(target["local_name"], "target.local_name"),
        "config_entry_id": _text(target["config_entry_id"], "target.config_entry_id"),
        "entity_id": _text(target["entity_id"], "target.entity_id"),
    }

    baseline = _mapping(raw["baseline"], "baseline")
    baseline_keys = {
        "power",
        "brightness_percent",
        "mode",
        "effect",
    }
    _exact_keys(baseline, baseline_keys, set(), "baseline")
    baseline_brightness = _integer(
        baseline["brightness_percent"],
        "baseline.brightness_percent",
        0,
        100,
    )
    normalised_baseline = {
        "power": _text(baseline["power"], "baseline.power"),
        "brightness_percent": baseline_brightness,
        "mode": _text(baseline["mode"], "baseline.mode"),
        "effect": _text(baseline["effect"], "baseline.effect"),
    }

    limits = _mapping(raw["limits"], "limits")
    limit_keys = {
        "max_brightness_percent",
        "max_run_seconds",
        "max_action_seconds",
        "max_marker_gap_seconds",
        "min_settle_seconds",
        "max_settle_seconds",
    }
    _exact_keys(limits, limit_keys, set(), "limits")
    normalised_limits = {
        "max_brightness_percent": _integer(limits["max_brightness_percent"], "limits.max_brightness_percent", 1, 10),
        "max_run_seconds": _integer(limits["max_run_seconds"], "limits.max_run_seconds", 1, 90),
        "max_action_seconds": _integer(limits["max_action_seconds"], "limits.max_action_seconds", 1, 10),
        "max_marker_gap_seconds": _integer(
            limits["max_marker_gap_seconds"],
            "limits.max_marker_gap_seconds",
            1,
            60,
        ),
        "min_settle_seconds": _integer(limits["min_settle_seconds"], "limits.min_settle_seconds", 1, 10),
        "max_settle_seconds": _integer(limits["max_settle_seconds"], "limits.max_settle_seconds", 1, 15),
    }
    if normalised_limits["min_settle_seconds"] > normalised_limits["max_settle_seconds"]:
        raise ManifestError("limits.min_settle_seconds exceeds limits.max_settle_seconds")
    if baseline_brightness > normalised_limits["max_brightness_percent"]:
        raise ManifestError("baseline brightness exceeds the run safety limit")

    windows_raw = raw["windows"]
    if not isinstance(windows_raw, list) or not windows_raw:
        raise ManifestError("windows must be a non-empty array")
    windows: list[VerificationWindow] = []
    window_ids: set[str] = set()
    expectation_ids: set[str] = set()
    for index, item in enumerate(windows_raw):
        label = f"windows[{index}]"
        window = _mapping(item, label)
        _exact_keys(window, {"id", "kind", "operator", "expected"}, set(), label)
        window_id = _identifier(window["id"], f"{label}.id")
        if window_id in window_ids:
            raise ManifestError(f"duplicate window id: {window_id}")
        window_ids.add(window_id)
        kind = _text(window["kind"], f"{label}.kind")
        if kind not in {"action", "restoration"}:
            raise ManifestError(f"{label}.kind must be action or restoration")
        expected_raw = window["expected"]
        if not isinstance(expected_raw, list) or not expected_raw:
            raise ManifestError(f"{label}.expected must be a non-empty array")
        expected = tuple(
            _load_expectation(frame, f"{label}.expected[{frame_index}]")
            for frame_index, frame in enumerate(expected_raw)
        )
        pairs: set[tuple[str, bytes]] = set()
        sequences: list[int] = []
        for expectation in expected:
            if expectation.id in expectation_ids:
                raise ManifestError(f"duplicate expectation id: {expectation.id}")
            expectation_ids.add(expectation.id)
            pair = (expectation.direction, expectation.value)
            if pair in pairs:
                raise ManifestError(f"{label} repeats the same direction and frame")
            pairs.add(pair)
            if expectation.sequence is not None:
                sequences.append(expectation.sequence)
            predicted_brightness = _brightness(expectation.value, expectation.direction)
            if predicted_brightness is not None and predicted_brightness > normalised_limits["max_brightness_percent"]:
                raise ManifestError(
                    f"{label}/{expectation.id} predicts brightness {predicted_brightness}% above the safety limit"
                )
        if sequences and sorted(sequences) != list(range(1, len(sequences) + 1)):
            raise ManifestError(f"{label} sequence values must be contiguous from 1")
        if kind == "action" and not any(frame.direction == "TX" and frame.min_count > 0 for frame in expected):
            raise ManifestError(f"{label} needs at least one required TX frame")
        windows.append(
            VerificationWindow(
                id=window_id,
                kind=kind,
                operator=_load_operator(
                    window["operator"],
                    f"{label}.operator",
                    normalised_limits["max_action_seconds"],
                ),
                expected=expected,
            )
        )

    restoration = _mapping(raw["restoration"], "restoration")
    _exact_keys(restoration, {"packet_hex"}, set(), "restoration")
    packet_hex = restoration["packet_hex"]
    if not isinstance(packet_hex, list) or not packet_hex:
        raise ManifestError("restoration.packet_hex must be a non-empty array")
    restoration_packets = tuple(
        _frame(item, f"restoration.packet_hex[{index}]") for index, item in enumerate(packet_hex)
    )
    for packet in restoration_packets:
        if (
            restoration_brightness := _brightness(packet, "TX")
        ) is not None and restoration_brightness > normalised_limits["max_brightness_percent"]:
            raise ManifestError(f"restoration predicts brightness {restoration_brightness}% above the safety limit")
    restoration_expected = {
        frame.value
        for window in windows
        if window.kind == "restoration"
        for frame in window.expected
        if frame.direction == "TX" and frame.max_count > 0
    }
    missing_restoration = [packet.hex() for packet in restoration_packets if packet not in restoration_expected]
    if missing_restoration:
        raise ManifestError("restoration packets must be declared in restoration windows")

    return RunManifest(
        run_id=_identifier(raw["run_id"], "run_id"),
        task_id=_identifier(raw["task_id"], "task_id"),
        provenance=normalised_provenance,
        ownership=normalised_ownership,
        target=normalised_target,
        baseline=normalised_baseline,
        limits=normalised_limits,
        windows=tuple(windows),
        restoration_packets=restoration_packets,
    )


def load_manifest(path: Path) -> RunManifest:
    return load_manifest_data(json.loads(path.read_text()))


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _atomic_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def initialise_run(manifest_path: Path, run_dir: Path) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest_data = manifest.to_dict()
    prediction_data = manifest.prediction_dict()
    _atomic_json(run_dir / MANIFEST_FILE, manifest_data)
    _atomic_json(run_dir / PREDICTION_FILE, prediction_data)
    state = {
        "schema_version": SCHEMA_VERSION,
        "run_id": manifest.run_id,
        "status": "prepared",
        "phase": "prepared",
        "manifest_sha256": _digest(manifest_data),
        "prediction_sha256": _digest(prediction_data),
        "target_address": manifest.target_address,
        "target_handle": None,
        "pcap_path": None,
        "markers": [],
        "ownership_checks": {},
        "invalid_reason": None,
    }
    _atomic_json(run_dir / STATE_FILE, state)
    return state


def _load_run(run_dir: Path) -> tuple[RunManifest, dict[str, Any]]:
    manifest = load_manifest(run_dir / MANIFEST_FILE)
    state = json.loads((run_dir / STATE_FILE).read_text())
    if state.get("schema_version") != SCHEMA_VERSION or state.get("run_id") != manifest.run_id:
        raise RunError("run state does not match the manifest")
    if state.get("manifest_sha256") != _digest(manifest.to_dict()):
        raise RunError("frozen manifest hash mismatch")
    prediction = json.loads((run_dir / PREDICTION_FILE).read_text())
    if prediction != manifest.prediction_dict():
        raise RunError("frozen prediction differs from the manifest")
    if state.get("prediction_sha256") != _digest(prediction):
        raise RunError("frozen prediction hash mismatch")
    return manifest, state


def _snapshot_errors(manifest: RunManifest, snapshot: Any) -> list[str]:
    raw = _mapping(snapshot, "Home Assistant snapshot")
    required = {
        "config_entry_id",
        "entity_id",
        "entry_state",
        "disabled_by",
        "entity_available",
        *manifest.baseline.keys(),
    }
    _exact_keys(raw, required, set(), "Home Assistant snapshot")
    expected = {
        "config_entry_id": manifest.target["config_entry_id"],
        "entity_id": manifest.target["entity_id"],
        "entry_state": "loaded",
        "disabled_by": None,
        "entity_available": True,
        **manifest.baseline,
    }
    return [f"{key}: expected {expected[key]!r}, got {raw[key]!r}" for key in expected if raw[key] != expected[key]]


def _handoff_errors(manifest: RunManifest, snapshot: Any) -> list[str]:
    raw = _mapping(snapshot, "Home Assistant handoff snapshot")
    required = {"config_entry_id", "entity_id", "entry_state", "disabled_by"}
    _exact_keys(raw, required, set(), "Home Assistant handoff snapshot")
    expected = {
        "config_entry_id": manifest.target["config_entry_id"],
        "entity_id": manifest.target["entity_id"],
        "entry_state": "not_loaded",
        "disabled_by": "user",
    }
    return [f"{key}: expected {expected[key]!r}, got {raw[key]!r}" for key in expected if raw[key] != expected[key]]


def _retained_errors(manifest: RunManifest, snapshot: Any) -> list[str]:
    raw = _mapping(snapshot, "Govee Home ownership snapshot")
    required = {
        "config_entry_id",
        "entity_id",
        "entry_state",
        "disabled_by",
        "app_connected",
        *manifest.baseline.keys(),
    }
    _exact_keys(raw, required, set(), "Govee Home ownership snapshot")
    expected = {
        "config_entry_id": manifest.target["config_entry_id"],
        "entity_id": manifest.target["entity_id"],
        "entry_state": "not_loaded",
        "disabled_by": "user",
        "app_connected": True,
        **manifest.baseline,
    }
    return [f"{key}: expected {expected[key]!r}, got {raw[key]!r}" for key in expected if raw[key] != expected[key]]


def record_ownership_snapshot(run_dir: Path, stage: str, snapshot: Any) -> dict[str, Any]:
    stages = {"before", "handoff", "retained-before", "retained-after", "after"}
    if stage not in stages:
        raise RunError("ownership stage must be before, handoff, retained-before, retained-after, or after")
    manifest, state = _load_run(run_dir)
    if stage == "before" and (manifest.ownership["start"] != "home_assistant" or state["status"] != "prepared"):
        raise RunError("the before snapshot must be recorded before arming")
    if stage == "handoff" and (
        manifest.ownership["start"] != "home_assistant"
        or state["status"] != "prepared"
        or "before" not in state["ownership_checks"]
    ):
        raise RunError("the handoff snapshot must follow the before snapshot")
    if stage == "retained-before" and (manifest.ownership["start"] != "govee_home" or state["status"] != "prepared"):
        raise RunError("the retained-before snapshot requires a Govee Home start")
    if stage == "after" and (manifest.ownership["end"] != "home_assistant" or state["status"] != "awaiting_ha"):
        raise RunError("the after snapshot must follow the final settled marker")
    if stage == "retained-after" and (manifest.ownership["end"] != "govee_home" or state["status"] != "awaiting_govee"):
        raise RunError("the retained-after snapshot must follow the final settled marker")
    if stage == "handoff":
        errors = _handoff_errors(manifest, snapshot)
    elif stage in {"retained-before", "retained-after"}:
        errors = _retained_errors(manifest, snapshot)
    else:
        errors = _snapshot_errors(manifest, snapshot)
    if errors:
        if stage in {"handoff", "retained-after", "after"}:
            state["status"] = "needs_recovery"
            state["phase"] = "needs_recovery"
            state["invalid_reason"] = f"ownership {stage} mismatch: " + "; ".join(errors)
            _atomic_json(run_dir / STATE_FILE, state)
        raise RunError(f"ownership {stage} mismatch: " + "; ".join(errors))
    state["ownership_checks"][stage] = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "snapshot": snapshot,
    }
    if stage in {"retained-after", "after"}:
        state["status"] = "ready_for_analysis"
        state["phase"] = "ready_for_analysis"
    _atomic_json(run_dir / STATE_FILE, state)
    return state


def _utc(value: datetime | None) -> datetime:
    result = value or datetime.now(UTC)
    if result.tzinfo is None:
        raise RunError("marker timestamps must include a timezone")
    return result.astimezone(UTC)


def _capture_paths(pcap_path: Path) -> dict[str, Path]:
    return {
        "pcap": pcap_path.resolve(),
        "actions": pcap_path.with_suffix(".actions.tsv").resolve(),
        "meta": pcap_path.with_suffix(".meta.json").resolve(),
        "current": (pcap_path.parent / ".current").resolve(),
    }


def _active_capture(paths: dict[str, Path], prediction_sha256: str, timestamp: datetime) -> datetime:
    if not paths["pcap"].is_file() or not paths["actions"].is_file() or not paths["current"].is_file():
        raise RunError("capture pcap, actions sidecar, and active state must all exist")
    fields = paths["current"].read_text().strip().split()
    if len(fields) != 4:
        raise RunError("capture state does not include the frozen prediction hash")
    _pid, capture_name, started_at_text, capture_prediction = fields
    if capture_name != paths["pcap"].stem:
        raise RunError("active capture name differs from the armed pcap")
    if capture_prediction != prediction_sha256:
        raise RunError("active capture prediction hash mismatch")
    try:
        started_at = datetime.fromisoformat(started_at_text)
    except ValueError as exc:
        raise RunError("active capture start time is invalid") from exc
    if started_at.tzinfo is None or started_at.astimezone(UTC) > timestamp:
        raise RunError("active capture start time does not cover the marker")
    return started_at.astimezone(UTC)


def _append_action_marker(path: Path, event: dict[str, Any]) -> None:
    with path.open("a") as stream:
        stream.write(f"{event['at']}\t{event['marker']}\n")
        stream.flush()
        os.fsync(stream.fileno())


def _invalidate(run_dir: Path, state: dict[str, Any], reason: str) -> None:
    state["status"] = "needs_recovery"
    state["phase"] = "needs_recovery"
    state["invalid_reason"] = reason
    _atomic_json(run_dir / STATE_FILE, state)


def _window_and_stage(manifest: RunManifest, marker: str) -> tuple[VerificationWindow, str]:
    try:
        window_id, stage = marker.rsplit(":", 1)
    except ValueError as exc:
        raise RunError(f"invalid marker: {marker}") from exc
    window = next((item for item in manifest.windows if item.id == window_id), None)
    if window is None or stage not in {"before-action", "after-action", "settled"}:
        raise RunError(f"invalid marker: {marker}")
    return window, stage


def record_marker(
    run_dir: Path,
    marker: str,
    *,
    at: datetime | None = None,
    pcap_path: Path | None = None,
    viewer_healthy: bool,
    phone_unlocked: bool,
    target_confirmed: bool = False,
    displayed: str | None = None,
    visual: str | None = None,
) -> dict[str, Any]:
    manifest, state = _load_run(run_dir)
    if state["status"] not in {"prepared", "active"}:
        raise RunError(f"cannot record markers while run status is {state['status']}")
    expected_markers = manifest.marker_sequence()
    marker_index = len(state["markers"])
    if marker_index >= len(expected_markers) or marker != expected_markers[marker_index]:
        expected_marker = expected_markers[marker_index] if marker_index < len(expected_markers) else "none"
        reason = f"expected marker {expected_marker}, got {marker}"
        if state["status"] == "active":
            _invalidate(run_dir, state, reason)
        raise RunError(reason)
    timestamp = _utc(at)
    if state["markers"] and timestamp <= datetime.fromisoformat(state["markers"][-1]["at"]):
        _invalidate(run_dir, state, "marker timestamps are not strictly increasing")
        raise RunError("marker timestamps are not strictly increasing")
    if state["markers"]:
        previous = datetime.fromisoformat(state["markers"][-1]["at"])
        gap_seconds = (timestamp - previous).total_seconds()
        if gap_seconds > manifest.limits["max_marker_gap_seconds"]:
            reason = f"phone activity gap exceeded {manifest.limits['max_marker_gap_seconds']} seconds"
            _invalidate(run_dir, state, reason)
            raise RunError(reason)
        armed_at = datetime.fromisoformat(state["markers"][0]["at"])
        if (timestamp - armed_at).total_seconds() > manifest.limits["max_run_seconds"]:
            reason = "run exceeded its maximum duration"
            _invalidate(run_dir, state, reason)
            raise RunError(reason)

    armed_paths: dict[str, Path] | None = None
    if marker == "armed":
        if pcap_path is None:
            raise RunError("armed requires a pcap path")
        armed_paths = _capture_paths(pcap_path)
        state["pcap_path"] = str(armed_paths["pcap"])
        state["actions_path"] = str(armed_paths["actions"])
        state["meta_path"] = str(armed_paths["meta"])
        state["current_path"] = str(armed_paths["current"])
        state["status"] = "needs_recovery"
        state["phase"] = "arming"
        state["invalid_reason"] = "arming did not complete"
        _atomic_json(run_dir / STATE_FILE, state)

    if not viewer_healthy or not phone_unlocked:
        reason = "viewer unhealthy" if not viewer_healthy else "phone locked"
        _invalidate(run_dir, state, reason)
        raise RunError(reason)

    event: dict[str, Any] = {
        "marker": marker,
        "at": timestamp.isoformat(),
        "viewer_healthy": True,
        "phone_unlocked": True,
    }
    closed_window_count: int | None = None
    if marker == "armed":
        required_checks = (
            {"before", "handoff"} if manifest.ownership["start"] == "home_assistant" else {"retained-before"}
        )
        if not required_checks <= state["ownership_checks"].keys():
            _invalidate(run_dir, state, "run ownership start is not proven")
            raise RunError("record the required ownership snapshots before arming")
        if not target_confirmed:
            _invalidate(run_dir, state, "armed requires confirmed target identity and pcap")
            raise RunError("armed requires confirmed target identity and pcap")
        assert armed_paths is not None
        paths = armed_paths
        try:
            capture_started_at = _active_capture(paths, state["prediction_sha256"], timestamp)
        except RunError as exc:
            _invalidate(run_dir, state, str(exc))
            raise
        if paths["actions"].read_text():
            _invalidate(run_dir, state, "actions sidecar must be empty before armed")
            raise RunError("actions sidecar must be empty before armed")
        trace = dg.parse_capture(paths["pcap"].read_bytes(), allow_truncated=True)
        active = dg.active_connections_at(trace, timestamp)
        handles = [handle for handle, address in active.items() if address == manifest.target_address]
        candidates = {
            (record.connection_handle, record.address)
            for record in trace.att
            if record.timestamp <= timestamp and dg._is_govee(record.value)
        }
        if len(handles) != 1:
            reason = f"target address maps to {len(handles)} active connection handles"
            _invalidate(run_dir, state, reason)
            raise RunError(reason)
        if any(handle != handles[0] or address != manifest.target_address for handle, address in candidates):
            _invalidate(run_dir, state, "multiple or unattributed Govee connections before armed")
            raise RunError("multiple or unattributed Govee connections before armed")
        for record in trace.att:
            if record.timestamp > timestamp or not dg._is_govee(record.value):
                continue
            if (brightness := _brightness(record.value, record.direction)) is not None:
                if brightness > manifest.limits["max_brightness_percent"]:
                    reason = f"pre-armed brightness {brightness}% exceeds the safety limit"
                    _invalidate(run_dir, state, reason)
                    raise RunError(reason)
            if (
                record.connection_handle == handles[0]
                and record.address == manifest.target_address
                and record.direction == "TX"
                and record.value[0] in (0x33, 0xA3)
            ):
                _invalidate(run_dir, state, "pre-armed target state-changing TX")
                raise RunError("pre-armed target state-changing TX")
        state["target_handle"] = handles[0]
        state["capture_started_at"] = capture_started_at.isoformat()
        state["status"] = "active"
        state["invalid_reason"] = None
        event["target_confirmed"] = True
        event["target_handle"] = handles[0]
    else:
        paths = {key: Path(state[f"{key}_path"]) for key in ("pcap", "actions", "meta", "current")}
        try:
            _active_capture(paths, state["prediction_sha256"], timestamp)
        except RunError as exc:
            _invalidate(run_dir, state, str(exc))
            raise
        window, stage = _window_and_stage(manifest, marker)
        if stage == "before-action":
            try:
                _validate_live_idle(manifest, state, timestamp)
            except (OSError, RunError, ValueError) as exc:
                reason = f"pre-action validation failed: {exc}"
                _invalidate(run_dir, state, reason)
                raise RunError(reason) from exc
            if displayed != window.operator.expected_before:
                reason = f"{window.id} displayed value before action was not the frozen value"
                _invalidate(run_dir, state, reason)
                raise RunError(reason)
            event["displayed"] = displayed
        elif stage == "after-action":
            if displayed != window.operator.expected_after or visual != "confirmed":
                reason = f"{window.id} visual result is ambiguous or unexpected"
                _invalidate(run_dir, state, reason)
                raise RunError(reason)
            before = datetime.fromisoformat(state["markers"][-1]["at"])
            allowed = min(manifest.limits["max_action_seconds"], window.operator.max_wait_seconds)
            if (timestamp - before).total_seconds() > allowed:
                reason = f"{window.id} action exceeded {allowed} seconds"
                _invalidate(run_dir, state, reason)
                raise RunError(reason)
            event["displayed"] = displayed
            event["visual"] = visual
        else:
            after = datetime.fromisoformat(state["markers"][-1]["at"])
            settle_seconds = (timestamp - after).total_seconds()
            if not manifest.limits["min_settle_seconds"] <= settle_seconds <= manifest.limits["max_settle_seconds"]:
                reason = f"{window.id} settle interval was {settle_seconds:.3f} seconds"
                _invalidate(run_dir, state, reason)
                raise RunError(reason)
            closed_window_count = next(
                index for index, candidate in enumerate(manifest.windows, start=1) if candidate.id == window.id
            )

    try:
        _append_action_marker(Path(state["actions_path"]), event)
    except OSError as exc:
        reason = f"could not persist capture marker: {exc}"
        _invalidate(run_dir, state, reason)
        raise RunError(reason) from exc
    state["markers"].append(event)
    state["phase"] = marker
    if closed_window_count is not None:
        try:
            progress = _validate_live_progress(
                manifest,
                state,
                closed_window_count,
                timestamp,
            )
        except (OSError, RunError, ValueError) as exc:
            reason = f"live window validation failed: {exc}"
            _invalidate(run_dir, state, reason)
            raise RunError(reason) from exc
        if progress["verdict"] not in {"wire-pass", "tx-only-pass"}:
            detail = progress["errors"][0] if progress["errors"] else progress["verdict"]
            reason = f"live window validation failed: {detail}"
            _invalidate(run_dir, state, reason)
            raise RunError(reason)
        state["last_live_verdict"] = progress["verdict"]
    if len(state["markers"]) == len(expected_markers):
        state["status"] = "awaiting_ha" if manifest.ownership["end"] == "home_assistant" else "awaiting_govee"
        state["phase"] = state["status"]
    _atomic_json(run_dir / STATE_FILE, state)
    return state


def invalidate_run(run_dir: Path, reason: str) -> dict[str, Any]:
    _, state = _load_run(run_dir)
    if state["status"] in {"complete", "invalid_recovered"}:
        raise RunError(f"run is already terminal: {state['status']}")
    _invalidate(run_dir, state, _text(reason, "reason"))
    return state


def complete_recovery(run_dir: Path, snapshot: Any) -> dict[str, Any]:
    manifest, state = _load_run(run_dir)
    if state["status"] != "needs_recovery":
        raise RunError("recovery is valid only for a run marked needs_recovery")
    errors = (
        _snapshot_errors(manifest, snapshot)
        if manifest.ownership["end"] == "home_assistant"
        else _retained_errors(manifest, snapshot)
    )
    if errors:
        raise RunError("recovery baseline mismatch: " + "; ".join(errors))
    artifacts = {
        "manifest": {
            "path": str(run_dir / MANIFEST_FILE),
            "sha256": _file_sha256(run_dir / MANIFEST_FILE),
        },
        "prediction": {
            "path": str(run_dir / PREDICTION_FILE),
            "sha256": _file_sha256(run_dir / PREDICTION_FILE),
        },
    }
    artifact_errors: list[str] = []
    if state["pcap_path"] is not None:
        current_path = Path(state["current_path"])
        if current_path.exists():
            raise RunError("capture is still active; stop it before completing recovery")
        marker_times = _marker_times(state)
        armed_at = marker_times.get("armed")
        end_at = max(marker_times.values()) if marker_times else None
        try:
            artifacts, _started_at, _stopped_at = _capture_artifacts(
                run_dir,
                state,
                armed_at,
                end_at,
            )
        except RunError as exc:
            artifact_errors.append(str(exc))
            for key in ("pcap", "actions", "meta"):
                path = Path(state[f"{key}_path"])
                if path.is_file():
                    artifacts[key] = {"path": str(path), "sha256": _file_sha256(path)}
    state["ownership_checks"]["recovery"] = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "snapshot": snapshot,
    }
    state["status"] = "invalid_recovered"
    state["phase"] = "invalid_recovered"
    report = {
        "schema_version": SCHEMA_VERSION,
        "run_id": manifest.run_id,
        "task_id": manifest.task_id,
        "simulation": False,
        "verdict": "invalid",
        "prediction_sha256": state["prediction_sha256"],
        "manifest_sha256": state["manifest_sha256"],
        "provenance": dict(manifest.provenance),
        "target": {
            "address": manifest.target_address,
            "connection_handle": state["target_handle"],
        },
        "windows": [],
        "restoration_source": (
            "home-assistant-readback" if manifest.ownership["end"] == "home_assistant" else "govee-home-readback"
        ),
        "restoration": {
            "source": (
                "home-assistant-readback" if manifest.ownership["end"] == "home_assistant" else "govee-home-readback"
            ),
            "required_tx": [packet.hex() for packet in manifest.restoration_packets],
            "observed_tx": [],
        },
        "markers": list(state["markers"]),
        "ownership": {
            "boundary": dict(manifest.ownership),
            "checks": dict(state["ownership_checks"]),
        },
        "frames": [],
        "errors": [state["invalid_reason"], *artifact_errors],
        "extra_rx": [],
        "artifacts": artifacts,
    }
    _write_report(run_dir, report)
    _atomic_json(run_dir / STATE_FILE, state)
    return state


def _marker_times(state: dict[str, Any]) -> dict[str, datetime]:
    return {item["marker"]: datetime.fromisoformat(item["at"]) for item in state["markers"]}


def _brightness(value: bytes, direction: str) -> int | None:
    if direction == "TX" and value[:2] == b"\x33\x04":
        return value[2]
    if direction == "TX" and value[:4] == b"\x33\x05\x15\x02":
        return value[4]
    if direction == "RX" and value[:2] == b"\xaa\x04":
        return value[2]
    if direction == "RX" and value[:4] == b"\xaa\x05\x15\x02":
        return value[4]
    return None


def _window_records(
    records: tuple[dg.AttRecord, ...],
    start: datetime,
    end: datetime,
) -> tuple[dg.AttRecord, ...]:
    return tuple(record for record in records if start <= record.timestamp <= end)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _capture_artifacts(
    run_dir: Path,
    state: dict[str, Any],
    armed_at: datetime | None,
    end_at: datetime | None,
) -> tuple[dict[str, Any], datetime, datetime]:
    pcap = Path(state["pcap_path"])
    actions = Path(state["actions_path"])
    meta = Path(state["meta_path"])
    if not pcap.is_file() or not actions.is_file() or not meta.is_file():
        raise RunError("pcap, actions, and capture metadata must exist before analysis")

    expected_actions = [f"{marker['at']}\t{marker['marker']}" for marker in state["markers"]]
    if actions.read_text().splitlines() != expected_actions:
        raise RunError("actions sidecar differs from persisted run markers")

    try:
        metadata = json.loads(meta.read_text())
    except json.JSONDecodeError as exc:
        raise RunError("capture metadata is not valid JSON") from exc
    if not isinstance(metadata, dict):
        raise RunError("capture metadata must be an object")
    required = {"capture", "started_at", "stopped_at", "actions", "prediction_sha256"}
    if not required <= metadata.keys():
        raise RunError("capture metadata is incomplete")
    if metadata["capture"] != pcap.stem or metadata["actions"] != actions.name:
        raise RunError("capture metadata names do not match the armed artifacts")
    if metadata["prediction_sha256"] != state["prediction_sha256"]:
        raise RunError("capture metadata prediction hash mismatch")
    if not isinstance(metadata["started_at"], str) or not isinstance(metadata["stopped_at"], str):
        raise RunError("capture metadata timestamps must be strings")
    try:
        started_at = datetime.fromisoformat(metadata["started_at"])
        stopped_at = datetime.fromisoformat(metadata["stopped_at"])
    except ValueError as exc:
        raise RunError("capture metadata timestamps are invalid") from exc
    if started_at.tzinfo is None or stopped_at.tzinfo is None:
        raise RunError("capture metadata timestamps must include a timezone")
    if stopped_at < started_at:
        raise RunError("capture metadata stop time precedes its start time")
    started_at = started_at.astimezone(UTC)
    stopped_at = stopped_at.astimezone(UTC)
    if armed_at is not None and end_at is not None and (started_at > armed_at or stopped_at < end_at):
        raise RunError("capture metadata does not cover every persisted marker")

    return (
        {
            "pcap": {"path": str(pcap), "sha256": _file_sha256(pcap)},
            "actions": {"path": str(actions), "sha256": _file_sha256(actions)},
            "capture_metadata": {
                "path": str(meta),
                "sha256": _file_sha256(meta),
                "started_at": started_at.isoformat(),
                "stopped_at": stopped_at.isoformat(),
            },
            "manifest": {
                "path": str(run_dir / MANIFEST_FILE),
                "sha256": _file_sha256(run_dir / MANIFEST_FILE),
            },
            "prediction": {
                "path": str(run_dir / PREDICTION_FILE),
                "sha256": _file_sha256(run_dir / PREDICTION_FILE),
            },
        },
        started_at,
        stopped_at,
    )


def _verdict(
    errors: list[str],
    action_confirmations: list[bool],
    required_action_tx_observed: bool,
) -> str:
    if not errors:
        return "wire-pass" if action_confirmations and all(action_confirmations) else "tx-only-pass"
    invalid_markers = (
        "unattributed Govee frame",
        "brightness ",
        "capture ",
        "actions sidecar",
        "target connection disconnected",
        "target reconnected",
        "pre-armed target state-changing TX",
        "post-settled target TX",
        "delayed or settle-window TX",
        "unwindowed target TX",
    )
    if any(error.startswith(invalid_markers) or any(marker in error for marker in invalid_markers) for error in errors):
        return "invalid"
    if not required_action_tx_observed and all(" observed 0, expected " in error for error in errors):
        return "no-write"
    return "mismatch"


def _report_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# {report['run_id']} evidence",
        "",
        f"**Verdict:** `{report['verdict']}`",
        "",
        f"**Prediction SHA-256:** `{report['prediction_sha256']}`",
        "",
        f"**Integration commit:** `{report['provenance']['integration_commit']}`",
        "",
        f"**Govee app build:** `{report['provenance']['app_build']}`",
        "",
        f"**Device firmware:** `{report['provenance']['device_firmware']}`",
        "",
        f"**Catalogue SHA-256:** `{report['provenance']['catalogue_sha256']}`",
        "",
        "| Window | TX result | State confirmation | Result |",
        "| --- | --- | --- | --- |",
    ]
    for window in report["windows"]:
        lines.append(
            f"| {window['id']} | {window['tx_result']} | {window['state_confirmation']} | {window['result']} |"
        )
    lines.extend(
        [
            "",
            f"**Restoration source:** {report['restoration_source']}",
            "",
        ]
    )
    if report["errors"]:
        lines.extend(["## Errors", "", *(f"- {error}" for error in report["errors"]), ""])
    if report["extra_rx"]:
        lines.extend(["## Additional target RX", "", *(f"- `{frame}`" for frame in report["extra_rx"]), ""])
    return "\n".join(lines)


def evaluate_run(
    manifest: RunManifest,
    state: dict[str, Any],
    records: tuple[dg.AttRecord, ...],
    *,
    connection_events: tuple[dg.ConnectionEvent, ...] = (),
    window_count: int | None = None,
    capture_start: datetime | None = None,
    capture_end: datetime | None = None,
    simulation: bool = False,
) -> dict[str, Any]:
    markers = _marker_times(state)
    windows = manifest.windows[:window_count] if window_count is not None else manifest.windows
    if not windows:
        raise RunError("at least one closed window is required for evaluation")
    armed_at = markers["armed"]
    end_at = markers[f"{windows[-1].id}:settled"]
    guard_start = capture_start or armed_at
    guard_end = capture_end or end_at
    target_handle = state["target_handle"]
    errors: list[str] = []
    extra_rx: list[str] = []
    guard_records = tuple(
        record for record in records if guard_start <= record.timestamp <= guard_end and dg._is_govee(record.value)
    )
    run_records = tuple(record for record in guard_records if armed_at <= record.timestamp <= end_at)

    for event in connection_events:
        if not guard_start < event.timestamp <= guard_end:
            continue
        if event.connection_handle == target_handle and not event.connected:
            errors.append(f"target connection disconnected at {event.timestamp.isoformat()}")
        if event.connected and event.address == manifest.target_address and event.connection_handle != target_handle:
            errors.append(
                f"target reconnected on handle {event.connection_handle:#06x} at {event.timestamp.isoformat()}"
            )

    for record in guard_records:
        if record.connection_handle != target_handle or record.address != manifest.target_address:
            errors.append(
                f"unattributed Govee frame at {record.timestamp.isoformat()} "
                f"handle={record.connection_handle:#06x} address={record.address}"
            )
        if (brightness := _brightness(record.value, record.direction)) is not None:
            if brightness > manifest.limits["max_brightness_percent"]:
                errors.append(
                    f"brightness {brightness}% exceeds {manifest.limits['max_brightness_percent']}% "
                    f"at {record.timestamp.isoformat()}"
                )
        if (
            record.timestamp < armed_at
            and record.connection_handle == target_handle
            and record.address == manifest.target_address
            and record.direction == "TX"
            and record.value[0] in (0x33, 0xA3)
        ):
            errors.append(f"pre-armed target state-changing TX {record.value.hex()}")
        if record.timestamp > end_at and record.direction == "TX":
            errors.append(f"post-settled target TX {record.value.hex()}")

    covered: set[int] = set()
    window_reports: list[dict[str, Any]] = []
    restoration_records: list[dg.AttRecord] = []
    action_confirmations: list[bool] = []
    required_action_tx_observed = False
    for window in windows:
        before = markers[f"{window.id}:before-action"]
        after = markers[f"{window.id}:after-action"]
        settled = markers[f"{window.id}:settled"]
        primary = _window_records(run_records, before, after)
        settle = tuple(record for record in run_records if after < record.timestamp <= settled)
        for record in (*primary, *settle):
            covered.add(id(record))
        if window.kind == "restoration":
            restoration_records.extend(record for record in primary if record.direction == "TX")

        counts: dict[str, int] = {}
        matched_ids: dict[int, str] = {}
        confirmation = False
        for expectation in window.expected:
            matched = [
                record
                for record in primary
                if record.direction == expectation.direction and record.value == expectation.value
            ]
            counts[expectation.id] = len(matched)
            for record in matched:
                matched_ids[id(record)] = expectation.id
            if not expectation.min_count <= len(matched) <= expectation.max_count:
                errors.append(
                    f"{window.id}/{expectation.id} observed {len(matched)}, "
                    f"expected {expectation.min_count}..{expectation.max_count}"
                )
            if expectation.state_confirmation:
                conflicting = [
                    record
                    for record in primary
                    if record.direction == "RX"
                    and record.value[:2] == expectation.value[:2]
                    and record.value != expectation.value
                ]
                if conflicting:
                    errors.append(f"{window.id}/{expectation.id} received a conflicting state reply")

        required_tx_records = [
            record
            for expectation in window.expected
            if expectation.direction == "TX" and expectation.min_count > 0
            for record in primary
            if record.direction == "TX" and record.value == expectation.value
        ]
        last_required_tx = max(record.timestamp for record in required_tx_records) if required_tx_records else None
        for expectation in window.expected:
            if not expectation.state_confirmation:
                continue
            matching_rx = [
                record for record in primary if record.direction == "RX" and record.value == expectation.value
            ]
            causal_rx = [
                record for record in matching_rx if last_required_tx is not None and record.timestamp > last_required_tx
            ]
            if matching_rx and not causal_rx:
                errors.append(f"{window.id}/{expectation.id} state confirmation preceded required TX")
            if causal_rx:
                confirmation = True

        unexpected_tx = [record for record in primary if record.direction == "TX" and id(record) not in matched_ids]
        for record in unexpected_tx:
            errors.append(f"{window.id} unexpected TX {record.value.hex()}")
        for record in settle:
            if record.direction == "TX":
                errors.append(f"{window.id} delayed or settle-window TX {record.value.hex()}")
            elif id(record) not in matched_ids:
                extra_rx.append(record.value.hex())
        for record in primary:
            if record.direction == "RX" and id(record) not in matched_ids:
                extra_rx.append(record.value.hex())

        sequenced = sorted(
            (expectation for expectation in window.expected if expectation.sequence is not None),
            key=lambda expectation: expectation.sequence or 0,
        )
        if sequenced:
            expected_order = [expectation.id for expectation in sequenced]
            actual_order = [
                matched_ids[id(record)]
                for record in primary
                if record.direction == "TX" and id(record) in matched_ids and matched_ids[id(record)] in expected_order
            ]
            if actual_order != expected_order:
                errors.append(f"{window.id} TX order was {actual_order}, expected {expected_order}")

        required_tx_ok = all(
            counts[expectation.id] >= expectation.min_count
            for expectation in window.expected
            if expectation.direction == "TX"
        )
        window_error = any(error.startswith(f"{window.id}/") or error.startswith(f"{window.id} ") for error in errors)
        if window.kind == "action":
            action_confirmations.append(confirmation)
            required_action_tx_observed = required_action_tx_observed or bool(required_tx_records)
        window_reports.append(
            {
                "id": window.id,
                "kind": window.kind,
                "counts": counts,
                "tx_result": "pass" if required_tx_ok and not unexpected_tx else "fail",
                "state_confirmation": "target-rx" if confirmation else "none",
                "result": "fail" if window_error else "pass",
            }
        )

    for record in run_records:
        if id(record) not in covered and record.direction == "TX":
            errors.append(f"unwindowed target TX {record.value.hex()} at {record.timestamp.isoformat()}")

    restoration_seen = {record.value for record in restoration_records}
    restoration_wire = all(packet in restoration_seen for packet in manifest.restoration_packets)
    restoration_source = (
        "wire"
        if restoration_wire
        else ("home-assistant-readback" if manifest.ownership["end"] == "home_assistant" else "govee-home-readback")
    )
    verdict = _verdict(errors, action_confirmations, required_action_tx_observed)
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": manifest.run_id,
        "task_id": manifest.task_id,
        "simulation": simulation,
        "verdict": verdict,
        "prediction_sha256": state["prediction_sha256"],
        "manifest_sha256": state["manifest_sha256"],
        "provenance": dict(manifest.provenance),
        "target": {
            "address": manifest.target_address,
            "connection_handle": target_handle,
        },
        "windows": window_reports,
        "restoration_source": restoration_source,
        "restoration": {
            "source": restoration_source,
            "required_tx": [packet.hex() for packet in manifest.restoration_packets],
            "observed_tx": sorted(record.value.hex() for record in restoration_records),
        },
        "markers": list(state["markers"]),
        "ownership": {
            "boundary": dict(manifest.ownership),
            "checks": dict(state["ownership_checks"]),
        },
        "frames": [
            {
                "timestamp": record.timestamp.isoformat(),
                "direction": record.direction,
                "connection_handle": record.connection_handle,
                "address": record.address,
                "hex": record.value.hex(),
                "label": dg.label(record.value, record.direction),
            }
            for record in guard_records
        ],
        "errors": errors,
        "extra_rx": sorted(set(extra_rx)),
    }


def _validate_live_progress(
    manifest: RunManifest,
    state: dict[str, Any],
    window_count: int,
    timestamp: datetime,
) -> dict[str, Any]:
    capture_start = datetime.fromisoformat(state["capture_started_at"])
    report: dict[str, Any] | None = None
    for attempt in range(11):
        trace = dg.parse_capture(
            Path(state["pcap_path"]).read_bytes(),
            allow_truncated=True,
        )
        report = evaluate_run(
            manifest,
            state,
            trace.att,
            connection_events=trace.connections,
            window_count=window_count,
            capture_start=capture_start,
            capture_end=timestamp,
        )
        missing_only = bool(report["errors"]) and all(" observed 0, expected " in error for error in report["errors"])
        if not missing_only or attempt == 10:
            return report
        time.sleep(0.1)
    raise RunError("live validation did not produce a verdict")


def _validate_live_idle(
    manifest: RunManifest,
    state: dict[str, Any],
    timestamp: datetime,
) -> None:
    armed_at = datetime.fromisoformat(state["markers"][0]["at"])
    settled_times = [
        datetime.fromisoformat(marker["at"]) for marker in state["markers"] if marker["marker"].endswith(":settled")
    ]
    idle_start = max(settled_times, default=armed_at)
    capture_start = datetime.fromisoformat(state["capture_started_at"])
    for attempt in range(2):
        trace = dg.parse_capture(
            Path(state["pcap_path"]).read_bytes(),
            allow_truncated=True,
        )
        records = tuple(
            record
            for record in trace.att
            if capture_start <= record.timestamp <= timestamp and dg._is_govee(record.value)
        )
        errors: list[str] = []
        for event in trace.connections:
            if not capture_start < event.timestamp <= timestamp:
                continue
            if event.connection_handle == state["target_handle"] and not event.connected:
                errors.append("target connection disconnected before action")
            if (
                event.connected
                and event.address == manifest.target_address
                and event.connection_handle != state["target_handle"]
            ):
                errors.append("target reconnected before action")
        for record in records:
            if record.connection_handle != state["target_handle"] or record.address != manifest.target_address:
                errors.append("unattributed Govee frame before action")
            if (brightness := _brightness(record.value, record.direction)) is not None:
                if brightness > manifest.limits["max_brightness_percent"]:
                    errors.append(f"brightness {brightness}% exceeds the safety limit before action")
            if record.timestamp < armed_at and record.direction == "TX" and record.value[0] in (0x33, 0xA3):
                errors.append("pre-armed target state-changing TX")
            if idle_start < record.timestamp <= timestamp and record.direction == "TX":
                errors.append(f"unwindowed target TX before action {record.value.hex()}")
        if errors:
            raise RunError(errors[0])
        if attempt == 0:
            time.sleep(0.1)


def _write_report(run_dir: Path, report: dict[str, Any]) -> None:
    _atomic_json(run_dir / EVIDENCE_JSON, report)
    markdown = run_dir / EVIDENCE_MARKDOWN
    temporary = markdown.with_suffix(".md.tmp")
    temporary.write_text(_report_markdown(report))
    os.chmod(temporary, 0o600)
    os.replace(temporary, markdown)


def analyse_run(run_dir: Path, pcap_path: Path | None = None) -> dict[str, Any]:
    manifest, state = _load_run(run_dir)
    if state["status"] != "ready_for_analysis":
        raise RunError("run must have a verified end-ownership snapshot before analysis")
    capture_path = Path(state["pcap_path"])
    if pcap_path is not None and pcap_path.resolve() != capture_path:
        raise RunError("analysis pcap differs from the pcap frozen at armed")
    trace = dg.parse_capture(capture_path.read_bytes())
    markers = _marker_times(state)
    artifact_error: str | None = None
    try:
        artifacts, capture_start, capture_end = _capture_artifacts(
            run_dir,
            state,
            markers["armed"],
            markers[f"{manifest.windows[-1].id}:settled"],
        )
    except RunError as exc:
        artifact_error = str(exc)
        artifacts = {}
        capture_start = datetime.fromisoformat(state["capture_started_at"])
        observed_times = [
            *(record.timestamp for record in trace.att),
            *(event.timestamp for event in trace.connections),
            markers[f"{manifest.windows[-1].id}:settled"],
        ]
        capture_end = max(observed_times)
    report = evaluate_run(
        manifest,
        state,
        trace.att,
        connection_events=trace.connections,
        capture_start=capture_start,
        capture_end=capture_end,
    )
    report["artifacts"] = artifacts
    if artifact_error is not None:
        report["errors"].append(artifact_error)
        report["verdict"] = "invalid"
    _write_report(run_dir, report)
    state["status"] = "complete"
    state["phase"] = "complete"
    state["verdict"] = report["verdict"]
    _atomic_json(run_dir / STATE_FILE, state)
    return report


def _simulation_state(manifest: RunManifest, state: dict[str, Any]) -> tuple[dict[str, Any], tuple[dg.AttRecord, ...]]:
    start = datetime.now(UTC)
    handle = 0x0040
    markers: list[dict[str, Any]] = [
        {
            "marker": "armed",
            "at": start.isoformat(),
            "viewer_healthy": True,
            "phone_unlocked": True,
            "target_confirmed": True,
            "target_handle": handle,
        }
    ]
    records: list[dg.AttRecord] = []
    cursor = start
    for window in manifest.windows:
        before = cursor + timedelta(seconds=1)
        after = before + timedelta(seconds=1)
        settled = after + timedelta(seconds=manifest.limits["min_settle_seconds"])
        markers.extend(
            (
                {
                    "marker": f"{window.id}:before-action",
                    "at": before.isoformat(),
                    "viewer_healthy": True,
                    "phone_unlocked": True,
                    "displayed": window.operator.expected_before,
                },
                {
                    "marker": f"{window.id}:after-action",
                    "at": after.isoformat(),
                    "viewer_healthy": True,
                    "phone_unlocked": True,
                    "displayed": window.operator.expected_after,
                    "visual": "confirmed",
                },
                {
                    "marker": f"{window.id}:settled",
                    "at": settled.isoformat(),
                    "viewer_healthy": True,
                    "phone_unlocked": True,
                },
            )
        )
        included: list[FrameExpectation] = []
        for expectation in window.expected:
            count = expectation.min_count
            if expectation.state_confirmation or (
                window.kind == "restoration" and expectation.value in manifest.restoration_packets
            ):
                count = max(count, 1)
            included.extend([expectation] * count)
        included.sort(key=lambda item: item.sequence if item.sequence is not None else 1000)
        step = (after - before) / (len(included) + 1)
        for index, expectation in enumerate(included, start=1):
            records.append(
                dg.AttRecord(
                    timestamp=before + step * index,
                    direction=expectation.direction,
                    connection_handle=handle,
                    address=manifest.target_address,
                    opcode=0x52 if expectation.direction == "TX" else 0x1B,
                    attribute_handle=0x0025,
                    value=expectation.value,
                )
            )
        cursor = settled
    snapshot = {
        "config_entry_id": manifest.target["config_entry_id"],
        "entity_id": manifest.target["entity_id"],
        "entry_state": "loaded",
        "disabled_by": None,
        "entity_available": True,
        **manifest.baseline,
    }
    retained = {
        "config_entry_id": manifest.target["config_entry_id"],
        "entity_id": manifest.target["entity_id"],
        "entry_state": "not_loaded",
        "disabled_by": "user",
        "app_connected": True,
        **manifest.baseline,
    }
    state["target_handle"] = handle
    state["markers"] = markers
    ownership_checks: dict[str, Any] = {}
    if manifest.ownership["start"] == "home_assistant":
        ownership_checks["before"] = {"recorded_at": start.isoformat(), "snapshot": snapshot}
        ownership_checks["handoff"] = {
            "recorded_at": start.isoformat(),
            "snapshot": {
                "config_entry_id": manifest.target["config_entry_id"],
                "entity_id": manifest.target["entity_id"],
                "entry_state": "not_loaded",
                "disabled_by": "user",
            },
        }
    else:
        ownership_checks["retained-before"] = {
            "recorded_at": start.isoformat(),
            "snapshot": retained,
        }
    end_stage = "after" if manifest.ownership["end"] == "home_assistant" else "retained-after"
    ownership_checks[end_stage] = {
        "recorded_at": cursor.isoformat(),
        "snapshot": snapshot if end_stage == "after" else retained,
    }
    state["ownership_checks"] = ownership_checks
    state["status"] = "ready_for_analysis"
    state["phase"] = "ready_for_analysis"
    return state, tuple(records)


def simulate_run(manifest_path: Path, run_dir: Path) -> dict[str, Any]:
    initialise_run(manifest_path, run_dir)
    manifest, state = _load_run(run_dir)
    state, records = _simulation_state(manifest, state)
    report = evaluate_run(manifest, state, records, simulation=True)
    report["artifacts"] = {
        "manifest": {
            "path": str(run_dir / MANIFEST_FILE),
            "sha256": _file_sha256(run_dir / MANIFEST_FILE),
        },
        "prediction": {
            "path": str(run_dir / PREDICTION_FILE),
            "sha256": _file_sha256(run_dir / PREDICTION_FILE),
        },
    }
    _write_report(run_dir, report)
    state["status"] = "complete"
    state["phase"] = "complete"
    state["verdict"] = report["verdict"]
    _atomic_json(run_dir / STATE_FILE, state)
    return report


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def _parse_time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    initialise = commands.add_parser("init")
    initialise.add_argument("manifest", type=Path)
    initialise.add_argument("run_dir", type=Path)

    ownership = commands.add_parser("ownership")
    ownership.add_argument("run_dir", type=Path)
    ownership.add_argument(
        "stage",
        choices=("before", "handoff", "retained-before", "retained-after", "after"),
    )
    ownership.add_argument("snapshot", type=Path)

    mark = commands.add_parser("mark")
    mark.add_argument("run_dir", type=Path)
    mark.add_argument("marker")
    mark.add_argument("--at")
    mark.add_argument("--pcap", type=Path)
    mark.add_argument("--viewer-healthy", action="store_true")
    mark.add_argument("--phone-unlocked", action="store_true")
    mark.add_argument("--target-confirmed", action="store_true")
    mark.add_argument("--displayed")
    mark.add_argument("--visual", choices=("confirmed", "ambiguous"))

    analyse = commands.add_parser("analyse")
    analyse.add_argument("run_dir", type=Path)
    analyse.add_argument("--pcap", type=Path)

    invalidate = commands.add_parser("invalidate")
    invalidate.add_argument("run_dir", type=Path)
    invalidate.add_argument("reason")

    recover = commands.add_parser("recover")
    recover.add_argument("run_dir", type=Path)
    recover.add_argument("snapshot", type=Path)

    simulate = commands.add_parser("simulate")
    simulate.add_argument("manifest", type=Path)
    simulate.add_argument("run_dir", type=Path)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        match args.command:
            case "init":
                state = initialise_run(args.manifest, args.run_dir)
                print(f"prepared {state['run_id']} prediction_sha256={state['prediction_sha256']}")
            case "ownership":
                record_ownership_snapshot(args.run_dir, args.stage, _read_json(args.snapshot))
                print(f"recorded {args.stage} ownership")
            case "mark":
                record_marker(
                    args.run_dir,
                    args.marker,
                    at=_parse_time(args.at),
                    pcap_path=args.pcap,
                    viewer_healthy=args.viewer_healthy,
                    phone_unlocked=args.phone_unlocked,
                    target_confirmed=args.target_confirmed,
                    displayed=args.displayed,
                    visual=args.visual,
                )
                print(f"recorded {args.marker}")
            case "analyse":
                report = analyse_run(args.run_dir, args.pcap)
                print(report["verdict"])
            case "invalidate":
                invalidate_run(args.run_dir, args.reason)
                print("run requires recovery")
            case "recover":
                complete_recovery(args.run_dir, _read_json(args.snapshot))
                print("invalid run recovered; create a new run id")
            case "simulate":
                report = simulate_run(args.manifest, args.run_dir)
                print(report["verdict"])
    except (ManifestError, RunError, OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
