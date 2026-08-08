from __future__ import annotations

import socket
import ssl
import struct
import threading

from .events import EventSink, EventType


class ClientHelloError(ValueError):
    """A peer did not send one bounded TLS ClientHello."""


def _read_exact(connection: socket.socket, length: int) -> bytes:
    value = bytearray()
    while len(value) < length:
        chunk = connection.recv(length - len(value))
        if not chunk:
            raise ClientHelloError("peer closed before ClientHello completed")
        value.extend(chunk)
    return bytes(value)


def _take(data: bytes, offset: int, length: int) -> tuple[bytes, int]:
    end = offset + length
    if end > len(data):
        raise ClientHelloError("ClientHello is truncated")
    return data[offset:end], end


def parse_client_hello(record: bytes, *, expected_sni: str) -> dict[str, object]:
    if len(record) < 9 or record[0] != 22:
        raise ClientHelloError("first TLS record is not a handshake")
    record_length = int.from_bytes(record[3:5], "big")
    if record_length != len(record) - 5 or record_length > 16384:
        raise ClientHelloError("invalid TLS record length")
    if record[5] != 1:
        raise ClientHelloError("first handshake is not ClientHello")
    handshake_length = int.from_bytes(record[6:9], "big")
    body, _offset = _take(record, 9, handshake_length)
    if handshake_length != len(body):
        raise ClientHelloError("invalid ClientHello length")

    offset = 0
    legacy_version, offset = _take(body, offset, 2)
    _random, offset = _take(body, offset, 32)
    session_length = body[offset]
    offset += 1
    _session, offset = _take(body, offset, session_length)
    cipher_bytes, offset = _take(body, offset + 2, int.from_bytes(body[offset : offset + 2], "big"))
    if len(cipher_bytes) % 2:
        raise ClientHelloError("cipher suite vector has odd length")
    compression_length = body[offset]
    offset += 1
    _compression, offset = _take(body, offset, compression_length)
    extension_types: list[int] = []
    sni_present = False
    sni_matched = False
    if offset < len(body):
        extension_length = int.from_bytes(body[offset : offset + 2], "big")
        extensions, offset = _take(body, offset + 2, extension_length)
        if offset != len(body):
            raise ClientHelloError("ClientHello has trailing bytes")
        extension_offset = 0
        while extension_offset < len(extensions):
            header, extension_offset = _take(extensions, extension_offset, 4)
            extension_type, value_length = struct.unpack("!HH", header)
            value, extension_offset = _take(extensions, extension_offset, value_length)
            extension_types.append(extension_type)
            if extension_type == 0:
                sni_present = True
                if len(value) < 5:
                    raise ClientHelloError("SNI extension is truncated")
                names_length = int.from_bytes(value[:2], "big")
                names = value[2 : 2 + names_length]
                if len(names) != names_length or not names:
                    raise ClientHelloError("SNI list is malformed")
                name_type = names[0]
                name_length = int.from_bytes(names[1:3], "big")
                name = names[3 : 3 + name_length]
                if name_type == 0 and len(name) == name_length:
                    sni_matched = name.decode("ascii", errors="strict").casefold() == expected_sni.casefold()
    return {
        "record_version": f"{record[1]}.{record[2]}",
        "client_version": f"{legacy_version[0]}.{legacy_version[1]}",
        "cipher_count": len(cipher_bytes) // 2,
        "extension_types": extension_types,
        "sni_present": sni_present,
        "sni_matched": sni_matched,
    }


class MqttClientHelloProbe:
    def __init__(
        self,
        *,
        run_id: str,
        expected_sni: str,
        events: EventSink,
        host: str,
        port: int,
    ) -> None:
        self.run_id = run_id
        self.expected_sni = expected_sni
        self.events = events
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind((host, port))
        self._listener.listen(1)
        self._listener.settimeout(0.2)
        self._stop = threading.Event()
        self.client_hello_seen = threading.Event()
        self.completed = self.client_hello_seen
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._started = False

    @property
    def address(self) -> tuple[str, int]:
        host, port = self._listener.getsockname()
        return str(host), int(port)

    def start(self) -> None:
        if self._started:
            raise RuntimeError("MQTT ClientHello probe is already started")
        self._started = True
        self._thread.start()

    def _serve(self) -> None:
        while not self._stop.is_set() and not self.client_hello_seen.is_set():
            try:
                connection, _address = self._listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            with connection:
                connection.settimeout(5)
                try:
                    header = _read_exact(connection, 5)
                    length = int.from_bytes(header[3:5], "big")
                    if length > 16384:
                        raise ClientHelloError("TLS record exceeds probe limit")
                    metadata = parse_client_hello(
                        header + _read_exact(connection, length),
                        expected_sni=self.expected_sni,
                    )
                except ClientHelloError, OSError, UnicodeDecodeError:
                    continue
                self.events.record(
                    EventType.MQTT_CLIENT_HELLO,
                    run_id=self.run_id,
                    **metadata,
                )
                self.client_hello_seen.set()

    def close(self) -> None:
        self._stop.set()
        self._listener.close()
        if self._started:
            self._thread.join(timeout=6)


def _read_mqtt_remaining_length(connection: ssl.SSLSocket) -> tuple[int, int]:
    value = 0
    multiplier = 1
    count = 0
    while count < 4:
        encoded = _read_exact(connection, 1)[0]
        count += 1
        value += (encoded & 0x7F) * multiplier
        if not encoded & 0x80:
            return value, count
        multiplier *= 128
    raise ValueError("MQTT remaining length exceeds four bytes")


