"""Coordinator integration of H6099 readback and recovery evidence."""

import asyncio
from dataclasses import replace
from unittest.mock import ANY, AsyncMock, MagicMock

import pytest
from bleak import BleakError

from custom_components.ha_govee_led_ble.const import get_profile
from custom_components.ha_govee_led_ble.control_arbiter import ControlIntent, async_control_intent
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode
from custom_components.ha_govee_led_ble.effect_compiler import compile_video_profile
from custom_components.ha_govee_led_ble.effect_deployments import EffectDeploymentRepository
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem, VideoProfile
from custom_components.ha_govee_led_ble.effect_runtime import EffectDeploymentEngine, async_apply_compiled_profile
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_black_border_query,
    build_blank_screen_query,
    build_brightness,
    build_brightness_query,
    build_h6099_diy_activation,
    build_physical_ic_count_query,
    build_power,
    build_power_query,
    build_subordinate_query,
)
from custom_components.ha_govee_led_ble.music_commands import (
    build_music_params,
    prepare_music_profile_writes,
    prepare_music_request,
)
from custom_components.ha_govee_led_ble.music_semantics import capture_music_parameters
from custom_components.ha_govee_led_ble.native_profile_controls import apply_black_border, apply_blank_screen
from tests.storage_test_double import InMemoryVersionedDocumentStore
from tests.test_h6099 import frame

M = "custom_components.ha_govee_led_ble.coordinator"
POLICY_FIELDS = (
    "blank_screen",
    "blank_screen_detection",
    "blank_screen_low_brightness_duration_seconds",
    "blank_screen_same_tone_duration_seconds",
)


@pytest.fixture
def device(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6099", configuration_url="test")
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(), disconnect=AsyncMock())
    coordinator._client = client
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(coordinator, "_renew_foreground_lease", lambda: None)
    return coordinator


def notify(device, prefix):
    device._notify_callback(None, bytearray(frame(prefix)))


def test_baseline_and_absent_music_fields(device):
    notify(device, "aa042a")
    assert device.brightness_pct == 42 and device._field_revisions["brightness_pct"] == 1
    notify(device, "aa0515011194")
    assert device.color_temp_kelvin == 4500
    notify(device, "aa0515010000")
    assert device.color_mode is ParsedMode.COLOUR and device.color_temp_kelvin is None
    assert device.color_temp_kelvin_source == "observed"
    assert device._field_revisions["color_temp_kelvin"] == 2
    device.music_color = (1, 2, 3)
    device.music_calm = True
    notify(device, "aa0513302a0101010203")
    assert device.music_mode == "bloom" and device.music_sensitivity == 42
    assert device.music_color == (1, 2, 3) and device.music_calm
    assert "music_color" not in device._field_revisions and "music_calm" not in device._field_revisions
    notify(device, "aa0513032a0000")
    assert device.music_color is None and device._field_revisions["music_color"] == 1


def test_display_replies_are_atomic_and_field_specific(device):
    notify(device, "aaa90a0601020a007800")
    before = device.capture_effect_control_state()
    revisions = dict(device._field_revisions)
    device._arm_expected_values(dict(zip(POLICY_FIELDS, (True, 1, 300, 600), strict=True)))
    notify(device, "aaa90a0601012c017800")
    assert device.capture_effect_control_state() == before
    assert device._field_revisions == revisions
    notify(device, "aaa90a0601012c015802")
    assert tuple(getattr(device, field) for field in POLICY_FIELDS) == (True, 1, 300, 600)
    assert all(device._field_revisions[field] == 2 for field in POLICY_FIELDS)
    notify(device, "aaa90b0101")
    assert device.black_border is True and device.capture_effect_control_state().black_border is True
    assert device._field_revisions["black_border"] == 1
    device._arm_expected_values({"black_border": False})
    notify(device, "aaa90b0101")
    assert device._field_revisions["black_border"] == 1
    notify(device, "aaa9060132")
    assert device._field_revisions["black_border"] == 1


