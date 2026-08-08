from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .redaction import HOSTNAME


@dataclass(frozen=True, slots=True)
class ResponseMutation:
    field: str
    original_length: int
    replacement_length: int
    expected_hostnames: tuple[str, ...]
    mqtt_port: int


def _count_key(value: Any, key_name: str) -> int:
    if isinstance(value, dict):
        return sum(key == key_name for key in value) + sum(_count_key(child, key_name) for child in value.values())
    if isinstance(value, list):
        return sum(_count_key(child, key_name) for child in value)
    return 0


def mutate_mqtt_address(
    payload: bytearray,
    *,
    content_type: str,
    content_encoding: str,
    replacement_hostname: str,
    expected_mqtt_port: int | None = None,
) -> ResponseMutation:
    if "json" not in content_type.casefold():
        raise ValueError("mqttAddress mutation requires a JSON response")
    if content_encoding and content_encoding.casefold() != "identity":
        raise ValueError("mqttAddress mutation requires identity content encoding")
    if not HOSTNAME.fullmatch(replacement_hostname):
        raise ValueError("replacement mqttAddress must be a hostname")
    try:
        decoded = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("mqttAddress mutation requires valid JSON") from error
    if not isinstance(decoded, dict) or _count_key(decoded, "mqttAddress") != 1:
        raise ValueError("response must contain exactly one mqttAddress field")
    original = decoded.get("mqttAddress")
    if not isinstance(original, str) or not HOSTNAME.fullmatch(original):
        raise ValueError("root mqttAddress must contain a hostname")
    mqtt_port = decoded.get("mqttPort")
    if not isinstance(mqtt_port, int) or not 1 <= mqtt_port <= 65535:
        raise ValueError("root mqttPort must contain a valid port")
    if expected_mqtt_port is not None and mqtt_port != expected_mqtt_port:
        raise ValueError("production mqttPort differs from the prepared probe port")

    original_token = json.dumps(original, ensure_ascii=True).encode()
    replacement_token = json.dumps(replacement_hostname, ensure_ascii=True).encode()
    pattern = re.compile(rb'("mqttAddress"\s*:\s*)' + re.escape(original_token))
    matches = tuple(pattern.finditer(payload))
    if len(matches) != 1:
        raise ValueError("mqttAddress JSON token is not uniquely replaceable")
    match = matches[0]
    mutated = payload[: match.start(0)] + match.group(1) + replacement_token + payload[match.end(0) :]
    payload[:] = mutated
    return ResponseMutation(
        field="mqttAddress",
        original_length=len(original),
        replacement_length=len(replacement_hostname),
        expected_hostnames=(replacement_hostname.casefold(),),
        mqtt_port=mqtt_port,
    )
