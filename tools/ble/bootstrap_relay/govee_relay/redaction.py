from __future__ import annotations

import gzip
import hashlib
import io
import json
import math
import re
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlsplit

EXACT_SENSITIVE_KEYS = frozenset(
    {
        "privatekey",
        "certificatepem",
        "certificate",
        "endpoint",
        "clientid",
        "publishtopic",
        "subscribetopic",
    }
)
SAFE_SCHEMA_KEYS = frozenset(
    {
        "code",
        "message",
        "data",
        "status",
        "success",
        "config",
        "credentials",
        "endpoint",
        "mqttEndpoint",
        "mqttAddress",
        "mqttPort",
        "port",
        "host",
        "url",
        "urls",
        "certificate",
        "certificatePem",
        "privateKey",
        "clientId",
        "publishTopic",
        "subscribeTopic",
        "topic",
        "topics",
        "device",
        "devices",
        "sku",
        "envId",
        "iotVersion",
        "otaUrl",
        "matterCertUrl",
        "weatherUrl",
        "region",
        "thingName",
    }
)
ENDPOINT_KEYS = frozenset({"endpoint", "mqttEndpoint", "mqttAddress"})
SENSITIVE_KEY_PARTS = (
    "key",
    "cert",
    "token",
    "secret",
    "password",
    "credential",
    "client",
    "device",
    "topic",
    "endpoint",
    "broker",
    "url",
    "thing",
    "region",
)
HOSTNAME = re.compile(r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$")
URL = re.compile(r"^https?://", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class SchemaFact:
    path: str
    value_type: str
    length: int | None = None
    string_class: str | None = None
    correlation_sha256: str | None = None
    sensitive_name: bool = False
    key_length: int | None = None
    key_class: str | None = None

    def as_event(self) -> dict[str, object]:
        return {key: value for key, value in asdict(self).items() if value is not None}


@dataclass(frozen=True, slots=True)
class ResponseSchema:
    encoding: str
    body_length: int
    body_sha256: str | None
    facts: tuple[SchemaFact, ...]

    def as_event(self) -> dict[str, object]:
        return {
            "encoding": self.encoding,
            "body_length": self.body_length,
            "body_sha256": self.body_sha256,
            "facts": [fact.as_event() for fact in self.facts],
        }


def sensitive_name(name: str) -> bool:
    lowered = name.casefold().replace("_", "").replace("-", "")
    return lowered in EXACT_SENSITIVE_KEYS or any(part in lowered for part in SENSITIVE_KEY_PARTS)


def classify_string(value: str) -> str:
    if "-----BEGIN " in value and "-----END " in value:
        return "pem-like"
    if URL.match(value):
        return "url-like"
    if HOSTNAME.match(value):
        return "hostname-like"
    return "opaque"


def _high_entropy_digest(value: str) -> str | None:
    if len(value) < 64:
        return None
    counts = {character: value.count(character) for character in set(value)}
    entropy = -sum((count / len(value)) * math.log2(count / len(value)) for count in counts.values())
    if entropy < 3.5 and "-----BEGIN " not in value:
        return None
    return hashlib.sha256(value.encode()).hexdigest()


def _walk(
    value: Any,
    path: str,
    key_name: str,
    facts: list[SchemaFact],
    *,
    key_length: int | None = None,
    key_class: str | None = None,
) -> None:
    is_sensitive = sensitive_name(key_name) if key_name else False
    if isinstance(value, dict):
        facts.append(
            SchemaFact(
                path,
                "object",
                length=len(value),
                sensitive_name=is_sensitive,
                key_length=key_length,
                key_class=key_class,
            )
        )
        for index, (key, child) in enumerate(value.items()):
            key_text = str(key)
            is_known = key_text in SAFE_SCHEMA_KEYS
            segment = key_text if is_known else f"<key#{index}>"
            child_path = f"{path}.{segment}" if path else segment
            _walk(
                child,
                child_path,
                key_text,
                facts,
                key_length=None if is_known else len(key_text),
                key_class=None if is_known else classify_string(key_text),
            )
        return
    if isinstance(value, list):
        facts.append(
            SchemaFact(
                path,
                "array",
                length=len(value),
                sensitive_name=is_sensitive,
                key_length=key_length,
                key_class=key_class,
            )
        )
        for index, child in enumerate(value):
            _walk(
                child,
                f"{path}[{index}]",
                key_name,
                facts,
                key_length=key_length,
                key_class=key_class,
            )
        return
    if isinstance(value, str):
        facts.append(
            SchemaFact(
                path,
                "string",
                length=len(value),
                string_class=classify_string(value),
                correlation_sha256=_high_entropy_digest(value) if is_sensitive else None,
                sensitive_name=is_sensitive,
                key_length=key_length,
                key_class=key_class,
            )
        )
        return
    value_type = (
        "null"
        if value is None
        else "boolean"
        if isinstance(value, bool)
        else "integer"
        if isinstance(value, int)
        else "number"
        if isinstance(value, float)
        else type(value).__name__
    )
    facts.append(
        SchemaFact(
            path,
            value_type,
            sensitive_name=is_sensitive,
            key_length=key_length,
            key_class=key_class,
        )
    )


def _decode_json_payload(
    payload: bytearray,
    *,
    content_encoding: str,
    maximum_decoded_bytes: int,
) -> tuple[bytearray, bool]:
    if not content_encoding or content_encoding.casefold() == "identity":
        return payload, False
    if content_encoding.casefold() != "gzip":
        raise ValueError("unsupported content encoding for schema extraction")
    decoded = bytearray()
    with gzip.GzipFile(fileobj=io.BytesIO(payload), mode="rb") as handle:
        decoded.extend(handle.read(maximum_decoded_bytes + 1))
    if len(decoded) > maximum_decoded_bytes:
        decoded[:] = b"\x00" * len(decoded)
        raise ValueError("decoded response exceeds schema limit")
    return decoded, True


def _collect_endpoint_candidates(value: Any, candidates: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in ENDPOINT_KEYS and isinstance(child, str):
                candidate = urlsplit(child).hostname if URL.match(child) else child
                if candidate and (HOSTNAME.match(candidate) or candidate.replace(".", "").isdigit()):
                    candidates.append(candidate.casefold())
            _collect_endpoint_candidates(child, candidates)
    elif isinstance(value, list):
        for child in value:
            _collect_endpoint_candidates(child, candidates)


def extract_response_schema(
    payload: bytearray,
    *,
    content_type: str,
    content_encoding: str = "",
    maximum_decoded_bytes: int = 262144,
) -> ResponseSchema:
    body_length = len(payload)
    if "json" not in content_type.casefold():
        return ResponseSchema(
            "non-json",
            body_length,
            hashlib.sha256(payload).hexdigest(),
            (),
        )
    json_payload, should_clear = _decode_json_payload(
        payload,
        content_encoding=content_encoding,
        maximum_decoded_bytes=maximum_decoded_bytes,
    )
    try:
        try:
            decoded = json.loads(json_payload)
        except UnicodeDecodeError, json.JSONDecodeError:
            return ResponseSchema(
                "invalid-json",
                body_length,
                hashlib.sha256(payload).hexdigest(),
                (),
            )
        facts: list[SchemaFact] = []
        _walk(decoded, "", "", facts)
        return ResponseSchema("json", body_length, None, tuple(facts))
    finally:
        if should_clear:
            json_payload[:] = b"\x00" * len(json_payload)


def endpoint_candidates(
    payload: bytearray,
    *,
    content_type: str,
    content_encoding: str = "",
    maximum_decoded_bytes: int = 262144,
) -> tuple[str, ...]:
    if "json" not in content_type.casefold():
        return ()
    json_payload, should_clear = _decode_json_payload(
        payload,
        content_encoding=content_encoding,
        maximum_decoded_bytes=maximum_decoded_bytes,
    )
    try:
        try:
            decoded = json.loads(json_payload)
        except UnicodeDecodeError, json.JSONDecodeError:
            return ()
        candidates: list[str] = []
        _collect_endpoint_candidates(decoded, candidates)
        return tuple(dict.fromkeys(candidates))
    finally:
        if should_clear:
            json_payload[:] = b"\x00" * len(json_payload)


def serialised_schema_contains(schema: ResponseSchema, secret: str) -> bool:
    return bool(secret and secret in json.dumps(schema.as_event(), sort_keys=True))
