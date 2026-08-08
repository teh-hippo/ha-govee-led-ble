from __future__ import annotations

import socket
import ssl
import threading
from collections.abc import Callable


def start_tls_server(
    context: ssl.SSLContext,
    handler: Callable[[ssl.SSLSocket], None],
) -> tuple[tuple[str, int], threading.Thread]:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen()

    def run() -> None:
        try:
            raw, _address = listener.accept()
            try:
                with context.wrap_socket(raw, server_side=True) as secure:
                    handler(secure)
            except OSError, ssl.SSLError:
                raw.close()
        finally:
            listener.close()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    host, port = listener.getsockname()
    return (str(host), int(port)), thread


def read_to_end(sock: ssl.SSLSocket) -> bytes:
    payload = bytearray()
    while True:
        chunk = sock.recv(8192)
        if not chunk:
            return bytes(payload)
        payload.extend(chunk)