@pytest.mark.parametrize("setting", ["black_border", "blank_screen"])
@pytest.mark.parametrize("fresh", [False, True])
async def test_refresh_and_observe_require_exact_reply(device, setting, fresh):
    device.subordinate_21_version = "1.00.11"
    expected = (
        {"black_border": False}
        if setting == "black_border"
        else dict(zip(POLICY_FIELDS, (True, 1, 300, 600), strict=True))
    )
    for field, value in expected.items():
        setattr(device, field, value)
    query = build_black_border_query("H6099") if setting == "black_border" else build_blank_screen_query("H6099")

    async def respond(_uuid, packet, **kwargs):
        if packet[1] in (0x30, 0x32):
            return
        assert packet == query
        notify(
            device, ("aaa90b0100" if setting == "black_border" else "aaa90a0601012c015802") if fresh else "aaa9060132"
        )

    device._client.write_gatt_char.side_effect = respond
    kwargs = (
        {"expected_black_border": False}
        if setting == "black_border"
        else {
            "expected_blank_screen": True,
            "expected_blank_screen_policy": (1, 300, 600),
        }
    )
    assert await device.refresh_state(**kwargs, timeout=0.01) is fresh
    assert await device.async_observe_effect(expected, timeout=0.01) is (True if fresh else None)
    assert await device.refresh_state(refresh_display_settings=frozenset({setting}), timeout=0.01) is fresh


@pytest.mark.parametrize("version", [None, "1.00.10", "1.00.11"])
async def test_border_query_gate_and_optional_setup(device, version):
    device.subordinate_21_version = version
    await device._send_state_queries(query_segments=False)
    packets = [call.args[1] for call in device._client.write_gatt_char.await_args_list]
    assert (build_black_border_query("H6099") in packets) is (version == "1.00.11")
    if version != "1.00.11":
        device._ensure_connected.reset_mock()
        assert not await device.refresh_state(expected_black_border=True, timeout=0)
        device._ensure_connected.assert_not_awaited()

    async def respond(_uuid, packet, **kwargs):
        for prefix in ("aa0101", "aa042a", "aa0515011194"):
            notify(device, prefix)

    device._client.write_gatt_char.side_effect = respond
    assert await device.refresh_state(
        refresh_all=True,
        required_domains=device.profile.setup_required_read_domains,
        timeout=0.01,
    )
    assert device.profile.physical_ic_count is None


async def test_ic_discovery_is_device_scoped_and_only_initializes_new_defaults(device):
    device.fw_version = device.hw_version = "1.00.00"
    await device._send_identity_queries()
    assert [call.args[1] for call in device._client.write_gatt_char.await_args_list] == [
        build_subordinate_query(0x20, "H6099"),
        build_subordinate_query(0x21, "H6099"),
        build_physical_ic_count_query("H6099"),
    ]
    for prefix in ("aa400000", "aa40ffff"):
        notify(device, prefix)
        assert device.profile.physical_ic_count is None
    notify(device, "aa40000e")
    assert device.profile.physical_ic_count == 14 and get_profile("H6099").physical_ic_count is None
    assert device.music_piano_key_count == 11 and device.music_separation_point == 3
    assert device.music_fountain_direction == "two_way"
    assert device._field_revisions == {}
    device.music_piano_key_count = 12
    notify(device, "aa40000e")
    assert device.music_piano_key_count == 12
    notify(device, "aa400000")
    assert device.profile.physical_ic_count == 14
    device._clear_client_state(device._client)
    assert device.profile.physical_ic_count is None
    notify(device, "aa40003c")
    assert device.music_piano_key_count == 12 and device._field_revisions == {}


@pytest.mark.parametrize("reply", ["aaa90b0101", "aa0101"])
async def test_full_refresh_needs_border_and_core_domains(device, reply):
    device.subordinate_21_version = "1.00.11"

    async def respond(*args, **kwargs):
        notify(device, reply)

    device._client.write_gatt_char.side_effect = respond
    assert not await device.refresh_state(refresh_all=True, timeout=0)


async def test_border_reconnect_guard_prevents_optimistic_state(device):
    device.subordinate_21_version = "1.00.11"

    async def reconnect():
        device.subordinate_21_version = None
        return device._client

    device._ensure_connected.side_effect = reconnect
    with pytest.raises(ValueError, match="black_border"):
        await apply_black_border(device, True)
    assert device.black_border is None and device.control_write_attempts == 0
    assert device._field_revisions == {} and device._expected_state == {}
    device._client.write_gatt_char.assert_not_awaited()


