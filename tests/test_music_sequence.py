"""Music retries restart the complete upload on a freshly negotiated connection."""

from dataclasses import replace
from unittest.mock import AsyncMock, patch

import pytest
from bleak import BleakError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.effect_compiler import compile_application
from custom_components.ha_govee_led_ble.effect_deployments import ObservationConfidence
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem, MusicProfile
from custom_components.ha_govee_led_ble.effect_runtime import async_apply_compiled_profile, compiled_observation
from custom_components.ha_govee_led_ble.generated_protocol_adapter import build_brightness, music_default_palette
from custom_components.ha_govee_led_ble.govee_encryption import (
    KEY_HANDSHAKE,
    GoveeCryptoError,
    parse_v1_handshake,
    parse_v2_handshake,
    parse_wire,
    unseal,
    v1_transform,
)
from custom_components.ha_govee_led_ble.music_commands import prepare_music_body_writes, prepare_music_profile_writes
from custom_components.ha_govee_led_ble.music_semantics import music_variant
from tests.test_govee_encryption import client, v1_reply, v2_reply


@pytest.mark.parametrize("route", ["native", "studio", "recovery"])
@pytest.mark.parametrize("version", [0, 1, 2])
@pytest.mark.parametrize("reject_reconnect", [False, True])
async def test_bloom_last_fragment_failure_restarts_all_packets(hass, route, version, reject_reconnect):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6099", configuration_url=None)
    transformed = []
    coordinator.profile = replace(
        coordinator.profile,
        read_domains=frozenset(),
        setup_required_read_domains=frozenset(),
        outbound_transform=lambda packet: transformed.append(packet) or b"\xfe" + packet,
    )
    coordinator.music_sensitivity = 42
    coordinator.music_calm = route == "native"
    snapshot = coordinator._pre_mode_snapshot
    compiled = compile_application(LibraryItem.new("Bloom", MusicProfile("H6099", "bloom", 42, calm=True)), "H6099")
    writes = prepare_music_profile_writes("H6099", "bloom", 42, None, True, {})
    packets = list(compiled.packets)
    assert [packet[0] for packet in packets] == [0x33, 0xA3, 0xA3, 0x33]
    prior = replace(
        coordinator.capture_effect_control_state(),
        mode="music",
        is_on=True,
        music_mode="bloom",
        music_calm=True,
        music_palette=music_default_palette(music_variant(coordinator.profile, 0x30)),
        music_body=writes[-2][1]["_music_body"][1],
    )
    prefix = [build_brightness(prior.brightness_pct, "H6099")] if route == "recovery" else []
    if route == "recovery":
        writes = prepare_music_body_writes("H6099", "bloom", 42, prior.music_body, profile=coordinator.profile)
    devices, attempts, host_ivs = [], [], []
    expected_state = {"music_mode": "off", "music_calm": route == "native"}

    async def connect(*args, **kwargs):
        connection = len(devices)
        if connection:
            expected_state["_music_palette"] = None
        device = client(bytes((1, version)) if version else None)
        devices.append(device)
        attempts.append([])
        key = bytes((connection + 1,)) * 16
        reply = v2_reply(bytes((connection + 1,)) * 8)
        device_key = parse_v2_handshake(reply)[1]
        phase, host_iv = 0, None
        if reject_reconnect and connection == 1:
            device.read_gatt_char.side_effect = GoveeCryptoError("invalid_marker")
            if not version:
                raise BleakError("reconnect unavailable")

        async def write(_uuid, frame, **kwargs):
            nonlocal phase, host_iv
            phase += 1
            if version == 1 and phase <= 2:
                assert parse_v1_handshake(frame).opcode == phase
                device.start_notify.call_args.args[1](None, bytearray(v1_reply(phase, key)))
                return
            if version == 2 and phase == 1:
                parsed = parse_wire("V2Request", frame)
                host_iv = AESGCM(KEY_HANDSHAKE).decrypt(parsed.nonce, parsed.sealed, frame[:16])
                host_ivs.append(host_iv)
                device.start_notify.call_args.args[1](None, bytearray(reply))
                return
            index = len(attempts[connection])
            plain = frame
            if version == 1:
                plain = v1_transform(frame, key, encrypt=False)
                assert coordinator._encryption._key == key
            elif version == 2:
                counter, plain = unseal(frame, host_iv, device_key)
                assert counter == 2 + index
            if version:
                assert frame != plain and frame not in packets
            if connection == 0 and prefix:
                if index == 0:
                    assert plain == b"\xfe" + prefix[0]
                    attempts[connection].append(plain)
                    return
                index -= 1
            assert plain == b"\xfe" + packets[index]
            expected_state.update(
                {
                    key: value
                    for key, value in writes[index][1].items()
                    if key not in {"_music_body", "_music_parameter_keys"}
                }
            )
            assert coordinator._music_body is None
            assert all(getattr(coordinator, field) == value for field, value in expected_state.items())
            if index < 3:
                assert coordinator._pre_mode_snapshot is snapshot
            else:
                assert coordinator._pre_mode_snapshot.rgb == (10, 20, 30)
            attempts[connection].append(plain)
            if connection == 0 and index == 2:
                raise BleakError("last companion fragment failed")
            if index == 2:
                coordinator.rgb_color = (10, 20, 30)

        device.write_gatt_char.side_effect = write
        return device

    async def apply():
        if route == "native":
            await coordinator.async_select_music_slug("bloom")
        elif route == "studio":
            await async_apply_compiled_profile(coordinator, compiled)
        else:
            await coordinator.async_restore_effect_control_state(prior, overwritten_diy_code=None)

    with (
        patch("custom_components.ha_govee_led_ble.coordinator.async_establish_ble_connection", side_effect=connect),
        patch.object(coordinator, "_send_identity_queries", AsyncMock()),
    ):
        try:
            if reject_reconnect:
                # Every further connection must fail, never fall back to plaintext or a fragment retry.
                original_connect = connect

                async def fail_after_first(*args, **kwargs):
                    if len(devices) > 1:
                        raise BleakError("reconnect unavailable")
                    return await original_connect(*args, **kwargs)

                with patch(
                    "custom_components.ha_govee_led_ble.coordinator.async_establish_ble_connection",
                    side_effect=fail_after_first,
                ):
                    with pytest.raises(GoveeCryptoError if version else BleakError):
                        await apply()
                assert attempts == [[b"\xfe" + p for p in prefix + packets[:3]], []]
                assert coordinator.music_mode == "off" and coordinator._pre_mode_snapshot is snapshot
            else:
                await apply()
                assert attempts == [[b"\xfe" + p for p in prefix + packets[:3]], [b"\xfe" + p for p in packets]]
                assert transformed == prefix + packets[:3] + packets
                assert coordinator.music_body == prior.music_body
                assert coordinator._encryption.active is bool(version)
                if version == 2:
                    assert host_ivs[0] != host_ivs[1]
            assert coordinator._field_revisions == coordinator._domain_revisions == {}
            assert "music_calm" not in coordinator._expected_state
        finally:
            await coordinator.disconnect()


@pytest.mark.parametrize("mode", ["bloom", "shiny", "piano_keys", "rhythm", "rolling"])
def test_music_observation_only_claims_readable_settings(mode):
    from custom_components.ha_govee_led_ble.const import get_profile

    profile = replace(get_profile("H6099"), physical_ic_count=60)
    compiled = compile_application(LibraryItem.new("Music", MusicProfile("H6099", mode, 42)), "H6099", profile=profile)
    expectations, confidence = compiled_observation(compiled, profile=profile)
    assert expectations["music_mode"] == mode and expectations["music_sensitivity"] == 42
    if mode in {"bloom", "shiny", "piano_keys"}:
        assert confidence is ObservationConfidence.MODE_MATCH
        assert expectations == {"is_on": True, "music_mode": mode, "music_sensitivity": 42}
    else:
        assert confidence is ObservationConfidence.SETTINGS_MATCH
        assert expectations["music_color"] is None
        assert ("music_calm" in expectations) is (mode == "rhythm")
