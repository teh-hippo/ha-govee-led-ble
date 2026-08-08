from __future__ import annotations

import ipaddress
import socket
import ssl
import threading
import time
from collections.abc import Callable

from .events import EventSink, EventType
from .http_wire import (
    ParsedDeviceRequest,
    UpstreamResponse,
    build_upstream_request,
    read_upstream_response,
)

Resolver = Callable[[str, int], list[tuple[int, tuple[object, ...]]]]


def system_resolver(host: str, port: int) -> list[tuple[int, tuple[object, ...]]]:
    return [
        (family, sockaddr)
        for family, socktype, _protocol, _canonical, sockaddr in socket.getaddrinfo(
            host,
            port,
            type=socket.SOCK_STREAM,
        )
        if socktype == socket.SOCK_STREAM
    ]


def address_is_public(sockaddr: tuple[object, ...]) -> bool:
    address = ipaddress.ip_address(str(sockaddr[0]))
    return address.is_global


class DeadlineReader:
    def __init__(
        self,
        secure: ssl.SSLSocket,
        *,
        deadline: float,
    ) -> None:
        self._secure = secure
        self._stream = secure.makefile("rb", buffering=0)
        self._deadline = deadline

    def _set_remaining_timeout(self) -> None:
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("upstream response exceeded the wall-clock deadline")
        self._secure.settimeout(remaining)

    def read(self, size: int = -1) -> bytes:
        self._set_remaining_timeout()
        return self._stream.read(size)

    def readline(self, size: int = -1) -> bytes:
        self._set_remaining_timeout()
        return self._stream.readline(size)

    def close(self) -> None:
        self._stream.close()


class RawUpstreamClient:
    """One pre-warmed, verified HTTP/1.1 connection to the bootstrap endpoint."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        context: ssl.SSLContext,
        resolver: Resolver = system_resolver,
        timeout_seconds: float = 3.0,
        require_public_address: bool = True,
        run_id: str | None = None,
        events: EventSink | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.context = context
        self.resolver = resolver
        self.timeout_seconds = timeout_seconds
        self.require_public_address = require_public_address
        self.run_id = run_id
        self.events = events
        self._tls_socket: ssl.SSLSocket | None = None
        self._lock = threading.Lock()
        self.requests_sent = 0
        self.fetch_count = 0

    @property
    def is_prewarmed(self) -> bool:
        return self._tls_socket is not None

    def prewarm(self, *, replace: bool = False) -> None:
        with self._lock:
            if self.requests_sent or self.fetch_count:
                raise RuntimeError("upstream connection cannot be replaced after a request")
            if self._tls_socket is not None:
                if not replace:
                    raise RuntimeError("upstream TLS is already pre-warmed")
                self._close_unlocked()
            addresses = self.resolver(self.host, self.port)
            if not addresses:
                raise RuntimeError("upstream resolver returned no addresses")
            family, sockaddr = addresses[0]
            if self.require_public_address and not address_is_public(sockaddr):
                raise RuntimeError("production upstream resolved to a non-public address")
            started = time.monotonic()
            raw = socket.socket(family, socket.SOCK_STREAM)
            raw.settimeout(self.timeout_seconds)
            try:
                raw.connect(sockaddr)
                self._tls_socket = self.context.wrap_socket(
                    raw,
                    server_hostname=self.host,
                )
            except Exception:
                raw.close()
                raise
            if self.events is not None and self.run_id is not None:
                self.events.record(
                    EventType.UPSTREAM_PREWARMED,
                    run_id=self.run_id,
                    duration_ms=round((time.monotonic() - started) * 1000, 3),
                )

    def fetch(self, request: ParsedDeviceRequest) -> UpstreamResponse:
        with self._lock:
            if self._tls_socket is None:
                raise RuntimeError("upstream TLS must be pre-warmed")
            if self.requests_sent or self.fetch_count:
                raise RuntimeError("one upstream request per client instance is permitted")
            payload = bytearray(build_upstream_request(request, upstream_host=self.host))
            started = time.monotonic()
            reader: DeadlineReader | None = None
            try:
                self._tls_socket.sendall(payload)
                self.requests_sent += 1
                reader = DeadlineReader(
                    self._tls_socket,
                    deadline=started + self.timeout_seconds,
                )
                response = read_upstream_response(reader)
                self.fetch_count += 1
                if self.events is not None and self.run_id is not None:
                    self.events.record(
                        EventType.UPSTREAM_FETCHED,
                        run_id=self.run_id,
                        status=response.status,
                        duration_ms=round((time.monotonic() - started) * 1000, 3),
                    )
                return response
            finally:
                payload[:] = b"\x00" * len(payload)
                if reader is not None:
                    reader.close()
                self._close_unlocked()

    def close(self) -> None:
        with self._lock:
            self._close_unlocked()

    def _close_unlocked(self) -> None:
        if self._tls_socket is not None:
            try:
                self._tls_socket.close()
            finally:
                self._tls_socket = None


class SingleFlightResponse:
    """Fetch one response for one run ID and replay it to every device retry."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._run_id: str | None = None
        self._response: UpstreamResponse | None = None
        self._error: BaseException | None = None
        self._fetching = False
        self._closed = False
        self.upstream_calls = 0

    def get(
        self,
        run_id: str,
        fetcher: Callable[[], UpstreamResponse],
    ) -> UpstreamResponse:
        with self._condition:
            if self._closed:
                raise RuntimeError("run cache closed")
            if self._run_id not in (None, run_id):
                raise RuntimeError("response cache cannot cross run IDs")
            self._run_id = run_id
            while self._fetching and not self._closed:
                self._condition.wait()
            if self._closed:
                raise RuntimeError("run cache closed")
            if self._response is not None:
                return self._response
            if self._error is not None:
                raise RuntimeError("the upstream request failed") from self._error
            self._fetching = True
        try:
            response = fetcher()
        except BaseException as error:
            with self._condition:
                self._error = error
                self._fetching = False
                self._condition.notify_all()
            raise
        with self._condition:
            if self._closed:
                response.clear()
                raise RuntimeError("run cache closed")
            self.upstream_calls += 1
            self._response = response
            self._fetching = False
            self._condition.notify_all()
            return response

    def clear(self) -> None:
        with self._condition:
            self._closed = True
            if self._response is not None:
                self._response.clear()
            self._response = None
            self._error = None
            self._run_id = None
            self._fetching = False
            self._condition.notify_all()