async def test_ic_reset_precedes_reconnect_await(hass, monkeypatch):
    device = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6099", configuration_url="test")
    device.profile = replace(device.profile, physical_ic_count=60)
    device.installation_direction, device.camera_health = 4, "healthy"

    async def connect(*args, **kwargs):
        assert device.profile.physical_ic_count is None
        assert device.installation_direction is None and device.camera_health == "unknown"
        raise BleakError("offline")

    monkeypatch.setattr(f"{M}.async_establish_ble_connection", connect)
    with pytest.raises(BleakError, match="offline"):
        await device._ensure_connected()
    assert device.control_write_attempts == 0


@pytest.mark.parametrize("failure", [False, True])
async def test_diy_recovery_activation_preserves_notification_and_zero_attempt_state(device, monkeypatch, failure):
    state = replace(device.capture_effect_control_state(), mode="custom", is_on=True, diy_code=0x1234)
    if failure:
        device._ensure_connected.side_effect = ValueError("unavailable")
        with pytest.raises(ValueError, match="unavailable"):
            await device.async_restore_effect_control_state(state, overwritten_diy_code=None)
        assert device.diy_code is None and device.control_write_attempts == 0
        return

    async def respond(_uuid, packet, **kwargs):
        if packet == build_h6099_diy_activation(0x1234):
            notify(device, "aa050a7856")
        elif packet == build_power_query("H6099"):
            notify(device, "aa0101")
        elif packet == build_brightness_query("H6099"):
            notify(device, "aa0464")
        else:
            assert packet in (build_power(True, "H6099"), build_brightness(100, "H6099"))

    device._client.write_gatt_char.side_effect = respond
    monkeypatch.setattr(device, "async_observe_effect", AsyncMock(return_value=True))
    # Expire write expectations so the notification represents a later authoritative change.
    monkeypatch.setattr(f"{M}.EXPECTED_STATE_TTL", 0)
    assert await device.async_restore_effect_control_state(state, overwritten_diy_code=None)
    assert device.diy_code == 0x5678
    device._client.write_gatt_char.reset_mock()
    assert not await device.async_restore_effect_control_state(state, overwritten_diy_code=0x1234)
    device._client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("attempted", [False, True])
@pytest.mark.parametrize("cleanup_fails", [False, True])
@pytest.mark.parametrize("cancelled", [False, True])
async def test_off_recovery_cleanup_preserves_original_failure(device, attempted, cleanup_fails, cancelled):
    state = replace(device.capture_effect_control_state(), mode="custom", is_on=False, diy_code=0x1234)
    error = asyncio.CancelledError() if cancelled else ValueError("original recovery failure")
    off = build_power(False, "H6099")

    def transform(packet):
        if packet != off and not attempted:
            raise error
        return packet

    async def transmit(_uuid, packet, **kwargs):
        if packet != off:
            raise error
        if cleanup_fails:
            raise RuntimeError("power-off cleanup failed")

    device.profile = replace(device.profile, outbound_transform=transform)
    device._client.write_gatt_char.side_effect = transmit
    with pytest.raises(type(error)) as caught:
        await device.async_restore_effect_control_state(state, overwritten_diy_code=None)
    assert caught.value is error
    packets = [call.args[1] for call in device._client.write_gatt_char.await_args_list]
    assert packets == ([build_power(True, "H6099"), off] if attempted else [])
    assert device.control_write_attempts == len(packets)
    assert not device._lock.locked() and not device._control_lock.locked()


