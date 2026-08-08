from __future__ import annotations

import ipaddress
import socket

import pytest

from govee_relay.guards import harden_process


class OfflineEgressError(RuntimeError):
    """The offline suite attempted a non-loopback connection."""


def _is_loopback(value: object) -> bool:
    try:
        return ipaddress.ip_address(str(value)).is_loopback
    except ValueError:
        return False


@pytest.fixture(scope="session", autouse=True)
def hardened_test_process():
    harden_process()


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch):
    original_getaddrinfo = socket.getaddrinfo
    original_connect = socket.socket.connect
    original_sendto = socket.socket.sendto

    def guarded_getaddrinfo(host, *args, **kwargs):
        results = original_getaddrinfo(host, *args, **kwargs)
        if any(not _is_loopback(result[4][0]) for result in results):
            raise OfflineEgressError(f"offline DNS resolved non-loopback host {host!r}")
        return results

    def guarded_connect(sock, address):
        if isinstance(address, str):
            return original_connect(sock, address)
        if not _is_loopback(address[0]):
            raise OfflineEgressError(f"offline socket attempted {address!r}")
        return original_connect(sock, address)

    def guarded_sendto(sock, data, address):
        if isinstance(address, str):
            return original_sendto(sock, data, address)
        if not _is_loopback(address[0]):
            raise OfflineEgressError(f"offline UDP socket attempted {address!r}")
        return original_sendto(sock, data, address)

    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "sendto", guarded_sendto)
