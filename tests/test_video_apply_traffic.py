"""Video Apply traffic through Studio and the real coordinator."""

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.ha_govee_led_ble.const import DOMAIN
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.effect_deployments import DeploymentPhase, ObservationConfidence
from custom_components.ha_govee_led_ble.effect_domain import RelativeBrightness, VideoProfile, effect_content_to_dict
from custom_components.ha_govee_led_ble.effect_websocket import WS_APPLY_SNAPSHOT
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_blank_screen,
    build_blank_screen_query,
    build_brightness_query,
    build_colour_mode_query,
    build_power_query,
    build_relative_brightness,
    build_relative_brightness_query,
    build_segment_query,
    build_video_mode,
    build_white_balance_query,
    parse_command,
)
from custom_components.ha_govee_led_ble.native_profile_controls import apply_relative_brightness
from custom_components.ha_govee_led_ble.transport import xor_checksum
from tests.coordinator_test_support import frame
from tests.test_effect_websocket import _setup_backend
from tests.test_h6199_capabilities import set_qualified_identity


def _reply(packet: bytes) -> bytearray:
    result = bytearray(packet)
    result[0] = 0xAA
    result[-1] = xor_checksum(result[:-1])
    return result


@dataclass
class _PeripheralState:
    is_on: bool = False
    video_mode: str = "off"
    full_screen: bool = True
    saturation: int = 50
    sound_effects: bool = False
    sound_effects_softness: int = 50
    white_balance_flag: int = 1
    white_balance_red: int = 16
    white_balance_blue: int = 3
    relative_brightness: tuple[int, int, int, int] = (80, 80, 80, 80)
    blank_screen: bool = True
    blank_screen_detection: int = 2
    blank_screen_low_brightness_duration_seconds: int = 10
    blank_screen_same_tone_duration_seconds: int = 120


