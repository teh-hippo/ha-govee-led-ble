"""Shared bounded-data limits for the optional Effect Studio stack."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Final

MAX_EFFECT_NAME_LENGTH: Final = 128
MAX_EFFECT_KIND_LENGTH: Final = 128
MAX_IDENTIFIER_LENGTH: Final = 255
MAX_TIMESTAMP_LENGTH: Final = 64
MAX_REVISION: Final = 9_007_199_254_740_991

MAX_LIBRARY_ITEMS: Final = 256
MAX_EDITOR_DEVICES: Final = 512
MAX_SCENE_CATALOGUE_ENTRIES: Final = 512
MAX_DEPLOYMENT_RECORDS: Final = 128
MAX_DEVICE_CACHE_ENTRIES: Final = 512
MAX_ACTIVE_WORKSPACE_ENTRIES: Final = 32
MAX_USER_STATE_RECORDS: Final = 256

MAX_JSON_DEPTH: Final = 16
MAX_JSON_NODES: Final = 4096
MAX_STORE_JSON_NODES: Final = 262_144
MAX_JSON_COLLECTION_ITEMS: Final = 1024
MAX_JSON_STRING_LENGTH: Final = 16_384
MAX_EFFECT_DOCUMENT_BYTES: Final = 65_536
MAX_PREFERENCES_BYTES: Final = 16_384
MAX_PREVIEW_SEQUENCE: Final = MAX_REVISION
MAX_LIBRARY_STORE_BYTES: Final = 16_777_216
MAX_DEPLOYMENT_STORE_BYTES: Final = 8_388_608
MAX_DEVICE_CACHE_STORE_BYTES: Final = 1_048_576
MAX_ACTIVE_WORKSPACE_STORE_BYTES: Final = 2_621_440
MAX_USER_STATE_STORE_BYTES: Final = 4_194_304


def validate_bounded_string(
    value: str,
    name: str,
    *,
    maximum: int,
    error_type: type[Exception],
    allow_empty: bool = False,
) -> None:
    if not isinstance(value, str):
        raise error_type(f"{name} must be a string")
    if not allow_empty and not value:
        raise error_type(f"{name} must not be empty")
    if len(value) > maximum:
        raise error_type(f"{name} must not exceed {maximum} characters")


def validate_revision(
    value: int,
    name: str,
    *,
    minimum: int,
    error_type: type[Exception],
) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= MAX_REVISION:
        raise error_type(f"{name} must be an integer from {minimum} to {MAX_REVISION}")


def validate_timestamp(
    value: str,
    name: str,
    *,
    error_type: type[Exception],
) -> None:
    validate_bounded_string(
        value,
        name,
        maximum=MAX_TIMESTAMP_LENGTH,
        error_type=error_type,
    )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise error_type(f"{name} must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise error_type(f"{name} must include a UTC offset")


def validate_json_document(
    value: object,
    name: str,
    *,
    maximum_bytes: int,
    error_type: type[Exception],
    maximum_nodes: int = MAX_JSON_NODES,
) -> None:
    nodes = 0

    def visit(item: object, path: str, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > maximum_nodes:
            raise error_type(f"{name} must not exceed {maximum_nodes} JSON values")
        if depth > MAX_JSON_DEPTH:
            raise error_type(f"{name} must not exceed {MAX_JSON_DEPTH} nested levels")
        if item is None or isinstance(item, bool):
            return
        if isinstance(item, int):
            if not -MAX_REVISION <= item <= MAX_REVISION:
                raise error_type(f"{path} must be within the JSON safe-integer range")
            return
        if isinstance(item, float):
            if not math.isfinite(item):
                raise error_type(f"{path} must be a finite number")
            return
        if isinstance(item, str):
            if len(item) > MAX_JSON_STRING_LENGTH:
                raise error_type(f"{path} must not exceed {MAX_JSON_STRING_LENGTH} characters")
            return
        if isinstance(item, Mapping):
            if len(item) > MAX_JSON_COLLECTION_ITEMS:
                raise error_type(f"{path} must not exceed {MAX_JSON_COLLECTION_ITEMS} fields")
            for key, nested in item.items():
                if not isinstance(key, str):
                    raise error_type(f"{path} contains a non-string key")
                if len(key) > MAX_JSON_STRING_LENGTH:
                    raise error_type(f"{path} contains a key longer than {MAX_JSON_STRING_LENGTH} characters")
                visit(nested, f"{path}.{key}", depth + 1)
            return
        if isinstance(item, Sequence) and not isinstance(item, str | bytes | bytearray):
            if len(item) > MAX_JSON_COLLECTION_ITEMS:
                raise error_type(f"{path} must not exceed {MAX_JSON_COLLECTION_ITEMS} items")
            for index, nested in enumerate(item):
                visit(nested, f"{path}[{index}]", depth + 1)
            return
        raise error_type(f"{path} contains a non-JSON value")

    visit(value, name, 0)
    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
    except (TypeError, ValueError) as exc:
        raise error_type(f"{name} must contain valid JSON values") from exc
    if len(encoded) > maximum_bytes:
        raise error_type(f"{name} must not exceed {maximum_bytes} bytes")
