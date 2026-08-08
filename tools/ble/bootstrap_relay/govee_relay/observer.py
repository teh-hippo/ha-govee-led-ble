from __future__ import annotations

import ipaddress
import json
import socket
import struct
import threading
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass

from .events import EventSink, EventType


class DnsWireError(ValueError):
    """A DNS query is outside the observer's tiny supported shape."""


def _parse_dns_question(packet: bytes) -> tuple[str, int, int, int]:
    if len(packet) < 13:
        raise DnsWireError("DNS packet is too short")
    labels: list[str] = []
    offset = 12
    while True:
        if offset >= len(packet):
            raise DnsWireError("DNS name is truncated")
        length = packet[offset]
        offset += 1
        if length == 0:
            break
        if length & 0xC0:
            raise DnsWireError("compressed query names are not supported")
        if offset + length > len(packet):
            raise DnsWireError("DNS label is truncated")
        labels.append(packet[offset : offset + length].decode("ascii"))
        offset += length
    if offset + 4 > len(packet):
        raise DnsWireError("DNS question type/class is truncated")
    query_type, query_class = struct.unpack("!HH", packet[offset : offset + 4])
    return ".".join(labels).casefold(), offset + 4, query_type, query_class


def parse_dns_question_name(packet: bytes) -> str:
    return _parse_dns_question(packet)[0]


def build_nxdomain_response(query: bytes) -> bytes:
    if len(query) < 12:
        raise DnsWireError("DNS packet is too short")
    _name, question_end, _query_type, _query_class = _parse_dns_question(query)
    flags = b"\x81\x83"
    return query[:2] + flags + query[4:6] + b"\x00\x00\x00\x00\x00\x00" + query[12:question_end]


def build_nodata_response(query: bytes) -> bytes:
    if len(query) < 12:
        raise DnsWireError("DNS packet is too short")
    _name, question_end, _query_type, _query_class = _parse_dns_question(query)
    flags = b"\x81\x80"
    return query[:2] + flags + query[4:6] + b"\x00\x00\x00\x00\x00\x00" + query[12:question_end]


def build_ipv4_response(query: bytes, address: str) -> bytes:
    if len(query) < 12:
        raise DnsWireError("DNS packet is too short")
    _name, question_end, query_type, query_class = _parse_dns_question(query)
    if query_type != 1 or query_class != 1:
        return build_nodata_response(query)
    packed_address = ipaddress.IPv4Address(address).packed
    flags = b"\x81\x80"
    answer = b"\xc0\x0c" + struct.pack("!HHIH", 1, 1, 5, len(packed_address)) + packed_address
    return query[:2] + flags + query[4:6] + b"\x00\x01\x00\x00\x00\x00" + query[12:question_end] + answer


class DnsObserver:
    def __init__(
        self,
        *,
        run_id: str,
        expected_hostname: str,
        events: EventSink,
        host: str = "127.0.0.1",
        port: int = 0,
        records: Mapping[str, str] | None = None,
    ) -> None:
        self.run_id = run_id
        self._expected_hostnames = {expected_hostname.casefold()} if expected_hostname else set()
        self._expected_lock = threading.Lock()
        self._records = {
            name.casefold(): str(ipaddress.IPv4Address(address)) for name, address in (records or {}).items()
        }
        self.events = events
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.bind((host, port))
        self._socket.settimeout(0.2)
        self._stop = threading.Event()
        self.matched = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._started = False

    @property
    def address(self) -> tuple[str, int]:
        host, port = self._socket.getsockname()
        return str(host), int(port)

    def start(self) -> None:
        if self._started:
            raise RuntimeError("DNS observer is already started")
        self._started = True
        self._thread.start()

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                query, address = self._socket.recvfrom(4096)
            except TimeoutError:
                continue
            except OSError:
                return
            try:
                name = parse_dns_question_name(query)
                with self._expected_lock:
                    matched = name in self._expected_hostnames
                if matched:
                    self.matched.set()
                    self.events.record(
                        EventType.DNS_MATCH,
                        run_id=self.run_id,
                        matched=True,
                    )
                response = (
                    build_ipv4_response(query, self._records[name])
                    if name in self._records
                    else build_nxdomain_response(query)
                )
                self._socket.sendto(response, address)
            except DnsWireError:
                continue

    def set_expected_hostnames(self, hostnames: tuple[str, ...]) -> None:
        with self._expected_lock:
            self._expected_hostnames = {hostname.casefold() for hostname in hostnames if hostname}

    def set_record(self, hostname: str, address: str) -> None:
        self._records[hostname.casefold()] = str(ipaddress.IPv4Address(address))

    def close(self) -> None:
        self._stop.set()
        self._socket.close()
        if self._started:
            self._thread.join(timeout=2)

    def __enter__(self) -> DnsObserver:
        self.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


