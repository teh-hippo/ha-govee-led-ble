import json
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


def test_existing_release_commit_is_valid() -> None:
    verify_commit("da748615^", "da748615", Path(__file__).parents[1])
