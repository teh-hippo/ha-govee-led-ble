from __future__ import annotations

import ssl
from pathlib import Path

from .events import EventSink
from .lifecycle import CleanupRegistry
from .mqtt_probe import MqttClientHelloProbe, MqttTlsConnectProbe
from .mutation import mutate_mqtt_address
from .observer import DnsObserver, NtpResponder
from .relay import LoopbackTlsRelay, RelayEngine
from .upstream import RawUpstreamClient


class RunAComponents:
    """Wire the tested relay components without providing a live CLI."""

    def __init__(
        self,
        *,
        run_id: str,
        device_host: str,
        device_context: ssl.SSLContext,
        upstream: RawUpstreamClient,
        event_path: Path,
        relay_host: str = "127.0.0.1",
        relay_port: int = 0,
        dns_host: str = "127.0.0.1",
        dns_port: int = 0,
        dns_records: dict[str, str] | None = None,
        ntp_host: str = "127.0.0.1",
        ntp_port: int = 0,
        mqtt_address_nonce: str | None = None,
        mqtt_probe_host: str | None = None,
        mqtt_probe_port: int | None = None,
        relay_ip: str | None = None,
        mqtt_server_context: ssl.SSLContext | None = None,
    ) -> None:
        self.events = EventSink(event_path)
        upstream.run_id = run_id
        upstream.events = self.events
        self.dns = DnsObserver(
            run_id=run_id,
            expected_hostname="",
            events=self.events,
            host=dns_host,
            port=dns_port,
            records=dns_records,
        )
        self.ntp = NtpResponder(host=ntp_host, port=ntp_port)
        self.mqtt_probe = (
            None
            if mqtt_probe_host is None or mqtt_probe_port is None or mqtt_address_nonce is None
            else (
                MqttTlsConnectProbe(
                    run_id=run_id,
                    context=mqtt_server_context,
                    events=self.events,
                    host=mqtt_probe_host,
                    port=mqtt_probe_port,
                )
                if mqtt_server_context is not None
                else MqttClientHelloProbe(
                    run_id=run_id,
                    expected_sni=mqtt_address_nonce,
                    events=self.events,
                    host=mqtt_probe_host,
                    port=mqtt_probe_port,
                )
            )
        )
        if self.mqtt_probe is not None:
            if relay_ip is None:
                raise ValueError("MQTT probe requires a relay IP")
            if mqtt_address_nonce is None:
                raise ValueError("MQTT probe requires a nonce hostname")
            self.dns.set_record(mqtt_address_nonce, relay_ip)
        self.engine = RelayEngine(
            run_id=run_id,
            device_host=device_host,
            fetch_upstream=upstream.fetch,
            events=self.events,
            on_endpoint_candidates=self.dns.set_expected_hostnames,
            response_mutator=(
                None
                if mqtt_address_nonce is None
                else lambda payload, content_type, content_encoding: mutate_mqtt_address(
                    payload,
                    content_type=content_type,
                    content_encoding=content_encoding,
                    replacement_hostname=mqtt_address_nonce,
                    expected_mqtt_port=mqtt_probe_port,
                )
            ),
        )
        self.relay = LoopbackTlsRelay(
            context=device_context,
            engine=self.engine,
            host=relay_host,
            port=relay_port,
        )
        self.upstream = upstream
        self.cleanup = CleanupRegistry()
        self.cleanup.add(self.events.close)
        self.cleanup.add(self.upstream.close)
        self.cleanup.add(self.dns.close)
        self.cleanup.add(self.ntp.close)
        if self.mqtt_probe is not None:
            self.cleanup.add(self.mqtt_probe.close)
        self.cleanup.add(self.relay.close)

    def start(self) -> None:
        try:
            self.upstream.prewarm()
            self.dns.start()
            self.ntp.start()
            if self.mqtt_probe is not None:
                self.mqtt_probe.start()
            self.relay.start()
        except Exception:
            self.close()
            raise

    def refresh_prewarm(self) -> None:
        self.upstream.prewarm(replace=True)

    def close(self) -> None:
        self.cleanup.close()

    def __enter__(self) -> RunAComponents:
        self.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
