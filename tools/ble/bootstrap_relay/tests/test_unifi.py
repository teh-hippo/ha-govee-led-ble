from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from govee_relay.unifi import (
    ManagedObject,
    RunACredentials,
    RunANetworkPlan,
    RunANetworkState,
    apply,
    preflight,
    render_plan,
    rotate_restore_passphrase,
    status,
    teardown,
    wait_for_client,
)


class FakeUniFi:
    def __init__(self) -> None:
        self.networks: list[dict[str, Any]] = [
            {
                "_id": "default",
                "name": "Default",
                "purpose": "corporate",
                "firewall_zone_id": "internal",
            },
            {
                "_id": "wan",
                "name": "Internet",
                "purpose": "wan",
                "firewall_zone_id": "wan-zone",
            },
        ]
        self.wlans: list[dict[str, Any]] = [
            {
                "_id": "existing-wlan",
                "name": "Existing",
                "wlan_band": "2g",
                "ap_group_mode": "all",
                "ap_group_ids": ["ap-group"],
            }
        ]
        self.policies: list[dict[str, Any]] = []
        self.clients: list[dict[str, Any]] = []
        self.created_payloads: list[tuple[str, dict[str, Any]]] = []
        self._next = 1

    def _id(self) -> str:
        value = f"created-{self._next}"
        self._next += 1
        return value

    def v1(self, path: str, method: str = "GET", data: dict[str, Any] | None = None) -> Any:
        if path == "rest/networkconf":
            if method == "GET":
                return self.networks
            assert data is not None
            item = {"_id": self._id(), "firewall_zone_id": "internal", **data}
            self.networks.append(item)
            self.created_payloads.append(("network", data))
            return [item]
        if path == "rest/wlanconf":
            if method == "GET":
                return self.wlans
            assert data is not None
            item = {"_id": self._id(), **data}
            self.wlans.append(item)
            self.created_payloads.append(("wlan", data))
            return [item]
        if path == "stat/sta":
            return self.clients
        if path.startswith("rest/networkconf/") and method == "DELETE":
            object_id = path.rsplit("/", 1)[1]
            self.networks = [item for item in self.networks if item["_id"] != object_id]
            return None
        if path.startswith("rest/wlanconf/") and method == "DELETE":
            object_id = path.rsplit("/", 1)[1]
            self.wlans = [item for item in self.wlans if item["_id"] != object_id]
            return None
        if path.startswith("rest/wlanconf/") and method == "PUT":
            object_id = path.rsplit("/", 1)[1]
            assert data is not None
            item = next(item for item in self.wlans if item["_id"] == object_id)
            item.update(data)
            return [item]
        raise AssertionError((path, method))

    def v2(self, path: str, method: str = "GET", data: dict[str, Any] | None = None) -> Any:
        if path == "firewall-policies":
            if method == "GET":
                return self.policies
            assert data is not None
            item = {"_id": self._id(), **data}
            self.policies.append(item)
            self.created_payloads.append(("policy", data))
            return item
        if path.startswith("firewall-policies/") and method == "DELETE":
            object_id = path.rsplit("/", 1)[1]
            self.policies = [item for item in self.policies if item["_id"] != object_id]
            return None
        raise AssertionError((path, method))


def credentials() -> RunACredentials:
    return RunACredentials(
        lab_ssid="LABA123",
        lab_passphrase="A1b2C3d4",  # noqa: S106 - fabricated test credential
        restore_ssid="BACK123",
        restore_passphrase="E5f6G7h8",  # noqa: S106 - fabricated test credential
    )


def test_credentials_are_stdin_only_and_strict():
    value = RunACredentials.read(io.StringIO("LABA123\nA1b2C3d4\nBACK123\nE5f6G7h8\n"))
    assert value == credentials()
    with pytest.raises(ValueError, match="exactly 7"):
        RunACredentials("short", "A1b2C3d4", "BACK123", "E5f6G7h8").validate()


