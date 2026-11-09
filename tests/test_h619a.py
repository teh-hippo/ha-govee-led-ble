"""Reconstructed H619A contracts, not hardware confirmation."""

from contextlib import asynccontextmanager
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak import BleakError

from custom_components.ha_govee_led_ble.const import device_profile
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_status import StatusDomain, decode_status_frame
from custom_components.ha_govee_led_ble.effect_catalogue import MODEL_EFFECT_CATALOGUES
from custom_components.ha_govee_led_ble.effect_compiler import compile_application, validate_compiled_geometry
from custom_components.ha_govee_led_ble.effect_domain import BuiltinScene, CatalogueRef, LibraryItem
from custom_components.ha_govee_led_ble.effect_storage import LibrarySnapshot
from custom_components.ha_govee_led_ble.generated_protocol_adapter import build_segment_query
from custom_components.ha_govee_led_ble.layered_scene import AppliedArea, Distribution, Selection
from custom_components.ha_govee_led_ble.layered_scene_decoder import (
    decode_catalogue_layered_scene,
    decode_layered_scene,
    encode_layered_scene,
)
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.light_commands import (
    build_color_rgb,
    build_color_temp,
    build_segment_brightness,
    build_segment_color_temp,
)
from custom_components.ha_govee_led_ble.music_commands import prepare_music_request
from custom_components.ha_govee_led_ble.native_scenes import build_native_scene_packets
from custom_components.ha_govee_led_ble.scenes import SCENE_ENTRIES
from custom_components.ha_govee_led_ble.transport import reassemble_a3, xor_checksum


def _frame(prefix: str) -> bytes:
    data = bytes.fromhex(prefix).ljust(19, b"\x00")
    return data + bytes((xor_checksum(data),))


def test_static_writes_select_ten_logical_segments_not_twenty_physical_ics():
    assert build_color_rgb(17, 34, 51, "H619A") == _frame("330515011122330000000000ff03")
    assert build_color_temp(4000, "H619A") == _frame("33051501ffffff0fa0ffd5a1ff03")
    assert build_segment_color_temp([10], 4000, "H619A") == _frame("33051501ffffff0fa0ffd5a10002")
    assert build_segment_brightness([10], 37, "H619A") == _frame("33051502250002")
    with pytest.raises(ValueError):
        build_segment_color_temp([11], 4000, "H619A")


@pytest.mark.parametrize(
    ("firmware", "hardware", "legacy"),
    [
        (None, None, True),
        ("2.07.01", None, True),
        (None, "2.01.02", True),
        ("1.05.99", "1.00.02", True),
        ("1.06.00", "1.00.01", True),
        ("1.06.00", "1.00.02", False),
        ("2.07.01", "2.01.02", False),
    ],
)
def test_segment_readback_revision_selects_only_its_layout(firmware, hardware, legacy):
    profile = device_profile("H619A", 2, 1, firmware=firmware, hardware=hardware)
    count = 3 if legacy else 4
    for group in range(1, count + 1):
        query = build_segment_query(group, "H619A", profile=profile)
        wire = profile.outbound_transform(query) if profile.outbound_transform is not None else query
        assert wire == _frame(f"aa{'a2' if legacy else 'a5'}{group:02x}")
    with pytest.raises(ValueError, match="geometry"):
        build_segment_query(count + 1, "H619A", profile=profile)
    with pytest.raises(ValueError, match="geometry"):
        build_segment_query(0, "H619A", profile=profile)

    last = _segment_page(count, legacy)
    decoded = decode_status_frame(last, "H619A", profile=profile)
    assert decoded is not None and decoded.domain is StatusDomain.SEGMENTS
    assert len(decoded.generated.body.segments) == (2 if legacy else 1)
    wrong = decode_status_frame(_segment_page(1, not legacy), "H619A", profile=profile)
    assert wrong is not None and wrong.domain is StatusDomain.OTHER
    for group in (0, count + 1):
        invalid = bytearray(last)
        invalid[2] = group
        invalid[-1] = xor_checksum(invalid[:-1])
        assert decode_status_frame(bytes(invalid), "H619A", profile=profile) is None

    for packet in (
        build_color_rgb(17, 34, 51, "H619A", profile=profile),
        build_segment_brightness([10], 37, "H619A", profile=profile),
    ):
        assert profile.outbound_transform is None or profile.outbound_transform(packet) == packet
    assert profile.supports_segment_brightness and profile.supports_segment_color_temperature


def _segment_page(group, legacy):
    group_size = 4 if legacy else 3
    indices = range((group - 1) * group_size, min(group * group_size, 10))
    records = b"".join(
        (b"" if legacy else bytes((50 + index,))) + bytes((index, index + 1, index + 2)) for index in indices
    )
    payload = (bytes((group,)) + records).ljust(17, b"\x7e")
    return _frame((bytes((0xAA, 0xA2 if legacy else 0xA5)) + payload).hex())


