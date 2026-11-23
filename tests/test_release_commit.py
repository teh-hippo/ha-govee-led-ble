import json
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.verify_release_commit import RELEASE_FILES, verify_commit, verify_release_files


def _release_files(version: str) -> dict[str, str]:
    uv_version = version.replace("-rc.", "rc")
    return {
        "custom_components/ha_govee_led_ble/manifest.json": json.dumps(
            {"domain": "ha_govee_led_ble", "version": version}
        ),
        "pyproject.toml": f'[project]\nname = "ha-govee-led-ble"\nversion = "{version}"\n',
        "uv.lock": (
            "version = 1\n\n[[package]]\n"
            'name = "ha-govee-led-ble"\n'
            f'version = "{uv_version}"\n'
            'source = { virtual = "." }\n'
        ),
    }


def test_release_files_accept_only_synchronised_versions() -> None:
    verify_release_files(
        _release_files("8.0.0-rc.35"),
        _release_files("8.0.0-rc.36"),
        set(RELEASE_FILES),
    )


def test_release_files_reject_changes_beyond_version() -> None:
    parent = _release_files("8.0.0-rc.35")
    current = _release_files("8.0.0-rc.36")
    current["pyproject.toml"] += 'description = "unexpected"\n'

    with pytest.raises(ValueError, match="beyond the project version"):
        verify_release_files(parent, current, set(RELEASE_FILES))


def test_release_files_reject_newline_only_changes() -> None:
    parent = _release_files("8.0.0-rc.35")
    current = _release_files("8.0.0-rc.36")
    current["pyproject.toml"] += "\n"

    with pytest.raises(ValueError, match="beyond the project version"):
        verify_release_files(parent, current, set(RELEASE_FILES))


def test_release_commit_verifies_diff_and_subject(tmp_path: Path) -> None:
    git = shutil.which("git")
    if git is None:
        pytest.skip("git is required")

    def run_git(*arguments: str) -> None:
        subprocess.run(  # noqa: S603 - fixed Git executable and local fixture arguments
            [git, *arguments],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            text=True,
        )

    run_git("init", "-b", "master")
    run_git("config", "user.name", "Fixture")
    run_git("config", "user.email", "fixture@example.invalid")
    for path, content in _release_files("8.0.0-rc.35").items():
        destination = tmp_path / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
    run_git("add", ".")
    run_git("-c", "commit.gpgsign=false", "commit", "-m", "fix: source")

    for path, content in _release_files("8.0.0-rc.36").items():
        (tmp_path / path).write_text(content, encoding="utf-8")
    run_git("add", ".")
    run_git("-c", "commit.gpgsign=false", "commit", "-m", "chore(release): 8.0.0-rc.36")

    verify_commit("HEAD^", "HEAD", tmp_path)
