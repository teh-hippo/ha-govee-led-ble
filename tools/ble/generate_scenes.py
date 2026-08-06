#!/usr/bin/env python3
"""Generate the embedded H617A runtime scene catalogue from its frozen API snapshot."""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import zlib
from pathlib import Path
from typing import Any, cast

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from custom_components.ha_govee_led_ble.protocol import scene_record_spans  # noqa: E402

CATALOGUE_PATH = Path(__file__).parent / "catalogues" / "effect-library-H617A.json"
SCENES_MODULE_PATH = Path(__file__).parents[2] / "custom_components" / "ha_govee_led_ble" / "scenes.py"
_PAYLOAD_PATTERN = re.compile(r'^_SCENES_PAYLOAD = "([^"]+)"  # noqa: E501$', re.MULTILINE)


def _runtime_name(scene: dict[str, Any]) -> str:
    name = str(scene["name"]).lower()
    variant = str(scene.get("variant", ""))
    if variant and variant.lower() not in {"a", "#0"}:
        name = f"{name} {variant.lower()}"
    return name


def _speed_config(scene: dict[str, Any]) -> list[Any] | None:
    """Reduce a scene's config array to the Speed slider model, validating it against the body.

    Every check here is a build gate for an invariant scene_body.ksy states in prose: a config
    entry's ``page`` names a body record, all of a scene's entries share one slider position, and
    that position indexes every option list. A catalogue refresh that breaks one fails the build
    instead of silently shipping a scene whose Speed byte lands in the wrong record.
    """
    if not scene.get("adjustable"):
        return None
    entries = [
        entry
        for entry in scene.get("config", [])
        if any(key in entry for key in ("moveIn", "moveAll", "color", "bright"))
    ]
    if not entries:
        return None
    label = f"{scene['name']} {scene['code']}"
    if scene.get("scene_type", 2) != 2:
        raise ValueError(f"{label}: only type-2 bodies are record containers, so Speed cannot be located")
    indices = {int(entry["defaultIndex"]) for entry in entries}
    if len(indices) != 1:
        raise ValueError(f"{label}: pages disagree on defaultIndex {sorted(indices)}")
    default_index = indices.pop()
    payload = base64.b64decode(scene["param"])
    spans = scene_record_spans(payload)
    record_count = len(spans)
    pages: list[list[Any]] = []
    option_counts: set[int] = set()
    for entry in entries:
        page = int(entry["page"])
        if not 0 <= page < record_count:
            if scene["code"] == 2219:
                # Heartbeat carries pages 1 and 2 for a two-record body, unlike every
                # capture-backed zero-based config. Leave its Speed unsupported until a
                # live application establishes whether this one entry is one-based or stale.
                return None
            raise ValueError(f"{label}: page {page} has no record (body holds {record_count})")
        brightness = [[int(item["brightPage"]), item["brightValue"]] for item in entry.get("bright", [])]
        options = [
            entry.get("moveIn", []),
            entry.get("moveAll", []),
            entry.get("color", []),
            *(values for _, values in brightness),
        ]
        for values in options:
            if values:
                option_counts.add(len(values))
                if not 0 <= default_index < len(values):
                    raise ValueError(f"{label}: page {page} default index {default_index} outside {values}")
        record_start, _ = spans[page]
        brightness_block_count = payload[record_start + 5]
        for block, _ in brightness:
            if not 0 <= block < brightness_block_count:
                raise ValueError(
                    f"{label}: page {page} brightness block {block} outside 0..{brightness_block_count - 1}"
                )
        pages.append(
            [
                page,
                entry.get("moveIn", []),
                entry.get("moveAll", []),
                entry.get("color", []),
                brightness,
            ]
        )
    if len(option_counts) != 1:
        raise ValueError(f"{label}: pages disagree on option count {sorted(option_counts)}")
    return [default_index, pages]


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
        speed = _speed_config(scene)
        data: list[object] = [code]
        if param or scene_type != 2 or speed is not None:
            data.append(param)
        if scene_type != 2 or speed is not None:
            data.append(scene_type)
        if speed is not None:
            data.append(speed)
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
