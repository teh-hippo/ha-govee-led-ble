"""Verify that a release commit changes only synchronised version metadata."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Mapping
from pathlib import Path

RELEASE_FILES = frozenset(
    {
        "custom_components/ha_govee_led_ble/manifest.json",
        "pyproject.toml",
        "uv.lock",
    }
)


def verify_release_files(
    parent: Mapping[str, str],
    current: Mapping[str, str],
    changed_files: set[str],
) -> None:
    if changed_files != RELEASE_FILES:
        actual = ", ".join(sorted(changed_files)) or "(none)"
        raise ValueError(f"release commit changed unexpected files: {actual}")

    parent_project = tomllib.loads(parent["pyproject.toml"])["project"]["version"]
    current_project = tomllib.loads(current["pyproject.toml"])["project"]["version"]
    parent_manifest = json.loads(parent["custom_components/ha_govee_led_ble/manifest.json"])["version"]
    current_manifest = json.loads(current["custom_components/ha_govee_led_ble/manifest.json"])["version"]
    if parent_project != parent_manifest:
        raise ValueError("parent project and manifest versions differ")
    if current_project != current_manifest:
        raise ValueError("release project and manifest versions differ")
    if parent_project == current_project:
        raise ValueError("release commit did not advance the version")

    parent_lock = _project_lock_version(parent["uv.lock"])
    current_lock = _project_lock_version(current["uv.lock"])
    if parent_lock != _uv_version(parent_project) or current_lock != _uv_version(current_project):
        raise ValueError("uv lock project version does not match the release version")

    expected = {
        "custom_components/ha_govee_led_ble/manifest.json": parent[
            "custom_components/ha_govee_led_ble/manifest.json"
        ].replace(parent_manifest, current_manifest, 1),
        "pyproject.toml": parent["pyproject.toml"].replace(parent_project, current_project, 1),
        "uv.lock": parent["uv.lock"].replace(parent_lock, current_lock, 1),
    }
    for path in RELEASE_FILES:
        if current[path] != expected[path]:
            raise ValueError(f"{path} contains changes beyond the project version")


def verify_commit(parent: str, head: str, repository: Path) -> None:
    changed_files = set(_git(repository, "diff", "--name-only", parent, head).splitlines())
    parent_files = {path: _git_file(repository, parent, path) for path in RELEASE_FILES}
    current_files = {path: _git_file(repository, head, path) for path in RELEASE_FILES}
    verify_release_files(parent_files, current_files, changed_files)

    subject = _git(repository, "show", "-s", "--format=%s", head)
    version = tomllib.loads(current_files["pyproject.toml"])["project"]["version"]
    if subject != f"chore(release): {version}":
        raise ValueError("release commit subject does not match its version")


def _project_lock_version(lock_text: str) -> str:
    packages = tomllib.loads(lock_text)["package"]
    matches = [package["version"] for package in packages if package["name"] == "ha-govee-led-ble"]
    if len(matches) != 1:
        raise ValueError("uv lock must contain exactly one project package")
    return str(matches[0])


def _uv_version(version: str) -> str:
    release, separator, candidate = version.partition("-rc.")
    return f"{release}rc{candidate}" if separator else version


def _git(repository: Path, *arguments: str) -> str:
    return _git_output(repository, *arguments).rstrip("\n")


def _git_file(repository: Path, revision: str, path: str) -> str:
    return _git_output(repository, "show", f"{revision}:{path}")


def _git_output(repository: Path, *arguments: str) -> str:
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git is required")
    result = subprocess.run(  # noqa: S603 - fixed Git executable and arguments
        [git, "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: verify_release_commit.py <parent> <head>")
    try:
        verify_commit(sys.argv[1], sys.argv[2], Path.cwd())
    except (KeyError, subprocess.CalledProcessError, TypeError, ValueError) as error:
        raise SystemExit(f"invalid release commit: {error}") from error
