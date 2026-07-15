import os
import subprocess
from datetime import datetime
from pathlib import Path

_SCRIPT = Path(__file__).parents[1] / "tools" / "ble" / "govee-capture.sh"


def _capture_env(tmp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "GOVEE_BLE_DIR": str(tmp_path),
            "GOVEE_WIN_CAP": "C:\\captures",
            "GOVEE_BTLOGGER": "C:\\tools\\idevicebtlogger.exe",
            "PWSH": "pwsh.exe",
        }
    )
    return env


def test_mark_records_timestamped_batch_action(tmp_path: Path):
    captures = tmp_path / "captures"
    captures.mkdir()
    (captures / ".current").write_text(f"123 batch-run 2026-07-13T15:00:00+10:00 {'a' * 64}\n")

    result = subprocess.run(  # noqa: S603
        ["/bin/bash", str(_SCRIPT), "mark", "Bloom", "Dynamic"],
        check=True,
        capture_output=True,
        text=True,
        env=_capture_env(tmp_path),
    )

    timestamp, label = (captures / "batch-run.actions.tsv").read_text().rstrip().split("\t", 1)
    assert datetime.fromisoformat(timestamp)
    assert label == "Bloom Dynamic"
    assert result.stdout.strip() == "marked 'Bloom Dynamic'"


def test_mark_requires_active_capture(tmp_path: Path):
    result = subprocess.run(  # noqa: S603
        ["/bin/bash", str(_SCRIPT), "mark", "Bloom Dynamic"],
        check=False,
        capture_output=True,
        text=True,
        env=_capture_env(tmp_path),
    )

    assert result.returncode == 1
    assert result.stdout.strip() == "no capture running"


def test_start_rejects_invalid_prediction_hash(tmp_path: Path):
    result = subprocess.run(  # noqa: S603
        ["/bin/bash", str(_SCRIPT), "start", "batch-run", "not-a-hash"],
        check=False,
        capture_output=True,
        text=True,
        env=_capture_env(tmp_path),
    )

    assert result.returncode == 1
    assert "prediction SHA-256" in result.stderr
