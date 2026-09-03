"""H6179 coordinator status and lifecycle semantics."""

import time
from datetime import time as dt_time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_status import (
    H6179_STATUS_FIELD_AUTHORITY,
    H6179_WRITE_FIELD_AUTHORITY,
    FieldAuthority,
    ParsedColorModeResponse,
    ParsedMode,
    parse_color_mode,
)
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    encode_h6179_brightness,
    parse_h6179_status,
)
from custom_components.ha_govee_led_ble.h6179_schedule import (
    LimitState,
    ScheduleAction,
    ScheduleSlot,
    ScheduleState,
    SleepState,
    WakeState,
)
from custom_components.ha_govee_led_ble.transport import xor_checksum

H = bytes.fromhex


def _status(domain: int, body: bytes) -> bytes:
    packet = bytearray((0xAA, domain))
    packet.extend(body)
    packet.extend(bytes(19 - len(packet)))
    packet.append(xor_checksum(packet))
    return bytes(packet)


def _mode(body: bytes) -> ParsedColorModeResponse:
    status = parse_h6179_status(_status(0x05, body))
    assert status is not None
    return parse_color_mode(status, "H6179")


@pytest.fixture
def h6179(hass) -> GoveeBLECoordinator:
    return GoveeBLECoordinator(
        hass,
        "AA:BB:CC:DD:EE:79",
        "H6179",
        configuration_url="homeassistant://ha-govee-led-ble/editor/test-entry",
    )


def test_h6179_field_authority_is_explicit() -> None:
    assert H6179_STATUS_FIELD_AUTHORITY == {
        "is_on": FieldAuthority.AUTHORITATIVE,
        "brightness_pct": FieldAuthority.AUTHORITATIVE,
        "fw_version": FieldAuthority.AUTHORITATIVE,
        "hw_version": FieldAuthority.AUTHORITATIVE,
        "color_mode": FieldAuthority.PROVISIONAL,
        "rgb_color": FieldAuthority.PROVISIONAL,
        "color_temp_kelvin": FieldAuthority.PROVISIONAL,
        "effect": FieldAuthority.PROVISIONAL,
        "unknown_scene_code": FieldAuthority.PROVISIONAL,
        "diy_code": FieldAuthority.PROVISIONAL,
        "music_mode": FieldAuthority.PROVISIONAL,
        "music_mode_id": FieldAuthority.PROVISIONAL,
        "music_sensitivity": FieldAuthority.PROVISIONAL,
        "music_color": FieldAuthority.PROVISIONAL,
    }
    assert set(H6179_WRITE_FIELD_AUTHORITY.values()) == {FieldAuthority.OPTIMISTIC}


def test_h6179_core_and_identity_replies_are_semantic() -> None:
    power = parse_h6179_status(_status(0x01, b"\x01"))
    brightness = parse_h6179_status(
        _status(0x04, bytes((encode_h6179_brightness(50),))),
    )
    firmware = parse_h6179_status(_status(0x06, b"1.00.08\x00"))
    hardware = parse_h6179_status(_status(0x07, b"\x03" + b"1.00.00\x00"))

    assert power is not None and power.values == {"is_on": True}
    assert brightness is not None and brightness.values == {"brightness_pct": 50}
    assert firmware is not None and firmware.values == {"version": "1.00.08"}
    assert hardware is not None and hardware.values == {"version": "1.00.00"}
    assert "raw_brightness" not in brightness.values


def test_h6179_static_rgb_and_temperature_readback() -> None:
    rgb = _mode(H("0d1234560000000000"))
    temperature = _mode(H("0dffffff0bb8ffb170"))

    assert rgb == ParsedColorModeResponse(
        mode=ParsedMode.COLOUR,
        rgb_color=(0x12, 0x34, 0x56),
    )
    assert temperature == ParsedColorModeResponse(
        mode=ParsedMode.COLOUR,
        color_temp_kelvin=3000,
    )


def test_h6179_known_scene_music_and_diy_readback() -> None:
    scene = _mode(H("041000"))
    music_auto = _mode(H("0e006300"))
    music_fixed = _mode(H("0e013201123456"))
    diy = _mode(H("0a3412"))

    assert scene == ParsedColorModeResponse(
        mode=ParsedMode.SCENE,
        effect="energetic",
        scene_code=0x10,
    )
    assert music_auto == ParsedColorModeResponse(
        mode=ParsedMode.MUSIC,
        music_mode="mode_0",
        music_mode_id=0,
        music_sensitivity=99,
    )
    assert music_fixed == ParsedColorModeResponse(
        mode=ParsedMode.MUSIC,
        music_mode="mode_1",
        music_mode_id=1,
        music_sensitivity=50,
        music_color=(0x12, 0x34, 0x56),
    )
    assert diy == ParsedColorModeResponse(
        mode=ParsedMode.DIY,
        diy_code=0x1234,
    )


def test_h6179_unknown_scene_remains_representable_but_unknown_modes_fail_closed() -> None:
    scene = _mode(H("040200"))

    assert scene == ParsedColorModeResponse(
        mode=ParsedMode.SCENE,
        scene_code=0x02,
    )
    assert parse_h6179_status(_status(0x05, H("0e7f3200"))) is None
    assert parse_h6179_status(_status(0x05, H("7f102030405060708090a0b0c0d0e0f001"))) is None