@pytest.mark.parametrize("legacy", [True, False])
async def test_segment_refresh_observes_only_revision_supported_fields(hass, monkeypatch, legacy):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", model="H619A", configuration_url=None)
    client = MagicMock(is_connected=True, start_notify=AsyncMock(), disconnect=AsyncMock())
    coordinator._client = client
    await coordinator._start_notify()
    receive = client.start_notify.call_args.args[1]
    coordinator._observe_identity_field("fw_version", "1.05.99" if legacy else "2.07.01")
    coordinator._observe_identity_field("hw_version", "2.01.02")
    coordinator.segment_brightness = [37] * 10
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(coordinator, "_renew_foreground_lease", MagicMock())

    async def write(_uuid, packet, **_kwargs):
        assert packet[1] == (0xA2 if legacy else 0xA5)
        receive(None, bytearray(_segment_page(packet[2], legacy)))

    client.write_gatt_char = AsyncMock(side_effect=write)
    assert await coordinator.async_refresh_segments()
    assert client.write_gatt_char.await_count == (3 if legacy else 4)
    assert coordinator.segment_colors == [(index, index + 1, index + 2) for index in range(10)]
    assert coordinator.segment_brightness == ([37] * 10 if legacy else list(range(50, 60)))
    assert coordinator.segment_brightness_readable is not legacy
    assert ("segment_brightness" in coordinator._field_revisions) is not legacy
    await coordinator.disconnect()