def test_plan_contains_no_credentials():
    rendered = json.dumps(render_plan(RunANetworkPlan.create(run_id="run-1", relay_ip="192.0.2.10")))
    assert "passphrase_length" in rendered
    assert "A1b2C3d4" not in rendered
    assert '"applied": false' in rendered
    assert repr(credentials()) == "RunACredentials(<redacted>)"


def test_preflight_reports_safe_prerequisites():
    result = preflight(
        FakeUniFi(),
        plan=RunANetworkPlan.create(run_id="run-1", relay_ip="192.0.2.10"),
    )
    assert result["conflicts"] == {
        "network_name": False,
        "vlan": False,
        "subnet": False,
        "policy_prefix": False,
    }
    assert result["all_ap_group"] is True


def test_apply_status_wait_and_teardown(tmp_path: Path):
    api = FakeUniFi()
    state_path = tmp_path / "unifi-state.json"
    plan = RunANetworkPlan.create(run_id="run-1", relay_ip="192.0.2.10")
    state = apply(
        api,
        plan=plan,
        credentials=credentials(),
        state_path=state_path,
    )
    assert state.network is not None
    assert len(state.policies) == 5
    persisted = state_path.read_text()
    assert "A1b2C3d4" not in persisted
    assert "E5f6G7h8" not in persisted
    assert state_path.stat().st_mode & 0o777 == 0o600

    network_payload = next(payload for kind, payload in api.created_payloads if kind == "network")
    assert network_payload["internet_access_enabled"] is False
    assert network_payload["dhcpd_dns_1"] == "192.0.2.10"
    assert network_payload["dhcpd_ntp_1"] == "192.0.2.10"
    policy_payloads = [payload for kind, payload in api.created_payloads if kind == "policy"]
    assert all(payload["action"] == "ALLOW" for payload in policy_payloads)
    assert all(payload["source"]["ips"] == ["192.168.30.0/24"] for payload in policy_payloads)
    current = status(api, state_path=state_path)
    assert current["policies_present"] == 5
    assert current["ready"] is True

    api.clients.append(
        {
            "mac": "00:11:22:33:44:55",
            "essid": "LABA123",
            "authorized": True,
        }
    )
    assert wait_for_client(
        api,
        state_path=state_path,
        role="lab",
        timeout_seconds=0.01,
    )
    api.clients.clear()
    assert not wait_for_client(
        api,
        state_path=state_path,
        role="lab",
        timeout_seconds=0,
    )

    restore_name = rotate_restore_passphrase(
        api,
        state_path=state_path,
        passphrase="N3wP4ss5",  # noqa: S106 - fabricated test credential
    )
    assert restore_name == "BACK123"
    restore = next(item for item in api.wlans if item["name"] == restore_name)
    assert restore["x_passphrase"] == "N3wP4ss5"  # noqa: S105 - fabricated test credential
    assert "N3wP4ss5" not in state_path.read_text()

    teardown(api, state_path=state_path)
    assert not state_path.exists()
    assert len(api.networks) == 2
    assert len(api.wlans) == 1
    assert api.policies == []


def test_apply_refuses_conflicting_vlan(tmp_path: Path):
    api = FakeUniFi()
    api.networks.append({"_id": "conflict", "name": "Other", "vlan": 30})
    with pytest.raises(RuntimeError, match="conflict"):
        apply(
            api,
            plan=RunANetworkPlan.create(run_id="run-1", relay_ip="192.0.2.10"),
            credentials=credentials(),
            state_path=tmp_path / "state.json",
        )


def test_teardown_refuses_renamed_object(tmp_path: Path):
    api = FakeUniFi()
    state_path = tmp_path / "state.json"
    state = RunANetworkState(
        run_id="run-1",
        relay_ip="192.0.2.10",
        network=ManagedObject("default", "Not Default"),
    )
    state_path.write_text(json.dumps(state.as_json()))
    with pytest.raises(RuntimeError, match="renamed"):
        teardown(api, state_path=state_path)