class _H6199Peripheral:
    def __init__(self, coordinator: GoveeBLECoordinator) -> None:
        self.coordinator = coordinator
        self.state = _PeripheralState()
        self.packets: list[bytes] = []
        self.accepted: list[dict[str, object]] = []
        self.produced: list[bytes] = []
        self.delivered: list[bytes] = []
        self.blank_write_completed = False
        self.contradict_final_relative = False
        self.drop_final_relative_replies = 0
        self.change_policy_after_mode_write = False
        self.change_policy_after_blank_write = False

    async def write_gatt_char(self, _uuid: object, packet: bytes, **_kwargs: object) -> None:
        packet = bytes(packet)
        self.packets.append(packet)
        if packet[0] == 0xAA:
            await self._answer(packet)
            return
        self._accept(packet)
        if packet[1] == 0x05 and self.change_policy_after_mode_write:
            self.state.blank_screen_detection = 1
            self.state.blank_screen_low_brightness_duration_seconds = 20
            self.state.blank_screen_same_tone_duration_seconds = 240
            await self._deliver(
                _reply(
                    build_blank_screen(
                        self.state.blank_screen,
                        "H6199",
                        self.state.blank_screen_detection,
                        self.state.blank_screen_low_brightness_duration_seconds,
                        self.state.blank_screen_same_tone_duration_seconds,
                    )
                )
            )
        await self._deliver(frame(f"33{packet[1]:02x}00"))

    async def _answer(self, packet: bytes) -> None:
        response: bytes | bytearray
        if packet == build_power_query("H6199"):
            response = frame("aa0101" if self.state.is_on else "aa0100")
        elif packet == build_brightness_query("H6199"):
            response = frame("aa042a")
        elif packet == build_colour_mode_query("H6199"):
            response = (
                _reply(
                    build_video_mode(
                        self.state.video_mode,
                        self.state.full_screen,
                        self.state.saturation,
                        self.state.sound_effects,
                        self.state.sound_effects_softness,
                        "H6199",
                    )
                )
                if self.state.video_mode != "off"
                else frame("aa051500")
            )
        elif packet == build_white_balance_query("H6199"):
            response = frame(
                "aaa90006"
                f"{self.state.white_balance_flag:02x}"
                f"{self.state.white_balance_red:02x}"
                f"{self.state.white_balance_blue:02x}"
                "011003"
            )
        elif packet == build_relative_brightness_query("H6199"):
            if self.blank_write_completed and self.drop_final_relative_replies:
                self.drop_final_relative_replies -= 1
                return
            values = self.state.relative_brightness
            if self.blank_write_completed and self.contradict_final_relative:
                self.contradict_final_relative = False
                values = (90, 90, 90, 90)
            response = _reply(build_relative_brightness(*values, "H6199"))
        elif packet == build_blank_screen_query("H6199"):
            if self.blank_write_completed and self.change_policy_after_blank_write:
                self.change_policy_after_blank_write = False
                self.state.blank_screen_detection = 1
                self.state.blank_screen_low_brightness_duration_seconds = 20
                self.state.blank_screen_same_tone_duration_seconds = 240
            response = _reply(
                build_blank_screen(
                    self.state.blank_screen,
                    "H6199",
                    self.state.blank_screen_detection,
                    self.state.blank_screen_low_brightness_duration_seconds,
                    self.state.blank_screen_same_tone_duration_seconds,
                )
            )
        elif packet in {
            build_segment_query(page, "H6199") for page in range(1, self.coordinator.profile.segment_group_count + 1)
        }:
            page = packet[2]
            count = min(
                self.coordinator.profile.segment_group_size,
                self.coordinator.profile.segment_count - (page - 1) * self.coordinator.profile.segment_group_size,
            )
            response = frame(f"aaa5{page:02x}" + "64ffffff" * count)
        else:
            raise AssertionError(f"Unexpected query {packet.hex()}")
        await self._deliver(response)

    def _accept(self, packet: bytes) -> None:
        parsed = parse_command(packet, "H6199")
        assert parsed is not None
        fields: dict[str, object]
        if packet[1] == 0x01:
            self.state.is_on = bool(parsed.body.is_on)
            fields = {"is_on": self.state.is_on}
        elif packet[1] == 0x05:
            self.state.video_mode = "movie" if int(parsed.body.detail.source) == 0 else "game"
            self.state.full_screen = bool(parsed.body.detail.region)
            self.state.saturation = parsed.body.detail.saturation
            self.state.sound_effects = bool(parsed.body.detail.sound_effects)
            self.state.sound_effects_softness = parsed.body.detail.softness
            fields = {"video_mode": self.state.video_mode}
        elif packet[1] == 0xAE:
            self.state.relative_brightness = (
                parsed.body.left_percent,
                parsed.body.top_percent,
                parsed.body.right_percent,
                parsed.body.bottom_percent,
            )
            fields = {"relative_brightness": self.state.relative_brightness}
        elif packet[1] == 0xA9 and int(parsed.body.setting) == 0:
            self.state.white_balance_flag = parsed.body.payload.manual
            self.state.white_balance_red = parsed.body.payload.red
            self.state.white_balance_blue = parsed.body.payload.blue
            fields = {
                "white_balance_flag": self.state.white_balance_flag,
                "white_balance_red": self.state.white_balance_red,
                "white_balance_blue": self.state.white_balance_blue,
            }
        elif packet[1] == 0xA9 and int(parsed.body.setting) == 10:
            self.state.blank_screen = bool(parsed.body.payload.is_on)
            self.state.blank_screen_detection = int(parsed.body.payload.detection)
            self.state.blank_screen_low_brightness_duration_seconds = (
                parsed.body.payload.low_brightness_duration_seconds
            )
            self.state.blank_screen_same_tone_duration_seconds = parsed.body.payload.same_tone_duration_seconds
            fields = {"blank_screen": self.state.blank_screen}
            self.blank_write_completed = True
        else:
            raise AssertionError(f"Unexpected control {packet.hex()}")
        self.accepted.append({"packet": packet.hex(), "fields": fields})

    async def _deliver(self, response: bytes | bytearray) -> None:
        frame_bytes = bytes(response)
        self.produced.append(frame_bytes)
        self.coordinator._notify_callback(None, bytearray(frame_bytes))
        self.delivered.append(frame_bytes)