class NtpResponder:
    def __init__(self, *, host: str = "127.0.0.1", port: int = 0) -> None:
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.bind((host, port))
        self._socket.settimeout(0.2)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._started = False

    @property
    def address(self) -> tuple[str, int]:
        host, port = self._socket.getsockname()
        return str(host), int(port)

    def start(self) -> None:
        if self._started:
            raise RuntimeError("NTP responder is already started")
        self._started = True
        self._thread.start()

    @staticmethod
    def _timestamp() -> bytes:
        value = time.time() + 2_208_988_800
        seconds = int(value)
        fraction = int((value - seconds) * (1 << 32))
        return struct.pack("!II", seconds, fraction)

    @classmethod
    def response(cls, request: bytes) -> bytes:
        if len(request) < 48:
            raise ValueError("NTP request is too short")
        version = (request[0] >> 3) & 0x07
        first = (version << 3) | 4
        now = cls._timestamp()
        return struct.pack("!BBBbII4s", first, 2, request[2], -20, 0, 0, b"LOCL") + now + request[40:48] + now + now

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                request, address = self._socket.recvfrom(512)
            except TimeoutError:
                continue
            except OSError:
                return
            try:
                self._socket.sendto(self.response(request), address)
            except ValueError:
                continue

    def close(self) -> None:
        self._stop.set()
        self._socket.close()
        if self._started:
            self._thread.join(timeout=2)

    def __enter__(self) -> NtpResponder:
        self.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


@dataclass(frozen=True, slots=True)
class EgressObservation:
    destination_class: str
    port: int | None

    def validate(self) -> None:
        if self.destination_class not in {
            "bootstrap-relay",
            "dns",
            "ntp",
            "unexpected-public",
            "unexpected-private",
        }:
            raise ValueError("unsupported egress destination class")
        if self.port is not None and not 1 <= self.port <= 65535:
            raise ValueError("invalid egress port")

    def record(self, *, run_id: str, events: EventSink) -> None:
        self.validate()
        events.record(
            EventType.EGRESS_DENIED,
            run_id=run_id,
            destination_class=self.destination_class,
            port=self.port,
        )


@dataclass(frozen=True, slots=True)
class IsolationManifest:
    ssid_characters: int = 7
    passphrase_characters: int = 8
    band: str = "2.4GHz"
    security: str = "WPA2-PSK"
    pmf: str = "off"
    band_steering: bool = False
    client_isolation: bool = True
    ipv6_ra: bool = False
    local_services: tuple[str, ...] = ("DHCP", "DNS", "NTP", "HTTPS relay")
    h6199_allowed_destinations: tuple[str, ...] = ("relay", "DNS", "NTP")
    relay_allowed_destinations: tuple[str, ...] = ("device.govee.com:443",)
    deny_other_egress: bool = True
    denied_egress_logging: bool = False
    applied: bool = False

    def validate(self) -> None:
        if self.applied:
            raise ValueError("Phase 1 manifests must remain unapplied")
        if self.ssid_characters != 7 or self.passphrase_characters != 8:
            raise ValueError("manifest must use a captured Wi-Fi field-length class")
        if self.band != "2.4GHz" or self.security != "WPA2-PSK":
            raise ValueError("manifest does not match the proven association shape")
        if self.pmf != "off" or self.band_steering:
            raise ValueError("PMF and band steering must remain disabled")
        if self.ipv6_ra or not self.client_isolation:
            raise ValueError("IPv6/RA must be off and client isolation on")
        if not self.deny_other_egress:
            raise ValueError("other egress must remain denied")

    def render(self) -> str:
        self.validate()
        return json.dumps(asdict(self), indent=2)
