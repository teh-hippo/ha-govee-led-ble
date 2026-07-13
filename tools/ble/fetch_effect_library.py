#!/usr/bin/env python3
"""Fetch and distil Govee's scene/effect catalogue for a given SKU.

Govee's mobile app pulls its built-in scene catalogue from an undocumented but
key-less endpoint::

    GET https://app2.govee.com/appsku/v1/light-effect-libraries?sku=<SKU>

Only an ``AppVersion`` header is required (no account/token). Each scene carries
the exact BLE payload the app writes to the device as a base64 ``scenceParam``
blob (chunked into 0xA3 multi-frames, then activated with ``33 05 04 <code>`` --
see ``build_scene`` / ``build_scene_multi`` in ``protocol.py``).

This tool fetches that response and distils it to a compact catalogue that is
directly usable for testing (name, category, BLE code, param, adjustable
parameters) without the multi-megabyte icon/rule noise of the raw response.

Usage::

    uv run python tools/ble/fetch_effect_library.py H617A [H6199 ...]
    uv run python tools/ble/fetch_effect_library.py H617A H6199 --check

Writes ``effect-library-<SKU>.json`` per SKU under ``tools/ble/catalogues`` by
default. ``--check`` fails with a structural delta instead of overwriting the
frozen snapshots. With ``--raw`` it also keeps the untouched API response as
``<SKU>-raw.json``.
"""

from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, cast

API_URL = "https://app2.govee.com/appsku/v1/light-effect-libraries"
# The endpoint gates on app version; a large sentinel keeps it from 426-ing us.
APP_VERSION = "9999999"
CATALOGUE_DIR = Path(__file__).parent / "catalogues"


def fetch_library(sku: str) -> dict[str, Any]:
    """Return the raw ``light-effect-libraries`` JSON for ``sku``."""
    url = f"{API_URL}?sku={urllib.parse.quote(sku)}"
    if not url.startswith("https://"):  # defensive: only ever talk to the API over TLS
        raise ValueError(f"refusing non-https URL: {url}")
    request = urllib.request.Request(url, headers={"AppVersion": APP_VERSION})  # noqa: S310 (fixed https host)
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return cast(dict[str, Any], json.load(response))


def _speed_config(light_effect: dict[str, Any]) -> Any:
    """Parse the (JSON-in-a-string) adjustable-parameter config, if present."""
    config = light_effect.get("speedInfo", {}).get("config") or ""
    if not config:
        return None
    try:
        return json.loads(config)
    except json.JSONDecodeError:
        return config


def distil(raw: dict[str, Any]) -> dict[str, Any]:
    """Reduce the raw response to a compact, testable catalogue."""
    scenes: list[dict[str, Any]] = []
    for category in raw.get("data", {}).get("categories", []):
        for scene in category.get("scenes", []):
            light_effects = scene.get("lightEffects", [])
            for index, light_effect in enumerate(light_effects):
                entry: dict[str, Any] = {
                    "category": category.get("categoryName"),
                    "name": scene.get("sceneName"),
                    "code": light_effect.get("sceneCode"),
                    "param": light_effect.get("scenceParam", ""),
                    "scene_type": light_effect.get("sceneType", scene.get("sceneType", 2)),
                }
                # Scenes with several sub-effects (e.g. "Action A/B/C") share a
                # name; keep the sub-label so each remains addressable.
                sub_name = light_effect.get("scenceName", "")
                if sub_name or len(light_effects) > 1:
                    entry["variant"] = sub_name or f"#{index}"
                if light_effect.get("speedInfo", {}).get("supSpeed"):
                    entry["adjustable"] = True
                    entry["config"] = _speed_config(light_effect)
                special = light_effect.get("specialEffect") or []
                if special:
                    entry["special_skus"] = sorted({sku for effect in special for sku in effect.get("supportSku", [])})
                scenes.append(entry)
    return {
        "sku": None,
        "scene_count": len({(scene["category"], scene["name"]) for scene in scenes}),
        "effect_count": len(scenes),
        "scenes": scenes,
    }


def _scene_key(scene: dict[str, Any]) -> tuple[str, str, str]:
    return str(scene.get("category", "")), str(scene.get("name", "")), str(scene.get("variant", ""))


def catalogue_drift(expected: dict[str, Any], current: dict[str, Any]) -> list[str]:
    """Return a stable, human-readable structural delta between two catalogues."""
    changes = []
    for field in ("sku", "scene_count", "effect_count"):
        if expected.get(field) != current.get(field):
            changes.append(f"{field}: {expected.get(field)!r} -> {current.get(field)!r}")

    expected_scenes = {_scene_key(scene): scene for scene in expected.get("scenes", [])}
    current_scenes = {_scene_key(scene): scene for scene in current.get("scenes", [])}
    for key in sorted(expected_scenes.keys() - current_scenes.keys()):
        changes.append(f"removed: {' / '.join(part for part in key if part)}")
    for key in sorted(current_scenes.keys() - expected_scenes.keys()):
        changes.append(f"added: {' / '.join(part for part in key if part)}")
    for key in sorted(expected_scenes.keys() & current_scenes.keys()):
        before, after = expected_scenes[key], current_scenes[key]
        fields = sorted(field for field in before.keys() | after.keys() if before.get(field) != after.get(field))
        if fields:
            changes.append(f"changed: {' / '.join(part for part in key if part)} ({', '.join(fields)})")
    return changes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("skus", nargs="+", help="Model SKU(s), e.g. H617A H619A")
    parser.add_argument("--out-dir", type=Path, default=CATALOGUE_DIR, help="Output/check directory")
    parser.add_argument("--raw", action="store_true", help="Also write the untouched API response")
    parser.add_argument("--check", action="store_true", help="Compare with frozen snapshots without overwriting")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    failed = False
    for sku in args.skus:
        raw = fetch_library(sku)
        if raw.get("status") != 200:
            print(f"{sku}: API returned status={raw.get('status')} message={raw.get('message')!r}")
            failed = True
            continue
        if args.raw and not args.check:
            (args.out_dir / f"{sku}-raw.json").write_text(json.dumps(raw, indent=2))
        catalogue = distil(raw)
        catalogue["sku"] = sku
        out_path = args.out_dir / f"effect-library-{sku}.json"
        if args.check:
            if not out_path.exists():
                print(f"{sku}: missing frozen snapshot {out_path}")
                failed = True
                continue
            expected = cast(dict[str, Any], json.loads(out_path.read_text()))
            changes = catalogue_drift(expected, catalogue)
            if changes:
                failed = True
                print(f"{sku}: catalogue drift ({len(changes)} change(s))")
                for change in changes:
                    print(f"  {change}")
            else:
                print(f"{sku}: unchanged at {catalogue['scene_count']} scenes / {catalogue['effect_count']} effects")
            continue
        out_path.write_text(json.dumps(catalogue, indent=2, ensure_ascii=False) + "\n")
        adjustable = sum(1 for scene in catalogue["scenes"] if scene.get("adjustable"))
        print(
            f"{sku}: {catalogue['scene_count']} scenes / {catalogue['effect_count']} effects "
            f"({adjustable} with adjustable parameters) -> {out_path.name}"
        )
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