async def test_music_recovery_uses_device_geometry_without_unsupported_colour(device, monkeypatch):
    notify(device, "aa40003c")
    state = replace(
        device.capture_effect_control_state(),
        mode="music",
        is_on=True,
        music_mode="piano_keys",
        music_color=(1, 2, 3),
        music_parameters={"key_count": 18, "gradient": False},
        music_palette=((12, 34, 56),) * 7,
        music_body=prepare_music_profile_writes(
            "H6099",
            "piano_keys",
            99,
            None,
            False,
            {"key_count": 18, "gradient": False},
            profile=device.profile,
            palette=((12, 34, 56),) * 7,
        )[-2][1]["_music_body"][1],
    )
    monkeypatch.setattr(device, "refresh_state", AsyncMock(return_value=True))
    assert not await device.async_restore_effect_control_state(state, overwritten_diy_code=None)
    packets = [call.args[1] for call in device._client.write_gatt_char.await_args_list]
    assert packets == [build_brightness(state.brightness_pct, "H6099")] + list(
        prepare_music_request(
            "H6099",
            "piano_keys",
            99,
            None,
            False,
            state.music_parameters,
            profile=device.profile,
            palette=state.music_palette,
        )
    )
    assert device.music_mode == "piano_keys" and device.music_sensitivity == 99
    assert device.music_color is None
    assert device.music_piano_key_count == 18 and device.music_piano_gradient is False
    assert device.music_palette == state.music_palette
    device.refresh_state.assert_awaited_once_with(
        expected_on=True,
        expected_brightness=100,
        expected_music_mode="piano_keys",
        expected_music_sensitivity=99,
    )
    assert "music_palette" not in device._expected_state
    assert device._field_revisions == {}


@pytest.mark.parametrize("missing_policy", [False, True])
async def test_video_recovery_restores_policy_and_border_only_when_requested(device, monkeypatch, missing_policy):
    notify(device, "aa0500010864010237")
    device.subordinate_21_version = "1.00.11"
    device.blank_screen = True
    device.black_border = True
    state = replace(
        device.capture_effect_control_state(),
        is_on=False,
        black_border=False,
        blank_screen_detection=None if missing_policy else 1,
        blank_screen_low_brightness_duration_seconds=300,
        blank_screen_same_tone_duration_seconds=600,
        video_restore_controls=("blank_screen", "blank_screen_policy", "black_border"),
    )
    blank, border = AsyncMock(), AsyncMock()
    monkeypatch.setattr(f"{M}.apply_blank_screen", blank)
    monkeypatch.setattr(f"{M}.apply_black_border", border)
    monkeypatch.setattr(device, "refresh_state", AsyncMock(return_value=True))

    async def transmit(_uuid, packet, **kwargs):
        if packet in (build_power(True, "H6099"), build_power(False, "H6099")):
            notify(device, "aa0101" if packet == build_power(True, "H6099") else "aa0100")
        elif packet == build_brightness(100, "H6099"):
            notify(device, "aa0464")

    device._client.write_gatt_char.side_effect = transmit
    assert await device.async_restore_effect_control_state(state, overwritten_diy_code=None) is not missing_policy
    packets = [call.args[1] for call in device._client.write_gatt_char.await_args_list]
    assert packets == [
        build_power(True, "H6099"),
        build_brightness(100, "H6099"),
        frame("330500010864010237"),
        build_power(False, "H6099"),
    ]
    assert device.refresh_state.await_args_list[-2].kwargs == {"expected_on": True, "expected_brightness": 100}
    assert device.refresh_state.await_args_list[-1].kwargs == {"expected_on": False}
    if missing_policy:
        blank.assert_not_awaited()
    else:
        blank.assert_awaited_once_with(device, True, policy=(1, 300, 600), write_guard=ANY)
    border.assert_awaited_once_with(device, False)
    blank.reset_mock()
    border.reset_mock()
    assert await device.async_restore_effect_control_state(
        replace(state, video_restore_controls=()),
        overwritten_diy_code=None,
    )
    blank.assert_not_awaited()
    border.assert_not_awaited()