@pytest.mark.parametrize("is_on", [False, True])
async def test_h6179_setup_accepts_lamp_off_or_on_and_optional_mode_can_be_missing(
    h6179: GoveeBLECoordinator,
    is_on: bool,
) -> None:
    client = MagicMock(is_connected=True)
    h6179._client = client
    h6179.rgb_color = (12, 34, 56)

    async def send(domains: frozenset[str]) -> bool:
        if domains == h6179.profile.setup_required_status_domains:
            h6179._notify_callback(None, bytearray(_status(0x01, bytes((is_on,)))))
            h6179._notify_callback(
                None,
                bytearray(_status(0x04, bytes((encode_h6179_brightness(50),)))),
            )
            return True
        return False

    with (
        patch.object(h6179, "_ensure_connected", new=AsyncMock(return_value=client)),
        patch.object(h6179, "_send_h6179_status_queries", new=AsyncMock(side_effect=send)),
    ):
        state = await h6179._async_update_data()

    assert state["is_on"] is is_on
    assert state["brightness_pct"] == 50
    assert h6179.rgb_color == (12, 34, 56)


def test_h6179_rejected_core_reply_does_not_advance_accepted_field_revision(
    h6179: GoveeBLECoordinator,
) -> None:
    h6179.is_on = True
    h6179._expected_state["is_on"] = (True, time.monotonic() + 60)
    baseline = h6179._field_revisions.get("is_on", 0)

    h6179._notify_callback(None, bytearray(_status(0x01, b"\x00")))

    assert h6179.is_on is True
    assert h6179._field_revisions.get("is_on", 0) == baseline

    h6179._notify_callback(None, bytearray(_status(0x01, b"\x01")))

    assert h6179._field_revisions["is_on"] == baseline + 1


def test_h6179_external_app_change_is_accepted_after_handoff_and_reconnect(
    h6179: GoveeBLECoordinator,
) -> None:
    client = MagicMock()
    h6179._client = client
    h6179.is_on = True
    h6179.brightness_pct = 100
    h6179._expected_state["is_on"] = (True, 0)
    h6179._clear_client_state(client)

    h6179._notify_callback(None, bytearray(_status(0x01, b"\x00")))
    h6179._notify_callback(
        None,
        bytearray(_status(0x04, bytes((encode_h6179_brightness(50),)))),
    )

    assert h6179._expected_state == {}
    assert h6179.is_on is False
    assert h6179.brightness_pct == 50
    assert MODEL_PROFILES["H6179"].provisional_status_domains >= {"mode"}


async def test_transport_disconnect_notifies_reactive_backend(
    h6179: GoveeBLECoordinator,
    hass,
) -> None:
    client = MagicMock()
    disconnected = AsyncMock()
    h6179.set_reactive_lifecycle_hooks(
        supersede=AsyncMock(),
        disconnect=disconnected,
    )
    h6179._client = client

    h6179._clear_client_state(client)
    await hass.async_block_till_done()

    disconnected.assert_awaited_once()


def test_h6179_schedule_replies_update_complete_state_before_domain_revision(
    h6179: GoveeBLECoordinator,
) -> None:
    assert h6179.h6179_schedule_state == ScheduleState.neutral()
    assert h6179.h6179_schedule_slot_one_time == (False, False, False, False)
    assert h6179.h6179_wake_one_time is False

    h6179._notify_callback(None, bytearray(_status(0x23, H("ff81061e8080160f00810c009500000080"))))
    h6179._notify_callback(None, bytearray(_status(0x11, bytes((1, 30, 45, 20)))))
    h6179._notify_callback(None, bytearray(_status(0x12, bytes((1, 100, 7, 15, 0x80, 30)))))
    h6179._notify_callback(None, bytearray(_status(0x0E, b"\x01")))

    assert h6179.h6179_schedule_state.schedule_slots == (
        ScheduleSlot(0, True, ScheduleAction.ON, dt_time(6, 30), 0),
        ScheduleSlot(1, True, ScheduleAction.OFF, dt_time(22, 15), 0),
        ScheduleSlot(2, True, ScheduleAction.ON, dt_time(12), 0x15),
        ScheduleSlot.disabled(3),
    )
    assert h6179.h6179_schedule_slot_one_time == (True, False, False, True)
    assert h6179.h6179_schedule_state.sleep == SleepState(True, 30, 45, 20)
    assert h6179.h6179_schedule_state.wake == WakeState(True, dt_time(7, 15), 0, 30, 100)
    assert bool(h6179.h6179_wake_one_time)
    assert h6179.h6179_schedule_state.limit_state == LimitState(True)
    assert all(h6179._status_domain_revisions[domain] == 1 for domain in ("schedules", "sleep", "wake", "limit"))


def test_h6179_semantic_schedule_rejection_is_logged_without_partial_state(
    h6179: GoveeBLECoordinator,
) -> None:
    initial = h6179.h6179_schedule_state

    h6179._notify_callback(None, bytearray(_status(0x23, H("0481061e8080160f00810c009500000080"))))

    assert h6179.h6179_schedule_state == initial
    assert h6179._status_domain_revisions.get("schedules", 0) == 0
    assert h6179.packet_log[-1]["outcome"] == "rejected"
    assert h6179.packet_log[-1]["reason"] == "semantic_rejected"
    assert h6179.packet_log[-1]["parser"] == "speculative/h6179_status_reply"
