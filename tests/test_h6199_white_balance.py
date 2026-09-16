"""H6199 register preservation, using the captured same-gain auto/manual replies."""

from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.effect_compiler import compile_video_profile
from custom_components.ha_govee_led_ble.effect_deployments import EffectDeploymentRepository, PriorControlState
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem, VideoProfile
from custom_components.ha_govee_led_ble.effect_persistence_validation import EffectStorageError
from custom_components.ha_govee_led_ble.effect_runtime import EffectDeploymentEngine, compiled_observation
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_brightness,
    build_power,
    build_white_balance,
    parse_command,
)
from custom_components.ha_govee_led_ble.native_profile_controls import apply_white_balance
from custom_components.ha_govee_led_ble.scenes import MODEL_SCENES
from tests.storage_test_double import InMemoryVersionedDocumentStore
from tests.test_h6099 import frame
from tests.test_h6199_capabilities import QUALIFIED

AUTO = bytes.fromhex("aaa9000601100300150500000000000000000007")
MANUAL = bytes.fromhex("aaa9000601100301150500000000000000000006")


@pytest.fixture
def coordinator(hass):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url="test")
    vars(coordinator).update(QUALIFIED)
    return coordinator


def test_captured_modes_and_defaults_survive_persistence(coordinator):
    snapshots = []
    for reply, flag in ((AUTO, 0), (MANUAL, 1)):
        coordinator._notify_callback(None, bytearray(reply))
        state = coordinator.capture_effect_control_state()
        assert (state.white_balance_flag, state.white_balance_red, state.white_balance_blue) == (flag, 21, 5)
        assert (
            state.white_balance_default_flag,
            state.white_balance_default_red,
            state.white_balance_default_blue,
        ) == (1, 16, 3)
        assert PriorControlState.from_dict(state.to_dict()) == state
        snapshots.append(state)
    assert snapshots[0] != snapshots[1]
    assert coordinator._field_revisions["white_balance_flag"] == coordinator._field_revisions["white_balance_red"]


@pytest.mark.parametrize("flag", [0, 1])
async def test_recovery_writes_original_flag_even_with_equal_gains(coordinator, monkeypatch, flag):
    scene = MODEL_SCENES["H6199"]["candlelight"]
    coordinator._notify_callback(None, bytearray(frame(f"aa0504{scene.code & 255:02x}{scene.code >> 8:02x}")))
    coordinator._notify_callback(None, bytearray(AUTO if flag == 0 else MANUAL))
    state = PriorControlState.from_dict(coordinator.capture_effect_control_state().to_dict())
    state = replace(state, video_restore_controls=("white_balance",))
    coordinator._notify_callback(None, bytearray(MANUAL if flag == 0 else AUTO))
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    coordinator._client = client
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))

    async def respond(**kwargs):
        if kwargs.get("query_white_balance"):
            coordinator._notify_callback(None, bytearray(AUTO if flag == 0 else MANUAL))
        if kwargs.get("query_power"):
            coordinator._notify_callback(None, bytearray(reply_power))
        if kwargs.get("query_brightness"):
            coordinator._notify_callback(None, bytearray(frame("aa0464")))
        if kwargs.get("query_color_mode"):
            coordinator._notify_callback(None, bytearray(frame(f"aa0504{scene.code & 255:02x}{scene.code >> 8:02x}")))
        return True

    reply_power = frame("aa0100")

    async def transmit(_uuid, packet, **kwargs):
        nonlocal reply_power
        if packet in (build_power(True, "H6199"), build_power(False, "H6199")):
            reply_power = frame("aa0101" if packet == build_power(True, "H6199") else "aa0100")

    client.write_gatt_char.side_effect = transmit
    monkeypatch.setattr(coordinator, "_send_state_queries", respond)
    assert await coordinator.async_restore_effect_control_state(state, overwritten_diy_code=None)
    assert client.write_gatt_char.await_args_list[0].args[1] == build_white_balance(21, 5, "H6199", flag=flag)
    assert coordinator.capture_effect_control_state().white_balance_flag == flag
    assert coordinator.white_balance_default_red == 16
    packets = [call.args[1] for call in client.write_gatt_char.await_args_list]
    assert build_brightness(100, "H6199") in packets and packets[-1] == build_power(False, "H6199")


@pytest.mark.parametrize("same_gains", [True, False])
async def test_legacy_missing_flag_never_infers_original_mode(coordinator, monkeypatch, same_gains):
    coordinator._notify_callback(None, bytearray(AUTO))
    raw = coordinator.capture_effect_control_state().to_dict()
    for field in (
        "white_balance_flag",
        "white_balance_default_flag",
        "white_balance_default_red",
        "white_balance_default_blue",
    ):
        raw.pop(field)
    legacy = PriorControlState.from_dict(raw)
    assert legacy.white_balance_flag is None
    assert legacy.white_balance_default_flag is None
    coordinator._notify_callback(None, bytearray(MANUAL))
    if not same_gains:
        coordinator.white_balance_red = 25
    send = AsyncMock()
    monkeypatch.setattr(coordinator, "send_command", send)
    monkeypatch.setattr(coordinator, "refresh_state", AsyncMock(return_value=True))
    assert not await coordinator.async_restore_effect_control_state(legacy, overwritten_diy_code=None)
    assert all(parse_command(call.args[0], "H6199").opcode.name != "display_setting" for call in send.await_args_list)
    assert legacy.white_balance_flag is None
    assert coordinator.white_balance_flag == 1


