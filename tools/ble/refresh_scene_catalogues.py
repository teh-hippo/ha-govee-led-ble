#!/usr/bin/env python3
"""Refresh the committed per-model scene snapshots from Govee's catalogue API."""

from __future__ import annotations

import argparse
import base64
import io
import json
import math
import sys
import urllib.parse
import urllib.request
import warnings
from importlib import import_module
from pathlib import Path
from typing import Any, cast

from kaitaistruct import KaitaiStream

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

SceneBody = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.scene_body").SceneBody,
)

API_URL = "https://app2.govee.com/appsku/v1/light-effect-libraries"
APP_VERSION = "9999999"
SNAPSHOT_DIR = Path(__file__).parents[2] / "custom_components" / "ha_govee_led_ble" / "scene_catalogues"
DEFAULT_SKUS = ("H6125", "H617A", "H6199")

# Glacier's current iOS application was captured rewriting the two stored 0xff movement
# bytes to the catalogue's default value 250 when applying the scene.
_CAPTURE_VERIFIED_SPEED_DEFAULT_REWRITES = frozenset({("H617A", 1026, 1088)})


def fetch_library(sku: str) -> dict[str, Any]:
    url = f"{API_URL}?sku={urllib.parse.quote(sku)}"
    request = urllib.request.Request(  # noqa: S310
        url,
        headers={"AppVersion": APP_VERSION},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return cast(dict[str, Any], json.load(response))


def _special_effect(effect: dict[str, Any], sku: str) -> dict[str, Any] | None:
    return next(
        (special for special in effect.get("specialEffect") or [] if sku in (special.get("supportSku") or [])),
        None,
    )


def _resolved_effect(effect: dict[str, Any], sku: str) -> dict[str, Any]:
    special = _special_effect(effect, sku)
    if special is None:
        return effect

    resolved = dict(effect)
    if special.get("sceneCode", 0) > 0:
        resolved["sceneCode"] = special["sceneCode"]
    if special.get("scenceParam"):
        resolved["scenceParam"] = special["scenceParam"]
    if special.get("scenceParamId", 0) != 0:
        resolved["scenceParamId"] = special["scenceParamId"]
    if "speedInfo" in special:
        resolved["speedInfo"] = special["speedInfo"]
    if special.get("sceneCode", 0) > 0 or (special.get("sceneType", 0) > 0 and special.get("scenceParam")):
        resolved["sceneType"] = special.get("sceneType", 0)
    return resolved


def _speed_config(effect: dict[str, Any]) -> list[dict[str, Any]]:
    config = effect.get("speedInfo", {}).get("config") or ""
    if not config:
        return []
    parsed = json.loads(config)
    if not isinstance(parsed, list):
        raise ValueError("scene speed config must be a list")
    return cast(list[dict[str, Any]], parsed)


def _parse_scene_records(param: str) -> list[Any]:
    payload = base64.b64decode(param)
    used = 3 + len(payload)
    num_chunks = max(2, math.ceil(used / 17))
    body = bytes((1, num_chunks, 2)) + payload
    body += bytes(num_chunks * 17 - len(body))
    parsed = SceneBody(KaitaiStream(io.BytesIO(body)))
    parsed._read()
    return cast(list[Any], parsed.records)


def _snapshot_speed(
    effect: dict[str, Any],
    label: str,
    *,
    allow_default_rewrite: bool = False,
) -> dict[str, Any] | None:
    if not effect.get("speedInfo", {}).get("supSpeed"):
        return None
    if int(effect.get("sceneType", 2)) != 2:
        raise ValueError(f"{label}: only type-2 scenes can expose Speed")

    entries = [
        entry
        for entry in _speed_config(effect)
        if any(key in entry for key in ("moveIn", "moveAll", "color", "bright"))
    ]
    if not entries:
        return None

    default_indices = {int(entry["defaultIndex"]) for entry in entries}
    if len(default_indices) != 1:
        raise ValueError(f"{label}: inconsistent default Speed positions")
    default_index = default_indices.pop()
    records = _parse_scene_records(str(effect["scenceParam"]))
    pages: list[dict[str, Any]] = []
    option_counts: set[int] = set()

    for entry in entries:
        page = int(entry["page"])
        if not 0 <= page < len(records):
            warnings.warn(
                f"{label}: Speed page {page} outside {len(records)} records; omitting Speed",
                stacklevel=2,
            )
            return None

        brightness = [
            {
                "block": int(item["brightPage"]),
                "values": [int(value) for value in item["brightValue"]],
            }
            for item in entry.get("bright", [])
        ]
        option_lists = [
            entry.get("moveIn", []),
            entry.get("moveAll", []),
            entry.get("color", []),
            *(item["values"] for item in brightness),
        ]
        for values in option_lists:
            if not values:
                continue
            option_counts.add(len(values))
            if not 0 <= default_index < len(values):
                raise ValueError(f"{label}: default Speed position outside option list")

        num_blocks = cast(int, records[page].body.num_brightness_blocks)
        if any(not 0 <= cast(int, item["block"]) < num_blocks for item in brightness):
            raise ValueError(f"{label}: brightness block outside parsed record")

        page_data: dict[str, Any] = {"page": page}
        for source, target in (
            ("moveIn", "move_in"),
            ("moveAll", "move_all"),
            ("color", "colour_speed"),
        ):
            if values := entry.get(source):
                page_data[target] = [int(value) for value in values]
        if brightness:
            page_data["brightness"] = brightness
        pages.append(page_data)

    if len(option_counts) != 1:
        raise ValueError(f"{label}: inconsistent Speed option counts")

    mismatches: list[str] = []
    for page_spec in pages:
        body = records[page_spec["page"]].body
        for field, actual in (
            ("move_in", body.selected_area_movement.speed),
            ("move_all", body.overall_movement.speed),
            ("colour_speed", body.colour_speed),
        ):
            if values := page_spec.get(field):
                expected = values[default_index]
                if actual != expected:
                    mismatches.append(f"page {page_spec['page']} {field} stores {actual}, default is {expected}")
        for brightness_spec in page_spec.get("brightness", []):
            actual = body.brightness_blocks[brightness_spec["block"]].brightness_speed
            expected = brightness_spec["values"][default_index]
            if actual != expected:
                mismatches.append(
                    f"page {page_spec['page']} brightness block {brightness_spec['block']} "
                    f"stores {actual}, default is {expected}"
                )

    if mismatches and not allow_default_rewrite:
        warnings.warn(
            f"{label}: default Speed metadata does not reproduce the stored scene body "
            f"({'; '.join(mismatches)}); omitting Speed",
            stacklevel=2,
        )
        return None
    return {"default_index": default_index, "pages": pages}


def build_snapshot(raw: dict[str, Any], sku: str) -> dict[str, Any]:
    if raw.get("status") != 200:
        raise ValueError(f"{sku}: API returned status={raw.get('status')} message={raw.get('message')!r}")

    categories = []
    effects = []
    identities: set[tuple[int, int]] = set()

    for category in raw.get("data", {}).get("categories", []):
        category_id = int(category["categoryId"])
        categories.append({"id": category_id, "name": str(category["categoryName"])})
        for scene in category.get("scenes", []):
            scene_id = int(scene["sceneId"])
            name = str(scene["sceneName"])
            light_effects = scene.get("lightEffects", [])
            for index, source_effect in enumerate(light_effects):
                effect = _resolved_effect(source_effect, sku)
                effect_id = int(effect["scenceParamId"])
                identity = (scene_id, effect_id)
                if identity in identities:
                    raise ValueError(f"{sku}: duplicate scene/effect identity {identity}")
                identities.add(identity)

                entry: dict[str, Any] = {
                    "category_id": category_id,
                    "scene_id": scene_id,
                    "effect_id": effect_id,
                    "name": name,
                    "code": int(effect["sceneCode"]),
                    "scene_type": int(effect.get("sceneType", scene.get("sceneType", 2))),
                }
                if sku == "H6199":
                    entry["music_code"] = 0
                variant = str(effect.get("scenceName") or "")
                if variant or len(light_effects) > 1:
                    entry["variant"] = variant or f"#{index}"
                if param := str(effect.get("scenceParam") or ""):
                    entry["param"] = param
                if sku == "H617A" and (
                    speed := _snapshot_speed(
                        effect,
                        f"{name}-{variant}" if variant else name,
                        allow_default_rewrite=(sku, scene_id, effect_id) in _CAPTURE_VERIFIED_SPEED_DEFAULT_REWRITES,
                    )
                ):
                    entry["speed"] = speed
                effects.append(entry)

    return {
        "schema_version": 1,
        "sku": sku,
        "categories": categories,
        "effects": effects,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skus", nargs="*", default=DEFAULT_SKUS)
    parser.add_argument("--out-dir", type=Path, default=SNAPSHOT_DIR)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail instead of overwriting snapshots that differ from the API",
    )
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stale = False
    for sku in args.skus:
        snapshot = build_snapshot(fetch_library(sku), sku)
        rendered = json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n"
        path = args.out_dir / f"{sku}.json"
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != rendered:
                stale = True
                print(f"{path}: stale")
            else:
                print(f"{path}: current")
            continue
        path.write_text(rendered, encoding="utf-8")
        print(f"{path}: wrote {len(snapshot['effects'])} effects")
    if stale:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
