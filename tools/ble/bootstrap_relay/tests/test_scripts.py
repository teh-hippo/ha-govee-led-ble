from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = (
    ROOT / "ai-lab.sh",
    ROOT / "baseline.sh",
    ROOT / "ha-platform.sh",
    ROOT / "rehearse-infra.sh",
    ROOT / "run-a.sh",
    ROOT / "windows-ble.sh",
)


def test_all_shell_entry_points_parse():
    for script in SCRIPTS:
        subprocess.run(  # noqa: S603 - fixed local bash syntax check
            ("/usr/bin/bash", "-n", str(script)),
            check=True,
        )


def test_run_a_recovery_uses_global_state_and_long_deadline():
    run_a = (ROOT / "run-a.sh").read_text()
    ai_lab = (ROOT / "ai-lab.sh").read_text()
    assert 'active_run_id=""' in run_a
    assert 'proxmox stop "$active_run_id"' in run_a
    assert '[ -e "$active_unifi_state" ]' in run_a
    assert "DEVICE_SNIFF_ADDRESS" not in run_a
    assert "--deadline-seconds 180" in ai_lab


def test_direct_ble_uses_windows_no_response_writes():
    ai_lab = (ROOT / "ai-lab.sh").read_text()
    run_a = (ROOT / "run-a.sh").read_text()
    windows_ble = (ROOT / "windows-ble.sh").read_text()
    assert "provision) provision" not in ai_lab
    assert "query-versions) query_versions" not in ai_lab
    assert "windows_ble provision" in run_a
    assert "HARNESS_BLE_BACKEND=windows" in windows_ble
    assert "--response no" in windows_ble
    assert 'network="$(cat)"' in windows_ble
    assert windows_ble.index('network="$(cat)"') < windows_ble.index('source "$repo/tools/harness/phone.sh"')
    assert "BLE_WRITE_INTENT_PATH" in windows_ble
    assert '[ -e "$ble_write_intent" ]' in run_a
    assert "take-device-b" in run_a
    assert "MUTATE-MQTT-ADDRESS-ONLY" in ai_lab
    assert "--stop-on-dns-match" in ai_lab
    assert "probe-client-hello" in ai_lab
    assert "take-device-c" in run_a
    assert "capture-mqtt-connect" in ai_lab
    assert "take-device-d" in run_a
    assert run_a.index('windows_ble provision >"$restore_log"') < run_a.index(
        'grep -q \'"event":"mqtt_connect_shape"\''
    )
