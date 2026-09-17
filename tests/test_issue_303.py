"""Issue #303 regression checks for protocol, readback and camera applicability.

Only BLE connection/I/O is stubbed unless a test explicitly isolates validation.
Synthetic profiles prove software capability boundaries, not H66A0 qualification.
Run: uv run --no-sync pytest tests/test_issue_303.py -v --tb=short
"""

from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, ModelProfile, ReadDomain
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_status import (
    ParsedMode,
    decode_status_frame_result,
    parse_color_mode,
)
from custom_components.ha_govee_led_ble.effect_domain import VideoProfile
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    _STATUS_ROOTS,
    H6199StatusReply,
    build_white_balance,
    build_white_balance_query,
)
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.native_profile_controls import apply_active_video_mode
from custom_components.ha_govee_led_ble.transport import xor_checksum
from custom_components.ha_govee_led_ble.video_applicability import validate_video_request, white_balance_readback_state
from tests.test_h6199_native_controls import frame, qualify


@pytest.fixture
def connected(hass, monkeypatch):
    def create(model):
        c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", model, configuration_url=None)
        c._client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(), disconnect=AsyncMock())
        monkeypatch.setattr(c, "_ensure_connected", AsyncMock(return_value=c._client))
        monkeypatch.setattr(c, "_renew_foreground_lease", lambda: None)
        return c

    return create


@pytest.mark.parametrize("kelvin", [0, 4000, 6500, 3123, 4100])
def test_static_reply_is_accepted_and_temperature_is_parsed(kelvin):
    packet = frame(f"aa051500{kelvin:04x}")
    assert len(packet) == 20 and xor_checksum(packet[:-1]) == packet[-1]
    result = decode_status_frame_result(packet, "H617A")
    assert result.parsed is not None, f"{kelvin} K rejected: {result.rejection}"
    parsed = parse_color_mode(result.parsed.generated, "H617A")
    assert parsed.mode is ParsedMode.COLOUR
    assert parsed.color_temp_kelvin == (kelvin or None)


@pytest.mark.parametrize("kelvin", [0, 4000, 6500, 3123, 4100])
async def test_static_reply_completes_setup_refresh(connected, kelvin):
    c = connected("H617A")
    client = c._client
    replies = {
        frame("aa01"): frame("aa0101"),
        frame("aa04"): frame("aa042a"),
        frame("aa05"): frame(f"aa051500{kelvin:04x}"),
    }

    async def respond(_uuid, packet, **kwargs):
        if packet in replies:
            c._notify_callback(None, bytearray(replies[packet]))

    client.write_gatt_char.side_effect = respond
    refreshed = await c.refresh_state(
        refresh_all=True, required_domains=c.profile.setup_required_read_domains, timeout=0.1
    )
    assert c.is_on and c.brightness_pct == 42
    assert {frame("aa01"), frame("aa04"), frame("aa05")} <= {
        call.args[1] for call in client.write_gatt_char.await_args_list
    }
    rejected = [entry["reason"] for entry in c.packet_log if entry["outcome"] == "rejected"]
    assert refreshed, f"{kelvin} K: power/brightness observed, colour_mode={c.color_mode}, rejected={rejected}"
    assert c.color_mode is ParsedMode.COLOUR


def test_zero_kelvin_is_not_a_new_temperature_observation(connected):
    c = connected("H6099")
    c._notify_callback(None, bytearray(frame("aa0515011194")))
    assert c.color_temp_kelvin == 4500
    revision = c._field_revisions["color_temp_kelvin"]
    c._notify_callback(None, bytearray(frame("aa0515010000")))
    assert c.color_mode is ParsedMode.COLOUR
    assert c.color_temp_kelvin == 4500
    assert c._field_revisions["color_temp_kelvin"] == revision, (
        f"zero created a fresh temperature observation: value={c.color_temp_kelvin}, "
        f"source={c.color_temp_kelvin_source}"
    )


