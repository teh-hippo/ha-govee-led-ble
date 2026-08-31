"""Synchronise the integration manifest with the project version."""

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]
PROJECT_PATH = ROOT / "pyproject.toml"
MANIFEST_PATH = ROOT / "custom_components/ha_govee_led_ble/manifest.json"


def main() -> None:
    version = tomllib.loads(PROJECT_PATH.read_text(encoding="utf-8"))["project"]["version"]
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["version"] = version
    MANIFEST_PATH.write_text(f"{json.dumps(manifest, indent=4)}\n", encoding="utf-8")


if __name__ == "__main__":
    main()
