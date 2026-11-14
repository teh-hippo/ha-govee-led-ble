import asyncio
import base64
import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_govee_led_ble.const import KELVIN_RANGE_1000_10000, ModelProfile, ReadDomain
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_refresh import STATE_QUERY_TIMEOUT
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode, decode_status_frame, parse_color_mode
from custom_components.ha_govee_led_ble.diagnostics import async_get_config_entry_diagnostics
from custom_components.ha_govee_led_ble.effect_catalogue import MODEL_EFFECT_CATALOGUES
from custom_components.ha_govee_led_ble.effect_compiler import DIY_ACK_EVIDENCE, compile_application, compile_effect
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem, MusicProfile, Origin, SourceKind
from custom_components.ha_govee_led_ble.effect_protocol_decoder import UnsupportedA3EffectError, decode_effect_frames
from custom_components.ha_govee_led_ble.effect_runtime import (
    _active_workspace_content,
    async_prepare_effect_control_state,
)
from custom_components.ha_govee_led_ble.effect_scenes import _scene_content
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    BulkStatusCollector,
    build_boolean_control,
    build_boolean_control_query,
    build_brightness,
    build_brightness_query,
    build_bulk_status_query,
    build_colour_mode_query,
    build_power,
    build_power_on_behaviour,
    build_power_on_behaviour_query,
    build_segment_query,
    parse_a3_effect_envelope,
    parse_command_ack_result,
    require_profile_packet,
    upload_ack_success,
)
from custom_components.ha_govee_led_ble.h60a6_effects import decode_native_scene
from custom_components.ha_govee_led_ble.h1771_effects import decode_h1771_diy, encode_h1771_diy
from custom_components.ha_govee_led_ble.layered_scene import CatalogueRef
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.light_commands import (
    build_color_rgb,
    build_segment_brightness,
    build_segment_color,
    build_segment_color_temp,
    parse_static_write,
)
from custom_components.ha_govee_led_ble.music_commands import (
    music_body_style,
    prepare_music_request,
    validate_music_body,
)
from custom_components.ha_govee_led_ble.music_semantics import H1771_MUSIC_VARIANTS
from custom_components.ha_govee_led_ble.native_effect import (
    NativeDiyLayer,
    NativeEffect,
    NativeOpaqueLayer,
    native_effect_from_value,
    native_effect_to_value,
)
from custom_components.ha_govee_led_ble.native_scenes import build_native_scene_packets, encode_authored_scene_body
from custom_components.ha_govee_led_ble.scenes import MODEL_SCENES, SceneEntry, _load_speed
from custom_components.ha_govee_led_ble.transport import reassemble_a3, xor_checksum

PROFILE = ModelProfile(
    "H1771 candidate",
    command_grammar="H1771",
    status_grammar="H1771",
    command_operations=frozenset({"power", "brightness", "static"}),
    read_domains=frozenset({ReadDomain.BRIGHTNESS, ReadDomain.COLOUR_MODE, ReadDomain.SEGMENTS}),
    colour_mode_query_selector=1,
    supports_rgb=True,
    supports_color_temperature=True,
    color_temp_range=KELVIN_RANGE_1000_10000,
    supports_segment_writes=True,
    supports_segment_brightness=True,
    supports_segment_color_temperature=True,
    segment_count=4,
    segment_group_size=4,
)
BULK_PROFILE = replace(
    PROFILE,
    bulk_status_grammar="H1771",
    setting_grammar="H1771",
    boolean_controls=frozenset({"source_0_enabled", "source_1_enabled", "gradual"}),
    supports_power_on_behaviour=True,
    read_domains=PROFILE.read_domains | {ReadDomain.POWER},
)
IDENTITY_PROFILE = replace(
    BULK_PROFILE,
    read_domains=BULK_PROFILE.read_domains
    | {ReadDomain.FIRMWARE, ReadDomain.HARDWARE, ReadDomain.WIRELESS_FIRMWARE, ReadDomain.WIRELESS_HARDWARE},
)
MUSIC_PROFILE = replace(
    BULK_PROFILE,
    command_ack_grammar="H617A",
    effect_grammar="H1771",
    music_grammar="H1771",
    music_modes=("rhythm", "expansion", "piano", "pulse", "flowing", "rolling"),
    music_variants=H1771_MUSIC_VARIANTS,
    command_operations=(BULK_PROFILE.command_operations or frozenset()) | {"music", "effect_upload"},
    music_upload_before_selector=True,
    music_requires_upload_ack=True,
)
SCENE_PROFILE = replace(
    MUSIC_PROFILE,
    supports_scenes=True,
    supports_custom_effects=True,
    command_operations=(MUSIC_PROFILE.command_operations or frozenset()) | {"scene", "diy"},
)


def frame(prefix):
    content = bytes.fromhex(prefix).ljust(19, b"\x00")
    return content + bytes((xor_checksum(content),))