async def test_registered_studio_video_apply_baseline(
    hass: HomeAssistant,
    hass_ws_client,
    monkeypatch,
) -> None:
    backend = await _setup_backend(hass)
    coordinator = GoveeBLECoordinator(
        hass,
        "11:22:33:44:55:66",
        "H6199",
        configuration_url="test",
    )
    set_qualified_identity(coordinator)
    peripheral = _H6199Peripheral(coordinator)
    client = MagicMock(
        is_connected=True,
        write_gatt_char=peripheral.write_gatt_char,
        disconnect=AsyncMock(),
    )
    coordinator._client = client
    coordinator._notification_token = object()
    coordinator._notify_started_monotonic = time.monotonic()
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    entry = SimpleNamespace(
        entry_id="entry-a",
        domain=DOMAIN,
        state=ConfigEntryState.LOADED,
        runtime_data=coordinator,
        title="Local H6199",
        options={},
    )
    monkeypatch.setattr(
        hass.config_entries,
        "async_get_entry",
        lambda entry_id: entry if entry_id == entry.entry_id else None,
    )
    connection = await hass_ws_client(hass)
    runs: list[dict[str, object]] = []
    try:
        for index in range(2):
            mode = "movie" if index % 2 == 0 else "game"
            before = len(peripheral.packets)
            content = VideoProfile(
                "H6199",
                mode,
                True,
                50,
                False,
                50,
                17,
                RelativeBrightness(100, 100, 100, 100),
                False,
            )
            await connection.send_json_auto_id(
                {
                    "type": WS_APPLY_SNAPSHOT,
                    "config_entry_id": entry.entry_id,
                    "name": f"#712 local baseline {mode}",
                    "content": effect_content_to_dict(content),
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            )
            response = await connection.receive_json()
            assert response["success"], response
            deployment = response["result"]["deployment"]
            assert deployment["phase"] == DeploymentPhase.CONFIRMED.value
            assert deployment["verification_confidence"] == ObservationConfidence.SETTINGS_MATCH.value
            exchanged = peripheral.packets[before:]
            assert len(exchanged) == (25 if index == 0 else 19)
            runs.append(
                {
                    "index": index + 1,
                    "mode": mode,
                    "exchange_count": len(exchanged),
                    "write_count": sum(packet[0] == 0x33 for packet in exchanged),
                    "query_count": sum(packet[0] == 0xAA for packet in exchanged),
                    "packets": [packet.hex() for packet in exchanged],
                    "deployment": deployment,
                }
            )
    finally:
        await connection.close()
        await backend.preview.async_shutdown()
        await coordinator.async_shutdown()

    assert [run["exchange_count"] for run in runs] == [25, 19]
    for run in runs:
        packets = [bytes.fromhex(packet) for packet in run["packets"]]
        mode_write = next(index for index, packet in enumerate(packets) if packet[0:2] == b"\x33\x05")
        assert packets[mode_write + 1 : mode_write + 3] == [
            build_power_query("H6199"),
            build_colour_mode_query("H6199"),
        ]
        assert packets.count(build_blank_screen_query("H6199")) == 4
        assert packets.count(build_white_balance_query("H6199")) == 2
        assert packets.count(build_relative_brightness_query("H6199")) == 2
    assert len(peripheral.accepted) == 9
    assert peripheral.produced == peripheral.delivered
    assert peripheral.state.video_mode == "game"
    assert peripheral.state.relative_brightness == (100, 100, 100, 100)
    assert peripheral.state.blank_screen is False


async def test_studio_apply_reacquires_policy_before_blank_screen_write(
    hass: HomeAssistant,
    hass_ws_client,
    monkeypatch,
) -> None:
    backend = await _setup_backend(hass)
    coordinator = GoveeBLECoordinator(
        hass,
        "11:22:33:44:55:66",
        "H6199",
        configuration_url="test",
    )
    set_qualified_identity(coordinator)
    peripheral = _H6199Peripheral(coordinator)
    peripheral.change_policy_after_mode_write = True
    client = MagicMock(
        is_connected=True,
        write_gatt_char=peripheral.write_gatt_char,
        disconnect=AsyncMock(),
    )
    coordinator._client = client
    coordinator._notification_token = object()
    coordinator._notify_started_monotonic = time.monotonic()
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    entry = SimpleNamespace(
        entry_id="entry-a",
        domain=DOMAIN,
        state=ConfigEntryState.LOADED,
        runtime_data=coordinator,
        title="Local H6199",
        options={},
    )
    monkeypatch.setattr(
        hass.config_entries,
        "async_get_entry",
        lambda entry_id: entry if entry_id == entry.entry_id else None,
    )
    connection = await hass_ws_client(hass)
    try:
        await connection.send_json_auto_id(
            {
                "type": WS_APPLY_SNAPSHOT,
                "config_entry_id": entry.entry_id,
                "name": "#712 changed policy",
                "content": effect_content_to_dict(
                    VideoProfile(
                        "H6199",
                        "movie",
                        True,
                        50,
                        False,
                        50,
                        17,
                        RelativeBrightness(100, 100, 100, 100),
                        False,
                    )
                ),
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
        response = await connection.receive_json()
        assert response["success"], response
        deployment = response["result"]["deployment"]
        assert deployment["phase"] == DeploymentPhase.CONFIRMED.value
        assert deployment["verification_confidence"] == ObservationConfidence.SETTINGS_MATCH.value
        blank_packet = build_blank_screen(False, "H6199", 1, 20, 240)
        assert peripheral.packets.count(blank_packet) == 1
        assert (
            peripheral.state.blank_screen_detection,
            peripheral.state.blank_screen_low_brightness_duration_seconds,
            peripheral.state.blank_screen_same_tone_duration_seconds,
        ) == (1, 20, 240)
    finally:
        await connection.close()
        await backend.preview.async_shutdown()
        await coordinator.async_shutdown()


@pytest.mark.parametrize("contradiction", ["relative_brightness", "blank_screen_policy"])
async def test_studio_apply_retries_final_contradiction(
    hass: HomeAssistant,
    hass_ws_client,
    monkeypatch,
    contradiction: str,
) -> None:
    backend = await _setup_backend(hass)
    coordinator = GoveeBLECoordinator(
        hass,
        "11:22:33:44:55:66",
        "H6199",
        configuration_url="test",
    )
    set_qualified_identity(coordinator)
    peripheral = _H6199Peripheral(coordinator)
    if contradiction == "relative_brightness":
        peripheral.contradict_final_relative = True
    else:
        peripheral.change_policy_after_blank_write = True
    client = MagicMock(
        is_connected=True,
        write_gatt_char=peripheral.write_gatt_char,
        disconnect=AsyncMock(),
    )
    coordinator._client = client
    coordinator._notification_token = object()
    coordinator._notify_started_monotonic = time.monotonic()
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    entry = SimpleNamespace(
        entry_id="entry-a",
        domain=DOMAIN,
        state=ConfigEntryState.LOADED,
        runtime_data=coordinator,
        title="Local H6199",
        options={},
    )
    monkeypatch.setattr(
        hass.config_entries,
        "async_get_entry",
        lambda entry_id: entry if entry_id == entry.entry_id else None,
    )
    connection = await hass_ws_client(hass)
    try:
        await connection.send_json_auto_id(
            {
                "type": WS_APPLY_SNAPSHOT,
                "config_entry_id": entry.entry_id,
                "name": "#712 retry contradiction",
                "content": effect_content_to_dict(
                    VideoProfile(
                        "H6199",
                        "movie",
                        True,
                        50,
                        False,
                        50,
                        17,
                        RelativeBrightness(100, 100, 100, 100),
                        False,
                    )
                ),
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
        response = await connection.receive_json()
        assert response["success"], response
        deployment = response["result"]["deployment"]
        assert deployment["phase"] == DeploymentPhase.CONFIRMED.value
        assert deployment["verification_confidence"] == ObservationConfidence.SETTINGS_MATCH.value
        assert sum(packet[0] == 0x33 and packet[1] == 0xAE for packet in peripheral.packets) == 2
        if contradiction == "blank_screen_policy":
            assert (
                sum(packet[0] == 0x33 and packet[1] == 0xA9 and packet[2] == 0x0A for packet in peripheral.packets) == 2
            )
        assert peripheral.state.relative_brightness == (100, 100, 100, 100)
    finally:
        await connection.close()
        await backend.preview.async_shutdown()
        await coordinator.async_shutdown()


async def test_studio_apply_missing_final_readback_does_not_replay(
    hass: HomeAssistant,
    hass_ws_client,
    monkeypatch,
) -> None:
    backend = await _setup_backend(hass)
    coordinator = GoveeBLECoordinator(
        hass,
        "11:22:33:44:55:66",
        "H6199",
        configuration_url="test",
    )
    set_qualified_identity(coordinator)
    peripheral = _H6199Peripheral(coordinator)
    peripheral.drop_final_relative_replies = 2
    client = MagicMock(
        is_connected=True,
        write_gatt_char=peripheral.write_gatt_char,
        disconnect=AsyncMock(),
    )
    coordinator._client = client
    coordinator._notification_token = object()
    coordinator._notify_started_monotonic = time.monotonic()
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    entry = SimpleNamespace(
        entry_id="entry-a",
        domain=DOMAIN,
        state=ConfigEntryState.LOADED,
        runtime_data=coordinator,
        title="Local H6199",
        options={},
    )
    monkeypatch.setattr(
        hass.config_entries,
        "async_get_entry",
        lambda entry_id: entry if entry_id == entry.entry_id else None,
    )
    connection = await hass_ws_client(hass)
    try:
        await connection.send_json_auto_id(
            {
                "type": WS_APPLY_SNAPSHOT,
                "config_entry_id": entry.entry_id,
                "name": "#712 missing final relative readback",
                "content": effect_content_to_dict(
                    VideoProfile(
                        "H6199",
                        "movie",
                        True,
                        50,
                        False,
                        50,
                        17,
                        RelativeBrightness(100, 100, 100, 100),
                        False,
                    )
                ),
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
        response = await connection.receive_json()
        assert response["success"], response
        deployment = response["result"]["deployment"]
        assert deployment["phase"] == DeploymentPhase.UNCERTAIN.value
        assert deployment["verification_confidence"] == ObservationConfidence.UNKNOWN.value
        assert sum(packet[0] == 0x33 and packet[1] == 0xAE for packet in peripheral.packets) == 1
        assert peripheral.state.relative_brightness == (100, 100, 100, 100)
    finally:
        await connection.close()
        await backend.preview.async_shutdown()
        await coordinator.async_shutdown()


async def test_studio_apply_invalidates_previous_setting_expectations(
    hass: HomeAssistant,
    hass_ws_client,
    monkeypatch,
) -> None:
    backend = await _setup_backend(hass)
    coordinator = GoveeBLECoordinator(
        hass,
        "11:22:33:44:55:66",
        "H6199",
        configuration_url="test",
    )
    set_qualified_identity(coordinator)
    peripheral = _H6199Peripheral(coordinator)
    client = MagicMock(
        is_connected=True,
        write_gatt_char=peripheral.write_gatt_char,
        disconnect=AsyncMock(),
    )
    coordinator._client = client
    coordinator._notification_token = object()
    coordinator._notify_started_monotonic = time.monotonic()
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    await apply_relative_brightness(coordinator, (100, 100, 100, 100))
    assert coordinator._expected_state.get("relative_brightness_left") == (
        100,
        coordinator._expected_state["relative_brightness_left"][1],
    )
    entry = SimpleNamespace(
        entry_id="entry-a",
        domain=DOMAIN,
        state=ConfigEntryState.LOADED,
        runtime_data=coordinator,
        title="Local H6199",
        options={},
    )
    monkeypatch.setattr(
        hass.config_entries,
        "async_get_entry",
        lambda entry_id: entry if entry_id == entry.entry_id else None,
    )
    connection = await hass_ws_client(hass)
    try:
        await connection.send_json_auto_id(
            {
                "type": WS_APPLY_SNAPSHOT,
                "config_entry_id": entry.entry_id,
                "name": "#712 invalidate previous expectation",
                "content": effect_content_to_dict(
                    VideoProfile(
                        "H6199",
                        "movie",
                        True,
                        50,
                        False,
                        50,
                        17,
                        RelativeBrightness(90, 90, 90, 90),
                        False,
                    )
                ),
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
        response = await connection.receive_json()
        assert response["success"], response
        deployment = response["result"]["deployment"]
        assert deployment["phase"] == DeploymentPhase.CONFIRMED.value
        assert deployment["verification_confidence"] == ObservationConfidence.SETTINGS_MATCH.value
        assert peripheral.state.relative_brightness == (90, 90, 90, 90)
        assert sum(packet[0] == 0x33 and packet[1] == 0xAE for packet in peripheral.packets) == 2
        relative_queries = [
            index
            for index, packet in enumerate(peripheral.packets)
            if packet == build_relative_brightness_query("H6199")
        ]
        assert len(relative_queries) == 3
    finally:
        await connection.close()
        await backend.preview.async_shutdown()
        await coordinator.async_shutdown()
