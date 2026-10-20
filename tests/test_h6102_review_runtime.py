"""H6102 regressions through real reconnect, notification and recovery paths."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak import BleakError
from homeassistant.config_entries import current_entry
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_govee_led_ble.const import DOMAIN, ReadDomain
from custom_components.ha_govee_led_ble.control_arbiter import ControlIntent
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.effect_deployments import (
    DeploymentPhase,
    EffectDeploymentRepository,
    PriorControlState,
)
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem, SingleEffect
from custom_components.ha_govee_led_ble.effect_persistence_validation import EffectStorageError
from custom_components.ha_govee_led_ble.effect_runtime import EffectDeploymentEngine
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_scene_activation,
    decode_wire_brightness,
    encode_wire_brightness,
)
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.light_commands import (
    build_color_rgb,
    build_color_temp,
    kelvin_to_rgb,
    parse_static_write,
)
from custom_components.ha_govee_led_ble.music_commands import prepare_music_profile_writes
from tests.storage_test_double import InMemoryVersionedDocumentStore
from tests.test_h6199_native_controls import frame


@pytest.fixture
async def radio(hass, monkeypatch):
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    with current_entry.set(entry):
        c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6102", configuration_url="studio", h6102_pact="10/1")
    state = {
        "fw": "3.02.02",
        "hw": "3.02.01",
        "mode": "15011194",
        "kelvin": 4500,
        "gradual": True,
        "on": True,
        "brightness": 50,
        "register_brightness": False,
        "fault_brightness": False,
        "brightness_reply_override": None,
        "accept_kelvin": True,
        "register_reply": True,
        "colours": [kelvin_to_rgb(4500)] * 15,
        "relative": [100] * 15,
        "accept_rgb_kelvin": True,
        "fault_upload": False,
        "pact_on_connect": None,
        "corrupt_kelvin_rgb": False,
    }
    packets, clients, timers = [], [], []

    async def connect(*args, **kwargs):
        if state["pact_on_connect"] is not None:
            from tests.test_h6199_pact1 import advertise

            advertise(c, state["pact_on_connect"])
        client = MagicMock(is_connected=True)
        clients.append(client)
        receive = None

        async def subscribe(_uuid, callback):
            nonlocal receive
            receive = callback

        async def transmit(_uuid, packet, **kw):
            packets.append(packet)
            reply = None
            if packet[:2] == bytes.fromhex("aa06") and state["fw"]:
                reply = "aa06" + state["fw"].encode().hex()
            elif packet[:2] == bytes.fromhex("aa07") and state["hw"]:
                reply = "aa0703" + state["hw"].encode().hex()
            elif packet[:2] == bytes.fromhex("aa01"):
                reply = "aa01" + ("01" if state["on"] else "00")
            elif packet[:2] == bytes.fromhex("aa04"):
                value = (
                    encode_wire_brightness(state["brightness"], (20, 254))
                    if state["register_brightness"]
                    else state["brightness"]
                )
                if state["brightness_reply_override"] is not None:
                    value = state["brightness_reply_override"]
                reply = "aa04" + bytes([value]).hex()
            elif packet[:2] == bytes.fromhex("aa05"):
                reply = "aa05" + state["mode"]
            elif packet[:2] == bytes.fromhex("aaa5"):
                body = [packet[2]]
                for index in range((packet[2] - 1) * 3, packet[2] * 3):
                    body.extend([state["relative"][index], *state["colours"][index]])
                reply = "aaa5" + bytes(body).hex()
            elif packet[:2] == bytes.fromhex("aaa3") and state["register_reply"]:
                reply = "aaa3" + ("01" if state["gradual"] else "00")
            elif packet[:2] == bytes.fromhex("aa0e"):
                reply = "aa0e00"
            elif packet[:2] == bytes.fromhex("3301"):
                state["on"] = bool(packet[2])
            elif packet[:2] == bytes.fromhex("3304"):
                if state["fault_brightness"]:
                    raise BleakError("brightness write failed")
                state["brightness"] = (
                    decode_wire_brightness(packet[2], (20, 254)) if state["register_brightness"] else packet[2]
                )
            elif packet[:2] == bytes.fromhex("33a3"):
                state["gradual"] = bool(packet[2])
                state["mode"] = "15" + bytes([packet[2]]).hex() + state["kelvin"].to_bytes(2, "big").hex()
            elif packet[:3] == bytes.fromhex("33050a"):
                state["mode"] = "0a" + packet[3:5].hex()
            elif packet[:3] == bytes.fromhex("330504"):
                state["mode"] = "04" + packet[3:5].hex()
            elif packet[0] == 0xA3 and packet[1] == 0xFF:
                reply = "a30400"
            if packet[0] == 0xA3 and state["fault_upload"]:
                raise RuntimeError("failed body upload")
            static = parse_static_write(packet, c.model, profile=c.profile)
            if static and static.kelvin is not None and state["accept_kelvin"]:
                state["kelvin"] = static.kelvin
                state["mode"] = "15" + bytes([int(state["gradual"])]).hex() + static.kelvin.to_bytes(2, "big").hex()
                state["colours"] = [static.kelvin_companion_rgb] * 15
                if state["corrupt_kelvin_rgb"]:
                    state["colours"][-1] = (1, 2, 3)
            if static and static.rgb is not None:
                for index in range(15):
                    if static.segment_mask & (1 << index):
                        state["colours"][index] = static.rgb
                if state["accept_rgb_kelvin"]:
                    state["kelvin"] = 0
                    state["mode"] = "15" + bytes([int(state["gradual"])]).hex() + "0000"
            if static and static.brightness_pct is not None:
                for index in range(15):
                    if static.segment_mask & (1 << index):
                        state["relative"][index] = static.brightness_pct
            if reply is not None:
                timers.append(asyncio.get_running_loop().call_later(0.001, receive, None, bytearray(frame(reply))))

        async def disconnect():
            client.is_connected = False
            kwargs["disconnected_callback"](client)

        client.start_notify = AsyncMock(side_effect=subscribe)
        client.write_gatt_char = AsyncMock(side_effect=transmit)
        client.disconnect = AsyncMock(side_effect=disconnect)
        return client

    monkeypatch.setattr("custom_components.ha_govee_led_ble.coordinator.async_establish_ble_connection", connect)
    monkeypatch.setattr("custom_components.ha_govee_led_ble.coordinator.IDENTITY_QUERY_TIMEOUT", 0.03)
    monkeypatch.setattr(c, "_start_keep_alive", lambda: None)
    try:
        yield c, state, packets, clients
    finally:
        await c.disconnect()
        for timer in timers:
            timer.cancel()


@pytest.mark.parametrize("method", ["async_apply_saved", "async_apply_snapshot"])
async def test_apply_after_idle_reconnect_rebuilds_fresh_baselines(radio, method):
    c, state, packets, clients = radio
    assert await c.refresh_state(refresh_all=True)
    await c.disconnect()
    packets.clear()
    repository = EffectDeploymentRepository(InMemoryVersionedDocumentStore())
    await repository.async_load()
    record = await getattr(EffectDeploymentEngine(repository), method)(
        c,
        LibraryItem.new("Single", SingleEffect(0, 0, 50, ((1, 2, 3),))),
        config_entry_id="entry",
        updated_at="2026-09-17T00:00:00Z",
    )
    assert record.phase is DeploymentPhase.CONFIRMED
    assert len(clients) == 2
    assert record.prior_state.color_temp_kelvin == 4500
    assert record.prior_state.static_gradual is True


@pytest.mark.parametrize("missing", ["fw", "hw"])
async def test_music_reconnect_revocation_precedes_power_and_upload(radio, missing):
    c, state, packets, _ = radio
    assert await c.refresh_state(refresh_all=True)
    writes = prepare_music_profile_writes(c.model, "bloom", 50, None, False, {}, profile=c.profile)
    await c.disconnect()
    state[missing] = None
    packets.clear()
    attempts = c.control_write_attempts
    with pytest.raises(ValueError, match="music mode"):
        await c.async_write_music_sequence(writes, mode_code=0x30, physical_ic_count=None, intent=ControlIntent.USER)
    assert c.control_write_attempts == attempts
    assert all(packet[0] == 0xAA for packet in packets)


async def test_music_retry_rechecks_revision_before_second_control_attempt(radio):
    c, state, packets, clients = radio
    assert await c.refresh_state(refresh_all=True)
    writes = prepare_music_profile_writes(c.model, "bloom", 50, None, False, {}, profile=c.profile)
    original = clients[-1].write_gatt_char.side_effect
    attempted = []

    async def fail(_uuid, packet, **kwargs):
        if packet[0] == 0x33:
            attempted.append(packet)
            state["hw"] = None
            raise BleakError("retry connection")
        await original(_uuid, packet, **kwargs)

    clients[-1].write_gatt_char.side_effect = fail
    packets.clear()
    with pytest.raises(ValueError, match="music mode"):
        await c.async_write_music_sequence(writes, mode_code=0x30, physical_ic_count=None, intent=ControlIntent.USER)
    assert len(attempted) == 1
    assert all(packet[0] == 0xAA for packet in packets)


async def test_mode_gradual_observation_never_confirms_register_write(radio):
    c, state, packets, _ = radio
    assert await c.refresh_state(refresh_all=True)
    baseline = c._field_revisions.get("boolean_gradual", 0)
    c._notify_callback(None, bytearray(frame("aa0515011194")))
    assert c.static_gradual is True
    assert c._field_revisions.get("boolean_gradual", 0) == baseline
    c._notify_callback(None, bytearray(frame("aaa300")))
    assert c.boolean_control_state["gradual"] is False
    assert c.static_gradual is True
    assert c._field_revisions["boolean_gradual"] == baseline + 1


async def test_music_recovery_revocation_precedes_brightness(radio):
    c, state, packets, _ = radio
    assert await c.refresh_state(refresh_all=True)
    writes = prepare_music_profile_writes(c.model, "bloom", 50, None, False, {}, profile=c.profile)
    body = next(values["_music_body"][1] for _, values in writes if values.get("_music_body"))
    from dataclasses import replace

    prior = replace(c.capture_effect_control_state(), mode="music", music_mode="bloom", music_body=body)
    await c.disconnect()
    state["hw"] = None
    packets.clear()
    with pytest.raises(ValueError, match="Music variant"):
        await c.async_restore_effect_control_state(prior, overwritten_diy_code=None)
    assert all(packet[0] == 0xAA for packet in packets)


async def test_music_variant_change_blocks_upload_after_power(radio):
    from dataclasses import replace

    c, state, packets, clients = radio
    assert await c.refresh_state(refresh_all=True)
    writes = prepare_music_profile_writes(c.model, "bloom", 50, None, False, {}, profile=c.profile)
    original = clients[-1].write_gatt_char.side_effect

    async def change_variant(_uuid, packet, **kwargs):
        await original(_uuid, packet, **kwargs)
        if packet[:2] == bytes.fromhex("3301"):
            c.profile = replace(
                c.profile,
                music_variants=tuple(
                    replace(variant, supports_style=False) if variant.mode_code == 0x30 else variant
                    for variant in c.profile.music_variants
                ),
            )

    clients[-1].write_gatt_char.side_effect = change_variant
    packets.clear()
    with pytest.raises(ValueError, match="Music variant"):
        await c.async_write_music_sequence(writes, mode_code=0x30, physical_ic_count=None, intent=ControlIntent.USER)
    assert len(packets) == 1 and packets[0][:2] == bytes.fromhex("3301")


@pytest.mark.parametrize("accept", [True, False])
async def test_kelvin_and_gradual_recovery_do_not_use_rendered_rgb_as_kelvin(radio, accept):
    c, state, packets, _ = radio
    assert await c.refresh_state(refresh_all=True)
    prior = PriorControlState.from_dict(c.capture_effect_control_state().to_dict())
    assert prior.color_temp_kelvin == 4500 and prior.static_gradual is True
    state.update(kelvin=3000, mode="15000bb8", gradual=False, accept_kelvin=accept)
    assert await c.refresh_state(refresh_all=True)
    packets.clear()
    restored = await c.async_restore_effect_control_state(prior, overwritten_diy_code=None)
    assert restored is accept
    assert build_color_temp(4500, c.model, profile=c.profile) in packets
    assert any(packet[:2] == bytes.fromhex("aaa3") for packet in packets)


@pytest.mark.parametrize("code", [402, 501, 504, 507])
async def test_authored_selector_recovery_is_selection_only(radio, code):
    c, state, packets, _ = radio
    state["mode"] = "04" + code.to_bytes(2, "little").hex()
    assert await c.refresh_state(refresh_all=True)
    prior = c.capture_effect_control_state()
    assert prior.mode == "scene" and prior.scene_code == code
    packets.clear()
    assert not await c.async_restore_effect_control_state(prior, overwritten_diy_code=None)
    assert build_scene_activation(c.model, code, profile=c.profile) in packets
    assert c.scene_code == code
    packets.clear()
    assert not await c.async_restore_effect_control_state(prior, overwritten_diy_code=code)
    assert not packets


async def test_qualified_pact1_static_is_owner_confirmed_whole_strip_rgb(radio):
    c, state, packets, _ = radio
    c.pact_type, c.pact_code = 1, 1
    state.update(hw="1.00.03", fw="1.06.00", register_brightness=True)
    c.fw_version, c.hw_version = state["fw"], state["hw"]
    c._resolve_device_profile()
    assert not c.profile.can_read(ReadDomain.COLOUR_MODE) and not c.profile.supports_segments
    assert await c.refresh_state(refresh_all=True)
    assert not {bytes(packet[:2]) for packet in packets} & {bytes.fromhex("aa05"), bytes.fromhex("aaa5")}
    red = build_color_rgb(255, 0, 0, c.model, profile=c.profile)
    assert red == bytes.fromhex("33051501ff00000000000000ff7f00000000005d")
    with pytest.raises(ValueError, match="colour temperature"):
        build_color_temp(4000, c.model, profile=c.profile)


@pytest.mark.parametrize("identity", [None, "ble", "configured", "configured_fw", "configured_hw"])
@pytest.mark.parametrize(
    ("register", "percent", "owner_frame"),
    [
        (235, 92, "aa04eb0000000000000000000000000000000045"),
        (255, 100, "aa04ff0000000000000000000000000000000051"),
    ],
)
async def test_issue310_setup_control_and_reconnect_use_brightness_register(
    radio, identity, register, percent, owner_frame
):
    from types import SimpleNamespace

    c, state, packets, clients = radio
    if identity in {"configured", "configured_fw", "configured_hw"}:
        c._configured_h6102_firmware, c._configured_h6102_hardware = "1.08.08", "1.00.03"
    c._note_advertisement(SimpleNamespace(manufacturer_data={34817: bytes.fromhex("ec000101")}))
    state.update(
        fw="1.08.08" if identity in {"ble", "configured_hw"} else None,
        hw="1.00.03" if identity in {"ble", "configured_fw"} else None,
        register_brightness=True,
        brightness=92,
        brightness_reply_override=register,
    )
    snapshot = await c._async_update_data()
    assert snapshot["brightness_pct"] == percent
    assert any(entry["raw"] == owner_frame and entry["outcome"] == "parsed" for entry in c.packet_log)
    assert c.profile.brightness_wire_range == (20, 254)
    assert c.profile.supports_rgb is (identity is not None)
    state["brightness_reply_override"] = None
    light = GoveeBLELight(c)
    light.async_write_ha_state = MagicMock()
    for value, register, percent in ((26, 41, 10), (128, 136, 50), (255, 254, 100)):
        await light.async_turn_on(brightness=value)
        assert state["brightness"] == c.brightness_pct == percent
        assert frame(f"3304{register:02x}") in packets
        assert "brightness_pct" in c._field_revisions
    if identity:
        await light.async_turn_on(rgb_color=(1, 2, 3))
        assert state["colours"] == [(1, 2, 3)] * 15
        assert light.rgb_color == (1, 2, 3)
    await light.async_turn_off()
    assert not state["on"] and not c.is_on
    await c.disconnect()
    assert await c.refresh_state(refresh_all=True, required_domains=c.profile.setup_required_read_domains)
    assert c.profile.brightness_wire_range == (20, 254) and c.brightness_pct == 100
    assert len(clients) >= 2


@pytest.mark.parametrize("missing", ["fw", "hw"])
async def test_issue310_cached_identity_does_not_authorize_colour_after_reconnect(radio, missing):
    c, state, packets, _ = radio
    c.pact_type, c.pact_code = 1, 1
    c._configured_h6102_firmware, c._configured_h6102_hardware = "1.08.08", "1.00.03"
    c._resolve_device_profile()
    state.update(fw="1.08.08", hw="1.00.03", register_brightness=True)
    assert await c.refresh_state(refresh_all=True)
    assert c._configured_h6102_firmware is c._configured_h6102_hardware is None
    await c.disconnect()
    assert c.profile.supports_rgb and c.fw_version == "1.08.08" and c.hw_version == "1.00.03"
    state[missing] = None
    packets.clear()
    attempts = c.control_write_attempts
    with pytest.raises(HomeAssistantError):
        await GoveeBLELight(c).async_turn_on(rgb_color=(1, 2, 3))
    assert c.profile.supports_rgb
    assert c.control_write_attempts == attempts
    assert all(packet[0] == 0xAA for packet in packets)


@pytest.mark.parametrize(("pact_type", "register"), [(1, 19), (10, 255)])
async def test_issue310_brightness_tolerance_excludes_low_registers_and_modern_percentages(radio, pact_type, register):
    c, _, _, _ = radio
    c.pact_type, c.pact_code = pact_type, 1
    c._resolve_device_profile()
    c._notify_callback(None, bytearray(frame(f"aa04{register:02x}")))
    assert c.packet_log[-1]["reason"] == "semantic_rejected"
    assert "brightness_pct" not in c._field_revisions


@pytest.mark.parametrize("fault", ["write", "stale_readback"])
async def test_issue310_failed_register_command_does_not_confirm_brightness(radio, fault):
    c, state, packets, _ = radio
    c.pact_type, c.pact_code = 1, 1
    c._resolve_device_profile()
    state.update(fw=None, hw=None, register_brightness=True, brightness=92)
    assert await c.refresh_state(refresh_all=True, required_domains=c.profile.setup_required_read_domains)
    revision = c._field_revisions["brightness_pct"]
    state["fault_brightness"] = fault == "write"
    state["brightness_reply_override"] = 235 if fault == "stale_readback" else None
    with pytest.raises(HomeAssistantError) as error:
        await GoveeBLELight(c).async_turn_on(brightness=128)
    assert error.value.translation_key == "device_command_failed"
    assert c.brightness_pct == 92 and c._field_revisions["brightness_pct"] == revision
    if fault == "write":
        assert state["brightness"] == 92
        assert not any(entry["dir"] == "tx" and entry["raw"] == frame("330488").hex() for entry in c.packet_log)
    else:
        assert state["brightness"] == 50


async def test_pact1_static_recovery_preserves_register_transport_without_confirming_unknown_controls(radio):
    c, state, packets, _ = radio
    c.pact_type, c.pact_code = 1, 1
    c._resolve_device_profile()
    state.update(hw="1.00.03", fw="1.08.08", register_brightness=True)
    assert await c.refresh_state(refresh_all=True)
    prior = c.capture_effect_control_state()
    light = GoveeBLELight(c)
    light.async_write_ha_state = MagicMock()
    await light.async_turn_on(brightness=255, rgb_color=(1, 2, 3))
    packets.clear()
    assert prior.static_gradual is None and "gradual" not in c.profile.boolean_controls
    assert not await c.async_restore_effect_control_state(prior, overwritten_diy_code=None)
    assert state["brightness"] == c.brightness_pct == prior.brightness_pct == 50
    assert frame("330488") in packets


def test_legacy_static_snapshot_keeps_new_fields_unknown():
    raw = {"mode": "colour", "is_on": True, "brightness_pct": 50, "rgb_color": [1, 2, 3]}
    assert PriorControlState.from_dict(raw).static_gradual is None
    with pytest.raises(EffectStorageError):
        PriorControlState.from_dict({**raw, "static_gradual": 2})


@pytest.mark.parametrize("fragment", [1, 2])
@pytest.mark.parametrize("replacement", [None, ("hopping", bytes.fromhex("3302010203040506aabbcc196104050708"))])
async def test_external_retained_body_change_stops_edit_and_preserves_external_value(hass, fragment, replacement):
    from tests.test_music_commands import _music_transport

    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6102", configuration_url=None, h6102_pact="10/1")
    c.fw_version, c.hw_version = "3.02.02", "3.02.01"
    c._resolve_device_profile()
    c._confirmed_identity_fields.update(c.profile.profile_identity_fields)
    c.music_mode = "hopping"
    c._music_body = ("hopping", bytes.fromhex("3302010203040506aabbcc196104050708"))
    with _music_transport(c) as physical:

        async def replace_body(*args, **kwargs):
            if physical.await_count == fragment:
                c._music_body = replacement

        physical.side_effect = replace_body
        with pytest.raises(ValueError, match="Retained music body changed"):
            await c.async_apply_music_params(0x33, parameters={"relative_brightness": 17})
        assert physical.await_count == fragment
        assert c._music_body == replacement


async def test_h6102_zero_kelvin_is_fresh_rgb_state(radio):
    c, state, _, _ = radio
    assert await c.refresh_state(refresh_all=True)
    revision = c._field_revisions["color_temp_kelvin"]
    c._notify_callback(None, bytearray(frame("aa0515010000")))
    assert c.color_temp_kelvin is None
    assert c.color_temp_kelvin_source == "observed"
    assert c._field_revisions["color_temp_kelvin"] == revision + 1


@pytest.mark.parametrize("accept", [True, False])
async def test_rgb_recovery_requires_explicit_fresh_zero_kelvin(radio, accept):
    c, state, _, _ = radio
    state.update(kelvin=0, mode="15010000", colours=[(12, 34, 56)] * 15)
    assert await c.refresh_state(refresh_all=True)
    assert c.rgb_color == (12, 34, 56) and c.color_temp_kelvin_source == "observed"
    prior = c.capture_effect_control_state()
    state.update(kelvin=4500, mode="15011194", colours=[(1, 2, 3)] * 15, accept_rgb_kelvin=accept)
    assert await c.async_restore_effect_control_state(prior, overwritten_diy_code=None) is accept
    assert state["colours"] == list(prior.segment_colors)


@pytest.mark.parametrize("mixed", [True, False])
@pytest.mark.parametrize("on", [True, False])
async def test_unrepresentable_kelvin_layout_is_never_overwritten_or_confirmed(radio, mixed, on):
    c, state, packets, _ = radio
    state.update(colours=[(9, 8, 7)] * 14 + ([(1, 2, 3)] if mixed else [(9, 8, 7)]), on=on)
    assert await c.refresh_state(refresh_all=True)
    prior = c.capture_effect_control_state()
    packets.clear()
    assert not await c.async_restore_effect_control_state(prior, overwritten_diy_code=None)
    assert state["colours"] == list(prior.segment_colors)
    assert state["on"] is on
    assert not any(parse_static_write(packet, c.model, profile=c.profile) for packet in packets)


async def test_matching_kelvin_with_wrong_fresh_segment_reply_is_incomplete(radio):
    c, state, _, _ = radio
    state["on"] = False
    assert await c.refresh_state(refresh_all=True)
    prior = c.capture_effect_control_state()
    state["corrupt_kelvin_rgb"] = True
    assert not await c.async_restore_effect_control_state(prior, overwritten_diy_code=None)
    assert state["kelvin"] == prior.color_temp_kelvin
    assert state["colours"] != list(prior.segment_colors)
    assert state["on"] is False


async def test_native_scene_revoked_at_connection_writes_nothing(radio):
    c, state, packets, _ = radio
    c.is_on = False
    state["pact_on_connect"] = 1
    with pytest.raises(ValueError, match="native scenes"):
        await c.async_apply_native_scene("sunrise", verify=True)
    assert all(packet[0] == 0xAA for packet in packets)


@pytest.mark.parametrize("code", [402, 501, 502, 503, 504, 505, 506, 507])
async def test_engine_failed_upload_never_reselects_overwritten_scene_slot(radio, code):
    from dataclasses import replace

    from custom_components.ha_govee_led_ble.effect_catalogue import resolve_catalogue_template

    c, state, packets, _ = radio
    state["mode"] = "04" + code.to_bytes(2, "little").hex()
    assert await c.refresh_state(refresh_all=True)
    content = resolve_catalogue_template("H6102", f"template:native-diy:{501 if code == 402 else code}").content
    if code == 402:
        content = replace(content, native_diy=None)
    repository = EffectDeploymentRepository(InMemoryVersionedDocumentStore())
    await repository.async_load()
    state["fault_upload"] = True
    packets.clear()
    with pytest.raises(RuntimeError, match="failed body upload"):
        await EffectDeploymentEngine(repository).async_apply_saved(
            c, LibraryItem.new("Failing", content), config_entry_id="entry", updated_at="2026-09-17T00:00:00Z"
        )
    assert build_scene_activation(c.model, code, profile=c.profile) not in packets
    assert repository.snapshot().records[0].phase is DeploymentPhase.UNCERTAIN