@pytest.mark.parametrize(
    ("packet", "prefix"),
    [
        (build_power(True, profile=PROFILE), "330101"),
        (build_brightness(50, profile=PROFILE), "330432"),
        (build_color_rgb(1, 2, 3, profile=PROFILE), "3305150101020300000000000f00"),
        (build_segment_color([2, 4], 1, 2, 3, profile=PROFILE), "3305150101020300000000000a00"),
        (build_segment_brightness([1, 3], 40, profile=PROFILE), "33051502280500"),
        (build_segment_color_temp([4], 4000, profile=PROFILE), "33051501ffffff0fa0ffd5a10800"),
    ],
)
def test_candidate_basic_commands_match_reconstructed_bytes(packet, prefix):
    assert packet == frame(prefix)
    require_profile_packet(packet, PROFILE)


def test_candidate_mask_is_checked_against_profile_geometry():
    packet = build_segment_color([1], 1, 2, 3, profile=PROFILE)
    parsed = parse_static_write(packet, profile=PROFILE)
    assert parsed is not None and parsed.segment_mask == 1
    with pytest.raises(ValueError, match="out of range"):
        build_segment_color([5], 1, 2, 3, profile=PROFILE)
    with pytest.raises(ValueError, match="segment mask"):
        require_profile_packet(frame("3305150101020300000000001000"), PROFILE)


@pytest.mark.parametrize(
    ("packet", "prefix"),
    [
        (build_brightness_query(profile=PROFILE), "aa04"),
        (build_colour_mode_query(profile=PROFILE), "aa0501"),
        (build_segment_query(1, profile=PROFILE), "aaa501"),
    ],
)
def test_candidate_queries_match_reconstructed_bytes(packet, prefix):
    assert packet == frame(prefix)
    require_profile_packet(packet, PROFILE)


@pytest.mark.parametrize("selector", ["0d", "15"])
def test_candidate_colour_mode_status_uses_separate_kelvin_observation(selector):
    decoded = decode_status_frame(frame(f"aa05{selector}010fa0"), profile=PROFILE)
    assert decoded is not None and decoded.domain is ReadDomain.COLOUR_MODE
    mode = parse_color_mode(decoded.generated, "H1771", profile=PROFILE)
    assert mode.mode is ParsedMode.COLOUR and mode.color_temp_kelvin == 4000


def test_candidate_rejects_out_of_geometry_queries_and_brightness_pages():
    with pytest.raises(ValueError, match="geometry"):
        require_profile_packet(frame("aaa502"), PROFILE)
    with pytest.raises(ValueError, match="selector"):
        require_profile_packet(frame("aa0500"), PROFILE)
    with pytest.raises(ValueError, match="brightness page"):
        require_profile_packet(frame("33051503020a141e28"), PROFILE)
    with pytest.raises(ValueError, match="brightness page"):
        require_profile_packet(frame("330515030165141e28"), PROFILE)


@pytest.mark.parametrize(
    ("control", "prefix"),
    [
        ("source_0_enabled", "33360001"),
        ("source_1_enabled", "33360101"),
        ("gradual", "33a301"),
    ],
)
def test_candidate_boolean_controls_and_bulk_queries(control, prefix):
    packet = build_boolean_control(control, True, "H1771", profile=BULK_PROFILE)
    assert packet == frame(prefix)
    require_profile_packet(packet, BULK_PROFILE)
    query = build_boolean_control_query(control, "H1771", profile=BULK_PROFILE)
    assert query == frame("ac0301a3" if control == "gradual" else "ac030136")
    require_profile_packet(query, BULK_PROFILE)
    assert build_bulk_status_query(BULK_PROFILE) == frame("ac03044136a3a5")


def test_candidate_power_on_behaviour_uses_bulk_readback():
    packet = build_power_on_behaviour("off", BULK_PROFILE)
    assert packet == frame("33410202")
    require_profile_packet(packet, BULK_PROFILE)
    query = build_power_on_behaviour_query(BULK_PROFILE)
    assert query == frame("ac030141")
    require_profile_packet(query, BULK_PROFILE)


def test_candidate_bulk_collector_requires_complete_well_formed_records():
    collector = BulkStatusCollector("H1771")
    complete = collector.feed(frame("ac000100090300010101040132360185"))
    assert [record.domain.name for record in complete.parsed.records] == ["power", "brightness", "zone_enable"]
    assert complete.parsed.records[-1].body.source_1_enabled
    collector = BulkStatusCollector("H1771")
    rejected = collector.feed(frame("ac0001000503003601850402"))
    assert rejected.parsed is None and collector.failed


def test_candidate_bulk_collector_rejects_duplicate_identity_selectors():
    collector = BulkStatusCollector("H1771")
    record = bytes.fromhex("070d11010203040506010009010204")
    payload = record * 2
    collector.feed(frame("ac000300010300" + payload[:12].hex()))
    collector.feed(frame("ac01" + payload[12:29].hex()))
    result = collector.feed(frame("acff" + payload[29:].hex()))
    assert result.parsed is None and collector.failed