async def test_manual_authoring_and_preview_verification_include_flag(coordinator):
    coordinator._notify_callback(None, bytearray(AUTO))
    revisions = dict(coordinator._field_revisions)
    writer = AsyncMock()
    await apply_white_balance(coordinator, (21, 5), writer=writer, verify=False)
    assert writer.await_args.args[0] == build_white_balance(21, 5, "H6199", flag=1)
    assert writer.await_args.kwargs["state_values"]["white_balance_flag"] == 1
    assert coordinator._field_revisions == revisions
    compiled = compile_video_profile(
        LibraryItem.new("Manual", VideoProfile("H6199", "movie", None, None, None, None, 17, None, None)), "H6199"
    )
    expectations, _ = compiled_observation(compiled)
    assert expectations["white_balance_flag"] == 1


async def test_same_gain_wrong_flag_is_not_fresh_confirmation(coordinator, monkeypatch):
    client = MagicMock(is_connected=True)
    coordinator._client = client
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))

    async def respond(**kwargs):
        coordinator._notify_callback(None, bytearray(AUTO))
        return True

    monkeypatch.setattr(coordinator, "_send_state_queries", respond)
    assert not await coordinator.refresh_state(
        expected_white_balance=(21, 5), expected_white_balance_flag=1, timeout=0.01
    )
    assert await coordinator.refresh_state(expected_white_balance=(21, 5), expected_white_balance_flag=0, timeout=0.01)


async def test_reset_uses_fresh_device_defaults_not_calibration_neutral(coordinator, monkeypatch):
    reply = frame("aaa90006001b09011505")

    async def refresh(**kwargs):
        coordinator._notify_callback(None, bytearray(reply))
        return True

    monkeypatch.setattr(coordinator, "refresh_state", refresh)
    writer = AsyncMock()
    await apply_white_balance(coordinator, None, writer=writer, verify=False)
    assert writer.await_args.args[0] == build_white_balance(27, 9, "H6199", flag=0)
    guard = writer.await_args.kwargs["write_guard"]
    guard()
    coordinator.white_balance_default_flag = 1
    with pytest.raises(ValueError, match="defaults changed"):
        guard()


async def test_reset_without_fresh_defaults_fails_before_write(coordinator, monkeypatch):
    coordinator._notify_callback(None, bytearray(AUTO))
    monkeypatch.setattr(coordinator, "refresh_state", AsyncMock(return_value=True))
    writer = AsyncMock()
    with pytest.raises(ValueError, match="defaults have not been read freshly"):
        await apply_white_balance(coordinator, None, writer=writer)
    writer.assert_not_awaited()


@pytest.mark.parametrize(
    "field",
    ["white_balance_flag", "white_balance_default_flag", "white_balance_default_red", "white_balance_default_blue"],
)
@pytest.mark.parametrize("value", [True, -1, 256, "1"])
def test_persisted_wb_fields_validate_bytes(coordinator, field, value):
    raw = coordinator.capture_effect_control_state().to_dict()
    raw[field] = value
    with pytest.raises(EffectStorageError):
        PriorControlState.from_dict(raw)


def test_unknown_wire_flags_preserved_but_not_writable(coordinator):
    coordinator._notify_callback(None, bytearray(frame("aaa90006021003ff1505")))
    state = coordinator.capture_effect_control_state()
    assert state.white_balance_flag == 255
    assert state.white_balance_default_flag == 2
    assert PriorControlState.from_dict(state.to_dict()) == state
    with pytest.raises(ValueError, match="known auto/manual flag"):
        build_white_balance(21, 5, "H6199", flag=255)


@pytest.mark.parametrize(
    "missing",
    ["white_balance_flag", "white_balance_default_flag", "white_balance_default_red", "white_balance_default_blue"],
)
async def test_deployment_requires_complete_prior_wb_register(coordinator, monkeypatch, missing):
    coordinator._notify_callback(None, bytearray(AUTO))
    setattr(coordinator, missing, None)

    async def refresh(**kwargs):
        if kwargs.get("refresh_all"):
            for prefix in ("aa0101", "aa0464", "aa05000100320032"):
                coordinator._notify_callback(None, bytearray(frame(prefix)))
        return True

    monkeypatch.setattr(coordinator, "refresh_state", refresh)
    engine = EffectDeploymentEngine(EffectDeploymentRepository(InMemoryVersionedDocumentStore()))
    compiled = compile_video_profile(
        LibraryItem.new("Manual", VideoProfile("H6199", "movie", None, None, None, None, 17, None, None)), "H6199"
    )
    with pytest.raises(RuntimeError, match="current video settings are incomplete"):
        await engine._async_prepare_prior_state(coordinator, compiled)


async def test_recovery_does_not_install_or_claim_changed_device_defaults(coordinator, monkeypatch):
    coordinator._notify_callback(None, bytearray(AUTO))
    original = coordinator.capture_effect_control_state()
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    coordinator._client = client
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))

    async def respond(**kwargs):
        if kwargs.get("query_white_balance"):
            coordinator._notify_callback(None, bytearray(frame("aaa90006001b09001505")))
        if kwargs.get("query_power"):
            coordinator._notify_callback(None, bytearray(frame("aa0100")))
        return True

    monkeypatch.setattr(coordinator, "_send_state_queries", respond)
    assert not await coordinator.async_restore_effect_control_state(original, overwritten_diy_code=None)
    assert coordinator.white_balance_default_flag == 0
    assert coordinator.white_balance_default_red == 27
    assert coordinator.white_balance_default_blue == 9
    assert original.white_balance_default_red == 16