@pytest.mark.parametrize("changed_at", [0, 1, 2, 3])
@pytest.mark.parametrize("count", [None, 14])
async def test_authored_music_rechecks_geometry_before_every_attempt(device, changed_at, count):
    notify(device, "aa40003c")
    state = replace(
        device.capture_effect_control_state(),
        mode="music",
        is_on=True,
        music_mode="piano_keys",
        music_parameters={"key_count": 18, "gradient": False},
        music_palette=((12, 34, 56),) * 7,
    )
    packets = prepare_music_request(
        "H6099",
        "piano_keys",
        99,
        None,
        False,
        state.music_parameters,
        profile=device.profile,
        palette=state.music_palette,
    )
    assert len(packets) == 4
    writes = prepare_music_profile_writes(
        "H6099",
        "piano_keys",
        99,
        None,
        False,
        state.music_parameters,
        profile=device.profile,
        palette=state.music_palette,
    )
    client = device._client

    def change_geometry():
        if client.write_gatt_char.await_count == changed_at:
            device.profile = replace(device.profile, physical_ic_count=count)

    async def reconnect():
        change_geometry()
        return client

    async def transmit(*args, **kwargs):
        change_geometry()

    device._ensure_connected.side_effect = reconnect
    client.write_gatt_char.side_effect = transmit
    with pytest.raises(ValueError, match="Physical IC count changed"):
        await device.async_write_music_sequence(writes, mode_code=52, physical_ic_count=60, intent=ControlIntent.USER)
    assert device.control_write_attempts == client.write_gatt_char.await_count == changed_at
    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == list(packets[:changed_at])
    assert device.music_mode == "off" and device._field_revisions == {}


@pytest.mark.parametrize("changed", [False, True])
async def test_authored_policy_recovery_checks_notifications_at_physical_boundary(device, monkeypatch, changed):
    notify(device, "aa0500010864010237")
    notify(device, "aaa90a0601020a007800")
    state = replace(
        device.capture_effect_control_state(),
        blank_screen_detection=1,
        blank_screen_low_brightness_duration_seconds=300,
        blank_screen_same_tone_duration_seconds=600,
        video_restore_controls=("blank_screen", "blank_screen_policy"),
    )
    assert type(state).from_dict(state.to_dict()) == state
    client = device._client

    async def reconnect():
        if changed:
            notify(device, "aaa90a0600011e00f000")
        return client

    device._ensure_connected.side_effect = reconnect
    monkeypatch.setattr(device, "refresh_state", AsyncMock(return_value=True))

    async def transmit(_uuid, packet, **kwargs):
        if packet in (build_power(True, "H6099"), build_power(False, "H6099")):
            notify(device, "aa0101" if packet == build_power(True, "H6099") else "aa0100")
        elif packet == build_brightness(100, "H6099"):
            notify(device, "aa0464")

    client.write_gatt_char.side_effect = transmit
    if changed:
        with pytest.raises(ValueError, match="policy changed before recovery write"):
            await device.async_restore_effect_control_state(state, overwritten_diy_code=None)
        assert device.control_write_attempts == 0 and device.blank_screen is False
        assert device.blank_screen_low_brightness_duration_seconds == 30
        assert device._expected_state == {}
    else:
        assert await device.async_restore_effect_control_state(state, overwritten_diy_code=None)
        assert client.write_gatt_char.await_args_list[0].args[1] == frame("33a90a0601012c015802")
        assert [call.args[1] for call in client.write_gatt_char.await_args_list[1:]] == [
            build_power(True, "H6099"),
            build_brightness(100, "H6099"),
            frame("330500010864010237"),
            build_power(False, "H6099"),
        ]
        assert tuple(getattr(device, field) for field in POLICY_FIELDS) == (True, 1, 300, 600)


@pytest.mark.parametrize("authored", [False, True])
async def test_studio_persists_policy_recovery_only_for_explicit_policy(device, monkeypatch, authored):
    notify(device, "aaa90a0601020a007800")

    async def refresh(**kwargs):
        if kwargs.get("refresh_all"):
            for prefix in ("aa0101", "aa0464", "aa0500010864010237"):
                notify(device, prefix)
        if kwargs.get("refresh_display_settings"):
            notify(device, "aaa90a0601020a007800")
        return True

    monkeypatch.setattr(device, "refresh_state", refresh)
    monkeypatch.setattr(device, "async_observe_effect", AsyncMock(return_value=True))
    content = VideoProfile("H6099", "movie", True, 50, False, 50, None, None, True)
    if authored:
        content = replace(
            content,
            blank_screen_detection=1,
            blank_screen_low_brightness_duration_seconds=300,
            blank_screen_same_tone_duration_seconds=600,
        )
    repository = EffectDeploymentRepository(InMemoryVersionedDocumentStore())
    await repository.async_load()
    result = await EffectDeploymentEngine(repository).async_apply_snapshot(
        device,
        LibraryItem.new("Video", content),
        config_entry_id="entry",
        updated_at="2026-09-15T00:00:00Z",
    )
    assert result.prior_state is not None
    assert ("blank_screen_policy" in result.prior_state.video_restore_controls) is authored
    assert "blank_screen" in result.prior_state.video_restore_controls


