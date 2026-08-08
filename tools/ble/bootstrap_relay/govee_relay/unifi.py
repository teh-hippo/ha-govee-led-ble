from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .guards import harden_process

APPLY_ACK = "APPLY-RUN-A-ISOLATION"
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,23}$")


class UniFiApi(Protocol):
    def v1(self, path: str, method: str = "GET", data: dict[str, Any] | None = None) -> Any: ...

    def v2(self, path: str, method: str = "GET", data: dict[str, Any] | None = None) -> Any: ...


class HttpUniFiApi:
    def __init__(self, url: str, api_key: str) -> None:
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.context = ssl.create_default_context()
        self.context.check_hostname = False
        self.context.verify_mode = ssl.CERT_NONE

    @classmethod
    def from_environment(cls) -> HttpUniFiApi:
        return cls(os.environ["UNIFI_URL"], os.environ["UNIFI_API_KEY"])

    def _request(self, url: str, method: str, data: dict[str, Any] | None) -> Any:
        body = None if data is None else json.dumps(data).encode()
        request = urllib.request.Request(  # noqa: S310 - fixed HTTPS controller URL
            url,
            data=body,
            method=method,
            headers={
                "X-API-KEY": self.api_key,
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(  # noqa: S310
                request,
                context=self.context,
                timeout=15,
            ) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            raw_error = error.read()
            message = ""
            try:
                decoded = json.loads(raw_error)
                candidate = decoded.get("meta", {}).get("msg")
                if isinstance(candidate, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", candidate):
                    message = f" ({candidate})"
            except UnicodeDecodeError, json.JSONDecodeError, AttributeError:
                pass
            raise RuntimeError(f"UniFi {method} request failed with HTTP {error.code}{message}") from error
        return json.loads(raw) if raw else None

    def v1(self, path: str, method: str = "GET", data: dict[str, Any] | None = None) -> Any:
        value = self._request(
            f"{self.url}/proxy/network/api/s/default/{path}",
            method,
            data,
        )
        return value.get("data", value) if isinstance(value, dict) else value

    def v2(self, path: str, method: str = "GET", data: dict[str, Any] | None = None) -> Any:
        return self._request(
            f"{self.url}/proxy/network/v2/api/site/default/{path}",
            method,
            data,
        )


@dataclass(frozen=True, slots=True)
class RunANetworkPlan:
    run_id: str
    relay_ip: str
    network_name: str
    vlan: int
    subnet: str
    network_cidr: str
    dhcp_start: str
    dhcp_stop: str
    policy_prefix: str

    @classmethod
    def create(cls, *, run_id: str, relay_ip: str, vlan: int = 30) -> RunANetworkPlan:
        if not RUN_ID.fullmatch(run_id):
            raise ValueError("run ID must be 1-24 letters, digits or hyphens")
        ipaddress.IPv4Address(relay_ip)
        if not 2 <= vlan <= 4094:
            raise ValueError("VLAN must be between 2 and 4094")
        return cls(
            run_id=run_id,
            relay_ip=relay_ip,
            network_name=f"Govee Relay {run_id}",
            vlan=vlan,
            subnet=f"192.168.{vlan}.1/24",
            network_cidr=f"192.168.{vlan}.0/24",
            dhcp_start=f"192.168.{vlan}.100",
            dhcp_stop=f"192.168.{vlan}.199",
            policy_prefix=f"Govee Relay {run_id}",
        )


@dataclass(frozen=True, slots=True, repr=False)
class RunACredentials:
    lab_ssid: str
    lab_passphrase: str
    restore_ssid: str
    restore_passphrase: str

    @classmethod
    def read(cls, stream: Any = sys.stdin) -> RunACredentials:
        lines = stream.read().splitlines()
        if len(lines) != 4:
            raise ValueError("stdin must contain lab SSID/passphrase and restore SSID/passphrase")
        value = cls(*lines)
        value.validate()
        return value

    def validate(self) -> None:
        if self.lab_ssid == self.restore_ssid:
            raise ValueError("lab and restore SSIDs must differ")
        for name, value, length in (
            ("lab SSID", self.lab_ssid, 7),
            ("restore SSID", self.restore_ssid, 7),
            ("lab passphrase", self.lab_passphrase, 8),
            ("restore passphrase", self.restore_passphrase, 8),
        ):
            try:
                encoded = value.encode("ascii")
            except UnicodeEncodeError as error:
                raise ValueError(f"{name} must be ASCII") from error
            if len(encoded) != length:
                raise ValueError(f"{name} must be exactly {length} bytes")
            if any(byte < 0x21 or byte > 0x7E for byte in encoded):
                raise ValueError(f"{name} must contain printable non-space ASCII")

    def __repr__(self) -> str:
        return "RunACredentials(<redacted>)"


@dataclass(slots=True)
class ManagedObject:
    object_id: str
    name: str


@dataclass(slots=True)
class RunANetworkState:
    run_id: str
    relay_ip: str
    network: ManagedObject | None = None
    lab_wlan: ManagedObject | None = None
    restore_wlan: ManagedObject | None = None
    policies: list[ManagedObject] = field(default_factory=list)

    def as_json(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "relay_ip": self.relay_ip,
            "network": None if self.network is None else asdict(self.network),
            "lab_wlan": None if self.lab_wlan is None else asdict(self.lab_wlan),
            "restore_wlan": None if self.restore_wlan is None else asdict(self.restore_wlan),
            "policies": [asdict(policy) for policy in self.policies],
        }

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> RunANetworkState:
        def managed(item: Any) -> ManagedObject | None:
            return None if item is None else ManagedObject(str(item["object_id"]), str(item["name"]))

        return cls(
            run_id=str(value["run_id"]),
            relay_ip=str(value["relay_ip"]),
            network=managed(value.get("network")),
            lab_wlan=managed(value.get("lab_wlan")),
            restore_wlan=managed(value.get("restore_wlan")),
            policies=[ManagedObject(str(item["object_id"]), str(item["name"])) for item in value.get("policies", [])],
        )


def _write_state(path: Path, state: RunANetworkState) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(state.as_json(), handle, sort_keys=True)
        handle.write("\n")
    os.replace(temporary, path)
    os.chmod(path, 0o600)


def _load_state(path: Path) -> RunANetworkState:
    return RunANetworkState.from_json(json.loads(path.read_text()))


def _rows(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, dict):
        data = value.get("data", value)
        return [data] if isinstance(data, dict) else list(data)
    return list(value)


def _created(value: Any) -> dict[str, Any]:
    rows = _rows(value)
    if len(rows) != 1 or "_id" not in rows[0]:
        raise RuntimeError("UniFi create response did not identify one object")
    return rows[0]


def _find_by_id(rows: list[dict[str, Any]], object_id: str) -> dict[str, Any] | None:
    return next((row for row in rows if str(row.get("_id")) == object_id), None)


def _network_source(zone_id: str, network_cidr: str) -> dict[str, object]:
    return {
        "zone_id": zone_id,
        "matching_target": "IP",
        "matching_target_type": "SPECIFIC",
        "ips": [network_cidr],
        "match_opposite_ips": False,
        "port_matching_type": "ANY",
        "match_opposite_ports": False,
    }


def _destination_any(zone_id: str) -> dict[str, object]:
    return {
        "zone_id": zone_id,
        "matching_target": "ANY",
        "port_matching_type": "ANY",
        "match_opposite_ports": False,
    }


def _destination_service(zone_id: str, relay_ip: str, port: int) -> dict[str, object]:
    return {
        "zone_id": zone_id,
        "matching_target": "IP",
        "matching_target_type": "SPECIFIC",
        "ips": [relay_ip],
        "match_opposite_ips": False,
        "port_matching_type": "SPECIFIC",
        "port": str(port),
        "match_opposite_ports": False,
    }


def _policy(
    *,
    name: str,
    action: str,
    protocol: str,
    index: int,
    source: dict[str, object],
    destination: dict[str, object],
    logging: bool,
) -> dict[str, object]:
    return {
        "name": name,
        "enabled": True,
        "action": action,
        "protocol": protocol,
        "ip_version": "IPV4",
        "index": index,
        "logging": logging,
        "connection_state_type": "ALL",
        "connection_states": [],
        "match_ip_sec": False,
        "match_opposite_protocol": False,
        "icmp_typename": "ANY",
        "icmp_v6_typename": "ANY",
        "schedule": {"mode": "ALWAYS"},
        "source": source,
        "destination": destination,
    }


def render_plan(plan: RunANetworkPlan) -> dict[str, object]:
    return {
        "run_id": plan.run_id,
        "network": {
            "name": plan.network_name,
            "vlan": plan.vlan,
            "subnet": plan.subnet,
            "internet_access": False,
            "network_isolation": True,
            "dhcp_dns": plan.relay_ip,
            "dhcp_ntp": plan.relay_ip,
        },
        "wlans": {
            "lab": {"ssid_length": 7, "passphrase_length": 8, "network": "isolated"},
            "restore": {"ssid_length": 7, "passphrase_length": 8, "network": "Default"},
        },
        "firewall": {
            "allow": ["relay tcp/443", "DNS udp/53", "DNS tcp/53", "NTP udp/123"],
            "block_and_log": [],
            "wan_isolation": "internet_access_enabled=false",
            "network_isolation": "all other internal",
            "source": plan.network_cidr,
        },
        "applied": False,
    }


def preflight(api: UniFiApi, *, plan: RunANetworkPlan) -> dict[str, object]:
    networks = _rows(api.v1("rest/networkconf"))
    wlans = _rows(api.v1("rest/wlanconf"))
    policies = _rows(api.v2("firewall-policies"))
    conflicts = {
        "network_name": any(network.get("name") == plan.network_name for network in networks),
        "vlan": any(network.get("vlan") == plan.vlan for network in networks),
        "subnet": any(network.get("ip_subnet") == plan.subnet for network in networks),
        "policy_prefix": any(str(policy.get("name", "")).startswith(plan.policy_prefix) for policy in policies),
    }
    result = {
        "run_id": plan.run_id,
        "conflicts": conflicts,
        "default_network": any(network.get("name") == "Default" for network in networks),
        "wan_network": any(network.get("purpose") == "wan" for network in networks),
        "all_ap_group": any(wlan.get("ap_group_mode") == "all" and bool(wlan.get("ap_group_ids")) for wlan in wlans),
    }
    if any(conflicts.values()):
        raise RuntimeError("planned UniFi resources conflict with existing state")
    if not all(
        (
            result["default_network"],
            result["wan_network"],
            result["all_ap_group"],
        )
    ):
        raise RuntimeError("UniFi prerequisites are incomplete")
    return result


def apply(
    api: UniFiApi,
    *,
    plan: RunANetworkPlan,
    credentials: RunACredentials,
    state_path: Path,
) -> RunANetworkState:
    credentials.validate()
    if state_path.exists():
        raise RuntimeError("UniFi run state already exists")
    networks = _rows(api.v1("rest/networkconf"))
    wlans = _rows(api.v1("rest/wlanconf"))
    preflight(api, plan=plan)
    if any(wlan.get("name") in {credentials.lab_ssid, credentials.restore_ssid} for wlan in wlans):
        raise RuntimeError("planned UniFi SSID conflicts with existing state")

    default_network = next((network for network in networks if network.get("name") == "Default"), None)
    wan_network = next((network for network in networks if network.get("purpose") == "wan"), None)
    if default_network is None or wan_network is None:
        raise RuntimeError("Default or WAN network is absent")
    default_zone = default_network.get("firewall_zone_id")
    if not isinstance(default_zone, str):
        raise RuntimeError("Default firewall zone is absent")
    preferred_wlan = next((wlan for wlan in wlans if wlan.get("ap_group_mode") == "all"), None)
    if preferred_wlan is None:
        raise RuntimeError("no existing all-AP WLAN supplies an AP group")

    state = RunANetworkState(plan.run_id, plan.relay_ip)
    network = _created(
        api.v1(
            "rest/networkconf",
            "POST",
            {
                "name": plan.network_name,
                "purpose": "corporate",
                "setting_preference": "manual",
                "vlan_enabled": True,
                "vlan": plan.vlan,
                "ip_subnet": plan.subnet,
                "dhcpd_enabled": True,
                "dhcpd_start": plan.dhcp_start,
                "dhcpd_stop": plan.dhcp_stop,
                "dhcpd_dns_enabled": True,
                "dhcpd_dns_1": plan.relay_ip,
                "dhcpd_ntp_enabled": True,
                "dhcpd_ntp_1": plan.relay_ip,
                "internet_access_enabled": False,
                "network_isolation_enabled": True,
                "is_nat": True,
                "enabled": True,
                "networkgroup": "LAN",
                "ipv6_interface_type": "none",
                "mdns_enabled": False,
            },
        )
    )
    state.network = ManagedObject(str(network["_id"]), plan.network_name)
    _write_state(state_path, state)
    internal_zone = network.get("firewall_zone_id")
    if not isinstance(internal_zone, str):
        for _attempt in range(20):
            refreshed = _find_by_id(
                _rows(api.v1("rest/networkconf")),
                state.network.object_id,
            )
            internal_zone = None if refreshed is None else refreshed.get("firewall_zone_id")
            if isinstance(internal_zone, str):
                break
            time.sleep(0.5)
    if not isinstance(internal_zone, str):
        raise RuntimeError("created network has no firewall zone")

    wlan_common = {
        "security": "wpapsk",
        "wpa_mode": "wpa2",
        "wpa_enc": "ccmp",
        "enabled": True,
        "l2_isolation": True,
        "wlan_band": "2g",
        "wlan_bands": ["2g"],
        "pmf_mode": "disabled",
        "bss_transition": False,
        "fast_roaming_enabled": False,
        "enhanced_iot": True,
        "ap_group_mode": "all",
        "ap_group_ids": preferred_wlan.get("ap_group_ids", []),
        "setting_preference": "manual",
    }
    lab_wlan = _created(
        api.v1(
            "rest/wlanconf",
            "POST",
            {
                **wlan_common,
                "name": credentials.lab_ssid,
                "x_passphrase": credentials.lab_passphrase,
                "networkconf_id": state.network.object_id,
            },
        )
    )
    state.lab_wlan = ManagedObject(str(lab_wlan["_id"]), credentials.lab_ssid)
    _write_state(state_path, state)
    restore_wlan = _created(
        api.v1(
            "rest/wlanconf",
            "POST",
            {
                **wlan_common,
                "name": credentials.restore_ssid,
                "x_passphrase": credentials.restore_passphrase,
                "networkconf_id": str(default_network["_id"]),
            },
        )
    )
    state.restore_wlan = ManagedObject(str(restore_wlan["_id"]), credentials.restore_ssid)
    _write_state(state_path, state)

    source = _network_source(internal_zone, plan.network_cidr)
    specifications = (
        ("HTTPS", "ALLOW", "tcp", 1500, _destination_service(default_zone, plan.relay_ip, 443), False),
        ("DNS UDP", "ALLOW", "udp", 1510, _destination_service(default_zone, plan.relay_ip, 53), False),
        ("DNS TCP", "ALLOW", "tcp", 1520, _destination_service(default_zone, plan.relay_ip, 53), False),
        ("NTP", "ALLOW", "udp", 1530, _destination_service(default_zone, plan.relay_ip, 123), False),
        ("MQTT Probe", "ALLOW", "tcp", 1540, _destination_service(default_zone, plan.relay_ip, 8883), False),
    )
    for suffix, action, protocol, index, destination, logging in specifications:
        name = f"{plan.policy_prefix} {suffix}"
        try:
            created = _created(
                api.v2(
                    "firewall-policies",
                    "POST",
                    _policy(
                        name=name,
                        action=action,
                        protocol=protocol,
                        index=index,
                        source=source,
                        destination=destination,
                        logging=logging,
                    ),
                )
            )
        except RuntimeError as error:
            raise RuntimeError(f"creating {suffix} firewall policy failed") from error
        state.policies.append(ManagedObject(str(created["_id"]), name))
        _write_state(state_path, state)
    return state


def _verify_named(rows: list[dict[str, Any]], managed: ManagedObject) -> dict[str, Any] | None:
    row = _find_by_id(rows, managed.object_id)
    if row is not None and row.get("name") != managed.name:
        raise RuntimeError(f"refusing to remove renamed UniFi object {managed.object_id}")
    return row


def teardown(api: UniFiApi, *, state_path: Path) -> None:
    state = _load_state(state_path)
    policies = _rows(api.v2("firewall-policies"))
    for policy in reversed(state.policies):
        if _verify_named(policies, policy) is not None:
            api.v2(f"firewall-policies/{policy.object_id}", "DELETE")
    wlans = _rows(api.v1("rest/wlanconf"))
    for wlan in (state.restore_wlan, state.lab_wlan):
        if wlan is not None and _verify_named(wlans, wlan) is not None:
            api.v1(f"rest/wlanconf/{wlan.object_id}", "DELETE")
    networks = _rows(api.v1("rest/networkconf"))
    if state.network is not None and _verify_named(networks, state.network) is not None:
        api.v1(f"rest/networkconf/{state.network.object_id}", "DELETE")
    state_path.unlink()


def rotate_restore_passphrase(api: UniFiApi, *, state_path: Path, passphrase: str) -> str:
    try:
        encoded = passphrase.encode("ascii")
    except UnicodeEncodeError as error:
        raise ValueError("restore passphrase must be ASCII") from error
    if len(encoded) != 8 or any(byte < 0x21 or byte > 0x7E for byte in encoded):
        raise ValueError("restore passphrase must be exactly 8 printable non-space ASCII bytes")
    state = _load_state(state_path)
    if state.restore_wlan is None:
        raise RuntimeError("restore WLAN is absent from state")
    row = _verify_named(_rows(api.v1("rest/wlanconf")), state.restore_wlan)
    if row is None:
        raise RuntimeError("restore WLAN is absent from UniFi")
    api.v1(
        f"rest/wlanconf/{state.restore_wlan.object_id}",
        "PUT",
        {"x_passphrase": passphrase},
    )
    return state.restore_wlan.name


def status(api: UniFiApi, *, state_path: Path) -> dict[str, object]:
    state = _load_state(state_path)
    networks = _rows(api.v1("rest/networkconf"))
    wlans = _rows(api.v1("rest/wlanconf"))
    policies = _rows(api.v2("firewall-policies"))
    network = None if state.network is None else _find_by_id(networks, state.network.object_id)
    lab_wlan = None if state.lab_wlan is None else _find_by_id(wlans, state.lab_wlan.object_id)
    restore_wlan = None if state.restore_wlan is None else _find_by_id(wlans, state.restore_wlan.object_id)
    default_network = next((item for item in networks if item.get("name") == "Default"), None)
    network_ready = (
        network is not None
        and network.get("internet_access_enabled") is False
        and network.get("network_isolation_enabled") is True
        and network.get("dhcpd_dns_1") == state.relay_ip
        and network.get("dhcpd_ntp_1") == state.relay_ip
        and network.get("ipv6_interface_type") == "none"
    )
    lab_wlan_ready = (
        lab_wlan is not None
        and state.network is not None
        and lab_wlan.get("networkconf_id") == state.network.object_id
        and lab_wlan.get("wlan_band") == "2g"
        and lab_wlan.get("pmf_mode") == "disabled"
        and lab_wlan.get("l2_isolation") is True
    )
    restore_wlan_ready = (
        restore_wlan is not None
        and default_network is not None
        and restore_wlan.get("networkconf_id") == default_network.get("_id")
        and restore_wlan.get("wlan_band") == "2g"
        and restore_wlan.get("pmf_mode") == "disabled"
        and restore_wlan.get("l2_isolation") is True
    )
    policies_present = sum(_find_by_id(policies, managed.object_id) is not None for managed in state.policies)
    result = {
        "run_id": state.run_id,
        "network_present": network is not None,
        "network_ready": network_ready,
        "lab_wlan_present": lab_wlan is not None,
        "lab_wlan_ready": lab_wlan_ready,
        "restore_wlan_present": restore_wlan is not None,
        "restore_wlan_ready": restore_wlan_ready,
        "policies_present": policies_present,
        "policies_expected": len(state.policies),
    }
    result["ready"] = (
        network_ready and lab_wlan_ready and restore_wlan_ready and policies_present == len(state.policies)
    )
    return result


def wait_for_client(
    api: UniFiApi,
    *,
    state_path: Path,
    role: str,
    timeout_seconds: float,
) -> bool:
    state = _load_state(state_path)
    managed = state.lab_wlan if role == "lab" else state.restore_wlan
    if managed is None:
        raise RuntimeError(f"{role} WLAN is absent from state")
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        clients = _rows(api.v1("stat/sta"))
        if any(client.get("essid") == managed.name and client.get("authorized") is not False for client in clients):
            return True
        time.sleep(1)
    return False


def main() -> int:
    harden_process()
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("plan", "check", "apply"):
        child = subparsers.add_parser(command)
        child.add_argument("--run-id", required=True)
        child.add_argument("--relay-ip", required=True)
        child.add_argument("--vlan", type=int, default=30)
        if command == "apply":
            child.add_argument("--ack", required=True)
            child.add_argument("--state", type=Path, required=True)
    for command in ("status", "teardown", "rotate-restore"):
        child = subparsers.add_parser(command)
        child.add_argument("--state", type=Path, required=True)
    wait = subparsers.add_parser("wait-client")
    wait.add_argument("--state", type=Path, required=True)
    wait.add_argument("--role", choices=("lab", "restore"), required=True)
    wait.add_argument("--timeout-seconds", type=float, default=30)

    args = parser.parse_args()
    if args.command == "plan":
        print(
            json.dumps(
                render_plan(
                    RunANetworkPlan.create(
                        run_id=args.run_id,
                        relay_ip=args.relay_ip,
                        vlan=args.vlan,
                    )
                ),
                sort_keys=True,
            )
        )
        return 0
    api = HttpUniFiApi.from_environment()
    if args.command == "check":
        print(
            json.dumps(
                preflight(
                    api,
                    plan=RunANetworkPlan.create(
                        run_id=args.run_id,
                        relay_ip=args.relay_ip,
                        vlan=args.vlan,
                    ),
                ),
                sort_keys=True,
            )
        )
        return 0
    if args.command == "apply":
        if args.ack != APPLY_ACK:
            raise SystemExit(f"--ack must equal {APPLY_ACK}")
        apply(
            api,
            plan=RunANetworkPlan.create(
                run_id=args.run_id,
                relay_ip=args.relay_ip,
                vlan=args.vlan,
            ),
            credentials=RunACredentials.read(),
            state_path=args.state,
        )
        print(json.dumps(status(api, state_path=args.state), sort_keys=True))
        return 0
    if args.command == "status":
        print(json.dumps(status(api, state_path=args.state), sort_keys=True))
        return 0
    if args.command == "teardown":
        teardown(api, state_path=args.state)
        return 0
    if args.command == "rotate-restore":
        lines = sys.stdin.read().splitlines()
        if len(lines) != 1:
            raise ValueError("stdin must contain one restore passphrase")
        restore_ssid = rotate_restore_passphrase(
            api,
            state_path=args.state,
            passphrase=lines[0],
        )
        print(json.dumps({"restore_ssid": restore_ssid, "updated": True}, sort_keys=True))
        return 0
    matched = wait_for_client(
        api,
        state_path=args.state,
        role=args.role,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps({"role": args.role, "matched": matched}, sort_keys=True))
    return 0 if matched else 1


if __name__ == "__main__":
    raise SystemExit(main())
