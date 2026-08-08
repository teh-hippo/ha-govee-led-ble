from __future__ import annotations

import gzip
import io
import re
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import unquote_plus

BOOTSTRAP_PATH = b"/device/v1/base/config"
EXPECTED_QUERY_KEYS = frozenset({"device", "sku", "wifiHardVersion", "wifiSoftVersion"})
HOP_BY_HOP_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)
HEADER_NAME = re.compile(rb"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")


class HttpWireError(ValueError):
    """The peer sent a shape outside the bounded relay contract."""


class BinaryReader(Protocol):
    def read(self, size: int = -1) -> bytes: ...

    def readline(self, size: int = -1) -> bytes: ...


@dataclass(frozen=True, slots=True)
class Header:
    name: bytes
    value: bytes

    @property
    def lower_name(self) -> str:
        return self.name.decode("ascii").casefold()


@dataclass(frozen=True, slots=True)
class RequestFingerprint:
    method: str
    path: str
    http_version: str
    ordered_header_names: tuple[str, ...]
    ordered_query_keys: tuple[str, ...]
    header_value_lengths: tuple[int, ...]
    query_value_lengths: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ParsedDeviceRequest:
    method: bytes
    path: bytes
    raw_query: bytes
    version: bytes
    headers: tuple[Header, ...]
    fingerprint: RequestFingerprint


@dataclass(slots=True)
class UpstreamResponse:
    version: bytes
    status: int
    reason: bytes
    headers: tuple[Header, ...]
    payload: bytearray

    def clear(self) -> None:
        self.payload[:] = b"\x00" * len(self.payload)


def _parse_query(raw_query: bytes) -> tuple[tuple[str, ...], tuple[int, ...]]:
    if not raw_query:
        raise HttpWireError("the bootstrap request is missing its query")
    keys: list[str] = []
    value_lengths: list[int] = []
    for component in raw_query.split(b"&"):
        key_bytes, separator, value = component.partition(b"=")
        if not separator:
            raise HttpWireError("every bootstrap query key must have a value")
        try:
            key = unquote_plus(key_bytes.decode("ascii"))
        except (UnicodeDecodeError, ValueError) as error:
            raise HttpWireError("invalid query-key encoding") from error
        keys.append(key)
        value_lengths.append(len(value))
    if len(keys) != len(set(keys)):
        raise HttpWireError("duplicate bootstrap query key")
    if not EXPECTED_QUERY_KEYS.issubset(keys):
        raise HttpWireError("bootstrap query is missing a required key")
    return tuple(keys), tuple(value_lengths)


def parse_device_request(raw_head: bytes, *, expected_host: str) -> ParsedDeviceRequest:
    if not raw_head.endswith(b"\r\n\r\n"):
        raise HttpWireError("incomplete HTTP request head")
    lines = raw_head[:-4].split(b"\r\n")
    try:
        method, target, version = lines[0].split(b" ", 2)
    except ValueError as error:
        raise HttpWireError("malformed HTTP request line") from error
    path, separator, raw_query = target.partition(b"?")
    if method != b"POST" or path != BOOTSTRAP_PATH or not separator:
        raise HttpWireError("unexpected bootstrap method or path")
    if not version.startswith(b"HTTP/"):
        raise HttpWireError("unexpected HTTP version")

    headers: list[Header] = []
    for line in lines[1:]:
        name, separator, value = line.partition(b":")
        if not separator or not HEADER_NAME.fullmatch(name):
            raise HttpWireError("malformed HTTP header")
        headers.append(Header(name, value.strip()))
    by_name: dict[str, list[Header]] = {}
    for header in headers:
        by_name.setdefault(header.lower_name, []).append(header)
    host_headers = by_name.get("host", [])
    if len(host_headers) != 1:
        raise HttpWireError("the bootstrap request must carry one Host header")
    if host_headers[0].value.decode("ascii", errors="strict") != expected_host:
        raise HttpWireError("unexpected device-facing Host")
    if "transfer-encoding" in by_name:
        raise HttpWireError("the bootstrap request must not be chunked")
    if "content-length" in by_name:
        values = by_name["content-length"]
        if len(values) != 1 or values[0].value != b"0":
            raise HttpWireError("the bootstrap request body must be empty")
    for required in ("accept", "envid", "iotversion"):
        if len(by_name.get(required, [])) != 1:
            raise HttpWireError(f"missing or duplicate {required} header")

    query_keys, query_lengths = _parse_query(raw_query)
    fingerprint = RequestFingerprint(
        method=method.decode("ascii"),
        path=path.decode("ascii"),
        http_version=version.decode("ascii"),
        ordered_header_names=tuple(header.name.decode("ascii") for header in headers),
        ordered_query_keys=query_keys,
        header_value_lengths=tuple(len(header.value) for header in headers),
        query_value_lengths=query_lengths,
    )
    return ParsedDeviceRequest(
        method=method,
        path=path,
        raw_query=raw_query,
        version=version,
        headers=tuple(headers),
        fingerprint=fingerprint,
    )