async def test_authored_policy_recovery_does_not_retry_over_a_filtered_notification(device, monkeypatch):
    notify(device, "aaa90a0601020a007800")
    state = replace(
        device.capture_effect_control_state(),
        blank_screen_detection=1,
        blank_screen_low_brightness_duration_seconds=300,
        blank_screen_same_tone_duration_seconds=600,
        video_restore_controls=("blank_screen", "blank_screen_policy"),
    )
    client = device._client
    monkeypatch.setattr(device, "_disconnect_locked", AsyncMock())

    async def transmit(*args, **kwargs):
        notify(device, "aaa90a0600011e00f000")
        raise BleakError("retry")

    client.write_gatt_char.side_effect = transmit
    with pytest.raises(ValueError, match="policy changed before recovery write"):
        await device.async_restore_effect_control_state(state, overwritten_diy_code=None)
    # The first policy attempt failed; power-off cleanup retries but must not mask the policy guard.
    assert device.control_write_attempts == client.write_gatt_char.await_count == 4
    assert [call.args[1] for call in client.write_gatt_char.await_args_list[1:]] == [build_power(False, "H6099")] * 3
    assert device._field_revisions["blank_screen"] == 1


@pytest.mark.parametrize("count", [60, 14])
async def test_ic_rediscovery_preserves_user_parameters_and_validates_new_bounds(device, count):
    notify(device, "aa40003c")
    device.music_piano_key_count = 30
    device.music_piano_gradient = True
    initialized = set(device._initialized_music_parameters)
    device._clear_client_state(device._client)
    notify(device, f"aa40{count:04x}")
    assert device.music_piano_key_count == 30 and device.music_piano_gradient
    assert device._initialized_music_parameters == initialized and device._field_revisions == {}
    parameters = capture_music_parameters(device, device.profile, "piano_keys")
    if count == 14:
        with pytest.raises(ValueError, match="key_count"):
            build_music_params(0x34, parameters, profile=device.profile)
    else:
        assert build_music_params(0x34, parameters, profile=device.profile)


@pytest.mark.parametrize("route", ["native", "preview", "recovery"])
@pytest.mark.parametrize("fresh", [False, True])
async def test_toggle_reads_fresh_external_policy_before_writing(device, monkeypatch, route, fresh):
    notify(device, "aaa90a0600020a007800")
    client = device._client
    saved = replace(device.capture_effect_control_state(), blank_screen=True)
    device._clear_client_state(client)
    device._client = client
    refresh = device.refresh_state

    async def immediate_refresh(**kwargs):
        return await refresh(**kwargs, timeout=0.01)

    monkeypatch.setattr(device, "refresh_state", immediate_refresh)

    async def transmit(_uuid, packet, **kwargs):
        if packet == build_blank_screen_query("H6099") and fresh:
            notify(device, "aaa90a0600011e00f000")
        elif packet[0] == 0x33:
            assert packet in (frame("33a90a0601011e00f000"), frame("330100"))
            assert device._control_arbiter.current_task_intent is intent

    client.write_gatt_char.side_effect = transmit

    async def preview(packet, *, write_guard=None, state_values=None, expected_values=None):
        await device.async_preview_write(
            packet, before_write=write_guard, state_values=state_values, expected_values=expected_values
        )

    intent = ControlIntent.PREVIEW if route == "preview" else ControlIntent.USER

    async def apply():
        async with async_control_intent(device, intent):
            if route == "recovery":
                # Verification is separate from the fresh policy read under test.
                async def recovery_refresh(**kwargs):
                    return await immediate_refresh(**kwargs) if "refresh_display_settings" in kwargs else True

                monkeypatch.setattr(device, "refresh_state", recovery_refresh)
                await device.async_restore_effect_control_state(saved, overwritten_diy_code=None)
            else:
                await apply_blank_screen(device, True, writer=preview if route == "preview" else None, verify=False)

    if fresh:
        await asyncio.wait_for(apply(), 1)
        assert device.blank_screen_detection == 1
        assert device.blank_screen_low_brightness_duration_seconds == 30
    else:
        with pytest.raises(ValueError, match="read freshly"):
            await asyncio.wait_for(apply(), 1)
        assert device.control_write_attempts == 0
    assert not device._lock.locked() and not device._control_lock.locked()