async def test_candidate_bulk_and_notification_update_independent_sources(hass):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H617A", configuration_url=None)
    coordinator.model = "H1771"
    coordinator.profile = BULK_PROFILE
    coordinator._bulk_collector = BulkStatusCollector("H1771")
    coordinator._bulk_query_incomplete = True
    coordinator._notify_callback(None, bytearray(frame("ac000100090300010101040132360185")))
    assert coordinator.is_on and coordinator.brightness_pct == 50
    assert coordinator.boolean_control_state == {"source_0_enabled": False, "source_1_enabled": True}
    coordinator._notify_callback(None, bytearray(frame("ee300103")))
    assert coordinator.is_on
    assert coordinator.boolean_control_state == {"source_0_enabled": True, "source_1_enabled": False}


async def test_candidate_bulk_rejects_conflicting_master_flags_atomically(hass):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H617A", configuration_url=None)
    coordinator.model = "H1771"
    coordinator.profile = BULK_PROFILE
    coordinator._bulk_collector = BulkStatusCollector("H1771")
    coordinator._bulk_query_incomplete = True
    coordinator._notify_callback(None, bytearray(frame("ac000100060300010101360100")))
    assert not coordinator._field_revisions and not coordinator.boolean_control_state
    assert coordinator._bulk_query_incomplete


