from __future__ import annotations

import argparse
import ipaddress
import json
import os
import platform
import re
import shutil
import signal
import ssl
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .events import EventType
from .guards import harden_process
from .orchestrator import RunAComponents
from .tls_profiles import (
    build_device_server_context,
    build_upstream_context,
    generate_test_certificate,
)
from .upstream import RawUpstreamClient

UNCHANGED_ACK = "UNCHANGED-PRODUCTION-RELAY"
MUTATE_MQTT_ACK = "MUTATE-MQTT-ADDRESS-ONLY"
UPSTREAM_HOST = "device.govee.com"
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,31}$")


@dataclass(frozen=True, slots=True)
class LiveConfig:
    run_id: str
    device_host: str
    relay_ip: str
    work_dir: Path
    event_path: Path
    state_path: Path
    relay_host: str = "0.0.0.0"  # noqa: S104 - isolated VLAN listener
    relay_port: int = 443
    dns_host: str = "0.0.0.0"  # noqa: S104 - isolated VLAN listener
    dns_port: int = 53
    ntp_host: str = "0.0.0.0"  # noqa: S104 - isolated VLAN listener
    ntp_port: int = 123
    deadline_seconds: float = 35.0
    prewarm_refresh_seconds: float = 8.0
    upstream_timeout_seconds: float = 3.0
    mqtt_address_nonce: str | None = None
    stop_on_dns_match: bool = False
    mqtt_probe_port: int | None = None
    capture_mqtt_connect: bool = False

    def validate(self) -> None:
        if not RUN_ID.fullmatch(self.run_id):
            raise ValueError("run ID must be 1-32 letters, digits or hyphens")
        if not self.device_host or "." not in self.device_host:
            raise ValueError("device-facing hostname is invalid")
        ipaddress.IPv4Address(self.relay_ip)
        if self.deadline_seconds <= 0 or self.prewarm_refresh_seconds <= 0:
            raise ValueError("live timing values must be positive")
        for port in (self.relay_port, self.dns_port, self.ntp_port):
            if not 0 <= port <= 65535:
                raise ValueError("listener port is invalid")
        if self.state_path == self.event_path:
            raise ValueError("state and event paths must differ")
        expected_nonce = f"{self.run_id}.nonce.{self.device_host}".casefold()
        if self.mqtt_address_nonce is not None and self.mqtt_address_nonce.casefold() != expected_nonce:
            raise ValueError("mqttAddress nonce must be derived from the run ID and device host")
        if self.capture_mqtt_connect and self.mqtt_probe_port is None:
            raise ValueError("MQTT CONNECT capture requires a probe port")
        if self.mqtt_address_nonce is not None and not self.stop_on_dns_match:
            if self.mqtt_probe_port is None:
                raise ValueError("mqttAddress mutation must stop on nonce DNS or ClientHello")
        if self.stop_on_dns_match and self.mqtt_probe_port is not None:
            raise ValueError("live run must choose one mutation stop condition")
        if self.mqtt_probe_port is not None and not 1 <= self.mqtt_probe_port <= 65535:
            raise ValueError("MQTT probe port is invalid")


def swap_total_kib(meminfo: Path = Path("/proc/meminfo")) -> int:
    for line in meminfo.read_text().splitlines():
        if line.startswith("SwapTotal:"):
            return int(line.split()[1])
    raise RuntimeError("SwapTotal is absent from /proc/meminfo")


def assert_swap_disabled(meminfo: Path = Path("/proc/meminfo")) -> None:
    if swap_total_kib(meminfo) != 0:
        raise RuntimeError("live relay refuses to run while swap is enabled")


def _write_private_json(path: Path, value: object) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(value, handle, sort_keys=True)
        handle.write("\n")
    os.replace(temporary, path)
    os.chmod(path, 0o600)


