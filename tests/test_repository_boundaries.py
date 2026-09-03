"""Repository ownership boundaries for external capture and physical tooling."""

import shutil
import subprocess
from pathlib import Path

_REPO = Path(__file__).parents[1]
_KAITAI_DIR = _REPO / "tools" / "ble" / "kaitai"
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


def test_speculative_kaitai_roots_are_quarantined_and_marked() -> None:
    speculative = tuple((_KAITAI_DIR / "speculative").glob("**/*.ksy"))
    missing_markers = {path.relative_to(_REPO) for path in speculative if "SPECULATIVE" not in path.read_text()}
    promoted_with_marker = {
        path.relative_to(_REPO) for path in _KAITAI_DIR.glob("*.ksy") if "SPECULATIVE" in path.read_text()
    }

    assert not missing_markers, "Speculative KSY files must contain a SPECULATIVE doc marker"
    assert not promoted_with_marker, "Evidence-backed top-level KSY files must not retain the SPECULATIVE marker"