def build_upstream_request(
    request: ParsedDeviceRequest,
    *,
    upstream_host: str,
) -> bytes:
    lines = [b"POST " + request.path + b"?" + request.raw_query + b" HTTP/1.1"]
    for header in request.headers:
        lower = header.lower_name
        if lower == "host":
            lines.append(header.name + b": " + upstream_host.encode("ascii"))
        elif lower in HOP_BY_HOP_HEADERS or lower.startswith("proxy-"):
            continue
        else:
            lines.append(header.name + b": " + header.value)
    return b"\r\n".join(lines) + b"\r\n\r\n"


def read_head(stream: BinaryReader, *, maximum_bytes: int) -> bytes:
    buffer = bytearray()
    while not buffer.endswith(b"\r\n\r\n"):
        chunk = stream.read(1)
        if not chunk:
            raise HttpWireError("peer closed before HTTP headers completed")
        buffer.extend(chunk)
        if len(buffer) > maximum_bytes:
            raise HttpWireError("HTTP headers exceed the configured limit")
    return bytes(buffer)


def _parse_response_head(raw_head: bytes, *, maximum_headers: int) -> tuple[bytes, int, bytes, tuple[Header, ...]]:
    lines = raw_head[:-4].split(b"\r\n")
    try:
        parts = lines[0].split(b" ", 2)
        if len(parts) == 2:
            version, status_bytes = parts
            reason = b""
        else:
            version, status_bytes, reason = parts
        status = int(status_bytes)
    except (ValueError, UnicodeError) as error:
        raise HttpWireError("malformed HTTP response status") from error
    if len(lines) - 1 > maximum_headers:
        raise HttpWireError("HTTP response has too many headers")
    headers: list[Header] = []
    for line in lines[1:]:
        name, separator, value = line.partition(b":")
        if not separator or not HEADER_NAME.fullmatch(name):
            raise HttpWireError("malformed HTTP response header")
        headers.append(Header(name, value.strip()))
    return version, status, reason, tuple(headers)


def _header_values(headers: tuple[Header, ...], name: str) -> list[bytes]:
    return [header.value for header in headers if header.lower_name == name]


def _read_exact(stream: BinaryReader, length: int) -> bytearray:
    payload = bytearray()
    while len(payload) < length:
        chunk = stream.read(length - len(payload))
        if not chunk:
            raise HttpWireError("peer closed before the response body completed")
        payload.extend(chunk)
    return payload


def _read_chunked(stream: BinaryReader, *, maximum_body_bytes: int) -> bytearray:
    payload = bytearray()
    while True:
        line = stream.readline()
        if not line.endswith(b"\r\n"):
            raise HttpWireError("malformed chunk length")
        size_token = line[:-2].split(b";", 1)[0]
        try:
            size = int(size_token, 16)
        except ValueError as error:
            raise HttpWireError("invalid chunk length") from error
        if size == 0:
            if stream.readline() != b"\r\n":
                raise HttpWireError("chunk trailers are not supported")
            return payload
        if len(payload) + size > maximum_body_bytes:
            raise HttpWireError("HTTP response body exceeds the configured limit")
        payload.extend(_read_exact(stream, size))
        if stream.read(2) != b"\r\n":
            raise HttpWireError("malformed chunk terminator")


def read_upstream_response(
    stream: BinaryReader,
    *,
    maximum_header_bytes: int = 32768,
    maximum_headers: int = 64,
    maximum_body_bytes: int = 262144,
) -> UpstreamResponse:
    raw_head = read_head(stream, maximum_bytes=maximum_header_bytes)
    version, status, reason, headers = _parse_response_head(raw_head, maximum_headers=maximum_headers)
    transfer_encoding = _header_values(headers, "transfer-encoding")
    content_lengths = _header_values(headers, "content-length")
    if status in {*range(100, 200), 204, 304}:
        payload = bytearray()
    elif transfer_encoding:
        if len(transfer_encoding) != 1 or transfer_encoding[0].lower() != b"chunked":
            raise HttpWireError("unsupported Transfer-Encoding")
        payload = _read_chunked(stream, maximum_body_bytes=maximum_body_bytes)
    elif content_lengths:
        if len(content_lengths) != 1:
            raise HttpWireError("duplicate Content-Length")
        try:
            length = int(content_lengths[0])
        except ValueError as error:
            raise HttpWireError("invalid Content-Length") from error
        if not 0 <= length <= maximum_body_bytes:
            raise HttpWireError("HTTP response body exceeds the configured limit")
        payload = _read_exact(stream, length)
    else:
        payload = bytearray()
        while True:
            chunk = stream.read(8192)
            if not chunk:
                break
            payload.extend(chunk)
            if len(payload) > maximum_body_bytes:
                raise HttpWireError("HTTP response body exceeds the configured limit")
    return UpstreamResponse(version, status, reason, headers, payload)


def build_device_response(response: UpstreamResponse) -> bytearray:
    lines = [b"HTTP/1.0 " + str(response.status).encode("ascii") + b" " + response.reason]
    for header in response.headers:
        lower = header.lower_name
        if lower in HOP_BY_HOP_HEADERS or lower in {"content-length", "transfer-encoding"}:
            continue
        lines.append(header.name + b": " + header.value)
    lines.append(b"Content-Length: " + str(len(response.payload)).encode("ascii"))
    return bytearray(b"\r\n".join(lines) + b"\r\n\r\n") + response.payload


def gzip_payload(payload: bytes) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as handle:
        handle.write(payload)
    return buffer.getvalue()