async def test_reconnect_does_not_qualify_readback_from_cached_versions(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", model="H619A", configuration_url=None)
    client = MagicMock(is_connected=True, disconnect=AsyncMock())
    coordinator._client = client
    coordinator._observe_identity_field("fw_version", "2.07.01")
    coordinator._observe_identity_field("hw_version", "2.01.02")
    assert coordinator.profile.status_grammar == "H619A"
    coordinator._clear_client_state(client)

    async def connect(*args, **kwargs):
        assert coordinator.profile.status_grammar == "H619A-legacy"
        assert (coordinator.fw_version, coordinator.hw_version) == ("2.07.01", "2.01.02")
        raise BleakError("connection refused")

    monkeypatch.setattr("custom_components.ha_govee_led_ble.coordinator.async_establish_ble_connection", connect)
    with pytest.raises(BleakError, match="connection refused"):
        await coordinator._ensure_connected()
    coordinator._client = client
    coordinator._observe_identity_field("fw_version", "2.07.01")
    assert coordinator.profile.status_grammar == "H619A-legacy"
    coordinator._observe_identity_field("hw_version", "2.01.02")
    assert coordinator.profile.status_grammar == "H619A"
    coordinator._observe_identity_field("hw_version", "invalid")
    assert coordinator.profile.status_grammar == "H619A-legacy"
    assert coordinator.hw_version == "2.01.02"
    coordinator._observe_identity_field("hw_version", "2.01.02")
    assert coordinator.profile.status_grammar == "H619A"
    await coordinator.disconnect()


@pytest.mark.parametrize("initial_legacy", [True, False])
async def test_revision_change_abandons_pages_and_ignores_old_format(hass, monkeypatch, initial_legacy):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", model="H619A", configuration_url=None)
    client = MagicMock(is_connected=True, start_notify=AsyncMock(), disconnect=AsyncMock())
    coordinator._client = client
    await coordinator._start_notify()
    receive = client.start_notify.call_args.args[1]
    coordinator._observe_identity_field("fw_version", "1.05.99" if initial_legacy else "2.07.01")
    coordinator._observe_identity_field("hw_version", "2.01.02")
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(coordinator, "_renew_foreground_lease", MagicMock())

    async def write(_uuid, packet, **_kwargs):
        receive(None, bytearray(_segment_page(packet[2], initial_legacy)))
        coordinator._observe_identity_field("fw_version", "2.07.01" if initial_legacy else "1.05.99")

    client.write_gatt_char = AsyncMock(side_effect=write)
    assert not await coordinator.async_refresh_segments()
    assert client.write_gatt_char.await_count == 1
    assert coordinator._segment_query_incomplete
    for group in range(1, 4 if initial_legacy else 5):
        receive(None, bytearray(_segment_page(group, initial_legacy)))
    assert coordinator.segment_state_source != "observed"
    assert not coordinator._segment_groups_observed
    assert coordinator._field_revisions.get("segment_colors", 0) == 0
    await coordinator.disconnect()


@pytest.mark.parametrize(
    ("mode", "code", "tail"),
    [
        ("bloom", 48, "0a50"),
        ("shiny", 49, "05640a"),
        ("separation", 50, "030061"),
        ("hopping", 51, "010101196201030308"),
        ("piano_keys", 52, "000f0a0507"),
        ("fountain", 53, "01010550"),
        ("day_and_night", 55, "0a0a00"),
    ],
)
def test_music_uses_twenty_ic_defaults_and_uploads_before_selector(mode, code, tail):
    writes = prepare_music_request("H619A", mode, 42, None, False, {})
    assert writes[0] == _frame("330101")
    assert writes[-1] == _frame(f"330513{code:02x}2a")
    envelope = reassemble_a3(writes[1:-1])
    expected = bytes((0x41, code, 7)) + bytes.fromhex("ff0000ff7f00ffff0000ff000000ff00ffff8b00ff" + tail)
    assert envelope[2 : 2 + len(expected)] == expected
    assert not any(envelope[2 + len(expected) :])


@pytest.mark.parametrize(
    ("firmware", "hardware", "legacy"),
    [
        (None, None, True),
        ("1.06.00", "1.00.01", True),
        ("1.05.99", "1.00.02", True),
        ("1.06.00", "1.00.02", False),
        ("2.07.01", "2.01.02", False),
    ],
)
def test_scene_revision_conversion_preserves_source_and_uses_physical_geometry(firmware, hardware, legacy):
    profile = device_profile("H619A", 2, 1, firmware=firmware, hardware=hardware)
    entry = next(entry for entry in SCENE_ENTRIES["H619A"] if entry.scene_type == 2)
    scene = decode_catalogue_layered_scene("H619A", entry)
    assert scene is not None
    layer = replace(
        scene.effect.layers[0],
        area=AppliedArea(0, 0),
        selection=Selection(3, 4, 2),
        unknown_flags=0x20,
        distribution=Distribution(3, True),
    )
    authored = replace(scene, effect=replace(scene.effect, layers=(layer,)))
    raw = encode_layered_scene(authored)
    packets = build_native_scene_packets("H619A", entry, canonical_body=raw, profile=profile)
    envelope = reassemble_a3(packets[:-1])
    parsed = decode_layered_scene(authored.template, envelope[3:])
    actual = parsed.effect.layers[0]
    assert actual.selection == (Selection(0, 0, 5) if legacy else layer.selection)
    assert actual.distribution == (Distribution(2, False) if legacy else layer.distribution)
    assert actual.unknown_flags == (0 if legacy else 0x20)
    assert encode_layered_scene(authored) == raw
    assert packets[-1] == _frame(f"330504{entry.code.to_bytes(2, 'little').hex()}")


def test_every_h619a_template_and_scene_compiles_for_each_scene_revision():
    for firmware, hardware in ((None, None), ("1.06.00", "1.00.02")):
        profile = device_profile("H619A", 2, 1, firmware=firmware, hardware=hardware)
        for template in MODEL_EFFECT_CATALOGUES["H619A"].templates:
            compiled = compile_application(
                LibraryItem.new(template.label, template.content),
                "H619A",
                diy_code=getattr(template.content, "native_diy", None) or 24,
                profile=profile,
            )
            assert compiled.packets
        for entry in SCENE_ENTRIES["H619A"]:
            packets = build_native_scene_packets("H619A", entry, profile=profile)
            assert packets[-1] == _frame(f"330504{entry.code.to_bytes(2, 'little').hex()}")
            if entry.speed is not None:
                bodies = {
                    b"".join(build_native_scene_packets("H619A", entry, speed_index=index, profile=profile))
                    for index in range(entry.speed.option_count)
                }
                assert len(bodies) == entry.speed.option_count


def test_prepared_scene_rejects_stale_cached_identity_and_changed_revision(hass):
    profile = device_profile("H619A", 2, 1, firmware="2.07.01", hardware="2.01.02")
    entry = next(entry for entry in SCENE_ENTRIES["H619A"] if entry.scene_type == 2)
    item = LibraryItem.new("Scene", BuiltinScene(CatalogueRef("H619A", entry.scene_id, entry.effect_id)))
    compiled = compile_application(item, "H619A", profile=profile)
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", model="H619A", configuration_url=None)
    coordinator.profile = profile
    coordinator.fw_version, coordinator.hw_version = "2.07.01", "2.01.02"
    with pytest.raises(ValueError, match="scene format changed"):
        validate_compiled_geometry(compiled, coordinator.effect_authorization_profile)
    coordinator._confirmed_identity_fields.update({"fw_version", "hw_version"})
    validate_compiled_geometry(compiled, coordinator.effect_authorization_profile)
    coordinator.hw_version = "1.00.01"
    coordinator._resolve_device_profile()
    with pytest.raises(ValueError, match="scene format changed"):
        validate_compiled_geometry(compiled, coordinator.effect_authorization_profile)


@pytest.mark.parametrize(
    ("selection", "expected"),
    [
        (Selection(0, 0, 40), Selection(0, 0, 10)),
        (Selection(1, 0, 40), Selection(1, 0, 20)),
        (Selection(2, 25, 24), Selection(2, 20, 20)),
        (Selection(3, 30, 30), Selection(3, 20, 18)),
    ],
)
def test_scene_geometry_rewrites_out_of_budget_fields_without_mutating_authored_content(selection, expected):
    profile = device_profile("H619A", 2, 1, firmware="1.06.00", hardware="1.00.02")
    entry = next(entry for entry in SCENE_ENTRIES["H619A"] if entry.scene_type == 2)
    scene = decode_catalogue_layered_scene("H619A", entry)
    assert scene is not None
    layer = replace(scene.effect.layers[0], area=AppliedArea(0, 0), selection=selection)
    layer = replace(
        layer,
        selected_movement=replace(layer.selected_movement, distance=255),
        overall_movement=replace(layer.overall_movement, distance=254),
    )
    authored = replace(scene, effect=replace(scene.effect, layers=(layer,)))
    parsed = decode_layered_scene(scene.template, encode_layered_scene(authored, profile=profile))
    assert parsed.effect.layers[0].selection == expected
    assert parsed.effect.layers[0].selected_movement.distance == 18
    assert parsed.effect.layers[0].overall_movement.distance == 18
    assert authored.effect.layers[0] == layer


@pytest.mark.parametrize("revoke_during_pacing", [False, True])
async def test_native_scene_uses_subscription_identity_and_rechecks_after_reply_pacing(
    hass, monkeypatch, revoke_during_pacing
):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", model="H619A", configuration_url=None)
    coordinator.profile = device_profile("H619A", 2, 1, firmware="2.07.01", hardware="2.01.02")
    coordinator.fw_version, coordinator.hw_version = "2.07.01", "2.01.02"
    coordinator.is_on = True
    if revoke_during_pacing:
        coordinator._confirmed_identity_fields.update({"fw_version", "hw_version"})
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    coordinator._client = client
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    entry = next(entry for entry in SCENE_ENTRIES["H619A"] if entry.scene_type == 2)

    async def sequence(packets, *, write_guard, **kwargs):
        expected = build_native_scene_packets("H619A", entry, profile=coordinator.effect_authorization_profile)
        assert packets == expected
        if revoke_during_pacing:
            monkeypatch.setattr(
                coordinator._reply_gate, "wait", AsyncMock(side_effect=coordinator._confirmed_identity_fields.clear)
            )
            await coordinator._async_write_packet(client, packets[0], before_write=write_guard)
        else:
            write_guard()

    monkeypatch.setattr(coordinator, "async_write_effect_sequence", AsyncMock(side_effect=sequence))
    if revoke_during_pacing:
        with pytest.raises(ValueError, match="scene format changed"):
            await coordinator.async_apply_native_scene("Candidate", scene_entry=entry, verify=False)
    else:
        await coordinator.async_apply_native_scene("Candidate", scene_entry=entry, verify=False)
        assert coordinator.effect_authorization_profile.rgbic_scene_v0 is True
    client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("fresh_identity", [False, True])
async def test_saved_scene_reconnects_before_compilation_after_idle_disconnect(hass, monkeypatch, fresh_identity):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", model="H619A", configuration_url=None)
    coordinator.profile = device_profile("H619A", 2, 1, firmware="1.06.00", hardware="1.00.02")
    coordinator.fw_version, coordinator.hw_version = "1.06.00", "1.00.02"
    coordinator.is_on = True
    entry = next(entry for entry in SCENE_ENTRIES["H619A"] if entry.scene_type == 2)
    item = LibraryItem.new("Saved", BuiltinScene(CatalogueRef("H619A", entry.scene_id, entry.effect_id)))

    async def connect():
        if fresh_identity:
            coordinator._confirmed_identity_fields.update({"fw_version", "hw_version"})
        return MagicMock(is_connected=True)

    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(side_effect=connect))
    policies = []

    @asynccontextmanager
    async def saved_effect_for_apply(*args, profile, **kwargs):
        policies.append(profile.rgbic_scene_v0)
        yield item

    engine = SimpleNamespace(async_apply_saved=AsyncMock())
    backend = SimpleNamespace(
        application=SimpleNamespace(
            saved_effect_for_apply=saved_effect_for_apply, library_snapshot=lambda: LibrarySnapshot((item,))
        ),
        engine=engine,
    )
    entity = GoveeBLELight(coordinator, config_entry_id="entry", effect_backend=backend)
    monkeypatch.setattr(entity, "_async_supersede_preview", AsyncMock())
    await entity._async_apply_saved_item(item)
    coordinator._ensure_connected.assert_awaited_once()
    engine.async_apply_saved.assert_awaited_once()
    assert policies == [not fresh_identity]