def parse_mqtt_connect(packet: bytes) -> dict[str, object]:
    if not packet or packet[0] >> 4 != 1 or packet[0] & 0x0F:
        raise ValueError("first MQTT packet is not CONNECT")
    offset = 1
    remaining_length = 0
    multiplier = 1
    while offset < len(packet) and multiplier <= 128**3:
        encoded = packet[offset]
        offset += 1
        remaining_length += (encoded & 0x7F) * multiplier
        if not encoded & 0x80:
            break
        multiplier *= 128
    else:
        raise ValueError("invalid MQTT remaining length")
    if remaining_length != len(packet) - offset:
        raise ValueError("MQTT CONNECT length does not match packet")

    def take_u16() -> int:
        nonlocal offset
        if offset + 2 > len(packet):
            raise ValueError("MQTT CONNECT is truncated")
        value = int.from_bytes(packet[offset : offset + 2], "big")
        offset += 2
        return value

    protocol_length = take_u16()
    if offset + protocol_length + 4 > len(packet):
        raise ValueError("MQTT CONNECT variable header is truncated")
    protocol_name = packet[offset : offset + protocol_length]
    offset += protocol_length
    protocol_level = packet[offset]
    connect_flags = packet[offset + 1]
    keepalive = int.from_bytes(packet[offset + 2 : offset + 4], "big")
    offset += 4
    if protocol_name != b"MQTT" or protocol_level not in {4, 5}:
        raise ValueError("unsupported MQTT protocol")
    if connect_flags & 0x01:
        raise ValueError("MQTT CONNECT reserved flag is set")

    client_id_length = take_u16()
    if offset + client_id_length > len(packet):
        raise ValueError("MQTT client ID is truncated")
    offset += client_id_length
    will_present = bool(connect_flags & 0x04)
    if will_present:
        will_topic_length = take_u16()
        offset += will_topic_length
        will_payload_length = take_u16()
        offset += will_payload_length
    if connect_flags & 0x80:
        username_length = take_u16()
        offset += username_length
    if connect_flags & 0x40:
        password_length = take_u16()
        offset += password_length
    if offset != len(packet):
        raise ValueError("MQTT CONNECT payload shape is inconsistent")
    return {
        "protocol_level": protocol_level,
        "remaining_length": remaining_length,
        "clean_session": bool(connect_flags & 0x02),
        "keepalive": keepalive,
        "client_id_length": client_id_length,
        "username_present": bool(connect_flags & 0x80),
        "password_present": bool(connect_flags & 0x40),
        "will_present": will_present,
        "will_qos": (connect_flags >> 3) & 0x03,
        "will_retain": bool(connect_flags & 0x20),
    }


class MqttTlsConnectProbe:
    def __init__(
        self,
        *,
        run_id: str,
        context: ssl.SSLContext,
        events: EventSink,
        host: str,
        port: int,
    ) -> None:
        self.run_id = run_id
        self.context = context
        self.events = events
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind((host, port))
        self._listener.listen(1)
        self._listener.settimeout(0.2)
        self._stop = threading.Event()
        self.completed = threading.Event()
        self.failed = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._started = False

    @property
    def address(self) -> tuple[str, int]:
        host, port = self._listener.getsockname()
        return str(host), int(port)

    def start(self) -> None:
        if self._started:
            raise RuntimeError("MQTT TLS probe is already started")
        self._started = True
        self._thread.start()

    def _serve(self) -> None:
        while not self._stop.is_set() and not self.completed.is_set():
            try:
                connection, _address = self._listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            connection.settimeout(8)
            try:
                with self.context.wrap_socket(connection, server_side=True) as secure:
                    cipher = secure.cipher()
                    self.events.record(
                        EventType.MQTT_TLS_ACCEPTED,
                        run_id=self.run_id,
                        tls_version=secure.version(),
                        cipher=None if cipher is None else cipher[0],
                    )
                    first = _read_exact(secure, 1)
                    remaining_length, encoded_length = _read_mqtt_remaining_length(secure)
                    if remaining_length > 16384:
                        raise ValueError("MQTT CONNECT exceeds probe limit")
                    variable = _read_exact(secure, remaining_length)
                    metadata = parse_mqtt_connect(
                        first + _encode_mqtt_remaining_length(remaining_length, encoded_length) + variable
                    )
                    self.events.record(
                        EventType.MQTT_CONNECT_SHAPE,
                        run_id=self.run_id,
                        **metadata,
                    )
                    self.completed.set()
            except TimeoutError:
                self.events.record(
                    EventType.MQTT_TLS_FAILED,
                    run_id=self.run_id,
                    reason="timeout",
                )
                self.failed.set()
                self.completed.set()
                connection.close()
            except ssl.SSLError as error:
                reason = getattr(error, "reason", None)
                safe_reason = (
                    reason
                    if isinstance(reason, str) and reason.replace("_", "").isalnum() and len(reason) <= 64
                    else "ssl_error"
                )
                self.events.record(
                    EventType.MQTT_TLS_FAILED,
                    run_id=self.run_id,
                    reason=safe_reason,
                )
                self.failed.set()
                self.completed.set()
                connection.close()
            except OSError, ValueError:
                self.events.record(
                    EventType.MQTT_TLS_FAILED,
                    run_id=self.run_id,
                    reason="protocol_error",
                )
                self.failed.set()
                self.completed.set()
                connection.close()

    def close(self) -> None:
        self._stop.set()
        self._listener.close()
        if self._started:
            self._thread.join(timeout=9)


def _encode_mqtt_remaining_length(value: int, expected_bytes: int) -> bytes:
    encoded = bytearray()
    while True:
        digit = value % 128
        value //= 128
        if value:
            digit |= 0x80
        encoded.append(digit)
        if not value:
            break
    if len(encoded) != expected_bytes:
        raise ValueError("MQTT remaining length encoding is non-canonical")
    return bytes(encoded)