def preflight(
    *,
    device_host: str,
    work_dir: Path,
    production_tls: bool,
) -> dict[str, object]:
    harden_process()
    certificate_dir = work_dir / "preflight-certificate"
    shutil.rmtree(certificate_dir, ignore_errors=True)
    try:
        files = generate_test_certificate(certificate_dir, device_host)
        context = build_device_server_context(files)
        cipher_names = {item["name"] for item in context.get_ciphers()}
        if "AES256-SHA256" not in cipher_names:
            raise RuntimeError("device-facing TLS context lacks AES256-SHA256")
        upstream_connected = False
        if production_tls:
            upstream = RawUpstreamClient(
                host=UPSTREAM_HOST,
                port=443,
                context=build_upstream_context(),
                timeout_seconds=3,
            )
            try:
                upstream.prewarm()
                upstream_connected = True
            finally:
                upstream.close()
        return {
            "python": platform.python_version(),
            "openssl": ssl.OPENSSL_VERSION,
            "device_tls": {
                "minimum": context.minimum_version.name,
                "maximum": context.maximum_version.name,
                "cipher": "AES256-SHA256",
                "certificate": "RSA-2048",
            },
            "production_tls_prewarm": upstream_connected,
        }
    finally:
        shutil.rmtree(certificate_dir, ignore_errors=True)


def _production_upstream(config: LiveConfig) -> RawUpstreamClient:
    return RawUpstreamClient(
        host=UPSTREAM_HOST,
        port=443,
        context=build_upstream_context(),
        timeout_seconds=config.upstream_timeout_seconds,
    )


def run_live(
    config: LiveConfig,
    *,
    no_swap_check: Callable[[], None] = assert_swap_disabled,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    upstream_factory: Callable[[LiveConfig], RawUpstreamClient] = _production_upstream,
    install_signal_handlers: bool = True,
) -> None:
    config.validate()
    harden_process()
    no_swap_check()
    if config.state_path.exists():
        raise RuntimeError("live relay state already exists")
    config.work_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(config.work_dir, 0o700)
    certificate_dir = config.work_dir / f"certificate-{config.run_id}"
    mqtt_certificate_dir = config.work_dir / f"mqtt-certificate-{config.run_id}"
    components: RunAComponents | None = None
    stop_reason = "deadline"
    try:
        files = generate_test_certificate(certificate_dir, config.device_host)
        mqtt_context = None
        if config.capture_mqtt_connect:
            if config.mqtt_address_nonce is None:
                raise ValueError("MQTT CONNECT capture requires a nonce hostname")
            mqtt_files = generate_test_certificate(
                mqtt_certificate_dir,
                config.mqtt_address_nonce,
            )
            mqtt_context = build_device_server_context(mqtt_files)
        components = RunAComponents(
            run_id=config.run_id,
            device_host=config.device_host,
            device_context=build_device_server_context(files),
            upstream=upstream_factory(config),
            event_path=config.event_path,
            relay_host=config.relay_host,
            relay_port=config.relay_port,
            dns_host=config.dns_host,
            dns_port=config.dns_port,
            dns_records={config.device_host: config.relay_ip},
            ntp_host=config.ntp_host,
            ntp_port=config.ntp_port,
            mqtt_address_nonce=config.mqtt_address_nonce,
            mqtt_probe_host=config.relay_host if config.mqtt_probe_port is not None else None,
            mqtt_probe_port=config.mqtt_probe_port,
            relay_ip=config.relay_ip,
            mqtt_server_context=mqtt_context,
        )
        if install_signal_handlers:
            components.cleanup.install_signal_handlers()
        components.start()
        _write_private_json(
            config.state_path,
            {
                "run_id": config.run_id,
                "pid": os.getpid(),
                "relay_address": components.relay.address,
                "dns_address": components.dns.address,
                "ntp_address": components.ntp.address,
                "event_path": str(config.event_path),
            },
        )
        started = monotonic()
        next_refresh = started + config.prewarm_refresh_seconds
        deadline = started + config.deadline_seconds
        while monotonic() < deadline:
            if components.cleanup.shutdown_requested.is_set():
                stop_reason = "signal"
                break
            if config.stop_on_dns_match and components.dns.matched.is_set():
                stop_reason = "dns_match"
                break
            if components.mqtt_probe is not None and components.mqtt_probe.completed.is_set():
                failure = getattr(components.mqtt_probe, "failed", None)
                if config.capture_mqtt_connect and failure is not None and failure.is_set():
                    stop_reason = "mqtt_tls_failed"
                else:
                    stop_reason = "mqtt_connect" if config.capture_mqtt_connect else "mqtt_client_hello"
                break
            now = monotonic()
            if now >= next_refresh and components.upstream.requests_sent == 0 and components.upstream.fetch_count == 0:
                try:
                    components.refresh_prewarm()
                except RuntimeError:
                    pass
                next_refresh = now + config.prewarm_refresh_seconds
            sleep(min(0.1, max(0.0, deadline - now)))
        components.events.record(
            EventType.STOP,
            run_id=config.run_id,
            reason=stop_reason,
        )
    except BaseException as error:
        if components is not None:
            try:
                components.events.record(
                    EventType.STOP,
                    run_id=config.run_id,
                    reason=type(error).__name__,
                )
            except Exception as event_error:
                raise BaseExceptionGroup(
                    "live relay and stop-event recording both failed",
                    [error, event_error],
                ) from error
        raise
    finally:
        try:
            if components is not None:
                components.close()
        finally:
            config.state_path.unlink(missing_ok=True)
            shutil.rmtree(certificate_dir, ignore_errors=True)
            shutil.rmtree(mqtt_certificate_dir, ignore_errors=True)


