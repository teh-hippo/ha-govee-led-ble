#!/usr/bin/env python3
"""Run a basic autonomous UAT scenario for an H6199 via Home Assistant APIs."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _request_json(
    method: str,
    url: str,
    token: str,
    payload: dict[str, Any] | None = None,
) -> Any:
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    req = Request(url, method=method, data=body)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    with urlopen(req, timeout=20) as response:
        raw = response.read()
        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))


def get_state(base_url: str, token: str, entity_id: str) -> dict[str, Any]:
    """Read an entity state object from HA."""
    url = f"{base_url}/api/states/{entity_id}"
    return _request_json("GET", url, token)


def try_get_state(base_url: str, token: str, entity_id: str) -> dict[str, Any] | None:
    """Read an entity state object from HA, returning None if unavailable."""
    try:
        return get_state(base_url, token, entity_id)
    except (HTTPError, URLError, TimeoutError):
        return None


def call_service(base_url: str, token: str, domain: str, service: str, data: dict[str, Any]) -> Any:
    """Call a Home Assistant service endpoint."""
    url = f"{base_url}/api/services/{domain}/{service}"
    return _request_json("POST", url, token, payload=data)


@dataclass
class Step:
    name: str
    domain: str
    service: str
    data: dict[str, Any]
    expected_light_state: str | None = None
    expected_effect: str | None = None
    expected_brightness_pct: int | None = None
    expected_capture_region: str | None = None
    expected_video_saturation: int | None = None
    expected_music_sensitivity: int | None = None


def _brightness_pct(value_255: int | None) -> int | None:
    if value_255 is None:
        return None
    return round(value_255 * 100 / 255)


def _float_state(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def _is_step_satisfied(
    step: Step,
    light_state: dict[str, Any] | None,
    capture_state: dict[str, Any] | None,
    video_sat_state: dict[str, Any] | None,
    music_sens_state: dict[str, Any] | None,
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if light_state is None:
        return (False, ["light entity state unavailable"])

    attrs = light_state.get("attributes", {})

    if step.expected_light_state is not None and light_state.get("state") != step.expected_light_state:
        errors.append(
            f"light.state expected={step.expected_light_state} actual={light_state.get('state')}"
        )

    if step.expected_effect is not None and attrs.get("effect") != step.expected_effect:
        errors.append(f"light.effect expected={step.expected_effect} actual={attrs.get('effect')}")

    if step.expected_brightness_pct is not None:
        actual_pct = _brightness_pct(attrs.get("brightness"))
        if actual_pct != step.expected_brightness_pct:
            errors.append(f"light.brightness_pct expected={step.expected_brightness_pct} actual={actual_pct}")

    if step.expected_capture_region is not None:
        if capture_state is None:
            errors.append("capture_region entity not configured")
        elif capture_state.get("state") != step.expected_capture_region:
            errors.append(
                f"capture_region expected={step.expected_capture_region} actual={capture_state.get('state')}"
            )

    if step.expected_video_saturation is not None:
        if video_sat_state is None:
            errors.append("video_saturation entity not configured")
        else:
            actual = _float_state(video_sat_state.get("state", ""))
            if actual is None or round(actual) != step.expected_video_saturation:
                errors.append(f"video_saturation expected={step.expected_video_saturation} actual={actual}")

    if step.expected_music_sensitivity is not None:
        if music_sens_state is None:
            errors.append("music_sensitivity entity not configured")
        else:
            actual = _float_state(music_sens_state.get("state", ""))
            if actual is None or round(actual) != step.expected_music_sensitivity:
                errors.append(f"music_sensitivity expected={step.expected_music_sensitivity} actual={actual}")

    return (len(errors) == 0, errors)


def _build_steps(
    light_entity_id: str,
    *,
    include_capture_region_assert: bool,
    include_video_saturation_assert: bool,
    include_music_sensitivity_assert: bool,
) -> list[Step]:
    return [
        Step(
            name="turn_on_video_movie",
            domain="light",
            service="turn_on",
            data={"entity_id": light_entity_id, "effect": "video: movie"},
            expected_light_state="on",
            expected_effect="video: movie",
        ),
        Step(
            name="set_video_game_part",
            domain="govee_ble_lights",
            service="set_video_mode",
            data={
                "entity_id": light_entity_id,
                "mode": "game",
                "capture_region": "part",
                "saturation": 55,
                "brightness": 40,
            },
            expected_light_state="on",
            expected_effect="video: game",
            expected_brightness_pct=40,
            expected_capture_region="part" if include_capture_region_assert else None,
            expected_video_saturation=55 if include_video_saturation_assert else None,
        ),
        Step(
            name="set_music_spectrum",
            domain="govee_ble_lights",
            service="set_music_mode",
            data={"entity_id": light_entity_id, "mode": "spectrum", "sensitivity": 70, "color": [1, 2, 3]},
            expected_light_state="on",
            expected_effect="music: spectrum",
            expected_music_sensitivity=70 if include_music_sensitivity_assert else None,
        ),
        Step(
            name="turn_off",
            domain="light",
            service="turn_off",
            data={"entity_id": light_entity_id},
            expected_light_state="off",
        ),
    ]


def run_harness(
    *,
    base_url: str,
    token: str,
    light_entity_id: str,
    capture_region_entity_id: str | None,
    video_saturation_entity_id: str | None,
    music_sensitivity_entity_id: str | None,
    timeout_seconds: float,
    poll_seconds: float,
) -> list[dict[str, Any]]:
    steps = _build_steps(
        light_entity_id,
        include_capture_region_assert=capture_region_entity_id is not None,
        include_video_saturation_assert=video_saturation_entity_id is not None,
        include_music_sensitivity_assert=music_sensitivity_entity_id is not None,
    )
    results: list[dict[str, Any]] = []

    for step in steps:
        started = time.monotonic()
        step_result: dict[str, Any] = {
            "name": step.name,
            "service": f"{step.domain}.{step.service}",
            "request": step.data,
            "status": "failed",
            "errors": [],
            "elapsed_seconds": 0.0,
        }

        try:
            call_service(base_url, token, step.domain, step.service, step.data)
        except (HTTPError, URLError, TimeoutError) as exc:
            step_result["errors"] = [f"service_call_failed: {exc}"]
            step_result["elapsed_seconds"] = round(time.monotonic() - started, 3)
            results.append(step_result)
            continue

        deadline = started + timeout_seconds
        while time.monotonic() < deadline:
            light_state = try_get_state(base_url, token, light_entity_id)
            capture_state = (
                try_get_state(base_url, token, capture_region_entity_id) if capture_region_entity_id else None
            )
            video_sat_state = (
                try_get_state(base_url, token, video_saturation_entity_id) if video_saturation_entity_id else None
            )
            music_sens_state = (
                try_get_state(base_url, token, music_sensitivity_entity_id) if music_sensitivity_entity_id else None
            )

            ok, errors = _is_step_satisfied(step, light_state, capture_state, video_sat_state, music_sens_state)
            if ok:
                step_result["status"] = "passed"
                step_result["errors"] = []
                step_result["light_state"] = light_state
                step_result["capture_state"] = capture_state
                step_result["video_saturation_state"] = video_sat_state
                step_result["music_sensitivity_state"] = music_sens_state
                break

            step_result["errors"] = errors
            time.sleep(poll_seconds)

        step_result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        results.append(step_result)

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Run H6199 UAT harness against Home Assistant.")
    parser.add_argument("--base-url", required=True, help="Home Assistant base URL, e.g. http://127.0.0.1:8123")
    parser.add_argument("--token", required=True, help="Long-lived Home Assistant token")
    parser.add_argument("--light-entity-id", required=True, help="Target light entity id, e.g. light.govee_h6199")
    parser.add_argument("--capture-region-entity-id", help="Optional select entity id for video capture region")
    parser.add_argument("--video-saturation-entity-id", help="Optional number entity id for video saturation")
    parser.add_argument("--music-sensitivity-entity-id", help="Optional number entity id for music sensitivity")
    parser.add_argument("--timeout-seconds", type=float, default=10.0, help="Per-step convergence timeout")
    parser.add_argument("--poll-seconds", type=float, default=0.5, help="State polling interval")
    parser.add_argument(
        "--output",
        default=f"artifacts/h6199-harness-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json",
        help="Output report path",
    )
    args = parser.parse_args()

    results = run_harness(
        base_url=args.base_url.rstrip("/"),
        token=args.token,
        light_entity_id=args.light_entity_id,
        capture_region_entity_id=args.capture_region_entity_id,
        video_saturation_entity_id=args.video_saturation_entity_id,
        music_sensitivity_entity_id=args.music_sensitivity_entity_id,
        timeout_seconds=args.timeout_seconds,
        poll_seconds=args.poll_seconds,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "base_url": args.base_url,
        "light_entity_id": args.light_entity_id,
        "results": results,
        "summary": {
            "total_steps": len(results),
            "passed": sum(1 for row in results if row["status"] == "passed"),
            "failed": sum(1 for row in results if row["status"] != "passed"),
        },
    }
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    print(f"Report written: {output_path}")

    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