@pytest.fixture
def scalar_model(monkeypatch):
    profile = ModelProfile(
        "Synthetic read-only scalar register",
        command_grammar="H6199",
        status_grammar="issue-303-status",
        video_grammar="H6199",
        supports_video_mode=True,
        video_modes=("movie", "game"),
        read_domains=frozenset({ReadDomain.DISPLAY_SETTING}),
        supports_white_balance_readback=True,
        video_white_balance_representation="scalar",
        video_white_balance_min=0,
        video_white_balance_max=100,
        video_white_balance_default=50,
        video_white_balance_calibration=tuple((value,) for value in range(101)),
    )
    monkeypatch.setitem(MODEL_PROFILES, "H9903", profile)
    monkeypatch.setitem(_STATUS_ROOTS, "issue-303-status", ("issue-303-status", H6199StatusReply))
    return profile


@pytest.mark.parametrize("writable", [False, True])
async def test_white_balance_read_is_independent_of_write_support(connected, scalar_model, monkeypatch, writable):
    monkeypatch.setitem(MODEL_PROFILES, "H9903", replace(scalar_model, supports_white_balance=writable))
    c = connected("H9903")
    query = frame("aaa906")

    async def respond(_uuid, packet, **kwargs):
        assert packet == query
        c._notify_callback(None, bytearray(frame("aaa9060132")))

    c._client.write_gatt_char.side_effect = respond
    # Unsolicited readback already works, even with calibration writes disabled.
    c._notify_callback(None, bytearray(frame("aaa9060132")))
    assert c.white_balance_scalar == 50 and c._field_revisions["white_balance_scalar"] == 1
    if not writable:
        with pytest.raises(ValueError, match="does not support white balance"):
            build_white_balance(50, None, c.model)
    refreshed = await c.refresh_state(refresh_display_settings=frozenset({"white_balance"}), timeout=0.1)
    assert refreshed, f"write support={writable}, query writes={c._client.write_gatt_char.await_count}"
    assert c._field_revisions["white_balance_scalar"] == 2


@pytest.mark.parametrize("writable", [False, True])
async def test_white_balance_query_is_scheduled_without_write_support(connected, scalar_model, monkeypatch, writable):
    monkeypatch.setitem(MODEL_PROFILES, "H9903", replace(scalar_model, supports_white_balance=writable))
    c = connected("H9903")
    assert await c._send_state_queries(query_white_balance=True, query_segments=False)
    packets = [call.args[1] for call in c._client.write_gatt_char.await_args_list]
    assert frame("aaa906") in packets, f"write support={writable}, scheduled={packets}"


@pytest.mark.parametrize("writable", [False, True])
def test_white_balance_query_builder_accepts_read_only_profile(scalar_model, monkeypatch, writable):
    monkeypatch.setitem(MODEL_PROFILES, "H9903", replace(scalar_model, supports_white_balance=writable))
    assert build_white_balance_query("H9903") == frame("aaa906")


def test_h617a_white_balance_query_needs_no_video_writes(scalar_model, monkeypatch):
    monkeypatch.setitem(
        MODEL_PROFILES,
        "H9903",
        replace(
            scalar_model,
            command_grammar="H617A",
            video_grammar=None,
            supports_video_mode=False,
            video_modes=(),
            video_white_balance_calibration=(),
        ),
    )
    assert build_white_balance_query("H9903") == frame("aaa906")


@pytest.mark.parametrize("qualified", [False, True])
def test_read_only_white_balance_preserves_firmware_gate(camera_device, qualified):
    c = camera_device
    c.profile = replace(c.profile, supports_white_balance=False)
    if c.model == "H6199" and not qualified:
        c.fw_version = None
    assert (white_balance_readback_state(c.profile, c) == "supported") is (c.model == "H6099" or qualified)


async def test_white_balance_refresh_requires_fresh_register(connected, scalar_model):
    c = connected("H9903")
    c._notify_callback(None, bytearray(frame("aaa9060132")))
    assert not await c.refresh_state(refresh_display_settings=frozenset({"white_balance"}), timeout=0.01)
    assert c._field_revisions["white_balance_scalar"] == 1


