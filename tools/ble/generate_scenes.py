#!/usr/bin/env python3
"""Generate the embedded H617A runtime scene catalogue from its frozen API snapshot."""

from __future__ import annotations

import argparse
import base64
import json
import re
import zlib
from pathlib import Path
from typing import Any, cast

CATALOGUE_PATH = Path(__file__).parent / "catalogues" / "effect-library-H617A.json"
SCENES_MODULE_PATH = Path(__file__).parents[2] / "custom_components" / "ha_govee_led_ble" / "scenes.py"
_PAYLOAD_PATTERN = re.compile(r'^_SCENES_PAYLOAD = "([^"]+)"  # noqa: E501$', re.MULTILINE)


def _runtime_name(scene: dict[str, Any]) -> str:
    name = str(scene["name"]).lower()
    variant = str(scene.get("variant", ""))
    if variant and variant.lower() not in {"a", "#0"}:
        name = f"{name} {variant.lower()}"
    return name


def build_runtime_catalogue(catalogue: dict[str, Any]) -> dict[str, list[object]]:
    """Reduce the frozen API catalogue to the fields needed by the integration runtime."""
    runtime: dict[str, list[object]] = {}
    for scene in catalogue["scenes"]:
        name = _runtime_name(scene)
        if name in runtime:
            raise ValueError(f"Duplicate runtime scene name: {name}")
        code = scene["code"]
        param = scene.get("param", "")
        scene_type = scene.get("scene_type", 2)
        data: list[object] = [code]
        if param or scene_type != 2:
            data.append(param)
        if scene_type != 2:
            data.append(scene_type)
        runtime[name] = data
    return runtime


def encode_runtime_catalogue(catalogue: dict[str, Any]) -> str:
    payload = json.dumps(build_runtime_catalogue(catalogue), separators=(",", ":")).encode()
    return base64.b85encode(zlib.compress(payload, level=9)).decode()


def _load_catalogue(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text()))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalogue", type=Path, default=CATALOGUE_PATH)
    parser.add_argument("--output", type=Path, default=SCENES_MODULE_PATH)
    parser.add_argument("--check", action="store_true", help="Fail instead of rewriting a stale payload")
    args = parser.parse_args()

    encoded = encode_runtime_catalogue(_load_catalogue(args.catalogue))
    source = args.output.read_text()
    match = _PAYLOAD_PATTERN.search(source)
    if match is None:
        raise SystemExit(f"Could not find _SCENES_PAYLOAD in {args.output}")
    if match.group(1) == encoded:
        print(f"{args.output}: scene payload is current")
        return
    if args.check:
        raise SystemExit(f"{args.output}: scene payload is stale")
    args.output.write_text(_PAYLOAD_PATTERN.sub(f'_SCENES_PAYLOAD = "{encoded}"  # noqa: E501', source))
    print(f"{args.output}: wrote {len(build_runtime_catalogue(_load_catalogue(args.catalogue)))} scenes")


if __name__ == "__main__":
    main()