async def test_candidate_bulk_identity_versions_are_redacted_and_applied_atomically(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H617A", configuration_url=None)
    coordinator.model = "H1771"
    coordinator.profile = IDENTITY_PROFILE
    coordinator._bulk_collector = BulkStatusCollector("H1771")
    coordinator._bulk_query_incomplete = True
    coordinator._client = MagicMock(is_connected=True)
    monkeypatch.setattr(coordinator, "_authorization_identity_fields", lambda: frozenset({"fw_version", "hw_version"}))
    main = bytes.fromhex("07111001020304050607080107000308010000")
    wireless = bytes.fromhex("070d11010203040506010009010204")
    payload = main + wireless
    packets = (
        frame("ac000300050300" + payload[:12].hex()),
        frame("ac01" + payload[12:29].hex()),
        frame("acff" + payload[29:].hex()),
    )
    for packet in packets[:-1]:
        coordinator._notify_callback(None, bytearray(packet))
        assert coordinator.fw_version is None and coordinator.hw_version is None
    coordinator._notify_callback(None, bytearray(packets[-1]))
    assert (coordinator.fw_version, coordinator.hw_version) == ("1.07.00", "3.08.01")
    assert (coordinator.wireless_firmware_version, coordinator.wireless_hardware_version) == ("1.00.09", "1.02.04")
    assert coordinator.subordinate_20_version is None and coordinator.subordinate_21_version is None
    assert coordinator.identity_fields_confirmed()
    coordinator._confirmed_identity_fields.clear()
    assert coordinator._identity_field_incomplete("fw_version")
    assert coordinator._identity_field_incomplete("hw_version")
    assert all(entry["redacted"] and not entry["raw"] for entry in coordinator.packet_log[-3:])
    baseline = coordinator._domain_revisions[ReadDomain.FIRMWARE]
    coordinator._bulk_collector = BulkStatusCollector("H1771")
    coordinator._bulk_query_incomplete = True
    for packet in packets:
        coordinator._notify_callback(None, bytearray(packet))
    assert coordinator.identity_fields_confirmed()
    assert coordinator._domain_revisions[ReadDomain.FIRMWARE] > baseline


async def test_candidate_identity_queries_use_bulk_path(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H617A", configuration_url=None)
    coordinator.profile = IDENTITY_PROFILE
    coordinator._client = MagicMock(is_connected=True)
    monkeypatch.setattr(coordinator, "_async_read_bulk_status", AsyncMock(return_value=True))
    await coordinator._send_identity_queries()
    coordinator._async_read_bulk_status.assert_awaited_once()
    assert coordinator._async_read_bulk_status.await_args.kwargs["domains"] == ()


@pytest.mark.parametrize("kelvin", [2200, 4000])
async def test_candidate_kelvin_verification_reads_the_ordinary_mode_reply(hass, monkeypatch, kelvin):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H1771", configuration_url=None)
    coordinator.is_on = True
    client = MagicMock(is_connected=True)
    coordinator._client = client
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(coordinator, "_renew_foreground_lease", MagicMock())
    light = GoveeBLELight(coordinator)
    monkeypatch.setattr(light, "_async_supersede_preview", AsyncMock())
    monkeypatch.setattr(light, "_notify_state_changed", MagicMock())

    async def write(_uuid, packet, **_kwargs):
        if packet == frame("aa0501"):
            coordinator._notify_callback(None, bytearray(frame(f"aa051500{kelvin:04x}")))

    client.write_gatt_char = AsyncMock(side_effect=write)
    await light.async_turn_on(color_temp_kelvin=kelvin)
    assert coordinator.color_temp_kelvin == kelvin and coordinator.color_temp_kelvin_source == "observed"
    assert coordinator.color_mode is ParsedMode.COLOUR
    assert client.write_gatt_char.await_args.args[1] == frame("aa0501")
    assert sum(call.args[1][0] == 0x33 for call in client.write_gatt_char.await_args_list) == 1


@pytest.fixture
def effect_connection(hass, monkeypatch, virtual_clock):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H1771", configuration_url=None)
    client = MagicMock(is_connected=True, disconnect=AsyncMock())
    coordinator._client = client
    coordinator._notification_token = object()
    coordinator._notify_started_monotonic = virtual_clock.virtual_time()
    coordinator._static_rgb_known = True
    coordinator.color_mode = ParsedMode.COLOUR
    coordinator.static_gradual = False
    coordinator.rgb_color = (255, 0, 0)
    coordinator.segment_colors = [(255, 0, 0)] * 4
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    replies = {
        frame("aa01"): frame("aa0101"),
        frame("aa04"): frame("aa0432"),
        frame("aa0501"): frame("aa0515000000"),
        frame("aaa501"): frame("aaa50164ff000064ff000064ff000064ff0000"),
        frame("ac030236a3"): frame("ac000100060300360107a30101"),
    }
    writes = []

    async def write(_uuid, packet, **_kwargs):
        writes.append(packet)
        if reply := replies.get(packet):
            coordinator._notify_callback(None, bytearray(reply))

    client.write_gatt_char = AsyncMock(side_effect=write)
    return coordinator, writes, replies


@pytest.mark.parametrize("preview", [False, True])
async def test_effect_preparation_reads_required_sources_without_unrelated_bulk_domains(effect_connection, preview):
    coordinator, writes, _replies = effect_connection
    assert await async_prepare_effect_control_state(coordinator, require_restorable_static=preview)
    prior = coordinator.capture_effect_control_state()
    assert prior.source_0_enabled is True and prior.source_1_enabled is True
    assert prior.brightness_pct == 50
    assert prior.static_gradual is True
    assert frame("ac030236a3") in writes
    assert all(packet[0] != 0x33 for packet in writes)
    if preview:
        assert prior.static_rgb_known
        assert prior.segment_colors == ((255, 0, 0),) * 4


@pytest.mark.parametrize("missing", ["aa04", "ac030236a3"])
async def test_effect_preparation_rejects_cached_required_fields_without_writes(effect_connection, missing):
    coordinator, writes, replies = effect_connection
    coordinator.boolean_control_state.update(source_0_enabled=True, source_1_enabled=True)
    coordinator._mark_received(ReadDomain.OTHER, "boolean_source_0_enabled", "boolean_source_1_enabled")
    del replies[frame(missing)]
    with pytest.raises(RuntimeError, match="Could not read current"):
        await async_prepare_effect_control_state(coordinator, require_restorable_static=True)
    assert all(packet[0] != 0x33 for packet in writes)


@pytest.mark.parametrize(
    ("preview", "mode", "reply"),
    [(False, "scene", "aa05043412"), (True, "music", "aa05135100")],
)
async def test_nonstatic_effect_preparation_does_not_require_gradual(effect_connection, preview, mode, reply):
    coordinator, writes, replies = effect_connection
    replies[frame("aa0501")] = frame(reply)
    replies[frame("ac030136")] = frame("ac000100030300360107")
    del replies[frame("ac030236a3")]

    assert await async_prepare_effect_control_state(coordinator, require_restorable_static=preview)
    prior = coordinator.capture_effect_control_state()
    assert prior.mode == mode and prior.static_gradual is None
    assert prior.source_0_enabled is True and prior.source_1_enabled is True
    assert frame("ac030236a3") not in writes


async def test_effect_preparation_rejects_resident_mode_change_between_reads(effect_connection):
    coordinator, writes, replies = effect_connection
    replies[frame("aa0501")] = frame("aa05043412")
    replies[frame("ac030136")] = frame("ac000100030300360107")
    write = coordinator._client.write_gatt_char.side_effect
    mode_reads = 0

    async def change_mode(uuid, packet, **kwargs):
        nonlocal mode_reads
        if packet == frame("aa0501"):
            mode_reads += 1
            if mode_reads == 2:
                replies[packet] = frame("aa050d000000")
        await write(uuid, packet, **kwargs)

    coordinator._client.write_gatt_char.side_effect = change_mode
    with pytest.raises(RuntimeError, match="mode or subscription changed"):
        await async_prepare_effect_control_state(coordinator, require_restorable_static=True)
    assert all(packet[0] != 0x33 for packet in writes)


async def test_effect_preparation_read_budget_starts_after_connection_setup(effect_connection):
    coordinator, _writes, _replies = effect_connection
    prepared = False

    async def ensure_connected():
        nonlocal prepared
        if not prepared:
            await asyncio.sleep(STATE_QUERY_TIMEOUT + 1)
            prepared = True
        return coordinator._client

    coordinator._ensure_connected.side_effect = ensure_connected
    assert await async_prepare_effect_control_state(coordinator, require_restorable_static=True)


async def test_effect_preparation_rejects_replaced_subscription(effect_connection):
    coordinator, writes, _replies = effect_connection
    write = coordinator._client.write_gatt_char.side_effect

    async def replace_subscription(uuid, packet, **kwargs):
        await write(uuid, packet, **kwargs)
        if packet == frame("ac030236a3"):
            coordinator._notification_token = object()

    coordinator._client.write_gatt_char.side_effect = replace_subscription
    with pytest.raises(RuntimeError, match="Could not read current"):
        await async_prepare_effect_control_state(coordinator, require_restorable_static=True)
    assert all(packet[0] != 0x33 for packet in writes)


@pytest.mark.parametrize("source", ["saved", "preview", "preview_rgb"])
async def test_music_effect_uses_fresh_preparation_without_replaying_upload(
    hass, monkeypatch, effect_connection, source
):
    from custom_components.ha_govee_led_ble.effect_deployments import DeploymentPhase, EffectDeploymentRepository
    from custom_components.ha_govee_led_ble.effect_preview import PreviewPhase
    from custom_components.ha_govee_led_ble.effect_runtime import EffectDeploymentEngine
    from tests.storage_test_double import InMemoryVersionedDocumentStore
    from tests.test_effect_preview import _manager, _open

    coordinator, writes, replies = effect_connection
    if source == "preview_rgb":
        coordinator.is_on = True
        coordinator.color_mode = ParsedMode.MUSIC
        coordinator._static_rgb_known = False
        coordinator.segment_state_source = "initial"
        light = GoveeBLELight(coordinator)
        monkeypatch.setattr(light, "_async_supersede_preview", AsyncMock())
        monkeypatch.setattr(light, "_notify_state_changed", MagicMock())
        monkeypatch.setattr(coordinator, "_renew_foreground_lease", MagicMock())
        await light.async_turn_on(rgb_color=(255, 0, 0))
        assert coordinator.segment_state_source == "optimistic"
        writes.clear()
    item = LibraryItem.new("Saved Flowing", MusicProfile("H1771", "flowing", 0))
    compiled = compile_application(item, "H1771")
    write = coordinator._client.write_gatt_char.side_effect

    async def acknowledge(uuid, packet, **kwargs):
        await write(uuid, packet, **kwargs)
        if packet == compiled.packets[-2]:
            coordinator._notify_callback(None, bytearray(frame("a341ff00")))
        elif packet == compiled.packets[-1]:
            replies[frame("aa0501")] = frame("aa05135100")
            coordinator._notify_callback(None, bytearray(frame("330500")))

    coordinator._client.write_gatt_char.side_effect = acknowledge
    if source == "saved":
        repository = EffectDeploymentRepository(InMemoryVersionedDocumentStore())
        await repository.async_load()
        result = await EffectDeploymentEngine(repository).async_apply_saved(
            coordinator, item, config_entry_id="entry-a", updated_at="2026-11-14T00:00:00Z"
        )
        assert result.phase is DeploymentPhase.CONFIRMED
    else:
        manager, _cache = await _manager(hass, monkeypatch, coordinator)
        owner = object()
        events = []
        session = _open(manager, owner, events)
        try:
            await manager.async_queue_snapshot(
                session_id=session,
                owner=owner,
                config_entry_id="entry-a",
                sequence=1,
                updated_at="2026-11-14T00:00:00Z",
                item=item,
            )
            await manager.async_wait_idle("entry-a")
            assert events[-1].phase is PreviewPhase.CONFIRMED
        finally:
            await manager.async_shutdown()
    assert [packet for packet in writes if packet[0] in (0x33, 0xA3)] == list(compiled.packets)
    assert coordinator.music_mode == "flowing"
    assert coordinator.music_sensitivity == 0


@pytest.mark.parametrize(
    ("selector", "kelvin", "reason"), [("7f", 2200, "unknown_selector"), ("15", 4000, "expectation_mismatch")]
)
async def test_failed_kelvin_retains_causal_diagnostics_after_packet_history_moves_on(
    hass, monkeypatch, effect_connection, selector, kelvin, reason
):
    coordinator, writes, replies = effect_connection
    coordinator.is_on = True
    replies[frame("aa0501")] = frame(f"aa05{selector}00{kelvin:04x}")
    light = GoveeBLELight(coordinator)
    monkeypatch.setattr(light, "_async_supersede_preview", AsyncMock())
    monkeypatch.setattr(light, "_notify_state_changed", MagicMock())
    monkeypatch.setattr(coordinator, "_renew_foreground_lease", MagicMock())
    await light.async_turn_on(color_temp_kelvin=2200)
    failure = coordinator._last_control_failure
    assert failure["reason"] == "verification_unavailable"
    assert failure["requested"] == {"color_temp_kelvin": 2200}
    assert failure["mode_observation"]["selector"] == int(selector, 16)
    assert failure["mode_observation"]["reason"] == reason
    assert failure["mode_observation"]["kelvin"] == (None if selector == "7f" else kelvin)
    assert failure["profile"]["status_grammar"] == "H1771"

    coordinator.color_temp_kelvin = 9000
    coordinator._last_mode_observation = {}
    for _ in range(60):
        coordinator._notify_callback(None, bytearray(frame("aa0101")))
    count = len(writes)
    entry = MockConfigEntry(domain="ha_govee_led_ble", data={})
    entry.runtime_data = coordinator
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["coordinator"]["last_control_failure"] == failure
    assert len(writes) == count
    assert "11:22:33:44:55:66" not in json.dumps(diagnostics)


async def test_live_rejection_keeps_qualified_recovery_context_without_writing(hass, monkeypatch, effect_connection):
    from custom_components.ha_govee_led_ble.effect_preview import PreviewPhase
    from tests.test_effect_preview import _manager, _open

    coordinator, writes, _replies = effect_connection
    coordinator._static_rgb_known = False
    manager, _cache = await _manager(hass, monkeypatch, coordinator)
    owner = object()
    events = []
    session = _open(manager, owner, events)
    try:
        await manager.async_queue_snapshot(
            session_id=session,
            owner=owner,
            config_entry_id="entry-a",
            sequence=1,
            updated_at="2026-11-14T00:00:00Z",
            item=LibraryItem.new("Flowing", MusicProfile("H1771", "flowing", 0)),
        )
        await manager.async_wait_idle("entry-a")
        assert events[-1].phase is PreviewPhase.FAILED
        history = manager._diagnostics.snapshot(config_entry_id="entry-a")["events"]
        failure = next(event for event in history if event["code"] == "preview_preparation_failed")
        context = failure["details"]["control_state"]
        assert context["reason"] == "ambiguous_static_intent"
        assert context["mode_observation"] == {
            "selector": 0x15,
            "mode": "colour",
            "kelvin": None,
            "accepted": True,
            "reason": "accepted",
        }
        assert context["state"]["static_rgb_known"] is False
        assert context["observations"]["color_mode"]["current_subscription"] is True
        assert context["sources"]["source_0_enabled"] is True
        assert context["source_generations"]["source_0_enabled"] == [
            coordinator._power_write_generation,
            coordinator._profile_generation,
        ]
        assert not any(packet[0] in (0x33, 0xA3) for packet in writes)
    finally:
        await manager.async_shutdown()


async def test_candidate_full_refresh_reads_mode_and_native_settings(hass):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H1771", configuration_url=None)
    client = MagicMock(is_connected=True)
    coordinator._client = client
    bulk = build_bulk_status_query(coordinator.profile)
    replies = {
        frame("aa01"): frame("aa0101"),
        frame("aa04"): frame("aa0432"),
        frame("aa0501"): frame("aa050d010fa0"),
        frame("aaa501"): frame("aaa501640102036404050664070809640a0b0c"),
        bulk: frame("ac0001000a0300360107a3010141020000"),
    }

    async def write(_uuid, packet, **_kwargs):
        coordinator._notify_callback(None, bytearray(replies[packet]))

    client.write_gatt_char = AsyncMock(side_effect=write)
    assert await coordinator._send_state_queries()
    assert coordinator.color_temp_kelvin == 4000
    assert coordinator.boolean_control_state == {
        "source_0_enabled": True,
        "source_1_enabled": True,
        "gradual": True,
    }
    assert coordinator.power_on_behaviour == "previous"


@pytest.mark.parametrize(
    ("control", "record"),
    [("source_0_enabled", "360103"), ("gradual", "a30101")],
)
async def test_candidate_setting_requires_fresh_bulk_confirmation(hass, monkeypatch, control, record):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H617A", configuration_url=None)
    coordinator.model = "H1771"
    coordinator.profile = BULK_PROFILE
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    coordinator._client = client
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    query = build_boolean_control_query(control, "H1771", profile=BULK_PROFILE)

    async def respond(_uuid, packet, **_kwargs):
        if packet == query:
            coordinator._notify_callback(None, bytearray(frame(f"ac000100030300{record}")))

    client.write_gatt_char.side_effect = respond
    await coordinator.async_set_boolean_control(control, True)
    assert coordinator.boolean_control_state[control] is True
    assert coordinator._field_revisions[f"boolean_{control}"] == 1


@pytest.mark.parametrize(("calm", "style"), [(True, 0), (False, 1)])
def test_candidate_music_upload_precedes_selector_and_preserves_style(calm, style):
    packets = prepare_music_request("H1771", "rhythm", 50, None, calm, {}, profile=MUSIC_PROFILE, palette=((1, 2, 3),))
    assert packets[0] == frame("330101")
    assert packets[-1] == frame("3305130432")
    for packet in packets:
        require_profile_packet(packet, MUSIC_PROFILE)
    envelope = reassemble_a3(packets[1:-1])
    assert envelope.startswith(bytes((1, len(packets) - 2, 0x41, 4, 1, 1, 2, 3, style)))
    body = bytes((4, 1, 1, 2, 3, style))
    assert music_body_style(body, "rhythm", profile=MUSIC_PROFILE) is calm
    assert validate_music_body(body, "rhythm", profile=MUSIC_PROFILE).tail.style == style


def test_candidate_music_ack_does_not_assume_mode_echo():
    parsed = parse_command_ack_result(frame("a341ff00"), "H1771", profile=MUSIC_PROFILE).parsed
    assert parsed is not None
    assert upload_ack_success(parsed, 0x41, protocol=0xA3) is True
    failed = parse_command_ack_result(frame("a341aa01"), "H1771", profile=MUSIC_PROFILE).parsed
    assert failed is not None
    assert upload_ack_success(failed, 0x41, protocol=0xA3) is False


@pytest.mark.parametrize(("status", "success"), [(0, True), (1, False)])
def test_candidate_diy_ack_uses_status_after_unqualified_byte(status, success):
    parsed = parse_command_ack_result(frame(f"a358ab{status:02x}"), "H1771", profile=SCENE_PROFILE).parsed
    assert parsed is not None
    assert upload_ack_success(parsed, 0x58, protocol=0xA3) is success


@pytest.mark.parametrize("scene_type", [0, 2, 5])
def test_candidate_catalogue_scene_upload_and_activation(scene_type):
    path = Path(__file__).parents[1] / "custom_components/ha_govee_led_ble/scene_catalogues/H1771.json"
    catalogue = json.loads(path.read_text(encoding="utf-8"))
    entry = next(item for item in catalogue["effects"] if item["scene_type"] == scene_type)
    scene = SceneEntry(
        code=entry["code"],
        param=entry.get("param", ""),
        scene_type=scene_type,
        diy_effect_codes=tuple(entry.get("diy_effect_codes", ())),
    )
    packets = build_native_scene_packets("H1771", scene, profile=SCENE_PROFILE)
    assert packets[-1] == frame("330504" + scene.code.to_bytes(2, "little").hex())
    for packet in packets:
        require_profile_packet(packet, SCENE_PROFILE)
    if scene_type in (0, 5):
        assert len(packets) == 1
    else:
        envelope = reassemble_a3(packets[:-1])
        assert parse_a3_effect_envelope(envelope, "H1771", profile=SCENE_PROFILE) is not None


def test_candidate_layered_scene_speed_changes_upload_not_selector():
    path = Path(__file__).parents[1] / "custom_components/ha_govee_led_ble/scene_catalogues/H1771.json"
    catalogue = json.loads(path.read_text(encoding="utf-8"))
    entry = next(item for item in catalogue["effects"] if item.get("speed"))
    speed = _load_speed(entry["speed"])
    assert speed is not None
    scene = SceneEntry(code=entry["code"], param=entry["param"], scene_type=2, speed=speed)
    slow = build_native_scene_packets("H1771", scene, speed_index=0, profile=SCENE_PROFILE)
    fast = build_native_scene_packets("H1771", scene, speed_index=speed.option_count - 1, profile=SCENE_PROFILE)
    assert slow[-1] == fast[-1]
    assert reassemble_a3(slow[:-1]) != reassemble_a3(fast[:-1])


def test_candidate_native_diy_roundtrips_all_catalogue_bodies():
    path = Path(__file__).parents[1] / "custom_components/ha_govee_led_ble/scene_catalogues/H1771.json"
    catalogue = json.loads(path.read_text(encoding="utf-8"))
    for entry in catalogue["effects"]:
        if entry["scene_type"] == 5:
            body = base64.b64decode(entry["param"])[1:]
            content = decode_h1771_diy(body)
            assert encode_h1771_diy(native_effect_from_value(native_effect_to_value(content))) == body


def test_candidate_authored_native_scene_retains_catalogue_wrapper_for_upload():
    path = Path(__file__).parents[1] / "custom_components/ha_govee_led_ble/scene_catalogues/H1771.json"
    entry = next(item for item in json.loads(path.read_text(encoding="utf-8"))["effects"] if item["scene_type"] == 5)
    original = base64.b64decode(entry["param"])
    reference = CatalogueRef("H1771", entry["scene_id"], entry["effect_id"])
    content = decode_native_scene(reference, original, family=957)
    scene = SceneEntry(code=entry["code"], param=entry["param"], scene_type=5, diy_effect_codes=(957,))
    body, speed = encode_authored_scene_body(content, scene)
    assert body == original and speed is None
    assert len(build_native_scene_packets("H1771", scene, canonical_body=body, profile=SCENE_PROFILE)) == 1
    first = content.layers[0]
    assert isinstance(first, NativeDiyLayer)
    content = replace(content, layers=(replace(first, speed=(first.speed + 1) % 101), content.layers[1]))
    body, speed = encode_authored_scene_body(content, scene)
    assert body != original and speed is None
    upload = build_native_scene_packets("H1771", scene, canonical_body=body, profile=SCENE_PROFILE)
    assert reassemble_a3(upload[:-1])[3:].startswith(body[1:])
    item = LibraryItem(
        id=UUID(int=1),
        version=1,
        updated_at="2026-01-01T00:00:00+00:00",
        name="Edited scene",
        content=content,
        origin=Origin(SourceKind.IMPORTED, "test"),
    )
    compiled = compile_effect(item, "H1771")
    assert reassemble_a3(compiled.upload_packets)[3:].startswith(body[1:])
    assert DIY_ACK_EVIDENCE in compiled.evidence_codes and compiled.upload_subtype == 0x58
    assert compiled.activation_packet == upload[-1]


def test_candidate_unmodified_native_scene_does_not_require_upload_ack():
    entry = next(scene for scene in MODEL_SCENES["H1771"].values() if scene.display_name == "Dreamland")
    reference = CatalogueRef("H1771", entry.scene_id, entry.effect_id)
    content = _scene_content(entry, reference, None, None)
    compiled = compile_effect(LibraryItem.new("Scene", content), "H1771")
    assert not compiled.upload_packets and compiled.upload_subtype is None
    assert DIY_ACK_EVIDENCE not in compiled.evidence_codes
    assert compiled.activation_packet is not None


@pytest.mark.parametrize(("name", "scene_type"), [("Forest", 2), ("Dreamland", 5)])
def test_candidate_scene_workspace_retains_catalogue_identity(name, scene_type):
    entry = next(scene for scene in MODEL_SCENES["H1771"].values() if scene.display_name == name)
    assert entry.scene_type == scene_type
    reference = CatalogueRef("H1771", entry.scene_id, entry.effect_id)
    content = _scene_content(entry, reference, None, None)
    if isinstance(content, NativeEffect):
        first = content.layers[0]
        assert isinstance(first, NativeDiyLayer)
        content = replace(content, layers=(replace(first, speed=(first.speed + 1) % 101), content.layers[1]))
    item = LibraryItem.new("Scene", content)
    compiled = compile_effect(item, "H1771")
    assert compiled.upload_packets
    restored = _active_workspace_content(content, compiled)
    assert restored.template == reference
    rebuilt = compile_effect(LibraryItem.new("Restored", restored), "H1771")
    assert rebuilt.activation_packet == compiled.activation_packet


def test_candidate_catalogue_diy_templates_compile_and_upload():
    templates = MODEL_EFFECT_CATALOGUES["H1771"].templates
    for template in templates:
        if not isinstance(template.content, NativeEffect):
            continue
        item = LibraryItem(
            id=UUID(int=1),
            version=1,
            updated_at="2026-01-01T00:00:00+00:00",
            name="Test",
            content=template.content,
            origin=Origin(SourceKind.IMPORTED, "test"),
        )
        compiled = compile_effect(item, "H1771")
        parsed = parse_a3_effect_envelope(reassemble_a3(compiled.upload_packets), "H1771")
        assert parsed.kind.name == "native_diy"
        assert decode_h1771_diy(encode_h1771_diy(template.content)) == template.content
        assert compiled.activation_packet == frame("33050afe00")
        if parsed.body.unknown_tail:
            with pytest.raises(UnsupportedA3EffectError, match="transport fill"):
                decode_effect_frames(compiled.upload_packets, "H1771", compiled.upload_transport)


def test_candidate_basic_and_advanced_diy_section_layouts():
    templates = MODEL_EFFECT_CATALOGUES["H1771"].templates
    basic = next(template.content for template in templates if template.id == "template:h1771:1:1")
    advanced = next(template.content for template in templates if template.id == "template:h1771:0:0")
    assert isinstance(basic, NativeEffect) and isinstance(advanced, NativeEffect)
    assert encode_h1771_diy(basic) == bytes.fromhex("19000a0001043202ff000000ff000b000101320102ff000000ff00")
    assert encode_h1771_diy(advanced) == bytes.fromhex("0b00060001013264a406010000")


@pytest.mark.parametrize(
    "second",
    [
        NativeDiyLayer(1, 25, ((1, 2, 3),), parameter=2, opaque=b"\xaa"),
        NativeDiyLayer(6, 25, ((1, 2, 3),)),
        NativeDiyLayer(7, 25, ((1, 2, 3),), parameter=2, flag=3),
        NativeDiyLayer(8, 25, ((1, 2, 3),), secondary_palette=((4, 5, 6),)),
        NativeDiyLayer(15, 25, (), parameter=50, angle=2700),
        NativeOpaqueLayer(99, bytes.fromhex("0163aabb")),
    ],
)
def test_candidate_native_diy_retains_sections_and_unknown_extensions(second):
    content = NativeEffect(
        model="H1771",
        family=957,
        layers=(NativeDiyLayer(0, 0, (), enabled=False, opaque=b"\x00\xab"), second),
        section_tail=b"\xcd",
        opaque=b"\xef",
    )
    body = encode_h1771_diy(content)
    assert decode_h1771_diy(body) == content
    assert encode_h1771_diy(decode_h1771_diy(body)) == body
