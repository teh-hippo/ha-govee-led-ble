from __future__ import annotations

import io

import pytest

from govee_relay.http_wire import (
    HttpWireError,
    build_device_response,
    build_upstream_request,
    gzip_payload,
    parse_device_request,
    read_upstream_response,
)

DEVICE_HOST = "govee.ai.xaz.lol"
QUERY = b"device=AA%3ABB%3ACC&sku=H6199&wifiHardVersion=1.2.3&wifiSoftVersion=4.5.6"


def request(*extra_headers: bytes) -> bytes:
    lines = [
        b"POST /device/v1/base/config?" + QUERY + b" HTTP/1.1",
        b"Accept: */*",
        b"Host: " + DEVICE_HOST.encode(),
        b"envId: 0",
        b"iotVersion: 0",
        *extra_headers,
    ]
    return b"\r\n".join(lines) + b"\r\n\r\n"


def test_request_parsing_and_exact_upstream_shape():
    parsed = parse_device_request(
        request(b"Connection: keep-alive", b"X-New-Firmware: present"),
        expected_host=DEVICE_HOST,
    )
    upstream = build_upstream_request(parsed, upstream_host="device.govee.com")

    assert parsed.raw_query == QUERY
    assert parsed.fingerprint.ordered_header_names == (
        "Accept",
        "Host",
        "envId",
        "iotVersion",
        "Connection",
        "X-New-Firmware",
    )
    assert upstream == (
        b"POST /device/v1/base/config?" + QUERY + b" HTTP/1.1\r\n"
        b"Accept: */*\r\n"
        b"Host: device.govee.com\r\n"
        b"envId: 0\r\n"
        b"iotVersion: 0\r\n"
        b"X-New-Firmware: present\r\n\r\n"
    )
    assert b"Connection:" not in upstream
    assert b"User-Agent:" not in upstream
    assert b"Accept-Encoding:" not in upstream
    assert b"Content-Length:" not in upstream


@pytest.mark.parametrize(
    "bad",
    [
        request().replace(b"device=AA%3ABB%3ACC", b"device=a&device=b"),
        request().replace(b"sku=H6199&", b""),
        request(b"Content-Length: 1"),
        request(b"Transfer-Encoding: chunked"),
        request().replace(b"Host: govee.ai.xaz.lol", b"Host: wrong.example"),
    ],
)
def test_request_rejections(bad: bytes):
    with pytest.raises(HttpWireError):
        parse_device_request(bad, expected_host=DEVICE_HOST)


def test_unknown_query_key_is_fingerprinted_and_forwarded_verbatim():
    raw = request().replace(
        b"wifiSoftVersion=4.5.6",
        b"wifiSoftVersion=4.5.6&futureFlag=a%20b",
    )
    parsed = parse_device_request(raw, expected_host=DEVICE_HOST)
    upstream = build_upstream_request(parsed, upstream_host="device.govee.com")
    assert parsed.fingerprint.ordered_query_keys[-1] == "futureFlag"
    assert b"futureFlag=a%20b" in upstream


def test_content_length_zero_is_preserved_upstream():
    parsed = parse_device_request(
        request(b"Content-Length: 0"),
        expected_host=DEVICE_HOST,
    )
    upstream = build_upstream_request(parsed, upstream_host="device.govee.com")
    assert b"Content-Length: 0\r\n" in upstream


def test_identity_response_payload_is_preserved():
    body = b'{"code":200,"data":{"endpoint":"nonce.example"}}'
    raw = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: application/json\r\n"
        b"X-Govee-Test: yes\r\n" + f"Content-Length: {len(body)}\r\n\r\n".encode() + body
    )
    response = read_upstream_response(io.BytesIO(raw))
    rendered = build_device_response(response)
    assert rendered.endswith(body)
    assert b"X-Govee-Test: yes" in rendered
    assert f"Content-Length: {len(body)}".encode() in rendered


def test_chunked_response_is_dechunked_without_changing_payload():
    body = b'{"code":200,"data":{}}'
    raw = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: application/json\r\n"
        b"Transfer-Encoding: chunked\r\n\r\n" + f"{len(body):X}\r\n".encode() + body + b"\r\n0\r\n\r\n"
    )
    response = read_upstream_response(io.BytesIO(raw))
    rendered = build_device_response(response)
    assert bytes(response.payload) == body
    assert rendered.endswith(body)
    assert b"Transfer-Encoding:" not in rendered


def test_gzip_response_stays_encoded_and_preserves_header():
    body = gzip_payload(b'{"code":200,"data":{}}')
    raw = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: application/json\r\n"
        b"Content-Encoding: gzip\r\n" + f"Content-Length: {len(body)}\r\n\r\n".encode() + body
    )
    response = read_upstream_response(io.BytesIO(raw))
    rendered = build_device_response(response)
    assert bytes(response.payload) == body
    assert rendered.endswith(body)
    assert b"Content-Encoding: gzip" in rendered


def test_response_limits_fail_closed():
    with pytest.raises(HttpWireError, match="headers exceed"):
        read_upstream_response(
            io.BytesIO(b"HTTP/1.1 200 OK\r\nX:" + b"a" * 50 + b"\r\n\r\n"),
            maximum_header_bytes=32,
        )


def test_response_reason_phrase_is_optional():
    response = read_upstream_response(io.BytesIO(b"HTTP/1.1 200\r\nContent-Length: 0\r\n\r\n"))
    assert response.status == 200
    assert response.reason == b""


def test_204_response_does_not_wait_for_connection_close():
    response = read_upstream_response(io.BytesIO(b"HTTP/1.1 204 No Content\r\nConnection: keep-alive\r\n\r\nignored"))
    assert response.payload == bytearray()
