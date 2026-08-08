from __future__ import annotations

import socket
import ssl
import threading
from collections.abc import Callable

from .events import EventSink, EventType
from .http_wire import (
    ParsedDeviceRequest,
    UpstreamResponse,
    build_device_response,
    parse_device_request,
    read_head,
)
from .mutation import ResponseMutation
from .redaction import endpoint_candidates, extract_response_schema
from .upstream import SingleFlightResponse


class RelayEngine:
    def __init__(
        self,
        *,
        run_id: str,
        device_host: str,
        fetch_upstream: Callable[[ParsedDeviceRequest], UpstreamResponse],
        events: EventSink,
        on_endpoint_candidates: Callable[[tuple[str, ...]], None] | None = None,
        response_mutator: Callable[[bytearray, str, str], ResponseMutation] | None = None,
    ) -> None:
        self.run_id = run_id
        self.device_host = device_host
        self.fetch_upstream = fetch_upstream
        self.events = events
        self.on_endpoint_candidates = on_endpoint_candidates
        self.response_mutator = response_mutator
        self.cache = SingleFlightResponse()
        self._schema_recorded = False
        self._schema_lock = threading.Lock()

    def handle(self, raw_head: bytes) -> bytearray:
        request = parse_device_request(raw_head, expected_host=self.device_host)
        self.events.record(
            EventType.REQUEST_SHAPE,
            run_id=self.run_id,
            fingerprint={
                "method": request.fingerprint.method,
                "path": request.fingerprint.path,
                "http_version": request.fingerprint.http_version,
                "ordered_header_names": request.fingerprint.ordered_header_names,
                "ordered_query_keys": request.fingerprint.ordered_query_keys,
                "header_value_lengths": request.fingerprint.header_value_lengths,
                "query_value_lengths": request.fingerprint.query_value_lengths,
            },
        )
        response = self.cache.get(
            self.run_id,
            lambda: self.fetch_upstream(request),
        )
        with self._schema_lock:
            if not self._schema_recorded:
                content_type = next(
                    (
                        header.value.decode("ascii", errors="replace")
                        for header in response.headers
                        if header.lower_name == "content-type"
                    ),
                    "",
                )
                content_encoding = next(
                    (
                        header.value.decode("ascii", errors="replace")
                        for header in response.headers
                        if header.lower_name == "content-encoding"
                    ),
                    "",
                )
                schema = extract_response_schema(
                    response.payload,
                    content_type=content_type,
                    content_encoding=content_encoding,
                )
                if self.response_mutator is None:
                    candidates = endpoint_candidates(
                        response.payload,
                        content_type=content_type,
                        content_encoding=content_encoding,
                    )
                else:
                    mutation = self.response_mutator(
                        response.payload,
                        content_type,
                        content_encoding,
                    )
                    candidates = mutation.expected_hostnames
                    self.events.record(
                        EventType.RESPONSE_MUTATED,
                        run_id=self.run_id,
                        field=mutation.field,
                        original_length=mutation.original_length,
                        replacement_length=mutation.replacement_length,
                    )
                if self.on_endpoint_candidates is not None:
                    self.on_endpoint_candidates(candidates)
                self.events.record(
                    EventType.RESPONSE_SCHEMA,
                    run_id=self.run_id,
                    schema=schema.as_event(),
                )
                self._schema_recorded = True
        rendered = build_device_response(response)
        self.events.record(
            EventType.RESPONSE_RELAYED,
            run_id=self.run_id,
            status=response.status,
            body_length=len(response.payload),
        )
        return rendered

    def close(self) -> None:
        self.cache.clear()


class LoopbackTlsRelay:
    """Small TLS relay server used by offline parity and integration tests."""

    def __init__(
        self,
        *,
        context: ssl.SSLContext,
        engine: RelayEngine,
        host: str = "127.0.0.1",
        port: int = 0,
    ) -> None:
        self.context = context
        self.engine = engine
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind((host, port))
        self._listener.listen()
        self._listener.settimeout(0.2)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._started = False
        self._handlers: set[threading.Thread] = set()
        self._handlers_lock = threading.Lock()

    @property
    def address(self) -> tuple[str, int]:
        host, port = self._listener.getsockname()
        return str(host), int(port)

    def start(self) -> None:
        if self._started:
            raise RuntimeError("relay is already started")
        self._started = True
        self._thread.start()

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                raw, _address = self._listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            raw.settimeout(10)
            thread = threading.Thread(target=self._run_handler, args=(raw,), daemon=True)
            with self._handlers_lock:
                self._handlers.add(thread)
            thread.start()

    def _run_handler(self, raw: socket.socket) -> None:
        try:
            self._handle(raw)
        finally:
            with self._handlers_lock:
                self._handlers.discard(threading.current_thread())

    def _handle(self, raw: socket.socket) -> None:
        secure: ssl.SSLSocket | None = None
        try:
            secure = self.context.wrap_socket(raw, server_side=True)
            with secure:
                cipher = secure.cipher()
                self.engine.events.record(
                    EventType.TLS_ACCEPTED,
                    run_id=self.engine.run_id,
                    tls_version=secure.version(),
                    cipher=None if cipher is None else cipher[0],
                )
                with secure.makefile("rwb", buffering=0) as stream:
                    head = read_head(stream, maximum_bytes=16384)
                    response = self.engine.handle(head)
                    try:
                        secure.sendall(response)
                    finally:
                        response[:] = b"\x00" * len(response)
        except Exception as error:
            try:
                self.engine.events.record(
                    EventType.CONNECTION_FAILED,
                    run_id=self.engine.run_id,
                    reason=type(error).__name__,
                )
            finally:
                if secure is None:
                    raw.close()

    def close(self) -> None:
        self._stop.set()
        self._listener.close()
        if self._started:
            self._thread.join(timeout=2)
        with self._handlers_lock:
            handlers = list(self._handlers)
        for handler in handlers:
            handler.join(timeout=11)
        self.engine.close()

    def __enter__(self) -> LoopbackTlsRelay:
        self.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
