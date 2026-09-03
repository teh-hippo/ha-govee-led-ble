"""H6179 reactive backend API and WebSocket contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest
import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.ha_govee_led_ble.const import DOMAIN
from custom_components.ha_govee_led_ble.control_arbiter import BLEControlArbiter
from custom_components.ha_govee_led_ble.h6179_reactive_service import (
    REACTIVE_START_WS_SCHEMA,
    REACTIVE_STOP_WS_SCHEMA,
    REACTIVE_UPDATE_WS_SCHEMA,
    WS_REACTIVE_START,
    WS_REACTIVE_STOP,
    WS_REACTIVE_UPDATE,
    async_setup_h6179_reactive,
)


@dataclass
class _Coordinator:
    model: str = "H6179"
    fw_version: str | None = "1.01.00"
    _control_arbiter: BLEControlArbiter = field(default_factory=BLEControlArbiter)
    frames: list[bytes] = field(default_factory=list)

    async def async_preview_preflight(self, *, timeout: float = 8.0) -> None:
        assert timeout > 0

    async def async_preview_write(self, packet: bytes) -> None:
        self.frames.append(packet)


def test_message_names_and_schemas_are_stable_and_exact() -> None:
    assert (WS_REACTIVE_START, WS_REACTIVE_UPDATE, WS_REACTIVE_STOP) == (
        "ha_govee_led_ble/reactive/start",
        "ha_govee_led_ble/reactive/update",
        "ha_govee_led_ble/reactive/stop",
    )

    start = REACTIVE_START_WS_SCHEMA({"type": WS_REACTIVE_START, "config_entry_id": "entry-a"})
    assert start == {
        "type": WS_REACTIVE_START,
        "config_entry_id": "entry-a",
        "legacy_colour_order": False,
    }
    REACTIVE_STOP_WS_SCHEMA(
        {
            "type": WS_REACTIVE_STOP,
            "config_entry_id": "entry-a",
            "session_id": "a" * 36,
        }
    )

    websocket_update = {
        "type": WS_REACTIVE_UPDATE,
        "config_entry_id": "entry-a",
        "session_id": "a" * 36,
        "rgb": {"r": 1, "g": 2, "b": 3},
    }
    assert REACTIVE_UPDATE_WS_SCHEMA(websocket_update) == websocket_update


@pytest.mark.parametrize(
    "payload",
    [
        {"pcm": [1, 2, 3]},
        {"audio": "AAAA"},
        {"r": 1, "g": 2, "b": 3, "pcm": []},
        {"r": True, "g": 2, "b": 3},
        {"r": 1.0, "g": 2, "b": 3},
        {"r": 1, "g": 2, "b": 256},
        [1, 2, 3],
    ],
)
def test_update_schemas_reject_non_exact_rgb(payload: object) -> None:
    with pytest.raises(vol.Invalid):
        REACTIVE_UPDATE_WS_SCHEMA(
            {
                "type": WS_REACTIVE_UPDATE,
                "config_entry_id": "entry-a",
                "session_id": "a" * 36,
                "rgb": payload,
            }
        )


async def test_authenticated_websocket_lifecycle_is_admin_only_and_rgb_only(
    hass: HomeAssistant,
    hass_ws_client,
    hass_read_only_access_token,
    monkeypatch,
) -> None:
    coordinator = _Coordinator()
    entry = SimpleNamespace(
        entry_id="entry-a",
        domain=DOMAIN,
        state=ConfigEntryState.LOADED,
        runtime_data=coordinator,
    )
    monkeypatch.setattr(
        hass.config_entries,
        "async_get_entry",
        lambda entry_id: entry if entry_id == entry.entry_id else None,
    )
    backend = await async_setup_h6179_reactive(hass)
    assert await async_setup_h6179_reactive(hass) is backend
    assert not hass.services.async_services().get(DOMAIN)

    read_only = await hass_ws_client(hass, access_token=hass_read_only_access_token)
    await read_only.send_json_auto_id(
        {
            "type": WS_REACTIVE_START,
            "config_entry_id": entry.entry_id,
        }
    )
    assert (await read_only.receive_json())["error"]["code"] == "unauthorized"

    owner = await hass_ws_client(hass)
    await owner.send_json_auto_id(
        {
            "type": WS_REACTIVE_START,
            "config_entry_id": "missing",
        }
    )
    assert (await owner.receive_json())["error"]["code"] == "reactive_target_unavailable"

    await owner.send_json_auto_id(
        {
            "type": WS_REACTIVE_START,
            "config_entry_id": entry.entry_id,
        }
    )
    started = await owner.receive_json()
    assert started["success"] is True
    session_id = started["result"]["session_id"]

    await owner.send_json_auto_id(
        {
            "type": WS_REACTIVE_UPDATE,
            "config_entry_id": entry.entry_id,
            "session_id": session_id,
            "rgb": {"r": 1, "g": 2, "b": 3},
        }
    )
    updated = await owner.receive_json()
    assert updated["result"]["state"] == "active"
    assert coordinator.frames == [bytes.fromhex("a5028301020330")]

    await owner.send_json_auto_id(
        {
            "type": WS_REACTIVE_UPDATE,
            "config_entry_id": entry.entry_id,
            "session_id": session_id,
            "rgb": {"r": 1, "g": 2, "b": 3, "audio": "forbidden"},
        }
    )
    assert (await owner.receive_json())["error"]["code"] == "invalid_format"

    await owner.send_json_auto_id(
        {
            "type": WS_REACTIVE_STOP,
            "config_entry_id": entry.entry_id,
            "session_id": session_id,
        }
    )
    stopped = await owner.receive_json()
    assert stopped["result"]["stop_reason"] == "requested"
    await backend.async_shutdown()
