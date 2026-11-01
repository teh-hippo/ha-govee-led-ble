"""Repository ownership boundaries for external capture and physical tooling."""

import shutil
import subprocess
from pathlib import Path

_REPO = Path(__file__).parents[1]
_IMPLEMENTATION_SUFFIXES = {".js", ".mjs", ".ps1", ".py", ".sh", ".ts"}
_EXTERNAL_IMPLEMENTATION_MARKERS = (
    "capture",
    "phone",
    "physical-lab",
    "physical_lab",
    "provision",
    "wda",
)


def _tracked_files() -> set[Path]:
    git = shutil.which("git")
    assert git is not None
    output = subprocess.check_output((git, "ls-files", "-z"), cwd=_REPO)  # noqa: S603 - fixed Git arguments
    return {
        path for raw_path in output.split(b"\0") if raw_path and (_REPO / (path := Path(raw_path.decode()))).is_file()
    }


def test_external_capture_and_physical_implementations_are_not_tracked() -> None:
    tracked = _tracked_files()
    offenders = {
        path
        for path in tracked
        if path.parts[:2] == ("tools", "harness")
        or path.suffix in {".pcap", ".pcapng"}
        or (
            path.suffix in _IMPLEMENTATION_SUFFIXES
            and any(marker in path.as_posix().casefold() for marker in _EXTERNAL_IMPLEMENTATION_MARKERS)
        )
    }

    assert not offenders, (
        "Capture, phone, WDA, physical-lab and executable provisioning implementations "
        "belong in their external repositories:\n" + "\n".join(sorted(map(str, offenders)))
    )