@pytest.mark.parametrize("change", ["filtered", "reconnect"])
async def test_toggle_guard_rejects_filtered_reply_or_reconnect(device, monkeypatch, change):
    client = device._client
    refresh = device.refresh_state

    async def immediate_refresh(**kwargs):
        return await refresh(**kwargs, timeout=0.01)

    monkeypatch.setattr(device, "refresh_state", immediate_refresh)

    async def transmit(_uuid, packet, **kwargs):
        if packet == build_blank_screen_query("H6099"):
            notify(device, "aaa90a0600020a007800")
        elif packet[0] == 0x33:
            notify(device, "aaa90a0600011e00f000")
            assert device.blank_screen_detection == 2  # The conflicting reply was filtered atomically.
            raise BleakError("retry")

    client.write_gatt_char.side_effect = transmit
    monkeypatch.setattr(device, "_disconnect_locked", AsyncMock())
    if change == "reconnect":

        def transform(packet):
            if packet[0] == 0x33:
                device._notification_token = object()
            return packet

        device.profile = replace(device.profile, outbound_transform=transform)
    with pytest.raises(ValueError, match="policy changed before write"):
        await apply_blank_screen(device, True)
    assert device.control_write_attempts == (1 if change == "filtered" else 0)
    assert device._field_revisions["blank_screen_detection"] == 1


@pytest.mark.parametrize("cached", [False, True])
@pytest.mark.parametrize("fresh", [False, True])
async def test_compiled_toggle_prepares_policy_before_any_control(device, monkeypatch, cached, fresh):
    if cached:
        notify(device, "aaa90a0600020a007800")
    before = device.capture_effect_control_state()
    client = device._client
    refresh = device.refresh_state
    queries = 0

    async def immediate_refresh(**kwargs):
        return await refresh(**kwargs, timeout=0.01)

    monkeypatch.setattr(device, "refresh_state", immediate_refresh)

    async def transmit(_uuid, packet, **kwargs):
        nonlocal queries
        if packet == build_blank_screen_query("H6099"):
            queries += 1
            if fresh:
                # External policy changes between preparation and the toggle.
                notify(device, "aaa90a0600011e00f000" if queries == 1 else "aaa90a06000228002c01")
        elif packet[0] == 0x33:
            assert queries >= 1 and fresh

    client.write_gatt_char.side_effect = transmit
    compiled = compile_video_profile(
        LibraryItem.new("Toggle", VideoProfile("H6099", "movie", True, 70, False, 40, None, None, True)), "H6099"
    )

    async def apply():
        async with async_control_intent(device, ControlIntent.PREVIEW):
            await async_apply_compiled_profile(device, compiled, verify=False)

    if fresh:
        await asyncio.wait_for(apply(), 1)
        controls = [call.args[1] for call in client.write_gatt_char.await_args_list if call.args[1][0] == 0x33]
        assert len(controls) == device.control_write_attempts == 3
        assert controls[-1] == frame("33a90a06010228002c01")
        assert queries == 2
    else:
        with pytest.raises(ValueError, match="read freshly"):
            await asyncio.wait_for(apply(), 1)
        assert device.control_write_attempts == 0
        assert not any(call.args[1][0] == 0x33 for call in client.write_gatt_char.await_args_list)
        assert device.capture_effect_control_state() == before
        assert not device._expected_state
    assert not device._lock.locked() and not device._control_lock.locked()