def _config_from_args(args: argparse.Namespace) -> LiveConfig:
    return LiveConfig(
        run_id=args.run_id,
        device_host=args.device_host,
        relay_ip=args.relay_ip,
        work_dir=args.work_dir,
        event_path=args.event_path,
        state_path=args.state_path,
        relay_host=args.relay_host,
        relay_port=args.relay_port,
        dns_host=args.dns_host,
        dns_port=args.dns_port,
        ntp_host=args.ntp_host,
        ntp_port=args.ntp_port,
        deadline_seconds=args.deadline_seconds,
        prewarm_refresh_seconds=args.prewarm_refresh_seconds,
        upstream_timeout_seconds=args.upstream_timeout_seconds,
        mqtt_address_nonce=args.mqtt_address_nonce,
        stop_on_dns_match=args.stop_on_dns_match,
        mqtt_probe_port=args.mqtt_probe_port,
        capture_mqtt_connect=args.capture_mqtt_connect,
    )


def _stop(state_path: Path) -> None:
    state = json.loads(state_path.read_text())
    pid = state.get("pid")
    if not isinstance(pid, int) or pid <= 1:
        raise RuntimeError("live relay state has no valid PID")
    os.kill(pid, signal.SIGTERM)


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check")
    check.add_argument("--device-host", required=True)
    check.add_argument("--work-dir", type=Path, required=True)
    check.add_argument("--production-tls", action="store_true")

    run = subparsers.add_parser("run")
    run.add_argument("--ack", required=True)
    run.add_argument("--run-id", required=True)
    run.add_argument("--device-host", required=True)
    run.add_argument("--relay-ip", required=True)
    run.add_argument("--work-dir", type=Path, required=True)
    run.add_argument("--event-path", type=Path, required=True)
    run.add_argument("--state-path", type=Path, required=True)
    run.add_argument("--relay-host", default="0.0.0.0")  # noqa: S104
    run.add_argument("--relay-port", type=int, default=443)
    run.add_argument("--dns-host", default="0.0.0.0")  # noqa: S104
    run.add_argument("--dns-port", type=int, default=53)
    run.add_argument("--ntp-host", default="0.0.0.0")  # noqa: S104
    run.add_argument("--ntp-port", type=int, default=123)
    run.add_argument("--deadline-seconds", type=float, default=35)
    run.add_argument("--prewarm-refresh-seconds", type=float, default=8)
    run.add_argument("--upstream-timeout-seconds", type=float, default=3)
    run.add_argument("--mqtt-address-nonce")
    run.add_argument("--stop-on-dns-match", action="store_true")
    run.add_argument("--mqtt-probe-port", type=int)
    run.add_argument("--capture-mqtt-connect", action="store_true")

    stop = subparsers.add_parser("stop")
    stop.add_argument("--state-path", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "check":
        print(
            json.dumps(
                preflight(
                    device_host=args.device_host,
                    work_dir=args.work_dir,
                    production_tls=args.production_tls,
                ),
                sort_keys=True,
            )
        )
        return 0
    if args.command == "stop":
        _stop(args.state_path)
        return 0
    expected_ack = MUTATE_MQTT_ACK if args.mqtt_address_nonce else UNCHANGED_ACK
    if args.ack != expected_ack:
        raise SystemExit(f"--ack must equal {expected_ack}")
    run_live(_config_from_args(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
