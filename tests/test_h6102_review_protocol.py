"""Effective-profile and independent register boundaries through the real coordinator."""

import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, ModelProfile, ReadDomain, get_profile
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_status import (
    ParsedMode,
    decode_status_frame,
    decode_status_frame_result,
    parse_color_mode,
    status_is_authorized,
)
from custom_components.ha_govee_led_ble.firmware_version import FirmwareVersion
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    ProtocolParseRejection,
    build_boolean_control,
    build_boolean_control_query,
    build_h6199_control,
    require_profile_packet,
)
from custom_components.ha_govee_led_ble.h6102_capabilities import resolve_h6102_capabilities
from custom_components.ha_govee_led_ble.transport import xor_checksum
from custom_components.ha_govee_led_ble.video_applicability import identity_version


def frame(prefix: str) -> bytes:
    body = bytes.fromhex(prefix).ljust(19, b"\x00")
    assert len(body) == 19
    return body + bytes([xor_checksum(body)])


def test_status_semantics_use_effective_grammar_roster_and_bounds() -> None:
    profile = ModelProfile(
        "Synthetic effective status",
        command_grammar="H617A",
        status_grammar="H6102",
        music_modes=("bloom",),
        min_color_temp_kelvin=3000,
        max_color_temp_kelvin=4500,
    )
    packet = frame("aa05133032")
    assert decode_status_frame_result(packet, "H9908").rejection is ProtocolParseRejection.UNSUPPORTED_MODEL
    decoded = decode_status_frame(packet, "H9908", profile=profile)
    assert decoded is not None
    assert parse_color_mode(decoded.generated, "H9908", profile=profile).music_mode == "bloom"
    with pytest.raises(ValueError, match="unsupported"):
        parse_color_mode(decoded.generated, "H9908", profile=replace(profile, music_modes=()))
    static = decode_status_frame(frame("aa0515010fa0"), "H9908", profile=profile)
    assert static is not None
    assert parse_color_mode(static.generated, "H9908", profile=profile).color_temp_kelvin == 4000
    with pytest.raises(ValueError, match="Kelvin"):
        parse_color_mode(static.generated, "H9908", profile=replace(profile, max_color_temp_kelvin=3500))


async def test_real_coordinator_uses_effective_status_not_static_sku(hass, monkeypatch) -> None:
    monkeypatch.setitem(MODEL_PROFILES, "H9908", ModelProfile("Synthetic registry", command_grammar="H6199"))
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H9908", configuration_url=None)
    coordinator.profile = ModelProfile(
        "Synthetic effective",
        command_grammar="H617A",
        status_grammar="H6102",
        read_domains=frozenset({ReadDomain.COLOUR_MODE}),
        music_modes=("bloom",),
    )
    coordinator._notify_callback(None, bytearray(frame("aa05133032")))
    assert coordinator.color_mode is ParsedMode.MUSIC and coordinator.music_mode == "bloom"
    revision = coordinator._field_revisions["color_mode"]
    coordinator.profile = replace(coordinator.profile, music_modes=())
    coordinator._notify_callback(None, bytearray(frame("aa05133032")))
    assert coordinator._field_revisions["color_mode"] == revision


async def test_real_coordinator_boolean_read_is_independent_of_basic_domains(hass, monkeypatch) -> None:
    monkeypatch.setitem(MODEL_PROFILES, "H9908", ModelProfile("Synthetic registry"))
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H9908", configuration_url=None)
    coordinator.profile = ModelProfile(
        "Synthetic boolean only",
        command_grammar="H617A",
        status_grammar="H6102",
        command_operations=frozenset({"power", "brightness"}),
        boolean_controls=frozenset({"gradual"}),
    )
    query = build_boolean_control_query("gradual", "H9908", profile=coordinator.profile)
    decoded = decode_status_frame(frame("aaa301"), "H9908", profile=coordinator.profile)
    assert decoded is not None and status_is_authorized(decoded, coordinator.profile)

    async def transmit(_uuid, packet, **kwargs):
        if packet == query:
            coordinator._notify_callback(None, bytearray(frame("aaa301")))

    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=transmit))
    coordinator._client = client
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(coordinator, "_renew_foreground_lease", lambda: None)
    await coordinator.async_set_boolean_control("gradual", True)
    assert coordinator.boolean_control_state == {"gradual": True}
    assert coordinator._field_revisions["boolean_gradual"] == 1


async def test_real_coordinator_ack_and_restricted_writer_use_effective_profile(hass, monkeypatch) -> None:
    monkeypatch.setitem(MODEL_PROFILES, "H9908", ModelProfile("Synthetic registry"))
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H9908", configuration_url=None)
    coordinator.profile = ModelProfile("Effective ACK", command_grammar="H617A", status_grammar="H6102")
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    coordinator._client = client
    future = asyncio.get_running_loop().create_future()
    coordinator._upload_ack = (client, None, coordinator._profile_generation, 4, future)
    coordinator._notify_callback(None, bytearray(frame("a30400")))
    assert future.done() and future.result() is True
    packet = build_boolean_control("limit", True, "H6102")
    with pytest.raises(ValueError, match="boolean control"):
        await coordinator._async_write_packet(client, packet)
    client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("operations", [None, frozenset({"power", "brightness", "limit", "multi_effect"})])
def test_removed_booleans_cannot_bypass_current_authorization(operations) -> None:
    original = get_profile("H6102")
    narrowed = replace(original, command_operations=operations, boolean_controls=frozenset())
    for control, opcode in (("limit", "0e"), ("gradual", "a3")):
        for packet in (
            build_boolean_control(control, True, "H6102", profile=original),
            build_boolean_control_query(control, "H6102", profile=original),
        ):
            with pytest.raises(ValueError, match="boolean control"):
                require_profile_packet(packet, narrowed)
        decoded = decode_status_frame(frame(f"aa{opcode}01"), profile=original)
        assert decoded is not None and not status_is_authorized(decoded, narrowed)
    # Existing raw H617A register and H6199's distinct native gradient remain valid.
    require_profile_packet(frame("33a300"), get_profile("H617A"))
    require_profile_packet(build_h6199_control("gradient", 1), get_profile("H6199"))


@pytest.mark.parametrize("value", ["3.02.02", "3.2.2", "1.3", "03.02.02", "3.002.02", None, True])
def test_one_version_policy_for_qualification_and_identity(value) -> None:
    parsed = FirmwareVersion.parse(value)
    assert (parsed is not None) == (identity_version(value) is not None)
    if parsed is not None:
        assert parsed.identity_number() == identity_version(value)
    resolution = resolve_h6102_capabilities(value, "configured", hardware="3.01.01", pact_type=10, pact_code=1)
    assert ("bloom" in resolution.profile.music_modes) is (parsed is not None)


def test_legacy_short_config_is_unqualified_until_reentered_or_observed(hass) -> None:
    coordinator = GoveeBLECoordinator(
        hass,
        "11:22:33:44:55:66",
        "H6102",
        configuration_url=None,
        h6102_firmware="3.2.2",
        h6102_firmware_source="configured",
        h6102_pact="10/1",
    )
    coordinator.hw_version = "3.01.01"
    coordinator._resolve_device_profile()
    assert coordinator._configured_h6102_firmware == "3.2.2"
    assert "bloom" not in coordinator.profile.music_modes
    coordinator.fw_version = "3.2.2"
    assert coordinator._identity_field_incomplete("fw_version")
    coordinator.fw_version = "3.02.02"
    coordinator._resolve_device_profile()
    assert not coordinator._identity_field_incomplete("fw_version")
    assert "bloom" in coordinator.profile.music_modes