@pytest.mark.parametrize("readable", [False, True])
def test_white_balance_query_requires_read_capability(scalar_model, monkeypatch, readable):
    monkeypatch.setitem(
        MODEL_PROFILES,
        "H9903",
        replace(
            scalar_model,
            supports_white_balance_readback=False if readable else True,
            read_domains=scalar_model.read_domains if readable else frozenset(),
        ),
    )
    with pytest.raises(ValueError, match="readback"):
        build_white_balance_query("H9903")


@pytest.fixture(params=["H6099", "H6199"])
def camera_device(connected, request):
    c = connected(request.param)
    if c.model == "H6199":
        qualify(c)
    c.is_on = True
    return c


def observe_camera(c, state):
    value = {"unknown": 255, "healthy": 1, "absent": 0, "incompatible": 2}[state]
    c._notify_callback(None, bytearray(frame(f"aa32{value:02x}")))
    field = "camera_health" if c.model == "H6099" else "camera_status"
    assert getattr(c, field) == state


@pytest.mark.parametrize("state", ["unknown", "healthy", "absent", "incompatible"])
def test_camera_evidence_controls_native_video_choices(camera_device, state):
    observe_camera(camera_device, state)
    effects = GoveeBLELight(camera_device).effect_list
    assert ("Game" in effects and "Movie" in effects) is (state in {"unknown", "healthy"}), effects


@pytest.mark.parametrize("state", ["unknown", "healthy", "absent", "incompatible"])
def test_camera_evidence_controls_saved_video_validation(camera_device, state):
    observe_camera(camera_device, state)
    content = VideoProfile(camera_device.model, "movie", None, None, None, None, None, None, None)
    if state in {"absent", "incompatible"}:
        with pytest.raises(ValueError, match="[Cc]amera"):
            validate_video_request(camera_device, content)
    else:
        validate_video_request(camera_device, content)


@pytest.mark.parametrize("state", ["unknown", "healthy", "absent", "incompatible"])
async def test_camera_evidence_blocks_physical_video_write(camera_device, state):
    c = camera_device
    observe_camera(c, state)
    # Disable confirmation to isolate admission through the real physical writer.
    try:
        await apply_active_video_mode(c, mode="movie", requested_values={}, verify=False)
    except ValueError, HomeAssistantError:
        assert state in {"absent", "incompatible"}
    writes = c._client.write_gatt_char.await_count
    assert (writes == 0) is (state in {"absent", "incompatible"}), f"camera={state}, physical writes={writes}"


@pytest.mark.parametrize("state", ["absent", "incompatible"])
async def test_video_service_reports_camera_reason(camera_device, monkeypatch, state):
    c = camera_device
    observe_camera(c, state)
    # Reproduce an unconfirmed command without waiting for BLE timeouts.
    monkeypatch.setattr(c, "refresh_state", AsyncMock(return_value=False))
    with pytest.raises(HomeAssistantError) as error:
        await GoveeBLELight(c)._async_set_video_mode("movie")
    key = error.value.translation_key
    assert key == f"camera_{state}", f"camera={state}, error={key}, cause={error.value.__cause__}"
    assert c._client.write_gatt_char.await_count == 0


@pytest.mark.parametrize("state", ["unknown", "absent", "incompatible"])
async def test_video_rechecks_camera_after_connect(camera_device, monkeypatch, state):
    c = camera_device
    observe_camera(c, "healthy")
    client = c._client

    async def connect():
        observe_camera(c, state)
        return client

    monkeypatch.setattr(c, "_ensure_connected", connect)
    if state == "unknown":
        assert await apply_active_video_mode(c, mode="movie", requested_values={}, verify=False)
        assert client.write_gatt_char.await_count == 1
    else:
        with pytest.raises(ValueError, match="Camera"):
            await apply_active_video_mode(c, mode="movie", requested_values={}, verify=False)
        assert client.write_gatt_char.await_count == 0
